"""Clases polimórficas para las fuentes de estructuras (Fase 3).

Reemplazan las cadenas if/elif por 'fuente' que había en pipeline/descargar.py. Cada
Fuente sabe descargar/localizar su propio archivo y describir el resultado; el paso
'descargar' solo pide una Fuente al registro y la usa, sin saber qué tipo es.

No tocan el proyecto (dict `d`/`l`) salvo para leerlo: quien llama decide qué hacer con
la ruta devuelta (típicamente guardarla en d["archivo"]/l["archivo"])."""
from __future__ import annotations

import json
import os
import urllib.request


# ---------------------------------------------------------------- dianas (receptores)
class FuenteDiana:
    """Cómo obtener la estructura de una diana, según d['fuente']."""
    tipo: str = ""

    def descargar(self, d: dict, crudos: str, net) -> str:
        """Devuelve la ruta absoluta descargada/localizada. Lanza IOError si falla,
        con el mensaje exacto que se le muestra al usuario."""
        raise NotImplementedError

    def describir(self, d: dict, arch: str) -> str:
        """Texto de éxito para el log, p. ej. 'RCSB 1M17.pdb'."""
        return self.tipo

    @staticmethod
    def crear(fuente: str) -> "FuenteDiana":
        return _REGISTRO_DIANA.get(fuente, FuenteArchivoDiana)()


class FuentePdbDiana(FuenteDiana):
    tipo = "pdb"

    def descargar(self, d, crudos, net):
        for ext in ("pdb", "cif"):
            dest = os.path.join(crudos, f"{d['id']}.{ext}")
            try:
                return net.bajar(f"https://files.rcsb.org/download/{d['pdb']}.{ext}", dest, intentos=3)
            except IOError:
                continue
        raise IOError(f"no se pudo descargar {d['pdb']} de RCSB")

    def describir(self, d, arch):
        return f"RCSB {d['pdb']}.{os.path.splitext(arch)[1].lstrip('.')}"


class FuenteAlphafoldDiana(FuenteDiana):
    tipo = "alphafold"

    def descargar(self, d, crudos, net):
        dest = os.path.join(crudos, f"{d['id']}.pdb")
        try:
            with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{d['uniprot']}", timeout=60) as r:
                info = json.load(r)[0]
            net.bajar(info["pdbUrl"], dest, intentos=3)
        except Exception as e:  # noqa: BLE001
            raise IOError(f"AlphaFold {d['uniprot']} ({e})") from e
        return dest

    def describir(self, d, arch):
        return f"AlphaFold {d['uniprot']}"


class FuenteArchivoDiana(FuenteDiana):
    """Archivo local: no hay nada que descargar; si llegamos aquí es que falta."""
    tipo = "archivo"

    def descargar(self, d, crudos, net):
        raise IOError(f"falta el archivo local {d.get('archivo')}")


_REGISTRO_DIANA = {c.tipo: c for c in (FuentePdbDiana, FuenteAlphafoldDiana, FuenteArchivoDiana)}


# ---------------------------------------------------------------- ligandos / controles
class FuenteLigando:
    """Cómo obtener la estructura de un ligando/control, según l['fuente']. Sólo existen
    para las fuentes que de verdad necesitan una descarga en este paso (ccd, pubchem) —
    'archivo' y 'smiles' ya traen su archivo puesto por el asistente, o se resuelven en
    otro paso del pipeline, así que FuenteLigando.crear() devuelve None para ellas."""
    tipo: str = ""
    limitar_tasa = False  # True = respeta el límite de peticiones/s del servicio (PubChem)

    def descargar(self, l: dict, carpeta: str, net):
        """Devuelve (ruta_absoluta, descripción_para_el_log). Lanza IOError si falla."""
        raise NotImplementedError

    @staticmethod
    def crear(fuente: str) -> "FuenteLigando | None":
        cls = _REGISTRO_LIGANDO.get(fuente)
        return cls() if cls else None


class FuenteCcdLigando(FuenteLigando):
    tipo = "ccd"

    def descargar(self, l, carpeta, net):
        dest = os.path.join(carpeta, l["id"] + ".sdf")
        for suf, desc in (("ideal", "coordenadas ideales"), ("model", "coordenadas de un cristal")):
            try:
                net.bajar(f"https://files.rcsb.org/ligands/download/{l['codigo']}_{suf}.sdf", dest, intentos=2)
                return dest, f"componente PDB {l['codigo']} ({desc})"
            except IOError:
                continue
        raise IOError(f"el código PDB '{l['codigo']}' no existe o no tiene coordenadas")


class FuentePubchemLigando(FuenteLigando):
    tipo = "pubchem"
    limitar_tasa = True  # PubChem pide ≤ 5 peticiones/s

    def descargar(self, l, carpeta, net):
        try:
            ruta, tipo = net.pubchem_sdf(str(l.get("cid") or l["consulta"]), os.path.join(carpeta, l["id"]))
        except IOError as e:
            raise IOError(f"PubChem no encontró '{l['consulta']}' ({e})") from e
        return ruta, f"PubChem '{l['consulta']}' {tipo}"


_REGISTRO_LIGANDO = {c.tipo: c for c in (FuenteCcdLigando, FuentePubchemLigando)}
