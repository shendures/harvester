; Harvest(DataCrawler) 배포용 Inno Setup 스크립트
;
; build-exe.ps1이 PyInstaller로 만든 dist\{#AppName}.exe를 감싸 Windows 설치
; 프로그램(Setup.exe)으로 패키징합니다. build-installer.ps1이 이 스크립트를
; 호출하며, 직접 실행할 때는 아래처럼 값을 넘깁니다:
;   ISCC installer.iss /DAppName=DataCrawler /DAppVersion=1.0.0 /DAppPublisher="회사명"
;
; 전제: build-exe.ps1로 dist\{#AppName}.exe가 이미 빌드돼 있어야 합니다.

#ifndef AppName
  #define AppName "CollectorApp"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher AppName
#endif

[Setup]
; 고객마다 exe 파일명(AppName)이 다른 현재 배포 구조(utility.get_app_name())와
; 동일하게, AppId도 AppName을 그대로 사용합니다 — 같은 AppName으로 재설치하면
; 업그레이드로 처리되고, 다른 AppName(다른 고객)은 별개 설치로 공존합니다.
AppId={#AppName}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppName}.exe
OutputDir=dist
OutputBaseFilename={#AppName}-Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=combine-harvester.ico
DisableProgramGroupPage=yes

; 한국어 설치 화면을 쓰려면 Inno Setup 공식 사이트의 "Islands"(사용자 번역
; 언어팩) 추가 다운로드로 Korean.isl을 Languages 폴더에 넣은 뒤, 아래 절의
; 주석을 해제하세요. 기본은 별도 설치 없이 항상 동작하는 English만 사용합니다.
; [Languages]
; Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

; 앱 데이터(%LOCALAPPDATA%\{#AppName}\ 의 request_info.json/custom_rules/
; schedules.json)는 고객이 직접 수정했을 수 있어 제거 시 삭제하지 않습니다
; (의도적 기본값 — 데이터 유실 방지).

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; GroupDescription: "추가 아이콘:"

[Files]
Source: "dist\{#AppName}.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "설치 완료 후 {#AppName} 실행"; Flags: nowait postinstall skipifsilent
