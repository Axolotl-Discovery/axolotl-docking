"""Pestaña 'Visualización': lista los complejos ya generados (paso
'interactions' del pipeline) y los abre con el PyMOL del entorno conda —
exactamente axd.resultados.abrir_pymol(), reutilizado tal cual."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ... import resultados as RES
from ...layout import Layout


class VisualizacionTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(lambda _p: self.refresh())

        layout = QVBoxLayout(self)
        title = QLabel("Visualización")
        title.setObjectName("Title")
        layout.addWidget(title)
        note = QLabel("Complejos proteína + ligando generados por el pipeline (paso 'interacciones').")
        note.setObjectName("Muted")
        layout.addWidget(note)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        open_btn = QPushButton("Abrir en PyMOL")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_pymol)
        folder_btn = QPushButton("Mostrar carpeta")
        folder_btn.clicked.connect(self._open_folder)
        row.addWidget(open_btn)
        row.addWidget(folder_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        proy = self.state.project
        if not proy:
            return
        comp_dir = Layout(proy).complexes_dir()
        if not os.path.isdir(comp_dir):
            return
        for fn in sorted(os.listdir(comp_dir)):
            if fn.endswith("_complex.pdb"):
                label = fn[:-len("_complex.pdb")].replace("__", "  +  ")
                item = QListWidgetItem(label)
                item.setData(1, os.path.join(comp_dir, fn))
                self.list.addItem(item)

    def _selected_path(self) -> str | None:
        item = self.list.currentItem()
        return item.data(1) if item else None

    def _open_pymol(self) -> None:
        path = self._selected_path()
        if not path:
            QMessageBox.information(self, "Elegí un complejo", "Seleccioná un complejo de la lista.")
            return
        RES.abrir_pymol(path)

    def _open_folder(self) -> None:
        path = self._selected_path()
        if path:
            RES.abrir_en_windows(os.path.dirname(path))
