# 고객 배포용 단일 exe 빌드 스크립트 (Windows PowerShell 전용)
# 사용법: .\build-exe.ps1 -SeqNo 000000
#
# 레포 루트의 request_info.json(.gitignore 대상, 배포할 고객의 blueprint)과
# render/, login/, refine/ 각 폴더의 {SeqNo}.py를 PyInstaller로 하나의 exe에 담습니다.
#
# render/·login/·refine/은 여러 고객의 규칙 파일을 함께 보관하는 "개발자용" 폴더입니다
# (guidelines/PREPROCESS.md §3.1a). 그대로 통째로 번들에 넣으면 다른 고객의
# 정제/렌더링/로그인 로직까지 이번 exe에 함께 유출됩니다 — 이 스크립트는 -SeqNo로
# 지정한 파일만 골라 임시 스테이징 폴더에 모은 뒤 그 폴더만 --add-data로
# 넘기는 방식으로 이를 방지합니다.
#
# request_info.json의 seq_no와 -SeqNo가 다르면 즉시 중단합니다 — 잘못된
# 고객 조합으로 패키징하는 실수를 빌드 시점에 막기 위함입니다.

param(
    [Parameter(Mandatory = $true)]
    [string]$SeqNo,

    # PyInstaller --name(exe 파일명)뿐 아니라 실행 시 %LOCALAPPDATA%\<AppName>\ 앱
    # 데이터 폴더명도 함께 결정합니다(utility.get_app_name()이 sys.executable의
    # 파일명을 읽어 자동으로 맞춥니다). 빌드 후 exe 파일명을 직접 바꾸면 다음 실행부터
    # 앱 데이터 폴더도 그 이름을 따라가므로, 기존에 시딩된 request_info.json/
    # render·login·refine을 못 찾는 것처럼 보일 수 있어 주의가 필요합니다.
    [string]$AppName = "CollectorApp"
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# ── 1. request_info.json 존재 및 seq_no 일치 확인 ──────────────────
$requestInfoPath = Join-Path $repoRoot "request_info.json"
if (-not (Test-Path $requestInfoPath)) {
    Write-Error "request_info.json이 레포 루트에 없습니다. 배포할 고객의 blueprint를 먼저 준비하세요."
    exit 1
}

# -Encoding UTF8 필수: Windows PowerShell은 지정 없이 Get-Content를 쓰면
# 시스템 기본 코드페이지(한글 Windows는 보통 CP949)로 읽어, request_info.json이
# UTF-8(Python이 저장)이면 한글이 깨지고 JSON 파싱 자체가 실패할 수 있음.
$requestInfo = Get-Content $requestInfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
$actualSeqNo = if ($requestInfo -is [System.Array]) { $requestInfo[0].seq_no } else { $requestInfo.seq_no }
if ($actualSeqNo -ne $SeqNo) {
    Write-Error "request_info.json의 seq_no($actualSeqNo)가 -SeqNo($SeqNo)와 다릅니다. 다른 고객 파일이 섞여 들어갈 위험이 있어 중단합니다."
    exit 1
}

# ── 2. 해당 SeqNo의 render/login/refine 규칙만 스테이징 (다른 고객 파일 유출 방지) ──
$stagingRoot = Join-Path $repoRoot "_build_staging"
if (Test-Path $stagingRoot) { Remove-Item $stagingRoot -Recurse -Force }

$foundKinds = @()
foreach ($kind in @("render", "login", "refine")) {
    $srcFile = Join-Path $repoRoot "$kind\$SeqNo.py"
    if (Test-Path $srcFile) {
        $destDir = Join-Path $stagingRoot $kind
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item $srcFile (Join-Path $destDir "$SeqNo.py")
        Write-Host "포함: $kind\$SeqNo.py"
        $foundKinds += $kind
    }
}
if ($foundKinds.Count -eq 0) {
    Write-Host "경고: SeqNo=$SeqNo 에 해당하는 규칙 파일이 없습니다(render/login/refine 모두). 커스텀 규칙 없이 빌드를 계속합니다."
}

# ── 3. PyInstaller 실행 ────────────────────────────────────────────
$iconPath = Join-Path $repoRoot "combine-harvester.ico"

# scrapy.cfg/settings.py/pipelines.py/middlewares.py는 Scrapy가 파일 탐색
# (scrapy.cfg) 또는 문자열 경로(ITEM_PIPELINES="pipelines.LoadItemPipeline",
# DOWNLOADER_MIDDLEWARES="middlewares.XXX")로 런타임에 동적 import합니다.
# 코드 어디에도 `import pipelines`/`import middlewares` 같은 정적 import가
# 없어 PyInstaller의 자동 의존성 분석이 이 모듈들을 놓치므로 --add-data로
# 소스 그대로 번들 루트에 넣어 일반 import 폴백이 찾을 수 있게 합니다.
# combine-harvester.ico도 --icon(exe 파일 아이콘)과는 별개로 layout.py가
# 트레이 아이콘으로 런타임에 파일 경로로 직접 읽으므로 데이터로 필요합니다.
$addDataArgs = @(
    "--add-data", "$requestInfoPath;.",
    "--add-data", "$(Join-Path $repoRoot 'scrapy.cfg');.",
    "--add-data", "$(Join-Path $repoRoot 'settings.py');.",
    "--add-data", "$(Join-Path $repoRoot 'pipelines.py');.",
    "--add-data", "$(Join-Path $repoRoot 'middlewares.py');.",
    "--add-data", "$(Join-Path $repoRoot 'spiders');spiders",
    "--add-data", "$iconPath;."
)
foreach ($kind in $foundKinds) {
    $addDataArgs += @("--add-data", "$(Join-Path $stagingRoot $kind);$kind")
}

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

# ── 4. 스테이징 정리 ────────────────────────────────────────────────
Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "빌드 완료: dist\$AppName.exe"
Write-Host "최초 실행 시 request_info.json / render / login / refine이 %LOCALAPPDATA%\$AppName\ 로 자동 시딩됩니다."
