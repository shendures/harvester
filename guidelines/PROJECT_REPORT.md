# DataCrawler v2.0 (Harvest) — 프로젝트 리포트

> 프로젝트 구조·아키텍처 설명 문서입니다. 함께 관리되는 문서:
> - **이슈·백로그**: `ISSUES.md`
> - **진행 이력**: `HISTORY.md`

- **최신 갱신**: 2026-07-25 17:40

---

## 1. 프로젝트 개요

**DataCrawler**는 Scrapy 크롤링 엔진과 PyQt6 GUI를 결합한 데스크톱 웹 데이터 수집 애플리케이션입니다.
사용자는 코드 없이 GUI를 통해 수집 조건을 설정하고, 실시간으로 수집 진행 상황을 모니터링하며,
결과를 CSV 파일 또는 데이터베이스로 내보낼 수 있습니다.

- **엔진**: Scrapy 2.14 (비동기 크롤링)
- **UI**: PyQt6
- **지원 데이터 형식**: HTML (정적 / Selenium 렌더링), JSON (REST API), XML
- **출력**: CSV, MongoDB, MySQL, PostgreSQL

### 구성 및 규모

| 영역 | 파일 | 규모 |
|---|---|---|
| GUI 레이아웃 | `layout.py` | 1,965줄 |
| 이벤트 핸들러 (Mixin) | `trigger.py` | 3,996줄 |
| 테마·공용 위젯·정제 규칙 UI 빌더 | `style.py` | 881줄 |
| 수집 워커 (QThread + multiprocessing) | `worker.py` | 513줄 |
| 요청 생성·데이터 추출 | `engine.py` | 320줄 |
| Spider 5종 | `spiders/` | html / html_render / json / xml / detail |
| 데이터 정제 | `preprocess.py` | 358줄 |
| 설정·상태 공유 (싱글턴 3종) | `conf.py` | 437줄 |

---

## 2. 아키텍처 요약

```
[사용자 GUI]
    main.py → layout.py
        │
        ├── GlobalToolbar (시작/중지 버튼)
        ├── DashboardPage (대시보드)
        ├── MonitorPage (수집 결과)
        ├── StatisticsPage (통계 분석)
        ├── SchedulerPage (스케줄러)
        ├── SessionSettingsPage (세션 설정)
        └── AuthManagerPage (인증 관리)

[수집 실행 흐름]
    worker.py (MultiprocessWorker, QThread)
        └── run_spider() — 별도 프로세스
                └── Scrapy CrawlerProcess
                        └── spiders/*.py
                                └── engine.py (요청 생성, 데이터 추출)
                                        └── pipelines.py (결과 출력)

[데이터 공유]
    multiprocessing.Queue  ←→  DataStore (싱글턴, 메인 프로세스 전용)

[설정 관리]
    request_info.json  →  BlueprintStorage (싱글턴)
    custom_rules/{render,refine}/{seq_no}.py  →  CustomModuleStorage (싱글턴)
    customized_settings.py (기본값 정의)
    settings.py (Scrapy 설정)
```

### 핵심 실행 흐름 (코드로 검증됨)

```
GUI 시작 버튼
  → GlobalToolbarTriggers._actual_start()      # blueprint + UI 설정으로 task 구성
  → MainWindow._launch_worker()                 # MultiprocessWorker(QThread) 시작
  → multiprocessing.Process(run_spider)         # Scrapy 격리 실행
      → CrawlerProcess → spiders/*.py
      → LoadItemPipeline: "RESULT_INFO:{json}" → stdout → Queue
  → MultiprocessWorker._handle_line()           # 파싱 → 시그널 emit
  → DashboardPage / MonitorPage 실시간 갱신
```

설계 강점: 프로세스 경계(DataStore는 메인 프로세스 전용)가 docstring에 명시됨,
큐 드레인 로직이 멀티프로세스 함정을 제대로 처리, `preprocess.DataRefiner`의
원본 불변·통계 추적 품질 높음.

---

## 3. 파일별 상세 설명

### 진입점

#### `main.py`
애플리케이션 진입점. PyQt6 앱을 초기화하고 `MainWindow`를 시작합니다.
- `QLocalServer` / `QLocalSocket`으로 중복 실행을 방지합니다.
- Windows 작업 표시줄 아이콘 등록(`SetCurrentProcessExplicitAppUserModelID`)을 처리합니다.
  실제 아이콘 이미지는 `app.setWindowIcon(QIcon(...))`(`combine-harvester.ico`)로 별도 지정합니다 —
  `SetCurrentProcessExplicitAppUserModelID`만으로는 작업 표시줄 그룹 식별자만 정해질 뿐
  아이콘 이미지 자체는 바뀌지 않습니다(트레이 아이콘은 `TrayManager`가 동일 파일로 별도 설정).

---

### GUI 레이어

#### `layout.py`
GUI의 전체 레이아웃과 페이지를 정의하는 핵심 파일 (2,000+ 줄).

| 클래스 | 역할 |
|---|---|
| `MainWindow` | 전체 윈도우 컨테이너. Sidebar + GlobalToolbar + 페이지 스택 조합 |
| `Sidebar` | 좌측 내비게이션 메뉴 (대시보드, 모니터링, 스케줄러, 통계분석, 세션설정, 인증관리) |
| `GlobalToolbar` | 상단 고정 툴바. URL 입력, 시작/중지 버튼 |
| `DashboardPage` | 수집 진행 상태(Step Tracker), 수집 설정(딜레이·스레드), 세션 통계, 실시간 모니터링 테이블 |
| `MonitorPage` | 4탭 구조 — ① Raw 수집결과 ② 정제규칙 설정 ③ 정제결과 ④ Before/After 비교(좌우 테이블 스크롤·정렬 동기화) |
| `StatisticsPage` | KPI 카드, 상태코드 도넛 차트, 응답시간 바 차트, 시간대별 추이 선 그래프, 세션 이력 테이블 |
| `SchedulerPage` | 스케줄 작업 등록/수정/삭제. 주기: 매일/주간/월간/특정일. "저장 대상"이 "정제"일 때 스케줄별 정제 규칙을 구성하는 가로 인라인 패널 포함(2026-07-17) |
| `SessionSettingsPage` | 수집 딜레이, 스레드, 타임아웃, 재시도, User-Agent, 쿠키, 프록시 설정 |
| `AuthManagerPage` | 로그인 정보(ID/PW) 또는 API 라이선스 토큰 관리 |
| `BarChart` / `LineChart` / `DonutChart` | QPainter 기반 커스텀 차트 위젯 |

#### `style.py`
테마 색상, 공통 위젯 팩토리, UI 컴포넌트를 정의합니다.
- `THEME` 클래스: 모든 색상의 단일 정의 소스 (BG_PRIMARY, ACCENT, GREEN, RED 등)
- `Parts`: 반복 사용되는 위젯(버튼, 카드, 레이블)을 생성하는 팩토리 메서드 모음
- `NavItem`, `TagButton`, `StatCard`, `Divider`, `EqualSpacingTable`, `ClickableRuleRow`:
  재사용 가능한 커스텀 위젯(`ClickableRuleRow`는 2026-07-17 `layout.py`에서 이전)
- `REFINE_RULE_DEFS`/`build_refine_rule_rows()`: 정제 규칙 체크박스 행 정의·빌더
  (2026-07-17 신설) — MonitorPage "② 정제 규칙 설정" 탭과 "새 스케줄 등록"의
  정제 규칙 패널이 공유(`layout.py`가 `trigger.py`를 import하는 구조상, 두 곳이
  공유할 UI 빌더는 순환 import 없이 양쪽이 모두 import 가능한 `style.py`에
  둠). 상세는 `guidelines/PREPROCESS.md` §2·§2.3 참고.

#### `trigger.py`
`layout.py`의 각 페이지 클래스에 **Mixin** 형태로 주입되는 이벤트 핸들러 모음.
레이아웃 코드(UI 구성)와 비즈니스 로직(버튼 클릭 처리)을 분리하기 위해 사용됩니다.

| 클래스 | 연결 대상 |
|---|---|
| `GlobalToolbarTriggers` | 시작/중지 버튼, URL 복사 |
| `DashboardPageTriggers` | 수집 시작, CSV 내보내기, 진행률 업데이트 |
| `MonitorPageTriggers` | 테이블 필터, 정제 실행, 결과 추출 |
| `StatisticsPageTriggers` | 통계 데이터 리로드/내보내기 |
| `SchedulerPageTriggers` | 스케줄 등록/수정/삭제/실행, 스케줄별 정제 규칙 패널 구성(`_open_schedule_refine_rules_dialog`는 2026-07-17 인라인 패널 도입으로 제거됨) |
| `SessionSettingsPageTriggers` | 세션 설정 저장, 프록시 추가/삭제/Import/활성화 토글 |
| `AuthManagerPageTriggers` | 인증 정보 저장 |
| `TrayManagerTriggers` | 시스템 트레이 아이콘 관리 |
| `MainWindowTriggers` | 윈도우 레벨 이벤트 |
| `LogViewerDialog` | 수집 로그 뷰어 다이얼로그 |

---

### 수집 실행 레이어

#### `worker.py`
수집 작업의 비동기 실행을 담당합니다.

- **`MultiprocessWorker` (QThread)**: UI 블로킹 없이 수집을 실행합니다.
  - 별도의 `multiprocessing.Process`로 Scrapy를 격리 실행합니다 (Scrapy는 프로세스당 1회 실행 제약).
  - `multiprocessing.Queue`를 통해 자식 프로세스의 수집 결과를 수신합니다.
  - PyQt6 시그널로 UI에 실시간 결과를 전달합니다: `new_row`, `progress`, `stats_update`, `finished`

- **`run_spider()`**: 자식 프로세스 진입점.
  - `sys.stdout` / `sys.stderr`를 `QueueWriter`로 리다이렉트하여 Scrapy 출력을 Queue로 전송합니다.
  - `RESULT_INFO:` 접두사로 수집 결과를, `EXECUTOR_STATUS:` 접두사로 성공/실패를 구분합니다.

- **`QueueWriter`**: 자식 프로세스의 `stdout`/`stderr`를 `Queue`로 리다이렉트하는 파일 유사 객체.

#### `engine.py`
Scrapy 요청 생성과 데이터 추출 로직의 핵심 모듈.

| 함수 | 역할 |
|---|---|
| `get_spider(request_info)` | `spiders` 키(`conditions` 내부 우선, 없으면 최상위 fallback)에 따라 적합한 Spider 클래스를 반환 |
| `get_scrapy_request(url, conditions, callback)` | GET/POST, 일반/렌더링/JSON/FormData 요청 객체를 생성 |
| `set_requests(collect_info, callback)` | URL 목록을 생성하고 요청을 yield |
| `get_result(collect_info, target, _items)` | HTML(XPath)/JSON/XML에서 데이터를 추출하여 딕셔너리 리스트로 반환 |
| `extract_data_from_root(root, _items)` | XPath 셀렉터 기준으로 컬럼별 값을 추출하고 행 단위로 재조합 |
| `set_item_loader(response, collect_info, data)` | Scrapy Item에 수집 결과를 패킹 |
| `get_response_status(response)` | 응답 정보(URL, IP, UA, 쿠키, 레이턴시)를 딕셔너리로 정리 |
| `set_chrome_webdriver(headless)` | Selenium Chrome 드라이버를 초기화 |

`run_login()`/`get_render_result()`처럼 사이트별(seq_no) 로그인·렌더링 로직을
`engine.py`에 하드코딩하던 옛 함수들은 제거되었습니다 — 현재는
`custom_rules/render/{seq_no}.py`의 `login(driver, login_info)`/
`render(driver, selectors, items)`를 `conf.CustomModuleStorage.load_login()`/
`load_render()`가 로드해 대체합니다(`engine.py:158` 주석 참고, §데이터 정제
및 `PREPROCESS.md` §3.1a 참고).

---

### Spider 패키지 (`spiders/`)

각 Spider는 데이터 형식과 수집 방식에 따라 분리되어 있습니다.

| 파일 | Spider 이름 | 설명 |
|---|---|---|
| `spihtml.py` | `spider_html` | 정적 HTML 페이지를 XPath로 파싱 |
| `spirenderer.py` | `spider_html_render` | Selenium으로 JavaScript 렌더링 후 XPath 파싱 |
| `spijson.py` | `spider_json` | REST API JSON 응답을 jmespath/점 경로로 추출 |
| `spixml.py` | `spider_xml` | XML 응답을 XPath로 파싱 |
| `spidetail.py` | `spider_detail` | 목록 페이지 → 상세 페이지 2단계 수집 |

모든 Spider는 `engine.get_scrapy_request()`로 요청을 생성하고 `engine.set_item_loader()`로 결과를 패킹하는 동일한 구조를 따릅니다.

---

### 파이프라인 (`pipelines.py`)

Scrapy Item이 Spider에서 나온 뒤 거치는 후처리 단계.

| 클래스 | 역할 |
|---|---|
| `LoadItemPipeline` | 수집 결과를 `RESULT_INFO:` 형식으로 stdout에 출력 → `MultiprocessWorker`가 수신 |

현재 유일한 파이프라인. 미사용이던 `DonasPipeline`·`CsvExportPipeline`·`MongoDBPipeline`은
PR #8에서 제거됨 (`ISSUES.md` 이슈 ④ 참고). GUI의 DB 내보내기 UI는 파이프라인에 연결되어 있지 않음.

---

### 데이터 정제 (`preprocess.py`)

수집된 raw 데이터를 정제하는 로직 전담 모듈.

- **`DataRefiner`**: 7가지 정제 규칙을 순서대로 적용합니다. 순서는 2026-07-16·
  07-17 두 차례 재배치를 거쳐 현재는 ①remove_null_row→②custom_rule→
  ③trim_whitespace→④remove_duplicate→⑤drop_columns→⑥fill_null→⑦cast_numeric
  입니다 — `custom_rule`은 더 이상 "항상 맨 먼저"가 아니라 계산량이 가장 가벼운
  `remove_null_row` 다음(②)으로 승격 이력은 PR #41(도입) → `1bfbeef`(정식 규칙화)
  → `6263b55`(현재 순서) 순. 상세 순서 변경 이력과 근거는 `PREPROCESS.md` §1·
  `HISTORY.md` 참고.
  1. `remove_null_row`: null 포함 행 제거 — 계산량이 가벼워 가장 먼저 실행
  2. `custom_rule`: seq_no별 커스텀 정제 함수 적용 (있고 활성화된 경우만, 아래 참고)
  3. `trim_whitespace`: 문자열 앞뒤 공백 제거
  4. `remove_duplicate`: 중복 행 제거
  5. `drop_columns`: 지정 컬럼 제외
  6. `fill_null`: null → 지정값 치환 (기본 빈 값 — GUI/`DataRefiner` 직접 호출 동일)
  7. `cast_numeric`: 문자열 숫자 → int/float 변환

- **`RefineStats`**: 정제 결과 통계(원본 행 수, 정제 후 행 수, 제거 행 수, 치환 값 수,
  `custom_rule_applied`/`custom_rule_error`)를 담는 dataclass.

- **커스텀 정제 규칙 (`custom_rule`, "7번째 규칙")**: 수집물(blueprint)마다 원시
  데이터 형식이 달라 범용 규칙만으로 커버되지 않는 경우를 위한 플러그인 메커니즘.
  `custom_rules/refine/{seq_no}.py`에 `refine(data)` 또는 `refine_row(row)`를
  정의하면 `preprocess.load_custom_rule(seq_no)`가 로드해 `DataRefiner`에
  전달합니다. 경로 해석·시딩·실제 로드는 `conf.CustomModuleStorage`가
  전담(§`conf.py` 참고). 상세 규약·개발 프로세스는 `PREPROCESS.md` 참고.
  GUI "② 정제 규칙 설정" 탭(및 "새 스케줄 등록"의 정제 규칙 패널)에서 "커스텀
  정제 규칙 적용" 체크박스를 켜면 remove_null_row/trim_whitespace/remove_duplicate
  가 자동으로 켜짐(토글마다 매번 강제 적용) — `fill_null`은 2026-07-17에 자동
  연동 대상에서 제외됨(사용자 피드백). 해제 시에는 자동 연동 대상 규칙에 영향 없음.

---

### 설정 및 상태 관리

#### `conf.py`
앱 전체에서 데이터를 공유하는 세 개의 싱글턴 클래스.

- **`DataStore`**: 수집된 행(`_rows`), URL 맵(`_url_map_list`), 세션 이력(`_sessions`), 스케줄(`_schedules`)을 메모리에 보관합니다. 메인 프로세스에서만 유효합니다.

- **`BlueprintStorage`**: `request_info.json`을 로드하여 수집 청사진을 관리합니다. 최초 1회 초기화 후 `reload()`로 갱신할 수 있습니다. 파일 위치(`app_dir`)는 `utility.data_dir()`가 결정합니다 — 운영(exe)은 `%LOCALAPPDATA%`, 개발(`.py`)은 저장소 in-place라 `file_path == default_source`가 되어 seed 복사 없이 저장소 파일을 그대로 읽습니다.

- **`CustomModuleStorage`**: seq_no별 커스텀 모듈(`{kind}/{seq_no}.py`)을
  로드합니다 (`53978d0`, render/refine 분리 리팩터링으로 옛 `CustomRuleStorage`를
  대체). 수집 단계(Selenium 자식 프로세스)와 정제 단계(메인 GUI 프로세스)는
  실행 컨텍스트가 달라 `kind` 파라미터(`"render"` / `"refine"`)로 물리적으로
  다른 서브폴더를 씁니다:
  - `kind="render"` → `custom_rules/render/{seq_no}.py`: `login(driver, login_info)`,
    `render(driver, selectors, items)`
  - `kind="refine"` → `custom_rules/refine/{seq_no}.py`: `refine(data)` 또는
    `refine_row(row)`

  `BlueprintStorage`와 동일한 경로 정책을 씁니다 — 데이터 폴더(`app_dir`)는
  `utility.data_dir()`가 결정(운영 exe: `%LOCALAPPDATA%`, 개발 `.py`: 저장소
  in-place)하고, seed-on-first-run은 `file_path != default_source`(=운영)일 때만
  번들 리소스에서 최초 1회 복사합니다(개발에선 저장소 파일을 직접 실행 → 편집·
  디버깅 즉시 반영, 같은 경로 self-copy 방지). seq_no마다 파일이 다르므로 단일
  값을 캐싱하지 않고 매 호출마다 새로 읽고 실행합니다. 존재 여부만 확인하는
  `has_refine()`/`has_render()`/`has_login()`은 AST 파싱만으로(exec 없이)
  판단하고, 실제 로드는 `load_refine()`/`load_render()`/`load_login()`이
  담당합니다. 배포 시 고객별 seq_no 파일만 골라 번들에 포함시키는 절차는
  레포 루트의 `build-exe.ps1` 참고.

#### `customized_settings.py`
각 설정 딕셔너리의 기본값을 반환하는 팩토리 함수 모음.

| 함수 | 반환하는 설정 |
|---|---|
| `get_request_settings()` | 수집 요청 정보 기본 구조 |
| `get_task_settings()` | 딜레이, 스레드, 타임아웃, 재시도 기본값 |
| `get_session_settings()` | UA 랜덤, 쿠키 랜덤, 프록시 설정 |
| `get_output_settings()` | 파일/DB 추출 설정 기본값 |
| `get_schedule_settings()` | 스케줄 설정 기본값 |
| `set_downloader_middlewares()` | 요청 정보 기반으로 활성화할 미들웨어 딕셔너리 반환 |
| `set_ip_settings()` | 프록시 IP 설정 반환 |

#### `settings.py`
Scrapy 프레임워크 설정 파일.

주요 설정:
- `CONCURRENT_REQUESTS = 32` / `CONCURRENT_REQUESTS_PER_DOMAIN = 8`
- `RANDOMIZE_DOWNLOAD_DELAY = True`
- `ITEM_PIPELINES`: 기본 `LoadItemPipeline` (GUI 실행 시에도 동일 파이프라인으로 재설정)
- `DOWNLOADER_MIDDLEWARES`: 프록시, User-Agent 랜덤화, 레이턴시 추적 순서로 구성
  (`scrapy_selenium.SeleniumMiddleware`는 죽은 의존성이라 `ISSUES.md` 이슈 ⑬에서
  제거됨 — 렌더링은 `spirenderer.py`가 자체 Chrome 드라이버로 전담)
- `SPIDER_MIDDLEWARES`: `middlewares.DelaySchedulerMiddleware` 등록(500)
- `TELNETCONSOLE_ENABLED = False` — 배포용 exe가 콘솔 접속 기능을 쓰지 않는데도
  기본 활성화 상태라 Windows 방화벽 알림을 유발해 비활성화

#### `middlewares.py`
Scrapy 다운로더/스파이더 미들웨어 모음.

| 클래스 | 역할 |
|---|---|
| `RandomUserAgentMiddleware` | 요청마다 User-Agent를 랜덤 교체 |
| `RandomCookieMiddleware` | 쿠키를 랜덤 설정 (이미 쿠키가 있으면 `None` 반환 — `ISSUES.md` 이슈 ③ 해결) |
| `RateLimitedProxyMiddleware` | 여유 있는 프록시를 무작위 순회로 할당, 전량 소진 시 `DelaySchedulerMiddleware`와 연동해 지연 재시도 (`ISSUES.md` 이슈 ② 해결) |
| `LatencyTrackingMiddleware` | 요청~응답 구간 레이턴시를 측정하여 `meta["pure_latency"]`에 저장 |
| `_DelayedRescheduler` | `DelaySchedulerMiddleware`/`RateLimitedProxyMiddleware`가 공유하는 지연 재주입 헬퍼 (`reactor.callLater` + `engine.crawl()`) |
| `DelaySchedulerMiddleware` | `SPIDER_MIDDLEWARES`에 등록되어 `delay_until`이 걸린 요청을 지연 재스케줄 (`ISSUES.md` 이슈 ⑤ 해결) |

---

### 유틸리티

#### `utility.py`
프로젝트 전반에서 사용하는 범용 함수 모음.

| 함수 | 역할 |
|---|---|
| `resource_path()` | **배포 기본값(read-only) 루트** 반환 — `.py`는 프로젝트 루트, `.exe`는 번들(`_MEIPASS`). 번들에 포함된 기본 리소스의 위치 |
| `data_dir(app_name)` | **앱이 실제로 읽고 쓰는 활성 데이터 폴더** 반환 — `.exe`(`sys._MEIPASS` 존재)면 `%LOCALAPPDATA%\<app>`(비-win32는 `~/.config/<app>`), `.py`면 `resource_path()`(저장소 in-place). 개발 시 편집 파일이 곧 실행 파일이 되어 디버깅(브레이크포인트·Step Into) 정상화. `resource_path()`와는 **운영에서만 갈라짐** |
| `get_app_name(default)` | 앱 데이터 폴더명 결정 — 빌드된 exe는 실행 파일명(`sys.frozen`), `.py`는 기본값 `CollectorApp` |
| `generate_combined_urls(url_template)` | URL 템플릿의 `${page:1:1:10}` (페이지네이션)과 `${keywords:서울,인천}` (목록 확장) 패턴을 파싱하여 URL 리스트 생성 |
| `get_target(data, target)` | 중첩 dict/list에서 점(`.`) 경로 또는 재귀 탐색으로 값 추출 |
| `_calculate_next_run(schedule_info)` | 일간/주간/월간/특정일 스케줄의 다음 실행 시각 계산 |

#### `glean.py`
URL 목록을 생성하는 단일 함수 `get_grains(collect_info)`.
내부적으로 `utility.generate_combined_urls()`를 호출합니다.

#### `items.py`
Scrapy Item 및 ItemLoader 정의. 수집 결과를 구조화된 형태로 파이프라인에 전달합니다.

#### `db_conn.py`
데이터베이스 연결 파라미터를 반환하는 헬퍼 모듈 (MySQL, PostgreSQL, MongoDB 지원).

#### `create_request_info.py`
`request_info.json` 파일을 생성하는 스크립트 (개발 도구).

---

### 환경 설정 패키지 (`env/`)

| 파일 | 역할 |
|---|---|
| `config.py` | `database.ini` 파일을 파싱하여 DB 접속 정보를 딕셔너리로 반환 |
| `create_ini.py` | `database.ini` 파일을 생성 |

---

## 4. 수집 데이터 흐름

```
request_info.json
    │  (BlueprintStorage로 로드)
    │
    ▼
GUI 시작 버튼 클릭
    │
    ▼
MultiprocessWorker.run()           ← QThread (UI 비블로킹)
    │
    ├── utility.generate_combined_urls()  → URL 목록 생성
    │
    └── multiprocessing.Process(run_spider)
            │
            ├── engine.get_spider() → Spider 클래스 선택
            │
            ├── Scrapy CrawlerProcess.crawl(spider, request_info)
            │       │
            │       ├── spider.start_requests()
            │       │       └── glean.get_grains() → URL 목록
            │       │               └── engine.get_scrapy_request() → Request 객체
            │       │
            │       ├── [middlewares] UA 교체, 쿠키, 프록시, 레이턴시 측정
            │       │
            │       ├── spider.parse(response)
            │       │       └── engine.get_result() → 딕셔너리 리스트
            │       │               └── engine.set_item_loader() → DonasItem
            │       │
            │       └── [pipelines] LoadItemPipeline
            │               └── print("RESULT_INFO:{...}")  → stdout → Queue
            │
            └── MultiprocessWorker._handle_line()
                    ├── DataStore.add_row()
                    ├── new_row.emit()   → DashboardPage / MonitorPage 테이블 갱신
                    ├── progress.emit()  → 프로그레스 바 갱신
                    └── stats_update.emit() → 세션 통계 갱신
```

---

## 5. 핵심 설정 파일: `request_info.json`

수집 작업의 청사진(blueprint)입니다. `BlueprintStorage`가 로드하고 `DataStore`와 각 Spider에 전달됩니다.

```json
{
  "seq_no": "000001",
  "title": "작업명",
  "url": "원본 URL",
  "callback_url": "https://example.com/list?page=${page:1:1:10}",
  "conditions": {
    "method": "GET",
    "dataFormat": "html",
    "rendering": false,
    "spiders": "html",
    "headers": null,
    "items": {
      "root": "//div[@class='list']/li",
      "title": ".//h2/text()",
      "price": ".//span[@class='price']/text()"
    }
  }
}
```

**`callback_url` 패턴**
- `${page:시작:증가:끝}` — 페이지네이션 URL 자동 생성
- `${keywords:서울,인천,부산}` — 키워드 목록으로 URL 확장

**`spiders` 값에 따른 Spider 선택**
| 값 | Spider | 설명 |
|---|---|---|
| `html` | `HtmlExtractorSpider` | 정적 HTML + XPath |
| `html_render` | `HtmlSeleniumSpider` | JS 렌더링 + XPath |
| `json` | `JsonExtractorSpider` | REST API + 점 경로 |
| `xml` | `XmlExtractorSpider` | XML + XPath |
| `detail` | `DetailExtractorSpider` | 목록→상세 2단계 |

> `spiders` 키는 `conditions` 내부(위 예시)와 최상위(현행 request_info.json) 어느 쪽에 있어도
> 동작합니다 (PR #14, 내부 우선). `items`의 XPath는 요소(`.//h2`)·텍스트(`.//h2/text()`)·속성(`@href`)
> 표기를 모두 지원합니다 (PR #13).

---

## 6. 의존성 요약

| 라이브러리 | 용도 |
|---|---|
| `Scrapy` | 비동기 웹 크롤링 엔진 |
| `PyQt6` | 데스크톱 GUI 프레임워크 |
| `selenium` | JavaScript 렌더링 페이지 수집 (`spirenderer.py`가 직접 구동, `scrapy-selenium`은 이슈 ⑬로 제거됨) |
| `webdriver-manager` | Chrome 드라이버 자동 설치 |
| `lxml` / `parsel` | HTML/XML 파싱 |
| `pymongo` | MongoDB 연결 |
| `mysqlclient` / `PyMySQL` | MySQL 연결 |
| `psycopg2` | PostgreSQL 연결 |
| `SQLAlchemy` | ORM (DB 추상화) |
| `furl` | URL 파싱/조작 |
| `python-dotenv` | 환경 변수 로드 |
| `pyinstaller` | 실행 파일(.exe) 빌드 — 레포 루트 `build-exe.ps1 -SeqNo {seq_no}`로 seq_no별 `custom_rules/`·`request_info.json`을 선별 번들 |
| Inno Setup | (Python 패키지 아님, Windows 전용 외부 도구) `build-installer.ps1`이 `build-exe.ps1`로 만든 `dist\{AppName}.exe`를 `installer.iss`로 감싸 설치 프로그램(`dist\{AppName}-Setup.exe`)으로 패키징 — 파일 배포 대신 설치/제거·바로가기 생성을 지원 |

