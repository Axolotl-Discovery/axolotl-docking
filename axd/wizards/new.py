"""Asistente de modo básico: crear proyecto, dianas y ligandos simplificados."""
import datetime as _dt
import os
import re
import shutil

from .. import config as C
from .. import ui
from ..infra import net
from ..infra.pdb import ADDITIVES, UNIPROT_RE, auto_decision, inspect_pdb
from ..layout import Layout
from .util import EXT_LIGANDO, id_unico, parece_smiles, partir_sdf

NOMBRES_CCD = {"VO4": "ortovanadato", "DVT": "decavanadato"}


def _mostrar_estructura(ruta):
    cadenas, het = inspect_pdb(ruta)
    if not cadenas and not het:
        ui.info("(formato mmCIF: no lo inspecciono aquí; escribe cadenas y ligando a mano)")
        return cadenas, het
    print("     Cadenas: " + ", ".join(f"{c} ({n} res)" for c, n in cadenas.items()))
    if het:
        print("     Heteroátomos (sin aguas):")
        for rn, ch, num, n in het[:25]:
            marca = ui.gris(" (aditivo/ion)") if rn in ADDITIVES else ""
            print(f"       {rn:>4s}  cadena {ch}  res {num:>5s}  {n:3d} átomos{marca}")
        if len(het) > 25:
            print(f"       … y {len(het) - 25} más")
    else:
        print("     Sin ligandos co-cristalizados.")
    return cadenas, het


# ---------------------------------------------------------------- crear proyecto
def asistente_nuevo():
    g = C.load_global()
    ui.titulo("Proyecto nuevo")
    modo = ui.menu("¿Qué modo prefieres?", [
        ("basic", "Básico  — tú das proteína y ligandos, todo lo demás es automático"),
        ("advanced", "Avanzado — eliges cadenas, cofactores, caja, semillas, exhaustiveness…"),
    ], defecto=1, salir="Cancelar")
    if not modo:
        return None
    ui.info("Puedes pegar rutas de Windows (C:\\Users\\...) o arrastrar la carpeta a la terminal.")
    base_def = g.get("carpeta_proyectos") or os.getcwd()
    base = ui.preguntar_ruta("Carpeta donde se creará el proyecto", base_def, tipo="carpeta")
    nombre = ui.preguntar("Nombre del proyecto", f"docking_{_dt.date.today().strftime('%Y%m%d')}", obligatorio=True)
    ruta = os.path.join(base, ui.nombre_seguro(nombre))
    if os.path.exists(os.path.join(ruta, C.PROJECT_FILE)):
        ui.aviso("Ya existe un proyecto con ese nombre ahí; lo abro en lugar de crearlo.")
        return ruta
    C.new_project(ruta, nombre.strip(), modo)
    g["carpeta_proyectos"] = base
    C.save_global(g)
    C.register_recent(ruta)
    ui.ok(f"Proyecto creado en {ruta}")
    p = C.load_project(ruta)

    pregunta_atomos_raros(ruta, p, avanzado=(modo == "advanced"))
    if modo == "basic":
        dianas_basico(ruta, p)
        ligandos_basico(ruta, p, controles=False)
        if ui.si_no("¿Quieres agregar un control positivo (un fármaco conocido para comparar)?", False):
            ligandos_basico(ruta, p, controles=True)
    else:
        from . import targets as _targets, ligands as _ligands, params as _params
        if ui.si_no("¿Añadir las dianas (receptores) ahora?", True):
            _targets.target_loop(ruta, p)
        if ui.si_no("¿Añadir los ligandos ahora?", True):
            _ligands.ligands_wizard(ruta, p, controles=False)
        if ui.si_no("¿Añadir controles positivos?", True):
            _ligands.ligands_wizard(ruta, p, controles=True)
        if ui.si_no("¿Ajustar parámetros de docking? (por defecto: 3 semillas, exhaustiveness 32)", False):
            _params.params_wizard(ruta, p)
    return ruta


def pregunta_atomos_raros(ruta, p, avanzado=False):
    """Sección para ligandos con metales u otros átomos que smina/Vina no conocen."""
    if not ui.si_no("¿Vas a trabajar con átomos poco comunes en los ligandos (vanadio, platino, rutenio, cobre…)?",
                    False):
        return
    ui.titulo("Átomos no comunes")
    ui.info("smina/Vina no tienen parámetros para esos átomos, así que el proyecto se dockeará con AutoDock4:")
    ui.info("  · parámetros del metal derivados del Universal Force Field (UFF), escritos y documentados")
    ui.info("    en 05_Analysis/metal_parameters.txt para tu sección de métodos;")
    ui.info("  · cargas parciales EEM conservando la carga total; clusters (oxovanadatos) como cuerpo rígido;")
    ui.info("  · TODO el proyecto (incluidos controles) usa AutoDock4 para que las energías sean comparables.")
    ui.aviso("Son parámetros genéricos: compara energías entre sí y valida con dinámica molecular.")
    ui.info("Los ligandos metálicos necesitan estructura 3D. Puedes escribirlos como componente del PDB:")
    ui.info("  PDB:VO4 = ortovanadato · PDB:DVT = decavanadato · o la ruta a un .sdf/.mol2 3D (p. ej. tetravanadato)")
    p["docking"]["engine"] = "ad4"
    if avanzado:
        p["docking"]["ad4_runs"] = ui.preguntar_int("Corridas de algoritmo genético por semilla", p["docking"].get("ad4_runs", 20), 1, 500)
        p["docking"]["ad4_evals"] = ui.preguntar_int("Evaluaciones de energía por corrida (2.5 M estándar, 25 M exhaustivo)",
                                                     p["docking"].get("ad4_evals", 2500000), 10000, 100000000)
    C.save_project(ruta, p)
    ui.ok("Proyecto configurado para AutoDock4 con átomos no comunes.")


def dianas_basico(ruta, p):
    ui.titulo("Proteínas (dianas)")
    ui.info("Escribe un PDB ID (p. ej. 1M17), un ID de UniProt (se baja de AlphaFold) o la ruta a un .pdb/.cif.")
    ui.info("Una por línea; Enter vacío para terminar.")
    crudos = Layout(ruta).receptors_raw_dir()
    while True:
        ui._modo_rutas(True)
        try:
            t = ui.preguntar(f"Proteína #{len(p['targets']) + 1}", "" if p["targets"] else None,
                             obligatorio=not p["targets"])
        finally:
            ui._modo_rutas(False)
        if not t:
            break
        d = {"chains": "auto", "cofactors": "auto", "box": {"mode": "auto"}}
        ruta_local = ui.a_ruta_linux(t)
        arch = None
        if os.path.isfile(ruta_local):
            nombre = os.path.splitext(os.path.basename(ruta_local))[0]
            ext = os.path.splitext(ruta_local)[1].lower() or ".pdb"
            arch = os.path.join(crudos, ui.nombre_seguro(nombre) + ext)
            if os.path.abspath(ruta_local) != os.path.abspath(arch):
                shutil.copy(ruta_local, arch)
            d.update(source="file", name=nombre, file=os.path.relpath(arch, ruta))
            ui.ok(f"Archivo copiado: 01_Receptors/{os.path.basename(arch)}")
        elif re.fullmatch(r"[0-9][A-Za-z0-9]{3}", t.strip()):
            pdb = t.strip().upper()
            d.update(source="pdb", pdb=pdb, name=pdb)
            try:
                arch = net.download_pdb(pdb, os.path.join(crudos, pdb))
                d["file"] = os.path.relpath(arch, ruta)
                ui.ok(f"{pdb} descargado de RCSB")
            except Exception:
                ui.aviso(f"No pude descargar {pdb} ahora; se intentará al correr el pipeline.")
        elif re.fullmatch(UNIPROT_RE, t.strip().upper()):
            uni = t.strip().upper()
            d.update(source="alphafold", uniprot=uni, name=f"AF-{uni}")
            try:
                arch = os.path.join(crudos, f"AF-{uni}.pdb")
                info = net.download_alphafold(uni, arch)
                d["file"] = os.path.relpath(arch, ruta)
                ui.ok(f"Modelo AlphaFold de {uni} descargado ({info.get('uniprotDescription', '')})")
            except Exception:
                ui.aviso(f"No pude descargar {uni} de AlphaFold ahora; se intentará al correr el pipeline.")
                arch = None
        else:
            ui.aviso("No reconozco eso como PDB ID, UniProt ni archivo existente.")
            continue
        if arch and os.path.exists(arch):
            cadenas, het = inspect_pdb(arch)
            ref, cad = auto_decision(het, cadenas)
            if ref:
                ui.info(f"Sitio de unión: ligando co-cristalizado {ref} → caja ahí y validación por redocking")
            elif cadenas:
                ui.info(f"Sin ligando co-cristalizado → docking ciego sobre la cadena {cad}")
        base_id = ui.nombre_seguro(d["name"])
        d["id"] = id_unico(base_id, {x["id"] for x in p["targets"]})
        p["targets"].append(d)
        C.save_project(ruta, p)


def _agregar_texto(t, agregar, carpeta, ruta, resolver=True):
    """Interpreta una línea: ruta a archivo/carpeta, SID/CID, SMILES o nombre."""
    ruta_local = ui.a_ruta_linux(t)
    if os.path.isdir(ruta_local) or (os.path.isfile(ruta_local) and ruta_local.lower().endswith(EXT_LIGANDO)):
        return _importar_rutas(ruta_local, agregar, carpeta, ruta)
    m = re.fullmatch(r"(?i)(pdb|ccd)\s*[:_-]?\s*([A-Za-z0-9]{1,5})", t.strip())
    if m:  # componente químico del PDB (coordenadas 3D, sirve para metales y clusters)
        codigo = m.group(2).upper()
        agregar({"name": NOMBRES_CCD.get(codigo, codigo), "source": "ccd", "code": codigo})
        ui.ok(f"Componente PDB {codigo}" + (f" ({NOMBRES_CCD[codigo]})" if codigo in NOMBRES_CCD else ""))
        return 1
    partes = t.split()
    if len(partes) == 2 and len(partes[1]) >= 4 and parece_smiles(partes[1]) and not partes[1].isdigit():  # "Aspirina CC(=O)Oc1..."
        agregar({"name": partes[0], "source": "smiles", "smiles": partes[1]})
        ui.ok(f"{partes[0]} (SMILES)")
        return 1
    if parece_smiles(t) and net.parse_pubchem(t)[0] == "nombre":
        agregar({"name": "smiles_1", "source": "smiles", "smiles": t})
        ui.ok("SMILES añadido (tip: escribe 'Nombre SMILES' para ponerle nombre)")
        return 1
    tipo, v = net.parse_pubchem(t)
    cid, titulo = net.resolve_pubchem(t) if resolver else (None, None)
    if cid:
        if tipo == "nombre":
            nombre = t
        elif titulo and len(titulo) <= 30 and ";" not in titulo:
            nombre = titulo
        else:  # títulos de PubChem muy largos (sales, mezclas): mejor el número
            nombre = f"CID_{cid}"
        ui.ok(f"{t} → {titulo or 'CID ' + cid} (CID {cid})")
    else:
        nombre = t if tipo == "nombre" else f"{tipo.upper()}_{v}"
        ui.aviso(f"No lo pude verificar en PubChem ahora ('{t}'); lo intentaré al descargar.")
    agregar({"name": nombre, "source": "pubchem", "query": t, "cid": cid})
    return 1


def _importar_rutas(ruta_local, agregar, carpeta, ruta):
    if os.path.isdir(ruta_local):
        archivos = sorted(os.path.join(ruta_local, x) for x in os.listdir(ruta_local) if x.lower().endswith(EXT_LIGANDO))
    else:
        archivos = [ruta_local]
    n = 0
    for a in archivos:
        ext = os.path.splitext(a)[1].lower()
        if ext == ".sdf" and len(partir_sdf(a)) > 1:
            for nom, bloque in partir_sdf(a):
                e = {"name": nom, "source": "file"}
                agregar(e)
                destino = os.path.join(carpeta, e["id"] + ".sdf")
                open(destino, "w").write(bloque)
                e["file"] = os.path.relpath(destino, ruta); n += 1
        else:
            e = {"name": os.path.splitext(os.path.basename(a))[0], "source": "file"}
            agregar(e)
            destino = os.path.join(carpeta, e["id"] + ext)
            if os.path.abspath(a) != os.path.abspath(destino):
                shutil.copy(a, destino)
            e["file"] = os.path.relpath(destino, ruta); n += 1
    ui.ok(f"{n} molécula(s) importadas de {os.path.basename(ruta_local.rstrip('/'))}")
    return n


def ligandos_basico(ruta, p, controles=False):
    clave = "controls" if controles else "ligands"
    carpeta = Layout(ruta).controls_dir() if controles else Layout(ruta).ligands_dir()
    ui.titulo("Controles positivos" if controles else "Ligandos")
    ui.info("Escribe uno por línea: nombre (quercetin), CID (5280343), SID (SID 482105756), 'Nombre SMILES',")
    ui.info("o la ruta a un archivo/carpeta con estructuras. Enter vacío para terminar.")
    ids = {x["id"] for x in p["ligands"] + p["controls"]}
    nuevos = []

    def agregar(e):
        e["id"] = id_unico(ui.nombre_seguro(e["name"])[:40], ids)
        ids.add(e["id"]); nuevos.append(e)

    while True:
        ui._modo_rutas(True)
        try:
            obligatorio = not controles and not p["ligands"] and not nuevos
            t = ui.preguntar(f"{'Control' if controles else 'Ligando'} #{len(p[clave]) + len(nuevos) + 1}",
                             None if obligatorio else "", obligatorio=obligatorio)
        finally:
            ui._modo_rutas(False)
        if not t:
            break
        _agregar_texto(t, agregar, carpeta, ruta)
    p[clave].extend(nuevos)
    C.save_project(ruta, p)
