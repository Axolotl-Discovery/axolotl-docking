"""Auto-actualización: envuelve exactamente lo que ya hace `Docking actualizar`
(axd.cli.actualizar: git pull --ff-only sobre la instalación) para poder
llamarlo sin bloquear la interfaz y sin los prints pensados para terminal."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ... import config as C


@dataclass
class UpdateCheck:
    is_git_install: bool
    current_version: str
    behind_by: int
    remote_summary: str  # últimos mensajes de commit nuevos, para el changelog


def _run(cmd, timeout=20):
    return subprocess.run(cmd, cwd=C.APP, capture_output=True, text=True, timeout=timeout)


def check_for_update() -> UpdateCheck:
    if not __import__("os").path.isdir(__import__("os").path.join(C.APP, ".git")):
        return UpdateCheck(is_git_install=False, current_version=C.VERSION, behind_by=0, remote_summary="")
    try:
        _run(["git", "fetch", "--quiet"], timeout=15)
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() or "main"
        behind_out = _run(["git", "rev-list", "--count", f"HEAD..origin/{branch}"]).stdout.strip()
        behind = int(behind_out) if behind_out.isdigit() else 0
        summary = ""
        if behind:
            summary = _run(["git", "log", "--oneline", f"HEAD..origin/{branch}", "-n", "6"]).stdout.strip()
    except (subprocess.SubprocessError, OSError, ValueError):
        return UpdateCheck(is_git_install=True, current_version=C.VERSION, behind_by=0, remote_summary="")
    return UpdateCheck(is_git_install=True, current_version=C.VERSION, behind_by=behind, remote_summary=summary)


def apply_update() -> tuple[bool, str]:
    """Replica axd.cli.actualizar(): git pull --ff-only + re-chmod de los
    scripts. Devuelve (ok, mensaje)."""
    import os
    r = _run(["git", "pull", "--ff-only"], timeout=120)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "git pull falló").strip()
    subprocess.call(["bash", "-c", f'chmod +x "{C.APP}/bin/"* "{C.APP}/scripts/"*.sh "{C.APP}"/*.sh 2>/dev/null'])
    new_version_file = os.path.join(C.APP, "VERSION")
    new_version = open(new_version_file).read().strip() if os.path.exists(new_version_file) else C.VERSION
    return True, new_version
