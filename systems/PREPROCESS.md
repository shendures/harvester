# 데이터 정제 (`preprocess.py`) — 규칙 정리 및 개발 지침

> 수집된 raw 데이터를 정제하는 로직(`preprocess.py`)에 대한 규칙 설명과
> 개발 프로세스 지침을 정리한 문서입니다. 구현 이력은 `HISTORY.md`(PR #41,
> #42), 이슈 상태는 `ISSUES.md` 참고.

---

## 1. 정제 파이프라인 개요

`DataRefiner`가 7개 규칙을 모두 소유하고 순차 적용합니다. 커스텀 규칙(`custom_rule`,
seq_no별 플러그인)이 **항상 맨 먼저 실행되는 ①번 규칙**입니다 — 사이트별 원시 데이터를
정규화한 뒤, 그 위에서 범용 규칙(중복 제거 등)을 적용하기 위함 (`preprocess.py:108` 주석 참고).

```
raw 수집 데이터
    │
    ▼
DataRefiner.run()
    ├─ ① custom_rule       (seq_no별, 있고 활성화된 경우에만 — 항상 맨 먼저 실행)
    ├─ ② remove_duplicate
    ├─ ③ remove_null_row
    ├─ ④ fill_null
    ├─ ⑤ trim_whitespace
    ├─ ⑥ drop_columns
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
   (`layout.py:525` `_refine_rules`, 기본값 `True`).

둘 중 하나라도 해당 안 되면(파일 없음 / 체크박스 꺼짐) 이 단계는 조용히 건너뛰고
범용 6규칙만 적용됩니다.

**체크박스 자동 연동** (`trigger.py` `_on_custom_rule_toggled`): "커스텀 정제 규칙
적용" 체크박스를 켤 때마다 ②~⑤(`remove_duplicate`/`remove_null_row`/`fill_null`/
`trim_whitespace`)가 자동으로 켜집니다(사용자가 개별적으로 꺼둔 상태여도 매번
덮어씀). 해제할 때는 ②~⑤에 영향을 주지 않고 직전 상태를 그대로 둡니다 — 커스텀
규칙이 정규화한 데이터에는 기본 위생 규칙(중복/결측 정리 등)이 항상 함께 돌도록
하기 위한 편의 기능이며, ⑥`drop_columns`·⑦`cast_numeric`은 연동 대상이 아닙니다.

---

## 2. 범용 정제 규칙 (`DataRefiner`, ①~⑦)

`preprocess.DataRefiner`가 아래 순서대로 적용합니다. **순서를 바꾸면 결과가
달라지므로 임의로 바꾸지 않습니다** (`preprocess.py:108` 주석 참고). 커스텀
규칙(① `custom_rule`)은 이 6종보다 먼저 실행되며 상세는 §3 참고.

| # | 규칙 키 | 내용 | 기본값 |
|---|---|---|---|
| ① | `custom_rule` | seq_no별 커스텀 규칙 적용 (§3) — **실행은 항상 맨 먼저** | 활성 |
| ② | `remove_duplicate` | 행 전체를 비교해 중복 행 제거 | 활성 |
| ③ | `remove_null_row` | 모든 필드가 null 판정값(`None`/`""`/`"null"`/`"None"`/`"NULL"`/`"N/A"`/`"n/a"`)인 행 제거 | 활성 |
| ④ | `fill_null` | 잔존 null 값을 지정한 값으로 치환 (기본 빈 값 — GUI/`DataRefiner` 직접 호출 동일) | 활성 |
| ⑤ | `trim_whitespace` | 문자열 값의 앞뒤 공백 제거 | 활성 |
| ⑥ | `drop_columns` | 지정한 컬럼(`drop_columns` 인자)을 결과에서 제외 | 비활성 |
| ⑦ | `cast_numeric` | 문자열을 int → float 순으로 변환 시도, 실패 시 원본 문자열 유지 | 비활성 |

- 규칙 활성화 여부는 GUI "② 정제 규칙 설정" 탭의 체크박스(`layout.py:525`
  `_refine_rules`)로 수집 단위 개별 제어. `custom_rule`도 동일한 방식으로 켜고 끌 수
  있음(`layout.py:682`).
- `DataRefiner.run()`은 원본 `raw_data`를 수정하지 않고(shallow copy 후 처리),
  `RefineStats`(원본 행 수, 정제 후 행 수, 제거 행 수, 치환 값 수, 제거된
  행의 원본 인덱스·사유, 셀 단위 변경 내역)를 함께 반환합니다.
- 빈 리스트나 `list[dict]`가 아닌 입력은 `run()` 진입 시 `TypeError`/`ValueError`로
  즉시 실패합니다 (조용한 유실 방지).

---

## 3. 커스텀 정제 규칙 (seq_no별 플러그인, "7번째 규칙")

수집물(blueprint)마다 원시 데이터 형식이 달라 범용 규칙 하나로 커버할 수
없는 경우를 위한 플러그인 메커니즘 (`preprocess.load_custom_rule`, PR #41/#42).

### 3.1 파일 규약

- 파일명: `{seq_no}.py` — `request_info.json`의 `seq_no` 값과 **문자열
  그대로 정확히 일치**해야 함 (예: `seq_no="000000"` → `000000.py`).
- **런타임/배포 경로**는 `request_info.json`(`BlueprintStorage`)과 완전히
  동일합니다 (2026-07-07, PR #42):
  - 번들 리소스 경로(`utility.resource_path()` 루트, 개발 시 프로젝트 루트 /
    PyInstaller 빌드 후 `_MEIPASS`)에 고객별 기본값을 패키징.
  - 앱 데이터 폴더(`LOCALAPPDATA/CollectorApp` 등)에 파일이 없으면 최초
    실행 시 번들 기본값을 그대로 복사(seed)하고, 이후에는 앱 데이터 폴더
    사본을 우선 사용 — 고객 PC에서 직접 수정 가능.
  - 경로 해석·시딩·로드는 `conf.CustomRuleStorage`(`resolve_path()`/`exists()`/
    `load()`)가 전담합니다 — `BlueprintStorage`와 동일한 패턴으로
    `preprocess.py`에서 이관(`3a10fab`, 2026-07-08). 이 평면 경로만 알고
    있으며, 아래 §3.1a의 개발용 폴더 구조와는 무관합니다.

#### 3.1a 개발 시점 관리 폴더: `custom_rules/`

레포 루트의 `custom_rules/{seq_no}.py`는 **개발자가 여러 고객/블루프린트의
정제 규칙 모듈을 한곳에 모아 작업하는 개발 전용 폴더**입니다 (2026-07-07
결정). 런타임이 참조하는 §3.1의 평면 경로와는 별개입니다.

- `request_info.json`(고객별 로컬 설정, `.gitignore` 등록·미추적)과 달리
  `custom_rules/`는 **git으로 이력 관리**합니다 — 정제 규칙은 설정값이
  아니라 코드이므로 변경 이력을 남길 필요가 있다는 판단.
- 특정 고객에게 배포할 때는 `custom_rules/{seq_no}.py` 중 해당 고객 파일
  **하나만** 레포 루트(=`utility.resource_path()` 위치)로 복사해 패키징합니다.
  이 복사 단계에서 다시 "파일 단위 1개"로 좁혀지므로 런타임 코드는 변경이
  필요 없습니다.
- 실제 정제 규칙 로직 작성은 Windows 개발 환경에서 진행됩니다.

### 3.2 함수 계약

파일 안에 아래 둘 중 하나를 정의합니다 (`preprocess.py:20-23`).

```python
def refine(data: list[dict]) -> list[dict]: ...   # 전체 목록 단위, 있으면 우선 사용
def refine_row(row: dict) -> dict: ...             # 행 단위
```

### 3.3 적용 조건과 실패 처리

로드(파일 찾기·`exec`)와 실행(호출·검증)이 서로 다른 계층에서 처리됩니다.

- **로드** (`trigger.py:1042`, `_run_refine()`): 해당 수집(task)의
  `needs_cleaning=True` **그리고** `seq_no`가 존재할 때만
  `load_custom_rule(seq_no)`를 호출합니다. `{seq_no}.py`가 없으면 `None`을
  반환 → 경고 로그 후 범용 규칙만 적용. 로드 중 예외(문법 오류 등)는 이
  지점에서 잡아 `err` 로그를 남기고 `custom_rule_fn = None`으로 진행합니다.
- **실행** (`preprocess.py:213` `DataRefiner._step_custom_rule()`): 로드된
  콜러블은 `DataRefiner(custom_rule=...)`로 전달되고, `rules["custom_rule"]`이
  켜져 있을 때만(§1) 실제로 호출됩니다. 호출 중 예외, 또는 반환값이
  입력과 동일한 길이의 `list`가 아닌 경우 모두 **원본 데이터로 폴백**하고
  `RefineStats.custom_rule_error`에 메시지를 담습니다(`preprocess.py:228`).
  성공하면 `RefineStats.custom_rule_applied = True`(`preprocess.py:231`).
- `trigger.py`는 `refiner.run()` 반환 후 `stats.custom_rule_applied`/
  `custom_rule_error`를 보고 로그·요약 문구를 결정합니다(`trigger.py:1070-1080`)
  — 커스텀 규칙의 버그가 수집 자체를 막지는 않지만, 배포 전 테스트하지
  않으면 실패가 로그로만 조용히 남고 지나갈 수 있습니다.
- GUI는 "② 정제 규칙 설정" 탭 진입 시 `needs_cleaning=True`인데
  `custom_rule_exists(seq_no)`가 `False`이면 1회 경고 팝업으로 안내합니다
  (`layout.py:582`, `trigger.py:983`). 이 팝업은 파일 존재 여부만 확인하며,
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
3. **정제 함수 작성**: `custom_rules/{seq_no}.py`에 `refine()` 또는
   `refine_row()` 중 로직에 맞는 형태로 작성 (§3.2 계약 준수, Windows
   개발 환경 기준). 이 폴더는 git으로 이력 관리되므로 커밋 대상.
4. **배포 전 단독 검증**: 실제 raw 데이터 샘플로 정제 함수를 임시
   스크립트에서 단독 실행해 예외 없이 기대한 출력이 나오는지 확인.
   검증 스크립트는 확인 후 삭제(저장소 커밋 정책과 동일하게 산출물로
   남기지 않음).
5. **배포 위치에 배치**: `custom_rules/{seq_no}.py`를 레포 루트
   (`utility.resource_path()` 위치)로 복사한 뒤 패키징 — 최초 실행 시 앱
   데이터 폴더로 자동 시딩됨.
6. **GUI 통합 확인**: "② 정제 규칙 설정" 탭 진입 시 경고 팝업이 뜨지
   않는지, "커스텀 정제 규칙 적용" 체크박스가 켜져 있는지, 실제 수집 1회
   실행 후 로그에 `"사용자 정의 규칙 적용됨"` 문구가 남는지,
   결과 데이터가 기대대로 정규화됐는지 확인.
7. **정리**: 검증용 임시 스크립트/파일 삭제. `custom_rules/{seq_no}.py`
   원본은 유지, 레포 루트로 복사했던 배포용 사본은 배포 산출물이므로
   그대로 두거나 다음 고객 빌드 전 정리.

---

## 5. 작업 프로세스 예시

`seq_no="000000"`(샤브올데이) 블루프린트를 예로 든 워크스루입니다. 가정:
`tel` 필드에 `"02)1234-5678"`처럼 괄호가 섞여 있어 하이픈으로 통일 정규화가
필요한 상황.

**1) `request_info.json`에서 `needs_cleaning: true` 설정**

**2) `custom_rules/000000.py` 작성** (Windows 개발 환경, git 추적 대상 —
현재 실제 배포된 내용, `418597f`에서 자릿수 기반 재조합 방식 대신 단순
치환으로 교체됨)
```python
# custom_rules/000000.py — seq_no=000000(샤브올데이) 전용 커스텀 정제
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
spec = importlib.util.spec_from_file_location("test", "custom_rules/000000.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

sample = [{"tel": "02)1234-5678", "name": "가게A"}, {"tel": "010)9876-5432", "name": "가게B"}]
print([m.refine_row(r) for r in sample])
# → tel이 "02-1234-5678", "010-9876-5432"로 정규화되는지 확인
```

**4) 배포**: `custom_rules/000000.py`를 레포 루트로 복사해 `000000.py`로
패키징 (`utility.resource_path()` 위치).

**5) GUI 통합 확인**: 탭 진입 시 경고 없음 → 수집 1회 실행 →
`"사용자 정의 규칙 적용됨"` 로그 확인 → 결과의 `tel` 필드
정규화 확인.

**6) 정리**: 검증 스크립트 삭제. `custom_rules/000000.py` 원본은 유지.

---

## 6. 관련 문서

- `HISTORY.md` — PR #41(커스텀 정제 규칙 플러그인 도입), PR #42(경로 통일
  + 미설정 경고) 구현 이력
- `ISSUES.md` — 관련 이슈·보안 관찰(§3)·백로그(§5)
- `PROJECT_REPORT.md` §데이터 정제 — 모듈 구조 개요
