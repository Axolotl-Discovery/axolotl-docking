"""Dónde se ejecuta el docking: CPU (smina / AutoDock4) o GPU (Vina-GPU 2.1).

La preferencia vive en el config global de la máquina (`dispositivo`), porque
depende del equipo, no del proyecto. El motor que de verdad usó un proyecto se
registra en su axd.json (`docking.motor_usado`) y no se mezcla: Vina-GPU y
smina usan la función de puntuación de Vina, pero sus búsquedas no son
idénticas, así que las energías de un mismo proyecto deben salir de un solo motor.

Vina-GPU 2.1 (DeltaGroupNJUPT, Apache-2.0) usa OpenCL y sólo soporta GPU
NVIDIA o AMD en Linux/WSL o Windows; no hay versión para macOS. Sus kernels se
compilan para un tamaño máximo de caja (scripts/instalar_vina_gpu.sh):
  small: caja ≤ 30 Å por lado (por defecto; ~1.1 GB para las rejillas)
  large: caja ≤ 70 Å por lado (opcional; ~15 GB, sólo equipos grandes)
Una caja mayor (p. ej. docking ciego sobre toda la proteína) va en CPU."""
from __future__ import annotations

import os
import platform

CPU, GPU = "cpu", "gpu"
DEVICE_KEY = "dispositivo"
VINA_GPU_DIR_KEY = "vina_gpu_dir"
DEFAULT_VINA_GPU_DIR = "~/tools/vina-gpu"
BOX_LIMITS = {"small": 30.0, "large": 70.0}
KERNELS = ("Kernel1_Opt.bin", "Kernel2_Opt.bin")
EXE = "vina-gpu"
GPU_VENDORS = ("nvidia", "amd")

VENDOR_LABEL = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "apple": "Apple", "unknown": ""}


def get_device(g: dict) -> str:
    return GPU if (g or {}).get(DEVICE_KEY) == GPU else CPU


def vina_gpu_dir(g: dict) -> str:
    return os.path.expanduser((g or {}).get(VINA_GPU_DIR_KEY) or DEFAULT_VINA_GPU_DIR)


def vina_gpu_variants(g: dict) -> dict:
    """{'small': (exe, carpeta_kernels), 'large': (...)} sólo de las variantes
    instaladas completas (binario ejecutable + los dos kernels compilados)."""
    base = vina_gpu_dir(g)
    out = {}
    for var in BOX_LIMITS:
        d = os.path.join(base, var)
        exe = os.path.join(d, EXE)
        if os.path.isfile(exe) and os.access(exe, os.X_OK) and all(os.path.isfile(os.path.join(d, k)) for k in KERNELS):
            out[var] = (exe, d)
    return out


def variant_for_box(size, variants: dict) -> str | None:
    """La variante más chica que admite la caja (lado mayor), o None si ninguna."""
    lado = max(float(x) for x in size)
    for var in ("small", "large"):
        if var in variants and lado <= BOX_LIMITS[var] + 1e-6:
            return var
    return None


def cpu_vendor(model: str) -> str:
    m = (model or "").lower()
    if "intel" in m:
        return "intel"
    if "amd" in m or "ryzen" in m or "epyc" in m or "threadripper" in m:
        return "amd"
    if "apple" in m or m.startswith("m1") or m.startswith("m2") or m.startswith("m3") or m.startswith("m4"):
        return "apple"
    return "unknown"


def gpu_support(hw) -> tuple[bool, str, object]:
    """(se_puede, motivo, gpu_elegida). Sólo dice si ESTE equipo puede usar
    Vina-GPU; que esté instalado se ve aparte con vina_gpu_variants()."""
    if platform.system() == "Darwin":
        return False, "Vina-GPU no tiene versión para macOS; en esta Mac el docking corre en CPU.", None
    gpus = [g for g in getattr(hw, "gpus", []) if g.vendor in GPU_VENDORS]
    if not gpus:
        otras = [g for g in getattr(hw, "gpus", [])]
        if otras:
            return False, (f"Se detectó {otras[0].name}, pero Vina-GPU sólo funciona con GPU NVIDIA o AMD "
                           "(vía OpenCL)."), otras[0]
        return False, "No se detectó una GPU NVIDIA o AMD en este equipo.", None
    return True, "", gpus[0]
