"""Diálogo '+ Agregar diana', con las 4 fuentes del wireframe 'Análisis —
buscar diana por nombre': Buscar por nombre (nuevo, RCSB Search API),
PDB ID, UniProt/AlphaFold y Archivo local. 'Trabajos recientes' no se toca
aquí — vive en axd.config.register_recent / la pestaña Proyecto, confirmado
sin cambios."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTabWidget,
                               QCheckBox, QVBoxLayout, QWidget)

from ... import layout as L
from ..services import connectivity, search_rcsb


class AgregarDianaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar diana")
        self.resize(520, 420)
        self.result_target: dict | None = None

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_search_tab(), "Buscar por nombre")
        self.tabs.addTab(self._build_pdb_tab(), "PDB ID")
        self.tabs.addTab(self._build_uniprot_tab(), "UniProt / AlphaFold")
        self.tabs.addTab(self._build_file_tab(), "Archivo local")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- buscar por nombre
    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.offline_banner = QLabel("📡  Sin conexión a internet — esto no es un error de Axolotl Docking. "
                                      "Usá PDB ID o archivo local mientras tanto.")
        self.offline_banner.setWordWrap(True)
        self.offline_banner.setObjectName("Muted")
        v.addWidget(self.offline_banner)

        row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Nombre de proteína, gen… (podés pegar texto, Ctrl+V)")
        self.search_box.returnPressed.connect(self._do_search)
        search_btn = QPushButton("Buscar")
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(self.search_box, 1)
        row.addWidget(search_btn)
        v.addLayout(row)

        self.human_only = QCheckBox("Sólo humano")
        v.addWidget(self.human_only)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda _i: self._use_search_result())
        v.addWidget(self.results, 1)

        use_btn = QPushButton("Usar esta diana")
        use_btn.setObjectName("Primary")
        use_btn.clicked.connect(self._use_search_result)
        v.addWidget(use_btn)

        self._refresh_offline_banner()
        return w

    def _refresh_offline_banner(self) -> None:
        online = connectivity.is_online()
        self.offline_banner.setVisible(not online)
        self.search_box.setEnabled(online)
        self.human_only.setEnabled(online)

    def _do_search(self) -> None:
        self._refresh_offline_banner()
        if not self.search_box.isEnabled():
            return
        query = self.search_box.text().strip()
        if not query:
            return
        self.results.clear()
        try:
            hits = search_rcsb.search_targets(query, human_only=self.human_only.isChecked())
        except search_rcsb.SearchError as e:
            QMessageBox.warning(self, "No pude verificar ahora",
                                 f'⚠ RCSB no respondió a tiempo para "{query}" (hay conexión, el servicio '
                                 f'puede estar lento): {e}')
            return
        if not hits:
            self.results.addItem("Sin resultados.")
            return
        for h in hits:
            item = QListWidgetItem(f"{h.pdb_id}  ·  {h.title}" + (f"  ·  {h.organism}" if h.organism else ""))
            item.setData(1, h)
            self.results.addItem(item)

    def _use_search_result(self) -> None:
        item = self.results.currentItem()
        if not item or not item.data(1):
            return
        hit = item.data(1)
        self.result_target = {"id": L.sanitize_id(hit.pdb_id), "source": "pdb", "name": hit.title or hit.pdb_id,
                               "pdb": hit.pdb_id, "chains": "auto", "cofactors": "auto",
                               "box": {"mode": "auto"}}
        self.accept()

    # ---------------------------------------------------------------- PDB ID
    def _build_pdb_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.pdb_id = QLineEdit()
        self.pdb_id.setPlaceholderText("1M17")
        form.addRow("PDB ID", self.pdb_id)
        self.pdb_name = QLineEdit()
        form.addRow("Nombre corto", self.pdb_name)
        btn = QPushButton("Usar este PDB ID")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_pdb)
        form.addRow(btn)
        return w

    def _use_pdb(self) -> None:
        pdb = self.pdb_id.text().strip().upper()
        if not pdb:
            return
        name = self.pdb_name.text().strip() or pdb
        self.result_target = {"id": L.sanitize_id(name), "source": "pdb", "name": name, "pdb": pdb,
                               "chains": "auto", "cofactors": "auto", "box": {"mode": "auto"}}
        self.accept()

    # ---------------------------------------------------------------- UniProt/AlphaFold
    def _build_uniprot_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.uniprot_id = QLineEdit()
        self.uniprot_id.setPlaceholderText("P00533")
        form.addRow("UniProt ID", self.uniprot_id)
        self.uniprot_name = QLineEdit()
        form.addRow("Nombre corto", self.uniprot_name)
        btn = QPushButton("Usar AlphaFold")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_uniprot)
        form.addRow(btn)
        return w

    def _use_uniprot(self) -> None:
        up = self.uniprot_id.text().strip().upper()
        if not up:
            return
        name = self.uniprot_name.text().strip() or up
        self.result_target = {"id": L.sanitize_id(name), "source": "alphafold", "name": name, "uniprot": up,
                               "chains": "auto", "cofactors": "auto", "box": {"mode": "auto"}}
        self.accept()

    # ---------------------------------------------------------------- archivo local
    def _build_file_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        row = QHBoxLayout()
        self.file_path = QLineEdit()
        browse = QPushButton("Elegir archivo…")
        browse.clicked.connect(self._browse_file)
        row.addWidget(self.file_path, 1)
        row.addWidget(browse)
        form.addRow("Archivo (.pdb/.cif)", row)
        self.file_name = QLineEdit()
        form.addRow("Nombre corto", self.file_name)
        btn = QPushButton("Usar este archivo")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._use_file)
        form.addRow(btn)
        return w

    def _browse_file(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Estructura", filter="Estructuras (*.pdb *.cif)")
        if f:
            self.file_path.setText(f)
            if not self.file_name.text():
                self.file_name.setText(os.path.splitext(os.path.basename(f))[0])

    def _use_file(self) -> None:
        path = self.file_path.text().strip()
        if not path:
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Archivo no encontrado", f"No encuentro el archivo:\n{path}")
            return
        name = self.file_name.text().strip() or os.path.splitext(os.path.basename(path))[0]
        # 'file' queda como la ruta elegida por ahora; quien recibe result_target
        # (AnalisisTab._add_target) la materializa dentro del proyecto — ver ahí.
        self.result_target = {"id": L.sanitize_id(name), "source": "file", "name": name, "file": path,
                               "chains": "auto", "cofactors": "auto", "box": {"mode": "auto"}}
        self.accept()
