"""Configuración persistente (config.json) tolerante a errores."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SUFFIXES = ("enter", "tab", "none")
PARITIES = ("N", "E", "O", "M", "S")


@dataclass
class Config:
    port: str = "auto"
    vid: int | None = None
    pid: int | None = None
    baud: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    suffix: str = "enter"
    prefix: str = ""
    autostart: bool = False
    paused: bool = False


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _opt_id(v):
    return v is None or (_is_int(v) and 0 <= v <= 0xFFFF)


VALID = {
    "port": lambda v: isinstance(v, str) and v.strip() != "",
    "vid": _opt_id,
    "pid": _opt_id,
    "baud": lambda v: _is_int(v) and 50 <= v <= 4_000_000,
    "bytesize": lambda v: v in (5, 6, 7, 8) and _is_int(v),
    "parity": lambda v: v in PARITIES,
    "stopbits": lambda v: v in (1, 2) and _is_int(v),
    "suffix": lambda v: v in SUFFIXES,
    "prefix": lambda v: isinstance(v, str),
    "autostart": lambda v: isinstance(v, bool),
    "paused": lambda v: isinstance(v, bool),
}


def config_dir(platform: str = sys.platform) -> Path:
    if env := os.environ.get("SERIAL_WEDGE_DIR"):
        return Path(env)
    if platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "SerialWedge"
    return Path.home() / ".config" / "serial-wedge"


def config_path() -> Path:
    return config_dir() / "config.json"


def from_dict(data) -> Config:
    """Construye un Config tomando cada campo válido; el resto queda por defecto."""
    c = Config()
    if isinstance(data, dict):
        for f in fields(Config):
            if f.name in data and VALID[f.name](data[f.name]):
                setattr(c, f.name, data[f.name])
    return c


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    return from_dict(data)


def write_json_atomic(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(cfg: Config, path: Path | None = None) -> None:
    write_json_atomic(path or config_path(), asdict(cfg))
