from types import SimpleNamespace

from serial_wedge import ports
from serial_wedge.config import Config
from serial_wedge.ports import PortInfo, resolve_port

FTDI = PortInfo("COM3", "USB Serial Port", 0x0403, 0x6001)
PL = PortInfo("COM10", "Prolific USB-to-Serial", 0x067B, 0x2303)
NATIVE = PortInfo("COM1", "Puerto de comunicaciones", None, None)


def lister(*items):
    return lambda: list(items)


def test_configured_port_present():
    assert resolve_port(Config(port="COM3"), lister(NATIVE, FTDI)) == ("COM3", "puerto configurado COM3")


def test_configured_port_absent_without_ids():
    dev, reason = resolve_port(Config(port="COM9"), lister(FTDI))
    assert dev is None and "COM9" in reason


def test_vid_pid_finds_renumbered_port():
    cfg = Config(port="COM3", vid=0x0403, pid=0x6001)
    renumbered = PortInfo("COM7", "USB Serial Port", 0x0403, 0x6001)
    dev, reason = resolve_port(cfg, lister(NATIVE, renumbered))
    assert dev == "COM7" and "0403:6001" in reason


def test_vid_pid_not_present():
    dev, reason = resolve_port(Config(port="auto", vid=1, pid=2), lister(FTDI))
    assert dev is None and "0001:0002" in reason


def test_auto_single_usb_port():
    assert resolve_port(Config(), lister(NATIVE, FTDI))[0] == "COM3"


def test_auto_no_usb_port():
    dev, reason = resolve_port(Config(), lister(NATIVE))
    assert dev is None and "no hay" in reason.lower()


def test_auto_several_usb_ports():
    dev, reason = resolve_port(Config(), lister(FTDI, PL))
    assert dev is None
    assert reason == "hay 2 puertos USB; elija uno en Configuración"


def test_list_fn_failure_is_reason_not_crash():
    def boom():
        raise OSError("sin acceso")
    dev, reason = resolve_port(Config(), boom)
    assert dev is None and "sin acceso" in reason


def test_list_ports_natural_sort_and_mapping(monkeypatch):
    raw = [SimpleNamespace(device=d, description=f"desc {d}", vid=v, pid=p)
           for d, v, p in [("COM10", 1, 2), ("COM2", None, None), ("COM1", 3, 4)]]
    monkeypatch.setattr(ports, "_comports", lambda: raw)
    got = ports.list_ports()
    assert [p.device for p in got] == ["COM1", "COM2", "COM10"]
    assert got[0] == PortInfo("COM1", "desc COM1", 3, 4)


def test_label():
    assert ports.label(FTDI) == "COM3 — USB Serial Port (0403:6001)"
    assert ports.label(NATIVE) == "COM1 — Puerto de comunicaciones"


def test_posix_device_path_not_listed_but_existing(tmp_path):
    dev = tmp_path / "ttyFAKE"
    dev.write_text("")
    assert resolve_port(Config(port=str(dev)), lister())[0] == str(dev)
    assert resolve_port(Config(port=str(tmp_path / "nada")), lister())[0] is None
