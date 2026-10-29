"""Paso 'consensus' (modo avanzado, opt-in): corre motores adicionales sobre los mismos pares
ligando–diana (mismos receptores, cajas y semillas) y los compara con ECR + acuerdo de poses.

Qué hace, en orden:
  1. Docking con cada motor extra → 04_Docking/Consensus/<motor>/<diana>/<ligando>_s<semilla>.pdbqt
     (el motor principal del proyecto no se repite: se lee de Results/).
  2. Redocking del ligando cristalográfico con cada motor extra, para ver si ese motor reproduce
     la pose experimental en esas dianas (un motor que no la reproduce pesa menos en la lectura).
  3. Análisis (axd.consensus): rangos por motor, ECR, τ de Kendall, RMSD entre mejores poses y
     veredicto por ligando → 05_Analysis/consensus_*.csv y consensus_meta.json.

Es reanudable: una corrida con salida completa se salta, igual que en el docking normal."""
import csv
import json
import os
import time

from common import affinity, is_complete, log, model1, pdbqt_element, pose1_pdb, title
import docking
from axd import consensus as K

# motor del consenso → motor concreto que lo ejecuta
EJECUTOR = {"vina": "smina", "vinardo": "vinardo", "ad4": "ad4"}


# ---------------------------------------------------------------- configuración
def configuracion(P):
    """(activo, motores pedidos). Se guarda en axd.json → docking.consensus."""
    c = P.cfg["docking"].get("consensus") or {}
    return bool(c.get("enabled")), K.motores_validos(c.get("engines") or K.DEFAULT_ENGINES)


def motor_principal(P):
    """Familia del motor con el que se hizo (o se hará) el docking normal: 'vina' o 'ad4'."""
    d = P.cfg["docking"]
    usado = d.get("motor_usado") or d.get("engine") or d.get("motor") or "smina"
    return "ad4" if usado == "ad4" else "vina"


def _ruta(P, motor, principal, diana, lig, s):
    if motor == principal:
        return P.layout.result_pdbqt(diana, lig, s)
    return P.layout.consensus_result_pdbqt(motor, diana, lig, s)


def _ruta_redock(P, motor, principal, diana, s):
    if motor == principal:
        return P.layout.redocking_result_pdbqt(diana, s)
    return P.layout.consensus_redocking_pdbqt(motor, diana, s)


def _parametros(P, d, caja):
    """Los mismos parámetros que el docking normal (incluida la búsqueda extra del modo ciego)."""
    if P.cfg.get("mode") == "basic" and caja.get("mode") == "blind":
        return dict(d, exhaustiveness=max(int(d["exhaustiveness"]), 64))
    return d


# ---------------------------------------------------------------- RMSD entre poses de dos motores
def _coords(pdbqt):
    els, xyz = [], []
    for l in open(pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM"):
            el = pdbqt_element(l)
            if el != "H":
                els.append(el)
                xyz.append((float(l[30:38]), float(l[38:46]), float(l[46:54])))
    return els, xyz


def rmsd_poses(a, b):
    """RMSD (Å) sin realinear entre la pose 1 de dos PDBQT del MISMO ligando. Usa la versión con
    simetría de RDKit (un anillo girado 180° no cuenta como error); si no se puede, el RMSD por orden
    de átomos. None si no son comparables."""
    ea, ca = _coords(a)
    eb, cb = _coords(b)
    if not ea or ea != eb:
        return None
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolAlign
        ma = Chem.MolFromPDBBlock(pose1_pdb(a), removeHs=True, proximityBonding=True, sanitize=False)
        mb = Chem.MolFromPDBBlock(pose1_pdb(b), removeHs=True, proximityBonding=True, sanitize=False)
        return float(rdMolAlign.CalcRMS(mb, ma))
    except Exception:  # noqa: BLE001
        return K.rmsd_ordenado(ca, cb)


# ---------------------------------------------------------------- trabajo
def _pares(P):
    cajas = P.boxes()
    trabajo = []
    for diana in P.cfg["targets"]:
        rec = P.receptor_pdbqt(diana)
        if diana["id"] not in cajas or not os.path.exists(rec):
            continue
        for lig, ctrl in P.ligands_for(diana["id"]):
            lp = P.ligand_pdbqt(lig, ctrl)
            if os.path.exists(lp):
                trabajo.append((diana, rec, lig, lp, ctrl))
    return cajas, trabajo


def _correr_motor(P, motor, principal, cajas, trabajo, d, rehacer, tiempos):
    """Docking de todos los pares con un motor extra. Devuelve el número de fallos."""
    import metals
    ejecutor = EJECUTOR[motor]
    elegibles = [t for t in trabajo if not (ejecutor != "ad4" and metals.necesita_ad4(t[3]))]
    omitidos = len(trabajo) - len(elegibles)
    if omitidos:
        log(f"  ⚛ {omitidos} ligando(s) tienen átomos que {K.nombre_motor(motor)} no conoce: sólo AutoDock4 "
            "los puede dockear; en esos pares el consenso no aplica.")
    m = docking.Motor(P, [t[3] for t in elegibles], forzar=ejecutor)
    if not m.disponible():
        return 1
    jobs = []
    for diana, rec, lig, lp, ctrl in elegibles:
        for s in d["seeds"]:
            jobs.append({"diana": diana, "rec": rec, "lp": lp, "s": s,
                         "sal": _ruta(P, motor, principal, diana["id"], lig["id"], s)})
    pendientes = [j for j in jobs if rehacer or not is_complete(j["sal"])]
    log(f"\n  ▸ {K.nombre_motor(motor)}: {len(jobs)} corridas ({len(jobs) - len(pendientes)} ya hechas) · "
        f"{m.etiqueta(d)}")
    fallos, t0 = 0, time.time()
    if pendientes:
        rp, guard = docking._plan_recursos(P, len(pendientes))
        docking._log_plan(rp, m.etiqueta(d))

        def uno(job):
            dd = dict(_parametros(P, d, cajas[job["diana"]["id"]]), cpu=rp.cpu_per_worker)
            return m.dockear(job["diana"]["id"], job["rec"], job["lp"], cajas[job["diana"]["id"]],
                             job["sal"], job["s"], dd, rehacer)

        hechas = 0
        for job, (e, _previa) in docking._ejecutar_en_pool(pendientes, uno, rp, guard):
            hechas += 1
            if e is None:
                fallos += 1
        log(f"    {hechas - fallos}/{len(pendientes)} corridas nuevas · {fallos} fallos · "
            f"{(time.time() - t0) / 60:.1f} min")
    tiempos[motor] = tiempos.get(motor, 0.0) + (time.time() - t0)
    return fallos


def _redocking_motor(P, motor, principal, cajas, d, rehacer, filas_out):
    """Redocking del ligando cristalográfico con un motor extra; agrega filas al CSV."""
    from ligands import preparar_ref_redocking
    ejecutor = EJECUTOR[motor]
    dianas = [x for x in P.cfg["targets"] if x.get("box", {}).get("mode") == "ligand"
              and x["id"] in cajas and os.path.exists(P.receptor_pdbqt(x))]
    if not dianas:
        return 0
    preparadas = []
    for diana in dianas:
        try:
            lig, ref = preparar_ref_redocking(P, diana)
        except Exception:  # noqa: BLE001
            lig, ref = None, None
        if lig:
            preparadas.append((diana, lig, ref))
    if not preparadas:
        return 0
    m = docking.Motor(P, [p[1] for p in preparadas], forzar=ejecutor)
    if not m.disponible():
        return 1
    fallos = 0
    for diana, lig, ref in preparadas:
        for s in d["seeds"]:
            sal = _ruta_redock(P, motor, principal, diana["id"], s)
            e, _prev = m.dockear(diana["id"], P.receptor_pdbqt(diana), lig, cajas[diana["id"]], sal, s, d, rehacer)
            r = None
            if e is not None:
                try:
                    r = docking.rmsd_simetrico(sal, ref)
                except Exception:  # noqa: BLE001
                    r = None
            else:
                fallos += 1
            filas_out.append(dict(motor=motor, diana=diana["id"], semilla=s, afinidad=e,
                                  rmsd=None if r is None else round(r, 3)))
    return fallos


# ---------------------------------------------------------------- análisis
def _leer_resultados(P, motores, principal, trabajo, seeds):
    """medias, tipos y la mejor semilla de cada (par, motor)."""
    medias, tipos, mejor = {}, {}, {}
    for diana, _rec, lig, _lp, ctrl in trabajo:
        clave = (diana["id"], lig["id"])
        tipos[clave] = "control" if ctrl else "ligando"
        medias[clave] = {}
        for mo in motores:
            vals = []
            for s in seeds:
                f = _ruta(P, mo, principal, diana["id"], lig["id"], s)
                if is_complete(f):
                    e = affinity(f)
                    if e is not None:
                        vals.append((e, f))
            if vals:
                medias[clave][mo] = sum(v for v, _ in vals) / len(vals)
                mejor[(clave, mo)] = min(vals)[1]
            else:
                medias[clave][mo] = None
    return medias, tipos, mejor


def _acuerdo_poses(motores, medias, mejor):
    rm, filas = {}, []
    for clave, por in medias.items():
        rm[clave] = {}
        presentes = [mo for mo in motores if por.get(mo) is not None]
        for i, a in enumerate(presentes):
            for b in presentes[i + 1:]:
                try:
                    r = rmsd_poses(mejor[(clave, a)], mejor[(clave, b)])
                except Exception:  # noqa: BLE001
                    r = None
                rm[clave][(a, b)] = r
                filas.append(dict(diana=clave[0], ligando=clave[1], motor_a=a, motor_b=b,
                                  rmsd=None if r is None else round(r, 3)))
    return rm, filas


def _escribir_csv(ruta, campos, filas):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def _tiempos_acumulados(P, nuevos, resultados):
    """Tiempo de cómputo por motor, acumulado entre corridas reanudadas."""
    previo = {}
    f = P.layout.consensus_engines_csv()
    if os.path.exists(f):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            try:
                previo[r["motor"]] = float(r["segundos"])
            except (KeyError, ValueError):
                pass
    filas = []
    for mo, (ok, total) in resultados.items():
        seg = previo.get(mo, 0.0) + nuevos.get(mo, 0.0)
        filas.append(dict(motor=mo, nombre=K.nombre_motor(mo), corridas_ok=ok, corridas_totales=total,
                          segundos=round(seg, 1) if (seg or mo in nuevos) else ""))
    _escribir_csv(f, ["motor", "nombre", "corridas_ok", "corridas_totales", "segundos"], filas)


def run(P, rehacer=False):
    title("5b · Consenso entre motores (modo avanzado)")
    activo, pedidos = configuracion(P)
    if not activo:
        log("  Modo consenso desactivado (Proyecto → Parámetros → Modo avanzado); se omite.")
        return 0
    principal = motor_principal(P)
    motores = K.motores_validos(pedidos + [principal])
    if len(motores) < 2:
        log("  ✘ El consenso necesita al menos 2 motores distintos; elige otro más en Parámetros.")
        return 1
    d = P.cfg["docking"]
    cajas, trabajo = _pares(P)
    if not trabajo:
        log("  ✘ No hay pares ligando–diana listos (corre 'receptores' y 'ligandos').")
        return 1
    log(f"  Motores: {', '.join(K.nombre_motor(m, d.get('motor_usado')) for m in motores)}"
        f"  ·  principal (ya corrido): {K.nombre_motor(principal, d.get('motor_usado'))}")
    n_extra = sum(len(trabajo) * len(d["seeds"]) for m in motores if m != principal)
    log(f"  Esto agrega {n_extra} corridas de docking además del paso 'docking'; tarda más y usa más CPU.")

    fallos, tiempos, redock = 0, {}, []
    for mo in [m for m in motores if m != principal]:
        fallos += _correr_motor(P, mo, principal, cajas, trabajo, d, rehacer, tiempos)
    for mo in [m for m in motores if m != principal]:
        log(f"\n  ▸ Redocking del ligando cristalográfico con {K.nombre_motor(mo)}")
        fallos += _redocking_motor(P, mo, principal, cajas, d, rehacer, redock)

    medias, tipos, mejor = _leer_resultados(P, motores, principal, trabajo, d["seeds"])
    con_datos = [m for m in motores if any(v.get(m) is not None for v in medias.values())]
    caidos = [m for m in motores if m not in con_datos]
    for m in caidos:
        log(f"  ✘ {K.nombre_motor(m)} no produjo resultados: queda fuera del consenso.")
        fallos += 1
    if len(con_datos) < 2:
        log("  ✘ Menos de 2 motores con resultados: no hay consenso que calcular.")
        return fallos or 1
    rm, filas_pose = _acuerdo_poses(con_datos, medias, mejor)
    res = K.analizar(medias, tipos, con_datos, rm)

    # ---- archivos
    campos = ["diana", "ligando", "tipo", "n_motores"] + [f"dG_{m}" for m in con_datos] \
        + [f"rango_{m}" for m in con_datos] \
        + ["ecr", "rango_consenso", "orden", "dispersion_rangos", "dispersion_norm", "rmsd_max", "veredicto", "motivo"]
    _escribir_csv(P.layout.consensus_summary_csv(), campos,
                  [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()} for f in res["filas"]])
    _escribir_csv(P.layout.consensus_poses_csv(), ["diana", "ligando", "motor_a", "motor_b", "rmsd"], filas_pose)
    _escribir_csv(P.layout.consensus_tau_csv(), ["diana", "motor_a", "motor_b", "tau"],
                  [dict(diana=di, motor_a=a, motor_b=b, tau=None if t is None else round(t, 3))
                   for di, pares in res["tau"].items() for (a, b), t in pares.items()])
    # redocking: filas del motor principal (paso 4) + las de los extras
    rd = P.layout.redocking_summary_csv()
    if os.path.exists(rd):
        for r in csv.DictReader(open(rd, encoding="utf-8")):
            redock.append(dict(motor=principal, diana=r["diana"], semilla=r["semilla"],
                               afinidad=r["afinidad"] or None, rmsd=r["rmsd"] or None))
    _escribir_csv(P.layout.consensus_redocking_csv(), ["motor", "diana", "semilla", "afinidad", "rmsd"], redock)
    resultados = {}
    for mo in motores:
        total = len(trabajo) * len(d["seeds"])
        ok = sum(1 for (di, _r, lg, _l, _c) in trabajo for s in d["seeds"]
                 if is_complete(_ruta(P, mo, principal, di["id"], lg["id"], s)))
        resultados[mo] = (ok, total)
    _tiempos_acumulados(P, tiempos, resultados)
    with open(P.layout.consensus_meta_json(), "w", encoding="utf-8") as fh:
        json.dump({"fecha": time.strftime("%Y-%m-%d %H:%M"), "motores": con_datos, "principal": principal,
                   "principal_real": d.get("motor_usado"), "sigma": res["sigma"],
                   "umbrales": {"rmsd": K.RMSD_OK, "dispersion": K.SPREAD_OK, "min_ligandos": K.MIN_LIGANDOS_RANGO},
                   "semillas": d["seeds"], "no_disponibles": caidos}, fh, indent=2, ensure_ascii=False)

    # ---- resumen en el log
    for diana in dict.fromkeys(f["diana"] for f in res["filas"]):
        log(f"\n  ▸ {diana}")
        log("    " + f"{'ligando':26s}" + "".join(f"{m[:8]:>9s}" for m in con_datos) + f"{'ECR#':>6s}  veredicto")
        for f in [x for x in res["filas"] if x["diana"] == diana]:
            cols = "".join(f"{f['dG_' + m]:9.2f}" if f.get(f"dG_{m}") is not None else f"{'NA':>9s}" for m in con_datos)
            pos = f"{f['orden']:>6d}" if "orden" in f else f"{'—':>6s}"
            log(f"    {f['ligando'][:26]:26s}{cols}{pos}  {f['veredicto']}"
                + (" ◆ control" if f["tipo"] == "control" else ""))
    cuenta = K.resumen_veredictos(res["filas"])
    log("\n  Veredictos: " + " · ".join(f"{k} {v}" for k, v in cuenta.items()))
    log("  Archivos: 05_Analysis/consensus_summary.csv · consensus_poses.csv · consensus_kendall.csv · "
        "consensus_redocking.csv · consensus_by_engine.csv")
    return fallos
