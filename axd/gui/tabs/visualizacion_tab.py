"""Pestaña 'Visualización': complejos proteína + ligando (paso 'interactions' del
pipeline) y dianas ya preparadas (receptor + caja), con el detalle de cada una
(interacciones o caja) y apertura en PyMOL del entorno conda
(axd.resultados.abrir_pymol, reutilizado tal cual).

Si no hay nada que mostrar, explica qué paso falta en vez de quedar en blanco."""
from __future__ import annotations

import csv
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ... import config as C
from ... import resultados as RES
from ...layout import Layout
from ..widgets.mol_viewer import MolViewer

ROLE = Qt.ItemDataRole.UserRole


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _read_interactions(path):
    """{(diana, ligando): [fila, ...]} desde 05_Analysis/interactions_detail.csv."""
    out = {}
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                out.setdefault((row.get("diana", ""), row.get("ligando", "")), []).append(row)
    except OSError:
        pass
    return out


def collect(proy):
    """Lo que la pestaña puede mostrar de un proyecto, sin Qt (para poder probarlo).

    Devuelve dict con:
      complexes: [{target, ligand, path, interactions}]
      targets:   [{id, path, box}]  (dianas con receptor preparado)
      hint:      texto que explica qué falta, o "" si hay algo que ver."""
    try:
        p = C.load_project(proy)
    except (OSError, ValueError):
        return {"complexes": [], "targets": [], "hint": "No pude leer el proyecto (axd.json)."}
    lay = Layout(proy)
    boxes = _read_json(lay.boxes_json())
    inter = _read_interactions(lay.interactions_detail_csv())

    targets, complexes = [], []
    lig_ids = [l["id"] for l in p.get("ligands", [])]
    for t in p.get("targets", []):
        tid = t["id"]
        rec = next((f for f in (lay.receptor_clean(tid), lay.receptor_pdbqt(tid)) if os.path.isfile(f)), None)
        if rec and tid in boxes:
            targets.append({"id": tid, "path": rec, "box": boxes[tid]})
        ctrl_ids = [c["id"] for c in p.get("controls", []) if not c.get("target") or c.get("target") == tid]
        for lid in lig_ids + ctrl_ids:
            f = lay.complex_pdb(tid, lid)
            if os.path.isfile(f):
                complexes.append({"target": tid, "ligand": lid, "path": f,
                                  "interactions": inter.get((tid, lid), [])})

    hint = ""
    if not p.get("targets"):
        hint = "Este proyecto aún no tiene dianas. Agrégalas en Análisis → Dianas."
    elif not targets and not complexes:
        hint = ("Ninguna diana tiene todavía receptor y caja preparados. Corre el proceso desde la pestaña "
                "Proceso (paso 2, receptores); si ya lo corriste, revisa las líneas con ✘ del log.")
    elif not complexes:
        hint = ("Aún no hay complejos proteína–ligando: aparecen después de docking, resumen e interacciones "
                "(pasos 5–7). Mientras tanto puedes abrir los receptores preparados.")
    return {"complexes": complexes, "targets": targets, "hint": hint}


def _fmt_box(box):
    c, s = box.get("center"), box.get("size")
    partes = [f"Modo: {box.get('mode', '?')}"]
    if c:
        partes.append("Centro: " + ", ".join(f"{v:.1f}" for v in c))
    if s:
        partes.append("Tamaño: " + " × ".join(f"{v:.0f}" for v in s) + " Å")
    if box.get("detail"):
        partes.append(str(box["detail"]))
    return partes


def _fmt_interaction(row):
    d = row.get("distancia", "")
    try:
        d = f"{float(d):.1f} Å"
    except ValueError:
        pass
    return f"{row.get('tipo', '?')} · {row.get('residuo', '')}{row.get('cadena', '')} · {d}".strip(" ·")


class VisualizacionTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.project_changed.connect(lambda _p: self.refresh())
        self.state.job_state_changed.connect(self._on_job_state)
        self._shown_path = None

        layout = QVBoxLayout(self)
        title = QLabel("Visualización")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setSpacing(3)
        self.list.setMinimumWidth(260)
        self.list.setMaximumWidth(380)
        self.list.currentItemChanged.connect(lambda *_: self._show_detail())
        body.addWidget(self.list)

        self.viewer = MolViewer(theme=getattr(state, "theme", "dark"), figures_dir_fn=self._figures_dir)
        self.state.theme_changed.connect(self.viewer.set_theme)
        body.addWidget(self.viewer, 3)

        self.side = QWidget()
        self.side.setFixedWidth(300)
        side = QVBoxLayout(self.side)
        side.setContentsMargins(12, 0, 0, 0)
        self.detail_title = QLabel()
        bold = QFont(self.detail_title.font())
        bold.setBold(True)
        bold.setPointSizeF(bold.pointSizeF() * 1.15)
        self.detail_title.setFont(bold)
        self.detail_title.setWordWrap(True)
        side.addWidget(self.detail_title)
        self.detail_sub = QLabel()
        self.detail_sub.setObjectName("Muted")
        self.detail_sub.setWordWrap(True)
        side.addWidget(self.detail_sub)
        self.detail = QListWidget()
        self.detail.setSpacing(2)
        side.addWidget(self.detail, 1)
        body.addWidget(self.side)
        layout.addLayout(body, 1)

        row = QHBoxLayout()
        self.open_btn = QPushButton("Abrir en PyMOL")
        self.open_btn.setObjectName("Primary")
        self.open_btn.clicked.connect(self._open_pymol)
        self.folder_btn = QPushButton("Mostrar carpeta")
        self.folder_btn.clicked.connect(self._open_folder)
        row.addWidget(self.open_btn)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.refresh()

    # ---------------------------------------------------------------- datos
    def showEvent(self, event):  # noqa: N802 — al entrar a la pestaña se ve lo último del disco
        super().showEvent(event)
        self.refresh()

    def _on_job_state(self, st) -> None:
        if not st or not st.get("vivo"):
            self.refresh()

    def _header(self, text):
        item = QListWidgetItem(text.upper())
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = QFont(self.list.font())
        font.setBold(True)
        font.setPointSizeF(max(7.0, font.pointSizeF() * 0.85))
        item.setFont(font)
        item.setForeground(QBrush(QColor("#9A9A9A")))
        self.list.addItem(item)

    def refresh(self) -> None:
        prev = self._selected()
        prev_path = prev["path"] if prev else None
        self.list.clear()
        proy = self.state.project
        data = collect(proy) if proy else {"complexes": [], "targets": [], "hint": "Abre un proyecto para ver sus complejos."}
        self.hint.setText(data["hint"])
        self.hint.setVisible(bool(data["hint"]))

        if data["complexes"]:
            self._header("Complejos")
            for c in data["complexes"]:
                n = len(c["interactions"])
                item = QListWidgetItem(f"{c['target']}  +  {c['ligand']}" + (f"   ·  {n} contactos" if n else ""))
                item.setData(ROLE, {"kind": "complex", **c})
                self.list.addItem(item)
        if data["targets"]:
            self._header("Dianas preparadas (receptor + caja)")
            for t in data["targets"]:
                item = QListWidgetItem(f"{t['id']}  ·  {t['box'].get('mode', '?')}")
                item.setData(ROLE, {"kind": "target", **t})
                self.list.addItem(item)

        sel = next((i for i in range(self.list.count())
                    if prev_path and (self.list.item(i).data(ROLE) or {}).get("path") == prev_path), None)
        if sel is None:
            sel = next((i for i in range(self.list.count()) if self.list.item(i).data(ROLE)), None)
        if sel is not None:
            self.list.setCurrentRow(sel)
        self._show_detail()

    def _selected(self):
        item = self.list.currentItem()
        return item.data(ROLE) if item else None

    def _show_detail(self) -> None:
        d = self._selected()
        self.detail.clear()
        self.open_btn.setVisible(bool(d))
        self.folder_btn.setVisible(bool(d))
        self.side.setVisible(bool(d))
        self.list.setVisible(self.list.count() > 0)
        self.viewer.setVisible(bool(d))
        self._update_viewer(d)
        if not d:
            self.detail_title.setText("")
            self.detail_sub.setText("")
            return
        if d["kind"] == "complex":
            self.detail_title.setText(f"Interacciones · {d['target']} + {d['ligand']}")
            rows = d["interactions"]
            self.detail_sub.setText(f"{len(rows)} contactos" if rows else
                                    "Sin tabla de interacciones para este complejo (paso 7).")
            for r in rows:
                self.detail.addItem(_fmt_interaction(r))
        else:
            self.detail_title.setText(f"Caja de docking · {d['id']}")
            self.detail_sub.setText(os.path.basename(d["path"]))
            for linea in _fmt_box(d["box"]):
                self.detail.addItem(linea)

    def _figures_dir(self) -> str:
        return Layout(self.state.project).figures_dir() if self.state.project else ""

    def _update_viewer(self, d) -> None:
        """Carga en el visor 3D lo seleccionado; no recarga si es lo mismo (el
        refresh periódico no debe reiniciar la cámara)."""
        key = (d["kind"], d["path"], len(d.get("interactions", []))) if d else None
        if key == self._shown_path:
            return
        self._shown_path = key
        if not d:
            self.viewer.clear()
        elif d["kind"] == "complex":
            self.viewer.show_complex(d["path"], d["interactions"], name=f"{d['target']}__{d['ligand']}")
        else:
            ref = Layout(self.state.project).ref_pdb(d["id"]) if self.state.project else None
            self.viewer.show_target(d["path"], d["box"], ref, name=d["id"])

    # ---------------------------------------------------------------- acciones
    def _open_pymol(self) -> None:
        d = self._selected()
        if not d:
            QMessageBox.information(self, "Elige un elemento", "Selecciona un complejo o una diana de la lista.")
            return
        RES.abrir_pymol(d["path"])

    def _open_folder(self) -> None:
        d = self._selected()
        if d:
            RES.abrir_en_windows(os.path.dirname(d["path"]))
