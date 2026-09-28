# Harvest — 아키텍처 개요 (Architecture Overview)

> 이 문서는 Harvest 크롤링 프로그램의 프로세스 경계·계층 구조·핵심 실행 흐름·설계 원칙을
> 한 곳에 모은 아키텍처 개요입니다. 모듈(.py) 단위 책임과 모듈 간 의존·연동 관계는
> `../MODULE_SPEC.md`, 신규 합류자용 프로젝트 개요·디렉터리 맵은 `project_report.md`, 정제
> 규칙의 세부 근거·호출 경로는 `preprocess.md`에서 각각 관리하므로 중복 없이 이 문서와
> 함께 참고하세요.

- **최신 갱신**: 2026-09-28 (`project_report.md` §2·§4, `preprocess.md` §1의 아키텍처
  콘텐츠를 통합·요약)

---

## 1. 시스템 개요

Scrapy 크롤링 엔진과 PyQt6 GUI를 결합한 데스크톱 웹 데이터 수집 애플리케이션입니다.
GUI에서 코드 없이 수집 조건을 설정하고 실시간 진행 상황을 모니터링하며, 결과를 CSV 또는
DB(MySQL/PostgreSQL/MongoDB)로 내보낼 수 있습니다.

- **엔진**: Scrapy 2.14 · **UI**: PyQt6 · **수집 형식**: HTML(정적/Selenium 렌더링), JSON, XML

---

## 2. 프로세스·계층 구조

GUI와 크롤러는 서로 다른 프로세스에서 실행되며 표준출력(stdout)과 `multiprocessing.Queue`로만
통신합니다.

```
[진입점] main.py → layout/ (Single/Multi 선택은 request_info.json 블루프린트 개수)

[GUI 계층 — 같은 프로세스, 항상 layout → trigger → style 방향]
  layout/*(위젯 트리, 로직 없음) → trigger/*(동작 Mixin, 다중상속) → style.py(테마 QSS)

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

[설정·상태 — GUI 프로세스 전용, 모두 싱글턴]
  conf.py: DataStore / BlueprintStorage(request_info.json 로드·관리) /
    CustomModuleStorage({render,login,refine}/{seq_no}.py 로드)
  customized_settings.py(설정 기본값 팩토리) · scraper/settings.py(Scrapy 자체 설정)

[수집 후 처리] trigger/monitor.py → preprocess.DataRefiner → db_conn.py 또는 파일 저장

[블루프린트 저작 — 앱 실행과 무관한 오프라인 트랙]
  generator_conditions.html(브라우저) → tb_blueprint(DB)
    → create_request_info.py(수동 실행) → request_info.json 재생성
```

---

## 3. 핵심 설계 원칙

① GUI(`layout/trigger`)는 크롤링(`scraper/engine`)을 직접 참조하지 않고 `worker.py` 하나로만
연결됩니다. ② `conf.DataStore`는 GUI 프로세스 전용이며 자식 프로세스와 상태를 공유하지
않습니다(큐 드레인으로만 동기화). ③ `utility.py`는 내부 의존성이 없는 최하위 공용 모듈로
거의 모든 계층이 참조합니다. ④ 사이트별(seq_no) 커스텀 로직(`render`/`login`/`refine`)은
하드코딩 대신 `conf.CustomModuleStorage`가 파일에서 동적 로드하는 플러그인 방식입니다.

---

## 4. 수집 실행 흐름

시작 버튼 클릭부터 결과가 화면에 반영되기까지의 전 과정입니다.

```
① 시작 버튼 → trigger/toolbar.py._actual_start()
     블루프린트+UI 설정 → task 구성 → BlueprintStorage 저장 → start_requested emit
② trigger/main_window.py → MultiprocessWorker(QThread) 기동
     utility.generate_combined_urls()로 URL 목록 생성(${page:...}/${keywords:...} 전개)
③ multiprocessing.Process(run_spider) ── 여기서부터 별도 프로세스(Scrapy 격리 실행)
     engine.get_spider()로 5종 스파이더 중 선택 → CrawlerProcess.crawl()
④ spider.start_requests() → glean.get_grains() → engine.get_scrapy_request()
⑤ [middlewares] UA/쿠키 랜덤화 · 프록시 레이트리밋 · 레이턴시 측정 · 지연 재스케줄
⑥ spider.parse() → engine.get_result() → engine.set_item_loader() → DonasItem
⑦ [pipelines] LoadItemPipeline → print("RESULT_INFO:{...}") → stdout → Queue
⑧ MultiprocessWorker._handle_line() (부모 프로세스, 파싱)
     ├─ DataStore.add_row()
     ├─ new_row.emit()      → Dashboard/Monitor 테이블 갱신
     ├─ progress.emit()     → 프로그레스 바 갱신
     └─ stats_update.emit() → 세션 통계 갱신
```

---

## 5. 정제·저장 흐름

수집 완료(`worker.finished`) 후 `trigger/monitor.py`가 `preprocess.DataRefiner`를 실행합니다.
규칙은 항상 아래 순서로 적용되며(원본 불변, `RefineStats`로 통계 반환), 수동 정제·스케줄
자동 저장 두 경로 모두 동일 파이프라인을 탑니다.

```
① remove_null_row → ② custom_rule(seq_no 플러그인) → ③ trim_whitespace
→ ④ remove_duplicate → ⑤ drop_columns → ⑥ fill_null → ⑦ cast_numeric
```

정제 결과는 "정제 결과"/"Before-After" 탭에 반영되고, `db_conn.save_db()` 또는 CSV/JSON
파일로 저장됩니다(DB 저장 전 `_check_db_connect_info()`로 연결 검증). 규칙별 순서 근거·
호출 경로 2가지(수동/스케줄)의 세부 차이는 `preprocess.md` §1 참고.

---

## 6. 블루프린트 저작 흐름 (오프라인)

앱 실행 흐름과 무관하며 `main.py`/`worker.py`/`engine.py`가 런타임에 호출하지 않습니다.

1. 운영자가 `generator_conditions.html`(서버 없는 순수 브라우저 도구)로 `conditions` JSON
   작성 → 수동으로 `tb_blueprint`에 저장
2. `create_request_info.py` 수동 실행 → `db_conn.read_db_data()` 조회 →
   `request_info.json` 재생성
3. 앱 재시작 시 `conf.BlueprintStorage`가 로드 → `main.py`가 블루프린트 개수로 Single/Multi
   결정

---

## 7. 참고

- **모듈별 상세 기능·의존관계**: `../MODULE_SPEC.md`
- **신규 합류자용 프로젝트 개요·디렉터리 맵**: `project_report.md`
- **정제 규칙 세부 근거·호출 경로**: `preprocess.md`
