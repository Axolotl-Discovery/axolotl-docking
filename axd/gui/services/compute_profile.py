"""Perfiles de uso de cómputo (Servidor / Estación de trabajo).

Decisión del usuario: por defecto se usa como máximo el 95% del cómputo
disponible en un servidor, y 70-80% en una estación de trabajo donde conviven
otros procesos (ajustable, con advertencia si se sube más). Se guarda en la
config global (~/.config/axolotl-docking/config.json vía axd.config), no por
proyecto, porque describe la máquina, no el experimento — igual que la
calibración."""
from __future__ import annotations

from dataclasses import dataclass

from ... import config as C
from ... import hardware as HW

WORKSTATION = "workstation"
SERVER = "server"

RECOMMENDED = {
    WORKSTATION: (70, 80),
    SERVER: (0, 95),
}
HARD_MAX = 95  # tope absoluto: nunca se ofrece el 100% del cómputo, ni en servidor
WARN_ABOVE = {
    WORKSTATION: 80,   # pasado esto, puede congelar otros procesos de la estación
    SERVER: 95,
}

DEFAULT_PROFILE = {"kind": WORKSTATION, "percent": 75}


@dataclass
class ComputeProfile:
    kind: str
    percent: int

    @property
    def recommended_range(self) -> tuple[int, int]:
        return RECOMMENDED.get(self.kind, RECOMMENDED[WORKSTATION])

    @property
    def warns(self) -> bool:
        return self.percent > WARN_ABOVE.get(self.kind, HARD_MAX)

    def effective_cores(self, usable_cores: int | None = None) -> int:
        """Núcleos a usar (lo que axd.runner escribe en docking.cpu)."""
        usable_cores = usable_cores or HW.detect().usable_cores
        return max(1, round(usable_cores * self.percent / 100))


def load() -> ComputeProfile:
    g = C.load_global()
    raw = g.get("compute_profile") or dict(DEFAULT_PROFILE)
    kind = raw.get("kind", WORKSTATION)
    percent = int(raw.get("percent", DEFAULT_PROFILE["percent"]))
    percent = max(1, min(HARD_MAX, percent))
    return ComputeProfile(kind=kind, percent=percent)


def save(profile: ComputeProfile) -> None:
    g = C.load_global()
    g["compute_profile"] = {"kind": profile.kind, "percent": profile.percent}
    C.save_global(g)


def apply_to_docking_params(docking: dict, profile: ComputeProfile | None = None) -> dict:
    """Devuelve una copia de p['docking'] con 'cpu' puesto según el perfil
    activo. cpu=0 en el esquema existente significa 'todos los núcleos'
    (ver axd.config.DEFAULT_DOCKING); aquí lo volvemos explícito."""
    profile = profile or load()
    out = dict(docking)
    out["cpu"] = profile.effective_cores()
    return out
