"""Single source of truth for a project's folder tree and file paths.

Before this module, every file that touched a project path (pipeline/comun.py,
axd/runner.py, axd/resultados.py, each pipeline step...) hard-coded strings
like "04_Docking/Resultados" on its own. Changing the layout meant grepping the
whole codebase. `Layout` is now the only place that knows the tree; everything
else asks it for a path.

Folder/file names are English (code-facing); the text shown to the user stays
Spanish wherever it already was — this module has no user-facing strings.

`migrate_in_place()` upgrades a project created with the old Spanish layout
(01_Receptores, 02_Ligandos, cajas.json, ...) to the current one: it renames
directories/files on disk and rewrites the relative paths stored inside the
loaded project dict. It is idempotent (a project already on the current layout
version is left untouched) and keeps a timestamped backup of axd.json before
the first destructive change.

Planned final location: `axolotl_docking/domain/layout.py`.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass

CURRENT_LAYOUT_VERSION = 2          # 1 = legacy Spanish layout (implicit), 2 = English layout


# ---------------------------------------------------------------- folder tree
# All directories a new project needs, English names, created up front.
ALL_FOLDERS = [
    "01_Receptors/clean",
    "02_Ligands",
    "03_Controls/crystal_ligand",
    "04_Docking/Receptors",
    "04_Docking/Ligands",
    "04_Docking/Controls",
    "04_Docking/Redocking",
    "04_Docking/Results",
    "04_Docking/BestPoses",
    "04_Docking/Complexes",
    "04_Docking/Maps",
    "04_Docking/logs",
    "05_Analysis",
    "06_Figures",
    "07_Report",
]


@dataclass
class Layout:
    """Every path inside one project, built from its root folder."""
    root: str

    def __post_init__(self):
        self.root = os.path.abspath(self.root)

    def r(self, *parts: str) -> str:
        """Join `parts` onto the project root. Every path method in this class goes
        through here, so this is also the one place that guards against a hostile
        id/path component (a target or ligand `id` with '..' or an absolute path)
        escaping the project directory — see `sanitize_id()` below, which is what
        keeps ids from reaching here in that shape in the first place."""
        path = os.path.join(self.root, *parts)
        norm, root_norm = os.path.normpath(path), os.path.normpath(self.root)
        if norm != root_norm and not norm.startswith(root_norm + os.sep):
            raise ValueError(
                f"ruta fuera del proyecto: {path!r} (un id/ruta con '..' o absoluto se coló sin sanear)")
        return path

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root)

    # ---- 01_Receptors
    def receptors_raw_dir(self) -> str:
        return self.r("01_Receptors")

    def receptors_clean_dir(self) -> str:
        return self.r("01_Receptors", "clean")

    def receptor_clean(self, target_id: str) -> str:
        return self.r("01_Receptors", "clean", f"{target_id}_clean.pdb")

    # ---- 02_Ligands
    def ligands_dir(self) -> str:
        return self.r("02_Ligands")

    # ---- 03_Controls
    def controls_dir(self) -> str:
        return self.r("03_Controls")

    def crystal_ligand_dir(self) -> str:
        return self.r("03_Controls", "crystal_ligand")

    def ref_sdf(self, target_id: str) -> str:
        return self.r("03_Controls", "crystal_ligand", f"{target_id}_ref_crystal.sdf")

    def ref_pdb(self, target_id: str) -> str:
        return self.r("03_Controls", "crystal_ligand", f"{target_id}_ref.pdb")

    # ---- 04_Docking
    def docking_dir(self) -> str:
        return self.r("04_Docking")

    def receptor_pdbqt(self, target_id: str) -> str:
        return self.r("04_Docking", "Receptors", f"{target_id}.pdbqt")

    def ligand_pdbqt(self, ligand_id: str, control: bool = False) -> str:
        return self.r("04_Docking", "Controls" if control else "Ligands", f"{ligand_id}.pdbqt")

    def ligand_prep_dir(self, control: bool = False) -> str:
        return self.r("04_Docking", "Controls" if control else "Ligands", "prep")

    def ligand_prep_sdf(self, ligand_id: str, control: bool = False) -> str:
        return self.r("04_Docking", "Controls" if control else "Ligands", "prep", f"{ligand_id}_H.sdf")

    def redocking_dir(self) -> str:
        return self.r("04_Docking", "Redocking")

    def redocking_ligand_pdbqt(self, target_id: str) -> str:
        return self.r("04_Docking", "Redocking", f"{target_id}_crystal.pdbqt")

    def results_dir(self) -> str:
        return self.r("04_Docking", "Results")

    def target_results_dir(self, target_id: str) -> str:
        return self.r("04_Docking", "Results", target_id)

    def result_pdbqt(self, target_id: str, ligand_id: str, seed) -> str:
        return self.r("04_Docking", "Results", target_id, f"{ligand_id}_s{seed}.pdbqt")

    def results_backup_dir(self, stamp: str) -> str:
        return self.r("04_Docking", f"Results_backup_{stamp}")

    def redocking_results_dir(self) -> str:
        return self.r("04_Docking", "Results", "Redocking")

    def redocking_result_pdbqt(self, target_id: str, seed) -> str:
        return self.r("04_Docking", "Results", "Redocking", f"{target_id}_crystal_s{seed}.pdbqt")

    def best_poses_dir(self) -> str:
        return self.r("04_Docking", "BestPoses")

    def best_pose_pdbqt(self, target_id: str, ligand_id: str) -> str:
        return self.r("04_Docking", "BestPoses", f"{target_id}__{ligand_id}.pdbqt")

    def complexes_dir(self) -> str:
        return self.r("04_Docking", "Complexes")

    def complex_base(self, target_id: str, ligand_id: str) -> str:
        """Path without extension: '<base>_complex.pdb' / '<base>_pose.sdf'."""
        return self.r("04_Docking", "Complexes", f"{target_id}__{ligand_id}")

    def complex_pdb(self, target_id: str, ligand_id: str) -> str:
        return self.complex_base(target_id, ligand_id) + "_complex.pdb"

    def complex_pose_sdf(self, target_id: str, ligand_id: str) -> str:
        return self.complex_base(target_id, ligand_id) + "_pose.sdf"

    def maps_dir(self) -> str:
        return self.r("04_Docking", "Maps")

    def target_maps_dir(self, target_id: str) -> str:
        return self.r("04_Docking", "Maps", target_id)

    def ad4_params_file(self) -> str:
        return self.r("04_Docking", "Maps", "AD4_axd.dat")

    def boxes_json(self) -> str:
        return self.r("04_Docking", "boxes.json")

    def logs_dir(self) -> str:
        return self.r("04_Docking", "logs")

    def job_state_file(self) -> str:
        return self.r("04_Docking", "logs", "job.json")

    def pipeline_log(self, stamp: str) -> str:
        return self.r("04_Docking", "logs", f"pipeline_{stamp}.log")

    def prep_receptor_log(self, target_id: str) -> str:
        return self.r("04_Docking", "logs", f"prep_receptor_{target_id}.log")

    # ---- 05_Analysis
    def analysis_dir(self) -> str:
        return self.r("05_Analysis")

    def affinities_summary_csv(self) -> str:
        return self.r("05_Analysis", "affinities_summary.csv")

    def affinity_matrix_csv(self) -> str:
        return self.r("05_Analysis", "affinity_matrix.csv")

    def affinities_runs_csv(self) -> str:
        return self.r("05_Analysis", "affinities_runs.csv")

    def redocking_summary_csv(self) -> str:
        return self.r("05_Analysis", "redocking_summary.csv")

    def interactions_detail_csv(self) -> str:
        return self.r("05_Analysis", "interactions_detail.csv")

    def interactions_summary_csv(self) -> str:
        return self.r("05_Analysis", "interactions_summary.csv")

    def metal_parameters_txt(self) -> str:
        return self.r("05_Analysis", "metal_parameters.txt")

    def affinities_xlsx(self, project_name_safe: str) -> str:
        return self.r("05_Analysis", f"{project_name_safe}_affinities.xlsx")

    def affinities_xlsx_glob(self) -> str:
        return self.r("05_Analysis", "*_affinities.xlsx")

    # ---- 06_Figures / 07_Report
    def figures_dir(self) -> str:
        return self.r("06_Figures")

    def report_dir(self) -> str:
        return self.r("07_Report")


# ---------------------------------------------------------------- id safety
# A target/ligand/control `id` ends up interpolated into file names all over this
# class (receptor_pdbqt, ligand_pdbqt, result_pdbqt, complex_base, ...). An id is
# meant to be a short code the user/UI picks (or a PDB ID), never a path — but
# nothing historically stopped one from containing '..' or acting like an
# absolute path once interpolated (e.g. an id of "/etc/passwd" makes
# f"{id}.pdbqt" joined via os.path.join silently discard the project root).
# sanitize_id() is the one place that turns arbitrary text into a safe path
# component; Layout.r()'s containment check above is the backstop in case an
# unsafe id reaches here anyway (an old project, a hand-edited axd.json, a
# future caller that forgets to sanitize).
def sanitize_id(text: str) -> str:
    """Same rules as axd.ui.nombre_seguro() (kept independently here so this
    path-safety module has no dependency on the terminal-UI module): strip
    accents, keep only [A-Za-z0-9._+-], collapse everything else to '_'.
    Idempotent: sanitize_id(x) == x already for any id that was already safe."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9._+-]+", "_", t.strip()).strip("_")
    return t or "sin_nombre"


def _unique(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def ensure_safe_ids(project_dict: dict) -> tuple[bool, dict]:
    """Re-derive any target/ligand/control id that isn't already a safe path
    component (sanitize_id(id) != id — e.g. it contains '/', '..', or came in
    unsanitized from a GUI dialog or a hand-edited/shared axd.json), keeping
    the result unique. Returns (changed, project_dict); the caller persists it
    the same way it does after migrate_in_place()/migrate_schema_to_english().

    Two passes so order never matters: first collect every id that is ALREADY
    safe (so a later fix can't collide with it), then fix the unsafe ones —
    each fix also joins `taken`, so two unsafe ids that would sanitize to the
    same thing still end up unique."""
    items = [item for key in ("targets", "ligands", "controls") for item in project_dict.get(key, [])]
    taken = {str(item.get("id", "")) for item in items if sanitize_id(str(item.get("id", ""))) == item.get("id")}
    changed = False
    for item in items:
        old = str(item.get("id", ""))
        if sanitize_id(old) != old:
            new = _unique(sanitize_id(old), taken)
            item["id"] = new
            taken.add(new)
            changed = True
    return changed, project_dict


# ---------------------------------------------------------------- migration
# (old relative path, new relative path), applied in order: top-level renames
# first, then nested ones that depend on an already-renamed parent.
_DIR_RENAMES = [
    ("01_Receptores", "01_Receptors"),
    ("02_Ligandos", "02_Ligands"),
    ("03_Controles", "03_Controls"),
    ("04_Docking/Receptores", "04_Docking/Receptors"),
    ("04_Docking/Ligandos", "04_Docking/Ligands"),
    ("04_Docking/Controles", "04_Docking/Controls"),
    ("04_Docking/Resultados", "04_Docking/Results"),
    ("04_Docking/MejoresPoses", "04_Docking/BestPoses"),
    ("04_Docking/Complejos", "04_Docking/Complexes"),
    ("04_Docking/Mapas", "04_Docking/Maps"),
    ("05_Analisis", "05_Analysis"),
    ("06_Figuras", "06_Figures"),
    ("07_Reporte", "07_Report"),
    # nested — parents above are already renamed by the time these run
    ("01_Receptors/limpios", "01_Receptors/clean"),
    ("03_Controls/ligando_cristal", "03_Controls/crystal_ligand"),
]

_FILE_RENAMES = [
    ("04_Docking/cajas.json", "04_Docking/boxes.json"),
    ("04_Docking/logs/trabajo.json", "04_Docking/logs/job.json"),
    ("05_Analysis/afinidades_resumen.csv", "05_Analysis/affinities_summary.csv"),
    ("05_Analysis/matriz_afinidad.csv", "05_Analysis/affinity_matrix.csv"),
    ("05_Analysis/afinidades_corridas.csv", "05_Analysis/affinities_runs.csv"),
    ("05_Analysis/redocking_resumen.csv", "05_Analysis/redocking_summary.csv"),
    ("05_Analysis/interacciones_resumen.csv", "05_Analysis/interactions_summary.csv"),
    ("05_Analysis/interacciones_detalle.csv", "05_Analysis/interactions_detail.csv"),
    ("05_Analysis/parametros_metales.txt", "05_Analysis/metal_parameters.txt"),
]

# per-item filename patterns that change (applied inside already-renamed dirs)
_FILENAME_TOKEN_RENAMES = [
    ("_ref_cristal.sdf", "_ref_crystal.sdf"),     # 03_Controls/crystal_ligand/<id>_ref_cristal.sdf
    ("_cristal.pdbqt", "_crystal.pdbqt"),          # 04_Docking/Redocking/<id>_cristal.pdbqt
    ("_cristal_s", "_crystal_s"),                  # .../Redocking/<id>_cristal_s<seed>.pdbqt
]


def _move_if_present(old_abs: str, new_abs: str) -> bool:
    if not os.path.exists(old_abs) or os.path.exists(new_abs):
        return False
    os.makedirs(os.path.dirname(new_abs), exist_ok=True)
    shutil.move(old_abs, new_abs)
    return True


def _rename_tokens_in_tree(root: str) -> None:
    """Rename files whose basename contains an old Spanish token, anywhere
    under root (covers e.g. 05_Analysis/<name>_afinidades.xlsx)."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            new_name = name
            for old_tok, new_tok in _FILENAME_TOKEN_RENAMES + [("_afinidades.xlsx", "_affinities.xlsx")]:
                if old_tok in new_name:
                    new_name = new_name.replace(old_tok, new_tok)
            if new_name != name:
                src, dst = os.path.join(dirpath, name), os.path.join(dirpath, new_name)
                if not os.path.exists(dst):
                    shutil.move(src, dst)


def _needs_migration(project_dict: dict, root: str) -> bool:
    if int(project_dict.get("layout_version", 1)) >= CURRENT_LAYOUT_VERSION:
        return False
    # also treat a fresh/empty project (nothing on disk yet) as "nothing to migrate"
    # but still worth stamping the version so it never re-checks on every load.
    return True


def _remap_relative_path(old_rel: str) -> str:
    """Rewrite one relative path (as stored in axd.json) through the rename
    tables, longest prefixes first so nested renames apply correctly."""
    if not old_rel:
        return old_rel
    norm = old_rel.replace("\\", "/")
    for old_dir, new_dir in sorted(_DIR_RENAMES, key=lambda p: -len(p[0])):
        if norm == old_dir or norm.startswith(old_dir + "/"):
            norm = new_dir + norm[len(old_dir):]
            break
    for old_tok, new_tok in _FILENAME_TOKEN_RENAMES + [("_afinidades.xlsx", "_affinities.xlsx")]:
        norm = norm.replace(old_tok, new_tok)
    return norm


def migrate_in_place(root: str, project_dict: dict) -> tuple[bool, dict]:
    """Upgrade a project directory + its loaded axd.json to the current layout.

    Returns (changed, project_dict). `project_dict` is mutated in place and
    also returned for convenience. The caller is responsible for persisting it
    (so this module never writes axd.json itself, only moves files/dirs and
    makes a timestamped backup copy before the first change).
    """
    if not _needs_migration(project_dict, root):
        return False, project_dict

    root = os.path.abspath(root)
    changed = False

    for old_rel, new_rel in _DIR_RENAMES:
        if _move_if_present(os.path.join(root, old_rel), os.path.join(root, new_rel)):
            changed = True
    for old_rel, new_rel in _FILE_RENAMES:
        if _move_if_present(os.path.join(root, old_rel), os.path.join(root, new_rel)):
            changed = True
    _rename_tokens_in_tree(root)

    for key in ("targets", "ligands", "controls"):
        for item in project_dict.get(key, []):
            if item.get("file"):
                item["file"] = _remap_relative_path(item["file"])

    project_dict["layout_version"] = CURRENT_LAYOUT_VERSION
    return True, project_dict


def backup_project_file(project_file: str) -> str | None:
    """Copy axd.json to a timestamped .bak sibling before a migration writes
    it back. Returns the backup path, or None if there was nothing to back up."""
    if not os.path.exists(project_file):
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = f"{project_file}.bak-{stamp}"
    shutil.copy2(project_file, backup)
    return backup
