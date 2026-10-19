"""Cliente HTTP único para RCSB, AlphaFold y PubChem.

Antes esta lógica estaba duplicada: una copia en axd/proyecto.py (para los asistentes
interactivos) y otra en pipeline/download.py (para el pipeline en segundo plano). Ahora
ambos importan de aquí; `attempts` deja que cada quien elija su política de reintentos
(los asistentes usan 1 para no bloquear al usuario, el pipeline usa 3 con backoff)."""
import json
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "axolotl-docking"}
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def download(url, dest, timeout=60, attempts=1):
    """Descarga `url` a `dest`. Con attempts>1 reintenta con backoff (1.5s, 3s, …);
    no reintenta en un 404 (no tiene sentido)."""
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                data = r.read()
            if not data.strip():
                raise IOError("respuesta vacía")
            open(dest, "wb").write(data)
            return dest
        except Exception as e:  # noqa: BLE001
            last = e
            if getattr(e, "code", None) == 404:
                break
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise IOError(str(last))


def download_pdb(pdb, dest_no_ext, attempts=1):
    """Prueba .pdb y, si no existe, .cif. Devuelve la ruta descargada."""
    for ext in ("pdb", "cif"):
        try:
            return download(f"https://files.rcsb.org/download/{pdb}.{ext}", f"{dest_no_ext}.{ext}", attempts=attempts)
        except IOError:
            continue
    raise IOError(f"No pude descargar {pdb} de RCSB")


def download_alphafold(uniprot, dest, timeout=60):
    """Descarga el modelo de AlphaFold DB para un UniProt. Devuelve el dict de metadatos de la API."""
    with urllib.request.urlopen(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot}", timeout=timeout) as r:
        info = json.load(r)[0]
    download(info["pdbUrl"], dest)
    return info


def parse_pubchem(text):
    """'SID 482105756' / 'sid:482105756' → ('sid','482105756'); 'CID 5280343' o '5280343' → ('cid',…);
    cualquier otra cosa → ('name', text)."""
    t = text.strip()
    m = re.fullmatch(r"(?i)(sid|cid)\s*[:#_-]?\s*(\d+)", t)
    if m:
        return m.group(1).lower(), m.group(2)
    if t.isdigit():
        return "cid", t
    return "name", t


def _pug_txt(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode().split("\n")


def resolve_pubchem(text):
    """Devuelve (cid, título) consultando PubChem, o (None, None) si no hay red/no existe.
    Los SID (sustancias) se traducen a su CID estandarizado."""
    kind, v = parse_pubchem(text)
    try:
        if kind == "sid":
            cids = [x for x in _pug_txt(f"{PUG}/substance/sid/{v}/cids/TXT") if x.strip()]
            cid = cids[0].strip() if cids else None
        elif kind == "cid":
            cid = v
        else:
            cid = _pug_txt(f"{PUG}/compound/name/{urllib.parse.quote(v)}/cids/TXT")[0].strip()
        if not cid:
            return None, None
        try:
            title = _pug_txt(f"{PUG}/compound/cid/{cid}/property/Title/TXT")[0].strip()
        except Exception:  # noqa: BLE001
            title = None
        return cid, title
    except Exception:  # noqa: BLE001
        return None, None


def pubchem_cid(query):  # compatibilidad
    return resolve_pubchem(query)[0]


def pubchem_sdf(query, dest_base, attempts=3):
    """Descarga SDF 3D (o 2D si no hay 3D) a `dest_base + '.sdf'`. Acepta nombre, CID
    ('5280343', 'CID 5280343') o SID de sustancia ('SID 482105756'): el SID se traduce a su
    CID estandarizado. Devuelve (ruta, descripción del tipo descargado)."""
    kind, v = parse_pubchem(query)
    if kind == "sid":
        cid = None
        try:
            cid = (_pug_txt(f"{PUG}/substance/sid/{v}/cids/TXT", timeout=30) or [None])[0]
            cid = cid.strip() if cid else None
        except Exception:  # noqa: BLE001
            cid = None
        if not cid:  # sustancia sin compuesto estandarizado: se usa el registro de la sustancia
            download(f"{PUG}/substance/sid/{v}/SDF", dest_base + ".sdf", attempts=attempts)
            return dest_base + ".sdf", f"sustancia SID {v} (se generará 3D con RDKit)"
        kind, v = "cid", cid
    if kind == "cid":
        base = f"{PUG}/compound/cid/{v}/SDF"
    else:
        base = f"{PUG}/compound/name/{urllib.parse.quote(v)}/SDF"
    try:
        download(base + "?record_type=3d", dest_base + ".sdf", attempts=attempts)
        return dest_base + ".sdf", "3D"
    except IOError:
        download(base + "?record_type=2d", dest_base + ".sdf", attempts=attempts)
        return dest_base + ".sdf", "2D (se generará 3D con RDKit)"
