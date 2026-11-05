import json
import os

import pytest

from serial_wedge import config
from serial_wedge.config import Config
from serial_wedge.ports import PortInfo

tk = pytest.importorskip("tkinter")

FTDI = PortInfo("COM3", "USB Serial Port", 0x0403, 0x6001)
NATIVE = PortInfo("COM1", "Puerto de comunicaciones", None, None)


@pytest.fixture
def root():
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("sin pantalla")
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk no disponible")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def make(root):
    from serial_wedge.settings_ui import SettingsWindow

    def factory(ports=(NATIVE, FTDI), running=True):
        calls = []
        w = SettingsWindow(root, list_fn=lambda: list(ports),
                           autostart_fn=lambda enabled: calls.append(enabled),
                           is_autostart_fn=lambda: False, running_fn=lambda: running, poll_ms=0)
        w.autostart_calls = calls
        return w
    return factory


def saved():
    return json.loads(config.config_path().read_text(encoding="utf-8"))


def test_title_and_port_choices(make, root):
    w = make()
    assert root.title() == "Pistola Serial — Configuración"
    assert w.port_box["values"] == ("Automático", "COM1 — Puerto de comunicaciones",
                                    "COM3 — USB Serial Port (0403:6001)")
    assert w.port_var.get() == "Automático"


def test_save_selected_port_with_ids(make):
    w = make()
    w.port_var.set("COM3 — USB Serial Port (0403:6001)")
    w.baud_var.set("19200")
    w.bytesize_var.set("7")
    w.parity_var.set("Par (E)")
    w.stopbits_var.set("2")
    w.suffix_var.set("Tab")
    w.prefix_var.set("#")
    w.autostart_var.set(True)
    w.save()
    d = saved()
    assert (d["port"], d["vid"], d["pid"]) == ("COM3", 0x0403, 0x6001)
    assert (d["baud"], d["bytesize"], d["parity"], d["stopbits"]) == (19200, 7, "E", 2)
    assert (d["suffix"], d["prefix"], d["autostart"]) == ("tab", "#", True)
    assert w.autostart_calls == [True]
    assert "Guardado" in w.message_var.get()


def test_save_automatic_clears_ids(make):
    config.save(Config(port="COM3", vid=1, pid=2, paused=True))
    w = make()
    w.port_var.set("Automático")
    w.suffix_var.set("Nada")
    w.save()
    d = saved()
    assert (d["port"], d["vid"], d["pid"], d["suffix"]) == ("auto", None, None, "none")
    assert d["paused"] is True  # la pausa no se toca desde aquí


def test_loads_existing_config(make):
    config.save(Config(port="COM3", vid=0x0403, pid=0x6001, baud=4800, parity="O", suffix="tab"))
    w = make()
    assert w.port_var.get() == "COM3 — USB Serial Port (0403:6001)"
    assert (w.baud_var.get(), w.parity_var.get(), w.suffix_var.get()) == ("4800", "Impar (O)", "Tab")


def test_absent_configured_port_is_kept(make):
    config.save(Config(port="COM9", vid=5, pid=6))
    w = make(ports=(FTDI,))
    assert w.port_var.get() == "COM9 (no conectado)"
    w.save()
    assert (saved()["port"], saved()["vid"], saved()["pid"]) == ("COM9", 5, 6)


def test_invalid_baud_not_saved(make):
    w = make()
    w.baud_var.set("rápido")
    w.save()
    assert not config.config_path().exists()
    assert "velocidad" in w.message_var.get().lower()


def test_refresh_ports(make):
    ports = [NATIVE]
    w = make()
    w.list_fn = lambda: list(ports)
    ports.append(FTDI)
    w.refresh_ports()
    assert len(w.port_box["values"]) == 3


def test_status_polling(make):
    config.write_json_atomic(config.config_dir() / "status.json", {
        "state": "conectado", "detail": "COM3 a 9600 baudios", "port": "COM3",
        "last_code": "7501234567890", "count": 4, "updated": "2026-11-05T10:00:00"})
    w = make()
    w.poll_status()
    assert "conectado" in w.state_var.get()
    assert w.code_var.get() == "Último código leído: 7501234567890  (4 códigos)"


def test_status_when_service_not_running(make):
    w = make(running=False)
    w.poll_status()
    assert "no está en ejecución" in w.state_var.get()
