# DataCrawler v2.0 (Harvest) — 진행 이력

> `PROJECT_REPORT.md`에서 분리된 작업 이력 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 미해결 이슈·백로그는 `ISSUES.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04 (조사 범위: 전체 소스 코드 약 16,200줄, 문서, Git 이력, 의존성, 보안)
- **최신 갱신**: 2026-07-11 20:00

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

### `PREPROCESS.md` 문서 신설 (`1faa6c1`, 2026-07-07)

- PR #41/#42로 구현된 커스텀 정제 규칙 플러그인의 규칙 정리·개발 프로세스
  지침을 `systems/PREPROCESS.md`로 신설 — 범용 규칙 표, 커스텀 규칙 파일
  규약, 개발용 `custom_rules/` 폴더(`request_info.json`과 달리 git 추적)
  정책, 배포 시 레포 루트로 복사하는 워크플로 등을 기록
- `.gitignore`에 `systems/STUDY.md`(개인 학습 노트, HISTORY.md/ISSUES.md와
  별도 관리) 제외 추가
- 직후 `custom_rules/` 개발 폴더 정책 서술을 뺐다가(`3b6ae0b`) 바로
  되돌리는(`d638788`) 왕복이 있었으나 최종 내용은 최초 커밋과 동일(net no-op)

### 6차 릴리스 (PR #45, 2026-07-07)

- `develop → main` 릴리스 PR 머지: main = `7df06b2` (`1faa6c1`/`3b6ae0b`/
  `d638788` 포함 — `PREPROCESS.md` 문서 추가분만 반영, 문서 전용 릴리스)
- 이 릴리스 이후 커밋(`b5721db` 이하, custom_rule 7번째 규칙 승격 등 실제
  코드 변경 포함)은 아직 `main`에 반영되지 않음 — 아래 "현재 브랜치 상태" 참고

### `custom_rules/` 저장소 추적 전환 (`b5721db`, 2026-07-08)

- `PREPROCESS.md` §3.1a 정책에 따라 `custom_rules/000000.py`(샤브올데이
  정제 규칙)와 `custom_rules/__init__.py`를 git 추적 대상으로 전환 — 정제
  규칙은 설정값이 아니라 코드이므로 `request_info.json`(gitignore 대상)과
  달리 이력 관리가 필요하다는 판단

### 로컬 개발 환경 정비 (`6bd7490`~`34cb288`, 2026-07-08)

- Windows 짝 스크립트 `git-setup-windows.ps1`을 저장소에 추가(WSL용
  `git-setup-wsl.sh`의 대응) — 아래 "현재 브랜치 상태"에 있던 기존 미결
  사항(Windows 클론 스크립트 untracked) 해소
- uv 기반 로컬 개발 환경 재현을 위해 `.python-version`/`pyproject.toml`/
  `uv.lock`을 한 차례 추적했다가(`6bd7490`), `requirements.txt`를 유일한
  의존성 출처로 유지하기 위해 다시 추적 해제(`a084d28`)하고 `.gitignore`에
  등록(`4625fd2`) — 파일 자체는 로컬에 남되 git 대상에서만 제외
- `.gitignore`의 uv 커스텀 블록이 pyenv 템플릿의 기존 `.python-version`
  라인과 중복 등록돼 있던 것을 정리(`34cb288`)

### GIT_GUIDE: 커밋/푸시/풀 전 대상 브랜치 명시 규칙 추가 (`c6bb30f`, 2026-07-08)

- §5와 체크리스트에 "실행 전 어떤 브랜치를 대상으로 하는지 사용자에게
  명시적으로 보고" 규칙 추가 — 브랜치가 명백해 보이는 경우에도 사전에
  밝혀 실수를 사후가 아닌 사전에 잡기 위함

### 커스텀 정제 규칙을 `DataRefiner`의 7번째 규칙으로 승격 (`1bfbeef`, `5cc8914`, `3a10fab`, 2026-07-08)

- **배경**: PR #41 도입 당시 커스텀 규칙은 `trigger.py`가 `DataRefiner.run()`
  호출 전 별도 단계로 직접 실행 — 범용 6규칙과 다른 계층에 있어 on/off
  제어나 결과 반영 방식이 비대칭적이었음
- **수정** (`1bfbeef`): `DataRefiner`가 `custom_rule` 콜러블을 생성자로 받아
  `_step_custom_rule()`로 나머지 6규칙보다 먼저 실행하는 "규칙 ⑦"로 흡수.
  `RefineStats`에 `custom_rule_applied`/`custom_rule_error` 필드 추가
  (반환값이 입력과 동일 길이의 list가 아니거나 예외 발생 시 원본 데이터로
  폴백). `layout.py`에 "커스텀 정제 규칙 적용" 체크박스를 추가해 나머지
  6규칙과 동일하게 토글 가능. `trigger.py`의 `_run_refine()`은 이제 규칙
  로드만 담당하고 실행·폴백 판단은 `DataRefiner`에 위임
- **문서화** (`5cc8914`): `PREPROCESS.md`를 이 구조 변경에 맞춰 갱신 —
  2단계 파이프라인 설명을 "7규칙 단일 파이프라인, ⑦이 항상 먼저 실행"으로
  정정, 새 체크박스·`RefineStats` 필드·오래된 줄 번호 참조 갱신
- **리팩터** (`3a10fab`): custom_rule 파일의 경로 해석·시딩·로드 로직을
  `preprocess.py`에서 `conf.CustomRuleStorage`(신설 싱글턴)로 이관 —
  `BlueprintStorage`와 동일한 구조로 통일. 번들 기본 경로도
  `custom_rules/{seq_no}.py`로 수정(기존에는 평탄한 프로젝트 루트를
  가리켜 실제 배치 위치와 불일치했음)
- 부수 효과로 `PROJECT_REPORT.md`의 관련 서술(6규칙→7규칙, 싱글턴 2개→3개)도
  함께 현행화

### fill_null 규칙에 사용자 지정 치환값 지원 (`bda1096`, `155e322`, 2026-07-08)

- **배경**: ③(현 ④) `fill_null` 규칙이 `preprocess.py`에 `"—"`로 하드코딩되어
  있어 사용자가 원하는 치환값(예: `"N/A"`, `"없음"`)을 지정할 수 없었음
- **수정**: `DataRefiner.__init__`에 `fill_value` 인자 추가, `_step_fill_null()`이
  하드코딩 대신 이 값을 사용. GUI는 이미 있던 `drop_columns` 체크박스의
  "옆에 `QLineEdit`" 패턴을 그대로 재사용해 `fill_null` 체크박스 옆에 입력 필드
  추가. 여러 차례 요구사항 조정을 거쳐 최종적으로 **GUI 기본값은 빈 값**(입력
  칸이 처음엔 비어 있고, 지우면 빈 값 치환됨을 안내하는 placeholder만 표시)으로
  결정 — `DataRefiner`를 직접 호출할 때(GUI를 거치지 않는 코드)의 기본값은 이
  시점엔 `"—"`로 유지(이후 `0cda32b`에서 통일, 아래 참고)
- **검증** (WSL uv venv, 헤드리스 PyQt6): 기본값·사용자 지정값·빈 입력 시 폴백
  3케이스 확인
- **문서화** (`155e322`): `PREPROCESS.md`/`PROJECT_REPORT.md`를 이 변경에 맞춰 동기화

### Before/After 비교 탭 좌우 테이블 스크롤·정렬 동기화 (`b6e1a95`, 2026-07-08)

- **배경**: "④ Before/After 비교" 탭의 `cmp_raw_table`/`cmp_ref_table`이 완전히
  독립적으로 동작해, 한쪽을 스크롤하거나 정렬해도 반대쪽은 그대로였음. 사용자
  요청으로 "같은 컬럼·방향으로만 동기화"(행 단위 정합까지는 보장하지 않는) 방식의
  구현 가능성을 먼저 검토한 뒤 승인받아 구현
- **수정**: 두 테이블의 `verticalScrollBar().valueChanged`를 상호 연결(같은 값이면
  재귀 종료). `horizontalHeader().sortIndicatorChanged`도 상호 연결해, 정렬된
  컬럼명을 반대쪽에서 이름으로 찾아 같은 방향으로 `sortByColumn()` 호출 — 컬럼
  인덱스가 아닌 **이름 기반 매칭**(`drop_columns`로 컬럼 구성이 달라질 수 있어서),
  대응 컬럼이 없으면 무시. Raw/Refined는 `remove_duplicate`/`remove_null_row`로
  행 수가 달라질 수 있어 "같은 줄 = 같은 원본 행"은 보장하지 않음
- **검증 중 실제 버그 발견**: Qt `QHeaderView.sortIndicatorSection()`이 한 번도
  정렬한 적 없는 테이블에서 `columnCount()`와 같은 범위 밖 값을 반환하는 경우가
  있어(컬럼 수 변경 후 내부 상태 미갱신), 가드가 `>= 0`만 확인하다가
  `horizontalHeaderItem()`의 `None`에서 크래시. 상한(`< columnCount()`)까지
  확인하도록 수정
- **검증**: 헤드리스 PyQt6 — raw↔ref 스크롤 동기화(양방향), raw↔ref 정렬
  동기화(컬럼명·방향·실제 행 순서), `drop_columns`로 대응 컬럼이 없을 때 안전
  무시, 상호 연결로 인한 무한 재귀 없음(호출 2회로 종료) — 6개 시나리오 PASS

### custom_rules/000000.py 전화번호 정규화 로직 단순화 (`418597f`, 2026-07-08)

- 샤브올데이(seq_no=000000) 커스텀 정제 규칙의 `tel` 필드 정규화 로직을, 자릿수
  기반 재조합(10/11자리 하이픈 삽입)에서 `")" → "-"` 단순 치환으로 교체(사용자
  직접 작성)

### DataRefiner 규칙 넘버링 재배치 및 fill_value 기본값 통일 (`0cda32b`, 2026-07-08)

- **배경**: `preprocess.py`의 순환 숫자 라벨이 `custom_rule`을 ⑦로 표기하면서도
  실제로는 항상 가장 먼저 실행되도록 되어 있어, 코드·문서를 처음 보는 사람에게
  혼란을 줄 수 있는 상태였음(사용자 요청으로 확인 후 재배치)
  - `preprocess.py` 전체(`DataRefiner` docstring·`__init__` Args·`RefineStats`
    필드 주석·`DEFAULT_RULES`·각 `_step_*` 메서드 섹션 주석), `trigger.py` 주석
    1건, `PREPROCESS.md`(다이어그램·규칙 표·섹션 제목), `PROJECT_REPORT.md`
    (요약 문장)의 순환 숫자를 실제 실행/GUI 순서로 재배치:
    `custom_rule`=①, `remove_duplicate`=②, `remove_null_row`=③, `fill_null`=④,
    `trim_whitespace`=⑤, `drop_columns`=⑥, `cast_numeric`=⑦
  - `PREPROCESS.md`의 `preprocess.py`/`trigger.py` 코드 라인 인용(구
    `preprocess.py:111/210/225/228`, `trigger.py:1037/1065-1072`)이 이 세션의
    앞선 `fill_value` 편집으로 몇 줄 밀려 있던 것도 함께 교정
  - `DataRefiner.__init__`의 `fill_value` 파라미터 기본값을 `"—"` → `""`로 변경
    — 이전까지 GUI 기본값(빈 값)과 `DataRefiner` 직접 호출 기본값(`"—"`)이
    달랐던 것을 통일
  - GUI 규칙명·부연 설명 문구 정리(사용자 피드백 반영): "커스텀 정제 규칙 적용"
    부연 설명을 실행 순서 설명 대신 기능 자체에 대한 설명("사용자 정의 정제
    함수를 적용합니다.")으로, `fill_null` 규칙명을 "null → 지정값 치환" →
    "결측값(N/A) 치환"으로, 부연 설명도 "삭제 대상 외 결측값을 지정한 값으로
    대체합니다."로 단순화
- **검증**: 순수 로직 회귀 테스트(`DEFAULT_RULES` 키 순서 불변, `custom_rule`
  최우선 실행 확인, 7규칙 전체 순차 적용 결과 확인, 신규 기본값(빈 값) 반영
  확인), 헤드리스 PyQt6 e2e(`_run_refine()` 회귀 없음, 변경된 GUI 텍스트 반영
  확인) — 주석·문서 전용 변경이라 실행 코드는 한 줄도 바뀌지 않음을 diff로도 확인

### 커스텀 정제 규칙 체크박스 — 규칙 ②~⑤ 자동 연동 (`3b98ac5`, `5a0d665`, 2026-07-08)

- **배경**: "커스텀 정제 규칙 적용"을 켤 때마다 함께 켜는 게 자연스러운 범용
  규칙(②~⑤: `remove_duplicate`/`remove_null_row`/`fill_null`/`trim_whitespace`)을
  사용자가 매번 수동으로 맞춰야 하는 번거로움 — 자동 연동 가능 여부를 먼저
  검토한 뒤 요구사항(양방향 연동, 매번 덮어쓰기)을 확정해 구현
- **최초 구현** (`3b98ac5`): `layout.py`에서 `custom_rule` 체크박스의
  `stateChanged`를 새 핸들러 `trigger.py:_on_custom_rule_toggled()`에 연결 —
  체크 시 ②~⑤를 모두 `True`로, 해제 시 모두 `False`로 강제 설정(토글마다 매번
  사용자의 개별 조정을 덮어씀). ⑥`drop_columns`·⑦`cast_numeric`은 연동 대상 아님
- **수정** (`5a0d665`, 사용자 피드백): "해제 시 ②~⑤도 같이 꺼지는" 동작을
  제거 — `custom_rule`을 켤 때만 ②~⑤를 강제로 켜고(기존과 동일하게 매번
  덮어씀), 끌 때는 ②~⑤ 상태에 아무 영향도 주지 않도록(직전 상태 유지) 변경
- **검증**: 헤드리스 PyQt6 — 수동으로 일부 꺼둔 상태에서 `custom_rule` 재체크
  시 강제로 다시 켜짐, 해제 시 ②~⑤ 상태 불변(직전 상태 유지), ⑥⑦ 비영향,
  `custom_rule`을 건드리지 않으면 수동 조정이 유지됨, `_run_refine()` 회귀
  없음 — 모든 시나리오 PASS

### GUI 중복 알림·더미 데이터 제거 및 layout.py→trigger.py 메서드 이관 (`6943a23`, 2026-07-08)

- **완료 알림 팝업 중복 제거**: `_on_finished()`의 정상 완료 분기에서 바로 위
  `log_manager.append_log("info", "크롤링 완료")`가 이미 로그로 남기는데도
  `QMessageBox.information(self, "success", "수집 완료.")`를 또 띄우고 있어
  중복 — 팝업 삭제(`trigger.py`). 결과 0건 시 뜨는 "수집 결과 없음" 경고
  팝업은 로그에 없는 안내 문구(URL/설정 확인)를 담고 있어 유지. 부수 효과:
  이 팝업이 모달이라 `schedule_page.mark_done()`/`_consume_pending_queue()`
  (다음 대기 스케줄 실행)가 사용자가 팝업을 닫아야 진행되던 구조였는데,
  삭제로 스케줄 연속 실행이 사용자 개입 없이 바로 이어지게 됨
- **세션 설정 프록시 목록 초기 더미 데이터 제거**: `SessionSettingsPage._seed()`
  (`10.0.0.1` 등 4개 샘플 행을 앱 시작 시 항상 채워 넣던 메서드)와 호출부 삭제
  — `_proxy_rows`는 빈 리스트로 시작, 사용자가 "+ 추가"/"Import"로 넣은
  항목만 표시
- **layout.py의 토글/트리거 성격 메서드를 trigger.py Mixin으로 이관**:
  "layout.py = UI 구성, trigger.py = 시그널 이벤트 핸들러(Mixin)" 원칙을
  기준으로 전수 분석한 결과, 5개 메서드가 이 원칙을 위반하고 있음을 확인
  (분석 상세는 대화 로그 참고):
  - `StatisticsPage.reload()` (약 90줄, `QTimer.timeout`에 연결된 데이터
    갱신 로직) → `StatisticsPageTriggers`
  - `SchedulerPage._manage_schedule_task()` (약 730줄, 스케줄 등록/수정
    다이얼로그+제출 핸들러 — 동일 패턴인 `_add_proxy_dialog`/`_add_cred_dialog`는
    이미 trigger.py에 있었음) → `SchedulerPageTriggers`
  - `SessionSettingsPage._proxy_table_context_menu()` /
    `_toggle_proxy_enabled()` / `_on_proxy_item_changed()` (프록시 활성/비활성
    토글 3종 — 호출부인 `_on_proxy_row_clicked()`는 이미 trigger.py에 있어
    같은 기능이 두 파일에 걸쳐 쪼개져 있었음) → `SessionSettingsPageTriggers`
  - 죽은 코드 `SessionSettingsPage.load_ip_list_from_file()`도 함께 제거
    (어디서도 연결되지 않았고, 존재하지 않는 `self.ip_proxy_table`을 참조 —
    호출됐다면 즉시 크래시)
  - orphan import 정리: layout.py에서 `re`/`csv`/`socket`/`defaultdict`/
    `db_conn`/`timedelta` 제거(이관된 코드에서만 쓰이던 것). trigger.py에는
    누락된 `QMenu`/`QSpinBox`/`QDoubleSpinBox`/`QDateEdit`/`defaultdict` 추가
  - **이관 중 실제 버그 2건 발견·수정**: ① `_manage_schedule_task()`의
    `request_info["callback_url"]`이 layout.py 모듈 전역변수를 참조하고
    있어 단순 이동만으로는 `NameError` — `BlueprintStorage().read()`로
    교체(trigger.py 다른 곳의 기존 관례와 동일). ② 위 위젯 import 누락
    — Python은 함수가 "정의된 모듈"의 전역 네임스페이스에서 이름을
    찾으므로, 모듈 간 메서드 이동 시 흔히 놓치기 쉬운 함정
- **검증** (WSL uv venv, Python 3.12, 헤드리스 PyQt6): `MainWindow()` 전체
  인스턴스화(스케줄 페이지가 실제 `SessionSettingsPage` 인스턴스를 쓰는지,
  즉 이슈 ⑨ 수정이 유지되는지 포함) + `reload()` 실측 데이터 갱신 +
  프록시 토글 전 구간(체크박스 클릭/우클릭 메뉴 삭제) +
  `_manage_schedule_task()` 등록/수정 양쪽 다이얼로그 빌드 — 6개 시나리오
  PASS. 검증용 venv/스크립트는 확인 후 삭제

### 수동 수집 완료 시 모니터링-Raw 탭 자동 전환 (`e875d76`, 2026-07-08)

- **배경**: 수집이 끝나도 화면은 사용자가 보고 있던 페이지 그대로 유지되어,
  결과를 보려면 매번 사이드바에서 "모니터링" → "① Raw 수집 결과" 탭을
  수동으로 찾아가야 했음
- **수정**: `MainWindowTriggers._on_finished()`의 정상 완료·결과 0건 분기
  양쪽에 `task.get("job") == "수동 실행"`일 때만 `self.stack`을
  `monitor_page`(index 1)로, `sidebar._btns` 체크 상태를 동기화하고,
  `monitor_page.tab_widget`을 "① Raw 수집 결과"(index 0)로 전환하는 코드
  추가. 스케줄 실행("job"=="스케줄 실행")과 중단(interrupted) 분기는
  그대로 두어 화면 전환 없음 — 무인 실행 중 다른 화면을 보고 있어도 갑자기
  전환되지 않도록 범위를 수동 실행으로 한정(사용자 확인 후 결정)
- **검증** (WSL uv venv, 헤드리스 PyQt6): `MultiprocessWorker.finished`
  시그널을 실제로 emit해 `_on_finished`의 `self.sender()` 가드까지 포함한
  실경로로 수동+성공/수동+0건/스케줄+성공/스케줄+0건/중단 5개 시나리오
  9개 assertion 확인 — 수동 실행 2건만 Raw 탭으로 전환되고 나머지는
  화면 유지됨을 확인. 검증용 venv/스크립트는 확인 후 삭제

### 수집 결과 0건 완료 시 진단 정보(URL 개수·소요시간·skip 건수) 노출 (`4f87aee`, 2026-07-08)

- **배경**: 수집이 완료됐지만 결과가 0건이면 항상 "URL 또는 수집 설정을
  확인하고 다시 시도해 주세요"라는 동일한 안내만 떴음. 실제로는 원인이
  ① URL 생성 자체 실패, ② URL은 생성됐지만 응답이 `url_list`와 매칭 안 돼
  전량 skip, ③ 응답은 받았으나 전부 에러, ④ 정상 응답인데 추출 로직이
  0건 파싱 등으로 갈리는데, 그중 "URL 불일치 skip" 정보는 `worker.py`에
  이미 감지 로직이 있었지만 `logger.warning()`(개발자 로그 파일 전용)만
  써서 실사용자에게는 절대 보이지 않는 상태였음
- **수정**:
  - `worker.py`: `MultiprocessWorker.__init__`에 `_skipped` 카운터 추가
    (URL 불일치 skip만 집계, 중복 응답 skip은 정상 동작이라 제외).
    `_emit_finished(callback_url, url_count)`로 시그니처 변경해 생성된
    URL 개수를 받고, `summary`에 `url_count`/`skipped` 필드 추가
  - `trigger.py`: `_on_finished()`의 0건 완료 분기 로그·팝업 문구에
    "생성 URL {n}개 · URL 불일치 skip {n}건 · 소요 {n}s" 요약 추가
    (소요 시간은 기존 `summary['elapsed']`를 그대로 재사용)
- **검증** (WSL uv venv, 헤드리스 PyQt6): `_handle_line()`의 불일치/중복
  skip 판정 분기별 카운터 증감, `_emit_finished()`가 만든 `summary`의
  `url_count`/`skipped` 값, `_on_finished()`가 그 값을 로그·팝업 텍스트에
  실제로 반영하는지, 수동+0건 시 Raw 탭 자동 전환이 회귀 없이 유지되는지
  — 15개 assertion 확인. 검증 스크립트는 확인 후 삭제

### 7차 릴리스 (PR #47, 2026-07-09)

- `develop → main` 릴리스 PR 머지: main = `c91a435` (GitHub 웹에서 직접 병합 —
  ruleset owner bypass)
- 포함 커밋(`bda1096`~`c1896af`, 15개): fill_null 사용자 지정 치환값, Before/After
  비교 탭 스크롤·정렬 동기화, custom_rules/000000.py tel 정규화 단순화, 커스텀
  정제 규칙 체크박스 ②~⑤ 자동 연동, DataRefiner 규칙 넘버링 재배치 및 fill_value
  기본값 통일, GUI 중복 완료 알림·프록시 더미 데이터 제거, layout.py→trigger.py
  토글/트리거 메서드 이관(+ 죽은 코드 제거), `worker.set_scrapy_settings()` 예외
  흡수 범위 축소, 수동 수집 완료 시 모니터링-Raw 탭 자동 전환, 수집 결과 0건
  완료 시 진단 정보(URL 개수·소요시간·skip 건수) 노출 — 각 항목의 상세 배경·
  수정·검증은 위 개별 항목 참고
- `ISSUES.md`(백로그 ④ 해소 표시, 재확인 날짜 갱신) · `PROJECT_REPORT.md`
  (layout.py/trigger.py/worker.py 줄 수 정정, scrapy-selenium 제거 반영 등
  묵은 오류 정정 포함) 문서 동기화도 이 릴리스 직후 반영

### CODING_GUIDE.md 기준 전체 코드 정리 (`refactor/code-cleanup`, 6개 커밋, 2026-07-10)

- **배경**: `systems/CODING_GUIDE.md` 신설 이후, 기존 코드베이스 전체(파이썬
  약 10,200줄)를 가이드 기준으로 점검·정리. 토큰 소모를 줄이기 위해
  `ruff`로 기계적 위반을 먼저 걸러내고, LLM은 ruff가 못 잡는 네이밍·매직넘버·
  중복·죽은 코드 등 판단이 필요한 부분만 파일 그룹 단위(소형 → 중형 →
  worker/db_conn/conf → layout/style → trigger.py)로 순회하며 처리
- **수정** (커밋 순):
  - `1128e6d`: 전 모듈 미사용 import·주석 처리된 죽은 코드·미사용 지역변수
    제거 + `ruff --fix`로 불필요한 세미콜론(E703)·한 줄 다중 import(E401)
    77건 자동 정리
  - `2aafc38`: ruff가 자동 수정하지 못한 나머지 41건(E701/E702/E712/E721/E722)
    수동 정리 — `engine.py`의 payload 3분기(True/False/None)는 `is True`/
    `is False`로 엄격 비교 유지(단순 진리값 검사로 바꾸면 None 검증이
    무너짐), bare except에는 문맥에 맞는 구체적 예외 타입 지정
  - `c34a87a`: 소형 모듈 12개 파일 — f-string 중첩 따옴표(Python<3.12
    미지원) 제거, 오해 소지 있는 변수명(`digits`→`normalized_tel`) 수정,
    반복되는 매직 넘버(`time.sleep(3)`) 상수화. 변수명 리네임 중
    `request_info["conditions"]["mainUrl"]`처럼 외부 도구
    (`generator_conditions.html`)가 만드는 딕셔너리 키까지 실수로 같이
    바뀔 뻔한 것을 발견해 롤백 — 이후 그룹 작업 시 딕셔너리 키 문자열은
    리네임 대상에서 제외
  - `6a442ba`: `engine.py`/`utility.py` — `get_render_result()`/`get_result()`의
    seq_no·dataFormat 분기에 `else`가 없어 미지원 값 유입 시
    `UnboundLocalError`로 크래시하던 것을 명시적 `ValueError`로 전환(지원
    경로 동작 무변경). 죽은 플래그 인자 함수 `update_slash(reverse=True)`
    제거(호출부 2곳 모두 `reverse=False`만 사용해 `True` 분기가 죽은
    코드였음) → `to_forward_slash()`로 단순화
  - `worker.py`/`middlewares.py`/`db_conn.py`/`conf.py`는 이전 세션들에서
    이미 충분히 정리되어 있어 이번 그룹은 변경 없음(검토만 수행)
  - `51fc797`: `layout.py` — `MonitorPage.preprocess()`의 docstring이
    "FILE/DB로 추출"이라 되어 있었으나 실제로는 정제 단계 진입 전 상태
    준비만 수행(실제 추출은 `_extract_result_table()`)하는 것으로 확인,
    docstring 정정. 주석 처리된 죽은 콜백 연결 2곳, 내용 없는 orphan
    섹션 헤더 제거
  - `122315c`: `trigger.py`에서 함수마다 반복 정의되던 `VALUE_COLORS`(3곳)·
    `DB_PORTS`(2곳, `DB_PORTS_S` 포함) 딕셔너리 리터럴을 모듈 레벨 상수로
    통합. `GlobalToolbar._update_step_ui()`가 `step_circles`/`step_labels`를
    채우는 코드가 `_build()`에 없어 항상 빈 리스트를 순회하는 완전한
    no-op였음을 데이터 흐름 분석으로 확인 후, 메서드·속성과 trigger.py의
    호출부 5곳을 함께 제거(각 호출 지점에 실제 동작하는
    `mw.dashboard._update_step_ui()`가 나란히 있어 동작 변화 없음)
- **의도적으로 보류한 것**: 스파이더 5종(`spihtml`/`spijson`/`spixml`/
  `spirenderer`/`spidetail`)의 `__init__`/예외처리 중복(DRY 위반)은 예정된
  다중 블루프린트 업그레이드(이슈 ⑯ 관련 재설계)와 겹칠 가능성이 높아
  보류. `run_login()`/`get_render_result()`의 고객사별(seq_no) 로직이
  `engine.py`에 하드코딩된 구조, `_manage_schedule_task()`(749줄) 등
  초대형 다이얼로그 빌더 함수 분리는 스타일 정리 범위를 넘는 설계 판단이라
  손대지 않음. `middlewares.py`의 미사용 `Random*Middleware` 클래스들은
  `settings.py`에 토글용 주석으로 남아 있어 의도적 코드로 판단, 유지
- **검증**: 매 커밋마다 `ruff check .`(전체 통과) + 전체 파일 `py_compile`
  통과 확인. 최종적으로 WSL uv venv(Python 3.12) + `QT_QPA_PLATFORM=offscreen`
  헤드리스 PyQt6로 `MainWindow` 실구동 — 페이지 5종 전환, Start/Stop 버튼
  (1000ms 타이머 대기까지 포함해 `GlobalToolbar._update_step_ui` 제거 후
  대시보드 단계 표시가 실제로 전환되는지 실측), 스케줄 작업 추가 다이얼로그
  (`DB_PORTS` 참조 경로), 모니터 테이블 상세보기(`VALUE_COLORS` 참조 경로)
  총 4개 시나리오 PASS. 검증용 venv/스크립트는 확인 후 삭제

### 대시보드 자동 저장 설정 이동 PR #55 되돌림 (`f54507f`, 2026-07-11)

- **배경**: PR #55(`3e30315`)가 "자동 저장 여부/대상(RAW/정제)" 설정을
  `MonitorPage`의 "⚙ 추출 설정" 다이얼로그에서 `DashboardPage` "수집 설정"
  카드로 옮겨 머지됨
- **되돌린 이유**: UI/UX상 사용자에게 혼동을 유발하고 배치가 적절하지 못하다는
  판단 — 별도 PR 없이 `develop`에 직접 revert 커밋으로 반영
- **처리**: 코드는 PR #55 이전 상태(자동 저장 설정이 "⚙ 추출 설정" 다이얼로그에
  위치)로 완전히 복귀. 재설계 여부·시점은 미정

### 자동 저장/자동 저장 대상을 "수집 & 저장 설정" 카드로 재이동 (`ec7f2bf`, 2026-07-11)

- **배경**: PR #55가 UI/UX 혼동으로 revert된 뒤, 같은 기능("수집 시작 전에
  자동 저장 여부·대상을 바로 보이는 곳에 두기")을 다른 배치로 재검토·재시도
- **이번엔 무엇이 다른가**:
  - 별도 "출력 설정" 카드 신설안은 검토 후 폐기 — 기존 `DashboardPage` "수집
    설정" 카드를 **"수집 & 저장 설정"으로 개명**해 재사용(작업 진행 상태
    카드와의 세로 높이 불균형 문제 자체가 발생하지 않음)
  - PR #55가 함께 추가했던 "⚙ 상세 설정" 버튼은 이번엔 **넣지 않음** —
    `MonitorPage`의 "⚙ 추출 설정" 다이얼로그에 이미 FILE/DB 상세 설정
    진입점이 있어 중복으로 판단
- **수정**:
  - `layout.py`: `TagButton` import 추가, 카드 제목 개명, 3번째 행에
    `auto_save_chk`(체크박스) + `auto_src_raw_btn`/`auto_src_ref_btn`
    (RAW/정제 토글) 추가. "정제" 토글에 "마지막으로 설정한 규칙이 그대로
    적용됨" 경고 툴팁 포함(PR #55 원안 그대로 재구현)
  - `trigger.py`: `DashboardPageTriggers`에 `_on_auto_save_toggled`(자동
    저장 꺼짐 시 RAW/정제 토글 비활성화), `_on_auto_save_source_selected`
    (RAW/정제 상호 배타) 신설. `_actual_start()`가 dashboard 위젯 값을
    읽어 `task["extract"]["auto_save"]`/`auto_save_source`에 반영.
    `MonitorPageTriggers._open_output_settings_dialog()`에서 auto_save
    관련 UI 3종과 `_apply_file()`의 커밋 로직 제거 — FILE/DB 상세 설정
    전용으로 정리(단일 위치 원칙, 중복 노출 없음)
- **검증** (WSL uv venv, Python 3.12, PyQt6 6.10.2, 헤드리스): 초기
  상태(자동 저장 꺼짐 → 토글 비활성화)·체크 시 활성화·RAW↔정제 상호
  배타·해제 시 재비활성화·경고 툴팁 존재, `_actual_start()` 실행 시
  `task["extract"]`에 dashboard 값이 정확히 반영되는지(정제 선택 포함),
  다이얼로그 소스에서 auto_save 관련 코드 완전 제거 확인, `MainWindow()`
  전체 인스턴스화 회귀 없음 — 5개 시나리오 PASS, `ruff check` 통과.
  검증용 venv는 확인 후 삭제

### 8차 릴리스 (PR #56, 2026-07-11)

- `develop → main` 릴리스 PR 머지(GitHub 웹 UI가 아닌 `gh pr merge --admin`,
  ruleset owner bypass): main = `e412ee4`
- 포함 커밋(`ec7f2bf`, `499edb0`): 대시보드 자동 저장 설정 재이동("수집 &
  저장 설정" 카드), 해당 경위 HISTORY.md 기록. PR #49~#55(코드 정리,
  모니터링 페이지 개선 3건, 문서 지침 추가, PR #55 이동+revert)도 함께 포함
- 로컬 `main`/`develop` 모두 `origin`과 동기화 확인

### 스케줄 실행 시 자동 저장 미적용 버그 수정 (`trigger.py:2108-2131`, 2026-07-11)

- **배경**: "스케줄링 작업을 통한 수집에서 자동 저장이 기본 설정되어
  있는지" 검토 요청으로 발견 — 스케줄 실행은 무인 실행이라 사람이 수동으로
  "추출"을 누를 수 없으므로, 코드는 스케줄 등록 시 자동 저장을 강제 On으로
  설계한 의도가 있었음(`schedule_info["auto_save"] = True`)
- **원인**: 이 강제 대입이 `extract` 딕셔너리가 아닌 `schedule_info` 최상위에
  쓰여 있어, 실제 자동 저장 여부를 판정하는 `_on_finished()`
  (`task["extract"].get("auto_save")`)가 참조하는 위치와 달랐음. 게다가 바로
  다음 줄 `schedule_info.update(common_fields)`가 `common_fields["extract"]`
  (`file`/`db` 키만 있고 `auto_save`/`auto_save_source` 키 자체가 없음)로
  `extract`를 통째로 교체하면서, 원래 `get_schedule_settings()` 기본값에
  있던 `extract.auto_save`/`auto_save_source` 키까지 함께 사라짐 — 결과적으로
  스케줄 실행이 완료돼도 자동 저장 분기가 항상 스킵되고 있었음(실측 재현으로
  확인). 스케줄 등록 다이얼로그 자체에는 자동 저장을 켜고 끌 UI가 없어
  전적으로 이 하드코딩에 의존하는 구조였음
- **수정**: `_apply_schedule()`의 "등록"·"수정" 두 분기 모두, `extract` 병합이
  끝난 뒤에 `target["extract"]["auto_save"] = True` /
  `["auto_save_source"] = "raw"`를 강제하도록 순서 조정 — 이후 어떤 병합도
  이 값을 덮어쓸 수 없음. `auto_save_source`를 `"raw"`로 고정한 이유는 "정제"를
  선택할 UI가 스케줄 다이얼로그에 없고, 무인 실행에서 리뷰 없이 마지막 정제
  규칙이 그대로 나가는 위험(추출 설정 다이얼로그에서도 지적된 리스크)을
  피하기 위함
- **검증** (WSL uv venv, Python 3.12, PyQt6 6.10.2, 헤드리스): 다이얼로그
  위젯 대신 최소 Qt 위젯으로 대체해 실제 `SchedulerPage._apply_schedule()`을
  직접 호출(저장 경로는 임시 폴더로 리다이렉트해 실사용자 홈 디렉토리 비오염) —
  신규 등록 시 `extract.auto_save=True`/`auto_save_source="raw"` 확인, 기존
  스케줄 수정 시 값 유지 및 다른 필드만 갱신됨 확인, `_on_finished()`가 보는
  최종 `task["extract"]`에서 자동 저장 분기가 실제로 True로 평가됨을 종단
  확인 — 3개 시나리오 PASS, `ruff check` 통과. 검증용 venv는 확인 후 삭제

### 스케줄 정제 자동 저장에 화면 상태 무관 고정 규칙 적용 (`a4c6375`, 2026-07-11)

- **배경**: "스케줄 실행 시 정제 데이터를 저장하려면 정제 규칙을 어떻게
  선택할지" 검토 중, `_run_refine()`이 정제 시 적용하는 규칙이 등록
  시점에 고정되는 게 아니라 **실행되는 순간 MonitorPage "② 정제 규칙
  설정" 탭의 체크박스 상태를 그대로 읽는 구조**임을 확인 — 사람이
  곁에 없는 무인 실행(스케줄)에서는 등록 시점과 전혀 다른(또는 완전히
  무관한 목적의) 규칙이 그대로 적용될 수 있고, 잘못 적용돼도 확인할
  방법이 없다는 근본 리스크로 판단
- **수정**: `_run_refine()`에 `rules_override`/`skip_ui_update` 옵션 추가
  — `rules_override`가 있으면 체크박스·제외 컬럼·치환값 등 화면 상태를
  전혀 읽지 않고 지정된 규칙 dict(및 `DataRefiner` 자체 기본값)만 사용,
  `skip_ui_update=True`면 정제 결과 테이블/요약/비교 탭 갱신과 탭 자동
  전환을 건너뜀(무인 실행 중 화면 방해 방지). 기존 무인자 호출(체크박스
  기반 수동 흐름)은 동작 변화 없음. 모듈 상수 `SCHEDULED_REFINE_RULES`
  신설 — "① 커스텀 정제 규칙 적용" 선택 시 자동 연동되는 조합과 동일
  (①~⑤=True, ⑥⑦=False). `_on_finished()`는 `auto_save_source=="refined"`
  이면서 `task["job"]=="스케줄 실행"`일 때만 `_extract_result_table()`
  호출 전에 이 고정 규칙으로 `_run_refine()`을 선실행 — 수동 실행·RAW
  저장 경로는 그대로
- seq_no별 커스텀 규칙 파일 로딩은 원래도 `task`(blueprint)의
  `seq_no`/`needs_cleaning`으로 결정돼 화면과 무관했으므로 변경 없음
- **검증** (WSL uv venv, Python 3.12, PyQt6 6.10.2, 헤드리스): 실제
  `MonitorPage._run_refine()`을 직접 호출 — 체크박스를 override와 반대로
  세팅해도 고정 규칙만 적용됨(중복·null 행 제거, trim 적용) 확인, 탭
  전환·결과 테이블 갱신이 스킵됨 확인, 인자 없는 기존 호출은 회귀 없이
  체크박스 기반으로 동작 확인. `MainWindow._on_finished()`를 스파이로
  감싸 (스케줄+정제)만 override 경로를 타고 (수동+정제)·(스케줄+RAW)는
  타지 않음을 확인 — 총 3개 시나리오 PASS, `ruff check` 통과. 검증용
  venv는 확인 후 삭제
- **잔여 리스크 기록**: `_run_refine()`의 빈 데이터 경고 모달이 스케줄+
  정제저장 조합에서 이론상 처음 도달 가능해진 점을 `ISSUES.md` 이슈 ⑱로
  등록(현재는 `_on_finished()`의 `total==0` 조기 반환으로 도달 불가, 보류)

### 스케줄 등록 시 자동 저장 대상(RAW/정제) 선택 기능 추가 (`e91c676`, 2026-07-11)

- **배경**: 스케줄 정제 자동 저장이 화면 상태와 무관한 고정 규칙
  (`SCHEDULED_REFINE_RULES`)을 적용하도록 이미 바뀐 덕분에, 스케줄마다
  RAW/정제 중 어느 쪽을 저장할지 사용자가 직접 고를 수 있게 노출해도
  더 이상 리스크가 없다고 판단 — 종전에는 스케줄 다이얼로그에 이 선택
  UI 자체가 없어 `auto_save_source`가 `"raw"`로 하드코딩돼 있었음
- **수정**: `_manage_schedule_task()`의 "Save Setting" 섹션(기존 FILE/DB
  출력 대상 토글 바로 아래)에 RAW/정제 `TagButton` 쌍 추가 — "정제"
  버튼에는 고정 규칙이 적용된다는 안내 툴팁 포함. 등록 모드는
  `output_info["extract"].get("auto_save_source", "raw")`, 수정 모드는
  `existing_extract.get("auto_save_source", "raw")`로 기존 선택값을
  복원(FILE/DB 토글과 동일한 패턴). `_apply_schedule()`의 하드코딩된
  `"raw"` 두 곳(등록/수정)을 이 토글의 체크 상태로 교체 — `auto_save`
  자체(자동 저장 여부)는 계속 무조건 강제 True 유지(스케줄은 항상
  저장해야 하므로 사용자가 끌 항목이 아님). `_on_finished()`/
  `_run_refine()`은 `auto_save_source` **값**만 보고 분기하므로 전혀
  수정하지 않음 — 이전 구현의 안전장치가 그대로 재사용됨
- **검증** (WSL uv venv, Python 3.12, PyQt6 6.10.2, 헤드리스):
  `_manage_schedule_task(sched_task="등록")` 스모크 테스트로 새 위젯
  포함해도 다이얼로그가 예외 없이 빌드되는지 확인, 실제
  `_apply_schedule()` 직접 호출로 RAW/정제 선택이 각각
  `auto_save_source`에 정확히 반영되는지, 기존 스케줄을 수정 모드에서
  반대 값으로 변경 시 정확히 갱신되는지, 수정 모드 진입 시 기존
  선택값이 올바르게 복원되는지 확인 — 4개 시나리오 PASS, `ruff check`
  통과. 검증용 venv는 확인 후 삭제

---

## 현재 브랜치 상태 (2026-07-11 기준)

| 브랜치 | 커밋 | WSL | Windows |
|---|---|---|---|
| `main` | `e412ee4` (PR #56) | ✅ | 미확인 |
| `develop` | `e91c676` | ✅ | 미확인 |

`main`/`develop`이 PR #56 릴리스로 동기화된 뒤, `develop`에 스케줄 자동
저장 버그 수정 + 스케줄 정제 자동 저장 고정 규칙 적용 + 스케줄 자동
저장 대상(RAW/정제) 선택 기능이 추가로 앞서 있음 — 아직 release PR
미실시.

미결 사항: `git-setup-windows.ps1` untracked 건은 `6bd7490`으로 해소됨.

