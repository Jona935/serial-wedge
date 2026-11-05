# Pistola Serial (`serial-wedge`)

Programa pequeño que se queda siempre en segundo plano y hace que un lector de
códigos de barras **serial** (puerto COM o COM virtual por USB) se comporte como
un lector tipo teclado: cada vez que se escanea un código, lo **escribe en la
ventana que tiene el foco** y pulsa **Enter**.

- Arranca con Windows y vive en la bandeja del sistema (junto al reloj).
- Si el lector se desconecta, se vuelve a conectar o la PC despierta de la
  suspensión, se reconecta solo.
- Después de la primera configuración no hay que tocar nada.
- Nunca escribe al puerto serie: solo lee.

## Puesta en marcha (Windows)

1. Copie `serial-wedge.exe` a una carpeta permanente, por ejemplo
   `C:\Programas\Pistola Serial\` (no lo deje en Descargas: el inicio automático
   apunta a esa ruta).
2. Haga doble clic en `serial-wedge.exe`. Aparece un icono de código de barras
   en la bandeja del sistema (puede estar dentro de la flechita «^»).
3. Clic derecho sobre el icono → **Configuración…**
4. Elija el puerto del lector, o deje **Automático** si es el único puerto serie
   USB conectado. Ajuste la velocidad (normalmente 9600) si su lector usa otra.
5. Marque **Iniciar con Windows** y pulse **Guardar**.
6. Con la ventana abierta, escanee un código: debe aparecer en «Último código
   leído». Listo: abra su programa (Excel, punto de venta…) y escanee.

El programa recuerda el lector por su identificador USB (VID:PID), así que lo
encuentra aunque Windows le cambie el número de COM.

## Cómo se comporta

| Color del punto | Estado      | Significado                                              |
|-----------------|-------------|----------------------------------------------------------|
| Verde           | conectado   | Leyendo el lector.                                       |
| Amarillo        | sin puerto  | El lector no está conectado (revisa cada 2 s).           |
| Rojo            | error       | No se pudo abrir o se cortó; reintenta (1, 2, 4… 10 s).  |
| Gris            | en pausa    | Pausado desde el menú («Pausar» / «Reanudar»).           |

- Menú del icono: estado, Pausar/Reanudar, Configuración…, Ver registro,
  Iniciar con Windows, Salir.
- Los códigos que terminan en CR/LF se envían al llegar el terminador; si el
  lector no manda terminador, el código se envía tras 0,2 s sin datos.
- Registro: `%APPDATA%\SerialWedge\serial-wedge.log` (en Linux
  `~/.config/serial-wedge/`). Se guardan arranques, conexiones, errores y el
  número de códigos, **no** el contenido de los códigos.
- Configuración: `config.json` en la misma carpeta. Si el archivo se daña, se
  usan los valores por defecto. Los cambios se aplican solos en ~1 s.
- Solo puede haber una copia en ejecución; abrirlo de nuevo no hace nada.

## Probador: comprobar que todo funciona

1. Clic derecho en el icono → **Configuración…** → pestaña **Probador**.
2. Pulse **Iniciar prueba**, haga clic en el **campo de prueba** y escanee un código.
3. Cada fila se marca con ✅ (bien), ❌ (problema) o ⏳ (esperando). Arriba
   aparece «Todo correcto ✅» o «Hay N problemas» con lo primero que conviene hacer.

El Probador no abre el puerto: lee lo que publica el programa en `status.json`,
así que se puede usar con el programa funcionando.

| Fila con ❌                    | Qué significa / qué hacer                                                    |
|-------------------------------|-------------------------------------------------------------------------------|
| Programa en marcha            | Pistola Serial no está abierta o no responde: ábrala (o reiníciela).          |
| Puerto encontrado y abierto   | Lector desconectado, puerto equivocado u ocupado por otro programa, o en pausa.|
| El lector envía datos         | (⏳) No llegó nada: revise cable, puerto y que el lector esté en modo serie.   |
| Datos legibles                | Llegan símbolos raros: la velocidad (baudios), la paridad o los bits no coinciden con el lector. |
| El teclado escribe lo mismo   | Lo escrito no coincide (se indica la primera diferencia) o Windows bloqueó la escritura porque la ventana destino corre como Administrador. |
| Enter enviado                 | No llegó la tecla final: revise «Después del código» (Enter/Tab/Nada).        |

«Rapidez» solo informa los milisegundos entre la lectura y la llegada al campo.
**Probar sin lector** escribe «PRUEBA-123» en el campo con el mismo método del
programa, para comprobar el tecleo sin escanear nada. **Copiar resultado** copia
un informe con los ajustes y cada fila; el contenido de los códigos solo se
incluye si marca «incluir códigos».

## Límites

- **Programas como Administrador**: Windows no deja que un programa normal
  envíe teclas a una ventana que corre como Administrador. Ejecute también
  `serial-wedge.exe` como Administrador o quite ese privilegio al programa destino.
- Escribe **donde esté el foco**: si el foco está en otra ventana, el código
  aparece allí.
- Linux (solo para desarrollo/pruebas): necesita `xdotool` y una sesión **X11**
  (no funciona en Wayland). El icono de bandeja necesita soporte AppIndicator.

## Probar sin teclear nada

```
serial-wedge --dry-run --no-tray            # muestra los códigos en la consola
serial-wedge --dry-run --no-tray --port COM4 --baud 9600
```

## Alternativa sin software

Muchos lectores pueden pasar a **modo teclado USB (HID)** escaneando un código
de configuración de su manual («USB HID Keyboard» / «USB KBW»). Si el suyo lo
permite, no necesita este programa.

## Desarrollo

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/python -m serial_wedge --no-tray --dry-run --port /tmp/wedgeB
python tools/make_icon.py          # regenera assets/serial-wedge.png/.ico
```

Simular un lector en Linux con un par de pseudoterminales:

```
socat pty,raw,echo=0,link=/tmp/wedgeA pty,raw,echo=0,link=/tmp/wedgeB &
printf '7501234567890\r\n' > /tmp/wedgeA
```

Compilar el `.exe` (en Windows):

```
pip install -e ".[dev]" pyinstaller
pyinstaller --noconfirm --onefile --windowed --name serial-wedge --icon assets/serial-wedge.ico ^
  --paths src --add-data "src/serial_wedge/assets;serial_wedge/assets" ^
  --hidden-import pystray._win32 run.py
```

El flujo `.github/workflows/build.yml` hace lo mismo en GitHub Actions y publica
`serial-wedge.exe` como Release.

Módulos (`src/serial_wedge/`): `config` (config.json), `ports` (elección del
puerto), `injector` (SendInput / xdotool), `wedge` (bucle de lectura),
`service` (hilo con reconexión y status.json), `tray` (icono), `settings_ui`
(ventana Tk, proceso aparte), `autostart`, `single` (instancia única),
`logsetup`.
