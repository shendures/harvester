# DataCrawler v2.0 (Harvest) — 이슈 및 백로그

> `PROJECT_REPORT.md`에서 분리된 이슈 관리 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 완료된 작업 이력은 `HISTORY.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-07-06

---

## 0. 요약 표 (해결 12건 · 미해결 4건)

| # | 이슈 요약 | 위치 | 상태 |
|---|---|---|---|
| ① | 리다이렉트 시 수집 결과 전량 skip → total=0 | `worker.py` / `engine.py` | ✅ 해결 (`d469277`) |
| ② | 프록시 활성 시 설정 키 불일치로 AttributeError, GUI 경로에서 프록시 무시 | `middlewares.py`, `worker.py`, `customized_settings.py` | ✅ 해결 (PR #5) |
| ③ | 쿠키 랜덤 미들웨어가 미들웨어 규약 위반(dict 반환) | `middlewares.py:349` | ✅ 해결 (PR #21) |
| ④ | MongoDBPipeline import 누락으로 즉시 NameError | `pipelines.py`, `settings.py` | ✅ 해결 (PR #8, 제거) |
| ⑤ | DelaySchedulerMiddleware 잘못된 설정 키·제거된 API 오용으로 미작동 | `settings.py:84`, `middlewares.py` | ✅ 해결 (PR #23) |
| ⑥ | `get_response_status()` None 필드 접근·비표준 상태코드 예외 | `engine.py:161,165` | ✅ 해결 (PR #19) |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 | `engine.py:67-74` | ✅ 해결 (PR #25) |
| ⑧ | `/text()` XPath 추출 깨짐(빈 값/ValueError) | `engine.py:299` | ✅ 해결 (PR #13) |
| ⑨ | 스케줄 기능이 실제 세션 설정과 분리 (UA/쿠키/프록시 무시) | `layout.py:1354`, `trigger.py:1852-1853` | ✅ 해결 |
| ⑩ | `net_rotate` 잔재 키로 프록시 목록 검증 (구버전 스키마) | `trigger.py:1741` | ✅ 해결 |
| ⑪ | 월간 스케줄 등록 시 QTimer OverflowError | `trigger.py:1939-1943, 1988-1989` | ✅ 해결 |
| ⑫ | 스케줄 저장 위치 오류(소스/설치 디렉터리, PyInstaller 시 유실) | `trigger.py:2009,2015,2018`, `layout.py:1346-1347` | ✅ 해결 |
| ⑬ | GUI 경로에서 SeleniumMiddleware 탈락 (이중 렌더링) | `worker.py:459`, `customized_settings.py:224-256` | ⬜ 미해결 |
| ⑭ | spirenderer 드라이버 누수 (`driver.quit()` finally 미사용) | `spiders/spirenderer.py:64-101` | ⬜ 미해결 |
| ⑮ | POST URL에 `?` 없으면 크래시, 미지원 분기 시 암묵적 None 반환 | `engine.py:36-37, 83-133` | ⬜ 미해결 |
| ⑯ | blueprint 2건 이상 시 빈 설정으로 기동, 워커 조용히 사망 | `conf.py:165-183`, `worker.py:92` | ⬜ 미해결 |

> 상세 설명·해결 경위는 아래 §1 표 참고.

---

## 1. 발견된 이슈 (심각도순)

| # | 이슈 | 위치 | 상태 |
|---|---|---|---|
| ① | **리다이렉트 시 수집 결과 전량 skip → total=0** | `worker.py` / `engine.py` | ✅ **해결** (`d469277`) |
| ② | 프록시 활성 시 즉시 AttributeError — 설정 키 불일치로 GUI 경로에서는 프록시 자체가 조용히 무시되고 있었음 | `middlewares.py`, `worker.py`, `customized_settings.py` | ✅ **해결** (PR #5) |
| ③ | 쿠키 랜덤 미들웨어가 이미 쿠키가 있으면 dict를 반환 (미들웨어 규약 위반) | `middlewares.py:349` (`if request.cookies: return request.cookies`) | ✅ **해결** (PR #21 — `return None`으로 수정, Scrapy `process_request` 규약(None/Response/Request) 준수) |
| ④ | MongoDBPipeline 실행 불가 — `db_conn`/`MongoClient` import 누락으로 로드 즉시 `NameError` | `pipelines.py`, `settings.py` | ✅ **해결** (PR #8 — 어떤 정상 경로에서도 미사용이라 복구 대신 **제거**, 기본 `ITEM_PIPELINES`를 `LoadItemPipeline`으로 교체) |
| ⑤ | `DelaySchedulerMiddleware`는 Scrapy에 존재하지 않는 설정 키(`SCHEDULER_MIDDLEWARES`)에 등록되어 로드되지 않음. 내부도 제거된 API(`engine.schedule`)·`DontCloseSpider` 오용 | `settings.py:84`, `middlewares.py` | ✅ **해결** (PR #23 — 등록 키·제거된 API·`DontCloseSpider` 오용 수정, `RateLimitedProxyMiddleware`와 연동해 프록시 소진 요청을 지연 재시도하도록 재설계. 코드 리뷰에서 나온 후속 결함 2건(강제 종료 시 재시도 유실, 재시도 상한 없음)도 병합 전 수정 완료) |
| ⑥ | `get_response_status()` 취약 필드 접근 — `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 **결과 조용히 유실**, 비표준 상태코드에서 `HTTPStatus()` ValueError | `engine.py:161,165` | ✅ **해결** (PR #19 — `ip_address` None 방어, `HTTPStatus()` ValueError를 try/except로 처리) |
| ⑦ | 미구현 스파이더 타입이 빈 dict 반환 → `process.crawl({})` | `engine.py:67-74` | ✅ **해결** (PR #25, `fcd35d6` — 미구현 타입은 `NotImplementedError`, 알 수 없는 타입은 `ValueError`를 명시적으로 raise) |
| ⑧ | **`/text()` XPath 추출 깨짐** — `extract_data_from_root()`가 텍스트 노드에 `node.xpath(".")`를 호출. 일반 문자열 텍스트 노드는 빈 값 반환(**조용한 유실**), `"100"` 등 JSON 파싱 가능한 텍스트는 parsel 1.11이 셀렉터를 json 타입으로 판정해 ValueError → **해당 페이지 추출 전체 실패**. 요소 XPath(`.//h2`)는 정상 (PR #8 검증 중 실측 발견) | `engine.py:299` | ✅ **해결** (PR #13 — `node.root`가 문자열이면 그대로 사용하도록 분기. 검증 중 `@attr` 속성 XPath도 동일 버그였음을 확인, 함께 해결) |
| ⑨ | **스케줄 기능이 실제 세션 설정과 분리** — `SchedulerPage.__init__`이 `SessionSettingsPage()`를 **새로 생성**해 보관. MainWindow가 쓰는 실제 세션 페이지와 다른 객체라서 스케줄 등록 시 읽는 `ua_check`/`cookie_check`는 항상 기본값이고, 사용자가 화면에서 바꾼 UA·쿠키 설정은 무시됨. 스케줄 task에는 `proxy` 키 자체가 없어 **스케줄 수집은 프록시를 절대 사용하지 않음** | `layout.py:1354`, `trigger.py:1852-1853` | ✅ **해결** (`SchedulerPage.session_page`를 `None`으로 초기화하고, `MainWindow.__init__`에서 실제 `SessionSettingsPage` 인스턴스를 주입하도록 변경. `_apply_schedule()`의 `common_fields`에 수동 실행 경로(`_actual_start`)와 동일한 스키마의 `proxy` 딕셔너리를 추가하고, 스케줄 "수정" 시 갱신되는 키 목록에도 `proxy` 포함) |
| ⑩ | **`net_rotate` 잔재 키 검증** — 스케줄 등록 시 프록시 목록 존재 여부를 `BlueprintStorage().read().get("net_rotate")`로 확인하지만, `net_rotate`는 구버전(frames_tmp.py) 스키마의 잔재로 현행 blueprint(request_info.json)에는 존재하지 않는 키. 프록시를 등록해도 항상 "목록 비어 있음"으로 판정 (⑨ 버그로 체크박스가 항상 꺼져 있어 현재는 우연히 도달하지 않을 뿐) | `trigger.py:1741` | ✅ **해결** (`self.session_page._proxy_rows`(현행 스키마)로 교체) |
| ⑪ | **월간 스케줄 등록 시 OverflowError** — `_register_timer`가 남은 시간을 ms로 환산해 `QTimer.start(ms)`에 전달. 30일 = 2,592,000,000ms로 C int 최대값(2,147,483,647)을 초과 → 약 24.8일 이상 남은 스케줄(월간 주기)은 등록 시점에 OverflowError. `mark_done`의 monthly 재등록(+30일)도 동일 | `trigger.py:1939-1943, 1988-1989` | ✅ **해결** (`_MAX_TIMER_MS`(7일) 상한을 두고, 남은 시간이 이를 초과하면 7일 뒤 `_register_timer`를 재호출해 남은 시간을 재계산하는 방식으로 청크 분할. int32 오버플로우 발생 불가) |
| ⑫ | **스케줄 저장 위치 오류** — `_save_schedules_to_json`/`_load_schedules_from_json`이 `self.file_path`(LOCALAPPDATA/CollectorApp — BlueprintStorage와 동일 정책)가 아닌 `self.default_source`(**소스/설치 디렉터리**)에 저장. PyInstaller 빌드 시 `resource_path()`가 임시 폴더(`_MEIPASS`)라서 **스케줄이 실행할 때마다 유실**. `file_path`는 선언만 되고 미사용 | `trigger.py:2009,2015,2018`, `layout.py:1346-1347` | ✅ **해결** (저장은 `self.file_path`(LOCALAPPDATA, 디렉터리 없으면 생성)에, 로드는 `file_path` 우선·없으면 `default_source` 폴백으로 `BlueprintStorage`와 동일한 정책 적용) |
| ⑬ | **GUI 실행 경로에서 `SeleniumMiddleware` 탈락** — `set_scrapy_settings()`가 `DOWNLOADER_MIDDLEWARES`를 `set_downloader_middlewares()` 결과로 통째로 교체하는데, 이 dict에는 settings.py의 `scrapy_selenium.SeleniumMiddleware: 800`이 없음. `html_render` 타입의 `SeleniumRequest`가 일반 요청으로 처리됨. 현재는 spirenderer가 parse에서 자체 Chrome을 다시 띄워 겉으로는 동작하지만 **같은 페이지를 2회 요청(일반 다운로드 + Selenium 렌더)** 하는 구조 | `worker.py:459`, `customized_settings.py:224-256` | ⬜ 미해결 |
| ⑭ | **spirenderer 드라이버 누수** — `driver.quit()`이 try 블록 마지막에 있어 셀렉터 매칭 실패 등 예외 발생 시 Chrome 프로세스가 정리되지 않고 누적됨 (`finally` 이동 필요) | `spiders/spirenderer.py:64-101` | ⬜ 미해결 |
| ⑮ | **POST URL에 `?`가 없으면 즉시 크래시** — `get_json_form()`의 `re.search(".*(?=\?)", url)[0]`가 `None[0]` → TypeError. 같은 줄들이 SyntaxWarning(`"\?"` 잘못된 이스케이프, 향후 Python에서 에러 승격) 유발. 또 `get_scrapy_request()`는 `payload`가 True/False 외의 값이거나 method가 GET/POST 외이면 암묵적으로 `None`을 반환해 스파이더가 `yield None` 하게 됨 | `engine.py:36-37, 83-133` | ⬜ 미해결 |
| ⑯ | **blueprint 2건 이상이면 빈 설정으로 기동 → 워커 조용히 사망** — `request_info.json` 루트 리스트에 항목이 2개 이상이면 unwrap 없이 리스트를 `_validate()`에 전달, `"url" in list`는 항상 False라 검증 실패 → 빈 dict 폴백. 이 상태로 시작하면 `worker.run()`의 `self.task["callback_url"]`(try 밖)에서 KeyError → QThread가 조용히 죽고 UI는 "실행 중"에 고착 | `conf.py:165-183`, `worker.py:92` | ⬜ 미해결 |

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

## 4. 미사용 코드·모듈 (2026-07-06 전수 감사)

> 전 모듈(약 16,000줄) import 그래프·참조 추적 결과. 삭제는 별도 커밋으로 분리 권장.

| 대상 | 내용 |
|---|---|
| **`frames_tmp.py` (5,796줄)** | 어디서도 import되지 않는 구버전 모놀리스(전체 코드의 36%). layout.py/trigger.py로 분리 완료된 임시 백업본. 이슈 ⑩의 `net_rotate` 잔재 스키마 출처 — **삭제 1순위** |
| `spiders/sample.py` | 0바이트 빈 파일 |
| `middlewares.py` | `RandomProxyMiddleware` 완전 미사용. `DonasSpiderMiddleware`/`DonasDownloaderMiddleware`는 startproject 보일러플레이트 (settings에서 None/주석 처리) |
| `engine.py` | `set_requests`, `requests_info`, `make_form_data_for_url_args` 미사용. 주석 처리된 `set_item_loader` 2벌(362-369, 405-422행). 미사용 import: `db_conn`, `dt`, `WebDriverWait`, `EC` |
| `utility.py` | `get_isin_dict`, `_calculate_next_run`, `check_lap_time`, `get_all_nested_keys` 미사용 |
| `items.py` | `DefaultItem`, `StoreItem`, `DonasBatchItem` 미사용 (실사용은 `DonasItem`/`DonasItemLoader`뿐) |
| `customized_settings.py` | `get_settting_frame`, `auth_settings`, `get_session_settings` 미사용 |
| `worker.py:55-60` | `LOG_TEMPLATES` — frames_tmp 시절 가짜 로그 생성용 잔재, 미사용 |
| `create_request_info.py` | 앱에서 import되지 않는 독립 스크립트(DB→request_info.json 생성용)라 유지는 타당. 단 `pickle` import 미사용 |
| `env/create_ini.py`, `env/check_ini_section.py` | 2021년산 일회성 독립 유틸 스크립트 — 유지 여부 선택 |
| `requirements.txt` | `mysqlclient`와 `PyMySQL` 중복 — `db_conn.py`는 `mysql+pymysql`만 사용하므로 `mysqlclient` 불필요 |
| ~~`layout.py:1346`~~ | ~~`SchedulerPage.file_path` 선언만 되고 미사용~~ → **해소** (이슈 ⑫ 해결, 실제 저장 경로로 사용됨) |

## 5. 남은 작업 백로그 (권장 우선순위)

1. ~~**스케줄 기능 복구 (⑨·⑩·⑪·⑫)**~~ → **해소** — SchedulerPage가 실제 SessionSettingsPage
   인스턴스를 주입받도록 수정, `net_rotate` 잔재 검증을 현행 스키마
   (`session_page._proxy_rows`)로 교체, 월간 스케줄 QTimer OverflowError 해소
   (7일 단위 타이머 분할), 스케줄 저장 경로를 `file_path`(LOCALAPPDATA)로 교정
2. **크롤링 경로 견고화 (⑬·⑭·⑮·⑯)** — GUI 경로 `DOWNLOADER_MIDDLEWARES`에
   `SeleniumMiddleware` 포함(또는 spirenderer 이중 렌더링 구조 정리),
   spirenderer `driver.quit()` finally 이동, `get_json_form()` `?` 없는 URL 방어
   + raw string 전환, `get_scrapy_request()` 미지원 분기 명시적 예외,
   BlueprintStorage 다건 리스트 검증 로직 수정 + `worker.run()` KeyError 방어
3. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
4. **`worker.set_scrapy_settings()` 예외 삼킴 개선** — 핵심 설정(`ITEM_PIPELINES`
   교체 등)은 try 밖으로 옮기고, try는 실패해도 진행 가능한 프록시 주입으로 한정
   (④는 해결됐지만 예외 삼킴 구조 자체는 남아 있음)
5. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
6. **정리**: §4 미사용 코드·모듈 삭제 (`frames_tmp.py` 우선),
   GUI DB 내보내기(UI만 존재)의 파이프라인 연결 여부 결정
7. (참고, 낮은 우선순위) **`DelaySchedulerMiddleware`의 `meta.pop('delay_until')` 제자리 변경** —
   동일 Request 객체가 두 번 yield되면 한쪽은 즉시, 한쪽은 지연 후 나가 중복 크롤 가능성.
   현재 모든 spider가 매번 새 Request를 생성하고 `delay_until`을 설정하는 코드도 없어
   당장은 도달 불가한 잠재 리스크 (PR #23 리뷰에서 확인, `middlewares.py:266-278`)
