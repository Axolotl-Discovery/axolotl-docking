"""Cliente HTTP único para RCSB, AlphaFold y PubChem.

Antes esta lógica estaba duplicada: una copia en axd/proyecto.py (para los asistentes
interactivos) y otra en pipeline/descargar.py (para el pipeline en segundo plano). Ahora
ambos importan de aquí; `intentos` deja que cada quien elija su política de reintentos
(los asistentes usan 1 para no bloquear al usuario, el pipeline usa 3 con backoff)."""
import json
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "axolotl-docking"}
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def bajar(url, destino, timeout=60, intentos=1):
    """Descarga `url` a `destino`. Con intentos>1 reintenta con backoff (1.5s, 3s, …);
    no reintenta en un 404 (no tiene sentido)."""
    ultimo = None
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                datos = r.read()
            if not datos.strip():
                raise IOError("respuesta vacía")
            open(destino, "wb").write(datos)
            return destino
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if getattr(e, "code", None) == 404:
                break
            if i < intentos - 1:
                time.sleep(1.5 * (i + 1))
    raise IOError(str(ultimo))


def descargar_pdb(pdb, destino_sin_ext, intentos=1):
    """Prueba .pdb y, si no existe, .cif. Devuelve la ruta descargada."""
    for ext in ("pdb", "cif"):
        try:
            return bajar(f"https://files.rcsb.org/download/{pdb}.{ext}", f"{destino_sin_ext}.{ext}", intentos=intentos)
        except IOError:
            continue
    raise IOError(f"No pude descargar {pdb} de RCSB")


def descargar_alphafold(uniprot, destino, timeout=60):
    """Descarga el modelo de AlphaFold DB para un UniProt. Devuelve el dict de metadatos de la API."""
    with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot}", timeout=timeout) as r:
        info = json.load(r)[0]
    bajar(info["pdbUrl"], destino)
    return info


def interpretar_pubchem(texto):
    """'SID 482105756' / 'sid:482105756' → ('sid','482105756'); 'CID 5280343' o '5280343' → ('cid',…);
    cualquier otra cosa → ('nombre', texto)."""
    t = texto.strip()
    m = re.fullmatch(r"(?i)(sid|cid)\s*[:#_-]?\s*(\d+)", t)
    if m:
        return m.group(1).lower(), m.group(2)
    if t.isdigit():
        return "cid", t
    return "nombre", t


def _pug_txt(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode().split("\n")


def pubchem_resolver(texto):
    """Devuelve (cid, titulo) consultando PubChem, o (None, None) si no hay red/no existe.
    Los SID (sustancias) se traducen a su CID estandarizado."""
    tipo, v = interpretar_pubchem(texto)
    try:
        if tipo == "sid":
            cids = [x for x in _pug_txt(f"{PUG}/substance/sid/{v}/cids/TXT") if x.strip()]
            cid = cids[0].strip() if cids else None
        elif tipo == "cid":
            cid = v
        else:
            cid = _pug_txt(f"{PUG}/compound/name/{urllib.parse.quote(v)}/cids/TXT")[0].strip()
        if not cid:
            return None, None
        try:
            titulo = _pug_txt(f"{PUG}/compound/cid/{cid}/property/Title/TXT")[0].strip()
        except Exception:  # noqa: BLE001
            titulo = None
        return cid, titulo
    except Exception:  # noqa: BLE001
        return None, None


def pubchem_cid(consulta):  # compatibilidad
    return pubchem_resolver(consulta)[0]


def pubchem_sdf(consulta, destino_base, intentos=3):
    """Descarga SDF 3D (o 2D si no hay 3D) a `destino_base + '.sdf'`. Acepta nombre, CID
    ('5280343', 'CID 5280343') o SID de sustancia ('SID 482105756'): el SID se traduce a su
    CID estandarizado. Devuelve (ruta, descripción del tipo descargado)."""
    tipo, v = interpretar_pubchem(consulta)
    if tipo == "sid":
        cid = None
        try:
            cid = (_pug_txt(f"{PUG}/substance/sid/{v}/cids/TXT", timeout=30) or [None])[0]
            cid = cid.strip() if cid else None
        except Exception:  # noqa: BLE001
            cid = None
        if not cid:  # sustancia sin compuesto estandarizado: se usa el registro de la sustancia
            bajar(f"{PUG}/substance/sid/{v}/SDF", destino_base + ".sdf", intentos=intentos)
            return destino_base + ".sdf", f"sustancia SID {v} (se generará 3D con RDKit)"
        tipo, v = "cid", cid
    if tipo == "cid":
        base = f"{PUG}/compound/cid/{v}/SDF"
    else:
        base = f"{PUG}/compound/name/{urllib.parse.quote(v)}/SDF"
    try:
        bajar(base + "?record_type=3d", destino_base + ".sdf", intentos=intentos)
        return destino_base + ".sdf", "3D"
    except IOError:
        bajar(base + "?record_type=2d", destino_base + ".sdf", intentos=intentos)
        return destino_base + ".sdf", "2D (se generará 3D con RDKit)"
