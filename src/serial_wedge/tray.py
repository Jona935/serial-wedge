"""Icono en la bandeja del sistema (pystray). La lógica pura se prueba sin pantalla."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from . import autostart, config as cfgmod
from .logsetup import log_path

log = logging.getLogger(__name__)
ICON_PATH = Path(__file__).resolve().parent / "assets" / "serial-wedge.png"
COLORS = {
    "conectado": (46, 160, 67),
    "sin_puerto": (240, 190, 30),
    "error": (220, 45, 45),
    "pausado": (140, 140, 140),
}
LABELS = {"conectado": "conectado", "sin_puerto": "sin puerto", "error": "error", "pausado": "en pausa"}


def _describe(state: str, detail: str) -> str:
    text = LABELS.get(state, state)
    return f"{text} ({detail})" if detail else text


def tooltip(state: str, detail: str) -> str:
    text = f"Pistola Serial: {_describe(state, detail)}"
    return text if len(text) <= 120 else text[:119] + "…"


def status_line(state: str, detail: str) -> str:
    return f"Estado: {_describe(state, detail)}"


def base_image() -> Image.Image:
    try:
        return Image.open(ICON_PATH).convert("RGBA")
    except OSError:  # sin el PNG, un cuadrado azul basta
        return Image.new("RGBA", (256, 256), (22, 45, 94, 255))


def make_image(state: str, base: Image.Image | None = None) -> Image.Image:
    img = (base or base_image()).resize((64, 64), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    d.ellipse([40, 40, 63, 63], fill=COLORS.get(state, COLORS["pausado"]) + (255,),
              outline=(255, 255, 255, 255), width=2)
    return img


@dataclass
class Item:
    text: str | Callable[[], str] | None  # None = separador
    action: Callable[[], None] | None = None
    enabled: bool = True
    checked: Callable[[], bool] | None = None


def build_menu(cb: dict, *, status, paused, autostart) -> list[Item]:
    login = "Iniciar con Windows" if sys.platform == "win32" else "Iniciar con la sesión"
    return [
        Item(status, enabled=False),
        Item(None),
        Item(lambda: "Reanudar" if paused() else "Pausar", cb["toggle_pause"]),
        Item("Configuración…", cb["settings"]),
        Item("Ver registro", cb["log"]),
        Item(login, cb["toggle_autostart"], checked=autostart),
        Item(None),
        Item("Salir", cb["quit"]),
    ]


def _with_item(fn):
    """pystray llama a text/checked con el MenuItem; nuestras funciones no lo usan."""
    return lambda _item: fn()


def _no_args(fn):
    return lambda: fn()


def to_pystray(items: list[Item], pystray) -> list:
    out = []
    for it in items:
        if it.text is None:
            out.append(pystray.Menu.SEPARATOR)
            continue
        text = _with_item(it.text) if callable(it.text) else it.text
        checked = _with_item(it.checked) if it.checked else None
        # pystray decide cómo llamar según el número de argumentos: siempre cero
        action = _no_args(it.action) if it.action else None
        out.append(pystray.MenuItem(text, action, enabled=it.enabled, checked=checked))
    return out


def settings_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--settings"]
    return [sys.executable, "-m", "serial_wedge", "--settings"]


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Notifier:
    """Decide cuándo mostrar un aviso: primera conexión y pérdida de conexión, máx. 1 cada 30 s."""

    def __init__(self, clock=time.monotonic, min_interval=30.0):
        self.clock, self.min_interval = clock, min_interval
        self.prev, self.ever_connected, self.last = None, False, None

    def message(self, state, detail):
        prev, self.prev = self.prev, state
        msg = None
        if state == "conectado" and not self.ever_connected:
            self.ever_connected = True
            msg = f"Lector conectado: {detail}"
        elif prev == "conectado" and state in ("error", "sin_puerto"):
            msg = "Se perdió la conexión con el lector; reintentando…"
        if msg is None:
            return None
        now = self.clock()
        if self.last is not None and now - self.last < self.min_interval:
            return None
        self.last = now
        return msg


class TrayApp:  # pragma: no cover - necesita bandeja del sistema real
    def __init__(self, make_service):
        self.service = make_service(self._on_state)
        self.notifier = Notifier()
        self.base = base_image()
        self.icon = None

    def _on_state(self, state, detail):
        if not self.icon:
            return
        self.icon.icon = make_image(state, self.base)
        self.icon.title = tooltip(state, detail)
        self.icon.update_menu()
        if msg := self.notifier.message(state, detail):
            try:
                self.icon.notify(msg, "Pistola Serial")
            except Exception:
                pass

    def _toggle_pause(self):
        self.service.set_paused(not self.service.config.paused)

    def _settings(self):
        try:
            subprocess.Popen(settings_command())
        except OSError:
            log.exception("No se pudo abrir la configuración")

    def _log(self):
        try:
            open_path(log_path())
        except Exception:
            log.exception("No se pudo abrir el registro")

    def _toggle_autostart(self):
        enabled = not autostart.is_autostart()
        try:
            autostart.set_autostart(enabled)
            cfg = cfgmod.load()
            cfg.autostart = enabled
            cfgmod.save(cfg)
        except Exception:
            log.exception("No se pudo cambiar el inicio automático")

    def _quit(self):
        self.service.stop()
        self.icon.stop()

    def run(self):
        import pystray

        items = build_menu(
            {"toggle_pause": self._toggle_pause, "settings": self._settings, "log": self._log,
             "toggle_autostart": self._toggle_autostart, "quit": self._quit},
            status=lambda: status_line(self.service.state, self.service.detail),
            paused=lambda: self.service.config.paused,
            autostart=autostart.is_autostart,
        )
        self.icon = pystray.Icon("serial-wedge", make_image("pausado", self.base), "Pistola Serial",
                                 menu=pystray.Menu(*to_pystray(items, pystray)))

        def setup(icon):
            icon.visible = True
            self.service.start()

        self.icon.run(setup=setup)
