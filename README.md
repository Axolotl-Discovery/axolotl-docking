#  Axolotl Docking

App de terminal para **docking molecular** de Axolotl Discovery. Se instala con un comando (WSL, Linux nativo o macOS) y se usa escribiendo:

```bash
Docking
```

Te pregunta las rutas y datos del proyecto (dianas, ligandos, controles) y hace todo lo demás: descarga estructuras, limpia receptores, calcula la caja, prepara ligandos, valida por redocking, corre smina con varias semillas en segundo plano y arma la tabla de afinidades.

---

## Instalación (una línea)

Funciona igual en **WSL (Ubuntu)**, **Linux nativo** y **macOS** — en una terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
```

Esto instala:

| Capa | Qué | Dónde |
|---|---|---|
| App | comando `Docking` (alias `docking` y `dock`) | `~/.axolotl-docking` → `~/.local/bin/Docking` |
| A | Miniforge + entorno conda (RDKit, Meeko, Open Babel, PDBFixer, OpenMM, gemmi, Vina, PyMOL, ProLIF, PLIP…) | `~/miniforge3/envs/axolotl-docking` |
| B | smina (Linux: binario estático · macOS: conda-env aislado de bioconda) | `~/tools/bin/smina` |
| C | ADFRsuite (`prepare_receptor`, `prepare_ligand`, AutoDock4…) | `~/tools/ADFRsuite-1.0` |

Las tres capas van **separadas a propósito**: instalar smina o ADFRsuite dentro de conda degrada numpy/rdkit/openbabel (o rompe el `base`).

### macOS

El pipeline completo (simulaciones incluidas) corre en macOS, con una sola salvedad:

- **Apple Silicon (M1/M2/M3/…):** ni smina ni ADFRsuite publican build nativo `osx-arm64` —
  el único binario de smina fuera de Linux es el de [bioconda para `osx-64`](https://anaconda.org/bioconda/smina/files)
  (Intel), y el tarball de [ADFRsuite para Mac](https://ccsb.scripps.edu/adfr/downloads/) tampoco distingue arquitectura.
  El instalador lo resuelve solo: activa **Rosetta 2** (lo instala si hace falta, pide confirmación
  del sistema una sola vez) y corre smina en un entorno conda `osx-64` aparte —separado del entorno
  principal para no arrastrar esa arquitectura a rdkit/numpy/openbabel, que sí tienen build nativo
  `arm64` y se instalan ahí sin pasar por Rosetta. Si algún paquete del entorno principal no tuviera
  build nativo `arm64` todavía, el instalador reintenta una vez forzando todo el entorno a `osx-64`
  antes de rendirse.
- **Intel:** no necesita nada especial, todas las capas tienen build nativo.
- Esta ruta se verificó de punta a punta (conda + smina + ADFRsuite reales, con un docking real)
  en CI sobre `macos-latest`, pero **macOS ya no está en los workflows**: los runners de macOS
  consumen minutos de Actions a ×10. Hoy se prueba a mano en una Mac propia.

Si en esa PC ya tienes un entorno llamado `axolotl-Docking` o `axolot-Docking`, el instalador lo detecta y lo reutiliza (sólo le añade lo que falte). Es seguro volver a correrlo.

Opciones:

```bash
# sólo la app, sin conda/smina/ADFR
curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash -s -- --solo-app
# usar un nombre de entorno específico
curl -fsSL .../install.sh | AXD_ENV=mi-entorno bash
```

Al terminar, abre una terminal nueva (o `source ~/.bashrc`) y escribe `Docking`.

---

## Uso

```
Docking                    menú interactivo
Docking nuevo              asistente para crear un proyecto
Docking abrir   [carpeta]  ver/editar dianas, ligandos y parámetros
Docking correr  [carpeta]  correr el pipeline (completo o por pasos)
Docking resultados [carpeta]  tablas de afinidad, redocking, interacciones; abrir complejos y Excel
Docking avance  [carpeta]  cuántas corridas van + tiempo restante (--vivo: se actualiza solo)
Docking log     [carpeta]  log en vivo
Docking detener [carpeta]  detener el trabajo en segundo plano
Docking reanudar[carpeta]  retomar donde se quedó (corte de luz, reinicio…)
Docking entorno            verificar / instalar / elegir entorno conda
Docking actualizar         bajar la última versión de GitHub
Docking gui                abrir la interfaz gráfica de escritorio (PySide6)
```

### Interfaz gráfica (GUI)

Además del menú de terminal, hay una interfaz de escritorio (`Docking gui`, PySide6) con 5 pestañas en
una barra de iconos a la derecha (desplegable para ver los nombres) — **Proyecto** (abrir/crear,
dianas, ligandos, caja y parámetros), **Proceso**, **Resultados** (tabla de afinidades; el ojo de cada
fila abre el visor 3D de ese complejo), **Postprocesamiento** (lo mismo que la opción "Ver resultados"
de la terminal: afinidades, matriz ligando × diana, redocking, interacciones y acciones) y **Entorno** —
que no duplica nada del pipeline: es una capa sobre el mismo `axd/` (mismo `axd.json`, mismo
`axd.runner`, mismo `axd.entorno`). Agrega algunas cosas que el CLI no tenía:

- **Visor 3D**: 3Dmol.js embebido (copia local, sin internet) con cartoon/superficie/sticks, ligando,
  residuos en contacto y caja de docking. Necesita QtWebEngine (viene con PySide6 de PyPI).
- **Eliminar último procesamiento** (Proceso): borra docking, resumen e interacciones (pasos 5–7) para
  rehacerlos, conservando receptores/ligandos preparados y redocking; antes guarda obligatoriamente una
  copia `.zip` (descomprimirla en el proyecto deja todo como estaba).
- **Dispositivo de ejecución** (Entorno): CPU (smina) o GPU (Vina-GPU 2.1), con el procesador y la
  tarjeta detectados — ver [Docking en GPU](#docking-en-gpu-vina-gpu-21).

- **Checkpoints automáticos**: cada 10% de avance real se guarda una foto de `axd.json` + qué resultados
  existen, en `.checkpoints/` dentro del proyecto (viaja con la carpeta). Se puede restaurar desde la
  pestaña Proceso.
- **Calibración de dispositivo**: en una máquina nueva, un benchmark corto (CPU, ~2s) ajusta la primera
  estimación de tiempo; se afina solo con avance real una vez que el trabajo lleva corridas hechas.
- **Perfil de cómputo**: *Estación de trabajo* (70-80% recomendado) o *Servidor* (hasta 95%), aplicado al
  `cpu` de los parámetros de docking.
- **Buscar diana por nombre**: usa la RCSB Search API para encontrar un PDB ID a partir de un nombre, con
  un indicador explícito de "sin conexión a internet" para no confundirlo con un error de la app.
- **Terminal acoplable/independiente**: el mismo `Docking abrir`/`correr` interactivo, dentro de la
  ventana o suelto en su propia ventana del sistema, sin que afecte al trabajo en segundo plano.
- **Auto-actualización**: envuelve `Docking actualizar` (git pull) con una pantalla de "hay una versión
  nueva" en vez de tener que usar la terminal.

Instalación (dentro del entorno conda, ya incluido en `env/environment.yml`):

```bash
pip install --break-system-packages pyside6   # si no viene ya del entorno conda
Docking gui
```

### Docking en GPU (Vina-GPU 2.1)

Opcional. Usa [Vina-GPU 2.1](https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1) (AutoDock-Vina-GPU-2.1,
Apache-2.0, OpenCL). Requisitos: **Linux o WSL** con GPU **NVIDIA o AMD** y su driver con OpenCL
(`clinfo -l` debe listar la plataforma). **No existe para macOS**: en Mac el docking sigue en CPU.

```bash
bash scripts/instalar_vina_gpu.sh            # detecta NVIDIA/AMD, compila y genera los kernels de TU GPU
bash scripts/instalar_vina_gpu.sh --plataforma amd --con-cajas-grandes   # opciones
```

Luego, en la GUI: Entorno → Dispositivo de ejecución → GPU. Notas:

- Compila en un commit fijo y genera los kernels OpenCL en tu equipo (2–5 min, puede pedir `sudo`
  para instalar Boost/OpenCL con apt).
- Por defecto admite **cajas de hasta 30 Å por lado** (docking dirigido). `--con-cajas-grandes` agrega
  hasta 70 Å, pero esa variante reserva ~15 GB de memoria; si no alcanza, se descarta sola. Una caja
  mayor (p. ej. docking ciego) necesita CPU.
- Vina-GPU no tiene `exhaustiveness`: la búsqueda la controlan `gpu_threads` (≥ 1000, por defecto 8000)
  y `gpu_search_depth` (opcional) en los parámetros de docking. Corre una corrida a la vez.
- **Un proyecto no mezcla motores**: el motor usado queda en `axd.json` (`docking.motor_usado`). Para
  cambiar de CPU a GPU (o al revés) con resultados ya hechos, usa *Eliminar último procesamiento*.
- Ligandos con átomos no comunes siguen yendo a AutoDock4 en CPU.
- En WSL, el driver de NVIDIA para Windows no siempre expone OpenCL; si `clinfo -l` no ve NVIDIA,
  Vina-GPU no puede usar la tarjeta.

---

Si estás dentro de la carpeta de un proyecto no hace falta poner `[carpeta]`. Las rutas se pueden pegar **como en Windows** (`C:\Users\Me\Desktop\...`) o arrastrando la carpeta a la terminal; TAB autocompleta.

### Modo básico y modo avanzado

Al crear un proyecto eliges el modo:

**Básico (todo automático)** — sólo te pregunta:
1. Carpeta y nombre del proyecto.
2. Proteínas: un **PDB ID** (`1M17`), un **ID de UniProt** (`P00533`, se baja de AlphaFold) o la ruta a un `.pdb/.cif`.
3. Ligandos, uno por línea, en lo que tengas a la mano:
   - nombre común: `quercetin`
   - **CID** de PubChem: `5280343` o `CID 5280343`
   - **SID** de PubChem: `SID 482105756` (se traduce a su compuesto)
   - SMILES con nombre: `Aspirina CC(=O)Oc1ccccc1C(=O)O`
   - ruta a un archivo o carpeta con estructuras (`.sdf .mol .mol2 .pdb .smi .pdbqt`)
4. (Opcional) un control positivo.

Lo demás lo decide solo: si la estructura trae un ligando co-cristalizado, pone la caja ahí, conserva esa cadena y sus cofactores/iones, y valida con redocking; si no hay ligando, hace docking ciego (con exhaustiveness 64). Arranca el pipeline completo en segundo plano.

**Avanzado** — tú eliges cadenas, cofactores, tipo de caja (ligando de referencia, residuos del sitio, ciego o coordenadas), margen, semillas, exhaustiveness, poses, CPU y qué pasos correr.

Puedes cambiar un proyecto de modo en `Docking abrir`.

### Átomos no comunes (vanadio, platino, rutenio, cobre…)

Al crear el proyecto la app pregunta **"¿Vas a trabajar con átomos poco comunes?"**. También lo detecta sola si un ligando trae un elemento que smina no conoce. En ese caso:

- todo el proyecto (ligandos, controles y redocking) se dockea con **AutoDock4** (`autogrid4` + `autodock4`, vienen con ADFRsuite), para que las energías sean comparables entre sí;
- los parámetros del elemento nuevo se añaden al archivo oficial `AD4.1_bound.dat` con la convención documentada por AutoDock: **Rii y epsii = x1 y D1 del Universal Force Field** (Rappé et al., *JACS* 1992, 114, 10024), volumen de la esfera de diámetro Rii, y solvatación/puentes de H como los metales de AD4. Todo queda escrito en `05_Analysis/metal_parameters.txt` (para la sección de métodos) y en `04_Docking/Maps/AD4_axd.dat`;
- cargas parciales **EEM** (Open Babel) conservando la carga formal total; los clusters se tratan como cuerpos rígidos.

Los ligandos metálicos necesitan estructura 3D. Se pueden pedir como componente del PDB:

| Escribe | Qué baja |
|---|---|
| `PDB:VO4` | ortovanadato |
| `PDB:DVT` | decavanadato |
| `PDB:XXX` | cualquier componente químico del PDB (coordenadas ideales) |

o dar la ruta a un `.sdf`/`.mol2` 3D (por ejemplo, tetravanadato desde una estructura cristalina). Ojo con el estado de protonación: a pH fisiológico predominan formas protonadas (p. ej. H₂VO₄⁻); usa el archivo con la protonación que corresponda.

> **Aviso:** son parámetros genéricos, no ajustados para cada metal. Usa las energías para comparar poses y sitios entre sí, y valida con dinámica molecular (o QM/MM) antes de sacar conclusiones.

### Pipeline

| Paso | Qué hace |
|---|---|
| `download` | RCSB / AlphaFold / PubChem por nombre, CID o SID (3D si existe), y SDF del ligando cristalográfico |
| `receptors` | cadenas + altloc A, cofactores elegidos, PDBFixer (sin reconstruir lazos), `prepare_receptor -A hydrogens`, caja desde coordenadas reales → `04_Docking/boxes.json` |
| `ligands` | quita sales, 3D con RDKit (ETKDGv3 + MMFF) si hace falta, Meeko con macrociclos rígidos |
| `redocking` | redockea el ligando cristalográfico y calcula RMSD simétrico (criterio ≤ 2 Å) |
| `docking` | smina: ligandos × dianas × semillas, en `/tmp` (rutas con espacios OK), escritura atómica, **reanudable** |
| `summary` | media ± DE, mejor, eficiencia de ligando, Δ vs control → CSV + Excel, mejores poses |
| `interactions` | **complejo proteína + ligando en un solo PDB** (con hidrógenos y enlaces) + pose en SDF, y análisis de interacciones con PLIP: puentes de H, hidrofóbicas, apilamiento π, catión-π, puentes salinos, halógeno, agua y metal (respaldo geométrico si PLIP falla) |

(Estos son los identificadores internos que usan `axd.runner` y la GUI — en el menú interactivo cada paso se muestra con su descripción en español, como en la tabla de arriba.)

### Ver resultados en la terminal

`Docking resultados` (o "Ver resultados" en el menú) muestra:

- tabla de afinidades por diana (la mejor resaltada), matriz ligando × diana y validación por redocking;
- interacciones por complejo (conteo por tipo) y el detalle residuo por residuo con distancias;
- abrir un complejo en **PyMOL** (del entorno conda) o con el programa predeterminado del sistema (Explorador en WSL, Finder en macOS), abrir el Excel o la carpeta.

### Estructura de un proyecto

```
mi_proyecto/
├─ axd.json                 configuración (la edita el asistente o la GUI)
├─ .checkpoints/            snapshots automáticos cada 10% de avance (GUI; viaja con la carpeta)
├─ 01_Receptors/            crudos + clean/
├─ 02_Ligands/  03_Controls/ (crystal_ligand/)
├─ 04_Docking/  Receptors/ Ligands/ Controls/ Redocking/ Results/<diana>/ BestPoses/ Complexes/ boxes.json logs/
├─ 05_Analysis/             affinities_summary.csv, affinity_matrix.csv, redocking_summary.csv, interactions_*.csv, *.xlsx
├─ 06_Figures/  07_Report/
└─ README.md  .gitignore
```

(Proyectos creados con versiones anteriores a la Fase 8, con nombres de carpeta en español, se migran solos
la primera vez que se abren — ver `axd/layout.py::migrate_in_place`.)

---

## Pruebas automatizadas

Hay una suite de pruebas (`pytest`) en `tests/` que cubre la lógica que no depende de
herramientas externas (smina, ADFRsuite, RDKit real): el modelo de dominio tipado,
las fuentes y cajas polimórficas, el plan de recursos y el seguro térmico, y la
paralelización real del docking. No requiere el entorno conda completo:

```
pip install pytest numpy
pytest
```

Lo que necesita binarios/paquetes reales (smina, ADFRsuite, RDKit, Open Babel) se sigue
verificando a mano, corriendo el pipeline sobre un proyecto de prueba dentro del entorno
conda (`env/environment.yml`, que ya incluye `pytest` para correr la suite ahí también).

Hay además dos workflows de GitHub Actions. **Ninguno corre automáticamente**: para no
generar gasto, ambos son sólo manuales (`workflow_dispatch`), y las pruebas se corren en
entornos propios (`pytest` y `QT_QPA_PLATFORM=offscreen python tests/smoke_gui.py`).

- [`gui-smoke.yml`](.github/workflows/gui-smoke.yml): arranca la GUI (PySide6, sin entorno
  gráfico real) en Linux y Windows — prueba que la ventana y las 5 pestañas funcionan.
- [`backend-real-install.yml`](.github/workflows/backend-real-install.yml): corre
  `scripts/instalar_entorno.sh` de verdad (conda + smina + ADFRsuite reales, descargados de
  Internet) en Linux, y hace un **docking real** con smina sobre un sistema clásico de
  tutorial (tripsina + bencenamidina, PDB 3PTB) para probar que las tres capas quedan
  funcionales de punta a punta — no sólo que el instalador compila.

## Notas

- El docking corre en segundo plano: puedes cerrar el menú. **En WSL**, deja abierta (minimizada) una terminal; si se cierran todas, Windows puede apagar WSL. En Linux nativo y macOS no hace falta: el proceso sigue aunque cierres la terminal.
- Tras un apagón: `Docking reanudar` limpia archivos a medias y sigue con lo que falta.
- «Rehacer desde cero» no borra nada: mueve los resultados anteriores a `04_Docking/Resultados_respaldo_<fecha>/`.
- Desinstalar: `bash ~/.axolotl-docking/uninstall.sh` (no toca proyectos, entorno ni `~/tools`).
