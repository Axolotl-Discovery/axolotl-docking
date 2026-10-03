"""Configuración global (~/.config/axolotl-docking/config.json) y de proyecto (axd.json)."""
import datetime as _dt
import json
import os
import subprocess

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = open(os.path.join(APP, "VERSION")).read().strip() if os.path.exists(os.path.join(APP, "VERSION")) else "dev"
CONF_DIR = os.path.expanduser(os.environ.get("AXD_CONFIG_DIR", "~/.config/axolotl-docking"))
CONF = os.path.join(CONF_DIR, "config.json")
ARCHIVO_PROYECTO = "axd.json"

DEFECTO_GLOBAL = {
    "entorno": "axolotl-docking",
    "conda": "~/miniforge3",
    "tools_bin": "~/tools/bin",
    "adfr_bin": "~/tools/ADFRsuite-1.0/bin",
    "carpeta_proyectos": "",
    "recientes": [],
}

CARPETAS = [
    "01_Receptores/limpios",
    "02_Ligandos",
    "03_Controles/ligando_cristal",
    "04_Docking/Receptores",
    "04_Docking/Ligandos",
    "04_Docking/Controles",
    "04_Docking/Redocking",
    "04_Docking/Resultados",
    "04_Docking/MejoresPoses",
    "04_Docking/Complejos",
    "04_Docking/logs",
    "05_Analisis",
    "06_Figuras",
    "07_Reporte",
]

DOCKING_DEFECTO = {
    "motor": "smina",
    "semillas": [42, 2026, 777],
    "exhaustiveness": 32,
    "num_modes": 9,
    "energy_range": 4,
    "cpu": 0,  # 0 = todos los núcleos
    "ad4_runs": 20,         # sólo con átomos no comunes (AutoDock4): corridas GA por semilla
    "ad4_evals": 2500000,   # evaluaciones de energía por corrida
}


# ---------------------------------------------------------------- global
def cargar_global():
    c = dict(DEFECTO_GLOBAL)
    if os.path.exists(CONF):
        try:
            c.update(json.load(open(CONF)))
        except (ValueError, OSError):
            pass
    return c


def guardar_global(c):
    os.makedirs(CONF_DIR, exist_ok=True)
    tmp = CONF + ".tmp"
    json.dump(c, open(tmp, "w"), indent=2, ensure_ascii=False)
    os.replace(tmp, CONF)


def registrar_reciente(ruta):
    c = cargar_global()
    r = [x for x in c.get("recientes", []) if x != ruta and os.path.exists(os.path.join(x, ARCHIVO_PROYECTO))]
    c["recientes"] = [ruta] + r[:9]
    guardar_global(c)


def ruta_conda(c=None):
    """Busca la instalación de conda: la configurada, la activa o las ubicaciones típicas."""
    c = c or cargar_global()
    candidatos = [c.get("conda", ""), os.environ.get("CONDA_EXE", "").rsplit("/bin/", 1)[0],
                  "~/miniforge3", "~/mambaforge", "~/miniconda3", "~/anaconda3"]
    for x in candidatos:
        x = os.path.expanduser(x or "")
        if x and os.path.exists(os.path.join(x, "etc/profile.d/conda.sh")):
            return x
    return None


def entornos_conda(base):
    if not base:
        return []
    try:
        out = subprocess.check_output([os.path.join(base, "bin/conda"), "env", "list", "--json"], text=True,
                                      stderr=subprocess.DEVNULL)
        return [os.path.basename(p) for p in json.loads(out)["envs"]]
    except Exception:
        d = os.path.join(base, "envs")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


# ---------------------------------------------------------------- proyecto
def buscar_proyecto(desde=None):
    """Sube desde la carpeta actual buscando axd.json."""
    d = os.path.abspath(desde or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, ARCHIVO_PROYECTO)):
            return d
        padre = os.path.dirname(d)
        if padre == d:
            return None
        d = padre


def nuevo_proyecto(ruta, nombre, modo="basico"):
    for sub in CARPETAS:
        os.makedirs(os.path.join(ruta, sub), exist_ok=True)
    p = {
        "nombre": nombre,
        "modo": modo,  # "basico" (todo automático) o "avanzado"
        "creado": _dt.date.today().isoformat(),
        "version_axd": VERSION,
        "dianas": [],
        "ligandos": [],
        "controles": [],
        "docking": dict(DOCKING_DEFECTO),
    }
    guardar_proyecto(ruta, p)
    gi = os.path.join(ruta, ".gitignore")
    if not os.path.exists(gi):
        open(gi, "w").write(
            "# Generado por Axolotl Docking\n__pycache__/\n*.part\n04_Docking/logs/*.pid\n"
            "04_Docking/logs/*.log\n.ipynb_checkpoints/\n*:Zone.Identifier\n")
    rd = os.path.join(ruta, "README.md")
    if not os.path.exists(rd):
        open(rd, "w").write(
            f"# {nombre}\n\n"
            "Proyecto de docking creado con **Axolotl Docking** (`Docking`).\n\n"
            "| Carpeta | Contenido |\n|---|---|\n"
            "| 01_Receptores | estructuras crudas (PDB/AlphaFold) y `limpios/` |\n"
            "| 02_Ligandos | ligandos de estudio (SDF) |\n"
            "| 03_Controles | controles positivos y ligandos cristalográficos |\n"
            "| 04_Docking | receptores/ligandos PDBQT, `cajas.json`, resultados y logs |\n"
            "| 05_Analisis | tablas de afinidad |\n| 06_Figuras | figuras |\n| 07_Reporte | reporte |\n")
    return p


def cargar_proyecto(ruta):
    p = json.load(open(os.path.join(ruta, ARCHIVO_PROYECTO), encoding="utf-8"))
    p.setdefault("dianas", []); p.setdefault("ligandos", []); p.setdefault("controles", [])
    p.setdefault("nombre", p.get("codigo") or os.path.basename(os.path.abspath(ruta)))
    p.setdefault("modo", "avanzado")  # proyectos creados con versiones anteriores
    d = dict(DOCKING_DEFECTO); d.update(p.get("docking", {})); p["docking"] = d
    return p


def guardar_proyecto(ruta, p):
    f = os.path.join(ruta, ARCHIVO_PROYECTO)
    json.dump(p, open(f + ".tmp", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    os.replace(f + ".tmp", f)
