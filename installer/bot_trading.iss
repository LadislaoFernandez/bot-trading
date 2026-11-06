; Instalador de Bot de trading para Windows (Inno Setup 6). Lo compila GitHub Actions:
;   iscc installer\bot_trading.iss /DVersion=1.4
; Necesita antes build\app (installer\armar_zip.py) y build\python (installer\preparar_python.ps1).

#define AppName "Bot de trading"
#ifndef Version
  #define Version "0.0"
#endif

[Setup]
AppId={{8F3C2A51-6B7D-4E0A-9C1B-2D5E7F903A14}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher=LadislaoFernandez
AppPublisherURL=https://github.com/LadislaoFernandez/bot-trading
DefaultDirName={localappdata}\Programs\BotTrading
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=BotTrading-Setup-{#Version}
SetupIconFile=..\app_icon.ico
UninstallDisplayIcon={app}\app_icon.ico
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
es.AutoInicio=Abrir el bot automáticamente al iniciar Windows
en.AutoInicio=Open the bot automatically when Windows starts
es.Opciones=Opciones:
en.Opciones=Options:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:Opciones}"
Name: "autostart"; Description: "{cm:AutoInicio}"; GroupDescription: "{cm:Opciones}"

[Files]
Source: "..\build\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "..\build\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BotTradingV2"; ValueData: "wscript.exe ""{app}\iniciar_oculto.vbs"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app.py"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
procedure CerrarBot();
var
  R: Integer;
begin
  { cierra la app del bot instalada en esta carpeta, si está abierta (no toca otras copias del bot) }
  Exec('powershell.exe', '-NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name=''pythonw.exe''\" | Where-Object { $_.CommandLine -like ''*' + ExpandConstant('{app}') + '\app.py*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
       '', SW_HIDE, ewWaitUntilTerminated, R);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CerrarBot();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Ajustes: String;
begin
  if CurStep = ssPostInstall then
  begin
    { primera instalación: la app arranca en el idioma elegido en el instalador }
    Ajustes := ExpandConstant('{app}\ajustes.json');
    if not FileExists(Ajustes) then
    begin
      if ActiveLanguage = 'en' then
        SaveStringToFile(Ajustes, '{"idioma": "en"}', False)
      else
        SaveStringToFile(Ajustes, '{"idioma": "es"}', False);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    CerrarBot();
end;
