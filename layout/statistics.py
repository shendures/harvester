# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import QTimer

from trigger import StatisticsPageTriggers
from style import StatCard, EqualSpacingTable
from .common import parts, build_scroll_body, BG_SECONDARY, BORDER, GREEN, BLUE, PURPLE
from .charts import RankedBarChart, HeatStripChart, GroupedBarChart


class StatisticsPage(QWidget, StatisticsPageTriggers):
    def __init__(self):
        super().__init__()
        self._build()
        # auto-refresh every 3 s
        self._timer = QTimer()
        self._timer.timeout.connect(self.reload)
        self._timer.start(3000)

    def _build(self):
        bl = build_scroll_body(self)

        # ── Reset ──────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.reset_btn = parts.action_btn("RESET")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        btn_row.addWidget(self.reset_btn)
        bl.addLayout(btn_row)

        # ── Row 1: KPI cards ──────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        self.kpi_total = StatCard("총 수집 항목", "0")
        self.kpi_success = StatCard("성공률", "0%", GREEN)
        self.kpi_avg_t = StatCard("평균 응답", "—", BLUE)
        self.kpi_sessions = StatCard("완료 세션", "0", PURPLE)
        for kpi in [self.kpi_total, self.kpi_success, self.kpi_avg_t, self.kpi_sessions]:
            kpi.setStyleSheet(f"background:{BG_SECONDARY}; border-radius:6px; border:1px solid {BORDER};")
            kpi_row.addWidget(kpi, 1)
        bl.addLayout(kpi_row)

        # ── Row 2: Status ranked list + heat strip + trend sparkline ──
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Status ranked list
        sw, sl = parts.card_widget("상태 코드 분포")
        self.status_chart = RankedBarChart()
        sl.addWidget(self.status_chart)
        row2.addWidget(sw, 1)

        # Response time heat strip
        rw2, rl2 = parts.card_widget("응답 시간 분포 (s)")
        self.resp_chart = HeatStripChart(color=BLUE)
        rl2.addWidget(self.resp_chart)
        row2.addWidget(rw2, 1)

        # Hourly trend sparkline hero
        lw, ll = parts.card_widget("시간대별 수집량 추이")
        self.trend_chart = GroupedBarChart()
        ll.addWidget(self.trend_chart)
        row2.addWidget(lw, 1)

        bl.addLayout(row2)

        # ── Row 3: Session history table ──────────
        tw, tl = parts.card_widget("세션 이력")
        self.session_table = EqualSpacingTable(
            parent=self,
            row_height=30,
            col_padding=10,
            hscroll_handle=50,
        )
        self.session_table.setColumnCount(11)
        self.session_table.setHorizontalHeaderLabels(
            ["NO", "Title", "URL", "Total Items", "Success", "Errors", "Avg Response", "Duration", "Start Time", "End Time", "Task Name"])
        tl.addWidget(self.session_table)
        bl.addWidget(tw)

