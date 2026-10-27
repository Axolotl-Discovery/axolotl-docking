"""Datos de la pestaña Visualización (axd.gui.tabs.visualizacion_tab.collect)."""
import csv
import json
import os

import pytest

pytest.importorskip("PySide6")

from axd import config as C  # noqa: E402
from axd.layout import Layout  # noqa: E402
from axd.gui.tabs.visualizacion_tab import collect  # noqa: E402


@pytest.fixture
def proy(tmp_path):
    ruta = str(tmp_path / "p")
    p = C.new_project(ruta, "p")
    p["targets"] = [{"id": "3OG7", "source": "pdb", "pdb": "3OG7", "chains": "A", "cofactors": [],
                     "box": {"mode": "auto"}}]
    p["ligands"] = [{"id": "5280343", "source": "pubchem"}]
    C.save_project(ruta, p)
    return ruta


def _escribir(path, texto="X\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(texto)


def test_sin_dianas_explica_que_falta(tmp_path):
    ruta = str(tmp_path / "vacio")
    C.new_project(ruta, "vacio")
    d = collect(ruta)
    assert d["complexes"] == [] and d["targets"] == [] and "no tiene dianas" in d["hint"]


def test_diana_sin_receptor_apunta_al_paso_2(proy):
    d = collect(proy)
    assert d["targets"] == [] and "paso 2" in d["hint"]


def test_receptor_preparado_se_lista_con_su_caja(proy):
    lay = Layout(proy)
    _escribir(lay.receptor_clean("3OG7"))
    _escribir(lay.boxes_json(), json.dumps({"3OG7": {"center": [1, 2, 3], "size": [22, 22, 22], "mode": "ligand"}}))
    d = collect(proy)
    assert [t["id"] for t in d["targets"]] == ["3OG7"]
    assert d["complexes"] == [] and "pasos 5–7" in d["hint"]


def test_complejo_con_interacciones(proy):
    lay = Layout(proy)
    _escribir(lay.complex_pdb("3OG7", "5280343"))
    os.makedirs(os.path.dirname(lay.interactions_detail_csv()), exist_ok=True)
    with open(lay.interactions_detail_csv(), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["diana", "ligando", "tipo", "residuo", "cadena", "distancia", "detalle", "metodo"])
        w.writeheader()
        w.writerow(dict(diana="3OG7", ligando="5280343", tipo="Puente de H", residuo="CYS532", cadena="A",
                        distancia="2.9", detalle="", metodo="plip"))
    d = collect(proy)
    assert d["hint"] == ""
    (c,) = d["complexes"]
    assert c["target"] == "3OG7" and c["ligand"] == "5280343" and len(c["interactions"]) == 1


def test_residuos_de_interacciones_unicos_y_con_cadena():
    from axd.gui.widgets.mol_viewer import residues_from_interactions
    rows = [{"residuo": "CYS532", "cadena": "A"}, {"residuo": "CYS532", "cadena": "A"},
            {"residuo": "TRP531", "cadena": "A"}, {"residuo": "HOH", "cadena": "A"}, {"residuo": "LEU-3", "cadena": ""}]
    assert residues_from_interactions(rows) == [{"resi": 532, "chain": "A"}, {"resi": 531, "chain": "A"}, {"resi": -3}]


def test_vendor_3dmol_presente():
    from axd.gui.widgets.mol_viewer import VENDOR_DIR
    js = os.path.join(VENDOR_DIR, "3Dmol-min.js")
    assert os.path.getsize(js) > 100_000 and os.path.isfile(os.path.join(VENDOR_DIR, "LICENSE"))
