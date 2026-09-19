# trigger/statistics.py
# StatisticsPage의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from typing import NamedTuple

from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor

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
# "연결 실패"에 TEXT_MUTED를 쓰는 건 나란히 놓인 "상태 코드 분포" 카드의
# STATUS_CODE_COLORS["000"]과 색 언어를 맞추기 위해서다.
OUTCOME_OK, OUTCOME_EMPTY = "정상 수집", "빈 응답"
OUTCOME_HTTP_ERR, OUTCOME_CONN_FAIL = "HTTP 오류", "연결 실패"
OUTCOME_SEGMENTS = (
    (OUTCOME_OK, GREEN), (OUTCOME_EMPTY, AMBER),
    (OUTCOME_HTTP_ERR, RED), (OUTCOME_CONN_FAIL, TEXT_MUTED),
)


def _percentile(sorted_values: list, q: float):
    """nearest-rank 백분위. statistics.quantiles()는 표본이 2개 미만이면
    ValueError라, 수집 1건만으로도 그려져야 하는 이 화면에서는 쓸 수 없다."""
    if not sorted_values:
        return None
    return sorted_values[min(int(len(sorted_values) * q), len(sorted_values) - 1)]


def _status_group(code: str) -> str:
    """상태 코드를 2xx/3xx/4xx/5xx로 묶는다. engine.handle_request_failure()가
    보고하는 연결 실패("000")는 HTTP 에러와 원인·대응이 달라 따로 분류한다."""
    if code == "000":
        return "000"
    return f"{code[0]}xx" if code[:1].isdigit() else "기타"


def _outcome(row: dict, code: str, is_ok: bool) -> str:
    """응답을 실제로 쓸 수 있었는지 기준으로 4분류한다 — 상태 코드만으로는
    "200인데 추출 0건"(빈 응답)이 성공과 구분되지 않는다. empty_extract는
    worker.py가 적재하기 전의 과거 stats_history.json 행에는 없어 None이
    되는데, 그때는 구분할 근거 자체가 없으므로 정상 수집으로 둔다."""
    if code == "000":
        return OUTCOME_CONN_FAIL
    if not is_ok:
        return OUTCOME_HTTP_ERR
    return OUTCOME_EMPTY if row.get("empty_extract") else OUTCOME_OK


class TrendWindow(NamedTuple):
    """수집량 추이 카드가 그릴 구간 — start는 첫 칸의 시작 시각(시간대별은 시
    단위, 그 외는 일 단위 자정), buckets는 칸 수, range_text는 카드명에 쓸 범위."""
    start: datetime
    buckets: int
    range_text: str


def _sunday_on_or_before(day: datetime) -> datetime:
    return day - timedelta(days=(day.weekday() + 1) % DAYS_PER_WEEK)


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
    TREND_WEEKLY: (list(WEEKDAY_LABELS), lambda ts: (ts.weekday() + 1) % DAYS_PER_WEEK),
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
        rate = f"{status_cnt.get('200', 0) / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]
        avg_time_val = sum(times) / len(times) if times else 0.0
        avg_t = f"{avg_time_val:.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        segments = [(k, v, STATUS_CODE_COLORS.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.status_chart.set_data(segments)

        buckets = defaultdict(int)
        for t in times:
            b = round(round(t / 0.2) * 0.2, 1)
            buckets[b] += 1
        sorted_b = sorted(buckets.items())
        labels = [str(k) for k, _ in sorted_b]
        values = [v for _, v in sorted_b]
        self.resp_chart.set_data(labels, values, avg_time_val, color=BLUE)

        agg = self._aggregate_rows(rows)

        # 4분류를 값이 0이어도 항상 모두 넘긴다 — RankedBarChart는 빈 리스트면
        # 카드를 통째로 비우므로, 수집 이력이 없을 때도 골격이 보이게 한다
        self.outcome_chart.set_data(
            [(label, agg["outcome"].get(label, 0), color) for label, color in OUTCOME_SEGMENTS])

        sorted_times = sorted(times)
        for card, q in ((self.kpi_p50, 0.50), (self.kpi_p95, 0.95), (self.kpi_p99, 0.99)):
            value = _percentile(sorted_times, q)
            card.update_value(f"{value:.2f}s" if value is not None else "—")

        # total_latency는 이 필드를 저장하기 시작한 시점 이후의 행에만 있으므로
        # 과거 데이터만 있으면 표본이 0이고, 그때는 "—"로 둔다.
        overhead_cnt = agg["overhead_cnt"]
        self.kpi_overhead.update_value(
            f"{agg['overhead_sum'] / overhead_cnt:.2f}s" if overhead_cnt else "—")

        self._refresh_quality_kpis(sessions, agg)

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
            labels, ok_vals, err_vals = self._daily_counts(agg, window.start, window.buckets)

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
    def _daily_counts(agg, start: datetime, days: int):
        """start부터 days일을 1일 칸으로 집계해 (라벨, 성공, 오류)를 반환한다 —
        _aggregate_rows()가 이미 만든 daily_ok/daily_err(키 = "YYYY-MM-DD")를
        읽기만 해서 행을 다시 순회하지 않는다."""
        dates = [start + timedelta(days=i) for i in range(days)]
        keys = [d.strftime("%Y-%m-%d") for d in dates]
        return ([d.strftime("%m-%d") for d in dates],
                [agg["daily_ok"].get(k, 0) for k in keys],
                [agg["daily_err"].get(k, 0) for k in keys])

    def _refresh_quality_kpis(self, sessions, agg):
        """세션 누계로 수집 품질 지표를 갱신한다. url_count(생성된 URL 수)와
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
        self.kpi_conn_fail.update_value(agg["status_group"].get("000", 0))

    def _aggregate_rows(self, rows):
        """url_maps를 한 번만 순회해 행 기반 집계를 모두 산출한다 — 3초마다
        호출되는데 행 수는 통계 초기화 전까지 계속 누적되므로, 지표마다 따로
        순회하지 않는다."""
        daily_ok, daily_err = defaultdict(int), defaultdict(int)
        status_group = defaultdict(int)
        outcome = defaultdict(int)
        overhead_sum, overhead_cnt = 0.0, 0

        for r in rows:
            code = str(r.get("status_code", ""))
            is_ok = code == "200"
            timestamp = r.get("timestamp") or ""

            status_group[_status_group(code)] += 1
            outcome[_outcome(r, code, is_ok)] += 1

            pure = r.get("pure_latency")
            total_latency = r.get("total_latency")
            if isinstance(pure, float) and isinstance(total_latency, float):
                overhead_sum += max(total_latency - pure, 0.0)
                overhead_cnt += 1

            if timestamp:
                (daily_ok if is_ok else daily_err)[timestamp[:10]] += 1

        return {
            "daily_ok": daily_ok, "daily_err": daily_err,
            "status_group": status_group, "outcome": outcome,
            "overhead_sum": overhead_sum, "overhead_cnt": overhead_cnt,
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
