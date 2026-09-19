# layout/statistics.py
# 통계 분석 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from datetime import datetime

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QMenu
from PyQt6.QtCore import QTimer, QSize

from trigger import StatisticsPageTriggers
from trigger.statistics import (
    TREND_HOURLY, TREND_PERIODS, TREND_MODE_RECENT, TREND_MODE_CALENDAR,
    TREND_ALL_TIME_CAPTIONS, trend_window,
)
from style import EqualSpacingTable, Divider, _load_svg_icon
from .common import (
    parts, theme, build_scroll_body, build_stat_summary_card, build_reset_button, build_popup_dialog,
    ACCENT_LIGHT, GREEN, BLUE, PURPLE, RED, AMBER, TEXT_SECONDARY,
)
from .charts import RankedBarChart, HeatStripChart, GroupedBarChart

TABLE_ROW_H = 30
TABLE_HEADER_H = 32          # EqualSpacingTable 헤더 높이 근사치
SESSION_TABLE_ROWS = 15      # 세션 이력 — 실행마다 늘어나는 유일한 표라 넉넉하게
JOB_TABLE_ROWS = 8           # 작업별 성능 비교 — 수집 목록 개수에 고정되는 표라 여유만 확보
HOST_TABLE_ROWS = 8          # 호스트별 현황 — 대체로 수집 목록 개수와 비슷한 수준
FAILED_URL_TABLE_ROWS = 10   # 반복 실패 URL — trigger/statistics.py의 FAILED_URL_TOP_N과
                             # 반드시 같은 값을 유지(캡보다 작거나 남는 여백이 생기지 않도록)

TREND_CHART_MIN_H = 280     # 카드가 늘어날 수 있도록 하한만 둔다
HEADER_ICON_SIZE = 14        # 수집량 추이 카드 헤더의 아이콘 버튼 — 아이콘 한 변(px)
HEADER_ICON_BTN_SIZE = (30, 20)


def _trend_title_text(period: str, range_text: str) -> str:
    """수집량 추이 카드 제목 — 선택한 기간명과 그 범위를 함께 보여준다."""
    return f"{period} 수집량 추이 ( {range_text} )"


def _trend_btn_text(period: str) -> str:
    """기간 필터 버튼 문구 — 기간명에 드롭다운 표식을 덧붙인다."""
    return f"{period}  ▾"


def _other_trend_mode(mode: str) -> str:
    """표시 방식 전환 버튼을 누르면 바뀔 방식(현재의 반대)."""
    return TREND_MODE_CALENDAR if mode == TREND_MODE_RECENT else TREND_MODE_RECENT


def _trend_mode_tooltip(mode: str) -> str:
    """표시 방식 전환 버튼 툴팁 — 아이콘만 있는 버튼이라 현재 방식과 클릭 시
    바뀔 방식을 함께 안내한다."""
    return f"현재: {mode} — 클릭하면 '{_other_trend_mode(mode)}'으로 전환합니다"


def _trend_popout_tooltip(period: str) -> str:
    """전체 보기 버튼 툴팁 — 기간마다 달라지는 접어서 합산하는 방식을 안내한다."""
    return f"전체 이력의 {TREND_ALL_TIME_CAPTIONS[period]} 수집량 추이를 새 창에서 보기"


def _header_icon_btn(icon_name: str, tooltip: str):
    """수집량 추이 카드 헤더용 아이콘 전용 아웃라인 버튼 — 전체 보기(⧉)와 표시 방식
    전환 버튼이 같은 크기·아이콘 크기·색으로 나란히 보이게 한다."""
    btn = parts.outline_btn("")
    btn.setIcon(_load_svg_icon(icon_name, TEXT_SECONDARY, "2", HEADER_ICON_SIZE))
    btn.setIconSize(QSize(HEADER_ICON_SIZE, HEADER_ICON_SIZE))
    btn.setFixedSize(*HEADER_ICON_BTN_SIZE)
    btn.setToolTip(tooltip)
    return btn


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
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_body(), 1)

    def _build_body(self) -> QWidget:
        """통계 본문 — KPI 카드, 분포/추이 차트, 세션 이력·집계 표를 한 화면에 쌓는다."""
        body_widget = QWidget()
        bl = build_scroll_body(body_widget)

        # 초기화 버튼은 본문 맨 위 우측 — 스크롤하면 함께 올라간다
        self.reset_btn = build_reset_button(
            parts, self,
            title="통계 초기화 확인",
            text="<b>누적된 통계 분석 데이터를 초기화하시겠습니까?</b>",
            informative_text="URL 응답 이력과 세션 이력이 모두 삭제되며, 되돌릴 수 없습니다.",
            on_confirmed=self._on_reset_clicked,
        )
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_row.addWidget(self.reset_btn)
        bl.addLayout(reset_row)

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

        # ── Row 3: Session history table ──────────
        session_card_w, self.session_table, self.session_badge = _build_table_card(
            self, "세션 이력",
            ["NO", "Title", "URL", "Total Items", "Success", "Errors", "Avg Response", "Duration",
             "Start Time", "End Time", "Task Name", "Result"],
            SESSION_TABLE_ROWS)
        bl.addWidget(session_card_w)

        # ── Row 4: 수집량 시계열 — 기간 필터 하나로 시/일 배율을 갈아끼운다 ──
        # stretch 1: 세션 이력 카드는 행 수만큼만 차지하므로 남는 세로 공간은 추이 카드가 흡수한다
        bl.addWidget(self._build_trend_card(), 1)

        # ── Row 5: 반복 실패 URL + 호스트별 현황 ──────
        row5 = QHBoxLayout()
        row5.setSpacing(10)

        fail_card_w, self.failed_url_table, self.failed_url_badge = _build_table_card(
            self, "반복 실패 URL", ["URL", "Failures", "Last Status", "Last Seen"],
            FAILED_URL_TABLE_ROWS)
        row5.addWidget(fail_card_w, 1)

        host_card_w, self.host_table, self.host_badge = _build_table_card(
            self, "호스트별 현황", ["Host", "Requests", "Success Rate", "Avg Response"],
            HOST_TABLE_ROWS)
        row5.addWidget(host_card_w, 1)

        bl.addLayout(row5)

        # ── Row 6: 작업별 성능 비교 ──────
        job_card_w, self.job_table, self.job_badge = _build_table_card(
            self, "작업별 성능 비교",
            ["Title", "Sessions", "Total Items", "Success Rate", "Avg Response", "Throughput"],
            JOB_TABLE_ROWS)
        bl.addWidget(job_card_w)

        return body_widget

    def _build_trend_card(self) -> QWidget:
        """기간 필터와 표시 방식 전환 버튼이 달린 수집량 추이 카드를 만든다. 제목
        줄을 직접 구성하는 건 card_widget()이 제목 우측에 위젯을 얹지 못하기
        때문이다(layout/single/monitor.py의 raw_popout_btn과 동일한 이유)."""
        self.trend_period = TREND_HOURLY
        self.trend_mode = TREND_MODE_RECENT
        card_w, card_l = parts.card_widget("")

        header_row = QHBoxLayout()
        initial_range = trend_window(self.trend_period, self.trend_mode, datetime.now()).range_text
        self.trend_title_lbl = parts.make_label(
            _trend_title_text(self.trend_period, initial_range), TEXT_SECONDARY, 12)
        self.trend_title_lbl.setStyleSheet(self.trend_title_lbl.styleSheet() + " letter-spacing:1px;")
        self.trend_title_lbl.setFixedHeight(self.trend_title_lbl.sizeHint().height())
        header_row.addWidget(self.trend_title_lbl)
        header_row.addStretch()

        self.trend_popout_btn = _header_icon_btn(
            "external-link", _trend_popout_tooltip(self.trend_period))
        self.trend_popout_btn.clicked.connect(self._open_trend_popup)
        header_row.addWidget(self.trend_popout_btn)
        header_row.addWidget(self._build_trend_mode_btn())
        header_row.addWidget(self._build_trend_filter_btn())
        card_l.addLayout(header_row)
        card_l.addWidget(Divider())

        # 최소 높이만 확보하고 Fixed로 묶지 않아, 페이지의 남는 세로 공간을
        # 이 차트가 흡수해 하단에 빈 공백이 남지 않게 한다
        # (팝업용 popup_chart는 별개 인스턴스라 영향 없음)
        self.trend_chart = GroupedBarChart()
        self.trend_chart.setMinimumHeight(TREND_CHART_MIN_H)
        card_l.addWidget(self.trend_chart)
        return card_w

    def _build_trend_filter_btn(self):
        """기간 필터 버튼과 선택 메뉴를 만든다. 메뉴 스타일은 프록시 테이블
        컨텍스트 메뉴(style.py의 PROXY_CONTEXT_MENU_QSS)와 같은 값을 쓴다."""
        self.trend_filter_btn = parts.outline_btn(_trend_btn_text(self.trend_period))
        self.trend_filter_btn.setToolTip("수집량 추이를 볼 기간을 선택합니다")
        # 기본 드롭다운 화살표는 테마 색을 따르지 않아, 버튼 문구의 "▾"로 대체한다
        self.trend_filter_btn.setStyleSheet(
            self.trend_filter_btn.styleSheet()
            + " QPushButton::menu-indicator { image:none; width:0; }")

        # 기간명 길이가 달라도 왼쪽 전환 버튼이 밀리지 않도록 폭은 가장 넓은 문구의
        # sizeHint로 고정한다
        widths = []
        for period in TREND_PERIODS:
            self.trend_filter_btn.setText(_trend_btn_text(period))
            widths.append(self.trend_filter_btn.sizeHint().width())
        self.trend_filter_btn.setFixedWidth(max(widths))
        self.trend_filter_btn.setText(_trend_btn_text(self.trend_period))

        menu = QMenu(self.trend_filter_btn)
        menu.setStyleSheet(theme.PROXY_CONTEXT_MENU_QSS)
        for period in TREND_PERIODS:
            menu.addAction(period, lambda checked=False, p=period: self._on_trend_period_changed(p))
        self.trend_filter_btn.setMenu(menu)
        return self.trend_filter_btn

    def _build_trend_mode_btn(self):
        """표시 방식 전환 아이콘 버튼 — 클릭하면 최근 기준 ↔ 현재 일자 기준을
        뒤집는다. 현재 방식은 툴팁과 카드명의 범위 문구로 확인한다."""
        self.trend_mode_btn = _header_icon_btn("calendar-sync", _trend_mode_tooltip(self.trend_mode))
        self.trend_mode_btn.clicked.connect(self._on_trend_mode_clicked)
        return self.trend_mode_btn

    def _on_trend_mode_clicked(self) -> None:
        """표시 방식을 반대로 뒤집고 차트를 즉시 다시 그린다."""
        self.trend_mode = _other_trend_mode(self.trend_mode)
        self.trend_mode_btn.setToolTip(_trend_mode_tooltip(self.trend_mode))
        self._refresh_summary()

    def _on_trend_period_changed(self, period: str) -> None:
        """기간 필터 선택을 반영하고 차트를 즉시 다시 그린다 — 3초 타이머와
        같은 경로(_refresh_summary)를 타므로 카드명 갱신도 그쪽에서 이뤄진다."""
        if period == self.trend_period:
            return
        self.trend_period = period
        self.trend_filter_btn.setText(_trend_btn_text(period))
        self.trend_popout_btn.setToolTip(_trend_popout_tooltip(period))
        self._refresh_summary()

    def _update_trend_title(self, range_text: str) -> None:
        """카드명을 현재 기간명과 범위 문구로 갱신한다(trigger/statistics.py의
        _refresh_trend_chart가 호출)."""
        self.trend_title_lbl.setText(_trend_title_text(self.trend_period, range_text))

    def _fit_table_height(self, table: EqualSpacingTable, row_count: int) -> None:
        """표 높이를 실제 행 수에 맞춘다 — _build_table_card()가 표에 저장해둔
        max_visible_rows 상한까지는 행 수만큼만 차지해 빈 공백을 없애고, 상한을
        넘으면 지금처럼 내부 스크롤로 넘어간다. trigger/statistics.py가 표를
        채운 뒤 호출한다."""
        max_rows = table.property("max_visible_rows")
        table.set_preferred_height(_table_height_for_rows(row_count, max_rows))

    # ── 전체 보기 팝업 (전체 이력을 기간의 한 주기로 접어 합산) ──────
    def _open_trend_popup(self) -> None:
        """선택한 기간의 수집량 추이를 전체 이력 기준(00~24시 / 요일별 / 일자별
        누적)으로 새 창에 보여주는 모달리스 팝업을 연다. 데이터는 열릴 때 한 번만
        계산해서 그린다."""
        trend = self._aggregate_all_time(self.trend_period)
        title = f"{self.trend_period} 수집량 추이 ({trend.caption})"
        dlg, lay = build_popup_dialog(self, title, (1200, 620), (700, 420))

        card_w, card_l = parts.card_widget(title)
        popup_chart = GroupedBarChart()
        popup_chart.set_data(trend.labels, [("성공", trend.ok_vals, GREEN), ("실패", trend.err_vals, RED)])
        card_l.addWidget(popup_chart)
        lay.addWidget(card_w)

        dlg.show()

