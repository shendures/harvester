# DataCrawler v2.0 (Harvest) — 개발 환경

> 개발과 실행에 필요한 도구, 설정, 명령을 기록합니다. 프로젝트의 목적은 [프로젝트 설명](README.md)에 기록합니다.

표기: **확인**은 이 문서를 정리하며 직접 실행해 확인한 명령이다. **기록**은 [HISTORY.md](HISTORY.md)나 [ISSUES.md](ISSUES.md)에 실행 검증이 남아 있으나 이번에 다시 실행하지 않은 명령이다.

## 필요한 도구

| 도구 또는 서비스 | 버전 | 용도 |
|---|---|---|
| Python | 3.12 이상 (`.venv`는 3.12.13) | 앱 실행 |
| 의존성 | [requirements.txt](../requirements.txt)에 고정 | PyQt6 6.10.2, Scrapy 2.14.1, selenium 4.41.0, SQLAlchemy 2.0.48 등 |
| Windows 10 이상 | — | exe·설치 프로그램 빌드(WSL·Linux에서는 빌드할 수 없다) |
| PyInstaller | 6.19.0 (requirements.txt에 포함) | exe 빌드 |
| Inno Setup 6 | 6.7.3에서 확인 | 설치 프로그램 빌드(Windows 전용 외부 도구, 선택) |
| Chrome | — | JS 렌더링 수집(`webdriver-manager`가 드라이버를 설치) |
| PostgreSQL | — | 블루프린트 원본 DB(`tb_blueprint`). 빌드와 `create_request_info.py`에 필요. 수집 결과 저장에는 MySQL·MongoDB도 지원 |

주요 의존성 용도: Scrapy·Twisted(크롤링), PyQt6(GUI), lxml·parsel(파싱), pymongo·mysqlclient·PyMySQL·psycopg2·SQLAlchemy(DB), furl(URL), python-dotenv.

## 설치 및 설정

1. 저장소를 클론한다. 브랜치는 `feature/* → develop → main`이다.
2. 가상환경을 만들고 의존성을 설치한다.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. `env/database.ini`를 준비한다(`env/`는 `.gitignore` 대상이라 머신마다 개별 준비).

| 환경 변수 또는 설정 파일 | 용도 | 준비 방법 |
|---|---|---|
| `env/database.ini` | `tb_blueprint` 조회와 DB 연동 | `env/create_ini.py`로 템플릿을 만든 뒤 호스트·계정을 채운다. **섹션명은 정확히 `[PostgreSQL]`(대문자 P)** 이어야 `db_conn.get_params("PostgreSQL")`이 읽는다. 템플릿은 소문자 `[postgresql]`이므로 직접 고쳐야 한다. 비밀번호 같은 값은 문서나 커밋에 넣지 않는다 |
| `request_info.json` | 블루프린트 목록 | 빌드 시 `build_manifest.py`가 DB에서 만들어 덮어쓴다. 로컬에서 직접 고치면 다음 빌드에 반영되지 않는다 |
| `render/`·`login/`·`refine/` | 사이트별 플러그인 | 저장소 루트의 개발 전용 폴더. git 미추적이며 [아래](#커스텀-규칙-개발검증배포) 참고 |

WSL 개발 환경 주의:
- WSL2에서 Windows에 설치된 DB로 접속하는 방법(게이트웨이 IP, 방화벽, 바인드 주소)은 개인 학습 노트 `docs/study/study_wsl_db_connect.md`에 정리돼 있다(git 미추적).
- `env/database.ini`의 host가 WSL→Windows 게이트웨이 주소(예: `172.22.224.1`)인 경우 그 WSL에서만 유효하다. 배포 빌드를 하는 Windows 머신에서는 그 머신 기준의 host를 따로 쓴다.
- WSL 네이티브 경로의 `.venv`는 이미 WSL용이다. 같은 클론에서 Windows 빌드용 가상환경을 만들지 않는다. Windows 빌드는 `/mnt/c`·`/mnt/d` 같은 Windows 경로의 별도 클론이나 다른 이름(`.venv-win`)의 가상환경에서 한다.

## 실행

```bash
python main.py            # 블루프린트 개수로 단일(1개)·다중(2개 이상) 화면을 자동 선택  (확인)
python main.py --multi    # 다중 화면 강제(블루프린트가 2개 이상일 때만)
python main.py --single   # 단일 화면 강제(블루프린트가 1개일 때만)
```

- 플래그가 블루프린트 개수와 모순되면 안내 메시지를 출력하고 종료 코드 1로 즉시 중단한다.
- 디스플레이가 없는 환경(WSL 등)에서는 `QT_QPA_PLATFORM=offscreen python main.py`로 기동 여부만 확인한다. 이번에 8초간 예외 없이 이벤트 루프에 머무는 것을 확인했다.
- 같은 사용자가 이미 앱을 실행 중이면 `QLocalServer`가 두 번째 실행을 막는다.
- 개발 실행(`.py`)의 데이터 폴더는 저장소 루트이고, exe는 `%LOCALAPPDATA%\<AppName>\`이다. 최초 실행 때 `request_info.json`과 플러그인 폴더가 그 위치로 복사된다.

## 테스트 및 검증

이 프로젝트에는 자동화 테스트가 없다([ISSUES.md](ISSUES.md) §3). 변경 후 아래를 쓴다.

```bash
python3 -m py_compile main.py conf.py worker.py preprocess.py   # 변경한 파일을 넣는다  (확인)
```

- 변경한 `.py`의 `py_compile` 통과를 기준으로 한다.
- GUI·로직은 `QT_QPA_PLATFORM=offscreen`으로 위젯을 인스턴스화해 직접 호출하는 일회용 스크립트로 확인하고, 확인 후 삭제한다.
- 변경한 심볼의 사용처는 `grep`으로 전수 확인한다.
- 스크립트가 쓰는 곳이 실제 데이터 폴더가 아니도록 한다. 수집 이력(`stats_history.json.gz`)은 git으로 복구할 수 없다.
- Windows GUI 확인이 필요한 변경은 HISTORY의 "검증" 열에 "Windows 확인 필요"로 남긴다.

## 빌드 (Windows 전용)

빌드는 매번 DB(`tb_blueprint`에서 `active = True`인 행 전체)를 조회한다. 어떤 고객을 포함할지는 DB의 `active` 플래그로 정한다. 먼저 `env/database.ini`가 이 머신 기준으로 DB에 접속할 수 있어야 한다.

```powershell
.\build-exe.ps1 -AppName DataCrawler                  # dist\DataCrawler.exe  (기록: 2026-07-21 Windows 실 빌드)
.\build-exe.ps1 -SeqNo 000000 000022 -AppName DataCrawler   # -SeqNo는 포함 필터가 아니라 검증용
.\build-installer.ps1 -AppName DataCrawler -AppVersion 1.0.0   # dist\DataCrawler-Setup.exe  (기록: 이슈㉘)
```

- 탐색기나 `cmd`에서는 같은 폴더의 `build-exe.bat`·`build-installer.bat`을 쓴다. 이 파일들은 `.venv`(없으면 `.venv-win`)를 자동으로 활성화한다. 환경은 미리 만들어 둬야 한다.
- 결과: `dist\<AppName>.exe` → `dist\<AppName>-Setup.exe`. `build-installer`는 먼저 `build-exe` 결과가 있어야 하고 `-AppName`이 같아야 한다.
- `build-exe.ps1`이 하는 일: `build_manifest.py`가 `request_info.json`을 만들고 활성 seq_no의 `render/login/refine` 파일을 임시 스테이징으로 골라 담는다 → 그 목록을 PyInstaller `--add-data`로 전달 → `--onefile --windowed`로 `main.py`를 빌드(`scrapy.cfg`, `scraper/` 패키지, `--hidden-import`, `--copy-metadata`를 함께 지정) → 스테이징 정리.
- `-AppName`은 exe 이름과 `%LOCALAPPDATA%\<AppName>\` 폴더명을 정한다. 빌드 후 exe 이름을 바꾸지 않는다. 바꾸면 다음 실행부터 빈 데이터 폴더를 찾는다.
- 제거 프로그램은 설치 프로그램에 자동으로 포함된다. 앱 데이터 폴더는 고객 수정본을 보호하려고 의도적으로 지우지 않는다.
- ISCC.exe는 PATH → `Program Files\Inno Setup 6` → `Program Files (x86)\Inno Setup 6` → `%LOCALAPPDATA%\Programs\Inno Setup 6` 순으로 찾는다.

### 빌드 트러블슈팅

| 증상 | 원인과 대처 |
|---|---|
| pyinstaller가 첫 로그에서 `NativeCommandError`로 중단 | PowerShell 5.1이 stderr의 정상 INFO 로그를 오류로 본다. 스크립트가 해당 구간만 `$ErrorActionPreference`를 낮추고 `$LASTEXITCODE`로 판정한다(이슈㉗). 스크립트가 최신인지 확인 |
| exe 실행 시 `ModuleNotFoundError` | `--copy-metadata` 목록 밖의 의존성이다. 모듈명을 pyinstaller 호출에 `--hidden-import` 또는 `--collect-all`로 추가 |
| exe에서 수집이 에러 없이 0건 | `multiprocessing.freeze_support()`가 빠지면 자식이 GUI를 재기동하다 단일 실행 감지로 즉시 종료된다. 현재는 `main.py`에 있다 |
| exe에서 Scrapy가 동작하지 않음 | `scrapy.cfg`·`scraper/`는 문자열 경로로 동적 import돼 자동 분석에 잡히지 않는다. 기동 로그의 `Enabled downloader middlewares:`·`Enabled item pipelines:`에 `scraper.` 항목이 보이는지 확인 |
| `build_manifest.py`가 "DB 접속 정보를 읽지 못했습니다"로 중단 | `env/database.ini`가 없거나 `[PostgreSQL]` 섹션명이 다르다 |
| "active=True인 블루프린트를 하나도 가져오지 못했습니다" | 연결 실패와 0건을 `db_conn.read_db_data()`가 구분하지 않는다. `tb_blueprint`를 직접 조회해 확인 |
| "DB에서 active 블루프린트를 조회하는 중" 문구에서 오래 멈춤 | PostgreSQL 연결에 `connect_timeout`이 없어 OS 기본 TCP 타임아웃까지 기다린다. host·포트·방화벽을 확인 |
| ISCC.exe를 찾을 수 없음 | Inno Setup 미설치이거나 탐색 경로 밖에 설치됐다. 실제 경로를 확인해 스크립트의 후보에 추가 |

## 커스텀 규칙 개발·검증·배포

사이트별 `render/{seq_no}.py`(렌더링), `login/{seq_no}.py`(로그인), `refine/{seq_no}.py`(정제)는 레포 루트의 개발 전용 폴더에서 관리한다. 이 폴더는 git 미추적이며 로컬 디스크에만 있다. 설계 이유와 함수 계약은 [ARCHITECTURE.md](ARCHITECTURE.md) §4·§5를 본다.

정제 규칙을 새로 만드는 순서:
1. 대상 블루프린트의 `needs_cleaning`을 `true`로 두고, `seq_no`를 문자열 그대로 확인한다(앞자리 0 유실 주의).
2. `refine/{seq_no}.py`에 `refine(data)`(목록 단위) 또는 `refine_row(row)`(행 단위)를 쓴다.
3. 실제 raw 샘플로 함수를 임시 스크립트에서 단독 실행해 예외 없이 기대한 출력이 나오는지 확인하고, 스크립트는 삭제한다.
4. `.\build-exe.ps1 -SeqNo {seq_no}`로 빌드한다. 해당 seq_no의 파일만 exe에 담긴다.
5. GUI에서 정제 규칙 설정 탭에 경고가 없는지, "커스텀 정제 규칙 적용"이 켜져 있는지 확인한다. 수집을 한 번 실행해 로그에 "사용자 정의 규칙 적용됨"이 남는지, 결과가 기대대로인지 본다.

주의:
- 규칙 안의 예외나 길이가 다른 반환값은 원본으로 폴백하고 로그에만 남는다. 배포 전에 3번을 거치지 않으면 조용히 지나간다.
- 파일은 `exec`로 로드되므로 개발자가 검수한 코드만 둔다.
- 개발 폴더에 여러 고객의 파일이 섞여 있어도 빌드는 활성 seq_no 것만 담는다.

## 관련 문서

- [프로젝트 설명](README.md): 목적과 주요 기능
- [아키텍처](ARCHITECTURE.md): 시스템 구성과 흐름
- [코드·스크립트·모듈 관계](MODULE_SPEC.md): 실행 진입점과 구성 요소 간 연결
