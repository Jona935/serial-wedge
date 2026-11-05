from serial_wedge.config import Config
from serial_wedge.probador import (
    ESPERANDO, FALLO, INFO, OK, PRUEBA_SIN_LECTOR, comparar, evaluar, informe, resumen,
)

NOW = 1_000_000.0
CODE = "7501234567890"


def st(**kw):
    base = {
        "state": "conectado", "detail": "COM3 a 9600 baudios", "port": "COM3",
        "last_code": CODE, "count": 1, "updated_ts": NOW - 1,
        "last_code_at": NOW - 2, "last_frame_at": NOW - 2, "last_typed_at": NOW - 2,
        "last_raw_hex": "37 35 30 31 32 33 34 35 36 37 38 39 30 0d 0a",
        "last_raw_text": CODE + "\\r\\n", "last_raw_len": 15, "last_terminator": "CRLF",
        "bytes_total": 15, "codes_total": 1, "garbled": False, "garbled_count": 0,
        "type_error": None,
    }
    base.update(kw)
    return base


def ev(status=None, texto=CODE, enter=True, cfg=None, **kw):
    kw.setdefault("inicio", NOW - 10)
    kw.setdefault("entry_at", NOW - 1.95)
    checks = evaluar(st() if status is None else status, texto, enter, cfg or Config(), NOW, **kw)
    return {c.id: c for c in checks}, checks


# -- todo bien -------------------------------------------------------------
def test_all_ok_and_order():
    by, checks = ev()
    assert [c.id for c in checks] == ["marcha", "puerto", "datos", "legibles", "teclado", "enter", "rapidez"]
    assert all(by[i].estado == OK for i in ["marcha", "puerto", "datos", "legibles", "teclado", "enter"])
    assert resumen(checks) == "Todo correcto ✅"


# -- 1 programa en marcha ----------------------------------------------------
def test_marcha_without_status():
    by, _ = ev({}, texto="", enter=False)
    assert by["marcha"].estado == FALLO and "Abra Pistola Serial" in by["marcha"].accion


def test_marcha_stale_status():
    by, _ = ev(st(updated_ts=NOW - 30))
    assert by["marcha"].estado == FALLO and "30 s" in by["marcha"].detalle


# -- 2 puerto ----------------------------------------------------------------
def test_puerto_sin_puerto_shows_reason_and_action():
    by, _ = ev(st(state="sin_puerto", detail="hay 2 puertos USB; elija uno en Configuración"))
    assert by["puerto"].estado == FALLO and "hay 2 puertos" in by["puerto"].detalle
    assert "Configuración" in by["puerto"].accion


def test_puerto_error_and_paused():
    by, _ = ev(st(state="error", detail="no se pudo abrir COM3: acceso denegado"))
    assert by["puerto"].estado == FALLO and "acceso denegado" in by["puerto"].detalle
    assert "otro programa" in by["puerto"].accion
    by, _ = ev(st(state="pausado", detail="lectura en pausa"))
    assert by["puerto"].estado == FALLO and "Reanudar" in by["puerto"].accion


def test_puerto_ok_detail():
    by, _ = ev()
    assert "COM3" in by["puerto"].detalle


# -- 3 datos -------------------------------------------------------------------
def test_datos_waiting_until_new_code():
    by, checks = ev(inicio=NOW - 1, texto="", enter=False)
    assert by["datos"].estado == ESPERANDO and "Escanee" in by["datos"].detalle
    assert by["legibles"].estado == ESPERANDO and by["teclado"].estado == ESPERANDO
    assert resumen(checks).startswith("Esperando")


def test_datos_ok_shows_bytes_terminator_and_raw():
    by, _ = ev()
    assert "15 bytes" in by["datos"].detalle and "CRLF" in by["datos"].detalle
    assert CODE not in by["datos"].detalle  # el contenido va aparte
    assert "0d 0a" in by["datos"].codigos and CODE in by["datos"].codigos


# -- 4 legibles ----------------------------------------------------------------
def test_garbled_data():
    by, _ = ev(st(garbled=True, garbled_count=3))
    assert by["legibles"].estado == FALLO
    assert by["legibles"].detalle.startswith("Se reciben símbolos raros: revise baudios y paridad")


# -- 5 teclado -----------------------------------------------------------------
def test_teclado_coincide_with_prefix():
    by, _ = ev(texto="#" + CODE, cfg=Config(prefix="#"))
    assert by["teclado"].estado == OK and by["teclado"].detalle == "Coincide"


def test_teclado_mismatch_shows_expected_and_received():
    by, _ = ev(texto="750123456789")
    assert by["teclado"].estado == FALLO and "Falta 1 carácter" in by["teclado"].detalle
    assert "esperado" in by["teclado"].codigos and "750123456789" in by["teclado"].codigos


def test_teclado_type_error_admin():
    err = "[Errno 5] SendInput bloqueado (¿aplicación como Administrador?)"
    by, _ = ev(st(type_error=err), texto="", enter=False)
    assert by["teclado"].estado == FALLO
    assert "Windows bloqueó la escritura: la ventana puede estar como Administrador" in by["teclado"].detalle


def test_teclado_other_type_error():
    by, _ = ev(st(type_error="Instale xdotool: sudo apt install xdotool (solo X11)"), texto="", enter=False)
    assert by["teclado"].estado == FALLO and "xdotool" in by["teclado"].detalle


def test_teclado_waiting_for_entry():
    by, _ = ev(texto="", enter=False)
    assert by["teclado"].estado == ESPERANDO and "clic en el campo" in by["teclado"].detalle


# -- 6 enter -------------------------------------------------------------------
def test_enter_missing_after_typing():
    by, _ = ev(enter=False)
    assert by["enter"].estado == FALLO and by["enter"].titulo == "Enter enviado"


def test_enter_missing_but_just_typed_waits():
    by, _ = ev(st(last_typed_at=NOW - 0.2), enter=False)
    assert by["enter"].estado == ESPERANDO


def test_tab_suffix_and_none_suffix():
    by, _ = ev(cfg=Config(suffix="tab"))
    assert by["enter"].titulo == "Tab enviado" and by["enter"].estado == OK
    by, _ = ev(cfg=Config(suffix="none"), enter=False)
    assert by["enter"].estado == OK and "sin tecla" in by["enter"].detalle


# -- 7 rapidez -----------------------------------------------------------------
def test_rapidez_ms():
    by, _ = ev()
    assert by["rapidez"].estado == INFO and by["rapidez"].detalle == "50 ms desde la lectura hasta el campo"


def test_rapidez_unknown():
    by, _ = ev(entry_at=None, texto="", enter=False)
    assert by["rapidez"].estado == INFO and "—" in by["rapidez"].detalle


# -- probar sin lector -----------------------------------------------------------
def test_sin_lector_ok():
    by, checks = ev(st(last_code=None, last_code_at=None, last_frame_at=None),
                    texto=PRUEBA_SIN_LECTOR, sin_lector=True)
    assert by["datos"].estado == INFO and by["legibles"].estado == INFO
    assert by["teclado"].estado == OK and by["enter"].estado == OK
    assert resumen(checks) == "Todo correcto ✅"


def test_sin_lector_injector_error():
    by, checks = ev(texto="", enter=False, sin_lector=True,
                    error_local="Instale xdotool: sudo apt install xdotool (solo X11)")
    assert by["teclado"].estado == FALLO and "xdotool" in by["teclado"].detalle
    assert resumen(checks).startswith("Hay 1 problema")


# -- comparar ------------------------------------------------------------------
def test_comparar_cases():
    assert comparar("ABC", "ABC") == (True, "Coincide")
    assert comparar("ABCD", "ABD") == (False, "Falta 1 carácter en la posición 3")
    assert comparar("ABCD", "AB") == (False, "Faltan 2 caracteres en la posición 3")
    assert comparar("ABC", "ABXC") == (False, "Sobra 1 carácter en la posición 3")
    assert comparar("ABC", "AXC") == (False, "Cambia 1 carácter (posición 2)")
    assert comparar("ABCD", "XBCY") == (False, "Cambian 2 caracteres (primera en la posición 1)")
    ok, det = comparar("ABCDEF", "AZ")
    assert not ok and det == "Difiere desde la posición 2 (se esperaban 6 caracteres, llegaron 2)"


# -- resumen e informe -----------------------------------------------------------
def test_resumen_counts_problems_and_first_action():
    _, checks = ev(st(state="sin_puerto", detail="no hay puertos USB serie conectados", garbled=True))
    text = resumen(checks)
    assert text.startswith("Hay 2 problemas") and "Conecte el lector" in text


def test_informe_without_codes():
    _, checks = ev(texto="750123456789")
    text = informe(checks, Config(port="COM3", baud=9600, parity="E"), incluir_codigos=False)
    assert CODE not in text and "750123456789" not in text
    assert "COM3" in text and "9600" in text and "Paridad: E" in text
    assert "❌ El teclado escribe lo mismo" in text and "Hay 1 problema" in text


def test_informe_with_codes():
    _, checks = ev()
    text = informe(checks, Config(), incluir_codigos=True)
    assert CODE in text and "✅ Programa en marcha" in text
