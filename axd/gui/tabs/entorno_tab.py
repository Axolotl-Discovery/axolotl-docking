"""Pestaña 'Entorno': dispositivo de ejecución (CPU/GPU), estado real de conda (axd.config/axd.entorno), ruta
manual, selector de entorno conda, perfil de cómputo, calibración de
dispositivo y actualizaciones."""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from ... import config as C
from ... import entorno as ENT
from ..dialogs.calibracion_dialog import CalibracionDialog
from ..services import calibration, compute_profile, updater
from ..widgets.device_panel import DevicePanel


class _UpdateWorkerSignals(QObject):
    done = Signal(bool, str)


class EntornoTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        root.addWidget(scroll)
        outer = QVBoxLayout(body)
        title = QLabel("Entorno")
        title.setObjectName("Title")
        outer.addWidget(title)

        # ---- dispositivo de ejecución (CPU / GPU)
        self.device_panel = DevicePanel(state)
        outer.addWidget(self.device_panel)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        outer.addWidget(sep)

        # ---- conda
        self.conda_status = QLabel("")
        outer.addWidget(self.conda_status)

        conda_row = QHBoxLayout()
        self.conda_path_edit = QLineEdit()
        self.conda_path_edit.setPlaceholderText("Ruta a la instalación de conda/miniforge")
        browse = QPushButton("Elegir carpeta…")
        browse.clicked.connect(self._browse_conda)
        save_path = QPushButton("Validar y guardar")
        save_path.setObjectName("Primary")
        save_path.clicked.connect(self._save_conda_path)
        conda_row.addWidget(self.conda_path_edit, 1)
        conda_row.addWidget(browse)
        conda_row.addWidget(save_path)
        outer.addLayout(conda_row)

        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("Entorno conda:"))
        self.env_combo = QComboBox()
        env_row.addWidget(self.env_combo, 1)
        use_env = QPushButton("Usar este")
        use_env.clicked.connect(self._use_selected_env)
        env_row.addWidget(use_env)
        outer.addLayout(env_row)

        verify_row = QHBoxLayout()
        verify_btn = QPushButton("Verificar entorno (doctor)")
        verify_btn.clicked.connect(self._run_doctor)
        verify_row.addWidget(verify_btn)
        verify_row.addStretch(1)
        outer.addLayout(verify_row)
        self.doctor_output = QLabel("")
        self.doctor_output.setWordWrap(True)
        self.doctor_output.setObjectName("Muted")
        outer.addWidget(self.doctor_output)

        # ---- reporte PDF (logos y datos del laboratorio)
        rep_title = QLabel("Reporte")
        rep_title.setObjectName("Title")
        outer.addWidget(rep_title)
        rep_note = QLabel("Aparecen en la portada y el pie de cada reporte PDF. El logo puede ser PNG o JPG.")
        rep_note.setObjectName("Muted")
        outer.addWidget(rep_note)
        rep_form = QFormLayout()
        self.rep_lab = QLineEdit()
        self.rep_lab.setPlaceholderText("Nombre del laboratorio o grupo")
        rep_form.addRow("Laboratorio", self.rep_lab)
        self.rep_autor = QLineEdit()
        self.rep_autor.setPlaceholderText("Persona responsable")
        rep_form.addRow("Responsable", self.rep_autor)
        logo_row = QHBoxLayout()
        self.rep_logo = QLineEdit()
        self.rep_logo.setPlaceholderText("Archivo de logo (opcional)")
        self.rep_logo.textChanged.connect(self._preview_logo)
        logo_btn = QPushButton("Elegir logo…")
        logo_btn.clicked.connect(self._browse_logo)
        logo_row.addWidget(self.rep_logo, 1)
        logo_row.addWidget(logo_btn)
        rep_form.addRow("Logo", logo_row)
        self.rep_preview = QLabel("")
        self.rep_preview.setFixedHeight(64)
        rep_form.addRow("", self.rep_preview)
        outer.addLayout(rep_form)
        rep_save = QPushButton("Guardar datos del reporte")
        rep_save.clicked.connect(self._save_report_settings)
        rep_row = QHBoxLayout()
        rep_row.addWidget(rep_save)
        rep_row.addStretch(1)
        outer.addLayout(rep_row)

        # ---- perfil de cómputo
        perfil_title = QLabel("Perfil de cómputo")
        perfil_title.setObjectName("Title")
        outer.addWidget(perfil_title)
        form = QFormLayout()
        self.profile_kind = QComboBox()
        self.profile_kind.addItem("Estación de trabajo", compute_profile.WORKSTATION)
        self.profile_kind.addItem("Servidor", compute_profile.SERVER)
        self.profile_kind.currentIndexChanged.connect(self._on_profile_kind_changed)
        form.addRow("Tipo de máquina", self.profile_kind)
        self.profile_slider = QSlider(Qt.Orientation.Horizontal)
        self.profile_slider.setRange(1, compute_profile.HARD_MAX)
        self.profile_slider.valueChanged.connect(self._on_profile_slider_changed)
        form.addRow("% de cómputo", self.profile_slider)
        self.profile_label = QLabel("")
        form.addRow("", self.profile_label)
        outer.addLayout(form)
        self.profile_warning = QFrame()
        self.profile_warning.setObjectName("BannerWarning")
        pw_layout = QVBoxLayout(self.profile_warning)
        pw_label = QLabel("⚠ Pasado el rango recomendado puede congelar otros procesos de esta máquina.")
        pw_label.setWordWrap(True)
        pw_layout.addWidget(pw_label)
        outer.addWidget(self.profile_warning)
        save_profile = QPushButton("Guardar perfil de cómputo")
        save_profile.setObjectName("Primary")
        save_profile.clicked.connect(self._save_profile)
        outer.addWidget(save_profile)

        # ---- calibración
        cal_title = QLabel("Calibración de dispositivo")
        cal_title.setObjectName("Title")
        outer.addWidget(cal_title)
        cal_row = QHBoxLayout()
        self.cal_label = QLabel("")
        self.cal_label.setObjectName("Muted")
        cal_row.addWidget(self.cal_label, 1)
        recal_btn = QPushButton("Recalibrar")
        recal_btn.clicked.connect(self._recalibrate)
        cal_row.addWidget(recal_btn)
        outer.addLayout(cal_row)

        # ---- actualizaciones
        upd_title = QLabel("Actualizaciones")
        upd_title.setObjectName("Title")
        outer.addWidget(upd_title)
        self.version_label = QLabel(f"v{C.VERSION}")
        outer.addWidget(self.version_label)
        self.update_status = QLabel("")
        self.update_status.setObjectName("Muted")
        outer.addWidget(self.update_status)
        upd_row = QHBoxLayout()
        self.check_update_btn = QPushButton("Buscar ahora")
        self.check_update_btn.clicked.connect(self._check_update)
        self.apply_update_btn = QPushButton("Actualizar y reiniciar")
        self.apply_update_btn.setObjectName("Primary")
        self.apply_update_btn.clicked.connect(self._apply_update)
        self.apply_update_btn.hide()
        upd_row.addWidget(self.check_update_btn)
        upd_row.addWidget(self.apply_update_btn)
        upd_row.addStretch(1)
        outer.addLayout(upd_row)

        outer.addStretch(1)

        self._signals = _UpdateWorkerSignals()
        self._signals.done.connect(self._on_update_checked)
        self._pending_update = None

        self.refresh()

    # ---------------------------------------------------------------- conda
    def refresh(self) -> None:
        g = C.load_global()
        self.rep_lab.setText(g.get("reporte_laboratorio", ""))
        self.rep_autor.setText(g.get("reporte_autor", ""))
        self.rep_logo.setText(g.get("reporte_logo", ""))
        conda = C.conda_path(g)
        self.conda_path_edit.setText(conda or g.get("conda", ""))
        envs = C.conda_environments(conda) if conda else []
        if conda and g["entorno"] in envs:
            self.conda_status.setText(f"● conda: {conda}  ·  entorno activo: {g['entorno']}")
        elif conda:
            self.conda_status.setText(f"● conda encontrado en {conda}, pero el entorno '{g['entorno']}' no existe"
                                       f" (hay: {', '.join(envs) or 'ninguno'})")
        else:
            self.conda_status.setText("● conda/miniforge no encontrado — indica la ruta a mano abajo.")
        self.env_combo.clear()
        for e in [x for x in envs if x not in ("base", "miniforge3")]:
            self.env_combo.addItem(e + ("  (activo)" if e == g["entorno"] else ""), e)

        profile = compute_profile.load()
        self.profile_kind.setCurrentIndex(self.profile_kind.findData(profile.kind))
        self.profile_slider.setValue(profile.percent)
        self._update_profile_label(profile)

        cal = calibration.load_for_this_device()
        if cal:
            origin = "medida" if cal.source == "benchmark" else "genérica (no calibrada)"
            self.cal_label.setText(f"~{cal.seconds_per_job:.0f} s por corrida de referencia · estimación {origin} "
                                    f"· {cal.measured_at}")
        else:
            self.cal_label.setText("Sin calibrar todavía.")

    def _browse_logo(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Logo para el reporte", os.path.expanduser("~"),
                                           "Imágenes (*.png *.jpg *.jpeg)")
        if f:
            self.rep_logo.setText(f)

    def _preview_logo(self, path: str) -> None:
        from PySide6.QtGui import QPixmap
        p = os.path.expanduser(path.strip())
        px = QPixmap(p) if p and os.path.isfile(p) else QPixmap()
        if px.isNull():
            self.rep_preview.setText("(sin logo)" if not path.strip() else "No se pudo leer esa imagen.")
            self.rep_preview.setPixmap(QPixmap())
        else:
            self.rep_preview.setPixmap(px.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))

    def _save_report_settings(self) -> None:
        logo = self.rep_logo.text().strip()
        if logo and not os.path.isfile(os.path.expanduser(logo)):
            QMessageBox.warning(self, "Logo no encontrado", "Ese archivo de logo no existe.")
            return
        g = C.load_global()
        g.update(reporte_laboratorio=self.rep_lab.text().strip(), reporte_autor=self.rep_autor.text().strip(),
                 reporte_logo=logo)
        C.save_global(g)
        QMessageBox.information(self, "Guardado", "Los próximos reportes usarán estos datos.")

    def _browse_conda(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de conda/miniforge")
        if d:
            self.conda_path_edit.setText(d)

    def _save_conda_path(self) -> None:
        path = self.conda_path_edit.text().strip()
        if not path or not os.path.exists(os.path.join(path, "etc/profile.d/conda.sh")):
            QMessageBox.warning(self, "Ruta inválida", "Esa carpeta no parece una instalación de conda válida "
                                 "(falta etc/profile.d/conda.sh). Si pegaste una ruta de Windows, recordá que "
                                 "acá se necesita la ruta de WSL/Linux.")
            return
        g = C.load_global()
        g["conda"] = path
        C.save_global(g)
        QMessageBox.information(self, "Guardado", "Ruta de conda guardada.")
        self.refresh()

    def _use_selected_env(self) -> None:
        env = self.env_combo.currentData()
        if not env:
            return
        g = C.load_global()
        g["entorno"] = env
        C.save_global(g)
        self.refresh()
        self._run_doctor()

    def _run_doctor(self) -> None:
        self.doctor_output.setText("Verificando (≈20 s)…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        ok = ENT.doctor(reparar_preguntando=False)
        self.doctor_output.setText("Todo listo para dockear." if ok else
                                    "Hay problemas de entorno — revisá la terminal para el detalle, o corré "
                                    "'Instalar/reparar' desde el CLI (Docking entorno).")
        self.refresh()

    # ---------------------------------------------------------------- perfil de cómputo
    def _current_profile(self) -> compute_profile.ComputeProfile:
        return compute_profile.ComputeProfile(kind=self.profile_kind.currentData(),
                                               percent=self.profile_slider.value())

    def _on_profile_kind_changed(self, _i: int) -> None:
        lo, hi = compute_profile.RECOMMENDED[self.profile_kind.currentData()]
        self.profile_slider.setValue((lo + hi) // 2)
        self._update_profile_label(self._current_profile())

    def _on_profile_slider_changed(self, _v: int) -> None:
        self._update_profile_label(self._current_profile())

    def _update_profile_label(self, profile: compute_profile.ComputeProfile) -> None:
        lo, hi = profile.recommended_range
        cores = profile.effective_cores()
        self.profile_label.setText(f"{profile.percent}% · recomendado {lo}-{hi}% · ≈{cores} núcleo(s) por "
                                    f"corrida de docking")
        self.profile_warning.setVisible(profile.warns)

    def _save_profile(self) -> None:
        compute_profile.save(self._current_profile())
        QMessageBox.information(self, "Guardado", "Perfil de cómputo guardado.")

    # ---------------------------------------------------------------- calibración
    def _recalibrate(self) -> None:
        dlg = CalibracionDialog(self)
        dlg.exec()
        self.refresh()

    # ---------------------------------------------------------------- actualizaciones
    def _check_update(self) -> None:
        self.update_status.setText("Buscando…")
        self.check_update_btn.setEnabled(False)
        threading.Thread(target=self._check_update_sync, daemon=True).start()

    def _check_update_sync(self) -> None:
        check = updater.check_for_update()
        self._pending_check = check
        self._signals.done.emit(True, "check")

    def _on_update_checked(self, _ok: bool, kind: str) -> None:
        self.check_update_btn.setEnabled(True)
        check = getattr(self, "_pending_check", None)
        if check is None:
            return
        if not check.is_git_install:
            self.update_status.setText("Esta instalación no es un clon de git; no se puede auto-actualizar.")
            self.apply_update_btn.hide()
        elif check.behind_by == 0:
            self.update_status.setText(f"Estás al día (v{check.current_version}).")
            self.apply_update_btn.hide()
        else:
            self.update_status.setText(f"Hay una actualización disponible ({check.behind_by} commit(s) nuevos):\n"
                                        f"{check.remote_summary}")
            self.apply_update_btn.show()

    def _apply_update(self) -> None:
        job = self.state.job_state() if hasattr(self.state, "job_state") else None
        if job and job.get("vivo"):
            if QMessageBox.question(self, "Hay un trabajo corriendo",
                                     "Hay un trabajo de docking corriendo. Actualizar reinicia la app; el "
                                     "trabajo en segundo plano no se detiene, pero vas a tener que reabrirla "
                                     "para seguir viéndolo. ¿Continuar?") != QMessageBox.StandardButton.Yes:
                return
        ok, msg = updater.apply_update()
        if ok:
            QMessageBox.information(self, "Actualizado", f"Actualizado a v{msg}. Reiniciá la app para usar la "
                                     "nueva versión.")
        else:
            QMessageBox.warning(self, "No se pudo actualizar", msg)
        self._check_update()
