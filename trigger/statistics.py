# trigger/statistics.py
# StatisticsPage의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

from collections import defaultdict
from datetime import datetime, timedelta

from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor

from .common import (
    store, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_MUTED,
    GREEN, RED, BLUE, STATUS_CODE_COLORS,
)

class StatisticsPageTriggers:
    """StatisticsPage의 데이터 로드·내보내기 메서드"""

    # ── data ───────────────────────────────────
    def reload(self):
        toolbar = getattr(self.window(), "global_toolbar", None)
        running = bool(getattr(toolbar, "_running", False)) if toolbar else False
        self.reset_btn.setEnabled(not running)

        rows = store.get_url_maps()
        sessions = store.get_sessions()

        total = len(rows)  # URL_LIST
        ok = sum(1 for r in rows if str(r["status_code"]) == "200")  # URL_LIST 중 RESPONSE = 200인 것
        rate = f"{ok / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]  # URL_LIST의 각각 URL의 순수 레이턴시
        avg_time_val = sum(times) / len(times) if times else 0.0
        avg_t = f"{avg_time_val:.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        # 상태 코드 분포 ( 통계 분석 - 상태 코드 분포 )
        status_cnt = defaultdict(int)
        for r in rows:
            status_cnt[str(r["status_code"])] += 1
        # ── 수정: STATUS_CODE_COLORS 키가 str이므로 조회 키도 str로 통일해
        # 단일 응답 시 Gray 오류 해소 ──
        segments = [(k, v, STATUS_CODE_COLORS.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.status_chart.set_data(segments)

        # 응답 시간 분포 (bucket 0.2 intervals) ( 통계 분석 - 응답 시간 분포  )
        buckets = defaultdict(int)
        for t in times:
            b = round(round(t / 0.2) * 0.2, 1)
            buckets[b] += 1
        sorted_b = sorted(buckets.items())
        labels = [str(k) for k, _ in sorted_b]
        values = [v for _, v in sorted_b]
        self.resp_chart.set_data(labels, values, avg_time_val, color=BLUE)

        # Hourly trend (last 12 hours) ( 통계분석 - 시간대별 수집량 추이 )
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
            [("성공", ok_vals, GREEN), ("오류", err_vals, RED)]
        )

        # Session table ( 통계 분석 - 세션 이력 )
        self.session_table.setSortingEnabled(False)
        self.session_table.setRowCount(0)
        for idx, s in enumerate(reversed(sessions), start=1):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            # title은 세션 레코드에 나중에 추가된 필드라 과거 stats_history.json에는
            # 없을 수 있음 — job/url도 함께 .get()으로 통일해 방어적으로 접근한다.
            vals = [str(idx), s.get("title", ""), s.get("url", ""), str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"],
                    s.get("job", "")]
            colors = [TEXT_MUTED, TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED, TEXT_PRIMARY]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.session_table.setItem(r, col, item)
        self.session_table.setSortingEnabled(True)

    # ── hourly popup data ──────────────────────
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

    # ── actions ────────────────────────────────
    def _on_reset_clicked(self):
        store.clear_url_maps()
        store.clear_sessions()
        self.reload()
