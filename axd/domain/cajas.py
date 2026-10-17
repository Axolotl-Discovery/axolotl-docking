"""Clases polimórficas para cada modo de caja de docking (Fase 3).

Reemplazan la cadena if/elif por 'modo' que había en pipeline/receptores.py. Cada Caja
calcula su propio centro/tamaño a partir de las líneas PDB ya filtradas que le pasa
ContextoCaja — no hace I/O ni conoce rutas de archivo, así que se puede probar aparte
del resto del paso 'receptores'."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ContextoCaja:
    """Lo que cada Caja necesita para calcularse, ya resuelto por receptores.py."""
    cuerpo: list       # líneas ATOM del receptor limpio (+ TER)
    cof: list          # líneas HETATM de los cofactores conservados
    ref: list          # líneas HETATM del ligando de referencia (sólo se llena en modo 'ligando')
    caja_fn: Callable  # _caja(coords, margen, minimo=0.0) -> (center, size)
    xyz_fn: Callable   # _xyz(lineas, sin_h=True) -> coords


@dataclass
class ResultadoCaja:
    ok: bool
    center: list[float] | None = None
    size: list[float] | None = None
    detalle: str = ""
    error: str = ""   # fatal: el paso falla para esta diana
    aviso: str = ""   # no fatal: se loguea pero se sigue


class Caja:
    modo: str = ""

    def calcular(self, ctx: ContextoCaja) -> ResultadoCaja:
        raise NotImplementedError

    @staticmethod
    def crear(caja_cfg: dict) -> "Caja":
        modo = caja_cfg.get("modo", "ciego")
        cls = _REGISTRO.get(modo, CajaCiega)
        return cls(caja_cfg)


class CajaLigando(Caja):
    """Centro en el ligando de referencia co-cristalizado (permite redocking)."""
    modo = "ligando"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calcular(self, ctx):
        if not ctx.ref:
            return ResultadoCaja(ok=False, error=f"no encontré el ligando de referencia {self.cfg['ref']} en la estructura")
        coords = ctx.xyz_fn(ctx.ref)
        c, s = ctx.caja_fn(coords, self.cfg.get("margen", 10), self.cfg.get("minimo", 22))
        det = f"ligando {self.cfg['ref']} ({len(coords)} átomos pesados)"
        return ResultadoCaja(ok=True, center=c, size=s, detalle=det)


class CajaResiduos(Caja):
    """Centro sobre un conjunto de residuos del sitio activo."""
    modo = "residuos"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calcular(self, ctx):
        quiero = []
        for tok in str(self.cfg["residuos"]).replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            ch, num = (tok.split(":") if ":" in tok else (None, tok))
            num = "".join(x for x in num if x.isdigit() or x == "-")
            quiero.append((ch.strip().upper() if ch else None, int(num)))
        sel = [l for l in ctx.cuerpo if l[:4] == "ATOM" and any(
            int(l[22:26]) == n and (ch is None or l[21] == ch) for ch, n in quiero)]
        if not sel:
            return ResultadoCaja(ok=False, error=f"ninguno de los residuos {self.cfg['residuos']} existe en el receptor limpio")
        c, s = ctx.caja_fn(ctx.xyz_fn(sel), self.cfg.get("margen", 8), self.cfg.get("minimo", 20))
        det = f"{len(quiero)} residuos ({len(sel)} átomos)"
        return ResultadoCaja(ok=True, center=c, size=s, detalle=det)


class CajaManual(Caja):
    """Centro y tamaño dados a mano."""
    modo = "manual"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calcular(self, ctx):
        return ResultadoCaja(ok=True, center=self.cfg["center"], size=self.cfg["size"], detalle="manual")


class CajaCiega(Caja):
    """Toda la proteína (docking ciego). Es también el modo por defecto si 'modo' no
    se reconoce, igual que antes."""
    modo = "ciego"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calcular(self, ctx):
        c, s = ctx.caja_fn(ctx.xyz_fn(ctx.cuerpo + ctx.cof), self.cfg.get("margen", 10))
        aviso = "la caja es muy grande (> 126 Å); considera docking por sitio" if max(s) > 126 else ""
        return ResultadoCaja(ok=True, center=c, size=s, detalle="ciego (proteína completa)", aviso=aviso)


_REGISTRO: dict[str, Any] = {c.modo: c for c in (CajaLigando, CajaResiduos, CajaManual, CajaCiega)}
