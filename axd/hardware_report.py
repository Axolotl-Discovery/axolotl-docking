"""`Docking hardware`: show the machine, the suggested resource plan and the
thermal status, and cache the result per machine.

All user-facing text is Spanish; code and comments are English. The cache is
written to ~/.config/axolotl-docking/hardware.json and the thermal defaults are
seeded into config.json if absent, so the program adapts to each computer where
it runs (config is local to each install).

Planned final location: `axolotl_docking/app/` (report view).
"""
from __future__ import annotations

import json
import os

from . import config as C
from . import hardware as H
from . import thermal as T
from . import tuning
from . import ui

HARDWARE_CACHE = os.path.join(C.CONF_DIR, "hardware.json")


def _save_cache(hw: H.Hardware, pol: tuning.ThermalPolicy) -> None:
    try:
        os.makedirs(C.CONF_DIR, exist_ok=True)
        payload = {"hardware": hw.to_dict(), "thermal": pol.to_config()}
        tmp = HARDWARE_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, HARDWARE_CACHE)
    except OSError:
        pass


def _seed_thermal_config(pol: tuning.ThermalPolicy) -> None:
    """Write the thermal defaults into config.json if the block is missing."""
    g = C.cargar_global()
    if "thermal" not in g:
        g["thermal"] = pol.to_config()
        C.guardar_global(g)


def cache_is_present() -> bool:
    return os.path.exists(HARDWARE_CACHE)


def _fmt_gb(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb else "?"


def report(redetect: bool = False) -> H.Hardware:
    """Detect, print the Spanish report, cache it, and return the Hardware."""
    ui.titulo("Hardware y optimización")
    hw = H.detect()

    g = C.cargar_global()
    pol = tuning.ThermalPolicy.from_config(g.get("thermal"))

    # --- machine
    ui.ok(f"Procesador: {hw.cpu_model}")
    entorno = []
    if hw.is_wsl:
        entorno.append("WSL")
    if hw.in_container:
        entorno.append("contenedor")
    if entorno:
        ui.info("Entorno: " + ", ".join(entorno))

    nucleos = f"{hw.usable_cores} usables"
    if hw.usable_cores != hw.logical_cores:
        nucleos += f" (de {hw.logical_cores} lógicos"
        nucleos += f", {hw.physical_cores} físicos)" if hw.physical_cores else ")"
    else:
        nucleos += f" · {hw.physical_cores} físicos"
    if hw.cpu_limited_by_cgroup:
        nucleos += " · limitado por cgroup"
    ui.info(f"Núcleos: {nucleos}")

    mem = f"{_fmt_gb(hw.mem_available_mb)} disponibles de {_fmt_gb(hw.mem_total_mb)}"
    if hw.mem_limited_by_cgroup:
        mem += " · limitado por cgroup"
    ui.info(f"Memoria: {mem}")

    if hw.gpus:
        for gp in hw.gpus:
            vram = f" · {_fmt_gb(gp.vram_mb)} VRAM" if gp.vram_mb else ""
            ui.info(f"GPU: {gp.name}{vram}")
        ui.info(ui.gris("  (los motores actuales —smina/AutoDock4— usan solo CPU; "
                        "la GPU es informativa y habilita un motor futuro)"))
    else:
        ui.info("GPU: no detectada")

    # --- resource plan
    ui.titulo("Plan de ejecución sugerido")
    rp = tuning.plan(hw)
    ui.ok(f"{rp.max_workers} corrida(s) en paralelo × {rp.cpu_per_worker} núcleo(s) "
          f"= {rp.cores_used} núcleos en uso")
    for n in rp.notes:
        ui.info(n)
    ui.info(ui.gris("  (en modo avanzado puedes fijar tú los núcleos; este plan es la recomendación)"))

    # --- thermal status
    ui.titulo("Seguro térmico")
    if not pol.enabled:
        ui.aviso("Desactivado. Si la CPU/GPU se sobrecalienta no se bajará el procesamiento.")
    else:
        ui.ok(f"Activado · umbral CPU {pol.cpu_throttle_c}/{pol.cpu_pause_c} °C · "
              f"GPU {pol.gpu_throttle_c}/{pol.gpu_pause_c} °C (reducir/pausar)")

    cpu_t = T.read_cpu_temp_c()
    gpu_t = T.read_gpu_temps_c()
    if cpu_t is not None:
        ui.info(f"Temperatura CPU ahora: {cpu_t:.0f} °C")
    else:
        aviso = "Sensor de CPU no disponible"
        if hw.is_wsl:
            aviso += " (típico en WSL: no puede proteger la CPU por temperatura)"
        ui.aviso(aviso)
    if gpu_t:
        ui.info("Temperatura GPU ahora: " + ", ".join(f"{t:.0f} °C" for t in gpu_t))
    elif hw.gpus:
        ui.info(ui.gris("  Sensor de GPU no disponible (instala nvidia-smi / usa --gpus en Docker)"))

    # --- persist per machine
    _seed_thermal_config(pol)
    _save_cache(hw, pol)
    ui.info(ui.gris(f"\n  Guardado en {C.CONF_DIR}/hardware.json (perfil de esta computadora)"))
    return hw
