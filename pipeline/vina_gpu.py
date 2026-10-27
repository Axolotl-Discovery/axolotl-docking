"""Corrida de docking con Vina-GPU 2.1 (motor GPU). Mismo contrato que
docking.correr_smina: devuelve (afinidad, ya_existia) y escribe la salida de
forma atómica. Vina-GPU no tiene --exhaustiveness: la búsqueda la controlan
--thread (hilos de búsqueda en la GPU, ≥ 1000) y --search_depth (si no se da,
Vina-GPU la decide)."""
import os
import shutil

from common import affinity, is_complete, log, run_cmd, tmp_dir
from axd import device as DEV

DEFAULT_THREADS = 8000


def etiqueta(d):
    sd = d.get("gpu_search_depth")
    return f"Vina-GPU · {int(d.get('gpu_threads') or DEFAULT_THREADS)} hilos" + (f" · profundidad {sd}" if sd else "")


def comando(exe, kernels_dir, caja, semilla, d):
    c, s = caja["center"], caja["size"]
    cmd = [exe, "--receptor", "r.pdbqt", "--ligand", "l.pdbqt", "--out", "o.pdbqt",
           "--center_x", str(c[0]), "--center_y", str(c[1]), "--center_z", str(c[2]),
           "--size_x", str(s[0]), "--size_y", str(s[1]), "--size_z", str(s[2]),
           "--seed", str(semilla), "--num_modes", str(d["num_modes"]), "--energy_range", str(d["energy_range"]),
           "--thread", str(max(1000, int(d.get("gpu_threads") or DEFAULT_THREADS))),
           "--opencl_binary_path", kernels_dir]
    if d.get("gpu_search_depth"):
        cmd += ["--search_depth", str(int(d["gpu_search_depth"]))]
    return cmd


def correr(variantes, rec, lig, caja, salida, semilla, d, rehacer=False):
    if is_complete(salida) and not rehacer:
        return affinity(salida), True
    var = DEV.variant_for_box(caja["size"], variantes)
    if var is None:
        lado = max(float(x) for x in caja["size"])
        lim = max((DEV.BOX_LIMITS[v] for v in variantes), default=0)
        log(f"      ✘ Vina-GPU: la caja mide {lado:.0f} Å y lo instalado admite hasta {lim:.0f} Å por lado. "
            "Achica la caja o usa CPU (Entorno → Dispositivo).")
        return None, False
    exe, kdir = variantes[var]
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    tmp = tmp_dir("dockgpu")
    try:
        shutil.copy(rec, os.path.join(tmp, "r.pdbqt"))
        shutil.copy(lig, os.path.join(tmp, "l.pdbqt"))
        cmd = comando(exe, kdir, caja, semilla, d)
        rc, out = run_cmd(cmd, cwd=tmp, timeout=6 * 3600)
        with open(salida[:-6] + ".log", "w") as fh:
            fh.write(" ".join(cmd) + "\n\n" + out)
        o = os.path.join(tmp, "o.pdbqt")
        if rc != 0 or not is_complete(o):
            motivo = ""
            if "Cannot find any" in out and "platform" in out:
                motivo = " — no encontró la plataforma OpenCL de la GPU (¿driver instalado?)"
            log(f"      ✘ Vina-GPU falló{motivo} (ver {os.path.basename(salida)[:-6]}.log)")
            return None, False
        shutil.copy(o, salida + ".part")
        os.replace(salida + ".part", salida)
        return affinity(salida), False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
