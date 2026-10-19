"""Panel de terminal real: corre el mismo `axd/cli.py` que usa el comando
`Docking` en una terminal de verdad, dentro de un QProcess, con su
entrada/salida mostradas aquí. No es una reimplementación del menú — es el
mismo proceso que correría `Docking abrir`, así que cualquier asistente
interactivo (axd/wizards/*) funciona igual.

Vive dentro de un QDockWidget en la ventana principal: Qt ya da 'soltar a una
ventana propia' / 'volver a acoplar' gratis (QDockWidget flotante), que es
justo el comportamiento de 'terminal independiente' del diseño."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ... import config as C


class TerminalPanel(QWidget):
    interactive_step_pending = Signal(bool)  # True = hay output a medio responder (ver diálogo de cierre)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self._awaiting_input = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.output = QPlainTextEdit(readOnly=True)
        self.output.setStyleSheet("background:#000000; color:#F2F2F2; font-family: ui-monospace, Menlo, monospace;"
                                   " border: none; border-radius: 0;")
        layout.addWidget(self.output, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Escribí una respuesta y Enter…")
        self.input.returnPressed.connect(self._send_line)
        self.input.setStyleSheet("background:#000000; color:#F2F2F2; font-family: ui-monospace, Menlo, monospace;"
                                  " border: 1px solid #3A3A3A;")
        send = QPushButton("Enviar")
        send.clicked.connect(self._send_line)
        restart = QPushButton("↻ Reiniciar")
        restart.clicked.connect(self.restart)
        row.addWidget(self.input, 1)
        row.addWidget(send)
        row.addWidget(restart)
        layout.addLayout(row)

    # ---------------------------------------------------------------- ciclo de vida
    def start(self, project_path: str | None) -> None:
        from PySide6.QtCore import QProcess
        self.stop()
        self.process = QProcess(self)
        if project_path:
            self.process.setWorkingDirectory(project_path)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        cli = __import__("os").path.join(C.APP, "axd", "cli.py")
        self.process.start(sys.executable, [cli])
        self.output.clear()
        self._set_awaiting(False)

    def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.kill()
            except RuntimeError:
                pass
            self.process = None
        self._set_awaiting(False)

    def restart(self) -> None:
        proj = None
        if self.process is not None:
            proj = self.process.workingDirectory()
        self.start(proj)

    def is_running(self) -> bool:
        from PySide6.QtCore import QProcess
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def has_pending_interactive_step(self) -> bool:
        """True si el proceso está vivo y esperando una respuesta — cerrar el
        panel/ventana en este momento perdería ese paso (ver diálogo de
        confirmación de cierre). No afecta al trabajo de docking en segundo
        plano: ese es un proceso completamente aparte (axd.runner, por PID)."""
        return self.is_running() and self._awaiting_input

    # ---------------------------------------------------------------- IO
    def _send_line(self) -> None:
        text = self.input.text()
        self.input.clear()
        if self.process is None:
            return
        self.process.write((text + "\n").encode())
        self._set_awaiting(False)

    def _on_output(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if not data:
            return
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(data)
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        # Heurística simple y honesta: si lo último que imprimió no termina en
        # salto de línea, lo normal en axd/ui.py es que esté esperando que el
        # usuario conteste en la misma línea (un prompt).
        self._set_awaiting(not data.endswith("\n"))

    def _on_finished(self, *_args) -> None:
        self._set_awaiting(False)

    def _set_awaiting(self, value: bool) -> None:
        if value != self._awaiting_input:
            self._awaiting_input = value
            self.interactive_step_pending.emit(value)
