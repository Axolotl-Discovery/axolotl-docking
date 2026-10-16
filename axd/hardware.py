"""Hardware detection for Axolotl Docking (standard library only).

This module runs in the interface layer, before the conda environment exists,
so it depends on nothing but the standard library and reads from /proc, /sys
and `nvidia-smi`.

It is cgroup-aware: inside a container started with `--cpus`/`--memory`, the
usable CPU and memory reflect the cgroup limit, not the host. This matters for
the planned Docker packaging, where the host /proc would otherwise overcount.

User-facing text lives in the report module; everything here is data.

NOTE: planned final location is `axolotl_docking/infra/hardware.py`. It lives
under `axd/` for now so the `Docking hardware` command works without the full
repackage. Nothing imports it except the report module and the CLI.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------- data model
@dataclass
class Gpu:
    name: str
    vram_mb: int | None = None
    vendor: str = "unknown"          # "nvidia", "amd", "intel", "unknown"


@dataclass
class Hardware:
    cpu_model: str = "desconocido"
    logical_cores: int = 1           # os.cpu_count()
    physical_cores: int = 1          # distinct (physical id, core id) in /proc/cpuinfo
    usable_cores: int = 1            # affinity ∩ cgroup limit — the number we schedule on
    mem_total_mb: int = 0            # MemTotal (or cgroup memory.max if lower)
    mem_available_mb: int = 0        # MemAvailable (or cgroup equivalent if lower)
    gpus: list[Gpu] = field(default_factory=list)
    is_wsl: bool = False
    in_container: bool = False
    cpu_limited_by_cgroup: bool = False
    mem_limited_by_cgroup: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gpus"] = [asdict(g) for g in self.gpus]
        return d


# ---------------------------------------------------------------- low-level readers
def _read(path: str) -> str | None:
    try:
        with open(path, errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


def _run(cmd: list[str], timeout: int = 5) -> str | None:
    """Run a command, return stdout, or None if it is missing or fails."""
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------- environment flags
def detect_wsl() -> bool:
    txt = _read("/proc/version") or ""
    return "microsoft" in txt.lower()


def detect_container() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    cg = _read("/proc/1/cgroup") or ""
    return any(tok in cg for tok in ("docker", "containerd", "kubepods", "lxc", "libpod"))


# ---------------------------------------------------------------- CPU
def _cpuinfo() -> list[dict[str, str]]:
    txt = _read("/proc/cpuinfo") or ""
    blocks, cur = [], {}
    for line in txt.splitlines():
        if not line.strip():
            if cur:
                blocks.append(cur); cur = {}
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            cur[k.strip()] = v.strip()
    if cur:
        blocks.append(cur)
    return blocks


def cpu_model() -> str:
    for b in _cpuinfo():
        for key in ("model name", "Model", "Processor", "cpu model"):
            if b.get(key):
                return b[key]
    return "desconocido"


def physical_cores(logical_fallback: int) -> int:
    pairs = set()
    for b in _cpuinfo():
        pid, cid = b.get("physical id"), b.get("core id")
        if pid is not None and cid is not None:
            pairs.add((pid, cid))
    return len(pairs) or logical_fallback


def _affinity_cores() -> int:
    try:
        return len(os.sched_getaffinity(0))          # respects taskset / cgroup pinning
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _cgroup_cpu_limit() -> float | None:
    """CPU cores allowed by cgroup, or None if unlimited/unavailable.

    cgroup v2: /sys/fs/cgroup/cpu.max -> "<quota> <period>" or "max <period>".
    cgroup v1: cpu.cfs_quota_us / cpu.cfs_period_us.
    """
    v2 = _read("/sys/fs/cgroup/cpu.max")
    if v2:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota, period = int(parts[0]), int(parts[1])
                if quota > 0 and period > 0:
                    return quota / period
            except ValueError:
                pass
        return None
    quota = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    try:
        q, p = int((quota or "-1").strip()), int((period or "100000").strip())
        if q > 0 and p > 0:
            return q / p
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------- memory
def _meminfo_mb(key: str) -> int:
    txt = _read("/proc/meminfo") or ""
    m = re.search(rf"^{re.escape(key)}:\s+(\d+)\s*kB", txt, re.M)
    return int(m.group(1)) // 1024 if m else 0


def _cgroup_mem_limit_mb() -> int | None:
    for path in ("/sys/fs/cgroup/memory.max",                       # v2
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):    # v1
        raw = _read(path)
        if raw and raw.strip().isdigit():
            mb = int(raw.strip()) // (1024 * 1024)
            # kernels report an astronomically large number when unlimited
            if 0 < mb < 1024 * 1024 * 64:        # < 64 TiB means a real limit
                return mb
    return None


# ---------------------------------------------------------------- GPU
def _nvidia_gpus() -> list[Gpu]:
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits"])
    if not out:
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else "NVIDIA GPU"
        vram = None
        if len(parts) > 1 and parts[1].isdigit():
            vram = int(parts[1])
        gpus.append(Gpu(name=name, vram_mb=vram, vendor="nvidia"))
    return gpus


def _lspci_gpus() -> list[Gpu]:
    """Fallback: list display controllers when nvidia-smi is absent."""
    out = _run(["lspci"])
    if not out:
        return []
    gpus = []
    for line in out.splitlines():
        if re.search(r"VGA compatible controller|3D controller|Display controller", line):
            desc = line.split(":", 2)[-1].strip()
            vendor = ("nvidia" if "NVIDIA" in desc else
                      "amd" if re.search(r"AMD|ATI|Radeon", desc) else
                      "intel" if "Intel" in desc else "unknown")
            gpus.append(Gpu(name=desc, vendor=vendor))
    return gpus


def detect_gpus() -> list[Gpu]:
    gpus = _nvidia_gpus()
    if gpus:
        return gpus
    # WSL exposes the GPU through /dev/dxg even when the tools are not installed.
    if os.path.exists("/dev/dxg"):
        return [Gpu(name="GPU vía WSL (/dev/dxg)", vendor="unknown")]
    return _lspci_gpus()


# ---------------------------------------------------------------- top level
def detect() -> Hardware:
    logical = os.cpu_count() or 1
    affinity = _affinity_cores()
    cg_cpu = _cgroup_cpu_limit()

    usable = affinity
    cpu_capped = False
    if cg_cpu is not None:
        capped = max(1, int(cg_cpu))
        if capped < usable:
            usable, cpu_capped = capped, True

    mem_total = _meminfo_mb("MemTotal")
    mem_avail = _meminfo_mb("MemAvailable") or mem_total
    cg_mem = _cgroup_mem_limit_mb()
    mem_capped = False
    if cg_mem is not None and cg_mem < mem_total:
        mem_total, mem_capped = cg_mem, True
        mem_avail = min(mem_avail, cg_mem)

    return Hardware(
        cpu_model=cpu_model(),
        logical_cores=logical,
        physical_cores=physical_cores(logical),
        usable_cores=max(1, usable),
        mem_total_mb=mem_total,
        mem_available_mb=mem_avail,
        gpus=detect_gpus(),
        is_wsl=detect_wsl(),
        in_container=detect_container(),
        cpu_limited_by_cgroup=cpu_capped,
        mem_limited_by_cgroup=mem_capped,
    )
