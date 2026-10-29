"""Reporte PDF (pipeline/report.py): datos, texto de métodos, referencias y PDF real."""
import csv
import json
import os

import pytest

import common
import report
from axd import config as C
from axd.layout import Layout


def _wcsv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def proy(tmp_path):
    ruta = str(tmp_path / "p")
    C.new_project(ruta, "Demo reporte")
    p = C.load_project(ruta)
    p["targets"] = [{"id": "3OG7", "source": "pdb", "pdb": "3OG7", "chains": "A", "cofactors": [],
                     "box": {"mode": "ligand"}}]
    p["ligands"] = [{"id": "asp", "name": "Aspirina", "source": "smiles", "smiles": "CC(=O)Oc1ccccc1C(=O)O"}]
    p["controls"] = [{"id": "ctl", "name": "Control", "source": "smiles", "smiles": "c1ccccc1O", "target": "3OG7"}]
    p["docking"]["motor_usado"] = "smina"
    C.save_project(ruta, p)
    lay = Layout(ruta)
    os.makedirs(os.path.dirname(lay.boxes_json()), exist_ok=True)
    with open(lay.boxes_json(), "w") as fh:
        json.dump({"3OG7": {"center": [1, 2, 3], "size": [22, 22, 22], "mode": "ligand"}}, fh)
    _wcsv(lay.affinities_summary_csv(), [
        dict(diana="3OG7", ligando="ctl", tipo="control", afinidad_media=-8.0, afinidad_de=0.1, mejor=-8.1,
             n_semillas=3, n_pesados=7, LE=1.1, delta_vs_control=0.0),
        dict(diana="3OG7", ligando="asp", tipo="ligando", afinidad_media=-8.5, afinidad_de=0.2, mejor=-8.7,
             n_semillas=3, n_pesados=13, LE=0.65, delta_vs_control=-0.5)])
    _wcsv(lay.redocking_summary_csv(), [{"diana": "3OG7", "semilla": 42, "afinidad": -9, "rmsd": 1.2}])
    _wcsv(lay.interactions_detail_csv(), [dict(diana="3OG7", ligando="asp", tipo="Puente de H", residuo="CYS532",
                                                cadena="A", distancia=2.9, detalle="", metodo="PLIP")])
    return ruta


def test_recolectar_y_resumen(proy):
    d = report.recolectar(common.Project(proy))
    (r,) = d["resumen"]
    assert r["mejor"] == "asp" and r["dg"] == -8.5 and r["supera_control"] is True
    assert r["redock_rmsd_min"] == 1.2 and d["motor"] == "smina"


def test_metodos_y_referencias_segun_lo_hecho(proy):
    d = report.recolectar(common.Project(proy))
    texto = " ".join(report.texto_metodos(d))
    assert "3OG7" in texto and "smina" in texto and "exhaustiveness 32" in texto
    assert "redocking" in texto and "PLIP" in texto and "co-cristalizado" in texto
    refs = " ".join(report.referencias(d))
    assert "Koes DR" in refs and "Trott O" in refs and "PLIP 2021" in refs and "Protein Data Bank" in refs
    d["motor"] = "vina-gpu"
    assert "Vina-GPU 2.1" in " ".join(report.referencias(d)) and "Koes DR" not in " ".join(report.referencias(d))


def test_pdf_real(proy):
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    rc = report.run(common.Project(proy))
    assert rc == 0
    rep = Layout(proy).report_dir()
    pdfs = [f for f in os.listdir(rep) if f.endswith(".pdf")]
    assert "reporte_ultimo.pdf" in pdfs and len(pdfs) == 2
    with open(os.path.join(rep, "reporte_ultimo.pdf"), "rb") as fh:
        data = fh.read()
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page") >= 3
