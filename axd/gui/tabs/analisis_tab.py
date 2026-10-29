"""Pestaña 'Proyecto' (antes 'Proyecto' + 'Análisis'): abrir/crear proyecto,
dianas, ligandos/controles, caja de docking y parámetros. Lee/escribe axd.json directamente vía axd.config.load_project /
save_project (el mismo dict que usan los asistentes de axd/wizards), para no
duplicar ningún esquema."""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QGroupBox, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ... import config as C
from ... import consensus as K
from ... import layout as L
from ..dialogs.agregar_diana_dialog import AgregarDianaDialog
from ..dialogs.agregar_ligando_dialog import AgregarLigandoDialog
from .proyecto_tab import ProyectosPage

SECCIONES = ("Proyecto", "Dianas", "Ligandos y controles", "Caja de docking", "Parámetros")


class AnalisisTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(self._on_project_changed)

        outer = QHBoxLayout(self)
        self.nav = nav = QListWidget()
        nav.setMaximumWidth(220)
        for label in SECCIONES:
            nav.addItem(QListWidgetItem(label))
        nav.currentRowChanged.connect(self._on_nav_changed)
        outer.addWidget(nav)

        self.stack = QStackedWidget()
        self.proyectos_page = ProyectosPage(state)
        self.stack.addWidget(self.proyectos_page)
        self._build_dianas_page()
        self._build_ligandos_page()
        self._build_caja_page()
        self._build_parametros_page()
        outer.addWidget(self.stack, 1)
        self._update_nav_enabled()
        nav.setCurrentRow(0)

    def _on_nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)

    def _on_project_changed(self, path: str) -> None:
        self._update_nav_enabled()
        if path and self.nav.currentRow() == 0:
            self.nav.setCurrentRow(1)  # al abrir un proyecto, directo a configurarlo
        elif not path:
            self.nav.setCurrentRow(0)
        self.refresh()

    def _update_nav_enabled(self) -> None:
        """Sin proyecto abierto sólo tiene sentido la sección 'Proyecto'."""
        hay = bool(self.state.project)
        for i in range(1, self.nav.count()):
            it = self.nav.item(i)
            flags = it.flags()
            it.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if hay else flags & ~Qt.ItemFlag.ItemIsEnabled)

    def _project(self) -> dict | None:
        if not self.state.project:
            return None
        return C.load_project(self.state.project)

    def _save(self, p: dict) -> None:
        C.save_project(self.state.project, p)
        self.refresh()

    def _materializar_archivo_local(self, carpeta_destino: str, item: dict) -> None:
        """Copia un archivo local elegido en el diálogo dentro de la carpeta del
        proyecto — lo mismo que ya hace el asistente de CLI (axd.wizards.new.
        _importar_rutas) y que el diálogo de la GUI no hacía: sin esto, 'file'
        quedaba apuntando a una ruta fuera del proyecto (a menudo absoluta), que
        deja de existir en cuanto el proyecto se mueve o se comparte."""
        origen = item["file"]
        ext = os.path.splitext(origen)[1] or ".pdb"
        os.makedirs(carpeta_destino, exist_ok=True)
        destino = os.path.join(carpeta_destino, item["id"] + ext)
        if os.path.abspath(origen) != os.path.abspath(destino):
            shutil.copy(origen, destino)
        item["file"] = os.path.relpath(destino, self.state.project)

    def refresh(self) -> None:
        self._refresh_dianas()
        self._refresh_ligandos()
        self._refresh_caja()
        self._refresh_parametros()

    # ---------------------------------------------------------------- Dianas
    def _build_dianas_page(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Dianas")
        title.setObjectName("Title")
        v.addWidget(title)
        row = QHBoxLayout()
        add_btn = QPushButton("+ Agregar diana")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self._add_target)
        remove_btn = QPushButton("Quitar seleccionada")
        remove_btn.clicked.connect(self._remove_target)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addStretch(1)
        v.addLayout(row)
        self.targets_table = QTableWidget(0, 4)
        self.targets_table.setHorizontalHeaderLabels(["ID", "Fuente", "Cadenas", "Caja"])
        v.addWidget(self.targets_table, 1)
        self.stack.addWidget(w)

    def _refresh_dianas(self) -> None:
        p = self._project()
        self.targets_table.setRowCount(0)
        if not p:
            return
        for t in p["targets"]:
            r = self.targets_table.rowCount()
            self.targets_table.insertRow(r)
            box = t.get("box", {})
            self.targets_table.setItem(r, 0, QTableWidgetItem(t["id"]))
            self.targets_table.setItem(r, 1, QTableWidgetItem(t["source"]))
            self.targets_table.setItem(r, 2, QTableWidgetItem(str(t.get("chains", "auto"))))
            self.targets_table.setItem(r, 3, QTableWidgetItem(box.get("mode", "auto")))

    def _add_target(self) -> None:
        p = self._project()
        if p is None:
            QMessageBox.information(self, "Sin proyecto", "Abre o crea un proyecto primero.")
            return
        dlg = AgregarDianaDialog(self)
        if dlg.exec() and dlg.result_target:
            if any(t["id"] == dlg.result_target["id"] for t in p["targets"]):
                QMessageBox.warning(self, "ID repetido", "Ya hay una diana con ese nombre corto.")
                return
            t = dlg.result_target
            if t["source"] == "file":
                self._materializar_archivo_local(L.Layout(self.state.project).receptors_raw_dir(), t)
            p["targets"].append(t)
            self._save(p)

    def _remove_target(self) -> None:
        p = self._project()
        row = self.targets_table.currentRow()
        if p is None or row < 0:
            return
        del p["targets"][row]
        self._save(p)

    # ---------------------------------------------------------------- Ligandos
    def _build_ligandos_page(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Ligandos y controles")
        title.setObjectName("Title")
        v.addWidget(title)
        row = QHBoxLayout()
        add_lig = QPushButton("+ Agregar ligando")
        add_lig.setObjectName("Primary")
        add_lig.clicked.connect(lambda: self._add_ligand("ligands"))
        add_ctrl = QPushButton("+ Agregar control")
        add_ctrl.clicked.connect(lambda: self._add_ligand("controls"))
        remove_btn = QPushButton("Quitar seleccionado")
        remove_btn.clicked.connect(self._remove_ligand)
        row.addWidget(add_lig)
        row.addWidget(add_ctrl)
        row.addWidget(remove_btn)
        row.addStretch(1)
        v.addLayout(row)
        self.ligands_table = QTableWidget(0, 3)
        self.ligands_table.setHorizontalHeaderLabels(["ID", "Fuente", "Tipo"])
        v.addWidget(self.ligands_table, 1)
        self.stack.addWidget(w)

    def _refresh_ligandos(self) -> None:
        p = self._project()
        self.ligands_table.setRowCount(0)
        if not p:
            return
        for kind, items in (("ligando", p["ligands"]), ("control", p["controls"])):
            for lig in items:
                r = self.ligands_table.rowCount()
                self.ligands_table.insertRow(r)
                self.ligands_table.setItem(r, 0, QTableWidgetItem(lig["id"]))
                self.ligands_table.setItem(r, 1, QTableWidgetItem(lig["source"]))
                self.ligands_table.setItem(r, 2, QTableWidgetItem(kind))

    def _add_ligand(self, bucket: str) -> None:
        p = self._project()
        if p is None:
            QMessageBox.information(self, "Sin proyecto", "Abre o crea un proyecto primero.")
            return
        dlg = AgregarLigandoDialog(self)
        if dlg.exec() and dlg.result_ligand:
            if any(x["id"] == dlg.result_ligand["id"] for x in p["ligands"] + p["controls"]):
                QMessageBox.warning(self, "ID repetido", "Ya hay un ligando/control con ese nombre corto.")
                return
            lig = dlg.result_ligand
            if lig["source"] == "file":
                lay = L.Layout(self.state.project)
                carpeta = lay.controls_dir() if bucket == "controls" else lay.ligands_dir()
                self._materializar_archivo_local(carpeta, lig)
            p[bucket].append(lig)
            self._save(p)

    def _remove_ligand(self) -> None:
        p = self._project()
        row = self.ligands_table.currentRow()
        if p is None or row < 0:
            return
        n_ligands = len(p["ligands"])
        if row < n_ligands:
            del p["ligands"][row]
        else:
            del p["controls"][row - n_ligands]
        self._save(p)

    # ---------------------------------------------------------------- Caja
    def _build_caja_page(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Caja de docking")
        title.setObjectName("Title")
        v.addWidget(title)
        self.box_target = QComboBox()
        self.box_target.currentIndexChanged.connect(self._load_box_for_selected)
        v.addWidget(self.box_target)

        form = QFormLayout()
        self.box_mode = QComboBox()
        for mode, label in (("auto", "Automático (ligando si hay, si no ciego)"), ("ligand", "Ligando de referencia"),
                            ("residues", "Residuos del sitio"), ("blind", "Ciego (proteína completa)"),
                            ("manual", "Coordenadas manuales")):
            self.box_mode.addItem(label, mode)
        form.addRow("Modo", self.box_mode)
        self.box_margin = QDoubleSpinBox()
        self.box_margin.setRange(0, 60)
        self.box_margin.setValue(10)
        form.addRow("Margen (Å)", self.box_margin)
        self.box_residues = QLineEdit()
        self.box_residues.setPlaceholderText("A:145, A:146, 203")
        form.addRow("Residuos (si aplica)", self.box_residues)
        v.addLayout(form)

        save_btn = QPushButton("Guardar caja")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save_box)
        v.addWidget(save_btn)
        v.addStretch(1)
        self.stack.addWidget(w)

    def _refresh_caja(self) -> None:
        p = self._project()
        self.box_target.clear()
        if not p:
            return
        for t in p["targets"]:
            self.box_target.addItem(t["id"], t["id"])
        self._load_box_for_selected()

    def _load_box_for_selected(self) -> None:
        p = self._project()
        tid = self.box_target.currentData()
        if not p or not tid:
            return
        t = next((x for x in p["targets"] if x["id"] == tid), None)
        if not t:
            return
        box = t.get("box", {})
        idx = self.box_mode.findData(box.get("mode", "auto"))
        self.box_mode.setCurrentIndex(max(0, idx))
        self.box_margin.setValue(box.get("margin", 10) or 10)
        self.box_residues.setText(str(box.get("residues", "") or ""))

    def _save_box(self) -> None:
        p = self._project()
        tid = self.box_target.currentData()
        if not p or not tid:
            return
        t = next((x for x in p["targets"] if x["id"] == tid), None)
        if not t:
            return
        box = {"mode": self.box_mode.currentData(), "margin": self.box_margin.value()}
        if self.box_mode.currentData() == "residues":
            box["residues"] = self.box_residues.text().strip()
        t["box"] = box
        self._save(p)

    # ---------------------------------------------------------------- Parámetros
    def _build_parametros_page(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Parámetros de docking")
        title.setObjectName("Title")
        v.addWidget(title)
        form = QFormLayout()
        self.seeds = QLineEdit()
        self.seeds.setPlaceholderText("42, 2026, 777")
        form.addRow("Semillas", self.seeds)
        self.exhaustiveness = QSpinBox()
        self.exhaustiveness.setRange(1, 128)
        form.addRow("Exhaustiveness", self.exhaustiveness)
        self.num_modes = QSpinBox()
        self.num_modes.setRange(1, 50)
        form.addRow("Poses (num_modes)", self.num_modes)
        self.energy_range = QSpinBox()
        self.energy_range.setRange(1, 20)
        form.addRow("Rango de energía", self.energy_range)
        v.addLayout(form)
        v.addWidget(self._build_consenso_box())
        note = QLabel("El límite de núcleos (CPU) lo controla el perfil de cómputo, en la pestaña Entorno.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        save_btn = QPushButton("Guardar parámetros")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save_params)
        v.addWidget(save_btn)
        v.addStretch(1)
        self.stack.addWidget(w)

    def _build_consenso_box(self) -> QGroupBox:
        box = QGroupBox("Modo avanzado · consenso entre motores")
        v = QVBoxLayout(box)
        self.cons_on = QCheckBox("Activar consenso (varios motores + ECR)")
        self.cons_on.setToolTip("Corre más de un motor de docking sobre los mismos pares y compara sus resultados.")
        self.cons_on.toggled.connect(self._cons_toggled)
        v.addWidget(self.cons_on)
        desc = QLabel("Un ligando es un candidato más fiable si motores con funciones de puntuación distintas "
                      "coinciden. Se combinan los rangos con ECR (Exponential Consensus Ranking) y se compara la "
                      "pose entre motores.")
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        v.addWidget(desc)
        self.cons_vina = QCheckBox("Vina (el motor principal del proyecto; siempre incluido)")
        self.cons_vina.setChecked(True)
        self.cons_vina.setEnabled(False)
        self.cons_vinardo = QCheckBox("Vinardo (smina con otra función de puntuación)")
        self.cons_ad4 = QCheckBox("AutoDock4 (requiere ADFRsuite; el más lento)")
        for c in (self.cons_vina, self.cons_vinardo, self.cons_ad4):
            c.toggled.connect(self._cons_update_estimate)
            v.addWidget(c)
        self.cons_estimate = QLabel("")
        self.cons_estimate.setObjectName("Muted")
        self.cons_estimate.setWordWrap(True)
        v.addWidget(self.cons_estimate)
        self._cons_loading = False
        return box

    def _cons_engines(self) -> list[str]:
        return [m for m, c in (("vina", self.cons_vina), ("vinardo", self.cons_vinardo), ("ad4", self.cons_ad4))
                if c.isChecked()]

    def _cons_update_estimate(self, *_a) -> None:
        p = self._project()
        on = self.cons_on.isChecked()
        for c in (self.cons_vinardo, self.cons_ad4):
            c.setEnabled(on)
        if not p or not on:
            self.cons_estimate.setText("Desactivado: el pipeline corre sólo el motor principal.")
            return
        pares, semillas = K.pares_del_proyecto(p), len(p["docking"].get("seeds") or [1])
        extra = K.corridas_extra(pares, semillas, self._cons_engines())
        total = sum(extra.values())
        if not total:
            self.cons_estimate.setText("Marca al menos un motor además de Vina para poder comparar.")
            return
        detalle = ", ".join(f"{K.nombre_motor(m)}: {n}" for m, n in extra.items())
        self.cons_estimate.setText(
            f"Se añaden {total} corridas de docking ({detalle}), más el redocking de cada motor. Tarda "
            "bastante más y usa más CPU y disco; AutoDock4 suele ser el más lento. Al terminar, el reporte "
            "incluye una sección que muestra las variaciones entre motores.")

    def _cons_toggled(self, on: bool) -> None:
        if on and not self._cons_loading:
            r = QMessageBox.question(
                self, "Activar el consenso",
                "El consenso corre varios motores de docking sobre los mismos pares ligando–diana.\n\n"
                "• Tarda más (cada motor extra repite todas las corridas).\n"
                "• Usa más CPU, más disco y, con AutoDock4, mucho más tiempo.\n\n¿Activarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                self.cons_on.blockSignals(True)
                self.cons_on.setChecked(False)
                self.cons_on.blockSignals(False)
        self._cons_update_estimate()

    def _refresh_parametros(self) -> None:
        p = self._project()
        if not p:
            return
        d = p["docking"]
        self.seeds.setText(", ".join(str(s) for s in d.get("seeds", [])))
        self.exhaustiveness.setValue(d.get("exhaustiveness", 32))
        self.num_modes.setValue(d.get("num_modes", 9))
        self.energy_range.setValue(d.get("energy_range", 4))
        c = d.get("consensus") or {}
        motores = c.get("engines") or K.DEFAULT_ENGINES
        self._cons_loading = True
        self.cons_on.setChecked(bool(c.get("enabled")))
        self.cons_vinardo.setChecked("vinardo" in motores)
        self.cons_ad4.setChecked("ad4" in motores)
        self._cons_loading = False
        self._cons_update_estimate()

    def _save_params(self) -> None:
        p = self._project()
        if not p:
            return
        try:
            seeds = [int(s.strip()) for s in self.seeds.text().split(",") if s.strip()]
        except ValueError:
            QMessageBox.warning(self, "Semillas inválidas", "Las semillas deben ser números separados por coma.")
            return
        p["docking"]["seeds"] = seeds or [42]
        p["docking"]["exhaustiveness"] = self.exhaustiveness.value()
        p["docking"]["num_modes"] = self.num_modes.value()
        p["docking"]["energy_range"] = self.energy_range.value()
        p["docking"]["consensus"] = {"enabled": self.cons_on.isChecked(), "engines": self._cons_engines()}
        self._save(p)
