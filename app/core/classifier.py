from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any


def normalize_extension(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return ""
    return value if value.startswith(".") else f".{value}"


class Categorizer:
    def __init__(self, categories: list[dict[str, Any]], ignored_extensions: list[str] | None = None,
                 ignored_patterns: list[str] | None = None):
        self.categories = [c for c in categories if c.get("enabled", True)]
        self.ignored_extensions = {normalize_extension(e) for e in (ignored_extensions or [])}
        self.ignored_patterns = [p.casefold() for p in (ignored_patterns or [])]
        self._suffixes: list[tuple[str, str]] = []
        for category in self.categories:
            for extension in category.get("extensions", []):
                normalized = normalize_extension(str(extension))
                if normalized:
                    self._suffixes.append((normalized, str(category["name"])))
        self._suffixes.sort(key=lambda pair: len(pair[0]), reverse=True)

    def category_for(self, path: Path) -> str | None:
        filename = path.name.casefold()
        if any(fnmatch.fnmatchcase(filename, pattern) for pattern in self.ignored_patterns):
            return None
        for ext in self.ignored_extensions:
            if filename.endswith(ext):
                return None
        for extension, category in self._suffixes:
            if filename.endswith(extension):
                return category
        return None

    def configured_extensions(self) -> dict[str, list[str]]:
        return {str(c["name"]): sorted({normalize_extension(str(e)) for e in c.get("extensions", [])})
                for c in self.categories}
