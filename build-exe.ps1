# 고객 배포용 단일 exe 빌드 스크립트 (Windows PowerShell 전용)
# 사용법: .\build-exe.ps1 -SeqNo 000000
#
# 레포 루트의 request_info.json(.gitignore 대상, 배포할 고객의 blueprint)과
# custom_rules/{render,refine}/{SeqNo}.py를 PyInstaller로 하나의 exe에 담습니다.
#
# custom_rules/는 여러 고객의 규칙 파일을 함께 보관하는 "개발자용" 폴더입니다
# (guidelines/PREPROCESS.md §3.1a). 그대로 통째로 번들에 넣으면 다른 고객의
# 정제/렌더링 로직까지 이번 exe에 함께 유출됩니다 — 이 스크립트는 -SeqNo로
# 지정한 파일만 골라 임시 스테이징 폴더에 모은 뒤 그 폴더만 --add-data로
# 넘기는 방식으로 이를 방지합니다.
#
# request_info.json의 seq_no와 -SeqNo가 다르면 즉시 중단합니다 — 잘못된
# 고객 조합으로 패키징하는 실수를 빌드 시점에 막기 위함입니다.

param(
    [Parameter(Mandatory = $true)]
    [string]$SeqNo,

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

$requestInfo = Get-Content $requestInfoPath -Raw | ConvertFrom-Json
$actualSeqNo = if ($requestInfo -is [System.Array]) { $requestInfo[0].seq_no } else { $requestInfo.seq_no }
if ($actualSeqNo -ne $SeqNo) {
    Write-Error "request_info.json의 seq_no($actualSeqNo)가 -SeqNo($SeqNo)와 다릅니다. 다른 고객 파일이 섞여 들어갈 위험이 있어 중단합니다."
    exit 1
}

# ── 2. 해당 SeqNo의 custom_rules만 스테이징 (다른 고객 파일 유출 방지) ──
$stagingRoot = Join-Path $repoRoot "_build_staging"
$stagingCustomRules = Join-Path $stagingRoot "custom_rules"
if (Test-Path $stagingRoot) { Remove-Item $stagingRoot -Recurse -Force }

$foundAny = $false
foreach ($kind in @("render", "refine")) {
    $srcFile = Join-Path $repoRoot "custom_rules\$kind\$SeqNo.py"
    if (Test-Path $srcFile) {
        $destDir = Join-Path $stagingCustomRules $kind
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item $srcFile (Join-Path $destDir "$SeqNo.py")
        Write-Host "포함: custom_rules\$kind\$SeqNo.py"
        $foundAny = $true
    }
}
if (-not $foundAny) {
    Write-Host "경고: SeqNo=$SeqNo 에 해당하는 custom_rules 파일이 없습니다(render/refine 모두). 커스텀 규칙 없이 빌드를 계속합니다."
}

# ── 3. PyInstaller 실행 ────────────────────────────────────────────
$iconPath = Join-Path $repoRoot "combine-harvester.ico"

$addDataArgs = @("--add-data", "$requestInfoPath;.")
if ($foundAny) {
    $addDataArgs += @("--add-data", "$stagingCustomRules;custom_rules")
}

# 주의: Scrapy/Selenium/SQLAlchemy 등은 동적 import를 많이 써서 최초 빌드 시
# ModuleNotFoundError가 날 수 있습니다. 발생하는 모듈을 --hidden-import 또는
# --collect-all로 추가하면서 반복 확인하세요 (requirements.txt의
# pyinstaller-hooks-contrib가 일부는 자동으로 처리해줍니다).
pyinstaller `
    --name $AppName `
    --onefile `
    --windowed `
    --icon $iconPath `
    @addDataArgs `
    (Join-Path $repoRoot "main.py")

# ── 4. 스테이징 정리 ────────────────────────────────────────────────
Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "빌드 완료: dist\$AppName.exe"
Write-Host "최초 실행 시 request_info.json / custom_rules가 %LOCALAPPDATA%\$AppName\ 로 자동 시딩됩니다."
