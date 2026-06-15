"""
ultra_id — Buscador Universal de Documentos Peruanos (GUI)
Estilo monocromo Macintosh — Tkinter
Tabs: Individual | Colectivo | Tutorial
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from core.models import ResultadoDocumento, TIPO_NOMBRES
from core.validator import validar_documento, parse_codigo_procesado, crear_resultado_vacio
from core.exporter import exportar, FORMATOS
from orchestrator import UltraBuscador

# ─── Paleta y fuentes ───────────────────────────────────────────────────────
BG         = "#FFFFFF"
FG         = "#000000"
FONT       = ("Courier New", 9)
FONT_BOLD  = ("Courier New", 9, "bold")
FONT_TITLE = ("Courier New", 11, "bold")
FONT_SMALL = ("Courier New", 8)

WIN_W = 700

TIPOS_OPCIONES = ["1 — DNI", "6 — RUC", "3 — Carnet Extranjería", "4 — Pasaporte"]
TIPO_MAP = {"1 — DNI": 1, "6 — RUC": 6, "3 — Carnet Extranjería": 3, "4 — Pasaporte": 4}

TUTORIAL_TEXT = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ULTRA_ID — BUSCADOR UNIVERSAL DE DOCUMENTOS PERUANOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIPOS DE DOCUMENTO
──────────────────
  Código  Tipo                    Formato
  ──────  ────────────────────    ─────────────────────────
    1     DNI                     8 dígitos numéricos
    3     Carnet de Extranjería   4–12 caracteres alfanum.
    4     Pasaporte               5–20 caracteres alfanum.
    6     RUC                     11 dígitos numéricos

CÓDIGO PROCESADO
────────────────
  Formato: "0000" + número + código_tipo

  Ejemplos:
    DNI 73231883   →  0000732318831
    RUC 20100041953 → 0000201000419536
    CE  000123456  →  00000001234563

FUENTES CONSULTADAS POR TIPO
─────────────────────────────
  DNI (tipo 1):
    • buscardniperu.com/como-saber-la-edad-por-dni/
      Campos: edad, fecha de nacimiento

  RUC (tipo 6):
    • universidadperu.com → razón social, condición, dirección
    • pad.minem.gob.pe (REINFO) → registro minero, estado vigencia
    • mineros-peru.vercel.app (RECPO API) → registro minero RECPO
    • apps.osce.gob.pe → RNP OSCE: penalidades, sanciones
    • sbs.gob.pe/app/uif/voc/ → Sujeto Obligado UIF/SBS

  Carnet Extranjería (tipo 3):
    • sistemasdgc.rree.gob.pe → nombres, nacionalidad, estado

  Pasaporte (tipo 4):
    • (fuente pendiente — se añadirá en próxima versión)

MODO COLECTIVO — FORMATO DE ARCHIVO
─────────────────────────────────────
  El archivo de entrada (CSV o Excel) debe tener:
    Opción A: columnas "numero_documento" y "tipo_codigo"
    Opción B: columna "codigo_procesado"
    Opción C: columna 1 = número, columna 2 = tipo (o solo columna 1
              si todos son del mismo tipo inferible por longitud)

  Inferencia automática de tipo por longitud:
    8 dígitos → DNI, 11 dígitos → RUC, otro → Carnet Extranjería

WORKERS (paralelismo)
──────────────────────
  Número de instancias de Chrome simultáneas para batch.
  3–4: balance óptimo velocidad/estabilidad.
  5:   más rápido, mayor uso de RAM y riesgo de bloqueos.

  Estimación de tiempo para 1000 documentos:
    DNI solo:  ~10–20 min con 4 workers
    RUC (5 fuentes): ~30–60 min con 4 workers

NOTAS Y LIMITACIONES
──────────────────────
  • La app usa Selenium (Chrome headless). Si Chrome no está
    instalado, instálalo antes de ejecutar.
  • Los sitios web pueden cambiar su estructura sin previo aviso.
    Si un campo aparece vacío, puede requerir actualización de
    los selectores en buscadores/*.py.
  • OSCE y SBS son SPAs o formularios dinámicos; los selectores
    están diseñados para ser resilientes pero pueden requerir
    ajustes después de actualizaciones del sitio.
  • Para millones de consultas, considera distribuir en lotes
    horarios para evitar rate-limiting.

VERSIÓN: 1.0  |  RPAPP_BAHC_ULTRA_ID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


# ─── Widgets utilitarios ────────────────────────────────────────────────────

class MacProgressBar(tk.Canvas):
    def __init__(self, parent, height=12, **kwargs):
        super().__init__(parent, height=height, bg=BG,
                         highlightthickness=1, highlightbackground=FG, **kwargs)
        self._pct = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value: float):
        self._pct = max(0.0, min(100.0, value))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            return
        fw = int((self._pct / 100.0) * (w - 2))
        if fw > 0:
            self.create_rectangle(1, 1, 1 + fw, h - 1, fill=FG, outline="")


def _mac_btn(parent, text, command, inverted=True):
    bg_n, fg_n = (FG, BG) if inverted else (BG, FG)
    b = tk.Label(parent, text=text, bg=bg_n, fg=fg_n, font=FONT_BOLD,
                 cursor="hand2", padx=10, pady=4, relief=tk.FLAT,
                 highlightthickness=1, highlightbackground=FG)
    b._enabled = True

    def _click(e):
        if b._enabled:
            command()

    def _enter(e):
        if b._enabled:
            b.config(bg=BG if inverted else FG, fg=FG if inverted else BG)

    def _leave(e):
        if b._enabled:
            b.config(bg=bg_n, fg=fg_n)

    b.bind("<Button-1>", _click)
    b.bind("<Enter>", _enter)
    b.bind("<Leave>", _leave)
    return b


def _entry(parent, textvariable, width=12, **kwargs):
    return tk.Entry(parent, textvariable=textvariable, width=width,
                    font=FONT, bg=BG, fg=FG, insertbackground=FG,
                    relief=tk.FLAT, highlightthickness=1,
                    highlightbackground=FG, highlightcolor=FG, **kwargs)


def _lbl(parent, text, font=None, **kwargs):
    return tk.Label(parent, text=text, bg=BG, fg=FG, font=font or FONT, **kwargs)


def _sep(parent, horizontal=True):
    if horizontal:
        tk.Frame(parent, bg=FG, height=1).pack(fill=tk.X)
    else:
        tk.Frame(parent, bg=FG, width=1).pack(fill=tk.Y)


# ─── Aplicación principal ───────────────────────────────────────────────────

class UltraIDApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ultra_id — Buscador Universal de Documentos")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._buscador: Optional[UltraBuscador] = None
        self._running = False
        self._stop_event = threading.Event()
        self._resultados: list[ResultadoDocumento] = []

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    # ── Construcción UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_tab_bar()
        self._content = tk.Frame(self, bg=BG, padx=12, pady=10)
        self._content.pack(fill=tk.BOTH)
        self._panel_individual = tk.Frame(self._content, bg=BG)
        self._panel_colectivo  = tk.Frame(self._content, bg=BG)
        self._panel_tutorial   = tk.Frame(self._content, bg=BG)
        self._build_panel_individual()
        self._build_panel_colectivo()
        self._build_panel_tutorial()
        self._show_tab("individual")
        self._build_log_bar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=FG, padx=10, pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="ULTRA_ID — BUSCADOR UNIVERSAL DE DOCUMENTOS PERUANOS",
                 bg=FG, fg=BG, font=FONT_TITLE).pack(side=tk.LEFT)
        tk.Label(hdr, text="RPAPP_BAHC_ULTRA_ID", bg=FG, fg=BG,
                 font=FONT_SMALL).pack(side=tk.RIGHT, pady=2)

    def _build_tab_bar(self):
        bar = tk.Frame(self, bg=FG, pady=0)
        bar.pack(fill=tk.X)
        tabs = [
            ("  INDIVIDUAL  ", "individual"),
            ("  COLECTIVO  ",  "colectivo"),
            ("  TUTORIAL  ",   "tutorial"),
        ]
        self._tab_btns = {}
        for text, key in tabs:
            lbl = tk.Label(bar, text=text, bg=BG, fg=FG, font=FONT_BOLD,
                           cursor="hand2", pady=5)
            lbl.pack(side=tk.LEFT)
            lbl.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            self._tab_btns[key] = lbl
        tk.Frame(bar, bg=BG).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _show_tab(self, tab: str):
        for key, lbl in self._tab_btns.items():
            lbl.config(bg=FG if key == tab else BG,
                       fg=BG if key == tab else FG)
        self._panel_individual.pack_forget()
        self._panel_colectivo.pack_forget()
        self._panel_tutorial.pack_forget()
        if tab == "individual":
            self._panel_individual.pack(fill=tk.BOTH)
        elif tab == "colectivo":
            self._panel_colectivo.pack(fill=tk.BOTH)
        else:
            self._panel_tutorial.pack(fill=tk.BOTH)

    # ── Panel Individual ──────────────────────────────────────────────────────

    def _build_panel_individual(self):
        p = self._panel_individual

        # Fila de entrada
        row = tk.Frame(p, bg=BG)
        row.pack(fill=tk.X, pady=(0, 6))

        _lbl(row, "Nro. Documento:").pack(side=tk.LEFT)
        self._num_var = tk.StringVar()
        e = _entry(row, self._num_var, width=20)
        e.pack(side=tk.LEFT, padx=(6, 8), ipady=4)
        e.bind("<Return>", lambda _: self._buscar_individual())

        _lbl(row, "Tipo:").pack(side=tk.LEFT)
        self._tipo_var = tk.StringVar(value=TIPOS_OPCIONES[0])
        om = tk.OptionMenu(row, self._tipo_var, *TIPOS_OPCIONES)
        om.config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT,
                  highlightthickness=1, highlightbackground=FG,
                  activebackground=FG, activeforeground=BG, bd=0)
        om["menu"].config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT, bd=0,
                          activebackground=FG, activeforeground=BG)
        om.pack(side=tk.LEFT, padx=(4, 10))

        _lbl(row, "o código procesado:").pack(side=tk.LEFT)
        self._cp_var = tk.StringVar()
        _entry(row, self._cp_var, width=18).pack(side=tk.LEFT, padx=(4, 10), ipady=4)

        self._btn_buscar = _mac_btn(row, "BUSCAR", self._buscar_individual)
        self._btn_buscar.pack(side=tk.LEFT)

        # Error label
        self._lbl_error = tk.Label(p, text="", bg=BG, fg=FG, font=FONT_SMALL, anchor="w")
        self._lbl_error.pack(fill=tk.X)

        # Treeview de resultados
        tree_frame = tk.Frame(p, bg=BG, highlightthickness=1, highlightbackground=FG)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 6))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Mono.Treeview",
                        background=BG, foreground=FG, fieldbackground=BG,
                        font=FONT, rowheight=18)
        style.configure("Mono.Treeview.Heading",
                        background=FG, foreground=BG, font=FONT_BOLD,
                        relief="flat")
        style.map("Mono.Treeview",
                  background=[("selected", FG)],
                  foreground=[("selected", BG)])

        self._tree = ttk.Treeview(tree_frame, columns=("fuente", "campo", "valor"),
                                  show="headings", style="Mono.Treeview",
                                  height=18)
        self._tree.heading("fuente", text="FUENTE")
        self._tree.heading("campo",  text="CAMPO")
        self._tree.heading("valor",  text="VALOR")
        self._tree.column("fuente", width=110, anchor="w")
        self._tree.column("campo",  width=200, anchor="w")
        self._tree.column("valor",  width=320, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Exportar resultado individual
        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(fill=tk.X, pady=(0, 2))
        self._btn_exp_ind = _mac_btn(btn_row, "EXPORTAR RESULTADO", self._exportar_individual,
                                     inverted=False)
        self._btn_exp_ind.pack(side=tk.LEFT)
        self._btn_exp_ind._enabled = False
        self._btn_exp_ind.config(cursor="")
        _lbl(btn_row, "  Formato:").pack(side=tk.LEFT)
        self._fmt_ind_var = tk.StringVar(value="xlsx")
        om2 = tk.OptionMenu(btn_row, self._fmt_ind_var, *FORMATOS)
        om2.config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT,
                   highlightthickness=1, highlightbackground=FG,
                   activebackground=FG, activeforeground=BG, bd=0)
        om2["menu"].config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT, bd=0,
                           activebackground=FG, activeforeground=BG)
        om2.pack(side=tk.LEFT, padx=4)

    def _buscar_individual(self):
        # Determinar número y tipo
        cp = self._cp_var.get().strip()
        if cp:
            try:
                numero, tipo = parse_codigo_procesado(cp)
            except ValueError as e:
                self._lbl_error.config(text=f"Código procesado inválido: {e}")
                return
        else:
            numero = self._num_var.get().strip()
            tipo   = TIPO_MAP.get(self._tipo_var.get(), 1)

        ok, msg = validar_documento(numero, tipo)
        if not ok:
            self._lbl_error.config(text=msg)
            return
        self._lbl_error.config(text="")

        # Limpiar treeview
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._btn_buscar._enabled = False
        self._btn_buscar.config(cursor="")
        self._btn_exp_ind._enabled = False
        self._btn_exp_ind.config(cursor="")
        self._log(f"Consultando {TIPO_NOMBRES.get(tipo,'?')} {numero}...")

        def _worker():
            try:
                if not self._buscador:
                    self._buscador = UltraBuscador(headless=True, workers=1)
                r = self._buscador.consultar_uno(numero, tipo)
            except Exception as exc:
                r = crear_resultado_vacio(numero, tipo)
                r.error_ruc = str(exc)
            self.after(0, lambda: self._mostrar_resultado_individual(r))

        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_resultado_individual(self, r: ResultadoDocumento):
        self._btn_buscar._enabled = True
        self._btn_buscar.config(cursor="hand2")

        # Poblar treeview con secciones
        d = r.to_dict()
        secciones = {
            "Identificación": ["numero_documento", "tipo_codigo", "tipo_nombre", "codigo_procesado"],
            "DNI":    [k for k in d if k.startswith("dni_")],
            "RUC":    [k for k in d if k.startswith("ruc_")],
            "REINFO": [k for k in d if k.startswith("reinfo_")],
            "RECPO":  [k for k in d if k.startswith("recpo_")],
            "OSCE":   [k for k in d if k.startswith("osce_")],
            "SBS":    [k for k in d if k.startswith("sbs_")],
            "CarExt": [k for k in d if k.startswith("carext_")],
            "Errores": [k for k in d if k.startswith("error_")],
        }

        for fuente, campos in secciones.items():
            tiene_datos = any(d.get(c) not in (None, "") for c in campos)
            if not tiene_datos:
                continue
            for campo in campos:
                val = d.get(campo)
                if val is None or val == "":
                    continue
                self._tree.insert("", tk.END, values=(fuente, campo, str(val)))

        errs = r.resumen_errores()
        if errs:
            self._log("Errores: " + " | ".join(errs))
        else:
            self._log(f"OK: {TIPO_NOMBRES.get(r.tipo_codigo,'?')} {r.numero_documento}")

        self._resultados = [r]
        self._btn_exp_ind._enabled = True
        self._btn_exp_ind.config(cursor="hand2")

    def _exportar_individual(self):
        if not self._resultados:
            return
        fmt = self._fmt_ind_var.get()
        ruta = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("Todos", "*.*")],
            initialfile=f"ultra_id_{self._resultados[0].numero_documento}.{fmt}",
            title="Guardar resultado",
        )
        if not ruta:
            return
        try:
            exportar(self._resultados, fmt, ruta)
            self._log(f"Exportado: {ruta}")
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc))

    # ── Panel Colectivo ───────────────────────────────────────────────────────

    def _build_panel_colectivo(self):
        p = self._panel_colectivo

        # Selección de archivo
        file_row = tk.Frame(p, bg=BG)
        file_row.pack(fill=tk.X, pady=(0, 6))
        _lbl(file_row, "Archivo de entrada:").pack(side=tk.LEFT)
        self._file_var = tk.StringVar(value="(ninguno seleccionado)")
        tk.Label(file_row, textvariable=self._file_var, bg=BG, fg=FG,
                 font=FONT_SMALL, anchor="w").pack(side=tk.LEFT, padx=6)
        _mac_btn(file_row, "SELECCIONAR", self._seleccionar_archivo,
                 inverted=False).pack(side=tk.LEFT)

        # Workers y formato
        opts_row = tk.Frame(p, bg=BG)
        opts_row.pack(fill=tk.X, pady=(0, 6))

        _lbl(opts_row, "Workers:").pack(side=tk.LEFT)
        self._workers_var = tk.IntVar(value=4)
        tk.Spinbox(opts_row, from_=1, to=5, increment=1,
                   textvariable=self._workers_var, width=3,
                   bg=BG, fg=FG, insertbackground=FG, relief=tk.FLAT,
                   highlightthickness=1, highlightbackground=FG, font=FONT,
                   buttonbackground=BG).pack(side=tk.LEFT, padx=(4, 16), ipady=2)

        _lbl(opts_row, "Formato salida:").pack(side=tk.LEFT)
        self._fmt_col_var = tk.StringVar(value="xlsx")
        om = tk.OptionMenu(opts_row, self._fmt_col_var, *FORMATOS)
        om.config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT,
                  highlightthickness=1, highlightbackground=FG,
                  activebackground=FG, activeforeground=BG, bd=0)
        om["menu"].config(bg=BG, fg=FG, font=FONT, relief=tk.FLAT, bd=0,
                          activebackground=FG, activeforeground=BG)
        om.pack(side=tk.LEFT, padx=(4, 16))

        _lbl(opts_row, "Nombre salida:").pack(side=tk.LEFT)
        self._output_var = tk.StringVar(
            value=f"ultra_id_{date.today().isoformat()}"
        )
        _entry(opts_row, self._output_var, width=22).pack(side=tk.LEFT, padx=(4, 0), ipady=2)

        # Progreso
        prog_row = tk.Frame(p, bg=BG)
        prog_row.pack(fill=tk.X, pady=(4, 4))
        self._prog_bar = MacProgressBar(prog_row, height=14)
        self._prog_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._lbl_pct = tk.Label(prog_row, text="0%", bg=BG, fg=FG,
                                  font=FONT_SMALL, width=6)
        self._lbl_pct.pack(side=tk.LEFT, padx=(6, 0))

        # Log colectivo
        log_frame = tk.Frame(p, bg=BG, highlightthickness=1, highlightbackground=FG)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self._log_text = tk.Text(log_frame, height=10, bg=BG, fg=FG,
                                  insertbackground=FG, font=FONT_SMALL,
                                  relief=tk.FLAT, wrap=tk.WORD, state=tk.DISABLED)
        log_vsb = tk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                command=self._log_text.yview,
                                bg=BG, troughcolor=BG, relief=tk.FLAT, width=10)
        self._log_text.configure(yscrollcommand=log_vsb.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Botones acción
        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(fill=tk.X, pady=(0, 2))
        self._btn_iniciar  = _mac_btn(btn_row, "INICIAR",   self._iniciar_colectivo, inverted=True)
        self._btn_detener  = _mac_btn(btn_row, "DETENER",   self._detener_colectivo, inverted=False)
        self._btn_guardar  = _mac_btn(btn_row, "GUARDAR RESULTADOS", self._guardar_colectivo, inverted=False)
        self._btn_iniciar.pack(side=tk.LEFT)
        self._btn_detener.pack(side=tk.LEFT, padx=(6, 0))
        self._btn_guardar.pack(side=tk.LEFT, padx=(6, 0))
        self._btn_detener._enabled = False
        self._btn_detener.config(cursor="")
        self._btn_guardar._enabled = False
        self._btn_guardar.config(cursor="")

        self._archivo_path: Optional[str] = None
        self._documentos_col: list[tuple[str, int]] = []

    def _seleccionar_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo de documentos",
            filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls"), ("Todos", "*.*")]
        )
        if not ruta:
            return
        self._archivo_path = ruta
        self._file_var.set(Path(ruta).name)
        try:
            from console import _leer_archivo
            docs = _leer_archivo(ruta)
            self._documentos_col = docs
            self._log_col(f"Archivo cargado: {len(docs)} documentos.")
        except Exception as e:
            messagebox.showerror("Error al leer archivo", str(e))

    def _log_col(self, msg: str):
        def _do():
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, msg + "\n")
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        self.after(0, _do)

    def _iniciar_colectivo(self):
        if not self._documentos_col:
            messagebox.showwarning("Sin datos", "Selecciona un archivo primero.")
            return

        self._running = True
        self._stop_event.clear()
        self._resultados = []
        self._prog_bar.set(0)
        self._lbl_pct.config(text="0%")
        self._btn_iniciar._enabled = False
        self._btn_iniciar.config(cursor="")
        self._btn_detener._enabled = True
        self._btn_detener.config(cursor="hand2")
        self._btn_guardar._enabled = False
        self._btn_guardar.config(cursor="")

        workers = max(1, min(5, self._workers_var.get()))

        def _worker():
            try:
                buscador = UltraBuscador(headless=True, workers=workers)
                resultados = buscador.consultar_masivo(
                    self._documentos_col,
                    on_progress=self._on_progress_col,
                    on_log=self._log_col,
                    stop_event=self._stop_event,
                )
                buscador.close()
                self._resultados = resultados
            except Exception as exc:
                self._log_col(f"Error fatal: {exc}")
            finally:
                self._running = False
                self.after(0, self._finalizar_colectivo)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_progress_col(self, done: int, total: int):
        pct = (done / total) * 100 if total else 0
        self.after(0, lambda: (
            self._prog_bar.set(pct),
            self._lbl_pct.config(text=f"{pct:.0f}%"),
        ))

    def _finalizar_colectivo(self):
        self._btn_iniciar._enabled = True
        self._btn_iniciar.config(cursor="hand2")
        self._btn_detener._enabled = False
        self._btn_detener.config(cursor="")
        if self._resultados:
            self._btn_guardar._enabled = True
            self._btn_guardar.config(cursor="hand2")
        errores = sum(1 for r in self._resultados if r.resumen_errores())
        self._log_col(
            f"Completado: {len(self._resultados)} documentos, {errores} con errores."
        )

    def _detener_colectivo(self):
        if self._running:
            self._stop_event.set()
            self._log_col("Deteniendo...")

    def _guardar_colectivo(self):
        if not self._resultados:
            return
        fmt = self._fmt_col_var.get()
        nombre = self._output_var.get().strip() or f"ultra_id_{date.today().isoformat()}"
        if not nombre.endswith(f".{fmt}"):
            nombre = f"{nombre}.{fmt}"
        ruta = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("Todos", "*.*")],
            initialfile=nombre,
            title="Guardar resultados",
        )
        if not ruta:
            return
        try:
            exportar(self._resultados, fmt, ruta)
            self._log_col(f"Guardado: {ruta}")
            messagebox.showinfo("Guardado", f"Resultados guardados en:\n{ruta}")
        except Exception as exc:
            messagebox.showerror("Error al guardar", str(exc))

    # ── Panel Tutorial ────────────────────────────────────────────────────────

    def _build_panel_tutorial(self):
        p = self._panel_tutorial
        txt_frame = tk.Frame(p, bg=BG, highlightthickness=1, highlightbackground=FG)
        txt_frame.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(txt_frame, bg=BG, fg=FG, font=FONT_SMALL,
                      relief=tk.FLAT, wrap=tk.WORD, state=tk.NORMAL,
                      padx=8, pady=8, height=28)
        vsb = tk.Scrollbar(txt_frame, orient=tk.VERTICAL, command=txt.yview,
                            bg=BG, troughcolor=BG, relief=tk.FLAT, width=10)
        txt.configure(yscrollcommand=vsb.set)
        txt.insert(tk.END, TUTORIAL_TEXT)
        txt.config(state=tk.DISABLED)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    # ── Log bar global ────────────────────────────────────────────────────────

    def _build_log_bar(self):
        tk.Frame(self, bg=FG, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        bar = tk.Frame(self, bg=BG, padx=8, pady=3)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_var = tk.StringVar(value="Listo.")
        tk.Label(bar, textvariable=self._status_var, bg=BG, fg=FG,
                 font=FONT_SMALL, anchor="w", justify=tk.LEFT).pack(fill=tk.X)

    def _log(self, msg: str):
        self.after(0, lambda: self._status_var.set(msg))

    # ── Cierre ────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("En progreso",
                                        "Hay una consulta activa. ¿Cerrar de todas formas?"):
                return
        self._running = False
        self._stop_event.set()
        if self._buscador:
            try:
                self._buscador.close()
            except Exception:
                pass
        self.destroy()


def main():
    app = UltraIDApp()
    app.mainloop()


if __name__ == "__main__":
    main()
