# trigger/statistics.py
# StatisticsPage의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

import calendar
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import NamedTuple

from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

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
REQUEST_RESULTS = {"ok": "성공", "warn": "빈 응답", "err": "실패"}
REQUEST_RESULT_MISSED, REQUEST_RESULT_UNKNOWN = "미수집", "-"
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7
DAYS_IN_MONTH_MAX = 31
WEEKDAY_LABELS = ("일", "월", "화", "수", "목", "금", "토")

# 전체 보기 팝업의 칸 설명 — 기간의 한 주기(하루/한 주/한 달) 안의 칸을 전체
# 이력에 걸쳐 접어서 합산한다. layout/statistics.py가 툴팁·팝업 제목에 그대로 쓴다.
TREND_ALL_TIME_CAPTIONS = {
    TREND_HOURLY: "00~24시 누적",
    TREND_WEEKLY: "요일별 누적",
    TREND_MONTHLY: "일자별 누적",
}

# 통계 "응답 결과 구성" 카드의 4분류 — 표시 순서와 색을 한곳에 묶는다.
# "연결 실패"에 TEXT_MUTED를 쓰는 건 대시보드 실시간 테이블이 상태 코드 "000"에 쓰는
# 색(STATUS_CODE_COLORS)과 색 언어를 맞추기 위해서다.
OUTCOME_OK, OUTCOME_EMPTY = "정상 수집", "빈 응답"
OUTCOME_HTTP_ERR, OUTCOME_CONN_FAIL = "HTTP 오류", "연결 실패"
OUTCOME_SEGMENTS = (
    (OUTCOME_OK, GREEN), (OUTCOME_EMPTY, AMBER),
    (OUTCOME_HTTP_ERR, RED), (OUTCOME_CONN_FAIL, TEXT_MUTED),
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


# 수집 상태 진단 배너의 판정 기준 — 임계값은 여기서만 바꾸고, 배너 툴팁
# (diagnosis_tooltip)이 이 상수에서 설명을 만들어 화면 문구와 어긋나지 않는다.
DIAG_MIN_SAMPLES = 10          # 응답이 이보다 적으면 판정하지 않는다
DIAG_CONN_FAIL_PROBLEM = 0.20  # 연결 실패 비율 — 이상이면 "문제"
DIAG_BLOCKED_PROBLEM = 0.20    # 접근 차단(403·429) 비율 — 이상이면 "문제"
DIAG_EMPTY_WARN = 0.30         # 빈 응답 비율 — 이상이면 "주의"
DIAG_HTTP_ERR_WARN = 0.10      # HTTP 오류 비율 — 이상이면 "주의"
BLOCKED_STATUS_CODES = ("403", "429")

# 엔진이 상태 코드를 받지 못했을 때(연결 실패 등) 넣는 값(engine.py) — HTTP 응답이 아니라
# 상태 코드 분포 카드에는 넣지 않고 "응답 결과 구성"의 연결 실패로 집계한다
NO_STATUS_CODE = "000"

# 상태 코드 분포에서 표에 없는 코드를 한 행으로 합쳐 표시하는 이름 — 코드 종류가 몇 개든 행 수를
# 최대 7행으로 묶어 카드 고정 높이 안에서 글자가 겹치지 않게 한다. 툴팁에는 기타에 든 코드를 최대
# OTHER_CODES_TOOLTIP_MAX개까지 적는다.
STATUS_OTHER_LABEL = "기타"
OTHER_CODES_TOOLTIP_MAX = 8

# 상태 코드 분포 도움말 툴팁에 적는 코드별 쉬운 말 — 막대 라벨에는 코드만 표시한다
STATUS_CODE_MEANINGS = {
    "200": "정상", "301": "이동", "403": "접근 거부", "404": "페이지 없음",
    "429": "요청 과다", "500": "서버 오류",
}

DIAG_OK, DIAG_WARN, DIAG_PROBLEM, DIAG_PENDING = "정상", "주의", "문제", "대기"


class Diagnosis(NamedTuple):
    level: str
    color: str
    detail: str


def diagnose(total: int, agg: dict) -> Diagnosis:
    """누적 응답 집계(_aggregate_rows 결과)를 정상/주의/문제로 판정하고, 원인과
    조치를 한 문장으로 돌려준다. 위에서부터 먼저 걸리는 규칙을 채택한다."""
    if total == 0:
        return Diagnosis(DIAG_PENDING, TEXT_MUTED,
                         "아직 수집 기록이 없습니다. 상단 ▶ 시작 버튼으로 수집을 실행하세요.")
    if total < DIAG_MIN_SAMPLES:
        return Diagnosis(DIAG_PENDING, TEXT_MUTED,
                         f"수집 기록이 적어 판단하기 어렵습니다. (현재 {total}건)")

    outcome = agg["outcome"]
    if outcome.get(OUTCOME_CONN_FAIL, 0) / total >= DIAG_CONN_FAIL_PROBLEM:
        return Diagnosis(DIAG_PROBLEM, RED,
                         "사이트에 연결하지 못했습니다. 인터넷 연결이나 프록시 설정을 확인하세요.")
    if agg["blocked"] / total >= DIAG_BLOCKED_PROBLEM:
        return Diagnosis(DIAG_PROBLEM, RED,
                         "사이트가 접근을 막고 있습니다. 수집 간격을 늘리거나 프록시를 사용하세요.")
    if outcome.get(OUTCOME_EMPTY, 0) / total >= DIAG_EMPTY_WARN:
        return Diagnosis(DIAG_WARN, AMBER,
                         "페이지는 열렸지만 데이터를 찾지 못했습니다. "
                         "사이트 구조가 바뀌었을 수 있으니 추출 설정을 확인하세요.")
    if outcome.get(OUTCOME_HTTP_ERR, 0) / total >= DIAG_HTTP_ERR_WARN:
        return Diagnosis(DIAG_WARN, AMBER,
                         "일부 페이지에서 오류 응답을 받았습니다. 상태 코드 분포에서 오류 종류를 확인하세요.")
    return Diagnosis(DIAG_OK, GREEN,
                     f"수집이 정상적으로 진행되고 있습니다. "
                     f"페이지 {total}개 중 {outcome.get(OUTCOME_OK, 0)}개에서 데이터를 가져왔습니다.")


def diagnosis_tooltip() -> str:
    """진단 배너 툴팁 — 판정 기준을 초기화 이후 누적 응답 기준으로 설명한다."""
    return "\n".join([
        "초기화 이후 누적된 모든 응답을 기준으로 판정합니다.",
        f"· 응답이 {DIAG_MIN_SAMPLES}건 미만이면 판단을 보류합니다.",
        f"· 문제: 연결 실패 {DIAG_CONN_FAIL_PROBLEM:.0%} 이상, "
        f"또는 접근 차단(403·429) {DIAG_BLOCKED_PROBLEM:.0%} 이상",
        f"· 주의: 빈 응답(페이지는 열렸지만 데이터 0건) {DIAG_EMPTY_WARN:.0%} 이상, "
        f"또는 HTTP 오류 {DIAG_HTTP_ERR_WARN:.0%} 이상",
        "· 정상: 위 조건에 모두 해당하지 않을 때",
    ])


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


def _other_codes_text(status_cnt: dict) -> str:
    """"기타" 막대 툴팁 — 기타에 합쳐진 코드를 건수 내림차순으로 적는다. 없으면 빈 문자열."""
    others = sorted(_other_status_counts(status_cnt).items(), key=lambda kv: (-kv[1], kv[0]))
    if not others:
        return ""
    listed = " · ".join(f"{code} {n}건" for code, n in others[:OTHER_CODES_TOOLTIP_MAX])
    rest = len(others) - OTHER_CODES_TOOLTIP_MAX
    suffix = f" 외 {rest}종" if rest > 0 else ""
    return f"{STATUS_OTHER_LABEL}에 포함된 코드: {listed}{suffix}"


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


def _status_group(code: str) -> str:
    """상태 코드를 2xx/3xx/4xx/5xx로 묶는다. engine.handle_request_failure()가
    보고하는 연결 실패("000")는 HTTP 에러와 원인·대응이 달라 따로 분류한다."""
    if code == NO_STATUS_CODE:
        return NO_STATUS_CODE
    return f"{code[0]}xx" if code[:1].isdigit() else "기타"


def _outcome(row: dict, code: str, is_ok: bool) -> str:
    """응답을 실제로 쓸 수 있었는지 기준으로 4분류한다 — 상태 코드만으로는
    "200인데 추출 0건"(빈 응답)이 성공과 구분되지 않는다. 추출 규칙 예외
    (extract_error)도 데이터 0건이라 빈 응답으로 센다. 두 필드는 과거
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
    """오늘이 속한 일(00~24시) / 주(일~토) / 월(1일~말일) 전체 구간."""
    if period == TREND_HOURLY:
        return TrendWindow(today, HOURS_PER_DAY, f"{today.month}/{today.day} 00~24시")
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


class StatisticsPageTriggers:
    """StatisticsPage의 데이터 로드·내보내기 메서드"""

    def reload(self):
        """요약(KPI·차트)과 세션 이력 테이블을 모두 갱신하는 전체 리로드.
        3초 주기 타이머는 테이블이 빠진 _refresh_summary()만 호출한다
        (layout/statistics.py 참고) — 세션 이력은 세션 종료 시점에만 바뀌므로
        매 틱 재구성이 불필요하고, 재구성마다 사용자가 적용한 정렬도 풀렸었다."""
        self._refresh_summary()
        self._refresh_session_table()

    def _refresh_summary(self):
        toolbar = getattr(self.window(), "global_toolbar", None)
        running = bool(getattr(toolbar, "_running", False)) if toolbar else False
        self.reset_btn.setEnabled(not running)

        rows = store.get_url_maps()
        sessions = store.get_sessions()

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
        self.kpi_conn_fail.update_value(agg["status_group"].get(NO_STATUS_CODE, 0))

        self._refresh_data_kpis(total, agg)
        self._refresh_process_kpis(agg)

        self.status_chart.set_data(_status_segments(status_cnt))
        self.status_chart.setToolTip(_other_codes_text(status_cnt))

        # 4분류를 값이 0이어도 항상 모두 넘긴다 — RankedBarChart는 빈 리스트면
        # 카드를 통째로 비우므로, 수집 이력이 없을 때도 골격이 보이게 한다
        self.outcome_chart.set_data(
            [(label, agg["outcome"].get(label, 0), color) for label, color in OUTCOME_SEGMENTS])
        self.speed_chart.set_data(
            [(label, agg["speed"].get(label, 0), color) for label, color in SPEED_SEGMENTS])

        self._refresh_quality_kpis(sessions)

        self._update_diagnosis(diagnose(total, agg))

        self._refresh_trend_chart(rows, agg)

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

    def _refresh_quality_kpis(self, sessions):
        """세션 누계로 상세 지표(처리량·요청 대비 응답률·스킵률)를 갱신한다 — 이 카드는
        상세 정보 영역이 생기기 전까지 숨겨 둔다(layout/statistics.py). url_count(생성된 URL 수)와
        skipped(URL 불일치로 버려진 응답 수)는 저장만 되고 어디에도 노출되지
        않던 값으로, 수집이 조용히 0건으로 끝나는 상황을 드러내는 지표다."""
        total = sum(s.get("total", 0) for s in sessions)
        elapsed = sum(s.get("elapsed", 0) or 0 for s in sessions)
        url_count = sum(s.get("url_count", 0) for s in sessions)
        skipped = sum(s.get("skipped", 0) for s in sessions)
        responded = total + skipped

        self.kpi_throughput.update_value(f"{total / elapsed:.1f}/s" if elapsed else "—")
        self.kpi_achieve.update_value(f"{total / url_count * 100:.1f}%" if url_count else "—")
        self.kpi_skip.update_value(f"{skipped / responded * 100:.1f}%" if responded else "—")

    def _refresh_process_kpis(self, agg: dict) -> None:
        """데이터 처리 카드를 갱신한다 — 응답 이후 추출된 데이터의 품질(필드 채움률·완전한
        행 비율)과 페이지당 수집량(중앙값·범위). 이 필드를 기록하기 시작한 이후의 응답이
        없으면 해당 지표는 "—"로 둔다. 페이지당 수집량은 데이터를 가져온 페이지("정상
        수집")만 대상으로 해 빈 응답이 중앙값·최소값을 0으로 끌어내리지 않게 한다."""
        cells = agg["field_cells"]
        self.kpi_fill_rate.update_value(f"{(cells - agg['empty_cells']) / cells * 100:.1f}%" if cells else "—")
        field_items = agg["field_items"]
        self.kpi_complete_rate.update_value(_percent(agg["complete_rows"], field_items) if field_items else "—")

        pages = agg["page_items"]
        self.kpi_page_median.update_value(f"{_count_text(_median(pages))}건" if pages else "—")
        self.kpi_item_range.update_value(f"{min(pages):,} ~ {max(pages):,}건" if pages else "—")

    def _refresh_data_kpis(self, total: int, agg: dict) -> None:
        """수집 데이터 카드를 갱신한다. 성공 기준은 응답 결과 구성 카드·진단 배너와
        같은 "정상 수집"이다. 데이터 건수(item_count)는 이 필드를 기록하기 시작한
        이후의 응답에만 있어, 해당 응답이 하나도 없으면 "—"로 둔다."""
        outcome = agg["outcome"]
        ok_pages = outcome.get(OUTCOME_OK, 0)
        self.kpi_data_rate.update_value(_percent(ok_pages, total))
        # 빈 응답 분류에는 추출 오류가 포함되므로, 두 값이 겹치지 않게 빼서 보여준다
        extract_err = agg["extract_err"]
        self.kpi_empty_pages.update_value(
            f"{outcome.get(OUTCOME_EMPTY, 0) - extract_err} / {extract_err}")

        if not agg["counted_pages"]:
            self.kpi_items.update_value("—")
            self.kpi_items_per_page.update_value("—")
            return
        self.kpi_items.update_value(f"{agg['item_sum']:,}건")
        counted_ok = agg["counted_ok_pages"]
        self.kpi_items_per_page.update_value(
            f"{agg['item_sum'] / counted_ok:.1f}건" if counted_ok else "0건")

    def _aggregate_rows(self, rows):
        """url_maps를 한 번만 순회해 행 기반 집계를 모두 산출한다 — 3초마다
        호출되는데 행 수는 통계 초기화 전까지 계속 누적되므로, 지표마다 따로
        순회하지 않는다."""
        daily_ok, daily_err = defaultdict(int), defaultdict(int)
        status_group = defaultdict(int)
        outcome = defaultdict(int)
        speed = defaultdict(int)
        blocked = 0
        extract_err = 0
        item_sum, counted_pages, counted_ok_pages = 0, 0, 0
        page_items = []
        field_cells = empty_cells = complete_rows = field_items = 0

        for r in rows:
            code = str(r.get("status_code", ""))
            is_ok = code == "200"
            timestamp = r.get("timestamp") or ""

            status_group[_status_group(code)] += 1
            row_outcome = _outcome(r, code, is_ok)
            outcome[row_outcome] += 1
            blocked += code in BLOCKED_STATUS_CODES
            extract_err += row_outcome == OUTCOME_EMPTY and bool(r.get("extract_error"))

            latency = r.get("pure_latency")
            if isinstance(latency, float):
                speed[_speed_bucket(latency)] += 1

            item_count = r.get("item_count")
            if isinstance(item_count, int):
                item_sum += item_count
                counted_pages += 1
                counted_ok_pages += row_outcome == OUTCOME_OK
                if row_outcome == OUTCOME_OK:
                    page_items.append(item_count)

            # 필드 채움 기록(worker.count_field_fill)이 있는 응답만 — 없는 과거 기록은 건너뛴다
            cells = r.get("field_cells")
            if isinstance(cells, int):
                field_cells += cells
                empty_cells += r.get("empty_cells", 0)
                complete_rows += r.get("complete_rows", 0)
                field_items += item_count if isinstance(item_count, int) else 0

            if timestamp:
                (daily_ok if is_ok else daily_err)[timestamp[:10]] += 1

        return {
            "daily_ok": daily_ok, "daily_err": daily_err,
            "status_group": status_group, "outcome": outcome, "speed": speed, "blocked": blocked,
            "extract_err": extract_err, "item_sum": item_sum,
            "counted_pages": counted_pages, "counted_ok_pages": counted_ok_pages,
            "page_items": page_items, "field_cells": field_cells, "empty_cells": empty_cells,
            "complete_rows": complete_rows, "field_items": field_items,
        }

    def _refresh_session_table(self):
        sessions = store.get_sessions()

        self.session_table.setRowCount(0)
        for idx, s in enumerate(reversed(sessions), start=1):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            # title은 세션 레코드에 나중에 추가된 필드라 과거 stats_history.json에는
            # 없을 수 있음 — job/url도 함께 .get()으로 통일해 방어적으로 접근한다.
            interrupted = s.get("interrupted", False)
            vals = [str(idx), s.get("title", ""), s.get("url", ""), str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"],
                    s.get("job", ""), "중단" if interrupted else "완료"]
            colors = [TEXT_MUTED, TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED, TEXT_PRIMARY,
                      RED if interrupted else GREEN]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, s)  # 더블클릭 시 요청 상세를 열 세션 레코드
                self.session_table.setItem(r, col, item)

        self.session_badge.setText(f"{len(sessions)}건")

    def _aggregate_all_time(self, period: str) -> AllTimeTrend:
        """store 전체 URL 응답 기록을 period의 전체 보기 방식으로 접어 합산한다."""
        return aggregate_all_time(store.get_url_maps(), period)

    def _on_reset_clicked(self):
        store.clear_url_maps()
        store.clear_sessions()
        store.save_stats_history()
        self.reload()
