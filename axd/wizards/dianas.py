"""Asistente de modo avanzado: añadir una diana (receptor) con control fino de cadenas,
cofactores y caja de docking."""
import os
import re
import shutil

from .. import config as C
from .. import ui
from ..infra import net
from ..infra.pdb import ADITIVOS
from ..layout import Layout
from .nuevo import _mostrar_estructura
from .util import id_unico


def bucle_dianas(ruta, p):
    while True:
        asistente_diana(ruta, p)
        if not ui.si_no("¿Añadir otra diana?", False):
            break


def asistente_diana(ruta, p):
    ui.titulo(f"Nueva diana #{len(p['dianas']) + 1}")
    fuente = ui.menu("¿De dónde viene la estructura?", [
        ("pdb", "PDB ID (se descarga de RCSB)"),
        ("alphafold", "AlphaFold DB (ID de UniProt)"),
        ("archivo", "Archivo local (.pdb / .cif, p. ej. modelo de AlphaFold2/ColabFold)"),
    ], defecto=1, salir="Cancelar")
    if not fuente:
        return
    crudos = Layout(ruta).receptors_raw_dir()
    d = {"fuente": fuente}
    if fuente == "pdb":
        pdb = ui.preguntar("PDB ID", obligatorio=True,
                           valida=lambda x: None if re.fullmatch(r"[0-9][A-Za-z0-9]{3}", x) else "Un PDB ID tiene 4 caracteres (p. ej. 1M17).").upper()
        nombre = ui.preguntar("Nombre corto de la diana (p. ej. EGFR)", obligatorio=True)
        d.update(pdb=pdb, nombre=nombre)
        base = os.path.join(crudos, f"{pdb}_{ui.nombre_seguro(nombre)}")
        try:
            arch = net.descargar_pdb(pdb, base)
            ui.ok(f"Descargado {os.path.basename(arch)}")
            d["archivo"] = os.path.relpath(arch, ruta)
        except Exception as e:
            ui.aviso(f"No se pudo descargar ahora ({e}); se intentará en el paso 'descargar'.")
            arch = None
    elif fuente == "alphafold":
        uni = ui.preguntar("ID de UniProt (p. ej. P00533)", obligatorio=True).upper()
        nombre = ui.preguntar("Nombre corto de la diana", obligatorio=True)
        d.update(uniprot=uni, nombre=nombre)
        arch = os.path.join(crudos, f"AF-{uni}_{ui.nombre_seguro(nombre)}.pdb")
        try:
            info = net.descargar_alphafold(uni, arch)
            ui.ok(f"Modelo AlphaFold descargado ({info.get('uniprotDescription', '')})")
            ui.info("Recuerda revisar pLDDT: recorta regiones desordenadas si van a estorbar la caja.")
            d["archivo"] = os.path.relpath(arch, ruta)
        except Exception as e:
            ui.aviso(f"No se pudo descargar ahora ({e}); se intentará en el paso 'descargar'.")
            arch = None
    else:
        src = ui.preguntar_ruta("Ruta del archivo del receptor", tipo="archivo")
        nombre = ui.preguntar("Nombre corto de la diana", os.path.splitext(os.path.basename(src))[0])
        ext = os.path.splitext(src)[1].lower() or ".pdb"
        arch = os.path.join(crudos, ui.nombre_seguro(nombre) + ext)
        if os.path.abspath(src) != os.path.abspath(arch):
            shutil.copy(src, arch)
        ui.ok(f"Copiado a 01_Receptors/{os.path.basename(arch)}")
        d.update(nombre=nombre, archivo=os.path.relpath(arch, ruta))

    cadenas, het = _mostrar_estructura(arch) if arch else ({}, [])
    defecto_cad = "".join(list(cadenas)[:1]) if cadenas else ""
    d["cadenas"] = ui.preguntar("Cadenas a conservar (p. ej. A o AB; vacío = todas)", defecto_cad).replace(",", "").replace(" ", "")
    cof = ui.preguntar("Cofactores/iones a conservar en el receptor, RES:CADENA separados por coma (p. ej. HEM:A,MG:A; vacío = ninguno)", "")
    d["cofactores"] = [x.strip().upper() for x in cof.split(",") if x.strip()]

    candidatos = [h for h in het if h[0] not in ADITIVOS and h[3] >= 6]
    ops = []
    if fuente != "alphafold":
        ops.append(("ligando", "Ligando co-cristalizado (centro en el ligando + margen) — permite redocking"))
    ops += [("residuos", "Residuos del sitio activo (p. ej. A:745,A:790,A:855)"),
            ("ciego", "Docking ciego (caja sobre toda la proteína)"),
            ("manual", "Coordenadas manuales (centro y tamaño)")]
    modo = ui.menu("¿Cómo definimos la caja de docking?", ops, defecto=1, salir=None)
    caja = {"modo": modo}
    if modo == "ligando":
        sug = f"{candidatos[0][0]}:{candidatos[0][1]}" if candidatos else None
        ref = ui.preguntar("Ligando de referencia RES:CADENA (p. ej. AQ4:A)", sug, obligatorio=True,
                           valida=lambda x: None if re.fullmatch(r"[A-Za-z0-9]{1,3}:[A-Za-z0-9]", x.strip()) else "Formato RES:CADENA").upper()
        caja.update(ref=ref, margen=ui.preguntar_float("Margen alrededor del ligando (Å)", 10.0),
                    minimo=ui.preguntar_float("Tamaño mínimo por eje (Å)", 22.0))
    elif modo == "residuos":
        caja.update(residuos=ui.preguntar("Residuos (CADENA:NÚM o NÚM, separados por coma)", obligatorio=True),
                    margen=ui.preguntar_float("Margen (Å)", 8.0), minimo=ui.preguntar_float("Tamaño mínimo por eje (Å)", 20.0))
    elif modo == "ciego":
        caja.update(margen=ui.preguntar_float("Margen alrededor de la proteína (Å)", 10.0))
        ui.info("Tip: en docking ciego sube exhaustiveness (≥ 64) en los parámetros.")
    else:
        c = ui.preguntar("Centro x y z (separado por espacios)", obligatorio=True,
                         valida=lambda x: None if len(x.replace(",", " ").split()) == 3 else "Necesito 3 números")
        s = ui.preguntar("Tamaño x y z en Å", "22 22 22",
                         valida=lambda x: None if len(x.replace(",", " ").split()) == 3 else "Necesito 3 números")
        caja.update(center=[float(v) for v in c.replace(",", " ").split()],
                    size=[float(v) for v in s.replace(",", " ").split()])
    d["caja"] = caja
    base_id = f"{d['pdb']}_{ui.nombre_seguro(d['nombre'])}" if d.get("pdb") else ui.nombre_seguro(d["nombre"])
    d["id"] = id_unico(base_id, {x["id"] for x in p["dianas"]})
    p["dianas"].append(d)
    C.guardar_proyecto(ruta, p)
    ui.ok(f"Diana '{d['id']}' añadida.")
