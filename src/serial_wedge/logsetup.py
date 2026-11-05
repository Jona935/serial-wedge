"""Registro rotativo en config_dir/serial-wedge.log.

A nivel INFO nunca se escriben los códigos leídos (pueden ser datos sensibles);
solo a nivel DEBUG.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import config_dir

LOG_NAME = "serial-wedge.log"


def log_path() -> Path:
    return config_dir() / LOG_NAME


def setup_logging(level=logging.INFO) -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, "_serial_wedge", False)]:
        root.removeHandler(h)
        h.close()
    handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._serial_wedge = True
    root.addHandler(handler)
    root.setLevel(level)
    return path
