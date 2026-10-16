# 고객 배포용 exe 빌드 스크립트 (Windows PowerShell 전용)
# 사용법: .\scripts\build-exe.ps1                       (실행 중 AppName을 직접 입력)
#        .\scripts\build-exe.ps1 -AppName DataCrawler
#        (어느 폴더에서 실행해도 저장소 루트를 기준으로 동작합니다)
#        cmd에서는: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-exe.ps1 ...
#
# 이 스크립트 하나가 가상환경 활성화, python/pyinstaller 사전 점검, 인자 대화형 입력,
# 빌드 전체를 처리합니다(과거 build-exe.bat 래퍼의 기능을 통합).
# -AppName을 명령줄로 주지 않으면 실행 중 입력받습니다(Enter만 치면 DataCrawler).
# DB의 active 블루프린트 전체가 항상 배포 대상에 포함됩니다.
#
# 무엇을 --add-data로 담을지는 이 파일에 내장된 Python 매니페스트 코드(1단계)가 결정합니다. 이 코드는
# 매 실행마다 DB(tb_blueprint, active=True)를 조회해 request_info.json을 새로 생성한 뒤, 그
# 내용을 근거로 (1) seq_no별 render/login/refine 규칙 파일과 (2) 고정 아이콘 자산
# (harvest/assets/combine-harvester.ico, harvest/assets/icon/)을 찾아 임시 스테이징 폴더에 모으고 그 결과를 manifest.json으로
# 저장합니다 — render/login/refine 파일의 실제 위치 판별은 conf.CustomModuleStorage.resolve_path()를
# 그대로 재사용해 앱 런타임과 로직이 어긋나지 않게 합니다(docs/DEV_ENV.md "커스텀 규칙 개발·검증·배포").
#
# render/·login/·refine/은 여러 고객의 규칙 파일을 함께 보관하는 "개발자용" 폴더입니다 — 그대로
# 통째로 번들에 넣으면 다른 고객의 정제/렌더링/로그인 로직까지 이번 exe에 함께 유출됩니다.
# 매니페스트 코드가 DB에서 가져온 active seq_no의 파일만 골라 스테이징하는 방식으로 이를
# 방지합니다.
#
# 이번 빌드에 포함할 고객은 로컬 파일이 아니라 DB에서 active로 표시하는 것으로 결정합니다.

param(
    # PyInstaller --name(exe 파일명)뿐 아니라 실행 시 %LOCALAPPDATA%\<AppName>\ 앱
    # 데이터 폴더명도 함께 결정합니다(utility.get_app_name()이 sys.executable의
    # 파일명을 읽어 자동으로 맞춥니다). 빌드 후 exe 파일명을 직접 바꾸면 다음 실행부터
    # 앱 데이터 폴더도 그 이름을 따라가므로, 기존에 시딩된 request_info.json/
    # render·login·refine을 못 찾는 것처럼 보일 수 있어 주의가 필요합니다.
    [string]$AppName = "DataCrawler"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
# python -m 실행과 PyInstaller 산출물(build/, dist/)이 항상 저장소 루트를 기준으로 생기게 한다.
Set-Location $repoRoot

# ── 0. 사전 준비: 가상환경 활성화, 도구 점검, 인자 입력 ─────────────
# Activate.ps1은 ExecutionPolicy에 막힐 수 있어 호출하지 않고, 활성화가 하는 일(PATH 앞에
# Scripts 추가, VIRTUAL_ENV 설정)만 직접 수행합니다. 이미 활성화돼 있으면 건드리지 않습니다.
if (-not $env:VIRTUAL_ENV) {
    foreach ($venvName in @(".venv", ".venv-win")) {
        $venvDir = Join-Path $repoRoot $venvName
        $scriptsDir = Join-Path $venvDir "Scripts"
        if (Test-Path (Join-Path $scriptsDir "activate.bat")) {
            $env:VIRTUAL_ENV = $venvDir
            $env:PATH = "$scriptsDir;$env:PATH"
            Write-Host "[정보] 가상환경 활성화: $venvDir"
            break
        }
    }
}

# where 대신 --version을 직접 실행한다 — Python 미설치 시 python이 스토어 스텁으로 해석되어
# 존재 여부만으로는 실제 실행 가능 여부를 알 수 없기 때문이다.
$toolsOk = $true
foreach ($tool in @("python", "pyinstaller")) {
    # 실행 파일이 PATH에 없으면 $LASTEXITCODE가 갱신되지 않아 앞 도구의 0이 남는다.
    # 그래서 존재 여부를 먼저 확인하고, 있을 때만 --version 종료 코드를 본다.
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $toolsOk = $false; continue }
    $ErrorActionPreference = "Continue"
    & $tool --version *> $null
    $toolExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($toolExit -ne 0) { $toolsOk = $false }
}
if (-not $toolsOk) {
    Write-Host ""
    Write-Host "[오류] 빌드에 필요한 python/pyinstaller를 실행할 수 없습니다."
    Write-Host "  $repoRoot\.venv\Scripts\ 또는 $repoRoot\.venv-win\Scripts\ 에서"
    Write-Host "  가상환경을 찾지 못했거나, 찾았어도 pyinstaller가 설치돼 있지 않습니다."
    Write-Host "  docs\DEV_ENV.md `"설치 및 설정`"을 참고해 가상환경을 준비하세요:"
    Write-Host "    python -m venv .venv"
    Write-Host "    .venv\Scripts\activate.bat"
    Write-Host "    pip install -r requirements.txt"
    exit 1
}

if (-not $PSBoundParameters.ContainsKey("AppName")) {
    $appInput = Read-Host "AppName을 입력하세요 [Enter=DataCrawler]"
    if ($appInput) { $AppName = $appInput }
}

# ── 1. 매니페스트 산출 (내장 Python) ──────────────────────────
# request_info.json 생성(DB 조회)과 seq_no별 render/login/refine 스테이징을 Python이 전담합니다
# (conf.py의 기존 경로 판별 로직을 그대로 재사용 — PowerShell에 같은 지식을 따로 두지 않기 위함).
$stagingRoot = Join-Path $repoRoot "_build_staging"
if (Test-Path $stagingRoot) { Remove-Item $stagingRoot -Recurse -Force }
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
$manifestPath = Join-Path $stagingRoot "manifest.json"

# 아래 Python 코드는 과거 harvest/tools/build_manifest.py였던 것을 그대로 내장한 것입니다.
# harvest.core.db_conn / utility / conf.CustomModuleStorage / tools.create_request_info를 재사용하므로
# 실행 시 저장소 루트가 import 경로에 있어야 합니다(아래 PYTHONPATH 설정).
$manifestPy = @'
"""
고객 배포용 exe에 PyInstaller --add-data로 포함해야 할 파일 목록(매니페스트)을 산출합니다.

request_info.json은 매 실행마다 DB(tb_blueprint, active=True)를 조회해 새로 생성합니다 —
로컬에 미리 준비해두는 파일이 아닙니다. 이번 빌드에 어떤 고객을 포함할지는 DB에서 해당
고객의 active 플래그를 켜두는 것으로 결정합니다(create_request_info.py와 동일한 쿼리·매핑
로직을 재사용 — ACTIVE_BLUEPRINT_QUERY, map_blueprints_to_request_info() 참고).

그 다음 (1) seq_no별 render/login/refine 규칙 파일과 (2) 고정 아이콘 자산
(harvest/assets/combine-harvester.ico, harvest/assets/icon/)을 찾아 스테이징 폴더에 모으고, build-exe.ps1이 그대로
PyInstaller --add-data 인자로 변환할 수 있는 JSON 파일로 저장합니다.

render/login/refine 파일의 실제 위치는 conf.CustomModuleStorage.resolve_path()를 그대로
재사용합니다 — 앱 런타임과 다른 판별 규칙을 이 스크립트가 따로 갖지 않도록 하기 위함입니다.
"""
import argparse
import json
import os
import shutil
import sys

from harvest.core import db_conn, utility
from harvest.core.conf import CustomModuleStorage
from harvest.config.create_request_info import ACTIVE_BLUEPRINT_QUERY, map_blueprints_to_request_info

KINDS = ("render", "login", "refine")


def fail(message: str) -> None:
    print(f"오류: {message}", file=sys.stderr)
    sys.exit(1)


def fetch_active_blueprints() -> tuple:
    """DB(tb_blueprint, active=True)를 조회해 (request_info_list, seq_nos)를 반환합니다.

    DB 접속정보를 못 읽거나 조회 결과가 비면 즉시 중단합니다 — db_conn.read_db_data()는
    연결 실패와 "active인 행이 진짜로 0건"을 구분하지 않고 똑같이 빈 리스트를 반환하므로,
    둘 다 조용히 넘기지 않고 명확한 오류로 멈추는 쪽을 택했습니다.
    """
    try:
        db_env = db_conn.get_params("PostgreSQL")
    except Exception as e:
        fail(
            f"DB 접속 정보를 읽지 못했습니다: {e}\n"
            "이 빌드 머신의 harvest/config/env/database.ini에 [PostgreSQL] 섹션(대소문자 정확히 일치)이 "
            "올바르게 구성되어 있는지 확인하세요."
        )

    print("DB에서 active 블루프린트를 조회하는 중입니다...")
    blueprint_rows = db_conn.read_db_data(db_env, ACTIVE_BLUEPRINT_QUERY)
    if not blueprint_rows:
        fail(
            "DB에서 active=True인 블루프린트를 하나도 가져오지 못했습니다. "
            "DB 연결 실패이거나 실제로 active인 데이터가 0건일 수 있습니다 — "
            "tb_blueprint를 직접 조회해 원인을 확인한 뒤 다시 시도하세요."
        )

    request_info_list = map_blueprints_to_request_info(blueprint_rows)
    seq_nos = []
    for i, blueprint in enumerate(request_info_list):
        if not blueprint.get("seq_no"):
            fail(f"DB에서 가져온 {i}번째 블루프린트에 seq_no가 없습니다.")
        seq_nos.append(blueprint["seq_no"])
    return request_info_list, seq_nos


def write_request_info(request_info_list: list, request_info_path: str) -> None:
    with open(request_info_path, "w", encoding="utf-8") as f:
        json.dump(request_info_list, f, ensure_ascii=False, indent=4)


def stage_custom_rules(seq_nos: list, staging_dir: str) -> list:
    """seq_no별 render/login/refine 규칙 파일을 staging_dir로 모으고,
    PyInstaller --add-data 항목({"src", "dest"} 딕셔너리) 목록으로 반환합니다."""
    storage = CustomModuleStorage()
    add_data = []
    any_found = False

    for seq_no in seq_nos:
        seq_has_file = False
        for kind in KINDS:
            src = storage.resolve_path(seq_no, kind)
            if not os.path.isfile(src):
                continue
            dest_dir = os.path.join(staging_dir, kind)
            os.makedirs(dest_dir, exist_ok=True)
            staged_path = os.path.join(dest_dir, f"{seq_no}.py")
            shutil.copy2(src, staged_path)
            print(f"포함: {kind}\\{seq_no}.py")
            add_data.append({"src": staged_path, "dest": f"harvest/config/{kind}"})
            seq_has_file = True
            any_found = True
        if not seq_has_file:
            print(f"경고: seq_no={seq_no}에 해당하는 규칙 파일이 없습니다(render/login/refine 모두).")

    if not any_found:
        print("경고: 어떤 seq_no에도 규칙 파일이 없습니다. 커스텀 규칙 없이 빌드를 계속합니다.")

    return add_data


def build_manifest(request_info_path: str, staging_dir: str) -> dict:
    request_info_list, actual_seq_nos = fetch_active_blueprints()
    write_request_info(request_info_list, request_info_path)
    print(
        f"request_info.json을 DB 기준으로 갱신했습니다 (active {len(actual_seq_nos)}건: "
        f"{', '.join(actual_seq_nos)})"
    )

    # request_info.json 원본과 고정 아이콘 자산(harvest/assets/combine-harvester.ico, harvest/assets/icon/)은
    # 고객 콘텐츠와 무관하게 항상 포함한다.
    add_data = [
        {"src": request_info_path, "dest": "harvest/config"},
        {"src": utility.asset_path("combine-harvester.ico"), "dest": "harvest/assets"},
        {"src": utility.asset_path("icon"), "dest": "harvest/assets/icon"},
    ]
    add_data.extend(stage_custom_rules(actual_seq_nos, staging_dir))

    return {"seq_nos": actual_seq_nos, "add_data": add_data}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="고객 배포용 exe에 포함할 --add-data 목록을 산출합니다.")
    parser.add_argument("--out", required=True, help="매니페스트 JSON을 저장할 경로")
    parser.add_argument("--staging-dir", required=True, help="seq_no별 규칙 파일을 모을 스테이징 폴더")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request_info_path = os.path.join(utility.config_dir(), "request_info.json")

    manifest = build_manifest(request_info_path, args.staging_dir)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
'@

$manifestPyPath = Join-Path $stagingRoot "_build_manifest.py"
# PowerShell 5.1의 파이프/Set-Content 기본 인코딩은 한글이 깨지므로 BOM 없는 UTF-8로 직접 기록한다.
[System.IO.File]::WriteAllText($manifestPyPath, $manifestPy, (New-Object System.Text.UTF8Encoding($false)))

$manifestScriptArgs = @(
    $manifestPyPath,
    "--out", $manifestPath,
    "--staging-dir", $stagingRoot
)

# PyInstaller 호출부와 동일한 이유(아래 2.의 주석 참고)로, 이 native 호출 주변에서만
# 일시적으로 $ErrorActionPreference를 낮추고 진짜 실패 여부는 $LASTEXITCODE로 판별합니다.
$ErrorActionPreference = "Continue"
$prevPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $repoRoot
python @manifestScriptArgs
$manifestExitCode = $LASTEXITCODE
$env:PYTHONPATH = $prevPythonPath
$ErrorActionPreference = "Stop"
if ($manifestExitCode -ne 0) {
    Write-Error "내장 매니페스트 단계가 실패했습니다 (종료 코드 $manifestExitCode). 위 로그를 확인하세요."
    exit 1
}

$manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$addDataArgs = @()
foreach ($entry in $manifest.add_data) {
    $addDataArgs += @("--add-data", "$($entry.src);$($entry.dest)")
}

# ── 2. PyInstaller 실행 ────────────────────────────────────────────
$iconPath = Join-Path $repoRoot "harvest\assets\combine-harvester.ico"

# harvest/crawler/scraper/ 패키지(scrapy.cfg 포함)는 Scrapy가 문자열
# 경로(ITEM_PIPELINES="harvest.crawler.scraper.pipelines.LoadItemPipeline",
# DOWNLOADER_MIDDLEWARES="harvest.crawler.scraper.middlewares.XXX")로 런타임에 동적
# import합니다. 코드 어디에도 `import harvest.crawler.scraper.pipelines` 같은 정적 import가
# 없어 PyInstaller의 자동 의존성 분석이 이 모듈들을 놓치므로 --add-data로
# 소스 그대로 번들에 넣어 일반 import 폴백이 찾을 수 있게 합니다.
# (고객 콘텐츠와 무관한 고정 항목이라 1단계 매니페스트 코드가 아니라 여기서 직접 추가합니다.)
$addDataArgs += @(
    "--add-data", "$(Join-Path $repoRoot 'harvest\crawler\scraper');harvest/crawler/scraper"
)

# 위 --add-data는 "디스크 폴백"이고, 이쪽이 1차 경로입니다. engine.py가
# harvest.crawler.scraper.items/spiders.*를 정적 import해 PyInstaller가 scraper 패키지
# 자체는 PYZ 아카이브에 넣는데, 정적 import가 없는 아래 3개만 PYZ에서 빠져
# "패키지는 PYZ, 일부 하위 모듈은 디스크"라는 혼합 상태가 됩니다. 원리상
# FrozenImporter가 scraper.__path__를 _MEIPASS\harvest\crawler\scraper로 잡아줘 해결되지만,
# 조용히 실패하면 커스텀 settings가 무시된 채 수집이 "성공"으로 끝나므로
# (과거 PR #66/#67의 장애 양상) 혼합에 기대지 않고 명시적으로 PYZ에 넣습니다.
$hiddenImportArgs = @()
foreach ($mod in @("harvest.crawler.scraper.settings", "harvest.crawler.scraper.middlewares", "harvest.crawler.scraper.pipelines")) {
    $hiddenImportArgs += @("--hidden-import", $mod)
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
    --distpath (Join-Path $repoRoot "dist") `
    --workpath (Join-Path $stagingRoot "work") `
    --specpath (Join-Path $stagingRoot "spec") `
    --onefile `
    --windowed `
    --icon $iconPath `
    @copyMetadataArgs `
    @hiddenImportArgs `
    @addDataArgs `
    (Join-Path $repoRoot "main.py")
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Error "pyinstaller가 실패했습니다 (종료 코드 $LASTEXITCODE). 위 로그를 확인하세요."
    exit 1
}

# ── 3. 스테이징 정리 ────────────────────────────────────────────────
Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue

# ── 4. 빌드 PC 앱데이터 정리 ────────────────────────────────────────
# exe에는 이 PC의 사용자 설정이 들어가지 않지만, 앱은 %LOCALAPPDATA%\<AppName>에 파일이 이미
# 있으면 번들 기본값으로 시딩하지 않습니다(BlueprintStorage). 직전 테스트의 설정·스케줄·통계
# 이력이 남지 않도록, 빌드 성공 후 이 폴더를 확인받고 삭제해 첫 실행이 항상 DB 기본값 시딩이 되게 합니다.
$appDataDir = $null
if ($env:LOCALAPPDATA -and $AppName -and $AppName -notmatch '[\\/]|\.\.') {
    $appDataDir = Join-Path $env:LOCALAPPDATA $AppName
}
if (-not $appDataDir) {
    Write-Host "[경고] 앱 데이터 폴더 경로를 안전하게 결정할 수 없어 정리를 건너뜁니다."
} elseif (Test-Path $appDataDir) {
    Write-Host ""
    Write-Host "빌드 PC의 앱 데이터 폴더: $appDataDir"
    Write-Host "저장된 설정·스케줄·통계 이력이 삭제됩니다."
    $resetAnswer = Read-Host "삭제하시겠습니까? [Y/n]"
    if (-not $resetAnswer -or $resetAnswer -match '^[yY]') {
        Remove-Item $appDataDir -Recurse -Force
        Write-Host "앱 데이터 폴더를 삭제했습니다."
    } else {
        Write-Host "앱 데이터 폴더 삭제를 건너뜁니다."
    }
} else {
    Write-Host "정리할 앱 데이터 폴더가 없습니다: $appDataDir"
}

Write-Host ""
Write-Host "빌드 완료: dist\$AppName.exe"
Write-Host "최초 실행 시 request_info.json / render / login / refine이 %LOCALAPPDATA%\$AppName\ 로 자동 시딩됩니다."
