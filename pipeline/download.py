"""Paso 'download': receptores (RCSB / AlphaFold), ligandos de PubChem y ligandos cristalográficos."""
import os
import time

from common import log, title
from axd.infra import net
from axd.domain.sources import TargetSource, LigandSource


def run(P, rehacer=False):
    title("1 · Descargas")
    fallos = 0
    crudos = P.layout.receptors_raw_dir()
    for d in P.cfg["targets"]:
        actual = P.r(d["file"]) if d.get("file") else None
        if actual and os.path.exists(actual) and (not rehacer or d["source"] == "file"):
            log(f"  = {d['id']}: {d['file']}")
        else:
            source = TargetSource.create(d["source"])
            try:
                arch = source.download(d, crudos, net)
                d["file"] = P.rel(arch)
                log(f"  ✔ {d['id']}: {source.describe(d, arch)}")
            except IOError as e:
                log(f"  ✘ {d['id']}: {e}"); fallos += 1

        # ligando cristalográfico con órdenes de enlace (para redocking)
        box = d.get("box", {})
        if box.get("mode") == "ligand" and d.get("pdb"):
            dest = P.ref_sdf(d)
            if os.path.exists(dest) and not rehacer:
                continue
            res, cad = (box["ref"].split(":") + [""])[:2]
            urls = [f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&auth_asym_id={cad}&encoding=sdf",
                    f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&encoding=sdf"]
            for u in urls:
                try:
                    net.download(u, dest, attempts=2)
                    log(f"    ✔ ligando cristalográfico {box['ref']} (SDF con enlaces)")
                    break
                except IOError:
                    continue
            else:
                log(f"    · sin SDF del ligando {box['ref']}; para redocking se usará el PDB (Open Babel)")

    for key, folder in (("ligands", P.layout.ligands_dir()), ("controls", P.layout.controls_dir())):
        for l in P.cfg[key]:
            source = LigandSource.create(l["source"])
            if source is None:  # 'file'/'smiles': ya tienen su archivo, o se resuelven en otro paso
                continue
            if l.get("file") and os.path.exists(P.r(l["file"])):
                log(f"  = {l['id']}: {l['file']}")
                continue
            try:
                arch, desc = source.download(l, folder, net)
                l["file"] = P.rel(arch)
                log(f"  ✔ {l['id']}: {desc}")
            except IOError as e:
                log(f"  ✘ {l['id']}: {e}"); fallos += 1
            if source.rate_limited:
                time.sleep(0.25)
    P.save()
    log(f"\n  Descargas terminadas · {fallos} fallo(s)")
    return fallos
