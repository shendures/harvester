# DataCrawler v2.0 (Harvest) — 이슈 및 백로그

> `PROJECT_REPORT.md`에서 분리된 이슈 관리 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 완료된 작업 이력은 `HISTORY.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-07-05

---

## 1. 발견된 이슈 (심각도순)

| # | 이슈 | 위치 | 상태 |
|---|---|---|---|
| ① | **리다이렉트 시 수집 결과 전량 skip → total=0** | `worker.py` / `engine.py` | ✅ **해결** (`d469277`) |
| ② | 프록시 활성 시 즉시 AttributeError — 설정 키 불일치로 GUI 경로에서는 프록시 자체가 조용히 무시되고 있었음 | `middlewares.py`, `worker.py`, `customized_settings.py` | ✅ **해결** (PR #5) |
| ③ | 쿠키 랜덤 미들웨어가 이미 쿠키가 있으면 dict를 반환 (미들웨어 규약 위반) | `middlewares.py:349` (`if request.cookies: return request.cookies`) | ⬜ 미해결 |
| ④ | MongoDBPipeline 실행 불가 — `db_conn`/`MongoClient` import 누락으로 로드 즉시 `NameError` | `pipelines.py`, `settings.py` | ✅ **해결** (PR #8 — 어떤 정상 경로에서도 미사용이라 복구 대신 **제거**, 기본 `ITEM_PIPELINES`를 `LoadItemPipeline`으로 교체) |
| ⑤ | `DelaySchedulerMiddleware`는 Scrapy에 존재하지 않는 설정 키(`SCHEDULER_MIDDLEWARES`)에 등록되어 로드되지 않음. 내부도 제거된 API(`engine.schedule`)·`DontCloseSpider` 오용 | `settings.py:84`, `middlewares.py` | ⬜ 미해결 |
| ⑥ | `get_response_status()` 취약 필드 접근 — `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 **결과 조용히 유실**, 비표준 상태코드에서 `HTTPStatus()` ValueError | `engine.py:161,165` | ⬜ 미해결 |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 → `process.crawl({})` | `engine.py:67-74` | ⬜ 미해결 |
| ⑧ | **`/text()` XPath 추출 깨짐** — `extract_data_from_root()`가 텍스트 노드에 `node.xpath(".")`를 호출. 일반 문자열 텍스트 노드는 빈 값 반환(**조용한 유실**), `"100"` 등 JSON 파싱 가능한 텍스트는 parsel 1.11이 셀렉터를 json 타입으로 판정해 ValueError → **해당 페이지 추출 전체 실패**. 요소 XPath(`.//h2`)는 정상 (PR #8 검증 중 실측 발견) | `engine.py:299` | ✅ **해결** (PR #13 — `node.root`가 문자열이면 그대로 사용하도록 분기. 검증 중 `@attr` 속성 XPath도 동일 버그였음을 확인, 함께 해결) |

## 2. 문서 vs 코드 불일치

- ~~`spiders` 키 위치 불일치~~ → **해소** (PR #14): `get_spider()`가 `conditions` 내부를
  우선 조회하고 최상위로 fallback — 현행 request_info.json(최상위)과 문서 §5 예시(내부)
  둘 다 동작
- ~~§5 예시의 `/text()` XPath 미동작~~ → **해소** (PR #13, 이슈 ⑧ 수정)
- `LoadItemPipeline` 등의 f-string 중첩 따옴표 문법은 **Python 3.12+ 전용** —
  PyInstaller 빌드 환경도 3.12+ 필수

## 3. 보안·운영 관찰

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

## 4. 남은 작업 백로그 (권장 우선순위)

1. **⑥ `get_response_status()` 방어 코드** — Selenium 응답·비표준 상태코드에서
   결과가 조용히 유실되는 문제
2. **③ 쿠키 미들웨어 반환값** — `return None`으로 1줄 수정
3. **⑤ `DelaySchedulerMiddleware` 정리/재설계** — 존재하지 않는 설정 키에 등록되어
   미로드, 내부도 제거된 API 사용. rate limit 초과 요청의 재시도(지연 재예약)
   설계와 묶어 재검토 (현재는 전 프록시 소진 시 IgnoreRequest로 폐기)
4. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
5. **`worker.set_scrapy_settings()` 예외 삼킴 개선** — 핵심 설정(`ITEM_PIPELINES`
   교체 등)은 try 밖으로 옮기고, try는 실패해도 진행 가능한 프록시 주입으로 한정
   (④는 해결됐지만 예외 삼킴 구조 자체는 남아 있음)
6. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
7. **정리**: `frames_tmp.py` 제거 여부 결정,
   미구현 스파이더 타입(⑦) 명시적 예외 처리, GUI 경로에서
   `set_downloader_middlewares()`가 `DOWNLOADER_MIDDLEWARES`를 통째로 교체해
   `LatencyTrackingMiddleware`·`SeleniumMiddleware`가 빠지는 문제 검토,
   GUI DB 내보내기(UI만 존재)의 파이프라인 연결 여부 결정
