"""Asistente de modo avanzado: añadir ligandos o controles positivos por varias vías
(PubChem, lista, carpeta, archivos sueltos, SMILES a mano)."""
import os
import re
import shutil

from .. import config as C
from .. import ui
from ..layout import Layout
from .new import _agregar_texto
from .util import EXT_LIGANDO, id_unico, parece_smiles, partir_sdf


def ligands_wizard(ruta, p, controles=False):
    clave = "controls" if controles else "ligands"
    carpeta = Layout(ruta).controls_dir() if controles else Layout(ruta).ligands_dir()
    etiqueta = "controles positivos" if controles else "ligandos"
    ids = {x["id"] for x in p["ligands"] + p["controls"]}
    nuevos = []

    def agregar(e):
        e["id"] = id_unico(ui.nombre_seguro(e["name"])[:40], ids)
        ids.add(e["id"]); nuevos.append(e)

    while True:
        modo = ui.menu(f"¿Cómo quieres añadir {etiqueta}?", [
            ("pubchem", "Escribir nombres, CID o SID (se descargan de PubChem)"),
            ("lista", "Archivo de lista .txt/.csv (un nombre por línea, o nombre,SMILES)"),
            ("carpeta", "Carpeta con estructuras (.sdf .mol .mol2 .pdb .smi)"),
            ("archivos", "Un archivo de estructura (SDF con una o varias moléculas, etc.)"),
            ("smiles", "Escribir SMILES a mano"),
        ], defecto=1, salir="Terminar")
        if not modo:
            break
        if modo == "pubchem":
            ui.info("Un compuesto por línea: nombre común, CID (5280343) o SID (SID 482105756). Vacío para terminar.")
            while True:
                n = ui.preguntar("Compuesto", "")
                if not n:
                    break
                _agregar_texto(n, agregar, carpeta, ruta)
        elif modo == "lista":
            f = ui.preguntar_ruta("Archivo de lista", tipo="archivo")
            for linea in open(f, encoding="utf-8-sig", errors="ignore"):
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                partes = [x.strip() for x in re.split(r"[,\t;|]", linea) if x.strip()]
                if partes[0].lower() in ("nombre", "name"):
                    continue
                if len(partes) >= 2 and parece_smiles(partes[1]):
                    agregar({"name": partes[0], "source": "smiles", "smiles": partes[1]})
                else:
                    agregar({"name": partes[0], "source": "pubchem", "query": partes[1] if len(partes) > 1 else partes[0]})
            ui.ok(f"{len(nuevos)} {etiqueta} leídos de la lista.")
        elif modo in ("carpeta", "archivos"):
            if modo == "carpeta":
                d = ui.preguntar_ruta("Carpeta con estructuras", tipo="carpeta")
                archivos = sorted(os.path.join(d, x) for x in os.listdir(d) if x.lower().endswith(EXT_LIGANDO))
            else:
                archivos = [ui.preguntar_ruta("Archivo de estructura", tipo="archivo")]
            for a in archivos:
                ext = os.path.splitext(a)[1].lower()
                if ext == ".sdf" and len(partir_sdf(a)) > 1:
                    for nom, bloque in partir_sdf(a):
                        e = {"name": nom, "source": "file"}
                        agregar(e)
                        destino = os.path.join(carpeta, e["id"] + ".sdf")
                        open(destino, "w").write(bloque)
                        e["file"] = os.path.relpath(destino, ruta)
                else:
                    e = {"name": os.path.splitext(os.path.basename(a))[0], "source": "file"}
                    agregar(e)
                    destino = os.path.join(carpeta, e["id"] + ext)
                    if os.path.abspath(a) != os.path.abspath(destino):
                        shutil.copy(a, destino)
                    e["file"] = os.path.relpath(destino, ruta)
            ui.ok(f"{len(archivos)} archivo(s) copiados a {os.path.relpath(carpeta, ruta)}/")
        elif modo == "smiles":
            ui.info("Línea vacía para terminar.")
            while True:
                n = ui.preguntar("Nombre", "")
                if not n:
                    break
                s = ui.preguntar("SMILES", obligatorio=True)
                agregar({"name": n, "source": "smiles", "smiles": s})

    if controles and nuevos and len(p["targets"]) > 1:
        ui.info("Puedes asignar cada control a su diana (si no, se dockea contra todas).")
        ops = [d["id"] for d in p["targets"]]
        for e in nuevos:
            print("     " + "  ".join(f"{ui.rosa(str(i))}) {x}" for i, x in enumerate(ops, 1)))
            r = ui.preguntar(f"Diana de '{e['name']}' (número; vacío = todas)", "",
                             valida=lambda x: None if x.isdigit() and 1 <= int(x) <= len(ops) else "Número de la lista")
            if r:
                e["target"] = ops[int(r) - 1]
    elif controles and nuevos and len(p["targets"]) == 1:
        for e in nuevos:
            e["target"] = p["targets"][0]["id"]
    p[clave].extend(nuevos)
    C.save_project(ruta, p)
    if nuevos:
        ui.ok(f"{len(nuevos)} {etiqueta} añadidos: " + ", ".join(e["id"] for e in nuevos))
