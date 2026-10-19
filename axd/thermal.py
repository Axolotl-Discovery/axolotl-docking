"""Temperature sensors and the overheating guard (standard library only).

Reading side only: this module reports what the CPU and GPU sensors say and
decides, given a ThermalPolicy, whether the docking pool should run, throttle
or pause. The policy thresholds live in `tuning.py`; the enforcement (acting on
the worker pool) is wired in the pipeline phase.

Honest limitations, stated so no false sense of safety is given:

  * WSL2 is a VM and usually exposes NO CPU thermal zones, so CPU temperature is
    often unreadable there. The NVIDIA GPU temperature IS readable via nvidia-smi
    even under WSL2.
  * Inside Docker the host sensors must be mounted (or run privileged) and the
    GPU needs `--gpus`.

When a sensor is unavailable the guard simply cannot protect that component and
`*_available()` returns False — the caller must say so to the user rather than
pretend the machine is protected.

Planned final location: `axolotl_docking/infra/thermal.py`.
"""
from __future__ import annotations

import glob
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------- CPU temperature
# thermal_zone `type` values that correspond to a CPU package/core on common chips
_CPU_ZONE_HINTS = ("x86_pkg_temp", "cpu", "coretemp", "k10temp", "k8temp",
                   "zenpower", "soc", "cpu-thermal")
# hwmon chip names that report CPU core temperatures
_CPU_HWMON_HINTS = ("coretemp", "k10temp", "k8temp", "zenpower", "cpu")


def _read(path: str) -> str | None:
    try:
        with open(path, errors="ignore") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _zone_temps() -> list[float]:
    temps = []
    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        ztype = (_read(f"{zone}/type") or "").lower()
        if not any(h in ztype for h in _CPU_ZONE_HINTS):
            continue
        raw = _read(f"{zone}/temp")
        if raw and raw.lstrip("-").isdigit():
            temps.append(int(raw) / 1000.0)        # millidegrees -> °C
    return temps


def _hwmon_temps() -> list[float]:
    temps = []
    for chip in glob.glob("/sys/class/hwmon/hwmon*"):
        name = (_read(f"{chip}/name") or "").lower()
        if not any(h in name for h in _CPU_HWMON_HINTS):
            continue
        for tfile in glob.glob(f"{chip}/temp*_input"):
            raw = _read(tfile)
            if raw and raw.lstrip("-").isdigit():
                temps.append(int(raw) / 1000.0)
    return temps


def read_cpu_temp_c() -> float | None:
    """Hottest CPU reading in °C, or None if no CPU sensor is available."""
    temps = _zone_temps() or _hwmon_temps()
    # sanity window: discard obviously bogus values
    temps = [t for t in temps if 5.0 <= t <= 130.0]
    return round(max(temps), 1) if temps else None


def cpu_sensor_available() -> bool:
    return read_cpu_temp_c() is not None


# ---------------------------------------------------------------- GPU temperature
def read_gpu_temps_c() -> list[float]:
    """Per-GPU temperature in °C from nvidia-smi; empty list if unavailable."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.strip().splitlines():
        m = re.search(r"-?\d+", line)
        if m:
            out.append(float(m.group()))
    return out


def gpu_sensor_available() -> bool:
    return bool(read_gpu_temps_c())


# ---------------------------------------------------------------- guard
class Decision(Enum):
    RUN = "run"              # temperatures fine, run at full plan
    THROTTLE = "throttle"    # hot: reduce concurrency
    PAUSE = "pause"          # too hot: launch no new jobs until it cools


@dataclass
class ThermalReading:
    cpu_c: float | None
    gpu_c: float | None      # hottest GPU
    decision: Decision
    reason: str = ""         # Spanish UI string when not RUN


class ThermalGuard:
    """Stateful guard with hysteresis, consulted between docking jobs.

    It never interrupts a running smina/autodock process (those cannot be
    preempted); it only governs whether the *next* job may start and how many
    workers stay active. That granularity is safe because the pipeline is
    resumable and checkpoints every completed run.
    """

    def __init__(self, policy):
        self.policy = policy
        self._paused = False     # sticky until the resume threshold is crossed

    def read(self) -> ThermalReading:
        if not getattr(self.policy, "enabled", True):
            return ThermalReading(None, None, Decision.RUN, "seguro térmico desactivado")

        cpu = read_cpu_temp_c()
        gpus = read_gpu_temps_c()
        gpu = max(gpus) if gpus else None

        over_pause = ((cpu is not None and cpu >= self.policy.cpu_pause_c) or
                      (gpu is not None and gpu >= self.policy.gpu_pause_c))
        can_resume = ((cpu is None or cpu <= self.policy.cpu_resume_c) and
                      (gpu is None or gpu <= self.policy.gpu_resume_c))
        over_throttle = ((cpu is not None and cpu >= self.policy.cpu_throttle_c) or
                         (gpu is not None and gpu >= self.policy.gpu_throttle_c))

        if over_pause:
            self._paused = True
        elif self._paused and can_resume:
            self._paused = False

        if self._paused:
            hot = self._hottest_str(cpu, gpu)
            return ThermalReading(cpu, gpu, Decision.PAUSE,
                                  f"Temperatura alta ({hot}): bajo el procesamiento por posible "
                                  "sobrecalentamiento; pauso corridas nuevas hasta que enfríe. "
                                  "Lo calculado se conserva.")
        if over_throttle:
            hot = self._hottest_str(cpu, gpu)
            return ThermalReading(cpu, gpu, Decision.THROTTLE,
                                  f"Temperatura elevada ({hot}): reduzco el número de corridas en paralelo.")
        return ThermalReading(cpu, gpu, Decision.RUN)

    @staticmethod
    def _hottest_str(cpu, gpu) -> str:
        parts = []
        if cpu is not None:
            parts.append(f"CPU {cpu:.0f} °C")
        if gpu is not None:
            parts.append(f"GPU {gpu:.0f} °C")
        return ", ".join(parts) or "sin lectura"
