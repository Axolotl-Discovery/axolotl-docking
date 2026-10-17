"""Configuración compartida de las pruebas (Fase 7).

- Pone la raíz del repo y `pipeline/` en sys.path, igual que hace `pipeline/comun.py`
  en producción (los pasos del pipeline usan imports planos: `import comun`, etc.).
- Aísla `axd.config` del config real del usuario (~/.config/axolotl-docking):
  las pruebas nunca deben leer ni escribir el config de la máquina donde corren.
- No requiere RDKit/Open Babel/smina/ADFRsuite instalados: donde el código original
  los necesita, cada prueba los sustituye por un doble explícito.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("AXD_CONFIG_DIR", tempfile.mkdtemp(prefix="axd_test_config_"))

import pytest  # noqa: E402


class FakeNet:
    """Doble de axd.infra.net: registra llamadas, no hace peticiones de red reales.
    `fallos` es el conjunto de URLs/consultas para las que debe lanzar IOError."""

    def __init__(self):
        self.llamadas = []
        self.fallos = set()

    def bajar(self, url, dest, intentos=1, timeout=None):
        self.llamadas.append(("bajar", url, dest))
        if url in self.fallos:
            raise IOError(f"no se pudo descargar {url}")
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        open(dest, "w").write("contenido de prueba")
        return dest

    def pubchem_sdf(self, consulta, base):
        self.llamadas.append(("pubchem_sdf", consulta, base))
        if consulta in self.fallos:
            raise IOError("no encontrado")
        dest = base + ".sdf"
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        open(dest, "w").write("mol de prueba")
        return dest, "3D"


@pytest.fixture
def fake_net():
    return FakeNet()


