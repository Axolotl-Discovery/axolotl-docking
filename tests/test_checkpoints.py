"""Checkpoints automáticos/manuales y su restauración (axd.gui.services.checkpoints)."""
import json
import os

import pytest

from axd import config as C
from axd.layout import Layout
from axd.gui.services import checkpoints as K

N_LIGANDOS = 10  # 1 diana x 10 ligandos x 1 semilla = 10 corridas → cada una vale 10%


@pytest.fixture
def proy(tmp_path):
    ruta = str(tmp_path / "demo")
    p = C.new_project(ruta, "demo")
    p["docking"]["seeds"] = [1]
    p["targets"] = [{"id": "T1", "source": "pdb", "pdb": "3PTB", "chains": "auto",
                     "cofactors": "auto", "box": {"mode": "auto"}}]
    p["ligands"] = [{"id": f"L{i}", "source": "file"} for i in range(N_LIGANDOS)]
    C.save_project(ruta, p)
    return ruta


def _corrida(proy, i):
    f = Layout(proy).result_pdbqt("T1", f"L{i}", 1)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w") as fh:
        fh.write("MODEL 1\nENDMDL\n")


def test_avance_y_checkpoint_automatico_sin_duplicados(proy):
    assert K.progress_fraction(proy) == (0, N_LIGANDOS)
    assert K.maybe_checkpoint(proy) is None  # 0%: nada que guardar
    for i in range(3):
        _corrida(proy, i)
    cp = K.maybe_checkpoint(proy)
    assert cp is not None and cp.pct == 30
    assert K.maybe_checkpoint(proy) is None  # mismo tramo: no se repite


def test_restaurar_reinicia_umbral_y_permite_nuevos_checkpoints(proy):
    for i in range(6):
        _corrida(proy, i)
        K.maybe_checkpoint(proy)
    c30 = next(c for c in K.list_checkpoints(proy) if c.pct == 30)
    K.restore_checkpoint(proy, c30, delete_newer_results=True)
    assert K.progress_fraction(proy) == (3, N_LIGANDOS)

    with open(K._state_path(proy), encoding="utf-8") as fh:
        assert json.load(fh)["last_pct"] == 30  # antes se quedaba en 60

    creados = []
    for i in range(3, 6):  # se rehace 40%, 50%, 60%
        _corrida(proy, i)
        cp = K.maybe_checkpoint(proy)
        creados.append(cp.pct if cp else None)
    assert creados == [40, 50, 60]


def test_restaurar_hace_backup_del_json_actual(proy):
    cp = K.manual_checkpoint(proy, "antes")
    K.restore_checkpoint(proy, cp)
    assert any(".bak-restore-" in n for n in os.listdir(proy))


def test_gitignore_de_proyecto_nuevo_excluye_checkpoints(proy):
    with open(os.path.join(proy, ".gitignore"), encoding="utf-8") as fh:
        assert ".checkpoints/" in fh.read()
