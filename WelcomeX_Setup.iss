; Script Inno Setup para WelcomeX
; Crear instalador profesional con todo incluido

#define MyAppName "WelcomeX"
#define MyAppVersion "4.9"
#define MyAppPublisher "PampaGuazú"
#define MyAppURL "https://pampaguazu.com"
#define MyAppExeName "WelcomeX.exe"

[Setup]
AppId={{E5C8F9A1-2B3D-4E5F-6A7B-8C9D0E1F2A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
OutputDir=installers
OutputBaseFilename=WelcomeX_Setup_v4.9
SetupIconFile=assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\WelcomeX.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
; NOTE: No incluir carpeta data (se crea automáticamente)

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  VLCInstalled: Boolean;
begin
  Result := True;
  
  // Verificar si VLC está instalado
  VLCInstalled := FileExists('C:\Program Files\VideoLAN\VLC\vlc.exe') or 
                   FileExists('C:\Program Files (x86)\VideoLAN\VLC\vlc.exe');
  
  if not VLCInstalled then
  begin
    if MsgBox('Para reproducir audio en los videos, necesitas VLC Media Player instalado.' + #13#10 + #13#10 +
              '¿Deseas descargarlo ahora?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://www.videolan.org/vlc/', '', '', SW_SHOW, ewNoWait, ResultCode);
    end;
  end;
end;
