"""Un id de diana/ligando/control no es un texto cualquiera: termina interpolado en
nombres de archivo en todas partes (Layout.receptor_pdbqt, ligand_pdbqt, result_pdbqt,
complex_base...). Antes de este fix, nada lo saneaba al venir de la GUI ni al cargar
un axd.json ya existente, así que un id con '..' (o con forma de ruta absoluta) podía
hacer que una ruta de salida escapara de la carpeta del proyecto.

Estas pruebas cubren las tres capas del arreglo:
  1. sanitize_id() neutraliza payloads de traversal sin dejar un '..' como segmento
     real de ruta (y es idempotente sobre ids ya seguros).
  2. ensure_safe_ids() / config.load_project() auto-reparan un axd.json que ya
     trajera un id inseguro (compartido, editado a mano, o de una GUI vieja).
  3. Layout.r() es el respaldo: si algo aguas arriba olvida sanear, falla alto
     (ValueError) en vez de escribir en silencio fuera del proyecto.
"""
import json
import os

import pytest

from axd import config as C, layout as L

PAYLOADS = [
    "../../../../../../tmp/pwned",
    "/etc/passwd",
    "....//....//etc/passwd",
    "a/../../b",
    "",
    "   ",
]


def _escapes(path, root):
    norm, root_norm = os.path.normpath(path), os.path.normpath(root)
    return not (norm == root_norm or norm.startswith(root_norm + os.sep))


@pytest.mark.parametrize("payload", PAYLOADS)
def test_sanitize_id_never_escapes_project(payload, tmp_path):
    lay = L.Layout(str(tmp_path))
    safe = L.sanitize_id(payload)
    assert _escapes(lay.receptor_pdbqt(safe), lay.root) is False


def test_sanitize_id_is_idempotent_for_already_safe_ids():
    for ya_seguro in ("3PTB", "1M17_v2", "benzamidine-control"):
        assert L.sanitize_id(ya_seguro) == ya_seguro


def test_layout_r_rejects_a_traversal_that_slipped_through():
    lay = L.Layout("/tmp/axd_proyecto_test")
    with pytest.raises(ValueError):
        lay.receptor_pdbqt("../../../../../../tmp/pwned")


def test_ensure_safe_ids_fixes_in_place_and_reports_changed():
    p = {"targets": [{"id": "../../evil", "name": "x"}], "ligands": [], "controls": []}
    changed, p = L.ensure_safe_ids(p)
    assert changed is True
    assert p["targets"][0]["id"] == L.sanitize_id("../../evil")


def test_ensure_safe_ids_avoids_collisions_regardless_of_order():
    # "a/b" sanea a "a_b", que ya es el id (seguro) de otro ítem: no deben
    # terminar compartiendo id pase lo que pase el orden en que aparezcan.
    p = {"targets": [{"id": "a/b", "name": "x"}, {"id": "a_b", "name": "y"}], "ligands": [], "controls": []}
    changed, p = L.ensure_safe_ids(p)
    assert changed is True
    ids = [t["id"] for t in p["targets"]]
    assert len(ids) == len(set(ids))


def test_load_project_self_heals_a_malicious_id_from_a_shared_axd_json(tmp_path):
    proj = str(tmp_path)
    for sub in L.ALL_FOLDERS:
        os.makedirs(os.path.join(proj, sub), exist_ok=True)
    axd = {
        "name": "compartido", "mode": "basic", "layout_version": L.CURRENT_LAYOUT_VERSION,
        "targets": [{"id": "../../../../tmp/evil", "source": "pdb", "pdb": "3PTB", "name": "3PTB",
                     "file": "01_Receptors/3PTB.pdb", "chains": "auto", "cofactors": "auto",
                     "box": {"mode": "auto"}}],
        "ligands": [], "controls": [], "docking": dict(C.DEFAULT_DOCKING),
    }
    json.dump(axd, open(os.path.join(proj, "axd.json"), "w"), indent=2)

    p = C.load_project(proj)  # el punto de entrada que usan CLI, GUI y pipeline

    fixed_id = p["targets"][0]["id"]
    assert fixed_id == L.sanitize_id("../../../../tmp/evil")
    # se reescribió axd.json con el id ya saneado...
    on_disk = json.load(open(os.path.join(proj, "axd.json")))
    assert on_disk["targets"][0]["id"] == fixed_id
    # ...y se guardó un respaldo del original antes de tocarlo.
    assert any(f.startswith("axd.json.bak-") for f in os.listdir(proj))
    lay = L.Layout(proj)
    assert _escapes(lay.receptor_pdbqt(fixed_id), lay.root) is False
