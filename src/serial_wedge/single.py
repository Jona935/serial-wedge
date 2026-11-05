"""Una sola instancia: el primero que ocupa el puerto local gana."""
from __future__ import annotations

import socket

PORT = 47653


def acquire(port: int = PORT):
    """Devuelve el socket (mantenerlo abierto) o None si ya hay otra instancia."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        s.close()
        return None
    return s
