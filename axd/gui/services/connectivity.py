"""Chequeo de conectividad a internet, para el indicador global 'sin conexión'.

Distinto a un error puntual de RCSB/PubChem (eso ya lo maneja cada fuente con
reintentos — ver axd/infra/net.py): esto responde "¿tiene sentido siquiera
intentar una búsqueda en línea ahora mismo?" con una prueba barata y rápida,
antes de que el usuario dispare una búsqueda y se encuentre con errores
confusos uno por uno."""
from __future__ import annotations

import socket

# Hosts estables, elegidos por ser servicios que la propia app ya usa (RCSB)
# o que casi nunca están caídos (DNS público de Google/Cloudflare) — basta con
# que *uno* responda para considerar que hay salida a internet.
_PROBE_HOSTS = [
    ("search.rcsb.org", 443),
    ("8.8.8.8", 53),
    ("1.1.1.1", 53),
]


def is_online(timeout: float = 1.5) -> bool:
    """True si al menos uno de los hosts de prueba acepta una conexión TCP.

    No depende de DNS por sí solo (incluye IPs crudas) para no confundir 'no
    hay internet' con 'el DNS de este dispositivo está mal configurado'."""
    for host, port in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False
