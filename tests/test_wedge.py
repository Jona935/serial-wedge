import pytest

from serial_wedge.wedge import run_wedge


class FakeConn:
    """Devuelve los trozos dados; b'' = tiempo de espera agotado. Al agotarse, pide parar."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.reads = 0

    def read(self, n):
        self.reads += 1
        assert n == 64
        if not self.chunks:
            return b""
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, data):
        raise AssertionError("el programa nunca debe escribir al puerto")

    @property
    def done(self):
        return not self.chunks


def run(chunks, suffix="enter", prefix="", **kw):
    conn = FakeConn(chunks)
    typed, seen = [], []
    run_wedge(conn, lambda t, s: typed.append((t, s)), suffix=suffix, prefix=prefix,
              on_code=seen.append, should_stop=lambda: conn.done and conn.reads > 50, **kw)
    return typed, seen


def test_code_split_across_reads():
    typed, _ = run([b"7501", b"2345", b"67890\r\n"])
    assert typed == [("7501234567890", "enter")]


def test_crlf_and_lf_and_cr():
    typed, _ = run([b"A\r\nB\nC\rD\r\n"])
    assert [t for t, _ in typed] == ["A", "B", "C", "D"]


def test_several_codes_in_one_read():
    typed, _ = run([b"111\r\n222\r\n333\r\n"])
    assert [t for t, _ in typed] == ["111", "222", "333"]


def test_no_terminator_idle_flush():
    typed, _ = run([b"ABC", b"123", b"", b"XYZ"])
    assert [t for t, _ in typed] == ["ABC123", "XYZ"]


def test_empty_lines_and_whitespace_ignored():
    typed, _ = run([b"\r\n\r\n  \r\n  42  \r\n\n"])
    assert [t for t, _ in typed] == ["42"]


def test_prefix_and_suffix_applied_but_on_code_gets_raw():
    typed, seen = run([b"9\r\n"], suffix="tab", prefix=">")
    assert typed == [(">9", "tab")]
    assert seen == ["9"]


def test_invalid_utf8_replaced():
    typed, _ = run([b"A\xffB\r\n"])
    assert typed == [("A�B", "enter")]


def test_buffer_cap_discards_runaway_data():
    typed, _ = run([b"x" * 100, b"y" * 100, b"OK\r\n"], max_buffer=150)
    assert typed[-1] == ("OK", "enter")
    assert all(len(t) <= 150 for t, _ in typed)


def test_stop_returns_immediately():
    conn = FakeConn([b"1\r\n"])
    typed = []
    run_wedge(conn, lambda t, s: typed.append(t), suffix="enter", prefix="", should_stop=lambda: True)
    assert typed == [] and conn.reads == 0


def test_oserror_propagates():
    with pytest.raises(OSError):
        run([b"1\r\n", OSError("desconectado")])


def test_never_writes_to_port():
    # FakeConn.write lanza AssertionError; si se llamara, la prueba fallaría.
    typed, _ = run([b"1\r\n", b"2", b""])
    assert [t for t, _ in typed] == ["1", "2"]
