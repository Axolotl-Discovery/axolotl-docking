"""`Docking verificar`: autodiagnóstico para quien acaba de instalar.

Hace tres cosas, en orden, y en cada una dice qué hacer si falla:
  1. revisa el entorno (conda, librerías, smina, ADFRsuite);
  2. corre un docking de prueba COMPLETO y pequeño (tripsina 3PTB + bencenamidina, el sistema
     clásico de los tutoriales de AutoDock/smina): descarga, receptor, ligando, docking y resumen;
  3. comprueba que la afinidad salió con sentido (negativa y en un rango razonable).

El proyecto de prueba vive en una carpeta temporal y se borra al terminar (--conservar lo deja)."""
from __future__ import annotations

import csv
import os
import shutil
import tempfile
import urllib.error
import urllib.request

from . import config as C
from . import entorno, runner, ui

PASOS_PRUEBA = ["download", "receptors", "ligands", "docking", "summary"]
DISCO_MIN_GB = 3.0
AFINIDAD_RANGO = (-14.0, -2.0)  # kcal/mol: fuera de esto, algo anda mal aunque el programa no falle

# Qué hacer según el paso que falló (se muestra tal cual al usuario)
REMEDIOS = {
    "download": "No se pudo descargar la estructura. Revisa tu conexión a internet (y que tu red/VPN no bloquee "
                "files.rcsb.org) y vuelve a correr:  Docking verificar",
    "receptors": "Falló la preparación del receptor. Corre  Docking entorno  para revisar ADFRsuite (prepare_receptor) "
                 "y PDBFixer.",
    "ligands": "Falló la preparación del ligando. Corre  Docking entorno  para revisar RDKit y Meeko.",
    "docking": "Falló smina. Corre  Docking entorno  y, si smina aparece como no encontrado, "
               "Docking entorno instalar.",
    "summary": "El docking terminó pero el resumen falló. Abre el ⓘ del paso en la GUI o el log del proyecto de "
               "prueba (opción --conservar) y mándalo a quien te dio el curso.",
}


def crear_ejemplo(ruta: str) -> dict:
    """Proyecto de prueba: 3PTB (tripsina) con su ligando cristalográfico como caja y bencenamidina."""
    C.new_project(ruta, "Verificación Axolotl Docking", mode="basic")
    p = C.load_project(ruta)
    p["targets"] = [{"id": "3PTB", "source": "pdb", "pdb": "3PTB", "chains": "auto", "cofactors": "auto",
                     "box": {"mode": "auto"}}]
    p["ligands"] = [{"id": "benzamidina", "name": "Bencenamidina", "source": "smiles", "smiles": "NC(=N)c1ccccc1"}]
    p["controls"] = []
    p["docking"].update(seeds=[42], exhaustiveness=8, num_modes=3)
    C.save_project(ruta, p)
    return p


def hay_internet(url: str = "https://files.rcsb.org", timeout: float = 8.0) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True  # el servidor respondió: hay conexión
    except Exception:  # noqa: BLE001
        return False


def disco_libre_gb(ruta: str) -> float:
    return shutil.disk_usage(ruta).free / 1e9


def evaluar_afinidad(proy: str):
    """(ok, mensaje) a partir de affinities_summary.csv del proyecto de prueba."""
    from .layout import Layout
    f = Layout(proy).affinities_summary_csv()
    if not os.path.exists(f):
        return False, "no se generó la tabla de afinidades"
    with open(f, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        return False, "la tabla de afinidades está vacía"
    try:
        dg = float(filas[0]["afinidad_media"])
    except (KeyError, ValueError):
        return False, "la tabla de afinidades no tiene una afinidad legible"
    lo, hi = AFINIDAD_RANGO
    if not lo <= dg <= hi:
        return False, f"la afinidad ({dg:.2f} kcal/mol) está fuera de lo esperable ({lo:g} a {hi:g})"
    return True, f"ΔG = {dg:.2f} kcal/mol"


def paso_fallido(proy: str):
    """(id, errores) del primer paso que falló, según steps.json; (None, []) si no hay."""
    data = runner.estado_pasos(proy) or {}
    for p in data.get("pasos", []):
        if p.get("estado") in ("error", "interrumpido"):
            return p["id"], p.get("errores", [])
    return None, []


def verificar(conservar: bool = False) -> int:
    ui.titulo("Verificación de la instalación")
    libre = disco_libre_gb(os.path.expanduser("~"))
    if libre < DISCO_MIN_GB:
        ui.error(f"Poco espacio en disco: {libre:.1f} GB libres (se recomiendan al menos {DISCO_MIN_GB:g} GB). "
                 "Libera espacio y vuelve a correr:  Docking verificar")
        return 1
    print(ui.negrita("1/3 · Entorno"))
    if not entorno.doctor(reparar_preguntando=False):
        ui.error("El entorno está incompleto. Corre  Docking entorno instalar  (tarda 10–20 min, necesita "
                 "internet) y luego vuelve a correr  Docking verificar.")
        return 1
    print()
    print(ui.negrita("2/3 · Docking de prueba (tripsina + bencenamidina; ~1–3 min)"))
    if not hay_internet():
        ui.error("No hay conexión con files.rcsb.org, de donde se baja la estructura de prueba. Revisa tu "
                 "internet o tu VPN y vuelve a correr:  Docking verificar")
        return 1
    carpeta = tempfile.mkdtemp(prefix="axd_verificar_")
    proy = os.path.join(carpeta, "prueba")
    try:
        crear_ejemplo(proy)
        runner.ejecutar(proy, PASOS_PRUEBA, fondo=False)
        print()
        print(ui.negrita("3/3 · Resultado"))
        fallo, errores = paso_fallido(proy)
        if fallo:
            ui.error(f"Falló el paso '{fallo}'.")
            for e in errores[:6]:
                print(ui.gris("   " + e))
            ui.info(REMEDIOS.get(fallo, "Revisa el log del proyecto de prueba (--conservar)."))
            return 1
        ok, msg = evaluar_afinidad(proy)
        if not ok:
            ui.error("El docking corrió pero el resultado no es creíble: " + msg + ".")
            ui.info(REMEDIOS["summary"])
            return 1
        ui.ok(f"Docking de prueba correcto ({msg}).")
        print()
        ui.ok(ui.negrita("Todo está listo. Crea tu primer proyecto con:  Docking nuevo"))
        return 0
    finally:
        if conservar:
            ui.info(f"Proyecto de prueba conservado en {proy}")
        else:
            shutil.rmtree(carpeta, ignore_errors=True)
