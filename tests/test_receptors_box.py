"""Regresión del error "'box'" (KeyError) al añadir una diana sin la clave 'box'."""
import receptors
from helpers import linea_pdb


def _pdb(tmp_path, con_ligando):
    lineas = [linea_pdb(i, " CA ", "ALA", "A", i, float(i), 0.0, 0.0) for i in range(1, 6)]
    if con_ligando:
        # auto_decision exige >= 8 átomos para considerar algo un ligando de referencia
        for k in range(9):
            lineas.append(linea_pdb(6 + k, f" C{k + 1} ", "BEN", "A", 100, 3.0 + k, 3.0, 3.0, tipo="HETATM"))
    f = tmp_path / "x.pdb"
    f.write_text("".join(lineas) + "END\n")
    return str(f)


def test_box_ausente_se_resuelve_sin_keyerror(tmp_path):
    d = {"id": "T", "chains": "auto", "cofactors": "auto"}  # sin 'box'
    receptors._resolver_auto(d, _pdb(tmp_path, con_ligando=False))
    assert d["box"]["mode"] == "blind" and d["box"]["auto"] is True


def test_box_ausente_con_ligando_usa_el_sitio_del_ligando(tmp_path):
    d = {"id": "T", "chains": "auto", "cofactors": "auto"}
    receptors._resolver_auto(d, _pdb(tmp_path, con_ligando=True))
    assert d["box"]["mode"] == "ligand" and d["box"]["ref"].startswith("BEN")


def test_box_explicito_no_se_pisa(tmp_path):
    d = {"id": "T", "chains": "auto", "cofactors": "auto",
         "box": {"mode": "manual", "center": [0, 0, 0], "size": [20, 20, 20]}}
    receptors._resolver_auto(d, _pdb(tmp_path, con_ligando=True))
    assert d["box"]["mode"] == "manual"


def test_necesita_auto():
    assert receptors._necesita_auto({"chains": ["A"], "cofactors": []})  # sin box
    assert receptors._necesita_auto({"chains": ["A"], "cofactors": [], "box": {}})
    assert receptors._necesita_auto({"chains": "auto", "cofactors": [], "box": {"mode": "blind"}})
    assert receptors._necesita_auto({"chains": ["A"], "cofactors": [], "box": {"mode": "auto"}})
    assert not receptors._necesita_auto({"chains": ["A"], "cofactors": [], "box": {"mode": "blind"}})
