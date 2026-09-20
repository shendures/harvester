# layout/statistics.py
# 통계 분석 화면 — 본문 위젯(StatisticsPanel)과 이를 감싼 페이지(StatisticsPage).

from datetime import datetime

from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QMenu, QTableWidgetItem
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor

from trigger import StatisticsPageTriggers
from trigger.statistics import (
    TREND_HOURLY, TREND_PERIODS, TREND_MODE_RECENT, TREND_MODE_CALENDAR,
    TREND_ALL_TIME_CAPTIONS, DAYS_IN_MONTH_MAX, SPEED_FAST_MAX, SPEED_NORMAL_MAX, SPEED_SLOW_MAX,
    STATUS_CODE_MEANINGS, speed_secs, trend_window, diagnose, diagnosis_tooltip, Diagnosis,
    session_request_rows, REQUEST_RESULTS, REQUEST_RESULT_MISSED,
)
from style import EqualSpacingTable, Divider, CollapsibleSection, _load_svg_icon
from .common import (
    parts, theme, build_scroll_body, build_stat_summary_card, build_reset_button, build_popup_dialog,
    ACCENT_LIGHT, GREEN, BLUE, PURPLE, RED, AMBER, TEXT_PRIMARY, TEXT_SECONDARY, BG_SECONDARY, BORDER,
)
from .charts import RankedBarChart, GroupedBarChart

TABLE_ROW_H = 30
TABLE_HEADER_H = 32          # EqualSpacingTable 헤더 높이 근사치
SESSION_TABLE_ROWS = 10      # 세션 이력 표의 고정 표시 행 수 — 넘치면 표 내부 스크롤
REQUEST_TABLE_HEADERS = ["NO", "URL", "Body", "Method", "Status", "Response", "Requested At", "Result"]
SESSION_TABLE_HEADERS = [
    "NO", "Title", "URL", "Total Items", "Success", "Errors", "Avg Response", "Duration",
    "Start Time", "End Time", "Task Name", "Result",
]

TREND_CHART_MIN_H = 280     # 카드가 늘어날 수 있도록 하한만 둔다
HEADER_ICON_SIZE = 14        # 수집량 추이 카드 헤더의 아이콘 버튼 — 아이콘 한 변(px)
HEADER_ICON_BTN_SIZE = (30, 20)

DIAG_BANNER_MARGINS = (14, 10, 14, 10)   # 진단 배너 안쪽 여백(좌·상·우·하)
DIAG_BANNER_SPACING = 12
DIAG_ACCENT_WIDTH = 4                    # 배너 왼쪽 상태 색 강조선 두께(px)
TREND_LABEL_SAMPLE = "00-00"  # 월별(31칸) 구간 라벨 표본 — trigger/statistics.py _daily_counts의 %m-%d 형식

DIAG_LEVEL_FONT_PX = 14
DIAG_DETAIL_FONT_PX = 13

# 지표·차트 카드 툴팁 — 스크래핑을 모르는 사용자가 용어와 숫자 읽는 법을 알 수 있게
# 쉬운 말로 적는다. KPI 튜플의 순서는 build_stat_summary_card()에 넘기는 spec 순서와 같다.
CARD_HELP_HINT = "\n각 숫자에 마우스를 올리면 자세한 설명이 나옵니다."
REQUEST_CARD_HELP = (
    "사이트에 요청을 보내고 응답을 받는 과정의 통계입니다.\n"
    "페이지가 열렸는지, 얼마나 빨랐는지, 연결이 끊겼는지를 봅니다." + CARD_HELP_HINT
)
PROCESS_CARD_HELP = (
    "응답을 받은 뒤 페이지에서 데이터를 꺼내는 과정의 결과입니다.\n"
    "꺼낸 데이터가 얼마나 빠짐없이 채워졌는지, 페이지마다 몇 건씩 나오는지를 봅니다." + CARD_HELP_HINT
)
DATA_CARD_HELP = (
    "수집한 데이터의 양과 데이터를 못 가져온 페이지 현황입니다.\n"
    "응답 결과 구성 카드와 겹치는 숫자를 상세하게 모아 둔 카드입니다." + CARD_HELP_HINT
)
DETAIL_CARD_HELP = "수집 속도와 요청 처리 현황을 보는 보조 지표입니다." + CARD_HELP_HINT

REQUEST_KPI_TIPS = (
    "초기화 이후 사이트에 요청해서 응답을 받은 페이지 수입니다. (누적)",
    "받은 응답 중 사이트가 정상적으로 답한(200) 비율입니다.\n"
    "페이지가 열렸다는 뜻일 뿐, 데이터를 가져왔는지는\n'응답 결과 구성'의 '정상 수집'에서 확인하세요.",
    "요청을 보내고 페이지가 도착하기까지 걸린 평균 시간입니다.\n길수록 사이트가 느리거나 혼잡하다는 뜻입니다.",
    "사이트에 아예 연결하지 못한 횟수입니다.\n인터넷 연결, 프록시 설정, 사이트 점검 여부를 확인하세요.",
)
PROCESS_KPI_TIPS = (
    "꺼낸 모든 항목 칸 중 값이 채워진 칸의 비율입니다.\n"
    "낮으면 추출 규칙이 일부 항목을 못 찾고 있다는 신호이니 수집 설정을 점검하세요.\n"
    "이 지표를 기록하기 시작한 이후 수집분부터 집계되며, 이전 기록만 있으면 '—'로 표시됩니다.",
    "꺼낸 데이터(행) 중 모든 항목이 채워진 행의 비율입니다.\n"
    "필드 채움률이 높아도 이 값이 낮으면 항목이 여러 행에 흩어져 비어 있는 것입니다.",
    "데이터를 가져온 페이지 1개에서 나온 건수의 중앙값입니다(평균보다 튀는 값에 덜 흔들립니다).\n"
    "페이지마다 비슷하게 나와야 정상이며, 평소보다 크게 줄면 사이트 구조가 바뀐 것일 수 있습니다.",
    "데이터를 가져온 페이지 중 가장 적게 나온 건수와 가장 많이 나온 건수입니다.\n"
    "범위가 지나치게 넓으면 일부 페이지에서만 추출이 잘 안 되고 있을 수 있습니다.",
)
DATA_KPI_TIPS = (
    "페이지에서 실제로 가져온 데이터(행)의 총 건수입니다.\n"
    "건수 기록을 시작한 이후 수집분부터 집계되며,\n이전 기록만 있으면 '—'로 표시됩니다.",
    "받은 페이지 중 실제로 데이터를 가져온 페이지의 비율입니다.\n"
    "위 '응답 결과 구성'의 '정상 수집'과 같은 기준입니다.",
    "데이터를 가져온 페이지 1개당 평균 수집 건수입니다.",
    "앞 숫자: 빈 응답 (페이지는 열렸지만 찾을 데이터가 없음)\n"
    "뒤 숫자: 추출 오류 (데이터를 꺼내는 규칙 자체가 실패)\n"
    "둘 다 수집 설정을 점검해야 하는 신호입니다.",
)
DETAIL_KPI_TIPS = (
    "1초에 평균 몇 페이지를 처리했는지입니다.",
    "보내기로 한 요청 중 응답을 받은 비율입니다.",
    "받은 응답 중 요청 목록과 맞지 않아 버려진 비율입니다.",
)
STATUS_MEANINGS_PER_LINE = 3


def _status_meaning_lines() -> str:
    """상태 코드 뜻 표를 툴팁 폭이 과도해지지 않게 줄마다 몇 개씩 끊어 적는다."""
    items = [f"{code} {meaning}" for code, meaning in STATUS_CODE_MEANINGS.items()]
    return "\n".join(
        " · ".join(items[i:i + STATUS_MEANINGS_PER_LINE])
        for i in range(0, len(items), STATUS_MEANINGS_PER_LINE))


STATUS_CHART_TIP = (
    "사이트가 응답과 함께 보내는 결과 번호(상태 코드)별 개수입니다.\n"
    + _status_meaning_lines() + "\n"
    "자주 보는 코드는 0건이어도 항상 표시됩니다.\n"
    "표에 없는 코드는 '기타'로 합쳐 표시하며, 기타 막대에 마우스를 올리면 세부 코드를 볼 수 있습니다.\n"
    "연결에 실패한 응답은 번호가 없어 여기에 없고, '응답 결과 구성'에서 확인할 수 있습니다."
)
SPEED_CHART_TIP = (
    f"응답이 도착하기까지 걸린 시간을 네 구간으로 나눈 것입니다.\n"
    f"빠름 {speed_secs(SPEED_FAST_MAX)}초 미만 · 보통 {speed_secs(SPEED_FAST_MAX)}~{speed_secs(SPEED_NORMAL_MAX)}초 · "
    f"느림 {speed_secs(SPEED_NORMAL_MAX)}~{speed_secs(SPEED_SLOW_MAX)}초 · 매우 느림 {speed_secs(SPEED_SLOW_MAX)}초 이상\n"
    "느린 쪽에 몰리면 사이트가 혼잡하거나 수집 간격·동시 요청 설정을 점검할 때입니다.\n"
    "평균값은 위 '요청·응답' 카드의 '평균 응답'에서 볼 수 있습니다."
)
OUTCOME_CHART_TIP = (
    "받은 응답을 4가지로 나눈 결과입니다.\n"
    "정상 수집: 실제로 데이터를 가져옴\n"
    "빈 응답: 페이지는 열렸지만 데이터 없음\n"
    "HTTP 오류: 사이트가 오류로 응답함\n"
    "연결 실패: 사이트에 연결하지 못함"
)


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


def _apply_tooltips(cards, tips) -> None:
    """KPI 카드마다 같은 순서의 툴팁 문구를 붙인다 — 개수가 다르면 어느 카드에
    엉뚱한 설명이 붙지 않도록 즉시 오류를 낸다."""
    for card, tip in zip(cards, tips, strict=True):
        card.setToolTip(tip)


class StatisticsPanel(QWidget, StatisticsPageTriggers):
    """통계 본문(KPI·차트·표 카드)과 자동 갱신을 함께 가진 자기완결 위젯 —
    어떤 레이아웃에든 addWidget만 하면 표시·갱신된다."""

    def __init__(self):
        super().__init__()
        self._reset_session_counters()
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
        """통계 본문 — KPI 카드, 응답 카드 3종, 수집량 추이, 세션 이력, 접이식 상세 정보를
        한 화면에 쌓는다."""
        body_widget = QWidget()
        bl = build_scroll_body(body_widget)

        # 맨 위 행: 수집 상태 진단 배너 + 초기화 버튼(우측) — 스크롤하면 함께 올라간다
        self.reset_btn = build_reset_button(
            parts, self,
            title="통계 초기화 확인",
            text="<b>누적된 통계 분석 데이터를 초기화하시겠습니까?</b>",
            informative_text="URL 응답 이력과 세션 이력이 모두 삭제되며, 되돌릴 수 없습니다.",
            on_confirmed=self._on_reset_clicked,
        )
        reset_row = QHBoxLayout()
        reset_row.setSpacing(10)
        reset_row.addWidget(self._build_diagnosis_banner(), 1)
        reset_row.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        bl.addLayout(reset_row)

        # ── 세션 통계: 현재 수집 세션의 실시간 집계 (워커 new_row로 갱신) ──
        live_card_w, live_cards = build_stat_summary_card(
            parts, "세션 통계",
            [("요청 완료", "0"), ("오류", "0", RED), ("총 수집 항목", "0", ACCENT_LIGHT), ("평균 응답", "—", GREEN)],
        )
        self.live_completed, self.live_errors, self.live_items, self.live_avg_latency = live_cards
        live_card_w.setFixedHeight(live_card_w.sizeHint().height())
        bl.addWidget(live_card_w)

        # ── Row 1: 요청·응답(좌) / 수집 데이터(우) KPI 카드를 5:5로 배치 ──
        # 두 카드 모두 setFixedHeight(sizeHint)로 고정하는 이유는 row1에는 다른
        # 두 행(Row2/Row3)만큼 세로 공간이 필요 없는데도, bl에 addStretch()가
        # 없어 남는 공간이 형제 행에 함께 배분되면 카드 안에 빈 공백만 늘어나기
        # 때문이다.
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        req_card_w, req_cards = build_stat_summary_card(
            parts, "요청·응답",
            [("확인한 페이지 수", "0"), ("응답 성공률", "0%", GREEN), ("평균 응답", "—", BLUE), ("연결 실패", "0", RED)],
            help_text=REQUEST_CARD_HELP,
        )
        self.kpi_total, self.kpi_resp_rate, self.kpi_avg_t, self.kpi_conn_fail = req_cards
        _apply_tooltips(req_cards, REQUEST_KPI_TIPS)
        req_card_w.setFixedHeight(req_card_w.sizeHint().height())
        row1.addWidget(req_card_w, 1)

        process_card_w, process_cards = build_stat_summary_card(
            parts, "데이터 처리",
            [("필드 채움률", "—", GREEN), ("완전한 행 비율", "—", BLUE),
             ("페이지당 중앙값", "—", ACCENT_LIGHT), ("수집량 범위", "—", PURPLE)],
            help_text=PROCESS_CARD_HELP,
        )
        self.kpi_fill_rate, self.kpi_complete_rate, self.kpi_page_median, self.kpi_item_range = process_cards
        _apply_tooltips(process_cards, PROCESS_KPI_TIPS)
        process_card_w.setFixedHeight(process_card_w.sizeHint().height())
        row1.addWidget(process_card_w, 1)

        bl.addLayout(row1)

        # ── Row 2: 응답 관련 카드 3종을 한 줄에 ──────
        # 세 카드 모두 기본 고정 높이 차트라 래퍼를 sizeHint에 고정하면 높이가 맞는다
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        sw, sl = parts.card_widget("상태 코드 분포", help_text=STATUS_CHART_TIP)
        self.status_chart = RankedBarChart(keep_order=True)
        sl.addWidget(self.status_chart)
        sw.setFixedHeight(sw.sizeHint().height())
        row2.addWidget(sw, 1)

        # 상태 코드가 못 가르는 축 — 200 응답이라도 추출 0건이면 쓸 수 없는
        # 응답이므로 "빈 응답"으로 따로 세어, 상태 코드 뒤에 가려진 수집 실패를
        # 드러낸다.
        ow, ol = parts.card_widget("응답 결과 구성", help_text=OUTCOME_CHART_TIP)
        self.outcome_chart = RankedBarChart()
        ol.addWidget(self.outcome_chart)
        ow.setFixedHeight(ow.sizeHint().height())
        row2.addWidget(ow, 1)

        # 빠름→매우 느림 순서 자체가 의미라 값 정렬을 끈다(keep_order)
        pw, pl = parts.card_widget("응답 속도 구간", help_text=SPEED_CHART_TIP)
        self.speed_chart = RankedBarChart(keep_order=True)
        pl.addWidget(self.speed_chart)
        pw.setFixedHeight(pw.sizeHint().height())
        row2.addWidget(pw, 1)

        bl.addLayout(row2)

        # ── Row 3: 수집량 시계열 — 기간 필터 하나로 시/일 배율을 갈아끼운다 ──
        # stretch 1: 세션 이력·Row2는 내용만큼만 차지하므로 남는 세로 공간은 추이 카드가 흡수한다
        bl.addWidget(self._build_trend_card(), 1)

        # ── Row 4: Session history table ──────────
        bl.addWidget(self._build_session_card())

        # ── 상세 정보(접이식): 보조 지표 ──────
        bl.addWidget(self._build_detail_section())

        return body_widget

    def _build_detail_section(self) -> QWidget:
        """접이식 "상세 정보" 영역 — 수집 데이터 요약과 수집 속도·요청 처리 현황을 보는
        보조 지표 카드를 담는다. 기본은 접힌 상태이고, 숨겨진 동안에도 값은 3초 타이머로 계속 갱신된다."""
        section = CollapsibleSection("상세 정보")

        data_card_w, data_cards = build_stat_summary_card(
            parts, "수집 데이터 요약",
            [("수집한 데이터", "—", ACCENT_LIGHT), ("데이터 수집 성공률", "0%", GREEN),
             ("페이지당 평균", "—", BLUE), ("빈 응답 / 추출 오류", "0 / 0", AMBER)],
            help_text=DATA_CARD_HELP,
        )
        self.kpi_items, self.kpi_data_rate, self.kpi_items_per_page, self.kpi_empty_pages = data_cards
        _apply_tooltips(data_cards, DATA_KPI_TIPS)
        section.body_layout.addWidget(data_card_w)

        detail_card_w, detail_cards = build_stat_summary_card(
            parts, "상세 지표",
            [("처리량", "—", BLUE), ("요청 대비 응답률", "—", GREEN), ("스킵률", "—", AMBER)],
            help_text=DETAIL_CARD_HELP,
        )
        self.kpi_throughput, self.kpi_achieve, self.kpi_skip = detail_cards
        _apply_tooltips(detail_cards, DETAIL_KPI_TIPS)
        section.body_layout.addWidget(detail_card_w)
        return section

    def _build_diagnosis_banner(self) -> QWidget:
        """수집 상태(정상/주의/문제/대기)와 원인·조치 문장을 보여주는 배너를 만든다.
        판정은 trigger/statistics.py의 diagnose()가 하고, 이 위젯은 결과를 그리기만
        한다(_update_diagnosis). 판정 기준은 배너 툴팁으로 안내한다."""
        self.diagnosis_banner = QFrame()
        self.diagnosis_banner.setObjectName("diagnosisBanner")
        self.diagnosis_banner.setToolTip(diagnosis_tooltip())

        lay = QHBoxLayout(self.diagnosis_banner)
        lay.setContentsMargins(*DIAG_BANNER_MARGINS)
        lay.setSpacing(DIAG_BANNER_SPACING)

        self.diagnosis_level_lbl = QLabel()
        lay.addWidget(self.diagnosis_level_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # 문장이 길어지면 잘리지 않고 줄바꿈되도록 한다
        self.diagnosis_detail_lbl = QLabel()
        self.diagnosis_detail_lbl.setWordWrap(True)
        lay.addWidget(self.diagnosis_detail_lbl, 1, Qt.AlignmentFlag.AlignVCenter)

        self._update_diagnosis(diagnose(0, {}))
        return self.diagnosis_banner

    def _update_diagnosis(self, diagnosis: Diagnosis) -> None:
        """진단 결과를 배너에 반영한다 — 상태 색은 강조선·상태 라벨에 쓰고, 색만으로
        전달하지 않도록 상태 이름을 글자로 함께 보여준다(trigger/statistics.py의
        _refresh_summary가 호출)."""
        self.diagnosis_banner.setStyleSheet(
            f"QFrame#diagnosisBanner {{ background:{BG_SECONDARY}; border:1px solid {BORDER};"
            f" border-left:{DIAG_ACCENT_WIDTH}px solid {diagnosis.color}; border-radius:6px; }}")
        self.diagnosis_level_lbl.setText(f"● {diagnosis.level}")
        self.diagnosis_level_lbl.setStyleSheet(
            f"color:{diagnosis.color}; font-size:{DIAG_LEVEL_FONT_PX}px; font-weight:bold;"
            " background:transparent; border:none;")
        self.diagnosis_detail_lbl.setText(diagnosis.detail)
        self.diagnosis_detail_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:{DIAG_DETAIL_FONT_PX}px;"
            " background:transparent; border:none;")

    def _build_session_card(self) -> QWidget:
        """제목 줄에 카운트 배지를 얹은 세션 이력 카드를 만든다. 제목 줄을 직접
        구성하는 건 card_widget()이 제목 옆에 위젯을 얹지 못하기 때문이다. 표 높이는
        SESSION_TABLE_ROWS행 높이로 고정해 넘치면 표 내부 스크롤로 넘어간다."""
        card_w, card_l = parts.card_widget("")

        header_row = QHBoxLayout()
        title_lbl = parts.make_label("세션 이력", TEXT_SECONDARY, 12)
        title_lbl.setStyleSheet(title_lbl.styleSheet() + " letter-spacing:1px;")
        title_lbl.setFixedHeight(title_lbl.sizeHint().height())
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        self.session_badge = parts.count_badge("0건", ACCENT_LIGHT)
        self.session_badge.setFixedHeight(self.session_badge.sizeHint().height())
        header_row.addWidget(self.session_badge)
        card_l.addLayout(header_row)
        card_l.addWidget(Divider())

        self.session_table = EqualSpacingTable(
            parent=self, row_height=TABLE_ROW_H, col_padding=10, hscroll_handle=50)
        self.session_table.setColumnCount(len(SESSION_TABLE_HEADERS))
        self.session_table.setHorizontalHeaderLabels(SESSION_TABLE_HEADERS)
        self.session_table.setFixedHeight(TABLE_HEADER_H + SESSION_TABLE_ROWS * TABLE_ROW_H)
        self.session_table.setToolTip("행을 더블클릭하면 요청 URL별 상세를 볼 수 있습니다.")
        self.session_table.cellDoubleClicked.connect(self._open_session_requests)
        card_l.addWidget(self.session_table)
        return card_w

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
        # 월별(최대 31칸)에서도 구간 라벨이 겹치지 않는 폭 — 기간을 바꿔도 카드 폭이
        # 변하지 않고, 창이 좁으면 페이지에 가로 스크롤이 생긴다
        self.trend_chart.setMinimumWidth(
            self.trend_chart.width_for_slots(DAYS_IN_MONTH_MAX, TREND_LABEL_SAMPLE))
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

    # ── 세션 요청 상세 팝업 (요청 1건 = 1행) ──────
    def _open_session_requests(self, row: int, _col: int) -> None:
        """더블클릭한 세션의 요청 URL별 결과를 새 창 표로 보여준다."""
        session = self.session_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        title = f"요청 상세 — {session.get('title') or session.get('job', '')} ({session['started']})"
        dlg, lay = build_popup_dialog(self, title, (1100, 520), (700, 320))

        card_w, card_l = parts.card_widget(title)
        table = EqualSpacingTable(parent=dlg, row_height=TABLE_ROW_H, col_padding=10, hscroll_handle=50)
        table.setColumnCount(len(REQUEST_TABLE_HEADERS))
        table.setHorizontalHeaderLabels(REQUEST_TABLE_HEADERS)
        result_colors = {
            REQUEST_RESULTS["ok"]: GREEN, REQUEST_RESULTS["warn"]: AMBER,
            REQUEST_RESULTS["err"]: RED, REQUEST_RESULT_MISSED: RED,
        }
        for values in session_request_rows(session):
            r = table.rowCount()
            table.insertRow(r)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                is_result_col = col == len(values) - 1
                item.setForeground(QColor(result_colors.get(value, TEXT_PRIMARY) if is_result_col else TEXT_PRIMARY))
                item.setToolTip(value)
                table.setItem(r, col, item)
        card_l.addWidget(table)
        lay.addWidget(card_w)
        dlg.show()

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



class StatisticsPage(QWidget):
    """통계 분석 페이지 — Single/Multi 메인 창이 그대로 공유하는 얇은 껍데기(대응
    클래스 없음). 본문은 StatisticsPanel이 담당하고, 이 클래스는 창 쪽 호출 계약인
    reload()만 위임한다."""

    def __init__(self):
        super().__init__()
        self.panel = StatisticsPanel()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.panel)

    def reload(self):
        self.panel.reload()

    def add_row(self, row: dict):
        self.panel.add_session_row(row)

    def reset_session_stats(self):
        self.panel.reset_session_stats()
