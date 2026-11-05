import pytest

from serial_wedge import __main__ as cli
from serial_wedge import __version__
from serial_wedge.injector import DryRunInjector, WedgeUnavailable


class FakeService:
    instances = []

    def __init__(self, **kw):
        self.kw = kw
        self.started = self.stopped = False
        FakeService.instances.append(self)

    def start(self):
        self.started = True
        self.kw["on_state"]("conectado", "X a 9600 baudios")

    def stop(self):
        self.stopped = True


@pytest.fixture
def fakes(monkeypatch):
    FakeService.instances.clear()
    monkeypatch.setattr(cli, "WedgeService", FakeService)
    monkeypatch.setattr(cli, "wait_for_exit", lambda: None)
    monkeypatch.setattr(cli.single, "acquire", lambda: object())
    monkeypatch.setattr(cli, "setup_logging", lambda: None)
    return FakeService.instances


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_parse_overrides():
    a = cli.parse_args(["--no-tray", "--dry-run", "--port", "/tmp/x", "--baud", "4800"])
    assert (a.no_tray, a.dry_run, a.port, a.baud) == (True, True, "/tmp/x", 4800)


def test_headless_dry_run_with_overrides(fakes, capsys):
    assert cli.main(["--no-tray", "--dry-run", "--port", "/tmp/wedgeB", "--baud", "19200"]) == 0
    svc = fakes[0]
    assert svc.started and svc.stopped
    assert svc.kw["overrides"] == {"port": "/tmp/wedgeB", "baud": 19200}
    assert isinstance(svc.kw["injector"], DryRunInjector)
    assert "conectado" in capsys.readouterr().out


def test_no_overrides_by_default(fakes):
    cli.main(["--no-tray", "--dry-run"])
    assert fakes[0].kw["overrides"] == {}


def test_already_running_exits_quietly(fakes, monkeypatch, capsys):
    monkeypatch.setattr(cli.single, "acquire", lambda: None)
    assert cli.main(["--no-tray", "--dry-run"]) == 0
    assert fakes == []


def test_missing_xdotool_reports_and_fails(fakes, monkeypatch, capsys):
    def boom():
        raise WedgeUnavailable("Instale xdotool: sudo apt install xdotool (solo X11)")
    monkeypatch.setattr(cli, "make_injector", boom)
    assert cli.main(["--no-tray"]) == 2
    assert "xdotool" in capsys.readouterr().out
    assert fakes == []


def test_settings_mode_skips_guard(monkeypatch):
    called = []
    monkeypatch.setattr(cli, "run_settings", lambda: called.append(True))
    monkeypatch.setattr(cli.single, "acquire", lambda: pytest.fail("no debe tomar el candado"))
    assert cli.main(["--settings"]) == 0 and called == [True]


def test_tray_mode_uses_tray(fakes, monkeypatch):
    ran = []

    class FakeTray:
        def __init__(self, make_service):
            self.svc = make_service(lambda s, d: None)

        def run(self):
            ran.append(self.svc)

    monkeypatch.setattr(cli, "TrayApp", FakeTray)
    assert cli.main(["--dry-run"]) == 0
    assert ran and isinstance(ran[0], FakeService)


def test_tray_failure_falls_back_to_headless(fakes, monkeypatch):
    class BrokenTray:
        def __init__(self, make_service):
            pass

        def run(self):
            raise RuntimeError("sin bandeja")

    monkeypatch.setattr(cli, "TrayApp", BrokenTray)
    assert cli.main(["--dry-run"]) == 0
    assert fakes[0].started and fakes[0].stopped


def test_main_survives_without_stdout(fakes, monkeypatch):
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    assert cli.main(["--no-tray", "--dry-run"]) == 0
