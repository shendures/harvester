"""
preprocess.py — DataCrawler v2.0
수집된 raw 데이터를 정제하는 로직을 전담하는 모듈입니다.

DataRefiner 클래스
  - 6가지 정제 규칙을 순차 적용
  - 원본 데이터를 절대 수정하지 않음 (shallow copy 후 처리)
  - 정제 통계(제거 행 수, 치환 값 수)를 함께 반환

RefineStats 데이터 클래스
  - 정제 결과 수치를 타입 안전하게 전달

load_custom_rule() 함수
  - 수집물(blueprint)마다 다른 사용자 정의 정제 로직을 파일 하나로 플러그인.
  - `request_info.json`과 동일한 경로 정책(BlueprintStorage)을 그대로 따릅니다:
        <앱 데이터 폴더>/{seq_no}.py         — 실제 실행 시 읽는 위치(고객 PC별로 다름)
        <번들 리소스 경로>/{seq_no}.py       — 패키징 시 포함한 고객별 기본값
    최초 실행 시 앱 데이터 폴더에 파일이 없으면 번들 기본값을 그대로 복사해 심고,
    이후에는 앱 데이터 폴더의 사본을 우선 사용합니다(고객 PC에서 직접 수정 가능).
  - 파일에는 아래 둘 중 하나를 정의:
        def refine(data: list[dict]) -> list[dict]: ...       # 전체 목록 단위
        def refine_row(row: dict) -> dict: ...                 # 행 단위
    (둘 다 있으면 refine()을 우선 사용)
  - 해당 seq_no 파일이 없으면 None을 반환 — 호출 측에서 "커스텀 규칙 없음"으로 처리.
  - DataRefiner의 6가지 규칙보다 먼저 적용하는 것을 권장 (원시 데이터를 사이트별로
    정규화한 뒤, 범용 규칙(중복 제거 등)을 그 위에서 실행).

사용 예:
    from preprocess import DataRefiner, RefineStats, load_custom_rule

    rules = {
        "custom_rule":      True,
        "remove_duplicate": True,
        "remove_null_row":  True,
        "fill_null":        True,
        "trim_whitespace":  True,
        "drop_columns":     False,
        "cast_numeric":     False,
    }

    custom_rule = load_custom_rule(seq_no)   # None이면 커스텀 규칙 없음

    refiner = DataRefiner(rules=rules, drop_columns=["brand"], custom_rule=custom_rule)
    refined_data, stats = refiner.run(raw_data)
"""

from __future__ import annotations
import copy
import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable

import utility


# ── 정제 통계 컨테이너 ────────────────────────────────────────────────
@dataclass
class RefineStats:
    """정제 과정에서 발생한 수치를 담는 불변 결과 객체."""
    raw_count:      int  = 0   # 원본 행 수
    refined_count:  int  = 0   # 정제 후 행 수
    removed:        int  = 0   # 제거된 행 수 (중복 + null 행 합산)
    filled:         int  = 0   # null → "—" 치환된 값 수
    deleted_indices: list = field(default_factory=list)  # 제거된 행의 원본 인덱스 목록
    deleted_reasons: dict = field(default_factory=dict)  # {원본인덱스: "중복" | "전체 필드 NULL"}
    modified_rows:  dict = field(default_factory=dict)  # {정제행위치: {컬럼: (변경전, 변경후)}}
    custom_rule_applied: bool     = False  # ⑦ custom_rule 정상 적용 여부
    custom_rule_error:   str | None = None  # ⑦ custom_rule 실행 중 예외 메시지 (있으면 원본 데이터로 폴백)

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
    "custom_rule":       True,  # ⑦ 커스텀 규칙(seq_no, 있으면) 적용
    "remove_duplicate": True,   # 중복 행 제거
    "remove_null_row":  True,   # 모든 필드 null 행 제거
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
        ⑦ custom_rule       — 커스텀 규칙(seq_no, 있고 활성화된 경우) 적용, 나머지보다 먼저 실행
        ① remove_duplicate  — 중복 행 제거
        ② remove_null_row   — 모든 필드 null 행 제거
        ③ fill_null         — 잔존 null → "—" 치환
        ④ trim_whitespace   — 문자열 공백 제거
        ⑤ drop_columns      — 지정 컬럼 제외
        ⑥ cast_numeric      — 숫자 타입 변환
    """

    def __init__(
        self,
        rules:        dict[str, bool] | None = None,
        drop_columns: list[str]       | None = None,
        custom_rule:  Callable[[list[dict]], list[dict]] | None = None,
    ) -> None:
        """
        Args:
            rules:        규칙 활성화 딕셔너리. None이면 DEFAULT_RULES 사용.
            drop_columns: ⑤ drop_columns 규칙 활성 시 제외할 컬럼명 목록.
            custom_rule:  ⑦ custom_rule 규칙 활성 시 실행할 콜러블
                          (`load_custom_rule()`의 반환값). None이면 이 step은 건너뜁니다.
        """
        self.rules:        dict[str, bool] = {**DEFAULT_RULES, **(rules or {})}
        self.drop_columns: list[str]       = drop_columns or []
        self.custom_rule:  Callable[[list[dict]], list[dict]] | None = custom_rule

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

        data, stats = self._step_custom_rule(data, stats)
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
                    stats.modified_rows.setdefault(refined_pos, {})[col] = (raw_val, refined_val)

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

    # ── 규칙 ⑦ 커스텀 규칙(seq_no) 적용 ─────────────────────────────
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

    # ── 규칙 ② 모든 필드 null 행 제거 ───────────────────────────────
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


# ── 사용자 정의 정제 규칙 로더 ─────────────────────────────────────────
def _app_dir() -> str:
    """
    앱 데이터 디렉터리 경로 — BlueprintStorage(request_info.json)와 동일한 정책
    (LOCALAPPDATA/CollectorApp 등)입니다. PyInstaller 설치/임시 디렉터리가 아니라
    이 경로에 두어야 배포 후에도 사용자가 파일을 자유롭게 수정할 수 있습니다.
    """
    if sys.platform == "win32":
        root = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        root = os.path.join(os.path.expanduser("~"), ".config")
    directory = os.path.join(root, "CollectorApp")
    os.makedirs(directory, exist_ok=True)
    return directory


def _resolve_custom_rule_path(seq_no) -> str:
    """
    `{seq_no}.py`의 실제 경로를 결정합니다. request_info.json과 동일한 위치
    정책(BlueprintStorage._initialize_storage와 동일 패턴)을 따릅니다:

    - 앱 데이터 폴더에 파일이 없고 번들 리소스 경로에 기본값이 있으면 최초
      1회 복사해 심습니다(고객별로 패키징에 포함한 기본 규칙).
    - 이후에는 앱 데이터 폴더의 파일을 우선 사용하고, 없으면 번들 리소스
      경로로 폴백합니다.
    """
    filename    = f"{seq_no}.py"
    file_path   = os.path.join(_app_dir(), filename)
    default_source = os.path.join(utility.resource_path(), filename)

    if not os.path.exists(file_path) and os.path.exists(default_source):
        shutil.copy2(default_source, file_path)

    return file_path if os.path.exists(file_path) else default_source


def custom_rule_exists(seq_no) -> bool:
    """
    `{seq_no}.py` 커스텀 정제 규칙 파일의 존재 여부만 확인합니다 — load_custom_rule()과
    달리 파일을 실행(exec)하지 않습니다. 번들 기본값→앱데이터 seed는 동일하게 적용됩니다.
    (예: GUI에서 "규칙 없음"을 안내만 하고 싶을 때, 불필요하게 사용자 코드를 실행하지
    않도록 분리된 가벼운 확인 함수)
    """
    return os.path.isfile(_resolve_custom_rule_path(seq_no))


def load_custom_rule(seq_no):
    """
    request_info.json과 동일한 경로 정책으로 사용자 정의 정제 함수를 로드합니다.

    파일에 refine(data: list[dict]) -> list[dict]가 있으면 그대로 반환하고,
    refine_row(row: dict) -> dict만 있으면 각 행에 적용하는 함수로 감싸서
    list[dict] -> list[dict] 형태의 callable로 반환합니다.

    Returns:
        callable | None — 파일이 없거나 두 함수 모두 없으면 None.

    Raises:
        파일 실행 중 발생한 예외(SyntaxError 등)는 그대로 전파합니다 —
        "규칙 없음"(None)과 "규칙이 있는데 깨져 있음"(예외)을 호출 측이
        구분해 다르게 안내할 수 있도록 의도한 동작입니다.
    """
    path = _resolve_custom_rule_path(seq_no)
    if not os.path.isfile(path):
        return None

    spec = importlib.util.spec_from_file_location(f"custom_rule_{seq_no}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "refine"):
        return module.refine
    if hasattr(module, "refine_row"):
        row_fn = module.refine_row
        return lambda data: [row_fn(row) for row in data]
    return None
