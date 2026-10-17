"""Modelo de dominio tipado: dataclasses para Diana, Ligando, ParamsDocking y Proyecto.

Convive con la representación en dict que ya usa todo el código existente (axd.config.cargar_proyecto /
guardar_proyecto, los asistentes de axd/wizards, el pipeline) — nada de lo que ya hace p["dianas"][i]["id"]
necesita cambiar todavía. Esto es la base típada para las fases siguientes (Fuente/Caja polimórficos,
pipeline con Paso/Contexto): código nuevo puede convertir con Proyecto.from_dict(p) / .to_dict() en los
bordes en vez de indexar dicts a mano.

Fidelidad de ida y vuelta: cualquier clave que no esté modelada explícitamente se guarda en `.extra` y se
vuelve a mezclar en to_dict(), así que dict -> dataclass -> dict nunca pierde datos silenciosamente, ni con
claves que añada un paso del pipeline en el futuro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _separar(d: dict, *campos: str) -> tuple[dict, dict]:
    """(conocidos, resto) — separa las claves ya modeladas del resto (-> .extra)."""
    conocidos = {k: d[k] for k in campos if k in d}
    resto = {k: v for k, v in d.items() if k not in campos}
    return conocidos, resto


@dataclass
class CajaConfig:
    """Caja de docking de una diana: cómo se define el sitio de unión."""
    modo: str = "auto"  # auto | ligando | residuos | ciego | manual
    ref: str | None = None
    margen: float | None = None
    minimo: float | None = None
    residuos: str | None = None
    center: list[float] | None = None
    size: list[float] | None = None
    auto: bool | None = None
    detalle: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    _CAMPOS = ("modo", "ref", "margen", "minimo", "residuos", "center", "size", "auto", "detalle")

    @classmethod
    def from_dict(cls, d: dict | None) -> "CajaConfig":
        conocidos, resto = _separar(dict(d or {}), *cls._CAMPOS)
        return cls(**conocidos, extra=resto)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._CAMPOS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        return out


@dataclass
class Diana:
    """Una proteína/receptor del proyecto."""
    id: str
    fuente: str  # pdb | alphafold | archivo
    nombre: str
    pdb: str | None = None
    uniprot: str | None = None
    archivo: str | None = None
    cadenas: Any = "auto"      # "auto" o las cadenas a conservar, p. ej. "A" o "AB"
    cofactores: Any = "auto"   # "auto" o list[str] de RES:CADENA
    caja: CajaConfig = field(default_factory=CajaConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    _CAMPOS = ("id", "fuente", "nombre", "pdb", "uniprot", "archivo", "cadenas", "cofactores")

    @classmethod
    def from_dict(cls, d: dict) -> "Diana":
        d = dict(d)
        caja = CajaConfig.from_dict(d.pop("caja", None))
        conocidos, resto = _separar(d, *cls._CAMPOS)
        return cls(**conocidos, caja=caja, extra=resto)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._CAMPOS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        out["caja"] = self.caja.to_dict()
        return out


@dataclass
class Ligando:
    """Un ligando o control positivo. El mismo modelo sirve para ambos — lo que
    distingue un control es simplemente vivir en p['controles'] en vez de p['ligandos']."""
    id: str
    nombre: str
    fuente: str  # pubchem | archivo | smiles | ccd
    consulta: str | None = None
    cid: str | None = None
    smiles: str | None = None
    codigo: str | None = None
    archivo: str | None = None
    diana: str | None = None  # sólo controles: a qué diana se asigna (None = todas)
    extra: dict[str, Any] = field(default_factory=dict)

    _CAMPOS = ("id", "nombre", "fuente", "consulta", "cid", "smiles", "codigo", "archivo", "diana")

    @classmethod
    def from_dict(cls, d: dict) -> "Ligando":
        conocidos, resto = _separar(dict(d), *cls._CAMPOS)
        return cls(**conocidos, extra=resto)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._CAMPOS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        return out


@dataclass
class ParamsDocking:
    """Parámetros de docking del proyecto (sección p['docking'])."""
    motor: str = "smina"  # smina | ad4
    semillas: list[int] = field(default_factory=lambda: [42, 2026, 777])
    exhaustiveness: int = 32
    num_modes: int = 9
    energy_range: int = 4
    cpu: int = 0  # 0 = todos los núcleos
    ad4_runs: int = 20
    ad4_evals: int = 2500000
    extra: dict[str, Any] = field(default_factory=dict)

    _CAMPOS = ("motor", "semillas", "exhaustiveness", "num_modes", "energy_range", "cpu", "ad4_runs", "ad4_evals")

    @classmethod
    def from_dict(cls, d: dict | None) -> "ParamsDocking":
        conocidos, resto = _separar(dict(d or {}), *cls._CAMPOS)
        return cls(**conocidos, extra=resto)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._CAMPOS:
            out[c] = getattr(self, c)
        return out


@dataclass
class Proyecto:
    """El proyecto completo (lo que hoy vive en axd.json)."""
    nombre: str
    modo: str = "avanzado"  # basico | avanzado
    creado: str | None = None
    version_axd: str | None = None
    layout_version: int | None = None
    dianas: list[Diana] = field(default_factory=list)
    ligandos: list[Ligando] = field(default_factory=list)
    controles: list[Ligando] = field(default_factory=list)
    docking: ParamsDocking = field(default_factory=ParamsDocking)
    extra: dict[str, Any] = field(default_factory=dict)

    _CAMPOS = ("nombre", "modo", "creado", "version_axd", "layout_version")

    @classmethod
    def from_dict(cls, d: dict) -> "Proyecto":
        d = dict(d)
        dianas = [Diana.from_dict(x) for x in d.pop("dianas", [])]
        ligandos = [Ligando.from_dict(x) for x in d.pop("ligandos", [])]
        controles = [Ligando.from_dict(x) for x in d.pop("controles", [])]
        docking = ParamsDocking.from_dict(d.pop("docking", None))
        conocidos, resto = _separar(d, *cls._CAMPOS)
        return cls(**conocidos, dianas=dianas, ligandos=ligandos, controles=controles, docking=docking, extra=resto)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._CAMPOS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        out["dianas"] = [x.to_dict() for x in self.dianas]
        out["ligandos"] = [x.to_dict() for x in self.ligandos]
        out["controles"] = [x.to_dict() for x in self.controles]
        out["docking"] = self.docking.to_dict()
        return out
