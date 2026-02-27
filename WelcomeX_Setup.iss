; Script Inno Setup para WelcomeX
; Instalador profesional con acceso directo, desinstalador y todo incluido

#define MyAppName "WelcomeX"
#define MyAppVersion "1.5.10"
#define MyAppPublisher "Pampa Guazú"
#define MyAppURL "https://pampaguazu.com.ar"
#define MyAppExeName "WelcomeX.exe"

[Setup]
AppId={{E5C8F9A1-2B3D-4E5F-6A7B-8C9D0E1F2A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
OutputDir=installers
OutputBaseFilename=WelcomeX_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=force
CloseApplicationsFilter=WelcomeX.exe
RestartApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Carpeta completa onedir (no extrae nada a %TEMP%, sin DLL errors)
Source: "dist\WelcomeX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licencia
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Menu Inicio
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Escritorio
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Limpiar archivos creados durante el uso (logs, cache)
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  TempDir: String;
  SR: TFindRec;
begin
  // Matar WelcomeX.exe si esta corriendo (forzado)
  Exec('taskkill', '/F /IM WelcomeX.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Esperar a que el proceso termine y libere recursos
  Sleep(1500);

  // Limpiar directorios _MEI* stale de PyInstaller en %TEMP%
  // Cuando WelcomeX es force-killed, PyInstaller no puede limpiar su directorio
  // temporal. Si queda incompleto, el siguiente arranque falla con DLL error.
  TempDir := GetEnv('TEMP');
  if FindFirst(TempDir + '\_MEI*', SR) then begin
    try
      repeat
        if (SR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          DelTree(TempDir + '\' + SR.Name, True, True, True);
      until not FindNext(SR);
    finally
      FindClose(SR);
    end;
  end;

  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  // Tambien matar al desinstalar
  Exec('taskkill', '/F /IM WelcomeX.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
  Result := True;
end;
