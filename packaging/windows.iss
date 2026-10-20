#define MyAppName "Character Compass"
#define MyAppVersion "0.3.0"

[Setup]
AppId=CharacterCompass
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\CharacterCompass
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=CharacterCompass-Setup
SetupIconFile=web\assets\icon.ico
UninstallDisplayIcon={app}\CharacterCompass.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Files]
Source: "dist\CharacterCompass\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Character Compass"; Filename: "{app}\CharacterCompass.exe"
Name: "{autodesktop}\Character Compass"; Filename: "{app}\CharacterCompass.exe"

[Run]
Filename: "{app}\CharacterCompass.exe"; Description: "启动 Character Compass"; Flags: nowait postinstall skipifsilent
