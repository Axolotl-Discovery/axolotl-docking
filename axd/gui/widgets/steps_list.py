"""Lista de pasos de la corrida (pestaña Proceso), como una lista de cosas por hacer:

  ☐  pendiente           ◷  en curso (con su hora de inicio)
  ✔  verde: completado   ✘  rojo: falló o se interrumpió  +  ⓘ  ver el reporte del error

Lee el estado que escribe el pipeline (axd.runner.estado_pasos ← 04_Docking/logs/steps.json)."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QGridLayout, QLabel, QPlainTextEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from ... import resultados as RES
from ... import runner as R
from .. import icons, theme

ICONO = {"pendiente": "step-pending", "en_curso": "step-running", "ok": "step-ok", "error": "step-error",
         "interrumpido": "step-error", "no_ejecutado": "step-skip"}
TEXTO_ESTADO = {"pendiente": "pendiente", "en_curso": "en curso", "ok": "completado", "error": "falló",
                "interrumpido": "interrumpido", "no_ejecutado": "no se ejecutó"}


def _duracion(seg):
    if seg is None:
        return ""
    seg = float(seg)
    if seg < 60:
        return f"{seg:.0f} s"
    if seg < 3600:
        return f"{seg / 60:.1f} min"
    return f"{seg / 3600:.1f} h"


def filas(data, pasos_planeados):
    """Normaliza a [{id, titulo, estado, detalle, errores}] para pintar. Sin corrida
    previa, los pasos planeados del proyecto aparecen como pendientes. Con una
    corrida terminada, un paso que nunca arrancó (p. ej. porque el anterior falló y
    el pipeline se detuvo) aparece como 'no se ejecutó'."""
    if not data:
        return [{"id": p, "titulo": R.DESCRIPCION_PASOS.get(p, p), "estado": "pendiente", "detalle": "",
                 "errores": []} for p in pasos_planeados]
    out = []
    terminado = data.get("terminado") or not data.get("vivo")
    for p in data.get("pasos", []):
        est = p.get("estado", "pendiente")
        if est == "pendiente" and terminado:
            est = "no_ejecutado"
        det = ""
        if est == "en_curso" and p.get("inicio"):
            det = f"desde {p['inicio']}"
        elif est in ("ok", "error") and p.get("segundos") is not None:
            det = _duracion(p["segundos"]) + (f" · {p['fallos']} problema(s)" if p.get("fallos") else "")
        out.append({"id": p["id"], "titulo": p.get("titulo") or p["id"], "estado": est, "detalle": det,
                    "errores": p.get("errores", [])})
    return out


class ErrorDialog(QDialog):
    def __init__(self, titulo, errores, log, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reporte del error")
        self.resize(760, 420)
        v = QVBoxLayout(self)
        t = QLabel(titulo)
        f = QFont(t.font())
        f.setBold(True)
        t.setFont(f)
        t.setWordWrap(True)
        v.addWidget(t)
        self.text = QPlainTextEdit("\n".join(errores) or "No se registraron detalles del error.")
        self.text.setReadOnly(True)
        self.text.setStyleSheet("font-family: Menlo, Consolas, 'DejaVu Sans Mono', monospace;")
        v.addWidget(self.text, 1)
        botones = QDialogButtonBox()
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        botones.addButton(cerrar, QDialogButtonBox.ButtonRole.RejectRole)
        copiar = QPushButton("Copiar")
        copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        botones.addButton(copiar, QDialogButtonBox.ButtonRole.ActionRole)
        if log and os.path.exists(log):
            ver = QPushButton("Abrir log completo")
            ver.clicked.connect(lambda: RES.abrir_en_windows(log))
            botones.addButton(ver, QDialogButtonBox.ButtonRole.ActionRole)
        v.addWidget(botones)


class StepsList(QFrame):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("StepsList")
        self.state = state
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(14, 10, 14, 10)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self._log = None

    def _clear(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()

    def refresh(self, proy, pasos_planeados) -> None:
        self._clear()
        if not proy:
            return
        data = R.estado_pasos(proy)
        self._log = (data or {}).get("log")
        t = theme.tokens_for(self.state.theme)
        color = {"pendiente": t["text_secondary"], "en_curso": t["accent"], "ok": t["success"],
                 "error": t["error"], "interrumpido": t["error"], "no_ejecutado": t["muted"]}
        for i, f in enumerate(filas(data, pasos_planeados)):
            est = f["estado"]
            ic = QLabel()
            ic.setPixmap(icons.pixmap(ICONO[est], color[est], 20))
            ic.setToolTip(TEXTO_ESTADO[est])
            ic.setAccessibleName(f"{f['titulo']}: {TEXTO_ESTADO[est]}")
            self.grid.addWidget(ic, i, 0)
            titulo = QLabel(f"{i + 1}. {f['titulo']}")
            if est in ("pendiente", "no_ejecutado"):
                titulo.setObjectName("Muted")
            self.grid.addWidget(titulo, i, 1)
            det = QLabel(f["detalle"] or TEXTO_ESTADO[est])
            det.setObjectName("Muted")
            self.grid.addWidget(det, i, 2)
            if est in ("error", "interrumpido"):
                b = QToolButton()
                b.setObjectName("InfoButton")
                b.setIcon(icons.icon("info", t["error"]))
                b.setIconSize(QSize(18, 18))
                b.setToolTip("Ver el reporte del error")
                b.setAccessibleName(f"Ver el reporte del error de: {f['titulo']}")
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c=False, ff=f: ErrorDialog(ff["titulo"], ff["errores"], self._log,
                                                                     self).exec())
                self.grid.addWidget(b, i, 3)
