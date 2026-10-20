#!/usr/bin/env bash
# ============================================================================
#  Instala el entorno de docking de Axolotl Discovery en TRES CAPAS separadas:
#    A · conda (miniforge) + entorno con RDKit, Meeko, Open Babel, PDBFixer, Vina, PyMOL…
#    B · smina estático en ~/tools/bin              (NUNCA vía conda, salvo Mac — ver abajo)
#    C · ADFRsuite en ~/tools/ADFRsuite-1.0         (NUNCA vía conda)
#  Es idempotente: lo que ya está instalado se respeta.
#  Opciones: --sin-smina  --sin-adfr
#
#  macOS: conda (miniforge) y ADFRsuite tienen build oficial de Mac. smina NO —
#  el único build fuera de Linux que existe es el de bioconda para osx-64
#  (Intel); en Apple Silicon se instala en un conda-env aparte forzando ese
#  subdir, y corre vía Rosetta 2 (se instala sola si falta). Si algún paquete
#  del entorno principal no tuviera build nativo osx-arm64, se reintenta una
#  vez forzando todo el entorno a osx-64 (Rosetta) antes de rendirse.
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

# Miniforge/smina/ADFRsuite se bajan directo por HTTPS (no vía conda, que sí
# verifica integridad por su cuenta) y hasta ahora no se comprobaba más que
# "no vino vacío"/"empieza con ELF". verificar_checksum calcula y muestra
# siempre el sha256 de lo descargado (para poder auditarlo/fijarlo a mano), y
# si la variable de entorno nombrada en $2 trae un hash esperado, lo exige
# como condición dura. Sin esa variable, sólo avisa — no se inventa un hash
# aquí porque uno equivocado sería peor que no tener ninguno.
verificar_checksum() {
  local archivo="$1" var_esperado="$2" esperado="${!2:-}" real
  real="$(sha256sum "$archivo" 2>/dev/null | awk '{print $1}')"
  if [ -z "$real" ]; then
    warn "no pude calcular sha256 de $(basename "$archivo") (¿falta sha256sum?)"
    return 0
  fi
  if [ -n "$esperado" ]; then
    if [ "$real" = "$esperado" ]; then
      ok "sha256 de $(basename "$archivo") verificado contra \$$var_esperado"
      return 0
    fi
    fail "sha256 de $(basename "$archivo") NO coincide con \$$var_esperado"
    fail "  esperado: $esperado"
    fail "  obtenido: $real"
    return 1
  fi
  warn "sha256 de $(basename "$archivo"): $real  (sin verificar — exporta \$$var_esperado para fijarlo)"
  return 0
}

SO="$(uname -s)"; ARCH="$(uname -m)"
ES_MAC=0; [ "$SO" = "Darwin" ] && ES_MAC=1
ES_ARM_MAC=0; [ "$ES_MAC" = 1 ] && [ "$ARCH" = "arm64" ] && ES_ARM_MAC=1

ensure_rosetta() {
  # smina (bioconda) y ADFRsuite no tienen build nativo arm64: sus binarios
  # Intel necesitan Rosetta 2 para correr en Apple Silicon.
  [ "$ES_ARM_MAC" = 1 ] || return 0
  arch -x86_64 /usr/bin/true >/dev/null 2>&1 && return 0
  echo "  · Instalando Rosetta 2 (hace falta para smina/ADFRsuite en Apple Silicon)…"
  softwareupdate --install-rosetta --agree-to-license >/dev/null 2>&1 \
    && ok "Rosetta 2 instalado" \
    || { fail "no pude instalar Rosetta 2 (corré a mano: softwareupdate --install-rosetta)"; return 1; }
}

ENV_NAME="${AXD_ENV:-$(python3 -c "import json;print(json.load(open('$CONF')).get('entorno','axolotl-docking'))" 2>/dev/null || echo axolotl-docking)}"
TOOLS="$HOME/tools"; mkdir -p "$TOOLS/bin"
PROBLEMAS=0

# ---------------------------------------------------------------- A · conda
paso "Capa A · conda + entorno '$ENV_NAME'"
CONDA_BASE=""
CANDIDATOS=("$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3")
[ "$ES_MAC" = 1 ] && CANDIDATOS+=("/opt/homebrew/Caskroom/miniforge/base" "/usr/local/Caskroom/miniforge/base")
for d in "${CANDIDATOS[@]}"; do
  [ -f "$d/etc/profile.d/conda.sh" ] && { CONDA_BASE="$d"; break; }
done
if [ -z "$CONDA_BASE" ]; then
  MF_OS="Linux"; [ "$ES_MAC" = 1 ] && MF_OS="MacOSX"
  echo "  · Instalando Miniforge en ~/miniforge3…"
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/mf.sh" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$MF_OS-$ARCH.sh" \
    && verificar_checksum "$tmp/mf.sh" AXD_MINIFORGE_SHA256 \
    && bash "$tmp/mf.sh" -b -p "$HOME/miniforge3" >/dev/null \
    && CONDA_BASE="$HOME/miniforge3" && "$CONDA_BASE/bin/conda" init bash zsh >/dev/null 2>&1 \
    && ok "Miniforge instalado" || { fail "No se pudo instalar Miniforge"; rm -rf "$tmp"; exit 1; }
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
       "gemmi": "gemmi", "numpy": "numpy", "pandas": "pandas", "openpyxl": "openpyxl", "scipy": "scipy",
       "PySide6": "pyside6"}
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
  elif [ "$ES_ARM_MAC" = 1 ] && ensure_rosetta; then
    warn "no resolvió con builds nativos de Apple Silicon; reintento forzando Intel (Rosetta 2)…"
    if CONDA_SUBDIR=osx-64 $SOLVER env create -y -n "$ENV_NAME" -f "$APP/env/environment.yml" 2>/dev/null \
       || CONDA_SUBDIR=osx-64 $SOLVER env create -n "$ENV_NAME" -f "$APP/env/environment.yml"; then
      conda activate "$ENV_NAME" && conda config --env --set subdir osx-64 && conda deactivate
      ok "entorno '$ENV_NAME' creado (Intel vía Rosetta 2)"
    else
      fail "no se pudo crear el entorno ni nativo ni vía Rosetta (revisa tu conexión y vuelve a correr: Docking entorno)"
      PROBLEMAS=$((PROBLEMAS+1))
    fi
  else
    fail "no se pudo crear el entorno (revisa tu conexión y vuelve a correr: Docking entorno)"; PROBLEMAS=$((PROBLEMAS+1))
  fi
fi

# ---------------------------------------------------------------- B · smina
if [ "$ES_MAC" = 1 ]; then
  # No existe build estático de smina para macOS. El único binario fuera de
  # Linux que hay es el de bioconda, sólo para osx-64 (Intel) — así que va en
  # un conda-env propio y aislado (nunca el principal, para no arriesgar las
  # versiones de rdkit/numpy/openbabel que ya resolvió ese entorno), forzado
  # a osx-64 aunque la Mac sea Apple Silicon (corre vía Rosetta 2).
  paso "Capa B · smina (bioconda, entorno aislado — macOS no tiene build estático)"
  SMINA_ENV="${ENV_NAME}-smina"
  if [ "$SIN_SMINA" = 1 ]; then
    echo "  · omitido (--sin-smina)"
  elif [ -x "$TOOLS/bin/smina" ]; then
    ok "smina ya instalado: $TOOLS/bin/smina"
  elif ensure_rosetta \
       && (CONDA_SUBDIR=osx-64 $SOLVER create -y -n "$SMINA_ENV" -c bioconda -c conda-forge smina \
           2>/dev/null || CONDA_SUBDIR=osx-64 $SOLVER create -n "$SMINA_ENV" -c bioconda -c conda-forge smina); then
    conda activate "$SMINA_ENV" && conda config --env --set subdir osx-64 && conda deactivate
    cat > "$TOOLS/bin/smina" <<SMINA_WRAPPER
#!/usr/bin/env bash
# Generado por instalar_entorno.sh: smina vive en su propio conda-env (bioconda
# no publica build nativo osx-arm64; en Apple Silicon corre vía Rosetta 2).
exec "$CONDA_BASE/envs/$SMINA_ENV/bin/smina" "\$@"
SMINA_WRAPPER
    chmod +x "$TOOLS/bin/smina"
    ok "smina instalado en $TOOLS/bin/smina (vía conda-env '$SMINA_ENV')"
  else
    fail "no pude instalar smina (bioconda) en macOS. Reintenta con: Docking entorno"; PROBLEMAS=$((PROBLEMAS+1))
  fi
else
  paso "Capa B · smina (binario estático)"
  if [ "$SIN_SMINA" = 1 ]; then
    echo "  · omitido (--sin-smina)"
  elif [ -x "$TOOLS/bin/smina" ] && head -c 4 "$TOOLS/bin/smina" | grep -q ELF; then
    ok "smina ya instalado: $TOOLS/bin/smina"
  else
    curl -fsSL -o "$TOOLS/bin/smina.part" "https://sourceforge.net/projects/smina/files/smina.static/download" \
      && head -c 4 "$TOOLS/bin/smina.part" | grep -q "ELF" \
      && verificar_checksum "$TOOLS/bin/smina.part" AXD_SMINA_SHA256 \
      && mv "$TOOLS/bin/smina.part" "$TOOLS/bin/smina" && chmod +x "$TOOLS/bin/smina" \
      && ok "smina instalado en $TOOLS/bin/smina" \
      || { rm -f "$TOOLS/bin/smina.part"; fail "no pude descargar smina (SourceForge). Reintenta más tarde con: Docking entorno"; PROBLEMAS=$((PROBLEMAS+1)); }
  fi
fi

# ---------------------------------------------------------------- C · ADFRsuite
paso "Capa C · ADFRsuite (prepare_receptor / prepare_ligand)"
ADFR_URL="https://ccsb.scripps.edu/adfr/download/1038/"   # Linux (64-bit), tarball installer
[ "$ES_MAC" = 1 ] && ADFR_URL="https://ccsb.scripps.edu/adfr/download/1033/"  # macOS, tarball installer
if [ "$SIN_ADFR" = 1 ]; then
  echo "  · omitido (--sin-adfr)"
elif [ -x "$TOOLS/ADFRsuite-1.0/bin/prepare_receptor" ]; then
  ok "ADFRsuite ya instalado: $TOOLS/ADFRsuite-1.0"
elif [ "$ES_MAC" = 1 ] && ! ensure_rosetta; then
  fail "ADFRsuite en Apple Silicon necesita Rosetta 2 y no se pudo instalar"; PROBLEMAS=$((PROBLEMAS+1))
else
  tmp=$(mktemp -d)
  echo "  · Descargando ADFRsuite (≈ 500 MB)…"
  # AXD_ADFR_SHA256 es específico de plataforma (el tarball de Linux y el de
  # macOS son archivos distintos): quien lo fije lo hace para el SO en el que
  # está corriendo esto, no para ambos a la vez.
  if curl -fL --progress-bar -o "$tmp/ADFRsuite.tar.gz" "$ADFR_URL" \
     && verificar_checksum "$tmp/ADFRsuite.tar.gz" AXD_ADFR_SHA256 \
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
