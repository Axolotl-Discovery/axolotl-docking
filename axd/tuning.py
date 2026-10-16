"""Turn detected hardware into a resource plan and hold the safety policies.

Pure logic, standard library only, no side effects — so it is easy to test and
relocate to `axolotl_docking/domain/tuning.py` later.

Two safety ideas live here:

  * Core budget. Never schedule 100 % of the machine. We cap total utilisation
    at ~90 % and always reserve at least one core (when more than one exists)
    so the OS stays responsive and the computer does not freeze during docking.

  * Thermal policy. Thresholds (with hysteresis) at which the docking pool slows
    down or pauses if the CPU/GPU gets too hot. The reading of the sensors lives
    in `thermal.py`; this module only states the numbers and the on/off switch.

Engines (smina, AutoDock4) are CPU-bound and parallelised across many
ligand×target×seed jobs. The plan therefore chooses how many docking jobs run
at once (`max_workers`) and how many cores each one gets (`cpu_per_worker`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# Rough resident footprint per concurrent docking worker (smina + python glue).
# Used only to keep the worker count under the available memory; generous on
# purpose so a low-RAM machine is never oversubscribed.
_MB_PER_WORKER = 1500

# Absolute ceiling: even if the user asks for every core, keep this much headroom.
HARD_MAX_FRACTION = 0.95
DEFAULT_MAX_FRACTION = 0.90


# ---------------------------------------------------------------- core budget
def core_budget(usable_cores: int, max_fraction: float = DEFAULT_MAX_FRACTION) -> int:
    """Cores we are willing to schedule, leaving headroom for the OS.

    Caps at `max_fraction` of usable cores and always reserves at least one core
    when the machine has more than one.
    """
    usable = max(1, int(usable_cores))
    if usable == 1:
        return 1
    reserved = max(1, round(usable * (1 - max_fraction)))
    return max(1, usable - reserved)


def confirm_core_choice(requested_cpu: int, usable_cores: int):
    """Validate a user's CPU choice for the docking step.

    `requested_cpu` follows the project convention: 0 means "all cores".
    Returns (allowed_cpu, warning) where `warning` is a Spanish UI string to
    show the user, or None when the choice already leaves headroom.
    The returned value is always capped at HARD_MAX_FRACTION of usable cores.
    """
    usable = max(1, int(usable_cores))
    hard_cap = core_budget(usable, HARD_MAX_FRACTION)      # never exceed ~95 %

    wants_all = requested_cpu == 0 or requested_cpu >= usable
    near_all = requested_cpu >= math.ceil(usable * HARD_MAX_FRACTION)

    if wants_all or near_all:
        allowed = hard_cap
        warning = (
            "⚠ Usar todos (o casi todos) los núcleos puede congelar la "
            "computadora durante el docking. Te recomiendo dejar al menos 1 "
            f"libre (máximo ~{int(HARD_MAX_FRACTION * 100)} %). "
            f"Limitaré a {allowed} de {usable} núcleos."
        )
        return allowed, warning
    return max(1, requested_cpu), None


# ---------------------------------------------------------------- resource plan
@dataclass
class ResourcePlan:
    max_workers: int           # docking jobs running at the same time
    cpu_per_worker: int        # --cpu passed to each smina/autodock process
    cores_used: int            # max_workers * cpu_per_worker
    reserved_cores: int        # kept free for the OS
    notes: list[str] = field(default_factory=list)   # Spanish UI strings


def plan(hw, n_jobs: int | None = None, max_fraction: float = DEFAULT_MAX_FRACTION) -> ResourcePlan:
    """Choose worker count and cores-per-worker from the detected hardware.

    Heuristic: Vina/smina scale well up to the physical core count and poorly on
    hyperthreads, and with many jobs several smaller workers beat one big worker.
    Memory and (optionally) the number of pending jobs cap the worker count.
    """
    usable = max(1, int(getattr(hw, "usable_cores", 1)))
    budget = core_budget(usable, max_fraction)
    notes: list[str] = []

    # Target threads per worker: enough to be efficient, small enough that
    # several jobs run at once (Vina/smina scale sublinearly past a few threads).
    target = 4 if budget >= 4 else (2 if budget >= 2 else 1)

    # Spend the whole budget: pick the worker count, then split cores evenly so
    # no core sits idle (e.g. 7 -> 1x7 would waste nothing; 14 -> 3x4+... ).
    max_workers = max(1, budget // target)
    cpu_per_worker = max(1, budget // max_workers)

    # memory guard
    mem_avail = int(getattr(hw, "mem_available_mb", 0) or 0)
    if mem_avail:
        by_mem = max(1, mem_avail // _MB_PER_WORKER)
        if by_mem < max_workers:
            notes.append(
                f"Memoria disponible ({mem_avail} MB): limito a {by_mem} "
                "corrida(s) en paralelo para no saturar la RAM."
            )
            max_workers = by_mem

    # do not spawn more workers than there is work
    if n_jobs is not None and n_jobs > 0:
        max_workers = min(max_workers, n_jobs)

    reserved = usable - budget
    if reserved > 0:
        notes.append(f"Dejo {reserved} núcleo(s) libre(s) para el sistema (tope ~{int(max_fraction * 100)} %).")

    physical = int(getattr(hw, "physical_cores", usable) or usable)
    if usable > physical:
        notes.append("Hay hyperthreading: el rendimiento no escala al 100 % con los hilos lógicos.")

    return ResourcePlan(
        max_workers=max_workers,
        cpu_per_worker=cpu_per_worker,
        cores_used=max_workers * cpu_per_worker,
        reserved_cores=max(0, reserved),
        notes=notes,
    )


# ---------------------------------------------------------------- thermal policy
@dataclass
class ThermalPolicy:
    """Temperatures (°C) at which the docking pool slows down or pauses.

    Defaults are conservative and generic; real limits vary by chip, so they
    are user-editable. `enabled=False` turns the guard off for this machine
    (always with a warning when the user does it).
    """
    enabled: bool = True
    cpu_throttle_c: int = 85       # reduce active workers above this
    cpu_pause_c: int = 92          # launch no new jobs above this
    cpu_resume_c: int = 75         # resume below this (hysteresis)
    gpu_throttle_c: int = 83
    gpu_pause_c: int = 90
    gpu_resume_c: int = 70
    poll_seconds: int = 10

    @classmethod
    def from_config(cls, cfg: dict | None) -> "ThermalPolicy":
        cfg = cfg or {}
        base = cls()
        for f in base.__dataclass_fields__:
            if f in cfg:
                setattr(base, f, cfg[f])
        return base

    def to_config(self) -> dict:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


DISABLE_THERMAL_WARNING = (
    "⚠ Vas a desactivar el seguro térmico. Si la CPU/GPU se sobrecalienta, la "
    "computadora podría apagarse o dañarse, y no bajaré el procesamiento. "
    "¿Seguro? (s/N)"
)
