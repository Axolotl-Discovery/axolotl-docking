"""Resumen y menú de edición de un proyecto ya creado."""
import shutil

from .. import config as C
from .. import runner
from .. import ui
from . import dianas as _dianas
from . import ligandos as _ligandos
from . import nuevo as _nuevo
from . import parametros as _parametros


def resumen_proyecto(ruta, p):
    ui.titulo(f"{p['nombre']}  ·  modo {'básico' if p.get('modo') == 'basico' else 'avanzado'}")
    print(f"   {ui.gris('Ruta:')} {ruta}")
    print(f"   {ui.negrita('Dianas')} ({len(p['dianas'])}):")
    for d in p["dianas"]:
        c = d.get("caja", {})
        det = {"ligando": f"ref {c.get('ref')}", "residuos": f"residuos {c.get('residuos')}",
               "ciego": "ciego", "manual": f"centro {c.get('center')}",
               "auto": "automática"}.get(c.get("modo"), "?")
        print(f"     · {d['id']:22s} cadenas {d.get('cadenas') or 'todas':6s} caja: {det}")
    for clave, et in (("ligandos", "Ligandos"), ("controles", "Controles")):
        xs = p[clave]
        print(f"   {ui.negrita(et)} ({len(xs)}): " + (", ".join(
            x["id"] + (ui.gris(f"→{x['diana']}") if x.get("diana") else "") for x in xs[:15]) + (" …" if len(xs) > 15 else "")))
    d = p["docking"]
    nt = sum(len(v) for v in runner.corridas_esperadas(p).values())
    if d.get("motor") == "ad4":
        print(f"   {ui.negrita('Docking')}: AutoDock4 (átomos no comunes) · {len(d['semillas'])} semillas × "
              f"{d.get('ad4_runs', 20)} corridas GA  →  {nt} corridas")
    else:
        print(f"   {ui.negrita('Docking')}: {len(d['semillas'])} semillas · exh {d['exhaustiveness']} · "
              f"{d['num_modes']} poses · cpu {d['cpu'] or 'todos'}  →  {nt} corridas")


def editar_proyecto(ruta):
    while True:
        p = C.cargar_proyecto(ruta)
        resumen_proyecto(ruta, p)
        basico = p.get("modo") == "basico"
        op = ui.menu("Editar proyecto", [
            ("diana", "Añadir diana"),
            ("lig", "Añadir ligandos"),
            ("ctrl", "Añadir controles positivos"),
            ("quitar", "Quitar una diana / ligando / control"),
            ("param", "Parámetros de docking"),
            ("modo", f"Cambiar a modo {'avanzado' if basico else 'básico'}"),
            ("raros", "Átomos no comunes / motor: " + ("AutoDock4" if p["docking"].get("motor") == "ad4" else "smina")),
            ("abrir", "Abrir la carpeta en el Explorador de Windows"),
        ])
        if op is None:
            return
        if op == "diana":
            _nuevo.dianas_basico(ruta, p) if basico else _dianas.asistente_diana(ruta, p)
        elif op == "lig":
            _nuevo.ligandos_basico(ruta, p, False) if basico else _ligandos.asistente_ligandos(ruta, p, False)
        elif op == "ctrl":
            _nuevo.ligandos_basico(ruta, p, True) if basico else _ligandos.asistente_ligandos(ruta, p, True)
        elif op == "raros":
            if p["docking"].get("motor") == "ad4":
                if ui.si_no("¿Volver a smina? (sólo si ya no hay ligandos con metales)", False):
                    p["docking"]["motor"] = "smina"; C.guardar_proyecto(ruta, p)
            else:
                _nuevo.pregunta_atomos_raros(ruta, p, avanzado=not basico)
        elif op == "modo":
            p["modo"] = "avanzado" if basico else "basico"
            C.guardar_proyecto(ruta, p)
            ui.ok(f"Modo {p['modo']}.")
        elif op == "param":
            _parametros.asistente_parametros(ruta, p)
        elif op == "abrir":
            abrir_explorador(ruta)
        elif op == "quitar":
            items = [("dianas", x["id"]) for x in p["dianas"]] + [("ligandos", x["id"]) for x in p["ligandos"]] + \
                    [("controles", x["id"]) for x in p["controles"]]
            if not items:
                continue
            k = ui.menu("¿Qué quitar? (los archivos no se borran)", [(i, f"{t[:-1]}: {n}") for i, (t, n) in enumerate(items)])
            if k is not None:
                t, n = items[k]
                p[t] = [x for x in p[t] if x["id"] != n]
                C.guardar_proyecto(ruta, p)
                ui.ok(f"Quitado {n}.")


def abrir_explorador(ruta):
    import subprocess
    if shutil.which("explorer.exe"):
        try:
            win = subprocess.check_output(["wslpath", "-w", ruta], text=True).strip()
            subprocess.Popen(["explorer.exe", win], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ui.ok("Abierto en el Explorador.")
            return
        except Exception:
            pass
    ui.info(f"Carpeta: {ruta}")
