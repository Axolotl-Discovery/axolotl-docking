"""Fase 2: fidelidad de ida y vuelta del modelo de dominio típado (axd/domain/models.py).

dict -> dataclass -> dict nunca debe perder ni reordenar información, incluidas claves
no modeladas (deben sobrevivir en `.extra`) y sub-objetos anidados (caja, docking)."""
from axd.domain.models import CajaConfig, Diana, Ligando, ParamsDocking, Proyecto


def test_caja_config_roundtrip_con_extra():
    d = {"modo": "ligando", "ref": "HEM:A", "margen": 10.0, "clave_futura": "algo"}
    c = CajaConfig.from_dict(d)
    assert c.modo == "ligando" and c.ref == "HEM:A" and c.margen == 10.0
    assert c.extra == {"clave_futura": "algo"}
    assert c.to_dict() == d


def test_caja_config_defaults_sin_dict():
    c = CajaConfig.from_dict(None)
    assert c.modo == "auto"
    assert c.to_dict() == {"modo": "auto"}  # campos None no se escriben


def test_diana_roundtrip_con_extra_y_caja():
    d = {"id": "d1", "fuente": "pdb", "nombre": "Prueba", "pdb": "1ABC", "cadenas": "A",
         "cofactores": ["HEM:A"], "caja": {"modo": "ciego", "margen": 10}, "campo_nuevo": 42}
    diana = Diana.from_dict(d)
    assert diana.id == "d1" and diana.caja.modo == "ciego"
    assert diana.cofactores == ["HEM:A"]  # campo modelado, no va a extra
    assert diana.extra == {"campo_nuevo": 42}
    assert diana.to_dict() == d


def test_ligando_roundtrip_control():
    d = {"id": "c1", "nombre": "Control A", "fuente": "pubchem", "consulta": "aspirin",
         "cid": "2244", "diana": "d1", "nota_extra": True}
    l = Ligando.from_dict(d)
    assert l.diana == "d1" and l.extra["nota_extra"] is True
    assert l.to_dict() == d


def test_params_docking_defaults_y_roundtrip():
    p = ParamsDocking.from_dict(None)
    assert p.motor == "smina" and p.cpu == 0 and p.semillas == [42, 2026, 777]
    d = {"motor": "ad4", "semillas": [1, 2], "exhaustiveness": 16, "num_modes": 5,
         "energy_range": 3, "cpu": 4, "ad4_runs": 10, "ad4_evals": 1000000, "futuro": "x"}
    p2 = ParamsDocking.from_dict(d)
    assert p2.to_dict() == d


def test_proyecto_roundtrip_completo():
    d = {
        "nombre": "Proyecto X", "modo": "basico", "creado": "2026-01-01", "version_axd": "1.3.0",
        "layout_version": 2,
        "dianas": [{"id": "d1", "fuente": "pdb", "nombre": "D1", "pdb": "1ABC",
                    "cadenas": "auto", "cofactores": "auto", "caja": {"modo": "auto"}}],
        "ligandos": [{"id": "l1", "nombre": "L1", "fuente": "smiles", "smiles": "CCO"}],
        "controles": [{"id": "c1", "nombre": "C1", "fuente": "ccd", "codigo": "HEM"}],
        "docking": {"motor": "smina", "semillas": [42], "exhaustiveness": 8, "num_modes": 9,
                    "energy_range": 4, "cpu": 0, "ad4_runs": 20, "ad4_evals": 2500000},
        "clave_del_futuro": {"a": 1},
    }
    p = Proyecto.from_dict(d)
    assert p.nombre == "Proyecto X" and len(p.dianas) == 1 and p.dianas[0].id == "d1"
    assert p.extra == {"clave_del_futuro": {"a": 1}}
    assert p.to_dict() == d


def test_proyecto_vacio_no_pierde_nada():
    d = {"nombre": "Vacío"}
    p = Proyecto.from_dict(d)
    assert p.dianas == [] and p.ligandos == [] and p.controles == []
    salida = p.to_dict()
    assert salida["nombre"] == "Vacío"
    assert salida["dianas"] == [] and salida["ligandos"] == [] and salida["controles"] == []
    assert salida["docking"] == ParamsDocking().to_dict()
