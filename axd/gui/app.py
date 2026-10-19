"""Punto de entrada de la GUI: `python -m axd.gui` o `Docking gui`."""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Axolotl Docking")

    from .main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
