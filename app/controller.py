from __future__ import annotations

import logging
import os
import subprocess
import stat
import sys
import time
from pathlib import Path
from typing import Any

from app.config.settings import SettingsStore
from app.core.history import HistoryStore
from app.core.multi_source import MultiSourceMonitor
from app.core.organizer import FileOrganizer
from app.desktop.logger import configure_logging

LOG = logging.getLogger("organizepro.controller")


class ApplicationController:
    def __init__(self, settings: SettingsStore | None = None):
        self.settings = settings or SettingsStore()
        self.started_at = time.time()
        self.log_file = configure_logging(Path(self.settings.get("log_directory") or self.settings.directory / "logs"), self.settings.get("log_level", "INFO"), self.settings.get("log_retention_days", 30))
        self.history = HistoryStore(self.settings.directory, int(self.settings.get("max_history_records", 5000)), int(self.settings.get("log_retention_days", 30)))
        self.organizer = FileOrganizer(self.settings.snapshot, self.history)
        self.monitor = MultiSourceMonitor(self.settings, self.history)

    def start_monitoring(self):
        state = self.settings.snapshot()
        if not state.get("sources") and not state.get("source_dir"):
            raise ValueError("Add at least one source folder in Source Manager.")
        result = self.monitor.start()
        return {"success": True, "status": result, "message": "Monitoring started. Existing files were added to the baseline and will not be moved."}

    def preview_existing(self):
        plans = self.organizer.scan(preview_only=True)
        total_bytes = sum(Path(x["source_path"]).stat().st_size for x in plans if Path(x["source_path"]).exists())
        return {"count": len(plans), "total_bytes": total_bytes, "items": plans, "message": "Preview only. No files were changed."}

    def dry_run_existing(self):
        plans = self.organizer.scan(preview_only=True)
        results = [self.organizer.process_file(Path(x["source_path"]), dry_run=True) for x in plans]
        return {"count": len(results), "items": results, "message": "Dry run complete. No files were moved."}

    def organize_existing(self, *, confirm_replace: bool = False):
        plans = self.organizer.scan(preview_only=True); results = []
        for item in plans:
            path = Path(item["source_path"])
            if path.exists(): results.append(self.organizer.process_file(path, confirm_replace=confirm_replace))
        return {"count": len(results), "organized": sum(r.get("action") == "move" for r in results), "skipped": sum(r.get("action") == "skip" for r in results), "failed": sum(r.get("action") == "error" for r in results), "items": results, "message": "Existing-file organization finished."}

    def apply_runtime_settings(self):
        self.log_file = configure_logging(Path(self.settings.get("log_directory") or self.settings.directory / "logs"), self.settings.get("log_level", "INFO"), self.settings.get("log_retention_days", 30))
        self.history.set_retention_days(int(self.settings.get("log_retention_days", 30)))

    def activity_records(self, *, limit=250, status="all", search=""):
        records = self.history.query(limit=limit, status=status, search=search)
        for record in records:
            record["can_undo"] = False
            if record.get("status") == "success" and record.get("operation") == "move":
                try:
                    original = Path(record.get("source_path", "")); target = Path(record.get("destination_path", "")); info = target.lstat()
                    safe_backup = True; backup_value = str(record.get("backup_path") or "")
                    if backup_value:
                        backup = Path(backup_value); bi = backup.lstat()
                        safe_backup = stat.S_ISREG(bi.st_mode) and backup.parent == target.parent and backup.name.startswith(target.name + ".organizepro-backup-")
                    record["can_undo"] = stat.S_ISREG(info.st_mode) and safe_backup and not original.exists() and not original.is_symlink()
                except OSError: record["can_undo"] = False
        return records

    def dashboard_status(self):
        cfg = self.settings.snapshot(); monitoring = self.monitor.status()
        return {"application":{"name":"OrganizePro","version":"0.0.1","uptime_seconds":int(time.time()-self.started_at)},"monitoring":monitoring,"source_dir":cfg.get("source_dir",""),"sources":self.settings.get("sources",[]),"destination_dir":cfg.get("destination_dir","") if cfg.get("use_custom_destination",False) else "","use_custom_destination":bool(cfg.get("use_custom_destination",False)),"stats":self.history.stats(),"recent_activity":self.history.query(limit=8),"log_file":str(self.log_file)}

    def category_stats(self):
        cfg=self.settings.snapshot(); dest=Path(cfg.get("destination_dir") or cfg.get("source_dir") or "").expanduser() if (cfg.get("destination_dir") or cfg.get("source_dir")) else None
        result=[]
        for category in cfg.get("categories",[]):
            folder=(dest/category["name"]) if dest else None; count=total=0
            try:
                if folder and folder.is_dir():
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            try:
                                if entry.is_file(follow_symlinks=False) and ".organizepro-backup-" not in entry.name:
                                    count+=1; total+=entry.stat(follow_symlinks=False).st_size
                            except OSError: continue
            except OSError: pass
            result.append({**category,"file_count":count,"total_bytes":total,"folder_path":str(folder) if folder else ""})
        return result

    def source_profiles(self):
        return self.settings.get("sources", [])

    def update_sources(self, payload):
        import uuid
        action=str(payload.get("action","")).lower(); sources=self.settings.get("sources",[])
        if action=="add":
            name=str(payload.get("name","")).strip(); source_dir=str(payload.get("source_dir","")).strip()
            if not name or not source_dir: raise ValueError("Source name and source directory are required.")
            sources.append({"id":uuid.uuid4().hex,"name":name,"enabled":True,"source_dir":source_dir,"use_custom_destination":bool(payload.get("use_custom_destination",False)),"destination_dir":str(payload.get("destination_dir","")),"recursive":bool(payload.get("recursive",False)),"categories":payload.get("categories") or self.settings.get("categories",[])})
        elif action in {"update","delete","enable","disable"}:
            sid=str(payload.get("id","")); profile=next((x for x in sources if str(x.get("id"))==sid),None)
            if not profile: raise ValueError("Source profile was not found.")
            if action=="delete": self.monitor.stop_source(sid); sources.remove(profile)
            elif action in {"enable","disable"}:
                profile["enabled"]=action=="enable"
                if action=="disable": self.monitor.stop_source(sid)
            else:
                for key in ("name","source_dir","use_custom_destination","destination_dir","recursive","categories","enabled"):
                    if key in payload: profile[key]=payload[key]
        else: raise ValueError("Unsupported source action.")
        self.settings.update({"sources":sources}); return sources

    def update_categories(self, payload):
        action=str(payload.get("action","")).lower(); categories=self.settings.get("categories",[])
        if action=="reset":
            from app.config.defaults import DEFAULT_CATEGORIES
            categories=[dict(c) for c in DEFAULT_CATEGORIES]
        elif action=="add":
            name=str(payload.get("name","")).strip(); extensions=_parse_extensions(payload.get("extensions",[]))
            if any(str(c["name"]).casefold()==name.casefold() for c in categories): raise ValueError("A category with that name already exists.")
            categories.append({"name":name,"extensions":extensions,"enabled":True,"protected":False})
        elif action=="update":
            old=str(payload.get("old_name","")); category=next((c for c in categories if c["name"]==old),None)
            if not category: raise ValueError("Category was not found.")
            name=str(payload.get("name",old)).strip()
            if any(c is not category and str(c["name"]).casefold()==name.casefold() for c in categories): raise ValueError("A category with that name already exists.")
            category["name"]=name; category["extensions"]=_parse_extensions(payload.get("extensions",category.get("extensions",[])),allow_empty=name.casefold()=="unknown")
            if "enabled" in payload: category["enabled"]=bool(payload["enabled"])
        elif action=="delete":
            name=str(payload.get("name","")); category=next((c for c in categories if c["name"]==name),None)
            if not category: raise ValueError("Category was not found.")
            if category.get("protected",False): raise ValueError("Default categories cannot be deleted. You can disable them instead.")
            categories.remove(category)
        else: raise ValueError("Unsupported category action.")
        updates={"categories":categories}
        if action=="update" and str(category.get("name","")).casefold()=="unknown" and "enabled" in payload: updates["unknown_file_handling"]="move_to_unknown" if category["enabled"] else "skip"
        self.settings.update(updates); return self.category_stats()

    def read_logs(self, limit=200):
        try:
            lines=self.log_file.read_text(encoding="utf-8",errors="replace").splitlines()[-max(1,min(limit,1000)):]; result=[]
            for line in reversed(lines):
                parts=line.split(" | ",3); result.append({"timestamp":parts[0] if parts else "","level":parts[1].strip() if len(parts)>1 else "INFO","logger":parts[2] if len(parts)>2 else "","message":parts[3] if len(parts)>3 else line})
            return result
        except OSError: return []

    def _open_directory(self,path):
        path=path.expanduser().resolve(strict=True)
        if not path.is_dir(): raise ValueError(f"Not a directory: {path}")
        if sys.platform=="win32": os.startfile(str(path))
        elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
        else: subprocess.Popen(["xdg-open",str(path)])
        return {"success":True,"path":str(path)}

    def open_folder(self,kind):
        cfg=self.settings.snapshot()
        if kind=="source": value=str(cfg.get("source_dir") or "").strip()
        elif kind in {"destination","organized"}: value=(str(cfg.get("destination_dir") or "").strip() if cfg.get("use_custom_destination",False) else str(cfg.get("source_dir") or "").strip())
        elif kind=="logs": return self._open_directory(self.log_file.parent)
        else: raise ValueError("Unsupported folder kind.")
        if not value: raise ValueError(f"The {kind} directory is not configured.")
        return self._open_directory(Path(value))

    def open_logs(self):
        self.log_file.parent.mkdir(parents=True,exist_ok=True); self.log_file.touch(exist_ok=True)
        if sys.platform=="win32": os.startfile(str(self.log_file))
        elif sys.platform=="darwin": subprocess.Popen(["open",str(self.log_file)])
        else: subprocess.Popen(["xdg-open",str(self.log_file)])
        return {"success":True,"path":str(self.log_file)}

    def open_operation_location(self,record_id,kind):
        record=self.history.find(record_id)
        if not record or record.get("operation") not in {"move","undo"}: raise ValueError("Operation record was not found.")
        if kind=="source": value=record.get("source_path","")
        elif kind=="destination": value=record.get("destination_path","")
        else: raise ValueError("Unsupported operation location.")
        if not value: raise ValueError("The requested operation path is unavailable.")
        path=Path(value).expanduser(); return self._open_directory(path if path.is_dir() else path.parent)

    def tray_actions(self,server):
        from app.desktop.notifications import notify
        def organize():
            server.open("#dashboard"); notify("OrganizePro","Review the existing-file preview in the dashboard before organizing.",self.settings.get("notifications",True))
        def dry_run():
            result=self.dry_run_existing(); notify("OrganizePro dry run",f"{result['count']} file(s) would be organized. No files moved.",self.settings.get("notifications",True))
        return {"open_dashboard":lambda:server.open(),"start":self.start_monitoring,"pause":self.monitor.pause,"resume":self.monitor.resume,"stop":self.monitor.stop,"organize_existing":organize,"dry_run":dry_run,"open_source":lambda:self.open_folder("source"),"open_destination":lambda:self.open_folder("destination"),"settings":lambda:server.open("#settings"),"logs":self.open_logs}

    def close(self):
        self.monitor.stop()


def _parse_extensions(value, *, allow_empty=False):
    if isinstance(value,str): items=value.replace("\n",",").split(",")
    elif isinstance(value,list): items=value
    else: raise ValueError("Extensions must be a comma-separated string or a list.")
    result=sorted({str(x).strip().lower() if str(x).strip().startswith(".") else "."+str(x).strip().lower() for x in items if str(x).strip()})
    if not result and not allow_empty: raise ValueError("At least one extension is required.")
    return result
