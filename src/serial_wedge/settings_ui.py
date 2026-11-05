"""Ventana de configuración (tkinter). Nunca abre el puerto serie: solo edita config.json
y muestra status.json, que escribe el servicio."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

from . import autostart, config as cfgmod, single
from .injector import make_injector
from .ports import label, list_ports
from .probador_ui import ProbadorPanel
from .tray import ICON_PATH, status_line

AUTO = "Automático"
BAUDS = ("1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200")
PARITY = {"N": "Ninguna (N)", "E": "Par (E)", "O": "Impar (O)", "M": "Marca (M)", "S": "Espacio (S)"}
SUFFIX = {"enter": "Enter", "tab": "Tab", "none": "Nada"}


def read_status() -> dict:
    try:
        data = json.loads((cfgmod.config_dir() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _service_running() -> bool:
    s = single.acquire()
    if s is None:
        return True
    s.close()
    return False


class SettingsWindow:
    def __init__(self, root, *, list_fn=list_ports, autostart_fn=None, is_autostart_fn=None,
                 running_fn=_service_running, poll_ms=1000, injector_factory=make_injector):
        self.root, self.list_fn, self.running_fn, self.poll_ms = root, list_fn, running_fn, poll_ms
        self.autostart_fn = autostart_fn or autostart.set_autostart
        is_auto = is_autostart_fn or autostart.is_autostart
        self.cfg = cfgmod.load()
        root.title("Pistola Serial — Configuración")
        try:
            self._icon = tk.PhotoImage(file=str(ICON_PATH))
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(sticky="nsew", padx=6, pady=6)
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text="Configuración")
        tester = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tester, text="Probador")
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value=str(self.cfg.baud))
        self.bytesize_var = tk.StringVar(value=str(self.cfg.bytesize))
        self.parity_var = tk.StringVar(value=PARITY[self.cfg.parity])
        self.stopbits_var = tk.StringVar(value=str(self.cfg.stopbits))
        self.suffix_var = tk.StringVar(value=SUFFIX[self.cfg.suffix])
        self.prefix_var = tk.StringVar(value=self.cfg.prefix)
        self.autostart_var = tk.BooleanVar(value=self.cfg.autostart or bool(is_auto()))
        self.message_var, self.state_var, self.code_var = tk.StringVar(), tk.StringVar(), tk.StringVar()

        row = 0

        def add(text, widget):
            nonlocal row
            ttk.Label(f, text=text).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            widget.grid(row=row, column=1, sticky="we", pady=3)
            row += 1

        port_row = ttk.Frame(f)
        self.port_box = ttk.Combobox(port_row, textvariable=self.port_var, state="readonly", width=42)
        self.port_box.pack(side="left", fill="x", expand=True)
        ttk.Button(port_row, text="Actualizar", command=self.refresh_ports).pack(side="left", padx=(6, 0))
        add("Puerto:", port_row)
        add("Velocidad (baudios):", ttk.Combobox(f, textvariable=self.baud_var, values=BAUDS, width=10))
        add("Bits de datos:", ttk.Combobox(f, textvariable=self.bytesize_var, values=("5", "6", "7", "8"),
                                           state="readonly", width=10))
        add("Paridad:", ttk.Combobox(f, textvariable=self.parity_var, values=list(PARITY.values()),
                                     state="readonly", width=14))
        add("Bits de parada:", ttk.Combobox(f, textvariable=self.stopbits_var, values=("1", "2"),
                                            state="readonly", width=10))
        add("Después del código:", ttk.Combobox(f, textvariable=self.suffix_var, values=list(SUFFIX.values()),
                                                state="readonly", width=10))
        add("Prefijo:", ttk.Entry(f, textvariable=self.prefix_var, width=12))
        ttk.Checkbutton(f, text="Iniciar con Windows", variable=self.autostart_var).grid(
            row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Button(f, text="Guardar", command=self.save).grid(row=row, column=1, sticky="e", pady=(8, 4))
        ttk.Label(f, textvariable=self.message_var, foreground="#1d5f2c").grid(
            row=row, column=0, sticky="w")
        row += 1
        box = ttk.LabelFrame(f, text="Estado del servicio (escanee para probar)", padding=8)
        box.grid(row=row, column=0, columnspan=2, sticky="we", pady=(8, 0))
        ttk.Label(box, textvariable=self.state_var).pack(anchor="w")
        ttk.Label(box, textvariable=self.code_var).pack(anchor="w")
        f.columnconfigure(1, weight=1)

        self.refresh_ports()
        self.poll_status()
        self.probador = ProbadorPanel(tester, read_status=read_status, load_config=cfgmod.load,
                                      injector_factory=injector_factory, poll_ms=poll_ms)

    # -- puertos ---------------------------------------------------------
    def refresh_ports(self):
        current = self.port_var.get()
        try:
            found = list(self.list_fn())
        except Exception:
            found = []
        self.choices = {AUTO: None}
        self.choices.update({label(p): p for p in found})
        if not current:  # primera carga: preseleccionar lo que dice config.json
            current = AUTO
            if self.cfg.port != "auto":
                match = [k for k, p in self.choices.items() if p and p.device == self.cfg.port]
                current = match[0] if match else f"{self.cfg.port} (no conectado)"
        if current not in self.choices:
            self.choices[current] = "keep"
        self.port_box["values"] = list(self.choices)
        self.port_var.set(current)

    # -- guardar ---------------------------------------------------------
    def save(self):
        try:
            baud = int(self.baud_var.get())
            if not cfgmod.VALID["baud"](baud):
                raise ValueError
        except ValueError:
            self.message_var.set("Velocidad no válida")
            return None
        cfg = cfgmod.load()  # conserva campos que esta ventana no edita (pausa)
        choice = self.choices.get(self.port_var.get())
        if choice is None:
            cfg.port, cfg.vid, cfg.pid = "auto", None, None
        elif choice != "keep":
            cfg.port, cfg.vid, cfg.pid = choice.device, choice.vid, choice.pid
        cfg.baud = baud
        cfg.bytesize = int(self.bytesize_var.get())
        cfg.parity = next(k for k, v in PARITY.items() if v == self.parity_var.get())
        cfg.stopbits = int(self.stopbits_var.get())
        cfg.suffix = next(k for k, v in SUFFIX.items() if v == self.suffix_var.get())
        cfg.prefix = self.prefix_var.get()
        cfg.autostart = bool(self.autostart_var.get())
        cfgmod.save(cfg)
        self.cfg = cfg
        try:
            self.autostart_fn(cfg.autostart)
        except Exception as exc:
            self.message_var.set(f"Guardado, pero no se pudo configurar el inicio: {exc}")
            return cfg
        self.message_var.set("Guardado. El servicio aplica los cambios en un segundo.")
        return cfg

    # -- estado en vivo --------------------------------------------------
    def poll_status(self):
        if not self.running_fn():
            self.state_var.set("El servicio no está en ejecución (abra Pistola Serial)")
            self.code_var.set("")
        else:
            st = read_status()
            self.state_var.set(status_line(st.get("state", "iniciando"), st.get("detail", "")))
            if st.get("last_code"):
                self.code_var.set(f"Último código leído: {st['last_code']}  ({st.get('count', 0)} códigos)")
            else:
                self.code_var.set("Aún no se ha leído ningún código")
        if self.poll_ms:
            self.root.after(self.poll_ms, self.poll_status)


def run_settings():  # pragma: no cover - interactivo
    root = tk.Tk()
    root.resizable(False, False)
    SettingsWindow(root)
    root.mainloop()
