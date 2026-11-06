from __future__ import annotations

import hashlib, logging, os, shutil, stat, tempfile, time
from pathlib import Path
from typing import Any
from app.core.classifier import Categorizer
from app.core.history import HistoryStore
from app.core.safety import exclusion_reason, has_link_component, is_link_like, is_within, wait_until_stable

LOG = logging.getLogger("organizepro.organizer")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while chunk:=stream.read(chunk_size): digest.update(chunk)
    return digest.hexdigest()


def unique_path(destination: Path) -> Path:
    if not destination.exists(): return destination
    name=destination.name; lowered=name.casefold()
    compound=next((ext for ext in (".tar.gz",".tar.bz2",".tar.xz",".tar.zst") if lowered.endswith(ext)),None)
    extension=compound or destination.suffix; stem=name[:-len(extension)] if extension else name; index=1
    while True:
        candidate=destination.with_name(f"{stem} ({index}){extension}")
        if not candidate.exists(): return candidate
        index+=1


class FileOrganizer:
    def __init__(self, settings_provider, history: HistoryStore):
        self.settings_provider=settings_provider; self.history=history

    def _paths(self, settings: dict[str, Any]) -> tuple[Path,Path]:
        source_input=Path(settings.get("source_dir") or "").expanduser()
        use_custom=bool(settings.get("use_custom_destination",False))
        destination_value=str(settings.get("destination_dir") or "").strip() if use_custom else ""
        destination_input=Path(destination_value).expanduser() if destination_value else source_input
        if is_link_like(source_input) or (use_custom and is_link_like(destination_input)): raise ValueError("Source and destination directories cannot be symbolic links.")
        source=source_input.resolve(strict=True); destination=destination_input.resolve(strict=False)
        if not source.is_dir(): raise ValueError("Source directory does not exist or is not a directory.")
        if use_custom and (source==destination or is_within(source,destination)): raise ValueError("Source and destination must be different; source cannot be inside destination.")
        return source,destination

    def plan(self,path:Path,*,root:Path|None=None,settings:dict[str,Any]|None=None)->dict[str,Any]:
        cfg=settings or self.settings_provider(); src_root,dest_root=self._paths(cfg)
        if is_link_like(path): return {"action":"skip","reason":"Symbolic links and junctions are not processed","source_path":str(path),"destination_path":"","category":None}
        if has_link_component(path.parent,src_root): return {"action":"skip","reason":"Files inside symbolic-link directories are not processed","source_path":str(path),"destination_path":"","category":None}
        path=path.resolve(strict=True); root=root or src_root; in_place=dest_root==src_root
        if in_place:
            try:
                relative=path.relative_to(src_root); category_names={str(x.get("name","")).casefold() for x in cfg.get("categories",[])}
                if relative.parts and relative.parts[0].casefold() in category_names: return {"action":"skip","reason":"OrganizePro output category folder","source_path":str(path),"destination_path":"","category":None}
            except (OSError,ValueError): pass
        reason=exclusion_reason(path,root,None if in_place else dest_root,cfg)
        if reason: return {"action":"skip","reason":reason,"source_path":str(path),"destination_path":"","category":None}
        categorizer=Categorizer(cfg.get("categories",[]),cfg.get("ignored_extensions",[])); category=categorizer.category_for(path)
        if category is None and cfg.get("unknown_file_handling")=="move_to_unknown" and any(str(x.get("name","")).casefold()=="unknown" and x.get("enabled",True) for x in cfg.get("categories",[])): category="Unknown"
        if category is None: return {"action":"skip","reason":"No category rule matched; unknown files are left untouched","source_path":str(path),"destination_path":"","category":None}
        category_dir=dest_root/category
        if has_link_component(category_dir,dest_root): return {"action":"skip","reason":"Destination category path contains a symbolic link or junction","source_path":str(path),"destination_path":"","category":category}
        target=category_dir/path.name
        if is_link_like(target): return {"action":"skip","reason":"Destination filename is a symbolic link or junction","source_path":str(path),"destination_path":str(target),"category":category}
        strategy=cfg.get("collision_strategy","rename")
        if target.exists():
            if strategy=="skip": return {"action":"skip","reason":"A file with this name already exists","source_path":str(path),"destination_path":str(target),"category":category}
            if strategy=="content" or (strategy=="rename" and cfg.get("duplicate_handling","skip_identical")=="skip_identical"):
                try:
                    if target.is_file() and path.stat().st_size==target.stat().st_size and file_sha256(path)==file_sha256(target): return {"action":"skip","reason":"Identical content already exists at destination","source_path":str(path),"destination_path":str(target),"category":category,"duplicate":True}
                except OSError as exc: return {"action":"skip","reason":f"Could not compare files: {exc}","source_path":str(path),"destination_path":str(target),"category":category}
                target=unique_path(target)
            elif strategy=="replace":
                if not cfg.get("allow_replace",False): return {"action":"skip","reason":"Replace is disabled in settings","source_path":str(path),"destination_path":str(target),"category":category}
            else: target=unique_path(target)
        return {"action":"move","reason":f"Matched {category} extension rule","source_path":str(path),"destination_path":str(target),"category":category}

    def move_safely(self,source:Path,destination:Path,*,replace:bool=False,trusted_root:Path|None=None)->Path|None:
        if trusted_root is not None and has_link_component(destination.parent,trusted_root): raise OSError("Destination path contains a symbolic link or junction")
        if is_link_like(destination): raise OSError("Destination is a symbolic link or junction")
        destination.parent.mkdir(parents=True,exist_ok=True)
        if trusted_root is not None and has_link_component(destination.parent,trusted_root): raise OSError("Destination path contains a symbolic link or junction")
        if destination.exists() and not replace: raise FileExistsError(destination)
        fd,staging_name=tempfile.mkstemp(prefix=".organizepro-",suffix=".tmp",dir=destination.parent); os.close(fd); staging=Path(staging_name)
        created_final=False; backup:Path|None=None
        try:
            before=source.lstat()
            if not stat.S_ISREG(before.st_mode): raise OSError("Source is no longer a regular file")
            shutil.copy2(source,staging); after=source.lstat()
            if not stat.S_ISREG(after.st_mode): raise OSError("Source was replaced by a non-regular file during copy")
            if before.st_size!=staging.stat().st_size: raise OSError("Copied file size verification failed")
            ident=lambda x:(x.st_size,x.st_mtime_ns,getattr(x,"st_dev",None),getattr(x,"st_ino",None))
            if ident(before)!=ident(after): raise OSError("Source file changed during copy; original was retained")
            if replace and destination.exists():
                backup=destination.with_name(f"{destination.name}.organizepro-backup-{int(time.time())}")
                if backup.exists(): backup=unique_path(backup)
                os.rename(destination,backup)
                try: self._commit_staging(staging,destination)
                except Exception: os.rename(backup,destination); raise
            else: self._commit_staging(staging,destination)
            created_final=True
            if destination.stat().st_size!=before.st_size: raise OSError("Destination verification failed")
            final_source=source.lstat()
            if not stat.S_ISREG(final_source.st_mode) or ident(before)!=ident(final_source): raise OSError("Source changed before finalization; the original was retained")
            source.unlink(); return backup
        except Exception:
            if created_final:
                try: destination.unlink(missing_ok=True)
                except OSError: LOG.exception("Could not remove failed destination staging file %s",destination)
            if backup is not None and backup.exists() and not destination.exists():
                try: os.rename(backup,destination)
                except OSError: LOG.exception("Could not restore collision backup %s",backup)
            raise
        finally: staging.unlink(missing_ok=True)

    @staticmethod
    def _commit_staging(staging:Path,destination:Path)->None:
        if os.name=="nt": os.rename(staging,destination)
        else: os.link(staging,destination)

    def process_file(self,path:Path,*,event_id:str|None=None,dry_run:bool=False,confirm_replace:bool=False,log_skips:bool=True,stable_verified:bool=False)->dict[str,Any]:
        cfg=self.settings_provider()
        try:
            source_root,dest_root=self._paths(cfg); source_stat=path.lstat()
            if not stat.S_ISREG(source_stat.st_mode): raise ValueError("Source is no longer a regular file")
            plan=self.plan(path,root=source_root,settings=cfg)
            if plan["action"]=="skip":
                if log_skips: self.history.add(operation="skip",status="skipped",filename=path.name,source_path=str(path),destination_path=plan.get("destination_path",""),file_size=source_stat.st_size,category=plan.get("category") or "",reason=plan["reason"],event_id=event_id)
                return plan
            if not stable_verified and not wait_until_stable(path,float(cfg.get("stability_seconds",3.0))):
                reason="File did not become stable and readable before the processing timeout"
                self.history.add(operation="skip",status="skipped",filename=path.name,source_path=str(path),destination_path=plan.get("destination_path",""),file_size=source_stat.st_size,category=plan.get("category") or "",reason=reason,event_id=event_id)
                return {**plan,"action":"skip","reason":reason}
            source_stat=path.lstat()
            if not stat.S_ISREG(source_stat.st_mode): raise ValueError("Source is no longer a regular file")
            destination=Path(plan["destination_path"])
            if dry_run:
                self.history.add(operation="dry_run",status="dry_run",filename=path.name,source_path=str(path),destination_path=str(destination),file_size=source_stat.st_size,category=plan["category"],reason=plan["reason"],event_id=event_id); plan["action"]="dry_run"; return plan
            if cfg.get("collision_strategy")=="replace" and destination.exists() and not confirm_replace:
                plan=dict(plan,action="skip",reason="Replacement requires explicit confirmation")
                self.history.add(operation="skip",status="skipped",filename=path.name,source_path=str(path),destination_path=str(destination),file_size=source_stat.st_size,category=plan["category"],reason=plan["reason"],event_id=event_id); return plan
            if destination.exists() and cfg.get("collision_strategy")=="replace" and not destination.is_file():
                plan=dict(plan,action="skip",reason="The existing destination is not a regular file; replacement was refused")
                self.history.add(operation="skip",status="skipped",filename=path.name,source_path=str(path),destination_path=str(destination),file_size=source_stat.st_size,category=plan["category"],reason=plan["reason"],event_id=event_id); return plan
            if destination.exists() and cfg.get("collision_strategy")!="replace":
                if cfg.get("collision_strategy")=="skip": raise FileExistsError(destination)
                destination=unique_path(destination); plan["destination_path"]=str(destination)
            backup=self.move_safely(path,destination,replace=cfg.get("collision_strategy")=="replace" and destination.exists(),trusted_root=dest_root)
            record=self.history.add(operation="move",status="success",filename=path.name,source_path=str(path),destination_path=str(destination),backup_path=str(backup) if backup else "",file_size=source_stat.st_size,category=plan["category"],reason=plan["reason"],event_id=event_id)
            plan.update(action="move",destination_path=str(destination),history_id=record["id"]); return plan
        except Exception as exc:
            LOG.exception("File processing failed: %s",path)
            self.history.add(operation="error",status="failed",filename=path.name,source_path=str(path),destination_path="",file_size=0,category="",reason="File processing failed",error=str(exc),event_id=event_id)
            return {"action":"error","reason":str(exc),"source_path":str(path),"destination_path":""}

    def scan(self,*,recursive:bool|None=None,preview_only:bool=True)->list[dict[str,Any]]:
        cfg=self.settings_provider(); root,destination=self._paths(cfg); recursive=cfg.get("recursive",False) if recursive is None else recursive; entries=[]
        if recursive:
            for current,dirs,files in os.walk(root,followlinks=False):
                current_path=Path(current)
                dirs[:]=[d for d in dirs if d.casefold() not in {x.casefold() for x in cfg.get("excluded_dirs",[])} and not is_link_like(current_path/d) and not (destination==current_path/d or is_within(destination,current_path/d))]
                entries.extend(current_path/name for name in files)
        else:
            try:
                with os.scandir(root) as iterator: entries.extend(Path(item.path) for item in iterator if item.is_file(follow_symlinks=False))
            except OSError: return []
        results=[]
        for path in sorted(entries,key=lambda p:str(p).casefold()):
            try:
                result=self.plan(path,root=root,settings={**cfg,"recursive":recursive})
                if result["action"]=="move": results.append(result)
                elif not preview_only: self.process_file(path)
            except (OSError,ValueError): continue
        return results

    def undo(self,record_id:str)->tuple[bool,str]:
        record=self.history.find(record_id)
        if not record or record.get("status")!="success" or record.get("operation")!="move": return False,"A completed move operation was not found."
        source=Path(record["source_path"]); destination=Path(record["destination_path"])
        if is_link_like(destination) or not destination.is_file(): return False,"The destination file is missing, linked, or is not a regular file."
        if source.exists() or is_link_like(source): return False,"The original path is occupied or linked; Undo will not overwrite it."
        backup_value=str(record.get("backup_path") or ""); backup=Path(backup_value) if backup_value else None
        if backup is not None:
            if backup.parent!=destination.parent or not backup.name.startswith(destination.name+".organizepro-backup-"): return False,"The replacement backup path is invalid; Undo was refused."
            if is_link_like(backup) or not backup.is_file(): return False,"The replacement backup is missing or unsafe; Undo was refused."
        try:
            source.parent.mkdir(parents=True,exist_ok=True); self.move_safely(destination,source,trusted_root=Path(source.anchor))
            if backup is not None:
                try: self.move_safely(backup,destination,trusted_root=Path(destination.anchor))
                except Exception:
                    if source.is_file() and not destination.exists(): self.move_safely(source,destination,trusted_root=Path(destination.anchor))
                    raise
            self.history.update_status(record_id,"undone")
            self.history.add(operation="undo",status="success",filename=record["filename"],source_path=str(destination),destination_path=str(source),file_size=int(record.get("file_size",0)),category=record.get("category",""),reason=f"Undo of {record_id}")
            return True,"File restored to its original location."
        except Exception as exc: return False,f"Undo failed: {exc}"
