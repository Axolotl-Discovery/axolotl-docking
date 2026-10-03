"""Paso 'ligandos': cualquier formato → SDF 3D con hidrógenos (RDKit) → PDBQT (Meeko).

Open Babel sólo se usa para leer formatos que RDKit no lee bien (mol2/pdb) en moléculas pequeñas.
"""
import os
import shutil

import metales
from comun import correr, en_tmp, herramienta, log, titulo


def elementos_de(ruta, smiles=None):
    """Elementos presentes, sin sanitizar (los metales hipervalentes rompen a RDKit) y sin Open Babel
    (Open Babel y RDKit en el mismo proceso pueden chocar)."""
    from rdkit import Chem
    if smiles:
        m = Chem.MolFromSmiles(smiles, sanitize=False)
        return {a.GetSymbol() for a in m.GetAtoms()} if m else set()
    ext = os.path.splitext(ruta)[1].lower()
    txt = open(ruta, errors="ignore").read()
    if ext in (".sdf", ".mol"):
        m = Chem.MolFromMolBlock(txt.split("$$$$")[0], sanitize=False, removeHs=False)
        if m:
            return {a.GetSymbol() for a in m.GetAtoms()}
    if ext in (".pdb", ".pdbqt"):
        return {(l[76:78].strip() or l[12:16].strip()[:1]).capitalize() for l in txt.splitlines()
                if l[:6] in ("ATOM  ", "HETATM")}
    if ext == ".mol2":
        sec, els = False, set()
        for l in txt.splitlines():
            if l.startswith("@<TRIPOS>"):
                sec = l.startswith("@<TRIPOS>ATOM"); continue
            if sec and l.split():
                els.add(l.split()[5].split(".")[0])
        return els
    if ext in (".smi", ".smiles"):
        return elementos_de(None, txt.split()[0])
    return set()


def normalizar_sdf_texto(txt):
    """CL→Cl, BR→Br… (el ModelServer de RCSB escribe elementos en mayúsculas y RDKit los toma como 'query')."""
    salida = []
    for r in txt.split("$$$$"):
        L = r.split("\n")
        i0 = 1 if L and L[0] == "" and len(L) > 4 else 0
        cab = i0 + 3
        if len(L) > cab and L[cab][:3].strip().isdigit():
            na = int(L[cab][:3])
            for k in range(cab + 1, min(len(L), cab + 1 + na)):
                e = L[k][31:34].strip()
                if len(e) == 2 and e.isupper():
                    L[k] = L[k][:31] + (e[0] + e[1].lower()).ljust(3) + L[k][34:]
        salida.append("\n".join(L))
    return "$$$$".join(salida)


def leer_molecula(ruta, smiles=None):
    """Devuelve un Mol de RDKit (sin garantizar 3D)."""
    from rdkit import Chem
    if smiles:
        m = Chem.MolFromSmiles(smiles)
        if m is None:
            raise ValueError(f"SMILES inválido: {smiles}")
        return m
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".smi", ".smiles"):
        linea = next(l for l in open(ruta) if l.strip() and not l.startswith("#"))
        return leer_molecula(None, linea.split()[0])
    if ext in (".sdf", ".mol"):
        bloque = normalizar_sdf_texto(open(ruta, errors="ignore").read()).split("$$$$")[0]
        m = Chem.MolFromMolBlock(bloque, removeHs=False)
        if m is not None:
            return m
    # mol2 / pdb / lo que RDKit no pudo: Open Babel → SDF
    obabel = herramienta("obabel")
    if not obabel:
        raise ValueError("no pude leer el archivo y Open Babel no está disponible")
    tmp = en_tmp("lig")
    try:
        sal = os.path.join(tmp, "x.sdf")
        correr([obabel, ruta, "-O", sal, "-l", "1"])
        if not os.path.exists(sal) or os.path.getsize(sal) == 0:
            raise ValueError("Open Babel no pudo convertir el archivo")
        m = Chem.MolFromMolBlock(open(sal).read().split("$$$$")[0], removeHs=False)
        if m is None:
            raise ValueError("RDKit no pudo interpretar la molécula convertida")
        return m
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def preparar_3d(m, semilla=42):
    """Fragmento mayor (quita sales), hidrógenos y conformero 3D (ETKDGv3 + MMFF) si hace falta."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.MolStandardize import rdMolStandardize
    nota = []
    frags = Chem.GetMolFrags(m, asMols=True, sanitizeFrags=True)
    if len(frags) > 1:
        m = rdMolStandardize.LargestFragmentChooser(preferOrganic=True).choose(m)
        nota.append("sal/solvente removido")
    es3d = m.GetNumConformers() > 0 and float(abs(m.GetConformer().GetPositions()[:, 2]).max()) > 1e-3
    if es3d:
        m = Chem.AddHs(m, addCoords=True)
    else:
        m = Chem.AddHs(Chem.RemoveHs(m))
        ps = AllChem.ETKDGv3(); ps.randomSeed = semilla
        if AllChem.EmbedMolecule(m, ps) != 0:
            ps.useRandomCoords = True
            if AllChem.EmbedMolecule(m, ps) != 0:
                raise ValueError("RDKit no pudo generar un conformero 3D")
        if AllChem.MMFFHasAllMoleculeParams(m):
            AllChem.MMFFOptimizeMolecule(m, maxIters=2000)
        else:
            AllChem.UFFOptimizeMolecule(m, maxIters=2000)
        nota.append("3D generado con RDKit")
    return m, nota


def a_pdbqt(m, salida, nombre):
    """Escribe SDF con H y lo pasa por Meeko (macrociclos rígidos: smina no entiende átomos G/CG)."""
    from rdkit import Chem
    mk = herramienta("mk_prepare_ligand.py")
    if not mk:
        raise ValueError("mk_prepare_ligand.py (Meeko) no está en el entorno")
    sdf = os.path.join(os.path.dirname(salida), "prep", f"{os.path.basename(salida)[:-6]}_H.sdf")
    os.makedirs(os.path.dirname(sdf), exist_ok=True)
    m.SetProp("_Name", nombre)
    w = Chem.SDWriter(sdf); w.write(m); w.close()
    rc, out = correr([mk, "-i", sdf, "-o", salida + ".part", "--rigid_macrocycles"])
    if not (os.path.exists(salida + ".part") and os.path.getsize(salida + ".part") > 0):
        raise ValueError("Meeko falló: " + out.strip().splitlines()[-1][:150] if out.strip() else "Meeko falló")
    os.replace(salida + ".part", salida)


def ejecutar(P, rehacer=False):
    titulo("3 · Ligandos y controles → PDBQT")
    fallos = 0
    total = 0
    for clave, control in (("ligandos", False), ("controles", True)):
        for l in P.cfg[clave]:
            total += 1
            salida = P.ligando_pdbqt(l, control)
            if os.path.exists(salida) and os.path.getsize(salida) > 0 and not rehacer:
                log(f"  = {l['id']}")
                continue
            try:
                if l.get("archivo", "").lower().endswith(".pdbqt"):
                    shutil.copy(P.r(l["archivo"]), salida)
                    log(f"  ✔ {l['id']} (PDBQT ya preparado, copiado)")
                    continue
                if l["fuente"] != "smiles" and not (l.get("archivo") and os.path.exists(P.r(l["archivo"]))):
                    raise ValueError("falta el archivo (corre el paso 'descargar')")
                ruta_l = P.r(l["archivo"]) if l.get("archivo") else None
                els = elementos_de(ruta_l, l.get("smiles"))
                if metales.es_metalico(els):
                    if not ruta_l:
                        raise ValueError("un ligando con metales necesita estructura 3D (archivo o PDB:CÓDIGO), no SMILES")
                    info = metales.preparar_en_subproceso(ruta_l, salida, l["id"])
                    log(f"  ✔ {l['id']:32s} {info['n']:3d} átomos  ⚛ {', '.join(info['elementos'])}  carga {info['carga']:+d}"
                        f"  · cargas {info['metodo']} · rígido · se dockea con AutoDock4"
                        + ("  [control]" if control else ""))
                    continue
                m = leer_molecula(ruta_l, l.get("smiles"))
                m, nota = preparar_3d(m)
                a_pdbqt(m, salida, l["id"])
                from rdkit.Chem import Descriptors
                log(f"  ✔ {l['id']:32s} {m.GetNumHeavyAtoms():3d} át. pesados  PM {Descriptors.MolWt(m):6.1f}"
                    + (f"  ({', '.join(nota)})" if nota else "") + ("  [control]" if control else ""))
            except Exception as e:  # noqa: BLE001
                log(f"  ✘ {l['id']}: {e}"); fallos += 1
    log(f"\n  Ligandos: {total - fallos}/{total} listos")
    return fallos


def preparar_ref_redocking(P, d):
    """Ligando cristalográfico → PDBQT para redocking. Devuelve (pdbqt, mol_ref_sin_H) o (None, None)."""
    from rdkit import Chem
    salida = P.r("04_Docking", "Redocking", f"{d['id']}_cristal.pdbqt")
    ref = None
    if not os.path.exists(P.ref_sdf(d)) and d.get("pdb") and d.get("caja", {}).get("ref"):
        # (modo básico: el ligando se eligió después de 'descargar') — SDF con órdenes de enlace de RCSB
        from descargar import _bajar
        res, cad = (d["caja"]["ref"].split(":") + [""])[:2]
        for u in (f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&auth_asym_id={cad}&encoding=sdf",
                  f"https://models.rcsb.org/v1/{d['pdb']}/ligand?auth_comp_id={res}&encoding=sdf"):
            try:
                _bajar(u, P.ref_sdf(d), intentos=2); break
            except IOError:
                continue
    if os.path.exists(P.ref_sdf(d)):
        txt = normalizar_sdf_texto(open(P.ref_sdf(d), errors="ignore").read())
        # si el SDF trae varias copias, se toma la más cercana a la referencia usada para la caja
        mols = [Chem.MolFromMolBlock(b + "$$$$", removeHs=False) for b in txt.split("$$$$") if b.strip()]
        mols = [x for x in mols if x is not None]
        if mols and os.path.exists(P.ref_pdb(d)):
            import numpy as np
            cref = np.array([[float(l[30:38]), float(l[38:46]), float(l[46:54])]
                             for l in open(P.ref_pdb(d)) if l[:6] == "HETATM"]).mean(0)
            mols.sort(key=lambda x: float(np.linalg.norm(x.GetConformer().GetPositions().mean(0) - cref)))
        ref = mols[0] if mols else None
    if ref is None and os.path.exists(P.ref_pdb(d)):
        try:
            ref = leer_molecula(P.ref_pdb(d))
        except ValueError:
            ref = None
    if ref is None:
        return None, None
    ref_noH = Chem.RemoveHs(ref)
    if not (os.path.exists(salida) and os.path.getsize(salida) > 0):
        a_pdbqt(Chem.AddHs(ref_noH, addCoords=True), salida, f"{d['id']}_cristal")
    return salida, ref_noH
