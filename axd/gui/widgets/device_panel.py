"""Panel 'Dispositivo de ejecución' (pestaña Entorno): elegir CPU o GPU para el
docking, con el equipo detectado. El icono es genérico (chip / tarjeta) y toma
el color del fabricante detectado; el fabricante y el modelo van en texto.

  CPU → smina (o AutoDock4 si hay átomos raros)      siempre disponible
  GPU → Vina-GPU 2.1 (OpenCL, NVIDIA o AMD)          si el equipo lo soporta y está instalado"""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

from ... import config as C
from ... import device as DEV
from .. import icons, theme

VENDOR_COLOR = {"intel": "#0071C5", "amd": "#E0342B", "nvidia": "#76B900", "apple": "#A0A0A0"}


def install_command() -> str:
    return f'bash "{os.path.join(C.APP, "scripts", "instalar_vina_gpu.sh")}"'


class _Card(QFrame):
    def __init__(self, kind: str, title: str):
        super().__init__()
        self.setObjectName("DeviceCard")
        self.kind = kind
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        row = QHBoxLayout()
        self.button = QToolButton()
        self.button.setObjectName("DeviceButton")
        self.button.setCheckable(True)
        self.button.setIconSize(QSize(44, 44))
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.button)
        col = QVBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("DeviceTitle")
        self.model = QLabel("")
        self.model.setWordWrap(True)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.model)
        col.addWidget(self.status)
        row.addLayout(col, 1)
        v.addLayout(row)
        self.extra = QHBoxLayout()
        v.addLayout(self.extra)


class DevicePanel(QWidget):
    device_changed = Signal(str)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._hw = None
        self.state.theme_changed.connect(lambda _t: self.refresh())

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Dispositivo de ejecución")
        title.setObjectName("Title")
        v.addWidget(title)
        note = QLabel("Dónde corre el docking. CPU usa smina; GPU usa Vina-GPU 2.1 (NVIDIA o AMD, Linux/WSL). "
                      "Un proyecto no mezcla motores: para cambiar de dispositivo con resultados ya hechos, elimina "
                      "el último procesamiento en Proceso.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)

        cards = QHBoxLayout()
        self.cpu = _Card(DEV.CPU, "CPU")
        self.gpu = _Card(DEV.GPU, "GPU")
        cards.addWidget(self.cpu, 1)
        cards.addWidget(self.gpu, 1)
        v.addLayout(cards)

        self.copy_btn = QPushButton("Copiar comando de instalación")
        self.copy_btn.clicked.connect(self._copy_command)
        self.gpu.extra.addWidget(self.copy_btn)
        self.redetect_btn = QPushButton("Volver a detectar")
        self.redetect_btn.clicked.connect(lambda: self.refresh(redetect=True))
        self.gpu.extra.addWidget(self.redetect_btn)
        self.gpu.extra.addStretch(1)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.addButton(self.cpu.button)
        self.group.addButton(self.gpu.button)
        self.cpu.button.clicked.connect(lambda: self._choose(DEV.CPU))
        self.gpu.button.clicked.connect(lambda: self._choose(DEV.GPU))

    # ---------------------------------------------------------------- datos
    def _hardware(self, redetect=False):
        if self._hw is None or redetect:
            from ... import hardware as HW
            try:
                self._hw = HW.detect()
            except Exception:  # noqa: BLE001 — la detección nunca debe tumbar la GUI
                self._hw = HW.Hardware()
        return self._hw

    def showEvent(self, event):  # noqa: N802 — detectar al mostrarse, no al arrancar la app
        super().showEvent(event)
        self.refresh()

    def refresh(self, redetect: bool = False) -> None:
        if not self.isVisible() and self._hw is None and not redetect:
            return
        hw = self._hardware(redetect)
        g = C.load_global()
        t = theme.tokens_for(self.state.theme)
        muted = t["text_secondary"]

        cvend = DEV.cpu_vendor(hw.cpu_model)
        self.cpu.button.setIcon(icons.icon("cpu", VENDOR_COLOR.get(cvend, muted), VENDOR_COLOR.get(cvend, t["accent"]), 44))
        label = DEV.VENDOR_LABEL.get(cvend, "")
        self.cpu.title.setText("CPU" + (f" · {label}" if label else ""))
        self.cpu.model.setText(f"{hw.cpu_model} · {hw.usable_cores} núcleos disponibles")
        self.cpu.status.setText("Motor: smina (AutoDock4 si hay átomos poco comunes). Siempre disponible.")

        ok, motivo, gpu = DEV.gpu_support(hw)
        gvend = getattr(gpu, "vendor", "unknown") if gpu else "unknown"
        gcolor = VENDOR_COLOR.get(gvend, muted)
        self.gpu.button.setIcon(icons.icon("gpu", gcolor, gcolor if gpu else t["accent"], 44))
        glabel = DEV.VENDOR_LABEL.get(gvend, "")
        self.gpu.title.setText("GPU" + (f" · {glabel}" if glabel else ""))
        if gpu:
            vram = f" · {gpu.vram_mb / 1024:.0f} GB" if getattr(gpu, "vram_mb", None) else ""
            self.gpu.model.setText(f"{gpu.name}{vram}")
        else:
            self.gpu.model.setText("No detectada")
        variants = DEV.vina_gpu_variants(g)
        installed = bool(variants)
        if not ok:
            self.gpu.status.setText(motivo)
        elif not installed:
            self.gpu.status.setText("Vina-GPU no está instalado. Córrelo una vez en una terminal (compila para tu "
                                    "GPU, 2–5 min; puede pedir tu contraseña para instalar dependencias):\n"
                                    + install_command())
        else:
            lim = max(DEV.BOX_LIMITS[v] for v in variants)
            self.gpu.status.setText(f"Motor: Vina-GPU 2.1 · cajas de hasta {lim:.0f} Å por lado "
                                    "(una caja mayor, p. ej. docking ciego, necesita CPU).")
        self.copy_btn.setVisible(ok and not installed)
        usable = ok and installed
        self.gpu.button.setEnabled(usable)
        self.gpu.setProperty("disabled", not usable)

        current = DEV.get_device(g)
        if current == DEV.GPU and not usable:
            current = DEV.CPU  # preferencia guardada, pero este equipo no puede: se muestra (y usa) CPU
        (self.gpu if current == DEV.GPU else self.cpu).button.setChecked(True)
        for card in (self.cpu, self.gpu):
            card.setProperty("selected", card.kind == current)
            card.style().unpolish(card)
            card.style().polish(card)

    # ---------------------------------------------------------------- acciones
    def _choose(self, device: str) -> None:
        g = C.load_global()
        if DEV.get_device(g) != device:
            g[DEV.DEVICE_KEY] = device
            C.save_global(g)
            self.device_changed.emit(device)
        self.refresh()

    def _copy_command(self) -> None:
        QGuiApplication.clipboard().setText(install_command())
        self.copy_btn.setText("Comando copiado ✓")
