# 수집 실행 4경로 — 에러 처리·피드백 설계 검토

> 수집 실행 경로(개별 실행·선택 수집·전체 수집·스케줄 실행)별로 에러를 팝업으로 막을지
> 로그로만 남길지가 뒤섞여 있는 문제를 분석한 설계 검토 문서입니다. §4는 이슈 등록 후보를
> `ISSUES.md` §2와 동일한 형식(`위치/상세/사유·필요 조치`)으로 정리해, 착수 결정 시 그대로
> 옮겨 등록할 수 있게 했습니다. 구조는 `PROJECT_REPORT.md`, 완료 이력은 `HISTORY.md`,
> 확정된 미해결 이슈는 `ISSUES.md` 참고.

- **작성일**: 2026-09-23
- **계기**: "자동 저장 설정된 수집 대상의 수집된 데이터가 0건일 경우 자동 저장되지 않도록
  구현" 요청 처리 중, `preprocess()`/`_extract_result_table()`의 "추출 불가" 팝업이
  EXTRACT 버튼이 아닌 자동 호출 경로에서도 뜨는 문제를 수정(작업 트리 변경, 미커밋)했고,
  이어서 "4개 실행 경로 전체에 대해 에러 처리 방향을 다시 설계해달라"는 요청으로 확장됨.
- **조사 방법**: Explore 서브에이전트 3개를 병렬로 투입해 ①4경로의 시작·큐잉·종료 메커니즘,
  ②현재 팝업/트레이/로그 등 피드백 수단 전수, ③실패 유형별 감지·전달·유실 여부를 각각
  조사한 뒤, 핵심 인용 코드를 직접 재확인. 이 문서의 file:line 인용은 모두 재확인을 거쳤음.

---

## 1. 핵심 진단

현재 코드는 "팝업이냐 로그냐"를 **`is_unattended`(또는 `silent`) 불리언 하나**로 결정한다.
이 하나가 서로 다른 세 질문을 뭉뚱그리고 있다.

1. 사람이 지금 화면 앞에 있는가 (모달을 *볼* 수 있는가)
2. 이 통보는 질문인가 알림인가 (모달이 *필요*한가)
3. 계속 진행하면 더 나빠지는가 (멈춰야 하는가)

그리고 이 앱에서 모달은 단순 UX 문제가 아니라 **실행 차단 장치**다. 대기 큐를 꺼내는
`_consume_pending_queue()`가 `_on_finished()`의 **마지막 줄**
(`trigger/main_window.py:258` 단일, `:570` 다중)에 있어서, 그 앞에서 `QMessageBox.exec()`가
뜨면 사용자가 닫을 때까지 다음 순번이 시작되지 않는다. 코드 주석도 이를 명시한다
(`trigger/main_window.py:494-495`): *"전체 수집·스케줄 실행은 '무인 흐름' — 모달을 띄우면
사용자가 닫아줄 때까지 다음 순번이 영영 시작되지 않으므로 트레이 알림만 사용."*

---

## 2. job 상수 정의와 레이아웃 대응

| 상수/리터럴 | 정의 위치 | 값 |
|---|---|---|
| `BATCH_JOB` | `trigger/main_window.py:329` | `"전체 수집"` |
| `SELECT_JOB` | `trigger/main_window.py:330` | `"선택 수집"` |
| `IMMEDIATE_MONITOR_JOBS` | `trigger/main_window.py:332` | `("수동 실행", SELECT_JOB)` |
| `"수동 실행"` | 리터럴, 주입 지점 `trigger/toolbar.py:103` | — |
| `"스케줄 실행"` | 리터럴, 주입 지점 `trigger/main_window.py:78` | — |

**"개별 실행"은 레이아웃에 따라 실제로 다른 job이다.** 단일 레이아웃 툴바의 ▶ 시작은
`"수동 실행"`이지만, 다중 레이아웃에는 툴바 시작 버튼 자체가 없고
(`layout/multi/toolbar.py:25-33`가 `_build_run_controls`를 빈 구현으로 오버라이드)
목록 행의 ▶는 `SELECT_JOB`으로 들어간다(`layout/multi/blueprint_list.py:467`).
`MainWindowTriggersSingle._on_finished`(`trigger/main_window.py:161`)는 단일 레이아웃에서만,
`MainWindowTriggersMulti._on_finished`(`:467`)는 다중 레이아웃에서만 실행되므로,
"개별 실행"의 실제 모습은 job 4종이 아니라 **job 라벨과 실행 성격이 어긋난 상태**다.

---

## 3. 4경로 비교

| 항목 | ①수동 실행 | ②선택 수집 | ③전체 수집 | ④스케줄 실행 |
|---|---|---|---|---|
| 레이아웃 | 단일 전용 | 다중 전용 | 다중 전용 | 단일·다중 공통 |
| 트리거 | 툴바 ▶(`toolbar.py:31`) | 목록 버튼/행 ▶(`blueprint_list.py:374,448`) | "전체 수집" 버튼(`:390`) | `QTimer`→`scheduler.py:288→256` |
| 실행 중 재요청 시 | 기존 워커 **죽이고 교체**(`main_window.py:115`) | 큐 뒤에 append(`:376`) | 큐 뒤에 append(`:376`) | 큐 뒤에 append(`:81`) |
| 대기 큐 사용 | ✗ | ✓ (`_pending_queue`, `layout/window_base.py:24`) | ✓ | ✓ |
| `is_unattended` 판정 | `job=="스케줄 실행"`→**False**(`:188,221`) | `job in ("스케줄 실행",BATCH_JOB)`→**False**(`:496`) | →**True** | →**True** |
| 0건 종료 시 통보 | 모달(`_show_no_data_dialog`) | 모달 | **트레이 알림만** | **트레이 알림만** |
| 자동 저장 `silent` | False (저장 실패 시 `QMessageBox.critical`) | False | True(로그만) | True(로그만) |
| 저장 충돌(덮어쓰기/테이블 존재) 모달 | 실행 중 뜸 | **실행 중 뜸 — N건 순차 실행을 차단** | 사전 확정(모달 없음) | 사전 확정(`schedule_save_type`) |
| 완료 후 화면 전환 | 즉시(`:253-255`) | 즉시(`:564-565`) | **큐가 빌 때만**(`:566-567`) | 없음 |
| 스케줄 재무장 | 해당 없음 | 해당 없음 | 해당 없음 | `_mark_schedule_done`→`scheduler.py:mark_done()` |
| 시작 전 검증 | 페이지 None 체크(로그만, `toolbar.py:57-62`) | 체크 0개→모달; `_build_task` 무방비 | 없음; `_build_task` 무방비 | 없음(등록 시점에만 검증); 블루프린트 소실 시 조용히 활성 블루프린트로 폴백(`scheduler.py:264-268`) |

**②가 가장 위험하다.** 사람이 방금 버튼을 눌렀다는 이유로 `is_unattended=False`인데,
실제 성격은 N건 순차 실행이다. JSON 덮어쓰기 확인(`trigger/monitor.py:1023`)과 DB 테이블
처리 선택(`:1058-1069`)은 `save_type is None`일 때만 뜨는데, `save_type`은 무인 실행에만
주입되므로(`extract_override`가 `is_unattended`일 때만 채워짐) **선택 수집 N건 중 1번째에서
저장 충돌 모달이 뜨면 나머지는 그 모달을 닫을 때까지 시작되지 않는다.**

**③은 반대로 어긋나 있다.** unattended로 분류돼 0건 시 트레이 알림을 쓰는데
(`trigger/main_window.py:510-515`), 사용자는 방금 버튼을 눌러 화면 앞에 있을 가능성이 높다.
3초짜리 트레이 풍선은 오히려 놓치기 쉽다.

**④는 통보 우선순위가 역전돼 있다.** 트레이 알림이 걸린 유일한 케이스가 "0건"인데, 더
치명적인 DB 저장 실패(`trigger/monitor.py:1086`)·자동 저장 예외
(`trigger/main_window.py:555`)는 로그 한 줄로 끝난다. 로그 뷰어는 별도 다이얼로그라 닫혀
있으면 아무도 못 본다.

---

## 4. 이슈 등록 후보 (구조적 결함)

아래 4건은 설계 논의 이전에 **그 자체로 버그**이며, `ISSUES.md` §2 형식(위치/상세/
사유·필요 조치)으로 정리했다. 착수 결정 시 그대로 옮겨 다음 사용 가능한 순번
(현재 최댓값 ㉛ 다음 — ㉜부터)을 붙여 등록하면 된다.

### 후보 A. `interrupted` 플래그가 "사용자 중단"과 "실행 실패" 두 의미로 오버로드됨

- **위치**: `worker.py:144-148`(중단 분기), `:215-220`(`EXECUTOR_STATUS: FAILED` 처리),
  `trigger/main_window.py:173-182`/`482-492`(`_on_finished` interrupted 조기 return)
- **상세**: Scrapy 자체 실행 실패(`ReactorNotRestartable` 등)를 자식이
  `EXECUTOR_STATUS: FAILED`로 보고하면 부모가 `self._running = False`를 세운다
  (`worker.py:219`). 그러면 다음 루프에서 **사용자 중단과 완전히 동일한 분기**로 들어가
  (`worker.py:144-148`) ①큐에 남아 있던 정상 수집 결과가 `_drain_queue()`로 폐기되고,
  ②로그에 사실과 다른 `"사용자에 의해 중단됨"`이 남고, ③`summary["interrupted"]=True`가
  되어 `_on_finished()`가 조기 return하면서 `_mark_schedule_done()`과
  `_consume_pending_queue()`를 모두 건너뛴다. 그 결과 스케줄은 status가 `"실행 중"`으로
  고착돼 앱 재시작 전까지 영구 정지하고, 배치 잔여 태스크는 `_pending_queue`에 남아 있다가
  나중에 다른 작업이 정상 종료될 때 예상치 못한 시점에 실행된다.
- **사유·필요 조치**: `summary`에 `aborted`(실행 실패) 필드를 `interrupted`(사용자 의도)와
  분리해 추가하고, `_on_finished()`의 조기 return 분기를 사용자 중단 전용으로 좁힌다.
  `aborted`는 큐를 비우지 않고 계속 진행하되 §6 심각도 체계의 "치명" 등급으로 통보한다.
  §6 원칙 설계보다 선행돼야 하는 전제 조건 — 이 분리 없이는 심각도 기반 정책 자체가
  성립하지 않는다.

### 후보 B. HTTP 200 + 추출 예외가 "성공"으로 집계됨

- **위치**: `worker.py:287-320`(`_handle_line` 분류 로직), `engine.py:453-458`
  (`build_failure_item`이 `extract_error`를 세팅하는 지점)
- **상세**: `empty_extract = status_code == 200 and not extracted and not extract_error`
  (`worker.py:289`)이므로, 추출 중 예외가 나 `extract_error`가 채워지면 `empty_extract`는
  False가 된다. HTTP는 200이므로 `elif status_code == 200: level = "ok"`
  (`worker.py:318-319`)로 떨어져 `_errors`에 포함되지 않고 `success`에 산입된다. 로그도
  `log_level = "info"`로 `f"{method} {url}"` 한 줄뿐(`:327-328`)이라 예외 내용이 전혀
  노출되지 않는다. 사이트 구조 변경으로 XPath가 전건 깨져도 세션 요약에는 "성공 N건"으로
  표시된다.
- **사유·필요 조치**: 분류 조건을 `extract_error`가 있으면 `empty_extract`와 별도로
  `"warn"`(또는 별도 `extract_error` 레벨)로 분리하고, `_errors`에는 포함하지 않되(응답
  자체는 성공) `success`와는 구분되는 집계 축을 둔다. 어떤 통보 정책을 설계하든 이 감지
  누락이 먼저 해소돼야 한다.

### 후보 C. 선택 수집(SELECT_JOB) 순차 실행 중 저장 충돌 모달이 큐를 차단

- **위치**: `trigger/main_window.py:530-553`(`MainWindowTriggersMulti._on_finished`의
  자동 저장 블록), `trigger/monitor.py:1021-1030`(JSON 덮어쓰기 확인),
  `:1057-1076`(DB 테이블 처리 선택)
- **상세**: `is_unattended = task.get("job") in ("스케줄 실행", BATCH_JOB)`
  (`main_window.py:496`)이라 `SELECT_JOB`은 무인으로 분류되지 않고, `extract_override`도
  `is_unattended`일 때만 주입되므로(`:548`) `save_type is None`이 되어 `_extract_result_table()`
  내부의 두 확인 모달이 그대로 실행된다. `_start_batch()`가 선택된 N건을 순차 실행하는
  구조이므로(`:358-401`), 1번째 저장에서 모달이 뜨면 2번째 이후는 사용자가 그 모달을 닫을
  때까지 시작되지 않는다. `main_window.py:494-495`의 주석이 경고한 문제가 선택 수집에는
  그대로 남아 있다.
- **사유·필요 조치**: §6 원칙 2(모달 허용 여부를 job 이름이 아니라 "단건 유인 실행"인지로
  판정)를 적용하면 자동으로 해소된다. 임시 조치로는 `task.get("batch_meta", {}).get("total", 1) > 1`
  이면 `SELECT_JOB`도 무인 취급해 저장 방식을 사전 확정(`schedule_save_type` 없으면 "new"
  기본값)하도록 좁힐 수 있다.

### 후보 D. 정제 경로에 "EXTRACT 버튼일 때만 팝업" 원칙이 미적용

- **위치**: `trigger/monitor.py:967-980`(`_extract_result_table`의 refined 분기),
  `:248-276`(`_run_refine`)
- **상세**: `_extract_result_table(source="refined")`가 아직 정제되지 않았고 `silent=False`면
  내부에서 `self._run_refine()`을 인자 없이 호출한다(`monitor.py:969` 부근 —
  `notify_empty` 파라미터가 이 호출에는 전달되지 않음). `_run_refine()`은 `skip_ui_update`
  기본값이 `False`라서, `_collected_data`가 비어 있으면 `"정제 불가"` 경고
  (`monitor.py:275`)를, 정제 실행 중 예외가 나면 `"정제 오류"` critical
  (`:327`)을 띄운다. 이 폴백 호출은 자동 저장 경로(수동 실행의 refined 자동 저장 등)에서도
  일어날 수 있어, 최근 커밋(`449f190`)과 작업 트리 변경이 세운 "EXTRACT 버튼 클릭 시에만
  팝업" 원칙과 정면으로 충돌한다. `monitor.py:975` 주석(`# else: _run_refine()이 이미
  "정제 불가" 경고를 띄웠음`)이 이를 의도된 동작으로 명시하고 있어, 원칙이 최신 변경
  이전 상태로 남아 있는 지점임이 코드에 드러난다.
- **사유·필요 조치**: `_extract_result_table()`에 이미 있는 `notify_empty` 파라미터를
  이 폴백 호출에도 전파하거나(`self._run_refine(skip_ui_update=not notify_empty)` 등),
  `_collected_data`가 비어 있고 `notify_empty=False`인 경우엔 폴백 호출 자체를 생략하고
  로그만 남기도록 좁힌다. 직전 작업(자동 저장 시 "추출 불가" 팝업 제거)의 자연스러운
  다음 단계.

---

## 5. 참고: 심각도가 감지되지 않거나 트레이 알림이 없는 지점

이 문서 §4의 4건 외에, 설계 단계에서 함께 고려할 관찰 사항(버그로 단정하기보다 정책
공백에 가까움 — 필요 시 별도 이슈로 승격):

- **비모달 지속 상태 부재**: `_update_step_ui()`는 실패해도 그냥 0(수집 대기)으로 돌아가고,
  `BLUEPRINT_STATUS_LABELS`(`layout/multi/blueprint_list.py:21`)에는 `"done"` 키조차 없어
  완료/실패가 모두 "대기"로 표시된다. 모달을 걷어내려면 받아줄 비모달 채널(배지·배너)이
  먼저 있어야 하는데, 지금은 없다.
- **무인 실행의 심각한 실패에 트레이 알림 없음**: 트레이 알림은 "0건" 하나에만 연결돼
  있고(`main_window.py:198-203,510-515`), DB 저장 실패·자동 저장 예외는 로그 한 줄뿐이다.
- **자식 프로세스 행(hang) 감지 로직 전무**: 전체 수집 타임아웃도, 마지막 메시지 이후
  무응답 워치독도 없다(`worker.py` 전체 확인). Selenium 세션이 멈추면 GUI가 "수집 중"에
  영구 고착되고 수동 중지 외 복구 경로가 없다.
- **전역 예외 훅 부재**: `main.py`에 `sys.excepthook` 등이 없어(grep 0건), Qt 슬롯 안에서
  포착되지 않은 예외는 사용자에게 어떤 형태로도 표시되지 않는다.

---

## 6. 설계 원칙 제안

### 원칙 1 — 모달은 "질문"에만 쓴다

현재 모달 대부분(`"추출 불가"`, `"정제 불가"`, `"수집 결과 없음"`, `"DB 저장 실패"`,
`"정제 오류"`)은 질문이 아니라 통보다. 사용자가 OK를 누르는 것 외에 할 일이 없다면
비모달 채널로 내린다. 진짜 질문(덮어쓰기 확인, DB 테이블 처리 선택)은 **실행 중에 물으면
안 되는 질문**이므로(큐 차단, 후보 C 참고), 스케줄의 `schedule_save_type`처럼 실행 전에
사전 확정한다.

> 질문은 실행 전에, 통보는 실행 후에.

### 원칙 2 — 모달 허용 여부를 job 이름이 아니라 실행 성격으로 판정

지금은 단일/다중이 `is_unattended` 정의를 다르게 쓰고(`main_window.py:188` vs `:496`),
`SELECT_JOB`은 `open_save_path`라는 또 다른 축으로 별도 처리된다(`:550`). job 문자열이
늘어날 때마다 분기가 증식하는 구조다. 이미 존재하는 데이터로 판정을 단순화한다:

```
모달 허용 = 사람이 직접 시작했고(task_nm 없음) AND 단건 실행이다(batch_meta.total <= 1)
```

- 수동 실행 → 허용 (단건, 후속 없음)
- 행 ▶ 개별 실행 → 허용 (`batch_meta.total == 1`)
- 선택/전체 수집 N건 → 차단 (N>1이면 무조건)
- 스케줄 → 차단 (`task_nm` 보유)

job 라벨 4개가 아니라 "단건 유인" vs "그 외" 2분류로 줄어들고, `silent`/`notify_empty`/
`skip_ui_update` 3개로 갈라진 현재 가드를 이 하나로 수렴시킬 수 있다.

### 원칙 3 — 심각도 3단계로 "멈출 것/기록할 것"을 가른다

| 등급 | 정의 | 판단 기준(예) | 유인 단건 | 순차 실행 | 스케줄(무인) |
|---|---|---|---|---|---|
| 치명(aborted) | 실행 자체가 성립 안 됨 | Scrapy 기동 실패(후보 A), 블루프린트 소실 | 모달 | 배너 + 큐 계속 여부 검토 | **트레이 알림** |
| 실패(failed) | 이번 건 산출물 없음 | 0건, 저장/정제 실패 | 상태 배너 | 배지 + 큐 계속 | **트레이 알림** |
| 열화(degraded) | 산출물은 있으나 품질 저하 | 일부 요청 실패, 추출 예외(후보 B), 규칙 미적용 | 로그 + 행 표식 | 로그 + 행 표식 | 로그만 |

현재는 무인 실행의 "실패" 등급에 트레이 알림이 없다(0건에만 있음). 수집은 됐는데 저장이
안 된 쪽이 더 치명적이므로 이 부분을 뒤집는다.

### 원칙 4 — 순차 실행은 건별 통보 대신 종료 요약

전체 수집 10건 중 3건이 0건이면 지금은 로그에 흩어진 3줄이 전부다. `_pending_queue`가
빌 때 "10건 중 7건 성공 · 2건 0건 · 1건 저장 실패" 형태의 요약을 한 번 내면 건별 통보보다
유용하고 모달 압력도 준다. `batch_meta`에 이미 index/total이 있어 집계 지점은 확보돼 있다.

---

## 7. 권장 착수 순서

1. **1순위 — 설계 이전에 고쳐야 할 버그**: 후보 A(`interrupted`/`aborted` 분리),
   후보 C(선택 수집 저장 충돌 모달 제거)
2. **2순위 — 설계 정립**: 원칙 2(모달 판정 기준 통일), 원칙 1(통보성 모달 → 배너/배지
   이관, 단 받아줄 채널을 §5 관찰사항대로 먼저 준비)
3. **3순위 — 관측성**: 후보 B(`extract_error` 오집계 수정), 후보 D(정제 경로 원칙 적용),
   원칙 3·4(심각도 체계, 배치 종료 요약)

---

## 8. 관련 변경 이력

- `449f190` — 수집 모니터링 테이블 행 클릭 시 추출 오류 안내 팝업 제거(동일 원칙의 선행 사례)
- 작업 트리 변경(미커밋, 이 문서 작성 시점) — `layout/single/monitor.py`(`preprocess()`
  단순화, `_SILENT_JOBS` 제거), `layout/multi/monitor.py`(동일), `trigger/monitor.py`
  (`_extract_result_table()`에 `notify_empty` 파라미터 추가), `trigger/main_window.py`
  (자동 저장 호출 2곳에 `notify_empty=False` 추가) — "빈 데이터" 케이스에 한해 원칙 1을
  선적용한 것으로, 후보 D가 지적하듯 정제 경로에는 아직 미적용.
