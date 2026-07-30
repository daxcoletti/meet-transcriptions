; Instalador de Meet Transcriptions para Windows (Inno Setup 6).
;
; Pasos de build (en Windows):
;   1. pip install ".[gui]" pyinstaller
;   2. python packaging\make_icon.py            (genera windows\icon.ico)
;   3. pyinstaller packaging\transcriptor.spec  (genera dist\MeetTranscriptions\)
;   4. Compilar este script con Inno Setup      (genera Output\MeetTranscriptions-Setup.exe)
;
; ffmpeg NO se incluye a propósito: la aplicación lo detecta en el primer
; arranque y ofrece descargarlo (ver INFO_INSTALACION.txt, que el wizard
; muestra antes de instalar).

#define MyAppName "Meet Transcriptions"
#define MyAppVersion "2.5.0"
#define MyAppPublisher "TRANS-IT Foundation"
#define MyAppExeName "MeetTranscriptions.exe"

[Setup]
AppId={{7E4B7C1A-2C3D-4F5E-9A8B-6D0E1F2A3B4C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Instalación por usuario: no pide administrador y las keys quedan en el
; perfil correcto.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=MeetTranscriptions-Setup-{#MyAppVersion}
SetupIconFile=windows\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; Auto-actualización: previa confirmación del usuario, la app lanza este
; Setup con /SILENT (progreso visible, sin wizard) y se cierra.
; force = cerrar la app si sigue corriendo; el relanzamiento lo hace la
; entrada [Run] postinstall (sin skipifsilent), así que RestartApplications
; queda en no para no abrirla dos veces.
CloseApplications=force
RestartApplications=no

; El instalador se muestra en el idioma del Windows del usuario; el texto
; informativo previo (ffmpeg + API keys) también va por idioma.
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "windows\INFO_INSTALL_EN.txt"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"; InfoBeforeFile: "windows\INFO_INSTALACION.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MeetTranscriptions\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Relanzar la app tras instalar, salvo en /VERYSILENT (winget, despliegues
; masivos): ahí un GUI abriéndose solo es comportamiento indeseado. El
; updater de la app usa /SILENT, así que la reapertura automática se mantiene.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall; Check: NotVerySilent

[Code]
function NotVerySilent(): Boolean;
begin
  Result := Pos('/VERYSILENT', UpperCase(GetCmdTail)) = 0;
end;

[UninstallRun]
; Quitar el autostart que la app registra en HKCU\...\Run al configurarse.
Filename: "reg"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v MeetTranscriptions /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
