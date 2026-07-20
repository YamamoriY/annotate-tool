; Inno Setup script for the Windows installer.
;
; build-windows.ps1 compiles this automatically. To run it by hand, build the
; onedir output first:
;     .\packaging\build-windows.ps1 -NoInstaller
;     iscc packaging\installer.iss
;
; The result is dist\win\annotate-tool-setup-<version>.exe
;
; This packages the onedir build (dist\win\annotate-tool\), not the onefile exe.
; Onefile would keep unpacking ~250MB to a temp directory on every launch, which
; defeats the point of installing it in the first place.

#define AppName "COCO Segmentation Viewer"

; build-windows.ps1 passes the version from pyproject.toml as /DAppVersion=...
; The fallback below only applies when iscc is run by hand.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppPublisher "Tkino117"
#define AppExeName "annotate-tool.exe"

[Setup]
; AppId identifies the application across versions. Keep it stable so upgrades
; replace the existing install instead of piling up separate entries.
AppId={{8F3A6C21-4B7E-4D19-9A52-1E6D0C7B3F84}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; Per-user install into %LocalAppData%\Programs so no admin rights or UAC prompt
; are needed. Switch to "admin" + {autopf} if a machine-wide install is wanted.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\annotate-tool
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Outputs land next to the PyInstaller build so dist\ stays the one place to look.
OutputDir=..\dist\win
OutputBaseFilename=annotate-tool-setup-{#AppVersion}
SetupIconFile=icons\app.ico
UninstallDisplayIcon={app}\{#AppExeName}

; LZMA2/max brings the ~250MB onedir tree down to roughly a third.
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; recursesubdirs picks up the whole PyInstaller tree (_internal\ and friends).
Source: "..\dist\win\annotate-tool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
