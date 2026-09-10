; =====================================================================
; Inno Setup - Instalador de Lynx (ACW PLAFT UAFE) - Beta 2.5
; =====================================================================
; Requiere que "python -m PyInstaller lynx.spec" se haya corrido antes -
; este script empaqueta la salida de PyInstaller (dist\Lynx.exe), no
; compila nada de Python por su cuenta.
;
; Instala SIN permisos de administrador (en la carpeta del usuario).
; Pide las credenciales durante la instalacion y genera el .env
; automaticamente en %APPDATA%\Lynx\ - mismo patron ya validado en el
; proyecto hermano (ACW - Informes Legales).
;
; Verifica que Google Chrome este instalado: el programa usa
; channel="chrome" en Playwright (Chrome REAL, no el Chromium
; empaquetado de Playwright), asi que sin Chrome no funciona.
; =====================================================================

#define NombreApp "Lynx"
#define VersionApp "2.5-beta"
#define PublicadorApp "Enlace"
#define EjecutableApp "Lynx.exe"

[Setup]
AppId={{8F3A1C7E-4B2D-4E9A-9C5F-7D1E3A6B8C24}
AppName={#NombreApp}
AppVersion={#VersionApp}
AppVerName={#NombreApp} {#VersionApp}
AppPublisher={#PublicadorApp}
DefaultDirName={userpf}\{#NombreApp}
DefaultGroupName={#NombreApp}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=instalador_salida
OutputBaseFilename=Lynx_Setup_{#VersionApp}
SetupIconFile=assets\lynx_icono.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Ejecutable unico (nuestro lynx.spec genera un solo .exe, a diferencia
; del proyecto hermano que genera una carpeta con _internal/)
Source: "dist\{#EjecutableApp}"; DestDir: "{app}"; Flags: ignoreversion
; Plantilla del Excel (por si se usa LocalExcelWriter en vez de Graph)
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data\staging"
Name: "{app}\data\logs"
Name: "{userappdata}\{#NombreApp}"

[Icons]
Name: "{group}\{#NombreApp}"; Filename: "{app}\{#EjecutableApp}"
Name: "{group}\Editar configuración (.env)"; Filename: "notepad.exe"; Parameters: """{userappdata}\{#NombreApp}\.env"""
Name: "{group}\Desinstalar {#NombreApp}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#NombreApp}"; Filename: "{app}\{#EjecutableApp}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#EjecutableApp}"; Description: "Ejecutar {#NombreApp} ahora"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Se borran las carpetas de trabajo, PERO NO %APPDATA%\Lynx\.env -
; la configuracion sobrevive a la desinstalacion a proposito, para no
; perder credenciales al actualizar de version.
Type: filesandordirs; Name: "{app}\data"

[Code]
var
  PaginaAzure: TInputQueryWizardPage;
  PaginaServicios: TInputQueryWizardPage;

{ Busca Google Chrome en las 3 ubicaciones tipicas de Windows:
  Program Files, Program Files (x86), y la instalacion por usuario
  (Chrome se puede instalar sin permisos de admin en LocalAppData). }
function ChromeEstaInstalado(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{commonpf}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

function InitializeSetup(): Boolean;
var
  Respuesta: Integer;
begin
  Result := True;

  if not ChromeEstaInstalado() then
  begin
    Respuesta := MsgBox(
      'No se encontro Google Chrome en este equipo.' + #13#10 + #13#10 +
      'Lynx necesita Google Chrome instalado para funcionar (usa el navegador ' +
      'real, no una version propia).' + #13#10 + #13#10 +
      'Puedes continuar con la instalacion, pero el programa NO va a poder ' +
      'consultar los sitios web hasta que instales Chrome desde:' + #13#10 +
      'https://www.google.com/chrome/' + #13#10 + #13#10 +
      '¿Deseas continuar de todas formas?',
      mbConfirmation, MB_YESNO);

    if Respuesta = IDNO then
      Result := False;
  end;
end;

procedure InitializeWizard;
begin
  PaginaAzure := CreateInputQueryPage(wpSelectDir,
    'Credenciales de Microsoft Graph API',
    'Necesarias para leer y escribir el Excel real en OneDrive',
    'Ingresa los valores proporcionados por TI (Entra ID / App Registration). ' +
    'Si aun no los tienes, puedes dejarlos en blanco y configurarlos despues ' +
    'editando el archivo .env (hay un acceso directo en el menu inicio).');
  PaginaAzure.Add('Tenant ID:', False);
  PaginaAzure.Add('Client ID:', False);
  PaginaAzure.Add('Client Secret:', True);
  PaginaAzure.Add('Drive ID:', False);
  PaginaAzure.Add('Item ID del Excel:', False);

  PaginaServicios := CreateInputQueryPage(PaginaAzure.ID,
    'Credenciales de Servicios Externos',
    'API keys para resolucion de captcha y resumen con IA',
    'La de 2Captcha resuelve automaticamente los captchas de los portales. ' +
    'La de OpenAI genera los resumenes de procesos judiciales.');
  PaginaServicios.Add('2Captcha API Key:', True);
  PaginaServicios.Add('OpenAI API Key:', True);
  PaginaServicios.Add('Cuenta de OneDrive (ej. unidadq@enlace.ec):', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RutaConfig: string;
  RutaEnvDestino: string;
  ContenidoEnv: TStringList;
  CuentaOneDrive: string;
begin
  if CurStep = ssPostInstall then
  begin
    RutaConfig := ExpandConstant('{userappdata}\{#NombreApp}');
    if not DirExists(RutaConfig) then
      CreateDir(RutaConfig);

    RutaEnvDestino := RutaConfig + '\.env';

    { Solo se genera si NO existe ya - al reinstalar/actualizar, la
      configuracion real del usuario NO se pisa. }
    if not FileExists(RutaEnvDestino) then
    begin
      CuentaOneDrive := PaginaServicios.Values[2];
      if CuentaOneDrive = '' then
        CuentaOneDrive := 'unidadq@enlace.ec';

      ContenidoEnv := TStringList.Create;
      try
        ContenidoEnv.Add('# Generado durante la instalacion de Lynx ' + '{#VersionApp}');
        ContenidoEnv.Add('# Editar aqui si alguna credencial cambia.');
        ContenidoEnv.Add('');
        ContenidoEnv.Add('# --- Microsoft Graph API (OneDrive + Excel) ---');
        ContenidoEnv.Add('AZURE_TENANT_ID=' + PaginaAzure.Values[0]);
        ContenidoEnv.Add('AZURE_CLIENT_ID=' + PaginaAzure.Values[1]);
        ContenidoEnv.Add('AZURE_CLIENT_SECRET=' + PaginaAzure.Values[2]);
        ContenidoEnv.Add('GRAPH_DRIVE_ID=' + PaginaAzure.Values[3]);
        ContenidoEnv.Add('GRAPH_EXCEL_ITEM_ID=' + PaginaAzure.Values[4]);
        ContenidoEnv.Add('CUENTA_ONEDRIVE=' + CuentaOneDrive);
        ContenidoEnv.Add('');
        ContenidoEnv.Add('# --- Resolucion automatica de captcha (2Captcha) ---');
        ContenidoEnv.Add('CAPTCHA_ENABLED=true');
        ContenidoEnv.Add('CAPTCHA_PROVIDER=2captcha');
        ContenidoEnv.Add('CAPTCHA_API_KEY=' + PaginaServicios.Values[0]);
        ContenidoEnv.Add('');
        ContenidoEnv.Add('# --- Resumenes con IA (OpenAI) ---');
        ContenidoEnv.Add('AI_SUMMARY_ENABLED=true');
        ContenidoEnv.Add('AI_SUMMARY_API_KEY=' + PaginaServicios.Values[1]);
        ContenidoEnv.Add('AI_SUMMARY_MODEL=gpt-4o-mini');
        ContenidoEnv.Add('');
        ContenidoEnv.Add('# --- Rutas locales y auditoria ---');
        ContenidoEnv.Add('LOCAL_DOWNLOAD_DIR=./data/staging');
        ContenidoEnv.Add('LOG_DIR=./data/logs');
        ContenidoEnv.Add('PROCESS_RUN_USER=bot-debida-diligencia');
        ContenidoEnv.SaveToFile(RutaEnvDestino);
      finally
        ContenidoEnv.Free;
      end;
    end;
  end;
end;
