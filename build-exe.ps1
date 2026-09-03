# 고객 배포용 exe 빌드 스크립트 (Windows PowerShell 전용)
# 사용법: .\build-exe.ps1                                    (DB의 active 블루프린트 전체 사용)
#        .\build-exe.ps1 -SeqNo 000000 000022 -AppName DataCrawler  (특정 seq_no 포함 여부 검증)
#
# 무엇을 --add-data로 담을지는 build_manifest.py(레포 루트)가 결정합니다. build_manifest.py는
# 매 실행마다 DB(tb_blueprint, active=True)를 조회해 request_info.json을 새로 생성한 뒤, 그
# 내용을 근거로 (1) seq_no별 render/login/refine 규칙 파일과 (2) 고정 아이콘 자산
# (combine-harvester.ico, icon/)을 찾아 임시 스테이징 폴더에 모으고 그 결과를 manifest.json으로
# 저장합니다 — render/login/refine 파일의 실제 위치 판별은 conf.CustomModuleStorage.resolve_path()를
# 그대로 재사용해 앱 런타임과 로직이 어긋나지 않게 합니다(guidelines/PREPROCESS.md §3.1a).
#
# render/·login/·refine/은 여러 고객의 규칙 파일을 함께 보관하는 "개발자용" 폴더입니다 — 그대로
# 통째로 번들에 넣으면 다른 고객의 정제/렌더링/로그인 로직까지 이번 exe에 함께 유출됩니다.
# build_manifest.py가 DB에서 가져온 active seq_no의 파일만 골라 스테이징하는 방식으로 이를
# 방지합니다.
#
# 이번 빌드에 포함할 고객은 로컬 파일이 아니라 DB에서 active로 표시하는 것으로 결정합니다.
# -SeqNo는 그 결과를 검증하는 용도입니다 — 지정하면 DB에서 가져온 active seq_no 목록에
# 지정한 값이 전부 포함되는지(부분집합) 확인해, 하나라도 없으면(예: 다중 사이트 고객인데
# 사이트 하나를 active 켜는 걸 깜빡한 경우) 즉시 중단합니다. 생략하면 이 검증을 건너뜁니다.

param(
    [string[]]$SeqNo = @(),

    # PyInstaller --name(exe 파일명)뿐 아니라 실행 시 %LOCALAPPDATA%\<AppName>\ 앱
    # 데이터 폴더명도 함께 결정합니다(utility.get_app_name()이 sys.executable의
    # 파일명을 읽어 자동으로 맞춥니다). 빌드 후 exe 파일명을 직접 바꾸면 다음 실행부터
    # 앱 데이터 폴더도 그 이름을 따라가므로, 기존에 시딩된 request_info.json/
    # render·login·refine을 못 찾는 것처럼 보일 수 있어 주의가 필요합니다.
    [string]$AppName = "CollectorApp"
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# ── 1. 매니페스트 산출 (build_manifest.py) ──────────────────────────
# request_info.json 생성(DB 조회)과 seq_no별 render/login/refine 스테이징을 Python이 전담합니다
# (conf.py의 기존 경로 판별 로직을 그대로 재사용 — PowerShell에 같은 지식을 따로 두지 않기 위함).
$stagingRoot = Join-Path $repoRoot "_build_staging"
if (Test-Path $stagingRoot) { Remove-Item $stagingRoot -Recurse -Force }
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
$manifestPath = Join-Path $stagingRoot "manifest.json"

$manifestScriptArgs = @(
    (Join-Path $repoRoot "build_manifest.py"),
    "--out", $manifestPath,
    "--staging-dir", $stagingRoot
)
if ($SeqNo.Count -gt 0) { $manifestScriptArgs += @("--seq-no") + $SeqNo }

# PyInstaller 호출부와 동일한 이유(아래 2.의 주석 참고)로, 이 native 호출 주변에서만
# 일시적으로 $ErrorActionPreference를 낮추고 진짜 실패 여부는 $LASTEXITCODE로 판별합니다.
$ErrorActionPreference = "Continue"
python @manifestScriptArgs
$manifestExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($manifestExitCode -ne 0) {
    Write-Error "build_manifest.py가 실패했습니다 (종료 코드 $manifestExitCode). 위 로그를 확인하세요."
    exit 1
}

$manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$addDataArgs = @()
foreach ($entry in $manifest.add_data) {
    $addDataArgs += @("--add-data", "$($entry.src);$($entry.dest)")
}

# ── 2. PyInstaller 실행 ────────────────────────────────────────────
$iconPath = Join-Path $repoRoot "combine-harvester.ico"

# scrapy.cfg/settings.py/pipelines.py/middlewares.py는 Scrapy가 파일 탐색
# (scrapy.cfg) 또는 문자열 경로(ITEM_PIPELINES="pipelines.LoadItemPipeline",
# DOWNLOADER_MIDDLEWARES="middlewares.XXX")로 런타임에 동적 import합니다.
# 코드 어디에도 `import pipelines`/`import middlewares` 같은 정적 import가
# 없어 PyInstaller의 자동 의존성 분석이 이 모듈들을 놓치므로 --add-data로
# 소스 그대로 번들 루트에 넣어 일반 import 폴백이 찾을 수 있게 합니다.
# (고객 콘텐츠와 무관한 고정 항목이라 build_manifest.py가 아니라 여기서 직접 추가합니다.)
$addDataArgs += @(
    "--add-data", "$(Join-Path $repoRoot 'scrapy.cfg');.",
    "--add-data", "$(Join-Path $repoRoot 'settings.py');.",
    "--add-data", "$(Join-Path $repoRoot 'pipelines.py');.",
    "--add-data", "$(Join-Path $repoRoot 'middlewares.py');.",
    "--add-data", "$(Join-Path $repoRoot 'spiders');spiders"
)

# Scrapy/Twisted 계열은 importlib.metadata로 설치된 패키지 정보를 조회하는데,
# PyInstaller는 기본적으로 이 메타데이터를 담지 않아 freeze 시 흔히 깨집니다
# (PackageNotFoundError 등). 아래 목록은 이 문제의 표준 해결책입니다.
$copyMetadataArgs = @()
foreach ($pkg in @(
    "cryptography", "cssselect", "defusedxml", "itemadapter", "itemloaders",
    "lxml", "packaging", "parsel", "protego", "pydispatcher", "pyopenssl",
    "queuelib", "service-identity", "tldextract", "twisted", "w3lib",
    "zope-interface"
)) {
    $copyMetadataArgs += @("--copy-metadata", $pkg)
}

# 주의: Selenium/SQLAlchemy 등 위 목록 밖의 의존성에서 여전히
# ModuleNotFoundError가 날 수 있습니다. 발생하는 모듈을 --hidden-import 또는
# --collect-all로 추가하면서 반복 확인하세요 (requirements.txt의
# pyinstaller-hooks-contrib가 일부는 자동으로 처리해줍니다).
# PyInstaller는 정상 진행 상황도 INFO 레벨로 stderr에 씁니다. 이 스크립트
# 최상단의 $ErrorActionPreference = "Stop" 상태에서 native 명령이 stderr에
# 한 줄이라도 쓰면 PowerShell이 이를 즉시 종료 오류로 취급해 실제로는
# 정상 진행 중인 pyinstaller를 첫 로그 줄에서 강제 중단시킵니다(Windows
# PowerShell 5.1 실 빌드로 재현·확인) — 그래서 이 호출 주변에서만 일시적으로
# "Continue"로 낮추고, 진짜 실패 여부는 $LASTEXITCODE로 직접 판별합니다.
$ErrorActionPreference = "Continue"
pyinstaller `
    --name $AppName `
    --onefile `
    --windowed `
    --icon $iconPath `
    @copyMetadataArgs `
    @addDataArgs `
    (Join-Path $repoRoot "main.py")
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Write-Error "pyinstaller가 실패했습니다 (종료 코드 $LASTEXITCODE). 위 로그를 확인하세요."
    exit 1
}

# ── 3. 스테이징 정리 ────────────────────────────────────────────────
Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "빌드 완료: dist\$AppName.exe"
Write-Host "최초 실행 시 request_info.json / render / login / refine이 %LOCALAPPDATA%\$AppName\ 로 자동 시딩됩니다."
