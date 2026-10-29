"""Modo consenso: núcleo puro (axd.consensus) y el paso del pipeline con motores simulados."""
import csv
import math
import os

import pytest

import common
import consensus_step
import docking
from axd import config as C
from axd import consensus as K
from axd import runner as R
from axd.gui.services import reset_run
from axd.layout import Layout


# ---------------------------------------------------------------- núcleo
def test_rangos_con_empates_y_none():
    r = K.rangos({"a": -9.0, "b": -8.0, "c": -8.0, "d": None, "e": -7.0})
    assert r == {"a": 1.0, "b": 2.5, "c": 2.5, "e": 4.0}


def test_ecr_formula_y_orden():
    s = 2.0
    assert K.ecr([1, 1], s) == pytest.approx(2 * math.exp(-0.5) / 2)
    assert K.ecr([1, 1], s) > K.ecr([1, 5], s) > K.ecr([5, 5], s)


def test_sigma_minimo_para_proyectos_chicos():
    assert K.sigma_ecr(100) == 10.0
    assert K.sigma_ecr(5) == 1.0


def test_kendall_tau():
    a = {"x": 1, "y": 2, "z": 3, "w": 4}
    assert K.kendall_tau(a, dict(a)) == pytest.approx(1.0)
    assert K.kendall_tau(a, {"x": 4, "y": 3, "z": 2, "w": 1}) == pytest.approx(-1.0)
    assert K.kendall_tau({"x": 1, "y": 2}, {"x": 1, "y": 2}) is None     # menos de 3
    assert K.kendall_tau(a, {k: 1 for k in a}) is None                    # no discrimina


def test_rmsd_ordenado():
    assert K.rmsd_ordenado([(0, 0, 0), (1, 0, 0)], [(0, 0, 0), (1, 0, 0)]) == 0
    assert K.rmsd_ordenado([(0, 0, 0)], [(3, 4, 0)]) == pytest.approx(5.0)
    assert K.rmsd_ordenado([(0, 0, 0)], []) is None


@pytest.mark.parametrize("spread,rmsd,esperado", [
    (0.0, 1.0, K.ROBUSTO), (0.9, 5.0, K.DISCREPANTE), (0.0, 5.0, K.PARCIAL), (0.9, 1.0, K.PARCIAL),
    (None, 1.0, K.ROBUSTO), (0.1, None, K.ROBUSTO), (None, None, K.SIN_DATOS),
])
def test_veredicto(spread, rmsd, esperado):
    assert K.veredicto(spread, rmsd)[0] == esperado


def _medias():
    # 4 ligandos; vina y vinardo coinciden, ad4 invierte el orden de 'd'
    base = {"a": (-10, -9, -9), "b": (-9, -8, -8), "c": (-8, -7, -7), "d": (-7, -6, -12)}
    medias = {("T", l): dict(zip(("vina", "vinardo", "ad4"), v)) for l, v in base.items()}
    tipos = {("T", l): "ligando" for l in base}
    return medias, tipos


def test_analizar_ranking_y_dispersion():
    medias, tipos = _medias()
    res = K.analizar(medias, tipos, ["vina", "vinardo", "ad4"])
    f = {x["ligando"]: x for x in res["filas"]}
    assert f["a"]["rango_vina"] == 1 and f["d"]["rango_ad4"] == 1 and f["d"]["rango_vina"] == 4
    assert f["d"]["dispersion_rangos"] == 3 and f["d"]["dispersion_norm"] == 1.0
    assert f["a"]["dispersion_rangos"] == 1
    assert f["a"]["orden"] < f["d"]["orden"] or f["d"]["veredicto"] == K.DISCREPANTE
    assert f["d"]["veredicto"] == K.DISCREPANTE      # sin RMSD: sólo cuenta la dispersión
    assert res["tau"]["T"][("vina", "vinardo")] == pytest.approx(1.0)
    assert res["tau"]["T"][("vina", "ad4")] < 1.0
    assert [x["ligando"] for x in res["filas"]][0] in ("a", "b")


def test_analizar_con_poses_y_motor_faltante():
    medias, tipos = _medias()
    medias[("T", "c")]["ad4"] = None                 # AutoDock4 falló con 'c'
    medias[("T", "a")]["ad4"] = -13.0                # y con 'c' fuera, 'a' sigue primero en los tres
    rm = {("T", "a"): {("vina", "vinardo"): 0.8, ("vina", "ad4"): 1.5, ("vinardo", "ad4"): 1.1}}
    res = K.analizar(medias, tipos, ["vina", "vinardo", "ad4"], rm)
    f = {x["ligando"]: x for x in res["filas"]}
    assert f["c"]["veredicto"] == K.INCOMPLETO and "AutoDock4" in f["c"]["motivo"]
    assert "orden" not in f["c"]
    assert f["a"]["rmsd_max"] == 1.5 and f["a"]["veredicto"] == K.ROBUSTO
    assert f["a"]["n_motores"] == 3 and f["c"]["n_motores"] == 2
    assert K.resumen_veredictos(res["filas"])[K.INCOMPLETO] == 1


def test_motores_validos_y_corridas_extra():
    assert K.motores_validos(["ad4", "x", "vina", "ad4"]) == ["vina", "ad4"]
    assert K.corridas_extra(10, 3, ["vina", "vinardo", "ad4"]) == {"vinardo": 30, "ad4": 30}
    assert K.corridas_extra(10, 3, ["vina", "vinardo"], principal_ya_corre=False) == {"vina": 30, "vinardo": 30}


# ---------------------------------------------------------------- runner / config / layout
def test_pasos_planeados_consenso_es_opt_in(tmp_path):
    ruta = str(tmp_path / "p")
    C.new_project(ruta, "X")
    p = C.load_project(ruta)
    assert "consensus" not in R.pasos_planeados(p)
    assert p["docking"]["consensus"]["enabled"] is False
    p["docking"]["consensus"]["enabled"] = True
    pasos = R.pasos_planeados(p)
    assert pasos.index("docking") < pasos.index("consensus") < pasos.index("summary")


def test_rutas_de_consenso_no_chocan_con_results(tmp_path):
    lay = Layout(str(tmp_path))
    a = lay.consensus_result_pdbqt("vinardo", "T", "L", 42)
    assert a.endswith(os.path.join("04_Docking", "Consensus", "vinardo", "T", "L_s42.pdbqt"))
    assert a != lay.result_pdbqt("T", "L", 42)
    assert "Consensus" in lay.consensus_redocking_pdbqt("ad4", "T", 1)


# ---------------------------------------------------------------- paso completo con motores simulados
def _pdbqt(path, energia, desplazar=0.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomos = [("C", 0.0, 0.0, 0.0), ("C", 1.5, 0.0, 0.0), ("OA", 2.2, 1.2, 0.0)]
    lines = ["MODEL 1", f"REMARK minimizedAffinity {energia}"]
    for i, (t, x, y, z) in enumerate(atomos, 1):
        lines.append(f"ATOM  {i:5d}  {t:<3s} LIG L   1    {x + desplazar:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00    +0.000 {t:<2s}")
    lines.append("ENDMDL")
    open(path, "w").write("\n".join(lines) + "\n")


class FakeMotor:
    """Reemplaza docking.Motor: escribe una pose sintética con una energía distinta por motor."""
    ENERGIAS = {"smina": 0.0, "vinardo": 1.0, "ad4": -2.0}
    creados = []

    def __init__(self, P, ligandos, forzar=None):
        self.nombre = "ad4" if forzar == "ad4" else "smina"
        self.scoring = "vinardo" if forzar == "vinardo" else None
        self.clave = forzar
        FakeMotor.creados.append(forzar)

    def disponible(self):
        return True

    def etiqueta(self, d):
        return f"fake {self.clave}"

    def dockear(self, diana_id, rec, lig, caja, salida, semilla, d, rehacer=False):
        base = {"ligA": -9.0, "ligB": -8.0, "ligC": -7.0, "ctl": -7.5}[os.path.basename(lig)[:-6]]
        e = base + self.ENERGIAS[self.clave]
        desplazo = 4.0 if self.clave == "ad4" else 0.0   # AD4 pone la pose lejos → RMSD grande
        _pdbqt(salida, e, desplazo)
        return e, False


@pytest.fixture
def proy(tmp_path, monkeypatch):
    ruta = str(tmp_path / "p")
    C.new_project(ruta, "Consenso")
    p = C.load_project(ruta)
    p["targets"] = [{"id": "T1", "source": "pdb", "pdb": "T1", "chains": "A", "cofactors": [],
                     "box": {"mode": "manual"}}]
    p["ligands"] = [{"id": i, "name": i, "source": "smiles", "smiles": "CCO"} for i in ("ligA", "ligB", "ligC")]
    p["controls"] = [{"id": "ctl", "name": "ctl", "source": "smiles", "smiles": "CCO", "target": "T1"}]
    p["docking"].update(seeds=[1, 2], motor_usado="smina")
    p["docking"]["consensus"] = {"enabled": True, "engines": ["vina", "vinardo", "ad4"]}
    C.save_project(ruta, p)
    lay = Layout(ruta)
    import json
    os.makedirs(os.path.dirname(lay.boxes_json()), exist_ok=True)
    json.dump({"T1": {"center": [0, 0, 0], "size": [20, 20, 20], "mode": "manual"}}, open(lay.boxes_json(), "w"))
    for nombre in ("ligA", "ligB", "ligC"):
        _pdbqt(lay.ligand_pdbqt(nombre), 0)
    _pdbqt(lay.ligand_pdbqt("ctl", True), 0)
    os.makedirs(os.path.dirname(lay.receptor_pdbqt("T1")), exist_ok=True)
    open(lay.receptor_pdbqt("T1"), "w").write("REMARK\n")
    # el docking normal (motor principal = smina) ya corrió
    for lig, base in (("ligA", -9.0), ("ligB", -8.0), ("ligC", -7.0), ("ctl", -7.5)):
        for s in (1, 2):
            _pdbqt(lay.result_pdbqt("T1", lig, s), base)
    FakeMotor.creados = []
    monkeypatch.setattr(docking, "Motor", FakeMotor)
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: (
        type("RP", (), {"max_workers": 2, "cpu_per_worker": 1, "reserved_cores": 0, "notes": []})(),
        type("G", (), {"policy": type("Pol", (), {"poll_seconds": 0.01})(),
                       "read": lambda self: __import__("axd.thermal", fromlist=["x"]).ThermalReading(
                           None, None, __import__("axd.thermal", fromlist=["x"]).Decision.RUN, "")})()))
    return ruta


def _csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def test_paso_consenso_extremo_a_extremo(proy, capsys):
    P = common.Project(proy)
    assert consensus_step.run(P) == 0
    lay = Layout(proy)
    assert sorted(set(FakeMotor.creados)) == ["ad4", "vinardo"]       # el principal no se repite
    for mo in ("vinardo", "ad4"):
        assert os.path.exists(lay.consensus_result_pdbqt(mo, "T1", "ligA", 1))
    filas = _csv(lay.consensus_summary_csv())
    assert {f["ligando"] for f in filas} == {"ligA", "ligB", "ligC", "ctl"}
    a = next(f for f in filas if f["ligando"] == "ligA")
    assert a["rango_vina"] == "1.0" and a["orden"] == "1"
    assert float(a["dG_vinardo"]) == pytest.approx(-8.0) and float(a["dG_ad4"]) == pytest.approx(-11.0)
    assert float(a["rmsd_max"]) > 2.0                                   # AD4 puso la pose lejos
    poses = _csv(lay.consensus_poses_csv())
    assert {(p["motor_a"], p["motor_b"]) for p in poses} == {("vina", "vinardo"), ("vina", "ad4"), ("vinardo", "ad4")}
    assert any(p["motor_a"] == "vina" and p["motor_b"] == "vinardo" and float(p["rmsd"]) < 0.01 for p in poses)
    assert _csv(lay.consensus_tau_csv())
    assert {r["motor"] for r in _csv(lay.consensus_engines_csv())} == {"vina", "vinardo", "ad4"}
    import json
    meta = json.load(open(lay.consensus_meta_json()))
    assert meta["motores"] == ["vina", "vinardo", "ad4"] and meta["principal"] == "vina"
    assert "Veredictos" in capsys.readouterr().out


def test_paso_consenso_es_reanudable(proy):
    P = common.Project(proy)
    consensus_step.run(P)
    llamadas = []
    original = FakeMotor.dockear
    FakeMotor.dockear = lambda self, *a, **k: (llamadas.append(1), original(self, *a, **k))[1]
    try:
        consensus_step.run(P)
    finally:
        FakeMotor.dockear = original
    # las corridas ya completas se saltan dentro de Motor.dockear real; aquí sólo comprobamos que el
    # paso no falla ni rompe los archivos al repetirse
    assert _csv(Layout(proy).consensus_summary_csv())


def test_paso_desactivado_no_hace_nada(proy):
    P = common.Project(proy)
    P.cfg["docking"]["consensus"]["enabled"] = False
    P.save()
    P = common.Project(proy)
    assert consensus_step.run(P) == 0
    assert not os.path.exists(Layout(proy).consensus_summary_csv())


def test_motor_principal_ad4_corre_vina_aparte(proy):
    P = common.Project(proy)
    P.cfg["docking"]["motor_usado"] = "ad4"
    assert consensus_step.motor_principal(P) == "ad4"
    P.cfg["docking"]["motor_usado"] = "vina-gpu"
    assert consensus_step.motor_principal(P) == "vina"


def test_eliminar_ultimo_procesamiento_borra_el_consenso(proy):
    P = common.Project(proy)
    consensus_step.run(P)
    lay = Layout(proy)
    assert any("Consensus" in f for f in reset_run.files_to_remove(proy))
    reset_run.remove(proy)
    assert not os.path.exists(lay.consensus_dir()) and not os.path.exists(lay.consensus_summary_csv())


def test_smina_recibe_vinardo_y_el_motor_forzado_ignora_el_dispositivo(proy, monkeypatch, tmp_path):
    import importlib
    real = importlib.reload(docking)                   # deshace el FakeMotor del fixture
    visto = {}

    def falso_run(cmd, cwd=None, timeout=None):
        visto["cmd"] = cmd
        _pdbqt(os.path.join(cwd, "o.pdbqt"), -7.1)
        return 0, "ok"

    monkeypatch.setattr(real, "run_cmd", falso_run)
    monkeypatch.setattr(real, "_smina", lambda: "smina")
    rec, lig = tmp_path / "r.pdbqt", tmp_path / "l.pdbqt"
    rec.write_text("x")
    lig.write_text("x")
    d = dict(exhaustiveness=8, num_modes=3, energy_range=4, cpu=0)
    caja = {"center": [0, 0, 0], "size": [10, 10, 10]}
    e, _ = real.correr_smina("smina", str(rec), str(lig), caja, str(tmp_path / "o" / "x_s1.pdbqt"), 1, d, scoring="vinardo")
    assert e == -7.1 and visto["cmd"][-2:] == ["--scoring", "vinardo"]
    visto.clear()
    real.correr_smina("smina", str(rec), str(lig), caja, str(tmp_path / "o" / "y_s1.pdbqt"), 1, d)
    assert "--scoring" not in visto["cmd"]
    P = common.Project(proy)
    m = real.Motor(P, [], forzar="vinardo")
    assert (m.nombre, m.scoring, m.forzado) == ("smina", "vinardo", True)
    assert "vinardo" in m.etiqueta(d)


def test_reporte_incluye_la_seccion_de_consenso(proy, tmp_path):
    import report
    P = common.Project(proy)
    assert consensus_step.run(P) == 0
    datos = report.recolectar(common.Project(proy))
    assert datos["consenso"]["motores"] == ["vina", "vinardo", "ad4"]
    texto = " ".join(report.texto_metodos(datos))
    assert "ECR" in texto and "Vinardo" in texto and "Robusto" in texto
    refs = " ".join(report.referencias(datos))
    assert "Exponential consensus ranking" in refs and "Vinardo" in refs and "Consensus docking" in refs
    salida = str(tmp_path / "r.pdf")
    report.generar_pdf(datos, salida, str(tmp_path / "fig"))
    import pymupdf as fitz
    doc = fitz.open(salida)
    txt = "\n".join(pg.get_text() for pg in doc)
    assert "Consenso entre motores" in txt and "Veredictos" in txt
    assert "Acuerdo de poses entre motores" in txt
    assert os.path.exists(str(tmp_path / "fig" / "consenso_T1.png"))
    open(os.path.join(os.environ.get("AXD_SAMPLE_DIR", str(tmp_path)), "consenso_demo.pdf"), "wb").write(open(salida, "rb").read())


def test_reporte_sin_consenso_no_cambia(proy, tmp_path):
    import report
    datos = report.recolectar(common.Project(proy))
    assert datos["consenso"] is None
    salida = str(tmp_path / "r.pdf")
    report.generar_pdf(datos, salida, str(tmp_path / "fig"))
    import pymupdf as fitz
    txt = "\n".join(pg.get_text() for pg in fitz.open(salida))
    assert "Consenso entre motores" not in txt
