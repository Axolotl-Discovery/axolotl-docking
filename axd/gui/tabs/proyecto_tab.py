"""Pestaña 'Proyecto': recientes (axd.config.register_recent / load_global,
sin tocar — ya confirmado por el usuario), abrir carpeta, crear proyecto
nuevo. Es una capa fina sobre axd.config.new_project / find_project."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ... import config as C


class _NuevoProyectoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proyecto nuevo")
        form = QFormLayout(self)

        row = QHBoxLayout()
        self.folder = QLineEdit()
        browse = QPushButton("Elegir carpeta…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        form.addRow("Carpeta", row)

        self.name = QLineEdit()
        form.addRow("Nombre", self.name)

        self.mode = QComboBox()
        self.mode.addItem("Básico (todo automático)", "basic")
        self.mode.addItem("Avanzado", "advanced")
        form.addRow("Modo", self.mode)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta donde crear el proyecto")
        if d:
            self.folder.setText(d)

    def values(self):
        return self.folder.text().strip(), self.name.text().strip(), self.mode.currentData()


class ProyectoTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)

        title = QLabel("Proyectos")
        title.setObjectName("Title")
        layout.addWidget(title)

        row = QHBoxLayout()
        open_btn = QPushButton("Abrir carpeta…")
        open_btn.clicked.connect(self._open_folder)
        new_btn = QPushButton("+ Proyecto nuevo")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self._new_project)
        row.addWidget(open_btn)
        row.addWidget(new_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.empty_label = QLabel("Todavía no hay proyectos recientes. Abrí una carpeta existente o creá uno "
                                   "nuevo.")
        self.empty_label.setObjectName("Muted")
        layout.addWidget(self.empty_label)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open_item)
        layout.addWidget(self.list, 1)

        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        recents = self.state.recent_projects()
        self.empty_label.setVisible(not recents)
        self.list.setVisible(bool(recents))
        for path in recents:
            item = QListWidgetItem(f"{os.path.basename(path)}   ·   {path}")
            item.setData(1, path)
            self.list.addItem(item)

    def _open_item(self, item: QListWidgetItem) -> None:
        self.state.open_project(item.data(1))

    def _open_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta del proyecto")
        if not d:
            return
        if not os.path.exists(os.path.join(d, C.PROJECT_FILE)):
            QMessageBox.warning(self, "No es un proyecto", f"Esa carpeta no tiene {C.PROJECT_FILE}. "
                                 "Creá el proyecto con '+ Proyecto nuevo'.")
            return
        self.state.open_project(d)

    def _new_project(self) -> None:
        dlg = _NuevoProyectoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder, name, mode = dlg.values()
        if not folder or not name:
            QMessageBox.warning(self, "Faltan datos", "Indicá carpeta y nombre.")
            return
        os.makedirs(folder, exist_ok=True)
        C.new_project(folder, name, mode=mode)
        self.state.open_project(folder)
