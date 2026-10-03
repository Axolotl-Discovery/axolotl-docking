"""Ver resultados desde la terminal: tablas de afinidad, redocking, interacciones y abrir archivos."""
import csv
import glob
import os
import shutil
import subprocess
import unicodedata

from . import config as C
from . import runner
from . import ui


def _ancho(t):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(t))


def _pad(t, n, der=False):
    t = str(t)
    return (" " * max(0, n - _ancho(t)) + t) if der else (t + " " * max(0, n - _ancho(t)))


def tabla(filas, columnas, titulos=None, numericas=(), resaltar=None, max_ancho=34):
    """Imprime una tabla alineada. resaltar(fila) → True pinta la fila en rosa."""
    titulos = titulos or columnas
    celdas = [[(str(f.get(c, "")) if f.get(c, "") not in (None, "nan") else "")[:max_ancho] for c in columnas]
              for f in filas]
    anchos = [max([_ancho(t)] + [_ancho(r[i]) for r in celdas]) for i, t in enumerate(titulos)]
    print("    " + "  ".join(ui.negrita(_pad(t, anchos[i], columnas[i] in numericas)) for i, t in enumerate(titulos)))
    print("    " + ui.gris("  ".join("─" * a for a in anchos)))
    for f, r in zip(filas, celdas):
        linea = "  ".join(_pad(v, anchos[i], columnas[i] in numericas) for i, v in enumerate(r))
        print("    " + (ui.rosa(linea) if resaltar and resaltar(f) else linea))


def _leer(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(x, nd=2):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------- vistas
def ver_afinidades(proy):
    filas = _leer(os.path.join(proy, "05_Analisis", "afinidades_resumen.csv"))
    if not filas:
        ui.aviso("Aún no hay tabla de afinidades. Corre el pipeline (o el paso 'resumen').")
        return
    por_diana = {}
    for f in filas:
        por_diana.setdefault(f["diana"], []).append(f)
    for diana, fs in por_diana.items():
        ui.titulo(f"Afinidades · {diana}")
        fs.sort(key=lambda f: float(f["afinidad_media"] or 0))
        mejor = fs[0]["ligando"]
        vista = [dict(lig=f["ligando"] + ("  ◆" if f["tipo"] == "control" else ""),
                      media=_num(f["afinidad_media"]), de=_num(f["afinidad_de"]), mejor=_num(f["mejor"]),
                      le=_num(f["LE"]), dc=(f"{float(f['delta_vs_control']):+.2f}" if f.get("delta_vs_control") else ""),
                      n=f.get("n_semillas", ""), _lig=f["ligando"]) for f in fs]
        tabla(vista, ["lig", "media", "de", "mejor", "le", "dc", "n"],
              ["Ligando", "ΔG media", "DE", "Mejor", "LE", "Δ control", "semillas"],
              numericas=("media", "de", "mejor", "le", "dc", "n"), resaltar=lambda f: f["_lig"] == mejor)
    print(ui.gris("\n    kcal/mol · más negativo = mayor afinidad predicha · ◆ control · LE = −ΔG / átomos pesados"))
    print(ui.gris("    Δ control negativo = el ligando supera al control"))


def ver_matriz(proy):
    filas = _leer(os.path.join(proy, "05_Analisis", "matriz_afinidad.csv"))
    if not filas:
        ui.aviso("Aún no hay matriz de afinidades.")
        return
    cols = [c for c in filas[0] if c != "ligando"]
    ui.titulo("Matriz ligando × diana (ΔG media, kcal/mol)")
    vista = [dict({"ligando": f["ligando"]}, **{c: _num(f[c]) for c in cols}) for f in filas]
    tabla(vista, ["ligando"] + cols, numericas=tuple(cols))


def ver_redocking(proy):
    filas = _leer(os.path.join(proy, "05_Analisis", "redocking_resumen.csv"))
    if not filas:
        ui.aviso("No hay redocking (sólo se hace cuando la caja viene de un ligando co-cristalizado).")
        return
    ui.titulo("Validación por redocking (criterio: RMSD ≤ 2 Å)")
    vista = [dict(diana=f["diana"], semilla=f["semilla"], afinidad=_num(f["afinidad"]), rmsd=_num(f["rmsd"]),
                  ok=("✔" if f["rmsd"] and float(f["rmsd"]) <= 2 else "✘")) for f in filas]
    tabla(vista, ["diana", "semilla", "afinidad", "rmsd", "ok"], ["Diana", "Semilla", "ΔG", "RMSD (Å)", ""],
          numericas=("semilla", "afinidad", "rmsd"))


def ver_interacciones(proy):
    res = _leer(os.path.join(proy, "05_Analisis", "interacciones_resumen.csv"))
    det = _leer(os.path.join(proy, "05_Analisis", "interacciones_detalle.csv"))
    if not res:
        ui.aviso("Aún no hay análisis de interacciones → opción 'Analizar interacciones ahora'.")
        return
    tipos = [c for c in res[0] if c not in ("diana", "ligando", "total", "residuos", "complejo")]
    activos = [t for t in tipos if any(int(f[t] or 0) for f in res)]
    ui.titulo("Interacciones por complejo (mejor pose)")
    abrev = {"Hidrofóbica": "Hidrof.", "Puente de H": "Pte. H", "Apilamiento π": "π-π", "Catión-π": "Cat-π",
             "Puente salino": "Salino", "Enlace de halógeno": "Halóg.", "Puente de agua": "Agua",
             "Coordinación metálica": "Metal"}
    tabla(res, ["diana", "ligando", "total"] + activos, ["Diana", "Ligando", "Total"] + [abrev.get(t, t) for t in activos],
          numericas=tuple(["total"] + activos))
    while True:
        ops = [(i, f"{f['diana']} + {f['ligando']}  {ui.gris('(' + f['total'] + ')')}") for i, f in enumerate(res)]
        k = ui.menu("Ver el detalle de un complejo", ops, salir="Volver")
        if k is None:
            return
        f = res[k]
        filas = [d for d in det if d["diana"] == f["diana"] and d["ligando"] == f["ligando"]]
        ui.titulo(f"{f['diana']} + {f['ligando']}")
        filas.sort(key=lambda d: (d["tipo"], float(d["distancia"] or 0)))
        filas = [dict(d, distancia=_num(d["distancia"])) for d in filas]
        tabla(filas, ["tipo", "residuo", "cadena", "distancia", "detalle"],
              ["Tipo", "Residuo", "Cad.", "Dist. (Å)", "Detalle"], numericas=("distancia",))
        print(ui.gris(f"\n    Residuos: {f['residuos']}"))
        print(ui.gris(f"    Complejo: {f['complejo']}  (método: {filas[0]['metodo'] if filas else '-'})"))
        if ui.si_no("¿Abrir este complejo?", False):
            abrir_complejo(proy, os.path.join(proy, f["complejo"]))


# ---------------------------------------------------------------- abrir archivos
def abrir_en_windows(ruta):
    """Abre un archivo o carpeta con el programa predeterminado de Windows."""
    if shutil.which("explorer.exe") and shutil.which("wslpath"):
        try:
            win = subprocess.check_output(["wslpath", "-w", ruta], text=True).strip()
            subprocess.Popen(["explorer.exe", win], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ui.ok(f"Abriendo {os.path.basename(ruta) or ruta} en Windows…")
            return True
        except Exception:  # noqa: BLE001
            pass
    for abridor in ("wslview", "xdg-open"):
        if shutil.which(abridor):
            subprocess.Popen([abridor, ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    ui.info(f"Ábrelo a mano: {ruta}")
    return False


def abrir_pymol(ruta):
    """Abre en PyMOL del entorno conda (necesita WSLg: Windows 11 o Windows 10 actualizado)."""
    g = C.cargar_global()
    conda = C.ruta_conda(g)
    if not conda:
        ui.error("No encontré conda."); return
    cmd = (f'source "{conda}/etc/profile.d/conda.sh" && conda activate "{g["entorno"]}" && '
           f'export PATH="$CONDA_PREFIX/bin:$PATH" && exec pymol "$1"')
    subprocess.Popen(["bash", "-c", cmd, "axd", ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    ui.ok("Abriendo PyMOL… (si no aparece ninguna ventana, tu WSL no tiene modo gráfico: usa la opción de Windows)")


def abrir_complejo(proy, ruta=None):
    if not ruta:
        comps = sorted(glob.glob(os.path.join(proy, "04_Docking", "Complejos", "*_complejo.pdb")))
        if not comps:
            ui.aviso("No hay complejos todavía → opción 'Analizar interacciones ahora'.")
            return
        k = ui.menu("¿Qué complejo?", [(c, os.path.basename(c)[:-13].replace("__", " + ")) for c in comps])
        if not k:
            return
        ruta = k
    como = ui.menu("¿Con qué lo abro?", [("pymol", "PyMOL (dentro de WSL)"),
                                         ("win", "Programa predeterminado de Windows (PyMOL, Chimera, Discovery Studio…)"),
                                         ("carpeta", "Mostrar el archivo en el Explorador")], defecto=1)
    if como == "pymol":
        abrir_pymol(ruta)
    elif como == "win":
        abrir_en_windows(ruta)
    elif como == "carpeta":
        abrir_en_windows(os.path.dirname(ruta))


def menu_resultados(proy):
    while True:
        p = C.cargar_proyecto(proy)
        hay = os.path.exists(os.path.join(proy, "05_Analisis", "afinidades_resumen.csv"))
        op = ui.menu(f"Resultados · {p['nombre']}", [
            ("afin", "Tabla de afinidades"),
            ("matriz", "Matriz ligando × diana"),
            ("redock", "Validación (redocking)"),
            ("inter", "Interacciones (contactos y tipos)"),
            ("analizar", "Analizar interacciones ahora / actualizar tablas"),
            ("complejo", "Abrir un complejo proteína + ligando"),
            ("excel", "Abrir el Excel de resultados"),
            ("carpeta", "Abrir la carpeta del proyecto"),
        ], defecto=1 if hay else 5)
        if op is None:
            return
        if op == "afin":
            ver_afinidades(proy); ui.pausa()
        elif op == "matriz":
            ver_matriz(proy); ui.pausa()
        elif op == "redock":
            ver_redocking(proy); ui.pausa()
        elif op == "inter":
            ver_interacciones(proy)
        elif op == "analizar":
            runner.ejecutar(proy, ["resumen", "interacciones"], fondo=False)
        elif op == "complejo":
            abrir_complejo(proy)
        elif op == "excel":
            xl = sorted(glob.glob(os.path.join(proy, "05_Analisis", "*_afinidades.xlsx")))
            if xl:
                abrir_en_windows(xl[0])
            else:
                ui.aviso("No hay Excel todavía (se genera en el paso 'resumen').")
        elif op == "carpeta":
            abrir_en_windows(proy)
