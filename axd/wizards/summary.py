"""Resumen y menú de edición de un proyecto ya creado."""
import shutil

from .. import config as C
from .. import runner
from .. import ui
from . import targets as _targets
from . import ligands as _ligands
from . import new as _new
from . import params as _params


def resumen_proyecto(ruta, p):
    ui.titulo(f"{p['name']}  ·  modo {'básico' if p.get('mode') == 'basic' else 'avanzado'}")
    print(f"   {ui.gris('Ruta:')} {ruta}")
    print(f"   {ui.negrita('Dianas')} ({len(p['targets'])}):")
    for d in p["targets"]:
        c = d.get("box", {})
        det = {"ligand": f"ref {c.get('ref')}", "residues": f"residuos {c.get('residues')}",
               "blind": "ciego", "manual": f"centro {c.get('center')}",
               "auto": "automática"}.get(c.get("mode"), "?")
        print(f"     · {d['id']:22s} cadenas {d.get('chains') or 'todas':6s} caja: {det}")
    for clave, et in (("ligands", "Ligandos"), ("controls", "Controles")):
        xs = p[clave]
        print(f"   {ui.negrita(et)} ({len(xs)}): " + (", ".join(
            x["id"] + (ui.gris(f"→{x['target']}") if x.get("target") else "") for x in xs[:15]) + (" …" if len(xs) > 15 else "")))
    d = p["docking"]
    nt = sum(len(v) for v in runner.corridas_esperadas(p).values())
    if d.get("engine") == "ad4":
        print(f"   {ui.negrita('Docking')}: AutoDock4 (átomos no comunes) · {len(d['seeds'])} semillas × "
              f"{d.get('ad4_runs', 20)} corridas GA  →  {nt} corridas")
    else:
        print(f"   {ui.negrita('Docking')}: {len(d['seeds'])} semillas · exh {d['exhaustiveness']} · "
              f"{d['num_modes']} poses · cpu {d['cpu'] or 'todos'}  →  {nt} corridas")


def editar_proyecto(ruta):
    while True:
        p = C.load_project(ruta)
        resumen_proyecto(ruta, p)
        basico = p.get("mode") == "basic"
        op = ui.menu("Editar proyecto", [
            ("diana", "Añadir diana"),
            ("lig", "Añadir ligandos"),
            ("ctrl", "Añadir controles positivos"),
            ("quitar", "Quitar una diana / ligando / control"),
            ("param", "Parámetros de docking"),
            ("modo", f"Cambiar a modo {'avanzado' if basico else 'básico'}"),
            ("raros", "Átomos no comunes / motor: " + ("AutoDock4" if p["docking"].get("engine") == "ad4" else "smina")),
            ("abrir", "Abrir la carpeta en el Explorador de Windows"),
        ])
        if op is None:
            return
        if op == "diana":
            _new.dianas_basico(ruta, p) if basico else _targets.target_wizard(ruta, p)
        elif op == "lig":
            _new.ligandos_basico(ruta, p, False) if basico else _ligands.ligands_wizard(ruta, p, False)
        elif op == "ctrl":
            _new.ligandos_basico(ruta, p, True) if basico else _ligands.ligands_wizard(ruta, p, True)
        elif op == "raros":
            if p["docking"].get("engine") == "ad4":
                if ui.si_no("¿Volver a smina? (sólo si ya no hay ligandos con metales)", False):
                    p["docking"]["engine"] = "smina"; C.save_project(ruta, p)
            else:
                _new.pregunta_atomos_raros(ruta, p, avanzado=not basico)
        elif op == "modo":
            p["mode"] = "advanced" if basico else "basic"
            C.save_project(ruta, p)
            ui.ok(f"Modo {p['mode']}.")
        elif op == "param":
            _params.params_wizard(ruta, p)
        elif op == "abrir":
            abrir_explorador(ruta)
        elif op == "quitar":
            items = [("targets", x["id"]) for x in p["targets"]] + [("ligands", x["id"]) for x in p["ligands"]] + \
                    [("controls", x["id"]) for x in p["controls"]]
            if not items:
                continue
            k = ui.menu("¿Qué quitar? (los archivos no se borran)", [(i, f"{t[:-1]}: {n}") for i, (t, n) in enumerate(items)])
            if k is not None:
                t, n = items[k]
                p[t] = [x for x in p[t] if x["id"] != n]
                C.save_project(ruta, p)
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
