@echo off
REM 고객 배포용 exe 빌드 배치 파일 (Windows 전용)
REM cmd/탐색기에서 PowerShell 스크립트(build-exe.ps1)를 바로 실행하기 위한 래퍼입니다.
REM 실제 빌드 로직(요청 정보 검증, staging, PyInstaller 옵션)은 build-exe.ps1에 있습니다.
REM 사용법: build-exe.bat [SeqNo[,SeqNo...]] [AppName]
REM   SeqNo는 선택 사항입니다 — 비워두면(Enter만 입력) request_info.json에 담긴
REM   seq_no를 자동으로 사용합니다(build_manifest.py가 판단). 특정 고객임을 직접
REM   확인하고 싶을 때만 지정하면, request_info.json 내용과 대조해 다르면 중단합니다.
REM   다중 블루프린트(request_info.json이 여러 고객 배열)를 지정할 때는 SeqNo를
REM   쉼표로 구분해 전부 나열합니다(AppName과 위치가 섞이지 않도록 명령줄 인자로
REM   줄 때는 반드시 쉼표 사용). 예: build-exe.bat 000000,000022 DataCrawler
REM   인자를 생략하면 실행 중 직접 입력받으며, 이때는 쉼표·공백 둘 다 가능합니다.

chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "SEQ_NO=%~1"
set "APP_NAME=%~2"

REM ── 가상환경 자동 활성화 ─────────────────────────────────────────
REM build-exe.ps1은 python/pyinstaller를 PATH로만 찾으므로, 이 뒤에서
REM 띄우는 자식 PowerShell 프로세스가 상속할 PATH를 여기서 맞춰준다.
REM (주의) 하나의 괄호 블록 안에서 set한 값을 같은 블록 안에서 곧바로
REM 읽으면 cmd가 블록 진입 전 값으로 치환해버리는 함정이 있어, 아래는
REM 의도적으로 모두 중첩 없는 최상위 단일 줄 문장이다.
set "VENV_ACTIVATE="
if not defined VIRTUAL_ENV if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" set "VENV_ACTIVATE=%SCRIPT_DIR%.venv\Scripts\activate.bat"
if not defined VIRTUAL_ENV if not defined VENV_ACTIVATE if exist "%SCRIPT_DIR%.venv-win\Scripts\activate.bat" set "VENV_ACTIVATE=%SCRIPT_DIR%.venv-win\Scripts\activate.bat"
if defined VENV_ACTIVATE call "%VENV_ACTIVATE%"
if defined VENV_ACTIVATE echo [정보] 가상환경 활성화: %VENV_ACTIVATE%

REM ── 사전 점검: python/pyinstaller를 실제로 실행할 수 있는가 ────────
REM where 대신 --version을 직접 실행해 확인한다 — Windows는 Python
REM 미설치 시 python이 스토어 스텁으로 해석되어 where만으로는 실제
REM 실행 가능 여부를 판별할 수 없기 때문이다.
python --version >nul 2>nul
if errorlevel 1 goto :env_missing
pyinstaller --version >nul 2>nul
if errorlevel 1 goto :env_missing
goto :env_ready

:env_missing
echo.
echo [오류] 빌드에 필요한 python/pyinstaller를 실행할 수 없습니다.
echo   %SCRIPT_DIR%.venv\Scripts\ 또는 %SCRIPT_DIR%.venv-win\Scripts\ 에서
echo   가상환경을 찾지 못했거나, 찾았어도 pyinstaller가 설치돼 있지 않습니다.
echo   guidelines\BUILD_GUIDE.md "0. 전제 조건"을 참고해 가상환경을 준비하세요:
echo     python -m venv .venv
echo     .venv\Scripts\activate.bat
echo     pip install -r requirements.txt
echo   준비가 끝나면 이 창을 닫고 build-exe.bat을 다시 실행하세요.
echo.
pause
exit /b 1

:env_ready

if "%SEQ_NO%"=="" (
    set /p SEQ_NO=배포할 고객의 seq_no를 입력하세요(비워두면 자동 감지, 다중이면 쉼표 또는 공백으로 구분):
)
REM PowerShell -SeqNo는 배열 파라미터([string[]])이므로 쉼표를 공백으로 바꿔
REM 여러 개의 개별 인자로 전달한다(아래 powershell 호출에서 따옴표 없이 확장).
set "SEQ_NO=%SEQ_NO:,= %"

if "%APP_NAME%"=="" (
    set /p APP_NAME=AppName을 입력하세요 [Enter=CollectorApp]:
)

if "%SEQ_NO%"=="" (
    if "%APP_NAME%"=="" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-exe.ps1"
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-exe.ps1" -AppName "%APP_NAME%"
    )
) else (
    if "%APP_NAME%"=="" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-exe.ps1" -SeqNo %SEQ_NO%
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-exe.ps1" -SeqNo %SEQ_NO% -AppName "%APP_NAME%"
    )
)

if errorlevel 1 (
    echo.
    echo 빌드 실패. 위 로그를 확인하세요.
    pause
    exit /b 1
)

echo.
echo 빌드 완료.
pause
