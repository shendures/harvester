# DataCrawler v2.0 (Harvest) — 개발 환경

> 개발과 실행에 필요한 도구, 설정, 명령을 기록합니다. 프로젝트의 목적은 [프로젝트 설명](README.md)에 기록합니다.

표기: **확인**은 이 문서를 정리하며 직접 실행해 확인한 명령이다. **기록**은 [HISTORY.md](HISTORY.md)나 [ISSUES.md](ISSUES.md)에 실행 검증이 남아 있으나 이번에 다시 실행하지 않은 명령이다.

## 필요한 도구

| 도구 또는 서비스 | 버전 | 용도 |
|---|---|---|
| Python | 3.12 이상 (`.venv`는 3.12.13) | 앱 실행 |
| 의존성 | [requirements.txt](../requirements.txt)에 고정 | PyQt6 6.10.2, Scrapy 2.14.1, selenium 4.41.0, SQLAlchemy 2.0.48 등 |
| Windows 10 이상 | — | exe 빌드(WSL·Linux에서는 빌드할 수 없다) |
| PyInstaller | 6.19.0 (requirements.txt에 포함) | exe 빌드 |
| Chrome | — | JS 렌더링 수집(`webdriver-manager`가 드라이버를 설치) |
| PostgreSQL | — | 블루프린트 원본 DB(`tb_blueprint`). 빌드와 `harvest/config/create_request_info.py`에 필요. 수집 결과 저장에는 MySQL·MongoDB도 지원 |

주요 의존성 용도: Scrapy·Twisted(크롤링), PyQt6(GUI), lxml·parsel(파싱), pymongo·mysqlclient·PyMySQL·psycopg2·SQLAlchemy(DB), furl(URL), python-dotenv.

## 설치 및 설정

1. 저장소를 클론한다. 브랜치는 `feature/* → develop → main`이다.
2. 가상환경을 만들고 의존성을 설치한다.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. `harvest/config/env/database.ini`를 준비한다(`env/`는 `.gitignore` 대상이라 머신마다 개별 준비).

| 환경 변수 또는 설정 파일 | 용도 | 준비 방법 |
|---|---|---|
| `harvest/config/env/database.ini` | `tb_blueprint` 조회와 DB 연동 | `python harvest/config/env/create_ini.py`로 같은 폴더에 템플릿을 만든 뒤 호스트·계정을 채운다. **섹션명은 정확히 `[PostgreSQL]`(대문자 P)** 이어야 `db_conn.get_params("PostgreSQL")`이 읽는다. 템플릿은 소문자 `[postgresql]`이므로 직접 고쳐야 한다. 비밀번호 같은 값은 문서나 커밋에 넣지 않는다 |
| `harvest/config/request_info.json` | 블루프린트 목록 | 빌드 시 `scripts/build-exe.ps1`의 매니페스트 단계가 DB에서 만들어 덮어쓴다. 로컬에서 직접 고치면 다음 빌드에 반영되지 않는다 |
| `harvest/config/render/`·`login/`·`refine/` | 사이트별 플러그인 | 수집 설정 폴더 안의 개발 전용 폴더. git 미추적이며 [아래](#커스텀-규칙-개발검증배포) 참고 |

2026-10-15 폴더 재구성 이전에 만든 클론은 git 미추적 파일이 자동으로 옮겨지지 않는다. 저장소 루트의 `request_info.json`, `render/`, `login/`, `refine/`, `env/`를 `harvest/config/`로 직접 옮긴다. 옮기지 않으면 앱이 기본값으로 기동하고 빌드의 매니페스트 단계는 규칙 파일을 찾지 못했다는 경고만 낸다. `env/create_ini.py`는 이제 자기 폴더에 `database.ini`를 쓰도록 고쳐 두었다(이전에는 실행 위치의 `env/`).

WSL 개발 환경 주의:
- WSL2에서 Windows에 설치된 DB로 접속하는 방법(게이트웨이 IP, 방화벽, 바인드 주소)은 개인 학습 노트 `docs/study/study_wsl_db_connect.md`에 정리돼 있다(git 미추적).
- `harvest/config/env/database.ini`의 host가 WSL→Windows 게이트웨이 주소(예: `172.22.224.1`)인 경우 그 WSL에서만 유효하다. 배포 빌드를 하는 Windows 머신에서는 그 머신 기준의 host를 따로 쓴다.
- WSL 네이티브 경로의 `.venv`는 이미 WSL용이다. 같은 클론에서 Windows 빌드용 가상환경을 만들지 않는다. Windows 빌드는 `/mnt/c`·`/mnt/d` 같은 Windows 경로의 별도 클론이나 다른 이름(`.venv-win`)의 가상환경에서 한다.

## 실행

```bash
python main.py            # 블루프린트 개수로 단일(1개)·다중(2개 이상) 화면을 자동 선택  (확인)
python main.py --multi    # 다중 화면 강제(블루프린트가 2개 이상일 때만)
python main.py --single   # 단일 화면 강제(블루프린트가 1개일 때만)
```

- 플래그가 블루프린트 개수와 모순되면 안내 메시지를 출력하고 종료 코드 1로 즉시 중단한다.
- 디스플레이가 없는 환경(WSL 등)에서는 `QT_QPA_PLATFORM=offscreen python main.py`로 기동 여부만 확인한다. 이번에 8초간 예외 없이 이벤트 루프에 머무는 것을 확인했다.
- 루트의 `main.py`는 `freeze_support()`를 호출하고 `harvest/app.py`의 `main()`을 실행하는 얇은 진입점이다. 개발 중 `harvest` 패키지는 저장소 루트에서 실행할 때만 import된다.
- 블루프린트 도구는 저장소 루트에서 모듈로 실행한다: `python -m harvest.config.create_request_info`(DB 접속 필요). `python harvest/config/<파일>.py`처럼 파일로 직접 실행하면 `harvest` import가 실패한다.
- 같은 사용자가 이미 앱을 실행 중이면 `QLocalServer`가 두 번째 실행을 막는다.
- 개발 실행(`.py`)에서 `request_info.json`과 플러그인은 `harvest/config/`를 그대로 읽고 쓴다(사본을 만들지 않는다). 수집 이력(`stats_history.json.gz`)도 같은 `harvest/config/`에 쓴다. exe는 `%LOCALAPPDATA%\<AppName>\`을 쓰며 최초 실행 때 `request_info.json`과 플러그인 폴더가 그 위치로 복사된다.

## 테스트 및 검증

이 프로젝트에는 자동화 테스트가 없다([ISSUES.md](ISSUES.md) §3). 변경 후 아래를 쓴다.

```bash
python3 -m py_compile main.py harvest/core/conf.py harvest/crawler/worker.py harvest/core/preprocess.py   # 변경한 파일을 넣는다  (확인)
```

- 변경한 `.py`의 `py_compile` 통과를 기준으로 한다.
- GUI·로직은 `QT_QPA_PLATFORM=offscreen`으로 위젯을 인스턴스화해 직접 호출하는 일회용 스크립트로 확인하고, 확인 후 삭제한다.
- 변경한 심볼의 사용처는 `grep`으로 전수 확인한다.
- 스크립트가 쓰는 곳이 실제 데이터 폴더가 아니도록 한다. 수집 이력(`stats_history.json.gz`)은 git으로 복구할 수 없다.
- Windows GUI 확인이 필요한 변경은 HISTORY의 "검증" 열에 "Windows 확인 필요"로 남긴다.

## 빌드 (Windows 전용)

빌드는 매번 DB(`tb_blueprint`에서 `active = True`인 행 전체)를 조회한다. 어떤 고객을 포함할지는 DB의 `active` 플래그로 정한다. 먼저 `harvest/config/env/database.ini`가 이 머신 기준으로 DB에 접속할 수 있어야 한다.

```powershell
.\scripts\build-exe.ps1 -AppName DataCrawler                  # dist\DataCrawler.exe  (기록: 2026-07-21 Windows 실 빌드, 당시 경로 .\build-exe.ps1)
.\scripts\build-exe.ps1 -SeqNo 000000 000022 -AppName DataCrawler   # -SeqNo는 포함 필터가 아니라 검증용
```

- 스크립트는 어느 폴더에서 실행해도 저장소 루트를 기준으로 동작한다. 2026-10-15 폴더 재구성 이후 `scripts/` 경로의 Windows 실빌드는 아직 확인하지 않았다([HISTORY.md](HISTORY.md)).

- `build-exe.ps1` 하나가 빌드 전체를 처리한다. `.venv`(없으면 `.venv-win`)를 자동으로 PATH에 올리고, `python`·`pyinstaller`를 실제로 실행해 점검하며, `-SeqNo`·`-AppName`을 주지 않으면 실행 중 입력받는다. 환경은 미리 만들어 둬야 한다. 탐색기 더블클릭 실행은 지원하지 않으며, cmd에서는 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-exe.ps1`로 실행한다. 이 통합 후 동작(가상환경 활성화·점검·대화형 입력·내장 매니페스트)의 Windows 실 빌드는 아직 확인하지 않았다.
- 결과: `dist\<AppName>.exe`.
- `scripts/build-exe.ps1`이 하는 일: 스크립트에 내장된 Python 매니페스트 코드가 `request_info.json`을 만들고 활성 seq_no의 `render/login/refine` 파일을 임시 스테이징으로 골라 담는다 → 그 목록을 PyInstaller `--add-data`로 전달 → `--onefile --windowed`로 `main.py`를 빌드(`harvest/crawler/scraper/` 패키지(`scrapy.cfg` 포함), `--hidden-import`, `--copy-metadata`를 함께 지정) → 스테이징 정리.
- `-AppName`은 exe 이름과 `%LOCALAPPDATA%\<AppName>\` 폴더명을 정한다. 빌드 후 exe 이름을 바꾸지 않는다. 바꾸면 다음 실행부터 빈 데이터 폴더를 찾는다.

### 빌드 트러블슈팅

| 증상 | 원인과 대처 |
|---|---|
| pyinstaller가 첫 로그에서 `NativeCommandError`로 중단 | PowerShell 5.1이 stderr의 정상 INFO 로그를 오류로 본다. 스크립트가 해당 구간만 `$ErrorActionPreference`를 낮추고 `$LASTEXITCODE`로 판정한다(이슈㉗). 스크립트가 최신인지 확인 |
| exe 실행 시 `ModuleNotFoundError` | `--copy-metadata` 목록 밖의 의존성이다. 모듈명을 pyinstaller 호출에 `--hidden-import` 또는 `--collect-all`로 추가 |
| exe에서 수집이 에러 없이 0건 | `multiprocessing.freeze_support()`가 빠지면 자식이 GUI를 재기동하다 단일 실행 감지로 즉시 종료된다. 현재는 `main.py`에 있다 |
| exe에서 Scrapy가 동작하지 않음 | `harvest/crawler/scraper/`는 문자열 경로로 동적 import돼 자동 분석에 잡히지 않는다. 기동 로그의 `Enabled downloader middlewares:`·`Enabled item pipelines:`에 `harvest.crawler.scraper.` 항목이 보이는지 확인 |
| 빌드의 매니페스트 단계가 "DB 접속 정보를 읽지 못했습니다"로 중단 | `harvest/config/env/database.ini`가 없거나 `[PostgreSQL]` 섹션명이 다르다 |
| "active=True인 블루프린트를 하나도 가져오지 못했습니다" | 연결 실패와 0건을 `db_conn.read_db_data()`가 구분하지 않는다. `tb_blueprint`를 직접 조회해 확인 |
| "DB에서 active 블루프린트를 조회하는 중" 문구에서 오래 멈춤 | PostgreSQL 연결에 `connect_timeout`이 없어 OS 기본 TCP 타임아웃까지 기다린다. host·포트·방화벽을 확인 |

## 커스텀 규칙 개발·검증·배포

사이트별 `render/{seq_no}.py`(렌더링), `login/{seq_no}.py`(로그인), `refine/{seq_no}.py`(정제)는 `harvest/config/`의 개발 전용 폴더에서 관리한다. 이 폴더는 git 미추적이며 로컬 디스크에만 있다. 설계 이유와 함수 계약은 [ARCHITECTURE.md](ARCHITECTURE.md) §4·§5를 본다.

정제 규칙을 새로 만드는 순서:
1. 대상 블루프린트의 `needs_cleaning`을 `true`로 두고, `seq_no`를 문자열 그대로 확인한다(앞자리 0 유실 주의).
2. `refine/{seq_no}.py`에 `refine(data)`(목록 단위) 또는 `refine_row(row)`(행 단위)를 쓴다.
3. 실제 raw 샘플로 함수를 임시 스크립트에서 단독 실행해 예외 없이 기대한 출력이 나오는지 확인하고, 스크립트는 삭제한다.
4. `.\scripts\build-exe.ps1 -SeqNo {seq_no}`로 빌드한다. 해당 seq_no의 파일만 exe에 담긴다.
5. GUI에서 정제 규칙 설정 탭에 경고가 없는지, "커스텀 정제 규칙 적용"이 켜져 있는지 확인한다. 수집을 한 번 실행해 로그에 "사용자 정의 규칙 적용됨"이 남는지, 결과가 기대대로인지 본다.

주의:
- 규칙 안의 예외나 길이가 다른 반환값은 원본으로 폴백하고 로그에만 남는다. 배포 전에 3번을 거치지 않으면 조용히 지나간다.
- 파일은 `exec`로 로드되므로 개발자가 검수한 코드만 둔다.
- 플러그인에서 프로젝트 모듈이 필요하면 전체 경로로 import한다(예: `from harvest.crawler import engine`). 최상위 `import engine`은 폴더 재구성 이후 실패한다.
- 개발 폴더에 여러 고객의 파일이 섞여 있어도 빌드는 활성 seq_no 것만 담는다.

## 관련 문서

- [프로젝트 설명](README.md): 목적과 주요 기능
- [아키텍처](ARCHITECTURE.md): 시스템 구성과 흐름
- [코드·스크립트·모듈 관계](MODULE_SPEC.md): 실행 진입점과 구성 요소 간 연결
