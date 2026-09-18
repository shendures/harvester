# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import QTimer, QSize

from trigger import StatisticsPageTriggers
from style import EqualSpacingTable, Divider, _load_svg_icon
from .common import (
    parts, build_scroll_body, build_stat_summary_card, build_reset_button, build_popup_dialog,
    ACCENT_LIGHT,
    GREEN, BLUE, PURPLE, RED, AMBER, TEXT_SECONDARY,
)
from .charts import RankedBarChart, HeatStripChart, GroupedBarChart

TABLE_ROW_H = 30
TABLE_HEADER_H = 32          # EqualSpacingTable 헤더 높이 근사치
SESSION_TABLE_ROWS = 15      # 세션 이력 — 실행마다 늘어나는 유일한 표라 넉넉하게
JOB_TABLE_ROWS = 8           # 작업별 성능 비교 — 수집 목록 개수에 고정되는 표라 여유만 확보
HOST_TABLE_ROWS = 8          # 호스트별 현황 — 대체로 수집 목록 개수와 비슷한 수준
FAILED_URL_TABLE_ROWS = 10   # 반복 실패 URL — trigger/statistics.py의 FAILED_URL_TOP_N과
                             # 반드시 같은 값을 유지(캡보다 작거나 남는 여백이 생기지 않도록)


def _table_height_for_rows(row_count: int, max_rows: int) -> int:
    """행 수(1행 이상 max_rows 이하)에 맞춘 표 높이(px)를 계산한다. 바닥을
    1행으로 두는 이유는 빈 상태에서도 안내 메시지 한 줄은 항상 표시되기
    때문 — _build_table_card()의 초기값과 StatisticsPage._fit_table_height()가
    공유한다. setMinimumHeight()만으로는 EqualSpacingTable의 sizeHint()가 더 커서
    (Expanding 정책이라 여유 공간이 있으면 그쪽이 이긴다) 행이 적어도 카드가
    줄어들지 않길래, 호출부에서 반드시 set_preferred_height()로 적용해야 한다."""
    visible = max(1, min(row_count, max_rows))
    return TABLE_HEADER_H + visible * TABLE_ROW_H


def _build_table_card(parent, title: str, headers: list, visible_rows: int) -> tuple:
    """제목 줄에 카운트 배지를 얹은 카드 안에 EqualSpacingTable을 넣어
    (카드, 테이블, 카운트 배지)를 반환한다 — 집계 표 카드 4종(반복 실패 URL/
    호스트별/작업별/세션 이력)이 공유한다. card_widget()은 제목 문자열만 받고
    옆에 위젯을 얹는 기능이 없어(아래 "시간대별 수집량 추이" 헤더와 같은 이유)
    제목 줄을 직접 구성한다. max_visible_rows는 표에 동적 프로퍼티로 저장해
    trigger/statistics.py의 _fit_table_height() 호출 시 재사용한다."""
    card_w, card_l = parts.card_widget("")

    # 제목/배지는 고정 높이로 둬, 카드가 늘어날 때 여분 높이를 표만 흡수하게 한다.
    header_row = QHBoxLayout()
    title_lbl = parts.make_label(title.upper(), TEXT_SECONDARY, 12)
    title_lbl.setStyleSheet(title_lbl.styleSheet() + " letter-spacing:1px;")
    title_lbl.setFixedHeight(title_lbl.sizeHint().height())
    header_row.addWidget(title_lbl)
    header_row.addStretch()
    badge = parts.count_badge("0건", ACCENT_LIGHT)
    badge.setFixedHeight(badge.sizeHint().height())
    header_row.addWidget(badge)
    card_l.addLayout(header_row)
    card_l.addWidget(Divider())

    table = EqualSpacingTable(parent=parent, row_height=TABLE_ROW_H, col_padding=10, hscroll_handle=50)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setProperty("max_visible_rows", visible_rows)
    table.set_preferred_height(_table_height_for_rows(1, visible_rows))
    card_l.addWidget(table)
    return card_w, table, badge


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
            text="통계 데이터를 초기화하시겠습니까?",
            informative_text="URL 응답 이력과 세션 이력이 모두 삭제되며, 되돌릴 수 없습니다.",
            on_confirmed=self._on_reset_clicked,
        )
        btn_row.addWidget(self.reset_btn)
        bl.addLayout(btn_row)

        self._build_overall_rows(bl)
        self._build_detail_rows(bl)

    def _build_overall_rows(self, bl):
        """페이지 전체를 요약하는 KPI 카드와 분포/추이 차트."""
        # ── Row 1: KPI summary card 3종을 한 줄에 나란히 배치 ──
        # (대시보드 "세션 통계"와 동일한 카드 패턴) 카드마다 전체 폭을 세로로
        # 나눠 쓰던 것을 row2/row3/row4와 같은 패턴으로 묶어, 가로 공백을
        # 줄이고 세로 공간을 절약한다. 카드당 지표가 4개뿐이라 3분할 폭에서도
        # 가장 긴 라벨("네트워크 오버헤드")이 잘리지 않는다. 세 카드 모두
        # setFixedHeight(sizeHint)로 고정하는 이유는 row1에는 다른 두 행(Row2/
        # Row3)만큼 세로 공간이 필요 없는데도, bl에 addStretch()가 없어 남는
        # 공간이 형제 행에 함께 배분되면 카드 안에 빈 공백만 늘어나기 때문이다.
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        kpi_card_w, (self.kpi_total, self.kpi_success, self.kpi_avg_t, self.kpi_sessions) = build_stat_summary_card(
            parts, "통계 요약",
            [("총 수집 항목", "0"), ("성공률", "0%", GREEN), ("평균 응답", "—", BLUE), ("완료 세션", "0", PURPLE)],
        )
        kpi_card_w.setFixedHeight(kpi_card_w.sizeHint().height())
        row1.addWidget(kpi_card_w, 1)

        # 응답 시간은 평균만으로는 롱테일이 은폐되므로 백분위를 함께 둔다.
        # 오버헤드 = total_latency - pure_latency(큐 대기/프록시 구간).
        lat_card_w, (self.kpi_p50, self.kpi_p95, self.kpi_p99, self.kpi_overhead) = build_stat_summary_card(
            parts, "응답 시간 상세",
            [("P50", "—", BLUE), ("P95", "—", AMBER), ("P99", "—", RED), ("네트워크 오버헤드", "—", PURPLE)],
        )
        lat_card_w.setFixedHeight(lat_card_w.sizeHint().height())
        row1.addWidget(lat_card_w, 1)

        quality_card_w, (self.kpi_throughput, self.kpi_achieve, self.kpi_skip, self.kpi_conn_fail) = build_stat_summary_card(
            parts, "수집 품질",
            [("처리량", "—", BLUE), ("수집 달성률", "—", GREEN), ("스킵률", "—", AMBER), ("연결 실패", "0", RED)],
        )
        quality_card_w.setFixedHeight(quality_card_w.sizeHint().height())
        row1.addWidget(quality_card_w, 1)

        bl.addLayout(row1)

        # ── Row 2: 현재 시점 스냅샷 분포(상태 코드/응답 시간) ──────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # 카드 래퍼 자체도 row1의 KPI 카드와 같은 이유로 sizeHint에 고정한다
        # (안 그러면 Row3가 커질 때 이 래퍼도 Preferred 정책 탓에 함께 늘어나
        # 내부 고정 높이 차트 아래로 빈 공백이 생긴다)
        sw, sl = parts.card_widget("상태 코드 분포")
        self.status_chart = RankedBarChart()
        sl.addWidget(self.status_chart)
        sw.setFixedHeight(sw.sizeHint().height())
        row2.addWidget(sw, 1)

        rw2, rl2 = parts.card_widget("응답 시간 분포 (s)")
        self.resp_chart = HeatStripChart(color=BLUE)
        rl2.addWidget(self.resp_chart)
        rw2.setFixedHeight(rw2.sizeHint().height())
        row2.addWidget(rw2, 1)

        # 상태 코드가 못 가르는 축 — 200 응답이라도 추출 0건이면 쓸 수 없는
        # 응답이므로 "빈 응답"으로 따로 세어, 성공률 뒤에 가려진 수집 실패를
        # 드러낸다. 내부 차트가 옆 두 카드와 같은 고정 높이(156)라 별도 높이
        # 보정 없이 세 카드가 나란히 맞는다.
        ow, ol = parts.card_widget("응답 결과 구성")
        self.outcome_chart = RankedBarChart()
        ol.addWidget(self.outcome_chart)
        ow.setFixedHeight(ow.sizeHint().height())
        row2.addWidget(ow, 1)

        bl.addLayout(row2)

        # ── Row 3: 시계열 추이(시간대별/일자별) — 둘 다 GroupedBarChart로
        # 같은 시각 언어를 공유해 시간 단위 비교가 한눈에 되도록 나란히 배치 ──
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        # Hourly trend sparkline — card_widget()은 우측에 위젯을 얹는 기능이
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

        # 최소 180 이상은 확보하되 Fixed가 아니라 growable로 둬서, 남는 여유
        # 공간을 이 두 차트가 흡수해 하단에 빈 공백이 남지 않게 한다
        # (팝업용 popup_chart는 별개 인스턴스라 영향 없음)
        self.trend_chart = GroupedBarChart()
        self.trend_chart.setMinimumHeight(180)
        ll.addWidget(self.trend_chart)
        row3.addWidget(lw, 1)

        dw, dl = parts.card_widget("일자별 수집 추세 (최근 14일)")
        self.daily_chart = GroupedBarChart()
        self.daily_chart.setMinimumHeight(180)
        dl.addWidget(self.daily_chart)
        row3.addWidget(dw, 1)

        bl.addLayout(row3)


    def _build_detail_rows(self, bl):
        """URL/호스트/작업/세션 단위로 쪼개 보는 집계·이력 표."""

        # ── Row 4: 반복 실패 URL + 호스트별 현황 ──────
        row4 = QHBoxLayout()
        row4.setSpacing(10)

        fail_card_w, self.failed_url_table, self.failed_url_badge = _build_table_card(
            self, "반복 실패 URL", ["URL", "Failures", "Last Status", "Last Seen"],
            FAILED_URL_TABLE_ROWS)
        row4.addWidget(fail_card_w, 1)

        host_card_w, self.host_table, self.host_badge = _build_table_card(
            self, "호스트별 현황", ["Host", "Requests", "Success Rate", "Avg Response"],
            HOST_TABLE_ROWS)
        row4.addWidget(host_card_w, 1)

        bl.addLayout(row4)

        # ── Row 5: 작업별 성능 비교 ──────
        job_card_w, self.job_table, self.job_badge = _build_table_card(
            self, "작업별 성능 비교",
            ["Title", "Sessions", "Total Items", "Success Rate", "Avg Response", "Throughput"],
            JOB_TABLE_ROWS)
        bl.addWidget(job_card_w)

        # ── Row 6: Session history table ──────────
        session_card_w, self.session_table, self.session_badge = _build_table_card(
            self, "세션 이력",
            ["NO", "Title", "URL", "Total Items", "Success", "Errors", "Avg Response", "Duration",
             "Start Time", "End Time", "Task Name", "Result"],
            SESSION_TABLE_ROWS)
        bl.addWidget(session_card_w)

        # 카드 4개가 실제 행 수만큼만 높이를 차지하도록 바꿨으므로(_fit_table_height),
        # 창이 더 클 때 남는 세로 공간이 카드마다 나눠져 늘어나지 않고 맨 아래로
        # 모이게 stretch를 둔다.
        bl.addStretch()

    def _fit_table_height(self, table: EqualSpacingTable, row_count: int) -> None:
        """표 높이를 실제 행 수에 맞춘다 — _build_table_card()가 표에 저장해둔
        max_visible_rows 상한까지는 행 수만큼만 차지해 빈 공백을 없애고, 상한을
        넘으면 지금처럼 내부 스크롤로 넘어간다. trigger/statistics.py가 표를
        채운 뒤 호출한다."""
        max_rows = table.property("max_visible_rows")
        table.set_preferred_height(_table_height_for_rows(row_count, max_rows))

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
        popup_chart.set_data(labels, [("성공", ok_vals, GREEN), ("실패", err_vals, RED)])
        card_l.addWidget(popup_chart)
        lay.addWidget(card_w)

        dlg.show()

