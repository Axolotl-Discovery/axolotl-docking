@echo off
rem ===========================================================================
rem  Axolotl Docking - instalador para Windows (doble clic)
rem
rem  Prepara WSL2 con Ubuntu y ejecuta dentro el instalador de Axolotl Docking.
rem  Si WSL no estaba instalado, hay que reiniciar y volver a ejecutar este archivo.
rem  Es seguro ejecutarlo varias veces: retoma donde se quedo.
rem
rem  NOTA: escrito sin poder probarlo en un Windows real. Si algo falla, copia el
rem  texto de la ventana y mandalo a quien te dio el curso.
rem ===========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title Axolotl Docking - instalador para Windows
set "INSTALL_URL=https://raw.githubusercontent.com/Axolotl-Discovery/axolotl-docking/main/install.sh"
set "DISTRO=Ubuntu"

echo.
echo  ============================================
echo    AXOLOTL DOCKING - instalador para Windows
echo  ============================================
echo.
echo  Esto activa WSL2 con Ubuntu e instala Axolotl Docking dentro.
echo  Necesitas internet y unos 6 GB libres. Tarda entre 15 y 30 minutos.
echo.

rem --- 1. Version de Windows (WSL2 pide Windows 10 version 2004 o mas nuevo, build 19041+)
set "BUILD=0"
for /f %%b in ('powershell -NoProfile -Command "[Environment]::OSVersion.Version.Build"') do set "BUILD=%%b"
if %BUILD% LSS 19041 goto :windows_viejo

rem --- 2. Ya hay Ubuntu en WSL?
wsl -d %DISTRO% -e true >nul 2>&1
if %errorlevel%==0 goto :instalar_dentro

rem --- 3. Instalar WSL + Ubuntu (necesita administrador)
net session >nul 2>&1
if not %errorlevel%==0 goto :pedir_admin

echo  [1/3] Instalando WSL2 y Ubuntu. Esto puede tardar varios minutos...
echo.
wsl --set-default-version 2 >nul 2>&1
wsl --install -d %DISTRO%
if not %errorlevel%==0 goto :fallo_wsl

echo.
echo  ----------------------------------------------------------------
echo   WSL quedo instalado. Ahora:
echo.
echo   1. Si Windows pide REINICIAR, reinicia el equipo.
echo   2. Se abrira una ventana de Ubuntu y te pedira crear un USUARIO y una
echo      CONTRASENA. Anotalos: la contrasena no se ve mientras la escribes.
echo   3. Cuando termine, cierra esa ventana y vuelve a ejecutar este archivo
echo      (instalar-windows.bat) para instalar Axolotl Docking.
echo  ----------------------------------------------------------------
echo.
pause
exit /b 0

:instalar_dentro
echo  [2/3] Instalando Axolotl Docking dentro de Ubuntu (WSL2).
echo        Si te pide una contrasena, es la de tu usuario de Ubuntu.
echo        Los pasos de conda, smina y ADFRsuite tardan; no cierres la ventana.
echo.
wsl --set-default-version 2 >nul 2>&1
wsl -d %DISTRO% -- bash -lc "command -v curl >/dev/null || (sudo apt-get update && sudo apt-get install -y curl); curl -fsSL %INSTALL_URL% | bash"
if not %errorlevel%==0 goto :fallo_instalacion

echo.
echo  [3/3] Verificando la instalacion con un docking de prueba...
echo.
wsl -d %DISTRO% -- bash -lic "Docking verificar"
if not %errorlevel%==0 goto :fallo_verificacion

echo.
echo  ----------------------------------------------------------------
echo   Todo listo. Para usar Axolotl Docking:
echo     - Doble clic en  abrir-docking.bat  (abre la interfaz grafica), o
echo     - Abre Ubuntu desde el menu Inicio y escribe:  Docking
echo  ----------------------------------------------------------------
echo.
pause
exit /b 0

:windows_viejo
echo  [X] Tu Windows es demasiado antiguo para WSL2 (build %BUILD%; hace falta 19041 o mayor).
echo      Actualiza Windows desde Configuracion ^> Windows Update y vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:pedir_admin
echo  Para activar WSL2 hace falta permiso de administrador.
echo  Windows te lo va a pedir ahora; acepta la ventana que aparece.
echo.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b 0

:fallo_wsl
echo.
echo  [X] No se pudo instalar WSL. Causas comunes:
echo      - La virtualizacion esta apagada en el BIOS/UEFI del equipo (busca
echo        "Virtualization", "VT-x" o "SVM" y activala).
echo      - No hay internet, o una VPN/red de la escuela bloquea la descarga.
echo      - Falta espacio en disco (se necesitan unos 6 GB).
echo      Corrige lo que aplique y vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:fallo_instalacion
echo.
echo  [X] La instalacion dentro de Ubuntu no termino bien.
echo      - Revisa que tengas internet y espacio en disco.
echo      - Vuelve a ejecutar este archivo: retoma donde se quedo.
echo      - Si se repite, copia las ultimas lineas de esta ventana y mandalas
echo        a quien te dio el curso.
echo.
pause
exit /b 1

:fallo_verificacion
echo.
echo  [X] La instalacion termino, pero la verificacion encontro un problema.
echo      Lee el mensaje de arriba: indica que paso fallo y que hacer.
echo      Puedes repetirla despues desde Ubuntu con:  Docking verificar
echo.
pause
exit /b 1
