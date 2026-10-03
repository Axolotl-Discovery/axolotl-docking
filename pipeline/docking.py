"""Pasos 'redocking' y 'docking' con smina. Reanudables: lo que ya tiene salida completa se salta."""
import csv
import os
import shutil
import time

import numpy as np

from comun import afinidad, completo, correr, en_tmp, herramienta, log, pose1_pdb, titulo


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


def redocking(P, rehacer=False):
    titulo("4 · Validación por redocking")
    from ligandos import preparar_ref_redocking
    smina = _smina()
    if not smina:
        log("  ✘ smina no está instalado. Corre:  Docking entorno"); return 1
    cajas, d = P.cajas(), P.cfg["docking"]
    filas, fallos = [], 0
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
        log(f"\n  ▸ {diana['id']} · ligando {diana['caja']['ref']}")
        for s in d["semillas"]:
            sal = P.r("04_Docking", "Resultados", "Redocking", f"{diana['id']}_cristal_s{s}.pdbqt")
            e, previa = correr_smina(smina, P.receptor_pdbqt(diana), lig, cajas[diana["id"]], sal, s, d, rehacer)
            r = None
            if e is not None:
                try:
                    r = rmsd_simetrico(sal, ref)
                except Exception as ex:  # noqa: BLE001
                    log(f"      ⚠ RMSD no calculado: {str(ex)[:90]}")
            log(f"    semilla {s:>6}: {e if e is not None else 'NA':>7} kcal/mol   RMSD = "
                f"{('%.2f Å' % r) if r is not None else 'NA'}{'  (previa)' if previa else ''}")
            filas.append(dict(diana=diana["id"], semilla=s, afinidad=e, rmsd=None if r is None else round(r, 3)))
    if not filas:
        log("  (ninguna diana tiene caja definida por ligando co-cristalizado)")
        return fallos
    f = P.r("05_Analisis", "redocking_resumen.csv")
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
    smina = _smina()
    if not smina:
        log("  ✘ smina no está instalado. Corre:  Docking entorno"); return 1
    cajas, d = P.cajas(), P.cfg["docking"]
    if rehacer:  # no se borra nada: lo anterior se mueve a un respaldo
        resp = P.r("04_Docking", "Resultados_respaldo_" + time.strftime("%Y%m%d_%H%M"))
        for diana in P.cfg["dianas"]:
            src = P.r("04_Docking", "Resultados", diana["id"])
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
    total = len(trabajo) * len(d["semillas"])
    hechas = sum(1 for (di, _, lig, _, _) in trabajo for s in d["semillas"]
                 if completo(P.r("04_Docking", "Resultados", di["id"], f"{lig['id']}_s{s}.pdbqt"))) if not rehacer else 0
    log(f"  {len(trabajo)} pares ligando–diana × {len(d['semillas'])} semillas = {total} corridas "
        f"({hechas} ya hechas) · exhaustiveness {d['exhaustiveness']}")
    t0, nuevas, fallos, actual = time.time(), 0, 0, None
    for diana, rec, lig, lp, ctrl in trabajo:
        if diana["id"] != actual:
            actual = diana["id"]
            c = cajas[actual]
            log(f"\n  ▸ {actual}   centro {c['center']}  caja {c['size']}")
        es = []
        for s in d["semillas"]:
            sal = P.r("04_Docking", "Resultados", diana["id"], f"{lig['id']}_s{s}.pdbqt")
            e, previa = correr_smina(smina, rec, lp, cajas[diana["id"]], sal, s, d, rehacer)
            if e is None:
                fallos += 1
            else:
                es.append(e)
                if not previa:
                    nuevas += 1; hechas += 1
        if es:
            eta = ""
            if nuevas:
                seg = (time.time() - t0) / nuevas * (total - hechas)
                eta = f"  ·  {hechas}/{total}  ·  faltan ~{seg / 3600:.1f} h" if seg > 3600 else f"  ·  {hechas}/{total}  ·  faltan ~{seg / 60:.0f} min"
            log(f"    {lig['id'][:40]:40s} {np.mean(es):7.2f} ± {np.std(es):4.2f} kcal/mol{'  [control]' if ctrl else ''}{eta}")
    log(f"\n  Docking terminado: {nuevas} corridas nuevas en {(time.time() - t0) / 60:.1f} min · {fallos} fallos")
    return fallos
