"""
preprocess.py — DataCrawler v2.0
수집된 raw 데이터를 정제하는 로직을 전담하는 모듈입니다.

DataRefiner 클래스
  - 6가지 정제 규칙을 순차 적용
  - 원본 데이터를 절대 수정하지 않음 (shallow copy 후 처리)
  - 정제 통계(제거 행 수, 치환 값 수)를 함께 반환

RefineStats 데이터 클래스
  - 정제 결과 수치를 타입 안전하게 전달

사용 예:
    from preprocess import DataRefiner, RefineStats

    rules = {
        "remove_duplicate": True,
        "remove_null_row":  True,
        "fill_null":        True,
        "trim_whitespace":  True,
        "drop_columns":     False,
        "cast_numeric":     False,
    }
    refiner = DataRefiner(rules=rules, drop_columns=["brand"])
    refined_data, stats = refiner.run(raw_data)
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field


# ── 정제 통계 컨테이너 ────────────────────────────────────────────────
@dataclass
class RefineStats:
    """정제 과정에서 발생한 수치를 담는 불변 결과 객체."""
    raw_count:      int  = 0   # 원본 행 수
    refined_count:  int  = 0   # 정제 후 행 수
    removed:        int  = 0   # 제거된 행 수 (중복 + null 행 합산)
    filled:         int  = 0   # null → "—" 치환된 값 수
    deleted_indices: list = field(default_factory=list)  # 제거된 행의 원본 인덱스 목록
    deleted_reasons: dict = field(default_factory=dict)  # {원본인덱스: "중복" | "NULL 포함"}
    modified_cells:  dict = field(default_factory=dict)  # {정제행위치: {컬럼: (변경전, 변경후)}}

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
            "modified_count": len(self.modified_cells),
        }


# ── 기본 정제 규칙 ────────────────────────────────────────────────────
DEFAULT_RULES: dict[str, bool] = {
    "remove_duplicate": True,   # 중복 행 제거
    "remove_null_row":  True,   # 필수 필드 null 행 제거
    "fill_null":        True,   # null → "—" 치환
    "trim_whitespace":  True,   # 문자열 앞뒤 공백 trim
    "drop_columns":     False,  # 선택 필드 제외 (기본 비활성)
    "cast_numeric":     False,  # 숫자 타입 변환  (기본 비활성)
}

# null 판정 기준값 집합
_NULL_VALUES: frozenset = frozenset({None, "", "null", "None", "NULL", "N/A", "n/a"})

# ── 정제 엔진 ────────────────────────────────────────────────────────
class DataRefiner:
    """
    수집된 raw 데이터에 정제 규칙을 순차 적용하는 엔진.

    규칙 적용 순서 (변경하지 마세요 — 순서가 결과에 영향을 미칩니다):
        ① remove_duplicate  — 중복 행 제거
        ② remove_null_row   — null 포함 행 제거
        ③ fill_null         — 잔존 null → "—" 치환
        ④ trim_whitespace   — 문자열 공백 제거
        ⑤ drop_columns      — 지정 컬럼 제외
        ⑥ cast_numeric      — 숫자 타입 변환
    """

    def __init__(
        self,
        rules:        dict[str, bool] | None = None,
        drop_columns: list[str]       | None = None,
    ) -> None:
        """
        Args:
            rules:        규칙 활성화 딕셔너리. None이면 DEFAULT_RULES 사용.
            drop_columns: ⑤ drop_columns 규칙 활성 시 제외할 컬럼명 목록.
        """
        self.rules:        dict[str, bool] = {**DEFAULT_RULES, **(rules or {})}
        self.drop_columns: list[str]       = drop_columns or []

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

        data, stats, orig_indices = self._step_remove_duplicate(data, stats, orig_indices)
        data, stats, orig_indices = self._step_remove_null_row(data, stats, orig_indices)
        data, stats = self._step_fill_null(data, stats)
        data, stats = self._step_trim_whitespace(data, stats)
        data        = self._step_drop_columns(data)
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
                    stats.modified_cells.setdefault(refined_pos, {})[col] = (raw_val, refined_val)

        return data, stats

    def update_rules(self, rules: dict[str, bool]) -> None:
        """규칙 딕셔너리를 부분 갱신합니다 (없는 키는 무시)."""
        for key in DEFAULT_RULES:
            if key in rules:
                self.rules[key] = bool(rules[key])

    def update_drop_columns(self, columns: list[str]) -> None:
        """제외할 컬럼명 목록을 교체합니다."""
        self.drop_columns = [c for c in columns if isinstance(c, str) and c.strip()]

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

    # ── 규칙 ① 중복 행 제거 ──────────────────────────────────────────
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

    # ── 규칙 ② 필수 필드 null 행 제거 ───────────────────────────────
    def _step_remove_null_row(
        self, data: list[dict], stats: RefineStats, orig_indices: list[int]
    ) -> tuple[list[dict], RefineStats, list[int]]:
        if not self.rules.get("remove_null_row"):
            return data, stats, orig_indices

        surviving, removed_idxs = [], []
        for row, orig_idx in zip(data, orig_indices):
            if any(v in _NULL_VALUES for v in row.values()):
                removed_idxs.append(orig_idx)
            else:
                surviving.append((row, orig_idx))

        stats.removed += len(removed_idxs)
        for orig_idx in removed_idxs:
            stats.deleted_reasons[orig_idx] = "NULL 포함"

        if surviving:
            new_data, new_indices = zip(*surviving)
            return list(new_data), stats, list(new_indices)
        return [], stats, []

    # ── 규칙 ③ null → "—" 치환 ───────────────────────────────────────
    def _step_fill_null(
        self, data: list[dict], stats: RefineStats
    ) -> tuple[list[dict], RefineStats]:
        if not self.rules.get("fill_null"):
            return data, stats

        for row in data:
            for k, v in row.items():
                if v in _NULL_VALUES:
                    row[k] = "—"
                    stats.filled += 1
        return data, stats

    # ── 규칙 ④ 문자열 공백 trim ──────────────────────────────────────
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

    # ── 규칙 ⑤ 선택 필드 제외 ───────────────────────────────────────
    def _step_drop_columns(self, data: list[dict]) -> list[dict]:
        if not self.rules.get("drop_columns") or not self.drop_columns:
            return data
        drop_set = set(self.drop_columns)
        return [{k: v for k, v in row.items() if k not in drop_set} for row in data]

    # ── 규칙 ⑥ 숫자 타입 변환 ───────────────────────────────────────
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
