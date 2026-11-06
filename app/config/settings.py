from __future__ import annotations

import copy
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from app.config.defaults import DEFAULT_SETTINGS

LOG = logging.getLogger("organizepro.settings")


def app_data_dir() -> Path:
    override = os.environ.get("ORGANIZEPRO_DATA_DIR")
    if override: base = Path(override).expanduser()
    elif sys.platform == "win32": base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "OrganizePro"
    elif sys.platform == "darwin": base = Path.home() / "Library" / "Application Support" / "OrganizePro"
    else: base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "organizepro"
    base.mkdir(parents=True, exist_ok=True)
    return base


class SettingsStore:
    def __init__(self, directory: Path | None = None):
        self.directory = (directory or app_data_dir()).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self._lock = threading.RLock(); self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        with self._lock:
            data: dict[str, Any] = {}
            if self.path.exists():
                try:
                    parsed = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict): data = parsed
                except (OSError, json.JSONDecodeError):
                    try: self.path.replace(self.path.with_suffix(".corrupt.json"))
                    except OSError: pass
            merged = copy.deepcopy(DEFAULT_SETTINGS); merged.update(data)
            categories = merged.get("categories", [])
            if not isinstance(categories, list) or any(not isinstance(item, dict) for item in categories): categories = copy.deepcopy(DEFAULT_SETTINGS["categories"])
            categories = [item for item in categories if str(item.get("name", "")).casefold() not in {"minecraft", "minecarft"}]
            existing = {str(item.get("name", "")).casefold() for item in categories}
            for item in DEFAULT_SETTINGS["categories"]:
                if item["name"].casefold() not in existing: categories.append(copy.deepcopy(item))
            merged["categories"] = categories; merged.pop("folder_profiles", None)
            if "use_custom_destination" not in data: merged["use_custom_destination"] = bool(merged.get("destination_dir"))
            merged.setdefault("sources", [])
            if not merged["sources"] and str(merged.get("source_dir") or "").strip():
                merged["sources"] = [{"id":"legacy-default","name":"Default source","enabled":True,"source_dir":merged.get("source_dir",""),"use_custom_destination":bool(merged.get("use_custom_destination",False)),"destination_dir":merged.get("destination_dir",""),"recursive":bool(merged.get("recursive",False)),"categories":copy.deepcopy(merged.get("categories",DEFAULT_SETTINGS["categories"]))}]
            merged["version"] = DEFAULT_SETTINGS["version"]
            try: validate_settings(merged)
            except (TypeError, ValueError, KeyError, OverflowError) as exc:
                LOG.warning("Invalid settings replaced with safe defaults: %s", exc)
                try: self.path.replace(self.path.with_suffix(".invalid.json"))
                except OSError: pass
                merged = copy.deepcopy(DEFAULT_SETTINGS)
            self._data = merged; self.save(); return self.snapshot()

    def save(self) -> bool:
        with self._lock:
            temp = self.path.with_suffix(f".tmp-{os.getpid()}")
            try:
                temp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
                os.replace(temp, self.path); return True
            except OSError:
                try: temp.unlink(missing_ok=True)
                except OSError: pass
                return False

    def snapshot(self) -> dict[str, Any]:
        with self._lock: return copy.deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock: return copy.deepcopy(self._data.get(key, default))

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        unknown = set(values) - set(DEFAULT_SETTINGS)
        if unknown: raise ValueError(f"Unsupported settings: {', '.join(sorted(unknown))}")
        with self._lock:
            candidate = copy.deepcopy(self._data); candidate.update(values)
            if "destination_dir" in values and "use_custom_destination" not in values and str(values.get("destination_dir") or "").strip(): candidate["use_custom_destination"] = True
            validate_settings(candidate); self._data = candidate
            if not self.save(): raise OSError(f"Could not persist settings to {self.path}")
            return self.snapshot()

    def reset(self) -> dict[str, Any]:
        with self._lock: self._data = copy.deepcopy(DEFAULT_SETTINGS); self.save(); return self.snapshot()


def validate_settings(data: dict[str, Any]) -> None:
    if not 0.5 <= float(data.get("stability_seconds", 3)) <= 600: raise ValueError("Stability duration must be between 0.5 and 600 seconds.")
    if not 0.5 <= float(data.get("polling_interval", 2)) <= 120: raise ValueError("Polling interval must be between 0.5 and 120 seconds.")
    if data.get("collision_strategy") not in {"rename", "skip", "content", "replace"}: raise ValueError("Invalid collision strategy.")
    if data.get("duplicate_handling", "skip_identical") not in {"skip_identical", "keep_both"}: raise ValueError("Invalid duplicate handling strategy.")
    if data.get("unknown_file_handling", "skip") not in {"skip", "move_to_unknown"}: raise ValueError("Invalid unknown-file handling strategy.")
    if str(data.get("log_level", "INFO")).upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}: raise ValueError("Invalid log level.")
    retention = int(data.get("log_retention_days", 30))
    if not 1 <= retention <= 3650: raise ValueError("Log retention must be between 1 and 3650 days.")
    if data.get("collision_strategy") == "replace" and not data.get("allow_replace"): raise ValueError("Replace requires the explicit Allow Replace setting.")
    paths = {}
    for key in ["source_dir"] + (["destination_dir"] if data.get("use_custom_destination", False) else []):
        value = str(data.get(key) or "").strip()
        if value:
            p = Path(value).expanduser()
            if not p.is_absolute(): raise ValueError(f"{key} must be an absolute path.")
            paths[key] = p.resolve(strict=False)
    source = paths.get("source_dir"); destination = paths.get("destination_dir") if data.get("use_custom_destination", False) else None
    if data.get("use_custom_destination", False) and not destination: raise ValueError("Choose a destination folder or turn off custom destination mode.")
    if source and destination and (source == destination or _is_relative_to(source, destination)): raise ValueError("The source directory cannot be the destination directory or inside it.")
    for key in ("excluded_dirs","excluded_patterns","ignored_extensions","protected_files","protected_patterns"):
        value = data.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value): raise ValueError(f"{key} must be a list of text values.")
    sources = data.get("sources", [])
    if not isinstance(sources, list): raise ValueError("sources must be a list.")
    ids = set()
    for profile in sources:
        if not isinstance(profile, dict): raise ValueError("Each source profile must be an object.")
        sid, name, source_path = str(profile.get("id","")).strip(), str(profile.get("name","")).strip(), str(profile.get("source_dir","")).strip()
        if not sid or sid in ids or not name or not source_path: raise ValueError("Each source needs a unique id, name, and source directory.")
        ids.add(sid); source = Path(source_path).expanduser()
        if not source.is_absolute(): raise ValueError("Source paths must be absolute.")
        use_dest = bool(profile.get("use_custom_destination",False)); dest_value = str(profile.get("destination_dir","")).strip()
        if use_dest and not dest_value: raise ValueError(f"Choose a destination for source {name} or disable custom destination.")
        if use_dest:
            dest = Path(dest_value).expanduser()
            if not dest.is_absolute(): raise ValueError("Destination paths must be absolute.")
            if _is_relative_to(source.resolve(strict=False), dest.resolve(strict=False)) or source.resolve(strict=False) == dest.resolve(strict=False): raise ValueError("A source cannot be inside its destination or equal to it.")
        if not isinstance(profile.get("categories", []), list): raise ValueError("Source categories must be a list.")
    names=set(); owners={}
    for category in data.get("categories", []):
        name=str(category.get("name","")).strip()
        if not name or name in {".",".."} or any(c in name for c in '<>:/\\|?*"'): raise ValueError(f"Invalid category name: {name!r}")
        if name.casefold() in names: raise ValueError(f"Duplicate category name: {name}")
        names.add(name.casefold())
        for ext in category.get("extensions", []):
            e=str(ext).strip().lower()
            if not e.startswith(".") or len(e)<2 or any(c in e for c in "/\\*?"): raise ValueError(f"Invalid extension: {e!r}")
            owner=owners.get(e)
            if owner and owner.casefold()!=name.casefold(): raise ValueError(f"Extension {e} is assigned to multiple categories.")
            owners[e]=name


def _is_relative_to(path: Path, parent: Path) -> bool:
    try: path.relative_to(parent); return True
    except ValueError: return False
