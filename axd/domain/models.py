"""Modelo de dominio típado: dataclasses para Target, Ligand, DockingParams y Project.

Convive con la representación en dict que ya usa todo el código existente (axd.config.load_project /
save_project, los asistentes de axd/wizards, el pipeline) — nada de lo que ya hace p["targets"][i]["id"]
necesita cambiar todavía. Esto es la base típada para las fases siguientes (Source/Box polimórficos,
pipeline con Paso/Contexto): código nuevo puede convertir con Project.from_dict(p) / .to_dict() en los
bordes en vez de indexar dicts a mano.

Fidelidad de ida y vuelta: cualquier clave que no esté modelada explícitamente se guarda en `.extra` y se
vuelve a mezclar en to_dict(), así que dict -> dataclass -> dict nunca pierde datos silenciosamente, ni con
claves que añada un paso del pipeline en el futuro.

Esquema en inglés (Fase 8): las claves del dict (y los valores de los campos tipo 'source'/'mode')
están en inglés desde esta fase. axd.config.migrate_schema_to_english() traduce en memoria un axd.json
viejo (con claves en español) al cargarlo, así que los proyectos creados con versiones anteriores siguen
funcionando."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _split(d: dict, *fields_: str) -> tuple[dict, dict]:
    """(known, rest) — separa las claves ya modeladas del resto (-> .extra)."""
    known = {k: d[k] for k in fields_ if k in d}
    rest = {k: v for k, v in d.items() if k not in fields_}
    return known, rest


@dataclass
class BoxConfig:
    """Caja de docking de una diana: cómo se define el sitio de unión."""
    mode: str = "auto"  # auto | ligand | residues | blind | manual
    ref: str | None = None
    margin: float | None = None
    minimum: float | None = None
    residues: str | None = None
    center: list[float] | None = None
    size: list[float] | None = None
    auto: bool | None = None
    detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    _FIELDS = ("mode", "ref", "margin", "minimum", "residues", "center", "size", "auto", "detail")

    @classmethod
    def from_dict(cls, d: dict | None) -> "BoxConfig":
        known, rest = _split(dict(d or {}), *cls._FIELDS)
        return cls(**known, extra=rest)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._FIELDS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        return out


@dataclass
class Target:
    """Una proteína/receptor del proyecto."""
    id: str
    source: str  # pdb | alphafold | file
    name: str
    pdb: str | None = None
    uniprot: str | None = None
    file: str | None = None
    chains: Any = "auto"      # "auto" o las cadenas a conservar, p. ej. "A" o "AB"
    cofactors: Any = "auto"   # "auto" o list[str] de RES:CADENA
    box: BoxConfig = field(default_factory=BoxConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    _FIELDS = ("id", "source", "name", "pdb", "uniprot", "file", "chains", "cofactors")

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        d = dict(d)
        box = BoxConfig.from_dict(d.pop("box", None))
        known, rest = _split(d, *cls._FIELDS)
        return cls(**known, box=box, extra=rest)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._FIELDS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        out["box"] = self.box.to_dict()
        return out


@dataclass
class Ligand:
    """Un ligando o control positivo. El mismo modelo sirve para ambos — lo que
    distingue un control es simplemente vivir en p['controls'] en vez de p['ligands']."""
    id: str
    name: str
    source: str  # pubchem | file | smiles | ccd
    query: str | None = None
    cid: str | None = None
    smiles: str | None = None
    code: str | None = None
    file: str | None = None
    target: str | None = None  # sólo controles: a qué diana se asigna (None = todas)
    extra: dict[str, Any] = field(default_factory=dict)

    _FIELDS = ("id", "name", "source", "query", "cid", "smiles", "code", "file", "target")

    @classmethod
    def from_dict(cls, d: dict) -> "Ligand":
        known, rest = _split(dict(d), *cls._FIELDS)
        return cls(**known, extra=rest)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._FIELDS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        return out


@dataclass
class DockingParams:
    """Parámetros de docking del proyecto (sección p['docking'])."""
    engine: str = "smina"  # smina | ad4
    seeds: list[int] = field(default_factory=lambda: [42, 2026, 777])
    exhaustiveness: int = 32
    num_modes: int = 9
    energy_range: int = 4
    cpu: int = 0  # 0 = todos los núcleos
    ad4_runs: int = 20
    ad4_evals: int = 2500000
    extra: dict[str, Any] = field(default_factory=dict)

    _FIELDS = ("engine", "seeds", "exhaustiveness", "num_modes", "energy_range", "cpu", "ad4_runs", "ad4_evals")

    @classmethod
    def from_dict(cls, d: dict | None) -> "DockingParams":
        known, rest = _split(dict(d or {}), *cls._FIELDS)
        return cls(**known, extra=rest)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._FIELDS:
            out[c] = getattr(self, c)
        return out


@dataclass
class Project:
    """El proyecto completo (lo que hoy vive en axd.json)."""
    name: str
    mode: str = "advanced"  # basic | advanced
    created: str | None = None
    axd_version: str | None = None
    layout_version: int | None = None
    targets: list[Target] = field(default_factory=list)
    ligands: list[Ligand] = field(default_factory=list)
    controls: list[Ligand] = field(default_factory=list)
    docking: DockingParams = field(default_factory=DockingParams)
    extra: dict[str, Any] = field(default_factory=dict)

    _FIELDS = ("name", "mode", "created", "axd_version", "layout_version")

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        d = dict(d)
        targets = [Target.from_dict(x) for x in d.pop("targets", [])]
        ligands = [Ligand.from_dict(x) for x in d.pop("ligands", [])]
        controls = [Ligand.from_dict(x) for x in d.pop("controls", [])]
        docking = DockingParams.from_dict(d.pop("docking", None))
        known, rest = _split(d, *cls._FIELDS)
        return cls(**known, targets=targets, ligands=ligands, controls=controls, docking=docking, extra=rest)

    def to_dict(self) -> dict:
        out = dict(self.extra)
        for c in self._FIELDS:
            v = getattr(self, c)
            if v is not None:
                out[c] = v
        out["targets"] = [x.to_dict() for x in self.targets]
        out["ligands"] = [x.to_dict() for x in self.ligands]
        out["controls"] = [x.to_dict() for x in self.controls]
        out["docking"] = self.docking.to_dict()
        return out
