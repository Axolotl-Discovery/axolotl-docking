"""Pestaña 'Resultados' (incluye la antigua 'Visualización').

Vista principal: la tabla de afinidades real (05_Analysis/affinities_summary.csv,
la que genera el paso 'resumen'), con un botón de ojo antes de "Diana" en cada
fila. El ojo cambia la pestaña al visor 3D de ese par diana + ligando
(axd.gui.tabs.visualizacion_tab), con un botón para volver a la tabla."""
from __future__ import annotations

import csv
import glob
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ... import resultados as RES
from ...layout import Layout
from .. import icons, theme
from .visualizacion_tab import VisualizacionTab

# Encabezados legibles para las columnas que escribe pipeline/summary.py; una
# columna desconocida se muestra con su nombre tal cual.
HEADERS = {
    "diana": "Diana", "ligando": "Ligando", "nombre": "Nombre", "tipo": "Tipo",
    "afinidad_media": "Afinidad media\n(kcal/mol)", "afinidad_de": "DE", "mejor": "Mejor\n(kcal/mol)",
    "n_semillas": "Semillas", "n_pesados": "Átomos\npesados", "LE": "LE", "le": "LE",
    "control_ref": "Control", "afinidad_control": "Afinidad\ncontrol", "delta_vs_control": "Δ vs\ncontrol",
}
NUMERIC = {"afinidad_media", "afinidad_de", "mejor", "n_semillas", "n_pesados", "LE", "le",
           "afinidad_control", "delta_vs_control"}


def read_affinities(proy):
    """(columnas, filas) de affinities_summary.csv, o ([], []) si no existe."""
    path = Layout(proy).affinities_summary_csv()
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return [], []
    return (list(rows[0].keys()) if rows else []), rows


def viewable(proy, target: str, ligand: str) -> str:
    """'complex' si hay complejo diana+ligando, 'target' si sólo la diana
    preparada (receptor limpio), '' si no hay nada que ver aún."""
    lay = Layout(proy)
    if os.path.isfile(lay.complex_pdb(target, ligand)):
        return "complex"
    if os.path.isfile(lay.receptor_clean(target)) or os.path.isfile(lay.receptor_pdbqt(target)):
        return "target"
    return ""


class ResultadosTab(QWidget):
    TABLE, VIEWER = 0, 1

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(lambda _p: self._on_project_changed())
        self.state.job_state_changed.connect(self._on_job_state)
        self.state.theme_changed.connect(lambda _t: self.refresh())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # ---- página tabla
        page = QWidget()
        layout = QVBoxLayout(page)
        head = QHBoxLayout()
        title = QLabel("Resultados")
        title.setObjectName("Title")
        head.addWidget(title)
        head.addStretch(1)
        self.viewer_btn = QPushButton("Ver estructuras 3D")
        self.viewer_btn.clicked.connect(lambda: self.show_viewer())
        head.addWidget(self.viewer_btn)
        layout.addLayout(head)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.excel_btn = QPushButton("Abrir Excel")
        self.excel_btn.clicked.connect(self._open_excel)
        self.folder_btn = QPushButton("Abrir carpeta 05_Analysis")
        self.folder_btn.clicked.connect(self._open_folder)
        row.addWidget(self.excel_btn)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.stack.addWidget(page)

        # ---- página visor
        self.viewer = VisualizacionTab(state, on_back=self.show_table)
        self.stack.addWidget(self.viewer)

        self.refresh()

    # ---------------------------------------------------------------- navegación
    def show_table(self) -> None:
        self.stack.setCurrentIndex(self.TABLE)
        self.refresh()

    def show_viewer(self, target: str | None = None, ligand: str | None = None) -> None:
        self.stack.setCurrentIndex(self.VIEWER)
        if target:
            self.viewer.select(target, ligand)
        else:
            self.viewer.refresh()

    def _on_project_changed(self) -> None:
        self.stack.setCurrentIndex(self.TABLE)
        self.refresh()

    def _on_job_state(self, st) -> None:
        if not st or not st.get("vivo"):
            self.refresh()

    # ---------------------------------------------------------------- tabla
    def refresh(self) -> None:
        proy = self.state.project
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.viewer_btn.setVisible(bool(proy))
        if not proy:
            self._empty("Abre un proyecto para ver resultados.")
            return
        cols, rows = read_affinities(proy)
        if not rows:
            self._empty("Aún no hay tabla de afinidades: aparece al terminar el paso 6 (resumen). "
                        "Mientras tanto puedes ver las dianas preparadas con «Ver estructuras 3D».")
            return
        self.empty_label.hide()
        self.table.show()

        t = theme.tokens_for(self.state.theme)
        self.table.setColumnCount(len(cols) + 1)
        self.table.setHorizontalHeaderLabels([""] + [HEADERS.get(c, c) for c in cols])
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            target, ligand = row.get("diana", ""), row.get("ligando", "")
            kind = viewable(proy, target, ligand)
            eye = QToolButton()
            eye.setObjectName("EyeButton")
            eye.setIcon(icons.icon("eye", t["accent"] if kind == "complex" else t["text_secondary"]))
            eye.setAutoRaise(True)
            eye.setCursor(Qt.CursorShape.PointingHandCursor)
            eye.setEnabled(bool(kind))
            eye.setToolTip({"complex": f"Ver {target} + {ligand} en 3D",
                            "target": f"Aún no hay complejo de {ligand}: se verá la diana {target} "
                                      "(el complejo sale en el paso 7, interacciones)",
                            "": "Aún no hay estructuras preparadas para esta diana"}[kind])
            eye.clicked.connect(lambda _c=False, a=target, b=ligand: self.show_viewer(a, b))
            self.table.setCellWidget(r, 0, eye)
            for c, col in enumerate(cols, start=1):
                item = QTableWidgetItem(str(row.get(col, "") or ""))
                if col in NUMERIC:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        hh.setStretchLastSection(False)

    def _empty(self, text: str) -> None:
        self.empty_label.setText(text)
        self.empty_label.show()
        self.table.hide()

    # ---------------------------------------------------------------- acciones
    def _open_excel(self) -> None:
        proy = self.state.project
        if not proy:
            return
        matches = glob.glob(Layout(proy).affinities_xlsx_glob())
        if not matches:
            QMessageBox.information(self, "No hay Excel", "Todavía no se generó el archivo .xlsx de afinidades.")
            return
        RES.abrir_en_windows(matches[0])

    def _open_folder(self) -> None:
        proy = self.state.project
        if proy:
            RES.abrir_en_windows(Layout(proy).analysis_dir())
