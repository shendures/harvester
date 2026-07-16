# 데이터 정제 (`preprocess.py`) — 규칙 정리 및 개발 지침

> 수집된 raw 데이터를 정제하는 로직(`preprocess.py`)에 대한 규칙 설명과
> 개발 프로세스 지침을 정리한 문서입니다. 구현 이력은 `HISTORY.md`(PR #41,
> #42, 스케줄 자동 정제는 `a4c6375`/`e91c676`), 이슈 상태는 `ISSUES.md` 참고.

- **최신 갱신**: 2026-07-17 02:38

---

## 1. 정제 파이프라인 개요

`DataRefiner`가 7개 규칙을 모두 소유하고 순차 적용합니다. 커스텀 규칙(`custom_rule`,
seq_no별 플러그인)은 **②번 규칙**으로, 완전 공백 행을 미리 걸러내는 ①remove_null_row
바로 다음, 나머지 범용 규칙(중복 제거 등)보다는 먼저 실행됩니다 — 사이트별 원시
데이터를 정규화한 뒤, 그 위에서 나머지 범용 규칙을 적용하기 위함
(`preprocess.py:110` 주석 참고).

> **순서 재배치 이력**: 2026-07-16에 ②~⑦(당시 번호 기준) 순서를 한 차례 재배치했고,
> 2026-07-17에 만 건 이상 규모 처리 시 메모리 절감을 위해 `custom_rule`을 맨 앞이
> 아닌 ②번으로(①remove_null_row만 앞에 둠) 재배치하면서, `trim_whitespace`↔
> `remove_duplicate` 순서도 함께 조정했습니다. 이전 순서/번호는 `HISTORY.md` 참고.

```
raw 수집 데이터
    │
    ▼
DataRefiner.run()
    ├─ ① remove_null_row   (계산량이 가벼워 가장 먼저 실행 — ②의 처리 대상도 줄임)
    ├─ ② custom_rule       (seq_no별, 있고 활성화된 경우에만 — ①을 제외한 나머지보다 먼저 실행)
    ├─ ③ trim_whitespace   (④보다 먼저 실행 — 공백만 다른 값도 동일 값으로 인식돼 중복 판정에 걸리도록)
    ├─ ④ remove_duplicate  (행 전체 정렬·비교라 상대적으로 비쌈 — ②③을 거쳐 정규화·trim된 뒤 실행)
    ├─ ⑤ drop_columns      (④까지의 중복 판정 기준은 원본 전체 컬럼 유지 — 그 뒤·⑥⑦보다는 먼저
    │                        실행해 이후 단계가 불필요한 컬럼을 순회하지 않도록 함)
    ├─ ⑥ fill_null
    └─ ⑦ cast_numeric
    │
    ▼
정제된 데이터 + RefineStats
```

`custom_rule` 단계가 실제로 실행되려면 두 조건을 모두 만족해야 합니다:
1. `trigger.py`의 `_run_refine()`이 `needs_cleaning=True`이고 `seq_no`가 있는 수집에
   한해 `load_custom_rule(seq_no)`로 규칙 함수를 로드해 `DataRefiner(custom_rule=...)`에
   전달 (파일이 없거나 로드 실패 시 `None` 전달, §3.3 참고).
2. `DataRefiner.rules["custom_rule"]`이 켜져 있어야 함 — GUI "② 정제 규칙 설정" 탭의
   "커스텀 정제 규칙 적용" 체크박스로 나머지 6개 규칙과 동일하게 개별 on/off 가능
   (`layout.py:518-526` `_refine_rules`, 기본값 `True`).

둘 중 하나라도 해당 안 되면(파일 없음 / 체크박스 꺼짐) 이 단계는 조용히 건너뛰고
범용 6규칙만 적용됩니다.

**체크박스 자동 연동** (`trigger.py:949-960` `_on_custom_rule_toggled`): "커스텀
정제 규칙 적용" 체크박스를 켤 때마다 ①③④⑥(`remove_null_row`/`trim_whitespace`/
`remove_duplicate`/`fill_null`)가 자동으로 켜집니다(사용자가 개별적으로 꺼둔
상태여도 매번 덮어씀). 해제할 때는 ①③④⑥에 영향을 주지 않고 직전 상태를 그대로
둡니다 — 커스텀 규칙이 정규화한 데이터에는 기본 위생 규칙(중복/결측 정리 등)이
항상 함께 돌도록 하기 위한 편의 기능입니다(단, ①remove_null_row는 예외적으로
`custom_rule`보다 먼저 실행되므로 "정규화 이후"는 아니지만, 완전 공백 행 제거는
정규화 여부와 무관하다고 판단해 함께 묶임). ⑤`drop_columns`·⑦`cast_numeric`은
연동 대상이 아닙니다.

### 1.1 실행 트리거: 수동 정제 vs 스케줄 자동 저장

`_run_refine(rules_override=None, skip_ui_update=False)`(`trigger.py:963`)는
두 가지 경로로 호출됩니다 — ①~⑦ 파이프라인 자체는 동일하고, 차이는 규칙
활성화 값의 출처와 UI 갱신 여부뿐입니다.

- **수동 정제** (GUI "② 정제 규칙 설정" 탭의 [정제 실행] 버튼,
  `layout.py:789-791`): `rules_override=None` — 화면 체크박스(`_refine_rules`)·
  `self._drop_column_names`(§2.2 다이얼로그의 [적용] 시점에 갱신됨)·`fill_null_input`
  값을 그대로 읽어 `DataRefiner`를 구성합니다(`trigger.py:982-997`). 결과는
  Raw/Refined 결과 테이블과 §2.1의 Before/After 비교 탭에 반영되고, 탭이 자동 전환됩니다.
- **스케줄 자동 저장** (`trigger.py:3732-3744`, `_on_finished()` 내부):
  무인 실행이라 화면 체크박스를 사람이 확인·조정할 수 없으므로,
  `task["extract"]["auto_save_source"] == "refined"`이고
  `task["job"] == "스케줄 실행"`일 때만 화면 상태를 완전히 무시하는 고정
  규칙 `SCHEDULED_REFINE_RULES`(`trigger.py:71-79` — ①②③④⑥=True, ⑤⑦=False,
  "커스텀 정제 규칙 적용" 체크 시 자동 연동되는 조합과 동일)로
  `rules_override=SCHEDULED_REFINE_RULES, skip_ui_update=True`를 호출합니다.
  `skip_ui_update=True`이면 결과 테이블·비교 탭 갱신과 탭 자동 전환을 모두
  건너뜁니다(`trigger.py:1050-1057`) — 무인 실행 중 화면이 갑자기 바뀌는
  것을 방지하기 위함입니다.

관련 잠재 리스크는 `ISSUES.md` 이슈 ⑱(보류) 참고.

---

## 2. 범용 정제 규칙 (`DataRefiner`, ①~⑦)

`preprocess.DataRefiner`가 아래 순서대로 적용합니다. **순서를 바꾸면 결과가
달라지므로 임의로 바꾸지 않습니다** (`preprocess.py:110` 주석 참고). 커스텀
규칙(② `custom_rule`)은 ①remove_null_row 다음, 나머지 5종보다는 먼저 실행되며
상세는 §3 참고.

| # | 규칙 키 | 내용 | 기본값 |
|---|---|---|---|
| ① | `remove_null_row` | 모든 필드가 null 판정값(`None`/`""`/`"null"`/`"None"`/`"NULL"`/`"N/A"`/`"n/a"`)인 행 제거 — **계산량이 가벼워 실행은 항상 맨 먼저** | 활성 |
| ② | `custom_rule` | seq_no별 커스텀 규칙 적용 (§3) | 활성 |
| ③ | `trim_whitespace` | 문자열 값의 앞뒤 공백 제거 | 활성 |
| ④ | `remove_duplicate` | 행 전체를 비교해 중복 행 제거 | 활성 |
| ⑤ | `drop_columns` | 지정한 컬럼(`drop_columns` 인자)을 결과에서 제외 — GUI는 필드명 버튼 다중 선택 다이얼로그로 지정(§2.2) | 비활성 |
| ⑥ | `fill_null` | 잔존 null 값을 지정한 값으로 치환 (치환값 기본 빈 값 — GUI/`DataRefiner` 직접 호출 동일) | 비활성 |
| ⑦ | `cast_numeric` | 문자열을 int → float 순으로 변환 시도, 실패 시 원본 문자열 유지 | 비활성 |

- 규칙 활성화 여부는 GUI "② 정제 규칙 설정" 탭의 체크박스(`layout.py:518-526`
  `_refine_rules` 기본값, `_rule_checkboxes` 위젯은 `layout.py:696-702`)로
  수집 단위 개별 제어. `custom_rule`도 동일한 방식으로 켜고 끌 수
  있음(`layout.py:680`, 토글 연결은 `layout.py:783`).
- `DataRefiner.run()`은 원본 `raw_data`를 수정하지 않고(shallow copy 후 처리),
  `RefineStats`(원본 행 수, 정제 후 행 수, 제거 행 수, 치환 값 수, 제거된
  행의 원본 인덱스·사유, 셀 단위 변경 내역)를 함께 반환합니다.
- 빈 리스트나 `list[dict]`가 아닌 입력은 `run()` 진입 시 `TypeError`/`ValueError`로
  즉시 실패합니다 (조용한 유실 방지).

### 2.1 정제 결과 시각화 — Before/After 비교 탭

"④ Before/After 비교" 탭(`layout.py:_build_compare_tab()`, 867-939줄)이
`RefineStats`를 시각화하는 유일한 화면입니다. `_update_compare_tab()`
(`trigger.py:1208-1298`)이 원본(`cmp_raw_table`)과 정제 후(`cmp_ref_table`)
데이터를 나란히 표시하며:

- `stats.deleted_indices`로 제거된 Raw 행을 강조 표시
- `stats.modified_rows`로 값이 바뀐 Refined 셀을 강조 표시
- `drop_columns` 규칙이 활성화된 경우 우측(정제 후) 테이블에서만 해당
  컬럼을 제외
- 좌우 테이블의 스크롤·정렬은 컬럼명 기준으로 상호 동기화됨(대응 컬럼이
  없으면 무시)

§1.1의 수동 정제 실행에서만 갱신되며, 스케줄 자동 저장 경로
(`skip_ui_update=True`)에서는 갱신되지 않습니다 — 무인 실행 결과를
검토하려면 다음 수동 실행 전까지 이 탭에는 반영되지 않는다는 점에
유의합니다.

### 2.2 제외 필드 지정(`drop_columns`, ⑤) 선택 UI

2026-07-16 세션 동안 두 단계로 바뀌었습니다:

1. 쉼표로 구분한 컬럼명을 직접 입력하는 `QLineEdit`(`drop_col_input`) →
   필드명당 체크 가능한 `TagButton` 인라인 그리드 (오타로 인한 조용한 미적용 제거)
2. 인라인 그리드 → **별도 다이얼로그**(`_open_output_settings_dialog()`와 동일한
   기존 패턴 재사용) — 필드 수십 개짜리 그리드가 다른 6개 규칙 행과 나란히 있으면
   시각적 리듬이 깨지는 문제 해결

현재 구조:

- 행에는 `⚙ 필드 선택` 버튼(`parts.settings_btn`)과 요약 라벨만 있고(`layout.py:752-774`),
  버튼 클릭 시 `_open_drop_columns_dialog()`(`trigger.py:1088`)가 필드 그리드를 담은
  `QDialog`를 띄웁니다.
- **`self._collected_data`(Raw 수집 결과)가 비어 있으면 다이얼로그를 열지 않고**
  `QMessageBox.warning()`으로 "수집을 먼저 진행한 후 필드를 선택해 주세요" 안내만
  띄웁니다. 필드 목록 자체는 `_get_result_columns()`(blueprint 기준)라 수집 없이도
  알 수 있지만, 실제 수집 결과를 보기 전에는 제외 설정을 하지 못하도록 의도적으로
  게이트를 걸었습니다. 이 확인은 `_has_collected_data_or_warn()`(`trigger.py:1073`,
  `_run_refine()`의 "수집된 데이터가 없습니다" 경고와 동일 문구)로 공통화되어 있으며,
  **두 지점에서 공유**합니다(2026-07-17, 코드 중복 방지 목적으로 헬퍼로 추출):
  1. "⚙ 필드 선택" 버튼 클릭 시(`_open_drop_columns_dialog()`)
  2. "제외 필드 지정" 규칙 체크박스를 체크할 때(`layout.py:763` `_on_drop_columns_toggled`)
     — 데이터가 없으면 **경고창이 뜨기 전에 먼저 체크박스를 해제**합니다
     (`cb.setChecked(False)`를 경고 호출보다 먼저 실행 — 이 호출이 `stateChanged`를
     재귀적으로 한 번 더 발생시켜 버튼/라벨 숨김까지 먼저 끝낸 뒤에야 경고창이 뜸,
     2026-07-17). 경고창이 표시되는 시점엔 체크박스·버튼·라벨이 이미 전부 꺼진
     상태로 화면에 반영돼 있어, 체크된 상태가 잠깐이라도 보이는 일이 없습니다.
     체크박스가 꺼져 있는 한 버튼 자체가 안 보이므로, 실질적으로 대부분의 경로는
     체크박스 시점에서 먼저 걸러지고 버튼 클릭 경로는 안전망 역할입니다.
- **source of truth는 `self._drop_column_names`**(`list[str]`)입니다. 다이얼로그를
  열 때마다 `_get_result_columns()`(`layout.py:942`, blueprint의 `conditions.items`
  키에서 `root`/`detail_root`/`main_root`/`detail` 제외)로 얻은 필드마다 `TagButton`을
  새로 생성해 `self._drop_column_names`에 있는지 여부로 초기 체크 상태를 설정합니다.
  [적용] 클릭 시에만 체크된 필드명을 다시 `self._drop_column_names`에 반영하고
  요약 라벨을 갱신합니다(`trigger.py:1158-1161` `_apply()`) — [취소]하면 다이얼로그를
  닫아도 이전 선택이 그대로 유지됩니다.
- 필드가 수십 개일 수 있다는 전제로 다이얼로그 내부는 4열 `QGridLayout` + 고정 높이
  (200px) `QScrollArea`로 구성해 스크롤로 대응합니다. 필드가 없으면 안내 레이블을 표시합니다.
- 행의 `⚙ 필드 선택` 버튼과 요약 라벨은 **규칙 체크박스가 켜져 있을 때만 보입니다**
  (`layout.py:752-774`의 `setVisible` 연동) — 꺼져 있으면 나머지 5개 단순 행과 완전히
  동일한 모양이 됩니다.
- `_run_refine()`(`trigger.py:963`)은 `self._drop_column_names`를 그대로 읽어
  `DataRefiner(drop_columns=...)`에 전달합니다 — 인터페이스 자체는 기존과 동일해
  정제 결과/비교 탭(§2.1) 등 하위 로직은 변경이 없습니다.
- **적용 범위는 수동 정제 실행에 한정**됩니다. 스케줄 자동 저장 경로는
  `rules_override`가 전달되면 `drop_columns`를 항상 빈 리스트로 강제하므로
  (`trigger.py:980`) 이 UI와 무관합니다.
- 필드 목록은 앱 시작 시점에 1회 읽은 모듈 전역 `request_info`
  (`layout.py:33`)를 기준으로 하므로, 런타임 중 blueprint가 reload돼도
  갱신되지 않습니다 — Raw/정제/비교 탭의 컬럼 헤더가 이미 가진 것과
  동일한 한계입니다.
- 더 이상 쓰이지 않게 된 `DataRefiner.update_drop_columns()`(문자열 파싱
  결과를 받아 교체하던 메서드, 호출부 전무)는 인라인 그리드 도입 시점에
  함께 삭제됐습니다.

---

## 3. 커스텀 정제 규칙 (seq_no별 플러그인, "7번째 규칙")

수집물(blueprint)마다 원시 데이터 형식이 달라 범용 규칙 하나로 커버할 수
없는 경우를 위한 플러그인 메커니즘 (`preprocess.load_custom_rule`, PR #41/#42).

### 3.1 파일 규약

- 파일명: `{seq_no}.py` — `request_info.json`의 `seq_no` 값과 **문자열
  그대로 정확히 일치**해야 함 (예: `seq_no="000000"` → `000000.py`).
- **런타임/배포 경로**는 `request_info.json`(`BlueprintStorage`)과 같은
  seed-on-first-run 정책을 따르되, kind(`render`/`refine`)별 서브폴더로
  나뉩니다 (2026-07-13, `53978d0`):
  - 번들 리소스 경로(`utility.resource_path()` 루트, 개발 시 프로젝트 루트 /
    PyInstaller 빌드 후 `_MEIPASS`) 아래 `custom_rules/refine/{seq_no}.py`에
    고객별 기본값을 패키징. 정제 단계는 `refine`, 수집(렌더링/로그인) 단계는
    `render`를 씁니다 — §3.1a 참고.
  - 앱 데이터 폴더(`LOCALAPPDATA/CollectorApp/custom_rules/refine/` 등)에
    파일이 없으면 최초 실행 시 번들 기본값을 그대로 복사(seed)하고, 이후에는
    앱 데이터 폴더 사본을 우선 사용 — 고객 PC에서 직접 수정 가능.
  - 경로 해석·시딩·로드는 `conf.CustomModuleStorage`(`resolve_path()`/
    `has_refine()`/`load_refine()`)가 전담합니다 — `BlueprintStorage`와 동일한
    패턴입니다. 이 클래스는 kind별 경로만 알고 있으며, 아래 §3.1a의 개발용
    폴더 구조와 1:1로 대응합니다.

#### 3.1a 개발 시점 관리 폴더: `custom_rules/`

레포 루트의 `custom_rules/{kind}/{seq_no}.py`는 **개발자가 여러 고객/블루프린트의
정제·수집 규칙 모듈을 한곳에 모아 작업하는 개발 전용 폴더**입니다. 런타임이
참조하는 §3.1의 경로와 구조가 그대로 대응합니다(레포 루트 = `utility.resource_path()`
위치).

- `request_info.json`(고객별 로컬 설정, `.gitignore` 등록·미추적)과 달리
  `custom_rules/`는 **git으로 이력 관리**합니다 — 정제·수집 규칙은 설정값이
  아니라 코드이므로 변경 이력을 남길 필요가 있다는 판단.
- `refine/{seq_no}.py`: 정제 단계(`refine()`/`refine_row()`, 메인 GUI
  프로세스에서 실행). 이 문서(§3.2 이하)의 주 대상.
- `render/{seq_no}.py`: 수집 단계(`render()`/`login()`, Selenium 자식
  프로세스에서 실행). 함수 계약은 `conf.CustomModuleStorage`의 클래스
  docstring 참고.
- **배포**: 특정 고객에게 배포할 때는 `build-exe.ps1 -SeqNo {seq_no}`를
  실행합니다. 이 스크립트가 `request_info.json`의 `seq_no`와 일치하는지
  검증한 뒤, 해당 seq_no의 `refine/`·`render/` 파일만 골라 임시 스테이징
  폴더에 모아 `--add-data`로 PyInstaller에 전달합니다 — `custom_rules/`
  전체를 그대로 번들에 넣으면 다른 고객의 규칙 파일까지 함께 유출되므로,
  레포 루트로 수동 복사하던 과거 방식 대신 이 스크립트로 seq_no 단위 선별을
  강제합니다(레포 루트 참고).
- 실제 정제·수집 규칙 로직 작성은 Windows 개발 환경에서 진행됩니다.

### 3.2 함수 계약

파일 안에 아래 둘 중 하나를 정의합니다 (`preprocess.py:24-26`).

```python
def refine(data: list[dict]) -> list[dict]: ...   # 전체 목록 단위, 있으면 우선 사용
def refine_row(row: dict) -> dict: ...             # 행 단위
```

### 3.3 적용 조건과 실패 처리

로드(파일 찾기·`exec`)와 실행(호출·검증)이 서로 다른 계층에서 처리됩니다.

- **로드** (`trigger.py:1001-1020`, `_run_refine()`): 해당 수집(task)의
  `needs_cleaning=True` **그리고** `seq_no`가 존재할 때만
  `load_custom_rule(seq_no)`를 호출합니다. `{seq_no}.py`가 없으면 `None`을
  반환 → 경고 로그 후 범용 규칙만 적용. 로드 중 예외(문법 오류 등)는 이
  지점에서 잡아 `err` 로그를 남기고 `custom_rule_fn = None`으로 진행합니다.
- **실행** (`preprocess.py:244` `DataRefiner._step_custom_rule()`): 로드된
  콜러블은 `DataRefiner(custom_rule=...)`로 전달되고, `rules["custom_rule"]`이
  켜져 있을 때만(§1) 실제로 호출됩니다. 호출 중 예외, 또는 반환값이
  입력과 동일한 길이의 `list`가 아닌 경우 모두 **원본 데이터로 폴백**하고
  `RefineStats.custom_rule_error`에 메시지를 담습니다(`preprocess.py:259`).
  성공하면 `RefineStats.custom_rule_applied = True`(`preprocess.py:262`).
- `trigger.py`는 `refiner.run()` 반환 후 `stats.custom_rule_applied`/
  `custom_rule_error`를 보고 로그 문구를 결정합니다(`trigger.py:1038-1048`,
  실제 로그 반영은 `trigger.py:1059-1066`) — 커스텀 규칙의 버그가 수집
  자체를 막지는 않지만, 배포 전 테스트하지 않으면 실패가 로그로만 조용히
  남고 지나갈 수 있습니다.
- GUI는 "② 정제 규칙 설정" 탭 진입 시 `needs_cleaning=True`인데
  `custom_rule_exists(seq_no)`가 `False`이면 1회 경고 팝업으로 안내합니다
  (연결부 `layout.py:576`, 핸들러 `trigger.py:924-946`
  `_on_monitor_tab_changed()`). 이 팝업은 파일 존재 여부만 확인하며,
  "커스텀 정제 규칙 적용" 체크박스(§1)가 꺼져 있는 경우는 별도로 안내하지
  않습니다.

### 3.4 보안 관찰

`load_custom_rule()`은 `importlib`로 `{seq_no}.py`를 그대로 `exec`합니다 —
샌드박싱이 없습니다. **개발자가 직접 작성·검수한 신뢰된 코드에만
사용**해야 하며, 고객이 직접 업로드하는 파일 등 외부 입력 경로로 확장할
경우 임의 코드 실행 위험이 됩니다.

---

## 4. 커스텀 규칙 개발 프로세스 (지침)

기존에 문서화된 절차가 없어 아래와 같이 신규로 정리합니다.

1. **요구사항 확정**: 어떤 필드/형식 문제 때문에 커스텀 규칙이 필요한지
   확인하고, 대상 블루프린트의 `request_info.json`에서 `needs_cleaning`을
   `true`로 설정.
2. **seq_no 확인**: 대상 블루프린트의 `seq_no` 값을 정확히 확인 (문자열
   앞자리 0 유실 등 오타 주의).
3. **정제 함수 작성**: `custom_rules/refine/{seq_no}.py`에 `refine()` 또는
   `refine_row()` 중 로직에 맞는 형태로 작성 (§3.2 계약 준수, Windows
   개발 환경 기준). 이 폴더는 git으로 이력 관리되므로 커밋 대상.
4. **배포 전 단독 검증**: 실제 raw 데이터 샘플로 정제 함수를 임시
   스크립트에서 단독 실행해 예외 없이 기대한 출력이 나오는지 확인.
   검증 스크립트는 확인 후 삭제(저장소 커밋 정책과 동일하게 산출물로
   남기지 않음).
5. **배포 빌드**: `.\build-exe.ps1 -SeqNo {seq_no}`를 실행 — 스크립트가
   `custom_rules/refine/{seq_no}.py`(있으면 `render/{seq_no}.py`도)와
   `request_info.json`을 자동으로 골라 exe에 포함시킵니다. 최초 실행 시
   앱 데이터 폴더로 자동 시딩됨.
6. **GUI 통합 확인**: "② 정제 규칙 설정" 탭 진입 시 경고 팝업이 뜨지
   않는지, "커스텀 정제 규칙 적용" 체크박스가 켜져 있는지, 실제 수집 1회
   실행 후 로그에 `"사용자 정의 규칙 적용됨"` 문구가 남는지,
   결과 데이터가 기대대로 정규화됐는지 확인.
7. **정리**: 검증용 임시 스크립트/파일 삭제. `custom_rules/refine/{seq_no}.py`
   원본은 유지 — 배포용 스테이징 폴더는 `build-exe.ps1`이 빌드 후 자동
   삭제하므로 별도 정리가 필요 없습니다.

---

## 5. 작업 프로세스 예시

`seq_no="000000"`(샤브올데이) 블루프린트를 예로 든 워크스루입니다. 가정:
`tel` 필드에 `"02)1234-5678"`처럼 괄호가 섞여 있어 하이픈으로 통일 정규화가
필요한 상황.

**1) `request_info.json`에서 `needs_cleaning: true` 설정**

**2) `custom_rules/refine/000000.py` 작성** (Windows 개발 환경, git 추적 대상 —
현재 실제 배포된 내용, `418597f`에서 자릿수 기반 재조합 방식 대신 단순
치환으로 교체됨)
```python
# custom_rules/refine/000000.py — seq_no=000000(샤브올데이) 전용 커스텀 정제
import re


def refine_row(row: dict) -> dict:
    tel = row.get("tel", "")
    digits = re.sub(r"\)", "-", tel)
    row["tel"] = digits
    return row
```

**3) 배포 전 단독 검증** (임시, 커밋 안 함)
```python
import importlib.util
spec = importlib.util.spec_from_file_location("test", "custom_rules/refine/000000.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

sample = [{"tel": "02)1234-5678", "name": "가게A"}, {"tel": "010)9876-5432", "name": "가게B"}]
print([m.refine_row(r) for r in sample])
# → tel이 "02-1234-5678", "010-9876-5432"로 정규화되는지 확인
```

**4) 배포**: `.\build-exe.ps1 -SeqNo 000000` 실행 — `custom_rules/refine/000000.py`와
`request_info.json`을 자동으로 골라 exe에 포함.

**5) GUI 통합 확인**: 탭 진입 시 경고 없음 → 수집 1회 실행 →
`"사용자 정의 규칙 적용됨"` 로그 확인 → 결과의 `tel` 필드
정규화 확인.

**6) 정리**: 검증 스크립트 삭제. `custom_rules/refine/000000.py` 원본은 유지 —
스테이징 폴더는 빌드 스크립트가 자동 삭제.

---

## 6. 관련 문서

- `HISTORY.md` — PR #41(커스텀 정제 규칙 플러그인 도입), PR #42(경로 통일
  + 미설정 경고), `a4c6375`/`e91c676`(스케줄 자동 정제 고정 규칙 + 대상
  선택 기능) 구현 이력
- `ISSUES.md` — §2 미해결·보류 이슈 중 ⑱(스케줄+정제 자동 저장 조합의
  빈 데이터 경고 잠재 리스크), §4 보안·운영 관찰, §6 백로그
- `PROJECT_REPORT.md` §데이터 정제 — 모듈 구조 개요
