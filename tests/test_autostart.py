import sys

from serial_wedge import autostart
from serial_wedge.autostart import RUN_KEY, VALUE_NAME, is_autostart, set_autostart, startup_command


class FakeKey:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    KEY_READ = 1
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.opened = []

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        self.opened.append((root, path))
        return FakeKey(self.values)

    OpenKey = CreateKeyEx

    def SetValueEx(self, key, name, reserved, kind, value):
        assert kind == self.REG_SZ
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ


EXE = r"C:\Programas\Pistola Serial\serial-wedge.exe"


def test_windows_enable_writes_quoted_path():
    reg = FakeWinreg()
    set_autostart(True, EXE, platform="win32", winreg_mod=reg)
    assert reg.values == {VALUE_NAME: f'"{EXE}"'}
    assert reg.opened[0] == ("HKCU", RUN_KEY)
    assert RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run" and VALUE_NAME == "SerialWedge"
    assert is_autostart(platform="win32", winreg_mod=reg)


def test_windows_command_with_args_not_requoted():
    reg = FakeWinreg()
    set_autostart(True, '"C:\\py\\python.exe" -m serial_wedge', platform="win32", winreg_mod=reg)
    assert reg.values[VALUE_NAME] == '"C:\\py\\python.exe" -m serial_wedge'


def test_windows_disable_and_disable_twice():
    reg = FakeWinreg()
    set_autostart(True, EXE, platform="win32", winreg_mod=reg)
    set_autostart(False, EXE, platform="win32", winreg_mod=reg)
    set_autostart(False, EXE, platform="win32", winreg_mod=reg)  # no falla
    assert reg.values == {} and not is_autostart(platform="win32", winreg_mod=reg)


def test_linux_desktop_file(tmp_path):
    set_autostart(True, "/opt/sw/serial-wedge", platform="linux", autostart_dir=tmp_path)
    f = tmp_path / "serial-wedge.desktop"
    text = f.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text and "Exec=/opt/sw/serial-wedge" in text
    assert is_autostart(platform="linux", autostart_dir=tmp_path)
    set_autostart(False, "x", platform="linux", autostart_dir=tmp_path)
    assert not f.exists() and not is_autostart(platform="linux", autostart_dir=tmp_path)
    set_autostart(False, "x", platform="linux", autostart_dir=tmp_path)  # idempotente


def test_linux_default_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    assert autostart.linux_autostart_dir() == tmp_path / ".config" / "autostart"


def test_startup_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", EXE)
    assert startup_command() == EXE


def test_startup_command_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert startup_command() == f'"{sys.executable}" -m serial_wedge'
