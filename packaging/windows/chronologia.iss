; Installateur Windows (Inno Setup 6).
; Usage : ISCC.exe /DAppVersion=0.1.0 packaging\windows\chronologia.iss
; Prérequis : dossier PyInstaller dist\chronologia déjà construit.

#ifndef AppVersion
  #error "Définir la version : /DAppVersion=x.y.z"
#endif

[Setup]
AppId={{6B9A8F5C-2C0E-4D7B-9E5B-3C1F6A7D2E41}
AppName=Chronologia
AppVersion={#AppVersion}
AppPublisher=Chronologia
DefaultDirName={autopf}\Chronologia
DefaultGroupName=Chronologia
UninstallDisplayIcon={app}\chronologia.exe
OutputDir=..\..\dist
OutputBaseFilename=Chronologia-Setup-{#AppVersion}
SetupIconFile=..\icon.ico
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; installation par utilisateur sans droits administrateur, ou pour tous si l'utilisateur le choisit
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\..\dist\chronologia\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Chronologia"; Filename: "{app}\chronologia.exe"
Name: "{group}\{cm:UninstallProgram,Chronologia}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Chronologia"; Filename: "{app}\chronologia.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\chronologia.exe"; Description: "{cm:LaunchProgram,Chronologia}"; Flags: nowait postinstall skipifsilent
