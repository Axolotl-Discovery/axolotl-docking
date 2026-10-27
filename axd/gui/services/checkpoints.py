"""Checkpoints de un proyecto: snapshot de axd.json + manifiesto de resultados,
guardado en `<proyecto>/.checkpoints/`. Viaja con la carpeta del proyecto (se
puede copiar a otro dispositivo), no depende de ninguna nube.

Se dispara automáticamente cada 10% de avance *real* (fracción de corridas de
docking completadas, usando el mismo criterio que axd.runner.mostrar_avance),
no por tiempo de reloj, porque el tiempo estimado es sólo eso: una
estimación (ver axd.gui.services.calibration)."""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field

from ... import config as C
from ... import runner as R
from ...layout import Layout

CHECKPOINTS_DIR = ".checkpoints"
STATE_FILE = "state.json"


@dataclass
class Checkpoint:
    id: str
    pct: int
    created_at: str
    label: str
    done: int
    total: int
    path: str
    extra: dict = field(default_factory=dict)


def _dir(proy) -> str:
    return os.path.join(proy, CHECKPOINTS_DIR)


def _state_path(proy) -> str:
    return os.path.join(_dir(proy), STATE_FILE)


def _load_state(proy) -> dict:
    f = _state_path(proy)
    if not os.path.exists(f):
        return {"last_pct": -1, "checkpoints": []}
    try:
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {"last_pct": -1, "checkpoints": []}


def _save_state(proy, state: dict) -> None:
    os.makedirs(_dir(proy), exist_ok=True)
    tmp = _state_path(proy) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, _state_path(proy))


def progress_fraction(proy) -> tuple[int, int]:
    """(hechas, total) corridas de docking completadas — mismo criterio que
    `Docking avance` (axd.runner.corridas_esperadas + runner._completo)."""
    p = C.load_project(proy)
    tabla = R.corridas_esperadas(p)
    lay = Layout(proy)
    total = hechas = 0
    for d, corr in tabla.items():
        for lig, s in corr:
            total += 1
            if R._completo(lay.result_pdbqt(d, lig, s)):
                hechas += 1
    return hechas, total


def _snapshot(proy, cp_id: str, pct: int, label: str, done: int, total: int) -> Checkpoint:
    dest = os.path.join(_dir(proy), cp_id)
    os.makedirs(dest, exist_ok=True)
    project_file = os.path.join(proy, C.PROJECT_FILE)
    if os.path.exists(project_file):
        shutil.copy2(project_file, os.path.join(dest, C.PROJECT_FILE))
    lay = Layout(proy)
    manifest_results = []
    if os.path.isdir(lay.results_dir()):
        for root, _dirs, files in os.walk(lay.results_dir()):
            for fn in files:
                fp = os.path.join(root, fn)
                manifest_results.append({"path": os.path.relpath(fp, proy), "mtime": os.path.getmtime(fp)})
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    manifest = {"id": cp_id, "pct": pct, "created_at": created_at, "label": label,
                "done": done, "total": total, "results": manifest_results}
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return Checkpoint(id=cp_id, pct=pct, created_at=created_at, label=label, done=done, total=total, path=dest)


def maybe_checkpoint(proy) -> Checkpoint | None:
    """Llamar periódicamente (p. ej. desde el poll de la pestaña Proceso)
    mientras hay un trabajo corriendo. Crea un checkpoint automático sólo la
    primera vez que se cruza cada múltiplo de 10% de avance real."""
    done, total = progress_fraction(proy)
    if total == 0:
        return None
    pct = int(10 * (10 * done // max(1, total)))  # bucket de 10 en 10, redondeado hacia abajo
    pct = min(90, pct)  # el 100% lo marca el propio fin del pipeline, no un checkpoint
    state = _load_state(proy)
    if pct <= state.get("last_pct", -1) or pct <= 0:
        return None
    cp_id = f"{pct:02d}pct_{time.strftime('%Y%m%d_%H%M%S')}"
    cp = _snapshot(proy, cp_id, pct, f"Automático · {pct}%", done, total)
    state["last_pct"] = pct
    state["checkpoints"] = state.get("checkpoints", []) + [cp.id]
    _save_state(proy, state)
    return cp


def manual_checkpoint(proy, label: str = "Manual") -> Checkpoint:
    done, total = progress_fraction(proy)
    pct = int(100 * done / total) if total else 0
    cp_id = f"manual_{time.strftime('%Y%m%d_%H%M%S')}"
    cp = _snapshot(proy, cp_id, pct, label, done, total)
    state = _load_state(proy)
    state["checkpoints"] = state.get("checkpoints", []) + [cp.id]
    _save_state(proy, state)
    return cp


def list_checkpoints(proy) -> list[Checkpoint]:
    d = _dir(proy)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        manifest_path = os.path.join(d, name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                m = json.load(fh)
        except (ValueError, OSError):
            continue
        out.append(Checkpoint(id=m["id"], pct=m["pct"], created_at=m["created_at"], label=m.get("label", ""),
                               done=m.get("done", 0), total=m.get("total", 0), path=os.path.join(d, name),
                               extra={"results": m.get("results", [])}))
    out.sort(key=lambda c: c.created_at, reverse=True)
    return out


def files_lost_on_restore(proy, checkpoint: Checkpoint) -> list[str]:
    """Rutas de resultados (relativas al proyecto) que son *más nuevas* que el
    checkpoint — lo que la restauración dejaría 'huérfano' de la config que se
    va a recuperar. No se borran solas: el diálogo de confirmación las lista y
    el usuario decide."""
    known = {r["path"] for r in checkpoint.extra.get("results", [])}
    lay = Layout(proy)
    lost = []
    if os.path.isdir(lay.results_dir()):
        for root, _dirs, files in os.walk(lay.results_dir()):
            for fn in files:
                fp = os.path.join(root, fn)
                rel = os.path.relpath(fp, proy)
                if rel not in known:
                    lost.append(rel)
    return sorted(lost)


def restore_checkpoint(proy, checkpoint: Checkpoint, delete_newer_results: bool = False) -> None:
    """Restaura axd.json desde el checkpoint (con backup del actual antes).
    Si delete_newer_results=True, además borra los archivos de resultado que
    files_lost_on_restore() marcó como posteriores al checkpoint."""
    current = os.path.join(proy, C.PROJECT_FILE)
    if os.path.exists(current):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        shutil.copy2(current, current + f".bak-restore-{stamp}")
    snap = os.path.join(checkpoint.path, C.PROJECT_FILE)
    if os.path.exists(snap):
        shutil.copy2(snap, current)
    if delete_newer_results:
        for rel in files_lost_on_restore(proy, checkpoint):
            fp = os.path.join(proy, rel)
            if os.path.exists(fp):
                os.remove(fp)
    # Reiniciar el umbral de checkpoints automáticos: si no, al rehacer el avance
    # perdido nunca se volverían a crear (last_pct seguiría en el máximo anterior).
    state = _load_state(proy)
    state["last_pct"] = (checkpoint.pct // 10) * 10
    _save_state(proy, state)
