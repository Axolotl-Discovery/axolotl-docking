"""Paso 'report': reporte PDF profesional de la corrida de docking (07_Report/).

Contenido: portada con logos, resumen ejecutivo, pasos de la corrida, métodos
(texto citable generado a partir de lo que de verdad se hizo), dianas y cajas,
ligandos con su estructura 2D, validación por redocking, afinidades (tabla y
gráficas), matriz ligando × diana, interacciones (tabla y figura 3D si existe),
problemas registrados, entorno de cómputo y referencias.

Usa ReportLab (BSD) para el PDF, matplotlib para las gráficas y RDKit para las
estructuras 2D; las figuras quedan también en 06_Figures/. La fuente es
DejaVu Sans (la que trae matplotlib) para que Δ, π, Å y ± se vean bien.

Logos y datos del laboratorio: config global (Entorno → Reporte):
  reporte_logo, reporte_laboratorio, reporte_autor."""
import csv
import datetime as _dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys

from common import log, title, tool

ACCENT = "#E0458F"
INK = "#1A1A1A"
MUTED = "#6B6B6B"
RULE = "#D9D9D9"
SOFT = "#F6F6F6"
OK = "#2E9E5B"
ERR = "#C94444"

MOTOR_NOMBRE = {"smina": "smina (función de puntuación de AutoDock Vina)",
                "vina-gpu": "Vina-GPU 2.1 (AutoDock Vina acelerado en GPU)",
                "ad4": "AutoDock4"}
FUENTE_NOMBRE = {"pdb": "Protein Data Bank (RCSB)", "alphafold": "AlphaFold DB", "file": "archivo local",
                 "pubchem": "PubChem", "smiles": "SMILES", "pdb_ligand": "PDB (ligando)"}

REFERENCIAS = {
    "vina": "Trott O, Olson AJ. AutoDock Vina: improving the speed and accuracy of docking with a new scoring "
            "function, efficient optimization, and multithreading. J Comput Chem. 2010;31(2):455–461.",
    "vina12": "Eberhardt J, Santos-Martins D, Tillack AF, Forli S. AutoDock Vina 1.2.0: new docking methods, "
              "expanded force field, and Python bindings. J Chem Inf Model. 2021;61(8):3891–3898.",
    "smina": "Koes DR, Baumgartner MP, Camacho CJ. Lessons learned in empirical scoring with smina from the CSAR "
             "2011 benchmarking exercise. J Chem Inf Model. 2013;53(8):1893–1904.",
    "vinagpu": "Tang S, Ding J, Zhu X, Wang Z, Zhao H, Wu J. Vina-GPU 2.1: towards further optimizing docking "
               "speed and precision of AutoDock Vina and its derivatives. bioRxiv. 2023. "
               "doi:10.1101/2023.11.04.565429.",
    "ad4": "Morris GM, Huey R, Lindstrom W, Sanner MF, Belew RK, Goodsell DS, Olson AJ. AutoDock4 and "
           "AutoDockTools4: automated docking with selective receptor flexibility. J Comput Chem. "
           "2009;30(16):2785–2791.",
    "adfr": "Ravindranath PA, Forli S, Goodsell DS, Olson AJ, Sanner MF. AutoDockFR: advances in protein-ligand "
            "docking with explicitly specified binding site flexibility. PLoS Comput Biol. 2015;11(12):e1004586.",
    "openmm": "Eastman P, Swails J, Chodera JD, et al. OpenMM 7: rapid development of high performance algorithms "
              "for molecular dynamics. PLoS Comput Biol. 2017;13(7):e1005659.",
    "rdkit": "RDKit: open-source cheminformatics. https://www.rdkit.org",
    "plip": "Adasme MF, Linnemann KL, Bolz SN, et al. PLIP 2021: expanding the scope of the protein–ligand "
            "interaction profiler to DNA and RNA. Nucleic Acids Res. 2021;49(W1):W530–W534.",
    "ecr": "Palacio-Rodríguez K, Lans I, Cavasotto CN, Cossio P. Exponential consensus ranking improves the outcome "
           "in docking and receptor ensemble docking. Sci Rep. 2019;9(1):5142. doi:10.1038/s41598-019-41594-3.",
    "vinardo": "Quiroga R, Villarreal MA. Vinardo: a scoring function based on AutoDock Vina improves scoring, "
               "docking, and virtual screening. PLoS One. 2016;11(5):e0155183.",
    "houston": "Houston DR, Walkinshaw MJ. Consensus docking: improving the reliability of docking in a virtual "
               "screening context. J Chem Inf Model. 2013;53(2):384–390.",
    "pdb": "Berman HM, Westbrook J, Feng Z, et al. The Protein Data Bank. Nucleic Acids Res. 2000;28(1):235–242.",
}


# ================================================================ datos (sin dependencias pesadas)
def _csv(path):
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _version_herramienta(nombre, args=("--version",)):
    exe = tool(nombre)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=20)
        txt = (r.stdout or r.stderr or "").strip().splitlines()
        return txt[0][:80] if txt else None
    except (OSError, subprocess.SubprocessError):
        return None


def recolectar(P):
    """Todo lo que va en el reporte, como datos simples (testeable sin ReportLab)."""
    from axd.config import APP, load_global
    lay = P.layout
    cfg = P.cfg
    d = cfg.get("docking", {})
    motor = d.get("motor_usado") or d.get("engine") or "smina"
    boxes = _json(lay.boxes_json(), {}) or {}
    afin = _csv(lay.affinities_summary_csv())
    inter_res = _csv(lay.interactions_summary_csv())
    inter_det = _csv(lay.interactions_detail_csv())
    redock = _csv(lay.redocking_summary_csv())
    pasos = (_json(lay.steps_state_file(), {}) or {}).get("pasos", [])
    g = load_global()
    try:
        version = open(os.path.join(APP, "VERSION")).read().strip()
    except OSError:
        version = "?"

    por_diana = {}
    for f in afin:
        por_diana.setdefault(f.get("diana", ""), []).append(f)
    for fs in por_diana.values():
        fs.sort(key=lambda f: _f(f.get("afinidad_media")) if _f(f.get("afinidad_media")) is not None else 1e9)

    resumen = []
    for t in cfg.get("targets", []):
        fs = [f for f in por_diana.get(t["id"], []) if f.get("tipo") != "control"]
        ctrl = [f for f in por_diana.get(t["id"], []) if f.get("tipo") == "control"]
        rs = [_f(r.get("rmsd")) for r in redock if r.get("diana") == t["id"] and _f(r.get("rmsd")) is not None]
        mejor = fs[0] if fs else None
        resumen.append({
            "diana": t["id"],
            "mejor": mejor.get("ligando") if mejor else None,
            "dg": _f(mejor.get("afinidad_media")) if mejor else None,
            "de": _f(mejor.get("afinidad_de")) if mejor else None,
            "control": ctrl[0].get("ligando") if ctrl else None,
            "dg_control": _f(ctrl[0].get("afinidad_media")) if ctrl else None,
            "supera_control": (mejor is not None and ctrl and _f(mejor.get("afinidad_media")) is not None
                               and _f(ctrl[0].get("afinidad_media")) is not None
                               and _f(mejor.get("afinidad_media")) < _f(ctrl[0].get("afinidad_media"))),
            "redock_rmsd_min": min(rs) if rs else None,
        })

    ligandos = []
    for l, ctrl in [(x, False) for x in cfg.get("ligands", [])] + [(x, True) for x in cfg.get("controls", [])]:
        ligandos.append({"id": l["id"], "nombre": l.get("name") or l["id"], "fuente": l.get("source", ""),
                         "consulta": l.get("query") or l.get("smiles") or l.get("code") or
                         (os.path.basename(l["file"]) if l.get("file") else ""),
                         "control": ctrl, "sdf": lay.ligand_prep_sdf(l["id"], ctrl), "smiles": l.get("smiles")})

    metodo_inter = sorted({r.get("metodo", "") for r in inter_det if r.get("metodo")})
    hw = None
    try:
        from axd import hardware as HW
        hw = HW.detect()
    except Exception:  # noqa: BLE001
        pass
    versiones = {"Axolotl Docking": version, "Python": platform.python_version()}
    for mod, nombre in (("rdkit", "RDKit"), ("numpy", "NumPy"), ("meeko", "Meeko"), ("openmm", "OpenMM"),
                        ("reportlab", "ReportLab")):
        try:
            versiones[nombre] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            pass
    if motor == "smina":
        v = _version_herramienta("smina")
        if v:
            versiones["smina"] = v
    elif motor == "vina-gpu":
        versiones["Vina-GPU"] = "2.1 (commit 180272b)"

    consenso = recolectar_consenso(P)
    if consenso and "ad4" in consenso["meta"].get("motores", []):
        versiones.setdefault("AutoDock4", "ADFRsuite")
    if consenso and any(m in ("vinardo",) for m in consenso["meta"].get("motores", [])):
        v = _version_herramienta("smina")
        if v:
            versiones["smina"] = v

    return {
        "consenso": consenso,
        "proyecto": cfg.get("name", os.path.basename(P.root)), "modo": cfg.get("mode", ""),
        "fecha": _dt.datetime.now().strftime("%d/%m/%Y %H:%M"), "version": version,
        "laboratorio": g.get("reporte_laboratorio", ""), "autor": g.get("reporte_autor", ""),
        "logo": g.get("reporte_logo", ""),
        "motor": motor, "docking": d, "dianas": cfg.get("targets", []), "cajas": boxes, "ligandos": ligandos,
        "afinidades": por_diana, "matriz": _csv(lay.affinity_matrix_csv()), "redocking": redock,
        "interacciones": inter_res, "interacciones_detalle": inter_det, "metodo_interacciones": metodo_inter,
        "pasos": pasos, "resumen": resumen, "versiones": versiones,
        "hardware": ({"cpu": hw.cpu_model, "nucleos": hw.usable_cores,
                      "gpu": ", ".join(x.name for x in hw.gpus) or "—",
                      "sistema": f"{platform.system()} {platform.release()}"} if hw else {}),
    }


def recolectar_consenso(P):
    """Datos del modo consenso (o None si no se corrió): resumen por ligando, τ de Kendall,
    RMSD entre poses, redocking por motor, tiempos por motor y la meta del análisis."""
    from axd import consensus as K
    lay = P.layout
    filas = _csv(lay.consensus_summary_csv())
    meta = _json(lay.consensus_meta_json(), {}) or {}
    if not filas or not meta:
        return None
    motores = meta.get("motores") or [c[3:] for c in filas[0] if c.startswith("dG_")]
    principal_real = meta.get("principal_real")
    por_diana = {}
    for f in filas:
        por_diana.setdefault(f.get("diana", ""), []).append(f)
    taus = {}
    for t in _csv(lay.consensus_tau_csv()):
        taus.setdefault(t.get("diana", ""), {})[(t.get("motor_a"), t.get("motor_b"))] = _f(t.get("tau"))
    return {"meta": meta, "motores": motores,
            "nombres": {m: K.nombre_motor(m, principal_real) for m in motores},
            "filas": por_diana, "tau": taus, "poses": _csv(lay.consensus_poses_csv()),
            "redocking": _csv(lay.consensus_redocking_csv()), "tiempos": _csv(lay.consensus_engines_csv()),
            "veredictos": K.resumen_veredictos(filas)}


def texto_consenso(datos):
    """Párrafos de métodos del consenso (vacío si no se corrió)."""
    c = datos.get("consenso")
    if not c:
        return []
    from axd import consensus as K
    nombres = ", ".join(c["nombres"][m] for m in c["motores"])
    sigma = c["meta"].get("sigma", {})
    sig = ", ".join(f"{d}: σ = {v:g}" for d, v in sigma.items())
    u = c["meta"].get("umbrales", {})
    return [
        f"Además del motor principal, se aplicó un consenso entre {len(c['motores'])} motores de docking con "
        f"funciones de puntuación distintas ({nombres}), con los mismos receptores, cajas, ligandos y semillas. "
        "Para cada diana se ordenaron los ligandos por afinidad media en cada motor y los rangos se combinaron con "
        "el consenso exponencial de rangos (ECR): ECR(i) = Σ_j (1/σ)·exp(−r_ij/σ), donde r_ij es el rango del "
        f"ligando i en el motor j y σ = 10 % del número de ligandos, con un mínimo de 1 ({sig}). El mínimo es una "
        "adaptación a proyectos con pocos ligandos y no forma parte del método original.",
        f"El acuerdo de poses se midió como el RMSD, sin realinear y con simetría, entre las mejores poses de cada "
        f"par de motores (coinciden si RMSD ≤ {u.get('rmsd', K.RMSD_OK)} Å). El veredicto por ligando es "
        f"«Robusto» si coinciden los rangos (dispersión normalizada (máx − mín)/(N − 1) ≤ {u.get('dispersion', K.SPREAD_OK)}) "
        "y las poses; «Parcial» si coincide sólo uno de los dos criterios; «Discrepante» si no coincide ninguno. "
        "Con menos de 3 ligandos por diana no se evalúan los rangos.",
    ]


def texto_metodos(datos):
    """Párrafo(s) de métodos, en español, a partir de lo que de verdad se hizo."""
    ds = datos["dianas"]
    pdb_ids = [t.get("pdb") for t in ds if t.get("source") == "pdb" and t.get("pdb")]
    af = [t.get("uniprot") or t["id"] for t in ds if t.get("source") == "alphafold"]
    partes = []
    origen = []
    if pdb_ids:
        origen.append("del Protein Data Bank (" + ", ".join(pdb_ids) + ")")
    if af:
        origen.append("de AlphaFold DB (" + ", ".join(af) + ")")
    if len(origen) < len(ds) and any(t.get("source") == "file" for t in ds):
        origen.append("de archivos proporcionados por el usuario")
    partes.append(
        "Las estructuras de las dianas se obtuvieron " + (" y ".join(origen) or "de archivos locales") + ". "
        "Los receptores se limpiaron (cadenas seleccionadas, sin aguas ni aditivos; se conservaron los cofactores "
        "indicados), se completaron los átomos pesados faltantes con PDBFixer (OpenMM) y se prepararon en formato "
        "PDBQT con prepare_receptor (ADFRsuite), añadiendo hidrógenos.")
    modos = {(datos["cajas"].get(t["id"], {}) or {}).get("mode", (t.get("box") or {}).get("mode", "")) for t in ds}
    caja = []
    if "ligand" in modos:
        caja.append("centrada en el ligando co-cristalizado con un margen alrededor")
    if "blind" in modos:
        caja.append("sobre toda la proteína (docking ciego)")
    if "residues" in modos:
        caja.append("alrededor de los residuos del sitio indicados")
    if "manual" in modos:
        caja.append("con centro y tamaño definidos manualmente")
    if caja:
        partes.append("La caja de búsqueda se definió " + "; ".join(caja) + " (centro y tamaño por diana en la "
                      "tabla de dianas).")
    partes.append("Los ligandos se prepararon con RDKit (estandarización, protonación, generación de conformero 3D "
                  "con ETKDGv3 y optimización MMFF94) y se convirtieron a PDBQT con Meeko.")
    d = datos["docking"]
    sem = d.get("seeds", [])
    motor = datos["motor"]
    if motor == "vina-gpu":
        params = f"{int(d.get('gpu_threads') or 8000)} hilos de búsqueda en GPU"
    elif motor == "ad4":
        params = (f"{d.get('ad4_runs', 20)} corridas del algoritmo genético de Lamarck con "
                  f"{int(d.get('ad4_evals', 2500000)):,} evaluaciones de energía cada una").replace(",", " ")
    else:
        params = f"exhaustiveness {d.get('exhaustiveness')}"
    partes.append(
        f"El docking se realizó con {MOTOR_NOMBRE.get(motor, motor)} ({params}; hasta {d.get('num_modes')} poses, "
        f"rango de energía {d.get('energy_range')} kcal/mol). Cada par ligando–diana se calculó con {len(sem)} "
        f"semilla(s) aleatoria(s) independientes ({', '.join(str(s) for s in sem)}); se reporta la media ± desviación "
        "estándar de la afinidad de la mejor pose de cada semilla. La eficiencia de ligando se calculó como "
        "LE = −ΔG / número de átomos pesados.")
    if datos["redocking"]:
        partes.append("El protocolo se validó por redocking del ligando co-cristalizado; se considera válido un RMSD "
                      "de la mejor pose ≤ 2.0 Å respecto a la pose experimental.")
    partes += texto_consenso(datos)
    mi = datos["metodo_interacciones"]
    if mi:
        quien = "PLIP" if any(m.lower() == "plip" for m in mi) else "criterios geométricos de distancia"
        partes.append(f"Las interacciones proteína–ligando de la mejor pose se analizaron con {quien}.")
    return partes


def parametros_legibles(datos):
    d = datos["docking"]
    partes = [f"semillas: {', '.join(str(s) for s in d.get('seeds', []))}"]
    if datos["motor"] == "vina-gpu":
        partes.append(f"hilos GPU: {int(d.get('gpu_threads') or 8000)}")
    elif datos["motor"] == "ad4":
        partes.append(f"corridas GA: {d.get('ad4_runs', 20)} × {int(d.get('ad4_evals', 2500000)):,} evaluaciones"
                      .replace(",", " "))
    else:
        partes.append(f"exhaustiveness: {d.get('exhaustiveness')}")
    partes.append(f"poses: {d.get('num_modes')}")
    partes.append(f"rango de energía: {d.get('energy_range')} kcal/mol")
    partes.append("CPU: todos los núcleos" if not int(d.get("cpu") or 0) else f"CPU: {d.get('cpu')} núcleos")
    return " · ".join(partes)


def referencias(datos):
    claves = []
    if any(t.get("source") == "pdb" for t in datos["dianas"]):
        claves.append("pdb")
    claves += ["openmm", "adfr", "rdkit"]
    m = datos["motor"]
    claves += {"smina": ["smina", "vina"], "vina-gpu": ["vinagpu", "vina"], "ad4": ["ad4"]}.get(m, ["vina"])
    c = datos.get("consenso")
    if c:
        claves += ["ecr", "houston"]
        if "vinardo" in c["motores"]:
            claves += ["vinardo", "smina"]
        if "ad4" in c["motores"]:
            claves.append("ad4")
    if any(x.lower() == "plip" for x in datos["metodo_interacciones"]):
        claves.append("plip")
    return [REFERENCIAS[k] for k in dict.fromkeys(claves)]


# ================================================================ figuras
def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": RULE,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False})
    return plt


def figura_afinidades(diana, filas, ruta):
    plt = _mpl()
    filas = [f for f in filas if _f(f.get("afinidad_media")) is not None]
    if not filas:
        return None
    nombres = [f.get("ligando", "") + (" ◆" if f.get("tipo") == "control" else "") for f in filas]
    vals = [_f(f["afinidad_media"]) for f in filas]
    errs = [_f(f.get("afinidad_de")) or 0 for f in filas]
    colores = [MUTED if f.get("tipo") == "control" else ACCENT for f in filas]
    alto = max(1.6, 0.38 * len(filas) + 0.8)
    fig, ax = plt.subplots(figsize=(6.4, alto), dpi=200)
    y = range(len(filas))
    ax.barh(list(y), vals, xerr=errs, color=colores, height=0.6, error_kw={"ecolor": INK, "elinewidth": 0.8,
                                                                            "capsize": 2})
    ax.set_yticks(list(y))
    ax.set_yticklabels(nombres)
    ax.invert_yaxis()
    ax.set_xlabel("ΔG media (kcal/mol) · más negativo = mayor afinidad predicha")
    ax.set_title(f"Afinidades · {diana}", loc="left", fontsize=10, color=INK, fontweight="bold")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.2f}", va="center", ha="right" if v < 0 else "left", fontsize=8, color="white"
                if abs(v) > abs(min(vals)) * 0.25 else INK)
    ax.axvline(0, color=RULE, lw=0.8)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def figura_consenso(diana, filas, motores, nombres, taus, ruta):
    """Izquierda: rango de cada ligando en cada motor (líneas que se cruzan = desacuerdo; en rojo los
    discrepantes). Derecha: τ de Kendall entre motores."""
    filas = [f for f in filas if f.get("orden") not in (None, "")]
    if not filas or len(motores) < 2:
        return None
    plt = _mpl()
    import numpy as np
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(9.0, max(2.8, 0.34 * len(filas) + 1.6)),
                                 gridspec_kw={"width_ratios": [1.7, 1]})
    color = {"Robusto": OK, "Parcial": "#D9A21B", "Discrepante": ERR}
    xs = list(range(len(motores)))
    for f in filas:
        ys = [_f(f.get(f"rango_{m}")) for m in motores]
        c = color.get(f.get("veredicto"), MUTED)
        ax.plot(xs, ys, "-o", color=c, lw=1.4, ms=4, alpha=0.9)
        ax.annotate(f.get("ligando", "")[:14], (xs[-1], ys[-1]), xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=7, color=c)
    ax.set_xticks(xs)
    ax.set_xticklabels([nombres[m].replace(" (", "\n(") for m in motores], fontsize=8)
    ax.set_xlim(-0.2, len(motores) - 1 + 0.9)
    ax.invert_yaxis()
    ax.set_ylabel("Rango (1 = mejor afinidad)")
    ax.set_title("Rango por motor", fontsize=9, color=INK, loc="left")
    ax.grid(axis="y", color=RULE, lw=0.4)
    mt = np.full((len(motores), len(motores)), np.nan)
    for i, a in enumerate(motores):
        mt[i, i] = 1.0
        for j, b in enumerate(motores):
            v = taus.get((a, b), taus.get((b, a))) if i != j else 1.0
            if v is not None:
                mt[i, j] = v
    im = bx.imshow(mt, vmin=-1, vmax=1, cmap="RdYlGn")
    bx.set_xticks(xs)
    bx.set_yticks(xs)
    cortos = [nombres[m].split(" (")[0] for m in motores]
    bx.set_xticklabels(cortos, fontsize=7, rotation=30, ha="right")
    bx.set_yticklabels(cortos, fontsize=7)
    for i in range(len(motores)):
        for j in range(len(motores)):
            if not np.isnan(mt[i, j]):
                bx.text(j, i, f"{mt[i, j]:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(mt[i, j]) > 0.75 else INK)
    bx.set_title("τ de Kendall entre motores", fontsize=9, color=INK, loc="left")
    for sp in bx.spines.values():
        sp.set_visible(False)
    fig.tight_layout()
    fig.savefig(ruta, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta


def figura_matriz(matriz, ruta):
    if not matriz:
        return None
    cols = [c for c in matriz[0] if c != "ligando"]
    if len(cols) < 2 and len(matriz) < 2:
        return None
    plt = _mpl()
    import numpy as np
    m = np.array([[(_f(r.get(c)) if _f(r.get(c)) is not None else np.nan) for c in cols] for r in matriz])
    fig, ax = plt.subplots(figsize=(min(7.0, 1.2 + 0.9 * len(cols)), max(1.8, 0.42 * len(matriz) + 1.0)), dpi=200)
    im = ax.imshow(m, cmap="RdPu_r", aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=30, ha="right")
    ax.set_yticks(range(len(matriz)))
    ax.set_yticklabels([r.get("ligando", "") for r in matriz])
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if not np.isnan(m[i, j]):
                ax.text(j, i, f"{m[i, j]:.1f}", ha="center", va="center", fontsize=8,
                        color="white" if m[i, j] < np.nanmean(m) else INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("ΔG media (kcal/mol)")
    ax.set_title("Matriz ligando × diana", loc="left", fontsize=10, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def figura_ligando_2d(lig, ruta):
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem, Draw
    except ImportError:
        return None
    m = None
    if os.path.exists(lig["sdf"]):
        m = Chem.MolFromMolFile(lig["sdf"], removeHs=True)
    if m is None and lig.get("smiles"):
        m = Chem.MolFromSmiles(lig["smiles"])
    if m is None:
        return None
    m = Chem.RemoveHs(m)
    AllChem.Compute2DCoords(m)
    try:
        Draw.MolToFile(m, ruta, size=(420, 300))
    except Exception:  # noqa: BLE001
        return None
    return ruta if os.path.exists(ruta) else None


def figura_complejo(complejo_pdb, ruta, capturas_dir, base):
    """Imagen 3D del complejo: una captura hecha en el visor (06_Figures/<base>.png) o,
    si no hay, un render con PyMOL sin interfaz (si está instalado)."""
    previa = os.path.join(capturas_dir, f"{base}.png")
    if os.path.exists(previa):
        return previa
    pymol = tool("pymol")
    if not pymol or not os.path.exists(complejo_pdb):
        return None
    pml = ruta[:-4] + ".pml"
    with open(pml, "w") as fh:
        fh.write(f"load {complejo_pdb}, c\nhide everything\nbg_color white\nset ray_opaque_background, 1\n"
                 "show cartoon, polymer\ncolor grey80, polymer\nshow sticks, resn LIG\n"
                 "color magenta, resn LIG and elem C\nshow sticks, byres (polymer within 4 of resn LIG) "
                 "and not name N+C+O\ncolor palegreen, byres (polymer within 4 of resn LIG) and elem C\n"
                 "set cartoon_transparency, 0.25\norient resn LIG\nzoom resn LIG, 8\n"
                 f"set ray_trace_mode, 1\nray 1400, 1000\npng {ruta}, dpi=200\nquit\n")
    try:
        subprocess.run([pymol, "-cq", pml], capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.remove(pml)
        except OSError:
            pass
    return ruta if os.path.exists(ruta) else None


# ================================================================ PDF
def _fuentes():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        import matplotlib
        base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        pdfmetrics.registerFont(TTFont("AXD", os.path.join(base, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("AXD-B", os.path.join(base, "DejaVuSans-Bold.ttf")))
        from reportlab.lib.fonts import addMapping
        addMapping("AXD", 0, 0, "AXD")
        addMapping("AXD", 1, 0, "AXD-B")
        return "AXD", "AXD-B"
    except Exception:  # noqa: BLE001 — sin matplotlib: Helvetica (sin Δ/π)
        return "Helvetica", "Helvetica-Bold"


def generar_pdf(datos, salida, figuras_dir):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from xml.sax.saxutils import escape as esc

    F, FB = _fuentes()
    W, H = letter
    margen = 2.0 * cm
    st = {
        "h1": ParagraphStyle("h1", fontName=FB, fontSize=15, leading=19, textColor=colors.HexColor(INK),
                             spaceBefore=6, spaceAfter=8, keepWithNext=1),
        "h2": ParagraphStyle("h2", fontName=FB, fontSize=11.5, leading=15, textColor=colors.HexColor(ACCENT),
                             spaceBefore=10, spaceAfter=5, keepWithNext=1),
        "p": ParagraphStyle("p", fontName=F, fontSize=9.5, leading=13.5, textColor=colors.HexColor(INK),
                            alignment=TA_LEFT, spaceAfter=5),
        "small": ParagraphStyle("small", fontName=F, fontSize=8, leading=10.5, textColor=colors.HexColor(MUTED)),
        "cell": ParagraphStyle("cell", fontName=F, fontSize=8.2, leading=10.5, textColor=colors.HexColor(INK)),
        "cellb": ParagraphStyle("cellb", fontName=FB, fontSize=8.2, leading=10.5, textColor=colors.HexColor(INK)),
        "celln": ParagraphStyle("celln", fontName=F, fontSize=8.2, leading=10.5, textColor=colors.HexColor(INK),
                                alignment=2),
        "cellnb": ParagraphStyle("cellnb", fontName=FB, fontSize=8.2, leading=10.5, textColor=colors.HexColor(INK),
                                 alignment=2),
        "ref": ParagraphStyle("ref", fontName=F, fontSize=8.2, leading=11, textColor=colors.HexColor(INK),
                              leftIndent=14, firstLineIndent=-14, spaceAfter=3),
    }

    def P_(t, s="p"):
        return Paragraph(t, st[s])

    def tabla(encabezado, filas, anchos=None, num_cols=(), resaltar=None, pad=None):
        data = [[P_(f"<b>{esc(str(h)).replace(chr(10), '<br/>')}</b>", "cellnb" if j in num_cols else "cellb")
                 for j, h in enumerate(encabezado)]]
        for fila in filas:
            data.append([c if isinstance(c, Paragraph) else P_(esc(str(c)), "celln" if j in num_cols else "cell")
                         for j, c in enumerate(fila)])
        t = Table(data, colWidths=anchos, repeatRows=1, hAlign="LEFT")
        estilo = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(SOFT)),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(ACCENT)),
                  ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(RULE)),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if pad is not None:  # tablas densas: menos relleno lateral
            estilo += [("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad)]
        if resaltar is not None:
            for r in resaltar:
                estilo.append(("BACKGROUND", (0, r + 1), (-1, r + 1), colors.HexColor("#FCE8F1")))
        t.setStyle(TableStyle(estilo))
        return t

    def img(ruta, ancho, dpi=None):
        """Con dpi (figuras de matplotlib a 200 dpi) se usa el tamaño físico de la figura,
        limitado a `ancho`; sin dpi, se escala a `ancho`."""
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(ruta).getSize()
        if dpi:
            ancho = min(ancho, iw / dpi * 2.54 * cm)
        return Image(ruta, width=ancho, height=ancho * ih / iw)

    def n(x, nd=2):
        v = _f(x)
        return "—" if v is None else f"{v:.{nd}f}"

    logo = datos.get("logo")
    logo = logo if logo and os.path.exists(os.path.expanduser(logo)) else None
    if logo:
        logo = os.path.expanduser(logo)

    class Lienzo(rl_canvas.Canvas):
        """Encabezado/pie en todas las páginas y 'página X de Y' (dos pasadas)."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._paginas = []

        def showPage(self):  # noqa: N802
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._decorar(total)
                super().showPage()
            super().save()

        def _decorar(self, total):
            pag = self._pageNumber
            self.saveState()
            # banda superior
            self.setFillColor(colors.HexColor(ACCENT))
            self.rect(0, H - 0.35 * cm, W, 0.35 * cm, stroke=0, fill=1)
            if pag > 1:
                self.setFont(FB, 9)
                self.setFillColor(colors.HexColor(ACCENT))
                self.drawString(margen, H - 1.15 * cm, "AXOLOTL DOCKING")
                self.setFont(F, 8)
                self.setFillColor(colors.HexColor(MUTED))
                self.drawRightString(W - margen, H - 1.15 * cm, f"{datos['proyecto']} · reporte de docking")
                self.setStrokeColor(colors.HexColor(RULE))
                self.setLineWidth(0.5)
                self.line(margen, H - 1.35 * cm, W - margen, H - 1.35 * cm)
            # pie
            self.setStrokeColor(colors.HexColor(RULE))
            self.line(margen, 1.45 * cm, W - margen, 1.45 * cm)
            self.setFont(F, 7.5)
            self.setFillColor(colors.HexColor(MUTED))
            pie = f"Generado con Axolotl Docking v{datos['version']} · {datos['fecha']}"
            if datos.get("laboratorio"):
                pie = f"{datos['laboratorio']} · " + pie
            self.drawString(margen, 1.0 * cm, pie)
            self.drawRightString(W - margen, 1.0 * cm, f"Página {pag} de {total}")
            self.restoreState()

    os.makedirs(figuras_dir, exist_ok=True)
    historia = []
    contador = [0]

    def sec(titulo):
        contador[0] += 1
        return f"{contador[0]}. {titulo}"

    # ------------------------------------------------ portada
    historia.append(Spacer(1, 1.2 * cm))
    cab = []
    if logo:
        cab.append(img(logo, 4.2 * cm))
    marca = Paragraph(f"<font name='{FB}' size='20' color='{ACCENT}'>AXOLOTL DOCKING</font><br/>"
                      f"<font name='{F}' size='9' color='{MUTED}'>Docking molecular · reporte automático</font>",
                      ParagraphStyle("m", leading=24))
    t = Table([[cab[0] if cab else "", marca]], colWidths=[5 * cm, None], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    historia.append(t)
    historia.append(Spacer(1, 2.2 * cm))
    historia.append(Paragraph("Reporte de docking molecular",
                              ParagraphStyle("t", fontName=FB, fontSize=24, leading=30,
                                             textColor=colors.HexColor(INK))))
    historia.append(Paragraph(esc(datos["proyecto"]), ParagraphStyle("s", fontName=F, fontSize=15, leading=20,
                                                                      textColor=colors.HexColor(ACCENT),
                                                                      spaceAfter=18)))
    meta = [["Fecha", datos["fecha"]], ["Motor de docking", MOTOR_NOMBRE.get(datos["motor"], datos["motor"])],
            ["Dianas", str(len(datos["dianas"]))],
            ["Ligandos / controles", f"{sum(1 for l in datos['ligandos'] if not l['control'])} / "
                                     f"{sum(1 for l in datos['ligandos'] if l['control'])}"],
            ["Semillas por par", str(len(datos["docking"].get("seeds", [])))]]
    if datos.get("consenso"):
        meta.append(["Consenso", f"{len(datos['consenso']['motores'])} motores (ECR + acuerdo de poses)"])
    if datos.get("laboratorio"):
        meta.insert(0, ["Laboratorio", datos["laboratorio"]])
    if datos.get("autor"):
        meta.insert(1 if datos.get("laboratorio") else 0, ["Responsable", datos["autor"]])
    mt = Table([[P_(f"<font color='{MUTED}'>{esc(a)}</font>", "cell"), P_(esc(b), "cellb")] for a, b in meta],
               colWidths=[4.5 * cm, 10 * cm], hAlign="LEFT")
    mt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor(RULE)),
                            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    historia.append(mt)
    historia.append(Spacer(1, 1.2 * cm))
    historia.append(P_("Las afinidades de docking son estimaciones computacionales de la energía libre de unión; "
                       "sirven para comparar y priorizar compuestos y no sustituyen la validación experimental.",
                       "small"))
    historia.append(PageBreak())

    # ------------------------------------------------ 1. resumen ejecutivo
    historia.append(P_(sec("Resumen ejecutivo"), "h1"))
    filas = []
    for r in datos["resumen"]:
        ctrl = "—"
        if r["control"]:
            ctrl = f"{r['control']} ({n(r['dg_control'])})" + (" · superado" if r["supera_control"] else "")
        red = "—" if r["redock_rmsd_min"] is None else (
            f"{r['redock_rmsd_min']:.2f} Å " + ("✔ válido" if r["redock_rmsd_min"] <= 2 else "✘ revisar"))
        filas.append([r["diana"], r["mejor"] or "sin resultados",
                      "—" if r["dg"] is None else f"{r['dg']:.2f} ± {r['de'] or 0:.2f}", ctrl, red])
    historia.append(tabla(["Diana", "Mejor ligando", "ΔG media (kcal/mol)", "Control", "Redocking (RMSD mín.)"],
                          filas, [3 * cm, 3.6 * cm, 3.4 * cm, 3.6 * cm, 3.6 * cm], num_cols=(2,)))
    if datos.get("consenso"):
        cv = datos["consenso"]["veredictos"]
        historia.append(P_("<b>Consenso entre motores:</b> " + ", ".join(
            esc(datos["consenso"]["nombres"][m]) for m in datos["consenso"]["motores"]) + ". Veredictos por ligando: " +
            " · ".join(f"{esc(k)} {v}" for k, v in cv.items()) + ". Detalle en la sección «Consenso entre motores».",
            "small"))
    if datos["pasos"]:
        historia.append(P_("Pasos de la corrida", "h2"))
        marca_estado = {"ok": f"<font color='{OK}'>✔ completado</font>",
                        "error": f"<font color='{ERR}'>✘ con problemas</font>",
                        "en_curso": "en curso", "pendiente": "no se ejecutó", "interrumpido":
                        f"<font color='{ERR}'>✘ interrumpido</font>"}
        filas = []
        for i, p in enumerate(datos["pasos"], 1):
            if p.get("id") == "report":
                continue
            seg = p.get("segundos")
            dur = "—" if seg is None else (f"{seg:.0f} s" if seg < 60 else f"{seg / 60:.1f} min")
            filas.append([str(i), p.get("titulo", p.get("id")), P_(marca_estado.get(p.get("estado"), "—"), "cell"),
                          dur])
        historia.append(tabla(["#", "Paso", "Estado", "Duración"], filas, [0.8 * cm, 10.6 * cm, 3.4 * cm, 2.4 * cm],
                              num_cols=(3,)))

    # ------------------------------------------------ 2. métodos
    historia.append(P_(sec("Métodos"), "h1"))
    for parrafo in texto_metodos(datos):
        historia.append(P_(esc(parrafo)))

    # ------------------------------------------------ 3. dianas
    historia.append(P_(sec("Dianas y cajas de docking"), "h1"))
    filas = []
    for t in datos["dianas"]:
        b = datos["cajas"].get(t["id"], {}) or {}
        c, s = b.get("center"), b.get("size")
        filas.append([t["id"], FUENTE_NOMBRE.get(t.get("source"), t.get("source", "")) +
                      (f" {t['pdb']}" if t.get("pdb") else ""),
                      str(t.get("chains", "")).replace("[", "").replace("]", "").replace("'", "") or "todas",
                      b.get("mode", (t.get("box") or {}).get("mode", "—")),
                      ", ".join(f"{v:.1f}" for v in c) if c else "—",
                      " × ".join(f"{v:.0f}" for v in s) + " Å" if s else "—"])
    historia.append(tabla(["Diana", "Fuente", "Cadenas", "Caja", "Centro (x, y, z)", "Tamaño"], filas,
                          [2.4 * cm, 4.2 * cm, 2.2 * cm, 1.8 * cm, 3.6 * cm, 3.2 * cm]))

    # ------------------------------------------------ 4. ligandos
    historia.append(P_(sec("Ligandos y controles"), "h1"))
    celdas = []
    for lig in datos["ligandos"]:
        ruta = figura_ligando_2d(lig, os.path.join(figuras_dir, f"ligando_{lig['id']}.png"))
        texto = P_(f"<b>{esc(lig['nombre'])}</b>{' ◆ control' if lig['control'] else ''}<br/>"
                   f"<font color='{MUTED}'>{esc(FUENTE_NOMBRE.get(lig['fuente'], lig['fuente']))}"
                   f"{(': ' + esc(str(lig['consulta']))) if lig['consulta'] else ''}</font>", "cell")
        celdas.append([img(ruta, 5.0 * cm) if ruta else P_("(sin estructura 2D)", "small"), texto])
    if celdas:
        grid = [celdas[i:i + 3] for i in range(0, len(celdas), 3)]
        filas_tabla = []
        for fila in grid:
            filas_tabla.append([c[0] for c in fila] + [""] * (3 - len(fila)))
            filas_tabla.append([c[1] for c in fila] + [""] * (3 - len(fila)))
        tl = Table(filas_tabla, colWidths=[5.6 * cm] * 3, hAlign="LEFT")
        tl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        historia.append(tl)

    # ------------------------------------------------ 5. validación
    if datos["redocking"]:
        historia.append(P_(sec("Validación por redocking"), "h1"))
        historia.append(P_("Se redockeó el ligando co-cristalizado en su propio receptor; un RMSD ≤ 2.0 Å de la mejor "
                           "pose indica que el protocolo reproduce la pose experimental."))
        filas = [[r.get("diana", ""), r.get("semilla", ""), n(r.get("afinidad")), n(r.get("rmsd")),
                  P_(f"<font color='{OK}'>✔ válido</font>" if (_f(r.get("rmsd")) or 99) <= 2
                     else f"<font color='{ERR}'>✘ revisar</font>", "cell")] for r in datos["redocking"]]
        historia.append(tabla(["Diana", "Semilla", "ΔG (kcal/mol)", "RMSD (Å)", "Resultado"], filas,
                              [3.6 * cm, 2.4 * cm, 3.2 * cm, 2.6 * cm, 3.0 * cm], num_cols=(1, 2, 3)))

    # ------------------------------------------------ resultados
    historia.append(P_(sec("Afinidades de unión"), "h1"))
    historia.append(P_("ΔG en kcal/mol (media ± desviación estándar entre semillas); más negativo indica mayor "
                       "afinidad predicha. LE: eficiencia de ligando. Δ control negativo: el ligando supera al "
                       "control. ◆ = control. En rosa, el mejor ligando de cada diana."))
    for diana, fs in datos["afinidades"].items():
        historia.append(P_(f"Diana {esc(diana)}", "h2"))
        filas = [[f.get("ligando", "") + (" ◆" if f.get("tipo") == "control" else ""),
                  f"{n(f.get('afinidad_media'))} ± {n(f.get('afinidad_de'))}", n(f.get("mejor")),
                  n(f.get("LE", f.get("le")), 3),
                  "—" if _f(f.get("delta_vs_control")) is None else f"{_f(f['delta_vs_control']):+.2f}",
                  f.get("n_semillas", "")] for f in fs]
        mejor = next((i for i, f in enumerate(fs) if f.get("tipo") != "control"), None)
        bloque = [tabla(["Ligando", "ΔG media ± DE", "Mejor", "LE", "Δ control", "Semillas"], filas,
                        [5.2 * cm, 3.2 * cm, 2.2 * cm, 2.0 * cm, 2.4 * cm, 2.0 * cm], num_cols=(1, 2, 3, 4, 5),
                        resaltar=[mejor] if mejor is not None else None)]
        fig = figura_afinidades(diana, fs, os.path.join(figuras_dir, f"afinidades_{diana}.png"))
        if fig:
            bloque += [Spacer(1, 6), img(fig, 15.5 * cm, dpi=200)]
        historia.append(KeepTogether(bloque))
    if not datos["afinidades"]:
        historia.append(P_("Aún no hay resultados de afinidad (pasos de docking y resumen).", "small"))
    fig = figura_matriz(datos["matriz"], os.path.join(figuras_dir, "matriz_ligando_diana.png"))
    if fig:
        historia.append(KeepTogether([P_("Matriz ligando × diana", "h2"), img(fig, 15.5 * cm, dpi=200)]))

    # ------------------------------------------------ consenso entre motores
    cons = datos.get("consenso")
    if cons:
        mot, nom = cons["motores"], cons["nombres"]
        historia.append(P_(sec("Consenso entre motores"), "h1"))
        historia.append(P_(
            "Un ligando es un candidato más fiable cuando motores con funciones de puntuación distintas lo "
            "colocan de forma parecida. Aquí se comparan " + ", ".join(esc(nom[m]) for m in mot) + ". «#» es el "
            "rango del ligando en ese motor dentro de la diana (1 = mejor afinidad); «ECR #» es su posición por "
            "consenso exponencial de rangos; «Disp.» es la diferencia entre su mejor y su peor rango; «RMSD máx» "
            "es la mayor distancia, en Å, entre las mejores poses de dos motores. Las "
            "energías de motores distintos no son comparables entre sí en valor absoluto: se comparan los "
            "órdenes y las poses."))
        cuenta = cons["veredictos"]
        historia.append(P_("Veredictos: " + " · ".join(f"<b>{esc(k)}</b> {v}" for k, v in cuenta.items()) +
                           f". Robusto = rangos y poses coinciden; Parcial = coincide sólo uno; Discrepante = no "
                           f"coincide ninguno (umbrales: dispersión normalizada ≤ "
                           f"{cons['meta'].get('umbrales', {}).get('dispersion', 0.25)}, RMSD ≤ "
                           f"{cons['meta'].get('umbrales', {}).get('rmsd', 2.0)} Å).", "small"))
        if cons["tiempos"]:
            ft = []
            for t in cons["tiempos"]:
                seg = _f(t.get("segundos"))
                ft.append([t.get("nombre", t.get("motor", "")), f"{t.get('corridas_ok', '')}/{t.get('corridas_totales', '')}",
                           "—" if seg is None else (f"{seg:.0f} s" if seg < 60 else f"{seg / 60:.1f} min")])
            historia.append(P_("Corridas y tiempo por motor", "h2"))
            historia.append(tabla(["Motor", "Corridas completas", "Tiempo de cómputo"], ft,
                                  [6.5 * cm, 4.5 * cm, 4.5 * cm], num_cols=(1, 2)))
            historia.append(P_("El tiempo del motor principal no se mide en este paso (se ve en «Pasos de la "
                               "corrida»). Los tiempos se acumulan si el paso se reanudó.", "small"))
        colv = {"Robusto": OK, "Parcial": "#B7860B", "Discrepante": ERR, "Incompleto": MUTED}
        for diana, fs in cons["filas"].items():
            ncol = len(mot)
            corto = {"vina": "Vina", "vinardo": "Vinardo", "ad4": "AD4"}
            ancho_lig, a_ecr, a_disp, a_rmsd, a_ver = 2.5 * cm, 1.1 * cm, 1.1 * cm, 1.3 * cm, 2.3 * cm
            ancho_m = (17.4 * cm - ancho_lig - a_ecr - a_disp - a_rmsd - a_ver) / (2 * ncol)
            filas = []
            for f in fs:
                v = f.get("veredicto", "")
                filas.append([f.get("ligando", "") + (" ◆" if f.get("tipo") == "control" else "")]
                             + [n(f.get(f"dG_{m}")) for m in mot]
                             + ["—" if _f(f.get(f"rango_{m}")) is None else f"{_f(f.get(f'rango_{m}')):g}" for m in mot]
                             + [f.get("orden") or "—", n(f.get("dispersion_rangos"), 1), n(f.get("rmsd_max"), 1),
                                P_(f"<font color='{colv.get(v, INK)}'><b>{esc(v)}</b></font>", "cell")])
            cab = ["Ligando"] + [f"ΔG\n{corto.get(m, m)}" for m in mot] + [f"#\n{corto.get(m, m)}" for m in mot] \
                + ["ECR #", "Disp.", "RMSD\nmáx", "Veredicto"]
            anchos = [ancho_lig] + [ancho_m] * (2 * ncol) + [a_ecr, a_disp, a_rmsd, a_ver]
            bloque = [P_(f"Diana {esc(diana)}", "h2"),
                      tabla(cab, filas, anchos, num_cols=tuple(range(1, 2 * ncol + 4)), pad=3)]
            fig = figura_consenso(diana, fs, mot, nom, cons["tau"].get(diana, {}),
                                  os.path.join(figuras_dir, f"consenso_{diana}.png"))
            if fig:
                bloque += [Spacer(1, 6), img(fig, 16.0 * cm, dpi=200)]
            incompletos = [f for f in fs if f.get("veredicto") == "Incompleto"]
            if incompletos:
                bloque.append(P_("Fuera del consenso por falta de resultado: " + "; ".join(
                    f"{esc(f.get('ligando', ''))} ({esc(f.get('motivo', ''))})" for f in incompletos), "small"))
            historia.append(KeepTogether(bloque))
        # acuerdo de poses entre motores
        pares = {}
        for r in cons["poses"]:
            v = _f(r.get("rmsd"))
            if v is not None:
                pares.setdefault((r.get("motor_a"), r.get("motor_b")), []).append(v)
        if pares:
            historia.append(P_("Acuerdo de poses entre motores", "h2"))
            fp = [[f"{nom.get(a, a)} ↔ {nom.get(b, b)}", f"{sum(v) / len(v):.2f}", f"{max(v):.2f}",
                   f"{sum(1 for x in v if x <= 2.0)}/{len(v)}"] for (a, b), v in pares.items()]
            historia.append(tabla(["Par de motores", "RMSD medio (Å)", "RMSD máx (Å)", "Pares con RMSD ≤ 2 Å"], fp,
                                  [7.0 * cm, 3.2 * cm, 3.2 * cm, 3.6 * cm], num_cols=(1, 2, 3)))
        # redocking por motor
        rd = {}
        for r in cons["redocking"]:
            v = _f(r.get("rmsd"))
            if v is not None:
                rd.setdefault((r.get("motor"), r.get("diana")), []).append(v)
        if rd:
            historia.append(P_("Redocking por motor", "h2"))
            historia.append(P_("RMSD de la mejor pose del ligando cristalográfico frente a la pose experimental. Un "
                               "motor que no la reproduce en una diana merece menos peso al leer el consenso en "
                               "esa diana.", "small"))
            fr = [[nom.get(m, m), d, f"{min(v):.2f}", f"{sum(v) / len(v):.2f}",
                   P_(f"<font color='{OK}'>✔ válido</font>" if min(v) <= 2 else f"<font color='{ERR}'>✘ revisar</font>",
                      "cell")] for (m, d), v in sorted(rd.items(), key=lambda kv: (kv[0][1] or "", kv[0][0] or ""))]
            historia.append(tabla(["Motor", "Diana", "RMSD mín (Å)", "RMSD medio (Å)", "Resultado"], fr,
                                  [4.6 * cm, 3.2 * cm, 3.0 * cm, 3.2 * cm, 3.0 * cm], num_cols=(2, 3)))

    # ------------------------------------------------ 7. interacciones
    if datos["interacciones"]:
        historia.append(P_(sec("Interacciones proteína–ligando (mejor pose)"), "h1"))
        for r in datos["interacciones"]:
            dia, lig = r.get("diana", ""), r.get("ligando", "")
            det = [x for x in datos["interacciones_detalle"] if x.get("diana") == dia and x.get("ligando") == lig]
            det.sort(key=lambda x: (x.get("tipo", ""), _f(x.get("distancia")) or 0))
            bloque = [P_(f"{esc(dia)} + {esc(lig)} · {r.get('total', len(det))} contactos", "h2")]
            comp = r.get("complejo") or ""
            complejo = comp if os.path.isabs(comp) else os.path.join(datos.get("_root", ""), comp)
            fig = figura_complejo(complejo, os.path.join(figuras_dir, f"complejo_{dia}__{lig}.png"), figuras_dir,
                                  f"{dia}__{lig}")
            tabla_det = tabla(["Tipo", "Residuo", "Cad.", "Dist. (Å)"],
                              [[x.get("tipo", ""), x.get("residuo", ""), x.get("cadena", ""), n(x.get("distancia"))]
                               for x in det] or [["—", "", "", ""]],
                              [3.4 * cm, 2.2 * cm, 1.5 * cm, 1.8 * cm], num_cols=(3,))
            if fig:
                fila = Table([[img(fig, 8.0 * cm), tabla_det]], colWidths=[8.4 * cm, None], hAlign="LEFT")
                fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
                bloque.append(fila)
            else:
                bloque.append(tabla_det)
            if r.get("residuos"):
                bloque.append(P_(f"Residuos en contacto: {esc(r['residuos'])}", "small"))
            historia.append(KeepTogether(bloque))

    # ------------------------------------------------ 8. problemas
    problemas = [(p.get("titulo", p.get("id")), e) for p in datos["pasos"] if p.get("id") != "report"
                 for e in p.get("errores", [])[:15]]
    if problemas:
        historia.append(P_(sec("Problemas registrados"), "h1"))
        historia.append(P_("Mensajes de error capturados durante la corrida (el log completo está en "
                           "04_Docking/logs/)."))
        historia.append(tabla(["Paso", "Mensaje"], [[a, b.strip()] for a, b in problemas],
                              [5.0 * cm, 12.0 * cm]))

    # ------------------------------------------------ 9. entorno
    historia.append(P_(sec("Entorno de cómputo y reproducibilidad"), "h1"))
    filas = [[k, v] for k, v in datos["versiones"].items()]
    hw = datos.get("hardware") or {}
    if hw:
        filas += [["Sistema", hw.get("sistema", "")], ["CPU", f"{hw.get('cpu', '')} · {hw.get('nucleos', '')} "
                                                               "núcleos disponibles"],
                  ["GPU", hw.get("gpu", "—")]]
    filas += [["Motor", MOTOR_NOMBRE.get(datos["motor"], datos["motor"])],
              ["Parámetros de docking", parametros_legibles(datos)]]
    historia.append(tabla(["Componente", "Versión / valor"], filas, [5.0 * cm, 12.0 * cm]))

    # ------------------------------------------------ 10. referencias
    historia.append(P_(sec("Referencias"), "h1"))
    for i, ref in enumerate(referencias(datos), 1):
        historia.append(P_(f"{i}. {esc(ref)}", "ref"))

    doc = SimpleDocTemplate(salida + ".part", pagesize=letter, leftMargin=margen, rightMargin=margen,
                            topMargin=2.0 * cm, bottomMargin=2.0 * cm, title=f"Reporte de docking · {datos['proyecto']}",
                            author=datos.get("autor") or datos.get("laboratorio") or "Axolotl Docking",
                            subject="Reporte de docking molecular", creator=f"Axolotl Docking v{datos['version']}")
    doc.build(historia, canvasmaker=Lienzo)
    os.replace(salida + ".part", salida)
    return salida


def _nombre_seguro(t):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", t).strip("_") or "proyecto"


# ================================================================ paso
def run(P, rehacer=False):
    title("8 · Reporte PDF")
    try:
        import reportlab  # noqa: F401
    except ImportError:
        log("  ✘ Falta ReportLab para generar el PDF. Instálalo en el entorno:  conda install -c conda-forge "
            "reportlab   (o corre 'Docking entorno').")
        return 1
    datos = recolectar(P)
    datos["_root"] = P.root
    os.makedirs(P.layout.report_dir(), exist_ok=True)
    sello = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    salida = os.path.join(P.layout.report_dir(), f"{_nombre_seguro(datos['proyecto'])}_reporte_{sello}.pdf")
    try:
        generar_pdf(datos, salida, P.layout.figures_dir())
    except Exception as e:  # noqa: BLE001
        log(f"  ✘ No se pudo generar el reporte: {e}")
        return 1
    ultimo = os.path.join(P.layout.report_dir(), "reporte_ultimo.pdf")
    try:
        shutil.copy(salida, ultimo)
    except OSError:
        pass
    log(f"  ✔ Reporte: {P.rel(salida)}  (figuras en {P.rel(P.layout.figures_dir())})")
    return 0


if __name__ == "__main__":  # uso directo: python pipeline/report.py <proyecto>
    import common
    sys.exit(run(common.Project(sys.argv[1])))
