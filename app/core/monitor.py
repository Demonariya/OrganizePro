from __future__ import annotations

import logging, os, queue, stat, threading, time, uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.core.organizer import FileOrganizer
from app.core.safety import filesystem_identity, has_link_component, is_link_like, structural_exclusion_reason, wait_until_stable

LOG=logging.getLogger("organizepro.monitor")
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE=True
except ImportError:
    FileSystemEventHandler=object
    Observer=None
    WATCHDOG_AVAILABLE=False


@dataclass(frozen=True)
class FileSignature:
    path:str
    size:int
    modified_ns:int
    device:int|None
    inode:int|None
    @classmethod
    def read(cls,path:Path):
        try:
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode): return None
            device,inode=filesystem_identity(info)
            return cls(str(path.resolve()),info.st_size,info.st_mtime_ns,device,inode)
        except OSError: return None
    @property
    def key(self): return (os.path.normcase(self.path),self.size,self.modified_ns,self.device,self.inode)


@dataclass(frozen=True)
class FileEvent:
    event_id:str
    signature:FileSignature
    observed_at:float


class _EventHandler(FileSystemEventHandler):
    def __init__(self,service):
        self.service=service
        if WATCHDOG_AVAILABLE: super().__init__()
    def on_created(self,event):
        if not event.is_directory: self.service.enqueue(Path(event.src_path))
    def on_modified(self,event):
        if not event.is_directory: self.service.enqueue(Path(event.src_path))
    def on_moved(self,event):
        if not event.is_directory: self.service.enqueue(Path(event.dest_path))


class MonitorService:
    def __init__(self,organizer:FileOrganizer,settings_provider):
        self.organizer=organizer; self.settings_provider=settings_provider
        self._queue:queue.Queue[FileEvent]=queue.Queue(maxsize=10000); self._stop=threading.Event(); self._resume=threading.Event(); self._resume.set()
        self._lock=threading.RLock(); self._observer=None; self._processor=None; self._poller=None; self._running=False; self._paused=False; self._started_at=None
        self._baseline={}; self._pending=set(); self._handled=set(); self._handled_order=[]
        self._stats={"queued":0,"processed":0,"success":0,"skipped":0,"failed":0,"baseline_files":0,"backend":"watchdog" if WATCHDOG_AVAILABLE else "polling"}

    @property
    def is_running(self):
        with self._lock: return self._running

    def start(self):
        with self._lock:
            if self._running: return self.status()
            cfg=self.settings_provider(); source_input=Path(cfg.get("source_dir") or "").expanduser(); use_custom=bool(cfg.get("use_custom_destination",False))
            destination_input=Path(str(cfg.get("destination_dir") or "")).expanduser() if use_custom else None
            if is_link_like(source_input) or (destination_input is not None and is_link_like(destination_input)): raise ValueError("Source and destination directories cannot be symbolic links.")
            source=source_input.resolve(strict=True); destination=destination_input.resolve(strict=False) if destination_input is not None else None
            if not source.is_dir() or (destination is not None and (source==destination or _is_under(source,destination))): raise ValueError("Select a valid source directory and, if enabled, a separate destination directory.")
            self._stop.clear(); self._resume.set(); self._discard_queued_events(); self._pending.clear(); self._handled.clear(); self._handled_order=[]
            self._baseline=self._snapshot(source,destination,cfg); self._stats["baseline_files"]=len(self._baseline); self._stats["backend"]="watchdog" if WATCHDOG_AVAILABLE else "polling"; self._started_at=time.time()
            self._processor=threading.Thread(target=self._process_loop,name="OrganizeProProcessor",daemon=True); self._processor.start()
            if WATCHDOG_AVAILABLE:
                try:
                    self._observer=Observer(); self._observer.schedule(_EventHandler(self),str(source),recursive=bool(cfg.get("recursive",False))); self._observer.start()
                    active=self._snapshot(source,destination,cfg)
                    for normalized,key in active.items():
                        if self._baseline.get(normalized)!=key: self.enqueue(Path(normalized))
                except Exception as exc:
                    LOG.warning("Filesystem observer failed; using polling fallback: %s",exc)
                    try:
                        if self._observer: self._observer.stop(); self._observer.join(timeout=2)
                    except Exception: pass
                    self._observer=None; self._stats["backend"]="polling"
            if self._observer is None:
                self._stats["backend"]="polling"; self._poller=threading.Thread(target=self._poll_loop,name="OrganizeProPoller",daemon=True); self._poller.start()
            self._running=True; LOG.info("Monitoring started (%s); baseline contains %d files.",self._stats["backend"],len(self._baseline)); return self.status()

    def pause(self):
        with self._lock:
            if self._running: self._paused=True; self._resume.clear()
    def resume(self):
        with self._lock:
            if self._running: self._paused=False; self._resume.set()
    def restart(self): self.stop(); return self.start()

    def stop(self):
        with self._lock:
            if not self._running: return
            self._stop.set(); self._resume.set(); observer=self._observer; self._observer=None
        if observer:
            try: observer.stop(); observer.join(timeout=5)
            except Exception: LOG.exception("Error stopping filesystem observer")
        for thread in (self._processor,self._poller):
            if thread and thread.is_alive():
                thread.join(timeout=30)
                if thread.is_alive(): LOG.error("Monitoring worker did not stop within 30 seconds: %s",thread.name)
        self._discard_queued_events()
        with self._lock:
            self._running=False; self._paused=False; self._processor=None; self._poller=None; self._started_at=None; self._pending.clear()
        LOG.info("Monitoring stopped")

    def _discard_queued_events(self):
        while True:
            try: event=self._queue.get_nowait()
            except queue.Empty: break
            try:
                with self._lock: self._pending.discard(event.signature.key)
            finally: self._queue.task_done()

    def enqueue(self,path:Path)->bool:
        cfg=self.settings_provider()
        try:
            source_input=Path(cfg.get("source_dir") or "").expanduser(); use_custom=bool(cfg.get("use_custom_destination",False))
            destination_input=Path(str(cfg.get("destination_dir") or "")).expanduser() if use_custom else None
            if is_link_like(path) or is_link_like(source_input) or (destination_input is not None and is_link_like(destination_input)): return False
            source=source_input.resolve(strict=True); destination=destination_input.resolve(strict=False) if destination_input is not None else None
            if has_link_component(path.parent,source): return False
            resolved=path.resolve(strict=True); signature=FileSignature.read(resolved)
            if signature is None: return False
            try: rel=resolved.relative_to(source)
            except ValueError: return False
            if destination is not None and (resolved==destination or _is_under(resolved,destination)): return False
            if destination is None and rel.parts and rel.parts[0].casefold() in {str(x.get("name","")).casefold() for x in cfg.get("categories",[])}: return False
            if structural_exclusion_reason(resolved,rel.parts,cfg,source): return False
            key=signature.key
            with self._lock:
                if key in self._pending or key in self._handled or self._baseline.get(os.path.normcase(signature.path))==key: return False
                self._pending.add(key)
            event=FileEvent(uuid.uuid4().hex,signature,time.monotonic())
            try: self._queue.put(event,timeout=.25)
            except queue.Full:
                with self._lock: self._pending.discard(key)
                LOG.error("File event queue full; dropped %s",resolved); return False
            self._stats["queued"]+=1; return True
        except (OSError,ValueError): return False

    def _snapshot(self,root:Path,destination:Path|None,cfg:dict[str,Any]):
        result={}
        for path in self._iter_files(root,cfg,destination):
            signature=FileSignature.read(path)
            if signature and (destination is None or not _is_under(path,destination)): result[os.path.normcase(signature.path)]=signature.key
        return result

    def _iter_files(self,root,cfg,destination=None):
        excluded={str(x).casefold() for x in cfg.get("excluded_dirs",[])}
        if root.name.casefold() in excluded: return
        if cfg.get("recursive",False):
            for current,dirs,files in os.walk(root,followlinks=False):
                current_path=Path(current)
                dirs[:]=[d for d in dirs if d.casefold() not in excluded and not (destination and _is_under(current_path/d,destination)) and not (destination is None and d.casefold() in {str(x.get("name","")).casefold() for x in cfg.get("categories",[])}) and not is_link_like(current_path/d)]
                for name in files: yield current_path/name
        else:
            try:
                with os.scandir(root) as items:
                    for item in items:
                        try:
                            if item.is_file(follow_symlinks=False): yield Path(item.path)
                        except OSError: continue
            except OSError as exc: LOG.warning("Cannot scan source directory %s: %s",root,exc)

    def _poll_loop(self):
        while not self._stop.is_set():
            self._resume.wait()
            if self._stop.is_set(): break
            cfg=self.settings_provider()
            try:
                root=Path(cfg["source_dir"]).expanduser().resolve(strict=True); dest_value=str(cfg.get("destination_dir") or "").strip() if cfg.get("use_custom_destination",False) else ""; dest=Path(dest_value).expanduser().resolve(strict=False) if dest_value else None
                current=self._snapshot(root,dest,cfg)
                for normalized,key in current.items():
                    if self._baseline.get(normalized)!=key: self.enqueue(Path(normalized))
                for normalized in set(self._baseline)-set(current): self._baseline.pop(normalized,None)
            except Exception: LOG.exception("Polling fallback failed; it will retry")
            self._stop.wait(max(.5,float(cfg.get("polling_interval",2.0))))

    def _process_loop(self):
        while not self._stop.is_set():
            self._resume.wait()
            if self._stop.is_set(): break
            try: event=self._queue.get(timeout=.25)
            except queue.Empty: continue
            key=event.signature.key
            try:
                if self._stop.is_set(): continue
                self._resume.wait()
                if self._stop.is_set(): continue
                if not self._wait_for_stability(Path(event.signature.path)):
                    self._record_skip(Path(event.signature.path),event.event_id,"File did not become stable or readable"); continue
                self._resume.wait()
                if self._stop.is_set(): continue
                current=FileSignature.read(Path(event.signature.path))
                if current is None: continue
                if event.signature.device is not None and event.signature.inode is not None and current.device is not None and current.inode is not None and (event.signature.device,event.signature.inode)!=(current.device,current.inode):
                    self._record_skip(Path(event.signature.path),event.event_id,"File identity changed after the event was observed"); continue
                result=self.organizer.process_file(Path(current.path),event_id=event.event_id,stable_verified=True); self._stats["processed"]+=1
                if result.get("action")=="move":
                    self._stats["success"]+=1; cfg=self.settings_provider()
                    try:
                        from app.desktop.notifications import notify
                        notify("OrganizePro",f"Organized {Path(current.path).name} into {result.get('category','a category')}.",bool(cfg.get("notifications",True)))
                    except Exception: LOG.debug("Could not display a file notification",exc_info=True)
                elif result.get("action")=="error": self._stats["failed"]+=1
                else: self._stats["skipped"]+=1
                self._remember(key)
                if current.key!=key: self._remember(current.key)
                self._baseline.pop(os.path.normcase(current.path),None)
            except Exception: LOG.exception("Unexpected error processing queued event %s",event.event_id); self._stats["failed"]+=1
            finally:
                with self._lock: self._pending.discard(key)
                self._queue.task_done()

    def _wait_for_stability(self,path):
        cfg=self.settings_provider(); return wait_until_stable(path,float(cfg.get("stability_seconds",3.0)),self._stop)
    def _record_skip(self,path,event_id,reason):
        self.organizer.history.add(operation="skip",status="skipped",filename=path.name,source_path=str(path),destination_path="",file_size=0,category="",reason=reason,event_id=event_id); self._stats["skipped"]+=1
    def _remember(self,key):
        with self._lock:
            if key in self._handled: return
            self._handled.add(key); self._handled_order.append(key)
            if len(self._handled_order)>4096: self._handled.discard(self._handled_order.pop(0))
    def status(self):
        with self._lock:
            uptime=max(0,time.time()-self._started_at) if self._started_at else 0
            return {**self._stats,"running":self._running,"paused":self._paused,"uptime_seconds":int(uptime),"pending":self._queue.qsize(),"baseline_files":len(self._baseline)}


def _is_under(path:Path,parent:Path)->bool:
    try: path.resolve().relative_to(parent.resolve()); return True
    except (OSError,ValueError): return False
