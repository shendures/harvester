# DataCrawler v2.0 (Harvest) — 진행 이력

> `PROJECT_REPORT.md`에서 분리된 작업 이력 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 미해결 이슈·백로그는 `ISSUES.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04 (조사 범위: 전체 소스 코드 약 16,200줄, 문서, Git 이력, 의존성, 보안)
- **최신 갱신**: 2026-07-07

---

## 완료된 작업 (시간순)

### 리다이렉트 URL 불일치 수정 (`d469277`, 12줄)

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

### 저장소 전체 줄바꿈(LF) 정규화 (`e10073c`, `3edb01a`)

- `.gitattributes(eol=lf)` 도입 이전에 CRLF로 커밋된 20개 파일 일괄 정규화
- `git diff --ignore-cr-at-eol` 기준 **내용 변경 0줄** 검증
- 부수 효과로 겪은 "EOL 림보"(CRLF blob + LF 규칙 → 영구 modified 유령 상태)의
  원인·진단·해법을 GIT_GUIDE에 문서화. main/develop 모두 LF blob을 가리키므로
  **재발 없음**

### Git 운영 체계 정비 (PR #2, #3)

- GitHub ruleset("PR 필수")과 가이드의 직접 머지 플로우 충돌 발견
  (직접 푸시 시 owner bypass 경고 발생)
- GIT_GUIDE를 **PR 기반 플로우로 개정**: `gh pr create` → `gh pr merge --admin`
  (1인 저장소는 자기 승인 불가로 `--admin` 필요)
- EOL 노이즈 진단법(`git diff --ignore-cr-at-eol`, `git add --renormalize`) 추가

### 1차 릴리스 및 멀티환경 동기화 (PR #4)

- `develop → main` 릴리스 PR 머지: main = `0155bfa`
- WSL / Windows 클론 모두 main·develop 동기화 완료, 양쪽 working tree clean 확인

### 프록시 rate limit 미들웨어 수정 (이슈 ②, PR #5)

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

### 검증용 테스트 제거 (PR #6)

- PR #5 검증용으로 작성한 미들웨어 유닛 테스트 8건을 정책(검증 산출물은
  저장소에 커밋하지 않음)에 따라 제거

### 문서 통합 (PR #7)

- `PROJECT_GUIDE.md`(구조) + `PROJECT_AUDIT_REPORT.md`(진행상황)를
  `PROJECT_REPORT.md`로 통합, 원본 삭제, `CLAUDE.md` 참조 갱신

### 미사용 파이프라인 제거 및 기본 파이프라인 교체 (이슈 ④, PR #8)

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

### 이슈 ⑧ 등록 및 리포트 현행화 (PR #9)

- 이슈 ⑧(`/text()` XPath 추출 깨짐)을 이슈 테이블·백로그 1순위로 등록
- 이슈 ④ 해결 처리, PR #7/#8 완료 작업 기록, 파이프라인 표·기본 설정 설명 현행화
- `worker.set_scrapy_settings()` 예외 삼킴 개선을 별도 백로그 항목으로 분리

### 2차 릴리스 (PR #10, 2026-07-05)

- Windows 환경 GUI 검증 완료 확인 후 `develop → main` 릴리스 PR 머지
- main = `2dfbdcd` (PR #5~#9 포함: 프록시 rate limit 수정, 테스트 제거,
  문서 통합, 이슈 ④ 해소, 이슈 ⑧ 백로그 등록)
- 이후 문서 분리(PR #11) 반영 릴리스 PR #12 머지 → main = `f611a65`

### `/text()`·`@attr` XPath 추출 수정 (이슈 ⑧, PR #13, 2026-07-05)

- **원인**: `engine.extract_data_from_root()`가 추출된 모든 노드에
  `node.xpath(".")`를 재호출 — 문자열 결과(text()/@attr)는 빈 값(조용한 유실),
  JSON 파싱 가능한 텍스트(`"100"` 등)는 parsel 1.11이 json 타입으로 판정해
  ValueError → 해당 페이지 추출 전체 실패
- **수정**: `node.root`가 문자열이면 그대로 사용, 요소 노드만 기존
  `xpath(".") + 태그 제거` 경로 유지 (요소 XPath 동작 무변경)
- **검증 중 확인**: `@href` 등 속성 XPath도 동일 버그 — 함께 해결
- **검증** (WSL uv venv, Python 3.12, parsel 1.11.0):
  - 유닛 4케이스(요소/일반 텍스트/숫자 텍스트/@href) — 수정 전 3/4 FAIL →
    수정 후 4/4 PASS
  - e2e(`run_spider` 자식 프로세스, `/text()`+`@href` blueprint) — 수정 전
    0건(EXECUTOR_STATUS는 SUCCESS인 채 조용한 유실) → 수정 후 2행 정상 수집

### `spiders` 키 조회 리팩터 (PR #14, 2026-07-05)

- **배경**: `get_spider()`가 blueprint 전체를 받으면서 최상위 `spiders` 키만
  조회 → 문서 §5 예시(`conditions` 내부 표기)와 불일치. request_info.json은
  현행 유지가 제약이라 fallback 방식 채택
- **수정**: 파라미터명을 `request_info`로 정정, `conditions["spiders"]` 우선
  조회 + 최상위 fallback. **request_info.json 무변경**
- **검증**: 사본 선검증 후 실코드 반영 — e2e 최상위 형태(현행) 수정 전후 모두
  PASS(회귀 없음), conditions 내부 형태 수정 전 FAIL(`KeyError: 'spiders'`) →
  수정 후 PASS, 유닛 4케이스(양쪽 존재 시 내부 우선 등) PASS
- 부수 효과: `PROJECT_REPORT.md` §5 예시의 문서-코드 불일치 2건 자연 해소

### 3차 릴리스 (PR #16, 2026-07-05)

- `develop → main` 릴리스 PR 머지: main = `f9fa763`
  (PR #13 이슈 ⑧ XPath 수정, PR #14 spiders 키 리팩터, PR #15 문서 현행화 포함)
- WSL·Windows 클론 모두 main·develop 동기화 완료

### `get_response_status()` 방어 코드 추가 (이슈 ⑥, PR #19, 2026-07-05)

- **원인**: Selenium 등으로 생성된 응답은 `response.ip_address`가 None일 수 있어
  `.compressed` 접근 시 AttributeError, 비표준 상태 코드(예: 520)는
  `HTTPStatus(response.status)`가 ValueError → 두 경우 모두 호출부(spider
  `parse()`)의 광범위 `except Exception`에 걸려 **결과가 조용히 유실**
- **수정**: `ip_address`는 None이면 그대로 None 전달, `reason`은
  `HTTPStatus()` ValueError를 try/except로 잡아 빈 문자열로 대체
- **검증** (WSL uv venv, Python 3.12): 유닛 2케이스(ip_address=None,
  비표준 상태코드 520) — 수정 전 각각 AttributeError로 FAIL / 수정 후 PASS
  (검증용 스크립트는 정책에 따라 검증 후 삭제)

### 4차 릴리스 (PR #20, 2026-07-05)

- `develop → main` 릴리스 PR 머지: main = `9a08497` (PR #19 이슈 ⑥ 수정 포함)
- WSL·Windows(`/mnt/d/Career/python_uv/Harvest`) 클론 모두 main·develop 동기화 완료

### 쿠키 랜덤 미들웨어 반환값 수정 (이슈 ③, PR #21, 2026-07-05)

- **원인**: `RandomCookieMiddleware.process_request()`가 요청에 이미 쿠키가
  있으면 `request.cookies`(dict)를 그대로 반환 — Scrapy의 `process_request`
  규약(`None`/`Response`/`Request`만 허용) 위반으로 `_InvalidOutput` 예외 발생
- **수정**: `return request.cookies` → `return None`
- **검증** (WSL uv venv, Python 3.12): 미들웨어 인스턴스에 쿠키가 설정된
  요청을 직접 전달 — 수정 전 dict 반환(AssertionError) / 수정 후 `None` 반환 PASS

### `DelaySchedulerMiddleware` 재설계 (이슈 ⑤, PR #23, 2026-07-06)

- **원인**: `settings.py`가 존재하지 않는 Scrapy 설정 키(`SCHEDULER_MIDDLEWARES`)에
  등록해 미들웨어 자체가 로드되지 않음. 내부 로직도 제거된 API
  (`spider.crawler.engine.schedule()`)를 호출하고, `process_spider_output` 안에서
  `DontCloseSpider`를 던져도 `spider_idle` 시그널 핸들러가 아니면 아무 효과가 없어
  구조적으로 이중으로 죽어 있었음. `request.meta['delay_until']`을 설정하는 호출부도
  전무해 완전한 죽은 코드였음
- **수정**:
  - `_DelayedRescheduler` 공유 헬퍼 신설 — `reactor.callLater` + `engine.crawl()`로
    지연 재주입, `spider_idle` 시그널에서 `DontCloseSpider`로 조기 종료 방지
  - `DelaySchedulerMiddleware`를 이 헬퍼로 재작성, `settings.py`의 등록 키를
    `SPIDER_MIDDLEWARES`로 정정
  - 백로그 메모(rate limit 재시도 설계와 함께 재검토)에 따라 `RateLimitedProxyMiddleware`도
    연동 — 프록시 전량 소진 시 `IgnoreRequest`로 폐기만 하던 것을 지연 재시도로 변경
  - 재주입 시 `request.replace(dont_filter=True)` 적용 (이미 dupefilter를 거친
    요청이 재주입 시 조용히 드롭되는 것 방지)
- **검증**: mock 크롤러(실제 Scrapy `Request`/`Settings` 객체 + twisted reactor)로
  지연 후 정상 재주입, rate limit 초과 시 폐기 대신 재스케줄 등록 확인 (검증 스크립트는
  정책에 따라 삭제)
- **PR #23 코드 리뷰 (8앵글 + 1-vote verify)에서 후속 결함 2건 CONFIRMED, 병합 전 수정**:
  1. `CLOSESPIDER_*` 확장이 `spider_idle`을 거치지 않고 스파이더를 직접 닫아
     `pending`/`DontCloseSpider` 가드를 우회 → 지연 타이머 발동 시 `engine.crawl()`의
     `RuntimeError`가 Twisted 콜백 안에서 조용히 삼켜져 재시도 요청이 소리 없이 유실.
     **수정**: 예약된 `DelayedCall`을 `pending_calls`에 추적하고, `spider_closed`
     시그널에서 남은 타이머를 명시적으로 취소 + 경고 로그 남기도록 변경
  2. `RateLimitedProxyMiddleware`의 재스케줄에 Scrapy `RetryMiddleware`의
     `RETRY_TIMES` 같은 상한이 없어, 프록시 풀 대비 동시성이 큰 실사용 설정에서
     무한 재스케줄 가능성 + 통계 미노출. **수정**: `MAX_RATE_LIMIT_RETRIES`(5회) +
     `request.meta['rate_limit_retries']` 카운터 추가, `rate_limit/rescheduled`·
     `rate_limit/max_reached` 통계 노출
  - **검증**: mock 크롤러 + 실제 reactor로 (a) 정상 지연 재주입 경로 회귀 없음,
    (b) 강제 종료 시 타이머 취소 후 닫힌 엔진에 `crawl()` 미호출, (c) 5회 재시도 후
    통계와 함께 포기 확인 (검증 스크립트는 정책에 따라 삭제)
  - 낮은 우선순위로 `meta.pop('delay_until')`의 제자리 변경(동일 Request 객체
    중복 yield 시 중복 크롤 가능성, 현재는 도달 불가한 잠재 리스크)은 백로그에 등록

### 미구현 스파이더 타입 예외 처리 (이슈 ⑦, PR #25, 2026-07-06)

- **원인**: `get_spider()`가 미구현 스파이더 타입 3종(`html_render_detail`,
  `json_detail`, `json_payload_detail`)에 빈 dict `{}`를 반환해 `worker.py`가
  그대로 `process.crawl({}, ...)`에 넘김. 인식 못 하는 타입에 대한 else 분기도
  없어 암묵적으로 `None`이 반환됨 — 두 경우 모두 Scrapy 내부 깊은 곳에서
  불투명한 실패로 나타남
- **수정**: 미구현 3종은 `NotImplementedError`, 미인식 타입은 `ValueError`를
  명시적으로 raise. `worker.py`의 기존 `get_spider()`/`process.crawl()` 주변
  try/except가 이미 로그를 남기고 깔끔히 중단하므로 호출부 변경은 불필요

### 스케줄 기능 전면 복구 (이슈 ⑨~⑫, PR #27, 2026-07-06)

- **원인**: `SchedulerPage`가 `MainWindow`의 실제 `SessionSettingsPage`를 쓰지
  않고 별도 인스턴스를 직접 생성·보관 — 스케줄 등록 시 읽는 UA/쿠키 설정이
  항상 기본값이고 `proxy` 키 자체가 없어 스케줄 수집은 프록시를 전혀 쓰지
  않음(⑨). 프록시 목록 존재 여부도 구버전(`frames_tmp.py`) 스키마 잔재인
  `net_rotate` 키로 확인해 항상 "목록 없음"으로 판정(⑩). 월간 스케줄은 남은
  시간을 ms로 환산해 `QTimer.start()`에 그대로 넘겨 30일치가 C int32 최댓값을
  넘어 OverflowError(⑪). 스케줄 저장이 설치/소스 디렉터리에 이뤄져
  PyInstaller 실행마다 유실(⑫)
- **수정**: `MainWindow`의 실제 `SessionSettingsPage` 인스턴스를 `SchedulerPage`에
  주입, 수동 실행과 동일한 스키마의 `proxy` 딕셔너리를 스케줄 payload에 추가,
  프록시 검증도 현행 스키마(`session_page._proxy_rows`)로 교체. 7일 단위로
  타이머를 재등록하는 방식으로 월간 스케줄의 int32 오버플로우 제거.
  저장/로드를 `file_path`(LOCALAPPDATA) 기준으로 변경(BlueprintStorage와
  동일 정책, 없으면 `default_source`로만 폴백)

### 죽은 SeleniumMiddleware 경로 제거 (이슈 ⑬, PR #29, 2026-07-06)

- **원인**: `SELENIUM_DRIVER_EXECUTABLE_PATH`가 항상 미설정이라
  `scrapy_selenium.SeleniumMiddleware`는 로드마다 `NotConfigured`로 자체
  비활성화. 설령 경로를 채워도 `scrapy_selenium` 0.0.7이 구버전 Selenium
  API(`executable_path`/`chrome_options`)를 써서 고정된 `selenium==4.41.0`에서
  `TypeError`. 실제 렌더링은 이미 `spirenderer.py`가 자체 Chrome 드라이버로
  전담하고 있어, 미들웨어를 GUI 경로에 추가 등록(대칭 맞추기)하는 대신 죽은
  의존성 자체를 제거하는 방향 선택
- **수정**: `settings.py`에서 `SeleniumMiddleware` 등록·`SELENIUM_DRIVER_*` 설정
  삭제, `engine.get_scrapy_request()`의 `html_render` 분기가 `SeleniumRequest`
  대신 일반 `scrapy.Request`를 반환, `requirements.txt`에서 `scrapy-selenium`
  제거 — 같은 페이지를 2회(일반 다운로드 + Selenium 렌더) 요청할 가능성도
  함께 차단

### spirenderer 드라이버 누수 수정 (이슈 ⑭, PR #31, 2026-07-06)

- **원인**: `driver.quit()`이 try 블록 마지막에 있어 렌더링/추출 중 예외(빈
  셀렉터 매칭의 `IndexError` 등) 발생 시 정리되지 않고 Chrome 프로세스가 누적
- **수정**: 드라이버 생성 이후 코드를 내부 try/finally로 감싸 `driver.quit()`을
  finally로 이동
- **검증**: mock으로 추출 도중 예외를 강제 발생시켜 `driver.quit()` 호출을 확인
  (검증 스크립트는 정책에 따라 삭제)

### POST URL 파싱·미지원 분기 방어 (이슈 ⑮, PR #33, 2026-07-06)

- **원인**: `get_json_form()`이 `?` 없는 POST URL에서 `None[0]` TypeError로
  크래시, 정규식도 잘못된 이스케이프(`\?`)를 써서 SyntaxWarning(향후 Python
  버전에서 SyntaxError로 승격 예정). `get_scrapy_request()`도 GET/POST 외
  method이거나 POST인데 `payload`가 True/False가 아니면 암묵적으로 `None`을
  반환해 스파이더가 `yield None`
- **수정**: `?` 부재 시 명시적 `ValueError`, 정규식을 raw string으로 전환.
  지원 범위 밖 method/payload 조합도 명시적 `ValueError`. 모든
  `start_requests()` 호출부가 이미 `try/except Exception`으로 감싸고 있어
  새 예외는 조용한 실패 대신 명확한 로그로 처리됨
- **검증**: GET / POST(formdata) / POST(json) 정상 경로 3종 + 신규 예외 3종을
  인터프리터에서 직접 실행해 확인

### 이슈 ⑯(다중 블루프린트 대응) 보류 처리 (PR #35, 2026-07-06)

- blueprint 2건 이상 시 빈 설정으로 기동되는 문제(이슈 ⑯)를, 단건 전제인
  현행 구조를 땜질 수정하는 대신 예정된 다중 블루프린트 업그레이드에서 함께
  재설계하기로 결정 — `ISSUES.md`에 미해결이 아닌 보류로 등록

### 재시작 시 구 워커의 지연 finished 신호 무시 (이슈 ⑰, PR #37, 2026-07-06)

- **원인**: 중지 직후 곧바로 재시작하면, 구 워커의 실제 정리(최대 ~1.3s)가
  끝나기 전에 새 워커가 시작됨. `QThread.wait()`가 메인 스레드 이벤트 루프를
  막는 동안 구 워커의 `finished` 신호가 큐잉됐다가 새 워커 시작 이후 뒤늦게
  도착 — `_on_finished`가 신호 출처를 구분하지 않아, 정상 수집 중인 새
  워커를 "중단됨"으로 되돌려 UI가 되돌아간 것처럼 보임
- **수정**: `_on_finished(task, summary)` 최상단에
  `if self.sender() is not self._worker: return` 가드 추가 — `self.sender()`는
  큐잉된 크로스스레드 연결이어도 실제 emit한 워커 인스턴스를 정확히 반환
- **검증**: 격리된 PyQt6 재현(구 워커 0.6s 지연 vs 신 워커 즉시 교체)으로
  구 워커 신호는 무시, 신 워커 신호는 정상 처리됨을 확인

### GUI 로그에서 내부 [DEBUG] 진단 메시지 제거 (PR #39, 2026-07-06)

- **배경**: URL 샘플 덤프, 자식 프로세스/드레인 내부 상태, `resp_info` 구조
  불일치, URL 불일치 skip, 최종 카운터 요약, 구 워커 신호 관련 메시지 등
  과거 디버깅용 `[DEBUG]` 로그가 사용자 대면 로그 뷰어에 그대로 노출되고
  있었음 — 내부 변수명이 드러나고 사용자가 취할 조치도 없었으며, 로그
  필터(ALL/INFO/OK/WARN/ERR)에도 DEBUG 등급이 없어 숨길 방법도 없었음
- **수정**: 해당 GUI 노출 emit만 제거(내부 `logger.*()` 콘솔/파일 로그는
  그대로 유지), 사용자에게 실질적 의미가 있는 2건(URL 미생성, 시작 시 URL
  개수)은 `[DEBUG]` 태그 없이 평문 로그로 남김

### 수집물별 커스텀 정제 규칙 플러그인 (PR #41, 2026-07-06)

- **배경**: 사이트마다 데이터 형식이 달라 범용 정제 규칙 하나로는 커버 불가
  — 수집물(blueprint)마다 별도 정제 로직을 파일 하나로 꽂아 넣을 수 있게 지원
- **구현**: `preprocess.load_custom_rule(seq_no)` 신설 — 당시엔
  `<앱 데이터 폴더>/custom_rules/{seq_no}.py`에 정의된 `refine(data)` 또는
  `refine_row(row)`를 로드(파일 없으면 `None`, 파일이 깨져 있으면 예외 그대로
  전파해 "규칙 없음"과 구분). `MonitorPageTriggers._run_refine()`에 배선 —
  blueprint의 `seq_no` + `needs_cleaning`이 모두 있을 때만 커스텀 규칙을
  `DataRefiner`의 6개 범용 규칙보다 먼저 적용, 로드/실행 실패 시 원본
  데이터로 폴백하며 로그로 남김(정제 자체는 막지 않음)

### 커스텀 정제 규칙 경로 통일 및 미설정 경고 (PR #42, 2026-07-07)

- **배경**: 이 프로그램은 고객마다 수집 대상·데이터 형식이 달라, 개발자가
  고객별로 `request_info.json`과 정제 규칙을 세트로 준비해 각자의 PC에 심어
  배포하는 구조. PR #41 당시 커스텀 규칙 파일은 `custom_rules/` 서브폴더에
  두고 번들 기본값 시딩(seeding)이 없어, 이미 구축된 `request_info.json`
  배포 방식(`BlueprintStorage`)과 다른 경로 정책을 쓰고 있었음
- **수정 ①(경로 통일)**: `preprocess._app_dir()`가 `request_info.json`과 동일한
  `LOCALAPPDATA/CollectorApp` 경로를 직접 가리키도록 변경. `BlueprintStorage`와
  동일한 seed-on-first-run 패턴(`_resolve_custom_rule_path`) 추가 — 앱 데이터
  폴더에 파일이 없고 번들 리소스 경로(`utility.resource_path()`, 고객별
  패키징에 포함한 기본 규칙)에 기본값이 있으면 최초 1회 복사해 심고, 이후엔
  앱 데이터 폴더 사본을 우선 사용(고객 PC에서 직접 수정 가능)
- **수정 ②(미설정 경고)**: `preprocess.custom_rule_exists(seq_no)` 신설 —
  `load_custom_rule()`과 달리 파일을 `exec`하지 않는 단순 존재 확인. 새
  `MonitorPageTriggers._on_monitor_tab_changed()`를 `tab_widget.currentChanged`에
  연결해 "② 정제 규칙 설정" 탭 진입 시 `needs_cleaning=True`인데 규칙 파일이
  없으면 팝업으로 안내. 같은 수집 결과에 대해 탭을 오가도 반복해서 뜨지
  않도록 `_cleaning_warned` 플래그로 최초 1회만 확인하고, `preprocess(task)`에서
  새 수집 결과가 들어올 때 리셋
- **검증**: 임시 uv venv(Python 3.12) 스크립트로 (a) 경로 해석·시딩(번들 →
  앱데이터 복사 → 이후 앱데이터 우선) 3케이스, (b) 헤드리스 PyQt6로 실제
  `MonitorPage` 인스턴스를 띄워 팝업 게이팅(needs_cleaning=False/규칙 없음/
  반복 방지/리셋/규칙 존재 시 무팝업) 5케이스 확인 (검증 스크립트는 정책에
  따라 삭제)

### 5차 릴리스 (PR #43, 2026-07-07)

- `develop → main` 릴리스 PR 머지: main = `90ef5ab`
  (PR #41 커스텀 정제 규칙 플러그인, PR #42 규칙 파일 경로 통일 + 미설정
  경고 팝업 + HISTORY.md 동기화 포함)
- 로컬 `main`/`develop` 모두 `origin`과 동기화 확인
- 참고: PR #20(4차 릴리스) 이후 `develop → main` 릴리스가 여러 차례(PR #22,
  #24, #26, #28, #30, #32, #34, #36, #38, #40) 있었으나 이 문서에는 개별
  기록되지 않았음 — 각 릴리스가 포함한 기능/수정 내용은 본 문서의 해당
  PR(#19, #21, #23, #25, #27, #29, #31, #33, #35, #37, #39) 항목에 이미
  기록되어 있어 별도 소급 기록은 생략

---

## 현재 브랜치 상태 (2026-07-07 기준)

| 브랜치 | 커밋 | WSL | Windows |
|---|---|---|---|
| `main` | `90ef5ab` (PR #43) | ✅ | 미확인 |
| `develop` | `90ef5ab` (PR #43과 동기화) | ✅ | 미확인 |

미결 사항: Windows 클론의 `git-setup-windows.ps1`이 untracked —
저장소 포함(권장, `git-setup-wsl.sh`의 짝) 또는 `.gitignore` 등록 중 선택 필요.
(2026-07-07 재확인: 여전히 미해결)

