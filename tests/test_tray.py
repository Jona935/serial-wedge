import sys

from serial_wedge import tray
from serial_wedge.tray import COLORS, Notifier, build_menu, make_image, settings_command, tooltip


def test_state_colours():
    assert COLORS["conectado"] == (46, 160, 67)
    assert set(COLORS) == {"conectado", "sin_puerto", "error", "pausado"}
    assert COLORS["error"][0] > 200 and COLORS["sin_puerto"][1] > 150


def test_tooltip_text_and_limit():
    assert tooltip("conectado", "COM3 a 9600 baudios") == "Pistola Serial: conectado (COM3 a 9600 baudios)"
    assert tooltip("sin_puerto", "").startswith("Pistola Serial: sin puerto")
    assert len(tooltip("error", "x" * 500)) <= 120


def test_status_line():
    assert tray.status_line("sin_puerto", "no hay puertos") == "Estado: sin puerto (no hay puertos)"


def test_make_image_has_status_dot():
    img = make_image("error")
    assert img.size == (64, 64)
    r, g, b, a = img.getpixel((52, 52))
    assert (r, g, b) == COLORS["error"] and a == 255
    assert make_image("pausado").getpixel((52, 52))[:3] == COLORS["pausado"]


def test_make_image_unknown_state_is_grey():
    assert make_image("iniciando").getpixel((52, 52))[:3] == COLORS["pausado"]


def make_menu(paused=False, autostart=False):
    calls = []
    cb = {k: (lambda k=k: calls.append(k)) for k in
          ("toggle_pause", "settings", "log", "toggle_autostart", "quit")}
    items = build_menu(cb, status=lambda: "Estado: conectado", paused=lambda: paused,
                       autostart=lambda: autostart)
    return items, calls


def text(item):
    return item.text() if callable(item.text) else item.text


def test_menu_structure_and_labels(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "win32")
    items, _ = make_menu()
    labels = [text(i) for i in items]
    assert labels == ["Estado: conectado", None, "Pausar", "Configuración…", "Ver registro",
                      "Iniciar con Windows", None, "Salir"]
    assert items[0].enabled is False
    assert items[5].checked() is False


def test_menu_reflects_paused_and_autostart():
    items, _ = make_menu(paused=True, autostart=True)
    assert text(items[2]) == "Reanudar" and items[5].checked() is True


def test_menu_actions_call_callbacks():
    items, calls = make_menu()
    for i in items:
        if i.action:
            i.action()
    assert calls == ["toggle_pause", "settings", "log", "toggle_autostart", "quit"]


def test_autostart_label_on_linux(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "linux")
    items, _ = make_menu()
    assert text(items[5]) == "Iniciar con la sesión"


def test_settings_command_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert settings_command() == [sys.executable, "-m", "serial_wedge", "--settings"]


def test_settings_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\sw\serial-wedge.exe")
    assert settings_command() == [r"C:\sw\serial-wedge.exe", "--settings"]


def test_notifier_first_connection_and_loss_rate_limited():
    now = [0.0]
    n = Notifier(clock=lambda: now[0], min_interval=30)
    assert n.message("sin_puerto", "") is None
    assert "conectado" in n.message("conectado", "COM3").lower()
    now[0] = 5
    assert n.message("error", "se perdió") is None  # menos de 30 s
    n.message("conectado", "COM3")
    now[0] = 40
    msg = n.message("sin_puerto", "")
    assert msg and "perdió" in msg
    now[0] = 80
    assert n.message("conectado", "COM3") is None  # solo la primera conexión avisa


def test_packaged_icon_exists():
    assert tray.ICON_PATH.is_file() and tray.base_image().size == (256, 256)


def test_to_pystray_builds_real_menu_items():
    pystray = __import__("pytest").importorskip("pystray")
    items, calls = make_menu(paused=True, autostart=True)
    menu = pystray.Menu(*tray.to_pystray(items, pystray))
    real = [i for i in menu.items if i is not pystray.Menu.SEPARATOR]
    assert [i.text for i in real][:2] == ["Estado: conectado", "Reanudar"]
    assert real[0].enabled is False and real[4].checked is True
    for i in real[1:]:
        i(None)  # pystray llama a la acción con el icono
    assert calls == ["toggle_pause", "settings", "log", "toggle_autostart", "quit"]
