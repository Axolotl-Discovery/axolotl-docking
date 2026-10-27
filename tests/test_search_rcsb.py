"""Búsqueda RCSB de la GUI con la red simulada (sin peticiones reales)."""
import io
import json
from unittest import mock

import pytest

from axd.gui.services import search_rcsb as S


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake(search_body):
    def urlopen(req, timeout=0):
        if "search.rcsb.org" in req.full_url:
            return _Resp(search_body)
        return _Resp(json.dumps({"struct": {"title": "BRAF V600E"}}).encode())
    return urlopen


def test_sin_resultados_204_cuerpo_vacio_devuelve_lista_vacia():
    with mock.patch("urllib.request.urlopen", side_effect=_fake(b"")):
        assert S.search_targets("proteina-inexistente") == []


def test_respuesta_invalida_es_searcherror():
    with mock.patch("urllib.request.urlopen", side_effect=_fake(b"<html>error</html>")):
        with pytest.raises(S.SearchError):
            S.search_targets("braf")


def test_con_resultado():
    body = json.dumps({"result_set": [{"identifier": "3OG7", "score": 1.0}]}).encode()
    with mock.patch("urllib.request.urlopen", side_effect=_fake(body)):
        hits = S.search_targets("braf")
    assert [h.pdb_id for h in hits] == ["3OG7"] and hits[0].title == "BRAF V600E"
