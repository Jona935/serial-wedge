"""Punto de entrada: serial-wedge [--settings | --no-tray] [--dry-run] [--port P] [--baud N]."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime

from . import __version__, single
from .injector import DryRunInjector, WedgeUnavailable, make_injector, safe_print
from .logsetup import setup_logging
from .service import WedgeService
from .tray import TrayApp

log = logging.getLogger("serial_wedge")


def parse_args(argv):
    p = argparse.ArgumentParser(prog="serial-wedge",
                                description="Teclea en la ventana activa los códigos de un lector serial.")
    p.add_argument("--settings", action="store_true", help="abrir la ventana de configuración")
    p.add_argument("--no-tray", action="store_true", help="sin icono de bandeja, en primer plano (Ctrl+C sale)")
    p.add_argument("--dry-run", action="store_true", help="mostrar los códigos en vez de teclearlos")
    p.add_argument("--port", help="usar este puerto (ignora config.json)")
    p.add_argument("--baud", type=int, help="usar esta velocidad (ignora config.json)")
    p.add_argument("--version", action="store_true", help="mostrar la versión")
    return p.parse_args(argv)


def run_settings():
    from .settings_ui import run_settings as run
    run()


def wait_for_exit():
    """Bloquea hasta Ctrl+C o SIGTERM."""
    done = threading.Event()
    try:
        signal.signal(signal.SIGTERM, lambda *_: done.set())
    except ValueError:  # fuera del hilo principal
        pass
    try:
        while not done.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass


def _print_state(state, detail):
    safe_print(f"[{datetime.now():%H:%M:%S}] estado: {state} — {detail}")


def main(argv=None) -> int:
    for name in ("stdout", "stderr"):  # .exe --windowed: no hay consola
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.version:
        safe_print(f"serial-wedge {__version__}")
        return 0
    if args.settings:
        run_settings()
        return 0

    guard = single.acquire()
    if guard is None:
        safe_print("Pistola Serial ya está en ejecución.")
        return 0
    setup_logging()
    try:
        injector = DryRunInjector() if args.dry_run else make_injector()
    except WedgeUnavailable as exc:
        log.error("%s", exc)
        safe_print(str(exc))
        return 2
    overrides = {k: v for k, v in (("port", args.port), ("baud", args.baud)) if v is not None}

    def make_service(on_state):
        return WedgeService(injector=injector, on_state=on_state, overrides=overrides)

    log.info("Pistola Serial %s iniciada", __version__)
    try:
        if not args.no_tray:
            tray = None
            try:
                tray = TrayApp(make_service)
                tray.run()
                return 0
            except Exception:
                if getattr(tray, "service", None) is not None:
                    tray.service.stop()
                log.exception("No se pudo mostrar el icono de bandeja; se sigue sin él")
                safe_print("Sin bandeja del sistema; funcionando en primer plano (Ctrl+C para salir).")
        service = make_service(_print_state)
        service.start()
        try:
            wait_for_exit()
        finally:
            service.stop()
        return 0
    finally:
        log.info("Pistola Serial detenida")
        if hasattr(guard, "close"):
            guard.close()


if __name__ == "__main__":
    sys.exit(main())
