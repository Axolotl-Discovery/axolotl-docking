"""Smoke test de la GUI (PySide6): arma la ventana principal, abre un
proyecto sintético y refresca las 6 pestañas, sin exigir conda/smina/ADFRsuite
ni un entorno gráfico real (usa QT_QPA_PLATFORM=offscreen).

No es parte de la suite de pytest (pytest.ini no lo recoge por el nombre)
porque crea una QApplication, y eso no convive bien con correr en paralelo
junto al resto de las pruebas. Se corre aparte:

    QT_QPA_PLATFORM=offscreen python tests/smoke_gui.py

Pensado sobre todo para verificar rápido, en CI, que el paquete axd.gui
arranca igual en Linux, macOS y Windows (ver .github/workflows/gui-smoke.yml) —
la lógica de dominio (axd.runner, axd.entorno, el pipeline) sigue siendo
Linux/WSL-only (smina y ADFRsuite no tienen build de Mac en este repo), pero
la ventana y las pestañas de la GUI en sí son Qt puro y deberían abrir en
cualquier sistema operativo soportado por PySide6."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile


def main() -> int:
    os.environ.setdefault("AXD_CONFIG_DIR", tempfile.mkdtemp(prefix="axd_gui_smoke_config_"))

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        pass
    app = QApplication.instance() or QApplication([])

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, repo_root)

    from axd import config as C
    from axd.gui.main_window import MainWindow
    from axd.gui.services import calibration

    # Evita que ProcesoTab abra el diálogo modal de calibración al abrir el
    # proyecto (calibration.needs_calibration() es True la primera vez que se
    # usa un AXD_CONFIG_DIR nuevo) — ese diálogo espera un click real y
    # colgaría este smoke test sin interacción (como colgó la primera corrida
    # local antes de este ajuste).
    calibration.use_generic_estimate()

    proy = tempfile.mkdtemp(prefix="axd_gui_smoke_project_")
    try:
        C.new_project(proy, "Smoke", mode="advanced")
        p = C.load_project(proy)
        p["targets"] = [{"id": "t1", "source": "file", "name": "t1", "file": "x.pdb",
                          "chains": "auto", "cofactors": "auto", "box": {"mode": "blind"}}]
        p["ligands"] = [{"id": "l1", "name": "l1", "source": "smiles", "smiles": "CCO"}]
        C.save_project(proy, p)

        win = MainWindow()
        win.show()
        win.state.open_project(proy)
        app.processEvents()

        assert win.tabs.count() == 6, f"se esperaban 6 pestañas, hay {win.tabs.count()}"
        for i in range(win.tabs.count()):
            w = win.tabs.widget(i)
            if hasattr(w, "refresh"):
                w.refresh()
        app.processEvents()

        assert win.tabs.widget(1).targets_table.rowCount() == 1, "la pestaña Análisis no cargó la diana"
        win.close()
        app.processEvents()
        print("OK: GUI smoke test passed")
        return 0
    finally:
        shutil.rmtree(proy, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
