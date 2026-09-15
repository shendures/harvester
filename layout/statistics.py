# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import QTimer, QSize

from trigger import StatisticsPageTriggers
from style import EqualSpacingTable, Divider, _load_svg_icon
from .common import (
    parts, build_scroll_body, build_stat_summary_card, build_reset_button, build_popup_dialog,
    GREEN, BLUE, PURPLE, RED, TEXT_SECONDARY,
)
from .charts import RankedBarChart, HeatStripChart, GroupedBarChart


class StatisticsPage(QWidget, StatisticsPageTriggers):
    def __init__(self):
        super().__init__()
        self._build()
        # auto-refresh every 3 s — 세션 이력 테이블은 세션 종료 시에만 바뀌므로
        # 제외하고 KPI/차트만 갱신한다(trigger/statistics.py의 reload() 참고)
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_summary)
        self._timer.start(3000)

    def _build(self):
        bl = build_scroll_body(self)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.reset_btn = build_reset_button(
            parts, self,
            title="통계 초기화 확인",
            text="<b>누적된 통계 분석 데이터를 초기화하시겠습니까?</b>",
            informative_text="URL 응답 이력과 세션 이력이 모두 삭제되며, 되돌릴 수 없습니다.",
            on_confirmed=self._on_reset_clicked,
        )
        btn_row.addWidget(self.reset_btn)
        bl.addLayout(btn_row)

        # ── Row 1: KPI summary card (대시보드 "세션 통계"와 동일한 카드 패턴) ──
        kpi_card_w, (self.kpi_total, self.kpi_success, self.kpi_avg_t, self.kpi_sessions) = build_stat_summary_card(
            parts, "통계 요약",
            [("총 수집 항목", "0"), ("성공률", "0%", GREEN), ("평균 응답", "—", BLUE), ("완료 세션", "0", PURPLE)],
        )
        bl.addWidget(kpi_card_w)

        # ── Row 2: Status ranked list + heat strip + trend sparkline ──
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        sw, sl = parts.card_widget("상태 코드 분포")
        self.status_chart = RankedBarChart()
        sl.addWidget(self.status_chart)
        row2.addWidget(sw, 1)

        rw2, rl2 = parts.card_widget("응답 시간 분포 (s)")
        self.resp_chart = HeatStripChart(color=BLUE)
        rl2.addWidget(self.resp_chart)
        row2.addWidget(rw2, 1)

        # Hourly trend sparkline hero — card_widget()은 우측에 위젯을 얹는 기능이
        # 없어(layout/single/monitor.py의 raw_popout_btn과 동일한 이유) 제목 줄을
        # 직접 구성해 우측 최상단에 "00~24시 누적 보기" 버튼을 둔다.
        lw, ll = parts.card_widget("")
        trend_hdr_row = QHBoxLayout()
        trend_title_lbl = parts.make_label("시간대별 수집량 추이".upper(), TEXT_SECONDARY, 12)
        trend_title_lbl.setStyleSheet(trend_title_lbl.styleSheet() + " letter-spacing:1px;")
        trend_hdr_row.addWidget(trend_title_lbl)
        trend_hdr_row.addStretch()
        self.hourly_popout_btn = parts.outline_btn("")
        self.hourly_popout_btn.setIcon(_load_svg_icon("external-link", TEXT_SECONDARY, "2", 14))
        self.hourly_popout_btn.setIconSize(QSize(14, 14))
        self.hourly_popout_btn.setFixedSize(30, 20)
        self.hourly_popout_btn.setToolTip("00~24시 전체 누적 수집량 추이를 새 창에서 보기")
        self.hourly_popout_btn.clicked.connect(self._open_hourly_trend_popup)
        trend_hdr_row.addWidget(self.hourly_popout_btn)
        ll.addLayout(trend_hdr_row)
        ll.addWidget(Divider())

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

    # ── Hourly trend popup (00~24시 전체 누적) ──────
    def _open_hourly_trend_popup(self) -> None:
        """시간대별 수집량 추이(00~24시, 날짜 무관 전체 누적)를 새 창에서
        보여주는 모달리스 팝업을 연다. 데이터는 열릴 때 한 번만 계산해서
        그린다."""
        dlg, lay = build_popup_dialog(
            self, "시간대별 수집량 추이 (00~24시 누적)", (1200, 620), (700, 420))

        card_w, card_l = parts.card_widget("시간대별 수집량 추이 (00~24시 누적)")
        popup_chart = GroupedBarChart()
        labels, ok_vals, err_vals = self._aggregate_hourly_all_time()
        popup_chart.set_data(labels, [("성공", ok_vals, GREEN), ("오류", err_vals, RED)])
        card_l.addWidget(popup_chart)
        lay.addWidget(card_w)

        dlg.show()

