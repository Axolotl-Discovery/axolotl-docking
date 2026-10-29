#!/usr/bin/env python3
"""Orquestador del pipeline. Lo lanza `Docking` dentro del entorno conda:
    python pipeline/run.py <carpeta_proyecto> [pasos...] [--rehacer]
Pasos: download receptors ligands redocking docking consensus summary interactions report  (o 'todo')
'consensus' sólo corre si el modo consenso está activado en el proyecto.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

import common  # noqa: E402
import consensus_step  # noqa: E402
from steps_state import StepTracker  # noqa: E402

ORDER = ["download", "receptors", "ligands", "redocking", "docking", "consensus", "summary", "interactions", "report"]


def main(argv):
    if not argv:
        print(__doc__); return 2
    proy, resto = argv[0], argv[1:]
    rehacer = "--rehacer" in resto
    pasos = [x for x in resto if not x.startswith("--")] or ["todo"]
    todo = "todo" in pasos
    if todo:
        pasos = ORDER
    pasos = [p for p in ORDER if p in pasos]
    P = common.Project(proy)
    if todo and not consensus_step.configuracion(P)[0]:  # opt-in: sin activarlo, ni aparece en la lista
        pasos = [p for p in pasos if p != "consensus"]
    t0 = time.time()
    print(f"Axolotl Docking · {P.cfg['name']} · {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"Pasos: {' → '.join(pasos)}" + ("  (rehaciendo todo)" if rehacer else ""))
    import download, docking, interactions, ligands, receptors, report, summary  # noqa: E401
    functions = {"download": download.run, "receptors": receptors.run, "ligands": ligands.run,
                 "redocking": docking.redocking, "docking": docking.matrix,
                 "consensus": consensus_step.run, "summary": summary.run, "interactions": interactions.run, "report": report.run}
    from axd.runner import DESCRIPCION_PASOS
    tracker = StepTracker(P.layout.steps_state_file(), pasos, DESCRIPCION_PASOS, log=os.environ.get("AXD_LOG"))
    total_fallos = 0
    try:
        for paso in pasos:
            tracker.iniciar(paso)
            excepcion = False
            try:
                P.cfg = common.load_project(P.root)  # por si otro paso lo actualizó
                f = functions[paso](P, rehacer=rehacer) or 0
            except KeyboardInterrupt:
                print("\n✘ Interrumpido.")
                tracker.terminar(paso, 1, excepcion=True)
                return 130
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stdout)  # a stdout: así el tracker lo guarda y la GUI lo muestra
                print(f"✘ El paso '{paso}' terminó con error.")
                f, excepcion = 1, True
            tracker.terminar(paso, f, excepcion)
            if excepcion and paso in ("receptors", "ligands") and "docking" in pasos:
                print("  Sin este paso el docking no puede continuar. Revisa el error y usa 'Docking reanudar'.")
                return 1
            total_fallos += f
    finally:
        tracker.cerrar()
    m = (time.time() - t0) / 60
    print(f"\n{'✔' if total_fallos == 0 else '⚠'} Terminado en {m:.1f} min · {total_fallos} problema(s)."
          + ("" if total_fallos == 0 else " Revisa las líneas con ✘ arriba."))
    return 0 if total_fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
