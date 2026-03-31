#define MyAppName "YCB"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "YCB"
#define MyAppExeName "YCB.exe"
#define MyOutputName "YCB-Setup-v0.1.0"

[Setup]
AppId={{B9C6CB8E-8F85-4E8D-B3F4-00C3D094F10A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\YCB
DefaultGroupName=YCB
DisableProgramGroupPage=yes
OutputDir=..\dist-setup
OutputBaseFilename={#MyOutputName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=..\ycb.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimp"; MessagesFile: "_local_inno\Inno Setup 6\Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "_local_inno\Inno Setup 6\Default.isl"

[CustomMessages]
chinesesimp.TypeFull=完整安装（推荐）
english.TypeFull=Full installation (recommended)
chinesesimp.TypeCompact=仅主程序
english.TypeCompact=Main program only
chinesesimp.TypeCustom=自定义安装
english.TypeCustom=Custom installation
chinesesimp.ComponentMain=主程序
english.ComponentMain=Main program
chinesesimp.ComponentYtDlp=安装 yt-dlp.exe（推荐）
english.ComponentYtDlp=Install yt-dlp.exe (recommended)
chinesesimp.ComponentFfmpeg=安装 ffmpeg.exe（推荐）
english.ComponentFfmpeg=Install ffmpeg.exe (recommended)
chinesesimp.ComponentDeno=安装 deno.exe（可选）
english.ComponentDeno=Install deno.exe (optional)
chinesesimp.TaskDesktopIcon=创建桌面快捷方式
english.TaskDesktopIcon=Create a desktop shortcut
chinesesimp.RunLaunch=启动 YCB
english.RunLaunch=Launch YCB

[Types]
Name: "full"; Description: "{cm:TypeFull}"
Name: "compact"; Description: "{cm:TypeCompact}"
Name: "custom"; Description: "{cm:TypeCustom}"; Flags: iscustom

[Components]
Name: "main"; Description: "{cm:ComponentMain}"; Types: full compact custom; Flags: fixed
Name: "comp_ytdlp"; Description: "{cm:ComponentYtDlp}"; Types: full custom
Name: "comp_ffmpeg"; Description: "{cm:ComponentFfmpeg}"; Types: full custom
Name: "comp_deno"; Description: "{cm:ComponentDeno}"; Types: custom

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\YCB.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: main
Source: "..\usage_intro.md"; DestDir: "{app}"; Flags: ignoreversion; Components: main
Source: "..\usage_intro_en.md"; DestDir: "{app}"; Flags: ignoreversion; Components: main
Source: "..\dist\backend_setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion

[Icons]
Name: "{group}\YCB"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\YCB"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:RunLaunch}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  ComponentsInfoPage: TOutputMsgWizardPage;
  InstallProgressPage: TOutputProgressWizardPage;
  ProgressTimerId: LongWord;
  ProgressFilePath: string;
  ResultFilePath: string;
  MissingFilePath: string;
  LogFilePath: string;
  SelectedComponentsCsv: string;
  MissingComponentsText: string;
  LastProgressMessage: string;
  FinishNoticeApplied: Boolean;

function SetTimer(hWnd, nIDEvent, uElapse, lpTimerFunc: LongWord): LongWord;
  external 'SetTimer@user32.dll stdcall';
function KillTimer(hWnd, uIDEvent: LongWord): Boolean;
  external 'KillTimer@user32.dll stdcall';

function WizardLangIsEnglish(): Boolean;
begin
  Result := CompareText(ActiveLanguage, 'english') = 0;
end;

function T(const Zh, En: string): string;
begin
  if WizardLangIsEnglish() then
    Result := En
  else
    Result := Zh;
end;

function GetInstallerLaunchLangCode(): string;
begin
  if WizardLangIsEnglish() then
    Result := 'en'
  else
    Result := 'zh';
end;

procedure WriteFirstLaunchLanguagePreference;
var
  PrefPath: string;
  JsonText: string;
  UserLocalFlagPath: string;
begin
  PrefPath := ExpandConstant('{app}\install_prefs.json');
  JsonText := '{' + #13#10 +
    '  "lang": "' + GetInstallerLaunchLangCode() + '"' + #13#10 +
    '}';
  SaveStringToFile(PrefPath, JsonText, False);
  UserLocalFlagPath := ExpandConstant('{localappdata}\YCB\.installer_lang_consumed');
  DeleteFile(UserLocalFlagPath);
  if CompareText(UserLocalFlagPath, ExpandConstant('{userappdata}\YCB\.installer_lang_consumed')) <> 0 then
    DeleteFile(ExpandConstant('{userappdata}\YCB\.installer_lang_consumed'));
end;


function GetSelectedOptionalComponents(): string;
var
  Value: string;
begin
  Value := '';
  if WizardIsComponentSelected('comp_ytdlp') then begin
    if Value <> '' then Value := Value + ',';
    Value := Value + 'yt-dlp';
  end;
  if WizardIsComponentSelected('comp_ffmpeg') then begin
    if Value <> '' then Value := Value + ',';
    Value := Value + 'ffmpeg';
  end;
  if WizardIsComponentSelected('comp_deno') then begin
    if Value <> '' then Value := Value + ',';
    Value := Value + 'deno';
  end;
  Result := Value;
end;

function GetUnselectedOptionalComponentsText(): string;
var
  Value: string;
begin
  Value := '';
  if not WizardIsComponentSelected('comp_ytdlp') then
    Value := Value + 'yt-dlp.exe' + #13#10;
  if not WizardIsComponentSelected('comp_ffmpeg') then
    Value := Value + 'ffmpeg.exe' + #13#10;
  if not WizardIsComponentSelected('comp_deno') then
    Value := Value + 'deno.exe' + #13#10;
  Result := Trim(Value);
end;

function ReadIniValue(const FileName, Section, Key, Default: string): string;
begin
  if FileExists(FileName) then
    Result := GetIniString(Section, Key, Default, FileName)
  else
    Result := Default;
end;

function GetDisplayComponentName(const ComponentName: string): string;
begin
  if ComponentName = 'yt-dlp' then
    Result := 'yt-dlp'
  else if ComponentName = 'ffmpeg' then
    Result := 'ffmpeg'
  else if ComponentName = 'deno' then
    Result := 'deno'
  else if (ComponentName = '(none)') or (ComponentName = '-') or (Trim(ComponentName) = '') then
    Result := T('未选择组件', 'No component selected')
  else if ComponentName = '(fatal)' then
    Result := T('安装器', 'Installer')
  else if ComponentName = '(args)' then
    Result := T('安装参数', 'Installer arguments')
  else if ComponentName = '(dir)' then
    Result := T('安装目录', 'Target directory')
  else
    Result := ComponentName;
end;

function GetPhaseHeadline(const PhaseName, DisplayComponentName: string): string;
begin
  if PhaseName = 'prepare' then
    Result := T('正在准备安装 ', 'Preparing ') + DisplayComponentName + '...'
  else if PhaseName = 'download' then
    Result := T('正在下载 ', 'Downloading ') + DisplayComponentName + '...'
  else if PhaseName = 'extract' then
    Result := T('正在解压 ', 'Extracting ') + DisplayComponentName + '...'
  else if PhaseName = 'verify' then
    Result := T('正在校验 ', 'Verifying ') + DisplayComponentName + '...'
  else if PhaseName = 'done' then
    Result := T('已安装 ', 'Installed ') + DisplayComponentName
  else if PhaseName = 'retry' then
    Result := T('正在重试安装 ', 'Retrying ') + DisplayComponentName + '...'
  else if PhaseName = 'skipped_existing' then
    Result := T('已跳过已存在的 ', 'Skipping existing ') + DisplayComponentName
  else if PhaseName = 'finished' then
    Result := T('可选组件安装完成', 'Optional component installation completed')
  else if PhaseName = 'skipped_all' then
    Result := T('未选择需要安装的可选组件', 'No optional components selected')
  else if PhaseName = 'error' then
    Result := T('安装失败：', 'Installation failed: ') + DisplayComponentName
  else
    Result := T('正在安装可选组件...', 'Installing optional components...');
end;

procedure RefreshProgressPageInternal;
var
  ComponentName: string;
  DisplayComponentName: string;
  PhaseName: string;
  MessageText: string;
  AttemptText: string;
  HeadlineText: string;
  BytesText: string;
  OverallProgress: Integer;
  ComponentProgress: Integer;
  CurrentBytes: Int64;
  TotalBytes: Int64;
  ComponentIndex: Integer;
  ComponentTotal: Integer;
  DetailText: string;
begin
  if not FileExists(ProgressFilePath) then
    Exit;

  ComponentName := ReadIniValue(ProgressFilePath, 'progress', 'component', '-');
  DisplayComponentName := GetDisplayComponentName(ComponentName);
  PhaseName := ReadIniValue(ProgressFilePath, 'progress', 'phase', '-');
  MessageText := ReadIniValue(ProgressFilePath, 'progress', 'message', '');
  AttemptText := ReadIniValue(ProgressFilePath, 'progress', 'attempt', '0') + '/' +
    ReadIniValue(ProgressFilePath, 'progress', 'max_attempts', '0');
  OverallProgress := StrToIntDef(ReadIniValue(ProgressFilePath, 'progress', 'overall_progress', '0'), 0);
  ComponentProgress := StrToIntDef(ReadIniValue(ProgressFilePath, 'progress', 'component_progress', '0'), 0);
  CurrentBytes := StrToInt64Def(ReadIniValue(ProgressFilePath, 'progress', 'current_bytes', '0'), 0);
  TotalBytes := StrToInt64Def(ReadIniValue(ProgressFilePath, 'progress', 'total_bytes', '0'), 0);
  ComponentIndex := StrToIntDef(ReadIniValue(ProgressFilePath, 'progress', 'component_index', '0'), 0);
  ComponentTotal := StrToIntDef(ReadIniValue(ProgressFilePath, 'progress', 'component_total', '0'), 0);

  if OverallProgress < 0 then OverallProgress := 0;
  if OverallProgress > 100 then OverallProgress := 100;
  if ComponentProgress < 0 then ComponentProgress := 0;
  if ComponentProgress > 100 then ComponentProgress := 100;

  HeadlineText := GetPhaseHeadline(PhaseName, DisplayComponentName);
  if (CurrentBytes > 0) or (TotalBytes > 0) then
    BytesText := Format('%s / %s', [IntToStr(CurrentBytes div 1024 div 1024) + ' MB', IntToStr(TotalBytes div 1024 div 1024) + ' MB'])
  else
    BytesText := T('暂无', 'N/A');

  DetailText :=
    HeadlineText + #13#10 +
    T('组件顺序: ', 'Component: ') + IntToStr(ComponentIndex) + '/' + IntToStr(ComponentTotal) + #13#10 +
    T('当前组件: ', 'Current Component: ') + DisplayComponentName + #13#10 +
    T('阶段标识: ', 'Phase: ') + PhaseName + #13#10 +
    T('单组件进度: ', 'Component Progress: ') + IntToStr(ComponentProgress) + '%' + #13#10 +
    T('总体进度: ', 'Overall Progress: ') + IntToStr(OverallProgress) + '%' + #13#10 +
    T('下载大小: ', 'Downloaded Size: ') + BytesText + #13#10 +
    T('重试次数: ', 'Retry Count: ') + AttemptText + #13#10 +
    T('状态说明: ', 'Status: ') + MessageText;

  InstallProgressPage.SetText(HeadlineText, DetailText);
  InstallProgressPage.SetProgress(OverallProgress, 100);

  if (MessageText <> '') and (MessageText <> LastProgressMessage) then
    LastProgressMessage := MessageText;
end;

procedure ProgressTimerProc(hWnd, Msg, IdEvent, Time: LongWord);
begin
  RefreshProgressPageInternal;
end;

procedure StartProgressPolling;
begin
  if ProgressTimerId = 0 then
    ProgressTimerId := SetTimer(0, 0, 400, CreateCallback(@ProgressTimerProc));
end;

procedure StopProgressPolling;
begin
  if ProgressTimerId <> 0 then begin
    KillTimer(0, ProgressTimerId);
    ProgressTimerId := 0;
  end;
end;

function ExecBackendInstaller(): Integer;
var
  Params: string;
  ResultCode: Integer;
begin
  ProgressFilePath := ExpandConstant('{tmp}\component_progress.ini');
  ResultFilePath := ExpandConstant('{tmp}\component_result.ini');
  MissingFilePath := ExpandConstant('{tmp}\manual_install_components.txt');
  LogFilePath := ExpandConstant('{tmp}\component_install.log');
  SelectedComponentsCsv := GetSelectedOptionalComponents();
  LastProgressMessage := '';

  if FileExists(ProgressFilePath) then DeleteFile(ProgressFilePath);
  if FileExists(ResultFilePath) then DeleteFile(ResultFilePath);
  if FileExists(MissingFilePath) then DeleteFile(MissingFilePath);
  if FileExists(LogFilePath) then DeleteFile(LogFilePath);

  Params :=
    '--dir "' + ExpandConstant('{app}') + '" ' +
    '--components "' + SelectedComponentsCsv + '" ' +
    '--retry 3 ' +
    '--timeout 300 ' +
    '--skip-existing ' +
    '--progress-file "' + ProgressFilePath + '" ' +
    '--result-file "' + ResultFilePath + '" ' +
    '--missing-components-file "' + MissingFilePath + '" ' +
    '--log-file "' + LogFilePath + '"';

  InstallProgressPage.SetText(
    T('正在安装可选组件...', 'Installing optional components...'),
    T('安装器正在准备下载与安装组件。', 'The installer is preparing optional component download and installation.'));
  InstallProgressPage.SetProgress(0, 100);
  InstallProgressPage.Show;

  StartProgressPolling;
  try
    if not Exec(ExpandConstant('{tmp}\backend_setup.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      ResultCode := 4;
  finally
    StopProgressPolling;
    RefreshProgressPageInternal;
    InstallProgressPage.Hide;
  end;

  Result := ResultCode;
end;

procedure UpdateMissingComponentsText;
var
  FileText: AnsiString;
  UnselectedText: string;
  CombinedText: string;
begin
  MissingComponentsText := '';
  if LoadStringFromFile(MissingFilePath, FileText) then
    MissingComponentsText := Trim(FileText);

  UnselectedText := GetUnselectedOptionalComponentsText();
  if UnselectedText <> '' then begin
    if MissingComponentsText <> '' then
      CombinedText := MissingComponentsText + #13#10 + UnselectedText
    else
      CombinedText := UnselectedText;
  end else begin
    CombinedText := MissingComponentsText;
  end;

  MissingComponentsText := Trim(CombinedText);
end;

procedure ApplyFinishNotice;
var
  NoticeText: string;
begin
  if FinishNoticeApplied then
    Exit;

  UpdateMissingComponentsText;
  if MissingComponentsText = '' then begin
    FinishNoticeApplied := True;
    Exit;
  end;

  NoticeText := #13#10#13#10 +
    T('以下组件未自动安装：', 'The following components were not installed automatically:') + #13#10 +
    MissingComponentsText + #13#10#13#10 +
    T('若要使用完整功能，请稍后手动安装这些组件。',
      'To use full functionality, please install these components manually later.');

  WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + NoticeText;
  FinishNoticeApplied := True;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  OptionalNotice: string;
begin
  Result := MemoDirInfo + NewLine + NewLine + MemoTypeInfo + NewLine + NewLine + MemoComponentsInfo;
  OptionalNotice := GetUnselectedOptionalComponentsText();
  if OptionalNotice <> '' then begin
    Result := Result + NewLine + NewLine +
      T('以下组件未勾选，安装器不会自动安装：', 'The following components are not selected and will not be installed automatically:') +
      NewLine + OptionalNotice + NewLine +
      T('若要使用完整功能，请稍后手动安装这些组件。',
        'To use full functionality, please install these components manually later.');
  end;
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

procedure InitializeWizard;
begin
  ComponentsInfoPage := CreateOutputMsgPage(
    wpSelectComponents,
    T('组件安装说明', 'Optional Components Notice'),
    T('以下组件会在安装过程中联网下载', 'The following components will be downloaded during setup'),
    T('已勾选组件会自动下载到程序目录；未勾选组件不会自动安装，后续若要使用完整功能需要手动安装。'#13#10#13#10'如需调整组件选择或安装目录，可点击“上一步”返回修改。',
      'Selected components will be downloaded into the application directory. Unselected components will be skipped and must be installed manually later for full functionality.'#13#10#13#10'If you need to change selected components or the install directory, click Back to revise them.'));

  InstallProgressPage := CreateOutputProgressPage(
    T('组件安装进度', 'Optional Component Installation Progress'),
    T('正在准备安装可选组件...', 'Preparing optional component installation...'));

  FinishNoticeApplied := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = ComponentsInfoPage.ID then begin
    WizardForm.BackButton.Visible := True;
    WizardForm.BackButton.Enabled := True;
  end;

  if CurPageID = wpFinished then
    ApplyFinishNotice;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  RetryChoice: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  WriteFirstLaunchLanguagePreference;

  repeat
    ResultCode := ExecBackendInstaller();
    UpdateMissingComponentsText;

    if ResultCode = 0 then
      Break;

    RetryChoice := MsgBox(
      T('可选组件安装失败。'#13#10#13#10'是：再试一次'#13#10'否：跳过失败组件并继续安装'#13#10'取消：终止安装',
        'Optional component installation failed.'#13#10#13#10'Yes: retry installation'#13#10'No: skip failed components and continue'#13#10'Cancel: abort setup'),
      mbError, MB_YESNOCANCEL);

    if RetryChoice = IDYES then
      continue;

    if RetryChoice = IDCANCEL then
      RaiseException(T('安装已取消：可选组件安装失败。', 'Setup cancelled: optional component installation failed.'));

    Break;
  until False;
end;
