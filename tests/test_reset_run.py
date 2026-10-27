"""Eliminar el último procesamiento (pasos 5–7) con respaldo .zip previo."""
import os
import zipfile

import pytest

pytest.importorskip("PySide6")

from axd import config as C  # noqa: E402
from axd.layout import Layout  # noqa: E402
from axd.gui.services import checkpoints as CK, reset_run  # noqa: E402


def _w(path, txt="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(txt)


@pytest.fixture
def proy(tmp_path):
    ruta = str(tmp_path / "p")
    p = C.new_project(ruta, "p")
    p["targets"] = [{"id": "T1", "source": "pdb", "pdb": "3OG7", "chains": "A", "cofactors": [], "box": {"mode": "auto"}}]
    p["ligands"] = [{"id": "L1", "source": "pubchem"}]
    C.save_project(ruta, p)
    lay = Layout(ruta)
    # pasos 5–7 (se borran)
    _w(lay.result_pdbqt("T1", "L1", 42), "MODEL 1\nENDMDL\n")
    _w(lay.best_pose_pdbqt("T1", "L1"))
    _w(lay.complex_pdb("T1", "L1"))
    _w(lay.affinities_summary_csv())
    _w(lay.affinity_matrix_csv())
    _w(lay.interactions_detail_csv())
    _w(lay.affinities_xlsx("p"))
    # lo que se conserva
    _w(lay.receptor_pdbqt("T1"))
    _w(lay.ligand_pdbqt("L1"))
    _w(lay.boxes_json(), "{}")
    _w(lay.redocking_result_pdbqt("T1", 42))
    _w(lay.redocking_summary_csv())
    _w(lay.pipeline_log("20261026_120000"), "log\n")
    return ruta


def test_lista_solo_pasos_5_a_7(proy):
    lay = Layout(proy)
    files = set(reset_run.files_to_remove(proy))
    assert lay.result_pdbqt("T1", "L1", 42) in files and lay.complex_pdb("T1", "L1") in files
    assert lay.affinities_xlsx("p") in files
    for keep in (lay.receptor_pdbqt("T1"), lay.ligand_pdbqt("L1"), lay.boxes_json(),
                 lay.redocking_result_pdbqt("T1", 42), lay.redocking_summary_csv()):
        assert keep not in files
    assert reset_run.summary(proy)["n_files"] == 7


def test_respaldo_y_eliminar(proy, tmp_path):
    lay = Layout(proy)
    zpath = reset_run.make_backup(proy, str(tmp_path / "copia.zip"))
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert "axd.json" in names and os.path.relpath(lay.complex_pdb("T1", "L1"), proy) in names
    assert any(n.endswith(".log") for n in names)

    st = CK._load_state(proy); st["last_pct"] = 90; CK._save_state(proy, st)
    assert reset_run.remove(proy) == 7
    assert reset_run.files_to_remove(proy) == []
    assert not os.path.exists(lay.target_results_dir("T1")) and not os.path.exists(lay.complexes_dir())
    for keep in (lay.receptor_pdbqt("T1"), lay.ligand_pdbqt("L1"), lay.redocking_result_pdbqt("T1", 42),
                 lay.redocking_summary_csv(), os.path.join(proy, "axd.json")):
        assert os.path.exists(keep), keep
    assert CK._load_state(proy)["last_pct"] == -1


def test_respaldo_dentro_de_04_docking_se_rechaza(proy):
    with pytest.raises(IOError):
        reset_run.make_backup(proy, os.path.join(Layout(proy).docking_dir(), "copia.zip"))
    assert reset_run.summary(proy)["n_files"] == 7  # no se borró nada


def test_restaurar_desde_el_zip_deja_todo_igual(proy, tmp_path):
    lay = Layout(proy)
    zpath = reset_run.make_backup(proy, str(tmp_path / "copia.zip"))
    reset_run.remove(proy)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(proy)
    assert os.path.isfile(lay.complex_pdb("T1", "L1")) and reset_run.summary(proy)["n_files"] == 7
