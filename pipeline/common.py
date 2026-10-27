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
from axd.config import load_project, save_project  # noqa: E402,F401
from axd.layout import Layout  # noqa: E402

try:  # silencia los avisos informativos de RDKit ("tagged as 2D", "More than one matching pattern")
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:
    pass

AD2EL = {"A": "C", "C": "C", "OA": "O", "O": "O", "NA": "N", "N": "N", "NS": "N", "SA": "S", "S": "S",
         "P": "P", "F": "F", "Cl": "Cl", "CL": "Cl", "Br": "Br", "BR": "Br", "I": "I", "HD": "H", "HS": "H",
         "H": "H", "Mg": "Mg", "MG": "Mg", "Zn": "Zn", "ZN": "Zn", "Fe": "Fe", "FE": "Fe", "Ca": "Ca",
         "CA": "Ca", "Mn": "Mn", "MN": "Mn", "Si": "Si", "B": "B"}


class Project:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.cfg = load_project(self.root)     # may migrate the schema/layout as a side effect
        self.layout = Layout(self.root)

    def save(self):
        save_project(self.root, self.cfg)

    def r(self, *parts):
        return os.path.join(self.root, *parts)

    def rel(self, p):
        return self.layout.rel(p)

    # rutas estándar — delegadas a Layout (fuente única de verdad)
    def receptor_pdbqt(self, d):
        return self.layout.receptor_pdbqt(d["id"])

    def receptor_clean(self, d):
        return self.layout.receptor_clean(d["id"])

    def ligand_pdbqt(self, lig, control=False):
        return self.layout.ligand_pdbqt(lig["id"], control)

    def ref_sdf(self, d):
        return self.layout.ref_sdf(d["id"])

    def ref_pdb(self, d):
        return self.layout.ref_pdb(d["id"])

    def boxes(self):
        f = self.layout.boxes_json()
        if not os.path.exists(f):
            return {}
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)

    def ligands_for(self, target_id):
        """[(entrada, es_control)] que se dockean contra una diana."""
        out = [(l, False) for l in self.cfg["ligands"]]
        out += [(c, True) for c in self.cfg["controls"] if not c.get("target") or c.get("target") == target_id]
        return out


# ---------------------------------------------------------------- salida
def title(t):
    print(f"\n━━ {t} " + "━" * max(2, 58 - len(t)), flush=True)


def log(t=""):
    print(t, flush=True)


def tool(name, extra=()):
    for c in [shutil.which(name)] + [os.path.expanduser(x) for x in extra]:
        if c and os.path.exists(c):
            return c
    return None


def tmp_dir(prefix="x"):
    """Carpeta temporal sin espacios (ADFRsuite y smina fallan con espacios en rutas).
    Lleva el PID del grupo para que 'Docking detener' la pueda limpiar."""
    try:
        g = os.getpgid(0)
    except OSError:
        g = os.getpid()
    return tempfile.mkdtemp(prefix=f"axd_{g}_{prefix}_", dir="/tmp")


def run_cmd(cmd, cwd=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---------------------------------------------------------------- PDBQT
def is_complete(pdbqt):
    """Una salida cuenta como terminada si tiene afinidad y cierra su último modelo
    (protege contra archivos truncados por un corte de luz)."""
    if not os.path.exists(pdbqt) or os.path.getsize(pdbqt) == 0:
        return False
    txt = open(pdbqt, errors="ignore").read()
    return ("minimizedAffinity" in txt or "VINA RESULT" in txt) and txt.rstrip().endswith("ENDMDL")


def affinity(pdbqt):
    for l in open(pdbqt, errors="ignore"):
        m = re.search(r"minimizedAffinity\s+(-?\d+\.?\d*)", l) or re.search(r"VINA RESULT:\s+(-?\d+\.?\d*)", l)
        if m:
            return float(m.group(1))
    return None


def pdbqt_element(l):
    t = l[77:79].strip()
    return AD2EL.get(t, t[:1].upper() + t[1:].lower() if t else "C")


def heavy_atoms_pdbqt(pdbqt):
    n = 0
    for l in open(pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM") and pdbqt_element(l) != "H":
            n += 1
    return n


def model1(pdbqt):
    """Texto del primer modelo de un PDBQT de salida."""
    out = []
    for l in open(pdbqt, errors="ignore"):
        out.append(l)
        if l.startswith("ENDMDL"):
            break
    return "".join(out)


def pose1_pdb(pdbqt, resname="LIG", chain="L"):
    """Pose 1 como PDB estándar (sólo átomos pesados), elementos inferidos del tipo AutoDock."""
    out = []
    for l in open(pdbqt, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] in ("ATOM  ", "HETATM"):
            el = pdbqt_element(l)
            if el == "H":
                continue
            n = len(out) + 1
            nom = (el + str(n))[:4]
            out.append(f"HETATM{n:5d} {nom:<4s} {resname:>3s} {chain}   1    {l[30:54]}  1.00  0.00          {el:>2s}\n")
    return "".join(out) + "END\n"


def now_str():
    return time.strftime("%H:%M:%S")
