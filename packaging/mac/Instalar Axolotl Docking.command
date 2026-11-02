#!/bin/bash
# Axolotl Docking - instalador para macOS (doble clic).
# Descarga y ejecuta el instalador oficial; instala la app de terminal "Docking"
# y su entorno (conda, smina, ADFRsuite). Necesita internet y ~6 GB libres.
set -o pipefail
cd "$HOME" || exit 1
echo
echo "  AXOLOTL DOCKING - instalador para macOS"
echo "  Tarda entre 15 y 30 minutos. No cierres esta ventana."
echo
curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
estado=$?
echo
if [ "$estado" -eq 0 ]; then
  echo "  Listo. Abre una Terminal nueva y escribe:  Docking"
else
  echo "  La instalacion no termino bien (codigo $estado). Es seguro volver a abrir este archivo:"
  echo "  retoma donde se quedo. Si se repite, copia las lineas con X de arriba y mandalas."
fi
echo
read -n 1 -s -r -p "  Pulsa una tecla para cerrar..."
echo
exit "$estado"
