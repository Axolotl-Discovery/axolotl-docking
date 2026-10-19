"""Pestaña 'Resultados': la tabla de afinidades real (05_Analysis/affinities_summary.csv,
la misma que genera el paso 'resumen' del pipeline), sin reimplementar el cálculo."""
from __future__ import annotations

import csv
import glob
import os

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ... import resultados as RES
from ...layout import Layout


class ResultadosTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(lambda _p: self.refresh())
        self.state.job_state_changed.connect(lambda _e: self.refresh())

        layout = QVBoxLayout(self)
        title = QLabel("Resultados")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.empty_label = QLabel("Aún no hay tabla de afinidades. Corré el pipeline (o el paso 'resumen').")
        self.empty_label.setObjectName("Muted")
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 0)
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

        self.refresh()

    def refresh(self) -> None:
        proy = self.state.project
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        if not proy:
            self.empty_label.setText("Abrí un proyecto para ver resultados.")
            self.empty_label.show()
            return
        csv_path = Layout(proy).affinities_summary_csv()
        if not os.path.exists(csv_path):
            self.empty_label.setText("Aún no hay tabla de afinidades. Corré el pipeline (o el paso 'resumen').")
            self.empty_label.show()
            return
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            self.empty_label.show()
            return
        self.empty_label.hide()
        cols = list(rows[0].keys())
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                self.table.setItem(r, c, QTableWidgetItem(str(row.get(col, ""))))

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
