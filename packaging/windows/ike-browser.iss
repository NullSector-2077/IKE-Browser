; Installer of I.K.E. for Windows (Inno Setup 6). Built by packaging/windows/build.py:
;
;   ISCC /DAppVersion=1.2.0 /DSourceDir=<folder to install> /DOutputDir=<where the setup goes>
;        /DIconFile=<ike-browser.ico> /DLicenseFile=<LICENSE> ike-browser.iss
;
; For one user, without administrator rights: the program goes into the
; user's own %LOCALAPPDATA%\Programs\I.K.E (a folder name cannot end with a
; dot on Windows), a shortcut into the Start menu, and - if the user leaves
; the box ticked - the entries under HKEY_CURRENT_USER that let Windows list
; I.K.E. among the browsers in Settings → Default apps. Nothing is written
; outside the user's profile and registry branch; nothing changes which
; browser is the default.
;
; The uninstaller removes all of that. It does not touch the user's data
; (%APPDATA%\ike-browser and %LOCALAPPDATA%\ike-browser): bookmarks,
; passwords, history and settings stay, as they do on Linux when the package
; is removed. docs/platforms/windows.md says how to delete them by hand.

#ifndef AppVersion
  #error AppVersion is not defined (use packaging/windows/build.py)
#endif
#ifndef SourceDir
  #error SourceDir is not defined (use packaging/windows/build.py)
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

#define AppName "I.K.E."
#define AppLongName "I.K.E. - Internet Kontrol Experience"
#define AppExe "ike-browser.exe"
#define AppUserModelID "IKE.Browser"
#define ProgId "IKEBrowserHTML"
#define ClientKey "Software\Clients\StartMenuInternet\IKE Browser"

[Setup]
AppId={{6C1D3E0B-7F3A-4D5E-9B1C-1A2E5F7C9D42}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=The I.K.E. project
AppPublisherURL=https://github.com/NullSector-2077/IKE-Browser
AppSupportURL=https://github.com/NullSector-2077/IKE-Browser/issues
AppUpdatesURL=https://github.com/NullSector-2077/IKE-Browser/releases
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription={#AppLongName} - setup
VersionInfoProductName={#AppName}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\I.K.E
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=ike-browser-{#AppVersion}-windows-x64-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
#ifdef IconFile
SetupIconFile={#IconFile}
#endif
#ifdef LicenseFile
LicenseFile={#LicenseFile}
#endif
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; a running I.K.E. creates this (ike/winapi.py): setup and uninstall ask to close it first
AppMutex=IKE.Browser.Running
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
english.RegisterBrowser=List I.K.E. among the browsers in Windows' "Default apps" (your default browser is not changed)
italian.RegisterBrowser=Elenca I.K.E. tra i browser nelle "App predefinite" di Windows (il browser predefinito non viene cambiato)
spanish.RegisterBrowser=Incluir I.K.E. entre los navegadores en "Aplicaciones predeterminadas" de Windows (no cambia el navegador predeterminado)
french.RegisterBrowser=Proposer I.K.E. parmi les navigateurs dans « Applications par défaut » de Windows (le navigateur par défaut ne change pas)
german.RegisterBrowser=I.K.E. unter den Browsern in den „Standard-Apps“ von Windows aufführen (der Standardbrowser wird nicht geändert)
portuguese.RegisterBrowser=Listar o I.K.E. entre os navegadores em "Aplicações predefinidas" do Windows (o navegador predefinido não é alterado)
japanese.RegisterBrowser=Windows の「既定のアプリ」のブラウザー一覧に I.K.E. を表示する（既定のブラウザーは変更されません）

[Tasks]
Name: "registerbrowser"; Description: "{cm:RegisterBrowser}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"; Comment: "{#AppLongName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; AppUserModelID: "{#AppUserModelID}"; Comment: "{#AppLongName}"; Tasks: desktopicon

[Registry]
; All under HKEY_CURRENT_USER, all removed by the uninstaller. They only make
; I.K.E. one of the choices in Settings → Default apps.
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "I.K.E. HTML Document"; Flags: uninsdeletekey; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: "AppUserModelID"; ValueData: "{#AppUserModelID}"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\Application"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\Application"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#AppExe},0"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\Application"; ValueType: string; ValueName: "AppUserModelId"; ValueData: "{#AppUserModelID}"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}"; ValueType: string; ValueName: ""; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"""; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{#AppLongName}: a light, independent web browser focused on privacy"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#AppExe},0"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities\URLAssociations"; ValueType: string; ValueName: "http"; ValueData: "{#ProgId}"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities\URLAssociations"; ValueType: string; ValueName: "https"; ValueData: "{#ProgId}"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".htm"; ValueData: "{#ProgId}"; Tasks: registerbrowser
Root: HKCU; Subkey: "{#ClientKey}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".html"; ValueData: "{#ProgId}"; Tasks: registerbrowser
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "IKE Browser"; ValueData: "{#ClientKey}\Capabilities"; Flags: uninsdeletevalue; Tasks: registerbrowser

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; what Python may have written next to the installed files (compiled copies)
Type: filesandordirs; Name: "{app}\ike"
Type: filesandordirs; Name: "{app}\vendor"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\licenses"
Type: files; Name: "{app}\__pycache__\*"
Type: dirifempty; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"
