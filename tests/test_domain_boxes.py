"""Fase 3: Box/BoxContext/BoxResult (axd/domain/boxes.py) — reemplazan la cadena
if/elif por 'mode' que había en pipeline/receptors.py. Las funciones _caja/_xyz que se
inyectan aquí son una reimplementación idéntica a la de receptors.py (coords.mean/max-min),
para no depender de ese módulo (que necesita numpy real, lo cual sí tenemos, pero así la
prueba es autocontenida y documenta el contrato de BoxContext)."""
import numpy as np
import pytest

from axd.domain.boxes import Box, BlindBox, LigandBox, ManualBox, ResidueBox, BoxContext

from helpers import linea_pdb


def _xyz(lineas, sin_h=True):
    xs = []
    for l in lineas:
        el = l[76:78].strip() or l[12:16].strip()[:1]
        if sin_h and el.upper() == "H":
            continue
        xs.append([float(l[30:38]), float(l[38:46]), float(l[46:54])])
    return np.array(xs)


def _caja(coords, margen, minimo=0.0):
    c = coords.mean(0)
    s = np.maximum(coords.max(0) - coords.min(0) + margen, minimo)
    return [round(float(v), 3) for v in c], [round(float(v), 1) for v in s]


def _ctx(cuerpo=(), cof=(), ref=()):
    return BoxContext(body=list(cuerpo), cofactors=list(cof), ref=list(ref), box_fn=_caja, xyz_fn=_xyz)


# ---------------------------------------------------------------- fábrica
def test_caja_crear_dispatch():
    assert isinstance(Box.create({"mode": "ligand"}), LigandBox)
    assert isinstance(Box.create({"mode": "residues"}), ResidueBox)
    assert isinstance(Box.create({"mode": "manual"}), ManualBox)
    assert isinstance(Box.create({"mode": "blind"}), BlindBox)


def test_caja_crear_modo_desconocido_cae_a_ciego():
    assert isinstance(Box.create({"mode": "lo-que-sea"}), BlindBox)
    assert isinstance(Box.create({}), BlindBox)  # falta 'mode' -> default 'blind'


# ---------------------------------------------------------------- LigandBox
def test_caja_ligando_calcula_centro_sobre_ref():
    ref = [linea_pdb(1, "C1", "HEM", "A", 100, 10.0, 10.0, 10.0, tipo="HETATM"),
           linea_pdb(2, "C2", "HEM", "A", 100, 12.0, 10.0, 10.0, tipo="HETATM")]
    obj = LigandBox({"ref": "HEM:A", "margin": 10.0, "minimum": 22.0})
    r = obj.calculate(_ctx(ref=ref))
    assert r.ok
    assert r.center == [11.0, 10.0, 10.0]
    assert r.size == [22.0, 22.0, 22.0]  # (12-10+10=12) < mínimo 22 -> se usa el mínimo
    assert "HEM:A" in r.detail and "2 átomos pesados" in r.detail


def test_caja_ligando_sin_ref_falla():
    obj = LigandBox({"ref": "HEM:A"})
    r = obj.calculate(_ctx(ref=[]))
    assert not r.ok
    assert "no encontré el ligando de referencia HEM:A" in r.error


# ---------------------------------------------------------------- ResidueBox
def test_caja_residuos_selecciona_por_cadena_y_numero():
    cuerpo = [
        linea_pdb(1, "CA", "ALA", "A", 50, 1.0, 0.0, 0.0),
        linea_pdb(2, "CA", "GLY", "A", 51, -1.0, 0.0, 0.0),
        linea_pdb(3, "CA", "LEU", "B", 50, 100.0, 0.0, 0.0),  # cadena distinta, no se incluye
    ]
    obj = ResidueBox({"residues": "A:50, A:51", "margin": 8, "minimum": 0})
    r = obj.calculate(_ctx(cuerpo=cuerpo))
    assert r.ok
    assert r.center == [0.0, 0.0, 0.0]
    assert "2 residuos (2 átomos)" in r.detail


def test_caja_residuos_sin_cadena_acepta_cualquiera():
    cuerpo = [linea_pdb(1, "CA", "ALA", "A", 50, 0.0, 0.0, 0.0),
              linea_pdb(2, "CA", "ALA", "B", 50, 2.0, 0.0, 0.0)]
    obj = ResidueBox({"residues": "50", "margin": 0, "minimum": 0})
    r = obj.calculate(_ctx(cuerpo=cuerpo))
    assert r.ok
    assert r.center == [1.0, 0.0, 0.0]  # ambos residuos "50" (de cualquier cadena) cuentan


def test_caja_residuos_ninguno_existe_falla():
    cuerpo = [linea_pdb(1, "CA", "ALA", "A", 50, 0.0, 0.0, 0.0)]
    obj = ResidueBox({"residues": "Z:999"})
    r = obj.calculate(_ctx(cuerpo=cuerpo))
    assert not r.ok
    assert "ninguno de los residuos Z:999 existe" in r.error


def test_caja_residuos_sin_clave_residues_falla_con_mensaje_claro():
    # Antes: KeyError sin atrapar (self.cfg["residues"]) si faltaba la clave —
    # p. ej. un axd.json compartido/editado a mano con box.mode="residues" pero
    # sin 'residues'. Ahora es un BoxResult(ok=False, ...) como cualquier otro fallo.
    obj = ResidueBox({})
    r = obj.calculate(_ctx())
    assert not r.ok
    assert "falta 'residues'" in r.error


def test_caja_residuos_token_malformado_falla_con_mensaje_claro():
    # Antes: ValueError sin atrapar (int("-")) propagándose fuera de calculate().
    obj = ResidueBox({"residues": "A:-"})
    r = obj.calculate(_ctx())
    assert not r.ok
    assert "mal formado" in r.error


# ---------------------------------------------------------------- ManualBox
def test_caja_manual_usa_valores_tal_cual():
    obj = ManualBox({"center": [1, 2, 3], "size": [10, 10, 10]})
    r = obj.calculate(_ctx())
    assert r.ok and r.center == [1, 2, 3] and r.size == [10, 10, 10] and r.detail == "manual"


def test_caja_manual_sin_center_o_size_falla_con_mensaje_claro():
    # Antes: KeyError sin atrapar (self.cfg["center"]/["size"]) si faltaban —
    # misma clase de defecto que el bug original de 'box' ausente.
    r = ManualBox({}).calculate(_ctx())
    assert not r.ok
    assert "center" in r.error and "size" in r.error

    r2 = ManualBox({"center": [1, 2, 3]}).calculate(_ctx())  # falta 'size'
    assert not r2.ok


# ---------------------------------------------------------------- BlindBox
def test_caja_ciega_usa_todo_el_cuerpo_y_cofactores():
    cuerpo = [linea_pdb(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0),
              linea_pdb(2, "CA", "ALA", "A", 2, 10.0, 0.0, 0.0)]
    cof = [linea_pdb(3, "ZN", "ZN", "A", 3, 5.0, 0.0, 0.0, tipo="HETATM")]
    obj = BlindBox({"margin": 10})
    r = obj.calculate(_ctx(cuerpo=cuerpo, cof=cof))
    assert r.ok
    assert r.detail == "ciego (proteína completa)"
    assert r.warning == ""  # caja pequeña, sin aviso


def test_caja_ciega_avisa_si_la_caja_es_enorme():
    cuerpo = [linea_pdb(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0),
              linea_pdb(2, "CA", "ALA", "A", 2, 200.0, 0.0, 0.0)]
    obj = BlindBox({"margin": 10})
    r = obj.calculate(_ctx(cuerpo=cuerpo))
    assert r.ok
    assert "muy grande" in r.warning and "126" in r.warning


def test_caja_ciega_descarta_hidrogenos():
    cuerpo = [linea_pdb(1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0),
              linea_pdb(2, "H1", "ALA", "A", 1, 999.0, 999.0, 999.0, elemento="H")]
    obj = BlindBox({"margin": 0})
    r = obj.calculate(_ctx(cuerpo=cuerpo))
    assert r.center == [0.0, 0.0, 0.0]  # el H lejano no debe mover el centro
