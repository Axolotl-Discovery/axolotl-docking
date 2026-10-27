"""Búsqueda de dianas por nombre (RCSB Search API) para la GUI.

El código existente (axd.domain.sources.PdbTargetSource, axd.infra.net) sólo
sabe *descargar* una diana cuando ya se conoce su PDB ID o su UniProt — no hay
forma de buscar "EGFR humano" y obtener candidatos. Esto cierra ese hueco
usando la API pública de búsqueda de RCSB (search.rcsb.org), con las mismas
convenciones de red que el resto del proyecto (sólo `urllib`, sin requests)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry/{}"
UA = {"User-Agent": "axolotl-docking-gui"}


@dataclass
class TargetHit:
    pdb_id: str
    title: str
    organism: str
    score: float


class SearchError(IOError):
    """Error de red/búsqueda, distinto de 'sin conexión' (eso lo decide
    connectivity.is_online() antes de intentar siquiera)."""


def _post_json(url, payload, timeout=20):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode().strip()
    # RCSB responde 204 sin cuerpo cuando no hay resultados; urllib no lo trata
    # como error, así que un cuerpo vacío se interpreta como "cero resultados".
    return json.loads(body) if body else {}


def _get_json(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def search_targets(query: str, *, human_only: bool = False, rows: int = 10) -> list[TargetHit]:
    """Busca estructuras por texto libre (nombre de proteína, gen, etc.).
    Lanza SearchError si falla la red o la API; no atrapa 'sin internet' —
    eso lo decide la UI con connectivity.is_online() antes de llamar aquí."""
    query = query.strip()
    if not query:
        return []
    terminal = {"type": "terminal", "service": "full_text", "parameters": {"value": query}}
    if human_only:
        node = {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                terminal,
                {"type": "terminal", "service": "text",
                 "parameters": {"attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
                                "operator": "exact_match", "value": "Homo sapiens"}},
            ],
        }
    else:
        node = terminal
    payload = {
        "query": node,
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": rows},
                             "sort": [{"sort_by": "score", "direction": "desc"}]},
    }
    try:
        result = _post_json(SEARCH_URL, payload)
    except urllib.error.HTTPError as e:
        if e.code == 204:  # sin resultados
            return []
        raise SearchError(f"RCSB respondió {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SearchError(str(e)) from e
    except ValueError as e:  # JSON inválido: respuesta inesperada de la API
        raise SearchError(f"respuesta inválida de RCSB: {e}") from e

    hits = result.get("result_set", [])[:rows]
    out = []
    for h in hits:
        pdb_id = h["identifier"]
        title, organism = pdb_id, ""
        try:
            entry = _get_json(ENTRY_URL.format(pdb_id))
            title = (entry.get("struct", {}) or {}).get("title", pdb_id)
            orgs = entry.get("rcsb_entity_source_organism") or []
            if orgs:
                organism = orgs[0].get("scientific_name", "")
            else:
                orgs2 = entry.get("rcsb_entity_host_organism") or []
                organism = orgs2[0].get("scientific_name", "") if orgs2 else ""
        except Exception:  # noqa: BLE001 — un detalle que no cargue no debe tumbar la búsqueda
            pass
        out.append(TargetHit(pdb_id=pdb_id, title=title, organism=organism, score=float(h.get("score", 0.0))))
    return out
