"""Paso 'descargar': receptores (RCSB / AlphaFold), ligandos de PubChem y ligandos cristalográficos."""
import json
import os
import time
import urllib.request

from comun import log, titulo
from axd.infra import net


def ejecutar(P, rehacer=False):
    titulo("1 · Descargas")
    fallos = 0
    crudos = P.layout.receptors_raw_dir()
    for d in P.cfg["dianas"]:
        actual = P.r(d["archivo"]) if d.get("archivo") else None
        if actual and os.path.exists(actual) and (not rehacer or d["fuente"] == "archivo"):
            log(f"  = {d['id']}: {d['archivo']}")
        elif d["fuente"] == "pdb":
            ok = False
            for ext in ("pdb", "cif"):
                dest = os.path.join(crudos, f"{d['id']}.{ext}")
                try:
                    net.bajar(f"https://files.rcsb.org/download/{d['pdb']}.{ext}", dest, intentos=3)
                    d["archivo"] = P.rel(dest); ok = True
                    log(f"  ✔ {d['id']}: RCSB {d['pdb']}.{ext}")
                    break
                except IOError:
                    continue
            if not ok:
                log(f"  ✘ {d['id']}: no se pudo descargar {d['pdb']} de RCSB"); fallos += 1
        elif d["fuente"] == "alphafold":
            dest = os.path.join(crudos, f"{d['id']}.pdb")
            try:
                with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{d['uniprot']}", timeout=60) as r:
                    info = json.load(r)[0]
                net.bajar(info["pdbUrl"], dest, intentos=3)
                d["archivo"] = P.rel(dest)
                log(f"  ✔ {d['id']}: AlphaFold {d['uniprot']}")
            except Exception as e:  # noqa: BLE001
                log(f"  ✘ {d['id']}: AlphaFold {d['uniprot']} ({e})"); fallos += 1
        else:
            log(f"  ✘ {d['id']}: falta el archivo local {d.get('archivo')}"); fallos += 1

        # ligando cristalográfico con órdenes de enlace (para redocking)
        caja = d.get("caja", {})
        if caja.get("modo") == "ligando" and d.get("pdb"):
            dest = P.ref_sdf(d)
            if os.path.exists(dest) and not rehacer:
                continue
            res, cad = (caja["ref"].split(":") + [""])[:2]
            urls = [f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&auth_asym_id={cad}&encoding=sdf",
                    f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&encoding=sdf"]
            for u in urls:
                try:
                    net.bajar(u, dest, intentos=2)
                    log(f"    ✔ ligando cristalográfico {caja['ref']} (SDF con enlaces)")
                    break
                except IOError:
                    continue
            else:
                log(f"    · sin SDF del ligando {caja['ref']}; para redocking se usará el PDB (Open Babel)")

    for clave, carpeta in (("ligandos", P.layout.ligands_dir()), ("controles", P.layout.controls_dir())):
        for l in P.cfg[clave]:
            if l["fuente"] == "ccd":
                if l.get("archivo") and os.path.exists(P.r(l["archivo"])):
                    log(f"  = {l['id']}: {l['archivo']}"); continue
                dest = os.path.join(carpeta, l["id"] + ".sdf")
                for suf, desc in (("ideal", "coordenadas ideales"), ("model", "coordenadas de un cristal")):
                    try:
                        net.bajar(f"https://files.rcsb.org/ligands/download/{l['codigo']}_{suf}.sdf", dest, intentos=2)
                        l["archivo"] = P.rel(dest)
                        log(f"  ✔ {l['id']}: componente PDB {l['codigo']} ({desc})")
                        break
                    except IOError:
                        continue
                else:
                    log(f"  ✘ {l['id']}: el código PDB '{l['codigo']}' no existe o no tiene coordenadas"); fallos += 1
                continue
            if l["fuente"] != "pubchem":
                continue
            if l.get("archivo") and os.path.exists(P.r(l["archivo"])):
                log(f"  = {l['id']}: {l['archivo']}")
                continue
            try:
                ruta, tipo = net.pubchem_sdf(str(l.get("cid") or l["consulta"]), os.path.join(carpeta, l["id"]))
                l["archivo"] = P.rel(ruta)
                log(f"  ✔ {l['id']}: PubChem '{l['consulta']}' {tipo}")
            except IOError as e:
                log(f"  ✘ {l['id']}: PubChem no encontró '{l['consulta']}' ({e})"); fallos += 1
            time.sleep(0.25)  # PubChem pide ≤ 5 peticiones/s
    P.guardar()
    log(f"\n  Descargas terminadas · {fallos} fallo(s)")
    return fallos
