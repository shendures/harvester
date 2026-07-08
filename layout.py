import os, re, csv, socket
import utility
from copy import deepcopy
from datetime import datetime, timedelta
from collections import defaultdict
import customized_settings
import db_conn

from conf import DataStore, BlueprintStorage
from trigger import (
    GlobalToolbarTriggers, DashboardPageTriggers, MonitorPageTriggers,
    StatisticsPageTriggers, SchedulerPageTriggers,
    SessionSettingsPageTriggers, AuthManagerPageTriggers,
    TrayManagerTriggers, MainWindowTriggers,
    LogViewerDialog,
)
from style import THEME, NavItem, TagButton, StatCard, Divider, Parts, EqualSpacingTable

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidgetItem, QFrame, QProgressBar,
    QScrollArea, QGridLayout, QStackedWidget,
    QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox,
    QCheckBox, QSizePolicy, QDateEdit, QSystemTrayIcon,
    QDialog, QMenu, QTabWidget
)
from PyQt6.QtCore import ( Qt, QTimer, QPoint, QDate, QObject, pyqtSignal )
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QLinearGradient, QIcon, QAction
)

store = DataStore()
blueprint = BlueprintStorage()  # 수집 정보 클래스
request_info = blueprint.read()  # 수집 정보
theme = THEME()
parts = Parts()

# ── THEME 색상 변수를 모듈 레벨에서 참조할 수 있도록 언패킹 ──────────────
# style.py의 THEME 클래스가 단일 정의 소스(Single Source of Truth)이며,
# 이 변수들은 그 인스턴스 속성을 그대로 바인딩한 것입니다.
# 색상을 변경할 때는 THEME 클래스만 수정하면 됩니다.
BG_PRIMARY    = theme.BG_PRIMARY
BG_SECONDARY  = theme.BG_SECONDARY
BG_HOVER      = theme.BG_HOVER
ACCENT        = theme.ACCENT
ACCENT_LIGHT  = theme.ACCENT_LIGHT
ACCENT_HOVER  = theme.ACCENT_HOVER
TEXT_PRIMARY  = theme.TEXT_PRIMARY
TEXT_SECONDARY= theme.TEXT_SECONDARY
TEXT_MUTED    = theme.TEXT_MUTED
BORDER        = theme.BORDER
BORDER_LIGHT  = theme.BORDER_LIGHT
GREEN         = theme.GREEN
AMBER         = theme.AMBER
RED           = theme.RED
BLUE          = theme.BLUE
PURPLE        = theme.PURPLE


# ══════════════════════════════════════════════════════
#  CLICKABLE RULE ROW  (정제 규칙 탭 — 블록 클릭 체크박스 토글)
# ══════════════════════════════════════════════════════
class ClickableRuleRow(QWidget):
    """
    정제 규칙 탭의 각 규칙 블록 위젯.
    블록 어디를 클릭해도 내부 QCheckBox가 토글됩니다.
    QCheckBox 자체 클릭은 기본 동작을 그대로 사용하고
    블록의 나머지 영역 클릭 시 checkbox.toggle()을 호출합니다.
    """
    def __init__(self, checkbox: QCheckBox, parent=None):
        super().__init__(parent)
        self._cb = checkbox
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        """체크박스 영역이 아닌 곳 클릭 시 체크박스 토글"""
        # 체크박스 자체의 히트 영역이면 기본 이벤트 전파
        cb_rect = self._cb.rect().translated(self._cb.pos())
        if cb_rect.contains(event.pos()):
            super().mousePressEvent(event)
            return
        self._cb.toggle()
        event.accept()


# ══════════════════════════════════════════════════════
#  GLOBAL TOOLBAR  (모든 페이지 공통 상단 툴바)
# ══════════════════════════════════════════════════════
class GlobalToolbar(QWidget, GlobalToolbarTriggers):
    """
    Sidebar 오른쪽 콘텐츠 영역 최상단에 고정 표시되는 공통 툴바.
    - URL 라벨 / URL 입력창 / URL 복사 버튼 / 시작·중지 버튼
    - start_requested : 시작 버튼 클릭 시 emit (request_info dict)
    - stop_requested  : 중지 버튼 클릭 시 emit
    - reset_requested : 수집 시작 직전 UI 초기화 요청 emit
    """
    start_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._start_cancelled = False   # 중지 시 QTimer 예약 콜백을 막는 플래그
        self.step_circles = []
        self.step_labels = []
        # 실제 페이지 인스턴스는 MainWindow._build()에서 set_pages()로 주입됩니다.
        self.dashboard = None
        self.monitor_page = None
        self.session_page = None
        self.auth_page = None
        self.log_manager = None  # MainWindow 생성 후 set_log_manager()로 주입
        self._build()
        self.task = {}

    # ── UI 구성 ───────────────────────────────────────
    def _build(self):
        self.setFixedHeight(49)
        self.setStyleSheet(
            f"background:{BG_SECONDARY}; border-bottom:1px solid {BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # 수집 방식 라벨
        lay.addWidget(parts.make_label(request_info["conditions"]["method"], ACCENT_LIGHT, 12, True))

        # URL 입력창
        self.url_input = QLineEdit(request_info["url"] if request_info else "")
        self.url_input.setCursorPosition(0)
        lay.addWidget(self.url_input, 1)

        # URL 복사 버튼
        self._copy_btn = parts.outline_btn("URL 복사")
        self._copy_btn.clicked.connect(self._copy_url)
        lay.addWidget(self._copy_btn)

        # 시작 / 중지 버튼
        self.run_btn = QPushButton("▶  시작")
        self.run_btn.setFixedWidth(90)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._toggle_run)
        self._style_run_btn(False)
        lay.addWidget(self.run_btn)

    # ── 내부 메서드 ───────────────────────────────────

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
                label_style = f"color: {TEXT_MUTED}; font-weight: normal;"
                circle_style = f"""
                    background: {BG_SECONDARY};
                    border: 2px solid {BORDER};
                    color: {TEXT_MUTED};
                """

            # 스타일 적용
            self.step_circles[i].setStyleSheet(circle_style + "border-radius: 14px; font-weight: bold;")
            self.step_labels[i].setStyleSheet(label_style + "font-size: 11px;")

# ══════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════
class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):

        self.setFixedWidth(190)
        self.setStyleSheet(f"background:{BG_SECONDARY}; border-right:1px solid {BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(2)

        logo = parts.make_label("DataCrawler", ACCENT_LIGHT, 15, True)
        logo.setStyleSheet(logo.styleSheet() + " padding:0 16px 12px;")
        lay.addWidget(logo)
        lay.addWidget(Divider())

        nav_lbl = parts.make_label("NAVIGATOR", TEXT_MUTED, 9)
        nav_lbl.setStyleSheet(nav_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(nav_lbl)

        PAGES = [("⬡", "대시보드"), ("≡", "모니터링"), ("◷", "스케줄러"), ("▲", "통계 분석")]

        # 첫번째 수집 정보 기준으로 SETTINGS 빌드
        SETTINGS = [("◎", "세션 설정"), ("⬡", "인증 관리")] if request_info["auth"] else [("◎", "세션 설정")]

        self._btns = []
        for i, (icon, label) in enumerate(PAGES):
            btn = NavItem(icon, label)
            btn.clicked.connect(lambda _, idx=i: self._on_nav(idx))
            lay.addWidget(btn)
            self._btns.append(btn)

        lay.addSpacing(8)
        lay.addWidget(Divider())

        set_lbl = parts.make_label("SETTINGS", TEXT_MUTED, 9)
        set_lbl.setStyleSheet(set_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(set_lbl)

        for j, (icon, label) in enumerate(SETTINGS):
            btn = NavItem(icon, label)
            page_idx = len(PAGES) + j  # 4, 5
            btn.clicked.connect(lambda _, idx=page_idx: self._on_nav(idx))
            lay.addWidget(btn)
            self._btns.append(btn)

        lay.addStretch()
        lay.addWidget(Divider())

        status_row = QHBoxLayout();
        status_row.setContentsMargins(16, 8, 16, 0)
        dot = parts.make_label("●", GREEN, 10)
        st = parts.make_label("연결됨", GREEN, 12)
        status_row.addWidget(dot)
        status_row.addWidget(st)
        status_row.addStretch()
        lay.addLayout(status_row)

        self._btns[0].setChecked(True)

    def _on_nav(self, idx):
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)
        self.page_changed.emit(idx)

# ══════════════════════════════════════════════════════
#  DASHBOARD PAGE
# ══════════════════════════════════════════════════════
class DashboardPage(QWidget, DashboardPageTriggers):

    def __init__(self):
        super().__init__()
        self.step_circles = []
        self.step_labels = []
        self.step_arrow_groups = []
        self._index = 0
        self._out_mode = None
        self.output_info = customized_settings.get_output_settings()
        self._running = False
        self._all_rows = []
        self._collected_data = []   # 수집된 원본 데이터를 메모리에 보관 (추출 시 사용)
        self._build()

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Config row
        cfg = QHBoxLayout();
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
        c1w, c1 = parts.card_widget("수집 설정")

        # Row 1 — 딜레이 / 스레드
        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(parts.make_label("Delay(s)", TEXT_SECONDARY, 12))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 10.0);
        self.delay_spin.setValue(0.5);
        self.delay_spin.setSingleStep(0.5);
        self.delay_spin.setDecimals(1);  # setDecimals : 소수점 자리 수 self.delay_spin.setSuffix("s")
        self.delay_spin.setToolTip("요청 간 대기 시간 (기본 1.5s)")
        r1.addWidget(self.delay_spin)
        r1.addSpacing(6)
        r1.addWidget(parts.make_label(" Threads", TEXT_SECONDARY, 12))
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16);
        self.thread_spin.setValue(4)
        self.thread_spin.setToolTip("병렬 수집 스레드 수")
        r1.addWidget(self.thread_spin)
        r1.addSpacing(6)
        r1.addStretch();
        c1.addLayout(r1)

        # Row 2 — 타임 아웃 / 재시도
        r2 = QHBoxLayout();
        r2.setSpacing(8)
        r2.addWidget(parts.make_label("Timeout(s)", TEXT_SECONDARY, 12))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60);
        self.timeout_spin.setValue(10)
        self.timeout_spin.setToolTip("요청 최대 대기 시간")
        r2.addWidget(self.timeout_spin)
        r2.addWidget(parts.make_label("   Retry", TEXT_SECONDARY, 12))
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5);
        self.retry_spin.setValue(2)
        self.retry_spin.setToolTip("실패 시 재시도 횟수 (기본 2회)")
        r2.addWidget(self.retry_spin)
        r2.addSpacing(6)
        r2.addStretch();
        c1.addLayout(r2)

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
        sg = QHBoxLayout();
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

        # ── 수집 모니터링 테이블 (MonitorPage에서 이동) ──────────
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
        """GlobalToolbar 에서 상태를 받아 내부 플래그만 동기화합니다."""
        self._running = v

    def _get_result_columns(self):
        """동적 컬럼 목록 — MonitorPage에서도 사용하므로 유지."""
        # [수정] request_info 구조 불완전 시 KeyError 방지
        try:
            items = list(request_info["conditions"]["items"].keys())
            return [c for c in items if c not in ("root", "detail_root", "main_root", "detail")]
        except (KeyError, TypeError):
            return []

# ══════════════════════════════════════════════════════
#  MONITOR PAGE
# ══════════════════════════════════════════════════════
class MonitorPage(QWidget, MonitorPageTriggers):
    def __init__(self):
        super().__init__()
        self._all_rows       = []
        self._collected_data = []   # raw 수집 데이터
        self._refined_data   = []   # 정제 후 데이터
        self._current_task   = {}   # 최근 완료된 수집의 task(seq_no/needs_cleaning 등 포함)
        self._cleaning_warned = False   # 이번 수집에 대해 "규칙 없음" 팝업을 이미 띄웠는지
        self._out_mode       = None
        self.output_info     = customized_settings.get_output_settings()

        # 정제 규칙 기본값 — True: 활성화 / False: 비활성화
        self._refine_rules = {
            "custom_rule":       True,   # 커스텀 규칙(seq_no) 적용
            "remove_duplicate":  True,   # 중복 행 제거
            "remove_null_row":   True,   # 모든 필드 null 행 제거
            "fill_null":         True,   # null → "—" 치환
            "trim_whitespace":   True,   # 문자열 앞뒤 공백 trim
            "drop_columns":      False,  # 선택 필드 제외 (비활성 기본)
            "cast_numeric":      False,  # 숫자 타입 변환 (비활성 기본)
        }
        self._drop_column_names: list[str] = []   # 제외할 컬럼명 목록
        self._fill_null_value: str = ""            # null 치환값 (기본: 빈 값)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── QTabWidget (4탭 구조) ─────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background: {BG_SECONDARY};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 6px 18px;
                font-size: 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {BG_PRIMARY};
                color: {ACCENT_LIGHT};
                border-bottom: 2px solid {ACCENT};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {BG_HOVER};
                color: {TEXT_SECONDARY};
            }}
        """)
        root.addWidget(self.tab_widget)

        # ── 탭 ① Raw 수집 결과 ────────────────────────────────────────
        self._build_raw_tab()
        # ── 탭 ② 정제 규칙 설정 ───────────────────────────────────────
        self._build_refine_rules_tab()
        # ── 탭 ③ 정제 결과 ────────────────────────────────────────────
        self._build_refined_tab()
        # ── 탭 ④ Before / After 비교 ──────────────────────────────────
        self._build_compare_tab()

        # 탭 전환 시 "② 정제 규칙 설정" 진입을 감지해 규칙 미설정 여부를 알림
        self.tab_widget.currentChanged.connect(self._on_monitor_tab_changed)

    # ── 탭 ① Raw 수집 결과 ────────────────────────────────────────────
    def _build_raw_tab(self):
        raw_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        raw_layout = QVBoxLayout(raw_widget)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.addWidget(scroll)

        # 수집 결과 요약 카드 (4칸)
        sum_card_w, sum_card_l = parts.card_widget("수집 결과 요약")
        sg = QHBoxLayout()
        sg.setSpacing(10)
        self.sum_total = StatCard("전체 항목",  "0")
        self.sum_ok    = StatCard("정상 행",     "0", GREEN)
        self.sum_err   = StatCard("null 포함",   "0", AMBER)
        self.sum_warn  = StatCard("중복 행",     "0", RED)
        for card in [self.sum_total, self.sum_ok, self.sum_err, self.sum_warn]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            sg.addWidget(card, 1)
        sum_card_l.addLayout(sg)
        bl.addWidget(sum_card_w)

        # 실시간 수집 결과 테이블
        tcw, tc = parts.card_widget("실시간 수집 결과 (RAW)")
        tbl_ctrl = QHBoxLayout()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 검색")
        self.search_box.setFixedWidth(220)
        self.search_box.textChanged.connect(self._apply_filter)
        tbl_ctrl.addWidget(self.search_box)

        self.count_lbl = QLabel("0 rows")
        self.count_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        tbl_ctrl.addWidget(self.count_lbl)
        tbl_ctrl.addStretch()

        raw_csv_btn = parts.outline_btn("RAW CSV 내보내기")
        raw_csv_btn.clicked.connect(self._export_raw_csv)
        tbl_ctrl.addWidget(raw_csv_btn)
        tc.addLayout(tbl_ctrl)

        # null·중복 안내
        info_lbl = parts.make_label(
            "● 주황색 배경: null 포함 행  ● 빨간색 배경: 중복 행",
            AMBER, 11
        )
        tc.addWidget(info_lbl)

        self.result_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.result_table.setColumnCount(len(self._get_result_columns()) + 1)
        self.result_table.setHorizontalHeaderLabels(["NO"] + self._get_result_columns())
        self.result_table.itemClicked.connect(self._show_detail)
        self.result_table.currentItemChanged.connect(self._on_current_item_changed)
        tc.addWidget(self.result_table)
        bl.addWidget(tcw, 1)

        # 선택 항목 상세
        dw, dl = parts.card_widget("선택 항목 상세")
        self.detail_lbl = parts.make_label("테이블에서 행을 클릭하세요.", TEXT_MUTED, 12)
        dl.addWidget(self.detail_lbl)
        bl.addWidget(dw)

        self.tab_widget.addTab(raw_widget, "① Raw 수집 결과")

    # ── 탭 ② 정제 규칙 설정 ──────────────────────────────────────────
    def _build_refine_rules_tab(self):
        rules_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        rules_layout.addWidget(scroll)

        # ── 기본 정제 규칙 카드 ──────────────────────────────────────
        rw, rl = parts.card_widget("정제 규칙")
        desc = parts.make_label(
            "활성화된 규칙이 위에서 아래 순서로 적용됩니다. 설정 후 [정제 실행] 버튼을 눌러주세요.",
            TEXT_MUTED, 11
        )
        rl.addWidget(desc)
        rl.addSpacing(8)

        rule_defs = [
            ("custom_rule",      "커스텀 정제 규칙 적용",
             "seq_no에 등록된 사용자 정의 규칙(refine/refine_row)을 범용 규칙보다 먼저 적용합니다."),
            ("remove_duplicate", "중복 행 제거",
             "모든 컬럼 값이 동일한 행을 1개만 유지합니다."),
            ("remove_null_row",  "모든 필드 null 행 제거",
             "모든 필드가 null·빈 값인 행만 삭제합니다."),
            ("fill_null",        "null → 지정값 치환",
             "삭제 대상 외 null 값을 지정한 값으로 대체합니다 (기본 '—')."),
            ("trim_whitespace",  "문자열 공백 trim",
             "문자열 필드의 앞뒤 공백 및 줄바꿈을 제거합니다."),
            ("drop_columns",     "제외 필드 지정",
             "추출에 불필요한 컬럼을 선택하여 제외합니다."),
            ("cast_numeric",     "숫자 타입 변환",
             "문자열로 수집된 숫자 필드를 int / float으로 변환합니다."),
        ]

        self._rule_checkboxes: dict[str, QCheckBox] = {}

        for key, title, desc_text in rule_defs:
            cb = QCheckBox()
            cb.setChecked(self._refine_rules[key])
            cb.setFixedSize(18, 18)
            self._rule_checkboxes[key] = cb

            # ── ClickableRuleRow: 블록 어디 클릭해도 체크박스 토글 ──
            row_w = ClickableRuleRow(checkbox=cb)
            row_w.setStyleSheet(
                f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};"
            )
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(12, 10, 12, 10)
            row_l.setSpacing(12)
            row_l.addWidget(cb)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            title_lbl = parts.make_label(title, TEXT_PRIMARY, 12)
            title_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
                f" background:transparent; border:none;"
            )
            desc_lbl = parts.make_label(desc_text, TEXT_MUTED, 11)
            desc_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
            )
            text_col.addWidget(title_lbl)
            text_col.addWidget(desc_lbl)
            row_l.addLayout(text_col, 1)

            if key == "drop_columns":
                self.drop_col_input = QLineEdit()
                self.drop_col_input.setPlaceholderText("제외할 컬럼명 (쉼표 구분, 예: price,brand)")
                self.drop_col_input.setFixedWidth(280)
                self.drop_col_input.setStyleSheet(
                    f"background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; "
                    f"border:1px solid {BORDER}; border-radius:4px; padding:3px 8px; font-size:11px;"
                )
                row_l.addWidget(self.drop_col_input)

            if key == "fill_null":
                self.fill_null_input = QLineEdit()
                self.fill_null_input.setPlaceholderText("비워두면 빈 값으로 채워집니다")
                self.fill_null_input.setFixedWidth(280)
                self.fill_null_input.setStyleSheet(
                    f"background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; "
                    f"border:1px solid {BORDER}; border-radius:4px; padding:3px 8px; font-size:11px;"
                )
                row_l.addWidget(self.fill_null_input)

            rl.addWidget(row_w)

        rl.addSpacing(12)

        run_row = QHBoxLayout()
        run_row.addStretch()
        run_btn = parts.action_btn("정제 실행")
        run_btn.setFixedWidth(120)
        run_btn.clicked.connect(self._run_refine)
        run_row.addWidget(run_btn)
        rl.addLayout(run_row)

        bl.addWidget(rw)
        bl.addStretch()
        self.tab_widget.addTab(rules_widget, "② 정제 규칙 설정")

    # ── 탭 ③ 정제 결과 ────────────────────────────────────────────────
    def _build_refined_tab(self):
        refined_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        ref_layout = QVBoxLayout(refined_widget)
        ref_layout.setContentsMargins(0, 0, 0, 0)
        ref_layout.addWidget(scroll)

        # 정제 결과 요약 카드
        ref_sum_w, ref_sum_l = parts.card_widget("정제 결과 요약")
        rsg = QHBoxLayout()
        rsg.setSpacing(10)
        self.ref_total  = StatCard("정제 후 행 수", "—")
        self.ref_removed = StatCard("제거된 행",    "—", RED)
        self.ref_filled  = StatCard("치환된 값",    "—", AMBER)
        self.ref_rate    = StatCard("정제율",        "—", GREEN)
        for card in [self.ref_total, self.ref_removed, self.ref_filled, self.ref_rate]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            rsg.addWidget(card, 1)
        ref_sum_l.addLayout(rsg)
        bl.addWidget(ref_sum_w)

        # 정제 데이터 테이블
        rtcw, rtc = parts.card_widget("정제 데이터 (REFINED)")
        ref_ctrl = QHBoxLayout()

        self.refined_search_box = QLineEdit()
        self.refined_search_box.setPlaceholderText("🔍 검색")
        self.refined_search_box.setFixedWidth(220)
        self.refined_search_box.textChanged.connect(self._apply_refined_filter)
        ref_ctrl.addWidget(self.refined_search_box)

        self.refined_count_lbl = QLabel("— rows")
        self.refined_count_lbl.setStyleSheet(
            f"color:{GREEN}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        ref_ctrl.addWidget(self.refined_count_lbl)
        ref_ctrl.addStretch()

        exp_btn = parts.action_btn("EXTRACT")
        exp_btn.clicked.connect(self._extract_result_table)
        ref_ctrl.addWidget(exp_btn)

        out_cfg_btn = QPushButton("⚙  추출 설정")
        out_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        out_cfg_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_SECONDARY}; color:{TEXT_SECONDARY};
                border:1px solid {BORDER_LIGHT}; border-radius:6px;
                padding:5px 12px; font-size:12px;
            }}
            QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT_LIGHT}; border-color:{ACCENT_LIGHT}; }}
        """)
        out_cfg_btn.clicked.connect(self._open_output_settings_dialog)
        ref_ctrl.addWidget(out_cfg_btn)
        rtc.addLayout(ref_ctrl)

        self.refined_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.refined_table.setColumnCount(len(self._get_result_columns()) + 1)
        self.refined_table.setHorizontalHeaderLabels(["NO"] + self._get_result_columns())
        self.refined_table.itemClicked.connect(self._show_refined_detail)
        self.refined_table.currentItemChanged.connect(self._on_refined_current_item_changed)
        rtc.addWidget(self.refined_table)
        bl.addWidget(rtcw, 1)

        # 정제 결과 상세
        rdw, rdl = parts.card_widget("선택 항목 상세 (정제 후)")
        self.refined_detail_lbl = parts.make_label("테이블에서 행을 클릭하세요.", TEXT_MUTED, 12)
        rdl.addWidget(self.refined_detail_lbl)
        bl.addWidget(rdw)

        self.tab_widget.addTab(refined_widget, "③ 정제 결과")

    # ── 탭 ④ Before / After 비교 ─────────────────────────────────────
    def _build_compare_tab(self):
        cmp_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        cmp_layout = QVBoxLayout(cmp_widget)
        cmp_layout.setContentsMargins(0, 0, 0, 0)
        cmp_layout.addWidget(scroll)

        # 정제 요약 카드
        cmp_sum_w, cmp_sum_l = parts.card_widget("정제 요약")
        csg = QHBoxLayout()
        csg.setSpacing(10)
        self.cmp_raw_total  = StatCard("Raw 행 수",    "—")
        self.cmp_ref_total  = StatCard("정제 후 행 수", "—", GREEN)
        self.cmp_removed    = StatCard("제거된 행",     "—", RED)
        self.cmp_rate       = StatCard("정제율",        "—", ACCENT_LIGHT)
        for card in [self.cmp_raw_total, self.cmp_ref_total, self.cmp_removed, self.cmp_rate]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            csg.addWidget(card, 1)
        cmp_sum_l.addLayout(csg)
        bl.addWidget(cmp_sum_w)

        # 좌우 비교 테이블 (Raw | Refined)
        side_w = QWidget()
        side_l = QHBoxLayout(side_w)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(10)

        # 좌: Raw
        raw_cmp_w, raw_cmp_l = parts.card_widget("Raw 데이터")
        self.cmp_raw_count = QLabel("— rows")
        self.cmp_raw_count.setStyleSheet(
            f"color:{AMBER}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        raw_cmp_l.addWidget(self.cmp_raw_count)
        self.cmp_raw_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        self.cmp_raw_table.setColumnCount(len(self._get_result_columns()) + 1)
        self.cmp_raw_table.setHorizontalHeaderLabels(["NO"] + self._get_result_columns())
        raw_cmp_l.addWidget(self.cmp_raw_table)
        side_l.addWidget(raw_cmp_w, 1)

        # 우: Refined
        ref_cmp_w, ref_cmp_l = parts.card_widget("정제 데이터")
        self.cmp_ref_count = QLabel("— rows")
        self.cmp_ref_count.setStyleSheet(
            f"color:{GREEN}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        ref_cmp_l.addWidget(self.cmp_ref_count)
        self.cmp_ref_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        self.cmp_ref_table.setColumnCount(len(self._get_result_columns()) + 1)
        self.cmp_ref_table.setHorizontalHeaderLabels(["NO"] + self._get_result_columns())
        ref_cmp_l.addWidget(self.cmp_ref_table)
        side_l.addWidget(ref_cmp_w, 1)

        bl.addWidget(side_w, 1)

        self.tab_widget.addTab(cmp_widget, "④ Before / After 비교")

    # ── 동적 컬럼 목록 ───────────────────────────────────────────────
    def _get_result_columns(self):
        # [수정] request_info 구조 불완전 시 KeyError 방지
        try:
            items = list(request_info["conditions"]["items"].keys())
            return [c for c in items if c not in ("root", "detail_root", "main_root", "detail")]
        except (KeyError, TypeError):
            return []

    # ── 워커 시그널 수신: 실시간 수집 결과 테이블 행 추가 ────────────
    def _reset_monitor_page(self):
        """중지 또는 수집 시작 시 — 모든 탭의 데이터 및 위젯 초기화"""
        # ① Raw 탭
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        self.result_table.setSortingEnabled(True)
        self._all_rows       = []
        self._collected_data = []
        self.count_lbl.setText("0 rows")
        self.sum_total.update_value(0)
        self.sum_ok.update_value(0)
        self.sum_err.update_value(0)
        self.sum_warn.update_value(0)
        self.detail_lbl.setText("테이블에서 행을 클릭하세요.")

        # ② 정제 결과 탭
        self._refined_data = []
        self.refined_table.setSortingEnabled(False)
        self.refined_table.setRowCount(0)
        self.refined_table.setSortingEnabled(True)
        self.refined_count_lbl.setText("— rows")
        self.ref_total.update_value("—")
        self.ref_removed.update_value("—")
        self.ref_filled.update_value("—")
        self.ref_rate.update_value("—")
        self.refined_detail_lbl.setText("테이블에서 행을 클릭하세요.")

        # ③ 비교 탭
        self.cmp_raw_table.setSortingEnabled(False)
        self.cmp_raw_table.setRowCount(0)
        self.cmp_raw_table.setSortingEnabled(True)
        self.cmp_ref_table.setSortingEnabled(False)
        self.cmp_ref_table.setRowCount(0)
        self.cmp_ref_table.setSortingEnabled(True)
        self.cmp_raw_count.setText("— rows")
        self.cmp_ref_count.setText("— rows")
        self.cmp_raw_total.update_value("—")
        self.cmp_ref_total.update_value("—")
        self.cmp_removed.update_value("—")
        self.cmp_rate.update_value("—")

    # ── 추출 관련 메서드 ──────────────────────────────────────────────
    def preprocess(self, task):
        """메모리(_collected_data)에 보관된 수집 데이터를 FILE 또는 DB로 추출"""
        # seq_no/needs_cleaning 등 정제 시 참조할 현재 작업 정보 보관
        self._current_task = task or {}
        self._cleaning_warned = False   # 새 수집 결과 — 팝업 안내 여부 초기화

        if not self._collected_data:
            QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return

        a = task

        data = self._collected_data
        headers = list(data[0].keys())

# ══════════════════════════════════════════════════════
#  MINI CHART WIDGETS
# ══════════════════════════════════════════════════════
class BarChart(QWidget):
    """레이블 + 값 배열을 받아 수직 막대 차트를 그림"""

    def __init__(self, labels=None, values=None, color=ACCENT, parent=None):
        super().__init__(parent)
        self.labels = labels or []
        self.values = values or []
        self.color = QColor(color)
        self.setMinimumHeight(160)

    def set_data(self, labels, values, color=None):
        self.labels = labels
        self.values = values
        if color: self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        if not self.values: return
        p = QPainter(self);
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 28
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        max_v = max(self.values) or 1
        n = len(self.values)
        bar_w = max(4, chart_w // n - 4)

        # grid lines
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pad_t + chart_h - int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y + 4, pad_l - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        # bars + labels
        for i, (lbl, val) in enumerate(zip(self.labels, self.values)):
            x = pad_l + i * (chart_w // n) + (chart_w // n - bar_w) // 2
            bar_h = int(chart_h * val / max_v)
            y = pad_t + chart_h - bar_h

            grad = QLinearGradient(x, y, x, y + bar_h)
            grad.setColorAt(0, self.color.lighter(130))
            grad.setColorAt(1, self.color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 3, 3)

            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, H - pad_b + 4, bar_w + 8, 20,
                       Qt.AlignmentFlag.AlignCenter, str(lbl))

            # value on top
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, max(y - 14, 0), bar_w + 8, 14,
                       Qt.AlignmentFlag.AlignCenter, str(val))

        p.end()

class LineChart(QWidget):
    """시계열 선 그래프"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets = []  # list of (label, values, color)
        self.x_labels = []
        self.setMinimumHeight(160)

    def set_data(self, x_labels, datasets):
        self.x_labels = x_labels
        self.datasets = datasets
        self.update()

    def paintEvent(self, e):
        if not self.datasets: return
        p = QPainter(self);
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt, pb = 40, 10, 14, 30
        cw, ch = W - pl - pr, H - pt - pb

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals) if all_vals else 1

        # grid
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pt + ch - int(ch * i / 4)
            p.drawLine(pl, y, W - pr, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y - 6, pl - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        n = max(len(self.x_labels), 1)
        step = cw / max(n - 1, 1)

        for label, vals, color in self.datasets:
            if not vals: continue
            qc = QColor(color)
            points = []
            for i, v in enumerate(vals):
                x = int(pl + i * step)

                if max_v == 0:
                    y = pt + ch
                else:
                    y = int(pt + ch - ch * v / max_v)
                points.append(QPoint(x, y))

            # line
            p.setPen(QPen(qc, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i + 1])

            # dots
            p.setBrush(QBrush(qc))
            p.setPen(QPen(QColor(BG_PRIMARY), 2))
            for pt2 in points:
                p.drawEllipse(pt2, 4, 4)

        # x labels
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Consolas", 8))
        for i, lbl in enumerate(self.x_labels):
            x = int(pl + i * step)
            p.drawText(x - 20, H - pb + 4, 40, 20, Qt.AlignmentFlag.AlignCenter, str(lbl))

        p.end()


class DonutChart(QWidget):
    """도넛 차트: segments = [(label, value, color)]"""

    def __init__(self, segments=None, parent=None):
        super().__init__(parent)
        self.segments = segments or []
        self.setMinimumSize(140, 140)
        self.setMaximumSize(180, 180)

    def set_data(self, segments):
        self.segments = segments
        self.update()

    def paintEvent(self, e):
        # [수정] 데이터가 없으면 아무것도 그리지 않고 리턴합니다.
        if not self.segments or sum(v for _, v, _ in self.segments) == 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        size = min(W, H) - 16
        x = (W - size) // 2
        y = (H - size) // 2

        total = sum(v for _, v, _ in self.segments)
        start = -90 * 16

        # 1. 파이 조각 그리기
        for label, val, color in self.segments:
            span = int(360 * 16 * val / total)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(QPen(QColor(BG_PRIMARY), 3))
            p.drawPie(x, y, size, size, start, span)
            start += span

        # 2. 가운데 구멍 뚫기 (Donut 형태)
        hole = int(size * 0.52)
        hx = (W - hole) // 2
        hy = (H - hole) // 2
        p.setBrush(QBrush(QColor(BG_SECONDARY)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(hx, hy, hole, hole)

        # 3. 센터 텍스트 (총합) 표시
        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        p.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter, str(total))

        p.end()


# ══════════════════════════════════════════════════════
#  STATISTICS PAGE
# ══════════════════════════════════════════════════════
class StatisticsPage(QWidget, StatisticsPageTriggers):
    def __init__(self):
        super().__init__()
        self._build()
        # auto-refresh every 3 s
        self._timer = QTimer();
        self._timer.timeout.connect(self.reload)
        self._timer.start(3000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Row 1: KPI cards ──────────────────────
        kpi_row = QHBoxLayout();
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
        row2 = QHBoxLayout();
        row2.setSpacing(10)

        # Status donut
        sw, sl = parts.card_widget("상태 코드 분포")
        inner = QHBoxLayout();
        inner.setSpacing(16)
        self.donut = DonutChart()
        inner.addWidget(self.donut)
        legend_w = QWidget();
        legend_w.setStyleSheet("background:transparent;")
        self.legend_lay = QVBoxLayout(legend_w);
        self.legend_lay.setSpacing(6);
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(legend_w);
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
        for r in rows: status_cnt[str(r["status_code"])] += 1
        # ── 수정: COLOR_MAP 키를 str 로 통일하여 단일 응답 시 Gray 오류 해소 ──
        COLOR_MAP = {"200": GREEN, "301": BLUE, "404": AMBER, "429": PURPLE, "500": RED}
        segments = [(k, v, COLOR_MAP.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.donut.set_data(segments)
        # rebuild legend
        for i in reversed(range(self.legend_lay.count())):
            w = self.legend_lay.itemAt(i).widget()
            if w: w.deleteLater()
        for k, v, color in segments:
            row_w = QWidget();
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w);
            rl.setContentsMargins(0, 0, 0, 0);
            rl.setSpacing(6)
            dot = QLabel("●");
            dot.setStyleSheet(f"color:{color}; font-size:12px;")
            txt = parts.make_label(f"{k}  {v}", TEXT_SECONDARY, 11)
            rl.addWidget(dot);
            rl.addWidget(txt);
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
            except:
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


# ══════════════════════════════════════════════════════
#  SCHEDULER PAGE
# ══════════════════════════════════════════════════════
class SchedulerPage(QWidget, SchedulerPageTriggers):

    schedule_run = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        self.app_dir = os.path.join(self.root_path, "CollectorApp")
        self.file_path = os.path.join(self.app_dir, "schedules.json")
        self.default_source = os.path.join(utility.resource_path(), "schedules.json")

        self._timers: dict[int, QTimer] = {}
        self._build()
        self._load_schedules_from_json()   # ← 앱 시작 시 저장된 스케줄 로드
        self._refresh_table()
        self.sched_task = {}
        self.session_page = None  # MainWindow가 실제 SessionSettingsPage 인스턴스를 주입

    # ────────────────────────────────────────────────
    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 본문(bl) 내 상단 버튼 영역 추가 ───────────────
        btn_container = QHBoxLayout()
        btn_container.addStretch()  # 왼쪽 여백을 꽉 채워 버튼을 오른쪽으로 밀어냄
        add_btn = parts.action_btn("+ 작업 추가")
        add_btn.clicked.connect(lambda: self._manage_schedule_task(sched_task="등록"))
        btn_container.addWidget(add_btn)
        bl.addLayout(btn_container)  # bl 레이아웃의 가장 처음에 추가됨
        # ──────────────────────────────────────────────

        # ══ Schedule Table ════════════════════════════
        tw, tl = parts.card_widget("등록된 작업")
        self.sched_table = EqualSpacingTable(parent=self, row_height=36, col_padding=10, hscroll_handle=50)
        self.sched_table.setColumnCount(7)
        self.sched_table.setHorizontalHeaderLabels(
            ["NO", "Task Name", "URL", "Execution Time", "Next Runtime", "Status", "Action"])
        tl.addWidget(self.sched_table)
        bl.addWidget(tw, 1)

        # ── Next Task ─────────────────────────────────
        nrw, nrl = parts.card_widget("Next Task")
        self.next_task_lbl = parts.make_label("등록된 스케줄 없음", TEXT_MUTED, 18, False)
        self.next_task_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nrl.addWidget(self.next_task_lbl)
        bl.addWidget(nrw)

        self._cd_timer = QTimer();
        self._cd_timer.timeout.connect(self._update_countdown)
        self._cd_timer.start(1000)


    # ── 스케줄 작업 등록·수정 통합 저장 ──────────────────

    # ── 스케줄 작업 Dialog (등록 / 수정 통합) ──────────────
    def _manage_schedule_task(self, sched_task=None, idx=None):
        """
        스케줄 등록·수정 다이얼로그를 띄운다.

        Parameters
        ----------
        sched_task : str  '등록' | '수정'
        idx        : int  수정 대상 스케줄 인덱스 (수정 모드에서만 필요)
        """
        # ── 수정 모드 선가드 ──────────────────────────────
        s = None
        if sched_task == "수정":
            if idx is None:
                return
            schedules = store.get_schedules()
            if idx >= len(schedules):
                return
            s = schedules[idx]

            # 수정 모드에서 공통으로 쓰이는 기존 값을 한 번만 파싱
            output_info      = customized_settings.get_output_settings()
            existing_extract = s.get("extract", output_info.get("extract", {}))
            ef               = existing_extract.get("file", {})
            edb              = existing_extract.get("db", {})
            existing_schedule   = s.get("schedule", {})
            existing_exec_str   = existing_schedule.get("exec_str", "")
            existing_interval   = existing_schedule.get("interval", "none")
            existing_run_at     = existing_schedule.get("run_at")
        else:
            output_info = customized_settings.get_output_settings()

        # ── 다이얼로그 기본 설정 ──────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("새 스케줄 등록" if sched_task == "등록" else "스케줄 수정")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 공통 헬퍼 ─────────────────────────────────────
        def sec_label(text):
            lbl = parts.make_label(text.upper(), TEXT_MUTED, 9)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1.5px;")
            return lbl

        def field_row(label, widget, label_w=110):
            row = QHBoxLayout()
            row.setSpacing(8)
            lw = parts.make_label(label, TEXT_SECONDARY, 12)
            lw.setFixedWidth(label_w)
            row.addWidget(lw)
            row.addWidget(widget, 1)
            return row

        def hms_combos():
            h = QComboBox(); h.addItems([f"{t:02d}" for t in range(24)])
            m = QComboBox(); m.addItems([f"{t:02d}" for t in range(60)])
            sc = QComboBox(); sc.addItems([f"{t:02d}" for t in range(60)])
            hms_style = f"""
                QComboBox {{
                    background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER_LIGHT}; border-radius:4px;
                    padding:2px 4px; font-size:12px;
                }}
                QComboBox::drop-down {{ border:none; width:14px; }}
                QComboBox QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
                }}
            """
            for cb in (h, m, sc):
                cb.setFixedWidth(52)
                cb.setStyleSheet(hms_style)
            return h, m, sc

        def time_sep():
            lbl = parts.make_label(":", TEXT_MUTED, 13, True)
            lbl.setFixedWidth(8)
            return lbl

        def iv_lbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 12)

        def _parse_hms_from_exec_str(exec_str: str):
            """exec_str 마지막 HH:MM:SS 파싱 → (h, m, s) int tuple"""
            try:
                part = exec_str.strip().split()[-1]
                h_, m_, s_ = part.split(":")
                return int(h_), int(m_), int(s_)
            except Exception:
                return 0, 0, 0

        # ── 타이틀 ────────────────────────────────────────
        root.addWidget(parts.make_label(
            "새 스케줄 등록" if sched_task == "등록" else "스케줄 수정",
            TEXT_PRIMARY, 14, True
        ))
        root.addSpacing(10)
        root.addWidget(Divider())
        root.addSpacing(14)

        # ── 기본 정보 ─────────────────────────────────────
        root.addWidget(sec_label("기본 정보"))
        root.addSpacing(8)

        if sched_task == "등록":
            sched_name   = QLineEdit("작업명을 입력하세요.")
            callback_url = QLineEdit(request_info["callback_url"])
        else:
            sched_name   = QLineEdit(s.get("task_nm", ""))
            callback_url = QLineEdit(s.get("callback_url", ""))

        callback_url.setCursorPosition(0)
        root.addLayout(field_row("Task Name", sched_name))
        root.addSpacing(6)
        root.addLayout(field_row("Target URL", callback_url))
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── 수집 설정 ─────────────────────────────────────
        root.addWidget(sec_label("수집 설정"))
        root.addSpacing(8)

        sched_delay = QDoubleSpinBox()
        sched_delay.setRange(0.5, 10.0)
        sched_delay.setSingleStep(0.5)
        sched_delay.setDecimals(1)
        sched_delay.setValue(s.get("delay", 0.5) if sched_task == "수정" else 0.5)

        sched_threads = QSpinBox()
        sched_threads.setRange(1, 16)
        sched_threads.setValue(s.get("threads", 4) if sched_task == "수정" else 4)

        sched_timeout = QSpinBox()
        sched_timeout.setRange(1, 60)
        sched_timeout.setValue(s.get("timeout", 10) if sched_task == "수정" else 10)

        sched_retry = QSpinBox()
        sched_retry.setRange(0, 5)
        sched_retry.setValue(s.get("retry", 3) if sched_task == "수정" else 3)

        cs_row = QHBoxLayout()
        cs_row.setSpacing(8)
        for lbl_txt, w in [
            ("Delay(s)", sched_delay), ("Thread", sched_threads),
            ("Timeout(s)", sched_timeout), ("Retry", sched_retry)
        ]:
            cs_row.addWidget(parts.make_label(lbl_txt, TEXT_MUTED, 11))
            cs_row.addWidget(w)
        cs_row.addStretch()
        root.addLayout(cs_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── Save Setting ──────────────────────────────────
        root.addWidget(sec_label("Save Setting"))
        root.addSpacing(8)

        if sched_task == "등록":
            self._sched_out_mode = "FILE" if output_info["extract"]["file"]["enabled"] else "DB"
        else:
            self._sched_out_mode = "FILE" if ef.get("enabled", True) else "DB"

        sched_out_file_btn = TagButton("FILE")
        sched_out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        sched_out_db_btn = TagButton("DB")
        sched_out_db_btn.setToolTip("데이터베이스 서버로 전송")
        sched_out_file_btn.setChecked(self._sched_out_mode == "FILE")
        sched_out_db_btn.setChecked(self._sched_out_mode == "DB")

        sched_out_mode_lbl = parts.make_label(
            "로컬 파일 저장 모드" if self._sched_out_mode == "FILE" else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(parts.make_label("출력 대상", TEXT_MUTED, 11))
        out_row.addSpacing(6)
        out_row.addWidget(sched_out_file_btn)
        out_row.addWidget(sched_out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(sched_out_mode_lbl)
        out_row.addStretch()
        root.addLayout(out_row)
        root.addSpacing(8)

        # ── 추출 설정 스택 (FILE / DB) ────────────────────
        sched_extract_stack = QStackedWidget()
        sched_extract_stack.setObjectName("schedExtractStack")
        sched_extract_stack.setStyleSheet(f"""
            QStackedWidget#schedExtractStack {{
                background:{BG_PRIMARY};
                border:1px solid {BORDER};
                border-radius:6px;
            }}
            QStackedWidget#schedExtractStack > QWidget {{
                background:{BG_PRIMARY};
                border:none;
            }}
        """)
        sched_extract_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # ── PAGE 0 : FILE 설정 ────────────────────────────
        sched_file_page = QWidget()
        sfp = QVBoxLayout(sched_file_page)
        sfp.setContentsMargins(14, 14, 14, 14)
        sfp.setSpacing(10)

        _fp = (ef.get("file_path") or customized_settings.set_desktop_dir()) if sched_task == "수정" \
              else (output_info["extract"]["file"]["file_path"] or customized_settings.set_desktop_dir())

        sched_path_lay = QHBoxLayout()
        sched_path_lay.setSpacing(8)
        sched_path_lay.addWidget(parts.make_label("경로", TEXT_SECONDARY, 12))
        sched_path_edit = QLineEdit(_fp)
        sched_path_edit.setReadOnly(True)
        sched_path_lay.addWidget(sched_path_edit, 1)
        sched_browse_btn = parts.outline_btn("Browse")
        sched_browse_btn.setFixedWidth(72)

        def _sched_browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", sched_path_edit.text() or "")
            if folder:
                sched_path_edit.setText(folder)

        sched_browse_btn.clicked.connect(_sched_browse)
        sched_path_lay.addWidget(sched_browse_btn)
        sfp.addLayout(sched_path_lay)

        _fn = (ef.get("file_name") or "untitled0") if sched_task == "수정" \
              else (output_info["extract"]["file"]["file_name"] or "untitled0")
        sched_fnm_lay = QHBoxLayout()
        sched_fnm_lay.setSpacing(10)
        sched_fnm_lay.addWidget(parts.make_label("파일명", TEXT_SECONDARY, 12))
        sched_file_nm = QLineEdit(_fn)
        sched_fnm_lay.addWidget(sched_file_nm)
        sfp.addLayout(sched_fnm_lay)

        sched_opt_lay = QHBoxLayout()
        sched_opt_lay.setSpacing(10)
        sched_opt_lay.addWidget(parts.make_label("형식", TEXT_SECONDARY, 12))

        sched_fmt_combo = QComboBox()
        sched_fmt_combo.addItems(["CSV", "JSON", "Excel"])
        sched_fmt_combo.setCurrentText(
            ef.get("file_format") or "CSV" if sched_task == "수정"
            else output_info["extract"]["file"]["file_format"]
        )
        sched_opt_lay.addWidget(sched_fmt_combo)
        sched_opt_lay.addSpacing(10)

        sched_enc_widget = QWidget()
        sched_enc_lay = QHBoxLayout(sched_enc_widget)
        sched_enc_lay.setContentsMargins(0, 0, 0, 0)
        sched_enc_lay.setSpacing(10)
        sched_enc_combo = QComboBox()
        sched_enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
        sched_enc_combo.setCurrentText(
            ef.get("file_encoding") or "UTF-8 BOM" if sched_task == "수정"
            else output_info["extract"]["file"]["file_encoding"]
        )
        sched_enc_lay.addWidget(parts.make_label("인코딩", TEXT_SECONDARY, 12))
        sched_enc_lay.addWidget(sched_enc_combo)
        sched_opt_lay.addWidget(sched_enc_widget)
        sched_opt_lay.addSpacing(10)

        sched_delim_widget = QWidget()
        sched_delim_lay = QHBoxLayout(sched_delim_widget)
        sched_delim_lay.setContentsMargins(0, 0, 0, 0)
        sched_delim_lay.setSpacing(10)
        sched_csv_delim = QLineEdit()
        sched_csv_delim.setText(
            ef.get("file_delimiter") or "," if sched_task == "수정"
            else (output_info["extract"]["file"]["file_delimiter"] or ",")
        )
        sched_delim_lay.addWidget(parts.make_label("구분자", TEXT_SECONDARY, 12))
        sched_delim_lay.addWidget(sched_csv_delim)
        sched_opt_lay.addWidget(sched_delim_widget)
        sched_opt_lay.addStretch()
        sfp.addLayout(sched_opt_lay)

        def _sched_on_fmt_changed(fmt_text: str):
            is_csv = (fmt_text == "CSV")
            sched_enc_widget.setVisible(is_csv)
            sched_delim_widget.setVisible(is_csv)

        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed)
        _sched_on_fmt_changed(sched_fmt_combo.currentText())

        sched_extract_stack.addWidget(sched_file_page)  # index 0

        # ── PAGE 1 : DB 설정 ──────────────────────────────
        sched_db_page = QWidget()
        sdp = QVBoxLayout(sched_db_page)
        sdp.setContentsMargins(14, 14, 14, 14)
        sdp.setSpacing(8)

        def _slbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 11)

        def _sinp(txt="", ph=""):
            e = QLineEdit(txt)
            e.setPlaceholderText(ph)
            return e

        DB_PORTS_S = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}
        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        sgrid.setColumnStretch(1, 1)

        _sdb_type = QComboBox()
        _sdb_type.addItems(["MySQL", "PostgreSQL", "MongoDB"])

        if sched_task == "등록":
            _sdb_type.setCurrentText(output_info["extract"]["db"]["db_env"])
            _sdb_host   = _sinp(txt=output_info["extract"]["db"]["host"])
            _sdb_port   = _sinp(txt=output_info["extract"]["db"]["port"])
            _sdb_name   = _sinp(output_info["extract"]["db"]["database"])
            _sdb_schema = _sinp(output_info["extract"]["db"]["schema"])
            _sdb_user   = _sinp(output_info["extract"]["db"]["user"])
            _sdb_pw     = _sinp(output_info["extract"]["db"]["password"])
            _sdb_data   = _sinp(output_info["extract"]["db"]["save_data_nm"])
        else:
            _sdb_type.setCurrentText(edb.get("db_env") or "MySQL")
            _sdb_host   = _sinp(edb.get("host") or "localhost")
            _sdb_port   = _sinp(edb.get("port") or "3306")
            _sdb_name   = _sinp(edb.get("database") or "")
            _sdb_schema = _sinp(edb.get("schema") or "")
            _sdb_user   = _sinp(edb.get("user") or "")
            _sdb_pw     = _sinp(edb.get("password") or "")
            _sdb_data   = _sinp(edb.get("save_data_nm") or "")

        _sdb_pw.setEchoMode(QLineEdit.EchoMode.Password)

        for _row_i, (_label, _widget) in enumerate([
            ("DB Type", _sdb_type), ("HOST", _sdb_host), ("PORT", _sdb_port),
            ("DB Name", _sdb_name), ("SCHEMA", _sdb_schema),
            ("USER", _sdb_user), ("PASSWORD", _sdb_pw), ("DATA Name", _sdb_data),
        ]):
            sgrid.addWidget(_slbl(_label), _row_i, 0)
            sgrid.addWidget(_widget, _row_i, 1)

        _sdb_type.currentTextChanged.connect(lambda t: _sdb_port.setText(DB_PORTS_S.get(t, "")))
        sdp.addLayout(sgrid)

        sched_test_row = QHBoxLayout()
        sched_test_row.setSpacing(10)
        sched_test_btn = parts.outline_btn("TEST CONNECTION")
        sched_test_result_lbl = parts.make_label("", TEXT_MUTED, 11)

        def _show_sched_conn_fail_dialog(reason: str):
            msg = QMessageBox(dlg)
            msg.setWindowTitle("연결 실패")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("<b>DB 연결에 실패했습니다.</b>")
            msg.setInformativeText(reason)
            msg.setStyleSheet(f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:12px; }}
                QPushButton {{
                    background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px;
                }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """)
            msg.exec()

        def _sched_test_conn():
            host = _sdb_host.text().strip() or "localhost"
            try:
                port = int(_sdb_port.text().strip())
            except ValueError:
                sched_test_result_lbl.setText("⚠ 포트 번호가 올바르지 않습니다")
                sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                _show_sched_conn_fail_dialog("포트 번호에 숫자가 아닌 값이 입력되어 있습니다.\n올바른 포트 번호를 입력하세요.")
                return
            sched_test_result_lbl.setText("⏳ 연결 중...")
            sched_test_result_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            sched_test_btn.setEnabled(False)
            QApplication.processEvents()
            info = {
                "db_env":       _sdb_type.currentText(),
                "host":         host,
                "port":         str(port),
                "database":     _sdb_name.text().strip(),
                "schema":       _sdb_schema.text().strip(),
                "user":         _sdb_user.text().strip(),
                "password":     _sdb_pw.text(),
                "save_data_nm": _sdb_data.text().strip(),
            }
            try:
                ok, reason = db_conn._check_db_connect_info(info)
                if ok:
                    sched_test_result_lbl.setText(f"✅ {host}:{port} 연결 성공")
                    sched_test_result_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
                else:
                    sched_test_result_lbl.setText("❌ 연결 실패")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_sched_conn_fail_dialog(reason)
            except ImportError:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        sched_test_result_lbl.setText(f"✅ {host}:{port} 소켓 연결 성공 (DB 드라이버 미설치)")
                        sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                except OSError as e:
                    sched_test_result_lbl.setText("❌ 연결 실패")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_sched_conn_fail_dialog(
                        f"DB 드라이버가 설치되어 있지 않아 소켓 연결을 시도했으나 실패했습니다.\n\n원인: {e}"
                    )
            except Exception as e:
                sched_test_result_lbl.setText("❌ 연결 실패")
                sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                _show_sched_conn_fail_dialog(str(e))
            finally:
                sched_test_btn.setEnabled(True)

        sched_test_btn.clicked.connect(_sched_test_conn)
        sched_test_row.addWidget(sched_test_btn)
        sched_test_row.addWidget(sched_test_result_lbl)
        sched_test_row.addStretch()
        sdp.addLayout(sched_test_row)

        sched_extract_stack.addWidget(sched_db_page)  # index 1
        sched_extract_stack.setCurrentIndex(0 if self._sched_out_mode == "FILE" else 1)

        def _update_sched_dialog_size():
            current_page = sched_extract_stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                sched_extract_stack.setFixedHeight(current_page.layout().sizeHint().height())
            dlg.layout().activate()
            dlg.adjustSize()

        def _sched_on_file_clicked():
            self._sched_out_mode = "FILE"
            sched_out_mode_lbl.setText("로컬 파일 저장 모드")
            sched_out_db_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(0)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        def _sched_on_db_clicked():
            self._sched_out_mode = "DB"
            sched_out_mode_lbl.setText("DB 서버 전송 모드")
            sched_out_file_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(1)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        sched_out_file_btn.clicked.connect(_sched_on_file_clicked)
        sched_out_db_btn.clicked.connect(_sched_on_db_clicked)

        sched_fmt_combo.currentTextChanged.disconnect(_sched_on_fmt_changed)
        def _sched_on_fmt_changed_with_resize(fmt_text: str):
            _sched_on_fmt_changed(fmt_text)
            _update_sched_dialog_size()
        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed_with_resize)

        root.addWidget(sched_extract_stack)
        root.addSpacing(10)

        # ── 저장 방식 콤보 ────────────────────────────────
        sched_save_type = QComboBox()
        sched_save_type.addItems(["선택하세요", "새로 만들기", "덮어쓰기", "추가하기"])
        if sched_task == "수정":
            existing_save_type = existing_schedule.get("schedule_save_type", "선택하세요")
            if existing_save_type in ["새로 만들기", "덮어쓰기", "추가하기"]:
                sched_save_type.setCurrentText(existing_save_type)
        sched_save_type.setFixedWidth(130)
        sched_save_type.setStyleSheet(theme.CB_STYLE)

        sv_row = QHBoxLayout()
        sv_row.setSpacing(8)
        sv_row.addWidget(parts.make_label("저장 방식", TEXT_MUTED, 11))
        sv_row.addWidget(sched_save_type)
        sv_row.addStretch()
        root.addLayout(sv_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        _update_sched_dialog_size()

        # ── Interval ──────────────────────────────────────
        root.addWidget(sec_label("Interval"))
        root.addSpacing(8)

        sched_interval = QComboBox()
        sched_interval.addItems(["선택하세요", "매일", "매주", "매월", "특정 날짜"])
        sched_interval.setFixedWidth(120)
        sched_interval.setStyleSheet(theme.CB_STYLE)

        container_daily   = QWidget()
        container_weekly  = QWidget()
        container_monthly = QWidget()
        container_date    = QWidget()

        # 매일
        self.d_h, self.d_m, self.d_s = hms_combos()
        dl = QHBoxLayout(container_daily)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(6)
        dl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_h, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_m, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_daily.setVisible(False)

        # 매주
        self.w_day = QComboBox()
        self.w_day.addItems(["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"])
        self.w_day.setFixedWidth(76); self.w_day.setStyleSheet(theme.CB_STYLE)
        self.w_h, self.w_m, self.w_s = hms_combos()
        wl = QHBoxLayout(container_weekly)
        wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(6)
        wl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(iv_lbl("매주"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_day, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addSpacing(6)
        wl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_h, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_m, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_weekly.setVisible(False)

        # 매월
        self.m_day = QComboBox()
        self.m_day.addItems([str(d) for d in range(1, 32)])
        self.m_day.setFixedWidth(50); self.m_day.setStyleSheet(theme.CB_STYLE)
        self.m_h, self.m_m, self.m_s = hms_combos()
        ml = QHBoxLayout(container_monthly)
        ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(6)
        ml.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("매월"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_day, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("일"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addSpacing(6)
        ml.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_h, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_m, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_monthly.setVisible(False)

        # 특정 날짜
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFixedWidth(110)
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_LIGHT}; border-radius:4px; padding:4px 6px; font-size:12px;
            }}
            QDateEdit::drop-down {{
                subcontrol-origin:padding; subcontrol-position:center right;
                width:20px; border-left:1px solid {BORDER_LIGHT};
                border-radius:0 4px 4px 0; background:{BG_HOVER};
            }}
            QDateEdit::down-arrow {{
                image:none; width:0; height:0;
                border-left:4px solid transparent; border-right:4px solid transparent;
                border-top:5px solid {TEXT_SECONDARY}; margin:0 4px;
            }}
        """)
        cal = self.date_edit.calendarWidget()
        if cal:
            cal.setMinimumDate(QDate.currentDate())
            cal.setStyleSheet(f"""
                QCalendarWidget QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    selection-background-color:{ACCENT}; selection-color:white;
                }}
                QCalendarWidget QAbstractItemView:disabled {{ color:{TEXT_MUTED}; background:{BG_PRIMARY}; }}
                QCalendarWidget QWidget#qt_calendar_navigationbar {{ background:{BG_PRIMARY}; }}
                QCalendarWidget QToolButton {{
                    background:transparent; color:{TEXT_PRIMARY}; font-size:12px; border:none; padding:4px;
                }}
                QCalendarWidget QToolButton:hover {{ background:{BG_HOVER}; border-radius:4px; }}
                QCalendarWidget QMenu {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}
                QCalendarWidget QSpinBox {{ background:{BG_PRIMARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER_LIGHT}; border-radius:3px; }}
            """)

        self.dat_h, self.dat_m, self.dat_s = hms_combos()
        datl = QHBoxLayout(container_date)
        datl.setContentsMargins(0, 0, 0, 0); datl.setSpacing(6)
        datl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(iv_lbl("날짜"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.date_edit, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addSpacing(6)
        datl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_h, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_m, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_date.setVisible(False)

        # ── 수정 모드: 기존 값을 위젯에 반영 ─────────────
        if sched_task == "수정":
            _iv_map = {"daily": 1, "weekly": 2, "monthly": 3, "date": 4}
            sched_interval.setCurrentIndex(_iv_map.get(existing_interval, 0))

            _ph, _pm, _ps = _parse_hms_from_exec_str(existing_exec_str)
            for cb, val in [
                (self.d_h, _ph), (self.d_m, _pm), (self.d_s, _ps),
                (self.w_h, _ph), (self.w_m, _pm), (self.w_s, _ps),
                (self.m_h, _ph), (self.m_m, _pm), (self.m_s, _ps),
                (self.dat_h, _ph), (self.dat_m, _pm), (self.dat_s, _ps),
            ]:
                cb.setCurrentText(f"{val:02d}")

            if existing_interval == "weekly":
                _DAY_NAMES = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
                for dn in _DAY_NAMES:
                    if dn in existing_exec_str:
                        self.w_day.setCurrentText(dn)
                        break

            if existing_interval == "monthly":
                try:
                    _day_match = re.search(r"매월\s*(\d+)일", existing_exec_str)
                    if _day_match:
                        self.m_day.setCurrentText(_day_match.group(1))
                except Exception:
                    pass

            if existing_interval == "date" and existing_run_at:
                try:
                    ra = existing_run_at if isinstance(existing_run_at, datetime) \
                         else datetime.fromisoformat(str(existing_run_at))
                    self.date_edit.setDate(QDate(ra.year, ra.month, ra.day))
                except Exception:
                    self.date_edit.setDate(QDate.currentDate())
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())

        # ── 주기 선택 행 ──────────────────────────────────
        iv_row = QHBoxLayout()
        iv_row.setSpacing(8); iv_row.setContentsMargins(0, 0, 0, 0)
        iv_row.addWidget(iv_lbl("주기"), 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addWidget(sched_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addStretch()

        detail_wrap = QWidget()
        detail_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detail_lay = QHBoxLayout(detail_wrap)
        detail_lay.setContentsMargins(8, 0, 0, 0); detail_lay.setSpacing(6)
        for c in [container_daily, container_weekly, container_monthly, container_date]:
            detail_lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)
        detail_lay.addStretch()

        def _on_iv_changed(iv_idx):
            container_daily.setVisible(iv_idx == 1)
            container_weekly.setVisible(iv_idx == 2)
            container_monthly.setVisible(iv_idx == 3)
            container_date.setVisible(iv_idx == 4)

        sched_interval.currentIndexChanged.connect(_on_iv_changed)
        _on_iv_changed(sched_interval.currentIndex())

        root.addLayout(iv_row)
        root.setSpacing(4)
        root.addWidget(detail_wrap)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── sched_info_dict 구성 ──────────────────────────
        sched_info_dict = {
            "sched_task":   sched_task,         # _apply_schedule이 모드를 구분하는 키
            "idx":          idx,                 # 수정 시 int, 등록 시 None
            "sched_name":   sched_name,
            "callback_url": callback_url,
            "delay":        sched_delay,
            "threads":      sched_threads,
            "timeout":      sched_timeout,
            "retry":        sched_retry,
            "interval":     sched_interval,
            "d_h": self.d_h,   "d_m": self.d_m,   "d_s": self.d_s,
            "w_day": self.w_day,
            "w_h": self.w_h,   "w_m": self.w_m,   "w_s": self.w_s,
            "m_day": self.m_day,
            "m_h": self.m_h,   "m_m": self.m_m,   "m_s": self.m_s,
            "date_edit":    self.date_edit,
            "dat_h": self.dat_h, "dat_m": self.dat_m, "dat_s": self.dat_s,
            "save_type":    sched_save_type,
            "path_edit":    sched_path_edit,
            "file_nm":      sched_file_nm,
            "fmt_combo":    sched_fmt_combo,
            "enc_combo":    sched_enc_combo,
            "csv_delim":    sched_csv_delim,
            "db_type":      _sdb_type,
            "db_host":      _sdb_host,
            "db_port":      _sdb_port,
            "db_name":      _sdb_name,
            "db_schema":    _sdb_schema,
            "db_user":      _sdb_user,
            "db_pw":        _sdb_pw,
            "db_data":      _sdb_data,
        }

        # ── 하단 버튼 ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn  = parts.action_btn("적용")
        cancel_btn = parts.outline_btn("취소")
        apply_btn.clicked.connect(lambda: self._apply_schedule(dlg=dlg, sched_info_dict=sched_info_dict))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()


    # ── Remaining Time 포맷 헬퍼 ──────────────────
    @staticmethod
    def _format_remaining(run_at: datetime) -> str:
        """
        남은 시간을 단위 자동 변환하여 반환합니다.
          - 24시간 이하     : HH:MM:SS
          - 24시간 초과     : N일 HH:MM:SS
          - 30일 초과       : N개월 N일
        """
        diff = (run_at - datetime.now()).total_seconds()
        if diff <= 0:
            return "대기 중"
        total_s = int(diff)
        total_m = total_s // 60
        total_h = total_m // 60
        total_d = total_h // 24
        months = total_d // 30
        rem_days = total_d % 30
        hh = total_h % 24
        mm = total_m % 60
        ss = total_s % 60
        if months > 0:
            return f"{months}개월 {rem_days}일"
        elif total_d > 0:
            return f"{total_d}일 {hh:02d}:{mm:02d}:{ss:02d}"
        else:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"

    # ── 테이블 갱신 ───────────────────────────────
    def _refresh_table(self):
        schedules = store.get_schedules()
        self.sched_table.setRowCount(0)
        STATUS_COLOR = {"대기": AMBER, "실행 중": GREEN, "완료": BLUE, "비활성": TEXT_MUTED}

        for idx, s in enumerate(schedules):
            r = self.sched_table.rowCount()
            self.sched_table.insertRow(r)

            # 인덱스
            idx_item = QTableWidgetItem();
            idx_item.setData(Qt.ItemDataRole.DisplayRole, idx)
            idx_item.setForeground(QColor(TEXT_MUTED))
            self.sched_table.setItem(r, 0, idx_item)

            # Task Name / URL / Execution Time (설정 주기 문자열)
            vals = [s["task_nm"], s.get("callback_url", ""), s["schedule"]["exec_str"]]
            colors = [TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY]
            for col, (val, color) in enumerate(zip(vals, colors), start=1):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.sched_table.setItem(r, col, item)

            # Next Runtime — Remaining Time only
            run_at = s["schedule"]["run_at"]
            if run_at:
                remaining_txt = self._format_remaining(run_at)
            else:
                remaining_txt = "—"
            nr_item = QTableWidgetItem(remaining_txt)
            nr_item.setForeground(QColor(PURPLE))
            self.sched_table.setItem(r, 4, nr_item)

            # Status
            status = s["schedule"]["status"]
            si = QTableWidgetItem(status)
            si.setForeground(QColor(STATUS_COLOR.get(status, TEXT_MUTED)))
            self.sched_table.setItem(r, 5, si)

            # Action (수정 / 삭제)
            action_w = QWidget();
            action_w.setStyleSheet("background:transparent;")
            al = QHBoxLayout(action_w);
            al.setContentsMargins(4, 2, 4, 2);
            al.setSpacing(4)
            edit_btn = parts.outline_btn("✎ 수정");
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(edit_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{ACCENT_LIGHT};")
            edit_btn.clicked.connect(lambda _, i=idx: self._manage_schedule_task(sched_task="수정", idx=i))
            # edit_btn.clicked.connect(lambda _, i=idx: self._show_edit_panel(i))
            del_btn = parts.outline_btn("삭제");
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(del_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{RED};")
            del_btn.clicked.connect(lambda _, i=idx: self._delete_schedule(i))
            al.addWidget(edit_btn);
            al.addWidget(del_btn)
            self.sched_table.setCellWidget(r, 6, action_w)


    # ── JSON 저장 / 로드 ──────────────────────────────


# ══════════════════════════════════════════════════════
#  PROXY SETTINGS PAGE
# ══════════════════════════════════════════════════════
class SessionSettingsPage(QWidget, SessionSettingsPageTriggers):
    def __init__(self):
        super().__init__()
        self._proxy_rows = []  # list of dict
        self._build()

    # ── 초기 더미 데이터 ──────────────────────────────
    def _seed(self):
        samples = [
            {"host": "10.0.0.1", "port": "8080", "protocol": "HTTP", "enabled": True, "latency": "82ms",
             "status": "활성"},
            {"host": "10.0.0.12", "port": "3128", "protocol": "SOCKS5", "enabled": True, "latency": "145ms",
             "status": "활성"},
            {"host": "10.0.0.23", "port": "8888", "protocol": "HTTP", "enabled": False, "latency": "—",
             "status": "비활성"},
            {"host": "45.12.34.99", "port": "1080", "protocol": "SOCKS4", "enabled": True, "latency": "310ms",
             "status": "활성"},
        ]
        # blockSignals: 초기 시드 삽입 중 itemChanged → _on_proxy_item_changed 호출 차단
        self._proxy_table.blockSignals(True)
        try:
            for s in samples:
                self._proxy_rows.append(s)
                self._insert_table_row(s)
        finally:
            self._proxy_table.blockSignals(False)

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 스크롤 바디 ──────────────────────────────────
        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 옵션 카드 ──────────────────────────────
        gw1, gl1 = parts.card_widget("세션 설정")
        row0 = QHBoxLayout();
        row0.setSpacing(16)

        self.ua_check = QCheckBox("UA 랜덤")
        self.ua_check.setToolTip("요청마다 User-Agent를 무작위로 변경")
        self.ua_check.setChecked(True)

        self.cookie_check = QCheckBox("Cookie 랜덤")
        self.cookie_check.setChecked(True)
        self.cookie_check.setToolTip("요청마다 Cookie 세션을 무작위로 순환")

        self._global_cb = QCheckBox("전역 프록시 사용")
        self._global_cb.setChecked(False)

        row0.addWidget(self.ua_check)
        row0.addWidget(self.cookie_check)
        row0.addWidget(self._global_cb)
        gl1.addLayout(row0)
        bl.addWidget(gw1)

        self.gw2, gl2 = parts.card_widget("프록시 옵션")
        row0 = QHBoxLayout();
        row0.setSpacing(16)
        self._rotate_cb = QCheckBox("자동 로테이션")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        self._test_cb = QCheckBox("연결 전 헬스체크")
        self._test_cb.setChecked(False)
        row0.addWidget(self._test_cb)
        row0.addStretch()
        gl2.addLayout(row0)
        row1 = QHBoxLayout();
        row1.setSpacing(10)
        row1.addWidget(parts.make_label("분당 IP 허용 갯수", TEXT_SECONDARY, 12))
        self._allow_ip_cnts = QSpinBox();
        self._allow_ip_cnts.setRange(1, 15);
        self._allow_ip_cnts.setValue(10)
        row1.addWidget(self._allow_ip_cnts)
        row1.addSpacing(20)
        row1.addWidget(parts.make_label("MAX RETRY", TEXT_SECONDARY, 12))
        self._retry_spin = QSpinBox();
        self._retry_spin.setRange(1, 20);
        self._retry_spin.setValue(3)
        row1.addWidget(self._retry_spin)
        row1.addStretch()
        gl2.addLayout(row1)
        bl.addWidget(self.gw2)

        # ── 프록시 목록 카드 ──────────────────────────────
        self.pw, pl = parts.card_widget("프록시 목록")
        # 테이블 헤더 행
        hdr_row = QHBoxLayout();
        hdr_row.setSpacing(8)
        hdr_row.addStretch()

        self._import_lbl = parts.make_label("", TEXT_MUTED, 10)
        self._import_btn = parts.outline_btn("📂 Import")
        self._import_btn.setToolTip("텍스트/CSV 파일에서 IP:PORT 형식의 프록시 목록을 불러옵니다")
        self._import_btn.clicked.connect(self._import_proxy_file)
        self._add_btn = parts.action_btn("+ 추가", ACCENT, ACCENT_HOVER)
        self._add_btn.clicked.connect(self._add_proxy_dialog)
        hdr_row.addWidget(self._import_lbl)
        hdr_row.addWidget(self._import_btn)
        hdr_row.addWidget(self._add_btn)
        pl.addLayout(hdr_row)
        self._proxy_table = self._make_proxy_table()
        pl.addWidget(self._proxy_table)
        bl.addWidget(self.pw)

        # ── 더미 데이터 시드 ──────────────────────────────
        self._seed()

        # 연결 부분
        self._global_cb.toggled.connect(self._activate_proxy_option)
        self._activate_proxy_option(self._global_cb.isChecked())

    # ── 프록시 활성/비활성 시각 전환 ────────────────────
    def _set_card_visual(self, card: QWidget, enabled: bool) -> None:
        """
        카드 컨테이너의 테두리·배경·자식 위젯 색상을 enabled 상태에 맞게 전환합니다.
        QSS는 THEME.PROXY_CARD_ENABLED_QSS / PROXY_CARD_DISABLED_QSS 프로퍼티에서 관리합니다.
        """
        if enabled:
            card.setStyleSheet(theme.PROXY_CARD_ENABLED_QSS)
        else:
            card.setStyleSheet(theme.PROXY_CARD_DISABLED_QSS)

    def _make_proxy_table(self):
        headers = ["활성", "프로토콜", "호스트", "포트", "레이턴시", "상태"]
        t = EqualSpacingTable(
            parent=self,
            row_height=36,
            col_padding=8,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._proxy_table_context_menu)
        # itemChanged: 체크박스 직접 클릭 시 상태 동기화
        t.itemChanged.connect(self._on_proxy_item_changed)
        # itemClicked: 행 어디를 클릭해도 활성/비활성 토글
        t.itemClicked.connect(self._on_proxy_row_clicked)
        t.setStyleSheet(t.styleSheet() + theme.PROXY_TABLE_INDICATOR_QSS)
        return t

    def _insert_table_row(self, data: dict):
        """
        QTableWidgetItem만 사용 — setCellWidget 완전 제거.
        체크박스·상태칩·삭제버튼을 텍스트 셀로 대체하여 대량 삽입 성능을 확보합니다.
        삭제는 우클릭 컨텍스트 메뉴(_proxy_table_context_menu)로 처리합니다.
        """
        t = self._proxy_table
        r = t.rowCount()
        t.insertRow(r)
        t.setRowHeight(r, 36)

        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter

        # col 0 — 활성 여부 (ItemIsUserCheckable — setCellWidget 없이 체크박스 렌더링)
        # setItem() 1회로 완결되어 대량 삽입 성능에 영향 없음
        enabled_item = QTableWidgetItem()
        enabled_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsUserCheckable   # 체크박스 렌더링 플래그
        )
        enabled_item.setCheckState(
            Qt.CheckState.Checked if data["enabled"] else Qt.CheckState.Unchecked
        )
        t.setItem(r, 0, enabled_item)

        # col 1 — 프로토콜
        color_map = {"HTTP": BLUE, "HTTPS": BLUE, "SOCKS5": PURPLE, "SOCKS4": AMBER}
        proto_item = QTableWidgetItem(data["protocol"])
        proto_item.setForeground(QColor(color_map.get(data["protocol"], TEXT_SECONDARY)))
        proto_item.setTextAlignment(align)
        proto_item.setFlags(proto_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 1, proto_item)

        # col 2 — 호스트
        host_item = QTableWidgetItem(data["host"])
        host_item.setForeground(QColor(TEXT_PRIMARY))
        host_item.setTextAlignment(align)
        host_item.setFlags(host_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 2, host_item)

        # col 3 — 포트
        port_item = QTableWidgetItem(data["port"])
        port_item.setForeground(QColor(TEXT_SECONDARY))
        port_item.setTextAlignment(align)
        port_item.setFlags(port_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 3, port_item)

        # col 4 — 레이턴시
        lat_item = QTableWidgetItem(data["latency"])
        lat_item.setForeground(QColor(GREEN if data["latency"] != "—" else TEXT_MUTED))
        lat_item.setTextAlignment(align)
        lat_item.setFlags(lat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 4, lat_item)

        # col 5 — 상태
        status_item = QTableWidgetItem(data["status"])
        status_item.setForeground(QColor(GREEN if data["status"] == "활성" else TEXT_MUTED))
        status_item.setTextAlignment(align)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 5, status_item)

    def _proxy_table_context_menu(self, pos):
        """
        우클릭 컨텍스트 메뉴 — 삭제 버튼(setCellWidget) 제거 대체.
        선택된 행을 삭제하거나 활성 상태를 토글합니다.
        """
        index = self._proxy_table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        menu = QMenu(self)
        # QSS는 THEME.PROXY_CONTEXT_MENU_QSS 프로퍼티에서 관리
        menu.setStyleSheet(theme.PROXY_CONTEXT_MENU_QSS)
        # 활성 토글 — checkState() 기준 (ItemIsUserCheckable 체크박스)
        enabled_item = self._proxy_table.item(row, 0)
        is_enabled = (
            enabled_item.checkState() == Qt.CheckState.Checked
        ) if enabled_item else False
        toggle_txt = "비활성으로 전환" if is_enabled else "활성으로 전환"
        toggle_act = menu.addAction(toggle_txt)
        menu.addSeparator()
        # 삭제
        del_act = menu.addAction("🗑  이 행 삭제")
        del_act.setProperty("is_delete", True)

        action = menu.exec(self._proxy_table.viewport().mapToGlobal(pos))
        if action == del_act:
            self._delete_row(row)
        elif action == toggle_act:
            # blockSignals: _toggle_proxy_enabled 내 col 0 setCheckState 시
            # itemChanged 재발생 → _on_proxy_item_changed 중복 호출 방지
            self._proxy_table.blockSignals(True)
            try:
                self._toggle_proxy_enabled(row, not is_enabled)
            finally:
                self._proxy_table.blockSignals(False)

    def _toggle_proxy_enabled(self, row: int, enable: bool):
        """
        활성 체크박스 상태·상태 컬럼·_proxy_rows 동기화.
        호출 전 반드시 blockSignals(True)로 감싸야 itemChanged 재귀를 방지합니다.
        """
        t = self._proxy_table
        if row >= t.rowCount():
            return
        # col 0 — 체크 상태 변경 (setText/setForeground 제거 — 체크박스는 텍스트 무관)
        enabled_item = t.item(row, 0)
        if enabled_item:
            enabled_item.setCheckState(
                Qt.CheckState.Checked if enable else Qt.CheckState.Unchecked
            )
        # col 5 — 상태 텍스트·색상 동기화
        status_item = t.item(row, 5)
        if status_item:
            status_txt = "활성" if enable else "비활성"
            status_item.setText(status_txt)
            status_item.setForeground(QColor(GREEN if enable else TEXT_MUTED))
        # _proxy_rows 동기화
        if row < len(self._proxy_rows):
            self._proxy_rows[row]["enabled"] = enable
            self._proxy_rows[row]["status"]  = "활성" if enable else "비활성"

    def _on_proxy_item_changed(self, item):
        """
        itemChanged 시그널 수신 — 사용자가 체크박스를 직접 클릭했을 때 호출됩니다.

        [재귀 방지]
        col 0이 아닌 변경(상태 컬럼 등)은 즉시 return합니다.
        _toggle_proxy_enabled() 호출 전 blockSignals(True)로 감싸
        col 0 setCheckState 시 itemChanged 재발생을 차단합니다.

        [_seed / 대량 import 중 호출 방지]
        blockSignals(True)로 삽입 루프를 감싸면 이 슬롯이 호출되지 않습니다.
        방어 조건으로 row >= len(_proxy_rows)이면 return합니다.
        """
        if item.column() != 0:
            return   # 활성 컬럼(col 0) 이외 변경은 무시
        row = item.row()
        if row >= len(self._proxy_rows):
            return   # _proxy_rows 미등록 행 방어 (seed/import 중 누수 방지)
        enable = item.checkState() == Qt.CheckState.Checked
        # blockSignals: _toggle_proxy_enabled 내 setCheckState → itemChanged 재귀 차단
        self._proxy_table.blockSignals(True)
        try:
            self._toggle_proxy_enabled(row, enable)
        finally:
            self._proxy_table.blockSignals(False)

    def load_ip_list_from_file(self):
        """파일을 첨부하여 IP 리스트 테이블에 로드합니다."""
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(
            self, "IP 리스트 파일 선택", "", "Text files (*.txt);;CSV files (*.csv);;All files (*.*)"
        )

        if not file_path:
            return

        ip_port_pattern = re.compile(r"^\d+\.\d+\.\d+\.\d+:\d+$")  # IP 주소 정규식
        try:

            if file_path.endswith('.csv'):

                with open(file_path, mode='r', encoding='utf-8') as f:

                    # DictReader 객체 생성
                    reader = csv.reader(f)

                    # 리스트 내 딕셔너리 형태로 한꺼번에 변환
                    raw_lines = [row[0] for row in reader]

            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_lines = [line.strip() for line in f if line.strip()]

            total_loaded = len(raw_lines)
            ip_list = [line for line in raw_lines if ip_port_pattern.fullmatch(line)]
            filtered_count = len(ip_list)

            if not ip_list:
                QMessageBox.warning(self, "파일 오류",
                                    f"파일에서 유효한 IP:PORT 형식({ip_port_pattern.pattern})의 데이터를 찾을 수 없습니다. ({total_loaded}개 항목 중 0개)")
                self.ip_proxy_table.setRowCount(0)
                # self.log_message(f"❌ IP 리스트 파일 로드 실패: 로드된 {total_loaded}개 항목 중 정규식에 일치하는 데이터가 없습니다.")
                return

            table = self.ip_proxy_table
            table.setUpdatesEnabled(False)
            try:
                table.setRowCount(len(ip_list))
                for row_index, ip in enumerate(ip_list):
                    table.setItem(row_index, 0, QTableWidgetItem(ip))
            finally:
                table.setUpdatesEnabled(True)

            if filtered_count > 0:
                table.selectRow(0)

            # self.log_message(f"✅ IP 리스트 파일 '{file_path}'에서 총 {total_loaded}개 항목 중 {filtered_count}개의 유효한 IP를 성공적으로 로드했습니다. (모든 항목 검사 완료)")

        except Exception as e:
            QMessageBox.critical(self, "파일 로드 오류", f"파일을 로드하거나 처리하는 중 오류가 발생했습니다: {e}")
            # self.log_message(f"❌ IP 리스트 파일 로드 실패: {e}")


# ══════════════════════════════════════════════════════
#  AUTH MANAGER PAGE
# ══════════════════════════════════════════════════════
class AuthManagerPage(QWidget, AuthManagerPageTriggers):
    def __init__(self):
        super().__init__()
        self._auth_rows = []
        self._build()

    def _seed(self):
        samples = [
            {"name": "Naver API", "type": "API Key", "key": "nav_****_xxxx", "expires": "2025-12-31", "status": "유효"},
            {"name": "Coupang Scraper", "type": "Cookie", "key": "sess=abc****", "expires": "2025-06-01",
             "status": "만료임박"},
            {"name": "AWS S3 Export", "type": "OAuth2", "key": "arn:aws:****", "expires": "상시", "status": "유효"},
            {"name": "Internal DB", "type": "Basic Auth", "key": "admin:****", "expires": "상시", "status": "유효"},
        ]
        for s in samples:
            self._auth_rows.append(s)
            self._insert_table_row(s)

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 인증 옵션 (탭 위 고정) ─────────────────
        global_w, global_l = parts.card_widget("전역 인증 옵션")
        global_w.setStyleSheet(
            global_w.styleSheet() + "border-radius:0px; border-left:none; border-right:none; border-top:none;")
        row0 = QHBoxLayout();
        row0.setSpacing(16)
        self._tls_cb = QCheckBox("TLS/SSL 인증서 검증")
        self._tls_cb.setChecked(False)
        self._tls_cb.stateChanged.connect(self._on_tls_toggle)
        row0.addWidget(self._tls_cb)
        self._store_cb = QCheckBox("인증 정보 암호화 저장")
        self._store_cb.setChecked(False)
        row0.addWidget(self._store_cb)
        self._rotate_cb = QCheckBox("세션 자동 갱신")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        row0.addStretch()
        self._cert_lbl = parts.make_label("● TLS 검증 활성화", GREEN, 12)
        row0.addWidget(self._cert_lbl)
        global_l.addLayout(row0)
        bl.addWidget(global_w)

        # ── 인증 자격증명 목록 ──────────────────────────
        cw, cl = parts.card_widget("자격증명 목록")
        hdr_row = QHBoxLayout()
        hdr_row.addStretch()
        self._add_cred_btn = parts.action_btn("+ 자격증명 추가", ACCENT, ACCENT_HOVER)
        self._add_cred_btn.clicked.connect(self._add_cred_dialog)
        self._export_btn = parts.outline_btn("내보내기 (암호화)")
        self._export_btn.clicked.connect(self._export_creds)
        hdr_row.addWidget(self._export_btn)
        hdr_row.addWidget(self._add_cred_btn)
        cl.addLayout(hdr_row)

        self._cred_table = self._make_cred_table()
        cl.addWidget(self._cred_table)
        bl.addWidget(cw)

        self._seed()

        # ── 로그인 대상 설정 카드 ────────────────────────
        lc_w, lc_l = parts.card_widget("로그인 대상 설정")

        def _field(label, widget, layout):
            row = QHBoxLayout();
            row.setSpacing(10)
            lbl = parts.make_label(label, TEXT_SECONDARY, 12)
            lbl.setFixedWidth(90)
            row.addWidget(lbl)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        self._login_url = QLineEdit()
        self._login_url.setPlaceholderText("https://example.com/login")
        self._login_url.setToolTip("로그인 폼이 있는 페이지 URL")

        self._login_id = QLineEdit()
        self._login_id.setPlaceholderText("아이디 / 이메일")

        self._login_pw = QLineEdit()
        self._login_pw.setPlaceholderText("비밀번호")
        self._login_pw.setEchoMode(QLineEdit.EchoMode.Password)

        # 비밀번호 표시/숨기기 토글
        pw_row = QHBoxLayout();
        pw_row.setSpacing(6)
        pw_row.addWidget(self._login_pw, 1)
        self._pw_toggle = QPushButton("👁")
        self._pw_toggle.setFixedSize(28, 28)
        self._pw_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pw_toggle.setCheckable(True)
        self._pw_toggle.setStyleSheet(f"""
                    QPushButton {{
                        background:{BG_PRIMARY}; color:{TEXT_MUTED};
                        border:1px solid {BORDER_LIGHT}; border-radius:4px; font-size:14px;
                    }}
                    QPushButton:checked {{ color:{ACCENT_LIGHT}; border-color:{ACCENT}; }}
                    QPushButton:hover {{ background:{BG_HOVER}; }}
                """)
        self._pw_toggle.toggled.connect(
            lambda on: self._login_pw.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        pw_row.addWidget(self._pw_toggle)
        pw_widget = QWidget();
        pw_widget.setLayout(pw_row)
        pw_widget.setStyleSheet("background:transparent;")

        self._login_method = QComboBox()
        self._login_method.addItems(["Form POST", "JavaScript Click", "OAuth2 Redirect", "Basic Auth Header"])
        self._login_method.setToolTip("로그인 처리 방식 선택")

        self._login_selector = QLineEdit()
        self._login_selector.setPlaceholderText("예: #login-btn  (선택사항 — 비워두면 자동 탐지)")
        self._login_selector.setToolTip("로그인 버튼 CSS 셀렉터 (Form POST 외 방식에서 사용)")

        self._login_success_kw = QLineEdit()
        self._login_success_kw.setPlaceholderText("예: 마이페이지, dashboard  (로그인 성공 판별 키워드)")
        self._login_success_kw.setToolTip("로그인 후 응답 페이지에서 찾을 성공 판별 키워드")

        _field("사이트 URL", self._login_url, lc_l)
        _field("아이디", self._login_id, lc_l)

        # 비밀번호 행은 toggle 버튼 포함이므로 직접 추가
        pw_outer = QHBoxLayout();
        pw_outer.setSpacing(10)
        pw_lbl = parts.make_label("비밀번호", TEXT_SECONDARY, 12);
        pw_lbl.setFixedWidth(90)
        pw_outer.addWidget(pw_lbl)
        pw_outer.addWidget(pw_widget, 1)
        lc_l.addLayout(pw_outer)

        _field("로그인 방식", self._login_method, lc_l)
        lc_l.addWidget(Divider())
        _field("로그인 셀렉터", self._login_selector, lc_l)
        _field("성공 판별 키워드", self._login_success_kw, lc_l)
        bl.addWidget(lc_w)

        # ── 연결 상태 & 액션 카드 ────────────────────────
        ac_w, ac_l = parts.card_widget("연결 상태")
        status_row = QHBoxLayout();
        status_row.setSpacing(12)

        self._login_status_dot = parts.make_label("●", TEXT_MUTED, 14)
        self._login_status_lbl = parts.make_label("미연결", TEXT_MUTED, 12)
        status_row.addWidget(self._login_status_dot)
        status_row.addWidget(self._login_status_lbl)
        status_row.addStretch()

        test_btn = parts.outline_btn("연결 테스트")
        test_btn.clicked.connect(self._test_login)
        save_btn = parts.action_btn("저장 & Credentials 등록")
        save_btn.clicked.connect(self._save_login)

        status_row.addWidget(test_btn)
        status_row.addWidget(save_btn)
        ac_l.addLayout(status_row)
        bl.addWidget(ac_w)

        # ── 저장된 Login Profile 목록 ────────────────────
        lp_w, lp_l = parts.card_widget("저장된 Login Profile")
        lp_hdr = QHBoxLayout();
        lp_hdr.addStretch()
        clear_all_btn = parts.outline_btn("전체 삭제")
        clear_all_btn.clicked.connect(self._clear_login_profiles)
        lp_hdr.addWidget(clear_all_btn)
        lp_l.addLayout(lp_hdr)

        self._profile_table = EqualSpacingTable(
            parent=self,
            row_height=32,
            col_padding=10,
            hscroll_handle=50,
        )
        self._profile_table.setColumnCount(5)
        self._profile_table.setHorizontalHeaderLabels(
            ["사이트 URL", "아이디", "방식", "상태", "액션"])
        self._profile_table.setFixedHeight(160)
        lp_l.addWidget(self._profile_table)
        bl.addWidget(lp_w)

    # ══════════════════════════════════════════════
    #  Login Info — 액션 메서드
    # ══════════════════════════════════════════════


    def _make_cred_table(self):
        headers = ["이름", "타입", "키 (마스킹)", "만료일", "상태", "액션"]
        t = EqualSpacingTable(
            parent=self,
            row_height=36,
            col_padding=8,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        return t

    def _insert_table_row(self, data: dict):

        r = self._cred_table.rowCount()
        self._cred_table.insertRow(r)
        self._cred_table.setRowHeight(r, 36)

        type_colors = {"API Key": BLUE, "Cookie": AMBER, "OAuth2": PURPLE, "Basic Auth": GREEN, "Bearer Token": RED}
        st_colors = {"유효": GREEN, "만료임박": AMBER, "만료": RED}

        vals_colors = [
            (data["name"], TEXT_PRIMARY),
            (data["type"], type_colors.get(data["type"], TEXT_SECONDARY)),
            (data["key"], TEXT_MUTED),
            (data["expires"], TEXT_SECONDARY),
        ]
        for col, (val, color) in enumerate(vals_colors):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._cred_table.setItem(r, col, item)

        # 상태 칩
        sc = st_colors.get(data["status"], TEXT_MUTED)
        bg_map = {"유효": "#052e16", "만료임박": "#451a03", "만료": "#450a0a"}
        bg = bg_map.get(data["status"], BG_HOVER)
        status_lbl = QLabel(data["status"])
        status_lbl.setStyleSheet(f"color:{sc}; background:{bg}; border-radius:10px; padding:2px 10px; font-size:11px;")
        sw3 = QWidget();
        sl3 = QHBoxLayout(sw3);
        sl3.setContentsMargins(4, 0, 4, 0);
        sl3.addWidget(status_lbl)
        self._cred_table.setCellWidget(r, 4, sw3)

        # 삭제 버튼
        del_btn = QPushButton("삭제")
        del_btn.setFixedHeight(24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};border:1px solid {RED};
            border-radius:4px;padding:0 8px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        del_btn.clicked.connect(lambda _, ri=r: self._delete_cred_row(ri))
        dw = QWidget();
        dl = QHBoxLayout(dw);
        dl.setContentsMargins(4, 2, 4, 2);
        dl.addWidget(del_btn)
        self._cred_table.setCellWidget(r, 5, dw)


# ══════════════════════════════════════════════════════
#  TRAY WINDOW
# ══════════════════════════════════════════════════════
class TrayManager(QObject, TrayManagerTriggers):
    """시스템 트레이 아이콘과 메뉴를 관리하는 클래스"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.tray_icon = QSystemTrayIcon(self.main_window)

        self.icon_path = utility.resource_path() + "\\" + "combine-harvester.ico"  # 아이콘

        # 아이콘 설정 (기존 소스에서 사용하던 아이콘 경로 적용)
        self.tray_icon.setIcon(QIcon(self.icon_path))  # 실제 아이콘 경로로 수정 필요

        self.setup_menu()

        # 트레이 아이콘 클릭 이벤트 연결 (더블 클릭 시 창 보이기 등)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def setup_menu(self):
        """트레이 우클릭 메뉴 구성"""
        tray_menu = QMenu()

        show_action = QAction("프로그램 열기", self.main_window)
        show_action.triggered.connect(self.restore_window)

        quit_action = QAction("종료", self.main_window)
        # QApplication.quit() 직접 연결 시 closeEvent를 우회하므로
        # 반드시 MainWindow.exit_app()을 통해 저장 후 종료해야 합니다.
        quit_action.triggered.connect(self.main_window.exit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()


    def show_message(self, title, message):
        """트레이 알림 메시지 표시"""
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

# ══════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════
class MainWindow(QMainWindow, MainWindowTriggers):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataCrawler v2.0")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self._worker = None
        self._pending_queue = []   # 스케줄 대기 큐: 실행 중 작업이 있을 때 후속 스케줄을 순서대로 보관

        # ── log_manager 를 _build() 이전에 먼저 생성 ──────────────────────
        # AuthManagerPage 등 _build() 안에서 생성되는 모든 페이지가
        # self.window().log_manager 를 통해 즉시 참조할 수 있도록 선행 생성합니다.
        self.log_manager = LogViewerDialog(parent=self)

        self._build()
        self.tray_manager = TrayManager(self)

    def _build(self):

        # ──  왼쪽 컨텐츠 영역: Sidebar ──
        left_widget = QWidget()
        self.setCentralWidget(left_widget)
        layout = QHBoxLayout(left_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._switch_page)
        layout.addWidget(self.sidebar)

        # ── 오른쪽 컨텐츠 영역: GlobalToolbar + QStackedWidget ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 공통 Toolbar (모든 페이지 공유)
        self.global_toolbar = GlobalToolbar()
        self.global_toolbar.start_requested.connect(self._start_crawl)
        self.global_toolbar.stop_requested.connect(self._stop_crawl)
        # self.global_toolbar.reset_requested.connect(self._reset_all_pages)
        right_layout.addWidget(self.global_toolbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.monitor_page = MonitorPage()
        self.schedule_page = SchedulerPage(); self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
        self.stats_page = StatisticsPage()
        self.session_page = SessionSettingsPage()
        self.schedule_page.session_page = self.session_page

        # Navigator 순서
        self.stack.addWidget(self.dashboard)  # 0
        self.stack.addWidget(self.monitor_page)  # 1
        self.stack.addWidget(self.schedule_page)  # 2
        self.stack.addWidget(self.stats_page)  # 3
        self.stack.addWidget(self.session_page)  # 4

        if request_info["auth"]:
            self.auth_page = AuthManagerPage()
            self.stack.addWidget(self.auth_page)  # 5

        # GlobalToolbar에 log_manager 주입 (log_manager는 __init__에서 이미 생성됨)
        self.global_toolbar.set_log_manager(self.log_manager)
        self.global_toolbar.set_pages(
            dashboard=self.dashboard,
            monitor_page=self.monitor_page,
            session_page=self.session_page,
            auth_page=getattr(self, 'auth_page', None),
        )

        right_layout.addWidget(self.stack, 1)

        # ── 메인 창 최하단 상태바 (최신 로그 한 줄 + 전체 로그 보기 버튼) ──

        status_bar = QWidget()
        status_bar.setFixedHeight(41)
        status_bar.setStyleSheet(
            f"background:{BG_SECONDARY}; border-top:1px solid {BORDER};"
        )
        sbl = QHBoxLayout(status_bar)
        sbl.setContentsMargins(14, 0, 14, 0)
        sbl.setSpacing(8)

        # 레벨 태그 (색상 표시)
        self.status_level = parts.make_label("", TEXT_MUTED, 11)
        self.status_level.setFixedWidth(48)
        sbl.addWidget(self.status_level)

        # 최신 로그 메시지 한 줄
        self.status_msg = parts.make_label("대기 중", TEXT_MUTED, 11)
        self.status_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sbl.addWidget(self.status_msg, 1)

        # 전체 로그 보기 버튼
        log_view_btn = parts.outline_btn("로그 전체 보기 ▲")
        log_view_btn.clicked.connect(self._open_log_viewer)
        sbl.addWidget(log_view_btn)

        right_layout.addWidget(status_bar)

        # log_manager.last_log 시그널 → 상태바 업데이트 연결
        self.log_manager.last_log.connect(self._update_status_bar)

        layout.addWidget(right_widget, 1)


