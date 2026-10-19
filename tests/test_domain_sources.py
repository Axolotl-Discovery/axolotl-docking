"""Fase 3: TargetSource/LigandSource (axd/domain/sources.py) — reemplazan las cadenas
if/elif por 'source' que había en pipeline/download.py. Se prueban con un `net` doble
(fake_net, de conftest.py), sin tocar la red."""
import pytest

from axd.domain.sources import (AlphafoldTargetSource, FileTargetSource, CcdLigandSource,
                                 TargetSource, LigandSource, PdbTargetSource, PubchemLigandSource)


# ---------------------------------------------------------------- fábrica
def test_fuente_diana_crear_dispatch():
    assert isinstance(TargetSource.create("pdb"), PdbTargetSource)
    assert isinstance(TargetSource.create("alphafold"), AlphafoldTargetSource)
    assert isinstance(TargetSource.create("file"), FileTargetSource)
    assert isinstance(TargetSource.create("algo-desconocido"), FileTargetSource)  # por defecto


def test_fuente_ligando_crear_dispatch():
    assert isinstance(LigandSource.create("ccd"), CcdLigandSource)
    assert isinstance(LigandSource.create("pubchem"), PubchemLigandSource)
    assert LigandSource.create("file") is None  # ya tiene su archivo
    assert LigandSource.create("smiles") is None   # se resuelve en otro paso


# ---------------------------------------------------------------- PdbTargetSource
def test_pdb_diana_descarga_pdb_directo(fake_net, tmp_path):
    d = {"id": "d1", "pdb": "1ABC"}
    arch = PdbTargetSource().download(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.pdb")
    assert fake_net.llamadas[0][1] == "https://files.rcsb.org/download/1ABC.pdb"


def test_pdb_diana_cae_a_cif_si_pdb_falla(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.pdb")
    d = {"id": "d1", "pdb": "1ABC"}
    arch = PdbTargetSource().download(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.cif")


def test_pdb_diana_falla_con_mensaje_exacto_si_ambos_fallan(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.pdb")
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.cif")
    d = {"id": "d1", "pdb": "1ABC"}
    with pytest.raises(IOError, match=r"^no se pudo descargar 1ABC de RCSB$"):
        PdbTargetSource().download(d, str(tmp_path), fake_net)


def test_pdb_diana_describir():
    assert PdbTargetSource().describe({"pdb": "1ABC"}, "/x/d1.pdb") == "RCSB 1ABC.pdb"


# ---------------------------------------------------------------- AlphafoldTargetSource
def test_alphafold_diana_descarga_ok(fake_net, tmp_path, monkeypatch):
    import json
    import io

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=None):
        assert "P12345" in url
        return FakeResp(json.dumps([{"pdbUrl": "https://alphafold.example/AF-P12345.pdb"}]).encode())

    monkeypatch.setattr("axd.domain.sources.urllib.request.urlopen", fake_urlopen)
    d = {"id": "d1", "uniprot": "P12345"}
    arch = AlphafoldTargetSource().download(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.pdb")
    assert fake_net.llamadas[0][1] == "https://alphafold.example/AF-P12345.pdb"


def test_alphafold_diana_falla_con_excepcion_envuelta(monkeypatch, fake_net, tmp_path):
    def fake_urlopen(url, timeout=None):
        raise OSError("sin conexión")

    monkeypatch.setattr("axd.domain.sources.urllib.request.urlopen", fake_urlopen)
    d = {"id": "d1", "uniprot": "P12345"}
    with pytest.raises(IOError, match=r"AlphaFold P12345"):
        AlphafoldTargetSource().download(d, str(tmp_path), fake_net)


# ---------------------------------------------------------------- FileTargetSource
def test_archivo_diana_siempre_falla():
    with pytest.raises(IOError, match=r"falta el archivo local ruta/que/no/existe\.pdb"):
        FileTargetSource().download({"file": "ruta/que/no/existe.pdb"}, "/x", net=None)


# ---------------------------------------------------------------- CcdLigandSource / PubchemLigandSource
def test_ccd_ligando_prueba_ideal_y_cae_a_model(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/HEM_ideal.sdf")
    l = {"id": "lig1", "code": "HEM"}
    ruta, desc = CcdLigandSource().download(l, str(tmp_path), fake_net)
    assert ruta == str(tmp_path / "lig1.sdf")
    assert "coordenadas de un cristal" in desc


def test_ccd_ligando_falla_si_codigo_no_existe(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/ZZZ_ideal.sdf")
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/ZZZ_model.sdf")
    with pytest.raises(IOError, match=r"el código PDB 'ZZZ' no existe"):
        CcdLigandSource().download({"id": "lig1", "code": "ZZZ"}, str(tmp_path), fake_net)


def test_pubchem_ligando_ok(fake_net, tmp_path):
    l = {"id": "lig1", "query": "aspirin", "cid": "2244"}
    ruta, desc = PubchemLigandSource().download(l, str(tmp_path), fake_net)
    assert ruta.endswith(".sdf")
    assert "PubChem 'aspirin'" in desc
    assert fake_net.llamadas[0] == ("pubchem_sdf", "2244", str(tmp_path / "lig1"))


def test_pubchem_ligando_falla_con_mensaje_envuelto(fake_net, tmp_path):
    fake_net.fallos.add("no-existe")
    l = {"id": "lig1", "query": "no-existe"}
    with pytest.raises(IOError, match=r"PubChem no encontró 'no-existe'"):
        PubchemLigandSource().download(l, str(tmp_path), fake_net)


def test_pubchem_limita_tasa_y_ccd_no():
    assert PubchemLigandSource.rate_limited is True
    assert CcdLigandSource.rate_limited is False
