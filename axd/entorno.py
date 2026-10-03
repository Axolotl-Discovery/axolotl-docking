"""Verificación e instalación del entorno de docking (conda + smina + ADFRsuite)."""
import os
import shutil
import subprocess

from . import config as C
from . import ui

OPCIONALES = {"PyMOL", "ProLIF", "MDAnalysis", "PLIP", "Vina", "matplotlib", "prepare_ligand"}

MODULOS = [("rdkit", "RDKit"), ("meeko", "Meeko"), ("openbabel.pybel", "Open Babel"), ("pdbfixer", "PDBFixer"),
           ("openmm", "OpenMM"), ("gemmi", "gemmi"), ("numpy", "numpy"), ("pandas", "pandas"),
           ("openpyxl", "openpyxl"), ("matplotlib", "matplotlib"), ("pymol", "PyMOL"), ("prolif", "ProLIF"),
           ("MDAnalysis", "MDAnalysis"), ("plip", "PLIP"), ("vina", "Vina")]

# Cada import va en su propio proceso: si una librería crashea (p. ej. el conflicto swig de vina/openbabel)
# no se lleva entre las patas al resto del chequeo ni da un falso "todo listo".
CHEQUEO_SH = "\n".join(
    f'python -c "import {m}" >/dev/null 2>&1 && echo "OK {n}" || echo "XX {n} - no se pudo importar"'
    for m, n in MODULOS) + "\necho FIN_CHEQUEO\n"


def doctor(reparar_preguntando=True):
    g = C.cargar_global()
    ui.titulo("Verificación del entorno")
    problemas = 0
    conda = C.ruta_conda(g)
    if conda:
        ui.ok(f"conda: {conda}")
    else:
        ui.error("conda/miniforge no encontrado"); problemas += 1
    envs = C.entornos_conda(conda)
    if conda and g["entorno"] in envs:
        ui.ok(f"entorno conda: {g['entorno']}")
        bash = (f'source "{conda}/etc/profile.d/conda.sh" && conda activate "{g["entorno"]}" || exit 3\n'
                + CHEQUEO_SH +
                'command -v mk_prepare_ligand.py >/dev/null && echo OK "mk_prepare_ligand.py" || echo XX "mk_prepare_ligand.py"; '
                'command -v obabel >/dev/null && echo OK obabel || echo XX obabel')
        ui.info("Probando las librerías del entorno (≈ 20 s)…")
        out = subprocess.run(["bash", "-c", bash], capture_output=True, text=True).stdout
        if "FIN_CHEQUEO" not in out:
            ui.error("  el chequeo de librerías no terminó (¿no se pudo activar el entorno?)"); problemas += 1
        for l in out.splitlines():
            if l.startswith("OK "):
                ui.ok("  " + l[3:])
            elif l.startswith("XX "):
                nombre = l[3:].split(" - ")[0].strip()
                if nombre == "Vina":
                    l = "XX Vina - no se pudo importar"
                if nombre in OPCIONALES:
                    ui.aviso("  " + l[3:] + ui.gris("  (opcional: el pipeline no lo necesita)"))
                else:
                    ui.error("  " + l[3:]); problemas += 1
    elif conda:
        ui.error(f"no existe el entorno '{g['entorno']}'" + (f" (hay: {', '.join(envs)})" if envs else ""))
        problemas += 1
    for nombre, carpeta in (("smina", g["tools_bin"]), ("prepare_receptor", g["adfr_bin"]),
                            ("prepare_ligand", g["adfr_bin"])):
        ruta = os.path.join(os.path.expanduser(carpeta), nombre)
        if os.path.exists(ruta) and os.access(ruta, os.X_OK):
            ui.ok(f"{nombre}: {ruta}")
        elif shutil.which(nombre):
            ui.ok(f"{nombre}: {shutil.which(nombre)}")
        elif nombre in OPCIONALES:
            ui.aviso(f"{nombre} no encontrado (opcional)")
        else:
            ui.error(f"{nombre} no encontrado (esperado en {ruta})"); problemas += 1
    print()
    if problemas == 0:
        ui.ok(ui.negrita("Todo listo para dockear."))
        return True
    ui.aviso(f"{problemas} problema(s).")
    if reparar_preguntando and ui.si_no("¿Instalar/reparar lo que falta ahora? (puede tardar 10-20 min)", True):
        instalar()
    return False


def instalar(extra=None):
    g = C.cargar_global()
    script = os.path.join(C.APP, "scripts", "instalar_entorno.sh")
    env = dict(os.environ, AXD_ENV=g["entorno"])
    subprocess.call(["bash", script] + (extra or []), env=env)


def elegir_entorno():
    """Permite usar un entorno existente (p. ej. axolot-Docking) en lugar de crear uno nuevo."""
    g = C.cargar_global()
    envs = [e for e in C.entornos_conda(C.ruta_conda(g)) if e not in ("base", "miniforge3")]
    if not envs:
        ui.info("No hay entornos conda (aparte de base).")
        return
    k = ui.menu(f"Entorno a usar (actual: {g['entorno']})", [(e, e) for e in envs])
    if k:
        g["entorno"] = k
        C.guardar_global(g)
        ui.ok(f"Usaré el entorno '{k}'.")
