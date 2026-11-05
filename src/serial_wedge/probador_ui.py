"""Pestaña «Probador»: cascarón Tk sobre probador.py. Nunca abre el puerto serie."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

from .probador import PRUEBA_SIN_LECTOR, SIMBOLO, evaluar, informe, resumen

FILAS = ["marcha", "puerto", "datos", "legibles", "teclado", "enter", "rapidez"]
KEYSYM = {"enter": "Return", "tab": "Tab"}


class ProbadorPanel:
    def __init__(self, parent, *, read_status, load_config, injector_factory,
                 clock=time.time, poll_ms=1000):
        self.parent, self.read_status, self.load_config = parent, read_status, load_config
        self.injector_factory, self.clock, self.poll_ms = injector_factory, clock, poll_ms
        self.chequeos = []

        self.resumen_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.resumen_var, font=("TkDefaultFont", 11, "bold"),
                  wraplength=520).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.filas = {}
        for i, fid in enumerate(FILAS, start=1):
            vars_ = (tk.StringVar(value=SIMBOLO["esperando"]), tk.StringVar(), tk.StringVar())
            ttk.Label(parent, textvariable=vars_[0], width=2).grid(row=i, column=0, sticky="nw")
            ttk.Label(parent, textvariable=vars_[1], width=26).grid(row=i, column=1, sticky="nw")
            ttk.Label(parent, textvariable=vars_[2], wraplength=330).grid(row=i, column=2, sticky="nw", pady=1)
            self.filas[fid] = vars_

        r = len(FILAS) + 1
        ttk.Label(parent, text="Campo de prueba (haga clic aquí y escanee):").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(10, 2))
        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(parent, textvariable=self.entry_var, width=48)
        self.entry.grid(row=r + 1, column=0, columnspan=3, sticky="we")
        for keysym in ("Return", "KP_Enter", "Tab"):
            self.entry.bind(f"<{keysym}>", lambda e: self.on_final_key(e.keysym))
        self.entry_var.trace_add("write", self._on_entry_change)

        buttons = ttk.Frame(parent)
        buttons.grid(row=r + 2, column=0, columnspan=3, sticky="we", pady=(8, 0))
        ttk.Button(buttons, text="Iniciar prueba", command=self.iniciar).pack(side="left")
        ttk.Button(buttons, text="Probar sin lector", command=self.probar_sin_lector).pack(side="left", padx=6)
        ttk.Button(buttons, text="Copiar resultado", command=self.copiar).pack(side="left")
        self.incluir_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text="incluir códigos", variable=self.incluir_var).pack(side="left", padx=6)
        self.mensaje_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.mensaje_var).grid(row=r + 3, column=0, columnspan=3, sticky="w")
        parent.columnconfigure(2, weight=1)

        self.iniciar(refrescar=False)
        self.refresh(programar=True)

    # -- estado de la prueba ------------------------------------------------------
    def iniciar(self, refrescar=True):
        self.inicio = self.clock()
        self.recibido, self.enter_visto, self.entry_at = "", False, None
        self._codigo_nuevo = True  # el próximo carácter empieza un código
        self.sin_lector, self.error_local = False, None
        self.entry_var.set("")
        self.mensaje_var.set("")
        if refrescar:
            self.entry.focus_set()
            self.refresh()

    def _on_entry_change(self, *_):
        if self.entry_var.get() and self._codigo_nuevo:
            self.entry_at = self.clock()  # llegada del primer carácter
            self._codigo_nuevo, self.enter_visto = False, False

    def on_final_key(self, keysym):
        """Return/Tab en el campo: guarda lo escrito y deja el campo listo para otro código."""
        texto = self.entry_var.get()
        if texto:
            self.recibido = texto
            esperado = KEYSYM.get(self.load_config().suffix)
            self.enter_visto = keysym.replace("KP_Enter", "Return") == esperado
            self._codigo_nuevo = True
            self.entry_var.set("")
            self.refresh()
        return "break"

    def _texto(self):
        return self.entry_var.get() or self.recibido

    # -- probar sin lector -------------------------------------------------------
    def probar_sin_lector(self, delay_ms=300):
        self.iniciar(refrescar=False)
        self.sin_lector = True
        self.entry.focus_force()
        self.mensaje_var.set(f"Tecleando «{PRUEBA_SIN_LECTOR}» en el campo…")
        if delay_ms is None:
            self._inyectar()
        else:
            self.parent.after(delay_ms, lambda: threading.Thread(target=self._inyectar, daemon=True).start())

    def _inyectar(self):
        try:
            type_code = self.injector_factory()
            type_code(PRUEBA_SIN_LECTOR, self.load_config().suffix)
        except Exception as exc:  # p. ej. sin xdotool o SendInput bloqueado
            self.error_local = str(exc) or type(exc).__name__

    # -- resultado ---------------------------------------------------------------
    def refresh(self, programar=False):
        self.chequeos = evaluar(self.read_status(), self._texto(), self.enter_visto, self.load_config(),
                                self.clock(), inicio=self.inicio, entry_at=self.entry_at,
                                sin_lector=self.sin_lector, error_local=self.error_local)
        for c in self.chequeos:
            icon, title, detail = self.filas[c.id]
            icon.set(SIMBOLO[c.estado])
            title.set(c.titulo)
            text = c.detalle + (f"\n→ {c.accion}" if c.estado == "fallo" and c.accion else "")
            mostrar = c.codigos and (c.estado == "fallo" or c.id == "datos")
            detail.set(text + (f"\n{c.codigos}" if mostrar else ""))
        self.resumen_var.set(resumen(self.chequeos))
        if programar and self.poll_ms:
            self.parent.after(self.poll_ms, lambda: self.refresh(programar=True))

    def copiar(self):
        text = informe(self.chequeos, self.load_config(), bool(self.incluir_var.get()))
        self.parent.clipboard_clear()
        self.parent.clipboard_append(text)
        self.mensaje_var.set("Resultado copiado al portapapeles")
        return text
