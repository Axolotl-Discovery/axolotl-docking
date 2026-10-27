"""Eliminar el último procesamiento (docking, resumen e interacciones: pasos
5–7) para poder rehacerlo, con un respaldo .zip obligatorio antes de borrar.

Se CONSERVA lo que es caro de rehacer y no depende del docking: estructuras
descargadas, receptores y ligandos preparados (PDBQT), cajas, mapas, redocking
(paso 4) y su tabla, y los parámetros de metales.

El .zip lleva los archivos que se van a borrar más axd.json, boxes.json y los
logs, con rutas relativas al proyecto: descomprimirlo dentro de la carpeta del
proyecto deja todo como estaba."""
from __future__ import annotations

import glob
import os
import time
import zipfile

from ... import config as C
from ... import runner as R
from ...layout import Layout
from . import checkpoints as CK

REDOCKING_DIRNAME = "Redocking"  # 04_Docking/Results/Redocking pertenece al paso 4: no se toca


def files_to_remove(proy) -> list[str]:
    """Rutas absolutas de los archivos generados por los pasos 5–7."""
    lay = Layout(proy)
    out = []
    res = lay.results_dir()
    if os.path.isdir(res):
        for name in sorted(os.listdir(res)):
            d = os.path.join(res, name)
            if name == REDOCKING_DIRNAME or not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                out += [os.path.join(root, f) for f in sorted(files)]
    for d in (lay.best_poses_dir(), lay.complexes_dir()):
        if os.path.isdir(d):
            for root, _dirs, files in os.walk(d):
                out += [os.path.join(root, f) for f in sorted(files)]
    for f in (lay.affinities_summary_csv(), lay.affinity_matrix_csv(), lay.affinities_runs_csv(),
              lay.interactions_detail_csv(), lay.interactions_summary_csv()):
        if os.path.isfile(f):
            out.append(f)
    out += sorted(glob.glob(lay.affinities_xlsx_glob()))
    return out


def _context_files(proy) -> list[str]:
    lay = Layout(proy)
    extra = [os.path.join(proy, C.PROJECT_FILE), lay.boxes_json()]
    if os.path.isdir(lay.logs_dir()):
        extra += sorted(glob.glob(os.path.join(lay.logs_dir(), "*.log")))
        extra += [lay.job_state_file()]
    return [f for f in extra if os.path.isfile(f)]


def summary(proy) -> dict:
    files = files_to_remove(proy)
    size = 0
    for f in files:
        try:
            size += os.path.getsize(f)
        except OSError:
            pass
    return {"n_files": len(files), "bytes": size}


def default_backup_name(proy) -> str:
    base = os.path.basename(os.path.abspath(proy)) or "proyecto"
    return f"{base}_respaldo_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def make_backup(proy, dest_zip: str) -> str:
    """Escribe el .zip y lo verifica (lectura completa con testzip). Lanza
    IOError si no se pudo escribir o quedó corrupto: en ese caso NO se debe borrar."""
    proy = os.path.abspath(proy)
    dest_zip = os.path.abspath(dest_zip)
    dock = os.path.abspath(Layout(proy).docking_dir())
    try:
        dentro = os.path.commonpath([dest_zip, dock]) == dock
    except ValueError:  # otra unidad (Windows)
        dentro = False
    if dentro:
        raise IOError("El respaldo no puede guardarse dentro de 04_Docking (se borraría con lo demás).")
    files = files_to_remove(proy) + _context_files(proy)
    tmp = dest_zip + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in dict.fromkeys(files):  # sin duplicados, en orden
                zf.write(f, os.path.relpath(f, proy))
        with zipfile.ZipFile(tmp) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise IOError(f"el respaldo quedó dañado ({bad})")
        os.replace(tmp, dest_zip)
    except (OSError, zipfile.BadZipFile) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise IOError(f"No se pudo crear el respaldo: {e}") from e
    return dest_zip


def remove(proy) -> int:
    """Borra lo de los pasos 5–7. Requiere que no haya un trabajo corriendo.
    Devuelve cuántos archivos se borraron."""
    e = R.estado(proy)
    if e and e.get("vivo"):
        raise RuntimeError("Hay un trabajo corriendo en este proyecto; detenlo antes de eliminar.")
    files = files_to_remove(proy)
    for f in files:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    lay = Layout(proy)
    # carpetas que quedaron vacías (nunca Results/Redocking)
    for d in (lay.best_poses_dir(), lay.complexes_dir()):
        if os.path.isdir(d) and not any(os.scandir(d)):
            os.rmdir(d)
    res = lay.results_dir()
    if os.path.isdir(res):
        for name in os.listdir(res):
            d = os.path.join(res, name)
            if name != REDOCKING_DIRNAME and os.path.isdir(d):
                for root, dirs, _files in os.walk(d, topdown=False):
                    for sub in dirs:
                        p = os.path.join(root, sub)
                        if not os.listdir(p):
                            os.rmdir(p)
                if not os.listdir(d):
                    os.rmdir(d)
    # sin resultados de docking, el próximo motor (CPU o GPU) queda registrado de cero
    p = C.load_project(proy)
    if p.get("docking", {}).pop("motor_usado", None) is not None:
        C.save_project(proy, p)
    # el avance vuelve a 0: los checkpoints automáticos deben poder dispararse de nuevo
    state = CK._load_state(proy)
    state["last_pct"] = -1
    CK._save_state(proy, state)
    return len(files)
