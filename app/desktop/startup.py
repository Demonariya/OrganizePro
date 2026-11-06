from __future__ import annotations
import logging,shlex,sys
from pathlib import Path
from typing import Any
LOG=logging.getLogger("organizepro.startup")
RUN_KEY=r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"; VALUE_NAME="OrganizePro"
class StartupManager:
    @staticmethod
    def command(start_minimized=False):
        flag=" --tray" if start_minimized else ""
        if getattr(sys,"frozen",False): return f'"{Path(sys.executable).resolve()}"{flag}'
        python=Path(sys.executable)
        if sys.platform=="win32" and python.name.casefold()=="python.exe":
            candidate=python.with_name("pythonw.exe")
            if candidate.exists(): python=candidate
        script=Path(__file__).resolve().parents[2]/"main.py"
        return f'"{python}" "{script}"{flag}' if sys.platform=="win32" else f'{shlex.quote(str(python))} {shlex.quote(str(script))}{flag}'
    @classmethod
    def status(cls)->dict[str,Any]:
        if sys.platform!="win32": return {"supported":False,"enabled":False,"command":cls.command(),"start_minimized":False,"message":"Windows startup integration is available on Windows."}
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_READ) as key:
                try:
                    command,_=winreg.QueryValueEx(key,VALUE_NAME); return {"supported":True,"enabled":True,"command":command,"start_minimized":"--tray" in command,"message":"Registered for the current Windows user."}
                except (FileNotFoundError,KeyError): return {"supported":True,"enabled":False,"command":cls.command(),"start_minimized":False,"message":"Not registered."}
        except (FileNotFoundError,KeyError): return {"supported":True,"enabled":False,"command":cls.command(),"start_minimized":False,"message":"Not registered."}
        except OSError as exc: return {"supported":True,"enabled":False,"command":"","start_minimized":False,"message":f"Could not read startup registration: {exc}"}
    @classmethod
    def set_enabled(cls,enabled:bool,start_minimized=False):
        if sys.platform!="win32": return False,"Windows startup registration is not supported on this platform."
        try:
            import winreg
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
                if enabled: winreg.SetValueEx(key,VALUE_NAME,0,winreg.REG_SZ,cls.command(start_minimized))
                else:
                    try: winreg.DeleteValue(key,VALUE_NAME)
                    except (FileNotFoundError,KeyError): pass
            state=cls.status()
            if bool(state.get("enabled"))!=bool(enabled): return False,"Windows did not confirm the requested startup state."
            return True,"Startup registration updated." if enabled else "Startup registration removed."
        except Exception as exc: LOG.exception("Startup registration failed"); return False,f"Startup registration failed: {exc}"
