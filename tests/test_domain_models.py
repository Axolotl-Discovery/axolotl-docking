"""Fase 2: fidelidad de ida y vuelta del modelo de dominio típado (axd/domain/models.py).

dict -> dataclass -> dict nunca debe perder ni reordenar información, incluidas claves
no modeladas (deben sobrevivir en `.extra`) y sub-objetos anidados (caja, docking)."""
from axd.domain.models import BoxConfig, Target, Ligand, DockingParams, Project


def test_caja_config_roundtrip_con_extra():
    d = {"mode": "ligand", "ref": "HEM:A", "margin": 10.0, "clave_futura": "algo"}
    c = BoxConfig.from_dict(d)
    assert c.mode == "ligand" and c.ref == "HEM:A" and c.margin == 10.0
    assert c.extra == {"clave_futura": "algo"}
    assert c.to_dict() == d


def test_caja_config_defaults_sin_dict():
    c = BoxConfig.from_dict(None)
    assert c.mode == "auto"
    assert c.to_dict() == {"mode": "auto"}  # campos None no se escriben


def test_diana_roundtrip_con_extra_y_caja():
    d = {"id": "d1", "source": "pdb", "name": "Prueba", "pdb": "1ABC", "chains": "A",
         "cofactors": ["HEM:A"], "box": {"mode": "blind", "margin": 10}, "campo_nuevo": 42}
    diana = Target.from_dict(d)
    assert diana.id == "d1" and diana.box.mode == "blind"
    assert diana.cofactors == ["HEM:A"]  # campo modelado, no va a extra
    assert diana.extra == {"campo_nuevo": 42}
    assert diana.to_dict() == d


def test_ligando_roundtrip_control():
    d = {"id": "c1", "name": "Control A", "source": "pubchem", "query": "aspirin",
         "cid": "2244", "target": "d1", "nota_extra": True}
    l = Ligand.from_dict(d)
    assert l.target == "d1" and l.extra["nota_extra"] is True
    assert l.to_dict() == d


def test_params_docking_defaults_y_roundtrip():
    p = DockingParams.from_dict(None)
    assert p.engine == "smina" and p.cpu == 0 and p.seeds == [42, 2026, 777]
    d = {"engine": "ad4", "seeds": [1, 2], "exhaustiveness": 16, "num_modes": 5,
         "energy_range": 3, "cpu": 4, "ad4_runs": 10, "ad4_evals": 1000000, "futuro": "x"}
    p2 = DockingParams.from_dict(d)
    assert p2.to_dict() == d


def test_proyecto_roundtrip_completo():
    d = {
        "name": "Proyecto X", "mode": "basic", "created": "2026-01-01", "axd_version": "1.3.0",
        "layout_version": 2,
        "targets": [{"id": "d1", "source": "pdb", "name": "D1", "pdb": "1ABC",
                    "chains": "auto", "cofactors": "auto", "box": {"mode": "auto"}}],
        "ligands": [{"id": "l1", "name": "L1", "source": "smiles", "smiles": "CCO"}],
        "controls": [{"id": "c1", "name": "C1", "source": "ccd", "code": "HEM"}],
        "docking": {"engine": "smina", "seeds": [42], "exhaustiveness": 8, "num_modes": 9,
                    "energy_range": 4, "cpu": 0, "ad4_runs": 20, "ad4_evals": 2500000},
        "clave_del_futuro": {"a": 1},
    }
    p = Project.from_dict(d)
    assert p.name == "Proyecto X" and len(p.targets) == 1 and p.targets[0].id == "d1"
    assert p.extra == {"clave_del_futuro": {"a": 1}}
    assert p.to_dict() == d


def test_proyecto_vacio_no_pierde_nada():
    d = {"name": "Vacío"}
    p = Project.from_dict(d)
    assert p.targets == [] and p.ligands == [] and p.controls == []
    salida = p.to_dict()
    assert salida["name"] == "Vacío"
    assert salida["targets"] == [] and salida["ligands"] == [] and salida["controls"] == []
    assert salida["docking"] == DockingParams().to_dict()
