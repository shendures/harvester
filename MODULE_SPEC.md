# Harvest — 모듈 기능서 (Module Functional Specification)

> 이 문서는 Harvest 크롤링 프로그램의 핵심 모듈이 각각 어떤 기능을 담당하며 서로
> 어떻게 상호작용하는지를 정리한 기능서입니다. 아키텍처/파일구조 스냅샷은
> `guidelines/PROJECT_REPORT.md`에서 별도 관리되므로 중복 없이 모듈 단위 책임과
> 모듈 간 의존·연동 관계에 집중합니다. 상세 요약표는 `MODULE_SPEC_SUMMARY.md` 참고.

- **작성 기준일**: 2026-09-14 (코드를 직접 읽고 확인한 내용 기준)

---

## 1. 문서 개요

**목적**: 특정 기능을 수정하려는 개발자가 어떤 모듈을 건드려야 하는지, 그 수정이
어떤 다른 모듈에 영향을 줄 수 있는지 빠르게 파악하도록 돕습니다.

**범위**: `layout/*`, `trigger/*`, `scraper/*`, `conf.py`, `create_request_info.py`,
`customized_settings.py`, `db_conn.py`, `engine.py`, `generator_conditions.html`,
`main.py`, `preprocess.py`, `style.py`, `utility.py`, `worker.py`

**표기 안내**: 요청 목록의 `items.py`/`middlewares.py`/`pipelines.py`는 저장소
루트가 아니라 `scraper/` 패키지 내부 파일이며(3.7절에서 함께 다룸), `customized_
setting.py`→`customized_settings.py`, `generator_condition.html`→`generator_
conditions.html`이 실제 파일명(모두 복수형)입니다.

---

## 2. 전체 아키텍처 요약

PyQt6 GUI와 Scrapy 크롤링 엔진을 결합한 데스크톱 앱으로, GUI와 크롤러는 서로 다른
프로세스에서 실행되며 표준출력(stdout)과 `multiprocessing.Queue`로만 통신합니다.

```
[진입점] main.py → layout/ (Single/Multi 선택은 request_info.json 블루프린트 개수)

[GUI 계층 — 같은 프로세스, 항상 layout → trigger → style 방향]
  layout/*(위젯 트리) → trigger/*(동작 Mixin, 다중상속) → style.py(테마 QSS)

[실행 브리지 — GUI 프로세스가 별도 OS 프로세스를 기동]
  trigger/main_window.py → worker.py:MultiprocessWorker(QThread)
    → multiprocessing.Process(run_spider)  ← 여기서부터 별도 프로세스

[크롤링 프로세스 — conf.DataStore에 직접 접근 불가]
  worker.run_spider() → engine.get_spider() → scraper/spiders/*.py
    ├── glean.py(URL 목록 생성)
    ├── engine.py(요청 생성·응답 추출·로그인)
    └── scraper/pipelines.py("RESULT_INFO:{json}"를 stdout 출력)

[프로세스 간 통신]
  child stdout → QueueWriter → Queue → MultiprocessWorker._handle_line()
    → conf.DataStore 갱신 + Qt 시그널(new_row/progress) emit → GUI 갱신

[설정·상태 — GUI 프로세스 전용]
  conf.py: DataStore/BlueprintStorage/CustomModuleStorage(싱글턴)
  customized_settings.py(기본값 팩토리) · request_info.json ⇄ BlueprintStorage
  {render,login,refine}/{seq_no}.py ⇄ CustomModuleStorage

[수집 후 처리] trigger/monitor.py → preprocess.DataRefiner → db_conn.py 또는 파일 저장

[블루프린트 저작 — 앱 실행과 무관한 오프라인 트랙]
  generator_conditions.html(브라우저) → tb_blueprint(DB)
    → create_request_info.py(수동 실행) → request_info.json 재생성
```

**핵심 설계 원칙**: ① GUI(`layout/trigger`)는 크롤링(`scraper/engine`)을 직접
참조하지 않고 `worker.py` 하나로만 연결됩니다. ② `conf.DataStore`는 GUI 프로세스
전용이며 자식 프로세스와 상태를 공유하지 않습니다. ③ `utility.py`는 내부
의존성이 없는 최하위 공용 모듈로 거의 모든 계층이 참조합니다.

---

## 3. 모듈별 상세 기능

### 3.1 진입점 — `main.py`

`QApplication` 생성 → 테마/아이콘 적용 → `QLocalServer`로 중복 실행 방지 →
`conf.BlueprintStorage().list_seq_nos()`로 블루프린트 개수 확인해 `layout.
MainWindowSingle`(1개) 또는 `layout.multi.MainWindowMulti`(2개 이상) 생성 → 표시.

**의존**: `layout`, `layout.multi`, `conf`, `style`, `utility` · **피의존**: 없음(엔트리포인트).

### 3.2 GUI 레이아웃 — `layout/` 패키지

QWidget 트리 구성만 담당(동작 로직 없음), 같은 이름의 `trigger/*` Mixin과
다중상속되어 동작을 위임받습니다. 블루프린트 1개면 `single/*`, 2개 이상이면
`multi/*`(대부분 `single`을 상속해 훅만 오버라이드)를 사용합니다.

| 구분 | 파일 | 클래스 | 기능 |
|---|---|---|---|
| 공용 | `common.py` | — | single/multi 공유 테마·헬퍼 허브(인증 필요 여부 판정 등) |
| 공용 | `auth.py` | `AuthManagerPage` | 인증 관리 화면 |
| 공용 | `session.py` | `SessionSettingsPage` | 세션/프록시 설정 화면 |
| 공용 | `scheduler.py` | `SchedulerPage` | 스케줄 목록 + 카운트다운 카드 |
| 공용 | `statistics.py`/`charts.py` | `StatisticsPage` 등 | 통계 대시보드 + 커스텀 차트 |
| 공용 | `tray.py` | `TrayManager` | 시스템 트레이 아이콘/메뉴 |
| single | `main_window.py` | `MainWindowSingle` | 사이드바+툴바+스택 위젯 조립 |
| single | `sidebar.py`/`toolbar.py` | `SidebarSingle`/`GlobalToolbarSingle` | 내비게이션 / 상단 툴바(시작·중지) |
| single | `common.py` | `ActiveBlueprintMixin` | 활성 블루프린트 조회(Multi 확장 지점) |
| single | `dashboard.py` | `DashboardPageSingle` | 진행상태 + 수집설정 + 실시간 모니터링 |
| single | `monitor.py` | `MonitorPageSingle` | 원본/정제규칙/정제결과/비교 4탭 |
| multi | `main_window.py` | `MainWindowMulti` | 블루프린트별 페이지 번들 지연 생성·관리 |
| multi | `sidebar.py`/`toolbar.py` | `*Multi(*Single)` | 표시 항목 재정의(인증관리 제거 등) |
| multi | `dashboard.py`/`monitor.py` | `*Multi(*Single)` | single 상속, 슬롯 배치만 조정 |
| multi | `monitor_target_list.py` | `MonitorTargetListPage` | 경량 블루프린트 목록(정제 화면용) |
| multi | `blueprint_list.py` | `BlueprintListPage` | 수집 목록 테이블(행별 실행/설정/선택) |

**의존**: `trigger/*`, `style.py`, `conf.py` · **피의존**: `main.py`만 최상위 import.
**주의**: `scraper/*`·`engine.py`·`worker.py`는 직접 참조하지 않습니다(`trigger/main_window.py` 뒤에 캡슐화).

### 3.3 GUI 이벤트/트리거 — `trigger/` 패키지

각 화면의 "동작 메서드"만 모은 Mixin 패키지로, GUI와 `conf`/`worker`/`engine`/
`db_conn`/`preprocess` 등 백엔드를 잇는 접점 역할도 겸합니다.

| 파일 | 클래스 | 기능 |
|---|---|---|
| `common.py` | (다수 함수) | 공용 허브 — task 설정 적용, 블루프린트 검증(`engine`), 추출/DB 설정 UI 빌더 |
| `auth.py` | `AuthManagerPageTriggers` | 자격증명 추가/삭제/내보내기 |
| `dashboard.py` | `DashboardPageTriggers` | 실시간 행 추가, 세션 통계, CSV 내보내기 |
| `log_viewer.py` | `LogViewerDialog` | 로그 뷰어(레벨 필터 + 키워드 검색) |
| `main_window.py` | `MainWindowTriggersSingle/Multi` | **오케스트레이션 핵심** — 워커 실행, 완료 후 정제·저장·스케줄 재무장 총괄 |
| `monitor.py` | `MonitorPageTriggers` | 정제 실행(`preprocess.DataRefiner`), 파일/DB 저장(`db_conn.save_db`) |
| `scheduler.py` | `SchedulerPageTriggers` | 스케줄 등록/수정, QTimer 카운트다운, `schedules.json` 영속화 |
| `session.py` | `SessionSettingsPageTriggers` | 프록시 추가/삭제/Import, 병렬 헬스체크 |
| `statistics.py` | `StatisticsPageTriggers` | KPI·분포·세션 이력 재계산 |
| `toolbar.py` | `GlobalToolbarTriggers` | 시작/중지 흐름, 수집설정 영속화 후 실행 요청 |

**의존**: `style.py`, `conf.py`, `worker.py`(main_window만), `engine.py`·`db_conn.py`·`preprocess.py`(common/monitor 등), `customized_settings.py`·`utility.py`(monitor·scheduler).
**피의존**: `layout/*`의 대응 Page 클래스 전부(다중상속).

### 3.4 테마·공용 위젯 — `style.py`

앱의 다크 테마 QSS와 재사용 위젯을 정의하는 유일한 소스입니다(비즈니스 로직
없음). `THEME`(팔레트), `EqualSpacingTable`(엑셀형 표), `Parts`(위젯 빌더),
`build_refine_rule_rows`(정제 규칙 UI, monitor·scheduler 공유) 등을 제공합니다.

**의존**: `utility.py`만(아이콘 경로) · **피의존**: `layout/*` 대부분, `trigger/*` 다수, `main.py`.

### 3.5 수집 실행 브리지 — `worker.py`

GUI(Qt) 스레드와 Scrapy 크롤링(별도 OS 프로세스)을 잇는 다리입니다. Scrapy의
Twisted 리액터는 같은 프로세스에서 재시작할 수 없어 매 크롤링마다 새 프로세스를
띄웁니다. `MultiprocessWorker(QThread)`가 `multiprocessing.Process(run_spider)`를
기동하고 큐를 폴링하며 `progress`/`new_row`/`finished` 시그널을 emit합니다.
`set_scrapy_settings()`가 `scraper.settings` 위에 `customized_settings.py`의
잡별 오버라이드(프록시, 미들웨어)를 적용합니다.

**의존**: `utility.py`, `engine.py`(`get_spider`만), `customized_settings.py`, `conf.DataStore`.
**피의존**: `trigger/main_window.py`가 유일한 호출자 — 전체 GUI는 이 클래스로만 크롤링을 시작합니다.

### 3.6 크롤링 유틸리티 — `engine.py`, `glean.py`

`engine.py`는 스파이더 자체가 아니라 **스파이더 공용 라이브러리**입니다.

| 함수 | 기능 |
|---|---|
| `get_spider(request_info)` | 스파이더 모드에 따라 5개 클래스 중 하나 반환 |
| `validate_blueprint_conditions()` | 실행 전 필수 `conditions` 키 검증 |
| `get_scrapy_request()` | `Request`/`FormRequest`/`JsonRequest` 생성 |
| `set_chrome_webdriver()`, `perform_login/logout()` | Selenium 드라이버·로그인 플로우 |
| `get_result()`/`set_item_loader()` | 데이터 추출 → `DonasItem`으로 적재 |

`glean.py`는 `utility.generate_combined_urls()`로 URL 목록을 만드는 1-함수 모듈입니다.

**의존**: 둘 다 `utility.py`; `engine.py`는 추가로 `conf.py`, `scraper.items`, `scraper.spiders.*`(전체 import, 순환참조 방지를 위해 `base.py`는 이를 지연 import).
**피의존**: `worker.py`(`get_spider`), 5개 스파이더 전부, `trigger/common.py`(검증 호출).

### 3.7 Scrapy 패키지 — `scraper/`

Scrapy가 동적으로 로드하는 구성요소를 모은 패키지입니다. `__init__.py`는
독스트링만 있고 하위 모듈을 재-export하지 않습니다(`engine.py`와의 순환참조 방지).

| 파일 | 클래스/함수 | 기능 |
|---|---|---|
| `settings.py` | — | Scrapy 기본 설정(동시요청 수, 미들웨어/파이프라인 등록) |
| `items.py` | `DonasItem`, `DonasItemLoader` | 스키마 사전선언 없이 임의 키를 담는 동적 Item |
| `middlewares.py` | `LatencyTrackingMiddleware`, `RateLimitedProxyMiddleware`, `DelaySchedulerMiddleware`, `RandomUserAgentMiddleware`, `RandomCookieMiddleware` | 지연시간 측정, 프록시 레이트리밋+재스케줄, UA/쿠키 랜덤화 |
| `pipelines.py` | `LoadItemPipeline` | 유일한 파이프라인 — 결과를 `RESULT_INFO:{json}`로 stdout 출력만 함 |
| `spiders/base.py` | `BaseExtractorSpider` | 공통 베이스(URL 목록→요청 생성), `name` 없어 단독 실행 불가 |
| `spiders/spihtml.py` | `HtmlExtractorSpider` | 정적 HTML XPath 추출 |
| `spiders/spijson.py` | `JsonExtractorSpider` | JSON API 경로 기반 추출 |
| `spiders/spixml.py` | `XmlExtractorSpider` | XML(`xmltodict`) 추출 |
| `spiders/spidetail.py` | `DetailExtractorSpider` | 목록→상세 페이지 2단계 크롤링 |
| `spiders/spirenderer.py` | `HtmlSeleniumSpider` | Selenium 렌더링 수집, 로그인/커스텀 렌더 훅 지원 |

**의존**: 모든 스파이더가 `engine.py`·`glean.py`·`utility.py`; `spirenderer.py`는 추가로 `conf.py`.
**피의존**: `engine.py`만 직접 import. `worker.py`/`customized_settings.py`는 파이프라인·미들웨어를 Scrapy 설정 딕셔너리 안 **문자열 경로**로만 참조(동적 로드).
**주의**: `layout/*`, `trigger/*`는 `scraper/*`를 전혀 import하지 않습니다.

### 3.8 설정·상태 관리 — `conf.py`, `customized_settings.py`

`conf.py`는 이름과 달리 정적 상수가 아니라 앱의 **영속 상태 싱글턴 모음**입니다.

| 클래스 | 기능 |
|---|---|
| `DataStore` | 수집 결과·URL 통계·세션 요약 보관(`stats_history.json` 영속화). **GUI 프로세스 전용** |
| `BlueprintStorage` | `request_info.json` 로드/저장, `seq_no` 검증, `read()`/`set_active()`/`update_settings()` |
| `CustomModuleStorage` | 블루프린트별 `render/login/refine` 커스텀 스크립트 시드·동적 로드 |

`customized_settings.py`는 GUI·worker가 공유하는 **기본값 팩토리**로, 요청/작업/
출력/스케줄 설정의 기본 구조와 프록시·미들웨어 설정 변환(`set_ip_settings`,
`set_downloader_middlewares`)을 제공합니다.

**의존**: `conf.py`→`customized_settings.py`,`utility.py`; `customized_settings.py`→없음.
**피의존**: `conf.py`는 거의 전 계층, `customized_settings.py`는 `conf.py`·`worker.py`·`create_request_info.py`·`layout/single/*`·`trigger/monitor.py`·`scheduler.py`.

### 3.9 데이터 정제 — `preprocess.py`

수집 완료 후 **GUI 프로세스에서** 원시 데이터를 정제하는 엔진입니다.
`DataRefiner`가 정해진 순서로 규칙을 적용합니다: ①null 행 제거 → ②커스텀 규칙
→ ③공백 정리 → ④중복 제거 → ⑤컬럼 삭제 → ⑥null 채움 → ⑦숫자형 변환(원본은
불변, 통계는 `RefineStats`로 반환).

**의존**: `conf.py`(커스텀 규칙 로드)만 · **피의존**: `trigger/common.py`(규칙 UI 초기화), `trigger/monitor.py`(`DataRefiner` 실행).

### 3.10 데이터베이스 연동 — `db_conn.py`

PostgreSQL/MySQL/MongoDB 3종을 지원하는 순수 DB 접근 계층입니다(Qt/Scrapy 의존
없음). `_check_db_connect_info()`(연결 검증+실패 원인 분류), `read_db_data()`,
`save_db(mode=append|overwrite)`를 제공합니다.

**의존**: `sqlalchemy`, `pymongo`(프로젝트 내부 모듈 의존 없음) · **피의존**: `create_request_info.py`, `trigger/common.py`·`monitor.py`(출력 설정 UI).

### 3.11 공용 유틸리티 — `utility.py`

프로젝트 내부 의존성이 전혀 없는 최하위 헬퍼 모음입니다. `resource_path()`/
`data_dir()`(경로), `transform_to_json()`, `generate_combined_urls()`(`${page:...}`/
`${keywords:...}` 템플릿 전개), `get_target()`(중첩 데이터 탐색)을 제공합니다.

**의존**: 없음(표준 라이브러리만) · **피의존**: 거의 모든 모듈(`conf`, `engine`, `glean`, `worker`, `main`, `style`, 다수 `layout/*`·`trigger/*`).

### 3.12 블루프린트 저작 도구 — `generator_conditions.html`, `create_request_info.py`

앱 실행 흐름과 무관한 **오프라인 트랙**입니다 — 런타임에 `main.py`/`worker.py`/
`engine.py`가 호출하지 않습니다.

- **`generator_conditions.html`**: 서버 없는 순수 브라우저 HTML+JS 도구. 운영자가
  직접 열어 수집 조건(`conditions` JSON)을 폼으로 생성해 DB에 수동 반영합니다.
  파이썬 코드와 완전히 분리되어 있습니다.
- **`create_request_info.py`**: `tb_blueprint`(활성 블루프린트)를 조회해
  `request_info.json`을 재생성하는 수동 실행 스크립트. `map_blueprints_to_
  request_info()`가 DB row를 `customized_settings.get_request_settings()` 스켈레톤에
  채웁니다.

**의존**(후자): `db_conn.py`, `utility.py`, `customized_settings.py` · **피의존**: `build_manifest.py`(쿼리·매핑 재사용). 앱 런타임에서는 미호출.

---

## 4. 모듈 간 상호작용

### 4.1 의존관계 표

| 모듈 | 직접 의존하는 모듈 |
|---|---|
| `main.py` | `layout`, `layout.multi`, `conf`, `style`, `utility` |
| `layout/*` | `trigger/*`, `style.py`, `conf.py`, (일부) `customized_settings.py` |
| `trigger/*` | `style.py`, `conf.py`, `worker.py`(main_window), `engine.py`(common), `db_conn.py`·`preprocess.py`(common/monitor), `customized_settings.py`·`utility.py` |
| `style.py` | `utility.py` |
| `worker.py` | `utility.py`, `engine.py`, `customized_settings.py`, `conf.py` |
| `engine.py` | `utility.py`, `conf.py`, `scraper.items`, `scraper.spiders.*` |
| `glean.py` | `utility.py` |
| `scraper/spiders/*` | `engine.py`, `glean.py`, `utility.py`, (renderer만) `conf.py` |
| `scraper/pipelines.py`·`middlewares.py` | 없음(문자열 경로로 동적 로드) |
| `conf.py` | `customized_settings.py`, `utility.py` |
| `customized_settings.py` / `db_conn.py` / `utility.py` | 없음 |
| `preprocess.py` | `conf.py` |
| `create_request_info.py` | `db_conn.py`, `utility.py`, `customized_settings.py` |
| `generator_conditions.html` | 없음(파이썬 코드와 완전 분리) |

### 4.2 대표 흐름

**① GUI 수집 실행 흐름**
1. 시작 버튼 클릭 → `trigger/toolbar.py._actual_start()`가 설정을 `BlueprintStorage`에 저장 후 `start_requested` emit
2. `trigger/main_window.py`가 `worker.MultiprocessWorker` 기동 → 별도 프로세스에서 `run_spider()` 실행
3. `engine.get_spider()`로 스파이더 결정 → `glean.get_grains()`(URL 전개) → `engine.get_scrapy_request()` → 스파이더 `parse()`(`engine.get_result()`)
4. `scraper/pipelines.py`가 `RESULT_INFO:{json}`을 stdout 출력 → `QueueWriter`가 `Queue`로 부모 프로세스에 전달
5. `worker._handle_line()`이 파싱해 `conf.DataStore` 갱신 + `new_row`/`progress` 시그널 emit → `trigger/dashboard.py`가 `layout` 테이블을 실시간 갱신

**② 정제·저장 흐름**
1. 수집 완료(`worker.finished`) → `trigger/main_window.py._on_finished()`
2. `trigger/monitor.py._run_refine()` → `preprocess.DataRefiner`(+커스텀 규칙) 실행 → "정제 결과"/"Before-After" 탭 반영
3. `_extract_result_table()`이 CSV/JSON 파일 또는 `db_conn.save_db()`로 저장(사전 `_check_db_connect_info` 검증)

**③ 블루프린트 저작 흐름(오프라인)**
1. 운영자가 `generator_conditions.html`로 `conditions` JSON 작성 → 수동으로 `tb_blueprint`에 저장
2. `create_request_info.py` 수동 실행 → `db_conn.read_db_data()` 조회 → `request_info.json` 재생성
3. 앱 재시작 시 `conf.BlueprintStorage`가 로드 → `main.py`가 블루프린트 개수로 Single/Multi 결정

---

## 5. 참고

- **아키텍처/파일구조 스냅샷**: `guidelines/PROJECT_REPORT.md`
- **정제 규칙(refine) 서브시스템 심화 문서**: `guidelines/PREPROCESS.md`
- **작업 이력**: `guidelines/HISTORY.md` · **이슈·백로그**: `guidelines/ISSUES.md`
- **모듈 요약표(1장 표)**: `MODULE_SPEC_SUMMARY.md`
