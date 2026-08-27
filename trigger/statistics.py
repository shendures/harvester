# trigger/statistics.py
# StatisticsPage의 데이터 로드·내보내기 메서드(StatisticsPageTriggers).

from collections import defaultdict
from datetime import datetime, timedelta

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget, QTableWidgetItem
from PyQt6.QtGui import QColor

from .common import (
    store, parts, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GREEN, AMBER, RED, BLUE, PURPLE,
)

class StatisticsPageTriggers:
    """StatisticsPage의 데이터 로드·내보내기 메서드"""

    # ── data ───────────────────────────────────
    def reload(self):
        rows = store.get_url_maps()
        sessions = store.get_sessions()
        if not rows and not sessions:
            return

        total = len(rows)  # URL_LIST
        ok = sum(1 for r in rows if str(r["status_code"]) == "200")  # URL_LIST 중 RESPONSE = 200인 것
        rate = f"{ok / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]  # URL_LIST의 각각 URL의 순수 레이턴시
        avg_t = f"{sum(times) / len(times):.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        # Donut ( 통계 분석 - 상태 코드 분포 )
        status_cnt = defaultdict(int)
        for r in rows:
            status_cnt[str(r["status_code"])] += 1
        # ── 수정: COLOR_MAP 키를 str 로 통일하여 단일 응답 시 Gray 오류 해소 ──
        COLOR_MAP = {"200": GREEN, "301": BLUE, "404": AMBER, "429": PURPLE, "500": RED}
        segments = [(k, v, COLOR_MAP.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.donut.set_data(segments)
        # rebuild legend
        for i in reversed(range(self.legend_lay.count())):
            w = self.legend_lay.itemAt(i).widget()
            if w:
                w.deleteLater()
        for k, v, color in segments:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:12px;")
            txt = parts.make_label(f"{k}  {v}", TEXT_SECONDARY, 11)
            rl.addWidget(dot)
            rl.addWidget(txt)
            rl.addStretch()
            self.legend_lay.addWidget(row_w)
        self.legend_lay.addStretch()

        # Response bar (bucket 0.2 intervals) ( 통계 분석 - 응답 시간 분포  )
        if times:
            buckets = defaultdict(int)
            for t in times:
                b = round(round(t / 0.2) * 0.2, 1)
                buckets[b] += 1
            sorted_b = sorted(buckets.items())
            labels = [str(k) for k, _ in sorted_b]
            values = [v for _, v in sorted_b]
            self.resp_bar.set_data(labels, values, BLUE)

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
        self.trend_line.set_data(
            [f"{h:02d}h" for h in hours],
            [("성공", ok_vals, GREEN), ("오류", err_vals, RED)]
        )

        # Session table ( 통계 분석 - 세션 이력 )
        self.session_table.setSortingEnabled(False)
        self.session_table.setRowCount(0)
        for s in reversed(sessions):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            vals = [s["job"], s["url"], str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"]]
            colors = [TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.session_table.setItem(r, col, item)
        self.session_table.setSortingEnabled(True)
