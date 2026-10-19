"""Pestaña 'Proceso': lanzar/detener/reanudar el pipeline real (axd.runner),
con barra de progreso en cortes de 10% y checkpoints automáticos."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from ... import config as C
from ... import runner as R
from ..dialogs.calibracion_dialog import CalibracionDialog
from ..dialogs.restaurar_checkpoint_dialog import RestaurarCheckpointDialog
from ..services import calibration, checkpoints as CK, compute_profile


class ProcesoTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._calibration_offered = False
        self.state.project_changed.connect(self._on_project_changed)
        self.state.job_state_changed.connect(self._on_job_state)

        layout = QVBoxLayout(self)
        title = QLabel("Proceso")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.status_label = QLabel("Abrí un proyecto para ver su avance.")
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.eta_label = QLabel("")
        self.eta_label.setObjectName("Muted")
        layout.addWidget(self.eta_label)

        row = QHBoxLayout()
        self.run_btn = QPushButton("▶ Correr pipeline")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        self.resume_btn = QPushButton("↻ Reanudar")
        self.resume_btn.clicked.connect(self._resume)
        self.stop_btn = QPushButton("■ Detener")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.run_btn)
        row.addWidget(self.resume_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        layout.addLayout(row)

        ck_row = QHBoxLayout()
        ck_label = QLabel("Checkpoints automáticos")
        ck_label.setObjectName("Title")
        ck_row.addWidget(ck_label)
        ck_row.addStretch(1)
        manual_ck = QPushButton("+ Guardar ahora")
        manual_ck.clicked.connect(self._manual_checkpoint)
        ver_todos = QPushButton("Ver todos / restaurar ↗")
        ver_todos.clicked.connect(self._open_checkpoints)
        ck_row.addWidget(manual_ck)
        ck_row.addWidget(ver_todos)
        layout.addLayout(ck_row)

        self.checkpoints_list = QListWidget()
        self.checkpoints_list.setMaximumHeight(140)
        layout.addWidget(self.checkpoints_list)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self._tick)
        self._poll_timer.start()

        self._set_controls_enabled(False)
        self.refresh()

    # ---------------------------------------------------------------- helpers
    def _project(self):
        return self.state.project

    def _set_controls_enabled(self, enabled: bool) -> None:
        for b in (self.run_btn, self.resume_btn, self.stop_btn):
            b.setEnabled(enabled)

    def _on_project_changed(self, path: str) -> None:
        self._set_controls_enabled(bool(path))
        if path and calibration.needs_calibration() and not self._calibration_offered:
            self._calibration_offered = True
            CalibracionDialog(self).exec()
        self.refresh()

    def _on_job_state(self, _state) -> None:
        self.refresh()

    def _tick(self) -> None:
        proy = self._project()
        if proy:
            e = R.estado(proy)
            if e and e.get("vivo"):
                CK.maybe_checkpoint(proy)
        self.refresh()

    # ---------------------------------------------------------------- acciones
    def _run(self) -> None:
        proy = self._project()
        if not proy:
            return
        p = C.load_project(proy)
        if not p["targets"]:
            QMessageBox.warning(self, "Falta configurar", "Agregá al menos una diana en Análisis.")
            return
        if not p["ligands"] and not p["controls"]:
            QMessageBox.warning(self, "Falta configurar", "Agregá al menos un ligando en Análisis.")
            return
        p["docking"] = compute_profile.apply_to_docking_params(p["docking"])
        C.save_project(proy, p)
        hay_ref = any(d.get("box", {}).get("mode") in ("ligand", "auto") for d in p["targets"])
        pasos = [x for x in R.PASOS if x != "redocking" or hay_ref]
        R.ejecutar(proy, pasos, fondo=True)
        self.refresh()

    def _resume(self) -> None:
        proy = self._project()
        if proy:
            R.reanudar(proy)
            self.refresh()

    def _stop(self) -> None:
        proy = self._project()
        if proy and R.detener(proy):
            self.refresh()

    def _manual_checkpoint(self) -> None:
        proy = self._project()
        if proy:
            CK.manual_checkpoint(proy)
            self._refresh_checkpoints()

    def _open_checkpoints(self) -> None:
        proy = self._project()
        if proy:
            RestaurarCheckpointDialog(proy, self).exec()
            self._refresh_checkpoints()

    # ---------------------------------------------------------------- refresco
    def refresh(self) -> None:
        proy = self._project()
        if not proy:
            self.status_label.setText("Abrí un proyecto para ver su avance.")
            self.progress.setValue(0)
            self.eta_label.setText("")
            self.checkpoints_list.clear()
            return
        e = R.estado(proy)
        done, total = CK.progress_fraction(proy)
        pct = int(100 * done / total) if total else 0
        self.progress.setValue(pct)
        if e and e.get("vivo"):
            self.status_label.setText(f"Corriendo (PID {e['pid']}) · {', '.join(e['pasos'])} · desde {e['inicio']}")
            self.resume_btn.setEnabled(False)
        elif e:
            self.status_label.setText(f"Último trabajo ({', '.join(e['pasos'])}) ya no está corriendo.")
            self.resume_btn.setEnabled(True)
        else:
            self.status_label.setText("No hay trabajo corriendo.")
            self.resume_btn.setEnabled(True)
        self._update_eta(proy, done, total, running=bool(e and e.get("vivo")))
        self._refresh_checkpoints()

    def _update_eta(self, proy, done, total, running: bool) -> None:
        if total == 0:
            self.eta_label.setText("El proyecto aún no tiene dianas/ligandos configurados.")
            return
        if done >= total:
            self.eta_label.setText("Completo.")
            return
        p = C.load_project(proy)
        profile = compute_profile.load()
        remaining = total - done
        if not running:
            seconds = calibration.estimate_seconds(remaining, p["docking"].get("exhaustiveness", 32),
                                                     parallel_jobs=profile.effective_cores())
            self.eta_label.setText(f"Estimado inicial (sin corridas aún): ~{_fmt_seconds(seconds)} "
                                    f"· perfil {profile.kind} ({profile.percent}%)")
        else:
            self.eta_label.setText(f"{done}/{total} corridas — el tiempo restante real se ve en el log "
                                    f"(se afina con el avance).")

    def _refresh_checkpoints(self) -> None:
        proy = self._project()
        self.checkpoints_list.clear()
        if not proy:
            return
        for cp in CK.list_checkpoints(proy)[:5]:
            self.checkpoints_list.addItem(QListWidgetItem(
                f"{cp.created_at}  ·  {cp.label}  ·  {cp.pct}%"))


def _fmt_seconds(seconds: float) -> str:
    if seconds > 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 60:.0f} min"
