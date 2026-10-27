#!/usr/bin/env bash
# ============================================================================
#  Instala el motor GPU de Axolotl Docking: Vina-GPU 2.1 (AutoDock-Vina-GPU-2.1,
#  DeltaGroupNJUPT, licencia Apache-2.0), compilado en ESTE equipo.
#
#  Requisitos: Linux o WSL, GPU NVIDIA o AMD con su driver y runtime OpenCL.
#  No existe Vina-GPU para macOS: ahí el docking sigue en CPU (smina).
#
#  Qué hace:
#    1. Detecta la plataforma (NVIDIA / AMD) — o se fuerza con --plataforma.
#    2. Instala con apt lo necesario para compilar (g++, Boost, cabeceras y
#       cargador OpenCL, clinfo), salvo --sin-apt.
#    3. Descarga el código en un commit FIJO (ver VINA_GPU_COMMIT) y lo compila.
#       Variante por defecto "small": cajas ≤ 30 Å por lado (docking dirigido;
#       reserva ~1.1 GB para las rejillas). Con --con-cajas-grandes compila además
#       "large" (≤ 70 Å), que reserva ~15 GB: sólo para equipos con ≥ 16 GB de RAM
#       y GPU con memoria de sobra; si no alcanza, se descarta sola.
#    4. Genera los kernels OpenCL de TU GPU (Kernel1_Opt.bin / Kernel2_Opt.bin)
#       con un docking corto del ejemplo que trae el propio Vina-GPU.
#  Resultado: ~/tools/vina-gpu/small/vina-gpu + kernels (y large/ si se pidió).
#
#  Opciones: --plataforma nvidia|amd   --con-cajas-grandes   --dir RUTA   --sin-apt
#  Variable: AXD_VINA_GPU_SRC=ruta  usa un código ya descargado (sin red).
#  Es idempotente: volver a correrlo recompila desde cero esa instalación.
# ============================================================================
set -uo pipefail
VINA_GPU_REPO="https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1"
VINA_GPU_COMMIT="180272b8a5265d6ed9664178345933cebe2cd349"
CONF="${AXD_CONFIG_DIR:-$HOME/.config/axolotl-docking}/config.json"
DEST="$HOME/tools/vina-gpu"; PLAT=""; CON_LARGE=0; SIN_APT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --plataforma) PLAT="${2:-}"; shift ;;
    --con-cajas-grandes) CON_LARGE=1 ;;
    --dir) DEST="${2:-}"; shift ;;
    --sin-apt) SIN_APT=1 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done
R=$'\033[38;5;205m'; V=$'\033[32m'; A=$'\033[33m'; X=$'\033[31m'; N=$'\033[0m'
ok()   { echo "  ${V}✔${N} $*"; }
warn() { echo "  ${A}⚠${N} $*"; }
fail() { echo "  ${X}✘${N} $*"; }
paso() { echo; echo "${R}── $* ${N}"; }

# ---------------------------------------------------------------- 0 · sistema
if [ "$(uname -s)" != "Linux" ]; then
  fail "Vina-GPU sólo se instala en Linux o WSL (no hay versión para macOS). El docking seguirá en CPU."
  exit 1
fi

# ---------------------------------------------------------------- 1 · plataforma
paso "1 · GPU"
if [ -z "$PLAT" ]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    PLAT=nvidia
  elif command -v lspci >/dev/null 2>&1 && lspci 2>/dev/null | grep -Ei 'vga|3d|display' | grep -qiE 'nvidia'; then
    PLAT=nvidia
  elif command -v lspci >/dev/null 2>&1 && lspci 2>/dev/null | grep -Ei 'vga|3d|display' | grep -qiE 'amd|ati|radeon'; then
    PLAT=amd
  fi
fi
case "$PLAT" in
  nvidia) MACRO_PLAT="-DNVIDIA_PLATFORM"; ok "GPU NVIDIA" ;;
  amd)    MACRO_PLAT="-DAMD_PLATFORM";    ok "GPU AMD" ;;
  *) fail "No detecté una GPU NVIDIA o AMD. Si la tienes, fuerza la plataforma: --plataforma nvidia|amd"; exit 1 ;;
esac

# ---------------------------------------------------------------- 2 · dependencias de compilación
paso "2 · Dependencias de compilación"
falta_algo() {
  command -v g++ >/dev/null && command -v git >/dev/null && command -v clinfo >/dev/null \
    && [ -f /usr/include/boost/program_options.hpp ] && [ -f /usr/include/CL/cl.h ] \
    && { ldconfig -p 2>/dev/null | grep -q 'libOpenCL.so ' || [ -e /usr/lib/x86_64-linux-gnu/libOpenCL.so ]; } \
    && return 1 || return 0
}
if falta_algo; then
  if [ "$SIN_APT" = 1 ] || ! command -v apt-get >/dev/null 2>&1; then
    fail "Faltan herramientas para compilar (g++, git, Boost, cabeceras OpenCL o clinfo) y no voy a usar apt."
    fail "Instala: g++ git libboost-{program-options,system,filesystem,thread}-dev ocl-icd-opencl-dev opencl-headers clinfo"
    exit 1
  fi
  echo "· Instalando paquetes de compilación (puede pedir tu contraseña)…"
  sudo apt-get update -qq && sudo apt-get install -y -qq g++ make git libboost-program-options-dev \
    libboost-system-dev libboost-filesystem-dev libboost-thread-dev ocl-icd-opencl-dev opencl-headers clinfo \
    || { fail "apt no pudo instalar las dependencias"; exit 1; }
fi
ok "g++, Boost, OpenCL y clinfo listos"

# El runtime OpenCL de la GPU lo pone el driver (no este script):
#   NVIDIA: el driver propietario trae su ICD de OpenCL.  AMD: ROCm / AMDGPU-PRO OpenCL.
PLATAFORMAS="$(clinfo -l 2>/dev/null || true)"
NOMBRE_PLAT="NVIDIA"; [ "$PLAT" = amd ] && NOMBRE_PLAT="AMD"
if echo "$PLATAFORMAS" | grep -q "$NOMBRE_PLAT"; then
  ok "OpenCL ve la plataforma $NOMBRE_PLAT"
else
  fail "OpenCL no ve ninguna plataforma $NOMBRE_PLAT (clinfo -l):"
  echo "$PLATAFORMAS" | sed 's/^/      /'
  if [ "$PLAT" = nvidia ]; then
    fail "Instala el driver de NVIDIA con soporte OpenCL. En WSL, el driver de Windows no siempre expone OpenCL."
  else
    fail "Instala el runtime OpenCL de AMD (ROCm)."
  fi
  exit 1
fi

# ---------------------------------------------------------------- 3 · código fuente
paso "3 · Código de Vina-GPU 2.1"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -n "${AXD_VINA_GPU_SRC:-}" ]; then
  SRC="$AXD_VINA_GPU_SRC"
  ok "usando código local: $SRC"
else
  git -C "$TMP" init -q src && git -C "$TMP/src" remote add origin "$VINA_GPU_REPO" \
    && git -C "$TMP/src" fetch -q --depth 1 origin "$VINA_GPU_COMMIT" \
    && git -C "$TMP/src" checkout -q FETCH_HEAD \
    || { fail "no pude descargar $VINA_GPU_REPO@$VINA_GPU_COMMIT"; exit 1; }
  [ "$(git -C "$TMP/src" rev-parse HEAD)" = "$VINA_GPU_COMMIT" ] || { fail "el commit descargado no coincide"; exit 1; }
  SRC="$TMP/src/AutoDock-Vina-GPU-2.1"
  ok "commit ${VINA_GPU_COMMIT:0:7} verificado"
fi
for f in main/main.cpp OpenCL/src/wrapcl.cpp OpenCL/src/kernels/kernel2.cl input_file_example/2bm2_protein.pdbqt; do
  [ -f "$SRC/$f" ] || { fail "falta $f en el código de Vina-GPU"; exit 1; }
done

# ---------------------------------------------------------------- 4 · compilar + kernels
LIBS="-lboost_program_options -lboost_system -lboost_filesystem -lboost_thread -lOpenCL -lstdc++fs -lpthread -lm"
ulimit -s 8192 2>/dev/null || ulimit -s unlimited 2>/dev/null || true   # Vina-GPU pide ≥ 8 MB de pila
VARIANTES="small"; [ "$CON_LARGE" = 1 ] && VARIANTES="small large"
rm -rf "$DEST/large"  # una "large" de una instalación previa sólo se conserva si se vuelve a pedir
mkdir -p "$DEST"
for VAR in $VARIANTES; do
  paso "4 · Variante $VAR (caja ≤ $([ "$VAR" = small ] && echo 30 || echo 70) Å)"
  BOX="-DSMALL_BOX"; [ "$VAR" = large ] && BOX="-DLARGE_BOX"
  D="$DEST/$VAR"; rm -rf "$D"; mkdir -p "$D"
  cp -r "$SRC/OpenCL" "$SRC/input_file_example" "$D/"
  FLAGS="-I$SRC/lib -I$SRC/OpenCL/inc -O3 -DOPENCL_3_0 $MACRO_PLAT $BOX -DBOOST_TIMER_ENABLE_DEPRECATED -DNDEBUG"
  echo "· compilando (1–3 min)…"
  g++ -o "$D/vina-gpu-kernels" "$SRC/main/main.cpp" "$SRC"/lib/*.cpp "$SRC/OpenCL/src/wrapcl.cpp" \
      $FLAGS -DBUILD_KERNEL_FROM_SOURCE $LIBS >"$D/build.log" 2>&1 \
    && g++ -o "$D/vina-gpu" "$SRC/main/main.cpp" "$SRC"/lib/*.cpp "$SRC/OpenCL/src/wrapcl.cpp" \
      $FLAGS $LIBS >>"$D/build.log" 2>&1 \
    || { fail "falló la compilación (ver $D/build.log)"; exit 1; }
  ok "compilado"
  echo "· generando los kernels para tu GPU (la primera vez tarda)…"
  ( cd "$D" && ./vina-gpu-kernels --receptor input_file_example/2bm2_protein.pdbqt \
      --ligand input_file_example/2bm2_ligand.pdbqt --out kernel_test_out.pdbqt \
      --center_x 40.415 --center_y 110.986 --center_z 82.673 --size_x 20 --size_y 20 --size_z 20 \
      --thread 1000 --search_depth 1 --seed 1 --opencl_binary_path . ) >"$D/kernels.log" 2>&1
  if [ -f "$D/Kernel1_Opt.bin" ] && [ -f "$D/Kernel2_Opt.bin" ] && grep -q "VINA RESULT" "$D/kernel_test_out.pdbqt" 2>/dev/null; then
    ok "kernels generados y docking de prueba correcto"
  elif [ "$VAR" = large ]; then
    # La variante grande reserva ~15 GB para las rejillas (sizeof(grids_cl) con LARGE_BOX); si no alcanza
    # se descarta y queda la pequeña (cajas ≤ 30 Å). No es un error del instalador.
    warn "la variante para cajas grandes no funcionó en este equipo (ver $D/kernels.log); se descarta."
    warn "Quedan disponibles las cajas de hasta 30 Å por lado."
    mv "$D/kernels.log" "$DEST/large-kernels.log" 2>/dev/null; rm -rf "$D"
    continue
  else
    fail "no se generaron los kernels (ver $D/kernels.log)"; exit 1
  fi
  rm -f "$D/vina-gpu-kernels" "$D/kernel_test_out.pdbqt"
  rm -rf "$D/input_file_example"
done

# ---------------------------------------------------------------- 5 · config
paso "5 · Configuración"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$CONF" "$DEST" <<'PY'
import json, os, sys
conf, dest = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(conf), exist_ok=True)
try:
    c = json.load(open(conf))
except (OSError, ValueError):
    c = {}
c["vina_gpu_dir"] = dest
json.dump(c, open(conf, "w"), indent=2, ensure_ascii=False)
PY
  ok "registrado en $CONF"
fi
echo
INSTALADAS="$(for v in small large; do [ -x "$DEST/$v/vina-gpu" ] && printf '%s ' "$v"; done)"
ok "Vina-GPU 2.1 instalado en $DEST (variantes: ${INSTALADAS% })."
echo "  Elige «GPU» en la pestaña Entorno (Dispositivo de ejecución) para usarlo."
echo "  Licencia de Vina-GPU 2.1: Apache-2.0 · $VINA_GPU_REPO"
