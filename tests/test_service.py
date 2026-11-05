import json
import os
import queue
import threading
import time

import pytest

from serial_wedge import config
from serial_wedge.config import Config
from serial_wedge.ports import PortInfo
from serial_wedge.service import WedgeService

SCANNER = PortInfo("COM3", "Lector", 0x0403, 0x6001)


def wait_until(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.005)
    raise AssertionError("condición no alcanzada a tiempo")


class FakeSerial:
    def __init__(self, port, cfg):
        self.port, self.cfg = port, cfg
        self.q = queue.Queue()
        self.closed = False

    def feed(self, item):
        self.q.put(item)

    def read(self, n):
        try:
            item = self.q.get(timeout=0.01)
        except queue.Empty:
            return b""
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, data):
        raise AssertionError("nunca se escribe al puerto")

    def close(self):
        self.closed = True


class Opener:
    """Abre FakeSerial; puede fallar las primeras `fail` veces."""

    def __init__(self, fail=0):
        self.fail = fail
        self.calls = []
        self.conns = []

    def __call__(self, port, cfg):
        self.calls.append((port, cfg))
        if self.fail:
            self.fail -= 1
            raise OSError("acceso denegado")
        conn = FakeSerial(port, cfg)
        self.conns.append(conn)
        return conn


@pytest.fixture
def make():
    made = []

    def factory(opener=None, ports=(SCANNER,), cfg=None, **kw):
        if cfg is not None:
            config.save(cfg)
        typed, states, waits = [], [], []
        port_list = list(ports)
        kw.setdefault("wait_fn", lambda ev, s: (waits.append(s), ev.wait(0.005)))
        svc = WedgeService(
            opener=opener or Opener(), injector=lambda t, s: typed.append((t, s)),
            list_fn=lambda: list(port_list), on_state=lambda st, d: states.append(st), **kw)
        svc.typed, svc.states, svc.waits, svc.port_list = typed, states, waits, port_list
        made.append(svc)
        svc.start()
        return svc

    yield factory
    for svc in made:
        svc.stop()


def status():
    try:
        return json.loads((config.config_dir() / "status.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def touch_config(cfg):
    config.save(cfg)
    p = config.config_path()
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def test_connects_and_types_codes(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    op.conns[0].feed(b"7501234567890\r\n")
    op.conns[0].feed(b"ABC")
    wait_until(lambda: len(svc.typed) == 2)
    assert svc.typed == [("7501234567890", "enter"), ("ABC", "enter")]
    assert op.calls[0][0] == "COM3"


def test_status_json_content(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    op.conns[0].feed(b"111\r\n222\r\n")
    wait_until(lambda: status().get("count") == 2)
    st = status()
    assert st["state"] == "conectado" and st["port"] == "COM3"
    assert st["last_code"] == "222" and isinstance(st["updated"], str)
    assert "detail" in st


def test_prefix_and_suffix_from_config(make):
    op = Opener()
    svc = make(op, cfg=Config(prefix="#", suffix="tab"))
    wait_until(lambda: svc.state == "conectado")
    op.conns[0].feed(b"5\n")
    wait_until(lambda: svc.typed)
    assert svc.typed == [("#5", "tab")]


def test_open_failure_backoff_then_connects(make):
    op = Opener(fail=2)
    svc = make(op, config_poll=100)
    wait_until(lambda: svc.state == "conectado")
    assert svc.states[:2] == ["error", "conectado"]  # el mismo error no se repite
    assert len(op.calls) == 3 and svc.waits[:2] == [1, 2]


def test_backoff_caps_at_ten_seconds(make):
    op = Opener(fail=10**6)
    svc = make(op, config_poll=100)
    wait_until(lambda: len(svc.waits) >= 7)
    assert svc.waits[:7] == [1, 2, 4, 8, 10, 10, 10]
    assert svc.state == "error" and "acceso denegado" in svc.detail


def test_read_error_mid_stream_reconnects(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    first = op.conns[0]
    first.feed(b"1\r\n")
    first.feed(OSError("cable desconectado"))
    wait_until(lambda: len(op.conns) == 2 and svc.state == "conectado")
    assert first.closed
    assert "error" in svc.states
    op.conns[1].feed(b"2\r\n")
    wait_until(lambda: len(svc.typed) == 2)
    assert [t for t, _ in svc.typed] == ["1", "2"]


def test_no_port_then_port_appears(make):
    op = Opener()
    svc = make(op, ports=(), config_poll=100)
    wait_until(lambda: svc.state == "sin_puerto")
    wait_until(lambda: 2 in svc.waits)
    assert op.calls == []
    svc.port_list.append(SCANNER)
    wait_until(lambda: svc.state == "conectado")


def test_port_vanishes_goes_to_sin_puerto(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    svc.port_list.clear()
    op.conns[0].feed(OSError("se fue"))
    wait_until(lambda: svc.state == "sin_puerto")


def test_pause_and_resume(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    svc.set_paused(True)
    wait_until(lambda: svc.state == "pausado")
    assert op.conns[0].closed and config.load().paused is True
    svc.set_paused(False)
    wait_until(lambda: svc.state == "conectado" and len(op.conns) == 2)


def test_starts_paused_from_config(make):
    op = Opener()
    svc = make(op, cfg=Config(paused=True))
    wait_until(lambda: svc.state == "pausado")
    time.sleep(0.05)
    assert op.calls == []


def test_config_change_reconnects_with_new_settings(make):
    op = Opener()
    svc = make(op, config_poll=0.02)
    wait_until(lambda: svc.state == "conectado")
    touch_config(Config(baud=19200))
    wait_until(lambda: len(op.conns) == 2)
    assert op.conns[0].closed
    assert op.calls[-1][1].baud == 19200


def test_config_change_interrupts_wait(make):
    op = Opener()
    svc = make(op, ports=(), config_poll=0.02, cfg=Config(port="COM3"))
    wait_until(lambda: svc.state == "sin_puerto")
    touch_config(Config(paused=True))
    wait_until(lambda: svc.state == "pausado")


def test_overrides_win_over_file(make):
    op = Opener()
    other = PortInfo("COM4", "Otro", 1, 2)
    svc = make(op, ports=(SCANNER, other), overrides={"port": "COM4", "baud": 4800})
    wait_until(lambda: svc.state == "conectado")
    assert op.calls[0][0] == "COM4" and op.calls[0][1].baud == 4800


def test_injector_error_keeps_connection(make):
    op = Opener()
    calls = []

    def bad(t, s):
        calls.append(t)
        raise OSError("SendInput bloqueado")

    svc = WedgeService(opener=op, injector=bad, list_fn=lambda: [SCANNER])
    svc.start()
    try:
        wait_until(lambda: svc.state == "conectado")
        op.conns[0].feed(b"1\r\n2\r\n")
        wait_until(lambda: len(calls) == 2)
        assert svc.state == "conectado" and len(op.conns) == 1
    finally:
        svc.stop()


def test_stop_joins_and_closes(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    t0 = time.monotonic()
    svc.stop()
    assert time.monotonic() - t0 < 2
    assert not svc.thread.is_alive() and op.conns[0].closed


def test_on_state_callback_sequence(make):
    op = Opener()
    svc = make(op, ports=())
    wait_until(lambda: svc.state == "sin_puerto")
    svc.port_list.append(SCANNER)
    wait_until(lambda: svc.state == "conectado")
    assert svc.states == ["sin_puerto", "conectado"]


def test_never_writes_even_under_traffic(make):
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    for i in range(20):
        op.conns[0].feed(f"{i}\r\n".encode())
    wait_until(lambda: len(svc.typed) == 20)
    assert svc.state == "conectado"


# -- datos para el Probador ------------------------------------------------------
def scan(make, *chunks, n=1, **kw):
    op = Opener()
    svc = make(op, **kw)
    wait_until(lambda: svc.state == "conectado")
    for c in chunks:
        op.conns[0].feed(c)
    wait_until(lambda: status().get("codes_total") == n and status().get("last_typed_at"))
    return svc, status()


@pytest.mark.parametrize("raw,term", [(b"123\r\n", "CRLF"), (b"123\r", "CR"),
                                      (b"123\n", "LF"), (b"123", "ninguno")])
def test_status_terminator(make, raw, term):
    _, st = scan(make, raw)
    assert st["last_terminator"] == term and st["last_code"] == "123"


def test_status_raw_fields(make):
    _, st = scan(make, b"7501234567890\r\n")
    assert st["last_raw_hex"] == "37 35 30 31 32 33 34 35 36 37 38 39 30 0d 0a"
    assert st["last_raw_text"] == "7501234567890\\r\\n" and st["last_raw_len"] == 15
    assert st["bytes_total"] == 15 and st["codes_total"] == 1
    assert st["garbled"] is False and st["garbled_count"] == 0 and st["type_error"] is None
    for k in ("last_code_at", "last_frame_at", "last_typed_at", "updated_ts"):
        assert isinstance(st[k], float)
    assert st["state"] == "conectado" and st["count"] == 1  # lo anterior sigue igual


def test_status_raw_is_capped_to_64_bytes(make):
    _, st = scan(make, b"9" * 100 + b"\r\n")
    assert len(st["last_raw_hex"].split()) == 64 and st["last_raw_len"] == 102


def test_status_garbled_high_bytes(make):
    _, st = scan(make, b"\xe5\x9a\xff\x13A\r\n")
    assert st["garbled"] is True and st["garbled_count"] == 1
    assert "\\xff" in st["last_raw_text"] and "\\x13" in st["last_raw_text"]


def test_status_garbled_clears_on_clean_frame(make):
    _, st = scan(make, b"\xff\xfeA\r\n", b"OK\r\n", n=2)
    assert st["garbled"] is False and st["garbled_count"] == 1


def test_status_type_error_then_cleared(make):
    op = Opener()
    fail = [True]

    def inj(t, s):
        if fail[0]:
            raise OSError(5, "SendInput bloqueado (¿aplicación como Administrador?)")

    svc = WedgeService(opener=op, injector=inj, list_fn=lambda: [SCANNER])
    svc.start()
    try:
        wait_until(lambda: svc.state == "conectado")
        op.conns[0].feed(b"1\r\n")
        wait_until(lambda: status().get("type_error"))
        assert "SendInput" in status()["type_error"]
        fail[0] = False
        op.conns[0].feed(b"2\r\n")
        wait_until(lambda: status().get("codes_total") == 2 and status().get("type_error") is None)
    finally:
        svc.stop()


def test_heartbeat_refreshes_updated_ts(make):
    svc = make(Opener(), heartbeat=0.05)
    wait_until(lambda: status().get("updated_ts"))
    first = status()["updated_ts"]
    wait_until(lambda: status().get("updated_ts", 0) > first)


def test_flow_service_status_evaluar(make):
    """Servicio -> status.json -> evaluar: todo ✅ si el «teclado» entrega lo mismo; ❌ si no."""
    from serial_wedge.probador import FALLO, OK, evaluar, resumen

    config.save(Config(prefix="#"))
    t0 = time.time()
    op = Opener()
    svc = make(op)
    wait_until(lambda: svc.state == "conectado")
    op.conns[0].feed(b"7501234567890\r\n")
    wait_until(lambda: svc.typed and status().get("last_typed_at"))
    texto, suffix = svc.typed[-1]
    entry_at = time.time()
    checks = evaluar(status(), texto, suffix == "enter", config.load(), time.time(),
                     inicio=t0, entry_at=entry_at)
    assert [c.estado for c in checks[:6]] == [OK] * 6 and resumen(checks) == "Todo correcto ✅"
    bad = evaluar(status(), texto[:-1], True, config.load(), time.time(), inicio=t0, entry_at=entry_at)
    assert bad[4].estado == FALLO and "Falta 1 carácter" in bad[4].detalle
