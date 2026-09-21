# DataCrawler v2.0 (Harvest) — 프로젝트 리포트

> 프로젝트 구조·아키텍처 설명 문서. 함께 관리되는 문서: 이슈·백로그 `ISSUES.md` · 진행 이력
> `HISTORY.md` · exe/설치 프로그램 빌드 절차 `BUILD_GUIDE.md` · 모듈별 책임·의존 관계 `../MODULE_SPEC.md`

- **최신 갱신**: 2026-09-19

---

## 1. 프로젝트 개요

**DataCrawler**는 Scrapy 크롤링 엔진과 PyQt6 GUI를 결합한 데스크톱 웹 데이터 수집 애플리케이션입니다.
GUI에서 코드 없이 수집 조건을 설정하고, 실시간 진행 상황을 모니터링하며, 결과를 CSV 또는 DB로
내보낼 수 있습니다.

- **엔진**: Scrapy 2.14 · **UI**: PyQt6 · **형식**: HTML(정적/Selenium 렌더링), JSON, XML
- **출력**: CSV, MongoDB, MySQL, PostgreSQL

| 영역 | 파일 | 규모 |
|---|---|---|
| GUI 레이아웃 | `layout/` 패키지 | 2,680줄 (22개 파일) |
| 이벤트 핸들러 (Mixin, 단일+다중 공용) | `trigger/` 패키지 | 4,667줄 (11개 파일) |
| 테마·공용 위젯·정제 규칙 UI | `style.py` | 881줄 |
| 수집 워커 (QThread+multiprocessing) | `worker.py` | 513줄 |
| 요청 생성·데이터 추출 | `engine.py` | 320줄 |
| Spider 5종 | `scraper/spiders/` | html/html_render/json/xml/detail |
| 데이터 정제 | `preprocess.py` | 358줄 |
| 설정·상태 공유 (싱글턴 3종) | `conf.py` | 437줄 |

---

## 2. 아키텍처 요약

```
GUI 시작 버튼
  → GlobalToolbarTriggers._actual_start()   # blueprint+UI 설정 → task 구성
  → MainWindowSingle._launch_worker()       # MultiprocessWorker(QThread) 시작
  → multiprocessing.Process(run_spider)     # Scrapy 격리 실행
      → CrawlerProcess → scraper/spiders/*.py
      → LoadItemPipeline: "RESULT_INFO:{json}" → stdout → Queue
  → MultiprocessWorker._handle_line()       # 파싱 → 시그널 emit
  → DashboardPageSingle / MonitorPageSingle 실시간 갱신
```

**설정 관리**: `request_info.json`⇄`BlueprintStorage` · `{render,login,refine}/{seq_no}.py`⇄
`CustomModuleStorage` · `customized_settings.py`(기본값) · `scraper/settings.py`(Scrapy 설정) — 모두 싱글턴.

**설계 강점**: 프로세스 경계(`DataStore`는 메인 프로세스 전용)가 명시적, 큐 드레인 로직이 멀티프로세스
함정을 제대로 처리, `preprocess.DataRefiner`의 원본 불변·통계 추적 품질이 높음.

---

## 3. 파일별 상세 설명

**`main.py`**: PyQt6 앱 초기화 → `MainWindowSingle` 시작. `QLocalServer`로 중복 실행 방지, Windows
작업표시줄 아이콘 등록 처리.

### `layout/` 패키지 (2,680줄, 22개 파일)
GUI 레이아웃·페이지 정의(로직 없음, 같은 이름의 `trigger/*` Mixin과 다중상속).

| 파일 | 클래스/함수 | 역할 |
|---|---|---|
| `common.py` | — | 싱글턴(`store`/`theme`/`parts`)·Single/Multi 공유 허브 |
| `charts.py`/`statistics.py` | `StatisticsPanel` 등 | 통계 대시보드 — 본문은 독립 패널 위젯(`StatisticsPanel`, `seq_no`로 블루프린트별 범위 지정), 레이아웃별 페이지는 `single/statistics.py`(`StatisticsPageSingle`)·`multi/statistics.py`(`StatisticsPageMulti`, 좌측 수집 대상 목록 + 블루프린트별 패널)(탭 없는 단일 스크롤 화면) — KPI·상태코드·응답시간·응답결과 → 세션 이력 표 → 수집량 추이 카드(기간 필터로 시간대별/주간별/월별을 고르고 전환 버튼으로 최근 기준/현재 일자 기준을 바꿈), 초기화 버튼은 본문 맨 위 우측 |
| `scheduler.py`/`session.py`/`auth.py` | `SchedulerPage` 등 | 스케줄·세션(딜레이/UA/프록시)·인증 관리 |
| `tray.py` | `TrayManager` | 시스템 트레이 아이콘/메뉴 |
| `single/` | `MainWindowSingle` 등 | 단일 수집 레이아웃 — 기준선 |
| `multi/` | `MainWindowMulti` 등 | 다중 블루프린트 레이아웃. `single/` 상속 후 훅만 오버라이드 |

**`style.py`(881줄)**: 테마(`THEME`)·위젯 팩토리(`Parts`)·재사용 위젯(`StatCard`/`EqualSpacingTable` 등)·
정제 규칙 UI 빌더(`build_refine_rule_rows`, MonitorPage와 스케줄 등록 화면이 공유). 상세는
`PREPROCESS.md` §2 참고.

### `trigger/` 패키지 (4,667줄, 11개 파일)
`layout/single·multi`의 각 페이지에 Mixin으로 주입되는 이벤트 핸들러(레이아웃-로직 분리). 단일·다중
수집이 이 패키지 하나를 공유.

| 파일 | 클래스 | 연결 대상 |
|---|---|---|
| `common.py` | — | 싱글턴·페이지 간 공유 헬퍼(DB 설정 그리드 등) |
| `log_viewer.py` | `LogViewerDialog` | 수집 로그 뷰어(레벨 필터+검색) |
| `toolbar.py`/`dashboard.py` | `GlobalToolbarTriggers` 등 | 시작/중지, 수집 시작, CSV 내보내기 |
| `monitor.py` | `MonitorPageTriggers` | 테이블 필터, 정제 실행, 결과 추출 |
| `statistics.py` | `StatisticsPageTriggers` | 통계 리로드/내보내기 |
| `scheduler.py` | `SchedulerPageTriggers` | 스케줄 등록/수정/삭제/실행, 정제 규칙 패널 |
| `session.py` | `SessionSettingsPageTriggers` 등 | 세션 저장, 프록시 관리·헬스체크 |
| `auth.py` | `AuthManagerPageTriggers` | 인증 정보 저장 |
| `main_window.py` | `MainWindowTriggersSingle/Multi` | 워커 실행 오케스트레이션, 트레이 관리 |

**`worker.py`(513줄)**: `MultiprocessWorker`(QThread)가 별도 `multiprocessing.Process`로 Scrapy를
격리 실행하고(프로세스당 1회 실행 제약), `Queue`로 결과를 수신해 `new_row`/`progress`/`stats_update`/
`finished` 시그널로 UI에 전달. `run_spider()`가 자식 프로세스 진입점, `QueueWriter`가 stdout/stderr를
Queue로 리다이렉트.

**`engine.py`(320줄)** — Scrapy 요청 생성·데이터 추출 핵심 모듈:

| 함수 | 역할 |
|---|---|
| `get_spider(request_info)` | `spiders` 키에 따라 Spider 클래스 반환 |
| `get_scrapy_request()` | GET/POST, 일반/렌더링/JSON/FormData 요청 생성 |
| `get_result()` | HTML(XPath)/JSON/XML 추출 → 딕셔너리 리스트 |
| `set_item_loader()` / `get_response_status()` | Item 패킹 / URL·IP·UA·쿠키·레이턴시 정리 |
| `set_chrome_webdriver()` | Selenium Chrome 드라이버 초기화 |

사이트별(seq_no) 로그인·렌더링은 `login/`·`render/{seq_no}.py`를 `conf.CustomModuleStorage`가 로드해
처리(하드코딩 제거됨).

### Spider 패키지 (`scraper/spiders/`)

| 파일 | Spider | 설명 |
|---|---|---|
| `spihtml.py` | `spider_html` | 정적 HTML XPath 파싱 |
| `spirenderer.py` | `spider_html_render` | Selenium 렌더링 + XPath |
| `spijson.py` | `spider_json` | REST API JSON, jmespath/점 경로 |
| `spixml.py` | `spider_xml` | XML XPath 파싱 |
| `spidetail.py` | `spider_detail` | 목록→상세 2단계 수집 |

모두 `engine.get_scrapy_request()`/`engine.set_item_loader()`로 동일 구조를 따름.

**파이프라인**(`scraper/pipelines.py`): `LoadItemPipeline`이 유일 — 결과를 `RESULT_INFO:` 형식으로
stdout 출력. GUI DB 내보내기 UI는 파이프라인에 연결되어 있지 않음.

**데이터 정제**(`preprocess.py`, 358줄): `DataRefiner`가 7규칙 순서 적용 — ①remove_null_row →
②custom_rule → ③trim_whitespace → ④remove_duplicate → ⑤drop_columns → ⑥fill_null → ⑦cast_numeric
(원본 불변, `RefineStats` 반환). 순서 변경 이력은 `PREPROCESS.md` §1·`HISTORY.md` 참고. 커스텀 규칙
(`custom_rule`)은 `refine/{seq_no}.py`의 `refine(data)`/`refine_row(row)`를 `conf.CustomModuleStorage`가
로드하는 플러그인 방식 — GUI에서 켜면 remove_null_row/trim_whitespace/remove_duplicate가 자동 연동
(`fill_null` 제외). 상세는 `PREPROCESS.md` 참고.

### 설정 및 상태 관리 — `conf.py`(437줄)
싱글턴 3종:
- **`DataStore`**: 수집 행·URL 맵·세션 이력·스케줄 메모리 보관(메인 프로세스 전용)
- **`BlueprintStorage`**: `request_info.json` 로드/관리. 위치는 `utility.data_dir()` 결정(운영 exe:
  `%LOCALAPPDATA%`, 개발: 저장소 in-place)
- **`CustomModuleStorage`**: seq_no별 커스텀 모듈(`render/`·`login/`·`refine/{seq_no}.py`) 로드 —
  `kind`로 물리적으로 다른 폴더 사용, `BlueprintStorage`와 동일한 seed-on-first-run 정책.
  `has_*()`는 AST 파싱만으로 존재 확인, `load_*()`가 실제 로드. 배포 절차는 `build-exe.ps1` 참고

**`customized_settings.py`**: 설정 기본값 팩토리(`get_request_settings()`/`get_task_settings()`/
`get_session_settings()`/`get_output_settings()`/`get_schedule_settings()`/`set_downloader_middlewares()`/
`set_ip_settings()`).

**`scraper/settings.py`**: `CONCURRENT_REQUESTS=32`, `RANDOMIZE_DOWNLOAD_DELAY=True`, 기본 파이프라인
`LoadItemPipeline`, 프록시/UA랜덤화/레이턴시 미들웨어 등록, `TELNETCONSOLE_ENABLED=False`.

**`scraper/middlewares.py`**:

| 클래스 | 역할 |
|---|---|
| `RandomUserAgentMiddleware`/`RandomCookieMiddleware` | UA 랜덤 교체 / 쿠키 랜덤 설정(기존 쿠키 있으면 무변경) |
| `RateLimitedProxyMiddleware` | 여유 프록시 무작위 순회, 전량 소진 시 지연 재시도 |
| `LatencyTrackingMiddleware`/`DelaySchedulerMiddleware` | 레이턴시 측정 / `delay_until` 지연 재스케줄 |

### 유틸리티
- **`utility.py`**: `resource_path()`(배포 기본값 루트)·`data_dir()`(실제 데이터 폴더)·
  `generate_combined_urls()`(`${page:...}`/`${keywords:...}` 전개)·`get_target()`(중첩 탐색)
- **`glean.py`**: `get_grains()` — URL 목록 생성 · **`scraper/items.py`**: `DonasItem`/`DonasItemLoader`
- **`db_conn.py`**: MySQL/PostgreSQL/MongoDB 연결 헬퍼(Qt/Scrapy 의존 없음)
- **`create_request_info.py`**: `request_info.json` 생성 스크립트(개발 도구, 런타임 미호출)
- **`env/config.py`/`create_ini.py`**: `database.ini` 파싱/생성

---

## 4. 수집 데이터 흐름

```
request_info.json → BlueprintStorage 로드 → GUI 시작 버튼 클릭
  → MultiprocessWorker.run()  (QThread, UI 비블로킹)
      ├── utility.generate_combined_urls() → URL 목록 생성
      └── multiprocessing.Process(run_spider)
              ├── engine.get_spider() → Spider 클래스 선택
              ├── CrawlerProcess.crawl(spider, request_info)
              │       ├── spider.start_requests() → glean.get_grains() → engine.get_scrapy_request()
              │       ├── [middlewares] UA 교체, 쿠키, 프록시, 레이턴시 측정
              │       ├── spider.parse() → engine.get_result() → engine.set_item_loader() → DonasItem
              │       └── [pipelines] LoadItemPipeline → print("RESULT_INFO:{...}") → stdout → Queue
              └── MultiprocessWorker._handle_line()
                      ├── DataStore.add_row()
                      ├── new_row.emit()      → Dashboard/Monitor 테이블 갱신
                      ├── progress.emit()     → 프로그레스 바 갱신
                      └── stats_update.emit() → 세션 통계 갱신
```

---

## 5. 핵심 설정 파일: `request_info.json`

수집 작업의 청사진(blueprint). `BlueprintStorage`가 로드하고 `DataStore`와 각 Spider에 전달.

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

**`callback_url` 패턴**: `${page:시작:증가:끝}`(페이지네이션) · `${keywords:서울,인천,부산}`(키워드 확장)

| `spiders` 값 | Spider | 설명 |
|---|---|---|
| `html` | `HtmlExtractorSpider` | 정적 HTML + XPath |
| `html_render` | `HtmlSeleniumSpider` | JS 렌더링 + XPath |
| `json` | `JsonExtractorSpider` | REST API + 점 경로 |
| `xml` | `XmlExtractorSpider` | XML + XPath |
| `detail` | `DetailExtractorSpider` | 목록→상세 2단계 |

> `spiders` 키는 `conditions` 내부·최상위 어느 쪽에 있어도 동작(내부 우선). `items`의 XPath는
> 요소(`.//h2`)·텍스트(`.//h2/text()`)·속성(`@href`) 표기를 모두 지원.

---

## 6. 의존성 요약

| 라이브러리 | 용도 |
|---|---|
| `Scrapy` / `PyQt6` | 비동기 크롤링 엔진 / 데스크톱 GUI 프레임워크 |
| `selenium` / `webdriver-manager` | JS 렌더링 수집(`spirenderer.py`가 직접 구동) / Chrome 드라이버 자동 설치 |
| `lxml` / `parsel` | HTML/XML 파싱 |
| `pymongo` / `mysqlclient`·`PyMySQL` / `psycopg2` | MongoDB / MySQL / PostgreSQL 연결 |
| `SQLAlchemy` | ORM (DB 추상화) |
| `furl` / `python-dotenv` | URL 파싱/조작 / 환경 변수 로드 |
| `pyinstaller` | exe 빌드 — `build-exe.ps1 -SeqNo {seq_no}`로 seq_no별 파일 선별 번들 |
| Inno Setup | (Windows 전용 외부 도구) `build-installer.ps1`이 exe를 설치 프로그램으로 패키징 |

> exe/설치 프로그램 빌드 절차 전체(사전 준비물, 단계별 명령, 트러블슈팅)는 `BUILD_GUIDE.md` 참고.
