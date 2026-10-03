#!/usr/bin/env bash
# Desinstala el comando Docking. NO borra tus proyectos, ni el entorno conda, ni smina/ADFRsuite.
set -u
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rm -f "$HOME/.local/bin/Docking" "$HOME/.local/bin/docking"
sed -i '/# >>> axolotl-docking >>>/,/# <<< axolotl-docking <<</d' "$HOME/.bashrc"
echo "✔ Comando 'Docking' eliminado y bloque quitado de ~/.bashrc"
echo "· Se conservan: tus proyectos, ~/.config/axolotl-docking, el entorno conda y ~/tools"
echo "  Para borrar también el código:  rm -rf \"$APP\""
echo "  Para borrar el entorno:         conda env remove -n <nombre>"
