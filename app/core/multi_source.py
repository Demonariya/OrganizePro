from __future__ import annotations

import copy
import threading
from typing import Any

from app.core.monitor import MonitorService
from app.core.organizer import FileOrganizer


class MultiSourceMonitor:
    """Owns one isolated organizer/monitor pair per configured source."""
    def __init__(self, settings_store, history):
        self.settings_store = settings_store; self.history = history
        self._lock = threading.RLock(); self._services: dict[str, tuple[FileOrganizer, MonitorService]] = {}

    def _profiles(self) -> list[dict[str, Any]]:
        cfg = self.settings_store.snapshot(); profiles = copy.deepcopy(cfg.get("sources", []))
        if not profiles and cfg.get("source_dir"):
            profiles = [{"id":"legacy-default","name":"Default source","enabled":True,"source_dir":cfg.get("source_dir"),"use_custom_destination":cfg.get("use_custom_destination",False),"destination_dir":cfg.get("destination_dir",""),"categories":cfg.get("categories",[])}]
        return [p for p in profiles if p.get("enabled",True) and p.get("source_dir")]

    def _config(self, profile: dict[str, Any]):
        base=self.settings_store.snapshot(); base.update({"source_dir":profile.get("source_dir",""),"use_custom_destination":bool(profile.get("use_custom_destination",False)),"destination_dir":profile.get("destination_dir",""),"categories":copy.deepcopy(profile.get("categories") or base.get("categories",[])),"recursive":bool(profile.get("recursive",base.get("recursive",False)))}); return base

    @property
    def is_running(self) -> bool:
        with self._lock: return any(m.is_running for _,m in self._services.values())

    def start(self):
        with self._lock:
            profiles=self._profiles()
            if not profiles: raise ValueError("Add at least one enabled source folder in Source Manager.")
            wanted={str(p["id"]):p for p in profiles}
            for key in list(self._services):
                if key not in wanted: self._services[key][1].stop(); del self._services[key]
            results=[]
            for key,profile in wanted.items():
                if key not in self._services:
                    provider=lambda p=profile:self._config(p); organizer=FileOrganizer(provider,self.history); self._services[key]=(organizer,MonitorService(organizer,provider))
                organizer,monitor=self._services[key]; monitor.settings_provider=lambda p=profile:self._config(p); organizer.settings_provider=monitor.settings_provider
                results.append({"id":key,"name":profile.get("name",key),"status":monitor.start()})
            return {"success":True,"sources":results,"status":self.status()}

    def stop(self):
        with self._lock:
            for _,monitor in self._services.values(): monitor.stop()
    def pause(self):
        with self._lock:
            for _,monitor in self._services.values(): monitor.pause()
    def resume(self):
        with self._lock:
            for _,monitor in self._services.values(): monitor.resume()
    def restart(self): self.stop(); return self.start()

    def status(self):
        with self._lock:
            profiles={str(p["id"]):p for p in self._profiles()}; items=[]
            for key,profile in profiles.items():
                pair=self._services.get(key); state=pair[1].status() if pair else {"running":False,"paused":False}
                items.append({"id":key,"name":profile.get("name",key),"source_dir":profile.get("source_dir",""),"destination_dir":profile.get("destination_dir","") if profile.get("use_custom_destination") else "",**state})
            running=sum(1 for x in items if x.get("running"))
            return {"running":running>0,"paused":bool(items) and all(x.get("paused") for x in items if x.get("running")),"source_count":len(items),"running_sources":running,"sources":items}

    def stop_source(self, source_id: str):
        with self._lock:
            pair=self._services.get(source_id)
            if pair: pair[1].stop()
            return self.status()

    def start_source(self, source_id: str):
        with self._lock:
            profile=next((p for p in self._profiles() if str(p.get("id"))==source_id),None)
            if not profile: raise ValueError("Source profile not found.")
            if source_id not in self._services:
                provider=lambda p=profile:self._config(p); organizer=FileOrganizer(provider,self.history); self._services[source_id]=(organizer,MonitorService(organizer,provider))
            return self._services[source_id][1].start()
