"""Punto de entrada de la GUI: `python -m axd.gui` o `Docking gui`."""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    # QtWebEngine (visor 3D de Visualización) exige esto antes de crear la app.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        pass  # el visor muestra un aviso y se usa PyMOL externo

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Axolotl Docking")

    from .main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
