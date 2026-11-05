"""Bucle de lectura: bytes del puerto -> códigos tecleados."""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)
_TERMINATORS = re.compile(rb"[\r\n]+")


def run_wedge(conn, type_code, *, suffix, prefix, on_code=None, should_stop, max_buffer=2048):
    """Lee hasta que should_stop() sea verdadero. Solo lee: nunca escribe al puerto.

    Un código termina en CR/LF o, si el lector no manda terminador, cuando la
    lectura vuelve vacía (el tiempo de espera del puerto) con datos pendientes.
    Los OSError de read() se propagan para que el servicio reconecte.
    """
    buf = b""

    def emit(raw: bytes):
        code = raw.decode("utf-8", errors="replace").strip()
        if not code:
            return
        if on_code:
            on_code(code)
        type_code(prefix + code, suffix)

    while not should_stop():
        chunk = conn.read(64)
        if not chunk:
            if buf:
                emit(buf)
                buf = b""
            continue
        *complete, buf = _TERMINATORS.split(buf + chunk)
        for raw in complete:
            emit(raw)
        if len(buf) > max_buffer:
            log.warning("Se descartaron %d bytes sin terminador (¿velocidad incorrecta?)", len(buf))
            buf = b""
