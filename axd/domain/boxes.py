"""Clases polimórficas para cada modo de caja de docking (Fase 3; esquema en inglés desde la Fase 8).

Reemplazan la cadena if/elif por 'mode' que había en pipeline/receptors.py. Cada Box
calcula su propio centro/tamaño a partir de las líneas PDB ya filtradas que le pasa
BoxContext — no hace I/O ni conoce rutas de archivo, así que se puede probar aparte
del resto del paso 'receptors'."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class BoxContext:
    """Lo que cada Box necesita para calcularse, ya resuelto por receptors.py."""
    body: list        # líneas ATOM del receptor limpio (+ TER)
    cofactors: list    # líneas HETATM de los cofactores conservados
    ref: list          # líneas HETATM del ligando de referencia (sólo se llena en modo 'ligand')
    box_fn: Callable   # box(coords, margin, minimum=0.0) -> (center, size)
    xyz_fn: Callable   # xyz(lines, no_h=True) -> coords


@dataclass
class BoxResult:
    ok: bool
    center: list[float] | None = None
    size: list[float] | None = None
    detail: str = ""
    error: str = ""   # fatal: el paso falla para esta diana
    warning: str = ""  # no fatal: se loguea pero se sigue


class Box:
    mode: str = ""

    def calculate(self, ctx: BoxContext) -> BoxResult:
        raise NotImplementedError

    @staticmethod
    def create(box_cfg: dict) -> "Box":
        mode = box_cfg.get("mode", "blind")
        cls = _REGISTRY.get(mode, BlindBox)
        return cls(box_cfg)


class LigandBox(Box):
    """Centro en el ligando de referencia co-cristalizado (permite redocking)."""
    mode = "ligand"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calculate(self, ctx):
        if not ctx.ref:
            return BoxResult(ok=False, error=f"no encontré el ligando de referencia {self.cfg['ref']} en la estructura")
        coords = ctx.xyz_fn(ctx.ref)
        c, s = ctx.box_fn(coords, self.cfg.get("margin", 10), self.cfg.get("minimum", 22))
        detail = f"ligando {self.cfg['ref']} ({len(coords)} átomos pesados)"
        return BoxResult(ok=True, center=c, size=s, detail=detail)


class ResidueBox(Box):
    """Centro sobre un conjunto de residuos del sitio activo."""
    mode = "residues"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calculate(self, ctx):
        want = []
        for tok in str(self.cfg["residues"]).replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            ch, num = (tok.split(":") if ":" in tok else (None, tok))
            num = "".join(x for x in num if x.isdigit() or x == "-")
            want.append((ch.strip().upper() if ch else None, int(num)))
        sel = [l for l in ctx.body if l[:4] == "ATOM" and any(
            int(l[22:26]) == n and (ch is None or l[21] == ch) for ch, n in want)]
        if not sel:
            return BoxResult(ok=False, error=f"ninguno de los residuos {self.cfg['residues']} existe en el receptor limpio")
        c, s = ctx.box_fn(ctx.xyz_fn(sel), self.cfg.get("margin", 8), self.cfg.get("minimum", 20))
        detail = f"{len(want)} residuos ({len(sel)} átomos)"
        return BoxResult(ok=True, center=c, size=s, detail=detail)


class ManualBox(Box):
    """Centro y tamaño dados a mano."""
    mode = "manual"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calculate(self, ctx):
        return BoxResult(ok=True, center=self.cfg["center"], size=self.cfg["size"], detail="manual")


class BlindBox(Box):
    """Toda la proteína (docking ciego). Es también el modo por defecto si 'mode' no
    se reconoce, igual que antes."""
    mode = "blind"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def calculate(self, ctx):
        c, s = ctx.box_fn(ctx.xyz_fn(ctx.body + ctx.cofactors), self.cfg.get("margin", 10))
        warning = "la caja es muy grande (> 126 Å); considera docking por sitio" if max(s) > 126 else ""
        return BoxResult(ok=True, center=c, size=s, detail="ciego (proteína completa)", warning=warning)


_REGISTRY: dict[str, Any] = {c.mode: c for c in (LigandBox, ResidueBox, ManualBox, BlindBox)}
