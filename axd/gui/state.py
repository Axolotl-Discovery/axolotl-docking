"""Estado compartido de la app: proyecto abierto, tema, conectividad, estado
del trabajo en segundo plano. Un único QObject con señales, inyectado en cada
pestaña/diálogo, para no tener media docena de variables globales sueltas."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from .. import config as C
from .. import runner as R
from .services import connectivity


class AppState(QObject):
    project_changed = Signal(str)       # ruta del proyecto, "" si se cerró
    theme_changed = Signal(str)         # "dark" | "light"
    offline_changed = Signal(bool)      # True = sin conexión a internet
    job_state_changed = Signal(object)  # dict de axd.runner.estado(), o None

    POLL_MS = 4000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: str | None = None
        self.theme: str = "dark"
        self.offline: bool = False
        self._last_job_state = None

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.POLL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()
        self._poll()  # primer chequeo inmediato, no esperar 4s para el primer estado

    # ---------------------------------------------------------------- proyecto
    def open_project(self, path: str) -> None:
        C.register_recent(path)
        self.project = path
        self.project_changed.emit(path)

    def close_project(self) -> None:
        self.project = None
        self.project_changed.emit("")

    def recent_projects(self) -> list[str]:
        g = C.load_global()
        import os
        return [p for p in g.get("recientes", []) if os.path.exists(os.path.join(p, C.PROJECT_FILE))]

    # ---------------------------------------------------------------- tema
    def set_theme(self, theme: str) -> None:
        if theme != self.theme:
            self.theme = theme
            self.theme_changed.emit(theme)

    def toggle_theme(self) -> None:
        self.set_theme("light" if self.theme == "dark" else "dark")

    # ---------------------------------------------------------------- polling
    def _poll(self) -> None:
        online = connectivity.is_online()
        if online == self.offline:  # offline es "not online"
            pass
        new_offline = not online
        if new_offline != self.offline:
            self.offline = new_offline
            self.offline_changed.emit(self.offline)

        if self.project:
            e = R.estado(self.project)
            if e != self._last_job_state:
                self._last_job_state = e
                self.job_state_changed.emit(e)

    def job_state(self):
        return self._last_job_state
