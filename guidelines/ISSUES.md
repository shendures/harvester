# DataCrawler v2.0 (Harvest) — 이슈 및 백로그

> `PROJECT_REPORT.md`에서 분리된 이슈 관리 문서입니다.
> 프로젝트 구조는 `PROJECT_REPORT.md`, 완료된 작업 이력은 `HISTORY.md` 참고.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-07-13 13:53

---

## 0. 요약 표 (해결 18건 · 미해결 4건 · 보류 2건)

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
| ⑨ | 스케줄 기능이 실제 세션 설정과 분리 (UA/쿠키/프록시 무시) | `layout.py:1366`, `trigger.py:1919-1923` | ✅ 해결 |
| ⑩ | `net_rotate` 잔재 키로 프록시 목록 검증 (구버전 스키마) | `trigger.py:1806` | ✅ 해결 |
| ⑪ | 월간 스케줄 등록 시 QTimer OverflowError | `trigger.py:2013-2015` (`_register_timer`, `mark_done`이 재사용) | ✅ 해결 |
| ⑫ | 스케줄 저장 위치 오류(소스/설치 디렉터리, PyInstaller 시 유실) | `trigger.py:2085, 2090-2091`, `layout.py:1357-1358` | ✅ 해결 |
| ⑬ | GUI 경로에서 SeleniumMiddleware 탈락 (이중 렌더링) | `worker.py:433`, `customized_settings.py:224-256` | ✅ 해결 |
| ⑭ | spirenderer 드라이버 누수 (`driver.quit()` finally 미사용) | `spiders/spirenderer.py:64-101` | ✅ 해결 |
| ⑮ | POST URL에 `?` 없으면 크래시, 미지원 분기 시 암묵적 None 반환 | `engine.py:36-37, 83-133` | ✅ 해결 |
| ⑯ | blueprint 2건 이상 시 빈 설정으로 기동, 워커 조용히 사망 | `conf.py:165-183`, `worker.py:92` | ⏸ 보류 (다중 블루프린트 업그레이드에서 재설계 예정) |
| ⑰ | 중지 직후 즉시 재시작 시 이전 워커의 지연된 finished 신호가 새 워커 상태를 덮어씀 | `trigger.py:2554` | ✅ 해결 |
| ⑱ | 스케줄+정제 자동 저장 조합에서 `_run_refine()`의 빈 데이터 경고가 무인 실행 중 블로킹 모달로 뜰 가능성 | `trigger.py:1046` (`_run_refine`), `_on_finished()`의 `total==0` 분기 | ⏸ 보류 (현재는 도달 불가, 잠재 리스크로 기록) |
| ⑲ | "② 정제 규칙 설정" 탭 [정제 실행] 버튼 클릭 시 `TypeError`가 처리되지 않아 프로세스 abort(프로그램 강제 종료) | `layout.py:763`, `trigger.py:1069` (`_run_refine`) | ✅ 해결 (PR #59) |
| ⑳ | `custom_rules/render/{seq_no}.py` 서브폴더 미이관 — render/refine 분리 리팩터링 중 000010(맥도날드)·000013(네이버) 원본이 삭제만 되고 재이관 안 됨 | `custom_rules/render/`(부재), `conf.py`(`CustomModuleStorage`) | ❌ 미해결 |
| ㉑ | `spirenderer.py`의 `conditions["login"]` 직접 접근이 신규 request_info.json(로그인 키 생략)과 스키마 불일치 → `KeyError` | `spiders/spirenderer.py:73`, `generator_conditions.html:1490` | ✅ 해결 |
| ㉒ | `generator_conditions.html`이 실제 스파이더 라우팅 키 `spiders`를 생성/안내하지 않아 DETAIL+렌더링 등 미구현 조합도 그대로 생성 가능 | `generator_conditions.html`, `engine.py:36-60` | ❌ 미해결 |
| ㉓ | `conditions.pageType`/`steps`/`redirect`, API 모드 `params`가 생성기에서 만들어지지만 백엔드 어디서도 읽지 않는 죽은 필드 | `generator_conditions.html:1360-1414,1454-1472`, `engine.py`, `glean.py` | ❌ 미해결 |
| ㉔ | `items` 딕셔너리의 예약 키(`root`/`detail`/`detail_root`/`main_root`)를 생성기가 일반 Name/Value 목록으로만 받아 힌트가 없음 → 오타 시 조용한 0건 수집 | `generator_conditions.html:558-585`, `spiders/spidetail.py:41-59,80-88`, `spiders/spirenderer.py:69` | ❌ 미해결 |

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
| ⑨ | **스케줄 기능이 실제 세션 설정과 분리** — `SchedulerPage.__init__`이 `SessionSettingsPage()`를 **새로 생성**해 보관. MainWindow가 쓰는 실제 세션 페이지와 다른 객체라서 스케줄 등록 시 읽는 `ua_check`/`cookie_check`는 항상 기본값이고, 사용자가 화면에서 바꾼 UA·쿠키 설정은 무시됨. 스케줄 task에는 `proxy` 키 자체가 없어 **스케줄 수집은 프록시를 절대 사용하지 않음** | `layout.py:1366`, `trigger.py:1919-1923` | ✅ **해결** (`SchedulerPage.session_page`를 `None`으로 초기화하고, `MainWindow.__init__`에서 실제 `SessionSettingsPage` 인스턴스를 주입하도록 변경. `_apply_schedule()`의 `common_fields`에 수동 실행 경로(`_actual_start`)와 동일한 스키마의 `proxy` 딕셔너리를 추가하고, 스케줄 "수정" 시 갱신되는 키 목록에도 `proxy` 포함) |
| ⑩ | **`net_rotate` 잔재 키 검증** — 스케줄 등록 시 프록시 목록 존재 여부를 `BlueprintStorage().read().get("net_rotate")`로 확인하지만, `net_rotate`는 구버전(frames_tmp.py) 스키마의 잔재로 현행 blueprint(request_info.json)에는 존재하지 않는 키. 프록시를 등록해도 항상 "목록 비어 있음"으로 판정 (⑨ 버그로 체크박스가 항상 꺼져 있어 현재는 우연히 도달하지 않을 뿐) | `trigger.py:1806` | ✅ **해결** (`self.session_page._proxy_rows`(현행 스키마)로 교체) |
| ⑪ | **월간 스케줄 등록 시 OverflowError** — `_register_timer`가 남은 시간을 ms로 환산해 `QTimer.start(ms)`에 전달. 30일 = 2,592,000,000ms로 C int 최대값(2,147,483,647)을 초과 → 약 24.8일 이상 남은 스케줄(월간 주기)은 등록 시점에 OverflowError. `mark_done`의 monthly 재등록(+30일)도 `_register_timer`를 재호출하는 동일 경로라 같은 문제 | `trigger.py:2013-2015` | ✅ **해결** (`_MAX_TIMER_MS`(7일) 상한을 두고, 남은 시간이 이를 초과하면 7일 뒤 `_register_timer`를 재호출해 남은 시간을 재계산하는 방식으로 청크 분할. int32 오버플로우 발생 불가) |
| ⑫ | **스케줄 저장 위치 오류** — `_save_schedules_to_json`/`_load_schedules_from_json`이 `self.file_path`(LOCALAPPDATA/CollectorApp — BlueprintStorage와 동일 정책)가 아닌 `self.default_source`(**소스/설치 디렉터리**)에 저장. PyInstaller 빌드 시 `resource_path()`가 임시 폴더(`_MEIPASS`)라서 **스케줄이 실행할 때마다 유실**. `file_path`는 선언만 되고 미사용 | `trigger.py:2085, 2090-2091`, `layout.py:1357-1358` | ✅ **해결** (저장은 `self.file_path`(LOCALAPPDATA, 디렉터리 없으면 생성)에, 로드는 `file_path` 우선·없으면 `default_source` 폴백으로 `BlueprintStorage`와 동일한 정책 적용) |
| ⑬ | **GUI 실행 경로에서 `SeleniumMiddleware` 탈락** — `set_scrapy_settings()`가 `DOWNLOADER_MIDDLEWARES`를 `set_downloader_middlewares()` 결과로 통째로 교체하는데, 이 dict에는 settings.py의 `scrapy_selenium.SeleniumMiddleware: 800`이 없음. `html_render` 타입의 `SeleniumRequest`가 일반 요청으로 처리됨. 현재는 spirenderer가 parse에서 자체 Chrome을 다시 띄워 겉으로는 동작하지만 **같은 페이지를 2회 요청(일반 다운로드 + Selenium 렌더)** 하는 구조 | `worker.py:433`, `customized_settings.py:224-256` | ✅ **해결** — 조사 결과 `scrapy_selenium.SeleniumMiddleware`는 CLI 경로에 등록돼 있어도 실제로는 항상 죽어있는 코드였음: `SELENIUM_DRIVER_EXECUTABLE_PATH=None`이라 `from_crawler`가 매번 `NotConfigured`로 자체 비활성화하고, 설령 경로를 채워도 `scrapy_selenium` 0.0.7이 구버전 Selenium API(`executable_path`/`chrome_options`)로 드라이버를 생성해 고정된 `selenium==4.41.0`에서는 `TypeError`로 크래시(직접 venv에서 시그니처 확인). 실제 렌더링/추출은 이미 `spirenderer.py`가 자체 Chrome 드라이버로 전담하고 있었으므로, GUI 쪽에 미들웨어를 추가 등록(대칭 맞추기)하는 대신 **죽은 의존성 자체를 제거**: `settings.py`에서 `SeleniumMiddleware` 등록과 `SELENIUM_DRIVER_*` 설정 삭제, `engine.get_scrapy_request()`의 `html_render` 분기가 `SeleniumRequest` 대신 일반 `scrapy.Request`를 반환하도록 변경, `requirements.txt`에서 `scrapy-selenium` 제거. CLI/GUI 양쪽 경로가 이제 동일하게 동작하며 이중 요청 가능성도 원천 차단됨 |
| ⑭ | **spirenderer 드라이버 누수** — `driver.quit()`이 try 블록 마지막에 있어 셀렉터 매칭 실패 등 예외 발생 시 Chrome 프로세스가 정리되지 않고 누적됨 (`finally` 이동 필요) | `spiders/spirenderer.py:64-101` | ✅ **해결** — 드라이버 생성(`engine.set_chrome_webdriver()`) 이후 코드를 내부 `try/finally`로 감싸 `driver.quit()`을 `finally`로 이동. 렌더링/추출 중 예외(`IndexError` 등)가 나도 항상 드라이버가 정리됨. mock으로 추출 도중 예외를 강제 발생시켜 `driver.quit()` 호출을 확인 |
| ⑮ | **POST URL에 `?`가 없으면 즉시 크래시** — `get_json_form()`의 `re.search(".*(?=\?)", url)[0]`가 `None[0]` → TypeError. 같은 줄들이 SyntaxWarning(`"\?"` 잘못된 이스케이프, 향후 Python에서 에러 승격) 유발. 또 `get_scrapy_request()`는 `payload`가 True/False 외의 값이거나 method가 GET/POST 외이면 암묵적으로 `None`을 반환해 스파이더가 `yield None` 하게 됨 | `engine.py:36-37, 83-133` | ✅ **해결** — `get_json_form()`에 `?` 존재 여부 사전 검증(`ValueError`로 명시적 실패) 추가, 정규식을 raw string(`r".*(?=\?)"` 등)으로 전환해 SyntaxWarning 제거. `get_scrapy_request()`는 method가 GET/POST가 아니거나 POST인데 `payload`가 True/False가 아닌 경우 각각 `ValueError`를 명시적으로 raise하도록 변경(기존 암묵적 `None` 반환 제거). 모든 `start_requests()` 호출부가 이미 `yield` 지점을 `try/except Exception`으로 감싸고 있어, 새 예외는 크래시 대신 기존과 동일하게 로그로 처리됨. GET/POST(formdata)/POST(json) 정상 경로 3종 + 신규 예외 3종을 인터프리터에서 직접 실행해 검증 |
| ⑯ | **blueprint 2건 이상이면 빈 설정으로 기동 → 워커 조용히 사망** — `request_info.json` 루트 리스트에 항목이 2개 이상이면 unwrap 없이 리스트를 `_validate()`에 전달, `"url" in list`는 항상 False라 검증 실패 → 빈 dict 폴백. 이 상태로 시작하면 `worker.run()`의 `self.task["callback_url"]`(try 밖)에서 KeyError → QThread가 조용히 죽고 UI는 "실행 중"에 고착 | `conf.py:165-183`, `worker.py:92` | ⏸ **보류** (2026-07-06) — 수집 목록 2개 이상을 다루는 다중 블루프린트 지원으로 프로그램을 업그레이드할 계획이 있어, 단건 전제의 현행 구조를 땜질 수정하지 않고 그 업그레이드에서 함께 재설계하기로 결정. 단건 검증 로직 자체는 여전히 유효하므로 별도 조치 없음 |
| ⑰ | **중지 직후 즉시 재시작 시 이전 워커의 지연된 `finished` 신호가 새 워커 상태를 덮어씀** — (사용자 실사용 중 리포트) `_toggle_run()`의 중지 분기는 `self._worker.stop()`(플래그만 세팅, 비동기)만 호출하고 버튼은 즉시 "▶ 시작"으로 복귀 — 실제 서브프로세스 정리는 `worker.run()` 루프가 감지(최대 0.5s) → `_terminate_process()`(최대 ~0.8s) → `finally: finished.emit()`까지 별도로 최대 ~1.3s 더 걸림. 이 창 안에 사용자가 즉시 재시작하면 `_launch_worker()`가 `wait(1500)`의 반환값을 확인하지 않고 새 `MultiprocessWorker`를 만들어 `start()`함. `QThread.wait()`는 메인 스레드 이벤트 루프를 막으므로, 그 사이 emit된 **구(舊) 워커의 `finished` 신호가 큐잉됐다가 새 워커 시작 이후 뒤늦게 처리**됨 — `_on_finished`가 신호 출처를 구분하지 않아 새 워커가 실제로는 정상 수집 중인데도 `global_toolbar.set_running(False)`·`dashboard._update_step_ui(0)`·"수집 중단" 로그로 UI가 되돌아가 **수집이 중간에 막힌 것처럼 보임** | `trigger.py:2554` | ✅ **해결** — `_on_finished(task, summary)` 최상단에 `if self.sender() is not self._worker: return` 가드 추가. `finished`는 항상 시그널/슬롯 연결을 통해 호출되므로 `self.sender()`가 실제 emit한 워커 인스턴스를 정확히 반환하며(큐잉된 크로스스레드 연결 포함), 이미 교체된 워커의 지연 신호는 로그만 남기고 무시. 격리된 PyQt6 재현(구 워커 0.6s 지연 vs 신 워커 즉시 교체)으로 "구 워커 신호는 무시, 신 워커 신호는 정상 처리"를 확인 |
| ⑱ | **스케줄+정제 자동 저장 조합에서 `_run_refine()`의 빈 데이터 경고가 무인 실행 중 블로킹 모달로 뜰 가능성** — 스케줄 실행 시 정제 데이터를 자동 저장하도록 고정 규칙을 적용하는 기능(`SCHEDULED_REFINE_RULES`, `_on_finished()`)을 구현하는 과정에서 발견. `_run_refine()`은 `self._collected_data`가 비어 있으면 `QMessageBox.warning()`(`trigger.py:1046`)을 띄우는데, 이 경로가 스케줄+정제저장 조합에서 처음으로 실제 도달 가능해짐(기존에는 스케줄 자동 저장 자체가 이슈 — 별도 기록 — 로 인해 항상 스킵되고 있어 도달 자체가 안 됐음). 무인 실행 중 사람이 없는 상태로 모달이 뜨면 확인 버튼을 누를 사람이 없어 앱이 사실상 멈춘 것처럼 보일 수 있음 | `trigger.py:1046` (`_run_refine`), `_on_finished()`의 `total==0` 조기 반환 분기 | ⏸ **보류** (2026-07-11) — 현재는 `_on_finished()`가 `summary["total"]==0`이면 정제/자동저장 로직에 도달하기 전에 이미 return하므로 실제로는 도달 불가. 다만 이 조기 반환 조건이 향후 바뀌거나 `_collected_data`가 비정상적으로 비게 되는 다른 경로가 생기면 노출될 수 있어 잠재 리스크로 기록. 조치가 필요해지면 무인 실행 경로에서는 모달 대신 로그만 남기고 조용히 스킵하는 방식으로 전환 권장 |
| ⑲ | **"② 정제 규칙 설정" 탭 [정제 실행] 버튼 클릭 시 프로그램이 강제 종료됨** — (사용자 실사용 중 리포트) `run_btn.clicked.connect(self._run_refine)`처럼 람다 없이 직접 연결되어 있었는데, `QPushButton.clicked` 시그널은 항상 `bool checked` 인자를 슬롯에 전달함. 이 `bool`이 `_run_refine(self, rules_override=None, skip_ui_update=False)`의 첫 파라미터인 `rules_override`로 그대로 들어가 `rules_override is not None` 분기가 참이 되고, 이어지는 `dict(rules_override)`가 `dict(False)`를 호출해 `TypeError: 'bool' object is not iterable` 발생. 이 코드는 `refiner.run()`을 감싸는 try/except(`trigger.py:1122-1126`) 범위 밖이라 예외가 그대로 전파되고, 처리해줄 `sys.excepthook`도 없어 PyQt6가 프로세스를 abort — 패키징된 실행 파일에는 콘솔이 없어 사용자에게는 "정제 실행 클릭 시 프로그램이 그냥 꺼짐"으로 보임. 버튼 클릭 경로와 무관하게 스케줄 자동 저장 경로(`trigger.py:3743`, `_run_refine(rules_override=SCHEDULED_REFINE_RULES, skip_ui_update=True)`)는 시그널이 아닌 직접 호출이라 애초에 영향 없었음 | `layout.py:763`, `trigger.py:1069` (`_run_refine`) | ✅ **해결** (PR #59) — `run_btn.clicked.connect(lambda: self._run_refine())`으로 감싸 시그널의 `bool` 인자가 전달되지 않도록 수정. 수정 전 코드로 버튼 클릭을 재현해 `TypeError` 및 프로세스 abort(exit code 134)를 실제로 확인했고, 수정 후에는 동일 시나리오에서 크래시 없이 정제 결과가 정상 반영됨을 확인. 스케줄 자동 저장 경로도 회귀 없이 정상 동작 확인 |
| ⑳ | **`custom_rules/render/{seq_no}.py` 서브폴더 미이관** — 수집(render, Selenium 자식 프로세스)과 정제(refine, 메인 GUI 프로세스)의 실행 컨텍스트가 달라 `custom_rules/render/`·`custom_rules/refine/`로 분리하는 리팩터링을 진행하던 중, 기존 `custom_rules/000010.py`(맥도날드 전용 `render()`)·`000013.py`(네이버 전용 `login()`)가 git에서 삭제만 되고 `custom_rules/render/`로 재이관되지 않은 채 중단됨. `custom_rules/refine/000000.py`(샤브올데이 정제)만 정상 이관 완료. 현재 `custom_rules/render/` 폴더 자체가 디스크에 존재하지 않음 | `custom_rules/render/`(부재), `conf.py`(`CustomModuleStorage`) | ❌ **미해결** (2026-07-13) — 지금 `request_info.json`에는 seq_no 000010/000013이 없어 즉시 실행에는 영향 없지만, 이 상태로 커밋하면 두 파일의 로직이 이력에서 유실된 채로 남음. `custom_rules/render/000010.py`, `custom_rules/render/000013.py`로 원본 로직을 그대로 재이관 필요 |
| ㉑ | **`spirenderer.py`의 `conditions["login"]` 직접 접근이 신규 request_info.json과 스키마 불일치** — `parse()`가 `conditions["login"]`을 `.get()` 없이 직접 키 접근하는 방식은 리팩터링 이전(`99144ed^`)부터의 관례로, "로그인 없는 사이트도 `login: null`을 명시한다"는 암묵적 스키마 전제가 깔려 있었음. 새로 갱신된 request_info.json(seq_no 000006, 샤브올데이)은 `login` 키 자체를 생략 — uv venv에서 실제 실행해 `KeyError: 'login'` 발생을 재현 확인. `parse()`의 바깥 `except Exception`에 조용히 잡혀 에러 로그만 남고 수집 결과 0건으로 종료됨(크래시는 아님). 원인을 추적해보니 `generator_conditions.html`의 `generatePattern()`이 출력 직전에 null 필드를 지우는 목록(`mainUrl`/`mainFormat`/`headers`/`params`/`items`)에 `login`도 함께 포함돼 있어, 로그인 옵션을 체크하지 않으면 `"login": null`이 아니라 키 자체가 삭제된 채 출력되고 있었음 | `spiders/spirenderer.py:73`, `generator_conditions.html:1490` | ✅ **해결** — 코드 수정(방어적 `.get()`) 대신 기존 관례(②)를 유지하는 쪽으로 결정: `generatePattern()`의 delete-if-null 목록에서 `'login'`을 제외해, 로그인 미사용 시에도 `"login": null`이 항상 명시적으로 출력되도록 수정. `spirenderer.py`는 변경 없음(백엔드가 이미 그렇게 짜여 있었으므로). Python으로 delete-if-null 로직을 재현해 수정 후 `login` 키가 유지됨을 확인 |

| ㉒ | **`generator_conditions.html`이 실제 스파이더 라우팅 키 `spiders`를 생성/안내하지 않음** — 어떤 스파이더 클래스가 실행되는지는 `conditions.accessType`/`pageType`이 아니라 별도의 최상위(또는 conditions 내부) `spiders` 문자열(`html`/`html_render`/`json`/`xml`/`detail`)로만 결정됨(`get_spider()`). 그런데 생성기 출력에는 이 키가 전혀 없어, 사용자가 request_info.json을 조립할 때 수기로 값을 채워야 하고 매핑을 안내해주는 화면도 없음. 특히 DETAIL+렌더링, DETAIL+JSON payload 같은 조합은 `html_render_detail`/`json_detail`/`json_payload_detail`로 이어지는데 이 값들은 `get_spider()`에서 `NotImplementedError`로 명시적으로 막혀 있는 미구현 스파이더라, 생성기 화면만 보고는 실행 불가능한 조합인지 알 수 없음 | `generator_conditions.html`, `engine.py:36-60` | ❌ **미해결** (2026-07-13) — UI에 `spiders` 선택 필드를 추가하거나 accessType/pageType/dataFormat/rendering 조합으로부터 자동 계산해 출력에 포함하고, 미구현 조합 선택 시 경고를 띄우는 개선 필요 |
| ㉓ | **`conditions.pageType`/`steps`/`redirect`, API 모드 `params`가 백엔드 어디서도 읽히지 않는 죽은 필드** — 실제 페이지네이션은 `callback_url` 문자열에 박아넣는 `${page:시작:증가:끝}` 템플릿(`utility.generate_combined_urls`)으로 처리되고, DETAIL 여부도 오직 `spiders` 값("detail")으로만 갈림. `conditions.pageType`/`conditions.steps`를 읽는 파이썬 코드가 전무(grep 전수 확인). `redirect`도 `get_scrapy_request()`가 요청 생성 시 실제로 반영하는 코드가 없음(과거 이슈 ①의 리다이렉트 수정은 응답 meta 처리 쪽이라 이 필드와 무관). API 모드의 `params` 역시 `engine.py`/스파이더 어디서도 읽지 않고, `get_spider()`가 `"api"`라는 accessType/spiders 값 자체를 인식하지 못해 **API 모드로 생성한 JSON은 현재 실행 경로가 아예 없음** | `generator_conditions.html:1360-1414,1454-1472`, `engine.py`, `glean.py`, `utility.py:58` | ❌ **미해결** (2026-07-13) — 사용자가 시간 들여 채워도 동작에 영향 없는 필드라 오해를 유발. 필드 제거 또는 "미구현" 표기, API 모드는 백엔드 구현 여부 결정 필요 |
| ㉔ | **`items` 딕셔너리의 예약 키에 대한 UI 힌트 부재** — 백엔드는 `items.root`(HTML/렌더링 스파이더 필수, `spihtml.py`/`spirenderer.py:69`), DETAIL 페이지의 `items.detail`(+ mainFormat=json이면 `items.detail_root`/`items.main_root`, `spidetail.py:41-59,80-88`)처럼 정해진 이름의 키를 기대하는데, 생성기는 이를 일반 Name/Value 목록으로만 받아 어떤 이름을 써야 하는지 안내가 전혀 없음. 오타·누락 시 `parse()`의 넓은 `except Exception`에 조용히 걸려 에러 로그만 남고 수집 결과 0건으로 종료됨(크래시 아님, ㉑과 동일한 실패 양상) | `generator_conditions.html:558-585`, `spiders/spidetail.py:41-59,80-88`, `spiders/spihtml.py`, `spiders/spirenderer.py:69` | ❌ **미해결** (2026-07-13) — pageType=DETAIL 선택 시 "root"/"detail"/"detail_root"/"main_root" 전용 입력 필드를 별도로 노출해 예약어를 강제하는 개선 필요 |

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
  또는 `.env` 이관 권장 (2026-07-09 재확인: 여전히 명시적 등록 안 됨)
- `ROBOTSTXT_OBEY=True`인 반면 봇 UA 행세·랜덤 쿠키·프록시 로테이션 미들웨어가
  공존 — 사용 정책 정리 필요
- **테스트 코드 0개** — 검증용으로 작성했던 미들웨어 테스트 8건은 검증 완료 후
  정책에 따라 저장소에서 제거됨 (PR #6). `preprocess.DataRefiner`,
  `utility.generate_combined_urls`가 테스트 도입 최적 지점
- `frames_tmp.py`(5,796줄)가 git 추적 중 — 가이드 스스로 임시 파일로 명시, 정리 대상 (2026-07-09 재확인: 여전히 추적 중, 어디서도 import 안 됨)
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
2. ~~**크롤링 경로 견고화 (⑬·⑭·⑮·⑯)**~~ → **⑬·⑭·⑮ 해소, ⑯ 보류**(다중 블루프린트 업그레이드에서 재설계 예정, §1 참고)
3. **보안**: `env/database.ini` 명시적 gitignore 등록(또는 `.env` 이관),
   키 노출 이력 점검
4. ~~**`worker.set_scrapy_settings()` 예외 삼킴 개선**~~ → **해소** (`f00bc77`) —
   핵심 설정(`DOWNLOADER_MIDDLEWARES`/`ITEM_PIPELINES`/`CONCURRENT_REQUESTS`/
   `DOWNLOAD_DELAY`/`DOWNLOAD_TIMEOUT`)을 try 밖으로 옮겨 실패 시 예외가
   그대로 전파되도록 변경, try는 실패해도 진행 가능한 프록시 설정 주입으로 한정
5. **테스트 도입**: `preprocess.py`, `utility.py` 순수 함수부터
   (이슈 ② 검증 시 미들웨어 테스트 8건을 작성해 효용은 확인됨 — PR #5 참고)
6. **정리**: §4 미사용 코드·모듈 삭제 (`frames_tmp.py` 우선),
   GUI DB 내보내기(UI만 존재)의 파이프라인 연결 여부 결정
7. (참고, 낮은 우선순위) **`DelaySchedulerMiddleware`의 `meta.pop('delay_until')` 제자리 변경** —
   동일 Request 객체가 두 번 yield되면 한쪽은 즉시, 한쪽은 지연 후 나가 중복 크롤 가능성.
   현재 모든 spider가 매번 새 Request를 생성하고 `delay_until`을 설정하는 코드도 없어
   당장은 도달 불가한 잠재 리스크 (PR #23 리뷰에서 확인, `middlewares.py:266-278`)
