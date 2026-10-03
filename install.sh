#!/usr/bin/env bash
# ============================================================================
#  Axolotl Docking — instalador de una línea (WSL / Linux)
#
#    curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
#
#  Opciones (después de "bash -s --"):
#    --solo-app      instala sólo el comando Docking (sin conda/smina/ADFR)
#    --sin-adfr      no instala ADFRsuite      --sin-smina   no instala smina
#  Variables:  AXD_HOME (carpeta de instalación, por defecto ~/.axolotl-docking)
#              AXD_REPO (URL del repo)   AXD_RAMA (rama, por defecto main)
#              AXD_ENV  (nombre del entorno conda)
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

  [ "$(uname -s)" = "Linux" ] || { echo "✘ Esto se instala dentro de WSL/Linux, no en Windows directamente."; exit 1; }
  grep -qi microsoft /proc/version 2>/dev/null || echo "${A}· No parece WSL; sigo igual (Linux nativo también funciona).${N}"

  # --- dependencias mínimas del sistema
  local falta=()
  for c in git python3 curl tar; do command -v "$c" >/dev/null || falta+=("$c"); done
  if [ ${#falta[@]} -gt 0 ]; then
    echo "· Instalando dependencias del sistema: ${falta[*]} (puede pedir tu contraseña)"
    sudo apt-get update -qq && sudo apt-get install -y -qq "${falta[@]}"
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

  # --- bloque en ~/.bashrc (PATH para el comando, smina y ADFRsuite)
  local RC="$HOME/.bashrc"
  touch "$RC"
  if ! grep -q ">>> axolotl-docking >>>" "$RC"; then
    cat >> "$RC" <<'BLOQUE'

# >>> axolotl-docking >>>
export PATH="$HOME/.local/bin:$HOME/tools/ADFRsuite-1.0/bin:$HOME/tools/bin:$PATH"
alias dock='Docking'
# <<< axolotl-docking <<<
BLOQUE
    echo "${V}✔${N} PATH y alias añadidos a ~/.bashrc"
  fi
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

  if [ "$SOLO_APP" = 0 ]; then
    bash "$DEST/scripts/instalar_entorno.sh" "${EXTRA[@]+"${EXTRA[@]}"}"
  else
    echo "· Instalación sólo de la app. Para el entorno después:  Docking entorno"
  fi

  echo
  echo "${V}✔ Listo.${N} Abre una terminal nueva de WSL (o corre: source ~/.bashrc) y escribe:"
  echo
  echo "      ${R}Docking${N}"
  echo
}

main "$@"
