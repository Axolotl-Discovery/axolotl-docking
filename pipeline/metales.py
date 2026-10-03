"""Ligandos con átomos poco comunes (vanadio, platino, rutenio, cobre…) → AutoDock4.

Por qué AutoDock4 y no smina/Vina: Vina/smina sólo conocen un conjunto fijo de tipos de átomo y no
aceptan V, Pt, Ru, etc. AutoDock4 permite añadir tipos nuevos con una línea `atom_par` en su archivo de
parámetros (procedimiento documentado por los autores de AutoDock).

Cómo se generan los parámetros de un elemento nuevo (queda escrito en 05_Analisis/parametros_metales.txt):
  · Rii (diámetro de van der Waals) y epsii (pozo de energía) = x1 y D1 del Universal Force Field
    (Rappé et al., J. Am. Chem. Soc. 1992, 114, 10024), leídos del UFF.prm de Open Babel del entorno.
  · vol = volumen de la esfera de diámetro Rii (misma convención que C, N, O en AD4).
  · solpar = −0.00110 y sin puentes de H, igual que los metales de AD4 (Mg, Mn, Fe, Zn, Ca).
Cargas parciales del ligando: EEM (Bultinck et al.) con Open Babel, conservando la carga formal total.
Los clusters (orto-, tetra-, decavanadato…) se tratan como cuerpos rígidos.

ADVERTENCIA (se repite en los logs): son parámetros genéricos, no ajustados para cada metal. Las energías
sirven para comparar poses/sitios entre sí, no como afinidades absolutas; conviene validar con
dinámica molecular o cálculos QM/MM.
"""
import glob
import math
import os
import re
import shutil
import subprocess

from comun import correr, en_tmp, herramienta, log

# tipos que smina/Vina entienden; cualquier otro obliga a usar AutoDock4
TIPOS_SMINA = {"C", "A", "N", "NA", "NS", "OA", "OS", "O", "S", "SA", "P", "F", "Cl", "CL", "Br", "BR", "I",
               "H", "HD", "HS", "G0", "G1", "G2", "G3", "CG0", "CG1", "CG2", "CG3", "Mg", "MG", "Zn", "ZN",
               "Fe", "FE", "Mn", "MN", "Ca", "CA"}
ELEMENTOS_ORGANICOS = {"H", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I", "B", "Si", "Se"}
EN_AD4 = {"H", "HD", "HS", "C", "A", "N", "NA", "NS", "OA", "OS", "F", "Mg", "MG", "P", "SA", "S", "Cl", "CL",
          "Ca", "CA", "Mn", "MN", "Fe", "FE", "Zn", "ZN", "Br", "BR", "I"}


# ---------------------------------------------------------------- tipos
def tipos_pdbqt(pdbqt):
    t = set()
    for l in open(pdbqt, errors="ignore"):
        if l[:6] in ("ATOM  ", "HETATM"):
            t.add(l[77:79].strip())
    return t


def necesita_ad4(pdbqt):
    return bool(tipos_pdbqt(pdbqt) - TIPOS_SMINA)


def es_metalico(elementos):
    return bool(set(elementos) - ELEMENTOS_ORGANICOS)


# ---------------------------------------------------------------- ligando metálico → PDBQT rígido
def preparar_ligando_metalico(ruta, salida, nombre):
    """Lee la estructura 3D con Open Babel, asigna cargas EEM y escribe un PDBQT rígido con tipos AD4."""
    from openbabel import pybel
    fmt = os.path.splitext(ruta)[1].lstrip(".").lower() or "sdf"
    fmt = {"mol": "mdl"}.get(fmt, fmt)
    mol = next(pybel.readfile(fmt, ruta))
    xyz = [a.coords for a in mol.atoms]
    if not any(abs(c[2]) > 1e-3 for c in xyz):
        raise ValueError("necesita una estructura 3D (2D/plana no sirve para un cluster metálico). "
                         "Usa 'PDB:CÓDIGO' (p. ej. PDB:DVT decavanadato, PDB:VO4 vanadato) o un archivo 3D")
    tiene_c = any(a.atomicnum == 6 for a in mol.atoms)
    if tiene_c and not any(a.atomicnum == 1 for a in mol.atoms):
        mol.addh()  # sólo si hay parte orgánica sin hidrógenos
    carga_formal = sum(a.OBAtom.GetFormalCharge() for a in mol.atoms)
    metodo = "EEM"
    try:
        q = mol.calccharges("eem")
        if any(math.isnan(x) or abs(x) > 4 for x in q) or abs(sum(q) - carga_formal) > 0.05:
            raise ValueError
    except Exception:  # noqa: BLE001
        q = [float(a.OBAtom.GetFormalCharge()) for a in mol.atoms]
        metodo = "carga formal"
    lineas, elementos = ["ROOT"], []
    for i, (a, carga) in enumerate(zip(mol.atoms, q), 1):
        ob = a.OBAtom
        el = pybel.ob.GetSymbol(a.atomicnum)
        elementos.append(el)
        vecinos = [pybel.ob.GetSymbol(n.GetAtomicNum()) for n in pybel.ob.OBAtomAtomIter(ob)]
        if el == "H":
            t = "HD" if any(v in ("N", "O") for v in vecinos) else "H"
        elif el == "C":
            t = "A" if ob.IsAromatic() else "C"
        elif el == "N":
            t = "N" if "H" in vecinos else "NA"
        elif el == "O":
            t = "OA"
        elif el == "S":
            t = "SA"
        else:
            t = el
        x, y, z = a.coords
        lineas.append(f"HETATM{i:5d} {(el + str(i))[:4]:<4s} LIG L   1    {x:8.3f}{y:8.3f}{z:8.3f}"
                      f"{1.0:6.2f}{0.0:6.2f}    {carga:6.3f} {t:<2s}")
    lineas += ["ENDROOT", "TORSDOF 0"]
    open(salida + ".part", "w").write("REMARK  ligando rígido con átomos no comunes (Axolotl Docking)\n"
                                      + "\n".join(lineas) + "\n")
    os.replace(salida + ".part", salida)
    # plantilla para construir complejos después
    prep = os.path.join(os.path.dirname(salida), "prep", f"{nombre}_H.sdf")
    os.makedirs(os.path.dirname(prep), exist_ok=True)
    mol.write("sdf", prep, overwrite=True)
    raros = sorted(set(elementos) - ELEMENTOS_ORGANICOS)
    return dict(elementos=raros, carga=carga_formal, metodo=metodo, n=len(elementos))


def preparar_en_subproceso(ruta, salida, nombre):
    """Open Babel corre en un proceso aparte (evita choques con RDKit en el mismo proceso)."""
    import json
    import sys
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "preparar", ruta, salida, nombre],
                       capture_output=True, text=True)
    lineas = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if r.returncode != 0 or not lineas:
        err = (r.stderr.strip().splitlines() or ["error desconocido"])[-1]
        raise ValueError(err.replace("ValueError: ", ""))
    return json.loads(lineas[-1])


# ---------------------------------------------------------------- parámetros AD4
def _uff_prm():
    pref = os.environ.get("CONDA_PREFIX", "")
    for patron in (os.path.join(pref, "share", "openbabel", "*", "UFF.prm"),
                   os.path.join(pref, "lib", "python3*", "site-packages", "openbabel", "share", "openbabel", "*", "UFF.prm")):
        for f in glob.glob(patron):
            return f
    d = os.environ.get("BABEL_DATADIR")  # (sin importar openbabel: choca con RDKit en el mismo proceso)
    if d and os.path.exists(os.path.join(d, "UFF.prm")):
        return os.path.join(d, "UFF.prm")
    import sys
    for f in glob.glob(os.path.join(sys.prefix, "**", "UFF.prm"), recursive=True):
        return f
    return None


def parametros_uff(elemento):
    f = _uff_prm()
    if not f:
        raise ValueError("no encontré UFF.prm de Open Babel para derivar parámetros")
    for l in open(f):
        if l.startswith("param"):
            p = l.split()
            m = re.match(r"([A-Z][a-z]?)", p[1])
            if m and m.group(1) == elemento:
                return p[1], float(p[4]), float(p[5])  # tipo UFF, x1 (Å), D1 (kcal/mol)
    raise ValueError(f"UFF no tiene parámetros para {elemento}")


URL_AD4 = "https://raw.githubusercontent.com/ccsb-scripps/AutoDock4/master/AD4.1_bound.dat"


def _base_ad4():
    """Archivo de parámetros AD4.1 oficial: el de ADFRsuite, uno ya descargado, o se baja del repositorio
    oficial de AutoDock4 (ccsb-scripps/AutoDock4)."""
    cache = os.path.expanduser("~/.config/axolotl-docking/AD4.1_bound.dat")
    for base in (os.path.expanduser("~/tools/ADFRsuite-1.0"),
                 os.path.dirname(os.path.dirname(herramienta("autodock4") or "/x/y"))):
        for nombre in ("AD4.1_bound.dat", "AD4_parameters.dat"):
            r = glob.glob(os.path.join(base, "**", nombre), recursive=True)
            if r:
                return r[0]
    if os.path.exists(cache):
        return cache
    try:
        import urllib.request
        with urllib.request.urlopen(URL_AD4, timeout=30) as r:
            datos = r.read()
        if b"atom_par OA" in datos:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            open(cache, "wb").write(datos)
            return cache
    except Exception:  # noqa: BLE001
        pass
    return None


def escribir_parametros(P, tipos_extra):
    """Crea 04_Docking/Mapas/AD4_axd.dat (base AD4.1 + tipos nuevos) y documenta la derivación."""
    os.makedirs(P.r("04_Docking", "Mapas"), exist_ok=True)
    destino = P.r("04_Docking", "Mapas", "AD4_axd.dat")
    base = _base_ad4()
    texto = open(base).read() if base else ""
    extra, doc = [], []
    for t in sorted(tipos_extra):
        if re.search(rf"^atom_par\s+{re.escape(t)}\s", texto, re.M):
            continue
        tipo_uff, x1, d1 = parametros_uff(t)
        vol = 4.0 / 3.0 * math.pi * (x1 / 2.0) ** 3
        extra.append(f"atom_par {t:<4s} {x1:6.3f} {d1:7.4f} {vol:8.4f} -0.00110  0.0  0.0  0  -1  -1  4"
                     f"    # UFF {tipo_uff} (Rappé 1992)")
        doc.append(f"  {t:4s} Rii = {x1:.3f} Å  epsii = {d1:.4f} kcal/mol  vol = {vol:.2f} Å³  solpar = -0.00110"
                   f"   (UFF {tipo_uff})")
    if not texto:
        raise ValueError("no encontré el archivo de parámetros AD4.1_bound.dat (ni en ADFRsuite ni pude descargarlo "
                         "de GitHub). Revisa tu conexión y vuelve a correr")
    with open(destino, "w") as fh:
        fh.write(texto.rstrip() + "\n")
        if extra:
            fh.write("# --- tipos añadidos por Axolotl Docking (UFF: Rappé et al. 1992) ---\n" + "\n".join(extra) + "\n")
    open(P.r("05_Analisis", "parametros_metales.txt"), "w").write(
        "Parámetros AutoDock4 para átomos no estándar (Axolotl Docking)\n"
        f"Archivo usado: 04_Docking/Mapas/AD4_axd.dat  (base: {base or 'parámetros internos de AutoDock4'})\n\n"
        + ("\n".join(doc) if doc else "  (no hizo falta añadir tipos)") + "\n\n"
        "Rii y epsii = x1 y D1 del Universal Force Field (Rappé et al., JACS 1992, 114, 10024);\n"
        "vol = esfera de diámetro Rii; solpar y ausencia de puentes de H como los metales de AD4.\n"
        "Cargas del ligando: EEM (Open Babel) con carga total = carga formal. Ligando rígido.\n"
        "Aviso: parámetros genéricos; interpretar energías de forma comparativa y validar (DM, QM/MM).\n")
    return destino, base


# ---------------------------------------------------------------- AutoDock4
def _npts(size, spacing=0.375):
    n = int(math.ceil(size / spacing))
    n += n % 2
    return max(10, min(n, 126))


def preparar_mapas(P, diana_id, receptor, caja, tipos_lig, param):
    """Corre autogrid4 una vez por diana (con todos los tipos de ligando del proyecto)."""
    carpeta = P.r("04_Docking", "Mapas", diana_id)
    marca = os.path.join(carpeta, "tipos.txt")
    clave = " ".join(sorted(tipos_lig)) + f" | {caja['center']} {caja['size']}"
    if os.path.exists(marca) and open(marca).read() == clave:
        return carpeta
    autogrid = herramienta("autogrid4", ["~/tools/ADFRsuite-1.0/bin/autogrid4"])
    if not autogrid:
        raise ValueError("autogrid4 no está (viene con ADFRsuite: corre 'Docking entorno')")
    tmp = en_tmp("grid")
    try:
        shutil.copy(receptor, os.path.join(tmp, "rec.pdbqt"))
        shutil.copy(param, os.path.join(tmp, "AD4_axd.dat"))
        rec_tipos = sorted(tipos_pdbqt(receptor))
        npts = [_npts(s) for s in caja["size"]]
        if any(_npts(s) == 126 and s / 0.375 > 126 for s in caja["size"]):
            log("    ⚠ la caja excede el máximo de AutoDock4 (~47 Å por eje); se recorta al centro")
        tl = sorted(tipos_lig)
        gpf = [f"npts {npts[0]} {npts[1]} {npts[2]}", "parameter_file AD4_axd.dat", "gridfld rec.maps.fld",
               "spacing 0.375", "receptor_types " + " ".join(rec_tipos), "ligand_types " + " ".join(tl),
               "receptor rec.pdbqt", "gridcenter {:.3f} {:.3f} {:.3f}".format(*caja["center"]), "smooth 0.5"]
        gpf += [f"map rec.{t}.map" for t in tl] + ["elecmap rec.e.map", "dsolvmap rec.d.map", "dielectric -0.1465"]
        open(os.path.join(tmp, "rec.gpf"), "w").write("\n".join(gpf) + "\n")
        rc, out = correr([autogrid, "-p", "rec.gpf", "-l", "rec.glg"], cwd=tmp)
        if not os.path.exists(os.path.join(tmp, "rec.e.map")):
            glg = open(os.path.join(tmp, "rec.glg"), errors="ignore").read() if os.path.exists(os.path.join(tmp, "rec.glg")) else out
            raise ValueError("autogrid4 falló: " + (glg.strip().splitlines() or ["?"])[-1][:150])
        if os.path.isdir(carpeta):
            shutil.rmtree(carpeta)
        shutil.copytree(tmp, carpeta)
        open(marca, "w").write(clave)
        return carpeta
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def correr_ad4(mapas, lig, salida, semilla, d):
    """Docking con autodock4 (LGA). Escribe la salida como PDBQT multi-modelo compatible con el resto
    del pipeline (REMARK minimizedAffinity = energía libre estimada de AD4)."""
    autodock = herramienta("autodock4", ["~/tools/ADFRsuite-1.0/bin/autodock4"])
    if not autodock:
        raise ValueError("autodock4 no está (viene con ADFRsuite: corre 'Docking entorno')")
    tmp = en_tmp("ad4")
    try:
        for f in os.listdir(mapas):
            if f.endswith((".map", ".fld", ".xyz", ".dat")):
                os.symlink(os.path.join(mapas, f), os.path.join(tmp, f))
        shutil.copy(lig, os.path.join(tmp, "lig.pdbqt"))
        txt = open(lig, errors="ignore").read().splitlines()
        tipos = sorted(tipos_pdbqt(lig))
        xyz = [(float(l[30:38]), float(l[38:46]), float(l[46:54])) for l in txt if l[:6] in ("ATOM  ", "HETATM")]
        about = [sum(c[i] for c in xyz) / len(xyz) for i in range(3)]
        flexible = any(l.startswith("BRANCH") for l in txt)
        runs = int(d.get("ad4_runs", 20))
        dpf = ["autodock_parameter_version 4.2", "outlev 1", "parameter_file AD4_axd.dat", "intelec",
               f"seed {semilla} {semilla * 7 + 1}", "ligand_types " + " ".join(tipos), "fld rec.maps.fld"]
        dpf += [f"map rec.{t}.map" for t in tipos] + ["elecmap rec.e.map", "desolvmap rec.d.map",
                                                       "move lig.pdbqt", "about {:.3f} {:.3f} {:.3f}".format(*about),
                                                       "tran0 random", "quaternion0 random"]
        if flexible:
            dpf.append("dihe0 random")
        dpf += ["rmstol 2.0", "extnrg 1000.0", "e0max 0.0 10000", "ga_pop_size 150",
                f"ga_num_evals {int(d.get('ad4_evals', 2500000))}", "ga_num_generations 27000", "ga_elitism 1",
                "ga_mutation_rate 0.02", "ga_crossover_rate 0.8", "ga_window_size 10", "ga_cauchy_alpha 0.0",
                "ga_cauchy_beta 1.0", "set_ga", "sw_max_its 300", "sw_max_succ 4", "sw_max_fail 4", "sw_rho 1.0",
                "sw_lb_rho 0.01", "ls_search_freq 0.06", "set_psw1", "unbound_model bound", f"ga_run {runs}",
                "analysis"]
        open(os.path.join(tmp, "lig.dpf"), "w").write("\n".join(dpf) + "\n")
        rc, out = correr([autodock, "-p", "lig.dpf", "-l", "lig.dlg"], cwd=tmp)
        dlg = os.path.join(tmp, "lig.dlg")
        poses = leer_dlg(dlg) if os.path.exists(dlg) else []
        open(salida[:-6] + ".log", "w").write("\n".join(dpf) + "\n\n" + out
                                             + (open(dlg, errors="ignore").read()[-4000:] if os.path.exists(dlg) else ""))
        if not poses:
            return None
        poses.sort(key=lambda p: p[0])
        modelos = []
        for k, (e, atomos) in enumerate(poses[:int(d.get("num_modes", 9))], 1):
            modelos.append(f"MODEL {k}\nREMARK minimizedAffinity {e:.4f}\nREMARK motor AutoDock4\n"
                           + "\n".join(atomos) + "\nENDMDL")
        open(salida + ".part", "w").write("\n".join(modelos) + "\n")
        os.replace(salida + ".part", salida)
        return poses[0][0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def leer_dlg(dlg):
    """[(energía, [líneas de átomos PDBQT])] de cada corrida del DLG."""
    poses, atomos, e = [], [], None
    for l in open(dlg, errors="ignore"):
        if not l.startswith("DOCKED: "):
            continue
        x = l[8:].rstrip("\n")
        if x.startswith("MODEL"):
            atomos, e = [], None
        elif "Estimated Free Energy of Binding" in x:
            m = re.search(r"=\s*([-+]?\d+\.?\d*)", x)
            e = float(m.group(1)) if m else None
        elif x.startswith(("ATOM", "HETATM")):
            atomos.append(x)
        elif x.startswith("ENDMDL") and atomos and e is not None:
            poses.append((e, atomos))
    return poses


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if sys.argv[1] == "preparar":
        print(json.dumps(preparar_ligando_metalico(*sys.argv[2:5])))
