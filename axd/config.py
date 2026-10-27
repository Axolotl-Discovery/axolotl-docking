"""Configuración global (~/.config/axolotl-docking/config.json) y de proyecto (axd.json)."""
import datetime as _dt
import json
import os
import subprocess

from . import layout as L
from . import domain as D

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = open(os.path.join(APP, "VERSION")).read().strip() if os.path.exists(os.path.join(APP, "VERSION")) else "dev"
CONF_DIR = os.path.expanduser(os.environ.get("AXD_CONFIG_DIR", "~/.config/axolotl-docking"))
CONF = os.path.join(CONF_DIR, "config.json")
PROJECT_FILE = "axd.json"

DEFAULT_GLOBAL = {
    "entorno": "axolotl-docking",
    "conda": "~/miniforge3",
    "tools_bin": "~/tools/bin",
    "adfr_bin": "~/tools/ADFRsuite-1.0/bin",
    "carpeta_proyectos": "",
    "recientes": [],
}

# Kept as an alias for anything still importing it directly; Layout is the
# single source of truth for folder names now.
CARPETAS = L.ALL_FOLDERS

DEFAULT_DOCKING = {
    "engine": "smina",
    "seeds": [42, 2026, 777],
    "exhaustiveness": 32,
    "num_modes": 9,
    "energy_range": 4,
    "cpu": 0,  # 0 = todos los núcleos
    "ad4_runs": 20,         # sólo con átomos no comunes (AutoDock4): corridas GA por semilla
    "ad4_evals": 2500000,   # evaluaciones de energía por corrida
}


# ---------------------------------------------------------------- esquema (Fase 8: claves en inglés)
# Proyectos creados con versiones anteriores (Fases 0-7) guardan axd.json con claves en español.
# Esta tabla es la única fuente de verdad para traducirlos en memoria al cargar, así que esos
# proyectos siguen funcionando sin que el usuario tenga que hacer nada. Es idempotente: un
# proyecto que ya está en inglés pasa sin cambios (ninguna clave vieja aparece).
_PROJECT_KEYS = {"nombre": "name", "modo": "mode", "creado": "created", "version_axd": "axd_version",
                 "dianas": "targets", "ligandos": "ligands", "controles": "controls"}
_TARGET_KEYS = {"fuente": "source", "nombre": "name", "archivo": "file", "cadenas": "chains",
                "cofactores": "cofactors", "caja": "box"}
_LIGAND_KEYS = {"fuente": "source", "nombre": "name", "consulta": "query", "codigo": "code",
                "archivo": "file", "diana": "target"}
_BOX_KEYS = {"modo": "mode", "margen": "margin", "minimo": "minimum", "residuos": "residues",
             "detalle": "detail"}
_DOCKING_KEYS = {"motor": "engine", "semillas": "seeds"}

_PROJECT_MODE_VALUES = {"basico": "basic", "avanzado": "advanced"}
_SOURCE_VALUES = {"archivo": "file"}  # pdb/alphafold/ccd/pubchem/smiles ya eran iguales en ambos idiomas
_BOX_MODE_VALUES = {"ligando": "ligand", "residuos": "residues", "ciego": "blind"}  # manual/auto ya coinciden


def _rename_keys(d: dict, table: dict) -> dict:
    return {table.get(k, k): v for k, v in d.items()}


def _migrate_box(box: dict) -> dict:
    box = _rename_keys(dict(box), _BOX_KEYS)
    if box.get("mode") in _BOX_MODE_VALUES:
        box["mode"] = _BOX_MODE_VALUES[box["mode"]]
    return box


def _migrate_target(t: dict) -> dict:
    t = _rename_keys(dict(t), _TARGET_KEYS)
    if t.get("source") in _SOURCE_VALUES:
        t["source"] = _SOURCE_VALUES[t["source"]]
    if "box" in t:
        t["box"] = _migrate_box(t["box"])
    return t


def _migrate_ligand(l: dict) -> dict:
    l = _rename_keys(dict(l), _LIGAND_KEYS)
    if l.get("source") in _SOURCE_VALUES:
        l["source"] = _SOURCE_VALUES[l["source"]]
    return l


def migrate_schema_to_english(p: dict) -> tuple[bool, dict]:
    """Traduce en memoria un axd.json con claves en español (Fases 0-7) al esquema en
    inglés de la Fase 8. Devuelve (cambió, proyecto). No toca nada si ya está en inglés."""
    claves_viejas = set(_PROJECT_KEYS) | {"dianas", "ligandos", "controles"}
    if not (claves_viejas & p.keys()):
        return False, p
    p = _rename_keys(dict(p), _PROJECT_KEYS)
    if p.get("mode") in _PROJECT_MODE_VALUES:
        p["mode"] = _PROJECT_MODE_VALUES[p["mode"]]
    p["targets"] = [_migrate_target(x) for x in p.get("targets", [])]
    p["ligands"] = [_migrate_ligand(x) for x in p.get("ligands", [])]
    p["controls"] = [_migrate_ligand(x) for x in p.get("controls", [])]
    if "docking" in p:
        p["docking"] = _rename_keys(dict(p["docking"]), _DOCKING_KEYS)
    return True, p


# ---------------------------------------------------------------- global
def load_global():
    c = dict(DEFAULT_GLOBAL)
    if os.path.exists(CONF):
        try:
            with open(CONF, encoding="utf-8") as fh:
                c.update(json.load(fh))
        except (ValueError, OSError):
            pass
    return c


def save_global(c):
    os.makedirs(CONF_DIR, exist_ok=True)
    tmp = CONF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, CONF)


def register_recent(path):
    c = load_global()
    r = [x for x in c.get("recientes", []) if x != path and os.path.exists(os.path.join(x, PROJECT_FILE))]
    c["recientes"] = [path] + r[:9]
    save_global(c)


def conda_path(c=None):
    """Busca la instalación de conda: la configurada, la activa o las ubicaciones típicas."""
    c = c or load_global()
    candidates = [c.get("conda", ""), os.environ.get("CONDA_EXE", "").rsplit("/bin/", 1)[0],
                  "~/miniforge3", "~/mambaforge", "~/miniconda3", "~/anaconda3"]
    for x in candidates:
        x = os.path.expanduser(x or "")
        if x and os.path.exists(os.path.join(x, "etc/profile.d/conda.sh")):
            return x
    return None


def conda_environments(base):
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
def find_project(start=None):
    """Sube desde la carpeta actual buscando axd.json."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, PROJECT_FILE)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def new_project(path, name, mode="basic"):
    for sub in L.ALL_FOLDERS:
        os.makedirs(os.path.join(path, sub), exist_ok=True)
    p = {
        "name": name,
        "mode": mode,  # "basic" (todo automático) o "advanced"
        "created": _dt.date.today().isoformat(),
        "axd_version": VERSION,
        "layout_version": L.CURRENT_LAYOUT_VERSION,
        "targets": [],
        "ligands": [],
        "controls": [],
        "docking": dict(DEFAULT_DOCKING),
    }
    save_project(path, p)
    gi = os.path.join(path, ".gitignore")
    if not os.path.exists(gi):
        open(gi, "w").write(
            "# Generado por Axolotl Docking\n__pycache__/\n*.part\n04_Docking/logs/*.pid\n"
            "04_Docking/logs/*.log\n.ipynb_checkpoints/\n.checkpoints/\n*:Zone.Identifier\n")
    rd = os.path.join(path, "README.md")
    if not os.path.exists(rd):
        open(rd, "w").write(
            f"# {name}\n\n"
            "Proyecto de docking creado con **Axolotl Docking** (`Docking`).\n\n"
            "| Carpeta | Contenido |\n|---|---|\n"
            "| 01_Receptors | estructuras crudas (PDB/AlphaFold) y `clean/` |\n"
            "| 02_Ligands | ligandos de estudio (SDF) |\n"
            "| 03_Controls | controles positivos y ligandos cristalográficos |\n"
            "| 04_Docking | receptores/ligandos PDBQT, `boxes.json`, resultados y logs |\n"
            "| 05_Analysis | tablas de afinidad |\n| 06_Figures | figuras |\n| 07_Report | reporte |\n")
    return p


def load_project(path):
    file = os.path.join(path, PROJECT_FILE)
    with open(file, encoding="utf-8") as fh:
        p = json.load(fh)
    changed_schema, p = migrate_schema_to_english(p)
    p.setdefault("targets", []); p.setdefault("ligands", []); p.setdefault("controls", [])
    p.setdefault("name", p.get("codigo") or os.path.basename(os.path.abspath(path)))
    p.setdefault("mode", "advanced")  # proyectos creados con versiones anteriores
    d = dict(DEFAULT_DOCKING); d.update(p.get("docking", {})); p["docking"] = d

    changed_layout, p = L.migrate_in_place(path, p)
    # Un id de diana/ligando/control que no sea un componente de ruta seguro (p. ej.
    # venido de un axd.json compartido/editado a mano, o de una GUI antigua que no lo
    # saneaba) se corrige aquí antes de que cualquier paso lo use para construir rutas
    # — ver axd.layout.sanitize_id() / Layout.r() para el porqué.
    changed_ids, p = L.ensure_safe_ids(p)
    if changed_schema or changed_layout or changed_ids:
        L.backup_project_file(file)
        save_project(path, p)
    return p


def save_project(path, p):
    f = os.path.join(path, PROJECT_FILE)
    with open(f + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2, ensure_ascii=False)
    os.replace(f + ".tmp", f)


# ---------------------------------------------------------------- modelo de dominio tipado
def load_project_typed(path) -> D.Project:
    """Como load_project(), pero devuelve el modelo tipado (axd.domain.Project) en vez
    del dict suelto. Pensado para código nuevo (fases 3+); el código existente sigue usando
    load_project() sin cambios."""
    return D.Project.from_dict(load_project(path))


def save_project_typed(path, p: D.Project):
    """Inverso de load_project_typed(): serializa el modelo tipado de vuelta a axd.json."""
    save_project(path, p.to_dict())
