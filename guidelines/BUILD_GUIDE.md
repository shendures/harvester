# BUILD_GUIDE — Windows exe 빌드 및 배포 가이드

> DataCrawler(Harvest)를 고객 배포용 `.exe` / 설치 프로그램(`Setup.exe`)으로 빌드하는
> 절차를 다룹니다. 함께 관리되는 문서:
> - **빌드 스크립트 도입·수정 이력**: `HISTORY.md` (PR #64·#65·#66, 이슈㉗·㉘ 등)
> - **알려진 이슈**: `ISSUES.md` (이슈㉕·㉗·㉘)
> - **아키텍처 개요**: `PROJECT_REPORT.md` §6 의존성 요약

- **최신 갱신**: 2026-09-03 22:19

---

## 0. 전제 조건

- **반드시 Windows 환경에서 실행**해야 합니다(PowerShell 또는 일반 명령 프롬프트/cmd 모두
  가능 — 아래 `build-exe.bat` 참고). `build-exe.ps1`/`build-installer.ps1` 모두 Windows 전용
  스크립트이며, PyInstaller가 만드는 `.exe`도 Windows 바이너리입니다(WSL/Linux에서는 빌드할
  수 없습니다).
- Python 3.12 이상 + `requirements.txt`의 패키지가 설치되어 있어야 합니다(`pyinstaller`,
  `pyinstaller-hooks-contrib` 포함). 가상환경을 쓰는 경우:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
  **주의**: WSL 네이티브 경로(`/home/...`)의 저장소 클론에서는 `.venv`가 WSL 실행/테스트용
  가상환경(Python 3.12, `guidelines/STUDY_WSL_DB_CONNECT.md` 등 참고)으로 이미 쓰이고
  있습니다 — 이 클론에서 위 명령을 그대로 실행하면 그 가상환경을 덮어씁니다. Windows
  빌드는 반드시 Windows 네이티브 경로(`/mnt/c`, `/mnt/d` 등)의 별도 클론에서, 또는 최소한
  다른 이름(`.venv-win` 등)의 가상환경으로 진행하세요.
  이 최초 1회 준비(가상환경 생성 + `pip install`)는 `build-exe.bat`이 대신해주지 않습니다 —
  아래 2단계의 자동 활성화는 **이미 만들어진** `.venv`/`.venv-win`을 찾아 매번 activate하는
  것만 대신합니다.
- **빌드 시 DB 접속이 반드시 필요합니다.** `build_manifest.py`가 매 빌드마다 DB(`tb_blueprint`
  테이블)를 조회해 `request_info.json`을 새로 생성하므로(1단계 참고), 이 빌드 머신에
  `env/database.ini`가 `[PostgreSQL]` 섹션(대소문자 정확히 일치)으로 올바르게 구성돼 있고
  DB에 네트워크로 접속 가능해야 합니다(`env/`는 `.gitignore` 대상이라 머신마다 개별 준비).
- 설치 프로그램(`Setup.exe`)까지 만들려면 [Inno Setup](https://jrsoftware.org/isinfo.php)이
  추가로 필요합니다(무료, Windows 전용 외부 도구 — Python 패키지 아님).

---

## 1. 배포할 고객의 청사진(blueprint) 준비

`request_info.json`은 더 이상 로컬에서 직접 준비하는 파일이 아닙니다 — **2단계의
`build_manifest.py`가 빌드할 때마다 DB(`tb_blueprint` 테이블의 `active = True` 행 전체)를
조회해 자동으로 생성/덮어씁니다.** "이번 빌드에 어떤 고객을 포함할지"는 로컬 JSON 편집이
아니라 **DB에서 해당 고객의 `active` 플래그를 켜두는 것**으로 결정합니다(2개 이상이면
`main.py`가 다중 수집 레이아웃을 자동 선택하는 것은 이전과 동일).

빌드 전 준비할 것은 다음 두 가지뿐입니다.

1. **이 빌드 머신의 `env/database.ini`가 올바르게 구성되어 있어야 합니다.** `[PostgreSQL]`
   섹션(대소문자 정확히 일치)에 이 머신 기준으로 유효한 `host`/`port`/`database`/`user`/
   `password`가 있어야 `build_manifest.py`가 DB에 접속할 수 있습니다(`env/`는 `.gitignore`
   대상이라 각 머신에 개별 준비).

   > **주의(WSL 개발 환경 전용 host 값)**: 이 저장소를 WSL에서 개발용으로 클론해 쓰는 경우
   > `env/database.ini`의 `host`가 `172.22.224.1`처럼 WSL→Windows 게이트웨이를 가리키는
   > 특수 주소로 되어 있을 수 있습니다(배경은 `guidelines/STUDY_WSL_DB_CONNECT.md` 참고).
   > 이는 **그 WSL 환경에서만 유효한 값**이며, 실제 고객 배포 빌드를 수행하는 다른
   > 머신(별도의 Windows 네이티브 클론 등)에서는 그 머신 기준으로 DB에 실제로 도달
   > 가능한 host(예: `localhost`, 사내 DB 서버 주소)로 별도 구성해야 합니다. 이 값을
   > 그대로 복사해 쓰면 빌드가 DB 연결 실패로 즉시 중단됩니다.
   >
   > **주의(섹션명 대소문자)**: `env/create_ini.py`로 새로 생성한 템플릿은 섹션명이
   > `[postgresql]`(소문자)입니다. `db_conn.get_params("PostgreSQL")`은 `ConfigParser`의
   > 대소문자 구분 규칙 때문에 정확히 `[PostgreSQL]`(대문자 P)이어야 인식합니다 —
   > 템플릿을 그대로 쓰면 파일이 있어도 "Section not found" 오류로 빌드가 중단되니
   > 섹션명을 직접 맞춰주세요.

2. **(필요 시) 커스텀 규칙** — `render/{seq_no}.py`(렌더링), `login/{seq_no}.py`(로그인),
   `refine/{seq_no}.py`(정제) 중 해당 고객에게 필요한 파일. **이 절차는 DB 연동과 무관하게
   이전과 동일합니다** — 여전히 로컬 파일로 관리합니다. DB에 active인 고객이 여럿이면 각
   `seq_no`별로 필요한 파일을 모두 준비하세요. 작성법은 `PREPROCESS.md` §3.1a 참고.

> `render/`·`login/`·`refine/`은 여러 고객의 규칙 파일을 함께 보관하는 개발자용 폴더입니다.
> 2단계의 `build_manifest.py`가 DB에서 가져온 active `seq_no`의 파일만 골라 담기 때문에,
> 이 폴더에 다른 고객 파일이 섞여 있어도 이번 빌드에는 포함되지 않습니다.

> **주의(request_info.json은 매 빌드마다 DB 기준으로 덮어써집니다)**: `build_manifest.py`를
> 실행하면 레포 루트의 `request_info.json`이 DB 조회 결과로 항상 새로 생성/덮어써집니다.
> 로컬에서 이 파일을 직접 수정해 테스트하던 습관이 있었다면 더 이상 유효하지 않습니다 —
> 변경 사항은 DB(`tb_blueprint`)에 반영해야 다음 빌드에 반영됩니다.

---

## 2. exe 빌드 — `build-exe.ps1`

```powershell
.\build-exe.ps1 -AppName DataCrawler
# DB(tb_blueprint, active=True)에서 자동으로 조회해 request_info.json을 생성합니다
# (다중 블루프린트도 전부 자동 포함). 특정 고객이 실제로 포함됐는지 검증하고 싶을
# 때만 -SeqNo를 지정하세요(다중이면 모두 나열) — 필터가 아니라 검증용입니다.
.\build-exe.ps1 -SeqNo 000000 000022 -AppName DataCrawler
```

> PowerShell을 직접 열지 않고 탐색기에서 더블클릭하거나 `cmd`에서 실행하고 싶다면
> 같은 폴더의 `build-exe.bat`을 대신 써도 됩니다(`build-exe.bat DataCrawler`처럼
> seq_no 검증 없이, 또는 `build-exe.bat 000000,000022 DataCrawler`처럼 검증할 seq_no를
> 쉼표로 구분, 인자를 생략하면 실행 중 입력받되 비워두면 검증 생략). 내부적으로
> `build-exe.ps1`을 그대로 호출하는 얇은 래퍼이며 빌드 로직은 동일합니다.
>
> `build-exe.bat`은 실행 시 레포 루트의 `.venv`(없으면 `.venv-win`, `.venv` 우선)를 자동으로
> 찾아 activate하므로, PowerShell에서 미리 activate하지 않고 **일반 cmd 창을 새로 열거나
> 탐색기에서 바로 더블클릭해도** 동작합니다. 이미 다른 방식으로 venv를 activate한 상태라면
> 그 설정을 그대로 존중해 재탐지하지 않습니다. 둘 다 찾지 못하거나 `python`/`pyinstaller`를
> 실행할 수 없으면 PowerShell을 호출하기 전에 안내 메시지를 띄우고 중단합니다.

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `-SeqNo` | 선택 | 이번 빌드에 반드시 포함되어야 할 고객 seq_no(복수 지정 가능) — **포함 대상을 고르는 필터가 아니라 검증용**입니다. DB에서 조회한 active 블루프린트 전체가 항상 request_info.json에 포함되며, `-SeqNo`를 지정하면 그 값이 전부 active 목록에 있는지만 확인해 하나라도 없으면(예: 다중 사이트 고객인데 사이트 하나를 active 켜는 걸 깜빡함) 즉시 중단합니다. 생략하면 이 검증을 건너뜁니다. |
| `-AppName` | 선택 (기본값 `CollectorApp`) | exe 파일명이자, 실행 시 데이터가 저장되는 `%LOCALAPPDATA%\<AppName>\` 폴더명도 함께 결정합니다. |

**스크립트가 하는 일 (요약)**
1. `build_manifest.py`(Python)가 DB(`tb_blueprint`, `active=True`)를 조회해
   `request_info.json`을 새로 생성하고, (모든 블루프린트의) `seq_no`별로
   `{render,login,refine}/{seq_no}.py`가 있는지 `conf.CustomModuleStorage`의 기존 경로
   판별 로직으로 확인해 임시 스테이징 폴더로 격리 — request_info.json과 고정 아이콘
   자산(`combine-harvester.ico`, `icon/`)도 함께 포함 목록(매니페스트)에 기록
2. PowerShell이 그 매니페스트를 읽어 PyInstaller `--add-data` 인자로 변환
3. PyInstaller `--onefile --windowed`로 `main.py`를 빌드하면서, 매니페스트의 목록에 더해
   동적 import라 자동 탐지되지 않는 `scrapy.cfg`/`settings.py`/`pipelines.py`/
   `middlewares.py`/`spiders/`(고객 콘텐츠와 무관한 고정 항목이라 PowerShell이 직접 추가),
   그리고 Scrapy/Twisted 계열이 필요로 하는 패키지 메타데이터(`--copy-metadata`)를 함께 번들
4. 스테이징 폴더 정리

**결과물**: `dist\<AppName>.exe`

---

## 3. (선택) 설치 프로그램으로 감싸기 — `build-installer.ps1`

exe 파일을 그대로 전달하는 대신 설치/제거·바로가기 생성을 지원하는 설치 프로그램을 만들고
싶다면, 2단계 완료 후 실행합니다.

```powershell
.\build-installer.ps1 -AppName DataCrawler -AppVersion 1.0.0
```

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `-AppName` | 선택 (기본값 `CollectorApp`) | 2단계와 **동일한 값**을 사용해야 합니다(`dist\<AppName>.exe`를 찾아 감쌈). |
| `-AppVersion` | 선택 (기본값 `1.0.0`) | 설치 프로그램에 표시될 버전. |
| `-AppPublisher` | 선택 (기본값 `-AppName`과 동일) | 설치 프로그램에 표시될 배포자명. |

Inno Setup의 커맨드라인 컴파일러 `ISCC.exe`를 PATH → `Program Files\Inno Setup 6` →
`Program Files (x86)\Inno Setup 6` → `%LOCALAPPDATA%\Programs\Inno Setup 6`(winget 사용자별
설치 경로) 순으로 탐색합니다.

**결과물**: `dist\<AppName>-Setup.exe`

---

## 4. 실행 후 확인

- 최초 실행 시 `request_info.json`/`render`/`login`/`refine`이 `%LOCALAPPDATA%\<AppName>\`로
  자동 복사(시딩)됩니다. 이후 실행부터는 그 위치의 파일을 읽습니다.
- exe 파일명을 빌드 후 **직접 바꾸지 마세요** — `utility.get_app_name()`이 실행 파일명으로
  데이터 폴더명을 결정하므로, 이름을 바꾸면 다음 실행부터 새 이름의 빈 데이터 폴더를 찾아
  기존 `request_info.json`/`render`/`login`/`refine`을 못 찾는 것처럼 보일 수 있습니다.

---

## 5. 트러블슈팅

| 증상 | 원인 / 대처 |
|---|---|
| `pyinstaller`가 첫 로그 줄에서 바로 멈추고 `NativeCommandError` | PowerShell 5.1이 pyinstaller의 정상 진행 로그(stderr에 쓰는 INFO 로그)를 오류로 오인하는 실측 버그. `build-exe.ps1`이 pyinstaller 호출 구간에서만 `$ErrorActionPreference`를 `Continue`로 낮추고 `$LASTEXITCODE`로 직접 판정하도록 이미 조치되어 있습니다(이슈㉗) — 만약 이 동작이 안 보이면 스크립트가 최신 버전인지 확인하세요. |
| 빌드는 성공했는데 실행한 exe에서 `ModuleNotFoundError` | `--copy-metadata` 목록(`cryptography`, `lxml`, `twisted` 등) 밖의 의존성(Selenium/SQLAlchemy 등)일 수 있습니다. 오류 메시지의 모듈명을 `build-exe.ps1`의 pyinstaller 호출에 `--hidden-import <모듈명>` 또는 `--collect-all <모듈명>`으로 추가한 뒤 재시도하세요. |
| exe 실행 시 Scrapy가 정상 동작하지 않음(엔진/스파이더 설정 관련 오류) | `scrapy.cfg`/`settings.py`/`pipelines.py`/`middlewares.py`가 문자열 경로로 동적 import되어 PyInstaller 자동 분석에 안 잡히는 케이스(PR #66에서 해결) — `build-exe.ps1`이 최신 버전인지 확인하세요. |
| `build-installer.ps1`에서 "Inno Setup(ISCC.exe)을 찾을 수 없습니다" | Inno Setup 미설치이거나, winget으로 사용자별 권한 없이 설치해 `%LOCALAPPDATA%\Programs\Inno Setup 6\`에 들어간 경우입니다(이슈㉘, 최신 스크립트는 이 경로도 탐색합니다). 여전히 안 잡히면 실제 설치 경로를 확인해 스크립트의 탐색 후보에 추가하세요. |
| `build-exe.ps1` 실행 후 "DB에서 active 블루프린트를 조회하는 중입니다..." 문구에서 오래 멈춰 있음(로그 추가 없이) | `db_conn.read_db_data()`의 PostgreSQL 연결에는 `connect_timeout`이 설정돼 있지 않아, 호스트가 방화벽 등으로 조용히 응답을 안 주면 OS 기본 TCP 타임아웃까지 멈춘 것처럼 보일 수 있습니다. `env/database.ini`의 host/포트/방화벽을 확인하세요. |
| `build_manifest.py`가 "DB 접속 정보를 읽지 못했습니다" 또는 "DB에서 active=True인 블루프린트를 하나도 가져오지 못했습니다"로 중단 | 전자는 `env/database.ini`에 `[PostgreSQL]` 섹션(대소문자 정확히 일치)이 없거나 파일 자체가 없는 경우(1단계의 섹션명 대소문자 주의 참고). 후자는 DB 연결 실패와 "실제로 active인 데이터가 0건"을 `db_conn.read_db_data()`가 구분하지 않고 똑같이 빈 결과로 반환하기 때문 — `tb_blueprint`를 직접 조회해 원인을 확인하세요. |

---

## 관련 문서

- 커스텀 규칙(정제/렌더링) 작성 및 배포 절차 상세: `PREPROCESS.md` §3.1a, §5
- 빌드 파이프라인 도입·수정 이력: `HISTORY.md` (2026-07-13, 2026-07-21 항목)
- 알려진 이슈: `ISSUES.md` 이슈㉕·㉗·㉘
