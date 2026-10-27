from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QMainWindow, QToolBar, QWidget

from .. import config as C
from .. import runner as R
from . import theme
from .dialogs.cerrar_con_trabajo_dialog import CerrarConTrabajoDialog
from .dialogs.cerrar_terminal_dialog import CerrarTerminalDialog
from .state import AppState
from .tabs.analisis_tab import AnalisisTab
from .tabs.entorno_tab import EntornoTab
from .tabs.postproceso_tab import PostprocesoTab
from .tabs.proceso_tab import ProcesoTab
from .tabs.resultados_tab import ResultadosTab
from .widgets.side_nav import SideTabs
from .widgets.terminal_panel import TerminalPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Axolotl Docking — v{C.VERSION}")
        self.resize(1440, 900)

        self.state = AppState(self)
        self.state.project_changed.connect(self._on_project_changed)
        self.state.offline_changed.connect(self._on_offline_changed)

        self._build_top_bar()

        # Navegación: barra vertical de iconos a la derecha, desplegable.
        g = C.load_global()
        self.tabs = SideTabs(collapsed=bool(g.get("gui_nav_collapsed", True)))
        self.tabs.addTab(AnalisisTab(self.state), "project", "Proyecto")
        self.tabs.addTab(ProcesoTab(self.state), "process", "Proceso")
        self.resultados_tab = ResultadosTab(self.state)
        self.tabs.addTab(self.resultados_tab, "results", "Resultados")
        self.postproceso_tab = PostprocesoTab(self.state)
        self.postproceso_tab.open_viewer.connect(self._open_viewer)
        self.tabs.addTab(self.postproceso_tab, "postproc", "Postprocesamiento")
        self.tabs.addTab(EntornoTab(self.state), "env", "Entorno")
        self.tabs.addAction("theme", "Cambiar tema", self.state.toggle_theme)
        self.tabs.addAction("terminal", "Terminal", self._toggle_terminal)
        self.tabs.collapsedChanged.connect(self._save_nav_collapsed)
        self.setCentralWidget(self.tabs)

        self._build_terminal_dock()

        self._apply_theme(self.state.theme)
        self.state.theme_changed.connect(self._apply_theme)

    def _open_viewer(self, target: str, ligand: str) -> None:
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.resultados_tab))
        self.resultados_tab.show_viewer(target or None, ligand or None)

    def _apply_theme(self, name: str) -> None:
        theme.apply_theme(self, name)
        t = theme.tokens_for(name)
        self.tabs.set_colors(t["text_secondary"], t["accent"])

    def _save_nav_collapsed(self, collapsed: bool) -> None:
        g = C.load_global()
        g["gui_nav_collapsed"] = collapsed
        C.save_global(g)

    # ---------------------------------------------------------------- barra superior
    def _build_top_bar(self) -> None:
        bar = QWidget()
        bar.setObjectName("TopBar")
        row = QHBoxLayout(bar)
        brand = QLabel("AXOLOTL DOCKING")
        brand.setObjectName("Brand")
        row.addWidget(brand)
        self.project_chip = QLabel("sin proyecto")
        self.project_chip.setObjectName("Chip")
        row.addWidget(self.project_chip)
        row.addStretch(1)

        self.offline_chip = QLabel("●  sin conexión a internet")
        self.offline_chip.setObjectName("ChipOffline")
        self.offline_chip.hide()
        row.addWidget(self.offline_chip)

        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.addWidget(bar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _on_offline_changed(self, offline: bool) -> None:
        self.offline_chip.setVisible(offline)

    def _on_project_changed(self, path: str) -> None:
        self.project_chip.setText(f"📁 {os.path.basename(path)}" if path else "sin proyecto")
        if self.terminal_dock.isVisible() or self.terminal_panel.is_running():
            self.terminal_panel.start(path or None)

    # ---------------------------------------------------------------- terminal
    def _build_terminal_dock(self) -> None:
        self.terminal_panel = TerminalPanel(self)
        self.terminal_dock = QDockWidget("Terminal — " + (self.state.project or "sin proyecto"), self)
        self.terminal_dock.setObjectName("TerminalDock")
        self.terminal_dock.setWidget(self.terminal_panel)
        self.terminal_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                                       QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                       QDockWidget.DockWidgetFeature.DockWidgetClosable)
        # Abajo por defecto: a la derecha ya está la barra de navegación.
        self.terminal_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea |
                                           Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock)
        self.terminal_dock.hide()
        self.terminal_dock.visibilityChanged.connect(self._on_terminal_visibility_changed)
        # Interceptamos el cierre nosotros: closeEvent de QDockWidget no es fácil
        # de cancelar desde fuera, así que usamos visibilityChanged + un flag.
        self.terminal_dock.topLevelChanged.connect(self._on_terminal_floated)
        self._closing_terminal_confirmed = False

    def _toggle_terminal(self) -> None:
        if self.terminal_dock.isVisible():
            self._request_close_terminal()
        else:
            self.terminal_dock.show()
            if not self.terminal_panel.is_running():
                self.terminal_panel.start(self.state.project)

    def _on_terminal_floated(self, floating: bool) -> None:
        label = "Terminal en ventana propia" if floating else "Terminal"
        self.terminal_dock.setWindowTitle(label)

    def _on_terminal_visibility_changed(self, visible: bool) -> None:
        if visible:
            return
        if self._closing_terminal_confirmed:
            self._closing_terminal_confirmed = False
            self.terminal_panel.stop()
            return
        if self.terminal_panel.has_pending_interactive_step():
            # Se cerró (click en la X) sin pasar por nuestro diálogo: lo
            # reabrimos y preguntamos, igual que el wireframe 'Cerrar panel
            # de terminal con paso a medio completar'.
            self.terminal_dock.show()
            self._request_close_terminal()
        else:
            self.terminal_panel.stop()

    def _request_close_terminal(self) -> None:
        if self.terminal_panel.has_pending_interactive_step():
            job = R.estado(self.state.project) if self.state.project else None
            dlg = CerrarTerminalDialog(bool(job and job.get("vivo")), job.get("pid") if job else None, self)
            if dlg.exec() and dlg.choice == CerrarTerminalDialog.CERRAR:
                self._closing_terminal_confirmed = True
                self.terminal_dock.hide()
        else:
            self._closing_terminal_confirmed = True
            self.terminal_dock.hide()

    # ---------------------------------------------------------------- cierre de la app
    def closeEvent(self, event) -> None:
        if self.state.project:
            job = R.estado(self.state.project)
            if job and job.get("vivo"):
                dlg = CerrarConTrabajoDialog(job, self)
                dlg.exec()
                if dlg.choice == CerrarConTrabajoDialog.CANCELAR:
                    event.ignore()
                    return
                if dlg.choice == CerrarConTrabajoDialog.DETENER:
                    R.detener(self.state.project)
        self.terminal_panel.stop()
        event.accept()
