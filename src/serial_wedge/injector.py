"""Escribe texto en la ventana con el foco, como si fuera un teclado."""
from __future__ import annotations

import shutil
import subprocess
import sys

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SUFFIX_VK = {"enter": 0x0D, "tab": 0x09, "none": None}
SUFFIX_XDOTOOL = {"enter": "Return", "tab": "Tab", "none": None}
SUFFIX_LABEL = {"enter": " [Enter]", "tab": " [Tab]", "none": ""}


class WedgeUnavailable(RuntimeError):
    """No hay forma de simular el teclado en este sistema."""


def build_key_events(text: str, suffix: str) -> list[tuple[int, int, int]]:
    """Eventos (wVk, wScan, dwFlags) para SendInput."""
    if suffix not in SUFFIX_VK:
        raise ValueError(f"sufijo desconocido: {suffix!r}")
    data = text.encode("utf-16-le")
    events = []
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        events += [(0, unit, KEYEVENTF_UNICODE), (0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    if (vk := SUFFIX_VK[suffix]) is not None:
        events += [(vk, 0, 0), (vk, 0, KEYEVENTF_KEYUP)]
    return events


def _send_windows(events) -> None:  # pragma: no cover - solo Windows
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):  # solo para que la unión tenga el tamaño correcto
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    if not events:
        return
    arr = (INPUT * len(events))()
    for slot, (vk, scan, flags) in zip(arr, events):
        slot.type = 1  # INPUT_KEYBOARD
        slot.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    sent = user32.SendInput(len(arr), arr, ctypes.sizeof(INPUT))
    if sent != len(arr):
        raise OSError(ctypes.get_last_error(), "SendInput bloqueado (¿aplicación como Administrador?)")


def make_injector(platform: str = sys.platform, which=shutil.which, run=subprocess.run):
    """Devuelve type_code(text, suffix) para la plataforma actual."""
    if platform == "win32":
        def type_code(text, suffix):
            _send_windows(build_key_events(text, suffix))
        return type_code

    exe = which("xdotool")
    if not exe:
        raise WedgeUnavailable("Instale xdotool: sudo apt install xdotool (solo X11)")

    def type_code(text, suffix):
        if text:
            run([exe, "type", "--clearmodifiers", "--delay", "0", "--", text], check=True)
        if key := SUFFIX_XDOTOOL[suffix]:
            run([exe, "key", key], check=True)
    return type_code


def safe_print(*args) -> None:
    """print que no falla en un .exe sin consola (sys.stdout es None)."""
    if sys.stdout is None:
        return
    try:
        print(*args, flush=True)
    except (OSError, ValueError):
        pass


class DryRunInjector:
    """Solo muestra los códigos; útil para probar sin teclear nada."""

    def __call__(self, text: str, suffix: str) -> None:
        safe_print(f"código: {text}{SUFFIX_LABEL.get(suffix, '')}")
