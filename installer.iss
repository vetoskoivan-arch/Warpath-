#define MyAppName "Warpath Inventory"
#define MyAppVersion "0.1.0"
[Setup]
AppId={{2FBCDE8E-8B29-4F5D-9AF3-83F62D39B9A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Warpath Inventory
DefaultGroupName=Warpath Inventory
OutputDir=output
OutputBaseFilename=WarpathInventorySetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
[Files]
Source: "dist\WarpathInventory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Warpath Inventory"; Filename: "{app}\WarpathInventory.exe"
Name: "{autodesktop}\Warpath Inventory"; Filename: "{app}\WarpathInventory.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
[Run]
Filename: "{app}\WarpathInventory.exe"; Description: "Запустить Warpath Inventory"; Flags: nowait postinstall skipifsilent
