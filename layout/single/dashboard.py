# layout/single/dashboard.py

import customized_settings

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar,
)
from PyQt6.QtCore import Qt

from conf import get_spider_mode, DEFAULT_COLLECT_SETTINGS
from trigger import DashboardPageTriggers
from trigger.common import _build_collect_settings_fields
from style import StatCard, EqualSpacingTable, apply_render_safety_limits
from ..common import (
    parts, build_scroll_body,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, ACCENT, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_MUTED, BORDER, RED, GREEN,
)
from .common import ActiveBlueprintMixin, count_badge_qss


class DashboardPageSingle(QWidget, DashboardPageTriggers, ActiveBlueprintMixin):

    # ── 단계 표시기("작업 진행 상태" 카드) 치수 ──────────────────────
    # 이 표시기는 카드 안에서만 쓰이는 전용 위젯이라 다른 화면과 공유하는
    # 여백 규칙이 없다 — 카드 폭 안에서 4단계가 보기 좋게 퍼지도록 튜닝된
    # 값이므로, 매직 넘버로 흩어놓지 않고 이름 붙여 한 곳에서 관리한다.
    _STEP_CIRCLE_SIZE = 34                 # 원형 단계 번호 라벨 지름
    _STEP_ROW_H_MARGIN = 60                # 좌우 여백 — 카드 폭 대비 4단계를 중앙에 모아 배치
    _STEP_ROW_V_MARGIN = 20                # 상하 여백
    _STEP_LINE_V_OFFSET = 25               # 연결선을 원 중심 높이로 끌어올리는 하단 여백
    # (원 34px + 아래 텍스트 라벨 높이만큼 행이 원보다 커서, 연결선을 상단
    # 정렬 그대로 두면 원의 위쪽에 붙어버린다. 원의 시각적 중심에 맞춘 값.)

    def __init__(self):
        super().__init__()
        self.step_circles = []
        self.step_labels = []
        self.step_arrow_groups = []
        self._index = 0
        self._out_mode = None
        self.output_info = customized_settings.get_output_settings()
        self._running = False
        self._session_error_count = 0
        self._session_latency_sum = 0.0
        self._session_latency_count = 0
        self._build()

    def _build(self):

        bl = build_scroll_body(self, spacing=12)
        self._configure_body_margins(bl)

        # Config row
        cfg = QHBoxLayout()
        cfg.setSpacing(10)

        # STEP TRACKER
        stw, stl = parts.card_widget("작업 진행 상태")
        step_container = QWidget()
        step_layout = QHBoxLayout(step_container)
        step_layout.setContentsMargins(
            self._STEP_ROW_H_MARGIN, self._STEP_ROW_V_MARGIN,
            self._STEP_ROW_H_MARGIN, self._STEP_ROW_V_MARGIN,
        )

        steps = ["수집 대기", "수집 세팅", "데이터 수집", "결과물 추출"]

        for i, text in enumerate(steps):
            # 1. 단계 숫자 원형 레이블
            circle = QLabel(str(i + 1))
            circle.setFixedSize(self._STEP_CIRCLE_SIZE, self._STEP_CIRCLE_SIZE)
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 초기 스타일 (대기 상태)
            circle.setStyleSheet(f"""
                        background: {BG_SECONDARY}; border: 2px solid {BORDER}; 
                        border-radius: 14px; color: {TEXT_MUTED}; font-weight: bold;
                    """)
            self.step_circles.append(circle)

            # 2. 단계 텍스트 레이블
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold;")
            self.step_labels.append(lbl)

            # 레이아웃에 추가
            step_unit = QVBoxLayout()
            step_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_unit.addWidget(circle, 0, Qt.AlignmentFlag.AlignCenter)
            step_unit.addWidget(lbl, 0, Qt.AlignmentFlag.AlignCenter)
            step_layout.addLayout(step_unit)

            # 단계 사이 연결 선 (마지막 단계 제외)
            if i < len(steps) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setStyleSheet(f"background: {BORDER}; margin-bottom: {self._STEP_LINE_V_OFFSET}px;")
                step_layout.addWidget(line, 1)  # 라인이 공간을 채우도록 가중치 1 부여

        stl.addWidget(step_container)
        cfg.addWidget(stw, 1)  # 상태창이 조금 더 넓게 배치 (비율 3)

        self._update_step_ui(0)  # 초기 실행 시 "수집 대기" 상태로 불이 들어오게 설정

        # card 1 — "수집 & 저장 설정"(Delay/Threads/Timeout/Retry/Auto Save)
        self._build_collect_settings_card(cfg)

        # "작업 진행 상태"(+단일의 "수집 & 저장 설정") 행을 별도 위젯으로 감싸 둔다 —
        # DashboardPageMulti가 _place_step_card를 오버라이드해 이 위젯을 이 페이지의
        # 스크롤 영역 밖(main_window의 별도 스택)으로 떼어내 배치할 수 있게 하기 위함.
        self.step_card_widget = QWidget()
        self.step_card_widget.setLayout(cfg)
        self._place_step_card(bl)

        # ── 프로그레스 바 (작업 진행 상태 ~ 세션 통계 사이) ──────────
        pb_card = QWidget()
        pb_card.setFixedHeight(41)
        pb_card.setStyleSheet(
            f"background:{BG_SECONDARY}; border-radius:8px; border:1px solid {BORDER};"
        )
        pbl = QHBoxLayout(pb_card)
        pbl.setContentsMargins(14, 0, 14, 0)
        pbl.setSpacing(10)

        self.prog_lbl = parts.make_label("대기 중", TEXT_MUTED, 11)
        pbl.addWidget(self.prog_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedHeight(4)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar{{background:{BG_HOVER};border-radius:2px;border:none;}}
            QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT},stop:1 {ACCENT_LIGHT});border-radius:2px;}}
        """)
        pbl.addWidget(self.prog_bar, 1)

        self.prog_pct = parts.make_label("0%", TEXT_MUTED, 11)
        self.prog_pct.setMinimumWidth(36)
        pbl.addWidget(self.prog_pct)

        bl.addWidget(pb_card)
        stw, stl = parts.card_widget("세션 통계")
        sg = QHBoxLayout()
        sg.setSpacing(10)
        self.s_total = StatCard("요청 완료", "0")
        self.s_err   = StatCard("오류", "0", RED)
        self.s_pages = StatCard("총 수집 항목", "0", ACCENT_LIGHT)
        self.s_speed = StatCard("평균 응답", "—", GREEN)
        for card in [self.s_total, self.s_err, self.s_pages, self.s_speed]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            sg.addWidget(card, 1)
        stl.addLayout(sg)
        bl.addWidget(stw)

        # ── 수집 모니터링 테이블 (MonitorPageSingle에서 이동) ──────────
        mon_tcw, mon_tc = parts.card_widget("수집 모니터링")
        mon_tcw.setMinimumHeight(300)  # 최소 높이를 300으로 제한
        mon_tbl_ctrl = QHBoxLayout()
        mon_tbl_ctrl.addStretch()
        self.mon_row_count_lbl = QLabel("0 rows")
        self.mon_row_count_lbl.setStyleSheet(count_badge_qss(ACCENT_LIGHT))
        mon_tbl_ctrl.addWidget(self.mon_row_count_lbl)
        mon_tbl_ctrl.addSpacing(10)
        mon_exp_csv = parts.outline_btn("내보내기")
        mon_exp_csv.clicked.connect(self._export_monitor_csv)
        mon_tbl_ctrl.addWidget(mon_exp_csv)
        mon_tc.addLayout(mon_tbl_ctrl)

        self.monitor_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.monitor_table.setColumnCount(9)
        self.monitor_table.setHorizontalHeaderLabels(
            ["NO", "URL", "STATUS", "IP_ADDRESS", "USER-AGENT", "COOKIES", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
        mon_tc.addWidget(self.monitor_table)
        bl.addWidget(mon_tcw, 1)

    def _place_step_card(self, bl: QVBoxLayout) -> None:
        """"작업 진행 상태" 행(self.step_card_widget)을 배치한다. 기본은 다른 카드들과
        같은 세로 스택(이 페이지 자체의 스크롤 영역)에 그대로 넣는다(단일 레이아웃).
        DashboardPageMulti는 이 훅을 오버라이드해 아무것도 하지 않는다 — 그 대신
        main_window가 step_card_widget을 "수집 목록" 위쪽의 별도 스택에 직접
        마운트한다(요구사항: 모니터링 페이지 카드 순서에 "수집 목록"을 끼워 넣기 위함)."""
        bl.addWidget(self.step_card_widget)

    def _configure_body_margins(self, bl: QVBoxLayout) -> None:
        """bl(스크롤 영역 내부 콘텐츠)의 여백을 조정하는 훅. 기본은 그대로 둔다(단일
        레이아웃 — 이 페이지가 독립된 화면이라 4면 여백이 모두 필요함). DashboardPageMulti는
        위쪽 여백만 0으로 줄인다 — "수집 목록" 카드와의 경계 여백은 main_window의
        상위 레이아웃 spacing이 대신 공급하므로, 여기서 위쪽까지 14px를 더하면
        카드 사이 간격이 다른 카드 쌍보다 두 배 가까이 벌어진다."""
        pass

    def _build_collect_settings_card(self, cfg: QHBoxLayout) -> None:
        """"수집 & 저장 설정" 카드(Delay/Threads/Timeout/Retry/Auto Save) — 위젯
        구성 자체는 _build_collect_settings_fields()(trigger/common.py)를 재사용한다.
        DashboardPageMulti는 이 훅을 오버라이드해 카드를 만들지 않는다(다중 레이아웃은
        같은 설정을 "⚙" 다이얼로그 쪽으로 옮겼으므로 대시보드에는 필요 없음)."""
        c1w, c1 = parts.card_widget("수집 & 저장 설정")

        content, widgets = _build_collect_settings_fields(
            self._active_blueprint_info().get("collect_settings") or DEFAULT_COLLECT_SETTINGS
        )
        c1.addWidget(content)

        self.delay_spin       = widgets["delay_spin"]
        self.thread_spin      = widgets["thread_spin"]
        self.timeout_spin     = widgets["timeout_spin"]
        self.retry_spin       = widgets["retry_spin"]
        self.auto_save_chk    = widgets["auto_save_chk"]
        self.auto_src_raw_btn = widgets["auto_src_raw_btn"]
        self.auto_src_ref_btn = widgets["auto_src_ref_btn"]

        # 렌더링(Selenium) 수집은 대시보드/스케줄 UI에서만 Threads/Delay 안전
        # 상한/하한을 강제한다(spirenderer.py는 더 이상 런타임 보정을 하지 않음).
        # 상한/하한을 넘으려는 시도는 상시 문구 대신 QToolTip 말풍선으로만 안내한다.
        if self._get_active_spider_mode() == "html_render":
            apply_render_safety_limits(
                self.thread_spin, self.delay_spin,
                customized_settings.get_render_safety_limits(),
            )

        c1w.setFixedWidth(320)
        cfg.addWidget(c1w, 1)

    # 단계 사이 (선)
    def _update_step_ui(self, step_idx):
        """
        현재 인덱스에 해당하는 단계만 주인공으로 만들고,
        나머지는 과거/미래 상관없이 모두 배경으로 보냅니다.
        """
        for i in range(len(self.step_circles)):
            # 현재 활성화된 단계 (Accent Color)
            if i == step_idx:
                circle_style = f"""
                    background: {ACCENT};
                    border: 2px solid {ACCENT_LIGHT};
                    color: white;
                """
                label_style = f"color: {TEXT_PRIMARY}; font-weight: bold;"

            # 그 외 모든 단계 (Muted Color)
            else:
                circle_style = f"""
                    background: {BG_SECONDARY};
                    border: 2px solid {BORDER};
                    color: {TEXT_MUTED};
                """
                label_style = f"color: {TEXT_MUTED}; font-weight: normal;"

            # 스타일 적용
            self.step_circles[i].setStyleSheet(circle_style + "border-radius: 14px; font-weight: bold;")
            self.step_labels[i].setStyleSheet(label_style + "font-size: 11px;")

    def _reset_dashboard(self):
        # 세션 통계 초기화
        self.s_total.update_value(0)
        self.s_err.update_value(0)
        self.s_pages.update_value(0)
        self.s_speed.update_value("—")
        self._session_error_count = 0
        self._session_latency_sum = 0.0
        self._session_latency_count = 0

        # 수집 모니터링 테이블 초기화
        self.monitor_table.setSortingEnabled(False)
        self.monitor_table.setRowCount(0)
        self.monitor_table.setSortingEnabled(True)
        self.mon_row_count_lbl.setText("0 rows")

        # 프로그레스 바 초기화
        self.prog_bar.setValue(0)
        self.prog_pct.setText("0%")
        self.prog_lbl.setText("대기 중")

        self._update_step_ui(0)

    def set_running(self, v: bool):
        """GlobalToolbarSingle 에서 상태를 받아 내부 플래그만 동기화합니다."""
        self._running = v

    def _get_active_spider_mode(self):
        """이 대시보드가 대상으로 하는 블루프린트의 스파이더 모드.
        DashboardPageMulti는 _active_blueprint_info() 훅만 오버라이드해
        이 메서드를 그대로 상속받는다."""
        return get_spider_mode(self._active_blueprint_info())
