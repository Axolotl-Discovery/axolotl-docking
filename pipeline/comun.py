"""Funciones compartidas por los pasos del pipeline (corren dentro del entorno conda)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from axd.config import cargar_proyecto, guardar_proyecto  # noqa: E402,F401

try:  # silencia los avisos informativos de RDKit ("tagged as 2D", "More than one matching pattern")
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:
    pass

AD2EL = {"A": "C", "C": "C", "OA": "O", "O": "O", "NA": "N", "N": "N", "NS": "N", "SA": "S", "S": "S",
         "P": "P", "F": "F", "Cl": "Cl", "CL": "Cl", "Br": "Br", "BR": "Br", "I": "I", "HD": "H", "HS": "H",
         "H": "H", "Mg": "Mg", "MG": "Mg", "Zn": "Zn", "ZN": "Zn", "Fe": "Fe", "FE": "Fe", "Ca": "Ca",
         "CA": "Ca", "Mn": "Mn", "MN": "Mn", "Si": "Si", "B": "B"}


class Proyecto:
    def __init__(self, raiz):
        self.raiz = os.path.abspath(raiz)
        self.cfg = cargar_proyecto(self.raiz)

    def guardar(self):
        guardar_proyecto(self.raiz, self.cfg)

    def r(self, *partes):
        return os.path.join(self.raiz, *partes)

    def rel(self, p):
        return os.path.relpath(p, self.raiz)

    # rutas estándar
    def receptor_pdbqt(self, d):
        return self.r("04_Docking", "Receptores", f"{d['id']}.pdbqt")

    def receptor_limpio(self, d):
        return self.r("01_Receptores", "limpios", f"{d['id']}_clean.pdb")

    def ligando_pdbqt(self, lig, control=False):
        return self.r("04_Docking", "Controles" if control else "Ligandos", f"{lig['id']}.pdbqt")

    def ref_sdf(self, d):
        return self.r("03_Controles", "ligando_cristal", f"{d['id']}_ref_cristal.sdf")

    def ref_pdb(self, d):
        return self.r("03_Controles", "ligando_cristal", f"{d['id']}_ref.pdb")

    def cajas(self):
        f = self.r("04_Docking", "cajas.json")
        return json.load(open(f)) if os.path.exists(f) else {}

    def ligandos_para(self, diana_id):
        """[(entrada, es_control)] que se dockean contra una diana."""
        out = [(l, False) for l in self.cfg["ligandos"]]
        out += [(c, True) for c in self.cfg["controles"] if not c.get("diana") or c.get("diana") == diana_id]
        return out


# ---------------------------------------------------------------- salida
def titulo(t):
    print(f"\n━━ {t} " + "━" * max(2, 58 - len(t)), flush=True)


def log(t=""):
    print(t, flush=True)


def herramienta(nombre, extra=()):
    for c in [shutil.which(nombre)] + [os.path.expanduser(x) for x in extra]:
        if c and os.path.exists(c):
            return c
    return None


def en_tmp(prefijo="x"):
    """Carpeta temporal sin espacios (ADFRsuite y smina fallan con espacios en rutas).
    Lleva el PID del grupo para que 'Docking detener' la pueda limpiar."""
    try:
        g = os.getpgid(0)
    except OSError:
        g = os.getpid()
    return tempfile.mkdtemp(prefix=f"axd_{g}_{prefijo}_", dir="/tmp")


def correr(cmd, cwd=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---------------------------------------------------------------- PDBQT
def completo(pdbqt):
    """Una salida cuenta como terminada si tiene afinidad y cierra su último modelo
    (protege contra archivos truncados por un corte de luz)."""
    if not os.path.exists(pdbqt) or os.path.getsize(pdbqt) == 0:
        return False
    txt = open(pdbqt, errors="ignore").read()
    return ("minimizedAffinity" in txt or "VINA RESULT" in txt) and txt.rstrip().endswith("ENDMDL")


def afinidad(pdbqt):
    for l in open(pdbqt, errors="ignore"):
        m = re.search(r"minimizedAffinity\s+(-?\d+\.?\d*)", l) or re.search(r"VINA RESULT:\s+(-?\d+\.?\d*)", l)
        if m:
            return float(m.group(1))
    return None


def elemento_pdbqt(l):
    t = l[77:79].strip()
    return AD2EL.get(t, t[:1].upper() + t[1:].lower() if t else "C")


def pesados_pdbqt(pdbqt):
    n = 0
    for l in open(pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM") and elemento_pdbqt(l) != "H":
            n += 1
    return n


def modelo1(pdbqt):
    """Texto del primer modelo de un PDBQT de salida."""
    out = []
    for l in open(pdbqt, errors="ignore"):
        out.append(l)
        if l.startswith("ENDMDL"):
            break
    return "".join(out)


def pose1_pdb(pdbqt, resname="LIG", cadena="L"):
    """Pose 1 como PDB estándar (sólo átomos pesados), elementos inferidos del tipo AutoDock."""
    out = []
    for l in open(pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM"):
            el = elemento_pdbqt(l)
            if el == "H":
                continue
            n = len(out) + 1
            nom = (el + str(n))[:4]
            out.append(f"HETATM{n:5d} {nom:<4s} {resname:>3s} {cadena}   1    {l[30:54]}  1.00  0.00          {el:>2s}\n")
    return "".join(out) + "END\n"


def ahora():
    return time.strftime("%H:%M:%S")
