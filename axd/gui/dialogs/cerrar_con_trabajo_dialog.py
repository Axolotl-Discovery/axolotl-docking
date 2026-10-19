from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class CerrarConTrabajoDialog(QDialog):
    """Se muestra al cerrar la app (o aplicar una actualización) mientras hay
    un trabajo de docking corriendo en segundo plano (axd.runner.estado())."""

    DEJAR_CORRIENDO = 1
    DETENER = 2
    CANCELAR = 0

    def __init__(self, job_state: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿Cerrar con un trabajo corriendo?")
        self.choice = self.CANCELAR

        layout = QVBoxLayout(self)
        pasos = ", ".join(job_state.get("pasos", []))
        layout.addWidget(QLabel(f"Hay un trabajo corriendo (PID {job_state.get('pid')}): {pasos}."))
        info = QLabel("Si lo dejás corriendo, sigue en segundo plano aunque cierres la app; podés volver a "
                       "abrirla y seguirlo en la pestaña Proceso. Si lo detenés, se pierde lo que falta de "
                       "esta corrida (lo ya terminado se conserva).")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        layout.addWidget(info)

        row = QVBoxLayout()
        b1 = QPushButton("Dejarlo corriendo y cerrar")
        b1.setObjectName("Primary")
        b1.clicked.connect(lambda: self._choose(self.DEJAR_CORRIENDO))
        b2 = QPushButton("Detener el trabajo y cerrar")
        b2.setObjectName("Danger")
        b2.clicked.connect(lambda: self._choose(self.DETENER))
        b3 = QPushButton("Cancelar")
        b3.clicked.connect(lambda: self._choose(self.CANCELAR))
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        layout.addLayout(row)

    def _choose(self, value: int) -> None:
        self.choice = value
        self.accept() if value != self.CANCELAR else self.reject()
