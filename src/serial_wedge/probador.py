"""Lógica pura del Probador: convierte status.json + lo tecleado en una lista de chequeos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

OK, FALLO, ESPERANDO, INFO = "ok", "fallo", "esperando", "info"
SIMBOLO = {OK: "✅", FALLO: "❌", ESPERANDO: "⏳", INFO: "ℹ"}
PRUEBA_SIN_LECTOR = "PRUEBA-123"
TECLA = {"enter": "Enter", "tab": "Tab"}
GARBLED_MSG = ("Se reciben símbolos raros: revise baudios y paridad "
               "(por ejemplo, pruebe paridad Par/Impar o 7 bits)")
ADMIN_MSG = "Windows bloqueó la escritura: la ventana puede estar como Administrador"


@dataclass
class Chequeo:
    id: str
    titulo: str
    estado: str
    detalle: str = ""
    accion: str = ""   # qué hacer si falla
    codigos: str = ""  # contenido leído/tecleado; solo se muestra o copia si se pide


def _plural(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def comparar(esperado: str, recibido: str) -> tuple[bool, str]:
    if esperado == recibido:
        return True, "Coincide"
    i = next((k for k, (a, b) in enumerate(zip(esperado, recibido)) if a != b),
             min(len(esperado), len(recibido)))
    d = len(esperado) - len(recibido)
    if d > 0 and esperado[:i] + esperado[i + d:] == recibido:
        return False, f"{'Falta' if d == 1 else 'Faltan'} {_plural(d, 'carácter', 'caracteres')} en la posición {i + 1}"
    if d < 0 and recibido[:i] + recibido[i - d:] == esperado:
        return False, f"{'Sobra' if d == -1 else 'Sobran'} {_plural(-d, 'carácter', 'caracteres')} en la posición {i + 1}"
    if d == 0:
        n = sum(a != b for a, b in zip(esperado, recibido))
        if n == 1:
            return False, f"Cambia 1 carácter (posición {i + 1})"
        return False, f"Cambian {n} caracteres (primera en la posición {i + 1})"
    return False, (f"Difiere desde la posición {i + 1} (se esperaban {len(esperado)} caracteres, "
                   f"llegaron {len(recibido)})")


def _updated_ts(status):
    if isinstance(status.get("updated_ts"), (int, float)):
        return status["updated_ts"]
    try:
        return datetime.fromisoformat(status["updated"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _causa(err: str) -> str:
    if "SendInput" in err or "Administrador" in err:
        return ADMIN_MSG
    return f"No se pudo teclear: {err}"


def _nuevo(ts, inicio):
    return isinstance(ts, (int, float)) and ts >= inicio


def evaluar(status: dict, texto_entry: str, enter_visto: bool, config, ahora: float, *,
            inicio: float = 0.0, entry_at: float | None = None, sin_lector: bool = False,
            error_local: str | None = None) -> list[Chequeo]:
    status = status or {}
    out = []

    # 1. programa en marcha
    ts = _updated_ts(status)
    if ts is None:
        out.append(Chequeo("marcha", "Programa en marcha", FALLO, "No hay noticias del servicio",
                           "Abra Pistola Serial (doble clic en serial-wedge.exe)"))
    elif ahora - ts > 5:
        out.append(Chequeo("marcha", "Programa en marcha", FALLO,
                           f"El programa no responde (último aviso hace {int(ahora - ts)} s)",
                           "Abra Pistola Serial o reinícielo desde la bandeja"))
    else:
        out.append(Chequeo("marcha", "Programa en marcha", OK, "Responde"))

    # 2. puerto
    state, detail = status.get("state"), status.get("detail", "")
    acciones = {
        "sin_puerto": "Conecte el lector o elija el puerto en Configuración",
        "error": "Cierre cualquier otro programa que use el puerto y revise el cable",
        "pausado": "Use «Reanudar» en el menú del icono de la bandeja",
    }
    if state == "conectado":
        out.append(Chequeo("puerto", "Puerto encontrado y abierto", OK, detail))
    elif state in acciones:
        out.append(Chequeo("puerto", "Puerto encontrado y abierto", FALLO, detail, acciones[state]))
    else:
        out.append(Chequeo("puerto", "Puerto encontrado y abierto", ESPERANDO, "Sin datos del servicio"))

    # 3 y 4. datos del lector
    frame_nuevo = _nuevo(status.get("last_frame_at"), inicio)
    if sin_lector:
        out.append(Chequeo("datos", "El lector envía datos", INFO, "No aplica en la prueba sin lector"))
        out.append(Chequeo("legibles", "Datos legibles", INFO, "No aplica en la prueba sin lector"))
    elif frame_nuevo:
        out.append(Chequeo(
            "datos", "El lector envía datos", OK,
            f"{status.get('last_raw_len', '?')} bytes · terminador: {status.get('last_terminator', '?')}",
            codigos=f"texto: {status.get('last_raw_text', '')} · hex: {status.get('last_raw_hex', '')}"))
        if status.get("garbled"):
            out.append(Chequeo("legibles", "Datos legibles", FALLO, GARBLED_MSG,
                               "En Configuración pruebe otra velocidad, paridad o bits de datos"))
        else:
            out.append(Chequeo("legibles", "Datos legibles", OK, "Sin símbolos raros"))
    else:
        out.append(Chequeo("datos", "El lector envía datos", ESPERANDO,
                           "Escanee un código (después de pulsar «Iniciar prueba»)"))
        out.append(Chequeo("legibles", "Datos legibles", ESPERANDO, "Esperando datos del lector"))

    # 5. lo tecleado coincide
    if sin_lector:
        disponible, esperado, err = True, PRUEBA_SIN_LECTOR, error_local
        typed_at = entry_at
    else:
        code = status.get("last_code")
        disponible = bool(code) and _nuevo(status.get("last_code_at"), inicio)
        esperado, err = f"{config.prefix}{code}", status.get("type_error")
        typed_at = status.get("last_typed_at")
    titulo = "El teclado escribe lo mismo"
    if not disponible:
        out.append(Chequeo("teclado", titulo, ESPERANDO, "Escanee un código con el cursor en el campo de prueba"))
    elif texto_entry:
        ok, det = comparar(esperado, texto_entry)
        out.append(Chequeo("teclado", titulo, OK if ok else FALLO, det,
                           "" if ok else "Revise el prefijo configurado y la distribución de teclado",
                           codigos=f"esperado: {esperado!r} · recibido: {texto_entry!r}"))
    elif err:
        causa = _causa(err)
        accion = ("Ejecute Pistola Serial como Administrador o abra el programa destino sin privilegios"
                  if causa == ADMIN_MSG else causa)
        out.append(Chequeo("teclado", titulo, FALLO, causa, accion))
    else:
        out.append(Chequeo("teclado", titulo, ESPERANDO, "Haga clic en el campo de prueba y escanee"))

    # 6. tecla final
    tecla = TECLA.get(config.suffix)
    titulo = f"{tecla} enviado" if tecla else "Tecla final"
    if not tecla:
        out.append(Chequeo("enter", titulo, OK, "Configurado sin tecla final"))
    elif enter_visto:
        out.append(Chequeo("enter", titulo, OK, f"Se recibió {tecla} después del código"))
    elif texto_entry and not (isinstance(typed_at, (int, float)) and ahora - typed_at < 1):
        out.append(Chequeo("enter", titulo, FALLO, f"No llegó {tecla} después del código",
                           f"Revise que «Después del código» sea «{tecla}» en Configuración"))
    else:
        out.append(Chequeo("enter", titulo, ESPERANDO, "Esperando el código"))

    # 7. rapidez (informativo)
    code_at = None if sin_lector else status.get("last_code_at")
    if entry_at is not None and _nuevo(code_at, inicio):
        ms = round((entry_at - code_at) * 1000)
        out.append(Chequeo("rapidez", "Rapidez", INFO, f"{ms} ms desde la lectura hasta el campo"))
    else:
        out.append(Chequeo("rapidez", "Rapidez", INFO, "— (sin medición)"))
    return out


def resumen(chequeos: list[Chequeo]) -> str:
    principales = [c for c in chequeos if c.id != "rapidez"]
    fallos = [c for c in principales if c.estado == FALLO]
    if fallos:
        n = len(fallos)
        return f"Hay {_plural(n, 'problema', 'problemas')}: {fallos[0].accion or fallos[0].detalle}"
    if all(c.estado in (OK, INFO) for c in principales):
        return "Todo correcto ✅"
    espera = next(c for c in principales if c.estado == ESPERANDO)
    return f"Esperando: {espera.detalle}"


def informe(chequeos: list[Chequeo], config, incluir_codigos: bool = False) -> str:
    ids = f"{config.vid:04x}:{config.pid:04x}" if config.vid is not None and config.pid is not None else "—"
    lines = [
        "Pistola Serial — resultado del probador",
        resumen(chequeos),
        "",
        f"Ajustes: Puerto: {config.port} (VID:PID {ids}) · Baudios: {config.baud} · "
        f"Bits de datos: {config.bytesize} · Paridad: {config.parity} · Bits de parada: {config.stopbits} · "
        f"Después del código: {config.suffix} · Prefijo: {'sí' if config.prefix else 'ninguno'}",
        "",
    ]
    for c in chequeos:
        lines.append(f"{SIMBOLO[c.estado]} {c.titulo}: {c.detalle}")
        if c.estado == FALLO and c.accion:
            lines.append(f"    → {c.accion}")
        if incluir_codigos and c.codigos:
            lines.append(f"    {c.codigos}")
    if not incluir_codigos:
        lines += ["", "(Sin el contenido de los códigos.)"]
    return "\n".join(lines)
