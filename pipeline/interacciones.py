"""Paso 'interacciones': complejo proteína + ligando (mejor pose) en un solo archivo y análisis de contactos.

Salidas:
  04_Docking/Complejos/<diana>__<ligando>_complejo.pdb   receptor limpio + mejor pose (con hidrógenos y enlaces)
  04_Docking/Complejos/<diana>__<ligando>_pose.sdf       la pose sola, con órdenes de enlace (para PyMOL/Chimera/Maestro)
  05_Analisis/interacciones_detalle.csv          una fila por interacción (tipo, residuo, distancia)
  05_Analisis/interacciones_resumen.csv          conteo por tipo y residuos clave por complejo
Usa PLIP (puentes H, hidrofóbicas, apilamiento π, catión-π, puentes salinos, halógeno, puentes de agua, metal).
Si PLIP no está o falla, usa criterios geométricos por distancia.
"""
import csv
import glob
import os
from collections import Counter

import numpy as np

from comun import elemento_pdbqt, log, titulo

TIPOS_ES = {"hidrofobica": "Hidrofóbica", "puente_h": "Puente de H", "pi_stacking": "Apilamiento π",
            "pi_cation": "Catión-π", "puente_salino": "Puente salino", "halogeno": "Enlace de halógeno",
            "puente_agua": "Puente de agua", "metal": "Coordinación metálica"}


# ---------------------------------------------------------------- complejo
def _pose_rdkit(pose_pdbqt, plantilla_sdf):
    """Pose 1 como Mol de RDKit con órdenes de enlace (de la plantilla preparada) e hidrógenos."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    bloque, n = [], 0
    for l in open(pose_pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM"):
            el = elemento_pdbqt(l)
            if el == "H":
                continue
            n += 1
            bloque.append(f"HETATM{n:5d} {(el + str(n))[:4]:<4s} LIG Z   1    {l[30:54]}  1.00  0.00          {el:>2s}\n")
    pose = Chem.MolFromPDBBlock("".join(bloque) + "END\n", removeHs=False, proximityBonding=True, sanitize=False)
    if plantilla_sdf and os.path.exists(plantilla_sdf):
        ref = Chem.MolFromMolFile(plantilla_sdf, removeHs=True)
        if ref is not None and ref.GetNumAtoms() == pose.GetNumAtoms():
            try:
                pose = AllChem.AssignBondOrdersFromTemplate(ref, pose)
                return Chem.AddHs(pose, addCoords=True), True
            except Exception:  # noqa: BLE001
                pass
    try:
        Chem.SanitizeMol(pose)
        return Chem.AddHs(pose, addCoords=True), False
    except Exception:  # noqa: BLE001
        return pose, False


def _ligando_pdb(mol, cadena="Z"):
    """Bloque PDB del ligando (HETATM + CONECT) renumerado para ir después del receptor."""
    from rdkit import Chem
    for i, a in enumerate(mol.GetAtoms(), 1):
        info = Chem.AtomPDBResidueInfo()
        info.SetResidueName("LIG"); info.SetChainId(cadena); info.SetResidueNumber(1); info.SetIsHeteroAtom(True)
        info.SetName(f"{a.GetSymbol()}{i}"[:4].ljust(4)); info.SetSerialNumber(i)
        a.SetMonomerInfo(info)
    return Chem.MolToPDBBlock(mol, flavor=4)  # sin END/MASTER


def construir_complejo(P, diana, lig_id, pose_pdbqt, control):
    rec = P.receptor_limpio(diana)
    if not os.path.exists(rec):
        return None, None
    carpeta = "Controles" if control else "Ligandos"
    plantilla = P.r("04_Docking", carpeta, "prep", f"{lig_id}_H.sdf")
    mol, con_enlaces = _pose_rdkit(pose_pdbqt, plantilla)
    os.makedirs(P.r("04_Docking", "Complejos"), exist_ok=True)
    base = P.r("04_Docking", "Complejos", f"{diana['id']}__{lig_id}")
    from rdkit import Chem
    try:
        w = Chem.SDWriter(base + "_pose.sdf"); mol.SetProp("_Name", lig_id); w.write(mol); w.close()
    except Exception:  # noqa: BLE001
        pass
    receptor = [l for l in open(rec) if l[:6] in ("ATOM  ", "HETATM", "TER   ")]
    ligando = _ligando_pdb(mol)
    # renumera seriales del ligando para que no choquen con los del receptor
    n0 = len(receptor) + 1
    lineas = []
    for l in ligando.splitlines():
        if l.startswith("HETATM"):
            lineas.append(f"HETATM{int(l[6:11]) + n0:5d}{l[11:]}")
        elif l.startswith("CONECT"):
            nums = [int(l[i:i + 5]) + n0 for i in range(6, len(l.rstrip()), 5) if l[i:i + 5].strip()]
            lineas.append("CONECT" + "".join(f"{x:5d}" for x in nums))
    cab = [f"REMARK   Complejo {diana['id']} + {lig_id} (mejor pose, Axolotl Docking)\n"]
    open(base + "_complejo.pdb", "w").writelines(cab + receptor + ["TER\n"] + [x + "\n" for x in lineas] + ["END\n"])
    return base + "_complejo.pdb", con_enlaces


# ---------------------------------------------------------------- PLIP
def interacciones_plip(complejo):
    import shutil
    import tempfile
    from plip.structure.preparation import PDBComplex
    tmp = tempfile.mkdtemp(prefix="axd_plip_")  # PLIP escribe archivos auxiliares: que no ensucien Complejos/
    cwd = os.getcwd()
    try:
        os.chdir(tmp)
        copia = os.path.join(tmp, "complejo.pdb")
        shutil.copy(complejo, copia)
        m = PDBComplex()
        m.output_path = tmp
        m.load_pdb(copia)
        m.analyze()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    filas = []
    for clave, s in m.interaction_sets.items():
        if not clave.startswith("LIG:"):
            continue

        def add(tipo, x, dist, extra=""):
            filas.append(dict(tipo=tipo, residuo=f"{x.restype}{x.resnr}", cadena=x.reschain,
                              distancia=round(float(dist), 2), detalle=extra))
        for x in s.hydrophobic_contacts:
            add("hidrofobica", x, x.distance)
        for x in s.hbonds_ldon + s.hbonds_pdon:
            add("puente_h", x, x.distance_ad, "ligando dona" if not x.protisdon else "proteína dona")
        for x in s.pistacking:
            add("pi_stacking", x, x.distance, {"P": "paralelo", "T": "en T"}.get(x.type, x.type))
        for x in s.pication_laro + s.pication_paro:
            add("pi_cation", x, x.distance)
        for x in s.saltbridge_lneg + s.saltbridge_pneg:
            add("puente_salino", x, x.distance)
        for x in s.halogen_bonds:
            add("halogeno", x, x.distance)
        for x in s.water_bridges:
            add("puente_agua", x, x.distance_aw)
        for x in s.metal_complexes:
            add("metal", x, x.distance, getattr(x, "metal_type", ""))
    return filas


def interacciones_plip_sub(complejo):
    """PLIP en un proceso aparte: usa Open Babel, que puede chocar con RDKit dentro del mismo proceso."""
    import json
    import subprocess
    import sys
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "plip", complejo], capture_output=True, text=True)
    lineas = [l for l in r.stdout.splitlines() if l.startswith("[")]
    if r.returncode != 0 or not lineas:
        raise RuntimeError((r.stderr.strip().splitlines() or [f"código {r.returncode}"])[-1][:80])
    return json.loads(lineas[-1])


# ---------------------------------------------------------------- respaldo geométrico
CARGADOS = {("ASP", "OD1"), ("ASP", "OD2"), ("GLU", "OE1"), ("GLU", "OE2"), ("LYS", "NZ"), ("ARG", "NH1"),
            ("ARG", "NH2"), ("ARG", "NE"), ("HIS", "ND1"), ("HIS", "NE2")}


def interacciones_geometricas(complejo):
    """Criterios por distancia (puente H ≤ 3.5 Å N/O–N/O; hidrofóbica ≤ 4.0 Å C–C; salina ≤ 4.0 Å)."""
    rec, lig = [], []
    for l in open(complejo):
        if l[:6] not in ("ATOM  ", "HETATM"):
            continue
        el = (l[76:78].strip() or l[12:16].strip()[:1]).upper()
        a = dict(nombre=l[12:16].strip(), res=l[17:20].strip(), cad=l[21], num=l[22:26].strip(), el=el,
                 xyz=np.array([float(l[30:38]), float(l[38:46]), float(l[46:54])]))
        (lig if l[17:20] == "LIG" else rec).append(a)
    filas, vistos = [], set()
    for ra in rec:
        for la in lig:
            if la["el"] == "H" or ra["el"] == "H":
                continue
            d = float(np.linalg.norm(ra["xyz"] - la["xyz"]))
            if d > 4.0:
                continue
            tipo = None
            if ra["el"] in ("N", "O") and la["el"] in ("N", "O") and d <= 3.5:
                tipo = "puente_h"
            elif (ra["res"], ra["nombre"]) in CARGADOS and la["el"] in ("N", "O"):
                tipo = "puente_salino"
            elif ra["el"] == "C" and la["el"] == "C":
                tipo = "hidrofobica"
            if tipo and (ra["cad"], ra["num"], tipo) not in vistos:
                vistos.add((ra["cad"], ra["num"], tipo))
                filas.append(dict(tipo=tipo, residuo=f"{ra['res']}{ra['num']}", cadena=ra["cad"],
                                  distancia=round(d, 2), detalle="geométrico"))
    return filas


# ---------------------------------------------------------------- paso
def ejecutar(P, rehacer=False):
    titulo("7 · Complejos e interacciones")
    import importlib.util
    if importlib.util.find_spec("plip"):
        motor = "PLIP"
    else:
        motor = "geométrico"
        log("  · PLIP no está instalado: uso criterios geométricos por distancia")
    poses = sorted(glob.glob(P.r("04_Docking", "MejoresPoses", "*__*.pdbqt")))
    if not poses:
        log("  Aún no hay mejores poses (corre 'docking' y 'resumen').")
        return 0
    dianas = {d["id"]: d for d in P.cfg["dianas"]}
    controles = {c["id"] for c in P.cfg["controles"]}
    detalle, resumen, fallos = [], [], 0
    for pose in poses:
        did, lid = os.path.basename(pose)[:-6].split("__", 1)
        if did not in dianas:
            continue
        try:
            comp, enlaces = construir_complejo(P, dianas[did], lid, pose, lid in controles)
            if not comp:
                log(f"  ✘ {did} + {lid}: falta el receptor limpio"); fallos += 1; continue
            usado = motor
            try:
                filas = interacciones_plip_sub(comp) if motor == "PLIP" else interacciones_geometricas(comp)
            except Exception as e:  # noqa: BLE001
                log(f"    ⚠ PLIP falló con {lid} ({str(e)[:60]}); uso criterio geométrico")
                filas, usado = interacciones_geometricas(comp), "geométrico"
            for f in filas:
                f.update(diana=did, ligando=lid, metodo=usado)
            detalle += filas
            cuenta = Counter(f["tipo"] for f in filas)
            residuos = Counter(f"{f['residuo']}{f['cadena']}" for f in filas)
            resumen.append(dict(diana=did, ligando=lid, total=len(filas),
                                **{TIPOS_ES[t]: cuenta.get(t, 0) for t in TIPOS_ES},
                                residuos=", ".join(r for r, _ in residuos.most_common()),
                                complejo=P.rel(comp)))
            log(f"  ✔ {did} + {lid}: {len(filas)} interacciones  "
                + "  ".join(f"{TIPOS_ES[t]} {n}" for t, n in cuenta.most_common()))
        except Exception as e:  # noqa: BLE001
            log(f"  ✘ {did} + {lid}: {e}"); fallos += 1
    campos = ["diana", "ligando", "tipo", "residuo", "cadena", "distancia", "detalle", "metodo"]
    with open(P.r("05_Analisis", "interacciones_detalle.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos); w.writeheader()
        for f in sorted(detalle, key=lambda x: (x["diana"], x["ligando"], x["tipo"], x["distancia"])):
            w.writerow({k: (TIPOS_ES.get(f[k], f[k]) if k == "tipo" else f[k]) for k in campos})
    if resumen:
        with open(P.r("05_Analisis", "interacciones_resumen.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(resumen[0])); w.writeheader(); w.writerows(resumen)
    # añade hojas al Excel si existe
    try:
        import pandas as pd
        xl = glob.glob(P.r("05_Analisis", "*_afinidades.xlsx"))
        if xl and resumen:
            with pd.ExcelWriter(xl[0], mode="a", if_sheet_exists="replace") as xw:
                pd.DataFrame(resumen).to_excel(xw, sheet_name="Interacciones", index=False)
                pd.read_csv(P.r("05_Analisis", "interacciones_detalle.csv")).to_excel(
                    xw, sheet_name="Interacciones_detalle", index=False)
    except Exception:  # noqa: BLE001
        pass
    log(f"\n  Complejos en 04_Docking/Complejos/ · tablas en 05_Analisis/interacciones_*.csv · método: {motor}")
    return fallos


if __name__ == "__main__":
    import json
    import sys
    if sys.argv[1] == "plip":
        print(json.dumps(interacciones_plip(sys.argv[2])))
