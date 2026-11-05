import json
import os

from serial_wedge import config
from serial_wedge.config import Config


def test_defaults():
    c = Config()
    assert (c.port, c.vid, c.pid, c.baud) == ("auto", None, None, 9600)
    assert (c.bytesize, c.parity, c.stopbits) == (8, "N", 1)
    assert (c.suffix, c.prefix, c.autostart, c.paused) == ("enter", "", False, False)


def test_config_dir_env_override(wedge_dir):
    assert config.config_dir() == wedge_dir


def test_config_dir_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("SERIAL_WEDGE_DIR")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.config_dir(platform="win32") == tmp_path / "SerialWedge"


def test_config_dir_linux(monkeypatch, tmp_path):
    monkeypatch.delenv("SERIAL_WEDGE_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.config_dir(platform="linux") == tmp_path / ".config" / "serial-wedge"


def test_load_missing_file_gives_defaults():
    assert config.load() == Config()


def test_load_corrupt_file_gives_defaults(wedge_dir):
    wedge_dir.mkdir()
    config.config_path().write_text("{no es json", encoding="utf-8")
    assert config.load() == Config()


def test_load_non_dict_json_gives_defaults(wedge_dir):
    wedge_dir.mkdir()
    config.config_path().write_text("[1, 2]", encoding="utf-8")
    assert config.load() == Config()


def test_load_invalid_values_fall_back_field_by_field(wedge_dir):
    wedge_dir.mkdir()
    config.config_path().write_text(json.dumps({
        "port": "COM7", "baud": "rápido", "bytesize": 9, "parity": "X",
        "stopbits": 3, "suffix": "f5", "prefix": 42, "vid": 1027, "pid": "x",
        "autostart": "si", "paused": True, "desconocido": 1,
    }), encoding="utf-8")
    c = config.load()
    assert c.port == "COM7" and c.vid == 1027 and c.paused is True
    assert (c.baud, c.bytesize, c.parity, c.stopbits) == (9600, 8, "N", 1)
    assert (c.suffix, c.prefix, c.pid, c.autostart) == ("enter", "", None, False)


def test_load_accepts_valid_values(wedge_dir):
    wedge_dir.mkdir()
    config.config_path().write_text(json.dumps({
        "baud": 115200, "bytesize": 7, "parity": "E", "stopbits": 2,
        "suffix": "tab", "prefix": ">", "autostart": True,
    }), encoding="utf-8")
    c = config.load()
    assert (c.baud, c.bytesize, c.parity, c.stopbits) == (115200, 7, "E", 2)
    assert (c.suffix, c.prefix, c.autostart) == ("tab", ">", True)


def test_save_roundtrip_and_creates_dir(wedge_dir):
    c = Config(port="COM3", vid=0x0403, pid=0x6001, baud=19200, suffix="none")
    config.save(c)
    assert config.load() == c
    assert json.loads(config.config_path().read_text(encoding="utf-8"))["port"] == "COM3"


def test_save_is_atomic(wedge_dir, monkeypatch):
    config.save(Config(port="COM1"))
    calls = []
    real = os.replace
    monkeypatch.setattr(config.os, "replace", lambda a, b: (calls.append((a, b)), real(a, b)))
    config.save(Config(port="COM2"))
    assert len(calls) == 1 and str(calls[0][1]) == str(config.config_path())
    assert config.load().port == "COM2"
    assert [p.name for p in wedge_dir.iterdir()] == ["config.json"]
