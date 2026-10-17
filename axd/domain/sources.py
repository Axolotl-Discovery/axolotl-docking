"""Clases polimórficas para las fuentes de estructuras (Fase 3; esquema en inglés desde la Fase 8).

Reemplazan las cadenas if/elif por 'source' que había en pipeline/download.py. Cada
TargetSource sabe descargar/localizar su propio archivo y describir el resultado; el paso
'download' solo pide una fuente al registro y la usa, sin saber qué tipo es.

No tocan el proyecto (dict `d`/`l`) salvo para leerlo: quien llama decide qué hacer con
la ruta devuelta (típicamente guardarla en d["file"]/l["file"])."""
from __future__ import annotations

import json
import os
import urllib.request


# ---------------------------------------------------------------- dianas (receptores)
class TargetSource:
    """Cómo obtener la estructura de una diana, según d['source']."""
    kind: str = ""

    def download(self, d: dict, raw_dir: str, net) -> str:
        """Devuelve la ruta absoluta descargada/localizada. Lanza IOError si falla,
        con el mensaje exacto que se le muestra al usuario."""
        raise NotImplementedError

    def describe(self, d: dict, path: str) -> str:
        """Texto de éxito para el log, p. ej. 'RCSB 1M17.pdb'."""
        return self.kind

    @staticmethod
    def create(source: str) -> "TargetSource":
        return _TARGET_REGISTRY.get(source, FileTargetSource)()


class PdbTargetSource(TargetSource):
    kind = "pdb"

    def download(self, d, raw_dir, net):
        for ext in ("pdb", "cif"):
            dest = os.path.join(raw_dir, f"{d['id']}.{ext}")
            try:
                return net.download(f"https://files.rcsb.org/download/{d['pdb']}.{ext}", dest, attempts=3)
            except IOError:
                continue
        raise IOError(f"no se pudo descargar {d['pdb']} de RCSB")

    def describe(self, d, path):
        return f"RCSB {d['pdb']}.{os.path.splitext(path)[1].lstrip('.')}"


class AlphafoldTargetSource(TargetSource):
    kind = "alphafold"

    def download(self, d, raw_dir, net):
        dest = os.path.join(raw_dir, f"{d['id']}.pdb")
        try:
            with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{d['uniprot']}", timeout=60) as r:
                info = json.load(r)[0]
            net.download(info["pdbUrl"], dest, attempts=3)
        except Exception as e:  # noqa: BLE001
            raise IOError(f"AlphaFold {d['uniprot']} ({e})") from e
        return dest

    def describe(self, d, path):
        return f"AlphaFold {d['uniprot']}"


class FileTargetSource(TargetSource):
    """Archivo local: no hay nada que descargar; si llegamos aquí es que falta."""
    kind = "file"

    def download(self, d, raw_dir, net):
        raise IOError(f"falta el archivo local {d.get('file')}")


_TARGET_REGISTRY = {c.kind: c for c in (PdbTargetSource, AlphafoldTargetSource, FileTargetSource)}


# ---------------------------------------------------------------- ligandos / controles
class LigandSource:
    """Cómo obtener la estructura de un ligando/control, según l['source']. Sólo existen
    para las fuentes que de verdad necesitan una descarga en este paso (ccd, pubchem) —
    'file' y 'smiles' ya traen su archivo puesto por el asistente, o se resuelven en
    otro paso del pipeline, así que LigandSource.create() devuelve None para ellas."""
    kind: str = ""
    rate_limited = False  # True = respeta el límite de peticiones/s del servicio (PubChem)

    def download(self, l: dict, folder: str, net):
        """Devuelve (ruta_absoluta, descripción_para_el_log). Lanza IOError si falla."""
        raise NotImplementedError

    @staticmethod
    def create(source: str) -> "LigandSource | None":
        cls = _LIGAND_REGISTRY.get(source)
        return cls() if cls else None


class CcdLigandSource(LigandSource):
    kind = "ccd"

    def download(self, l, folder, net):
        dest = os.path.join(folder, l["id"] + ".sdf")
        for suf, desc in (("ideal", "coordenadas ideales"), ("model", "coordenadas de un cristal")):
            try:
                net.download(f"https://files.rcsb.org/ligands/download/{l['code']}_{suf}.sdf", dest, attempts=2)
                return dest, f"componente PDB {l['code']} ({desc})"
            except IOError:
                continue
        raise IOError(f"el código PDB '{l['code']}' no existe o no tiene coordenadas")


class PubchemLigandSource(LigandSource):
    kind = "pubchem"
    rate_limited = True  # PubChem pide ≤ 5 peticiones/s

    def download(self, l, folder, net):
        try:
            path, kind = net.pubchem_sdf(str(l.get("cid") or l["query"]), os.path.join(folder, l["id"]))
        except IOError as e:
            raise IOError(f"PubChem no encontró '{l['query']}' ({e})") from e
        return path, f"PubChem '{l['query']}' {kind}"


_LIGAND_REGISTRY = {c.kind: c for c in (CcdLigandSource, PubchemLigandSource)}
