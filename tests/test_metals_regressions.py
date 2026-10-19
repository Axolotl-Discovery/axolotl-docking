"""Regresión (encontrada y arreglada en la Fase 4): pipeline/metals.py::_base_ad4() colgaba
la máquina cuando autodock4 no estaba instalado.

Causa original: `os.path.dirname(os.path.dirname(herramienta("autodock4") or "/x/y"))` daba
"/" cuando la herramienta no se encontraba, y luego `glob.glob("/**/AD4.1_bound.dat",
recursive=True)` intentaba recorrer todo el disco. El arreglo: sólo se añade el candidato
derivado de autodock4 cuando SÍ se encontró, y cada candidato se descarta con `os.path.isdir`
antes de globbear."""
import os
import time

import metals
import axd.infra.net as net_mod


def _sin_red(monkeypatch):
    """Hace que axd.infra.net.download() falle siempre, sin tocar la red."""
    def falla(*a, **k):
        raise IOError("sin red en la prueba")
    monkeypatch.setattr(net_mod, "download", falla)


def test_base_ad4_no_cuelga_sin_autodock4_ni_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(metals, "tool", lambda *a, **k: None)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "no-existe" / p.lstrip("~/")))
    _sin_red(monkeypatch)

    t0 = time.time()
    resultado = metals._base_ad4()
    dt = time.time() - t0

    assert resultado is None
    assert dt < 2.0, f"_base_ad4() tardó {dt:.2f}s: parece estar recorriendo el filesystem completo"


def test_base_ad4_descarta_candidato_inexistente_de_autodock4(tmp_path, monkeypatch):
    """Si autodock4 SÍ se encuentra pero en una ruta rara, el candidato derivado
    (dirname(dirname(ruta))) puede no existir: debe descartarse sin reventar ni colgarse."""
    ruta_falsa = "/no/existe/bin/autodock4"
    monkeypatch.setattr(metals, "tool", lambda *a, **k: ruta_falsa)
    monkeypatch.setattr(os.path, "expanduser",
                         lambda p: str(tmp_path / "tampoco-existe" / p.lstrip("~/")))
    _sin_red(monkeypatch)

    t0 = time.time()
    resultado = metals._base_ad4()
    assert resultado is None
    assert time.time() - t0 < 2.0


def test_base_ad4_encuentra_el_archivo_cuando_existe(tmp_path, monkeypatch):
    adfr = tmp_path / "adfr"
    (adfr / "sub").mkdir(parents=True)
    destino = adfr / "sub" / "AD4.1_bound.dat"
    destino.write_text("atom_par OA  ...\n")

    def fake_expanduser(p):
        if p == "~/tools/ADFRsuite-1.0":
            return str(adfr)
        return str(tmp_path / "config" / p.lstrip("~/"))

    monkeypatch.setattr(metals, "tool", lambda *a, **k: None)
    monkeypatch.setattr(os.path, "expanduser", fake_expanduser)

    resultado = metals._base_ad4()
    assert resultado == str(destino)


def test_base_ad4_usa_cache_si_ya_existe(tmp_path, monkeypatch):
    cache = tmp_path / "config" / "AD4.1_bound.dat"
    cache.parent.mkdir(parents=True)
    cache.write_text("atom_par OA  ...\n")

    def fake_expanduser(p):
        if p == "~/tools/ADFRsuite-1.0":
            return str(tmp_path / "no-existe-adfr")
        if p == "~/.config/axolotl-docking/AD4.1_bound.dat":
            return str(cache)
        return p

    monkeypatch.setattr(metals, "tool", lambda *a, **k: None)
    monkeypatch.setattr(os.path, "expanduser", fake_expanduser)

    assert metals._base_ad4() == str(cache)
