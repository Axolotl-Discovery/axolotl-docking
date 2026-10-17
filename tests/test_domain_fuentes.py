"""Fase 3: FuenteDiana/FuenteLigando (axd/domain/fuentes.py) — reemplazan las cadenas
if/elif por 'fuente' que había en pipeline/descargar.py. Se prueban con un `net` doble
(fake_net, de conftest.py), sin tocar la red."""
import pytest

from axd.domain.fuentes import (FuenteAlphafoldDiana, FuenteArchivoDiana, FuenteCcdLigando,
                                 FuenteDiana, FuenteLigando, FuentePdbDiana, FuentePubchemLigando)


# ---------------------------------------------------------------- fábrica
def test_fuente_diana_crear_dispatch():
    assert isinstance(FuenteDiana.crear("pdb"), FuentePdbDiana)
    assert isinstance(FuenteDiana.crear("alphafold"), FuenteAlphafoldDiana)
    assert isinstance(FuenteDiana.crear("archivo"), FuenteArchivoDiana)
    assert isinstance(FuenteDiana.crear("algo-desconocido"), FuenteArchivoDiana)  # por defecto


def test_fuente_ligando_crear_dispatch():
    assert isinstance(FuenteLigando.crear("ccd"), FuenteCcdLigando)
    assert isinstance(FuenteLigando.crear("pubchem"), FuentePubchemLigando)
    assert FuenteLigando.crear("archivo") is None  # ya tiene su archivo
    assert FuenteLigando.crear("smiles") is None   # se resuelve en otro paso


# ---------------------------------------------------------------- FuentePdbDiana
def test_pdb_diana_descarga_pdb_directo(fake_net, tmp_path):
    d = {"id": "d1", "pdb": "1ABC"}
    arch = FuentePdbDiana().descargar(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.pdb")
    assert fake_net.llamadas[0][1] == "https://files.rcsb.org/download/1ABC.pdb"


def test_pdb_diana_cae_a_cif_si_pdb_falla(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.pdb")
    d = {"id": "d1", "pdb": "1ABC"}
    arch = FuentePdbDiana().descargar(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.cif")


def test_pdb_diana_falla_con_mensaje_exacto_si_ambos_fallan(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.pdb")
    fake_net.fallos.add("https://files.rcsb.org/download/1ABC.cif")
    d = {"id": "d1", "pdb": "1ABC"}
    with pytest.raises(IOError, match=r"^no se pudo descargar 1ABC de RCSB$"):
        FuentePdbDiana().descargar(d, str(tmp_path), fake_net)


def test_pdb_diana_describir():
    assert FuentePdbDiana().describir({"pdb": "1ABC"}, "/x/d1.pdb") == "RCSB 1ABC.pdb"


# ---------------------------------------------------------------- FuenteAlphafoldDiana
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

    monkeypatch.setattr("axd.domain.fuentes.urllib.request.urlopen", fake_urlopen)
    d = {"id": "d1", "uniprot": "P12345"}
    arch = FuenteAlphafoldDiana().descargar(d, str(tmp_path), fake_net)
    assert arch == str(tmp_path / "d1.pdb")
    assert fake_net.llamadas[0][1] == "https://alphafold.example/AF-P12345.pdb"


def test_alphafold_diana_falla_con_excepcion_envuelta(monkeypatch, fake_net, tmp_path):
    def fake_urlopen(url, timeout=None):
        raise OSError("sin conexión")

    monkeypatch.setattr("axd.domain.fuentes.urllib.request.urlopen", fake_urlopen)
    d = {"id": "d1", "uniprot": "P12345"}
    with pytest.raises(IOError, match=r"AlphaFold P12345"):
        FuenteAlphafoldDiana().descargar(d, str(tmp_path), fake_net)


# ---------------------------------------------------------------- FuenteArchivoDiana
def test_archivo_diana_siempre_falla():
    with pytest.raises(IOError, match=r"falta el archivo local ruta/que/no/existe\.pdb"):
        FuenteArchivoDiana().descargar({"archivo": "ruta/que/no/existe.pdb"}, "/x", net=None)


# ---------------------------------------------------------------- FuenteCcdLigando / FuentePubchemLigando
def test_ccd_ligando_prueba_ideal_y_cae_a_model(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/HEM_ideal.sdf")
    l = {"id": "lig1", "codigo": "HEM"}
    ruta, desc = FuenteCcdLigando().descargar(l, str(tmp_path), fake_net)
    assert ruta == str(tmp_path / "lig1.sdf")
    assert "coordenadas de un cristal" in desc


def test_ccd_ligando_falla_si_codigo_no_existe(fake_net, tmp_path):
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/ZZZ_ideal.sdf")
    fake_net.fallos.add("https://files.rcsb.org/ligands/download/ZZZ_model.sdf")
    with pytest.raises(IOError, match=r"el código PDB 'ZZZ' no existe"):
        FuenteCcdLigando().descargar({"id": "lig1", "codigo": "ZZZ"}, str(tmp_path), fake_net)


def test_pubchem_ligando_ok(fake_net, tmp_path):
    l = {"id": "lig1", "consulta": "aspirin", "cid": "2244"}
    ruta, desc = FuentePubchemLigando().descargar(l, str(tmp_path), fake_net)
    assert ruta.endswith(".sdf")
    assert "PubChem 'aspirin'" in desc
    assert fake_net.llamadas[0] == ("pubchem_sdf", "2244", str(tmp_path / "lig1"))


def test_pubchem_ligando_falla_con_mensaje_envuelto(fake_net, tmp_path):
    fake_net.fallos.add("no-existe")
    l = {"id": "lig1", "consulta": "no-existe"}
    with pytest.raises(IOError, match=r"PubChem no encontró 'no-existe'"):
        FuentePubchemLigando().descargar(l, str(tmp_path), fake_net)


def test_pubchem_limita_tasa_y_ccd_no():
    assert FuentePubchemLigando.limitar_tasa is True
    assert FuenteCcdLigando.limitar_tasa is False
