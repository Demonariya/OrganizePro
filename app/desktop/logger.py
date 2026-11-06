from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path, level: str = "INFO", retention_days: int = 30) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / "organizepro.log"
    logger = logging.getLogger("organizepro")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.flush(); handler.close()
        except Exception:
            pass
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    file_handler = TimedRotatingFileHandler(logfile, when="midnight", interval=1, backupCount=max(1, min(int(retention_days), 3650)), encoding="utf-8", utc=False)
    file_handler.setFormatter(formatter); logger.addHandler(file_handler)
    if sys.stdout is not None and sys.stderr is not None:
        console = logging.StreamHandler(); console.setFormatter(formatter); logger.addHandler(console)
    return logfile
