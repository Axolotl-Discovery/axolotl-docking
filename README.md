# 🦎 Axolotl Docking

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

### Qué te pregunta el asistente

1. **Carpeta y código** del proyecto (`AXD-XXX-26-01`), cliente y descripción.
2. **Dianas**: PDB ID (RCSB), UniProt (AlphaFold DB) o archivo local. Muestra las cadenas y ligandos co-cristalizados para que elijas. Caja por:
   - ligando co-cristalizado (centro + margen, mínimo por eje) → habilita **redocking**,
   - residuos del sitio activo, docking ciego o coordenadas manuales.
3. **Ligandos y controles**: nombres de PubChem, lista `.txt/.csv` (`nombre` o `nombre,SMILES`), carpeta o archivo (`.sdf .mol .mol2 .pdb .smi .pdbqt`, SDF con varias moléculas incluido) o SMILES. Cada control se puede asignar a su diana.
4. **Parámetros**: semillas (3 por defecto), exhaustiveness (32), poses, CPU.

### Pipeline

| Paso | Qué hace |
|---|---|
| `descargar` | RCSB / AlphaFold / PubChem (3D si existe), y SDF del ligando cristalográfico |
| `receptores` | cadenas + altloc A, cofactores elegidos, PDBFixer (sin reconstruir lazos), `prepare_receptor -A hydrogens`, caja desde coordenadas reales → `04_Docking/cajas.json` |
| `ligandos` | quita sales, 3D con RDKit (ETKDGv3 + MMFF) si hace falta, Meeko con macrociclos rígidos |
| `redocking` | redockea el ligando cristalográfico y calcula RMSD simétrico (criterio ≤ 2 Å) |
| `docking` | smina: ligandos × dianas × semillas, en `/tmp` (rutas con espacios OK), escritura atómica, **reanudable** |
| `resumen` | media ± DE, mejor, eficiencia de ligando, Δ vs control → CSV + Excel, mejores poses |

### Estructura de un proyecto

```
AXD-XXX-26-01/
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
