from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QProgressBar, QVBoxLayout

from ..services import calibration


class CalibracionDialog(QDialog):
    """Aparece en un dispositivo nuevo (ver calibration.needs_calibration()).
    'Calibrar ahora' corre el benchmark real (un par de segundos, bloqueante
    a propósito: es corto); 'Usar una estimación genérica' guarda el valor de
    referencia y no vuelve a preguntar en esta máquina."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración de dispositivo")
        self.result_calibration = None

        layout = QVBoxLayout(self)
        title = QLabel("Este dispositivo no está calibrado")
        title.setObjectName("Title")
        layout.addWidget(title)
        text = QLabel(
            "Para estimar cuánto va a tardar el docking en esta máquina, se corre un benchmark corto "
            "(un par de segundos, sólo CPU, sin tocar archivos ni red). El estimado se afina solo una vez "
            "que el trabajo lleva corridas terminadas — esto sólo evita un número inventado al principio."
        )
        text.setWordWrap(True)
        text.setObjectName("Muted")
        layout.addWidget(text)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox()
        self.btn_calibrate = buttons.addButton("Calibrar ahora", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_generic = buttons.addButton("Usar una estimación genérica por ahora",
                                              QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_calibrate.setObjectName("Primary")
        self.btn_calibrate.clicked.connect(self._calibrate)
        self.btn_generic.clicked.connect(self._generic)
        layout.addWidget(buttons)

    def _calibrate(self) -> None:
        self.btn_calibrate.setEnabled(False)
        self.btn_generic.setEnabled(False)
        self.progress.show()
        self.status.setText("Midiendo…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        self.result_calibration = calibration.calibrate_now()
        self.accept()

    def _generic(self) -> None:
        self.result_calibration = calibration.use_generic_estimate()
        self.reject()
