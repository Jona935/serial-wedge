"""Servicio en segundo plano: busca el lector, lo abre, teclea y reconecta solo."""
from __future__ import annotations

import dataclasses
import logging
import math
import os
import threading
import time
from datetime import datetime

from . import config as cfgmod
from .ports import list_ports, resolve_port
from .wedge import run_wedge

log = logging.getLogger(__name__)
STATES = ("pausado", "sin_puerto", "conectado", "error")


def open_serial(port, cfg):
    import serial
    return serial.Serial(port, baudrate=cfg.baud, bytesize=cfg.bytesize, parity=cfg.parity,
                         stopbits=cfg.stopbits, timeout=0.2)


def _default_wait(event: threading.Event, seconds: float) -> None:
    event.wait(seconds)


class WedgeService:
    def __init__(self, *, injector, opener=open_serial, list_fn=list_ports, on_state=None,
                 config_path=None, status_path=None, overrides=None, wait_fn=_default_wait,
                 clock=time.monotonic, config_poll=1.0, absent_poll=2.0, max_backoff=10.0):
        self._inject, self._opener, self._list_fn = injector, opener, list_fn
        self._on_state = on_state
        self._config_path = config_path or cfgmod.config_path()
        self._status_path = status_path or cfgmod.config_dir() / "status.json"
        self._overrides = dict(overrides or {})
        self._wait_fn, self._clock = wait_fn, clock
        self._config_poll, self._absent_poll, self._max_backoff = config_poll, absent_poll, max_backoff
        self._stop = threading.Event()
        self._wake = threading.Event()  # interrumpe esperas (parar, pausar, config nueva)
        self._lock = threading.Lock()
        self._sig = None
        self._changed = False
        self._next_check = 0.0
        self.config = self._load()
        self.state, self.detail, self.port = "iniciando", "", None
        self.last_code, self.count = None, 0
        self._conn = None
        self.thread = None

    # -- ciclo de vida -------------------------------------------------
    def start(self):
        self.thread = threading.Thread(target=self._run, name="serial-wedge", daemon=True)
        self.thread.start()
        log.info("Servicio iniciado")

    def stop(self, timeout=5.0):
        self._stop.set()
        self._wake.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout)
        self._close()
        if self.thread:
            log.info("Servicio detenido (%d códigos leídos)", self.count)

    def set_paused(self, paused: bool):
        with self._lock:
            cfg = cfgmod.load(self._config_path)
            cfg.paused = paused
            cfgmod.save(cfg, self._config_path)
            self.config = self._load()  # también actualiza la firma: no cuenta como cambio externo
        log.info("Lectura %s", "en pausa" if paused else "reanudada")
        self._wake.set()

    # -- configuración -------------------------------------------------
    def _signature(self):
        try:
            st = os.stat(self._config_path)
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def _load(self):
        self._sig = self._signature()
        cfg = cfgmod.load(self._config_path)
        return dataclasses.replace(cfg, **self._overrides) if self._overrides else cfg

    def _config_changed(self) -> bool:
        """True si config.json cambió (y entonces la recarga)."""
        if self._signature() == self._sig:
            return False
        with self._lock:
            self.config = self._load()
        log.info("Configuración recargada")
        return True

    # -- estado --------------------------------------------------------
    def _set_state(self, state, detail):
        if (state, detail) == (self.state, self.detail):
            return
        self.state, self.detail = state, detail
        log.info("Estado: %s (%s)", state, detail)
        self._write_status()
        if self._on_state:
            try:
                self._on_state(state, detail)
            except Exception:
                log.exception("Error en on_state")

    def _write_status(self):
        try:
            cfgmod.write_json_atomic(self._status_path, {
                "state": self.state, "detail": self.detail, "port": self.port,
                "last_code": self.last_code, "count": self.count,
                "updated": datetime.now().isoformat(timespec="seconds"),
            })
        except OSError:
            log.exception("No se pudo escribir status.json")

    def _got_code(self, code):
        self.last_code, self.count = code, self.count + 1
        log.debug("Código leído: %r", code)
        if self.count % 100 == 1:
            log.info("Códigos leídos: %d", self.count)
        self._write_status()

    def _type(self, text, suffix):
        try:
            self._inject(text, suffix)
        except Exception as exc:  # un fallo al teclear no debe cortar la conexión
            log.error("No se pudo teclear el código: %s", exc)

    # -- bucle -----------------------------------------------------------
    def _sleep(self, seconds) -> None:
        """Espera interrumpible por stop(), set_paused() o cambio de configuración."""
        slices = max(1, math.ceil(seconds / self._config_poll))
        for _ in range(slices):
            if self._stop.is_set() or self._wake.is_set():
                return
            self._wait_fn(self._wake, min(seconds, self._config_poll))
            if self._config_changed():
                return

    def _should_leave(self) -> bool:
        if self._stop.is_set() or self.config.paused:
            return True
        now = self._clock()
        if now >= self._next_check:
            self._next_check = now + self._config_poll
            return self._config_changed()
        return False

    def _close(self):
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _run(self):
        backoff = 1
        while not self._stop.is_set():
            self._wake.clear()
            self._config_changed()
            cfg = self.config
            if cfg.paused:
                self.port = None
                self._set_state("pausado", "lectura en pausa")
                self._sleep(self._config_poll)
                continue
            device, reason = resolve_port(cfg, self._list_fn)
            if device is None:
                self.port = None
                self._set_state("sin_puerto", reason)
                self._sleep(self._absent_poll)
                continue
            try:
                self._conn = self._opener(device, cfg)
            except Exception as exc:
                self._set_state("error", f"no se pudo abrir {device}: {exc}")
                self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)
                continue
            backoff = 1
            self.port = device
            self._set_state("conectado", f"{device} a {cfg.baud} baudios")
            try:
                run_wedge(self._conn, self._type, suffix=cfg.suffix, prefix=cfg.prefix,
                          on_code=self._got_code, should_stop=self._should_leave)
            except Exception as exc:
                log.warning("Se perdió la conexión con %s: %s", device, exc)
                self._close()
                self._set_state("error", f"se perdió {device}: {exc}")
                self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)
            finally:
                self._close()
