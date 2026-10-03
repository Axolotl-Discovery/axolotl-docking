"""Asistentes interactivos: crear proyecto, añadir dianas, ligandos, controles y parámetros."""
import datetime as _dt
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
from collections import OrderedDict

from . import config as C
from . import runner
from . import ui

EXT_LIGANDO = (".sdf", ".mol", ".mol2", ".pdb", ".smi", ".smiles", ".pdbqt")
AGUAS = {"HOH", "WAT", "DOD", "H2O"}
ADITIVOS = {"SO4", "PO4", "GOL", "EDO", "PEG", "PG4", "ACT", "CL", "NA", "K", "DMS", "FMT", "MPD", "BME",
            "TRS", "EPE", "IOD", "NO3", "IMD", "CIT", "MES", "ACY", "1PE", "P6G", "BR"}


# ---------------------------------------------------------------- red
def descargar(url, destino, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "axolotl-docking"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        datos = r.read()
    if not datos:
        raise IOError("respuesta vacía")
    with open(destino, "wb") as f:
        f.write(datos)
    return destino


def descargar_pdb(pdb, destino_sin_ext):
    for ext in ("pdb", "cif"):
        try:
            return descargar(f"https://files.rcsb.org/download/{pdb}.{ext}", f"{destino_sin_ext}.{ext}")
        except Exception:
            continue
    raise IOError(f"No pude descargar {pdb} de RCSB")


def descargar_alphafold(uniprot, destino):
    with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot}", timeout=60) as r:
        info = json.load(r)[0]
    descargar(info["pdbUrl"], destino)
    return info


def pubchem_cid(consulta):
    q = urllib.parse.quote(consulta)
    try:
        with urllib.request.urlopen(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{q}/cids/TXT",
                                    timeout=20) as r:
            return r.read().decode().split()[0]
    except Exception:
        return None


# ---------------------------------------------------------------- inspección de PDB
def inspeccionar_pdb(ruta):
    """Devuelve (cadenas{cadena: n_residuos}, heteros[(resname, cadena, resseq, n_atomos)])."""
    cadenas, het = OrderedDict(), OrderedDict()
    if not ruta.lower().endswith(".pdb"):
        return cadenas, []
    vistos = set()
    for l in open(ruta, errors="ignore"):
        if l.startswith("ENDMDL"):
            break
        if l[:6] == "ATOM  ":
            k = (l[21], l[22:27])
            if k not in vistos:
                vistos.add(k); cadenas[l[21]] = cadenas.get(l[21], 0) + 1
        elif l[:6] == "HETATM":
            rn = l[17:20].strip()
            if rn in AGUAS:
                continue
            k = (rn, l[21], l[22:26].strip())
            het[k] = het.get(k, 0) + 1
    return cadenas, [(k[0], k[1], k[2], n) for k, n in het.items()]


def _mostrar_estructura(ruta):
    cadenas, het = inspeccionar_pdb(ruta)
    if not cadenas and not het:
        ui.info("(formato mmCIF: no lo inspecciono aquí; escribe cadenas y ligando a mano)")
        return cadenas, het
    print("     Cadenas: " + ", ".join(f"{c} ({n} res)" for c, n in cadenas.items()))
    if het:
        print("     Heteroátomos (sin aguas):")
        for rn, ch, num, n in het[:25]:
            marca = ui.gris(" (aditivo/ion)") if rn in ADITIVOS else ""
            print(f"       {rn:>4s}  cadena {ch}  res {num:>5s}  {n:3d} átomos{marca}")
        if len(het) > 25:
            print(f"       … y {len(het) - 25} más")
    else:
        print("     Sin ligandos co-cristalizados.")
    return cadenas, het


def _id_unico(base, existentes):
    i, x = 2, base
    while x in existentes:
        x = f"{base}_{i}"; i += 1
    return x


# ---------------------------------------------------------------- crear proyecto
def asistente_nuevo():
    g = C.cargar_global()
    ui.titulo("Proyecto nuevo")
    ui.info("Puedes pegar rutas de Windows (C:\\Users\\...) o arrastrar la carpeta a la terminal.")
    base_def = g.get("carpeta_proyectos") or os.getcwd()
    base = ui.preguntar_ruta("Carpeta donde se creará el proyecto", base_def, tipo="carpeta")
    yy = _dt.date.today().strftime("%y")
    codigo = ui.preguntar("Código del proyecto", f"AXD-XXX-{yy}-01", obligatorio=True, editable=True)
    cliente = ui.preguntar("Cliente (opcional)", "")
    desc = ui.preguntar("Descripción corta (opcional)", "")
    ruta = os.path.join(base, ui.nombre_seguro(codigo))
    if cliente and os.path.basename(base.rstrip("/")) != cliente.strip():
        if ui.si_no(f"¿Crear dentro de una subcarpeta del cliente ('{cliente.strip()}')?", False):
            ruta = os.path.join(base, cliente.strip(), ui.nombre_seguro(codigo))
    if os.path.exists(os.path.join(ruta, C.ARCHIVO_PROYECTO)):
        ui.aviso("Ya existe un proyecto ahí; lo abro en lugar de crearlo.")
        return ruta
    C.nuevo_proyecto(ruta, codigo.strip(), cliente.strip(), desc.strip())
    g["carpeta_proyectos"] = base
    C.guardar_global(g)
    C.registrar_reciente(ruta)
    ui.ok(f"Proyecto creado en {ruta}")

    p = C.cargar_proyecto(ruta)
    if ui.si_no("¿Añadir las dianas (receptores) ahora?", True):
        bucle_dianas(ruta, p)
    if ui.si_no("¿Añadir los ligandos ahora?", True):
        asistente_ligandos(ruta, p, controles=False)
    if ui.si_no("¿Añadir controles positivos?", True):
        asistente_ligandos(ruta, p, controles=True)
    if ui.si_no("¿Ajustar parámetros de docking? (por defecto: 3 semillas, exhaustiveness 32)", False):
        asistente_parametros(ruta, p)
    resumen_proyecto(ruta, p)
    return ruta


# ---------------------------------------------------------------- dianas
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
    crudos = os.path.join(ruta, "01_Receptores")
    d = {"fuente": fuente}
    if fuente == "pdb":
        pdb = ui.preguntar("PDB ID", obligatorio=True,
                           valida=lambda x: None if re.fullmatch(r"[0-9][A-Za-z0-9]{3}", x) else "Un PDB ID tiene 4 caracteres (p. ej. 1M17).").upper()
        nombre = ui.preguntar("Nombre corto de la diana (p. ej. EGFR)", obligatorio=True)
        d.update(pdb=pdb, nombre=nombre)
        base = os.path.join(crudos, f"{pdb}_{ui.nombre_seguro(nombre)}")
        try:
            arch = descargar_pdb(pdb, base)
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
            info = descargar_alphafold(uni, arch)
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
        ui.ok(f"Copiado a 01_Receptores/{os.path.basename(arch)}")
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
    d["id"] = _id_unico(base_id, {x["id"] for x in p["dianas"]})
    p["dianas"].append(d)
    C.guardar_proyecto(ruta, p)
    ui.ok(f"Diana '{d['id']}' añadida.")


# ---------------------------------------------------------------- ligandos
def _partir_sdf(ruta):
    """Separa un SDF de varias moléculas: [(nombre, bloque)]."""
    txt = open(ruta, errors="ignore").read()
    regs = [r.strip("\n") for r in txt.split("$$$$") if r.strip()]
    return [((r.splitlines()[0].strip() if r.splitlines() else "") or f"mol{i + 1}", r + "\n$$$$\n")
            for i, r in enumerate(regs)]


def _parece_smiles(t):
    return " " not in t and (bool(re.search(r"[=#()\[\]@/\\]", t)) or bool(re.fullmatch(r"[BCNOSPFIcnosp0-9]+", t)))


def asistente_ligandos(ruta, p, controles=False):
    clave = "controles" if controles else "ligandos"
    carpeta = os.path.join(ruta, "03_Controles" if controles else "02_Ligandos")
    etiqueta = "controles positivos" if controles else "ligandos"
    ids = {x["id"] for x in p["ligandos"] + p["controles"]}
    nuevos = []

    def agregar(e):
        e["id"] = _id_unico(ui.nombre_seguro(e["nombre"]), ids)
        ids.add(e["id"]); nuevos.append(e)

    while True:
        modo = ui.menu(f"¿Cómo quieres añadir {etiqueta}?", [
            ("pubchem", "Escribir nombres (se descargan de PubChem)"),
            ("lista", "Archivo de lista .txt/.csv (un nombre por línea, o nombre,SMILES)"),
            ("carpeta", "Carpeta con estructuras (.sdf .mol .mol2 .pdb .smi)"),
            ("archivos", "Un archivo de estructura (SDF con una o varias moléculas, etc.)"),
            ("smiles", "Escribir SMILES a mano"),
        ], defecto=1, salir="Terminar")
        if not modo:
            break
        if modo == "pubchem":
            ui.info("Escribe un compuesto por línea (nombre común o CID). Línea vacía para terminar.")
            while True:
                n = ui.preguntar("Compuesto", "")
                if not n:
                    break
                cid = pubchem_cid(n)
                if cid:
                    ui.ok(f"{n} → CID {cid}")
                else:
                    ui.aviso(f"No lo encontré en PubChem ahora mismo ('{n}'); lo intentaré al descargar.")
                agregar({"nombre": n, "fuente": "pubchem", "consulta": n, "cid": cid})
        elif modo == "lista":
            f = ui.preguntar_ruta("Archivo de lista", tipo="archivo")
            for linea in open(f, encoding="utf-8-sig", errors="ignore"):
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                partes = [x.strip() for x in re.split(r"[,\t;|]", linea) if x.strip()]
                if partes[0].lower() in ("nombre", "name"):
                    continue
                if len(partes) >= 2 and _parece_smiles(partes[1]):
                    agregar({"nombre": partes[0], "fuente": "smiles", "smiles": partes[1]})
                else:
                    agregar({"nombre": partes[0], "fuente": "pubchem", "consulta": partes[1] if len(partes) > 1 else partes[0]})
            ui.ok(f"{len(nuevos)} {etiqueta} leídos de la lista.")
        elif modo in ("carpeta", "archivos"):
            if modo == "carpeta":
                d = ui.preguntar_ruta("Carpeta con estructuras", tipo="carpeta")
                archivos = sorted(os.path.join(d, x) for x in os.listdir(d) if x.lower().endswith(EXT_LIGANDO))
            else:
                archivos = [ui.preguntar_ruta("Archivo de estructura", tipo="archivo")]
            for a in archivos:
                ext = os.path.splitext(a)[1].lower()
                if ext == ".sdf" and len(_partir_sdf(a)) > 1:
                    for nom, bloque in _partir_sdf(a):
                        e = {"nombre": nom, "fuente": "archivo"}
                        agregar(e)
                        destino = os.path.join(carpeta, e["id"] + ".sdf")
                        open(destino, "w").write(bloque)
                        e["archivo"] = os.path.relpath(destino, ruta)
                else:
                    e = {"nombre": os.path.splitext(os.path.basename(a))[0], "fuente": "archivo"}
                    agregar(e)
                    destino = os.path.join(carpeta, e["id"] + ext)
                    if os.path.abspath(a) != os.path.abspath(destino):
                        shutil.copy(a, destino)
                    e["archivo"] = os.path.relpath(destino, ruta)
            ui.ok(f"{len(archivos)} archivo(s) copiados a {os.path.relpath(carpeta, ruta)}/")
        elif modo == "smiles":
            ui.info("Línea vacía para terminar.")
            while True:
                n = ui.preguntar("Nombre", "")
                if not n:
                    break
                s = ui.preguntar("SMILES", obligatorio=True)
                agregar({"nombre": n, "fuente": "smiles", "smiles": s})

    if controles and nuevos and len(p["dianas"]) > 1:
        ui.info("Puedes asignar cada control a su diana (si no, se dockea contra todas).")
        ops = [d["id"] for d in p["dianas"]]
        for e in nuevos:
            print("     " + "  ".join(f"{ui.rosa(str(i))}) {x}" for i, x in enumerate(ops, 1)))
            r = ui.preguntar(f"Diana de '{e['nombre']}' (número; vacío = todas)", "",
                             valida=lambda x: None if x.isdigit() and 1 <= int(x) <= len(ops) else "Número de la lista")
            if r:
                e["diana"] = ops[int(r) - 1]
    elif controles and nuevos and len(p["dianas"]) == 1:
        for e in nuevos:
            e["diana"] = p["dianas"][0]["id"]
    p[clave].extend(nuevos)
    C.guardar_proyecto(ruta, p)
    if nuevos:
        ui.ok(f"{len(nuevos)} {etiqueta} añadidos: " + ", ".join(e["id"] for e in nuevos))


# ---------------------------------------------------------------- parámetros
def asistente_parametros(ruta, p):
    d = p["docking"]
    ui.titulo("Parámetros de docking (smina)")
    n = ui.preguntar_int("Número de semillas (réplicas independientes)", len(d["semillas"]), 1, 10)
    base = [42, 2026, 777, 1234, 31415, 2718, 1618, 4242, 9001, 1337]
    d["semillas"] = (d["semillas"] + [s for s in base if s not in d["semillas"]])[:n]
    d["exhaustiveness"] = ui.preguntar_int("Exhaustiveness (8 rápido · 32 estándar · 64+ ciego)", d["exhaustiveness"], 1, 512)
    d["num_modes"] = ui.preguntar_int("Número de poses por corrida", d["num_modes"], 1, 50)
    d["energy_range"] = ui.preguntar_int("Rango de energía (kcal/mol)", d["energy_range"], 1, 20)
    d["cpu"] = ui.preguntar_int("Núcleos de CPU (0 = todos)", d["cpu"], 0, 512)
    C.guardar_proyecto(ruta, p)
    ui.ok("Parámetros guardados.")


# ---------------------------------------------------------------- resumen / edición
def resumen_proyecto(ruta, p):
    ui.titulo(f"{p['codigo']}" + (f" · {p['cliente']}" if p.get("cliente") else ""))
    print(f"   {ui.gris('Ruta:')} {ruta}")
    print(f"   {ui.negrita('Dianas')} ({len(p['dianas'])}):")
    for d in p["dianas"]:
        c = d.get("caja", {})
        det = {"ligando": f"ref {c.get('ref')}", "residuos": f"residuos {c.get('residuos')}",
               "ciego": "ciego", "manual": f"centro {c.get('center')}"}.get(c.get("modo"), "?")
        print(f"     · {d['id']:22s} cadenas {d.get('cadenas') or 'todas':6s} caja: {det}")
    for clave, et in (("ligandos", "Ligandos"), ("controles", "Controles")):
        xs = p[clave]
        print(f"   {ui.negrita(et)} ({len(xs)}): " + (", ".join(
            x["id"] + (ui.gris(f"→{x['diana']}") if x.get("diana") else "") for x in xs[:15]) + (" …" if len(xs) > 15 else "")))
    d = p["docking"]
    nt = sum(len(v) for v in runner.corridas_esperadas(p).values())
    print(f"   {ui.negrita('Docking')}: {len(d['semillas'])} semillas · exh {d['exhaustiveness']} · "
          f"{d['num_modes']} poses · cpu {d['cpu'] or 'todos'}  →  {nt} corridas")


def editar_proyecto(ruta):
    while True:
        p = C.cargar_proyecto(ruta)
        resumen_proyecto(ruta, p)
        op = ui.menu("Editar proyecto", [
            ("diana", "Añadir diana"),
            ("lig", "Añadir ligandos"),
            ("ctrl", "Añadir controles positivos"),
            ("quitar", "Quitar una diana / ligando / control"),
            ("param", "Parámetros de docking"),
            ("abrir", "Abrir la carpeta en el Explorador de Windows"),
        ])
        if op is None:
            return
        if op == "diana":
            asistente_diana(ruta, p)
        elif op == "lig":
            asistente_ligandos(ruta, p, False)
        elif op == "ctrl":
            asistente_ligandos(ruta, p, True)
        elif op == "param":
            asistente_parametros(ruta, p)
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
