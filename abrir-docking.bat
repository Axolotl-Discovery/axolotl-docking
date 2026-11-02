@echo off
rem Abre la interfaz grafica de Axolotl Docking (dentro de WSL2). Doble clic.
rem Necesita Windows 11, o Windows 10 con WSL actualizado (wsl --update), para mostrar ventanas.
setlocal EnableExtensions
chcp 65001 >nul
title Axolotl Docking
wsl -d Ubuntu -e true >nul 2>&1
if errorlevel 1 (
  echo  [X] No encuentro Ubuntu en WSL. Ejecuta primero  instalar-windows.bat
  echo.
  pause
  exit /b 1
)
wsl -d Ubuntu -- bash -lic "Docking gui"
if errorlevel 1 (
  echo.
  echo  [X] No se pudo abrir la interfaz grafica. Prueba:
  echo      1. Abre PowerShell y ejecuta:  wsl --update
  echo      2. Reinicia WSL con:  wsl --shutdown   y vuelve a abrir este archivo.
  echo      3. Mientras tanto, puedes usar la version de terminal: abre Ubuntu y escribe  Docking
  echo.
  pause
)
