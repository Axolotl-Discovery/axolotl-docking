"""Paso 'descargar': receptores (RCSB / AlphaFold), ligandos de PubChem y ligandos cristalográficos."""
import os
import time

from comun import log, titulo
from axd.infra import net
from axd.domain.fuentes import FuenteDiana, FuenteLigando


def ejecutar(P, rehacer=False):
    titulo("1 · Descargas")
    fallos = 0
    crudos = P.layout.receptors_raw_dir()
    for d in P.cfg["dianas"]:
        actual = P.r(d["archivo"]) if d.get("archivo") else None
        if actual and os.path.exists(actual) and (not rehacer or d["fuente"] == "archivo"):
            log(f"  = {d['id']}: {d['archivo']}")
        else:
            fuente = FuenteDiana.crear(d["fuente"])
            try:
                arch = fuente.descargar(d, crudos, net)
                d["archivo"] = P.rel(arch)
                log(f"  ✔ {d['id']}: {fuente.describir(d, arch)}")
            except IOError as e:
                log(f"  ✘ {d['id']}: {e}"); fallos += 1

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
            fuente = FuenteLigando.crear(l["fuente"])
            if fuente is None:  # 'archivo'/'smiles': ya tienen su archivo, o se resuelven en otro paso
                continue
            if l.get("archivo") and os.path.exists(P.r(l["archivo"])):
                log(f"  = {l['id']}: {l['archivo']}")
                continue
            try:
                arch, desc = fuente.descargar(l, carpeta, net)
                l["archivo"] = P.rel(arch)
                log(f"  ✔ {l['id']}: {desc}")
            except IOError as e:
                log(f"  ✘ {l['id']}: {e}"); fallos += 1
            if fuente.limitar_tasa:
                time.sleep(0.25)
    P.guardar()
    log(f"\n  Descargas terminadas · {fallos} fallo(s)")
    return fallos
