; ============================================================================
;  Axolotl Docking - instalador .exe para Windows (Inno Setup 6)
;
;  Empaqueta los .bat del repo (instalar-windows.bat / abrir-docking.bat) en un
;  asistente de instalacion con accesos directos. El instalador es pequeno: el
;  resto (WSL2, Ubuntu, conda, smina, ADFRsuite) lo descarga instalar-windows.bat
;  al terminar, igual que el instalacion manual.
;
;  Compilar localmente:  iscc /DAppVersion=1.3.0 windows\axolotl-docking.iss
;  (en CI lo hace .github/workflows/windows-installer.yml)
; ============================================================================
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{79CD1B09-74A4-4D28-99C4-931F06EF515C}
AppName=Axolotl Docking
AppVersion={#AppVersion}
AppPublisher=Axolotl Discovery
AppPublisherURL=https://axolotldiscovery.com/
AppSupportURL=https://github.com/Axolotl-Discovery/axolotl-docking/issues
DefaultDirName={localappdata}\Axolotl Docking
DefaultGroupName=Axolotl Docking
DisableProgramGroupPage=yes
; Sin admin para copiar archivos; instalar-windows.bat pide admin solo para WSL.
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=AxolotlDocking-Windows
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Axolotl Docking
MinVersion=10.0.19041

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\instalar-windows.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\abrir-docking.bat";    DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";              DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";            DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Axolotl Docking";                  Filename: "{app}\abrir-docking.bat";   WorkingDir: "{app}"
Name: "{group}\Instalar o reparar Axolotl Docking"; Filename: "{app}\instalar-windows.bat"; WorkingDir: "{app}"
Name: "{group}\Desinstalar Axolotl Docking";      Filename: "{uninstallexe}"
Name: "{autodesktop}\Axolotl Docking";            Filename: "{app}\abrir-docking.bat";   WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Run]
; Prepara WSL2 + Ubuntu y ejecuta install.sh. Tarda 15-30 min y necesita internet y ~6 GB.
Filename: "{app}\instalar-windows.bat"; WorkingDir: "{app}"; \
  Description: "Instalar ahora WSL2, Ubuntu y Axolotl Docking (necesita internet, ~6 GB y 15-30 min)"; \
  Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
spanish.FinishedLabel=Axolotl Docking quedo copiado. Para terminar, ejecuta "Instalar o reparar Axolotl Docking" (o marca la casilla de abajo): activa WSL2 con Ubuntu e instala el motor de docking. Si Windows pide reiniciar, reinicia y vuelve a ejecutarlo.
