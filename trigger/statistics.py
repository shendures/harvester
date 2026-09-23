# trigger/statistics.py
# StatisticsPanel의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

import calendar
import json
import math
import re
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NamedTuple

from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

import engine
from conf import BlueprintStorage
from .common import (
    store, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_MUTED,
    GREEN, RED, BLUE, AMBER, STATUS_CODE_COLORS,
)

# 수집량 추이 카드의 기간 필터 — layout/statistics.py가 필터 메뉴를 만들 때
# 이 튜플을 그대로 읽어간다. 기간별 구간(시작·칸 수·범위 문구)은 표시 방식에
# 따라 trend_window()가 정한다. 시간대별만 1시간 칸이고 나머지는 1일 칸이다.
TREND_HOURLY, TREND_WEEKLY, TREND_MONTHLY = "시간대별", "주간별", "월별"
TREND_PERIODS = (TREND_HOURLY, TREND_WEEKLY, TREND_MONTHLY)

# 표시 방식 — 최근 N 구간(기본) / 오늘이 속한 일·주·월 전체
TREND_MODE_RECENT, TREND_MODE_CALENDAR = "최근 기준", "현재 일자 기준"

NO_BODY_TEXT = "-"
# 요청 상세 표의 결과 문구 — worker가 기록한 outcome(로그 레벨)을 표시 문구로 옮긴다
REQUEST_RESULTS = {"ok": "성공", "warn": "데이터 누락", "err": "실패"}
REQUEST_RESULT_MISSED, REQUEST_RESULT_UNKNOWN = "미수집", "-"
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7
DAYS_IN_MONTH_MAX = 31
WEEKDAY_LABELS = ("일", "월", "화", "수", "목", "금", "토")

# 전체 보기 팝업의 칸 설명 — 기간의 한 주기(하루/한 주/한 달) 안의 칸을 전체
# 이력에 걸쳐 접어서 합산한다. layout/statistics.py가 툴팁·팝업 제목에 그대로 쓴다.
TREND_ALL_TIME_CAPTIONS = {
    TREND_HOURLY: "00~23시 누적",
    TREND_WEEKLY: "요일별 누적",
    TREND_MONTHLY: "일자별 누적",
}

# 통계 "응답 결과 구성" 카드의 4분류 — 표시 순서와 색을 한곳에 묶는다.
# "연결 실패"에 TEXT_MUTED를 쓰는 건 대시보드 실시간 테이블이 상태 코드 "000"에 쓰는
# 색(STATUS_CODE_COLORS)과 색 언어를 맞추기 위해서다.
OUTCOME_OK, OUTCOME_EMPTY = "정상 수집", "데이터 누락"
OUTCOME_HTTP_ERR, OUTCOME_CONN_FAIL = "HTTP 오류", "연결 실패"
OUTCOME_SEGMENTS = (
    (OUTCOME_HTTP_ERR, RED), (OUTCOME_CONN_FAIL, TEXT_MUTED),
    (OUTCOME_OK, GREEN), (OUTCOME_EMPTY, AMBER),
)


# "응답 속도 구간" 카드의 구간 경계(초) — 라벨 문구도 이 값에서 만들어 화면·툴팁이
# 경계와 어긋나지 않게 한다.
SPEED_FAST_MAX, SPEED_NORMAL_MAX, SPEED_SLOW_MAX = 0.5, 2.0, 5.0


def speed_secs(value: float) -> str:
    """구간 경계를 라벨용 문자열로 — 정수는 소수점을 떼서 "2.0"이 아닌 "2"로 보인다."""
    return f"{value:g}"


SPEED_FAST = f"빠름 ({speed_secs(SPEED_FAST_MAX)}초 미만)"
SPEED_NORMAL = f"보통 ({speed_secs(SPEED_FAST_MAX)}~{speed_secs(SPEED_NORMAL_MAX)}초)"
SPEED_SLOW = f"느림 ({speed_secs(SPEED_NORMAL_MAX)}~{speed_secs(SPEED_SLOW_MAX)}초)"
SPEED_VERY_SLOW = f"매우 느림 ({speed_secs(SPEED_SLOW_MAX)}초 이상)"
SPEED_SEGMENTS = (
    (SPEED_FAST, GREEN), (SPEED_NORMAL, BLUE),
    (SPEED_SLOW, AMBER), (SPEED_VERY_SLOW, RED),
)


def _speed_bucket(latency: float) -> str:
    """응답 시간을 4구간 중 하나로 분류한다 — 경계값은 느린 쪽에 넣는다(0.5초는 "보통")."""
    if latency < SPEED_FAST_MAX:
        return SPEED_FAST
    if latency < SPEED_NORMAL_MAX:
        return SPEED_NORMAL
    if latency < SPEED_SLOW_MAX:
        return SPEED_SLOW
    return SPEED_VERY_SLOW


BLOCKED_STATUS_CODES = ("403", "429")

# 엔진이 상태 코드를 받지 못했을 때(연결 실패 등) 넣는 값(engine.py) — HTTP 응답이 아니라
# 상태 코드 분포 카드에는 넣지 않고 "응답 결과 구성"의 연결 실패로 집계한다
NO_STATUS_CODE = "000"

# 상태 코드 분포에서 표에 없는 코드를 한 행으로 합쳐 표시하는 이름 — 코드 종류가 몇 개든 행 수를
# 최대 7행으로 묶어 카드 고정 높이 안에서 글자가 겹치지 않게 한다.
STATUS_OTHER_LABEL = "기타"

# 상태 코드 분포 도움말 툴팁에 적는 코드별 쉬운 말 — 막대 라벨에는 코드만 표시한다
STATUS_CODE_MEANINGS = {
    "200": "정상", "301": "이동", "403": "접근 거부", "404": "페이지 없음",
    "429": "요청 과다", "500": "서버 오류",
}

DIAG_OK, DIAG_WARN, DIAG_PROBLEM, DIAG_PENDING = "정상", "주의", "문제", "대기"
# 지표 단위 등급 — 신뢰구간이 임계값을 걸쳐 어느 쪽으로도 단정할 수 없는 상태
DIAG_HOLD = "보류"
DIAG_LEVEL_COLORS = {
    DIAG_OK: GREEN, DIAG_WARN: AMBER, DIAG_PROBLEM: RED,
    DIAG_PENDING: TEXT_MUTED, DIAG_HOLD: TEXT_MUTED,
}
# 종합 등급은 지표별 등급 중 가장 나쁜 것을 따른다 — 보류는 "아직 모름"이라 최하위
DIAG_LEVEL_RANK = {DIAG_HOLD: 0, DIAG_OK: 1, DIAG_WARN: 2, DIAG_PROBLEM: 3}

GRADE_ORDER = (DIAG_OK, DIAG_WARN, DIAG_PROBLEM, DIAG_HOLD, DIAG_PENDING)
GRADE_MEANINGS = {
    DIAG_OK: "이상 신호가 없습니다",
    DIAG_WARN: "확인이 필요한 값이 있습니다",
    DIAG_PROBLEM: "바로 점검이 필요합니다",
    DIAG_HOLD: "데이터가 부족해 아직 판단하지 않습니다",
    DIAG_PENDING: "판단할 수집 기록이 아직 없습니다",
}

CONFIDENCE_Z = 1.96      # 95% 양측 신뢰수준의 표준정규 분위수
CONFIDENCE_Z_STRICT = 2.576   # 99% 양측 — 크게 불안정("문제")을 줄 때 요구하는 더 강한 근거
RECENT_WINDOW = 100      # 최근 악화 감지가 보는 최근 응답 수
MIN_COMPARE = 30         # 최근/이전 구간 비교에 필요한 각 구간의 최소 응답 수
BANNER_MAX_CAUSES = 2    # 배너에 이어 붙이는 원인 문장 수 — 나머지는 상세 보기에서 본다

# 회차별 패턴 판정 — 여러 번 수집했을 때 결과가 회차마다 일정하면 정상, 들쭉날쭉하면 정상으로 보지 않는다.
PATTERN_WINDOW = 5              # 배너가 판정하는 최근 수집 회차 수 — 이보다 오래된 이력은 판정에서 뺀다
PATTERN_MIN_SESSIONS = 3        # 패턴 판정을 시작하는 데 필요한 완료된 수집 회차 수
YIELD_NOISE_K = 6.0             # 수집량 편차가 회차 간 자체 노이즈의 몇 배를 넘어야 불안정으로 보는지
PATTERN_SPREAD_WARN = 0.10      # 회차 간 편차가 이 이상이면 불안정("주의") — 비율은 %p 차이, 수집량은 상대 편차
PATTERN_SPREAD_PROBLEM = 0.30   # 이 이상이면 크게 불안정("문제")
SMALL_SESSION_RESPONSES = 30    # 회차당 응답이 이보다 적으면 한 회차의 작은 이상을 놓칠 수 있다고 알린다
PATTERN_ADVICE = "사이트 상태나 설정이 회차마다 달라졌는지 확인하세요."

# 판정에 쓰지 않고 상세 팝업에 참고값으로만 적는 KPI의 이름
REF_AVG_LATENCY, REF_THROUGHPUT = "평균 응답", "처리량"

# 평가 축 — 통계 화면의 카드 하나가 축 하나에 대응한다
AXIS_CONNECTION = "연결 안정성"
AXIS_RESPONSE = "응답 정상성"
AXIS_YIELD = "수집 성과"
AXIS_QUALITY = "데이터 품질"
AXIS_PERFORMANCE = "응답 성능"

# 축별 최소 수집 횟수 — 응답을 아무리 많이 모아도 한 번의 수집이면 독립적인 관측이 아니라서,
# 개수 게이트와 별개로 수집 횟수를 본다. 연결·응답은 지금 당장 조치가 필요한 문제라 1회부터
# 알리고, 추출 규칙의 구조적 품질일수록 여러 번 봐야 판단할 수 있어 더 기다린다.
AXIS_MIN_SESSIONS = {
    AXIS_CONNECTION: 1, AXIS_RESPONSE: 1,
    AXIS_YIELD: 2, AXIS_PERFORMANCE: 2,
    AXIS_QUALITY: 3,
}

# 종합 평가 표의 "평가 축" 기본 정렬 순서
AXIS_DISPLAY_ORDER = (AXIS_PERFORMANCE, AXIS_CONNECTION, AXIS_RESPONSE, AXIS_YIELD, AXIS_QUALITY)
AXIS_RANK = {axis: i for i, axis in enumerate(AXIS_DISPLAY_ORDER)}


class MetricSpec(NamedTuple):
    """지표 하나의 판정 기준 — 임계값을 여기에서만 정의해 배너·상세 표·툴팁이 같은 값을 읽는다.
    higher_is_better면 값이 클수록 좋은 지표라 부등호를 뒤집고, percent면 백분율로 표시한다.
    sample_unit은 지표마다 분모가 다르기 때문에 둔다(응답 / 추출된 행 / 회차).
    pattern_only면 절대 기준 없이 회차별 패턴으로만 판정하며, warn·problem은 회차 간 편차 기준이다."""
    axis: str
    name: str
    warn: float
    problem: float
    higher_is_better: bool
    percent: bool
    sample_unit: str
    cause: str
    remedy: str
    pattern_only: bool = False

    @property
    def advice(self) -> str:
        """원인과 해결 방법을 이은 한 문장 — 배너와 표 행 툴팁이 쓴다."""
        return f"{self.cause} {self.remedy}"


# 임계값은 모두 경험적 기본값이다 — 상세 보기 표에 기준을 함께 노출해 실측 후 조정할 수 있게 한다.
SPEC_CONN_FAIL = MetricSpec(
    AXIS_CONNECTION, "연결 실패율", 0.05, 0.20, False, True, "건",
    "사이트에 연결하지 못했습니다.", "인터넷 연결이나 프록시 설정을 확인하세요.")
SPEC_BLOCKED = MetricSpec(
    AXIS_RESPONSE, "접근 차단율", 0.05, 0.20, False, True, "건",
    "사이트가 접근을 막고 있습니다.", "수집 간격을 늘리거나 프록시를 사용하세요.")
SPEC_HTTP_ERR = MetricSpec(
    AXIS_RESPONSE, "HTTP 오류율", 0.10, 0.30, False, True, "건",
    "일부 페이지에서 오류 응답을 받았습니다.", "상태 코드 분포에서 오류 종류를 확인하세요.")
SPEC_EMPTY = MetricSpec(
    AXIS_YIELD, "데이터 누락률", 0.30, 0.60, False, True, "건",
    "페이지는 열렸지만 데이터를 찾지 못했습니다.",
    "사이트 구조가 바뀌었을 수 있으니 수집 조건을 확인하세요.")
SPEC_VALID = MetricSpec(
    AXIS_QUALITY, "유효 데이터 비율", 0.90, 0.70, True, True, "행",
    "꺼낸 데이터에 빈 항목이 많습니다.", "추출 규칙이 일부 항목을 못 찾고 있는지 확인하세요.")
SPEC_SESSION_ITEMS = MetricSpec(
    AXIS_QUALITY, "페이지당 수집량", PATTERN_SPREAD_WARN, PATTERN_SPREAD_PROBLEM, False, False, "회차",
    "수집 회차마다 페이지당 수집량이 달라졌습니다.",
    "사이트 구조가 바뀌었거나 일부 페이지가 빠지고 있는지 확인하세요.",
    pattern_only=True)
SPEC_SLOW = MetricSpec(
    AXIS_PERFORMANCE, "지연 응답 비율", 0.30, 0.60, False, True, "건",
    "응답이 느린 쪽에 몰려 있습니다.", "사이트가 혼잡하거나 수집 간격·동시 요청 설정을 점검할 때입니다.")

# 최근 구간과 이전 구간을 비교한 결과
TREND_WORSE, TREND_BETTER, TREND_FLAT = "악화", "개선", "변화 없음"


class Diagnosis(NamedTuple):
    level: str
    color: str
    detail: str


class PatternResult(NamedTuple):
    """지표 하나의 회차별 패턴 — values는 회차 순서의 값(비율 또는 페이지당 수집량), spread는
    그 편차(비율은 최대-최소, 수집량은 (최대-최소)/평균), level은 일정 여부에 따른 등급이다."""
    level: str
    values: tuple
    spread: float


class MetricVerdict(NamedTuple):
    """지표 하나의 판정 결과 — 신뢰구간을 쓰지 않는 지표(페이지당 수집량)는 low/high가 None이고,
    pattern은 회차별 패턴을 판정할 수 있을 때(완료된 수집 PATTERN_MIN_SESSIONS회 이상)만 채운다.
    live는 진행 중이거나 중단된 수집의 응답이 절대 판정을 끌어올려 등급이 정해졌음을, absolved는
    절대 판정은 "주의"였으나 회차 패턴이 일정해 정상으로 본 지표임을 뜻한다."""
    spec: MetricSpec
    level: str
    observed: float | None
    low: float | None
    high: float | None
    sample: int
    pattern: PatternResult | None = None
    live: bool = False
    absolved: bool = False


class Regression(NamedTuple):
    """최근 구간과 그 이전 구간의 정상 수집률 비교 — z는 두 비율 차이의 검정통계량."""
    trend: str
    recent_rate: float
    prior_rate: float
    recent_n: int
    prior_n: int
    z: float


class RowFacts(NamedTuple):
    """응답 1건에서 뽑은 회차 집계용 값 — 행마다 한 번만 계산해 합산 집계와 회차별 집계가
    같은 분류를 쓰게 한다. bucket은 응답 시간이 없으면 None, item_count는 정수가 아니면 None."""
    code: str
    outcome: str
    bucket: str | None
    item_count: int | None
    complete_rows: int
    field_items: int


@dataclass
class SessionTally:
    """수집 1회에 귀속된 응답의 집계 — 회차별 패턴 판정의 입력이다. timed는 응답 시간이
    기록된 응답 수로 지연 응답 비율의 분모이고, ok_pages·ok_items는 데이터를 가져온
    페이지 수와 그 추출 건수 합이다."""
    responses: int = 0
    conn_fail: int = 0
    blocked: int = 0
    http_err: int = 0
    empty: int = 0
    slow: int = 0
    timed: int = 0
    complete_rows: int = 0
    field_items: int = 0
    ok_pages: int = 0
    ok_items: int = 0

    def add(self, facts: RowFacts) -> None:
        self.responses += 1
        self.conn_fail += facts.outcome == OUTCOME_CONN_FAIL
        self.blocked += facts.code in BLOCKED_STATUS_CODES
        self.http_err += facts.outcome == OUTCOME_HTTP_ERR
        self.empty += facts.outcome == OUTCOME_EMPTY
        if facts.bucket is not None:
            self.timed += 1
            self.slow += facts.bucket in (SPEED_SLOW, SPEED_VERY_SLOW)
        self.complete_rows += facts.complete_rows
        self.field_items += facts.field_items
        if facts.outcome == OUTCOME_OK and facts.item_count is not None:
            self.ok_pages += 1
            self.ok_items += facts.item_count


class EvalWindow(NamedTuple):
    """배너가 판정하는 최근 수집 구간 — agg는 그 구간 응답의 집계(회차별 per_session 포함)이고,
    responses는 구간의 응답 수, sessions는 구간 안 수집 횟수(진행 중 1회 포함), all_sessions는
    초기화 이후 전체 수집 횟수다."""
    agg: dict
    responses: int
    sessions: int
    all_sessions: int


EMPTY_WINDOW = EvalWindow({}, 0, 0, 0)


class Evaluation(NamedTuple):
    """배너에 쓸 종합 판정과 상세 보기에 쓸 지표별 근거 — sessions·all_sessions는 판정 범위
    안내에 쓸 판정 시점의 수집 횟수로, 팝업이 열릴 때의 값을 같은 스냅샷에서 읽게 한다."""
    diagnosis: Diagnosis
    verdicts: list
    regression: Regression | None
    sessions: int
    all_sessions: int
    session_size: float


def _wilson_bounds(hits: int, sample: int) -> tuple:
    """이항 비율의 Wilson 점수 신뢰구간(95%). 표본이 적으면 구간이 넓어져 어느 쪽으로도
    단정할 수 없게 되므로, hits/sample을 임계값과 바로 비교할 때 생기는 소표본 오판
    (예: 2/10을 20%로 읽어 "문제"로 단정)을 막는다. sample은 1 이상이어야 한다."""
    p = hits / sample
    z_sq = CONFIDENCE_Z ** 2
    denom = 1 + z_sq / sample
    center = (p + z_sq / (2 * sample)) / denom
    margin = CONFIDENCE_Z * math.sqrt(p * (1 - p) / sample + z_sq / (4 * sample ** 2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _two_proportion_z(hits_a: int, n_a: int, hits_b: int, n_b: int) -> float:
    """두 비율 차이의 z 통계량(합동 표준오차 기준) — 음수면 A쪽 비율이 더 낮다는 뜻."""
    pooled = (hits_a + hits_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    return (hits_a / n_a - hits_b / n_b) / se if se else 0.0


def _chi2_critical(df: int, z: float = CONFIDENCE_Z) -> float:
    """자유도 df 카이제곱 분포의 상위 임계값 — Wilson–Hilferty 근사라 scipy 없이 표준
    라이브러리만으로 구한다. z가 CONFIDENCE_Z면 단측 97.5%, CONFIDENCE_Z_STRICT면 99.5%다."""
    scale = 2 / (9 * df)
    return df * (1 - scale + z * math.sqrt(scale)) ** 3


def _chi2_statistic(series: list) -> float:
    """회차별 (건수, 표본)이 하나의 공통 비율에서 벗어난 정도 — 동질성 카이제곱 통계량이다.
    공통 비율이 0 또는 1이면 모든 회차가 같아 검정할 것이 없으므로 0이다."""
    pooled = sum(hits for hits, _ in series) / sum(sample for _, sample in series)
    if pooled in (0.0, 1.0):
        return 0.0
    return sum((hits - sample * pooled) ** 2 / (sample * pooled * (1 - pooled))
               for hits, sample in series)


def _spread_level(spread: float) -> str:
    """회차 간 편차의 크기를 등급으로 — 비율(%p 차이)과 수집량(상대 편차)이 같은 기준을 쓴다."""
    if spread >= PATTERN_SPREAD_PROBLEM:
        return DIAG_PROBLEM
    return DIAG_WARN if spread >= PATTERN_SPREAD_WARN else DIAG_OK


def _judge_pattern_rate(series: list) -> PatternResult:
    """회차별 비율이 일정한지 판정한다. 우연 변동을 막는 통계적 유의(동질성 카이제곱)와
    표본이 커서 무의미한 차이까지 잡아내는 것을 막는 실질 편차(PATTERN_SPREAD_WARN)를
    모두 넘어야 불안정으로 본다. 회차당 응답이 적으면 유의하다고 나오는 순간 편차가 거의
    항상 커서 유의수준이 그대로 "문제" 오탐이 되므로, "문제"는 더 엄격한
    유의수준(CONFIDENCE_Z_STRICT)까지 넘을 때만 주고 못 넘으면 "주의"로 둔다."""
    rates = tuple(hits / sample for hits, sample in series)
    spread = max(rates) - min(rates)
    chi2, df = _chi2_statistic(series), len(series) - 1
    if chi2 <= _chi2_critical(df):
        return PatternResult(DIAG_OK, rates, spread)
    level = _spread_level(spread)
    if level == DIAG_PROBLEM and chi2 <= _chi2_critical(df, CONFIDENCE_Z_STRICT):
        level = DIAG_WARN
    return PatternResult(level, rates, spread)


def _noise_scale(values: tuple) -> float:
    """연속한 회차 값의 차이 중 작은 쪽 절반의 평균 — 회차 간 자연 변동의 크기 추정치다. 이상
    회차가 만드는 큰 차이를 버려야, 그 이상이 자기 자신의 노이즈 추정을 부풀려 가리지 않는다."""
    steps = sorted(abs(b - a) for a, b in zip(values, values[1:]))
    kept = steps[:(len(steps) + 1) // 2]
    return sum(kept) / len(kept)


def _judge_pattern_items(tallies: list) -> PatternResult | None:
    """회차별 정상 수집 페이지당 평균 수집량이 일정한지 판정한다. 비율 지표처럼 통계와 실질
    편차를 모두 넘어야 불안정으로 본다 — 편차가 회차 간 자체 노이즈(_noise_scale)의
    YIELD_NOISE_K배를 넘는지가 통계, PATTERN_SPREAD_WARN 이상인지가 실질이다. 노이즈가 0이면
    (회차마다 값이 같으면) 통계 조건은 저절로 충족된다. 평균이 0이면 편차가 정의되지 않아 보류."""
    per_page = tuple(t.ok_items / t.ok_pages for t in tallies if t.ok_pages)
    if len(per_page) < PATTERN_MIN_SESSIONS:
        return None
    mean = sum(per_page) / len(per_page)
    if mean == 0:
        return PatternResult(DIAG_HOLD, per_page, 0.0)
    span = max(per_page) - min(per_page)
    level = _spread_level(span / mean) if span > YIELD_NOISE_K * _noise_scale(per_page) else DIAG_OK
    return PatternResult(level, per_page, span / mean)


def _session_gated(spec: MetricSpec, sessions: int) -> bool:
    """수집 횟수가 이 지표의 축 기준에 못 미쳐 아직 등급을 매기지 않을지."""
    return sessions < AXIS_MIN_SESSIONS[spec.axis]


def _is_gate_pending(verdict: MetricVerdict, sessions: int) -> bool:
    """수집 횟수 게이트 때문에 보류 중인지 — 게이트를 건너뛰고 이미 등급이 매겨진 지표는 제외한다."""
    return verdict.level == DIAG_HOLD and _session_gated(verdict.spec, sessions)


def _ratio_level(spec: MetricSpec, low: float, high: float) -> str:
    """신뢰구간이 임계값 한쪽에 온전히 놓일 때만 등급을 매기고, 걸치면 보류한다."""
    if spec.higher_is_better:
        if high <= spec.problem:
            return DIAG_PROBLEM
        if high < spec.warn:
            return DIAG_WARN
        return DIAG_OK if low >= spec.warn else DIAG_HOLD
    if low >= spec.problem:
        return DIAG_PROBLEM
    if low >= spec.warn:
        return DIAG_WARN
    return DIAG_OK if high < spec.warn else DIAG_HOLD


def _judge_ratio(spec: MetricSpec, hits: int, sample: int, sessions: int) -> MetricVerdict:
    """비율 지표 하나를 Wilson 신뢰구간으로 판정한다. 표본이 0이면 보류하고, 수집 횟수가
    모자라면 값·구간은 그대로 계산해 두고 등급만 보류한다 — 화면 위 KPI 카드가 이미 같은
    숫자를 보여주고 있어 상세 표에서 "—"로 비면 카드와 어긋난다."""
    if sample == 0:
        return MetricVerdict(spec, DIAG_HOLD, None, None, None, 0)
    low, high = _wilson_bounds(hits, sample)
    # 데이터 누락 100%는 수집 횟수를 기다릴 이유가 없다 — 표본이 충분해 신뢰구간이 문제 기준을 넘으면 첫 수집부터 판정
    all_empty = spec is SPEC_EMPTY and hits == sample
    gated = _session_gated(spec, sessions) and not all_empty
    level = DIAG_HOLD if gated else _ratio_level(spec, low, high)
    return MetricVerdict(spec, level, hits / sample, low, high, sample)


def _ratio_samples(total: int, agg: dict) -> list:
    """(지표, 해당 건수, 분모) 목록 — 분모가 지표마다 다르다는 점이 핵심이다.
    유효 데이터 비율은 추출된 행, 지연 응답 비율은 응답 시간이 기록된 응답이 분모라
    전체 응답 수 하나로 표본 충분 여부를 판단할 수 없다."""
    outcome, speed = agg["outcome"], agg["speed"]
    return [
        (SPEC_CONN_FAIL, outcome.get(OUTCOME_CONN_FAIL, 0), total),
        (SPEC_BLOCKED, agg["blocked"], total),
        (SPEC_HTTP_ERR, outcome.get(OUTCOME_HTTP_ERR, 0), total),
        (SPEC_EMPTY, outcome.get(OUTCOME_EMPTY, 0), total),
        (SPEC_VALID, agg["complete_rows"], agg["field_items"]),
        (SPEC_SLOW, speed.get(SPEED_SLOW, 0) + speed.get(SPEED_VERY_SLOW, 0),
         sum(speed.values())),
    ]


# 비율 지표별 회차 집계의 (건수, 표본) 필드 — _ratio_samples()의 합산 분자·분모와 같은 정의다
SESSION_RATIO_FIELDS = {
    SPEC_CONN_FAIL: ("conn_fail", "responses"),
    SPEC_BLOCKED: ("blocked", "responses"),
    SPEC_HTTP_ERR: ("http_err", "responses"),
    SPEC_EMPTY: ("empty", "responses"),
    SPEC_VALID: ("complete_rows", "field_items"),
    SPEC_SLOW: ("slow", "timed"),
}


def _session_pattern(spec: MetricSpec, tallies: list) -> PatternResult | None:
    """지표의 회차별 패턴 — 표본이 있는 회차가 PATTERN_MIN_SESSIONS개에 못 미치면 None."""
    if spec.pattern_only:
        return _judge_pattern_items(tallies)
    hits_field, sample_field = SESSION_RATIO_FIELDS[spec]
    series = [(getattr(t, hits_field), getattr(t, sample_field))
              for t in tallies if getattr(t, sample_field)]
    return _judge_pattern_rate(series) if len(series) >= PATTERN_MIN_SESSIONS else None


def _unpatterned_floor(verdict: MetricVerdict, tallies: list) -> str:
    """패턴 시리즈에 편입되지 않은 응답(진행 중이거나 중단된 수집)이 절대 판정을 끌어올렸다면 그
    등급을, 아니면 보류를 돌려준다. 전체 응답 기준 절대 등급(verdict.level)이 완료된 회차만의
    절대 등급보다 나쁠 때만 끌어올린 것으로 보므로, 완료된 이력이 일정하게 "주의"인 경우는
    새 수집이 시작돼도 등급이 흔들리지 않는다."""
    hits_field, sample_field = SESSION_RATIO_FIELDS[verdict.spec]
    completed = _judge_ratio(verdict.spec,
                             sum(getattr(t, hits_field) for t in tallies),
                             sum(getattr(t, sample_field) for t in tallies),
                             len(tallies)).level
    raised = DIAG_LEVEL_RANK[verdict.level] > DIAG_LEVEL_RANK[completed]
    return verdict.level if raised else DIAG_HOLD


def _with_pattern(verdict: MetricVerdict, tallies: list) -> MetricVerdict:
    """절대 판정에 회차별 패턴을 결합한다 — 일관성이 우선이라 패턴이 일정하면 절대 기준이
    "주의"이거나 보류여도 정상으로 보되, 절대 기준이 "문제"인 값은 일정해도 문제로 둔다
    (매번 전량 실패하는 수집이 일정하다는 이유로 정상이 되지 않게 하는 안전망). 패턴은 완료된
    회차만 보므로, 시리즈 밖 응답이 절대 판정을 끌어올린 부분은 사면하지 않고 그대로 남긴다."""
    pattern = _session_pattern(verdict.spec, tallies)
    if pattern is None:
        return verdict
    if verdict.spec.pattern_only:
        verdict = verdict._replace(observed=sum(pattern.values) / len(pattern.values),
                                   sample=len(pattern.values))
    level = DIAG_PROBLEM if verdict.level == DIAG_PROBLEM else pattern.level
    floor = DIAG_HOLD if verdict.spec.pattern_only else _unpatterned_floor(verdict, tallies)
    live = DIAG_LEVEL_RANK[floor] > DIAG_LEVEL_RANK[level]
    final = floor if live else level
    # 절대 기준을 넘었는데 패턴이 일정해 정상이 된 지표 — 등급은 정상이지만 배너와 상세 보기가 밝힌다
    absolved = verdict.level == DIAG_WARN and DIAG_LEVEL_RANK[final] < DIAG_LEVEL_RANK[DIAG_WARN]
    return verdict._replace(level=final, pattern=pattern, live=live, absolved=absolved)


def _recent_split(total: int, agg: dict) -> tuple:
    """(최근 정상 수집 수, 최근 응답 수, 이전 정상 수집 수, 이전 응답 수) — 이전 구간은
    누계에서 최근 창을 빼서 구하므로 행을 다시 순회하지 않는다."""
    recent = agg["recent_ok"]
    recent_n, recent_ok = len(recent), sum(recent)
    return recent_ok, recent_n, agg["outcome"].get(OUTCOME_OK, 0) - recent_ok, total - recent_n


def detect_regression(recent_ok: int, recent_n: int,
                      prior_ok: int, prior_n: int) -> Regression | None:
    """최근 구간과 이전 구간의 정상 수집률을 2-표본 비율 z-검정으로 비교한다. 누적 전체
    비율만 보면 과거 정상분에 묻혀 최근 악화가 드러나지 않기 때문에 따로 본다.
    양쪽 표본이 MIN_COMPARE에 못 미치면 비교하지 않고 None."""
    if recent_n < MIN_COMPARE or prior_n < MIN_COMPARE:
        return None
    z = _two_proportion_z(recent_ok, recent_n, prior_ok, prior_n)
    if z <= -CONFIDENCE_Z:
        trend = TREND_WORSE
    elif z >= CONFIDENCE_Z:
        trend = TREND_BETTER
    else:
        trend = TREND_FLAT
    return Regression(trend, recent_ok / recent_n, prior_ok / prior_n, recent_n, prior_n, z)


REGRESSION_REMEDY = "최근 실행 설정과 대상 사이트를 확인하세요."


def _regression_cause(regression: Regression) -> str:
    return (f"최근 {regression.recent_n}건의 정상 수집률이 {regression.recent_rate:.0%}로 "
            f"이전 {regression.prior_n}건({regression.prior_rate:.0%})보다 크게 낮아졌습니다.")


def regression_text(regression: Regression) -> str:
    """최근 악화 문장 — 배너와 상세 보기가 같은 문구를 쓴다."""
    return f"{_regression_cause(regression)} {REGRESSION_REMEDY}"


def _worst_level(verdicts: list) -> str:
    """지표별 등급 중 가장 나쁜 것 — 전부 보류면 보류."""
    return max((v.level for v in verdicts), key=lambda level: DIAG_LEVEL_RANK[level],
               default=DIAG_HOLD)


def _next_gate(verdicts: list, sessions: int) -> int | None:
    """게이트에 걸려 보류 중인 축 가운데 가장 먼저 풀리는 기준 수집 횟수. 없으면 None."""
    pending = [AXIS_MIN_SESSIONS[v.spec.axis] for v in verdicts
               if _is_gate_pending(v, sessions)]
    return min(pending) if pending else None


def _pending_detail(verdicts: list, sessions: int, total: int) -> str:
    """전부 보류일 때의 안내 — 수집 횟수가 모자란 건지, 응답 표본이 적은 건지 구분한다."""
    gate = _next_gate(verdicts, sessions)
    if gate is not None:
        return (f"수집 {sessions}회로는 아직 판단하기 어렵습니다. "
                f"수집 {gate}회부터 평가를 시작합니다(현재 응답 {total}건).")
    return (f"수집 기록이 적어 아직 판단하기 어렵습니다(현재 {total}건). "
            "응답이 더 쌓이면 자동으로 판정합니다.")


def _is_unstable(verdict: MetricVerdict) -> bool:
    """회차별 패턴이 일정하지 않아 등급이 매겨졌는지."""
    return verdict.pattern is not None and verdict.pattern.level in (DIAG_WARN, DIAG_PROBLEM)


def _cause_text(verdict: MetricVerdict) -> str:
    """배너에 적는 원인 문장 — 패턴이 흔들렸다면 그 사실을, 아니면 지표가 나쁠 때의 조치를
    적는다. 지표명이 모두 받침으로 끝나 조사 "이"가 어색하지 않다."""
    if _is_unstable(verdict):
        return f"{verdict.spec.name}이 수집 회차마다 일정하지 않습니다({_pattern_range_text(verdict)})."
    return verdict.spec.advice


def _absolved_text(absolved: list) -> str:
    """일정해서 정상으로 본 지표 중 절대 기준을 넘는 값의 안내 — 지표명·값·기준을
    BANNER_MAX_CAUSES개까지 적고 나머지는 개수로 줄인다."""
    shown = [f"{v.spec.name} {metric_value_text(v.spec, v.observed)}"
             f"(주의 {_threshold_text(v.spec, v.spec.warn)} {_criteria_compare(v.spec)})"
             for v in absolved[:BANNER_MAX_CAUSES]]
    rest = len(absolved) - BANNER_MAX_CAUSES
    return "·".join(shown) + (f" 외 {rest}개" if rest > 0 else "")


def _pattern_runs(verdicts: list) -> int:
    """회차별 패턴으로 판정한 수집 회차 수 — 패턴 판정을 하지 않았으면 0."""
    return max((len(v.pattern.values) for v in verdicts if v.pattern), default=0)


def _banner_diagnosis(verdicts: list, regression, total: int, sessions: int) -> Diagnosis:
    """종합 등급과 배너 문장을 만든다. 등급은 지표 중 가장 나쁜 것을 따르되, 최근 악화가
    잡히면 최소 "주의"로 올린다 — 누적 비율은 정상이어도 지금 수집이 무너졌을 수 있다."""
    worsened = regression is not None and regression.trend == TREND_WORSE
    level = _worst_level(verdicts)
    if worsened and DIAG_LEVEL_RANK[level] < DIAG_LEVEL_RANK[DIAG_WARN]:
        level = DIAG_WARN

    if level == DIAG_HOLD:
        return Diagnosis(DIAG_PENDING, DIAG_LEVEL_COLORS[DIAG_PENDING],
                         _pending_detail(verdicts, sessions, total))

    # 원인 문장은 "이 지표가 나쁠 때"의 설명이라 정상 등급에서는 쓰지 않는다
    shown = ([v for v in verdicts if v.level == level][:BANNER_MAX_CAUSES]
             if level in (DIAG_WARN, DIAG_PROBLEM) else [])
    causes = [_cause_text(v) for v in shown]
    if any(_is_unstable(v) for v in shown):
        causes.append(PATTERN_ADVICE)
    if worsened:
        causes.append(regression_text(regression))
    if not causes:
        runs = _pattern_runs(verdicts)
        absolved = [v for v in verdicts if v.absolved]
        if absolved:
            # 일정해서 정상으로 본 것이지 값이 괜찮다는 뜻이 아니므로 "정상적으로 진행"이라 단정하지 않는다
            causes = [f"최근 {runs}회 수집 결과는 일정하지만 절대 기준을 넘는 값이 있습니다 — "
                      f"{_absolved_text(absolved)}. 사이트의 원래 특성인지 확인하세요."]
        else:
            # 회차별 패턴으로 판정했다면 확인한 근거가 페이지 수가 아니라 회차의 일정함이다
            causes = ["수집이 정상적으로 진행되고 있습니다. "
                      + (f"최근 {runs}회 수집 결과가 일정합니다." if runs
                         else f"확인한 페이지 {total}개에서 이상 신호가 없습니다.")]
        # 정상인데 아직 안 본 축이 남아 있으면 "전부 확인했다"는 오해가 생기므로 함께 밝힌다
        gate = _next_gate(verdicts, sessions)
        if gate is not None:
            causes.append("아직 평가하지 않은 항목이 있습니다 — "
                          f"수집 {gate}회부터 순차로 판정합니다(현재 {sessions}회).")
    return Diagnosis(level, DIAG_LEVEL_COLORS[level], " ".join(causes))


def evaluate(total: int, agg: dict, window: EvalWindow) -> Evaluation:
    """통계 화면 5개 카드의 KPI를 판정해 종합 평가를 만든다. 지표 판정은 최근 수집 구간(window)만
    본다 — 초기화 이후 전체를 보면 과거의 이상이 회복 뒤에도 배너에 남기 때문이다. 지표마다
    신뢰구간과 축별 수집 횟수로 절대 판정을 하고, 완료된 수집이 PATTERN_MIN_SESSIONS회
    이상이면 회차별 패턴의 일정함을 결합한다. total(초기화 이후 전체 응답 수)이 0이면 집계가
    비어 있으므로(화면 조립 시의 evaluate(0, {}, EMPTY_WINDOW)) 바로 대기로 끝낸다."""
    sessions = window.sessions
    if total == 0:
        return Evaluation(
            Diagnosis(DIAG_PENDING, DIAG_LEVEL_COLORS[DIAG_PENDING],
                      "아직 수집 기록이 없습니다. 상단 ▶ 시작 버튼으로 수집을 실행하세요."),
            [], None, sessions, window.all_sessions, 0.0)

    verdicts = [_judge_ratio(spec, hits, sample, sessions)
                for spec, hits, sample in _ratio_samples(window.responses, window.agg)]
    # 절대 기준이 없는 지표라 패턴을 판정하기 전까지는 보류다
    verdicts.append(MetricVerdict(SPEC_SESSION_ITEMS, DIAG_HOLD, None, None, None, 0))
    verdicts.sort(key=lambda v: AXIS_RANK[v.spec.axis])
    tallies = window.agg["per_session"]
    if len(tallies) >= PATTERN_MIN_SESSIONS:
        verdicts = [_with_pattern(v, tallies) for v in verdicts]
    session_size = sum(t.responses for t in tallies) / len(tallies) if tallies else 0.0
    # 최근 악화는 회차 안의 변화를 보는 검정이라 창으로 자르지 않는다 — 회차당 응답이 적으면
    # 창 안에서는 비교할 이전 구간이 없어 검정이 죽는다. 자체 표본 조건(최근 RECENT_WINDOW건 +
    # 이전 MIN_COMPARE건)을 이미 갖고 있고, 수집 1회 중간부터 차단이 시작되는 패턴은 그
    # 자체로 실제 신호라 수집 횟수로 막지 않는다
    regression = detect_regression(*_recent_split(total, agg))
    return Evaluation(_banner_diagnosis(verdicts, regression, window.responses, sessions),
                      verdicts, regression, sessions, window.all_sessions, session_size)


def metric_value_text(spec: MetricSpec, value: float | None) -> str:
    """지표값 표시 문자열 — 비율은 백분율, 수집량은 천 단위 쉼표와 소수 첫째 자리의 건수."""
    if value is None:
        return "—"
    return f"{value:.1%}" if spec.percent else f"{value:,.1f}건"


def metric_interval_text(verdict: MetricVerdict) -> str:
    """95% 신뢰구간 표시 문자열 — 표 한 칸에 들어가도록 단위는 끝에 한 번만 적는다.
    구간을 쓰지 않는 지표는 "—"."""
    if verdict.low is None:
        return "—"
    if verdict.spec.percent:
        return f"{verdict.low * 100:.1f}~{verdict.high * 100:.1f}%"
    return f"{verdict.low:.2f}~{verdict.high:.2f}"


def metric_sample_text(verdict: MetricVerdict) -> str:
    """판정에 쓴 표본 크기 — 지표마다 분모가 달라 단위를 함께 적는다."""
    return f"{verdict.sample:,}{verdict.spec.sample_unit}"


def _criteria_compare(spec: MetricSpec) -> str:
    """임계값을 넘었다고 볼 방향 — 값이 클수록 좋은 지표는 부등호를 뒤집는다."""
    return "미만" if spec.higher_is_better else "이상"


def _threshold_text(spec: MetricSpec, value: float) -> str:
    """임계값 표기 — 회차별 패턴 전용 지표의 기준은 수집량이 아니라 편차 비율이라 백분율로 적는다."""
    return f"{value:.0%}" if spec.pattern_only else metric_value_text(spec, value)


def metric_criteria_text(spec: MetricSpec) -> str:
    """표 한 칸에 들어가는 짧은 기준 문구 — 앞이 주의, 뒤가 문제 임계값이다."""
    if spec.pattern_only:
        return f"편차 {_threshold_text(spec, spec.warn)} / {_threshold_text(spec, spec.problem)}"
    return (f"{_threshold_text(spec, spec.warn)} / "
            f"{_threshold_text(spec, spec.problem)} {_criteria_compare(spec)}")


def _pattern_range_text(verdict: MetricVerdict) -> str:
    """회차별 값의 최소~최대 — 배너 문장과 표 칸이 같은 표기를 쓴다."""
    values = verdict.pattern.values
    if verdict.spec.percent:
        return f"{min(values) * 100:.1f}~{max(values) * 100:.1f}%"
    return f"{min(values):,.1f}~{max(values):,.1f}건"


def metric_pattern_text(verdict: MetricVerdict) -> str:
    """표 한 칸에 들어가는 회차 패턴 문구 — 판정하지 않았으면 "—"."""
    pattern = verdict.pattern
    if pattern is None or pattern.level == DIAG_HOLD:
        return "—"
    if _is_unstable(verdict):
        return f"불안정 {_pattern_range_text(verdict)}"
    if verdict.absolved:
        return "일정·기준 초과"
    return "일정·진행분 반영" if verdict.live else "일정"


def _grade_guide_lines() -> list:
    """등급별 뜻 — 종합 평가 도움말이 등급 읽는 법으로 보여준다."""
    return [f"· {level} : {GRADE_MEANINGS[level]}" for level in GRADE_ORDER]


def _min_sessions_lines() -> list:
    """축별 최소 수집 횟수 — 같은 횟수인 축끼리 묶어 한 줄씩 적는다."""
    grouped = defaultdict(list)
    for axis, minimum in AXIS_MIN_SESSIONS.items():
        grouped[minimum].append(axis)
    return [f"    - {' · '.join(axes)} : {minimum}회" for minimum, axes in sorted(grouped.items())]


def _regression_help_text(regression) -> str:
    """최근 악화 검사 결과 한 줄 — 비교하지 못했으면 그 사유를 적고, 통계값(z)은 드러내지 않는다."""
    if regression is None:
        return "· 최근 악화 검사 : 아직 비교할 만큼 응답이 쌓이지 않았습니다"
    verdict = {TREND_WORSE: "눈에 띄게 나빠졌습니다", TREND_BETTER: "좋아졌습니다",
               TREND_FLAT: "큰 변화 없습니다"}[regression.trend]
    return (f"· 최근 악화 검사 : 최근 {regression.recent_n:,}건 {regression.recent_rate:.0%} / "
            f"이전 {regression.prior_n:,}건 {regression.prior_rate:.0%} → {verdict}")


def diagnosis_help_text(sessions: int, all_sessions: int, regression, session_size: float,
                        reference_kpis: tuple) -> str:
    """종합 평가 팝업 제목 옆 도움말 — 무엇을 보는지, 등급 읽는 법, 판정 방식, 현재 상태 순으로
    소제목을 나눠 쉬운 말로 적는다. 툴팁은 자동 줄바꿈이 없어 한 줄을 짧게 끊어 둔다."""
    reference = " · ".join(f"{name} {value}" for name, value in reference_kpis)
    state = [f"· 판정 범위 : 전체 {all_sessions}회 중 최근 {sessions}회",
             f"· 참고 값(판정에 쓰지 않음) : {reference}" if reference else "",
             _regression_help_text(regression)]
    if 0 < session_size < SMALL_SESSION_RESPONSES:
        state.append(f"· 회차당 응답이 평균 {session_size:.0f}건으로 적어\n  한 회차의 작은 이상은 놓칠 수 있습니다")
    lines = [
        "■ 이 평가는 무엇인가요?",
        f"최근 {PATTERN_WINDOW}회 수집(진행 중 포함)을 살펴",
        "\"지금 수집이 잘 되고 있는지\" 알려줍니다.",
        "(위 KPI 카드는 초기화 이후 누적 값입니다)",
        "",
        "■ 등급은 이렇게 읽으세요",
        *_grade_guide_lines(),
        "종합 등급은 지표 중 가장 나쁜 등급을 따릅니다.",
        "",
        "■ 어떻게 판정하나요?",
        "· 표본이 적으면 단정하지 않고 \"보류\"합니다",
        "  (95% 신뢰구간으로 판단)",
        "· 수집 1회는 관측 1번이라 항목마다",
        "  최소 수집 횟수가 필요합니다",
        *_min_sessions_lines(),
        f"· 수집이 {PATTERN_MIN_SESSIONS}회 이상이면 회차마다 결과가 일정한지도 봅니다",
        "  (일정하면 정상, 들쭉날쭉하면 주의, 더 강한 근거(99%)가 있으면 문제 —",
        "  단 절대 기준이 원래 '문제'인 값은 일정해도 문제로 봅니다)",
        "· 절대 기준은 '주의'인데 회차가 일정하면 정상으로 보되",
        "  배너와 이 표에 함께 표시합니다",
        "· 진행 중이거나 중단된 수집의 응답은 회차 패턴에 들어가기",
        "  전까지 절대 기준으로 판정합니다",
        "· 데이터 누락이 100%이면 횟수와 무관하게 바로 판정합니다",
        f"· 최근 {RECENT_WINDOW}건이 이전보다 눈에 띄게 나빠지면 따로 알립니다",
        "",
        "■ 지금 상태",
        *filter(None, state),
    ]
    return "\n".join(lines)


def _other_status_counts(status_cnt: dict) -> dict:
    """표(STATUS_CODE_MEANINGS)에 없는 코드별 건수 — 연결 실패("000")는 응답 결과 구성에서
    다루므로 제외한다."""
    return {code: n for code, n in status_cnt.items()
            if code not in STATUS_CODE_MEANINGS and code != NO_STATUS_CODE}


def _status_segments(status_cnt: dict) -> list:
    """상태 코드 분포 막대 목록 — 기본 코드(STATUS_CODE_MEANINGS)는 0건이어도 항상 코드
    번호 오름차순으로 넣어 갱신돼도 막대 위치가 바뀌지 않게 하고, 표에 없는 코드는 건수를
    합쳐 "기타" 한 행으로 끝에 붙인다(없으면 행을 만들지 않는다)."""
    segments = [(code, status_cnt.get(code, 0), STATUS_CODE_COLORS.get(code, ACCENT_LIGHT))
                for code in sorted(STATUS_CODE_MEANINGS)]
    other_total = sum(_other_status_counts(status_cnt).values())
    if other_total:
        segments.append((STATUS_OTHER_LABEL, other_total, ACCENT_LIGHT))
    return segments


def _median(values: list) -> float:
    """정렬해서 가운데 값(짝수 개면 가운데 두 값의 평균)을 돌려준다 — 값이 하나 이상이어야 한다."""
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _count_text(value: float) -> str:
    """건수를 천 단위 쉼표와 함께 — 정수면 소수점 없이, 짝수 개 중앙값처럼 .5면 소수 첫째 자리까지."""
    return f"{int(value):,}" if value == int(value) else f"{value:,.1f}"


def _percent(part: int, whole: int) -> str:
    """part/whole을 소수 첫째 자리 백분율 문자열로 — whole이 0이면 "0%"."""
    return f"{part / whole * 100:.1f}%" if whole else "0%"


def _item_range_text(pages: list) -> str:
    """페이지당 수집량의 최소/최대 건수와 그 비율을 한 줄로 — 최소=최대면 건수를
    한 번만 쓰고 괄호에 비율(100%)만 덧붙인다. pages가 비어 있거나 최대가 0이면
    "—"(0으로 나누기·의미 없는 0%를 피함)."""
    if not (pages and max(pages)):
        return "—"
    low, high = min(pages), max(pages)
    ratio = f"({_percent(low, high)})"
    if low == high:
        return f"{_count_text(high)}건{ratio}"
    return f"{_count_text(low)}건/{_count_text(high)}건{ratio}"


def _status_group(code: str) -> str:
    """상태 코드를 2xx/3xx/4xx/5xx로 묶는다. engine.handle_request_failure()가
    보고하는 연결 실패("000")는 HTTP 에러와 원인·대응이 달라 따로 분류한다."""
    if code == NO_STATUS_CODE:
        return NO_STATUS_CODE
    return f"{code[0]}xx" if code[:1].isdigit() else "기타"


def _outcome(row: dict, code: str, is_ok: bool) -> str:
    """응답을 실제로 쓸 수 있었는지 기준으로 4분류한다 — 상태 코드만으로는
    "200인데 추출 0건"(데이터 누락)이 성공과 구분되지 않는다. 추출 규칙 예외
    (extract_error)도 데이터 0건이라 데이터 누락으로 센다. 두 필드는 과거
    stats_history.json 행에는 없을 수 있는데, 그때는 구분할 근거가 없으므로
    정상 수집으로 둔다."""
    if code == NO_STATUS_CODE:
        return OUTCOME_CONN_FAIL
    if not is_ok:
        return OUTCOME_HTTP_ERR
    if row.get("empty_extract") or row.get("extract_error"):
        return OUTCOME_EMPTY
    return OUTCOME_OK


class TrendWindow(NamedTuple):
    """수집량 추이 카드가 그릴 구간 — start는 첫 칸의 시작 시각(시간대별은 시
    단위, 그 외는 일 단위 자정), buckets는 칸 수, range_text는 카드명에 쓸 범위."""
    start: datetime
    buckets: int
    range_text: str


def _sunday_based_weekday(day: datetime) -> int:
    """일요일을 0으로 하는 요일 번호(weekday()는 월요일이 0)."""
    return (day.weekday() + 1) % DAYS_PER_WEEK


def _sunday_on_or_before(day: datetime) -> datetime:
    return day - timedelta(days=_sunday_based_weekday(day))


def _week_of_month(day: datetime) -> tuple:
    """일요일 시작 달력 주 기준으로 day가 속한 주의 시작일(일요일)과, day가 속한
    달의 1일이 든 주를 1주차로 셀 때의 주차를 반환한다."""
    week_start = _sunday_on_or_before(day)
    first_week_start = _sunday_on_or_before(day.replace(day=1))
    return week_start, (week_start - first_week_start).days // DAYS_PER_WEEK + 1


def _recent_window(period: str, now: datetime, today: datetime) -> TrendWindow:
    """오늘(현재 시각)을 끝으로 하는 최근 24시간 / 7일 / 31일(월별은 한 달 최대 일수) 구간."""
    if period == TREND_HOURLY:
        this_hour = now.replace(minute=0, second=0, microsecond=0)
        return TrendWindow(this_hour - timedelta(hours=HOURS_PER_DAY - 1),
                           HOURS_PER_DAY, f"최근 {HOURS_PER_DAY}시간")
    days = DAYS_PER_WEEK if period == TREND_WEEKLY else DAYS_IN_MONTH_MAX
    return TrendWindow(today - timedelta(days=days - 1), days, f"최근 {days}일")


def _calendar_window(period: str, today: datetime) -> TrendWindow:
    """오늘이 속한 일(00~23시) / 주(일~토) / 월(1일~말일) 전체 구간."""
    if period == TREND_HOURLY:
        return TrendWindow(today, HOURS_PER_DAY, f"{today.month}/{today.day} 00~23시")
    if period == TREND_WEEKLY:
        week_start, week_no = _week_of_month(today)
        return TrendWindow(week_start, DAYS_PER_WEEK, f"{today.month}월 {week_no}주차")
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return TrendWindow(today.replace(day=1), days_in_month, f"{today.month}월")


def trend_window(period: str, mode: str, now: datetime) -> TrendWindow:
    """기간(시간대별/주간별/월별)과 표시 방식에 맞는 추이 구간을 계산한다.
    now를 인자로 받아 시각에 의존하지 않는 순수 함수로 둔다."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if mode == TREND_MODE_CALENDAR:
        return _calendar_window(period, today)
    return _recent_window(period, now, today)


class AllTimeTrend(NamedTuple):
    """전체 보기 팝업이 그릴 접어서 합산한 수집량 — caption은 칸 설명(팝업 제목용)."""
    caption: str
    labels: list
    ok_vals: list
    err_vals: list


# 기간별 (칸 라벨, 타임스탬프 → 칸 번호) — 한 주기 안에서의 위치로 접는다.
# 요일은 일요일을 0번 칸으로 둔다(weekday()는 월요일이 0).
_ALL_TIME_FOLDS = {
    TREND_HOURLY: ([f"{h:02d}h" for h in range(HOURS_PER_DAY)], lambda ts: ts.hour),
    TREND_WEEKLY: (list(WEEKDAY_LABELS), _sunday_based_weekday),
    TREND_MONTHLY: ([f"{d}일" for d in range(1, DAYS_IN_MONTH_MAX + 1)], lambda ts: ts.day - 1),
}


def _row_facts(row: dict) -> RowFacts:
    """응답 1건의 분류·집계용 값 — 합산 집계(_aggregate_rows)와 회차별 집계(_session_tallies)가
    같은 분류를 쓰도록 한곳에서 만든다. 필드 채움 기록(worker.count_field_fill)이 없는 과거
    응답은 채움 값을 0으로 둬 집계에서 빠지게 한다."""
    code = str(row.get("status_code", ""))
    latency = row.get("pure_latency")
    item_count = row.get("item_count") if isinstance(row.get("item_count"), int) else None
    has_fill = isinstance(row.get("field_cells"), int)
    return RowFacts(
        code, _outcome(row, code, code == "200"),
        _speed_bucket(latency) if isinstance(latency, float) else None, item_count,
        row.get("complete_rows", 0) if has_fill else 0, (item_count or 0) if has_fill else 0)


def _recent_sessions(sessions: list, count: int) -> list:
    """시작 시각이 유효한 수집 중 가장 최근 count개(시작 순) — 중단된 수집도 1회로 센다."""
    dated = sorted((s for s in sessions if s.get("started", "")[:1].isdigit()),
                   key=lambda s: s["started"])
    return dated[len(dated) - min(count, len(dated)):]


def _session_windows(sessions: list) -> list:
    """완료된(중단·실패하지 않은) 수집의 (시작, 종료) 시각을 시작 순으로 — 응답을 회차에
    귀속하는 데 쓴다. 중단·실행 실패한 수집은 일부만 돌아 대표성이 없어 패턴 시리즈에서
    뺀다. url_map의 session 필드는 항상 1이라 쓸 수 없어, 응답의 timestamp가 어느 구간에
    드는지로 귀속한다."""
    return sorted((s["started"], s["finished"]) for s in sessions
                  if not s.get("interrupted") and not s.get("aborted")
                  and s.get("started", "")[:1].isdigit())


def _window_slot(windows: list, starts: list, timestamp: str) -> int | None:
    """timestamp가 든 수집 구간의 번호 — 어느 구간에도 안 들면(진행 중인 수집 등) None."""
    slot = bisect_right(starts, timestamp) - 1
    return slot if slot >= 0 and timestamp <= windows[slot][1] else None


def _session_tallies(rows: list, sessions: list) -> list:
    """응답을 완료된 수집 회차별로 집계한다 — 어느 회차인지는 timestamp가 든 [시작, 종료]
    구간으로 귀속하고, 어느 구간에도 안 드는 응답(진행 중인 수집 등)은 회차에 넣지 않는다."""
    windows = _session_windows(sessions)
    starts = [start for start, _ in windows]
    tallies = [SessionTally() for _ in windows]
    for row in rows:
        slot = _window_slot(windows, starts, row.get("timestamp") or "")
        if slot is not None:
            tallies[slot].add(_row_facts(row))
    return [t for t in tallies if t.responses]


def aggregate_all_time(rows, period: str) -> AllTimeTrend:
    """전체 URL 응답 기록을 기간의 한 주기(하루의 시 / 한 주의 요일 / 한 달의 일자)
    안의 칸으로 접어 합산한다. 이력이 아무리 길어도 칸 수가 고정된다. 타임스탬프
    형식이 잘못됐거나 timestamp/status_code가 없는 행은 건너뛴다."""
    labels, slot_of = _ALL_TIME_FOLDS[period]
    ok_vals, err_vals = [0] * len(labels), [0] * len(labels)

    for r in rows:
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
            counts = ok_vals if str(r["status_code"]) == "200" else err_vals
        except (ValueError, KeyError, TypeError):
            continue
        counts[slot_of(ts)] += 1

    return AllTimeTrend(TREND_ALL_TIME_CAPTIONS[period], list(labels), ok_vals, err_vals)


def _session_requests(session: dict) -> list[dict]:
    """세션 레코드의 요청 목록을 {url, body, ...} dict로 정규화한다. requests가 없는
    과거 기록은 템플릿 url 1건으로 대체하며, 결과 필드(outcome 등)는 비워 둔다."""
    return session.get("requests") or [{"url": session.get("url", ""), "body": None}]


def session_request_rows(session: dict) -> list[list[str]]:
    """요청 상세 표의 행(NO, URL, Body, Method, Status, Response, Requested At, Result)."""
    method = session.get("method", "GET")
    rows = []
    for no, r in enumerate(_session_requests(session), start=1):
        body = NO_BODY_TEXT if r["body"] is None else json.dumps(r["body"], ensure_ascii=False)
        latency = r.get("latency")
        response = f"{latency}s" if isinstance(latency, (int, float)) else NO_BODY_TEXT
        # outcome 키가 아예 없으면 결과를 기록하지 않던 과거 기록(미상), None이면 응답 미수신
        result = REQUEST_RESULT_UNKNOWN if "outcome" not in r else REQUEST_RESULTS.get(r["outcome"], REQUEST_RESULT_MISSED)
        rows.append([
            str(no), r["url"], body, method,
            str(r["status_code"]) if r.get("status_code") is not None else NO_BODY_TEXT,
            response, r.get("timestamp") or NO_BODY_TEXT, result,
        ])
    return rows


def empty_data_notice(extract_errors: int, missing_conditions: str | None) -> list:
    """모든 응답이 빈 데이터일 때의 원인·해결 방법 항목 — 데이터로 확인된 원인(설정 누락·추출 예외)은
    단정하는 문장으로, 확인하지 못한 원인은 "~수도 있습니다" 문장으로 적는다. 확인된 원인이 있으면
    그 밖의 가능성(데이터 페이지가 아님·실제 데이터 없음)은 줄인다."""
    notes = []
    if missing_conditions:
        notes.append(f"수집 조건(conditions)이 비어 있습니다({missing_conditions}). "
                     "누락된 수집 조건 항목을 채우세요.")
    if extract_errors:
        notes.append(f"데이터 추출 중 예외가 {extract_errors}건 발생했습니다. "
                     "수집 로그와 응답 상세에서 예외 내용을 확인하세요.")
    notes.append("사이트 구조가 바뀌었을 수도 있습니다. "
                 "사이트 구조와 추출 규칙(셀렉터/JSON·XML 경로)을 확인하세요.")
    if not notes[:-1]:
        notes.append("200 응답이어도 실제 데이터 페이지가 아닐 수도 있습니다. "
                     "차단·로그인 요구·점검 안내·리다이렉트 여부를 확인하세요.")
        notes.append("해당 시점에 수집할 데이터가 실제로 없을 수도 있습니다. "
                     "대상 사이트에서 데이터 유무를 확인하세요.")
    return notes


class Review(NamedTuple):
    """종합 평가 팝업 표 하단의 글 — grades는 표를 등급별로 묶은 요약(레벨, 문장) 목록으로
    총평을 대신하며, notes는 이슈별 원인과 해결 방법 항목이며 등급이 주의·문제일 때만 있다."""
    grades: list
    notes: list


REVIEW_SUMMARY_SENTENCES = 2   # 수집 기록이 없을 때 남기는 배너 문장 수 — 팝업 폭에서 2줄 안에 든다


def _first_sentences(text: str, count: int) -> str:
    """앞 count개 문장만 남긴다."""
    return " ".join(re.split(r"(?<=\.)\s+", text)[:count])


def _grade_breakdown(verdicts: list) -> list:
    """지표를 등급별로 묶어 "등급 N개(지표명·...) — 뜻" 형태의 줄을 만든다(정상→대기 순, 항목이
    있는 등급만). 표의 '상태' 열을 그대로 집계한 것이라 표 내용과 항상 일치한다."""
    grouped = defaultdict(list)
    for v in verdicts:
        grouped[v.level].append(v.spec.name)
    return [(level, f"{level} {len(grouped[level])}개({' · '.join(grouped[level])}) "
                    f"— {GRADE_MEANINGS[level]}")
            for level in GRADE_ORDER if grouped[level]]


def _issue_notes(verdict: MetricVerdict, empty_notice: list | None) -> list:
    """지표 하나의 이슈 항목 — 회차 불안정이면 그 사실을, 데이터 누락이면 원인 후보별 항목을, 그 밖에는
    지표 고유의 원인과 해결 방법을 한 항목으로 적는다."""
    spec = verdict.spec
    if _is_unstable(verdict):
        return [f"{_cause_text(verdict)} {PATTERN_ADVICE}"]
    if spec is SPEC_EMPTY and empty_notice:
        return empty_notice
    return [f"{spec.cause} {spec.remedy}"]


def diagnosis_review(evaluation: Evaluation, empty_notice: list | None) -> Review:
    """표 아래 글을 만든다 — 표를 등급별로 묶은 요약이 총평을 대신하고, 주의·문제 이슈가 있으면
    원인·해결 방법 항목을(심한 것부터) 덧붙인다. 판정할 지표 자체가 없으면(수집 기록 없음) 등급
    묶음 대신 안내 문장 한 줄을 보여준다."""
    grades = _grade_breakdown(evaluation.verdicts)
    diagnosis = evaluation.diagnosis
    if not grades:
        return Review([(DIAG_PENDING, _first_sentences(diagnosis.detail, REVIEW_SUMMARY_SENTENCES))], [])
    if diagnosis.level not in (DIAG_WARN, DIAG_PROBLEM):
        return Review(grades, [])

    issues = sorted((v for v in evaluation.verdicts if v.level in (DIAG_WARN, DIAG_PROBLEM)),
                    key=lambda v: -DIAG_LEVEL_RANK[v.level])
    notes = [note for v in issues for note in _issue_notes(v, empty_notice)]
    regression = evaluation.regression
    if regression is not None and regression.trend == TREND_WORSE:
        notes.append(regression_text(regression))
    return Review(grades, notes)


class StatisticsPageTriggers:
    """StatisticsPanel의 데이터 로드·내보내기 메서드"""

    seq_no = None  # None이면 전체 블루프린트 합산, 값이 있으면 그 블루프린트의 통계만

    _empty_notice = None  # 전체가 빈 데이터일 때의 원인·해결 방법 항목(list[str]) — 종합 평가 팝업이 읽는다

    _collecting = False  # 수집 진행 중 여부 — 창이 set_collecting()으로 넘긴다

    def set_collecting(self, collecting: bool) -> None:
        """수집 시작/종료를 즉시 반영한다 — 초기화 버튼을 잠그고 진행 중 수집을 평가에 넣는다."""
        self._collecting = collecting
        self.reset_btn.setEnabled(not collecting)
        self._refresh_if_visible()

    def _title(self):
        """seq_no 블루프린트의 제목 — seq_no가 없는 과거 세션 기록을 제목으로 매칭할 때 쓴다."""
        blueprint = BlueprintStorage().get(self.seq_no)
        return blueprint.get("title") if blueprint else None

    def _rows(self) -> list:
        return store.get_url_maps(self.seq_no)

    def _sessions(self) -> list:
        return store.get_sessions(self.seq_no, self._title())

    def reload(self):
        """요약(KPI·차트)과 세션 이력 테이블을 모두 갱신하는 전체 리로드.
        3초 주기 타이머는 테이블이 빠진 _refresh_summary()만 호출한다
        (layout/statistics.py 참고) — 세션 이력은 세션 종료 시점에만 바뀌므로
        매 틱 재구성이 불필요하고, 재구성마다 사용자가 적용한 정렬도 풀렸었다."""
        self._refresh_summary()
        self._refresh_session_table()

    def _refresh_summary(self):
        rows = self._rows()
        sessions = self._sessions()

        total = len(rows)
        status_cnt = defaultdict(int)
        for r in rows:
            status_cnt[str(r["status_code"])] += 1
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]
        avg_time_val = sum(times) / len(times) if times else 0.0
        avg_t = f"{avg_time_val:.2f}s" if times else "—"

        agg = self._aggregate_rows(rows)

        # 요청·응답 카드 — 응답 성공률은 HTTP 200 비율(데이터 유무와 무관)
        self.kpi_total.update_value(total)
        self.kpi_resp_rate.update_value(_percent(status_cnt.get("200", 0), total))
        self.kpi_avg_t.update_value(avg_t)

        self._refresh_process_kpis(agg)

        self.status_chart.set_data(_status_segments(status_cnt))

        # 4분류를 값이 0이어도 항상 모두 넘긴다 — RankedBarChart는 빈 리스트면
        # 카드를 통째로 비우므로, 수집 이력이 없을 때도 골격이 보이게 한다
        self.outcome_chart.set_data(
            [(label, agg["outcome"].get(label, 0), color) for label, color in OUTCOME_SEGMENTS])
        self.speed_chart.set_data(
            [(label, agg["speed"].get(label, 0), color) for label, color in SPEED_SEGMENTS])

        throughput = self._refresh_throughput_kpi(sessions)

        self._reference_kpis = ((REF_AVG_LATENCY, avg_t), (REF_THROUGHPUT, throughput))
        self._update_diagnosis(evaluate(total, agg, self._evaluation_window(rows, sessions, self._collecting)))

        self._refresh_trend_chart(rows, agg)
        self._refresh_empty_notice(total, agg)

    def _refresh_empty_notice(self, total: int, agg: dict) -> None:
        """응답이 전부 데이터 누락일 때만 그 종합 원인을 보관한다 — 수집은 막지 않고, 종합 평가 팝업이
        표 아래에 보여준다. seq_no가 없으면(단일 모드 전체 합산) 유일한 블루프린트의 설정 누락을 확인한다."""
        if not (total > 0 and agg["outcome"].get(OUTCOME_EMPTY, 0) == total):
            self._empty_notice = None
            return
        storage = BlueprintStorage()
        seq_no = self.seq_no or next(iter(storage.list_seq_nos()), None)
        blueprint = storage.get(seq_no) if seq_no else None
        missing = engine.validate_blueprint_conditions(blueprint) if blueprint else None
        self._empty_notice = empty_data_notice(agg["extract_errors"], missing)

    def _refresh_trend_chart(self, rows, agg):
        """선택된 기간·표시 방식(layout/statistics.py의 self.trend_period,
        self.trend_mode)에 맞춰 수집량 추이 카드(성공/실패 막대)와 카드명을
        다시 그린다. 매 갱신마다 현재 시각으로 구간을 잡으므로 자정이 지나면
        시간대/주차/월이 자동으로 넘어간다."""
        window = trend_window(self.trend_period, self.trend_mode, datetime.now())
        if self.trend_period == TREND_HOURLY:
            labels, ok_vals, err_vals = self._hourly_counts(rows, window.start, window.buckets)
        else:
            labels, ok_vals, err_vals = self._daily_counts(
                agg, window.start, window.buckets, with_weekday=self.trend_period == TREND_WEEKLY)

        self._update_trend_title(window.range_text)
        self.trend_chart.set_data(
            labels, [("성공", ok_vals, GREEN), ("실패", err_vals, RED)])

    @staticmethod
    def _hourly_counts(rows, start: datetime, hours: int):
        """[start, start+hours) 구간을 1시간 칸으로 집계해 (라벨, 성공, 오류)를
        반환한다. 칸 번호를 start부터의 경과 시간으로 정하므로 구간이 자정을
        넘어도 서로 다른 시각이 한 칸에 섞이지 않는다."""
        ok_vals, err_vals = [0] * hours, [0] * hours
        end = start + timedelta(hours=hours)

        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError, TypeError):
                continue
            if not start <= ts < end:
                continue
            slot = (ts - start) // timedelta(hours=1)
            counts = ok_vals if str(r.get("status_code", "")) == "200" else err_vals
            counts[slot] += 1

        labels = [f"{(start + timedelta(hours=i)).hour:02d}h" for i in range(hours)]
        return labels, ok_vals, err_vals

    @staticmethod
    def _daily_counts(agg, start: datetime, days: int, with_weekday: bool = False):
        """start부터 days일을 1일 칸으로 집계해 (라벨, 성공, 오류)를 반환한다 —
        _aggregate_rows()가 이미 만든 daily_ok/daily_err(키 = "YYYY-MM-DD")를
        읽기만 해서 행을 다시 순회하지 않는다. with_weekday면 라벨을 "9/20 (일)"처럼
        요일과 함께, 아니면 칸이 많은 월별용으로 짧은 "09-20"으로 만든다."""
        dates = [start + timedelta(days=i) for i in range(days)]
        keys = [d.strftime("%Y-%m-%d") for d in dates]
        if with_weekday:
            labels = [f"{d.month}/{d.day} ({WEEKDAY_LABELS[_sunday_based_weekday(d)]})" for d in dates]
        else:
            labels = [d.strftime("%m-%d") for d in dates]
        return (labels,
                [agg["daily_ok"].get(k, 0) for k in keys],
                [agg["daily_err"].get(k, 0) for k in keys])

    def _refresh_throughput_kpi(self, sessions) -> str:
        """세션 누계(응답 수 ÷ 소요 시간)로 처리량 KPI를 갱신하고 표시 문구를 돌려준다 —
        종합 평가 상세 보기가 같은 값을 참고값으로 다시 계산하지 않게 한다."""
        total = sum(s.get("total", 0) for s in sessions)
        elapsed = sum(s.get("elapsed", 0) or 0 for s in sessions)
        text = f"{total / elapsed:.1f}/s" if elapsed else "—"
        self.kpi_throughput.update_value(text)
        return text

    def _refresh_process_kpis(self, agg: dict) -> None:
        """데이터 처리 카드를 갱신한다 — 페이지당 수집량(중앙값, 최소·최대 건수+비율)과
        유효 데이터 비율(모든 항목이 채워진 행). 페이지당 수집량은 데이터를 가져온 페이지("정상
        수집")만 대상으로 해 데이터 누락이 중앙값·최소값을 0으로 끌어내리지 않게 하며,
        필드 채움 기록이 없는 과거 응답만 있으면 유효 데이터 비율은 "—"로 둔다."""
        pages = agg["page_items"]
        self.kpi_page_median.update_value(f"{_count_text(_median(pages))}건" if pages else "—")
        self.kpi_item_range.update_value(_item_range_text(pages))

        field_items = agg["field_items"]
        self.kpi_valid_rate.update_value(_percent(agg["complete_rows"], field_items) if field_items else "—")

    def _evaluation_window(self, rows, sessions, running: bool) -> EvalWindow:
        """배너가 판정할 최근 PATTERN_WINDOW회 수집 구간을 집계한다 — 초기화 이후 누적으로 보면
        과거의 이상이 회복 뒤에도 배너에 남아서다. 구간은 그 수집 중 가장 이른 것의 시작
        시각부터의 모든 응답이라 진행 중이거나 중단된 수집의 응답도 들어가며, 오래된 이상은 시간이
        지나면 자연히 빠진다. 세션은 완료 시점에 기록되므로 진행 중인 수집은 running으로 1회
        센다 — 그대로 두면 첫 수집 내내 배너가 침묵해 연결·응답 축을 1회로 낮춘 의미가 사라진다."""
        recent = _recent_sessions(sessions, PATTERN_WINDOW - running)
        cutoff = recent[0]["started"] if recent else ""
        window_rows = [r for r in rows if (r.get("timestamp") or "") >= cutoff]
        agg = self._aggregate_rows(window_rows)
        agg["per_session"] = _session_tallies(window_rows, recent)
        return EvalWindow(agg, len(window_rows), len(recent) + running, len(sessions) + running)

    def _aggregate_rows(self, rows):
        """url_maps를 한 번만 순회해 행 기반 집계를 모두 산출한다 — 3초마다
        호출되는데 행 수는 통계 초기화 전까지 계속 누적되므로, 지표마다 따로
        순회하지 않는다."""
        daily_ok, daily_err = defaultdict(int), defaultdict(int)
        status_group = defaultdict(int)
        outcome = defaultdict(int)
        speed = defaultdict(int)
        blocked = 0
        extract_errors = 0
        page_items = []
        complete_rows = field_items = 0
        # 최근 악화 감지용 창 — 고정 길이라 행이 아무리 쌓여도 메모리가 늘지 않고,
        # 이전 구간 값은 누계에서 이 창을 빼서 구하므로 순회도 한 번으로 끝난다
        recent_ok = deque(maxlen=RECENT_WINDOW)

        for r in rows:
            facts = _row_facts(r)
            timestamp = r.get("timestamp") or ""

            status_group[_status_group(facts.code)] += 1
            outcome[facts.outcome] += 1
            blocked += facts.code in BLOCKED_STATUS_CODES
            extract_errors += bool(r.get("extract_error"))
            recent_ok.append(facts.outcome == OUTCOME_OK)
            if facts.bucket is not None:
                speed[facts.bucket] += 1
            if facts.item_count is not None and facts.outcome == OUTCOME_OK:
                page_items.append(facts.item_count)
            complete_rows += facts.complete_rows
            field_items += facts.field_items

            if timestamp:
                (daily_ok if facts.code == "200" else daily_err)[timestamp[:10]] += 1

        return {
            "daily_ok": daily_ok, "daily_err": daily_err,
            "status_group": status_group, "outcome": outcome, "speed": speed, "blocked": blocked,
            "extract_errors": extract_errors,
            "page_items": page_items, "complete_rows": complete_rows, "field_items": field_items,
            "recent_ok": recent_ok,
        }

    def _refresh_session_table(self):
        sessions = self._sessions()

        self.session_table.setRowCount(0)
        for idx, s in enumerate(reversed(sessions), start=1):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            # title은 세션 레코드에 나중에 추가된 필드라 과거 stats_history.json에는
            # 없을 수 있음 — job/url도 함께 .get()으로 통일해 방어적으로 접근한다.
            interrupted = s.get("interrupted", False)
            aborted     = s.get("aborted", False)
            status_label = "중단" if interrupted else ("실패" if aborted else "완료")
            vals = [str(idx), s.get("title", ""), s.get("url", ""), str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"],
                    s.get("job", ""), status_label]
            colors = [TEXT_MUTED, TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED, TEXT_PRIMARY,
                      RED if (interrupted or aborted) else GREEN]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, s)  # 더블클릭 시 요청 상세를 열 세션 레코드
                self.session_table.setItem(r, col, item)

        self.session_badge.setText(f"{len(sessions)}건")

    def _aggregate_all_time(self, period: str) -> AllTimeTrend:
        """이 패널 범위의 URL 응답 기록을 period의 전체 보기 방식으로 접어 합산한다."""
        return aggregate_all_time(self._rows(), period)

    def _on_reset_clicked(self):
        store.clear_url_maps(self.seq_no)
        store.clear_sessions(self.seq_no, self._title())
        store.save_stats_history()
        self.reload()
