# DataCrawler v2.0 (Harvest) — 프로젝트 리포트

> `PROJECT_GUIDE.md`(구조 설명)와 `PROJECT_AUDIT_REPORT.md`(진행상황/이슈)를 통합한 문서입니다.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-07-05
- **조사 범위**: 전체 소스 코드(약 16,200줄), 문서(`systems/`), Git 이력, 의존성, 보안

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
| GUI 레이아웃 | `layout.py` | 3,010줄 |
| 이벤트 핸들러 (Mixin) | `trigger.py` | 2,660줄 |
| 수집 워커 (QThread + multiprocessing) | `worker.py` | 511줄 |
| 요청 생성·데이터 추출 | `engine.py` | 426줄 |
| Spider 5종 | `spiders/` | html / html_render / json / xml / detail |
| 데이터 정제 | `preprocess.py` | 279줄 |
| 프로토타입 잔재 (정리 대상) | `frames_tmp.py` | 5,796줄 (git 추적 중) |

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
원본 불변·통계 추적 품질 높음. `PROJECT_GUIDE.md`(구 문서) 충실도 높음.

---

## 3. 파일별 상세 설명

### 진입점

#### `main.py`
애플리케이션 진입점. PyQt6 앱을 초기화하고 `MainWindow`를 시작합니다.
- `QLocalServer` / `QLocalSocket`으로 중복 실행을 방지합니다.
- Windows 작업 표시줄 아이콘 등록(`SetCurrentProcessExplicitAppUserModelID`)을 처리합니다.

---

### GUI 레이어

#### `layout.py`
GUI의 전체 레이아웃과 페이지를 정의하는 핵심 파일 (3000+ 줄).

| 클래스 | 역할 |
|---|---|
| `MainWindow` | 전체 윈도우 컨테이너. Sidebar + GlobalToolbar + 페이지 스택 조합 |
| `Sidebar` | 좌측 내비게이션 메뉴 (대시보드, 모니터링, 스케줄러, 통계분석, 세션설정, 인증관리) |
| `GlobalToolbar` | 상단 고정 툴바. URL 입력, 시작/중지 버튼 |
| `DashboardPage` | 수집 진행 상태(Step Tracker), 수집 설정(딜레이·스레드), 세션 통계, 실시간 모니터링 테이블 |
| `MonitorPage` | 4탭 구조 — ① Raw 수집결과 ② 정제규칙 설정 ③ 정제결과 ④ Before/After 비교 |
| `StatisticsPage` | KPI 카드, 상태코드 도넛 차트, 응답시간 바 차트, 시간대별 추이 선 그래프, 세션 이력 테이블 |
| `SchedulerPage` | 스케줄 작업 등록/수정/삭제. 주기: 매일/주간/월간/특정일 |
| `SessionSettingsPage` | 수집 딜레이, 스레드, 타임아웃, 재시도, User-Agent, 쿠키, 프록시 설정 |
| `AuthManagerPage` | 로그인 정보(ID/PW) 또는 API 라이선스 토큰 관리 |
| `BarChart` / `LineChart` / `DonutChart` | QPainter 기반 커스텀 차트 위젯 |

#### `style.py`
테마 색상, 공통 위젯 팩토리, UI 컴포넌트를 정의합니다.
- `THEME` 클래스: 모든 색상의 단일 정의 소스 (BG_PRIMARY, ACCENT, GREEN, RED 등)
- `Parts`: 반복 사용되는 위젯(버튼, 카드, 레이블)을 생성하는 팩토리 메서드 모음
- `NavItem`, `TagButton`, `StatCard`, `Divider`, `EqualSpacingTable`: 재사용 가능한 커스텀 위젯

#### `trigger.py`
`layout.py`의 각 페이지 클래스에 **Mixin** 형태로 주입되는 이벤트 핸들러 모음.
레이아웃 코드(UI 구성)와 비즈니스 로직(버튼 클릭 처리)을 분리하기 위해 사용됩니다.

| 클래스 | 연결 대상 |
|---|---|
| `GlobalToolbarTriggers` | 시작/중지 버튼, URL 복사 |
| `DashboardPageTriggers` | 수집 시작, CSV 내보내기, 진행률 업데이트 |
| `MonitorPageTriggers` | 테이블 필터, 정제 실행, 결과 추출 |
| `StatisticsPageTriggers` | 통계 데이터 리로드 |
| `SchedulerPageTriggers` | 스케줄 등록/수정/삭제/실행 |
| `SessionSettingsPageTriggers` | 세션 설정 저장 |
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
| `get_spider(conditions)` | 수집 조건(`spiders` 키)에 따라 적합한 Spider 클래스를 반환 |
| `get_scrapy_request(url, conditions, callback)` | GET/POST, 일반/렌더링/JSON/FormData 요청 객체를 생성 |
| `set_requests(collect_info, callback)` | URL 목록을 생성하고 요청을 yield |
| `get_result(collect_info, target, _items)` | HTML(XPath)/JSON/XML에서 데이터를 추출하여 딕셔너리 리스트로 반환 |
| `extract_data_from_root(root, _items)` | XPath 셀렉터 기준으로 컬럼별 값을 추출하고 행 단위로 재조합 |
| `set_item_loader(response, collect_info, data)` | Scrapy Item에 수집 결과를 패킹 |
| `get_response_status(response)` | 응답 정보(URL, IP, UA, 쿠키, 레이턴시)를 딕셔너리로 정리 |
| `set_chrome_webdriver(headless)` | Selenium Chrome 드라이버를 초기화 |
| `run_login(driver, seq_no, login_info)` | 사이트별 Selenium 로그인 자동화 |

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
| `sample.py` | — | 샘플/참조용 Spider |

모든 Spider는 `engine.get_scrapy_request()`로 요청을 생성하고 `engine.set_item_loader()`로 결과를 패킹하는 동일한 구조를 따릅니다.

---

### 파이프라인 (`pipelines.py`)

Scrapy Item이 Spider에서 나온 뒤 거치는 후처리 단계.

| 클래스 | 역할 |
|---|---|
| `LoadItemPipeline` | 수집 결과를 `RESULT_INFO:` 형식으로 stdout에 출력 → `MultiprocessWorker`가 수신 |

현재 유일한 파이프라인. 미사용이던 `DonasPipeline`·`CsvExportPipeline`·`MongoDBPipeline`은
PR #8에서 제거됨 (이슈 ④ 참고). GUI의 DB 내보내기 UI는 파이프라인에 연결되어 있지 않음.

---

### 데이터 정제 (`preprocess.py`)

수집된 raw 데이터를 정제하는 로직 전담 모듈.

- **`DataRefiner`**: 6가지 정제 규칙을 순서대로 적용합니다.
  1. `remove_duplicate`: 중복 행 제거
  2. `remove_null_row`: null 포함 행 제거
  3. `fill_null`: null → `"—"` 치환
  4. `trim_whitespace`: 문자열 앞뒤 공백 제거
  5. `drop_columns`: 지정 컬럼 제외
  6. `cast_numeric`: 문자열 숫자 → int/float 변환

- **`RefineStats`**: 정제 결과 통계(원본 행 수, 정제 후 행 수, 제거 행 수, 치환 값 수)를 담는 dataclass.

---

### 설정 및 상태 관리

#### `conf.py`
앱 전체에서 데이터를 공유하는 두 개의 싱글턴 클래스.

- **`DataStore`**: 수집된 행(`_rows`), URL 맵(`_url_map_list`), 세션 이력(`_sessions`), 스케줄(`_schedules`)을 메모리에 보관합니다. 메인 프로세스에서만 유효합니다.

- **`BlueprintStorage`**: `request_info.json`을 로드하여 수집 청사진을 관리합니다. 최초 1회 초기화 후 `reload()`로 갱신할 수 있습니다.

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
- `DOWNLOADER_MIDDLEWARES`: 프록시, User-Agent 랜덤화, 레이턴시 추적, Selenium 실행 순서로 구성

#### `middlewares.py`
Scrapy 다운로더/스파이더 미들웨어 모음.

| 클래스 | 역할 |
|---|---|
| `RandomUserAgentMiddleware` | 요청마다 User-Agent를 랜덤 교체 |
| `RandomCookieMiddleware` | 쿠키를 랜덤 설정 (⚠️ 반환값 이슈 — §7 이슈 ③ 참고) |
| `RateLimitedProxyMiddleware` | IP 로테이션 및 분당 요청 수 제한 |
| `LatencyTrackingMiddleware` | 요청~응답 구간 레이턴시를 측정하여 `meta["pure_latency"]`에 저장 |
| `DelaySchedulerMiddleware` | 스케줄러 레벨 딜레이 적용 (⚠️ 미로드 — §7 이슈 ⑤ 참고) |

---

### 유틸리티

#### `utility.py`
프로젝트 전반에서 사용하는 범용 함수 모음.

| 함수 | 역할 |
|---|---|
| `resource_path()` | `.py` / `.exe` 환경 모두에서 프로젝트 루트 경로 반환 |
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

#### `frames_tmp.py`
UI 레이아웃 프로토타이핑용 임시 파일 (5,796줄). **git 추적 중 — 정리 대상 (§5 참고)**.

---

### 환경 설정 패키지 (`env/`)

| 파일 | 역할 |
|---|---|
| `config.py` | `database.ini` 파일을 파싱하여 DB 접속 정보를 딕셔너리로 반환 |
| `check_ini_section.py` | `.ini` 파일의 섹션 목록을 확인 |
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
  "auth": false,
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

> ⚠️ `spiders` 키는 `conditions` 안이 아니라 **최상위**에 있어야 실제 코드와 일치합니다 (예시는 통일 필요, §6 참고).

---

## 6. 의존성 요약

| 라이브러리 | 용도 |
|---|---|
| `Scrapy` | 비동기 웹 크롤링 엔진 |
| `PyQt6` | 데스크톱 GUI 프레임워크 |
| `scrapy-selenium` / `selenium` | JavaScript 렌더링 페이지 수집 |
| `webdriver-manager` | Chrome 드라이버 자동 설치 |
| `lxml` / `parsel` | HTML/XML 파싱 |
| `pymongo` | MongoDB 연결 |
| `mysqlclient` / `PyMySQL` | MySQL 연결 |
| `psycopg2` | PostgreSQL 연결 |
| `SQLAlchemy` | ORM (DB 추상화) |
| `furl` | URL 파싱/조작 |
| `python-dotenv` | 환경 변수 로드 |
| `pyinstaller` | 실행 파일(.exe) 빌드 |

---

## 7. 진행상황 및 이슈 (감사 이력)

### 7-1. 발견된 이슈 (심각도순, 2026-07-05 기준 재확인)

| # | 이슈 | 위치 | 상태 |
|---|---|---|---|
| ① | **리다이렉트 시 수집 결과 전량 skip → total=0** | `worker.py` / `engine.py` | ✅ **해결** (`d469277`) |
| ② | 프록시 활성 시 즉시 AttributeError — 설정 키 불일치로 GUI 경로에서는 프록시 자체가 조용히 무시되고 있었음 | `middlewares.py`, `worker.py`, `customized_settings.py` | ✅ **해결** (PR #5) |
| ③ | 쿠키 랜덤 미들웨어가 이미 쿠키가 있으면 dict를 반환 (미들웨어 규약 위반) | `middlewares.py:349` (`if request.cookies: return request.cookies`) | ⬜ 미해결 |
| ④ | MongoDBPipeline 실행 불가 — `db_conn`/`MongoClient` import 누락으로 로드 즉시 `NameError` | `pipelines.py`, `settings.py` | ✅ **해결** (PR #8 — 어떤 정상 경로에서도 미사용이라 복구 대신 **제거**, 기본 `ITEM_PIPELINES`를 `LoadItemPipeline`으로 교체) |
| ⑤ | `DelaySchedulerMiddleware`는 Scrapy에 존재하지 않는 설정 키(`SCHEDULER_MIDDLEWARES`)에 등록되어 로드되지 않음. 내부도 제거된 API(`engine.schedule`)·`DontCloseSpider` 오용 | `settings.py:84`, `middlewares.py` | ⬜ 미해결 |
| ⑥ | `get_response_status()` 취약 필드 접근 — `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 **결과 조용히 유실**, 비표준 상태코드에서 `HTTPStatus()` ValueError | `engine.py:161,165` | ⬜ 미해결 |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 → `process.crawl({})` | `engine.py:67-74` | ⬜ 미해결 |
| ⑧ | **`/text()` XPath 추출 깨짐** — `extract_data_from_root()`가 텍스트 노드에 `node.xpath(".")`를 호출. 일반 문자열 텍스트 노드는 빈 값 반환(**조용한 유실**), `"100"` 등 JSON 파싱 가능한 텍스트는 parsel 1.11이 셀렉터를 json 타입으로 판정해 ValueError → **해당 페이지 추출 전체 실패**. 요소 XPath(`.//h2`)는 정상 (PR #8 검증 중 실측 발견) | `engine.py:299` | ⬜ 미해결 |

### 문서 vs 코드 불일치

- 위 §5의 request_info.json 예시는 `spiders` 키를 `conditions` 안에 두지만
  실제 파일·코드는 **최상위** 키 사용 (실제 쪽이 정답, 예시 수정 필요)
- 위 §5 예시의 `items` XPath가 `.//h2/text()` 형태인데, 현재 엔진 코드에서
  `/text()` XPath는 이슈 ⑧로 인해 정상 동작하지 않음 — 요소 XPath(`.//h2`)가
  실제 동작 형태 (⑧ 수정 방향 결정 시 예시도 함께 정리)
- `LoadItemPipeline` 등의 f-string 중첩 따옴표 문법은 **Python 3.12+ 전용** —
  PyInstaller 빌드 환경도 3.12+ 필수

### 보안·운영 관찰

- **`env/database.ini`에 실제 API 키 4개 평문 존재** (공공데이터포털, 한국은행,
  OpenDART, IROS). git 미추적 상태이지만, 그 이유가 Python 템플릿 `.gitignore`의
  `env/` 규칙(가상환경용)에 **우연히** 걸렸기 때문 → `.gitignore`에 명시적 등록
  또는 `.env` 이관 권장 (2026-07-05 재확인: 여전히 명시적 등록 안 됨)
- `ROBOTSTXT_OBEY=True`인 반면 봇 UA 행세·랜덤 쿠키·프록시 로테이션 미들웨어가
  공존 — 사용 정책 정리 필요
- **테스트 코드 0개** — 검증용으로 작성했던 미들웨어 테스트 8건은 검증 완료 후
  정책에 따라 저장소에서 제거됨 (PR #6). `preprocess.DataRefiner`,
  `utility.generate_combined_urls`가 테스트 도입 최적 지점
- `frames_tmp.py`(5,796줄)가 git 추적 중 — 가이드 스스로 임시 파일로 명시, 정리 대상 (2026-07-05 재확인: 여전히 추적 중)
- Scrapy 2.16으로 올리면 sync `start_requests()`가 **에러 없이 무시되어 0건 수집**
  (검증 중 실측) — 업그레이드 시 async `start()` 마이그레이션 필수

### 7-2. 완료된 작업

#### 리다이렉트 URL 불일치 수정 (`d469277`, 12줄)

- **원인**: `worker._handle_line()`이 응답의 최종 URL(`response.url`)로 사전 생성한
  url_list를 대조 → 리다이렉트 사이트는 최종 URL ≠ 요청 URL이라 모든 결과가
  "URL 불일치"로 skip되어 total=0
- **수정**:
  - `engine.get_response_status()`: `resp_info`에 `req_url`(리다이렉트 전 최초 요청
    URL, `response.meta["redirect_urls"][0]`) 추가
  - `worker._handle_line()`: 대조 기준을 `req_url`로 변경 (없으면 기존 `url` fallback)
- **검증**:
  - 로컬 302 리다이렉트 서버 + `run_spider` 자식 프로세스 e2e —
    수정 전 로직 skip 재현 / 수정 후 정상 수집·데이터 추출 확인 (PASS)
  - Windows 환경 GUI 실행 — 리다이렉트 사이트 실수집 정상 동작 확인

#### 저장소 전체 줄바꿈(LF) 정규화 (`e10073c`, `3edb01a`)

- `.gitattributes(eol=lf)` 도입 이전에 CRLF로 커밋된 20개 파일 일괄 정규화
- `git diff --ignore-cr-at-eol` 기준 **내용 변경 0줄** 검증
- 부수 효과로 겪은 "EOL 림보"(CRLF blob + LF 규칙 → 영구 modified 유령 상태)의
  원인·진단·해법을 GIT_GUIDE에 문서화. main/develop 모두 LF blob을 가리키므로
  **재발 없음**

#### Git 운영 체계 정비 (PR #2, #3)

- GitHub ruleset("PR 필수")과 가이드의 직접 머지 플로우 충돌 발견
  (직접 푸시 시 owner bypass 경고 발생)
- GIT_GUIDE를 **PR 기반 플로우로 개정**: `gh pr create` → `gh pr merge --admin`
  (1인 저장소는 자기 승인 불가로 `--admin` 필요)
- EOL 노이즈 진단법(`git diff --ignore-cr-at-eol`, `git add --renormalize`) 추가

#### 릴리스 및 멀티환경 동기화 (PR #4)

- `develop → main` 릴리스 PR 머지: main = `0155bfa`
- WSL / Windows 클론 모두 main·develop 동기화 완료, 양쪽 working tree clean 확인

#### 프록시 rate limit 미들웨어 수정 (이슈 ②, PR #5)

- **원인 (수정 과정에서 2건 추가 발견)**:
  1. `middlewares.py:213`이 주석 처리된 클래스 속성 `REQUESTS_PER_MINUTE` 참조
     → 프록시 목록이 로드되면 첫 요청부터 AttributeError
  2. **설정 키 불일치** — worker는 `PROXY_REQ_INFO`(읽는 코드 없음)에 저장,
     미들웨어는 최상위 `ip_list`/`allow_ip_cnts` 조회 → GUI 경로에서는
     프록시 목록이 항상 빈 리스트라 **프록시가 조용히 무시**됨 (①에 도달조차 못 함)
  3. **형식 불일치** — GUI 프록시 행은 dict(host/port/protocol/enabled)인데
     미들웨어는 그대로 `meta['proxy']`에 할당 (Scrapy는 URL 문자열 요구)
- **수정**:
  - `customized_settings.set_ip_settings()`: dict 행 → `"http://host:port"` URL
    변환, `enabled=False` 행 제외
  - `worker.set_scrapy_settings()`: `PROXY_REQ_INFO` 대신 미들웨어가 읽는
    `ip_list`/`allow_ip_cnts` 키로 직접 주입
  - `RateLimitedProxyMiddleware.process_request()`: `self.req_per_minute` 사용,
    `allow_ip_cnts ≤ 0`은 무제한 취급, "랜덤 1개 선택 후 초과 시 폐기" →
    **여유 있는 프록시를 무작위 순회로 선택**(전부 소진 시에만 IgnoreRequest).
    무의미해진 `delay_until` 재스케줄 유도 코드 제거 (⑤ 재설계는 백로그 유지)
- **검증**:
  - 유닛 테스트 8건 작성·전건 PASS — URL 변환·비활성 행 제외, 제한 초과 시
    IgnoreRequest, 프록시 간 분산, 0=무제한, 60초 윈도우 만료 후 재허용
    (검증용 임시 산출물로, 검증 완료 후 저장소에서 제거 — PR #6)
  - e2e: 로컬 대상 서버 + 요청 카운트 포워드 프록시 + `run_spider` 자식 프로세스 —
    수정 전(git stash) 프록시 경유 0건 재현 / 수정 후 전 요청 프록시 경유 + 수집 성공
  - WSL 테스트 환경: 저장소 `.venv`는 Windows용이라 uv로 별도 구성 (Python 3.12)

#### 문서 통합 (PR #7)

- `PROJECT_GUIDE.md`(구조) + `PROJECT_AUDIT_REPORT.md`(진행상황)를
  본 문서(`PROJECT_REPORT.md`)로 통합, 원본 삭제, `CLAUDE.md` 참조 갱신

#### 미사용 파이프라인 제거 및 기본 파이프라인 교체 (이슈 ④, PR #8)

- **방향**: import 복구(a) 대신 **제거(b)** 선택 — MongoDBPipeline은 GUI의 어떤
  정상 경로에서도 미사용(GUI가 항상 `LoadItemPipeline`으로 교체)이었고, GUI의
  DB 내보내기 UI는 파이프라인에 연결되어 있지 않음
- **수정** (7파일, +1/−283줄):
  - `pipelines.py`: `LoadItemPipeline`만 유지. `DonasPipeline`(템플릿 잔재),
    `CsvExportPipeline`(주석 참조만 존재), `MongoDBPipeline`(로드 즉시 NameError),
    주석 처리된 MongoDB 구버전 초안(79줄), 불필요해진 import 제거
  - `settings.py`: 기본 `ITEM_PIPELINES` → `LoadItemPipeline` (CLI 실행·예외 삼킴
    연쇄의 크래시 경로 자체 제거). 정의된 적 없는 `PostgreSQLPipeline` 주석 제거
  - `customized_settings.py`: 호출처 없는 `set_item_pipelines()` 제거
  - spiders 4종: 삭제된 `CsvExportPipeline`을 가리키던 주석 제거
- **검증** (WSL uv venv, Python 3.12):
  - 기본 설정 크롤(CLI 경로 상당) e2e — 수정 전(develop) `NameError: db_conn`
    재현 / 수정 후 `LoadItemPipeline` 로드 + `RESULT_INFO` 정상 추출
  - GUI 경로 e2e(`multiprocessing` + `run_spider`) — `EXECUTOR_STATUS: SUCCESS`
  - 검증 중 이슈 ⑧(`/text()` XPath 추출 깨짐) 신규 발견 → 백로그 등록

### 현재 브랜치 상태 (2026-07-05 기준)

| 브랜치 | 커밋 | WSL | Windows |
|---|---|---|---|
| `main` | `0155bfa` (PR #4) | ✅ | ✅ |
| `develop` | `0bbf496` (PR #8, main보다 앞섬) | ✅ | 확인 필요 |

미결 사항: Windows 클론의 `git-setup-windows.ps1`이 untracked —
저장소 포함(권장, `git-setup-wsl.sh`의 짝) 또는 `.gitignore` 등록 중 선택 필요.
`develop`(PR #5~#8 반영)의 **Windows GUI 검증 후 `main` 릴리스 PR** 대기 중.

---

## 8. 남은 작업 백로그 (권장 우선순위)

1. **⑧ `/text()` XPath 추출 깨짐** (`engine.py:299`) — 텍스트 노드에
   `node.xpath(".")` 호출: 일반 문자열은 빈 값(조용한 유실), JSON 파싱 가능한
   텍스트(`"100"` 등)는 parsel json 타입 판정 → ValueError로 페이지 추출 전체
   실패. 수정 방향: 텍스트 노드 셀렉터는 `node.get()`을 그대로 쓰도록 분기
   (요소 노드만 `xpath(".")` + 태그 제거 경로). §5 예시 JSON의 `/text()` 표기도
   수정 방향에 맞춰 함께 정리
2. **⑥ `get_response_status()` 방어 코드** — Selenium 응답·비표준 상태코드에서
   결과가 조용히 유실되는 문제
3. **③ 쿠키 미들웨어 반환값** — `return None`으로 1줄 수정
4. **⑤ `DelaySchedulerMiddleware` 정리/재설계** — 존재하지 않는 설정 키에 등록되어
   미로드, 내부도 제거된 API 사용. rate limit 초과 요청의 재시도(지연 재예약)
   설계와 묶어 재검토 (현재는 전 프록시 소진 시 IgnoreRequest로 폐기)
5. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
6. **`worker.set_scrapy_settings()` 예외 삼킴 개선** — 핵심 설정(`ITEM_PIPELINES`
   교체 등)은 try 밖으로 옮기고, try는 실패해도 진행 가능한 프록시 주입으로 한정
   (④는 해결됐지만 예외 삼킴 구조 자체는 남아 있음)
7. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
8. **정리**: `frames_tmp.py` 제거 여부 결정, 위 §5 예시 JSON 수정,
   미구현 스파이더 타입(⑦) 명시적 예외 처리, GUI 경로에서
   `set_downloader_middlewares()`가 `DOWNLOADER_MIDDLEWARES`를 통째로 교체해
   `LatencyTrackingMiddleware`·`SeleniumMiddleware`가 빠지는 문제 검토,
   GUI DB 내보내기(UI만 존재)의 파이프라인 연결 여부 결정
9. **릴리스**: Windows GUI에서 `develop`(PR #5~#8) 검증 후 `develop → main` 릴리스 PR
