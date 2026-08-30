# layout/single/dashboard.py

import customized_settings

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar,
    QScrollArea, QCheckBox, QSpinBox,
)
from PyQt6.QtCore import Qt

from conf import get_spider_mode
from trigger import DashboardPageTriggers
from style import (
    StatCard, Divider, EqualSpacingTable, TagButton,
    BoundNoticeSpinBox, BoundNoticeDoubleSpinBox, apply_render_safety_limits,
)
from ..common import (
    parts,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, ACCENT, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER, RED, GREEN,
)
from .common import ActiveBlueprintMixin


class DashboardPageSingle(QWidget, DashboardPageTriggers, ActiveBlueprintMixin):

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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Config row
        cfg = QHBoxLayout()
        cfg.setSpacing(10)

        # STEP TRACKER
        stw, stl = parts.card_widget("작업 진행 상태")
        step_container = QWidget()
        step_layout = QHBoxLayout(step_container)
        step_layout.setContentsMargins(60, 20, 60, 20)  # 좌우 마진 조정

        steps = ["수집 대기", "수집 세팅", "데이터 수집", "결과물 추출"]

        for i, text in enumerate(steps):
            # 1. 단계 숫자 원형 레이블
            circle = QLabel(str(i + 1))
            circle.setFixedSize(34, 34)  # 원 크기
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
                line.setStyleSheet(f"background: {BORDER}; margin-bottom: 25px;")
                step_layout.addWidget(line, 1)  # 라인이 공간을 채우도록 가중치 1 부여

        stl.addWidget(step_container)
        cfg.addWidget(stw, 1)  # 상태창이 조금 더 넓게 배치 (비율 3)

        self._update_step_ui(0)  # 초기 실행 시 "수집 대기" 상태로 불이 들어오게 설정

        # card 1
        c1w, c1 = parts.card_widget("수집 & 저장 설정")

        # Row 1 — 딜레이 / 스레드
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        r1.addWidget(parts.make_label("Delay(s)", TEXT_SECONDARY, 12))
        self.delay_spin = BoundNoticeDoubleSpinBox()
        self.delay_spin.setRange(0.5, 10.0)
        self.delay_spin.setValue(0.5)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setDecimals(1)  # setDecimals : 소수점 자리 수 self.delay_spin.setSuffix("s")
        self.delay_spin.setToolTip("요청 간 대기 시간 (기본 0.5s)")
        r1.addWidget(self.delay_spin)
        r1.addSpacing(6)
        r1.addWidget(parts.make_label(" Threads", TEXT_SECONDARY, 12))
        self.thread_spin = BoundNoticeSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(4)
        self.thread_spin.setToolTip("병렬 수집 스레드 수")
        r1.addWidget(self.thread_spin)
        r1.addSpacing(6)
        r1.addStretch()
        c1.addLayout(r1)

        # 렌더링(Selenium) 수집은 대시보드/스케줄 UI에서만 Threads/Delay 안전
        # 상한/하한을 강제한다(spirenderer.py는 더 이상 런타임 보정을 하지 않음).
        # 상한/하한을 넘으려는 시도는 상시 문구 대신 QToolTip 말풍선으로만 안내한다.
        if self._get_active_spider_mode() == "html_render":
            apply_render_safety_limits(
                self.thread_spin, self.delay_spin,
                customized_settings.get_render_safety_limits(),
            )

        # Row 2 — 타임 아웃 / 재시도
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(parts.make_label("Timeout(s)", TEXT_SECONDARY, 12))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setValue(10)
        self.timeout_spin.setToolTip("요청 최대 대기 시간")
        r2.addWidget(self.timeout_spin)
        r2.addWidget(parts.make_label("   Retry", TEXT_SECONDARY, 12))
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.retry_spin.setValue(2)
        self.retry_spin.setToolTip("실패 시 재시도 횟수 (기본 2회)")
        r2.addWidget(self.retry_spin)
        r2.addSpacing(6)
        r2.addStretch()
        c1.addLayout(r2)

        # Row 3 — 자동 저장 (수집 완료 시 결과를 자동으로 저장할지 / 무엇을 저장할지)
        c1.addSpacing(6)
        c1.addWidget(Divider())
        c1.addSpacing(6)

        r3 = QHBoxLayout()
        r3.setSpacing(8)
        self.auto_save_chk = QCheckBox("Auto Save")
        self.auto_save_chk.setToolTip("수집 완료 시 선택된 출력 대상(FILE/DB)에 자동 저장")
        self.auto_save_chk.setChecked(True)
        r3.addWidget(self.auto_save_chk)
        r3.addSpacing(6)

        self.auto_src_raw_btn = TagButton("RAW")
        self.auto_src_raw_btn.setChecked(True)   # 기본값: customized_settings.get_output_settings()의 auto_save_source="raw"와 동일
        self.auto_src_ref_btn = TagButton("정제")
        self.auto_src_ref_btn.setToolTip(
            "'② 정제 규칙 설정' 탭에서 마지막으로 설정해 둔 규칙이 그대로 적용됩니다.\n"
            "이번 수집을 위해 규칙을 다시 확인하지 않았다면 의도한 결과가 아닐 수 있습니다."
        )
        r3.addWidget(self.auto_src_raw_btn)
        r3.addWidget(self.auto_src_ref_btn)
        r3.addStretch()
        c1.addLayout(r3)

        self.auto_save_chk.toggled.connect(self._on_auto_save_toggled)
        self.auto_src_raw_btn.clicked.connect(lambda: self._on_auto_save_source_selected(False))
        self.auto_src_ref_btn.clicked.connect(lambda: self._on_auto_save_source_selected(True))
        self._on_auto_save_toggled(self.auto_save_chk.isChecked())

        c1w.setFixedWidth(320)
        cfg.addWidget(c1w, 1)
        bl.addLayout(cfg)

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
        self.mon_row_count_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
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
