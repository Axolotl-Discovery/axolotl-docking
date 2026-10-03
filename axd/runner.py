"""Ejecuta los pasos del pipeline dentro del entorno conda y controla trabajos en segundo plano."""
import datetime as _dt
import json
import os
import signal
import subprocess
import sys
import time

from . import config as C
from . import ui

PASOS = ["descargar", "receptores", "ligandos", "redocking", "docking", "resumen"]
DESCRIPCION_PASOS = {
    "descargar": "Descargar estructuras (RCSB / AlphaFold) y ligandos (PubChem)",
    "receptores": "Limpiar receptores (PDBFixer + prepare_receptor) y calcular cajas",
    "ligandos": "Preparar ligandos y controles (3D + Meeko → PDBQT)",
    "redocking": "Validación por redocking del ligando cristalográfico (RMSD)",
    "docking": "Docking smina: todos los ligandos × todas las dianas × semillas",
    "resumen": "Tabla de afinidades (media ± DE, LE, Δ vs control) y mejores poses",
}


def _logs(proy):
    d = os.path.join(proy, "04_Docking", "logs")
    os.makedirs(d, exist_ok=True)
    return d


def _estado_file(proy):
    return os.path.join(_logs(proy), "trabajo.json")


def estado(proy):
    f = _estado_file(proy)
    if not os.path.exists(f):
        return None
    try:
        e = json.load(open(f))
    except ValueError:
        return None
    e["vivo"] = _vivo(e.get("pid"))
    return e


def _vivo(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:  # descarta procesos zombi
        return open(f"/proc/{pid}/stat").read().split(") ")[1][0] != "Z"
    except OSError:
        return True


def _script_entorno(g):
    """Comando bash que activa el entorno y pone smina/ADFR en el PATH."""
    return (
        'source "$AXD_CONDA/etc/profile.d/conda.sh" && conda activate "$AXD_ENV" || '
        '{ echo "✘ No pude activar el entorno conda \'$AXD_ENV\'. Corre: Docking entorno"; exit 3; }; '
        # ADFRsuite trae su propio "python" 2.7: va AL FINAL del PATH y se usa el python del entorno por ruta
        'export PATH="$CONDA_PREFIX/bin:$PATH:$AXD_ADFR:$AXD_TOOLS"; export PYTHONUNBUFFERED=1; '
        'exec "$CONDA_PREFIX/bin/python" "$AXD_APP/pipeline/run.py" "$AXD_PROY" "$@"'
    )


def _env(proy):
    g = C.cargar_global()
    conda = C.ruta_conda(g)
    if not conda:
        ui.error("No encontré conda/miniforge. Instálalo con:  Docking entorno")
        return None
    e = dict(os.environ)
    e.update(AXD_CONDA=conda, AXD_ENV=g["entorno"], AXD_APP=C.APP, AXD_PROY=proy,
             AXD_ADFR=os.path.expanduser(g["adfr_bin"]), AXD_TOOLS=os.path.expanduser(g["tools_bin"]))
    return e


def ejecutar(proy, pasos, fondo=True, extra=None):
    """Lanza run.py con los pasos indicados. En fondo: sobrevive a cerrar el menú."""
    if not pasos:
        return
    e = estado(proy)
    if e and e["vivo"]:
        ui.aviso(f"Ya hay un trabajo corriendo en este proyecto (PID {e['pid']}: {', '.join(e['pasos'])}).")
        ui.info("Usa 'Ver avance', 'Detener' o espera a que termine.")
        return
    env = _env(proy)
    if env is None:
        return
    args = list(pasos) + (extra or [])
    sello = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log = os.path.join(_logs(proy), f"pipeline_{sello}.log")
    cmd = ["bash", "-c", _script_entorno(None), "axd"] + args
    if fondo:
        with open(log, "w") as fh:
            p = subprocess.Popen(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 start_new_session=True, cwd=proy)
        json.dump(dict(pid=p.pid, pasos=list(pasos), extra=extra or [], inicio=sello, log=log),
                  open(_estado_file(proy), "w"), indent=2)
        time.sleep(1.5)
        if p.poll() is not None and p.returncode != 0:
            ui.error(f"El trabajo terminó de inmediato (código {p.returncode}). Últimas líneas del log:")
            print(ui.gris("".join(open(log).readlines()[-15:])))
            return
        ui.ok(f"Trabajo lanzado en segundo plano (PID {p.pid}).")
        ui.info(f"Log: {os.path.relpath(log, proy)}")
        ui.info("Puedes cerrar este menú; sigue corriendo mientras la terminal de WSL siga abierta.")
        ui.info("Para ver cómo va:  Docking avance   ·   en vivo:  Docking log")
    else:
        with open(log, "w") as fh:
            p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, cwd=proy, text=True, bufsize=1,
                                 start_new_session=True)
            json.dump(dict(pid=p.pid, pasos=list(pasos), extra=extra or [], inicio=sello, log=log),
                      open(_estado_file(proy), "w"), indent=2)
            try:
                for linea in p.stdout:
                    sys.stdout.write(linea); fh.write(linea); fh.flush()
                p.wait()
            except KeyboardInterrupt:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                p.wait()
                ui.aviso("Interrumpido. Lo hecho hasta ahora se conserva; puedes reanudar.")
        try:
            os.remove(_estado_file(proy))
        except OSError:
            pass
        (ui.ok if p.returncode == 0 else ui.error)(f"Terminado (código {p.returncode}). Log: {os.path.relpath(log, proy)}")


def detener(proy, silencioso=False):
    e = estado(proy)
    if not e or not e["vivo"]:
        if not silencioso:
            ui.info("No hay ningún trabajo corriendo en este proyecto.")
        return False
    try:
        os.killpg(e["pid"], signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(e["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not _vivo(e["pid"]):
            break
        time.sleep(0.25)
    else:
        try:
            os.killpg(e["pid"], signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    subprocess.run(["bash", "-c", f"rm -rf /tmp/axd_{e['pid']}_* 2>/dev/null"])
    ui.ok(f"Trabajo detenido (PID {e['pid']}). Lo terminado se conserva.")
    return True


def reanudar(proy):
    e = estado(proy)
    if e and e["vivo"]:
        ui.aviso("Ya está corriendo; no lanzo otro.")
        return
    # limpia escrituras a medias de un corte de luz o de un 'detener'
    n = 0
    for raiz, _, archivos in os.walk(os.path.join(proy, "04_Docking", "Resultados")):
        for a in archivos:
            if a.endswith(".part"):
                os.remove(os.path.join(raiz, a)); n += 1
    if n:
        ui.info(f"Eliminé {n} archivos incompletos (.part).")
    pasos = (e or {}).get("pasos") or ["docking", "resumen"]
    ui.info("Retomando: " + ", ".join(pasos) + ui.gris("  (lo ya terminado se salta)"))
    extra = [x for x in (e or {}).get("extra", []) if x != "--rehacer"]  # reanudar nunca vuelve a empezar de cero
    ejecutar(proy, pasos, fondo=True, extra=extra)


# ---------------------------------------------------------------- avance
def _completo(f):
    try:
        if os.path.getsize(f) == 0:
            return False
        with open(f, "rb") as fh:
            fh.seek(max(0, os.path.getsize(f) - 200))
            fin = fh.read().decode(errors="ignore").rstrip()
        return fin.endswith("ENDMDL")
    except OSError:
        return False


def corridas_esperadas(p):
    sem = p["docking"]["semillas"]
    dianas = [d["id"] for d in p["dianas"]]
    tabla = {}
    for d in dianas:
        ligs = [l["id"] for l in p["ligandos"]]
        ligs += [c["id"] for c in p["controles"] if not c.get("diana") or c.get("diana") == d]
        tabla[d] = [(l, s) for l in ligs for s in sem]
    return tabla


def mostrar_avance(proy):
    p = C.cargar_proyecto(proy)
    ui.titulo(f"Avance · {p['nombre']}")
    e = estado(proy)
    if e and e["vivo"]:
        ui.ok(f"Corriendo (PID {e['pid']}) · pasos: {', '.join(e['pasos'])} · desde {e['inicio']}")
    elif e:
        ui.info(f"Último trabajo ({', '.join(e['pasos'])}, {e['inicio']}) ya no está corriendo.")
        _ultimo_error(e)
    else:
        ui.info("No hay trabajo corriendo.")
    tabla = corridas_esperadas(p)
    if not tabla:
        ui.aviso("El proyecto aún no tiene dianas configuradas.")
        return
    res = os.path.join(proy, "04_Docking", "Resultados")
    total = hechas = 0
    ultimo = None
    print()
    for d, corr in tabla.items():
        n = 0
        for lig, s in corr:
            f = os.path.join(res, d, f"{lig}_s{s}.pdbqt")
            if _completo(f):
                n += 1
                m = os.path.getmtime(f)
                if not ultimo or m > ultimo[0]:
                    ultimo = (m, f"{d}/{lig}_s{s}")
        total += len(corr); hechas += n
        barra = "█" * int(20 * n / max(1, len(corr))) + "░" * (20 - int(20 * n / max(1, len(corr))))
        print(f"   {d:24s} {ui.rosa(barra)} {n:4d}/{len(corr)}")
    pct = 100 * hechas / max(1, total)
    print(f"\n   {ui.negrita('Total')}: {hechas}/{total} corridas de docking ({pct:.0f}%)")
    if ultimo:
        print(f"   Última terminada: {ultimo[1]}  ({time.strftime('%H:%M:%S', time.localtime(ultimo[0]))})")
    if e and e["vivo"] and hechas and ultimo:
        try:
            t0 = time.mktime(time.strptime(e["inicio"], "%Y%m%d_%H%M%S"))
            hechas_ahora = sum(1 for d, corr in tabla.items() for lig, s in corr
                               if _completo(os.path.join(res, d, f"{lig}_s{s}.pdbqt"))
                               and os.path.getmtime(os.path.join(res, d, f"{lig}_s{s}.pdbqt")) >= t0)
            if hechas_ahora:
                seg = (time.time() - t0) / hechas_ahora * (total - hechas)
                print(f"   Tiempo restante estimado: ~{seg / 3600:.1f} h" if seg > 3600 else
                      f"   Tiempo restante estimado: ~{seg / 60:.0f} min")
        except ValueError:
            pass


def _ultimo_error(e):
    try:
        lineas = open(e["log"]).readlines()[-6:]
    except OSError:
        return
    if any("✘" in l or "Traceback" in l or "Error" in l for l in lineas):
        ui.aviso("El log termina con errores:")
        print(ui.gris("".join("     " + l for l in lineas)))


def ver_log(proy):
    e = estado(proy)
    if not e:
        logs = sorted(f for f in os.listdir(_logs(proy)) if f.startswith("pipeline_"))
        if not logs:
            ui.info("Aún no hay logs.")
            return
        log = os.path.join(_logs(proy), logs[-1])
    else:
        log = e["log"]
    ui.info(f"{os.path.relpath(log, proy)}   {ui.gris('(Ctrl+C para salir del log; el trabajo sigue)')}")
    # seguimiento propio (tail -f falla en carpetas de Windows /mnt/c con "No data available")
    try:
        with open(log, errors="replace") as fh:
            lineas = fh.readlines()
            sys.stdout.write("".join(lineas[-40:])); sys.stdout.flush()
            quieto = 0
            while True:
                nuevo = fh.read()
                if nuevo:
                    sys.stdout.write(nuevo); sys.stdout.flush(); quieto = 0
                else:
                    quieto += 1
                    if quieto >= 4 and not (estado(proy) or {}).get("vivo"):
                        print(); ui.info("El trabajo terminó.")
                        return
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print()


def avance_vivo(proy, cada=5):
    """Refresca la pantalla de avance hasta que termine el trabajo o se presione Ctrl+C."""
    try:
        while True:
            print("\033[2J\033[H", end="")
            mostrar_avance(proy)
            print(ui.gris(f"\n  Se actualiza cada {cada} s · Ctrl+C para salir (el trabajo sigue)"))
            e = estado(proy)
            if not e or not e.get("vivo"):
                return
            time.sleep(cada)
    except KeyboardInterrupt:
        print()
