"""Calibración de dispositivo: un benchmark corto para ajustar la estimación
de tiempo en una máquina nueva.

Importante sobre qué mide: en el momento de calibrar (antes de correr nada)
todavía no hay un entorno conda activado ni binarios de smina/ADFRsuite
garantizados, así que no podemos cronometrar una corrida real de docking. En
su lugar medimos la *velocidad de cómputo en bruto* de la máquina con un
benchmark estándar (hash criptográfico, puramente CPU-bound, sin E/S ni red)
y la comparamos contra una máquina de referencia para la que sí conocemos el
tiempo típico de una corrida de smina con los parámetros por defecto
(exhaustiveness 32). Esto da una **estimación inicial razonable**, no un
número exacto — exactamente como ya aclara axd.runner.mostrar_avance, el
estimado real y bueno llega una vez el trabajo lleva corridas terminadas,
porque ahí se mide el tiempo real transcurrido entre ellas. La calibración
sólo evita que esa primera estimación (antes de tener ningún dato real) sea
un número inventado igual en toda máquina.

Se guarda en la config global, keyed por una huella de hardware, para no
tener que repetirla en cada proyecto de la misma máquina."""
from __future__ import annotations

import hashlib
import platform
import time
from dataclasses import dataclass

from ... import config as C
from ... import hardware as HW

# Segundos típicos de una corrida de smina (exhaustiveness=32, proteína/ligando
# de tamaño medio) en la máquina de referencia usada para fijar BASELINE_HASHRATE.
REFERENCE_SECONDS_PER_JOB = 90.0
REFERENCE_EXHAUSTIVENESS = 32

# hashes/segundo de sha256 sobre bloques de 1 MiB en la máquina de referencia
# (un portátil de 4 núcleos de gama media, medido una vez con este mismo
# benchmark) — el punto de comparación para traducir "qué tan rápida es esta
# CPU" a "cuánto se tarda probablemente un smina en ella".
REFERENCE_HASHRATE = 850.0

_BENCH_SECONDS = 2.0  # duración objetivo del benchmark: corto, pero estable


@dataclass
class Calibration:
    fingerprint: str
    hashrate: float          # hashes/seg medidos en esta máquina
    seconds_per_job: float    # estimación resultante para exhaustiveness=32
    measured_at: str
    source: str = "benchmark"  # "benchmark" | "generic" (el usuario la saltó)


def hardware_fingerprint(hw: HW.Hardware | None = None) -> str:
    hw = hw or HW.detect()
    raw = "|".join([hw.cpu_model, str(hw.logical_cores), str(hw.physical_cores),
                    str(hw.usable_cores), str(bool(hw.gpus)), platform.machine()])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def run_benchmark(seconds: float = _BENCH_SECONDS) -> float:
    """CPU-bound puro: sha256 repetido sobre un bloque de 1 MiB durante
    `seconds` segundos en un solo núcleo (igual que smina, el cuello de
    botella real de docking es cómputo de un solo hilo por corrida, aunque
    corran varias corridas en paralelo). Devuelve hashes/segundo."""
    block = b"\0" * (1024 * 1024)
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < seconds:
        hashlib.sha256(block).digest()
        n += 1
    elapsed = time.perf_counter() - t0
    return n / elapsed if elapsed > 0 else 0.0


def _seconds_per_job(hashrate: float) -> float:
    if hashrate <= 0:
        return REFERENCE_SECONDS_PER_JOB
    ratio = REFERENCE_HASHRATE / hashrate
    return REFERENCE_SECONDS_PER_JOB * ratio


def calibrate_now() -> Calibration:
    """Corre el benchmark y guarda el resultado en la config global."""
    fp = hardware_fingerprint()
    hashrate = run_benchmark()
    cal = Calibration(
        fingerprint=fp, hashrate=hashrate, seconds_per_job=_seconds_per_job(hashrate),
        measured_at=_dt_now(), source="benchmark",
    )
    _save(cal)
    return cal


def use_generic_estimate() -> Calibration:
    """El usuario eligió 'usar una estimación genérica por ahora' en vez de
    calibrar (ver diálogo CalibracionDispositivo)."""
    cal = Calibration(fingerprint=hardware_fingerprint(), hashrate=REFERENCE_HASHRATE,
                       seconds_per_job=REFERENCE_SECONDS_PER_JOB, measured_at=_dt_now(), source="generic")
    _save(cal)
    return cal


def load_for_this_device() -> Calibration | None:
    g = C.load_global()
    table = g.get("calibraciones") or {}
    fp = hardware_fingerprint()
    raw = table.get(fp)
    if not raw:
        return None
    return Calibration(**raw)


def needs_calibration() -> bool:
    return load_for_this_device() is None


def estimate_seconds(n_jobs: int, exhaustiveness: int = REFERENCE_EXHAUSTIVENESS,
                      parallel_jobs: int = 1, cal: Calibration | None = None) -> float:
    """Estimación inicial del tiempo total, antes de tener ninguna corrida
    real terminada. parallel_jobs = cuántas corridas de smina caben a la vez
    (normalmente = núcleos asignados por el perfil de cómputo, porque cada
    corrida de smina usa ~1 núcleo de forma efectiva con cpu=1 por proceso)."""
    cal = cal or load_for_this_device() or use_generic_estimate()
    per_job = cal.seconds_per_job * (exhaustiveness / REFERENCE_EXHAUSTIVENESS)
    return n_jobs * per_job / max(1, parallel_jobs)


def _dt_now() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat(timespec="seconds")


def _save(cal: Calibration) -> None:
    g = C.load_global()
    table = g.get("calibraciones") or {}
    table[cal.fingerprint] = dict(fingerprint=cal.fingerprint, hashrate=cal.hashrate,
                                   seconds_per_job=cal.seconds_per_job, measured_at=cal.measured_at,
                                   source=cal.source)
    g["calibraciones"] = table
    C.save_global(g)
