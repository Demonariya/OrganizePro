# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = Path(SPECPATH)
block_cipher = None
a = Analysis([str(ROOT / "main.py")], pathex=[str(ROOT)], binaries=[], datas=[(str(ROOT / "assets"), "assets"), (str(ROOT / "app" / "web" / "frontend"), "app/web/frontend")], hiddenimports=["watchdog.observers.winapi", "pystray._win32", "PIL.Image", "winotify"], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["tkinter"], win_no_prefer_redirects=False, win_private_assemblies=False, cipher=block_cipher, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name="OrganizePro", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False, argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None, icon=str(ROOT / "assets" / "icon.ico"))
