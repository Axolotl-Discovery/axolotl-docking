"""Lista de pasos de Proceso: el pipeline anota el estado de cada paso y sus errores."""
import json
import os
import sys

import pytest

from steps_state import StepTracker
from axd import config as C
from axd import runner as R
from axd.layout import Layout


@pytest.fixture
def proy(tmp_path):
    ruta = str(tmp_path / "p")
    C.new_project(ruta, "p")
    return ruta


def _leer(proy):
    with open(Layout(proy).steps_state_file(), encoding="utf-8") as fh:
        return json.load(fh)


def test_estados_y_errores_por_paso(proy, capsys):
    t = StepTracker(Layout(proy).steps_state_file(), ["download", "receptors", "docking"],
                    R.DESCRIPCION_PASOS, log="/x/pipeline.log")
    try:
        assert [p["estado"] for p in _leer(proy)["pasos"]] == ["pendiente"] * 3
        t.iniciar("download")
        print("  ✔ 3OG7 descargado")
        t.terminar("download", 0)
        t.iniciar("receptors")
        assert _leer(proy)["pasos"][1]["estado"] == "en_curso"
        print("  ▸ 3OG7")
        print("    ✘ error: could not convert string to float: ''")
        t.terminar("receptors", 1)
    finally:
        t.cerrar()
    d = _leer(proy)
    assert [p["estado"] for p in d["pasos"]] == ["ok", "error", "pendiente"]
    assert d["pasos"][1]["errores"] == ["    ✘ error: could not convert string to float: ''"]
    assert d["pasos"][0]["errores"] == [] and d["terminado"] and d["log"] == "/x/pipeline.log"
    assert "✔ 3OG7 descargado" in capsys.readouterr().out  # la salida real sigue yendo al log
    assert sys.stdout is not None


def test_traceback_completo_se_guarda(proy):
    t = StepTracker(Layout(proy).steps_state_file(), ["ligands"], R.DESCRIPCION_PASOS)
    try:
        t.iniciar("ligands")
        print("Traceback (most recent call last):")
        print('  File "x.py", line 1, in <module>')
        print("ValueError: SMILES inválido")
        print("línea normal posterior")
        t.terminar("ligands", 1, excepcion=True)
    finally:
        t.cerrar()
    err = _leer(proy)["pasos"][0]["errores"]
    assert err[0].startswith("Traceback") and err[-1] == "ValueError: SMILES inválido"


def test_paso_en_curso_sin_trabajo_vivo_es_interrumpido(proy):
    t = StepTracker(Layout(proy).steps_state_file(), ["docking", "summary"], R.DESCRIPCION_PASOS)
    t.iniciar("docking")
    sys.stdout = t._stdout  # simula un corte: nunca se llamó terminar() ni cerrar()
    d = R.estado_pasos(proy)
    assert d["pasos"][0]["estado"] == "interrumpido" and d["pasos"][0]["errores"]


def test_filas_para_la_gui(proy):
    pytest.importorskip("PySide6")
    from axd.gui.widgets.steps_list import filas
    sin_correr = filas(None, ["download", "docking"])
    assert [f["estado"] for f in sin_correr] == ["pendiente", "pendiente"]
    data = {"terminado": True, "vivo": False, "pasos": [
        {"id": "receptors", "titulo": "R", "estado": "error", "segundos": 2.0, "fallos": 1, "errores": ["✘ x"]},
        {"id": "docking", "titulo": "D", "estado": "pendiente", "errores": []}]}
    f = filas(data, [])
    assert [x["estado"] for x in f] == ["error", "no_ejecutado"] and "1 problema" in f[0]["detalle"]


def test_traceback_de_un_paso_llega_al_reporte_de_error(tmp_path, monkeypatch):
    """Regresión: run.py imprimía el traceback a stderr y el reporte sólo decía «terminó con error»."""
    import json
    import subprocess
    import sys
    import textwrap
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = textwrap.dedent(f"""
        import sys, traceback
        sys.path.insert(0, {os.path.join(root, 'pipeline')!r})
        from steps_state import StepTracker
        t = StepTracker({str(tmp_path / 's.json')!r}, ['a'], {{}})
        t.iniciar('a')
        try:
            1 / 0
        except Exception:
            traceback.print_exc(file=sys.stdout)
        t.terminar('a', 1, True)
        t.cerrar()
    """)
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True)
    errores = json.load(open(tmp_path / "s.json"))["pasos"][0]["errores"]
    assert any("ZeroDivisionError" in e for e in errores)
