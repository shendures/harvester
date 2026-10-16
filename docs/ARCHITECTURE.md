# DataCrawler v2.0 (Harvest) — 아키텍처

> 시스템의 경계, 주요 구성 요소, 실행·데이터 흐름을 설명합니다. 개별 파일과 모듈의 연결은 [코드·스크립트·모듈 관계](MODULE_SPEC.md)에 기록합니다.

## 1. 시스템 개요

- 핵심 설계 목표: 사이트별 코드 수정 없이 설정(블루프린트)만으로 수집하고, 크롤링 장애가 GUI를 멈추지 않게 한다.
- 시스템 경계: 단일 PC에서 도는 데스크톱 앱 하나다. GUI 프로세스와 크롤링 자식 프로세스 둘로 나뉘며 서버는 없다. 블루프린트 작성은 앱 밖(오프라인)이 맡는다.
- 외부 시스템: 수집 대상 웹사이트(HTTP, 필요 시 Chrome 드라이버), 저장 대상 DB(MongoDB·MySQL·PostgreSQL), 블루프린트 원본 DB(`tb_blueprint`, PostgreSQL).
- 기술: Scrapy 2.14, PyQt6, 수집 형식 HTML·JSON·XML.

## 2. 구성 요소와 책임

| 구성 요소 | 시스템에서 맡는 역할 | 연결되는 구성 요소 |
|---|---|---|
| GUI 위젯 트리(`harvest/gui/layout/`) | 화면 구성만 담당한다. 동작은 없다 | 같은 이름의 `harvest/gui/trigger/` Mixin(다중상속), `harvest/gui/style.py` |
| 동작 Mixin(`harvest/gui/trigger/`) | 화면 이벤트를 처리하고 백엔드를 호출한다 | `conf`, `worker`, `preprocess`, `db_conn` |
| 실행 브리지(`harvest/crawler/worker.py`) | 크롤링을 별도 OS 프로세스로 기동하고 결과를 GUI로 전달한다 | `harvest/gui/trigger/main_window.py`, `engine` |
| 크롤링 엔진(`harvest/crawler/engine.py`, `harvest/crawler/glean.py`, `harvest/crawler/scraper/`) | URL 전개, 요청 생성, 데이터 추출, 미들웨어, 결과 출력 | `worker`(자식 프로세스로 실행) |
| 설정·상태(`harvest/core/conf.py`, `harvest/core/customized_settings.py`) | 블루프린트, 수집 이력, 사이트별 플러그인을 싱글턴으로 관리한다 | GUI 프로세스 전용 |
| 정제(`harvest/core/preprocess.py`) | 수집 후 7단계 규칙으로 데이터를 정제한다 | `harvest/gui/trigger/monitor.py`, `conf` |
| DB 연동(`harvest/core/db_conn.py`) | 3종 DB 저장·조회와 연결 검증 | `harvest/gui/trigger/`, `harvest/config/create_request_info.py` |
| 블루프린트 저작 도구 | `harvest/assets/generator_conditions.html`과 `harvest/config/create_request_info.py`. 앱 실행과 무관한 오프라인 트랙 | `tb_blueprint`, `request_info.json` |
| 사이트별 플러그인(`harvest/config/render/`, `login/`, `refine/`) | seq_no별 렌더링·로그인·정제 로직 | `conf.CustomModuleStorage`가 파일에서 로드 |

구성 요소 간 경계와 통신 방식:
- GUI와 크롤러는 서로 다른 프로세스이며 표준출력(stdout)과 `multiprocessing.Queue`로만 통신한다.
- GUI 계층의 의존 방향은 항상 `layout → trigger → style`이다. `layout`과 `trigger`는 `scraper`·`engine`을 직접 참조하지 않고 `harvest/crawler/worker.py` 하나로만 이어진다.
- `conf.DataStore`는 GUI 프로세스 전용이다. 자식 프로세스는 접근하지 못하며 큐 드레인으로만 동기화된다.
- 패키지 의존 방향은 `harvest/gui → harvest/crawler/worker.py → harvest/core`, `harvest/crawler → harvest/core`다. `harvest/core`는 `gui`·`crawler`를 import하지 않는다. `harvest/config/create_request_info.py`는 오프라인 전용이라 앱 실행에서 import되지 않는다.
- `harvest/core/utility.py`는 내부 의존성이 없는 최하위 공용 모듈이다.

## 3. 주요 실행 흐름

### 3.1 수집 실행

1. 시작 버튼 → `harvest/gui/trigger/toolbar.py`가 블루프린트와 화면 설정으로 task를 구성하고 `BlueprintStorage`에 저장한 뒤 시작을 요청한다.
2. `harvest/gui/trigger/main_window.py`가 `MultiprocessWorker`(QThread)를 기동한다. 워커가 `utility.generate_combined_urls()`로 URL 목록(`${page:...}`, `${keywords:...}` 전개)을 만든다.
3. `multiprocessing.Process(run_spider)`로 별도 프로세스를 띄운다. Twisted 리액터는 재시작할 수 없어 수집마다 새 프로세스를 쓴다. `engine.get_spider()`가 스파이더 5종 중 하나를 고른다.
4. 스파이더가 요청을 만들고(`glean` → `engine`), 미들웨어가 UA·쿠키 랜덤화, 프록시 레이트리밋, 지연 측정을 처리한다. 응답을 추출해 `DonasItem`으로 적재한다.
5. `harvest/crawler/scraper/pipelines.py`가 `RESULT_INFO:{json}`을 stdout에 출력한다. 자식의 stdout은 큐를 거쳐 부모에 도착한다.
6. `MultiprocessWorker`가 줄을 파싱해 `DataStore`를 갱신하고 `new_row`·`progress`·`stats_update` 시그널을 보낸다. 화면이 갱신된다.

실패 처리: 스파이더 실행 자체가 실패하면(`EXECUTOR_STATUS: FAILED`) 워커는 `aborted`로 기록한다. 사용자 중단(`interrupted`)과 구분하며, 스케줄 재무장과 대기 큐 소비는 정상 진행한다. 실행 경로별 통보 방식은 [3.5절](#35-수집-실행-4경로와-에러실패-처리)에 정리한다.

### 3.2 정제와 저장

수집 완료(`worker.finished`) 후 `harvest/gui/trigger/monitor.py`가 `preprocess.DataRefiner`를 실행한다. 원본은 바꾸지 않고 `RefineStats`를 함께 반환한다. 규칙 순서는 고정이며 바꾸면 결과가 달라진다.

```
① remove_null_row → ② custom_rule → ③ trim_whitespace → ④ remove_duplicate
→ ⑤ drop_columns → ⑥ fill_null → ⑦ cast_numeric
```

- ①은 계산이 가벼워 맨 앞에 둔다. ②는 ①로 줄어든 데이터에 적용해 사이트별 원시 데이터를 정규화한다.
- ③은 ④보다 먼저 와서 공백만 다른 값도 중복으로 잡는다. ④는 비싼 전체 비교라 ②③ 뒤에 둔다.
- ⑤는 중복 판정 이후, ⑥⑦ 이전에 둔다. 이후 단계가 불필요한 컬럼을 순회하지 않게 한다.
- 실행 경로는 두 가지다. 수동 정제는 화면의 체크박스·제외 필드·치환값을 읽고 결과를 화면에 반영한다. 스케줄 자동 저장은 무인 실행이라 스케줄에 저장된 규칙(없으면 고정 기본값)을 쓰고 화면을 갱신하지 않는다.
- 무인 실행에서 데이터가 비면 모달을 띄우지 않고 경고 로그만 남긴다. 모달은 큐 소비와 스케줄을 막기 때문이다.
- 결과는 CSV·JSON 파일이나 `db_conn.save_db()`로 저장한다. DB 저장 전 연결을 검증한다.

### 3.3 통계 종합 평가

통계 화면의 배너는 응답 이력(`DataStore`의 URL 응답 행)으로 수집 상태를 평가한다. KPI 카드·차트는 초기화 이후 누적을 보여 주고, 배너는 최근 5회 수집을 판정한다.

- 지표별로 비율 신뢰구간(Wilson 95%)을 구해 주의·문제 임계값과 비교한다. 구간이 임계값에 걸치면 판정을 보류한다.
- 평가 항목: 연결 실패율, 접근 차단율(403·429), HTTP 오류율, 빈 응답률, 지연 응답 비율, 유효 데이터 비율, 페이지당 수집량. 응답 성공률, 처리량, 평균 응답은 판정에 쓰지 않는다.
- 판정은 수집 1회부터 시작하고 "문제"도 1회에 확정한다. 1회차 "문제"에는 일시 장애 가능성을 배너로 알린다. 페이지당 수집량은 회차 간 비교 지표라 3회부터 판정한다.
- 완료된 수집이 3회 이상이면 회차별 값이 일정한지 본다. 일정하면 절대 기준 "주의"여도 정상으로 보되, 절대 "문제"는 일정해도 문제로 둔다. 진행 중 수집이 끌어올린 부분은 사면하지 않는다.
- 종합 등급은 지표 중 가장 나쁜 등급이다. 전부 보류면 "대기"다. 최근 100건과 이전 구간의 정상 수집률은 별도 검정으로 악화를 알린다.
- 임계값과 윈도우·유의수준 상수는 `harvest/gui/trigger/statistics.py` 상단에서 조정한다.

### 3.4 블루프린트 저작(오프라인)

앱 실행 흐름과 무관하며 `main.py`·`harvest/crawler/worker.py`·`harvest/crawler/engine.py`는 이를 호출하지 않는다.

1. 운영자가 `harvest/assets/generator_conditions.html`(서버 없는 브라우저 도구)로 `conditions` JSON을 만들고 `tb_blueprint`에 수동 저장한다.
2. `harvest/config/create_request_info.py`를 수동 실행하면 `db_conn.read_db_data()`로 조회해 `request_info.json`을 재생성한다. 빌드 때는 `scripts/build-exe.ps1`에 내장된 매니페스트 코드가 같은 조회를 수행한다.
3. 앱 시작 시 `conf.BlueprintStorage`가 로드하고, `main.py`가 블루프린트 개수로 단일(1개)·다중(2개 이상) 화면을 정한다.

### 3.5 수집 실행 4경로와 에러·실패 처리

수집은 네 경로로 시작되며 모두 3.1의 같은 워커·완료 처리(`_on_finished`)를 거친다. 경로마다 "그 순간 결과를 보고 있는 사람이 있는가"와 "뒤에 기다리는 작업이 있는가"가 달라 에러를 알리는 방법이 갈린다.

| 경로 | 화면 | 시작 주체 | 실행 중 재요청 | 뒤에 기다리는 작업 |
|---|---|---|---|---|
| 수동 실행 | 단일 | 툴바 ▶ | 실행 중인 워커를 멈추고 교체한다 | 없음 |
| 선택 수집 | 다중 | 목록의 체크 후 실행·행 ▶ | `_pending_queue` 뒤에 붙는다 | 선택한 N건(행 ▶는 1건) |
| 전체 수집 | 다중 | 전체 수집 버튼 | `_pending_queue` 뒤에 붙는다 | 전체 N건 |
| 스케줄 실행 | 단일·다중 | `QTimer`(스케줄러) | `_pending_queue` 뒤에 붙는다 | 다른 스케줄·배치와 큐를 공유한다 |

선택·전체 수집은 `batch_meta`(`index`/`total`)로 순서를 알고, 스케줄은 `task_nm`을 가진다. 이 두 속성이 아래 판단의 근거다.

**판단 기준: 모달은 단건 유인 실행에서만 허용한다.** 모달이 떠 있는 동안에는 `_on_finished` 끝의 `_consume_pending_queue()`가 실행되지 않아 다음 순번이 시작되지 않는다. 그래서 "사람이 직접 시작했고(`task_nm` 없음) 단건(`batch_meta.total <= 1`)인가"를 `harvest/gui/trigger/common.py`의 `_modal_allowed(task)` 한 곳에서 판정한다. 수동 실행과 행 ▶ 단건은 허용, 선택·전체 수집(N건)과 스케줄은 금지다. 정제 규칙을 스케줄 고정값으로 강제할지는 모달과 별개 축이라 따로 판정한다.

**에러·실패 처리 방식**

| 상황 | 기록·처리 | 유인 단건 | 무인·순차(모달 금지) |
|---|---|---|---|
| 사용자 중단(`interrupted`) | 경고 로그. 중지 시 대기 큐를 비우므로 큐를 더 소비하지 않는다 | 그대로 | 그대로 |
| 실행 실패(`aborted`) | 오류 로그에 `abort_reason`을 남긴다. 스케줄 재무장과 큐 소비는 계속한다 | 모달 | 트레이 알림 + 대시보드 실패 배너 + 다중 목록 "실패" 표시 |
| 0건 종료 | 오류 로그. 스케줄 재무장과 큐 소비는 계속한다 | 모달 | 트레이 알림 + 대시보드 배너 + 다중 목록 "실패" 표시 |
| 자동 저장 중 정제 실패 | 자동 저장 경로에서는 정제 불가·정제 오류 모달을 띄우지 않고 로그만 남긴다(EXTRACT 버튼 클릭은 기존처럼 모달) | 로그 | 로그 |
| 무인 실행의 파일·DB 저장 실패 | 로그 + 트레이 알림 | (유인은 모달) | 로그 + 트레이 알림 |
| 추출 예외가 난 HTTP 200 응답 | 성공이 아니라 경고(`warn`)로 분류한다. 오류 응답 집계(`_errors`)에는 넣지 않는다 | 로그 | 로그 |

- **질문은 실행 전에, 통보는 실행 후에 한다.** 덮어쓰기 확인이나 DB 테이블 처리 선택 같은 질문은 실행 중 모달로 물으면 큐를 막는다. 스케줄은 등록 시 저장 방식을 정해 두고(`schedule_save_type`), 모달이 금지된 실행은 저장 대상이 겹쳐도 확인창 없이 사전 확정된 방식(기본값 새로 저장)으로 저장한다.
- **통보 채널은 지속 시간으로 나눈다.** 트레이 알림은 몇 초 뒤 사라지는 즉시 통보이고, 대시보드 실패 배너는 다음 수집을 시작할 때까지 남으며, 다중 화면 수집 목록의 "실패" 상태(빨간 글씨)는 앱을 다시 열어 봐도 확인된다.
- **순차 실행은 건별 통보 대신 종료 요약을 남긴다.** 선택·전체 수집은 마지막 건(`batch_meta.index == total - 1`)이 끝날 때 "총 N건 중 성공·0건·실패" 로그 한 줄을 남긴다. 종료 판정에 `_pending_queue`가 비었는지를 쓰지 않는 것은 스케줄과 같은 큐를 공유해 오판하기 때문이다. 단일 화면의 수동·스케줄 실행에는 이 요약이 없다.
- 자동 저장 실패나 정제 중 예외는 `_on_finished`에서 로그만 남기고 다음 순번으로 넘어간다. 한 건의 실패가 뒤의 작업을 막지 않는 것이 우선이다.

조사 배경과 구현·검증 내용은 [HISTORY.md](HISTORY.md)의 2026-09-23 항목에 있다.

## 4. 데이터와 외부 연동

| 데이터 또는 연동 | 생성·입력 위치 | 저장·전달 위치 | 형식 또는 계약 |
|---|---|---|---|
| `request_info.json` | `harvest/config/create_request_info.py`, 빌드 시 `scripts/build-exe.ps1` 내장 매니페스트 코드 | 앱 데이터 폴더, `BlueprintStorage`가 로드 | 블루프린트 배열. 원소 수로 단일·다중 결정 |
| 수집 결과 행 | 자식 프로세스 파이프라인 | stdout → 큐 → `DataStore` | 한 줄 `RESULT_INFO:{json}` |
| 통계 응답 이력 | `harvest/crawler/worker.py`가 응답마다 기록 | `stats_history.json.gz` (gzip, 컴팩트 JSON) | URL 사전 + 응답 배열. 저장 때 `.bak` 한 세대, 읽을 수 없으면 `.corrupt`로 보존 후 `.bak` 복구 |
| 스케줄 | 스케줄 등록 화면 | 앱 데이터 폴더의 `schedules.json` | 스케줄별 규칙·저장 설정 포함. DB 저장 자격증명이 평문으로 들어간다 |
| 사이트별 플러그인 | 개발자가 작성 | `harvest/config/{render,login,refine}/`의 `{seq_no}.py` → 앱 데이터 폴더로 최초 1회 복사 | 파일명은 `seq_no`와 문자열 그대로 일치 |
| 수집 대상 사이트 | 스파이더·Selenium | HTTP | `ROBOTSTXT_OBEY=True`이지만 UA·쿠키 랜덤화·프록시 로테이션이 공존한다 |
| 저장 DB | `db_conn.save_db()` | MongoDB·MySQL·PostgreSQL | `append`·`overwrite` 모드 |

`request_info.json` 예시(필드는 대표값):

```json
[
  {
    "seq_no": "000001",
    "title": "작업명",
    "url": "https://example.com/list",
    "callback_url": "https://example.com/list?page=${page:1:1:10}",
    "conditions": {
      "dataFormat": "html",
      "method": "GET",
      "rendering": false,
      "items": { "root": "//div[@class='list']/li", "title": ".//h2/text()" }
    },
    "spiders": "html",
    "needs_cleaning": true
  }
]
```

`callback_url`은 페이지네이션(`${page:시작:증가:끝}`)과 키워드 확장(`${keywords:...}`)을 지원한다. `spiders`는 수집 방식을, `conditions`는 데이터 형식과 추출 규칙을 정한다. 전체 필드는 `harvest/assets/generator_conditions.html`이 정의한다.

사이트별 플러그인 계약(`conf.CustomModuleStorage`가 로드):

| 종류 | 실행 위치 | 함수 |
|---|---|---|
| `refine/{seq_no}.py` | GUI 프로세스 | `refine(data)` 또는 `refine_row(row)` |
| `render/{seq_no}.py` | Selenium 자식 프로세스 | `render()` |
| `login/{seq_no}.py` | Selenium 자식 프로세스 | `login(driver, login_info)` |

## 5. 주요 설계 결정

| 결정 | 이유 | 영향 |
|---|---|---|
| 크롤링을 별도 OS 프로세스로 실행 | Twisted 리액터는 한 프로세스에서 재시작할 수 없고, 크롤러 장애가 GUI를 멈추면 안 된다 | 상태 공유가 불가능하다. 결과는 stdout·큐로만 넘기고, `PyInstaller` exe에서는 `multiprocessing.freeze_support()`가 필수다 |
| GUI가 `harvest/crawler/worker.py` 하나로만 크롤링과 연결 | 의존 방향을 고정해 한쪽 변경이 다른 쪽에 번지지 않게 한다 | `layout`·`trigger`에서 `scraper`·`engine`을 import하면 안 된다 |
| 소스를 `harvest/{core,crawler,gui,tools}`로 역할별 분리 | GUI 프로세스, 크롤링 자식 프로세스, 공용 계층의 경계를 디렉터리로 드러내고 루트에는 진입점·설정 파일만 둔다 | `harvest`는 저장소 루트에서 실행할 때만 import된다. 플러그인에서 `import engine`처럼 옛 최상위 이름을 쓰면 실패하므로 `from harvest.crawler import engine`으로 써야 한다. 이미 배포돼 앱 데이터 폴더에 시딩된 옛 플러그인 사본은 교체 전까지 이 이름으로 실패한다([ISSUES.md](ISSUES.md) §2) |
| 사이트별 로직은 플러그인 파일 | seq_no마다 엔진 코드를 고치지 않으려는 목적이다 | 파일명은 seq_no와 같아야 한다. `exec`로 로드하며 샌드박스가 없어 개발자가 검수한 코드만 써야 한다 |
| 수집 설정 폴더(`harvest/config/`)의 플러그인·`env/`·`request_info.json`은 git 미추적 | 고객별 규칙 코드와 접속 정보는 개발 자체에 필요하지 않다. 한 폴더에 모아 `.gitignore`가 경로로 고정한다 | `/harvest/config/{render,refine,login}/` 패턴이 어긋나면 고객 코드가 추적 대상이 된다. 다른 클론이 pull하면 파일이 삭제로 적용될 수 있다. 빌드는 활성 seq_no의 파일만 골라 담아 다른 고객 규칙의 유출을 막는다 |
| `login()`·`render()`·`refine()`을 폴더별로 분리 | 실행 컨텍스트(자식/GUI 프로세스)와 역할이 달라 한 폴더에 섞으면 구분이 안 된다 | 앱 데이터 폴더 레이아웃(`%LOCALAPPDATA%\<AppName>\{kind}\`)은 이 폴더 구조와 1:1이라 옮기면 배포된 앱의 사용자 수정본이 유실된다. 개발·번들 쪽 원본 위치(`harvest/config/`)만 옮길 수 있다 |
| 로그인 수집은 `html_render`에만 둔다 | 로그인과 수집이 같은 브라우저 세션이라 세션 일관성이 보장된다. 다른 스파이더에 쿠키를 이식하면 UA 랜덤화·쿠키 미들웨어와 충돌해 세션이 무효화될 위험이 있다 | 다른 스파이더로 확장하려면 이 충돌부터 풀어야 한다 |
| Scrapy 구성 파일을 `harvest/crawler/scraper/` 패키지로 모음 | GUI와 엔진 파일을 구분하고 PyInstaller 번들 목록을 단순화한다 | 패키지 이름은 `scrapy`가 아니라 `scraper`여야 한다(라이브러리를 가려 기동이 불가능해진다). 미들웨어·파이프라인은 문자열 경로로 로드되므로 틀려도 예외 없이 기본값으로 동작한다. 기동 로그의 `Enabled ...` 목록으로 확인한다 |
| `__init__.py`는 하위 모듈을 재export하지 않음 | Scrapy 설정 로딩과 `engine ↔ spiders` 순환 import를 피한다 | 앱은 `harvest/crawler/worker.py`가 `import engine`을 `CrawlerProcess` 생성보다 먼저 실행해 우회 중이다 |
| 정제 규칙 순서를 고정 | 순서가 결과와 메모리·시간 비용을 좌우한다(3.2절) | 순서를 바꾸면 결과가 달라진다 |
| 무인·순차 실행은 모달 금지 | 모달이 떠 있는 동안 대기 큐의 다음 순번과 스케줄이 시작되지 않는다. 선택·전체 수집(N건)도 방금 버튼을 눌렀을 뿐 실제로는 순차 무인 실행이다 | 판정은 job 이름이 아니라 `task`의 속성(`task_nm`, `batch_meta.total`)으로 하며 `_modal_allowed()` 한 곳에 둔다. 새 경고를 추가할 때 같은 판정을 쓰고, 금지된 경로의 실패는 트레이 알림·배너·로그로 남긴다(3.5절) |
| 실행 실패와 사용자 중단을 분리 | 둘을 한 플래그로 다루면 실행 실패가 중단으로 처리돼 스케줄이 다음 실행을 예약하지 못하고 대기 큐가 남는다 | 종료 요약에 `aborted`와 `interrupted`가 별도 필드다. 종료 분기를 추가할 때 스케줄 재무장·큐 소비를 건너뛰는 것은 사용자 중단뿐이어야 한다 |
| 순차 실행 결과는 마지막 건에서 한 번 요약 | 건별 통보는 모달 압력을 키우고 로그에 흩어진다 | 종료 판정은 `batch_meta`로 하며 `_pending_queue` 상태는 쓰지 않는다. 요약은 성공·0건·실패 3범주이고 저장 실패는 따로 세지 않는다 |
| 통계 이력은 영구 보존, gzip 단일 파일 | 평가가 누적 이력에 기대고, 용량과 손상 위험을 함께 줄인다 | 통계 초기화는 통계 화면의 RESET만 한다. 중지 버튼은 이력을 지우지 않는다 |
| 통계 평가는 신뢰구간 + 회차 패턴 | 소표본 단정과 일회성 이상 오탐을 막는다 | 최근 5회 창만 판정한다. 회차당 응답이 30건 미만이면 한 회차의 작은 이상은 놓칠 수 있어 상세 보기에 고지한다 |

알려진 한계와 후속 과제:
- 통계 평가는 단일 수집 항목을 전제한다. 다중 수집 항목은 회차가 섞이면 차이를 불안정으로 오판할 수 있다.
- 어느 회차가 이상인지, 정상 문구의 근거 수치, 개선·악화 방향은 아직 표시하지 않는다.
- 회차당 1% 수준의 느린 하락은 5회 창에서 보이지 않는다.
- 스케줄의 로그인 수집은 [ISSUES.md](ISSUES.md) ㉙에 보류로 기록돼 있다.
- 수집 실행 에러 처리(3.5절)의 남은 부분:
  - 자식 프로세스가 멈춰도(예: Selenium 세션 정지) 전체 타임아웃이나 무응답 감지가 없어 "수집 중"에 고착되고, 수동 중지 외 복구 경로가 없다.
  - `sys.excepthook` 같은 전역 예외 훅이 없어 Qt 슬롯에서 잡히지 않은 예외는 사용자에게 표시되지 않는다.
  - 실패 표시는 치명·실패·열화 구분 없이 빨간색 하나다. 무인 실행의 저장 실패는 트레이 알림과 로그까지만이고 대시보드 배너·목록 상태·배치 요약에는 반영되지 않는다.
  - 수동 단건 실행의 실패는 즉시 팝업으로 알린다. 지켜보는 사용자에게는 즉각 피드백이 낫다고 보아 배너로 바꾸지 않았다.

## 6. 관련 문서

- [프로젝트 설명](README.md): 목적과 주요 기능
- [개발 환경](DEV_ENV.md): 설치와 실행 방법
- [코드·스크립트·모듈 관계](MODULE_SPEC.md): 파일별 책임과 의존 관계
- [작업 이력](HISTORY.md), [이슈·백로그](ISSUES.md): 설계 결정의 배경과 남은 과제
