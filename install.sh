#!/usr/bin/env bash
# ============================================================================
#  Axolotl Docking — instalador de una línea (WSL / Linux / macOS)
#
#    curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
#
#  Opciones (después de "bash -s --"):
#    --solo-app      instala sólo el comando Docking (sin conda/smina/ADFR)
#    --sin-adfr      no instala ADFRsuite      --sin-smina   no instala smina
#  Variables:  AXD_HOME (carpeta de instalación, por defecto ~/.axolotl-docking)
#              AXD_REPO (URL del repo)   AXD_RAMA (rama, por defecto main)
#              AXD_ENV  (nombre del entorno conda)
#
#  macOS: funciona igual (conda/smina/ADFRsuite tienen build de Mac), con una
#  salvedad en Apple Silicon — ver la nota de Capa B en scripts/instalar_entorno.sh
#  (smina de bioconda no tiene build nativo arm64 todavía; se instala vía
#  Rosetta 2, que este instalador ofrece activar si hace falta).
# ============================================================================
set -euo pipefail

main() {
  local REPO="${AXD_REPO:-https://github.com/Axolotl-Discovery/axolotl-docking.git}"
  local RAMA="${AXD_RAMA:-main}"
  local DEST="${AXD_HOME:-$HOME/.axolotl-docking}"
  local SOLO_APP=0 EXTRA=()
  for a in "$@"; do
    case "$a" in
      --solo-app) SOLO_APP=1 ;;
      --sin-adfr|--sin-smina) EXTRA+=("$a") ;;
      *) echo "Opción desconocida: $a" ;;
    esac
  done

  R=$'\033[38;5;205m'; V=$'\033[32m'; A=$'\033[33m'; N=$'\033[0m'
  echo "${R}"
  echo "   ( \\    / )   AXOLOTL DISCOVERY"
  echo "    \\ \\__/ /    Instalando la app de terminal 'Docking'…"
  echo "${N}"

  local SO; SO="$(uname -s)"
  case "$SO" in
    Linux)
      grep -qi microsoft /proc/version 2>/dev/null || echo "${A}· No parece WSL; sigo igual (Linux nativo también funciona).${N}"
      ;;
    Darwin)
      echo "${A}· macOS detectado.${N} El pipeline de docking funciona igual (conda + smina + ADFRsuite"
      echo "  tienen build de Mac); en Apple Silicon, smina corre vía Rosetta 2 (ver más abajo)."
      ;;
    *)
      echo "✘ Esto se instala en WSL, Linux nativo o macOS. '$SO' no está soportado."; exit 1 ;;
  esac

  # --- dependencias mínimas del sistema
  local falta=()
  for c in git python3 curl tar; do command -v "$c" >/dev/null || falta+=("$c"); done
  if [ ${#falta[@]} -gt 0 ]; then
    if [ "$SO" = "Darwin" ]; then
      echo "✘ Falta(n): ${falta[*]}. En macOS, instala las herramientas de línea de comandos de Xcode"
      echo "  ('xcode-select --install') y vuelve a correr este instalador."
      exit 1
    fi
    echo "· Instalando dependencias del sistema: ${falta[*]} (puede pedir tu contraseña)"
    sudo apt-get update -qq && sudo apt-get install -y -qq "${falta[@]}"
  fi

  # --- comprobaciones previas: mejor avisar ahora que fallar a los 15 minutos
  if [ "$SOLO_APP" = 0 ]; then
    local LIBRE_KB; LIBRE_KB="$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')"
    if [ -n "$LIBRE_KB" ] && [ "$LIBRE_KB" -lt 6000000 ]; then
      echo "${A}✘ Poco espacio en disco: $((LIBRE_KB / 1024 / 1024)) GB libres en $HOME; se necesitan unos 6 GB.${N}"
      echo "  Libera espacio y vuelve a correr el instalador (lo ya instalado se respeta)."
      exit 1
    fi
    if ! curl -fsSI -m 15 https://github.com >/dev/null 2>&1; then
      echo "${A}✘ No hay conexión con github.com.${N} Revisa tu internet, tu VPN o el proxy de tu red y vuelve a correr el instalador."
      exit 1
    fi
    if [ "$SO" = "Linux" ] && grep -qi microsoft /proc/version 2>/dev/null && ! grep -qi wsl2 /proc/version 2>/dev/null; then
      echo "${A}⚠ Parece WSL 1: la instalación es lenta y algunas herramientas pueden fallar.${N}"
      echo "  Pasa Ubuntu a WSL 2 desde PowerShell:  wsl --set-version Ubuntu 2"
    fi
  fi

  # --- código: si se corre desde un clon, se usa ese; si no, se clona
  local AQUI=""
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  if [ -n "$AQUI" ] && [ -f "$AQUI/bin/Docking" ] && [ -z "${AXD_HOME:-}" ]; then
    DEST="$AQUI"
    echo "${V}✔${N} Usando el código de esta carpeta: $DEST"
  elif [ -d "$DEST/.git" ]; then
    echo "· Actualizando $DEST"
    git -C "$DEST" pull --ff-only -q
  else
    echo "· Descargando $REPO → $DEST"
    git clone -q --depth 1 -b "$RAMA" "$REPO" "$DEST"
  fi
  chmod +x "$DEST/bin/"* "$DEST/scripts/"*.sh "$DEST/"*.sh 2>/dev/null || true

  # --- comando "Docking" (y "docking") en ~/.local/bin
  mkdir -p "$HOME/.local/bin"
  ln -sf "$DEST/bin/Docking" "$HOME/.local/bin/Docking"
  ln -sf "$DEST/bin/Docking" "$HOME/.local/bin/docking"

  # --- bloque en el/los rc de la shell (PATH para el comando, smina y ADFRsuite)
  # macOS usa zsh por defecto desde Catalina (y suele tener además un .bash_profile
  # de instalaciones viejas); Linux/WSL casi siempre bash. Se escribe en todos los
  # que existan o correspondan a $SHELL, para no fallar por adivinar mal.
  local RCS=("$HOME/.bashrc")
  if [ "$SO" = "Darwin" ]; then
    RCS=("$HOME/.zshrc")
    [ -f "$HOME/.bash_profile" ] && RCS+=("$HOME/.bash_profile")
    [[ "${SHELL:-}" == */bash ]] && RCS+=("$HOME/.bashrc")
  fi
  for RC in "${RCS[@]}"; do
    touch "$RC"
    # (se reescribe en cada instalación para corregir versiones viejas del bloque)
    sed -i.bak '/# >>> axolotl-docking >>>/,/# <<< axolotl-docking <<</d' "$RC" && rm -f "$RC.bak"
    cat >> "$RC" <<'BLOQUE'

# >>> axolotl-docking >>>
# ADFRsuite y smina van AL FINAL: ADFRsuite trae su propio "python" 2.7 que taparía al de conda
export PATH="$HOME/.local/bin:$PATH:$HOME/tools/bin:$HOME/tools/ADFRsuite-1.0/bin"
alias dock='Docking'
# <<< axolotl-docking <<<
BLOQUE
    echo "${V}✔${N} PATH y alias actualizados en $RC"
  done
  export PATH="$HOME/.local/bin:$PATH"

  # --- configuración: si ya hay un entorno de docking, lo reutiliza
  python3 - "$DEST" <<'PY'
import json, os, subprocess, sys
conf_dir = os.path.expanduser("~/.config/axolotl-docking"); os.makedirs(conf_dir, exist_ok=True)
f = os.path.join(conf_dir, "config.json")
c = json.load(open(f)) if os.path.exists(f) else {}
if os.environ.get("AXD_ENV"):
    c["entorno"] = os.environ["AXD_ENV"]
elif "entorno" not in c:
    envs = []
    for base in ("~/miniforge3", "~/mambaforge", "~/miniconda3", "~/anaconda3"):
        d = os.path.expanduser(base + "/envs")
        if os.path.isdir(d):
            envs += os.listdir(d)
    previos = [e for e in envs if e.lower().replace("_", "-") in ("axolotl-docking", "axolot-docking")]
    c["entorno"] = previos[0] if previos else "axolotl-docking"
    if previos:
        print(f"✔ Encontré tu entorno existente '{previos[0]}': lo usaré.")
json.dump(c, open(f, "w"), indent=2)
PY

  local RC_ENTORNO=0
  if [ "$SOLO_APP" = 0 ]; then
    bash "$DEST/scripts/instalar_entorno.sh" "${EXTRA[@]+"${EXTRA[@]}"}" || RC_ENTORNO=$?
  else
    echo "· Instalación sólo de la app. Para el entorno después:  Docking entorno"
  fi

  if [ "$RC_ENTORNO" != 0 ]; then
    echo
    echo "${A}⚠ El entorno no quedó completo.${N} Es seguro volver a correr este mismo instalador: retoma donde se quedó."
    echo "  Si se repite, copia las líneas con ✘ de arriba y mándalas a quien te dio el curso."
    echo "  Para ver qué falta:  Docking entorno"
    exit "$RC_ENTORNO"
  fi
  echo
  echo "${V}✔ Listo.${N} Abre una terminal nueva (o corre: source ${RCS[0]}) y escribe:"
  echo
  echo "      ${R}Docking${N}"
  echo
  echo "  Antes de empezar, comprueba que todo funciona (hace un docking de prueba, ~2 min):"
  echo
  echo "      ${R}Docking verificar${N}"
  echo
}

main "$@"
