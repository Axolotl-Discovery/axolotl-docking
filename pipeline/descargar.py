"""Paso 'descargar': receptores (RCSB / AlphaFold), ligandos de PubChem y ligandos cristalográficos."""
import json
import os
import time
import urllib.parse
import urllib.request

from comun import log, titulo

UA = {"User-Agent": "axolotl-docking"}


def _bajar(url, destino, timeout=90, intentos=3):
    ultimo = None
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                datos = r.read()
            if not datos.strip():
                raise IOError("vacío")
            open(destino, "wb").write(datos)
            return True
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if getattr(e, "code", None) == 404:
                break
            time.sleep(1.5 * (i + 1))
    raise IOError(str(ultimo))


def _pubchem(consulta, destino_base):
    """Descarga SDF 3D (o 2D si no hay 3D). Devuelve la ruta."""
    if consulta.strip().isdigit():
        base = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{consulta.strip()}/SDF"
    else:
        base = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(consulta)}/SDF"
    try:
        _bajar(base + "?record_type=3d", destino_base + ".sdf")
        return destino_base + ".sdf", "3D"
    except IOError:
        _bajar(base + "?record_type=2d", destino_base + ".sdf")
        return destino_base + ".sdf", "2D (se generará 3D con RDKit)"


def ejecutar(P, rehacer=False):
    titulo("1 · Descargas")
    fallos = 0
    crudos = P.r("01_Receptores")
    for d in P.cfg["dianas"]:
        actual = P.r(d["archivo"]) if d.get("archivo") else None
        if actual and os.path.exists(actual) and (not rehacer or d["fuente"] == "archivo"):
            log(f"  = {d['id']}: {d['archivo']}")
        elif d["fuente"] == "pdb":
            ok = False
            for ext in ("pdb", "cif"):
                dest = os.path.join(crudos, f"{d['id']}.{ext}")
                try:
                    _bajar(f"https://files.rcsb.org/download/{d['pdb']}.{ext}", dest)
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
                _bajar(info["pdbUrl"], dest)
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
                    _bajar(u, dest, intentos=2)
                    log(f"    ✔ ligando cristalográfico {caja['ref']} (SDF con enlaces)")
                    break
                except IOError:
                    continue
            else:
                log(f"    · sin SDF del ligando {caja['ref']}; para redocking se usará el PDB (Open Babel)")

    for clave, carpeta in (("ligandos", "02_Ligandos"), ("controles", "03_Controles")):
        for l in P.cfg[clave]:
            if l["fuente"] != "pubchem":
                continue
            if l.get("archivo") and os.path.exists(P.r(l["archivo"])):
                log(f"  = {l['id']}: {l['archivo']}")
                continue
            try:
                ruta, tipo = _pubchem(str(l.get("cid") or l["consulta"]), P.r(carpeta, l["id"]))
                l["archivo"] = P.rel(ruta)
                log(f"  ✔ {l['id']}: PubChem '{l['consulta']}' {tipo}")
            except IOError as e:
                log(f"  ✘ {l['id']}: PubChem no encontró '{l['consulta']}' ({e})"); fallos += 1
            time.sleep(0.25)  # PubChem pide ≤ 5 peticiones/s
    P.guardar()
    log(f"\n  Descargas terminadas · {fallos} fallo(s)")
    return fallos
