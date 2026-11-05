"""Inicio automático con la sesión (registro Run en Windows, .desktop en Linux)."""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SerialWedge"
DESKTOP_NAME = "serial-wedge.desktop"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" -m serial_wedge'


def linux_autostart_dir() -> Path:
    return Path.home() / ".config" / "autostart"


def _quoted(command: str) -> str:
    return command if command.startswith('"') else f'"{command}"'


def _winreg(mod):
    if mod is None:
        import winreg as mod  # noqa: PLC0415 - solo existe en Windows
    return mod


def set_autostart(enabled: bool, command: str | None = None, *, platform=sys.platform,
                  winreg_mod=None, autostart_dir: Path | None = None) -> None:
    command = command or startup_command()
    if platform == "win32":
        reg = _winreg(winreg_mod)
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            if enabled:
                reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, _quoted(command))
            else:
                try:
                    reg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return
    path = Path(autostart_dir or linux_autostart_dir()) / DESKTOP_NAME
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=Pistola Serial\n"
            f"Exec={command}\nX-GNOME-Autostart-enabled=true\nTerminal=false\n",
            encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def is_autostart(*, platform=sys.platform, winreg_mod=None, autostart_dir: Path | None = None) -> bool:
    if platform == "win32":
        reg = _winreg(winreg_mod)
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
                reg.QueryValueEx(key, VALUE_NAME)
            return True
        except OSError:
            return False
    return (Path(autostart_dir or linux_autostart_dir()) / DESKTOP_NAME).exists()
