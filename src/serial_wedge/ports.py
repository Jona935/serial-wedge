"""Listado de puertos serie y elección del puerto del lector."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    vid: int | None
    pid: int | None


def _comports():
    from serial.tools import list_ports as lp
    return lp.comports()


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _is_posix_device(name: str) -> bool:
    """Rutas como /dev/pts/3 o enlaces de socat no aparecen en comports()."""
    return name.startswith("/") and os.path.exists(name)


def list_ports() -> list[PortInfo]:
    items = [PortInfo(p.device, p.description or "", p.vid, p.pid) for p in _comports()]
    return sorted(items, key=lambda p: _natural_key(p.device))


def ids(vid, pid) -> str:
    return f"{vid:04x}:{pid:04x}"


def label(p: PortInfo) -> str:
    text = f"{p.device} — {p.description}"
    return f"{text} ({ids(p.vid, p.pid)})" if p.vid is not None else text


def resolve_port(config, list_fn=list_ports) -> tuple[str | None, str]:
    """Devuelve (dispositivo o None, motivo legible)."""
    try:
        available = list(list_fn())
    except Exception as exc:  # p. ej. permisos al enumerar
        return None, f"no se pudieron listar los puertos: {exc}"
    if config.port != "auto" and (any(p.device == config.port for p in available)
                                  or _is_posix_device(config.port)):
        return config.port, f"puerto configurado {config.port}"
    if config.vid is not None and config.pid is not None:
        for p in available:
            if (p.vid, p.pid) == (config.vid, config.pid):
                return p.device, f"lector {ids(p.vid, p.pid)} en {p.device}"
        return None, f"lector {ids(config.vid, config.pid)} no conectado"
    if config.port != "auto":
        return None, f"el puerto {config.port} no está presente"
    usb = [p for p in available if p.vid is not None]
    if len(usb) == 1:
        return usb[0].device, f"único puerto USB {usb[0].device}"
    if not usb:
        return None, "no hay puertos USB serie conectados"
    return None, f"hay {len(usb)} puertos USB; elija uno en Configuración"
