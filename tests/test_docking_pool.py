"""Fase 6: pool real de corridas en pipeline/docking.py (matriz/redocking + ThermalGuard).

No depende de smina/AutoDock4/RDKit reales: Motor, _plan_recursos y rmsd_simetrico se
sustituyen por dobles deterministas; sólo se prueba la orquestación (concurrencia,
conteos, CSV, logs), que es lo que cambió en esta fase."""
import csv
import io
import os
import threading
import time
from contextlib import redirect_stdout

import pytest

import docking
from axd.thermal import Decision, ThermalReading
from axd.tuning import ResourcePlan


# ---------------------------------------------------------------- dobles
class FakeGuard:
    class _Pol:
        poll_seconds = 0.02

    def __init__(self, secuencia=()):
        self.policy = self._Pol()
        self._secuencia = list(secuencia)
        self.lecturas = []

    def read(self):
        d = self._secuencia.pop(0) if self._secuencia else Decision.RUN
        self.lecturas.append(d)
        return ThermalReading(None, None, d, "" if d == Decision.RUN else f"estado {d}")


class ConcurrencyTracker:
    def __init__(self):
        self.en_vuelo = 0
        self.max_visto = 0
        self.lock = threading.Lock()
        self.llamadas = []

    def entrar(self, etiqueta):
        with self.lock:
            self.en_vuelo += 1
            self.max_visto = max(self.max_visto, self.en_vuelo)
            self.llamadas.append(etiqueta)
        time.sleep(0.03)  # fuerza superposición real entre hilos

    def salir(self):
        with self.lock:
            self.en_vuelo -= 1


class FakeLayout:
    def __init__(self, raiz):
        self.raiz = raiz

    def result_pdbqt(self, diana_id, lig_id, s):
        return os.path.join(self.raiz, f"{diana_id}_{lig_id}_{s}.pdbqt")

    def redocking_result_pdbqt(self, diana_id, s):
        return os.path.join(self.raiz, f"redock_{diana_id}_{s}.pdbqt")

    def redocking_summary_csv(self):
        return os.path.join(self.raiz, "redocking.csv")

    def results_backup_dir(self, ts):
        return os.path.join(self.raiz, "backup", ts)

    def target_results_dir(self, diana_id):
        return os.path.join(self.raiz, diana_id)


class FakeP:
    def __init__(self, raiz, dianas, ligandos, controles, docking_cfg, cajas, modo="avanzado"):
        self.cfg = {"dianas": dianas, "ligandos": ligandos, "controles": controles,
                    "docking": docking_cfg, "modo": modo}
        self._cajas = cajas
        self.layout = FakeLayout(str(raiz))
        os.makedirs(self.layout.raiz, exist_ok=True)

    def cajas(self):
        return self._cajas

    def receptor_pdbqt(self, d):
        return os.path.join(self.layout.raiz, f"rec_{d['id']}.pdbqt")

    def ligando_pdbqt(self, lig, ctrl=False):
        return os.path.join(self.layout.raiz, f"lig_{lig['id']}.pdbqt")

    def ligandos_para(self, diana_id):
        out = [(l, False) for l in self.cfg["ligandos"]]
        out += [(c, True) for c in self.cfg["controles"] if not c.get("diana") or c.get("diana") == diana_id]
        return out

    def rel(self, p):
        return os.path.relpath(p, self.layout.raiz)


def _preparar_archivos(P):
    for d in P.cfg["dianas"]:
        open(P.receptor_pdbqt(d), "w").write("REC")
    for l in P.cfg["ligandos"] + P.cfg["controles"]:
        open(P.ligando_pdbqt(l), "w").write("LIG")


@pytest.fixture
def tracker():
    return ConcurrencyTracker()


def _fake_motor_cls(tracker, fallo_en=None):
    class FakeMotor:
        def __init__(self, P, ligandos_pdbqt):
            pass

        def disponible(self):
            return True

        def etiqueta(self, d):
            return "motor de prueba"

        def dockear(self, diana_id, rec, lig, caja, salida, semilla, d, rehacer=False):
            tracker.entrar((diana_id, lig, semilla))
            try:
                if fallo_en and fallo_en(diana_id, lig, semilla):
                    return None, False
                return -7.5 + semilla * 0.1, False
            finally:
                tracker.salir()

    return FakeMotor


# ---------------------------------------------------------------- _limite_por_estado (función pura)
@pytest.mark.parametrize("decision,max_workers,esperado", [
    (Decision.RUN, 4, 4),
    (Decision.THROTTLE, 4, 2),
    (Decision.THROTTLE, 1, 1),
    (Decision.PAUSE, 4, 0),
])
def test_limite_por_estado(decision, max_workers, esperado):
    assert docking._limite_por_estado(decision, max_workers) == esperado


# ---------------------------------------------------------------- _ejecutar_en_pool (motor del pool)
def test_pool_ejecuta_cada_job_una_vez_respetando_max_workers():
    jobs = [{"n": i} for i in range(10)]
    tr = ConcurrencyTracker()

    def ejecutar_uno(job):
        tr.entrar(job["n"])
        try:
            return (1.0, False)
        finally:
            tr.salir()

    rp = ResourcePlan(max_workers=3, cpu_per_worker=1, cores_used=3, reserved_cores=0, notes=[])
    guard = FakeGuard()
    resultados = list(docking._ejecutar_en_pool(jobs, ejecutar_uno, rp, guard))

    assert len(resultados) == 10
    assert sorted(tr.llamadas) == list(range(10))
    assert tr.max_visto <= 3
    assert tr.max_visto > 1, "no se demostró paralelismo real"


def test_pool_pause_no_bloquea_para_siempre():
    jobs = [{"n": i} for i in range(4)]
    ejecutados = []

    def ejecutar_uno(job):
        ejecutados.append(job["n"])
        return (1.0, False)

    rp = ResourcePlan(max_workers=2, cpu_per_worker=1, cores_used=2, reserved_cores=0, notes=[])
    guard = FakeGuard(secuencia=[Decision.PAUSE, Decision.PAUSE])

    t0 = time.time()
    resultados = list(docking._ejecutar_en_pool(jobs, ejecutar_uno, rp, guard))
    dt = time.time() - t0

    assert len(resultados) == 4
    assert sorted(ejecutados) == [0, 1, 2, 3]
    assert dt < 5, f"el pool tardó demasiado ({dt:.2f}s): ¿quedó bloqueado?"
    assert Decision.PAUSE in guard.lecturas


def test_pool_registra_error_inesperado_sin_tumbar_el_resto():
    jobs = [{"n": 0}, {"n": 1}]

    def ejecutar_uno(job):
        if job["n"] == 0:
            raise RuntimeError("boom")
        return (2.0, False)

    rp = ResourcePlan(max_workers=2, cpu_per_worker=1, cores_used=2, reserved_cores=0, notes=[])
    guard = FakeGuard()
    resultados = dict((job["n"], r) for job, r in docking._ejecutar_en_pool(jobs, ejecutar_uno, rp, guard))
    assert resultados[0] == (None, False)
    assert resultados[1] == (2.0, False)


# ---------------------------------------------------------------- matriz()
def test_matriz_paraleliza_y_reproduce_conteos(tmp_path, tracker, monkeypatch):
    dianas = [{"id": "d1"}, {"id": "d2"}]
    ligandos = [{"id": "LIGA"}, {"id": "LIGX"}]
    controles = [{"id": "CTRL1"}]
    cajas = {"d1": {"center": [0, 0, 0], "size": [20, 20, 20]},
             "d2": {"center": [1, 1, 1], "size": [20, 20, 20]}}
    docking_cfg = {"semillas": [1, 2, 3], "exhaustiveness": 8, "cpu": 0}
    P = FakeP(tmp_path, dianas, ligandos, controles, docking_cfg, cajas)
    _preparar_archivos(P)

    rp = ResourcePlan(max_workers=3, cpu_per_worker=2, cores_used=6, reserved_cores=1, notes=["nota de prueba"])
    guard = FakeGuard()

    def fallo_en(diana_id, lig, semilla):
        return diana_id == "d2" and "LIGX" in lig and semilla == 2

    monkeypatch.setattr(docking, "Motor", _fake_motor_cls(tracker, fallo_en))
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: (rp, guard))

    buf = io.StringIO()
    with redirect_stdout(buf):
        fallos = docking.matriz(P)
    salida = buf.getvalue()

    total_esperado = len(dianas) * (len(ligandos) + len(controles)) * len(docking_cfg["semillas"])  # 18
    assert len(tracker.llamadas) == total_esperado
    assert len(set(tracker.llamadas)) == total_esperado, "alguna corrida se repitió o faltó"
    assert tracker.max_visto <= rp.max_workers
    assert tracker.max_visto > 1, "no se demostró paralelismo real"
    assert fallos == 1
    assert "nota de prueba" in salida
    assert "Paralelismo: 3 corrida(s) a la vez × 2 núcleo(s)" in salida
    assert "▸ d1" in salida and "▸ d2" in salida
    assert "[control]" in salida


def test_matriz_throttle_reduce_la_concurrencia_real(tmp_path, tracker, monkeypatch):
    dianas = [{"id": "d1"}]
    ligandos = [{"id": f"L{i}"} for i in range(6)]
    cajas = {"d1": {"center": [0, 0, 0], "size": [20, 20, 20]}}
    docking_cfg = {"semillas": [1], "exhaustiveness": 8, "cpu": 0}
    P = FakeP(tmp_path, dianas, ligandos, [], docking_cfg, cajas)
    _preparar_archivos(P)

    rp = ResourcePlan(max_workers=4, cpu_per_worker=1, cores_used=4, reserved_cores=0, notes=[])
    guard = FakeGuard(secuencia=[Decision.THROTTLE] * 3)

    monkeypatch.setattr(docking, "Motor", _fake_motor_cls(tracker))
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: (rp, guard))

    buf = io.StringIO()
    with redirect_stdout(buf):
        fallos = docking.matriz(P)

    assert fallos == 0
    assert len(tracker.llamadas) == 6
    assert tracker.max_visto <= 4


def test_matriz_sin_trabajo_no_falla(tmp_path, tracker, monkeypatch):
    """Ninguna diana tiene receptor/caja: matriz() se omite sin fallos (comportamiento
    original) y no debe intentar siquiera construir un plan de recursos para 0 corridas."""
    docking_cfg = {"semillas": [1], "exhaustiveness": 8, "cpu": 0}
    P = FakeP(tmp_path, [{"id": "d1"}], [{"id": "L1"}], [], docking_cfg, {})  # sin cajas -> se omite d1
    monkeypatch.setattr(docking, "Motor", _fake_motor_cls(tracker))
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: pytest.fail("no debería llamarse sin trabajo"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        fallos = docking.matriz(P)
    assert fallos == 0
    assert tracker.llamadas == []


# ---------------------------------------------------------------- redocking()
def test_redocking_en_paralelo_escribe_csv_y_rmsd(tmp_path, tracker, monkeypatch):
    dianas = [
        {"id": "d1", "caja": {"modo": "ligando", "ref": "HEM:A"}},
        {"id": "d2", "caja": {"modo": "ciego"}},  # se omite: no es modo 'ligando', no cuenta como fallo
    ]
    cajas = {"d1": {"center": [0, 0, 0], "size": [20, 20, 20]}}
    docking_cfg = {"semillas": [10, 20], "exhaustiveness": 8, "cpu": 0}
    P = FakeP(tmp_path, dianas, [{"id": "LIGA"}], [], docking_cfg, cajas)
    _preparar_archivos(P)
    open(P.layout.redocking_result_pdbqt("d1", 10), "w").write("X")
    open(P.layout.redocking_result_pdbqt("d1", 20), "w").write("X")

    class FakeLigandosMod:
        @staticmethod
        def preparar_ref_redocking(P, d):
            return (P.layout.redocking_result_pdbqt(d["id"], "crystal"), f"ref-mol-{d['id']}")

    import sys
    monkeypatch.setitem(sys.modules, "ligandos", FakeLigandosMod())

    rp = ResourcePlan(max_workers=2, cpu_per_worker=1, cores_used=2, reserved_cores=0, notes=[])
    guard = FakeGuard()

    monkeypatch.setattr(docking, "Motor", _fake_motor_cls(tracker))
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: (rp, guard))
    monkeypatch.setattr(docking, "rmsd_simetrico", lambda sal, ref: 1.23)

    buf = io.StringIO()
    with redirect_stdout(buf):
        fallos = docking.redocking(P)

    assert fallos == 0, "d1 no debería fallar; d2 se omite sin contar como fallo"
    f = P.layout.redocking_summary_csv()
    assert os.path.exists(f)
    with open(f) as fh:
        filas = list(csv.DictReader(fh))
    assert len(filas) == 2
    assert {row["semilla"] for row in filas} == {"10", "20"}
    assert all(row["rmsd"] == "1.23" for row in filas)


def test_redocking_falla_si_falta_receptor(tmp_path, tracker, monkeypatch):
    dianas = [{"id": "d1", "caja": {"modo": "ligando", "ref": "HEM:A"}}]
    P = FakeP(tmp_path, dianas, [{"id": "LIGA"}], [], {"semillas": [1], "exhaustiveness": 8, "cpu": 0}, {})
    monkeypatch.setattr(docking, "Motor", _fake_motor_cls(tracker))
    monkeypatch.setattr(docking, "_plan_recursos", lambda P, n: pytest.fail("no debería llamarse"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        fallos = docking.redocking(P)
    assert fallos == 1
