#!/usr/bin/env bash
# ============================================================================
#  Instala el entorno de docking de Axolotl Discovery en TRES CAPAS separadas:
#    A · conda (miniforge) + entorno con RDKit, Meeko, Open Babel, PDBFixer, Vina, PyMOL…
#    B · smina estático en ~/tools/bin              (NUNCA vía conda)
#    C · ADFRsuite en ~/tools/ADFRsuite-1.0         (NUNCA vía conda)
#  Es idempotente: lo que ya está instalado se respeta.
#  Opciones: --sin-smina  --sin-adfr
# ============================================================================
set -uo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$HOME/.config/axolotl-docking/config.json"
SIN_SMINA=0; SIN_ADFR=0
for a in "$@"; do
  case "$a" in --sin-smina) SIN_SMINA=1 ;; --sin-adfr) SIN_ADFR=1 ;; esac
done
R=$'\033[38;5;205m'; V=$'\033[32m'; A=$'\033[33m'; X=$'\033[31m'; N=$'\033[0m'
ok()   { echo "  ${V}✔${N} $*"; }
warn() { echo "  ${A}⚠${N} $*"; }
fail() { echo "  ${X}✘${N} $*"; }
paso() { echo; echo "${R}── $* ${N}"; }

ENV_NAME="${AXD_ENV:-$(python3 -c "import json;print(json.load(open('$CONF')).get('entorno','axolotl-docking'))" 2>/dev/null || echo axolotl-docking)}"
TOOLS="$HOME/tools"; mkdir -p "$TOOLS/bin"
PROBLEMAS=0

# ---------------------------------------------------------------- A · conda
paso "Capa A · conda + entorno '$ENV_NAME'"
CONDA_BASE=""
for d in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3"; do
  [ -f "$d/etc/profile.d/conda.sh" ] && { CONDA_BASE="$d"; break; }
done
if [ -z "$CONDA_BASE" ]; then
  echo "  · Instalando Miniforge en ~/miniforge3…"
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/mf.sh" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh" \
    && bash "$tmp/mf.sh" -b -p "$HOME/miniforge3" >/dev/null \
    && CONDA_BASE="$HOME/miniforge3" && "$CONDA_BASE/bin/conda" init bash >/dev/null 2>&1 \
    && ok "Miniforge instalado" || { fail "No se pudo instalar Miniforge"; exit 1; }
  rm -rf "$tmp"
else
  ok "conda encontrado en $CONDA_BASE"
fi
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
SOLVER="conda"; command -v mamba >/dev/null && SOLVER="mamba"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  ok "el entorno '$ENV_NAME' ya existe: sólo instalo lo que le falte (sin tocar lo demás)"
  conda activate "$ENV_NAME"
  PY="$CONDA_PREFIX/bin/python"   # nunca 'python' a secas: ADFRsuite trae un python 2.7
  [ -x "$PY" ] || { fail "el entorno no tiene python propio"; PY=python; }
  FALTAN=$("$PY" - <<'PY'
import importlib, importlib.util
req = {"rdkit": "rdkit", "meeko": "meeko", "openbabel": "openbabel", "pdbfixer": "pdbfixer", "openmm": "openmm",
       "gemmi": "gemmi", "numpy": "numpy", "pandas": "pandas", "openpyxl": "openpyxl", "scipy": "scipy"}
print(" ".join(p for m, p in req.items() if importlib.util.find_spec(m) is None))
PY
)
  if [ -n "$FALTAN" ]; then
    echo "  · Faltan: $FALTAN"
    $SOLVER install -y -n "$ENV_NAME" -c conda-forge $FALTAN || { fail "no pude instalar: $FALTAN"; PROBLEMAS=$((PROBLEMAS+1)); }
  fi
  command -v mk_prepare_ligand.py >/dev/null || "$PY" -m pip install -q meeko
  conda deactivate
else
  echo "  · Creando el entorno (10-20 min la primera vez)…"
  if $SOLVER env create -y -n "$ENV_NAME" -f "$APP/env/environment.yml" 2>/dev/null \
     || $SOLVER env create -n "$ENV_NAME" -f "$APP/env/environment.yml"; then
    ok "entorno '$ENV_NAME' creado"
  else
    fail "no se pudo crear el entorno (revisa tu conexión y vuelve a correr: Docking entorno)"; PROBLEMAS=$((PROBLEMAS+1))
  fi
fi

# ---------------------------------------------------------------- B · smina
paso "Capa B · smina (binario estático)"
if [ "$SIN_SMINA" = 1 ]; then
  echo "  · omitido (--sin-smina)"
elif [ -x "$TOOLS/bin/smina" ] && head -c 4 "$TOOLS/bin/smina" | grep -q ELF; then
  ok "smina ya instalado: $TOOLS/bin/smina"
else
  curl -fsSL -o "$TOOLS/bin/smina.part" "https://sourceforge.net/projects/smina/files/smina.static/download" \
    && head -c 4 "$TOOLS/bin/smina.part" | grep -q "ELF" \
    && mv "$TOOLS/bin/smina.part" "$TOOLS/bin/smina" && chmod +x "$TOOLS/bin/smina" \
    && ok "smina instalado en $TOOLS/bin/smina" \
    || { rm -f "$TOOLS/bin/smina.part"; fail "no pude descargar smina (SourceForge). Reintenta más tarde con: Docking entorno"; PROBLEMAS=$((PROBLEMAS+1)); }
fi

# ---------------------------------------------------------------- C · ADFRsuite
paso "Capa C · ADFRsuite (prepare_receptor / prepare_ligand)"
if [ "$SIN_ADFR" = 1 ]; then
  echo "  · omitido (--sin-adfr)"
elif [ -x "$TOOLS/ADFRsuite-1.0/bin/prepare_receptor" ]; then
  ok "ADFRsuite ya instalado: $TOOLS/ADFRsuite-1.0"
else
  tmp=$(mktemp -d)
  echo "  · Descargando ADFRsuite (≈ 500 MB)…"
  if curl -fL --progress-bar -o "$tmp/ADFRsuite.tar.gz" "https://ccsb.scripps.edu/adfr/download/1038/" \
     && tar xzf "$tmp/ADFRsuite.tar.gz" -C "$tmp"; then
    d=$(find "$tmp" -maxdepth 1 -type d -name "ADFRsuite_*" | head -1)
    ( cd "$d" && yes | ./install.sh -d "$TOOLS/ADFRsuite-1.0" -c 0 >/dev/null 2>&1 )
    [ -x "$TOOLS/ADFRsuite-1.0/bin/prepare_receptor" ] && ok "ADFRsuite instalado" \
      || { fail "falló la instalación de ADFRsuite"; PROBLEMAS=$((PROBLEMAS+1)); }
  else
    fail "no pude descargar ADFRsuite de ccsb.scripps.edu"; PROBLEMAS=$((PROBLEMAS+1))
  fi
  rm -rf "$tmp"
fi

# ---------------------------------------------------------------- config
mkdir -p "$(dirname "$CONF")"
python3 - "$CONF" "$ENV_NAME" "$CONDA_BASE" <<'PY'
import json, os, sys
f, env, base = sys.argv[1:4]
c = json.load(open(f)) if os.path.exists(f) else {}
c.update(entorno=env, conda=base.replace(os.path.expanduser("~"), "~", 1),
         tools_bin="~/tools/bin", adfr_bin="~/tools/ADFRsuite-1.0/bin")
json.dump(c, open(f, "w"), indent=2)
PY

echo
if [ "$PROBLEMAS" = 0 ]; then
  echo "${V}✔ Entorno de docking listo.${N}"
else
  echo "${A}⚠ Terminó con $PROBLEMAS problema(s). Puedes volver a correrlo: lo instalado se respeta.${N}"
fi
exit 0
