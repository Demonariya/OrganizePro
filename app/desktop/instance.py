from __future__ import annotations
import os,sys
from pathlib import Path
class SingleInstance:
    def __init__(self,name:str,data_dir:Path): self.name=name; self.data_dir=data_dir; self.handle=None; self.file_handle=None; self.kernel32=None
    def acquire(self)->bool:
        if sys.platform=="win32":
            import ctypes
            kernel32=ctypes.WinDLL("kernel32",use_last_error=True); kernel32.CreateMutexW.argtypes=(ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p); kernel32.CreateMutexW.restype=ctypes.c_void_p; kernel32.CloseHandle.argtypes=(ctypes.c_void_p,); kernel32.CloseHandle.restype=ctypes.c_bool; ctypes.set_last_error(0); handle=kernel32.CreateMutexW(None,False,f"Local\\{self.name}")
            if not handle: return False
            if ctypes.get_last_error()==183: kernel32.CloseHandle(handle); return False
            self.kernel32=kernel32; self.handle=handle; return True
        try:
            import fcntl
            lock_path=self.data_dir/"instance.lock"; self.file_handle=lock_path.open("a+"); fcntl.flock(self.file_handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); self.file_handle.seek(0); self.file_handle.truncate(); self.file_handle.write(str(os.getpid())); self.file_handle.flush(); return True
        except (OSError,ImportError):
            if self.file_handle:
                try: self.file_handle.close()
                except OSError: pass
                self.file_handle=None
            return False
    def release(self):
        if sys.platform=="win32" and self.handle:
            if self.kernel32 is not None: self.kernel32.CloseHandle(self.handle)
            self.handle=None; self.kernel32=None
        elif self.file_handle:
            try:
                import fcntl
                fcntl.flock(self.file_handle.fileno(),fcntl.LOCK_UN); self.file_handle.close()
            except OSError: pass
            self.file_handle=None
