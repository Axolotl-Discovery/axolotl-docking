from PySide6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout


class CerrarTerminalDialog(QDialog):
    """Sólo aparece si TerminalPanel.has_pending_interactive_step() es True.
    Si no hay nada a medio responder, el panel/ventana se cierra directo, sin
    preguntar (política 'toast primero, modal sólo cuando es irreversible')."""

    CANCELAR = 0
    CERRAR = 1

    def __init__(self, job_running: bool, job_pid: int | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿Cerrar la terminal?")
        self.choice = self.CANCELAR

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hay un paso a medio completar en esta terminal."))
        msg = QLabel("Si la cerrás, se interrumpe — igual que si cerraras una terminal real sin terminar de "
                      "escribir.")
        msg.setWordWrap(True)
        msg.setObjectName("Muted")
        layout.addWidget(msg)

        if job_running:
            banner = QFrame()
            banner.setObjectName("BannerSuccess")
            banner.setProperty("class", "Banner")
            b_layout = QVBoxLayout(banner)
            text = QLabel(f"✓ El trabajo de docking en segundo plano (PID {job_pid}) no se ve afectado — "
                          "sigue corriendo y lo podés seguir viendo en la pestaña Proceso, cierres o no esta "
                          "terminal.")
            text.setWordWrap(True)
            b_layout.addWidget(text)
            banner.setStyleSheet("QFrame { border-radius: 8px; padding: 10px; }")
            layout.addWidget(banner)

        cancel = QPushButton("Cancelar (seguir con el asistente)")
        cancel.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        close_anyway = QPushButton("Cerrar igual (se pierde este paso)")
        close_anyway.setObjectName("Danger")
        close_anyway.clicked.connect(lambda: self._choose(self.CERRAR))
        layout.addWidget(cancel)
        layout.addWidget(close_anyway)

    def _choose(self, value: int) -> None:
        self.choice = value
        self.accept()
