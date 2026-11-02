"""`Docking verificar`: proyecto de ejemplo, evaluación de la afinidad y detección del paso que falló."""
import csv
import json
import os

import pytest

from axd import config as C
from axd import verificar as V
from axd.layout import Layout


def test_el_proyecto_de_ejemplo_es_pequeno_y_valido(tmp_path):
    ruta = str(tmp_path / "p")
    p = V.crear_ejemplo(ruta)
    assert p["targets"][0]["pdb"] == "3PTB" and p["ligands"][0]["id"] == "benzamidina"
    d = C.load_project(ruta)["docking"]
    assert d["seeds"] == [42] and d["exhaustiveness"] == 8


def _tabla(ruta, dg):
    f = Layout(ruta).affinities_summary_csv()
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["diana", "ligando", "afinidad_media"])
        w.writeheader()
        w.writerow(dict(diana="3PTB", ligando="benzamidina", afinidad_media=dg))


@pytest.mark.parametrize("dg,ok", [(-6.2, True), (-0.3, False), (-30.0, False), (3.0, False)])
def test_evaluar_afinidad(tmp_path, dg, ok):
    ruta = str(tmp_path / "p")
    V.crear_ejemplo(ruta)
    _tabla(ruta, dg)
    assert V.evaluar_afinidad(ruta)[0] is ok


def test_sin_tabla_no_es_ok(tmp_path):
    ruta = str(tmp_path / "p")
    V.crear_ejemplo(ruta)
    ok, msg = V.evaluar_afinidad(ruta)
    assert not ok and "no se generó" in msg


def test_paso_fallido_lee_steps_json(tmp_path):
    ruta = str(tmp_path / "p")
    V.crear_ejemplo(ruta)
    f = Layout(ruta).steps_state_file()
    os.makedirs(os.path.dirname(f), exist_ok=True)
    json.dump({"vivo": False, "terminado": True, "pasos": [
        {"id": "download", "estado": "ok"},
        {"id": "receptors", "estado": "error", "errores": ["✘ prepare_receptor no está"]}]}, open(f, "w"))
    assert V.paso_fallido(ruta) == ("receptors", ["✘ prepare_receptor no está"])
    assert "receptors" in V.REMEDIOS and set(V.PASOS_PRUEBA) <= set(V.REMEDIOS) | {"download"}


def test_verificar_corta_con_poco_disco_y_sin_internet(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(V, "disco_libre_gb", lambda r: 0.5)
    assert V.verificar() == 1
    assert "espacio en disco" in capsys.readouterr().out
    monkeypatch.setattr(V, "disco_libre_gb", lambda r: 50.0)
    monkeypatch.setattr(V.entorno, "doctor", lambda reparar_preguntando=True: True)
    monkeypatch.setattr(V, "hay_internet", lambda *a, **k: False)
    assert V.verificar() == 1
    assert "files.rcsb.org" in capsys.readouterr().out


def test_verificar_flujo_feliz_con_pipeline_simulado(monkeypatch, capsys):
    monkeypatch.setattr(V, "disco_libre_gb", lambda r: 50.0)
    monkeypatch.setattr(V.entorno, "doctor", lambda reparar_preguntando=True: True)
    monkeypatch.setattr(V, "hay_internet", lambda *a, **k: True)
    vistos = {}

    def falso(proy, pasos, fondo=True, extra=None):
        vistos["pasos"], vistos["fondo"] = pasos, fondo
        _tabla(proy, -6.5)

    monkeypatch.setattr(V.runner, "ejecutar", falso)
    assert V.verificar() == 0
    assert vistos == {"pasos": V.PASOS_PRUEBA, "fondo": False}
    assert "Todo está listo" in capsys.readouterr().out


def test_verificar_explica_el_paso_que_fallo(monkeypatch, capsys):
    monkeypatch.setattr(V, "disco_libre_gb", lambda r: 50.0)
    monkeypatch.setattr(V.entorno, "doctor", lambda reparar_preguntando=True: True)
    monkeypatch.setattr(V, "hay_internet", lambda *a, **k: True)

    def falso(proy, pasos, fondo=True, extra=None):
        f = Layout(proy).steps_state_file()
        os.makedirs(os.path.dirname(f), exist_ok=True)
        json.dump({"vivo": False, "terminado": True,
                   "pasos": [{"id": "docking", "estado": "error", "errores": ["✘ smina falló"]}]}, open(f, "w"))

    monkeypatch.setattr(V.runner, "ejecutar", falso)
    assert V.verificar() == 1
    out = capsys.readouterr().out
    assert "docking" in out and "smina falló" in out and "Docking entorno" in out
