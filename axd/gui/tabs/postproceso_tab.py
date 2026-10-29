"""Pestaña 'Postprocesamiento': lo mismo que la opción 4 de la versión de
terminal (axd.resultados.menu_resultados), en la GUI:

  · Tabla de afinidades (por diana, ordenada, mejor ligando resaltado)
  · Matriz ligando × diana (coloreada por ΔG)
  · Validación por redocking (RMSD ≤ 2 Å)
  · Consenso entre motores (sólo si se activó el modo avanzado): ΔG y rango por motor, ECR, veredicto
  · Interacciones (resumen por complejo + detalle del seleccionado)
  · Acciones: analizar interacciones ahora / actualizar tablas, ver complejo
    en 3D, abrir el Excel, abrir la carpeta del proyecto

Lee los mismos CSV de 05_Analysis que la terminal; no recalcula nada."""
from __future__ import annotations

import csv
import glob
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ... import consensus as K
from ... import resultados as RES
from ... import runner as R
from ...layout import Layout
from .. import theme

SECCIONES = ("Tabla de afinidades", "Matriz ligando × diana", "Validación (redocking)", "Consenso entre motores",
             "Interacciones", "Acciones")
TIPOS_ABREV = {"Hidrofóbica": "Hidrof.", "Puente de H": "Pte. H", "Apilamiento π": "π-π", "Catión-π": "Cat-π",
               "Puente salino": "Salino", "Enlace de halógeno": "Halóg.", "Puente de agua": "Agua",
               "Coordinación metálica": "Metal"}


# ---------------------------------------------------------------- datos (sin Qt)
def _read(path):
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def affinities_by_target(proy):
    """{diana: [fila, ...]} ordenadas por afinidad media (más negativa primero)."""
    out = {}
    for f in _read(Layout(proy).affinities_summary_csv()):
        out.setdefault(f.get("diana", ""), []).append(f)
    for fs in out.values():
        fs.sort(key=lambda f: _f(f.get("afinidad_media")) if _f(f.get("afinidad_media")) is not None else 1e9)
    return out


def affinity_matrix(proy):
    """(dianas, filas) de affinity_matrix.csv; cada fila: {'ligando', diana: valor}."""
    rows = _read(Layout(proy).affinity_matrix_csv())
    cols = [c for c in (rows[0] if rows else {}) if c != "ligando"]
    return cols, rows


def redocking_rows(proy):
    out = []
    for f in _read(Layout(proy).redocking_summary_csv()):
        rmsd = _f(f.get("rmsd"))
        out.append(dict(f, ok=(rmsd is not None and rmsd <= 2.0)))
    return out


def consensus_data(proy):
    """(motores, {diana: [fila,…]}, taus por diana, meta) del último consenso, o ([], {}, {}, {})."""
    import json
    lay = Layout(proy)
    filas = _read(lay.consensus_summary_csv())
    if not filas:
        return [], {}, {}, {}
    motores = [c[3:] for c in filas[0] if c.startswith("dG_")]
    por = {}
    for f in filas:
        por.setdefault(f.get("diana", ""), []).append(f)
    taus = {}
    for t in _read(lay.consensus_tau_csv()):
        taus.setdefault(t.get("diana", ""), []).append(t)
    try:
        with open(lay.consensus_meta_json(), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        meta = {}
    return motores, por, taus, meta


def interactions(proy):
    """(tipos_activos, resumen, detalle)."""
    res = _read(Layout(proy).interactions_summary_csv())
    det = _read(Layout(proy).interactions_detail_csv())
    tipos = [c for c in (res[0] if res else {}) if c not in ("diana", "ligando", "total", "residuos", "complejo")]
    activos = [t for t in tipos if any((_f(f.get(t)) or 0) > 0 for f in res)]
    return activos, res, det


def matrix_color(value, vmin, vmax, accent="#FF5FAF"):
    """Color de celda: más intenso cuanto más negativo (mejor) el ΔG. None si no hay valor."""
    if value is None or vmin is None or vmax is None:
        return None
    span = (vmax - vmin) or 1.0
    strength = (vmax - value) / span  # 1 = el más negativo
    c = QColor(accent)
    c.setAlphaF(0.12 + 0.6 * max(0.0, min(1.0, strength)))
    return c


# ---------------------------------------------------------------- UI
def _item(text, numeric=False, bold=False):
    it = QTableWidgetItem(text)
    if numeric:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if bold:
        f = QFont(it.font())
        f.setBold(True)
        it.setFont(f)
    return it


def _num(x, nd=2):
    v = _f(x)
    return "" if v is None else f"{v:.{nd}f}"


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(False)
    return t


def _page(title_text):
    w = QWidget()
    v = QVBoxLayout(w)
    title = QLabel(title_text)
    title.setObjectName("Title")
    v.addWidget(title)
    empty = QLabel("")
    empty.setObjectName("Muted")
    empty.setWordWrap(True)
    v.addWidget(empty)
    return w, v, empty


class PostprocesoTab(QWidget):
    open_viewer = Signal(str, str)  # diana, ligando → MainWindow abre el visor de Resultados

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(lambda _p: self.refresh())
        self.state.job_state_changed.connect(self._on_job_state)
        self.state.theme_changed.connect(lambda _t: self.refresh())

        outer = QHBoxLayout(self)
        self.nav = QListWidget()
        self.nav.setMaximumWidth(230)
        self.nav.setMinimumWidth(190)  # la tabla de consenso es ancha y no debe achicar el menú
        for s in SECCIONES:
            self.nav.addItem(QListWidgetItem(s))
        outer.addWidget(self.nav)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        self._build_afinidades()
        self._build_matriz()
        self._build_redocking()
        self._build_consenso()
        self._build_interacciones()
        self._build_acciones()
        self.nav.setCurrentRow(0)
        self.refresh()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _on_job_state(self, st) -> None:
        if not st or not st.get("vivo"):
            self.refresh()

    def refresh(self) -> None:
        proy = self.state.project
        self._refresh_afinidades(proy)
        self._refresh_matriz(proy)
        self._refresh_redocking(proy)
        self._refresh_consenso(proy)
        self._refresh_interacciones(proy)
        self._refresh_acciones(proy)

    # ---------------------------------------------------------------- afinidades
    def _build_afinidades(self):
        w, v, self.af_empty = _page("Tabla de afinidades")
        row = QHBoxLayout()
        row.addWidget(QLabel("Diana:"))
        self.af_target = QComboBox()
        self.af_target.currentIndexChanged.connect(lambda _i: self._fill_afinidades())
        row.addWidget(self.af_target)
        row.addStretch(1)
        v.addLayout(row)
        self.af_table = _table(["Ligando", "ΔG media", "DE", "Mejor", "LE", "Δ control", "Semillas"])
        v.addWidget(self.af_table, 1)
        note = QLabel("kcal/mol · más negativo = mayor afinidad predicha · ◆ control · LE = −ΔG / átomos pesados · "
                      "Δ control negativo = el ligando supera al control · en negrita, el mejor de la diana")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self.stack.addWidget(w)
        self._af_data = {}

    def _refresh_afinidades(self, proy):
        self._af_data = affinities_by_target(proy) if proy else {}
        prev = self.af_target.currentText()
        self.af_target.blockSignals(True)
        self.af_target.clear()
        for d in self._af_data:
            self.af_target.addItem(d)
        if prev in self._af_data:
            self.af_target.setCurrentText(prev)
        self.af_target.blockSignals(False)
        self.af_empty.setText("" if self._af_data else
                              "Aún no hay tabla de afinidades: aparece al terminar el paso 6 (resumen).")
        self.af_empty.setVisible(not self._af_data)
        self._fill_afinidades()

    def _fill_afinidades(self):
        fs = self._af_data.get(self.af_target.currentText(), [])
        self.af_table.setRowCount(len(fs))
        for r, f in enumerate(fs):
            best = r == 0
            dc = _f(f.get("delta_vs_control"))
            vals = [(f.get("ligando", "") + ("  ◆" if f.get("tipo") == "control" else ""), False),
                    (_num(f.get("afinidad_media")), True), (_num(f.get("afinidad_de")), True),
                    (_num(f.get("mejor")), True), (_num(f.get("LE", f.get("le")), 3), True),
                    ("" if dc is None else f"{dc:+.2f}", True), (str(f.get("n_semillas", "")), True)]
            for c, (txt, numeric) in enumerate(vals):
                self.af_table.setItem(r, c, _item(txt, numeric, bold=best))

    # ---------------------------------------------------------------- matriz
    def _build_matriz(self):
        w, v, self.mx_empty = _page("Matriz ligando × diana (ΔG media, kcal/mol)")
        self.mx_table = _table([])
        v.addWidget(self.mx_table, 1)
        note = QLabel("Color más intenso = ΔG más negativo (mayor afinidad predicha) dentro de la matriz.")
        note.setObjectName("Muted")
        v.addWidget(note)
        self.stack.addWidget(w)

    def _refresh_matriz(self, proy):
        cols, rows = affinity_matrix(proy) if proy else ([], [])
        self.mx_empty.setText("" if rows else "Aún no hay matriz de afinidades (paso 6, resumen).")
        self.mx_empty.setVisible(not rows)
        self.mx_table.clear()
        self.mx_table.setColumnCount(len(cols) + 1)
        self.mx_table.setHorizontalHeaderLabels(["Ligando"] + cols)
        self.mx_table.setRowCount(len(rows))
        vals = [_f(f.get(c)) for f in rows for c in cols]
        vals = [x for x in vals if x is not None]
        vmin, vmax = (min(vals), max(vals)) if vals else (None, None)
        accent = theme.tokens_for(self.state.theme)["accent"]
        for r, f in enumerate(rows):
            self.mx_table.setItem(r, 0, _item(f.get("ligando", "")))
            for c, col in enumerate(cols, start=1):
                x = _f(f.get(col))
                it = _item(_num(x), numeric=True)
                color = matrix_color(x, vmin, vmax, accent)
                if color is not None:
                    it.setBackground(QBrush(color))
                self.mx_table.setItem(r, c, it)

    # ---------------------------------------------------------------- redocking
    def _build_redocking(self):
        w, v, self.rd_empty = _page("Validación por redocking (criterio: RMSD ≤ 2 Å)")
        self.rd_table = _table(["Diana", "Semilla", "ΔG", "RMSD (Å)", "Resultado"])
        v.addWidget(self.rd_table, 1)
        self.stack.addWidget(w)

    def _refresh_redocking(self, proy):
        rows = redocking_rows(proy) if proy else []
        self.rd_empty.setText("" if rows else "No hay redocking: sólo se hace cuando la caja viene de un ligando "
                                               "co-cristalizado.")
        self.rd_empty.setVisible(not rows)
        t = theme.tokens_for(self.state.theme)
        self.rd_table.setRowCount(len(rows))
        for r, f in enumerate(rows):
            for c, (txt, numeric) in enumerate([(f.get("diana", ""), False), (str(f.get("semilla", "")), True),
                                                (_num(f.get("afinidad")), True), (_num(f.get("rmsd")), True)]):
                self.rd_table.setItem(r, c, _item(txt, numeric))
            ok = _item("✔ válido" if f["ok"] else "✘ revisar")
            ok.setForeground(QBrush(QColor(t["success"] if f["ok"] else t["error"])))
            self.rd_table.setItem(r, 4, ok)

    # ---------------------------------------------------------------- consenso
    def _build_consenso(self):
        w, v, self.cs_empty = _page("Consenso entre motores (ECR + acuerdo de poses)")
        row = QHBoxLayout()
        row.addWidget(QLabel("Diana:"))
        self.cs_target = QComboBox()
        self.cs_target.currentIndexChanged.connect(lambda _i: self._fill_consenso())
        row.addWidget(self.cs_target)
        row.addStretch(1)
        v.addLayout(row)
        self.cs_table = _table([])
        v.addWidget(self.cs_table, 1)
        self.cs_tau = QLabel("")
        self.cs_tau.setWordWrap(True)
        v.addWidget(self.cs_tau)
        note = QLabel(f"ΔG en kcal/mol · «#» = rango en ese motor · ECR# = posición por consenso (1 = mejor) · "
                      f"RMSD máx = mayor distancia entre las mejores poses de dos motores · veredicto: Robusto = "
                      f"rangos (dispersión ≤ {K.SPREAD_OK}) y poses (≤ {K.RMSD_OK} Å) coinciden; Parcial = sólo uno "
                      f"de los dos; Discrepante = ninguno.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self.stack.addWidget(w)
        self._cs = ([], {}, {}, {})

    def _refresh_consenso(self, proy):
        self._cs = consensus_data(proy) if proy else ([], {}, {}, {})
        _m, por, _t, _meta = self._cs
        prev = self.cs_target.currentText()
        self.cs_target.blockSignals(True)
        self.cs_target.clear()
        for d in por:
            self.cs_target.addItem(d)
        if prev in por:
            self.cs_target.setCurrentText(prev)
        self.cs_target.blockSignals(False)
        self.cs_empty.setText("" if por else
                              "Sin consenso todavía. Actívalo en Proyecto → Parámetros → Modo avanzado y corre el "
                              "proceso (el paso «consenso» corre después del docking).")
        self.cs_empty.setVisible(not por)
        self._fill_consenso()

    def _fill_consenso(self):
        motores, por, taus, meta = self._cs
        filas = por.get(self.cs_target.currentText(), [])
        nombres = [K.nombre_motor(m, (meta or {}).get("principal_real")).split(" (")[0] for m in motores]
        heads = ["Ligando"] + [f"ΔG {n}" for n in nombres] + [f"# {n}" for n in nombres] \
            + ["ECR#", "Disp.", "RMSD máx (Å)", "Veredicto"]
        self.cs_table.clear()
        self.cs_table.setColumnCount(len(heads))
        self.cs_table.setHorizontalHeaderLabels(heads)
        self.cs_table.setRowCount(len(filas))
        t = theme.tokens_for(self.state.theme)
        color = {K.ROBUSTO: t["success"], K.DISCREPANTE: t["error"], K.PARCIAL: t["accent"]}
        for r, f in enumerate(filas):
            vals = [f.get("ligando", "") + ("  ◆" if f.get("tipo") == "control" else "")]
            vals += [_num(f.get(f"dG_{m}")) for m in motores]
            vals += [("" if _f(f.get(f"rango_{m}")) is None else f"{_f(f.get(f'rango_{m}')):g}") for m in motores]
            vals += [str(f.get("orden", "") or "—"), _num(f.get("dispersion_rangos"), 1), _num(f.get("rmsd_max"), 1)]
            for c, txt in enumerate(vals):
                self.cs_table.setItem(r, c, _item(txt, numeric=c > 0, bold=f.get("orden") == "1"))
            it = _item(f.get("veredicto", ""))
            it.setToolTip(f.get("motivo", ""))
            if f.get("veredicto") in color:
                it.setForeground(QBrush(QColor(color[f["veredicto"]])))
            self.cs_table.setItem(r, len(vals), it)
        pares = taus.get(self.cs_target.currentText(), [])
        partes = [f"{K.nombre_motor(p['motor_a'])} ↔ {K.nombre_motor(p['motor_b'])}: τ = {_num(p.get('tau'))}"
                  for p in pares if _f(p.get("tau")) is not None]
        self.cs_tau.setText("Acuerdo entre motores (τ de Kendall; 1 = mismo orden): " + " · ".join(partes)
                            if partes else "")

    # ---------------------------------------------------------------- interacciones
    def _build_interacciones(self):
        w, v, self.in_empty = _page("Interacciones por complejo (mejor pose)")
        self.in_table = _table([])
        self.in_table.itemSelectionChanged.connect(self._fill_detalle)
        v.addWidget(self.in_table, 2)
        head = QHBoxLayout()
        self.in_detail_title = QLabel("")
        f = QFont(self.in_detail_title.font())
        f.setBold(True)
        self.in_detail_title.setFont(f)
        head.addWidget(self.in_detail_title)
        head.addStretch(1)
        self.in_view_btn = QPushButton("Ver en 3D")
        self.in_view_btn.clicked.connect(self._view_selected)
        head.addWidget(self.in_view_btn)
        v.addLayout(head)
        self.in_detail = _table(["Tipo", "Residuo", "Cadena", "Dist. (Å)", "Detalle"])
        self.in_detail.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.in_detail, 3)
        self.in_footer = QLabel("")
        self.in_footer.setObjectName("Muted")
        self.in_footer.setWordWrap(True)
        v.addWidget(self.in_footer)
        self.stack.addWidget(w)
        self._in_res, self._in_det = [], []

    def _refresh_interacciones(self, proy):
        activos, self._in_res, self._in_det = interactions(proy) if proy else ([], [], [])
        self.in_empty.setText("" if self._in_res else
                              "Aún no hay análisis de interacciones → sección «Acciones», "
                              "«Analizar interacciones ahora».")
        self.in_empty.setVisible(not self._in_res)
        cols = ["diana", "ligando", "total"] + activos
        self.in_table.blockSignals(True)
        self.in_table.clear()
        self.in_table.setColumnCount(len(cols))
        self.in_table.setHorizontalHeaderLabels(["Diana", "Ligando", "Total"] + [TIPOS_ABREV.get(t, t) for t in activos])
        self.in_table.setRowCount(len(self._in_res))
        for r, f in enumerate(self._in_res):
            for c, col in enumerate(cols):
                self.in_table.setItem(r, c, _item(str(f.get(col, "")), numeric=c >= 2))
        self.in_table.blockSignals(False)
        if self._in_res:
            self.in_table.selectRow(0)
        self._fill_detalle()

    def _selected_complex(self):
        rows = self.in_table.selectionModel().selectedRows() if self.in_table.selectionModel() else []
        if not rows or rows[0].row() >= len(self._in_res):
            return None
        return self._in_res[rows[0].row()]

    def _fill_detalle(self):
        f = self._selected_complex()
        self.in_view_btn.setVisible(bool(f))
        if not f:
            self.in_detail.setRowCount(0)
            self.in_detail_title.setText("")
            self.in_footer.setText("")
            return
        det = [d for d in self._in_det if d.get("diana") == f.get("diana") and d.get("ligando") == f.get("ligando")]
        det.sort(key=lambda d: (d.get("tipo", ""), _f(d.get("distancia")) or 0))
        self.in_detail_title.setText(f"Detalle · {f.get('diana')} + {f.get('ligando')}")
        self.in_detail.setRowCount(len(det))
        for r, d in enumerate(det):
            for c, (txt, numeric) in enumerate([(d.get("tipo", ""), False), (d.get("residuo", ""), False),
                                                (d.get("cadena", ""), False), (_num(d.get("distancia")), True),
                                                (d.get("detalle", ""), False)]):
                self.in_detail.setItem(r, c, _item(txt, numeric))
        metodo = det[0].get("metodo", "-") if det else "-"
        self.in_footer.setText(f"Residuos: {f.get('residuos', '')} · Complejo: {f.get('complejo', '')} · "
                               f"método: {metodo}")

    def _view_selected(self):
        f = self._selected_complex()
        if f:
            self.open_viewer.emit(f.get("diana", ""), f.get("ligando", ""))

    # ---------------------------------------------------------------- acciones
    def _build_acciones(self):
        w, v, self.ac_empty = _page("Acciones")
        self.ac_status = QLabel("")
        self.ac_status.setObjectName("Muted")
        self.ac_status.setWordWrap(True)
        v.addWidget(self.ac_status)
        for label, desc, fn, primary in (
            ("Analizar interacciones ahora / actualizar tablas",
             "Corre en segundo plano los pasos 'resumen' e 'interacciones' sobre los resultados que ya hay.",
             self._analizar, True),
            ("Generar reporte PDF",
             "Reporte profesional con logos, métodos, tablas, figuras y referencias (07_Report). Los logos y el "
             "laboratorio se configuran en Entorno → Reporte.", self._generar_reporte, True),
            ("Abrir último reporte", "El PDF más reciente de 07_Report.", self._abrir_reporte, False),
            ("Ver un complejo en 3D", "Abre el visor de la pestaña Resultados.", self._ver_3d, False),
            ("Abrir el Excel de resultados", "El .xlsx que genera el paso 'resumen'.", self._abrir_excel, False),
            ("Abrir la carpeta del proyecto", "En el Finder / Explorador / gestor de archivos.", self._abrir_carpeta,
             False),
        ):
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(fn)
            d = QLabel(desc)
            d.setObjectName("Muted")
            row = QHBoxLayout()
            row.addWidget(b)
            row.addWidget(d, 1)
            v.addLayout(row)
        v.addStretch(1)
        self.stack.addWidget(w)

    def _refresh_acciones(self, proy):
        if not proy:
            self.ac_status.setText("Abre un proyecto para usar estas acciones.")
            return
        e = R.estado(proy)
        self.ac_status.setText("Hay un trabajo corriendo en este proyecto: espera a que termine para analizar."
                               if e and e.get("vivo") else "")

    def _analizar(self):
        proy = self.state.project
        if not proy:
            return
        e = R.estado(proy)
        if e and e.get("vivo"):
            QMessageBox.information(self, "Trabajo en curso", "Ya hay un trabajo corriendo; espera a que termine.")
            return
        R.ejecutar(proy, ["summary", "interactions"], fondo=True)
        self.ac_status.setText("Analizando en segundo plano… el avance se ve en la pestaña Proceso; "
                               "las tablas se actualizan solas al terminar.")

    def _ver_3d(self):
        f = self._selected_complex()
        self.open_viewer.emit(f.get("diana", "") if f else "", f.get("ligando", "") if f else "")

    def _abrir_excel(self):
        proy = self.state.project
        xl = sorted(glob.glob(Layout(proy).affinities_xlsx_glob())) if proy else []
        if not xl:
            QMessageBox.information(self, "No hay Excel", "No hay Excel todavía (se genera en el paso 'resumen').")
            return
        RES.abrir_en_windows(xl[0])

    def _generar_reporte(self):
        proy = self.state.project
        if not proy:
            return
        e = R.estado(proy)
        if e and e.get("vivo"):
            QMessageBox.information(self, "Trabajo en curso", "Ya hay un trabajo corriendo; espera a que termine.")
            return
        R.ejecutar(proy, ["report"], fondo=True)
        self.ac_status.setText("Generando el reporte en segundo plano… quedará en 07_Report "
                               "(«Abrir último reporte» cuando termine).")

    def _abrir_reporte(self):
        proy = self.state.project
        d = Layout(proy).report_dir() if proy else ""
        pdfs = sorted((f for f in glob.glob(os.path.join(d, "*.pdf")) if not f.endswith("reporte_ultimo.pdf")),
                      key=os.path.getmtime) if d else []
        if not pdfs:
            QMessageBox.information(self, "Sin reporte", "Todavía no hay reportes. Usa «Generar reporte PDF».")
            return
        RES.abrir_en_windows(pdfs[-1])

    def _abrir_carpeta(self):
        if self.state.project:
            RES.abrir_en_windows(self.state.project)
