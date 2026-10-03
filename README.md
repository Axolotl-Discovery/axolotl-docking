#  Axolotl Docking

App de terminal para **docking molecular** de Axolotl Discovery. Se instala con un comando en WSL y se usa escribiendo:

```bash
Docking
```

Te pregunta las rutas y datos del proyecto (dianas, ligandos, controles) y hace todo lo demás: descarga estructuras, limpia receptores, calcula la caja, prepara ligandos, valida por redocking, corre smina con varias semillas en segundo plano y arma la tabla de afinidades.

---

## Instalación (una línea)

En una terminal de **WSL (Ubuntu)**:

```bash
curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
```

Esto instala:

| Capa | Qué | Dónde |
|---|---|---|
| App | comando `Docking` (alias `docking` y `dock`) | `~/.axolotl-docking` → `~/.local/bin/Docking` |
| A | Miniforge + entorno conda (RDKit, Meeko, Open Babel, PDBFixer, OpenMM, gemmi, Vina, PyMOL, ProLIF, PLIP…) | `~/miniforge3/envs/axolotl-docking` |
| B | smina estático | `~/tools/bin/smina` |
| C | ADFRsuite (`prepare_receptor`, `prepare_ligand`, AutoDock4…) | `~/tools/ADFRsuite-1.0` |

Las tres capas van **separadas a propósito**: instalar smina o ADFRsuite dentro de conda degrada numpy/rdkit/openbabel (o rompe el `base`).

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
Docking avance  [carpeta]  cuántas corridas van + tiempo restante
Docking log     [carpeta]  log en vivo
Docking detener [carpeta]  detener el trabajo en segundo plano
Docking reanudar[carpeta]  retomar donde se quedó (corte de luz, reinicio…)
Docking entorno            verificar / instalar / elegir entorno conda
Docking actualizar         bajar la última versión de GitHub
```

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

### Pipeline

| Paso | Qué hace |
|---|---|
| `descargar` | RCSB / AlphaFold / PubChem por nombre, CID o SID (3D si existe), y SDF del ligando cristalográfico |
| `receptores` | cadenas + altloc A, cofactores elegidos, PDBFixer (sin reconstruir lazos), `prepare_receptor -A hydrogens`, caja desde coordenadas reales → `04_Docking/cajas.json` |
| `ligandos` | quita sales, 3D con RDKit (ETKDGv3 + MMFF) si hace falta, Meeko con macrociclos rígidos |
| `redocking` | redockea el ligando cristalográfico y calcula RMSD simétrico (criterio ≤ 2 Å) |
| `docking` | smina: ligandos × dianas × semillas, en `/tmp` (rutas con espacios OK), escritura atómica, **reanudable** |
| `resumen` | media ± DE, mejor, eficiencia de ligando, Δ vs control → CSV + Excel, mejores poses |

### Estructura de un proyecto

```
mi_proyecto/
├─ axd.json                 configuración (la edita el asistente)
├─ 01_Receptores/           crudos + limpios/
├─ 02_Ligandos/  03_Controles/ (ligando_cristal/)
├─ 04_Docking/  Receptores/ Ligandos/ Controles/ Redocking/ Resultados/<diana>/ MejoresPoses/ cajas.json logs/
├─ 05_Analisis/             afinidades_resumen.csv, matriz_afinidad.csv, redocking_resumen.csv, *.xlsx
├─ 06_Figuras/  07_Reporte/
└─ README.md  .gitignore
```

---

## Notas

- El docking corre en segundo plano: puedes cerrar el menú, pero **deja abierta (minimizada) una terminal de WSL**; si se cierran todas, Windows puede apagar WSL.
- Tras un apagón: `Docking reanudar` limpia archivos a medias y sigue con lo que falta.
- «Rehacer desde cero» no borra nada: mueve los resultados anteriores a `04_Docking/Resultados_respaldo_<fecha>/`.
- Desinstalar: `bash ~/.axolotl-docking/uninstall.sh` (no toca proyectos, entorno ni `~/tools`).
