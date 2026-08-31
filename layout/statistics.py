# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import QTimer

from trigger import StatisticsPageTriggers
from style import StatCard, EqualSpacingTable
from .common import parts, build_scroll_body, BG_SECONDARY, BORDER, GREEN, BLUE, PURPLE
from .charts import BarChart, LineChart, DonutChart


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

        # ── Row 2: Status pie + bar chart ─────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Status donut
        sw, sl = parts.card_widget("상태 코드 분포")
        inner = QHBoxLayout()
        inner.setSpacing(16)
        self.donut = DonutChart()
        inner.addWidget(self.donut)
        legend_w = QWidget()
        legend_w.setStyleSheet("background:transparent;")
        self.legend_lay = QVBoxLayout(legend_w)
        self.legend_lay.setSpacing(6)
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(legend_w)
        inner.addStretch()
        sl.addLayout(inner)
        row2.addWidget(sw, 1)

        # Response time histogram (24 buckets)
        rw2, rl2 = parts.card_widget("응답 시간 분포 (s)")
        self.resp_bar = BarChart(color=BLUE)
        rl2.addWidget(self.resp_bar)
        row2.addWidget(rw2, 2)
        bl.addLayout(row2)

        # ── Row 3: Hourly trend line ───────────────
        lw, ll = parts.card_widget("시간대별 수집량 추이")
        self.trend_line = LineChart()
        self.trend_line.setMinimumHeight(180)
        ll.addWidget(self.trend_line)
        bl.addWidget(lw)

        # ── Row 4: Session history table ──────────
        tw, tl = parts.card_widget("세션 이력")
        self.session_table = EqualSpacingTable(
            parent=self,
            row_height=30,
            col_padding=10,
            hscroll_handle=50,
        )
        self.session_table.setColumnCount(9)
        self.session_table.setHorizontalHeaderLabels(
            ["작업명", "URL", "총 항목", "성공", "오류", "평균 응답", "소요 시간", "시작 시각", "완료 시각"])
        tl.addWidget(self.session_table)
        bl.addWidget(tw)

