#!/usr/bin/env python3
"""Orquestador del pipeline. Lo lanza `Docking` dentro del entorno conda:
    python pipeline/run.py <carpeta_proyecto> [pasos...] [--rehacer]
Pasos: descargar receptores ligandos redocking docking resumen  (o 'todo')
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

import comun  # noqa: E402

ORDEN = ["descargar", "receptores", "ligandos", "redocking", "docking", "resumen"]


def main(argv):
    if not argv:
        print(__doc__); return 2
    proy, resto = argv[0], argv[1:]
    rehacer = "--rehacer" in resto
    pasos = [x for x in resto if not x.startswith("--")] or ["todo"]
    if "todo" in pasos:
        pasos = ORDEN
    pasos = [p for p in ORDEN if p in pasos]
    P = comun.Proyecto(proy)
    t0 = time.time()
    print(f"Axolotl Docking · {P.cfg['nombre']} · {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"Pasos: {' → '.join(pasos)}" + ("  (rehaciendo todo)" if rehacer else ""))
    import descargar, docking, ligandos, receptores, resumen  # noqa: E401
    funciones = {"descargar": descargar.ejecutar, "receptores": receptores.ejecutar, "ligandos": ligandos.ejecutar,
                 "redocking": docking.redocking, "docking": docking.matriz, "resumen": resumen.ejecutar}
    total_fallos = 0
    for paso in pasos:
        try:
            P.cfg = comun.cargar_proyecto(P.raiz)  # por si otro paso lo actualizó
            f = funciones[paso](P, rehacer=rehacer) or 0
        except KeyboardInterrupt:
            print("\n✘ Interrumpido."); return 130
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print(f"✘ El paso '{paso}' terminó con error.")
            f = 1
            if paso in ("receptores", "ligandos") and "docking" in pasos:
                print("  Sin este paso el docking no puede continuar. Revisa el error y usa 'Docking reanudar'.")
                return 1
        total_fallos += f
    m = (time.time() - t0) / 60
    print(f"\n{'✔' if total_fallos == 0 else '⚠'} Terminado en {m:.1f} min · {total_fallos} problema(s)."
          + ("" if total_fallos == 0 else " Revisa las líneas con ✘ arriba."))
    return 0 if total_fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
