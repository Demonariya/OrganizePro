from __future__ import annotations

DEFAULT_CATEGORIES = [
    {"name": "Documents", "extensions": [".pdf", ".doc", ".docx", ".txt", ".epub", ".json"], "enabled": True, "protected": True},
    {"name": "Pictures", "extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"], "enabled": True, "protected": True},
    {"name": "Videos", "extensions": [".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"], "enabled": True, "protected": True},
    {"name": "Programs", "extensions": [".exe", ".msi", ".apk", ".msix", ".appx"], "enabled": True, "protected": True},
    {"name": "Compressed", "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".tar.gz", ".iso"], "enabled": True, "protected": True},
    {"name": "Music", "extensions": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"], "enabled": True, "protected": True},
    {"name": "Unknown", "extensions": [], "enabled": True, "protected": True},
]

DEFAULT_EXCLUDED_DIRS = ["node_modules", ".git", ".venv", "venv", "__pycache__", "target", "dist", ".next", ".gradle", ".idea", ".vscode", ".pytest_cache", ".mypy_cache"]
DEFAULT_EXCLUDED_PATTERNS = ["*.part", "*.crdownload", "*.download", "*.partial", "*.tmp", "*.temp", "~$*", "*.swp", "*.lock.tmp", "Thumbs.db", "desktop.ini", ".DS_Store"]
DEFAULT_PROTECTED_FILES = ["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.toml", "Cargo.lock", "pyproject.toml", "requirements.txt", "tsconfig.json", ".gitignore", "README.md", "go.mod", "go.sum", "composer.json", "Gemfile", "Gemfile.lock", "Pipfile", "Pipfile.lock"]
DEFAULT_PROTECTED_PATTERNS = ["*.d.ts", "*.pyi", "*.sln", "*.csproj", "*.vcxproj"]
DEFAULT_SETTINGS = {"version": 1, "sources": [], "source_dir": "", "destination_dir": "", "use_custom_destination": False, "recursive": False, "stability_seconds": 3.0, "polling_interval": 2.0, "collision_strategy": "rename", "duplicate_handling": "skip_identical", "unknown_file_handling": "skip", "allow_replace": False, "start_with_windows": False, "start_minimized": False, "auto_start_monitoring": False, "open_dashboard_on_start": True, "notifications": True, "log_level": "INFO", "log_retention_days": 30, "max_history_records": 5000, "excluded_dirs": DEFAULT_EXCLUDED_DIRS, "excluded_patterns": DEFAULT_EXCLUDED_PATTERNS, "ignored_extensions": [".bak", ".old", ".dmp", ".log"], "protected_files": DEFAULT_PROTECTED_FILES, "protected_patterns": DEFAULT_PROTECTED_PATTERNS, "protect_project_directories": True, "categories": DEFAULT_CATEGORIES}
