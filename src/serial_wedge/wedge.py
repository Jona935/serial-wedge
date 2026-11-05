"""Bucle de lectura: bytes del puerto -> códigos tecleados."""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)
_SPLIT = re.compile(rb"([\r\n]+)")


def terminator_name(sep: bytes) -> str:
    if not sep:
        return "ninguno"
    if sep.startswith(b"\r\n"):
        return "CRLF"
    return "CR" if sep.startswith(b"\r") else "LF"


def _frames(data: bytes, final: bool):
    """Separa data en [(parte, separador)] y lo que queda pendiente.

    Un CR al final queda pendiente (salvo en el vaciado final) por si el LF llega
    en la siguiente lectura: así CRLF partido en dos lecturas se reconoce como CRLF.
    """
    pieces = _SPLIT.split(data)
    rest = pieces[-1]
    pairs = list(zip(pieces[0:-1:2], pieces[1:-1:2]))
    if not final and pairs and rest == b"" and pairs[-1][1].endswith(b"\r"):
        part, sep = pairs.pop()
        rest = part + sep
    if final and rest:
        pairs.append((rest, b""))
        rest = b""
    return pairs, rest


def run_wedge(conn, type_code, *, suffix, prefix, on_code=None, on_frame=None, on_raw=None,
              should_stop, max_buffer=2048):
    """Lee hasta que should_stop() sea verdadero. Solo lee: nunca escribe al puerto.

    Un código termina en CR/LF o, si el lector no manda terminador, cuando la
    lectura vuelve vacía (el tiempo de espera del puerto) con datos pendientes.
    on_raw(bytes) recibe cada lectura; on_frame(código, bytes_crudos, terminador)
    cada trama. Los OSError de read() se propagan para que el servicio reconecte.
    """
    buf = b""

    def emit(pairs):
        for part, sep in pairs:
            if not part:
                continue
            code = part.decode("utf-8", errors="replace").strip()
            if on_frame:
                on_frame(code, part + sep, terminator_name(sep))
            if not code:
                continue
            if on_code:
                on_code(code)
            type_code(prefix + code, suffix)

    while not should_stop():
        chunk = conn.read(64)
        if not chunk:
            if buf:
                pairs, buf = _frames(buf, final=True)
                emit(pairs)
            continue
        if on_raw:
            on_raw(chunk)
        pairs, buf = _frames(buf + chunk, final=False)
        emit(pairs)
        if len(buf) > max_buffer:
            log.warning("Se descartaron %d bytes sin terminador (¿velocidad incorrecta?)", len(buf))
            buf = b""
