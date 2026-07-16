"""
preprocess.py — DataCrawler v2.0
수집된 raw 데이터를 정제하는 로직을 전담하는 모듈입니다.

DataRefiner 클래스
  - 7가지 정제 규칙을 순차 적용
  - 원본 데이터를 절대 수정하지 않음 (shallow copy 후 처리)
  - 정제 통계(제거 행 수, 치환 값 수)를 함께 반환

RefineStats 데이터 클래스
  - 정제 결과 수치를 타입 안전하게 전달

load_custom_rule() 함수
  - 수집물(blueprint)마다 다른 사용자 정의 정제 로직을 파일 하나로 플러그인.
  - 경로 해석·시딩·실제 로드는 conf.CustomModuleStorage가 전담하며(BlueprintStorage와
    동일한 정책), 이 함수는 그 얇은 위임입니다. 수집 단계용 render()/login()은
    실행 컨텍스트가 달라 별도 폴더(custom_rules/render/)에 있으며, 이 함수는 정제
    단계(refine/refine_row)만 다룹니다:
        <앱 데이터 폴더>/custom_rules/refine/{seq_no}.py         — 실제 실행 시 읽는 위치(고객 PC별로 다름)
        <번들 리소스 경로>/custom_rules/refine/{seq_no}.py       — 패키징 시 포함한 고객별 기본값
    최초 실행 시 앱 데이터 폴더에 파일이 없으면 번들 기본값을 그대로 복사해 심고,
    이후에는 앱 데이터 폴더의 사본을 우선 사용합니다(고객 PC에서 직접 수정 가능).
  - 파일에는 아래 둘 중 하나를 정의:
        def refine(data: list[dict]) -> list[dict]: ...       # 전체 목록 단위
        def refine_row(row: dict) -> dict: ...                 # 행 단위
    (둘 다 있으면 refine()을 우선 사용)
  - 해당 seq_no 파일이 없으면 None을 반환 — 호출 측에서 "커스텀 규칙 없음"으로 처리.
  - DataRefiner(custom_rule=...)에 전달하면 ②번 규칙으로 적용됩니다 — 완전 공백
    행을 미리 제거하는 ①remove_null_row 바로 다음, 나머지 범용 규칙(중복 제거
    등)보다는 먼저 실행되어 원시 데이터를 사이트별로 정규화한 뒤, 그 위에서
    나머지 규칙이 동작합니다 (2026-07-17, 메모리 절감을 위해 ①remove_null_row만
    앞으로 재배치 — 이전에는 custom_rule이 항상 맨 먼저 실행됐음, HISTORY.md 참고).

사용 예:
    from preprocess import DataRefiner, RefineStats, load_custom_rule

    rules = {
        "remove_null_row":  True,
        "custom_rule":      True,
        "trim_whitespace":  True,
        "remove_duplicate": True,
        "drop_columns":     False,
        "fill_null":        True,
        "cast_numeric":     False,
    }

    custom_rule = load_custom_rule(seq_no)   # None이면 커스텀 규칙 없음

    refiner = DataRefiner(rules=rules, drop_columns=["brand"], custom_rule=custom_rule)
    refined_data, stats = refiner.run(raw_data)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

import conf


# ── 정제 통계 컨테이너 ────────────────────────────────────────────────
@dataclass
class RefineStats:
    """정제 과정에서 발생한 수치를 담는 불변 결과 객체."""
    raw_count:      int  = 0   # 원본 행 수
    refined_count:  int  = 0   # 정제 후 행 수
    removed:        int  = 0   # 제거된 행 수 (중복 + null 행 합산)
    filled:         int  = 0   # null → 지정값 치환된 값 수
    deleted_indices: list = field(default_factory=list)  # 제거된 행의 원본 인덱스 목록
    deleted_reasons: dict = field(default_factory=dict)  # {원본인덱스: "중복" | "전체 필드 NULL"}
    modified_rows:  dict = field(default_factory=dict)  # {정제행위치: {컬럼: (변경전, 변경후)}}
    custom_rule_applied: bool     = False  # ② custom_rule 정상 적용 여부
    custom_rule_error:   str | None = None  # ② custom_rule 실행 중 예외 메시지 (있으면 원본 데이터로 폴백)

    @property
    def refine_rate(self) -> str:
        """정제율 (정제 후 행 수 / 원본 행 수 × 100)"""
        if self.raw_count == 0:
            return "—"
        return f"{self.refined_count / self.raw_count * 100:.1f}%"

    def to_dict(self) -> dict:
        return {
            "raw_count":      self.raw_count,
            "refined_count":  self.refined_count,
            "removed":        self.removed,
            "filled":         self.filled,
            "refine_rate":    self.refine_rate,
            "deleted_count":  len(self.deleted_indices),
            "modified_count": len(self.modified_rows),
        }


# ── 기본 정제 규칙 ────────────────────────────────────────────────────
DEFAULT_RULES: dict[str, bool] = {
    "remove_null_row":  True,   # 모든 필드 null 행 제거
    "custom_rule":       True,  # ② 커스텀 규칙(seq_no, 있으면) 적용
    "trim_whitespace":  True,   # 문자열 앞뒤 공백 trim
    "remove_duplicate": True,   # 중복 행 제거
    "drop_columns":     False,  # 선택 필드 제외 (기본 비활성)
    "fill_null":        True,   # null → 지정값 치환 (기본 빈 값)
    "cast_numeric":     False,  # 숫자 타입 변환  (기본 비활성)
}

# null 판정 기준값 집합
_NULL_VALUES: frozenset = frozenset({None, "", "null", "None", "NULL", "N/A", "n/a"})

# ── 정제 엔진 ────────────────────────────────────────────────────────
class DataRefiner:
    """
    수집된 raw 데이터에 정제 규칙을 순차 적용하는 엔진.

    규칙 적용 순서 (변경하지 마세요 — 순서가 결과에 영향을 미칩니다.
    2026-07-17, 만 건 이상 규모 처리 시 메모리/CPU 절감 + 정확성 개선을 위해 재배치됨
    — 이전 순서는 HISTORY.md 참고):
        ① remove_null_row   — 모든 필드 null 행 제거. 계산량이 가벼워 가장 먼저 실행,
                               ②custom_rule 처리 대상도 그만큼 줄임
        ② custom_rule       — 커스텀 규칙(seq_no, 있고 활성화된 경우) 적용 — ①을 제외한
                               나머지 범용 규칙보다는 먼저 실행해 원시 데이터를 정규화
        ③ trim_whitespace   — 문자열 공백 제거 (④ remove_duplicate보다 먼저 실행 —
                               공백만 다른 값도 동일 값으로 인식돼 중복 판정에 걸리도록 하기 위함)
        ④ remove_duplicate  — 중복 행 제거 (행 전체를 정렬·비교하는 비교적 비싼 연산이라
                               ②③을 거쳐 정규화·trim된 뒤 실행 — 판정 정확도도 더 높음)
        ⑤ drop_columns      — 지정 컬럼 제외 (④까지의 중복 판정 기준은 원본 전체 컬럼
                               그대로 유지하기 위해 그 뒤에 실행 — 아래보다는 먼저 실행해
                               이후 단계가 불필요한 컬럼까지 순회하지 않도록 함)
        ⑥ fill_null         — 잔존 null → 지정값 치환 (기본 빈 값)
        ⑦ cast_numeric      — 숫자 타입 변환
    """

    def __init__(
        self,
        rules:        dict[str, bool] | None = None,
        drop_columns: list[str]       | None = None,
        custom_rule:  Callable[[list[dict]], list[dict]] | None = None,
        fill_value:   str = "",
    ) -> None:
        """
        Args:
            rules:        규칙 활성화 딕셔너리. None이면 DEFAULT_RULES 사용.
            drop_columns: ⑤ drop_columns 규칙 활성 시 제외할 컬럼명 목록.
            custom_rule:  ② custom_rule 규칙 활성 시 실행할 콜러블
                          (`load_custom_rule()`의 반환값). None이면 이 step은 건너뜁니다.
            fill_value:   ⑥ fill_null 규칙 활성 시 null 값을 대체할 문자열. 기본 빈 값(`""`).
        """
        self.rules:        dict[str, bool] = {**DEFAULT_RULES, **(rules or {})}
        self.drop_columns: list[str]       = drop_columns or []
        self.custom_rule:  Callable[[list[dict]], list[dict]] | None = custom_rule
        self.fill_value:   str = fill_value

    # ── 공개 인터페이스 ───────────────────────────────────────────────
    def run(self, raw_data: list[dict]) -> tuple[list[dict], RefineStats]:
        """
        raw_data에 규칙을 순차 적용합니다.

        Args:
            raw_data: 수집된 원본 데이터 리스트 (dict 리스트).

        Returns:
            (refined_data, RefineStats) — 원본 raw_data는 수정되지 않습니다.

        Raises:
            TypeError:  raw_data가 list[dict]가 아닐 때.
            ValueError: raw_data가 빈 리스트일 때.
        """
        self._validate(raw_data)

        data        = self._shallow_copy(raw_data)
        stats       = RefineStats(raw_count=len(raw_data))
        orig_indices = list(range(len(raw_data)))  # 각 행의 원본 위치 추적

        data, stats, orig_indices = self._step_remove_null_row(data, stats, orig_indices)
        data, stats = self._step_custom_rule(data, stats)
        data, stats = self._step_trim_whitespace(data, stats)
        data, stats, orig_indices = self._step_remove_duplicate(data, stats, orig_indices)
        data        = self._step_drop_columns(data)
        data, stats = self._step_fill_null(data, stats)
        data        = self._step_cast_numeric(data)

        stats.refined_count  = len(data)

        # 제거된 원본 인덱스 확정
        survived = set(orig_indices)
        stats.deleted_indices = [i for i in range(len(raw_data)) if i not in survived]

        # 생존 행에서 셀 단위 변경 감지 (원본 vs 정제 후)
        for refined_pos, orig_idx in enumerate(orig_indices):
            raw_row     = raw_data[orig_idx]
            refined_row = data[refined_pos]
            for col, raw_val in raw_row.items():
                if col not in refined_row:  # drop_columns로 제거된 컬럼
                    continue
                refined_val = refined_row[col]
                if raw_val != refined_val:
                    stats.modified_rows.setdefault(refined_pos, {})[col] = (raw_val, refined_val)

        return data, stats

    def update_rules(self, rules: dict[str, bool]) -> None:
        """규칙 딕셔너리를 부분 갱신합니다 (없는 키는 무시)."""
        for key in DEFAULT_RULES:
            if key in rules:
                self.rules[key] = bool(rules[key])

    # ── 유효성 검사 ───────────────────────────────────────────────────
    @staticmethod
    def _validate(raw_data: list[dict]) -> None:
        if not isinstance(raw_data, list):
            raise TypeError(f"raw_data는 list여야 합니다. 전달된 타입: {type(raw_data).__name__}")
        if len(raw_data) == 0:
            raise ValueError("raw_data가 빈 리스트입니다.")
        bad = [i for i, r in enumerate(raw_data) if not isinstance(r, dict)]
        if bad:
            raise TypeError(f"raw_data[{bad[0]}] 요소가 dict가 아닙니다: {type(raw_data[bad[0]]).__name__}")

    @staticmethod
    def _shallow_copy(raw_data: list[dict]) -> list[dict]:
        """각 행 dict를 shallow copy하여 원본 보호."""
        return [row.copy() for row in raw_data]

    # ── 규칙 ① 모든 필드 null 행 제거 ───────────────────────────────
    def _step_remove_null_row(
        self, data: list[dict], stats: RefineStats, orig_indices: list[int]
    ) -> tuple[list[dict], RefineStats, list[int]]:
        if not self.rules.get("remove_null_row"):
            return data, stats, orig_indices

        surviving, removed_idxs = [], []
        for row, orig_idx in zip(data, orig_indices):
            if all(v in _NULL_VALUES for v in row.values()):
                removed_idxs.append(orig_idx)
            else:
                surviving.append((row, orig_idx))

        stats.removed += len(removed_idxs)
        for orig_idx in removed_idxs:
            stats.deleted_reasons[orig_idx] = "전체 필드 NULL"

        if surviving:
            new_data, new_indices = zip(*surviving)
            return list(new_data), stats, list(new_indices)
        return [], stats, []

    # ── 규칙 ② 커스텀 규칙(seq_no) 적용 ─────────────────────────────
    def _step_custom_rule(
        self, data: list[dict], stats: RefineStats
    ) -> tuple[list[dict], RefineStats]:
        if not self.rules.get("custom_rule") or self.custom_rule is None:
            return data, stats

        try:
            result = self.custom_rule(data)
            if not isinstance(result, list) or len(result) != len(data):
                got = len(result) if isinstance(result, list) else type(result).__name__
                raise ValueError(
                    f"커스텀 규칙은 입력과 동일한 길이의 list를 반환해야 합니다 "
                    f"(입력 {len(data)}행, 반환 {got})"
                )
        except Exception as e:
            stats.custom_rule_error = str(e)
            return data, stats

        stats.custom_rule_applied = True
        return result, stats

    # ── 규칙 ③ 문자열 공백 trim ──────────────────────────────────────
    def _step_trim_whitespace(
        self, data: list[dict], stats: RefineStats
    ) -> tuple[list[dict], RefineStats]:
        if not self.rules.get("trim_whitespace"):
            return data, stats

        for row in data:
            for k, v in row.items():
                if isinstance(v, str):
                    row[k] = v.strip()
        return data, stats

    # ── 규칙 ④ 중복 행 제거 ──────────────────────────────────────────
    def _step_remove_duplicate(
        self, data: list[dict], stats: RefineStats, orig_indices: list[int]
    ) -> tuple[list[dict], RefineStats, list[int]]:
        if not self.rules.get("remove_duplicate"):
            return data, stats, orig_indices

        seen: set[tuple] = set()
        unique: list[dict] = []
        new_indices: list[int] = []
        for row, orig_idx in zip(data, orig_indices):
            try:
                key = tuple(sorted((k, str(v)) for k, v in row.items()))
            except Exception:
                key = tuple(str(row))
            if key not in seen:
                seen.add(key)
                unique.append(row)
                new_indices.append(orig_idx)
            else:
                stats.removed += 1
                stats.deleted_reasons[orig_idx] = "중복"
        return unique, stats, new_indices

    # ── 규칙 ⑤ 선택 필드 제외 ───────────────────────────────────────
    def _step_drop_columns(self, data: list[dict]) -> list[dict]:
        if not self.rules.get("drop_columns") or not self.drop_columns:
            return data
        drop_set = set(self.drop_columns)
        return [{k: v for k, v in row.items() if k not in drop_set} for row in data]

    # ── 규칙 ⑥ null → 지정값 치환 ─────────────────────────────────────
    def _step_fill_null(
        self, data: list[dict], stats: RefineStats
    ) -> tuple[list[dict], RefineStats]:
        if not self.rules.get("fill_null"):
            return data, stats

        for row in data:
            for k, v in row.items():
                if v in _NULL_VALUES:
                    row[k] = self.fill_value
                    stats.filled += 1
        return data, stats

    # ── 규칙 ⑦ 숫자 타입 변환 ───────────────────────────────────────
    def _step_cast_numeric(self, data: list[dict]) -> list[dict]:
        if not self.rules.get("cast_numeric"):
            return data

        for row in data:
            for k, v in row.items():
                if not isinstance(v, str):
                    continue
                stripped = v.strip()
                # int 시도
                try:
                    row[k] = int(stripped)
                    continue
                except (ValueError, OverflowError):
                    pass
                # float 시도
                try:
                    row[k] = float(stripped)
                except (ValueError, OverflowError):
                    pass   # 변환 불가 — 원본 문자열 유지
        return data


# ── 사용자 정의 정제 규칙 로더 ─────────────────────────────────────────
# 경로 해석·시딩·로드 실행은 conf.CustomModuleStorage가 전담합니다(BlueprintStorage와
# 동일한 정책). 아래 두 함수는 기존 호출부(trigger.py 등)와의 호환을 위한 얇은 위임이며,
# 정제 단계(refine/refine_row)만 다룹니다 — 같은 파일의 render()/login()은 다루지 않습니다.
def custom_rule_exists(seq_no) -> bool:
    """`{seq_no}.py`에 refine() 또는 refine_row()가 정의돼 있는지 확인합니다 (exec 안 함)."""
    return conf.CustomModuleStorage().has_refine(seq_no)


def load_custom_rule(seq_no):
    """`{seq_no}.py`를 로드하여 사용자 정의 정제 함수를 반환합니다 (없으면 None)."""
    return conf.CustomModuleStorage().load_refine(seq_no)
