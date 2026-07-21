# 배포용 exe를 Windows 설치 프로그램(Setup.exe)으로 감싸는 스크립트 (Windows PowerShell 전용)
# 사용법:
#   .\build-exe.ps1 -SeqNo 000000 -AppName DataCrawler   (exe 먼저 빌드)
#   .\build-installer.ps1 -AppName DataCrawler -AppVersion 1.0.0
#
# Inno Setup(무료, https://jrsoftware.org/isinfo.php)이 설치돼 있어야 하며,
# 이 스크립트는 커맨드라인 컴파일러 ISCC.exe를 PATH 또는 기본 설치 경로에서
# 찾아 installer.iss를 컴파일합니다. build-exe.ps1과 마찬가지로 -AppName은
# 실행 파일명뿐 아니라 설치 프로그램 이름(dist\<AppName>-Setup.exe)에도
# 그대로 쓰입니다.

param(
    [string]$AppName = "CollectorApp",
    [string]$AppVersion = "1.0.0",
    [string]$AppPublisher = $AppName
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# ── 1. 대상 exe 존재 확인 (build-exe.ps1로 먼저 빌드돼 있어야 함) ──────
$exePath = Join-Path $repoRoot "dist\$AppName.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "dist\$AppName.exe 가 없습니다. 먼저 .\build-exe.ps1 -SeqNo <SeqNo> -AppName $AppName 로 exe를 빌드하세요."
    exit 1
}

# ── 2. ISCC.exe(Inno Setup 커맨드라인 컴파일러) 탐색 ──────────────────
$isccCmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCmd) {
    $iscc = $isccCmd.Source
} else {
    $candidates = @(
        "$Env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${Env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        # winget 등으로 관리자 권한 없이 설치하면 시스템 전체가 아닌
        # 사용자별 경로에 설치됨(실측 확인, 2026-07-21) — 함께 탐색 대상에 포함
        "$Env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) {
        Write-Error "Inno Setup(ISCC.exe)을 찾을 수 없습니다. https://jrsoftware.org/isinfo.php 에서 설치한 뒤 다시 실행하세요."
        exit 1
    }
}

# ── 3. Inno Setup 컴파일 ───────────────────────────────────────────
& $iscc `
    "/DAppName=$AppName" `
    "/DAppVersion=$AppVersion" `
    "/DAppPublisher=$AppPublisher" `
    (Join-Path $repoRoot "installer.iss")

Write-Host ""
Write-Host "설치 프로그램 생성 완료: dist\$AppName-Setup.exe"
