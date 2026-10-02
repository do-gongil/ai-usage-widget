; Inno Setup 스크립트: dist\release\UsageWidget → dist\ai-usage-widget-setup.exe
; build_widget.bat이 publish 후 ISCC로 컴파일한다. 버전은 /DAppVersion=x.y.z 로 넘긴다.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C0B7E2A-3F1D-4C55-9A7E-5D2B8F41C0A7}
AppName=AI Usage Widget
AppVersion={#AppVersion}
AppPublisher=do-gongil
AppPublisherURL=https://github.com/do-gongil/ai-usage-widget
; 관리자 권한 없이 사용자 폴더에 설치
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\ai-usage-widget
DefaultGroupName=AI Usage Widget
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=ai-usage-widget-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\UsageWidget.exe
; 앱이 실행 중이면 설치/제거 전에 종료하라고 안내 (앱의 단일 인스턴스 뮤텍스)
AppMutex=Local\UsageTray.SingleInstance
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\release\UsageWidget\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI Usage Widget"; Filename: "{app}\UsageWidget.exe"
Name: "{group}\{cm:UninstallProgram,AI Usage Widget}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AI Usage Widget"; Filename: "{app}\UsageWidget.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UsageWidget.exe"; Description: "{cm:LaunchProgram,AI Usage Widget}"; Flags: nowait postinstall skipifsilent

[Code]
// 제거 시 앱이 등록한 "시작 시 실행" 항목도 지운다 (설정 %APPDATA%\UsageTray 는 남김)
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'UsageTray');
end;
