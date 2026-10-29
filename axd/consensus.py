"""Modo consenso (avanzado): varios motores de docking sobre los mismos pares ligando–diana.

Idea: un ligando es un candidato fiable si motores con funciones de puntuación DISTINTAS
coinciden, no sólo si uno le da buena energía. Este módulo es puro (sin RDKit ni smina):
recibe afinidades y RMSD ya calculados y devuelve el análisis, para poder probarlo y
reutilizarlo desde el pipeline, la GUI y el reporte.

Método de consenso de rangos: ECR (Exponential Consensus Ranking, Palacio-Rodríguez et al.,
Sci Rep 2019). Para cada ligando i y cada motor j con rango r_ij (1 = mejor afinidad):

    ECR(i) = Σ_j (1/σ) · exp(−r_ij / σ)        σ = 10 % del número de ligandos

Se ordena de mayor a menor ECR. Una sola métrica de rangos no basta para llamar «robusto» a un
resultado, así que se añade el acuerdo de poses (RMSD entre las mejores poses de cada par de
motores; Houston y Walkinshaw, 2013) y un veredicto por ligando.

Motores (funciones de puntuación distintas = «familias» independientes):
  vina     el motor principal del proyecto (smina con la función Vina, o Vina-GPU)
  vinardo  smina con --scoring vinardo (Quiroga y Villarreal, 2016)
  ad4      AutoDock4 (campo de fuerzas semiempírico propio)
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- catálogo
ENGINES = {
    "vina": {"nombre": "Vina (smina)", "ref": "Trott y Olson, 2010"},
    "vinardo": {"nombre": "Vinardo (smina)", "ref": "Quiroga y Villarreal, 2016"},
    "ad4": {"nombre": "AutoDock4", "ref": "Morris et al., 2009"},
}
DEFAULT_ENGINES = ["vina", "vinardo", "ad4"]

# Umbrales del veredicto (se documentan en el reporte)
RMSD_OK = 2.0          # Å: dos motores «coinciden» en la pose si su RMSD es ≤ 2 Å
SPREAD_OK = 0.25       # dispersión de rangos normalizada (máx − mín)/(N − 1) ≤ 0.25
MIN_LIGANDOS_RANGO = 3  # con menos ligandos un ranking no dice nada

ROBUSTO, PARCIAL, DISCREPANTE = "Robusto", "Parcial", "Discrepante"
INCOMPLETO, SIN_DATOS = "Incompleto", "Sin datos"


def nombre_motor(clave: str, principal: str | None = None) -> str:
    """Nombre legible; el motor «vina» cambia de nombre si el proyecto usa la GPU."""
    if clave == "vina" and principal == "vina-gpu":
        return "Vina-GPU"
    return ENGINES.get(clave, {}).get("nombre", clave)


def motores_validos(motores) -> list[str]:
    """Sólo motores conocidos, sin repetir y en un orden estable."""
    vistos = [m for m in dict.fromkeys(motores or []) if m in ENGINES]
    return [m for m in ENGINES if m in vistos]


def pares_del_proyecto(p: dict) -> int:
    """Pares ligando–diana (controles incluidos) de un proyecto, para estimar el trabajo."""
    n = 0
    for t in p.get("targets", []):
        n += len(p.get("ligands", [])) + sum(1 for c in p.get("controls", [])
                                             if not c.get("target") or c.get("target") == t["id"])
    return n


def corridas_extra(n_pares: int, n_semillas: int, motores, principal_ya_corre: bool = True) -> dict:
    """Cuántas corridas adicionales pide el consenso (el motor principal ya se ejecutó
    en el paso de docking, así que 'vina' no suma)."""
    extra = [m for m in motores_validos(motores) if not (m == "vina" and principal_ya_corre)]
    return {m: n_pares * n_semillas for m in extra}


# ---------------------------------------------------------------- rangos y ECR
def rangos(valores: dict) -> dict:
    """Rangos 1..N (1 = menor afinidad, o sea, mejor). Empates → rango medio.
    Los valores None se ignoran."""
    ok = sorted((v, k) for k, v in valores.items() if v is not None)
    out, i = {}, 0
    while i < len(ok):
        j = i
        while j + 1 < len(ok) and ok[j + 1][0] == ok[i][0]:
            j += 1
        medio = (i + j) / 2 + 1
        for _v, k in ok[i:j + 1]:
            out[k] = medio
        i = j + 1
    return out


def sigma_ecr(n: int) -> float:
    """σ = 10 % de N (Palacio-Rodríguez et al.). Con pocos ligandos se fija un mínimo de 1
    para que el rango 1 no pese infinitamente más que el 2: es una adaptación a proyectos
    pequeños, no parte del método original."""
    return max(1.0, 0.1 * n)


def ecr(rangos_por_motor: list, sigma: float) -> float:
    return sum(math.exp(-r / sigma) / sigma for r in rangos_por_motor)


def kendall_tau(a: dict, b: dict) -> float | None:
    """τ-b de Kendall entre dos rankings (dicts ligando → valor). None si no hay ≥ 3 en común
    o si uno de los dos no discrimina nada."""
    claves = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    if len(claves) < MIN_LIGANDOS_RANGO:
        return None
    conc = disc = ta = tb = 0
    for i in range(len(claves)):
        for j in range(i + 1, len(claves)):
            da = a[claves[i]] - a[claves[j]]
            db = b[claves[i]] - b[claves[j]]
            if da == 0 and db == 0:
                continue
            if da == 0:
                ta += 1
            elif db == 0:
                tb += 1
            elif (da > 0) == (db > 0):
                conc += 1
            else:
                disc += 1
    den = math.sqrt((conc + disc + ta) * (conc + disc + tb))
    return None if den == 0 else (conc - disc) / den


# ---------------------------------------------------------------- RMSD sin realinear
def rmsd_ordenado(a, b) -> float | None:
    """RMSD (Å) entre dos listas de (x, y, z) con los mismos átomos en el mismo orden.
    Es una cota superior del RMSD con simetría; el pipeline intenta primero la versión
    simétrica de RDKit y recurre a ésta si no se puede."""
    if not a or len(a) != len(b):
        return None
    s = sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 for p, q in zip(a, b))
    return math.sqrt(s / len(a))


# ---------------------------------------------------------------- veredicto
def veredicto(spread_norm, rmsd_max) -> tuple[str, str]:
    """(veredicto, motivo). Se evalúan los criterios disponibles: todos cumplidos → Robusto;
    ninguno → Discrepante; mezcla → Parcial."""
    criterios, partes = [], []
    if spread_norm is not None:
        ok = spread_norm <= SPREAD_OK
        criterios.append(ok)
        partes.append(f"rangos {'coinciden' if ok else 'difieren'} (dispersión {spread_norm:.2f})")
    if rmsd_max is not None:
        ok = rmsd_max <= RMSD_OK
        criterios.append(ok)
        partes.append(f"poses {'coinciden' if ok else 'difieren'} (RMSD máx {rmsd_max:.1f} Å)")
    if not criterios:
        return SIN_DATOS, "no hay suficientes ligandos ni poses para comparar"
    if all(criterios):
        return ROBUSTO, "; ".join(partes)
    if not any(criterios):
        return DISCREPANTE, "; ".join(partes)
    return PARCIAL, "; ".join(partes)


# ---------------------------------------------------------------- análisis completo
def analizar(medias: dict, tipos: dict, motores, rmsd: dict | None = None) -> dict:
    """medias: {(diana, ligando): {motor: afinidad media o None}}
    tipos:  {(diana, ligando): 'ligando' | 'control'}
    rmsd:   {(diana, ligando): {(motor_a, motor_b): Å}}   (opcional)
    Devuelve {'motores': [...], 'filas': [...], 'tau': {diana: {(a, b): τ}}, 'sigma': {diana: σ}}.

    Sólo entran al ranking de consenso los ligandos que TODOS los motores resolvieron en esa
    diana: con motores faltantes los ECR no serían comparables. Los demás quedan «Incompleto»."""
    motores = motores_validos(motores)
    rmsd = rmsd or {}
    filas, tau, sigmas = [], {}, {}
    por_diana: dict = {}
    for (diana, lig), v in medias.items():
        por_diana.setdefault(diana, []).append(lig)
    for diana, ligs in por_diana.items():
        completos = [l for l in ligs if all(medias[(diana, l)].get(m) is not None for m in motores)]
        rk = {m: rangos({l: medias[(diana, l)][m] for l in completos}) for m in motores}
        n = len(completos)
        sigma = sigma_ecr(n)
        sigmas[diana] = sigma
        puntaje = {l: ecr([rk[m][l] for m in motores], sigma) for l in completos}
        orden = sorted(completos, key=lambda l: -puntaje[l])
        rk_cons = rangos({l: -puntaje[l] for l in completos})
        tau[diana] = {(a, b): kendall_tau({l: medias[(diana, l)][a] for l in completos},
                                          {l: medias[(diana, l)][b] for l in completos})
                      for i, a in enumerate(motores) for b in motores[i + 1:]}
        for lig in ligs:
            fila = {"diana": diana, "ligando": lig, "tipo": tipos.get((diana, lig), "ligando"),
                    "n_motores": sum(1 for m in motores if medias[(diana, lig)].get(m) is not None)}
            for m in motores:
                fila[f"dG_{m}"] = medias[(diana, lig)].get(m)
            if lig in rk_cons:
                rs = [rk[m][lig] for m in motores]
                spread = (max(rs) - min(rs)) / (n - 1) if n >= MIN_LIGANDOS_RANGO else None
                pares = [v for v in rmsd.get((diana, lig), {}).values() if v is not None]
                rmax = max(pares) if pares else None
                ver, motivo = veredicto(spread, rmax)
                for m in motores:
                    fila[f"rango_{m}"] = rk[m][lig]
                fila.update(ecr=puntaje[lig], rango_consenso=rk_cons[lig], orden=orden.index(lig) + 1,
                            dispersion_rangos=max(rs) - min(rs), dispersion_norm=spread, rmsd_max=rmax,
                            veredicto=ver, motivo=motivo)
            else:
                faltan = [nombre_motor(m) for m in motores if medias[(diana, lig)].get(m) is None]
                fila.update(veredicto=INCOMPLETO, motivo="sin resultado en: " + ", ".join(faltan))
            filas.append(fila)
    filas.sort(key=lambda f: (f["diana"], f.get("orden", 10 ** 9), f["ligando"]))
    return {"motores": motores, "filas": filas, "tau": tau, "sigma": sigmas}


def resumen_veredictos(filas) -> dict:
    out = {}
    for f in filas:
        out[f["veredicto"]] = out.get(f["veredicto"], 0) + 1
    return out
