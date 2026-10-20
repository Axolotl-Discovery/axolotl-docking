from __future__ import annotations

import os

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ... import layout as L


class AgregarLigandoDialog(QDialog):
    """Fuentes ya soportadas por el pipeline (axd.domain.sources.PubchemLigandSource /
    CcdLigandSource) más SMILES/archivo, que el asistente de ligandos (axd/wizards/ligands.py)
    ya resuelve en otro paso."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar ligando")
        self.resize(460, 320)
        self.result_ligand: dict | None = None

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._pubchem_tab(), "PubChem (nombre/CID/SID)")
        self.tabs.addTab(self._smiles_tab(), "SMILES")
        self.tabs.addTab(self._file_tab(), "Archivo")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pubchem_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.query = QLineEdit()
        self.query.setPlaceholderText("quercetin · CID 5280343 · SID 482105756")
        form.addRow("Consulta", self.query)
        self.name1 = QLineEdit()
        form.addRow("Nombre corto", self.name1)
        btn = QPushButton("Usar")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_pubchem)
        form.addRow(btn)
        return w

    def _use_pubchem(self) -> None:
        q = self.query.text().strip()
        if not q:
            return
        name = self.name1.text().strip() or q.split()[0]
        self.result_ligand = {"id": L.sanitize_id(name), "name": name, "source": "pubchem", "query": q}
        self.accept()

    def _smiles_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.name2 = QLineEdit()
        form.addRow("Nombre corto", self.name2)
        self.smiles = QLineEdit()
        self.smiles.setPlaceholderText("CC(=O)Oc1ccccc1C(=O)O")
        form.addRow("SMILES", self.smiles)
        btn = QPushButton("Usar")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_smiles)
        form.addRow(btn)
        return w

    def _use_smiles(self) -> None:
        smi = self.smiles.text().strip()
        name = self.name2.text().strip()
        if not smi or not name:
            return
        self.result_ligand = {"id": L.sanitize_id(name), "name": name, "source": "smiles", "smiles": smi}
        self.accept()

    def _file_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        row = QHBoxLayout()
        self.file_path = QLineEdit()
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.file_path, 1)
        row.addWidget(browse)
        form.addRow("Archivo/carpeta", row)
        self.name3 = QLineEdit()
        form.addRow("Nombre corto", self.name3)
        btn = QPushButton("Usar")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_file)
        form.addRow(btn)
        return w

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Estructura del ligando",
                                            filter="Estructuras (*.sdf *.mol *.mol2 *.pdb *.smi *.pdbqt)")
        if f:
            self.file_path.setText(f)
            if not self.name3.text():
                self.name3.setText(os.path.splitext(os.path.basename(f))[0])

    def _use_file(self) -> None:
        path = self.file_path.text().strip()
        name = self.name3.text().strip() or (os.path.splitext(os.path.basename(path))[0] if path else "")
        if not path or not name:
            return
        self.result_ligand = {"id": L.sanitize_id(name), "name": name, "source": "file", "file": path}
        self.accept()
