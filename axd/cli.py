"""Punto de entrada de `Docking`: menú interactivo y subcomandos."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from axd import config as C  # noqa: E402
from axd import entorno, proyecto, runner, ui  # noqa: E402

AYUDA = f"""
{ui.negrita('Docking')} — Axolotl Discovery  (v{C.VERSION})

Uso:  Docking                    abre el menú interactivo
      Docking nuevo              asistente para crear un proyecto
      Docking abrir   [carpeta]  ver/editar dianas, ligandos y parámetros
      Docking correr  [carpeta]  correr el pipeline (completo o por pasos)
      Docking avance  [carpeta]  ver cuántas corridas van  (Docking avance --vivo: se actualiza solo)
      Docking log     [carpeta]  ver el log en vivo
      Docking detener [carpeta]  detener el trabajo en segundo plano
      Docking reanudar[carpeta]  retomar donde se quedó (p. ej. tras un corte de luz)
      Docking entorno            verificar / instalar conda, smina y ADFRsuite
      Docking actualizar         bajar la última versión desde GitHub
      Docking version | ayuda

[carpeta] es opcional: si estás dentro de un proyecto se usa ese; si no, te pregunta.
"""


def elegir_proyecto(arg=None, preguntar=True):
    if arg:
        r = ui.a_ruta_linux(arg)
        if os.path.exists(os.path.join(r, C.ARCHIVO_PROYECTO)):
            C.registrar_reciente(r)
            return r
        ui.error(f"No hay un proyecto (axd.json) en {r}")
        return None
    aqui = C.buscar_proyecto()
    g = C.cargar_global()
    recientes = [x for x in g.get("recientes", []) if os.path.exists(os.path.join(x, C.ARCHIVO_PROYECTO))]
    if aqui and not preguntar:
        return aqui
    ops = []
    if aqui:
        ops.append((aqui, f"{os.path.basename(aqui)} {ui.gris('(carpeta actual)')}"))
    ops += [(r, f"{os.path.basename(r)} {ui.gris(os.path.dirname(r))}") for r in recientes if r != aqui]
    ops.append(("__otra__", "Otra carpeta…"))
    if len(ops) == 1:
        sel = "__otra__"
    else:
        sel = ui.menu("¿Qué proyecto?", ops, defecto=1)
        if sel is None:
            return None
    if sel == "__otra__":
        r = ui.preguntar_ruta("Carpeta del proyecto", tipo="carpeta")
        if not os.path.exists(os.path.join(r, C.ARCHIVO_PROYECTO)):
            ui.error("Esa carpeta no tiene axd.json. Crea el proyecto con 'Proyecto nuevo'.")
            return None
        sel = r
    C.registrar_reciente(sel)
    return sel


def menu_correr(proy):
    p = C.cargar_proyecto(proy)
    proyecto.resumen_proyecto(proy, p)
    if not p["dianas"]:
        ui.aviso("Primero añade al menos una diana (Editar proyecto).")
        return
    if not p["ligandos"] and not p["controles"]:
        ui.aviso("Primero añade ligandos (Editar proyecto).")
        return
    hay_ref = any(d.get("caja", {}).get("modo") in ("ligando", "auto") for d in p["dianas"])
    if p.get("modo") == "basico":
        # modo básico: todo el pipeline, en segundo plano, sin preguntas
        if not ui.si_no("¿Arranco el docking completo ahora? (corre en segundo plano)", True):
            return
        runner.ejecutar(proy, [x for x in runner.PASOS if x != "redocking" or hay_ref], fondo=True)
        return
    op = ui.menu("¿Qué corremos?", [
        ("todo", "Pipeline completo" + ui.gris(" (descargar → receptores → ligandos → "
                                                + ("redocking → " if hay_ref else "") + "docking → resumen)")),
        ("prep", "Sólo preparación" + ui.gris(" (descargar → receptores → ligandos" + (" → redocking)" if hay_ref else ")"))),
        ("pasos", "Elegir pasos uno por uno"),
    ], defecto=1)
    if op is None:
        return
    if op == "todo":
        pasos = [x for x in runner.PASOS if x != "redocking" or hay_ref]
    elif op == "prep":
        pasos = ["descargar", "receptores", "ligandos"] + (["redocking"] if hay_ref else [])
    else:
        pasos = []
        for x in runner.PASOS:
            if x == "redocking" and not hay_ref:
                continue
            if ui.si_no(f"{x:11s} — {runner.DESCRIPCION_PASOS[x]}", x != "redocking"):
                pasos.append(x)
    if not pasos:
        return
    extra = []
    if "docking" in pasos and any(
            os.path.exists(os.path.join(proy, "04_Docking", "Resultados", d["id"])) and
            os.listdir(os.path.join(proy, "04_Docking", "Resultados", d["id"])) for d in p["dianas"]):
        if ui.si_no("Hay resultados previos. ¿Rehacer TODO desde cero? (No = sólo lo que falta)", False):
            extra.append("--rehacer")
    largo = "docking" in pasos or "redocking" in pasos
    fondo = ui.si_no("¿Correr en segundo plano? (recomendado para docking)", largo)
    runner.ejecutar(proy, pasos, fondo=fondo, extra=extra)


def actualizar():
    if not os.path.isdir(os.path.join(C.APP, ".git")):
        ui.error("Esta instalación no es un clon de git; reinstala con el comando de una línea.")
        return
    r = subprocess.call(["git", "-C", C.APP, "pull", "--ff-only"])
    if r == 0:
        subprocess.call(["bash", "-c", f'chmod +x "{C.APP}/bin/"* "{C.APP}/scripts/"*.sh "{C.APP}"/*.sh 2>/dev/null'])
        ui.ok("Actualizado.")


def menu_principal():
    ui.banner(C.VERSION)
    g = C.cargar_global()
    if not C.ruta_conda(g) or g["entorno"] not in C.entornos_conda(C.ruta_conda(g)):
        ui.aviso("El entorno de docking no está instalado o no lo encuentro → opción 'Entorno'.")
    while True:
        op = ui.menu("Menú principal", [
            ("nuevo", "Proyecto nuevo"),
            ("abrir", "Abrir / editar proyecto"),
            ("correr", "Correr pipeline"),
            ("avance", "Ver avance"),
            ("log", "Ver log en vivo"),
            ("detener", "Detener trabajo"),
            ("reanudar", "Reanudar trabajo"),
            ("entorno", "Entorno: verificar / instalar / elegir"),
            ("actualizar", "Actualizar Docking"),
        ], salir="Salir")
        try:
            if op is None:
                print(ui.gris("  ¡Nos vemos! 🦎") if ui.COLOR else "")
                return
            despachar(op, None, interactivo=True)
        except ui.Cancelado:
            ui.info("Cancelado.")


def despachar(op, arg, interactivo=False):
    if op == "nuevo":
        ruta = proyecto.asistente_nuevo()
        if ruta:
            menu_correr(ruta)
    elif op == "abrir":
        r = elegir_proyecto(arg)
        r and proyecto.editar_proyecto(r)
    elif op == "correr":
        r = elegir_proyecto(arg)
        r and menu_correr(r)
    elif op == "avance":
        vivo = VIVO or (interactivo and ui.si_no("¿Verlo en vivo (se actualiza solo)?", True))
        r = elegir_proyecto(arg, preguntar=interactivo)
        if r and vivo:
            runner.avance_vivo(r)
        elif r:
            runner.mostrar_avance(r)
            interactivo and ui.pausa()
    elif op == "log":
        r = elegir_proyecto(arg, preguntar=interactivo)
        r and runner.ver_log(r)
    elif op == "detener":
        r = elegir_proyecto(arg, preguntar=interactivo)
        if r and runner.detener(r):
            runner.mostrar_avance(r)
    elif op == "reanudar":
        r = elegir_proyecto(arg, preguntar=interactivo)
        r and runner.reanudar(r)
    elif op == "entorno":
        sub = ui.menu("Entorno", [("ver", "Verificar"), ("instalar", "Instalar / reparar todo"),
                                  ("elegir", "Elegir otro entorno conda existente")], defecto=1)
        if sub == "ver":
            entorno.doctor()
        elif sub == "instalar":
            entorno.instalar()
        elif sub == "elegir":
            entorno.elegir_entorno()
    elif op == "actualizar":
        actualizar()
    else:
        print(AYUDA)


ALIAS = {"new": "nuevo", "crear": "nuevo", "editar": "abrir", "open": "abrir", "run": "correr", "pipeline": "correr",
         "status": "avance", "estado": "avance", "stop": "detener", "resume": "reanudar", "doctor": "entorno",
         "update": "actualizar", "logs": "log"}


VIVO = False


def main(argv=None):
    global VIVO
    argv = list(sys.argv[1:] if argv is None else argv)
    for f in ("--vivo", "-v", "vivo"):
        if f in argv[1:]:
            argv.remove(f); VIVO = True
    try:
        if not argv:
            return menu_principal()
        op = ALIAS.get(argv[0].lower(), argv[0].lower())
        arg = argv[1] if len(argv) > 1 else None
        if op in ("version", "--version", "-v"):
            print(C.VERSION)
        elif op in ("ayuda", "help", "-h", "--help"):
            print(AYUDA)
        elif op == "entorno" and arg in ("verificar", "check"):
            entorno.doctor()
        elif op == "entorno" and arg == "instalar":
            entorno.instalar(argv[2:])
        elif op in ("nuevo", "abrir", "correr", "avance", "log", "detener", "reanudar", "entorno", "actualizar"):
            despachar(op, arg)
        else:
            ui.error(f"No conozco el comando '{argv[0]}'.")
            print(AYUDA)
            return 1
    except ui.Cancelado:
        ui.info("Cancelado.")
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
