"""Pasos 'redocking' y 'docking' con smina. Reanudables: lo que ya tiene salida completa se salta.

Fase 6: las corridas ya no son estrictamente secuenciales. `axd.tuning.plan()` decide
cuántas corridas van en paralelo y con cuántos núcleos cada una (según el hardware
detectado y lo que pida el proyecto), y `axd.thermal.ThermalGuard` se consulta entre
lanzamientos para frenar (THROTTLE) o dejar de lanzar corridas nuevas (PAUSE) si la
CPU/GPU se calienta demasiado. El guardia nunca interrumpe un smina/AutoDock4 en
curso (no se puede); sólo decide si se lanza la siguiente corrida."""
import concurrent.futures as cf
import csv
import os
import shutil
import time

import numpy as np

from comun import afinidad, completo, correr, en_tmp, herramienta, log, pose1_pdb, titulo
from axd.thermal import Decision


def _smina():
    return herramienta("smina", ["~/tools/bin/smina"])


def correr_smina(smina, rec, lig, caja, salida, semilla, d, rehacer=False):
    """Ejecuta smina en /tmp (sin espacios) y escribe la salida de forma atómica.
    Devuelve (afinidad, ya_existia)."""
    if completo(salida) and not rehacer:
        return afinidad(salida), True
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    tmp = en_tmp("dock")
    try:
        shutil.copy(rec, os.path.join(tmp, "r.pdbqt"))
        shutil.copy(lig, os.path.join(tmp, "l.pdbqt"))
        c, s = caja["center"], caja["size"]
        cmd = [smina, "-r", "r.pdbqt", "-l", "l.pdbqt",
               "--center_x", str(c[0]), "--center_y", str(c[1]), "--center_z", str(c[2]),
               "--size_x", str(s[0]), "--size_y", str(s[1]), "--size_z", str(s[2]),
               "--exhaustiveness", str(d["exhaustiveness"]), "--num_modes", str(d["num_modes"]),
               "--energy_range", str(d["energy_range"]), "--seed", str(semilla), "-o", "o.pdbqt"]
        if int(d.get("cpu") or 0) > 0:
            cmd += ["--cpu", str(d["cpu"])]
        rc, out = correr(cmd, cwd=tmp)
        open(salida[:-6] + ".log", "w").write(" ".join(cmd) + "\n\n" + out)
        o = os.path.join(tmp, "o.pdbqt")
        if rc != 0 or not os.path.exists(o) or os.path.getsize(o) == 0:
            log(f"      ✘ smina falló (ver {os.path.basename(salida)[:-6]}.log)")
            return None, False
        shutil.copy(o, salida + ".part")
        os.replace(salida + ".part", salida)
        return afinidad(salida), False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- RMSD
def rmsd_simetrico(pose_pdbqt, ref_noH):
    """RMSD (Å) sin realinear, considerando simetría, entre la pose 1 y el ligando cristalográfico."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolAlign
    pose = Chem.MolFromPDBBlock(pose1_pdb(pose_pdbqt), removeHs=True, proximityBonding=True, sanitize=False)
    pose = AllChem.AssignBondOrdersFromTemplate(ref_noH, pose)
    return rdMolAlign.CalcRMS(pose, ref_noH)


# ---------------------------------------------------------------- motor (smina o AutoDock4)
class Motor:
    """Decide el motor del proyecto: smina por defecto; AutoDock4 si algún ligando tiene átomos que
    smina no conoce (V, Pt, Ru…) o si el proyecto lo pide. Se usa el MISMO motor para todo el proyecto
    (ligandos, controles y redocking) para que las energías sean comparables."""

    def __init__(self, P, ligandos_pdbqt):
        import metales
        self.P, self.m = P, metales
        pedido = P.cfg["docking"].get("motor", "smina")
        raros = [p for p in ligandos_pdbqt if os.path.exists(p) and metales.necesita_ad4(p)]
        self.nombre = "ad4" if (pedido == "ad4" or raros) else "smina"
        self.smina = _smina()
        self.param = None
        if self.nombre == "ad4":
            tipos = set()
            for p in ligandos_pdbqt:
                if os.path.exists(p):
                    tipos |= metales.tipos_pdbqt(p)
            self.tipos = tipos
            self.param, base = metales.escribir_parametros(P, tipos - metales.EN_AD4)
            if raros:
                log("  ⚛ Hay ligandos con átomos no comunes → TODO el proyecto se dockea con AutoDock4 "
                    "(para que las energías sean comparables)")
            log(f"  · Parámetros: {P.rel(self.param)} (detalle en 05_Analysis/metal_parameters.txt)")
            log("  ⚠ Parámetros genéricos (UFF) para metales: usa las energías de forma comparativa y valida con DM.")

    def disponible(self):
        if self.nombre == "smina" and not self.smina:
            log("  ✘ smina no está instalado. Corre:  Docking entorno"); return False
        return True

    def etiqueta(self, d):
        return (f"exhaustiveness {d['exhaustiveness']}" if self.nombre == "smina"
                else f"AutoDock4 · {d.get('ad4_runs', 20)} corridas GA × {int(d.get('ad4_evals', 2500000)):,} evaluaciones")

    def dockear(self, diana_id, rec, lig, caja, salida, semilla, d, rehacer=False):
        if self.nombre == "smina":
            return correr_smina(self.smina, rec, lig, caja, salida, semilla, d, rehacer)
        if completo(salida) and not rehacer:
            return afinidad(salida), True
        os.makedirs(os.path.dirname(salida), exist_ok=True)
        try:
            mapas = self.m.preparar_mapas(self.P, diana_id, rec, caja, self.tipos | self.m.tipos_pdbqt(lig), self.param)
            e = self.m.correr_ad4(mapas, lig, salida, semilla, d)
        except Exception as ex:  # noqa: BLE001
            log(f"      ✘ AutoDock4: {ex}")
            return None, False
        if e is None:
            log(f"      ✘ AutoDock4 no produjo poses (ver {os.path.basename(salida)[:-6]}.log)")
        return e, False


# ---------------------------------------------------------------- Fase 6: paralelización real
def _plan_recursos(P, n_jobs):
    """Hardware detectado + plan de concurrencia (axd.tuning) + guardia térmica (axd.thermal)
    para esta corrida del pipeline. `n_jobs` es el número de corridas pendientes: el plan
    no crea más trabajadores que trabajo por hacer."""
    from axd import hardware as HW, tuning
    from axd.config import cargar_global
    hw = HW.detect()
    g = cargar_global()
    pol = tuning.ThermalPolicy.from_config(g.get("thermal"))
    cpu_pedido = int(P.cfg["docking"].get("cpu") or 0) or None
    rp = tuning.plan(hw, n_jobs=max(1, n_jobs), cpu_per_worker=cpu_pedido)
    from axd.thermal import ThermalGuard
    return rp, ThermalGuard(pol)


def _limite_por_estado(decision, max_workers):
    """Cuántas corridas pueden estar en vuelo a la vez según la última lectura térmica."""
    if decision == Decision.PAUSE:
        return 0
    if decision == Decision.THROTTLE:
        return max(1, max_workers // 2)
    return max_workers


def _log_plan(rp, etiqueta_motor):
    log(f"  Paralelismo: {rp.max_workers} corrida(s) a la vez × {rp.cpu_per_worker} núcleo(s) cada una"
        + (f" · {rp.reserved_cores} núcleo(s) libre(s)" if rp.reserved_cores else "") + f" · {etiqueta_motor}")
    for n in rp.notes:
        log(f"  {n}")


def _ejecutar_en_pool(jobs, ejecutar_uno, rp, guard):
    """Corre `ejecutar_uno(job)` para cada job en `jobs` respetando el plan de concurrencia
    y el seguro térmico. Entrega (job, resultado) EN ORDEN DE TERMINACIÓN (no en el orden
    de la lista): con corridas en paralelo, no hay forma de preservar el orden original sin
    desperdiciar paralelismo. Nunca cancela una corrida de smina/AutoDock4 en curso; sólo
    decide si se lanza la siguiente."""
    max_workers = max(1, rp.max_workers)
    poll = max(1, int(getattr(guard.policy, "poll_seconds", 10)))
    idx, futuros, decision_previa = 0, {}, None
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        while idx < len(jobs) or futuros:
            lectura = guard.read()
            if lectura.decision is not decision_previa and lectura.reason:
                log(f"  {lectura.reason}")
            decision_previa = lectura.decision
            limite = _limite_por_estado(lectura.decision, max_workers)
            while idx < len(jobs) and len(futuros) < limite:
                job = jobs[idx]; idx += 1
                futuros[ex.submit(ejecutar_uno, job)] = job
            if not futuros:
                time.sleep(poll); continue
            listos, _ = cf.wait(futuros.keys(), timeout=poll, return_when=cf.FIRST_COMPLETED)
            for fut in listos:
                job = futuros.pop(fut)
                try:
                    resultado = fut.result()
                except Exception as ex_:  # noqa: BLE001
                    log(f"      ✘ error inesperado: {ex_}")
                    resultado = (None, False)
                yield job, resultado


def redocking(P, rehacer=False):
    titulo("4 · Validación por redocking")
    from ligandos import preparar_ref_redocking
    cajas, d = P.cajas(), P.cfg["docking"]
    todos = [P.ligando_pdbqt(l, c) for x in P.cfg["dianas"] for l, c in P.ligandos_para(x["id"])]
    motor = Motor(P, todos)
    if not motor.disponible():
        return 1
    fallos = 0
    # ---- preparación por diana (I/O + RDKit: se queda secuencial, no es el cuello de botella)
    preparadas = []
    for diana in P.cfg["dianas"]:
        if diana.get("caja", {}).get("modo") != "ligando":
            continue
        if diana["id"] not in cajas or not os.path.exists(P.receptor_pdbqt(diana)):
            log(f"  ✘ {diana['id']}: falta receptor/caja (paso 'receptores')"); fallos += 1; continue
        try:
            lig, ref = preparar_ref_redocking(P, diana)
        except Exception as e:  # noqa: BLE001
            lig, ref = None, None
            log(f"  ✘ {diana['id']}: no pude preparar el ligando cristalográfico ({e})")
        if not lig:
            fallos += 1; continue
        preparadas.append((diana, lig, ref))

    jobs = [{"diana": diana, "lig": lig, "s": s, "sal": P.layout.redocking_result_pdbqt(diana["id"], s)}
            for diana, lig, ref in preparadas for s in d["semillas"]]

    def _correr_redocking(job):
        return motor.dockear(job["diana"]["id"], P.receptor_pdbqt(job["diana"]), job["lig"],
                              cajas[job["diana"]["id"]], job["sal"], job["s"], d, rehacer)

    refs = {diana["id"]: ref for diana, lig, ref in preparadas}
    dianas_con_encabezado = set()
    filas = []
    if jobs:
        rp, guard = _plan_recursos(P, len(jobs))
        _log_plan(rp, motor.etiqueta(d))
        for job, (e, previa) in _ejecutar_en_pool(jobs, _correr_redocking, rp, guard):
            diana = job["diana"]
            if diana["id"] not in dianas_con_encabezado:
                dianas_con_encabezado.add(diana["id"])
                log(f"\n  ▸ {diana['id']} · ligando {diana['caja']['ref']}")
            r = None
            if e is not None:
                try:
                    r = rmsd_simetrico(job["sal"], refs[diana["id"]])
                except Exception as ex:  # noqa: BLE001
                    log(f"      ⚠ RMSD no calculado: {str(ex)[:90]}")
            log(f"    semilla {job['s']:>6}: {e if e is not None else 'NA':>7} kcal/mol   RMSD = "
                f"{('%.2f Å' % r) if r is not None else 'NA'}{'  (previa)' if previa else ''}")
            filas.append(dict(diana=diana["id"], semilla=job["s"], afinidad=e,
                               rmsd=None if r is None else round(r, 3)))
    if not filas:
        log("  (ninguna diana tiene caja definida por ligando co-cristalizado)")
        return fallos
    f = P.layout.redocking_summary_csv()
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["diana", "semilla", "afinidad", "rmsd"]); w.writeheader(); w.writerows(filas)
    log("\n  Criterio de validación: RMSD ≤ 2.0 Å en la pose 1")
    for diana in sorted({x["diana"] for x in filas}):
        rs = [x["rmsd"] for x in filas if x["diana"] == diana and x["rmsd"] is not None]
        if rs:
            log(f"   {'✔' if min(rs) <= 2 else '✘'} {diana:24s} RMSD mín {min(rs):.2f} · media {np.mean(rs):.2f} Å")
        else:
            log(f"   ? {diana:24s} sin RMSD")
    log(f"  Tabla: {P.rel(f)}")
    return fallos


def matriz(P, rehacer=False):
    titulo("5 · Docking (matriz ligandos × dianas)")
    cajas, d = P.cajas(), P.cfg["docking"]
    if rehacer:  # no se borra nada: lo anterior se mueve a un respaldo
        resp = P.layout.results_backup_dir(time.strftime("%Y%m%d_%H%M"))
        for diana in P.cfg["dianas"]:
            src = P.layout.target_results_dir(diana["id"])
            if os.path.isdir(src) and os.listdir(src):
                os.makedirs(resp, exist_ok=True)
                shutil.move(src, os.path.join(resp, diana["id"]))
        if os.path.isdir(resp):
            log(f"  Resultados anteriores respaldados en {P.rel(resp)}")
    trabajo = []
    for diana in P.cfg["dianas"]:
        rec = P.receptor_pdbqt(diana)
        if diana["id"] not in cajas or not os.path.exists(rec):
            log(f"  ✘ {diana['id']}: falta receptor o caja (corre 'receptores'); se omite")
            continue
        for lig, ctrl in P.ligandos_para(diana["id"]):
            lp = P.ligando_pdbqt(lig, ctrl)
            if not os.path.exists(lp):
                log(f"  ✘ {lig['id']}: falta su PDBQT (corre 'ligandos'); se omite")
                continue
            trabajo.append((diana, rec, lig, lp, ctrl))
    motor = Motor(P, [lp for (_, _, _, lp, _) in trabajo])
    if not motor.disponible():
        return 1
    total = len(trabajo) * len(d["semillas"])
    hechas = sum(1 for (di, _, lig, _, _) in trabajo for s in d["semillas"]
                 if completo(P.layout.result_pdbqt(di["id"], lig["id"], s))) if not rehacer else 0
    log(f"  {len(trabajo)} pares ligando–diana × {len(d['semillas'])} semillas = {total} corridas "
        f"({hechas} ya hechas) · {motor.etiqueta(d)}")

    jobs = []
    for diana, rec, lig, lp, ctrl in trabajo:
        dd = d
        if P.cfg.get("modo") == "basico" and cajas[diana["id"]].get("modo") == "ciego":
            dd = dict(d, exhaustiveness=max(int(d["exhaustiveness"]), 64))  # ciego necesita más búsqueda
        for s in d["semillas"]:
            sal = P.layout.result_pdbqt(diana["id"], lig["id"], s)
            jobs.append({"diana": diana, "rec": rec, "lig": lig, "lp": lp, "ctrl": ctrl, "s": s, "sal": sal, "dd": dd})

    def _correr_matriz(job, rp):
        dd = dict(job["dd"], cpu=rp.cpu_per_worker)
        return motor.dockear(job["diana"]["id"], job["rec"], job["lp"], cajas[job["diana"]["id"]],
                              job["sal"], job["s"], dd, rehacer)

    restantes = {(diana["id"], lig["id"]): len(d["semillas"]) for diana, rec, lig, lp, ctrl in trabajo}
    acumulado = {clave: [] for clave in restantes}
    dianas_con_encabezado = set()
    t0, nuevas, fallos = time.time(), 0, 0
    if jobs:
        rp, guard = _plan_recursos(P, total - hechas)
        _log_plan(rp, motor.etiqueta(d))
        for job, (e, previa) in _ejecutar_en_pool(jobs, lambda j: _correr_matriz(j, rp), rp, guard):
            diana, lig, ctrl = job["diana"], job["lig"], job["ctrl"]
            if diana["id"] not in dianas_con_encabezado:
                dianas_con_encabezado.add(diana["id"])
                c = cajas[diana["id"]]
                log(f"\n  ▸ {diana['id']}   centro {c['center']}  caja {c['size']}")
            clave = (diana["id"], lig["id"])
            if e is None:
                fallos += 1
            else:
                acumulado[clave].append(e)
                if not previa:
                    nuevas += 1; hechas += 1
            restantes[clave] -= 1
            if restantes[clave] == 0:
                es = acumulado[clave]
                if es:
                    eta = ""
                    if nuevas:
                        seg = (time.time() - t0) / nuevas * (total - hechas)
                        eta = (f"  ·  {hechas}/{total}  ·  faltan ~{seg / 3600:.1f} h" if seg > 3600
                               else f"  ·  {hechas}/{total}  ·  faltan ~{seg / 60:.0f} min")
                    log(f"    {lig['id'][:40]:40s} {np.mean(es):7.2f} ± {np.std(es):4.2f} kcal/mol"
                        f"{'  [control]' if ctrl else ''}{eta}")
    log(f"\n  Docking terminado: {nuevas} corridas nuevas en {(time.time() - t0) / 60:.1f} min · {fallos} fallos")
    return fallos
