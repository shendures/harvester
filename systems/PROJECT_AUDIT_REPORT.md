# Harvest (DataCrawler v2.0) 심층 조사 및 진행 리포트

- **조사 일자**: 2026-07-03 ~ 2026-07-04
- **조사 범위**: 전체 소스 코드(약 16,200줄), 문서(`systems/`), Git 이력, 의존성, 보안
- **작성**: Claude Code (Fable 5)

---

## 1. 프로젝트 요약

**Scrapy 2.14 크롤링 엔진 + PyQt6 데스크톱 GUI를 결합한 노코드 웹 데이터 수집기.**
사용자는 GUI로 수집 조건을 설정하고, 실시간 모니터링·정제·통계를 거쳐 CSV/DB로 내보낸다.

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
원본 불변·통계 추적 품질 높음. `systems/PROJECT_GUIDE.md` 문서 충실도 높음.

---

## 2. 심층 조사에서 발견된 이슈 (심각도순)

| # | 이슈 | 위치 | 상태 |
|---|---|---|---|
| ① | **리다이렉트 시 수집 결과 전량 skip → total=0** | `worker.py` / `engine.py` | ✅ **해결** (`d469277`) |
| ② | 프록시 활성 시 즉시 AttributeError — `REQUESTS_PER_MINUTE` 정의가 주석 처리됨. 심층 조사 결과 설정 키 불일치로 GUI 경로에서는 프록시 자체가 조용히 무시되고 있었음 | `middlewares.py`, `worker.py`, `customized_settings.py` | ✅ **해결** (PR #5) |
| ③ | 쿠키 랜덤 미들웨어가 dict를 반환 (미들웨어 규약 위반) | `middlewares.py:374` | ⬜ 미해결 |
| ④ | MongoDBPipeline 실행 불가 — `db_conn` import 누락(NameError), `MongoClient` import 주석 처리. CLI `scrapy crawl` 즉시 실패. `set_scrapy_settings()` 예외 삼킴과 연쇄 시 GUI 경로도 위험 | `pipelines.py:133,145` | ⬜ 미해결 |
| ⑤ | `DelaySchedulerMiddleware`는 존재하지 않는 설정 키(`SCHEDULER_MIDDLEWARES`)에 등록되어 로드되지 않음. 내부도 제거된 API(`engine.schedule`)·`DontCloseSpider` 오용 | `settings.py:84`, `middlewares.py` | ⬜ 미해결 |
| ⑥ | `get_response_status()` 취약 필드 접근 — `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 **결과 조용히 유실**, 비표준 상태코드에서 `HTTPStatus()` ValueError | `engine.py` | ⬜ 미해결 |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 → `process.crawl({})` | `engine.py:67-74` | ⬜ 미해결 |

### 문서 vs 코드 불일치

- PROJECT_GUIDE의 request_info.json 예시는 `spiders` 키를 `conditions` 안에 두지만
  실제 파일·코드는 **최상위** 키 사용 (실제 쪽이 정답, 문서 예시 수정 필요)
- `LoadItemPipeline` 등의 f-string 중첩 따옴표 문법은 **Python 3.12+ 전용** —
  PyInstaller 빌드 환경도 3.12+ 필수

### 보안·운영 관찰

- **`env/database.ini`에 실제 API 키 4개 평문 존재** (공공데이터포털, 한국은행,
  OpenDART, IROS). git 미추적 상태이지만, 그 이유가 Python 템플릿 `.gitignore`의
  `env/` 규칙(가상환경용)에 **우연히** 걸렸기 때문 → `.gitignore`에 명시적 등록
  또는 `.env` 이관 권장
- `ROBOTSTXT_OBEY=True`인 반면 봇 UA 행세·랜덤 쿠키·프록시 로테이션 미들웨어가
  공존 — 사용 정책 정리 필요
- **테스트 코드 0개** — `preprocess.DataRefiner`, `utility.generate_combined_urls`가
  테스트 도입 최적 지점
- `frames_tmp.py`(5,796줄)가 git 추적 중 — 가이드 스스로 임시 파일로 명시, 정리 대상
- Scrapy 2.16으로 올리면 sync `start_requests()`가 **에러 없이 무시되어 0건 수집**
  (검증 중 실측) — 업그레이드 시 async `start()` 마이그레이션 필수

---

## 3. 완료된 작업

### 3-1. 리다이렉트 URL 불일치 수정 (`d469277`, 12줄)

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

### 3-2. 저장소 전체 줄바꿈(LF) 정규화 (`e10073c`, `3edb01a`)

- `.gitattributes(eol=lf)` 도입 이전에 CRLF로 커밋된 20개 파일 일괄 정규화
- `git diff --ignore-cr-at-eol` 기준 **내용 변경 0줄** 검증
- 부수 효과로 겪은 "EOL 림보"(CRLF blob + LF 규칙 → 영구 modified 유령 상태)의
  원인·진단·해법을 GIT_GUIDE에 문서화. main/develop 모두 LF blob을 가리키므로
  **재발 없음**

### 3-3. Git 운영 체계 정비 (PR #2, #3)

- GitHub ruleset("PR 필수")과 가이드의 직접 머지 플로우 충돌 발견
  (직접 푸시 시 owner bypass 경고 발생)
- GIT_GUIDE를 **PR 기반 플로우로 개정**: `gh pr create` → `gh pr merge --admin`
  (1인 저장소는 자기 승인 불가로 `--admin` 필요)
- EOL 노이즈 진단법(`git diff --ignore-cr-at-eol`, `git add --renormalize`) 추가

### 3-4. 릴리스 및 멀티환경 동기화 (PR #4)

- `develop → main` 릴리스 PR 머지: main = `0155bfa`
- WSL / Windows 클론 모두 main·develop 동기화 완료, 양쪽 working tree clean 확인

### 3-5. 프록시 rate limit 미들웨어 수정 (이슈 ②, PR #5)

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

### 현재 브랜치 상태 (2026-07-04 기준)

| 브랜치 | 커밋 | WSL | Windows |
|---|---|---|---|
| `main` | `0155bfa` (PR #4) | ✅ | ✅ |
| `develop` | `c1e7b52` (PR #3) | ✅ | ✅ |

미결 사항: Windows 클론의 `git-setup-windows.ps1`이 untracked —
저장소 포함(권장, `git-setup-wsl.sh`의 짝) 또는 `.gitignore` 등록 중 선택 필요.
PR #5(프록시 수정) 머지 후 Windows 클론은 develop pull 필요.

---

## 4. 남은 작업 백로그 (권장 우선순위)

1. **④ MongoDBPipeline import 누락** — CLI 실행 크래시 및 GUI 연쇄 실패 경로 차단
   (`worker.set_scrapy_settings()`의 예외 삼킴 개선 포함)
2. **⑥ `get_response_status()` 방어 코드** — Selenium 응답·비표준 상태코드에서
   결과가 조용히 유실되는 문제
3. **③ 쿠키 미들웨어 반환값** — `return None`으로 1줄 수정
4. **⑤ `DelaySchedulerMiddleware` 정리/재설계** — 존재하지 않는 설정 키에 등록되어
   미로드, 내부도 제거된 API 사용. rate limit 초과 요청의 재시도(지연 재예약)
   설계와 묶어 재검토 (현재는 전 프록시 소진 시 IgnoreRequest로 폐기)
5. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
6. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
7. **정리**: `frames_tmp.py` 제거 여부 결정, PROJECT_GUIDE 예시 JSON 수정,
   미구현 스파이더 타입(⑦) 명시적 예외 처리, GUI 경로에서
   `set_downloader_middlewares()`가 `DOWNLOADER_MIDDLEWARES`를 통째로 교체해
   `LatencyTrackingMiddleware`·`SeleniumMiddleware`가 빠지는 문제 검토

---

