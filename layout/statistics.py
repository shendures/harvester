# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QDialog
from PyQt6.QtCore import QTimer, QSize, Qt

from trigger import StatisticsPageTriggers
from trigger.common import _default_dialog_qss
from style import StatCard, EqualSpacingTable, Divider, _load_svg_icon
from .common import parts, build_scroll_body, BG_SECONDARY, BORDER, GREEN, BLUE, PURPLE, RED, TEXT_SECONDARY
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
    def _make_hourly_popup_dialog(self, title: str, size: tuple, min_size: tuple) -> tuple:
        """layout/single/monitor.py의 _make_popup_dialog와 동일한 골격의 최소
        복제본. StatisticsPage는 MonitorPageSingle을 상속하지 않아 그 메서드를
        직접 재사용할 수 없고, monitor.py는 손대지 않는 파일이라 옮기지 않는다."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(False)
        dlg.resize(*size)
        dlg.setMinimumSize(*min_size)
        dlg.setStyleSheet(_default_dialog_qss())
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        return dlg, lay

    def _open_hourly_trend_popup(self) -> None:
        """시간대별 수집량 추이(00~24시, 날짜 무관 전체 누적)를 새 창에서
        보여주는 모달리스 팝업을 연다. 데이터는 열릴 때 한 번만 계산해서
        그린다."""
        dlg, lay = self._make_hourly_popup_dialog(
            "시간대별 수집량 추이 (00~24시 누적)", (1200, 620), (700, 420))

        card_w, card_l = parts.card_widget("시간대별 수집량 추이 (00~24시 누적)")
        popup_chart = GroupedBarChart()
        labels, ok_vals, err_vals = self._aggregate_hourly_all_time()
        popup_chart.set_data(labels, [("성공", ok_vals, GREEN), ("오류", err_vals, RED)])
        card_l.addWidget(popup_chart)
        lay.addWidget(card_w)

        dlg.show()

