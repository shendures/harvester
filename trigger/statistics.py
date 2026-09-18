# trigger/statistics.py
# StatisticsPage의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse

from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor

from .common import (
    store, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_MUTED,
    GREEN, RED, BLUE, AMBER, PURPLE, STATUS_CODE_COLORS,
)

DAILY_TREND_DAYS = 14
FAILED_URL_TOP_N = 10

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


class StatisticsPageTriggers:
    """StatisticsPage의 데이터 로드·내보내기 메서드"""

    def reload(self):
        """요약(KPI·차트)과 이력/집계 테이블을 모두 갱신하는 전체 리로드.
        3초 주기 타이머는 테이블이 빠진 _refresh_summary()만 호출한다
        (layout/statistics.py 참고) — 세션 이력은 세션 종료 시점에만 바뀌므로
        매 틱 재구성이 불필요하고, 재구성마다 사용자가 적용한 정렬도 풀렸었다.
        집계 테이블 3종도 같은 이유로 이쪽 경로에만 둔다."""
        self._refresh_summary()
        self._refresh_session_table()
        self._refresh_aggregate_tables()

    def _refresh_summary(self):
        toolbar = getattr(self.window(), "global_toolbar", None)
        running = bool(getattr(toolbar, "_running", False)) if toolbar else False
        self.reset_btn.setEnabled(not running)

        rows = store.get_url_maps()
        sessions = store.get_sessions()

        total = len(rows)
        ok = sum(1 for r in rows if str(r["status_code"]) == "200")
        rate = f"{ok / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]
        avg_time_val = sum(times) / len(times) if times else 0.0
        avg_t = f"{avg_time_val:.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        status_cnt = defaultdict(int)
        for r in rows:
            status_cnt[str(r["status_code"])] += 1
        # ── 수정: STATUS_CODE_COLORS 키가 str이므로 조회 키도 str로 통일해
        # 단일 응답 시 Gray 오류 해소 ──
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

        hour_ok = defaultdict(int)
        hour_err = defaultdict(int)
        now = datetime.now()
        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_h = int((now - ts).total_seconds() // 3600)
                if 0 <= diff_h < 12:
                    bucket = now.hour - diff_h
                    if str(r["status_code"]) == "200":
                        hour_ok[bucket] += 1
                    else:
                        hour_err[bucket] += 1
            except (ValueError, KeyError, TypeError):
                pass
        hours = [(now - timedelta(hours=11 - i)).hour for i in range(12)]
        ok_vals = [hour_ok.get(h, 0) for h in hours]
        err_vals = [hour_err.get(h, 0) for h in hours]
        self.trend_chart.set_data(
            [f"{h:02d}h" for h in hours],
            [("성공", ok_vals, GREEN), ("실패", err_vals, RED)]
        )

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

        days = [(datetime.now() - timedelta(days=DAILY_TREND_DAYS - 1 - i)).strftime("%Y-%m-%d")
                for i in range(DAILY_TREND_DAYS)]
        self.daily_chart.set_data(
            [d[5:] for d in days],
            [("성공", [agg["daily_ok"].get(d, 0) for d in days], GREEN),
             ("실패", [agg["daily_err"].get(d, 0) for d in days], RED)]
        )

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
        url_fail = defaultdict(lambda: {"count": 0, "last_status": "", "last_seen": ""})
        host = defaultdict(lambda: {"req": 0, "ok": 0, "lat_sum": 0.0, "lat_cnt": 0})
        daily_ok, daily_err = defaultdict(int), defaultdict(int)
        status_group = defaultdict(int)
        outcome = defaultdict(int)
        overhead_sum, overhead_cnt = 0.0, 0

        for r in rows:
            code = str(r.get("status_code", ""))
            is_ok = code == "200"
            req_url = r.get("req_url") or ""
            timestamp = r.get("timestamp") or ""

            status_group[_status_group(code)] += 1
            outcome[_outcome(r, code, is_ok)] += 1

            if not is_ok:
                entry = url_fail[req_url]
                entry["count"] += 1
                # rows는 수집 순서대로 쌓이므로 마지막에 덮어쓴 값이 최신 기록이다
                entry["last_status"] = code
                entry["last_seen"] = timestamp

            entry = host[urlparse(req_url).netloc or "—"]
            entry["req"] += 1
            entry["ok"] += 1 if is_ok else 0

            pure = r.get("pure_latency")
            if isinstance(pure, float):
                entry["lat_sum"] += pure
                entry["lat_cnt"] += 1

            total_latency = r.get("total_latency")
            if isinstance(pure, float) and isinstance(total_latency, float):
                overhead_sum += max(total_latency - pure, 0.0)
                overhead_cnt += 1

            if timestamp:
                (daily_ok if is_ok else daily_err)[timestamp[:10]] += 1

        return {
            "url_fail": url_fail, "host": host,
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
        self._fit_table_height(self.session_table, len(sessions))

    def _fill_table(self, table, records):
        """records = [[(값, 색), ...], ...]로 표를 다시 채운다 — 집계 표 3종 공용.
        셀 값이 길어 잘릴 수 있는 URL/호스트를 위해 전 셀에 툴팁을 단다."""
        table.setRowCount(0)
        for record in records:
            r = table.rowCount()
            table.insertRow(r)
            for col, (val, color) in enumerate(record):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                item.setToolTip(val)
                table.setItem(r, col, item)

    def _refresh_aggregate_tables(self):
        """반복 실패 URL / 호스트별 현황 / 작업별 성능 표를 갱신한다. 표를 채운 뒤
        카운트 배지 텍스트와 표 높이(_fit_table_height — 실제 행 수만큼만 차지)를
        함께 갱신해, 데이터가 적을 때 카드에 빈 공백이 남지 않게 한다."""
        agg = self._aggregate_rows(store.get_url_maps())

        top_failures = sorted(agg["url_fail"].items(), key=lambda kv: kv[1]["count"], reverse=True)
        if top_failures:
            rows = [[(url, ACCENT_LIGHT), (str(info["count"]), RED),
                     (info["last_status"], STATUS_CODE_COLORS.get(info["last_status"], TEXT_PRIMARY)),
                     (info["last_seen"], TEXT_MUTED)]
                    for url, info in top_failures[:FAILED_URL_TOP_N]]
        else:
            # 빈 표는 "실패 없음"과 "수집 이력 없음"이 구분되지 않아 한 줄로 알린다
            message = "실패한 URL이 없습니다" if store.get_url_maps() else "수집 이력이 없습니다"
            rows = [[(message, TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED)]]
        self._fill_table(self.failed_url_table, rows)
        self.failed_url_badge.setText(f"{len(top_failures)}건")
        self._fit_table_height(self.failed_url_table, len(rows))

        hosts = sorted(agg["host"].items(), key=lambda kv: kv[1]["req"], reverse=True)
        if hosts:
            host_rows = [
                [(host, ACCENT_LIGHT), (str(info["req"]), TEXT_PRIMARY),
                 (f"{info['ok'] / info['req'] * 100:.1f}%", GREEN if info["ok"] == info["req"] else AMBER),
                 (f"{info['lat_sum'] / info['lat_cnt']:.2f}s" if info["lat_cnt"] else "—", BLUE)]
                for host, info in hosts
            ]
        else:
            # failed_url_table과 달리 호스트는 요청마다 항상 존재하므로 구분할
            # "성공/실패" 케이스가 없다 — 수집 이력 자체가 없는 경우만 있다
            host_rows = [[("수집 이력이 없습니다", TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED)]]
        self._fill_table(self.host_table, host_rows)
        self.host_badge.setText(f"{len(hosts)}건")
        self._fit_table_height(self.host_table, len(host_rows))

        self._refresh_job_table()

    def _refresh_job_table(self):
        """세션 이력을 블루프린트(title)별로 묶어 성능을 비교한다 — 세션 이력
        테이블은 세션을 나열만 할 뿐 작업 단위 집계가 없었다."""
        jobs = defaultdict(lambda: {"sessions": 0, "total": 0, "success": 0, "elapsed": 0.0, "avg_sum": 0.0})
        for s in store.get_sessions():
            entry = jobs[s.get("title") or s.get("job") or "—"]
            entry["sessions"] += 1
            entry["total"] += s.get("total", 0)
            entry["success"] += s.get("success", 0)
            entry["elapsed"] += s.get("elapsed", 0) or 0
            entry["avg_sum"] += s.get("avg_time", 0) or 0

        sorted_jobs = sorted(jobs.items(), key=lambda kv: kv[1]["total"], reverse=True)
        if sorted_jobs:
            rows = [
                [(title, TEXT_PRIMARY), (str(i["sessions"]), TEXT_MUTED), (str(i["total"]), TEXT_PRIMARY),
                 (f"{i['success'] / i['total'] * 100:.1f}%" if i["total"] else "—",
                  GREEN if i["success"] == i["total"] else AMBER),
                 (f"{i['avg_sum'] / i['sessions']:.2f}s", BLUE),
                 (f"{i['total'] / i['elapsed']:.1f}/s" if i["elapsed"] else "—", PURPLE)]
                for title, i in sorted_jobs
            ]
        else:
            rows = [[("작업 이력이 없습니다", TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED),
                     ("", TEXT_MUTED), ("", TEXT_MUTED), ("", TEXT_MUTED)]]
        self._fill_table(self.job_table, rows)
        self.job_badge.setText(f"{len(sorted_jobs)}건")
        self._fit_table_height(self.job_table, len(rows))

    def _aggregate_hourly_all_time(self):
        """store 전체 URL 응답 기록을 날짜 구분 없이 시(0~23) 단위로 합산한다.
        reload()의 '최근 12시간' 집계와 달리 diff_h 필터 없이 ts.hour 자체를
        버킷 키로 쓴다."""
        rows = store.get_url_maps()
        hour_ok = defaultdict(int)
        hour_err = defaultdict(int)
        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                if str(r["status_code"]) == "200":
                    hour_ok[ts.hour] += 1
                else:
                    hour_err[ts.hour] += 1
            except (ValueError, KeyError, TypeError):
                pass
        labels = [f"{h:02d}h" for h in range(24)]
        ok_vals = [hour_ok.get(h, 0) for h in range(24)]
        err_vals = [hour_err.get(h, 0) for h in range(24)]
        return labels, ok_vals, err_vals

    def _on_reset_clicked(self):
        store.clear_url_maps()
        store.clear_sessions()
        store.save_stats_history()
        self.reload()
