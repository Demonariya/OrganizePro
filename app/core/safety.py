from __future__ import annotations

import fnmatch, os, stat as stat_module, time, zipfile, tarfile, gzip, bz2, lzma
from functools import lru_cache
from pathlib import Path
from typing import Any

TEMPORARY_SUFFIXES=(".part",".crdownload",".download",".partial",".tmp",".temp")
ARCHIVE_EXTENSIONS={".zip",".jar",".apk",".docx",".xlsx",".pptx",".odt",".ods",".odp",".tar",".tar.gz",".tar.bz2",".tar.xz",".tgz",".rar",".7z",".iso",".gz",".bz2",".xz"}
PROJECT_MARKERS={"package.json","package-lock.json","pnpm-lock.yaml","yarn.lock","cargo.toml","cargo.lock","pyproject.toml","requirements.txt","pipfile","pipfile.lock","go.mod","go.sum","pom.xml","build.gradle","build.gradle.kts","composer.json","gemfile","gemfile.lock","tsconfig.json",".git",".gitignore"}

def is_within(path:Path,parent:Path)->bool:
    try: path.relative_to(parent); return True
    except ValueError: return False

def is_link_like(path:Path)->bool:
    try:
        if path.is_symlink(): return True
        fn=getattr(path,"is_junction",None); return bool(fn()) if callable(fn) else False
    except OSError: return True

def has_link_component(path:Path,trusted_root:Path)->bool:
    candidate=Path(os.path.abspath(path)); root=Path(os.path.abspath(trusted_root))
    if not is_within(candidate,root): return True
    current=candidate
    while True:
        if is_link_like(current): return True
        if current==root: return False
        parent=current.parent
        if parent==current: return True
        current=parent

@lru_cache(maxsize=8192)
def _directory_has_project_marker(directory:str,modified_ns:int)->bool:
    del modified_ns
    try:
        with os.scandir(directory) as entries: return any(e.name.casefold() in PROJECT_MARKERS and not e.is_symlink() for e in entries)
    except OSError: return True

def has_project_ancestor(path:Path,source_root:Path)->bool:
    current=path.parent; root=source_root.resolve(strict=False); home=Path.home().resolve(strict=False)
    if is_within(root,home): boundary=home
    else:
        boundary=root
        for _ in range(4):
            parent=boundary.parent
            if parent==boundary: break
            boundary=parent
    while True:
        try:
            info=current.stat()
            if _directory_has_project_marker(str(current),info.st_mtime_ns): return True
        except OSError: return True
        if current==boundary: break
        parent=current.parent
        if parent==current: break
        current=parent
    return False

def is_incomplete_archive(path:Path)->bool:
    suffixes={s.casefold() for s in path.suffixes}
    if not suffixes.intersection(ARCHIVE_EXTENSIONS): return False
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive: archive.infolist()
            return False
        lowered=path.name.casefold()
        if lowered.endswith((".tar",".tar.gz",".tar.bz2",".tar.xz",".tgz")):
            with tarfile.open(path,"r:*") as archive: archive.getmembers()
            return False
        if lowered.endswith((".zip",".jar",".apk",".docx",".xlsx",".pptx",".odt",".ods",".odp")): return True
        with path.open("rb") as stream:
            if lowered.endswith(".7z"): return stream.read(6)!=b"7z\xbc\xaf\x27\x1c"
            if lowered.endswith(".rar"):
                header=stream.read(8); return not (header.startswith(b"Rar!\x1a\x07\x00") or header.startswith(b"Rar!\x1a\x07\x01\x00"))
            if lowered.endswith(".iso"): stream.seek(32769); return stream.read(5)!=b"CD001"
            if lowered.endswith(".gz"):
                if stream.read(2)!=b"\x1f\x8b": return True
                with gzip.open(path,"rb") as f:
                    while f.read(1024*1024): pass
                return False
            if lowered.endswith(".bz2"):
                if stream.read(3)!=b"BZh": return True
                with bz2.open(path,"rb") as f:
                    while f.read(1024*1024): pass
                return False
            if lowered.endswith(".xz"):
                if stream.read(6)!=b"\xfd7zXZ\x00": return True
                with lzma.open(path,"rb") as f:
                    while f.read(1024*1024): pass
                return False
        return False
    except (OSError,zipfile.BadZipFile,tarfile.TarError,EOFError): return True

def structural_exclusion_reason(path:Path,relative_parts:tuple[str,...],settings:dict[str,Any],source_root:Path)->str|None:
    if is_link_like(path): return "Symbolic links and junctions are not processed"
    if not settings.get("recursive",False) and len(relative_parts)>1: return "Recursive monitoring is disabled"
    excluded={str(x).casefold() for x in settings.get("excluded_dirs",[])}
    if any(p.casefold() in excluded for p in relative_parts[:-1]): return "Excluded directory"
    name=path.name.casefold()
    if name.startswith("~$") or any(name.endswith(s) for s in TEMPORARY_SUFFIXES): return "Temporary or incomplete file"
    if any(fnmatch.fnmatchcase(name,str(p).casefold()) for p in settings.get("excluded_patterns",[])): return "Excluded filename pattern"
    if any(name.endswith(str(e).casefold()) for e in settings.get("ignored_extensions",[])): return "Ignored extension"
    protected={str(x).casefold() for x in settings.get("protected_files",[])}
    if name in protected or any(fnmatch.fnmatchcase(name,str(p).casefold()) for p in settings.get("protected_patterns",[])): return "Protected development or metadata file"
    if settings.get("protect_project_directories",True) and has_project_ancestor(path,source_root): return "File belongs to a detected development project"
    return None

def exclusion_reason(path:Path,root:Path,destination:Path|None,settings:dict[str,Any])->str|None:
    if is_link_like(path): return "Symbolic links and junctions are not processed"
    try: resolved=path.resolve(strict=False)
    except OSError: return "Path cannot be resolved"
    if destination and is_within(resolved,destination): return "Destination directory is excluded"
    try: relative=resolved.relative_to(root)
    except ValueError: return "File is outside the source directory"
    reason=structural_exclusion_reason(resolved,relative.parts,settings,root)
    if reason: return reason
    if is_incomplete_archive(resolved): return "Archive is incomplete or invalid"
    try:
        if not path.is_file(): return "Not a regular file"
    except OSError: return "File is inaccessible"
    return None

def wait_until_stable(path:Path,stability_seconds:float,stop_event=None,timeout_seconds:float|None=None)->bool:
    required=max(.5,min(float(stability_seconds),600.0)); timeout=timeout_seconds if timeout_seconds is not None else max(30.0,required*10)
    def snapshot():
        try:
            info=path.lstat()
            if not stat_module.S_ISREG(info.st_mode): return None
            return (info.st_size,info.st_mtime_ns,getattr(info,"st_dev",None),getattr(info,"st_ino",None))
        except OSError: return None
    previous=snapshot()
    if previous is None: return False
    started=time.monotonic(); stable_since=started
    while time.monotonic()-started<timeout:
        if stop_event is not None and stop_event.is_set(): return False
        delay=min(.5,required/4)
        if stop_event is not None:
            if stop_event.wait(delay): return False
        else: time.sleep(delay)
        current=snapshot()
        if current is None: return False
        if current!=previous: previous=current; stable_since=time.monotonic(); continue
        if time.monotonic()-stable_since>=required:
            try:
                with path.open("rb") as stream: stream.read(1)
                return True
            except OSError: stable_since=time.monotonic()
    return False

def filesystem_identity(stat_result:os.stat_result)->tuple[int|None,int|None]:
    return getattr(stat_result,"st_dev",None),getattr(stat_result,"st_ino",None)
