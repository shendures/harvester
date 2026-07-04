# DataCrawler v2.0 (Harvest) — 진행 이력

> `PROJECT_REPORT.md`에서 분리된 작업 이력 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 미해결 이슈·백로그는 `ISSUES.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04 (조사 범위: 전체 소스 코드 약 16,200줄, 문서, Git 이력, 의존성, 보안)
- **최신 갱신**: 2026-07-05

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

---

## 현재 브랜치 상태 (2026-07-05 기준)

| 브랜치 | 커밋 | WSL | Windows |
|---|---|---|---|
| `main` | `f611a65` (PR #12) | ✅ | pull 필요 |
| `develop` | `6389f03` (PR #14) + 본 문서 현행화 PR | ✅ | pull 필요 |

미결 사항: Windows 클론의 `git-setup-windows.ps1`이 untracked —
저장소 포함(권장, `git-setup-wsl.sh`의 짝) 또는 `.gitignore` 등록 중 선택 필요.
