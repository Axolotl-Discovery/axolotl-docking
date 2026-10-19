"""Paso 'receptors': limpieza (cadenas, altloc, cofactores), PDBFixer, prepare_receptor y cajas.

Lecciones del entorno Axolotl aplicadas aquí:
  · NUNCA se usa Open Babel para receptores (fragmenta proteínas grandes): se usa prepare_receptor (ADFRsuite).
  · La caja SIEMPRE se calcula de las coordenadas reales del receptor/ligando que se va a usar.
  · ADFRsuite no tolera espacios en rutas → se trabaja en /tmp.
"""
import json
import os
import shutil

import numpy as np

from common import run_cmd, tmp_dir, tool, log, title
from axd.domain.boxes import Box, LigandBox, BoxContext

MODIFICADOS = {"MSE", "TPO", "SEP", "PTR", "CSO", "HYP", "MLY", "KCX", "CME", "OCS", "CSD", "LLP", "M3L", "SCY"}


def _a_pdb(ruta, tmpdir):
    """Convierte mmCIF a PDB con gemmi si hace falta."""
    if not ruta.lower().endswith((".cif", ".mmcif")):
        return ruta
    import gemmi
    st = gemmi.read_structure(ruta)
    st.setup_entities()
    out = os.path.join(tmpdir, "convertido.pdb")
    st.write_pdb(out)
    return out


def _lineas(pdb):
    for l in open(pdb, errors="ignore"):
        if l.startswith("ENDMDL"):
            break  # sólo el primer modelo (NMR / AlphaFold multi-modelo)
        if l[:6] in ("ATOM  ", "HETATM") and l[16] in " A":
            yield l[:16] + " " + l[17:].rstrip("\r\n") + "\n"  # quita el indicador de altloc


def _xyz(lineas, sin_h=True):
    xs = []
    for l in lineas:
        el = l[76:78].strip() or l[12:16].strip()[:1]
        if sin_h and el.upper() == "H":
            continue
        xs.append([float(l[30:38]), float(l[38:46]), float(l[46:54])])
    return np.array(xs)


def _caja(coords, margen, minimo=0.0):
    c = coords.mean(0)
    s = np.maximum(coords.max(0) - coords.min(0) + margen, minimo)
    return [round(float(v), 3) for v in c], [round(float(v), 1) for v in s]


def _spec(texto):
    """'HEM:A' → ('HEM','A'); 'HEM' → ('HEM', None)."""
    a = texto.strip().upper().split(":")
    return a[0], (a[1] if len(a) > 1 and a[1] else None)


def _resolver_auto(d, crudo):
    """Modo básico: decide cadena, cofactores y caja a partir de la estructura."""
    from axd.infra.pdb import COFACTOR_CODES, METAL_CODES, auto_decision, inspect_pdb
    cads, het = inspect_pdb(crudo)
    ref, cad = auto_decision(het, cads)
    if d.get("chains") == "auto":
        d["chains"] = cad
    if d.get("cofactors") == "auto":
        d["cofactors"] = sorted({f"{h[0]}:{h[1]}" for h in het
                                 if h[0] in COFACTOR_CODES | METAL_CODES and (not d["chains"] or h[1] in d["chains"])})
    if d.get("box", {}).get("mode") == "auto":
        d["box"] = ({"mode": "ligand", "ref": ref, "margin": 10.0, "minimum": 22.0, "auto": True} if ref
                    else {"mode": "blind", "margin": 10.0, "auto": True})
    log(f"    automático → cadena {d['chains'] or 'todas'}"
        + (f", cofactores {', '.join(d['cofactors'])}" if d["cofactors"] else "")
        + (f", sitio = ligando {ref}" if d["box"]["mode"] == "ligand" else ", docking ciego (no hay ligando co-cristalizado)"))


def run(P, rehacer=False):
    title("2 · Receptores y cajas de docking")
    prep = tool("prepare_receptor", ["~/tools/ADFRsuite-1.0/bin/prepare_receptor"])
    if not prep:
        log("  ✘ prepare_receptor (ADFRsuite) no está instalado. Corre:  Docking entorno")
        return len(P.cfg["targets"])
    try:
        from openmm.app import PDBFile
        from pdbfixer import PDBFixer
        fixer = True
    except ImportError:
        fixer = False
        log("  ⚠ PDBFixer no disponible: no se completarán átomos faltantes")

    boxes = P.boxes()
    fallos = 0
    cambios = False
    for d in P.cfg["targets"]:
        log(f"\n  ▸ {d['id']}")
        if not d.get("file") or not os.path.exists(P.r(d["file"])):
            log("    ✘ falta la estructura (corre el paso 'download')"); fallos += 1; continue
        salida = P.receptor_pdbqt(d)
        tmp = tmp_dir("rec")
        try:
            crudo = _a_pdb(P.r(d["file"]), tmp)
            if "auto" in (d.get("chains"), d.get("cofactors"), d.get("box", {}).get("mode")):
                _resolver_auto(d, crudo)
                cambios = True
            cadenas = set(d.get("chains") or "")
            cofs = [_spec(x) for x in d.get("cofactors", [])]
            box_cfg = d.get("box", {"mode": "blind", "margin": 10})
            ref_spec = _spec(box_cfg["ref"]) if box_cfg.get("mode") == "ligand" else None

            pol, cof, ref = [], [], []
            ref_res = None
            for l in _lineas(crudo):
                rn, ch = l[17:20].strip(), l[21]
                if cadenas and ch not in cadenas and not (ref_spec and rn == ref_spec[0]):
                    continue
                if l[:6] == "ATOM  ":
                    if not cadenas or ch in cadenas:
                        pol.append(l)
                    continue
                if ref_spec and rn == ref_spec[0] and (ref_spec[1] in (None, ch)):
                    clave = (ch, l[22:27])
                    if ref_res is None:
                        ref_res = clave
                    if clave == ref_res:  # sólo una copia del ligando
                        ref.append(l)
                    continue
                if any(rn == r and (c is None or c == ch) for r, c in cofs):
                    cof.append(l)
                elif rn in MODIFICADOS:
                    pol.append(l)
            if not pol:
                log(f"    ✘ no quedaron átomos de proteína (¿cadenas '{d.get('chains')}' correctas?)"); fallos += 1; continue

            # ---- PDBFixer sobre el polímero
            pol_pdb = os.path.join(tmp, "pol.pdb")
            open(pol_pdb, "w").writelines(pol + ["END\n"])
            if fixer:
                try:
                    fx = PDBFixer(filename=pol_pdb)
                    fx.findMissingResidues(); fx.missingResidues = {}  # no reconstruye lazos
                    fx.findNonstandardResidues(); fx.replaceNonstandardResidues()
                    fx.findMissingAtoms(); fx.addMissingAtoms()
                    with open(pol_pdb, "w") as f:
                        PDBFile.writeFile(fx.topology, fx.positions, f, keepIds=True)
                    n_falt = sum(len(v) for v in fx.missingAtoms.values()) + sum(len(v) for v in fx.missingTerminals.values())
                    log(f"    PDBFixer: {n_falt} átomos pesados completados")
                except Exception as e:  # noqa: BLE001
                    log(f"    ⚠ PDBFixer falló ({str(e)[:80]}); sigo con la estructura original")
            cuerpo = [l for l in open(pol_pdb) if l[:6] in ("ATOM  ", "HETATM", "TER   ")]
            limpio = P.receptor_clean(d)
            open(limpio, "w").writelines(cuerpo + cof + ["END\n"])
            n_at = sum(1 for l in cuerpo if l[:4] == "ATOM")
            log(f"    limpio: {n_at} átomos de proteína, {len(cof)} de cofactores → {P.rel(limpio)}")

            # ---- caja
            mode = box_cfg.get("mode", "blind")
            box_obj = Box.create(box_cfg)
            if isinstance(box_obj, LigandBox) and ref:
                open(P.ref_pdb(d), "w").writelines([l.replace("ATOM  ", "HETATM") for l in ref] + ["END\n"])
            result = box_obj.calculate(BoxContext(body=cuerpo, cofactors=cof, ref=ref, box_fn=_caja, xyz_fn=_xyz))
            if not result.ok:
                log(f"    ✘ {result.error}"); fallos += 1; continue
            if result.warning:
                log(f"    ⚠ {result.warning}")
            c, s, det = result.center, result.size, result.detail
            boxes[d["id"]] = dict(center=c, size=s, mode=mode, detail=det)
            log(f"    caja: centro {c}  tamaño {s} Å  [{det}]")

            # ---- PDBQT con ADFRsuite
            if os.path.exists(salida) and os.path.getsize(salida) > 0 and not rehacer:
                log(f"    = {P.rel(salida)} ya existe")
                continue
            shutil.copy(limpio, os.path.join(tmp, "rec.pdb"))
            rc, out = run_cmd([prep, "-r", "rec.pdb", "-o", "rec.pdbqt", "-A", "hydrogens", "-U", "nphs_lps_waters"],
                              cwd=tmp, timeout=1800)
            open(P.layout.prep_receptor_log(d["id"]), "w").write(out)
            if os.path.exists(os.path.join(tmp, "rec.pdbqt")) and os.path.getsize(os.path.join(tmp, "rec.pdbqt")) > 0:
                shutil.copy(os.path.join(tmp, "rec.pdbqt"), salida)
                log(f"    ✔ prepare_receptor → {P.rel(salida)}")
            else:
                log(f"    ✘ prepare_receptor falló (ver {P.rel(P.layout.prep_receptor_log(d['id']))})"); fallos += 1
        except Exception as e:  # noqa: BLE001
            log(f"    ✘ error: {e}"); fallos += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    json.dump(boxes, open(P.layout.boxes_json(), "w"), indent=2)
    if cambios:
        P.save()  # guarda lo que se decidió automáticamente (cadenas, cofactores, caja)
    log(f"\n  Receptores: {len(P.cfg['targets']) - fallos}/{len(P.cfg['targets'])} listos · "
        f"cajas en {P.rel(P.layout.boxes_json())}")
    return fallos
