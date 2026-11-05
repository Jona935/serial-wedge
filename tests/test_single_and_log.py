import logging
import socket

import pytest

from serial_wedge import logsetup, single


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_default_port():
    assert single.PORT == 47653


def test_second_instance_is_rejected_then_allowed_after_release():
    port = free_port()
    first = single.acquire(port)
    assert first is not None
    try:
        assert single.acquire(port) is None
    finally:
        first.close()
    again = single.acquire(port)
    assert again is not None
    again.close()


def test_binds_loopback_only():
    s = single.acquire(free_port())
    try:
        assert s.getsockname()[0] == "127.0.0.1"
    finally:
        s.close()


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def test_log_file_rotating_info(wedge_dir, clean_root):
    path = logsetup.setup_logging()
    assert path == wedge_dir / "serial-wedge.log"
    logging.getLogger("serial_wedge.x").info("arranque")
    logging.getLogger("serial_wedge.x").debug("código secreto 123")
    for h in logging.getLogger().handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "arranque" in text and "secreto" not in text
    h = next(h for h in logging.getLogger().handlers if getattr(h, "_serial_wedge", False))
    assert (h.maxBytes, h.backupCount) == (512 * 1024, 3)


def test_log_setup_twice_does_not_duplicate(wedge_dir, clean_root):
    logsetup.setup_logging()
    logsetup.setup_logging()
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_serial_wedge", False)]
    assert len(ours) == 1
