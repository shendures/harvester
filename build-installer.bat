@echo off
REM 배포용 exe를 설치 프로그램(Setup.exe)으로 감싸는 배치 파일 (Windows 전용)
REM cmd/탐색기에서 PowerShell 스크립트(build-installer.ps1)를 바로 실행하기 위한 래퍼입니다.
REM Inno Setup은 Setup.exe를 만들 때 삭제 프로그램(uninstaller)도 함께 자동으로 포함하므로
REM (제어판 "프로그램 추가/제거", 시작 메뉴 "<AppName> 제거"), 별도 명령이 필요 없습니다.
REM 사용법: build-installer.bat [AppName] [AppVersion] [AppPublisher]
REM   먼저 build-exe.bat(또는 build-exe.ps1)으로 같은 AppName의 exe를 dist\에 빌드해둬야
REM   합니다. 인자를 생략하면 실행 중 직접 입력받으며, 비워두면 build-installer.ps1과
REM   동일한 기본값(DataCrawler / 1.0.0 / AppName과 동일)을 사용합니다.

chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_NAME=%~1"
set "APP_VERSION=%~2"
set "APP_PUBLISHER=%~3"

if "%APP_NAME%"=="" (
    set /p APP_NAME=설치 프로그램을 만들 exe의 AppName을 입력하세요(build-exe.bat으로 먼저 빌드 필요) [Enter=DataCrawler]:
)
if "%APP_NAME%"=="" set "APP_NAME=DataCrawler"

REM ps1도 이 존재 확인을 하지만, Version/Publisher를 다 입력받은 뒤에야 알려주면
REM 번거로우므로 여기서 먼저 확인해 빠르게 안내한다(ps1의 검증과 중복이지만 UX상 유익).
if not exist "%SCRIPT_DIR%dist\%APP_NAME%.exe" (
    echo.
    echo [오류] dist\%APP_NAME%.exe 가 없습니다.
    echo   먼저 build-exe.bat(또는 .\build-exe.ps1 -AppName %APP_NAME%)로 exe를 빌드하세요.
    echo.
    pause
    exit /b 1
)

if "%APP_VERSION%"=="" (
    set /p APP_VERSION=버전을 입력하세요 [Enter=1.0.0]:
)
if "%APP_VERSION%"=="" set "APP_VERSION=1.0.0"

if "%APP_PUBLISHER%"=="" (
    set /p APP_PUBLISHER=배포자명을 입력하세요 [Enter=%APP_NAME%]:
)
if "%APP_PUBLISHER%"=="" set "APP_PUBLISHER=%APP_NAME%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-installer.ps1" -AppName "%APP_NAME%" -AppVersion "%APP_VERSION%" -AppPublisher "%APP_PUBLISHER%"

if errorlevel 1 (
    echo.
    echo 설치 프로그램 생성 실패. 위 로그를 확인하세요.
    pause
    exit /b 1
)

echo.
echo 생성 완료: dist\%APP_NAME%-Setup.exe (실행 시 삭제 프로그램도 자동으로 함께 설치됩니다)
pause
