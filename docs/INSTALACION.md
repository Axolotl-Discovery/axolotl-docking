# Guía de instalación para alumnos

Axolotl Docking es **gratuito**. Esta guía es para quien empieza: sigue los pasos en orden y, si algo falla, mira
la sección **«Si algo sale mal»** al final.

Antes de empezar necesitas:

- **Internet** durante toda la instalación (descarga unos 2–3 GB).
- **Unos 6 GB libres** en el disco.
- **15–30 minutos.** No cierres las ventanas mientras trabajan.

---

## Windows 10 / 11

Axolotl Docking corre dentro de **WSL2** (un Ubuntu que vive dentro de Windows). El instalador lo activa por ti.

1. **Descarga** el proyecto: en la página de GitHub del curso pulsa **Code → Download ZIP** y descomprímelo
   (clic derecho → *Extraer todo*). No lo ejecutes desde dentro del ZIP.
2. Abre la carpeta y haz **doble clic en `instalar-windows.bat`**.
   - Si Windows muestra «Windows protegió su PC», pulsa **Más información → Ejecutar de todas formas**. Es normal con
     archivos descargados que no están firmados.
   - Cuando Windows pida **permiso de administrador**, acéptalo.
3. **Primera vez:** el instalador activa WSL2 y Ubuntu. Si Windows pide **reiniciar**, reinicia.
   Se abrirá una ventana de Ubuntu que te pide un **usuario y una contraseña**. Escríbelos y anótalos (la contraseña
   no se ve al teclearla; es normal). Cuando termine, cierra esa ventana.
4. **Vuelve a hacer doble clic en `instalar-windows.bat`.** Ahora instala Axolotl Docking dentro de Ubuntu.
   Si pide contraseña es la de Ubuntu del paso anterior. Tarda varios minutos.
5. Al final corre solo un **docking de prueba**. Debe terminar con **«Todo está listo»**.
6. Para usarlo, **doble clic en `abrir-docking.bat`** (abre la ventana del programa).
   También puedes abrir *Ubuntu* desde el menú Inicio y escribir `Docking`.

> La ventana gráfica necesita **Windows 11**, o Windows 10 con WSL actualizado (`wsl --update` en PowerShell).
> Si no abre, la versión de terminal funciona igual: abre Ubuntu y escribe `Docking`.

## Linux (Ubuntu, Debian, Fedora…)

Abre una terminal y pega una línea:

```bash
curl -fsSL https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh | bash
```

Si pide contraseña es la de tu usuario (para instalar `git`, `curl` y `python3` si faltan). Al terminar, **abre una
terminal nueva** y comprueba la instalación:

```bash
Docking verificar
```

Debe terminar con **«Todo está listo»**. Después, para abrir el programa: `Docking gui` (ventana) o `Docking` (terminal).

## Mac

La misma línea de Linux funciona en Mac (Terminal). En Apple Silicon el instalador activa Rosetta 2 si hace falta.

---

## Primer proyecto

1. Abre el programa (`abrir-docking.bat` en Windows, `Docking gui` en Linux/Mac).
2. En la pestaña **Proyecto** crea un proyecto nuevo y añade una **diana** (por ejemplo, un código PDB) y uno o más
   **ligandos**.
3. En **Proceso** pulsa **Correr pipeline**. La lista de pasos se va marcando; si un paso falla, el ⓘ rojo muestra el
   motivo.
4. Los resultados aparecen en **Resultados** y **Postprocesamiento**; el reporte en PDF se genera en el paso final.

---

## Si algo sale mal

**Cualquier error:** copia el texto de la ventana (o haz una captura) y mándalo a quien te dio el curso. Es seguro
**volver a ejecutar el instalador**: retoma donde se quedó.

| Qué ves | Qué hacer |
|---|---|
| «Tu Windows es demasiado antiguo para WSL2» | Actualiza Windows (Configuración → Windows Update) y repite. |
| «No se pudo instalar WSL» | Casi siempre es la **virtualización apagada** en la BIOS/UEFI (busca *Virtualization*, *VT-x* o *SVM* y actívala). También pueden bloquearlo una VPN o la red de la escuela. |
| Windows pide reiniciar | Reinicia y vuelve a ejecutar `instalar-windows.bat`. |
| «Poco espacio en disco» | Libera al menos 6 GB y repite. |
| «No hay conexión con github.com» | Revisa tu internet; apaga la VPN o prueba con otra red. |
| «Parece WSL 1» | En PowerShell: `wsl --set-version Ubuntu 2`. |
| `Docking verificar` falla en un paso | Lee el mensaje: dice qué paso falló y qué hacer. Para revisar lo instalado: `Docking entorno`. |
| `Docking: command not found` | Cierra y abre la terminal. Si sigue, ejecuta `source ~/.bashrc`. |
| La ventana gráfica no abre en Windows | En PowerShell: `wsl --update`, luego `wsl --shutdown` y abre `abrir-docking.bat` de nuevo. Mientras tanto usa `Docking` en terminal. |

Para **desinstalar**: `bash ~/.axolotl-docking/uninstall.sh` (no borra tus proyectos).
