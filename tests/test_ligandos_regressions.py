"""Regresión (Fase 4): pipeline/ligandos.py::preparar_ref_redocking() tenía
`from descargar import _bajar`, una función borrada en la Fase 3/5 — ImportError
latente en cualquier proyecto en modo básico que necesitara redocking sin el SDF
de referencia ya descargado. El arreglo la enruta por axd.infra.net.bajar()."""
import os
import sys
import types

import pytest


@pytest.fixture
def rdkit_falso(monkeypatch):
    """ligandos.py hace `from rdkit import Chem` dentro de la función — no a nivel de
    módulo — así que basta con que el nombre exista en sys.modules cuando se llama."""
    chem = types.SimpleNamespace(
        MolFromMolBlock=lambda *a, **k: None,
        RemoveHs=lambda m: m,
        AddHs=lambda m, **k: m,
    )
    fake_rdkit = types.SimpleNamespace(Chem=chem)
    monkeypatch.setitem(sys.modules, "rdkit", fake_rdkit)
    monkeypatch.setitem(sys.modules, "rdkit.Chem", chem)
    return chem


class FakeLayout:
    def __init__(self, raiz):
        self.raiz = raiz

    def redocking_ligand_pdbqt(self, diana_id):
        return os.path.join(self.raiz, f"redock_{diana_id}.pdbqt")


class FakeP:
    def __init__(self, raiz):
        self.layout = FakeLayout(str(raiz))

    def ref_sdf(self, d):
        return os.path.join(self.layout.raiz, f"{d['id']}_ref.sdf")

    def ref_pdb(self, d):
        return os.path.join(self.layout.raiz, f"{d['id']}_ref.pdb")


def test_preparar_ref_redocking_usa_axd_infra_net(tmp_path, rdkit_falso, monkeypatch):
    import ligandos

    llamadas = []

    def fake_bajar(url, dest, intentos=1, timeout=None):
        llamadas.append((url, dest, intentos))
        raise IOError("no se encontró (ambas URLs fallan en la prueba)")

    import axd.infra.net as net_mod
    monkeypatch.setattr(net_mod, "bajar", fake_bajar)

    P = FakeP(tmp_path)
    d = {"id": "d1", "pdb": "1ABC", "caja": {"ref": "HEM:A"}}

    # no debe lanzar ImportError (la regresión original) ni ningún otro error no manejado;
    # al no haber SDF/PDB de referencia, el resultado esperado es (None, None).
    resultado = ligandos.preparar_ref_redocking(P, d)
    assert resultado == (None, None)

    assert len(llamadas) == 2, "debió intentar las dos URLs de models.rcsb.org"
    for url, dest, intentos in llamadas:
        assert url.startswith("https://models.rcsb.org/v1/1ABC/ligand?auth_comp_id=HEM")
        assert dest == P.ref_sdf(d)
        assert intentos == 2


def test_preparar_ref_redocking_no_descarga_si_ya_existe_el_sdf(tmp_path, rdkit_falso, monkeypatch):
    import ligandos

    def fake_bajar(*a, **k):
        raise AssertionError("no debería llamarse: el SDF ya existe")

    import axd.infra.net as net_mod
    monkeypatch.setattr(net_mod, "bajar", fake_bajar)

    P = FakeP(tmp_path)
    d = {"id": "d1", "pdb": "1ABC", "caja": {"ref": "HEM:A"}}
    open(P.ref_sdf(d), "w").write("SDF de prueba\n$$$$\n")

    # MolFromMolBlock devuelve None en el doble -> no hay molécula de referencia válida,
    # pero lo importante es que NO intenta descargar (y no revienta con ImportError).
    resultado = ligandos.preparar_ref_redocking(P, d)
    assert resultado == (None, None)
