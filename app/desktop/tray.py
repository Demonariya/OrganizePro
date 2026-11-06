from __future__ import annotations
import logging, threading
from pathlib import Path
from typing import Callable
LOG=logging.getLogger("organizepro.tray")
class TrayService:
    def __init__(self,actions:dict[str,Callable[[],None]],status:Callable[[],dict]): self.actions=actions; self.status=status; self.icon=None; self.thread=None
    def start(self,icon_path:Path)->bool:
        try:
            import pystray
            from pystray import Menu,MenuItem
            from PIL import Image
            image=Image.open(icon_path).convert("RGBA")
            def item(label,key): return MenuItem(label,lambda _icon,_item:self._call(key))
            menu=Menu(MenuItem(lambda _item:self._status_label(),None,enabled=False),Menu.SEPARATOR,item("Open Dashboard","open_dashboard"),item("Start Monitoring","start"),item("Pause Monitoring","pause"),item("Resume Monitoring","resume"),item("Stop Monitoring","stop"),Menu.SEPARATOR,item("Organize Existing Files…","organize_existing"),item("Dry Run","dry_run"),Menu.SEPARATOR,item("Open Source Folder","open_source"),item("Open Organized Folder","open_destination"),item("Settings","settings"),item("View Logs","logs"),Menu.SEPARATOR,item("Exit OrganizePro","exit"))
            self.icon=pystray.Icon("OrganizePro",image,"OrganizePro",menu); self.thread=threading.Thread(target=self.icon.run,name="OrganizeProTray",daemon=True); self.thread.start(); return True
        except Exception: LOG.exception("Could not initialize system tray"); return False
    def _call(self,key):
        try:
            callback=self.actions.get(key)
            if callback: callback()
        except Exception: LOG.exception("Tray action failed: %s",key)
    def _status_label(self):
        current=self.status(); state="Stopped" if not current.get("running") else "Paused" if current.get("paused") else "Monitoring"; return f"OrganizePro — {state}"
    def stop(self):
        if self.icon:
            try: self.icon.stop()
            except Exception: LOG.exception("Could not stop tray icon")
            self.icon=None
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread(): self.thread.join(timeout=3)
        self.thread=None
