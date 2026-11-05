import subprocess

import pytest

from serial_wedge import injector
from serial_wedge.injector import (
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, WedgeUnavailable, build_key_events, make_injector,
)

DOWN, UP = KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP


def test_flag_values():
    assert (KEYEVENTF_UNICODE, KEYEVENTF_KEYUP) == (0x0004, 0x0002)


def test_events_for_text_with_enter():
    assert build_key_events("A1", "enter") == [
        (0, ord("A"), DOWN), (0, ord("A"), UP),
        (0, ord("1"), DOWN), (0, ord("1"), UP),
        (0x0D, 0, 0), (0x0D, 0, 0x0002),
    ]


def test_events_tab_and_none():
    assert build_key_events("", "tab") == [(0x09, 0, 0), (0x09, 0, 0x0002)]
    assert build_key_events("x", "none") == [(0, ord("x"), DOWN), (0, ord("x"), UP)]


def test_events_non_ascii_bmp():
    assert build_key_events("ñ", "none") == [(0, 0xF1, DOWN), (0, 0xF1, UP)]


def test_events_surrogate_pair():
    ev = build_key_events("😀", "none")  # U+1F600
    assert [e[1] for e in ev] == [0xD83D, 0xD83D, 0xDE00, 0xDE00]
    assert [e[2] for e in ev] == [DOWN, UP, DOWN, UP]


def test_events_unknown_suffix_rejected():
    with pytest.raises(ValueError):
        build_key_events("x", "f5")


def test_windows_selection_uses_sendinput(monkeypatch):
    sent = []
    monkeypatch.setattr(injector, "_send_windows", sent.append)
    make_injector(platform="win32")("7", "enter")
    assert sent == [build_key_events("7", "enter")]


class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        assert kw.get("check") is True
        return subprocess.CompletedProcess(argv, 0)


def test_linux_xdotool_argv_enter():
    run = FakeRun()
    make_injector(platform="linux", which=lambda n: "/usr/bin/xdotool", run=run)("75012", "enter")
    assert run.calls == [
        ["/usr/bin/xdotool", "type", "--clearmodifiers", "--delay", "0", "--", "75012"],
        ["/usr/bin/xdotool", "key", "Return"],
    ]


def test_linux_xdotool_argv_tab_and_none():
    run = FakeRun()
    inj = make_injector(platform="linux", which=lambda n: "xdotool", run=run)
    inj("-A", "tab")
    inj("B", "none")
    assert run.calls == [
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", "-A"],
        ["xdotool", "key", "Tab"],
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", "B"],
    ]


def test_linux_without_xdotool_raises():
    with pytest.raises(WedgeUnavailable, match="Instale xdotool"):
        make_injector(platform="linux", which=lambda n: None)


def test_dry_run_prints(capsys):
    injector.DryRunInjector()("123", "enter")
    assert "123" in capsys.readouterr().out


def test_dry_run_survives_missing_stdout(monkeypatch):
    monkeypatch.setattr("sys.stdout", None)
    injector.DryRunInjector()("123", "enter")  # no debe fallar
