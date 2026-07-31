# DataCrawler v2.0 (Harvest) — 이슈 및 백로그

> `PROJECT_REPORT.md`에서 분리된 이슈 관리 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 완료된 작업 이력은 `HISTORY.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-07-31 14:25
- **현황**: 해결 25건 · 미해결 3건 · 보류 2건

> **작성 규칙**: 해결된 이슈(✅)는 §1 표(`# | 이슈 | 위치 | 원인 | 해결 | PR/커밋`)에 한 행으로 추가합니다.
> 미해결(❌)·보류(⏸) 이슈는 표에 넣지 않고 §2에 `### 항목명 — 상태 (날짜)` 헤딩과 `위치/상세/사유·필요 조치` 불릿 리스트로 작성합니다 — 표 셀에는 진행 중인 원인 분석·대안 검토 같은 긴 서술이 담기지 않기 때문입니다.
> 이슈가 해결되면 §2 항목을 삭제하고 §1 표로 옮깁니다.

---

## 1. 해결된 이슈 (25건)

| # | 이슈 | 위치 | 원인 | 해결 | PR/커밋 |
|---|---|---|---|---|---|
| ① | 리다이렉트 시 수집 결과 전량 skip → total=0 | `worker.py` / `engine.py` | `worker._handle_line()`이 응답의 최종 URL로 url_list를 대조 — 리다이렉트 사이트는 최종 URL≠요청 URL이라 전량 skip | `engine.get_response_status()`에 `req_url` 추가, 대조 기준을 `req_url`로 변경 | `d469277` |
| ② | 프록시 활성 시 설정 키 불일치로 AttributeError, GUI 경로에서 프록시 무시 | `middlewares.py`, `worker.py`, `customized_settings.py` | ①`middlewares.py:213`이 주석 처리된 `REQUESTS_PER_MINUTE` 참조로 AttributeError, ②worker는 `PROXY_REQ_INFO`에 저장하지만 미들웨어는 `ip_list`/`allow_ip_cnts` 조회(GUI 경로는 항상 빈 리스트), ③GUI는 dict 행, 미들웨어는 URL 문자열 요구 | 값 변환·주입 키 정정, "여유 프록시 무작위 순회 선택"으로 재작성 | PR #5 |
| ③ | 쿠키 랜덤 미들웨어가 미들웨어 규약 위반(dict 반환) | `middlewares.py:349` | 쿠키 있으면 `request.cookies`(dict)를 그대로 반환 — Scrapy `process_request` 규약(None/Response/Request만 허용) 위반으로 `_InvalidOutput` | `return None`으로 수정 | PR #21 |
| ④ | MongoDBPipeline import 누락으로 즉시 NameError | `pipelines.py`, `settings.py` | `db_conn`/`MongoClient` import 누락, 어떤 정상 경로에서도 미사용 | 복구 대신 제거, 기본 `ITEM_PIPELINES`를 `LoadItemPipeline`로 교체 | PR #8 |
| ⑤ | DelaySchedulerMiddleware 잘못된 설정 키·제거된 API 오용으로 미작동 | `settings.py:84`, `middlewares.py` | 존재하지 않는 설정 키(`SCHEDULER_MIDDLEWARES`)에 등록돼 미로드, 내부도 제거된 API(`engine.schedule`)·`DontCloseSpider` 오용 | 등록 키를 `SPIDER_MIDDLEWARES`로 정정, `_DelayedRescheduler` 헬퍼로 재작성, `RateLimitedProxyMiddleware`와 연동. 리뷰에서 나온 후속 결함 2건(강제종료 시 재시도 유실, 재시도 상한 없음)도 병합 전 수정 | PR #23 |
| ⑥ | `get_response_status()` None 필드 접근·비표준 상태코드 예외 | `engine.py:161,165` | `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 결과 조용히 유실, 비표준 상태코드는 `HTTPStatus()` ValueError | None 방어, ValueError를 try/except로 처리 | PR #19 |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 | `engine.py:67-74` | `process.crawl({})`로 이어져 Scrapy 내부에서 불투명한 실패 | 미구현 타입은 `NotImplementedError`, 미인식 타입은 `ValueError` 명시적 raise | PR #25, `fcd35d6` |
| ⑧ | `/text()` XPath 추출 깨짐(빈 값/ValueError) | `engine.py:299` | `extract_data_from_root()`가 텍스트 노드에도 `node.xpath(".")` 호출 — 문자열 텍스트는 빈 값 조용히 유실, JSON 파싱 가능 텍스트는 parsel 1.11이 json 타입 판정해 ValueError로 전체 실패(`@attr`도 동일 버그) | `node.root`가 문자열이면 그대로 사용하도록 분기 | PR #13 |
| ⑨ | 스케줄 기능이 실제 세션 설정과 분리(UA/쿠키/프록시 무시) | `layout.py:1366`, `trigger.py:1919-1923` | `SchedulerPage.__init__`이 `SessionSettingsPage()`를 별도로 새로 생성해 MainWindow의 실제 세션 페이지와 다른 객체 — UA/쿠키는 항상 기본값, `proxy` 키 자체가 없어 스케줄 수집은 프록시 절대 미사용 | 실제 `SessionSettingsPage` 인스턴스를 주입하도록 변경, `_apply_schedule()`에 수동 실행과 동일 스키마의 `proxy` 딕셔너리 추가 | - |
| ⑩ | `net_rotate` 잔재 키로 프록시 목록 검증(구버전 스키마) | `trigger.py:1806` | 구버전(frames_tmp.py) 스키마 잔재 키라 현행 blueprint에는 존재하지 않아 항상 "목록 없음" 판정 | `session_page._proxy_rows`(현행 스키마)로 교체 | - |
| ⑪ | 월간 스케줄 등록 시 QTimer OverflowError | `trigger.py:2013-2015` | 남은 시간을 ms로 환산해 `QTimer.start()`에 그대로 전달 — 30일치가 C int32 최댓값 초과 | 7일 단위로 타이머를 재등록하는 방식으로 청크 분할 | - |
| ⑫ | 스케줄 저장 위치 오류(소스/설치 디렉터리, PyInstaller 시 유실) | `trigger.py:2085, 2090-2091`, `layout.py:1357-1358` | `self.default_source`(소스/설치 디렉터리)에 저장 — PyInstaller 빌드 시 `resource_path()`가 임시 폴더(`_MEIPASS`)라 실행마다 유실 | 저장은 `self.file_path`(LOCALAPPDATA)로, 로드는 `file_path` 우선·없으면 `default_source` 폴백 | - |
| ⑬ | GUI 경로에서 SeleniumMiddleware 탈락(이중 렌더링) | `worker.py:433`, `customized_settings.py:224-256` | 조사 결과 애초에 `SELENIUM_DRIVER_EXECUTABLE_PATH` 미설정으로 항상 `NotConfigured` 자체 비활성화, 채워도 구버전 API로 `TypeError` — 죽은 의존성이었음. 실제 렌더링은 `spirenderer.py`가 전담 | `settings.py`에서 등록·설정 삭제, `html_render` 분기가 일반 `scrapy.Request` 반환, `scrapy-selenium` 의존성 제거 | - |
| ⑭ | spirenderer 드라이버 누수(`driver.quit()` finally 미사용) | `spiders/spirenderer.py:64-101` | `driver.quit()`이 try 블록 마지막에 있어 예외 발생 시 Chrome 프로세스 누적 | 드라이버 생성 이후 코드를 try/finally로 감싸 `driver.quit()`을 finally로 이동 | - |
| ⑮ | POST URL에 `?` 없으면 크래시, 미지원 분기 시 암묵적 None 반환 | `engine.py:36-37, 83-133` | `get_json_form()`의 `None[0]` TypeError + 잘못된 정규식 이스케이프, `get_scrapy_request()`가 미지원 조합에서 암묵적 None 반환 → `yield None` | `?` 부재 시 명시적 ValueError, 정규식 raw string 전환, 미지원 조합도 명시적 ValueError | - |
| ⑰ | 중지 직후 즉시 재시작 시 이전 워커의 지연된 finished 신호가 새 워커 상태를 덮어씀 | `trigger.py:2554` | 구 워커 정리가 비동기로 최대 ~1.3s 걸리는데, 그 사이 재시작하면 큐잉된 구 워커의 `finished` 신호가 새 워커 시작 후 뒤늦게 도착 — `_on_finished`가 출처 구분 안 해 새 워커를 "중단됨"으로 되돌림 | `_on_finished()` 최상단에 `if self.sender() is not self._worker: return` 가드 추가 | - |
| ⑱ | 스케줄+정제 자동 저장 조합에서 빈 데이터 시 블로킹 모달 노출 가능 | `layout.py:preprocess()`, `trigger.py:_run_refine()`/`_extract_result_table()` | 세 함수 모두 "무인 실행"을 고려하지 않고 데이터가 비면 항상 `QMessageBox.warning()` 호출 — 재조사 결과 `worker.py`의 `_done`(=summary total)은 URL 매칭 응답 수만 세고 실제 추출된 `data`(items) 존재 여부는 반영하지 않아, `summary.total>0`이라 `_on_finished()`의 `total==0` 조기 return을 통과하면서도 `_collected_data`가 완전히 비는 경우(셀렉터 불일치 등)가 가능함을 확인 — 원래 문서가 지목했던 `_run_refine()` 외에 `preprocess()`(job 종류 무관 매번 호출)·`_extract_result_table()`의 raw 분기(`auto_save_source` 기본값이라 오히려 더 자주 노출)까지 총 3곳 모두 도달 가능했음 | 3곳 모두에 무인 실행 신호(`task.get("job")=="스케줄 실행"`/`skip_ui_update`/`silent`)로 분기 추가 — 모달 대신 `log_manager.append_log("warn", ...)`로 대체. `_extract_result_table("refined", silent=True)`는 호출부가 이미 `SCHEDULED_REFINE_RULES`로 정제를 실행한 뒤이므로 화면 상태 기반 `_run_refine()` 폴백 호출도 차단 | `6ae108f` |
| ⑲ | "②정제 규칙 설정" 탭 [정제 실행] 클릭 시 TypeError로 프로세스 abort | `layout.py:763`, `trigger.py:1069` | `clicked.connect(self._run_refine)`가 시그널의 `bool checked` 인자를 `rules_override`로 그대로 전달 — `dict(False)` 호출로 `TypeError`, try/except 범위 밖이라 PyQt6가 프로세스 abort | `clicked.connect(lambda: self._run_refine())`으로 감싸 bool 인자 차단 | PR #59 |
| ⑳ | `custom_rules/render/{seq_no}.py` 서브폴더 미이관 | `custom_rules/render/`(부재), `conf.py` | render/refine 서브폴더 분리 리팩터링 중 000010(맥도날드)·000013(네이버) 원본이 삭제만 되고 재이관 안 됨 | 삭제 커밋의 부모 커밋에서 원본 복원(`git show 53978d0^:...`)해 `custom_rules/render/`로 재이관 | - |
| ㉑ | `spirenderer.py`의 `conditions["login"]` 직접 접근이 신규 request_info.json과 스키마 불일치 | `spiders/spirenderer.py:73`, `generator_conditions.html:1490` | "로그인 없는 사이트도 `login: null` 명시" 암묵적 스키마 전제인데, 생성기의 delete-if-null 목록에 `login`도 포함돼 로그인 미사용 시 키 자체가 삭제됨 → `KeyError` | 코드(`.get()` 방어) 대신 기존 관례 유지 — 생성기 delete-if-null 목록에서 `login` 제외 | - |
| ㉕ | PyInstaller 배포 파이프라인 부재로 커스텀 규칙 번들 여부 보장 불가 | `guidelines/PREPROCESS.md`, (부재였던) 빌드 스크립트 | `.spec`·빌드 스크립트가 저장소에 전무해 `--add-data` 구성이 수동·비문서화, `PREPROCESS.md` 안내도 구경로 기준이라 실제 조회 경로와 불일치 | `build-exe.ps1` 신설(seq_no 일치 검증, 스테이징 후 번들), `PREPROCESS.md` 경로 안내 갱신 | - |
| ㉖ | 배포 exe에서 CustomModuleStorage가 seq_no와 무관하게 render/refine 폴더를 항상 생성 | `conf.py:294-309` | `CustomModuleStorage.__init__()`이 인스턴스화 시점에 `render`/`refine` 두 서브폴더를 조건 없이 만들어, 정제 규칙만 있고 렌더링 규칙은 없는 seq_no도 `%LOCALAPPDATA%\CollectorApp\custom_rules\render\` 빈 폴더가 생성됨(실사용 exe에서 확인) | `__init__()`의 선제적 폴더 생성 루프 제거 — `resolve_path()`가 이미 실제 시딩 대상이 있을 때만 온디맨드로 폴더를 만들고 있어 그 로직에만 의존하도록 정리 | `85463ef` |
| ㉗ | `build-exe.ps1`이 pyinstaller의 정상 INFO 로그를 오류로 오인해 빌드 첫 줄에서 강제 중단 | `build-exe.ps1:28,109` | 스크립트 최상단 `$ErrorActionPreference = "Stop"` 상태에서 `pyinstaller`(native 명령)가 진행 상황을 stderr에 INFO로 기록 — PowerShell 5.1이 stderr 첫 줄을 즉시 종료 오류로 승격시켜 실제로는 정상 진행 중인 빌드를 매번 시작 직후 중단시킴(Windows 실 빌드로 재현 — PR #64 도입 이후 이 스크립트로 완주된 적이 실제로 없었음, 기존 dist 산출물은 스크립트를 거치지 않은 수동 pyinstaller 실행 결과였음) | `pyinstaller` 호출 앞뒤로만 `$ErrorActionPreference`를 `"Continue"`↔`"Stop"`으로 일시 전환하고, 실패 여부는 `$LASTEXITCODE`로 직접 판별해 0이 아니면 명시적으로 중단 | Windows 실 빌드로 수정 전(첫 INFO 줄에서 `NativeCommandError`로 즉시 중단, exe 미생성) → 수정 후(정상 완주, `dist\DataCrawler.exe` 생성, `EXITCODE=0`) 확인. 이어서 `build-installer.ps1`도 검토 — Inno Setup(ISCC.exe) 자체가 이 머신에 미설치라 실행 검증은 보류 |
| ㉘ | `build-installer.ps1`의 ISCC.exe 탐색 경로에 사용자별 설치 위치 누락 | `build-installer.ps1:33-36` | winget으로 Inno Setup을 설치(관리자 권한 없이 실행하면 기본이 사용자별 설치)하니 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`에 설치됐는데, 탐색 후보 목록은 시스템 전체 설치 경로(`Program Files`/`Program Files (x86)`)만 확인 — 사용자별 설치 시 항상 "찾을 수 없음"으로 실패 | 탐색 후보 목록에 `$Env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe`를 추가 | Windows 실 빌드 — winget으로 실제 Inno Setup 6.7.3 설치(사용자별 경로 확인) → 수정 전 탐색 실패 재현 → 수정 후 정상 탐색+컴파일, `dist\DataCrawler-Setup.exe`(PE32 GUI, 약 73MB) 생성 확인. `build-exe.ps1`(이슈㉗)→`build-installer.ps1` 전 과정이 실제 Windows 환경에서 처음부터 끝까지 완주됨을 최초로 확인 |
| ㉚ | 무인(스케줄) 실행에서 0건 수집 시 모달이 프로세스를 막고, 스케줄 재무장(`mark_done`)도 스킵되어 해당 스케줄이 영구 정지 | `trigger.py:_on_finished()`(3793-3841), `trigger.py:mark_done()`(2323) | `total==0` 분기가 `is_unattended` 판별보다 앞에 있어 무인 실행에도 `QMessageBox.exec()`가 떠서 아무도 없는 자리에서 프로세스가 블로킹됨. 게다가 이 분기가 `mark_done()` 호출 전에 `return`해, 다음 회차 `run_at` 재계산·`_register_timer()` 재등록이 아예 일어나지 않아 스케줄이 조용히 죽음(HISTORY 재현: 0건 1회 발생 후 해당 스케줄은 GUI에 "대기"로 보여도 실제로는 다시 실행되지 않음) | ①무인 실행이면 모달 대신 `TrayManager.show_message(..., icon=Warning)`로 대체, ②0건이어도 `mark_done(job_name, total=0)`을 호출해 재무장 보장, ③`mark_done()`이 `total`을 받아 스케줄 dict에 `last_result`(건수·시각)를 기록·영속화, ④`SchedulerPage` 테이블에 "Last Result" 컬럼 추가해 0건 실행을 붉은색으로 표시 — `.agents/product-marketing.md`의 "GUI로 운영 가능" 문구 정정(2026-07-31) 과정에서 코드 검증 중 발견 | - |

---

## 2. 미해결·보류 이슈 (4건)

### ⑯ blueprint 2건 이상 시 빈 설정으로 기동, 워커 조용히 사망 — ⏸ 보류 (2026-07-06)

- **위치**: `conf.py:165-183`, `worker.py:92`
- **상세**: `request_info.json` 루트 리스트에 항목이 2개 이상이면 unwrap 없이 리스트를 `_validate()`에 전달, `"url" in list`는 항상 False라 검증 실패 → 빈 dict 폴백. 이 상태로 시작하면 `worker.run()`의 `self.task["callback_url"]`(try 밖)에서 KeyError → QThread가 조용히 죽고 UI는 "실행 중"에 고착.
- **보류 사유**: 수집 목록 2개 이상을 다루는 다중 블루프린트 지원으로 프로그램을 업그레이드할 계획이 있어, 단건 전제의 현행 구조를 땜질 수정하지 않고 그 업그레이드에서 함께 재설계하기로 결정. 단건 검증 로직 자체는 여전히 유효하므로 별도 조치 없음.

### ㉒ `generator_conditions.html`이 실제 스파이더 라우팅 키 `spiders`를 생성/안내하지 않음 — ❌ 미해결 (2026-07-13)

- **위치**: `generator_conditions.html`, `engine.py:36-60`
- **상세**: 어떤 스파이더 클래스가 실행되는지는 `conditions.accessType`/`pageType`이 아니라 별도의 최상위(또는 conditions 내부) `spiders` 문자열(`html`/`html_render`/`json`/`xml`/`detail`)로만 결정됨(`get_spider()`). 그런데 생성기 출력에는 이 키가 전혀 없어, 사용자가 request_info.json을 조립할 때 수기로 값을 채워야 하고 매핑을 안내해주는 화면도 없음. 특히 DETAIL+렌더링, DETAIL+JSON payload 같은 조합은 `html_render_detail`/`json_detail`/`json_payload_detail`로 이어지는데 이 값들은 `get_spider()`에서 `NotImplementedError`로 명시적으로 막혀 있는 미구현 스파이더라, 생성기 화면만 보고는 실행 불가능한 조합인지 알 수 없음.
- **필요 조치**: UI에 `spiders` 선택 필드를 추가하거나 accessType/pageType/dataFormat/rendering 조합으로부터 자동 계산해 출력에 포함하고, 미구현 조합 선택 시 경고를 띄우는 개선 필요.

### ㉓ `conditions.pageType`/`steps`/`redirect`, API 모드 `params`가 백엔드 어디서도 읽히지 않는 죽은 필드 — ❌ 미해결 (2026-07-13)

- **위치**: `generator_conditions.html:1360-1414,1454-1472`, `engine.py`, `glean.py`, `utility.py:58`
- **상세**: 실제 페이지네이션은 `callback_url` 문자열에 박아넣는 `${page:시작:증가:끝}` 템플릿(`utility.generate_combined_urls`)으로 처리되고, DETAIL 여부도 오직 `spiders` 값("detail")으로만 갈림. `conditions.pageType`/`conditions.steps`를 읽는 파이썬 코드가 전무(grep 전수 확인). `redirect`도 `get_scrapy_request()`가 요청 생성 시 실제로 반영하는 코드가 없음(과거 이슈 ①의 리다이렉트 수정은 응답 meta 처리 쪽이라 이 필드와 무관). API 모드의 `params` 역시 `engine.py`/스파이더 어디서도 읽지 않고, `get_spider()`가 `"api"`라는 accessType/spiders 값 자체를 인식하지 못해 API 모드로 생성한 JSON은 현재 실행 경로가 아예 없음.
- **필요 조치**: 사용자가 시간 들여 채워도 동작에 영향 없는 필드라 오해를 유발. 필드 제거 또는 "미구현" 표기, API 모드는 백엔드 구현 여부 결정 필요.

### ㉔ `items` 딕셔너리의 예약 키에 대한 UI 힌트 부재 — ❌ 미해결 (2026-07-13)

- **위치**: `generator_conditions.html:558-585`, `spiders/spidetail.py:41-59,80-88`, `spiders/spihtml.py`, `spiders/spirenderer.py:69`
- **상세**: 백엔드는 `items.root`(HTML/렌더링 스파이더 필수, `spihtml.py`/`spirenderer.py:69`), DETAIL 페이지의 `items.detail`(+ mainFormat=json이면 `items.detail_root`/`items.main_root`, `spidetail.py:41-59,80-88`)처럼 정해진 이름의 키를 기대하는데, 생성기는 이를 일반 Name/Value 목록으로만 받아 어떤 이름을 써야 하는지 안내가 전혀 없음. 오타·누락 시 `parse()`의 넓은 `except Exception`에 조용히 걸려 에러 로그만 남고 수집 결과 0건으로 종료됨(크래시 아님, ㉑과 동일한 실패 양상).
- **필요 조치**: pageType=DETAIL 선택 시 "root"/"detail"/"detail_root"/"main_root" 전용 입력 필드를 별도로 노출해 예약어를 강제하는 개선 필요.

### ㉙ 로그인 인증 수집의 스케줄러 연동 미구현 — ⏸ 보류 (2026-07-23)

- **위치**: `trigger.py`의 `GlobalToolbarTriggers._actual_start()`(반영됨, `a0be22f`) vs
  `SchedulerPageTriggers._apply_schedule()`/`_run_now()`(미반영)
- **상세**: 매뉴얼 "시작" 흐름은 인증 관리 페이지(`AuthManagerPage`)에 입력된 로그인 정보
  (`loginUrl`/`id`/`password`)를 `_actual_start()`가 `task["conditions"]["login"]`에 실시간
  반영하도록 구현됨(`request_info.json` 파일에는 쓰지 않고 이번 실행 task에만 반영). 반면
  스케줄 실행(`_run_now()`)은 `self.sched_task.update(deepcopy(BlueprintStorage().read())); self.sched_task.update(s)`로
  별도 구성되는데, `s`(등록 시점에 저장된 스케줄 dict)에는 로그인 정보가 전혀 없어 결국
  `BlueprintStorage().read()`의 `conditions.login`(대개 `id`/`password`가 `null`)만 그대로
  쓰임 — 로그인 인증이 필요한 수집을 스케줄로 등록해도 실제 자격증명 없이 실행되어 로그인
  실패로 수집이 중단될 수 있음.
- **보류 사유·필요 조치**: 스케줄은 무인 실행(이슈 ⑱ 참고)이라 매뉴얼 흐름처럼 "실행 시점의
  위젯 값"을 읽는 방식은 부적합 — 이미 같은 이유로 정제 규칙(`refine_rules`)이 스케줄 등록
  시점(`_apply_schedule()`)에 체크박스 상태를 스냅샷해 스케줄 dict에 저장하는 방식을 쓰고
  있으므로, 로그인 정보도 동일 패턴(등록 시점 스냅샷 → `_save_schedules_to_json()`으로 영속화
  → `_run_now()`에서 `sched_task["conditions"]["login"]`에 명시적 병합)을 적용하는 방향으로
  검토됨. DB 저장 자격증명(`db_pw`)도 이미 평문으로 스케줄 JSON에 저장되고 있어 새로운 보안
  리스크는 아님. 사용자와 우선순위 논의 후 착수 예정이라 별도 조치 없이 보류.

---

## 3. 문서 vs 코드 불일치

- ~~`spiders` 키 위치 불일치~~ → **해소** (PR #14): `get_spider()`가 `conditions` 내부를
  우선 조회하고 최상위로 fallback — 현행 request_info.json(최상위)과 문서 §5 예시(내부)
  둘 다 동작
- ~~§5 예시의 `/text()` XPath 미동작~~ → **해소** (PR #13, 이슈 ⑧ 수정)
- `LoadItemPipeline` 등의 f-string 중첩 따옴표 문법은 **Python 3.12+ 전용** —
  PyInstaller 빌드 환경도 3.12+ 필수

## 4. 보안·운영 관찰

- **`env/database.ini`에 실제 API 키 4개 평문 존재** (공공데이터포털, 한국은행,
  OpenDART, IROS). git 미추적 상태이지만, 그 이유가 Python 템플릿 `.gitignore`의
  `env/` 규칙(가상환경용)에 **우연히** 걸렸기 때문 → `.gitignore`에 명시적 등록
  또는 `.env` 이관 권장 (2026-07-09 재확인: 여전히 명시적 등록 안 됨)
- `ROBOTSTXT_OBEY=True`인 반면 봇 UA 행세·랜덤 쿠키·프록시 로테이션 미들웨어가
  공존 — 사용 정책 정리 필요
- **테스트 코드 0개** — 검증용으로 작성했던 미들웨어 테스트 8건은 검증 완료 후
  정책에 따라 저장소에서 제거됨 (PR #6). `preprocess.DataRefiner`,
  `utility.generate_combined_urls`가 테스트 도입 최적 지점
- `frames_tmp.py`(5,796줄)가 git 추적 중 — 가이드 스스로 임시 파일로 명시, 정리 대상 (2026-07-09 재확인: 여전히 추적 중, 어디서도 import 안 됨)
- Scrapy 2.16으로 올리면 sync `start_requests()`가 **에러 없이 무시되어 0건 수집**
  (검증 중 실측) — 업그레이드 시 async `start()` 마이그레이션 필수

## 5. 미사용 코드·모듈 (2026-07-06 전수 감사)

> 전 모듈(약 16,000줄) import 그래프·참조 추적 결과. 삭제는 별도 커밋으로 분리 권장.

| 대상 | 내용 |
|---|---|
| **`frames_tmp.py` (5,796줄)** | 어디서도 import되지 않는 구버전 모놀리스(전체 코드의 36%). layout.py/trigger.py로 분리 완료된 임시 백업본. 이슈 ⑩의 `net_rotate` 잔재 스키마 출처 — **삭제 1순위** |
| `spiders/sample.py` | 0바이트 빈 파일 |
| `middlewares.py` | `RandomProxyMiddleware` 완전 미사용. `DonasSpiderMiddleware`/`DonasDownloaderMiddleware`는 startproject 보일러플레이트 (settings에서 None/주석 처리) |
| `engine.py` | `set_requests`, `requests_info`, `make_form_data_for_url_args` 미사용. 주석 처리된 `set_item_loader` 2벌(362-369, 405-422행). 미사용 import: `db_conn`, `dt`, `WebDriverWait`, `EC` |
| `utility.py` | `get_isin_dict`, `_calculate_next_run`, `check_lap_time`, `get_all_nested_keys` 미사용 |
| `items.py` | `DefaultItem`, `StoreItem`, `DonasBatchItem` 미사용 (실사용은 `DonasItem`/`DonasItemLoader`뿐) |
| `customized_settings.py` | `get_settting_frame`, `auth_settings`, `get_session_settings` 미사용 |
| `worker.py:55-60` | `LOG_TEMPLATES` — frames_tmp 시절 가짜 로그 생성용 잔재, 미사용 |
| `create_request_info.py` | 앱에서 import되지 않는 독립 스크립트(DB→request_info.json 생성용)라 유지는 타당. 단 `pickle` import 미사용 |
| `env/create_ini.py`, `env/check_ini_section.py` | 2021년산 일회성 독립 유틸 스크립트 — 유지 여부 선택 |
| `requirements.txt` | `mysqlclient`와 `PyMySQL` 중복 — `db_conn.py`는 `mysql+pymysql`만 사용하므로 `mysqlclient` 불필요 |
| ~~`layout.py:1346`~~ | ~~`SchedulerPage.file_path` 선언만 되고 미사용~~ → **해소** (이슈 ⑫ 해결, 실제 저장 경로로 사용됨) |

## 6. 남은 작업 백로그 (권장 우선순위)

1. ~~**스케줄 기능 복구 (⑨·⑩·⑪·⑫)**~~ → **해소** — SchedulerPage가 실제 SessionSettingsPage
   인스턴스를 주입받도록 수정, `net_rotate` 잔재 검증을 현행 스키마
   (`session_page._proxy_rows`)로 교체, 월간 스케줄 QTimer OverflowError 해소
   (7일 단위 타이머 분할), 스케줄 저장 경로를 `file_path`(LOCALAPPDATA)로 교정
2. ~~**크롤링 경로 견고화 (⑬·⑭·⑮·⑯)**~~ → **⑬·⑭·⑮ 해소, ⑯ 보류**(다중 블루프린트 업그레이드에서 재설계 예정, §2 참고)
3. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
4. ~~**`worker.set_scrapy_settings()` 예외 삼킴 개선**~~ → **해소** (`f00bc77`) —
   핵심 설정(`DOWNLOADER_MIDDLEWARES`/`ITEM_PIPELINES`/`CONCURRENT_REQUESTS`/
   `DOWNLOAD_DELAY`/`DOWNLOAD_TIMEOUT`)을 try 밖으로 옮겨 실패 시 예외가
   그대로 전파되도록 변경, try는 실패해도 진행 가능한 프록시 설정 주입으로 한정
5. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
6. **정리**: §5 미사용 코드·모듈 삭제 (`frames_tmp.py` 우선),
   GUI DB 내보내기(UI만 존재)의 파이프라인 연결 여부 결정
7. (참고, 낮은 우선순위) **`DelaySchedulerMiddleware`의 `meta.pop('delay_until')` 제자리 변경** —
   동일 Request 객체가 두 번 yield되면 한쪽은 즉시, 한쪽은 지연 후 나가 중복 크롤 가능성.
   현재 모든 spider가 매번 새 Request를 생성하고 `delay_until`을 설정하는 코드도 없어
   당장은 도달 불가한 잠재 리스크 (PR #23 리뷰에서 확인, `middlewares.py:266-278`)
