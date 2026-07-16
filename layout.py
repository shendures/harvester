import os
import utility
from datetime import datetime
import customized_settings

from conf import DataStore, BlueprintStorage
from trigger import (
    GlobalToolbarTriggers, DashboardPageTriggers, MonitorPageTriggers,
    StatisticsPageTriggers, SchedulerPageTriggers,
    SessionSettingsPageTriggers, AuthManagerPageTriggers,
    TrayManagerTriggers, MainWindowTriggers,
    LogViewerDialog,
)
from style import THEME, NavItem, StatCard, Divider, Parts, EqualSpacingTable, TagButton

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidgetItem, QFrame, QProgressBar,
    QScrollArea, QStackedWidget,
    QSpinBox, QDoubleSpinBox, QMessageBox,
    QCheckBox, QSizePolicy, QSystemTrayIcon,
    QMenu, QTabWidget
)
from PyQt6.QtCore import ( Qt, QTimer, QPoint, QObject, pyqtSignal )
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
    - reset_requested : 정의만 되어 있고 어디서도 emit/connect되지 않는 미사용 시그널
    """
    start_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._start_cancelled = False   # 중지 시 QTimer 예약 콜백을 막는 플래그
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

        status_row = QHBoxLayout()
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
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 10.0)
        self.delay_spin.setValue(0.5)
        self.delay_spin.setSingleStep(0.5)
        self.delay_spin.setDecimals(1)  # setDecimals : 소수점 자리 수 self.delay_spin.setSuffix("s")
        self.delay_spin.setToolTip("요청 간 대기 시간 (기본 0.5s)")
        r1.addWidget(self.delay_spin)
        r1.addSpacing(6)
        r1.addWidget(parts.make_label(" Threads", TEXT_SECONDARY, 12))
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(4)
        self.thread_spin.setToolTip("병렬 수집 스레드 수")
        r1.addWidget(self.thread_spin)
        r1.addSpacing(6)
        r1.addStretch()
        c1.addLayout(r1)

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
            "remove_null_row":   True,   # 모든 필드 null 행 제거
            "custom_rule":       True,   # 커스텀 규칙(seq_no) 적용
            "trim_whitespace":   True,   # 문자열 앞뒤 공백 trim
            "remove_duplicate":  True,   # 중복 행 제거
            "drop_columns":      False,  # 선택 필드 제외 (비활성 기본)
            "fill_null":         False,  # null → 지정값 치환 (비활성 기본)
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
        self.sum_err   = StatCard("전체 null",   "0", AMBER)
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

        raw_exp_btn = parts.action_btn("EXTRACT")
        raw_exp_btn.clicked.connect(lambda: self._extract_result_table(source="raw"))
        tbl_ctrl.addWidget(raw_exp_btn)

        raw_out_cfg_btn = parts.settings_btn("⚙  추출 설정")
        raw_out_cfg_btn.clicked.connect(self._open_output_settings_dialog)
        tbl_ctrl.addWidget(raw_out_cfg_btn)
        tc.addLayout(tbl_ctrl)

        # null·중복 안내
        info_lbl = parts.make_label(
            "● 주황색 배경: 전체 null 행  ● 빨간색 배경: 중복 행",
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
            ("remove_null_row",  "모든 필드 null 행 제거",
             "모든 필드가 null·빈 값인 행만 삭제합니다."),
            ("custom_rule",      "커스텀 정제 규칙 적용",
             "사용자 정의 정제 함수를 적용합니다."),
            ("trim_whitespace",  "문자열 공백 trim",
             "문자열 필드의 앞뒤 공백 및 줄바꿈을 제거합니다."),
            ("remove_duplicate", "중복 행 제거",
             "모든 컬럼 값이 동일한 행을 1개만 유지합니다."),
            ("drop_columns",     "제외 필드 지정",
             "추출에 불필요한 컬럼을 선택하여 제외합니다."),
            ("fill_null",        "결측값(N/A) 치환",
             "삭제 대상 외 결측값을 지정한 값으로 대체합니다."),
            ("cast_numeric",     "숫자 타입 변환",
             "문자열로 수집된 숫자 필드를 int / float으로 변환합니다."),
        ]

        self._rule_checkboxes: dict[str, QCheckBox] = {}

        # 체크박스 옆에 별도 입력/선택 컨트롤이 붙는 규칙 — 컨트롤을 텍스트 바로
        # 옆에 붙이고 남는 공간은 그 뒤로 보내, 카드 오른쪽 끝에 붙어 보이지 않게 함
        rows_with_control = ("drop_columns", "fill_null")

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

            has_control = key in rows_with_control
            row_l.addLayout(text_col, 0 if has_control else 1)
            if has_control:
                row_l.addSpacing(16)

            if key == "fill_null":
                self.fill_null_input = QLineEdit()
                self.fill_null_input.setPlaceholderText("비워두면 빈 값으로 채워집니다")
                self.fill_null_input.setFixedWidth(220)
                self.fill_null_input.setVisible(cb.isChecked())
                self.fill_null_input.setStyleSheet(
                    f"background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; "
                    f"border:1px solid {BORDER}; border-radius:4px; padding:3px 8px; font-size:11px;"
                )
                cb.stateChanged.connect(
                    lambda state, w=self.fill_null_input: w.setVisible(
                        state == Qt.CheckState.Checked.value)
                )
                row_l.addWidget(self.fill_null_input)

            if key == "drop_columns":
                drop_columns_settings_btn = parts.settings_btn("⚙  필드 선택")
                drop_columns_settings_btn.setVisible(cb.isChecked())
                drop_columns_settings_btn.clicked.connect(self._open_drop_columns_dialog)
                row_l.addWidget(drop_columns_settings_btn)

                self.drop_columns_summary_lbl = parts.make_label("", TEXT_MUTED, 11)
                self._update_drop_columns_summary()
                self.drop_columns_summary_lbl.setVisible(cb.isChecked())
                row_l.addWidget(self.drop_columns_summary_lbl)

                def _on_drop_columns_toggled(state, cb=cb, b=drop_columns_settings_btn, l=self.drop_columns_summary_lbl):
                    checked = state == Qt.CheckState.Checked.value
                    if checked and not self._collected_data:
                        # 경고창이 뜨기 전에 체크박스를 먼저 되돌림 — setChecked(False)가
                        # 이 핸들러를 재귀 호출해 버튼/라벨 숨김까지 먼저 끝낸 뒤에 경고 표시
                        cb.setChecked(False)
                        self._has_collected_data_or_warn()
                        return
                    b.setVisible(checked)
                    l.setVisible(checked)

                cb.stateChanged.connect(_on_drop_columns_toggled)

            if has_control:
                row_l.addStretch()

            rl.addWidget(row_w)

        # 커스텀 정제 규칙 체크 시 규칙 ①③④⑥(remove_null_row/trim_whitespace/
        # remove_duplicate/fill_null)를 자동으로 켬 (해제 시에는 영향 없음)
        self._rule_checkboxes["custom_rule"].stateChanged.connect(self._on_custom_rule_toggled)

        rl.addSpacing(12)

        run_row = QHBoxLayout()
        run_row.addStretch()
        run_btn = parts.action_btn("정제 실행")
        run_btn.setFixedWidth(120)
        run_btn.clicked.connect(lambda: self._run_refine())
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
        exp_btn.clicked.connect(lambda: self._extract_result_table(source="refined"))
        ref_ctrl.addWidget(exp_btn)

        out_cfg_btn = parts.settings_btn("⚙  추출 설정")
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

        # 좌우 테이블 세로 스크롤 동기화
        self.cmp_raw_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_cmp_vscroll(self.cmp_raw_table, self.cmp_ref_table, v))
        self.cmp_ref_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_cmp_vscroll(self.cmp_ref_table, self.cmp_raw_table, v))

        # 좌우 테이블 정렬 동기화 (같은 컬럼명·방향)
        self.cmp_raw_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_raw_table, self.cmp_ref_table, idx, order))
        self.cmp_ref_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_ref_table, self.cmp_raw_table, idx, order))

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
        """정제 단계 진입 직전 상태 준비 — 실제 FILE/DB 추출은 _extract_result_table()이 수행."""
        # seq_no/needs_cleaning 등 정제 시 참조할 현재 작업 정보 보관
        self._current_task = task or {}
        self._cleaning_warned = False   # 새 수집 결과 — 팝업 안내 여부 초기화

        if not self._collected_data:
            QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return

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
        if color:
            self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        if not self.values:
            return
        p = QPainter(self)
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
        if not self.datasets:
            return
        p = QPainter(self)
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
            if not vals:
                continue
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
        self._timer = QTimer()
        self._timer.timeout.connect(self.reload)
        self._timer.start(3000)

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
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

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


# ══════════════════════════════════════════════════════
#  SCHEDULER PAGE
# ══════════════════════════════════════════════════════
class SchedulerPage(QWidget, SchedulerPageTriggers):

    schedule_run = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        self.app_dir = os.path.join(self.root_path, utility.get_app_name())
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
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

        self._cd_timer = QTimer()
        self._cd_timer.timeout.connect(self._update_countdown)
        self._cd_timer.start(1000)


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
            idx_item = QTableWidgetItem()
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
            action_w = QWidget()
            action_w.setStyleSheet("background:transparent;")
            al = QHBoxLayout(action_w)
            al.setContentsMargins(4, 2, 4, 2)
            al.setSpacing(4)
            edit_btn = parts.outline_btn("✎ 수정")
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(edit_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{ACCENT_LIGHT};")
            edit_btn.clicked.connect(lambda _, i=idx: self._manage_schedule_task(sched_task="수정", idx=i))
            del_btn = parts.outline_btn("삭제")
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(del_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{RED};")
            del_btn.clicked.connect(lambda _, i=idx: self._delete_schedule(i))
            al.addWidget(edit_btn)
            al.addWidget(del_btn)
            self.sched_table.setCellWidget(r, 6, action_w)


# ══════════════════════════════════════════════════════
#  PROXY SETTINGS PAGE
# ══════════════════════════════════════════════════════
class SessionSettingsPage(QWidget, SessionSettingsPageTriggers):
    def __init__(self):
        super().__init__()
        self._proxy_rows = []  # list of dict
        self._build()

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 스크롤 바디 ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 옵션 카드 ──────────────────────────────
        gw1, gl1 = parts.card_widget("세션 설정")
        row0 = QHBoxLayout()
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
        row0 = QHBoxLayout()
        row0.setSpacing(16)
        self._rotate_cb = QCheckBox("자동 로테이션")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        self._test_cb = QCheckBox("연결 전 헬스체크")
        self._test_cb.setChecked(False)
        row0.addWidget(self._test_cb)
        row0.addStretch()
        gl2.addLayout(row0)
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(parts.make_label("분당 IP 허용 갯수", TEXT_SECONDARY, 12))
        self._allow_ip_cnts = QSpinBox()
        self._allow_ip_cnts.setRange(1, 15)
        self._allow_ip_cnts.setValue(10)
        row1.addWidget(self._allow_ip_cnts)
        row1.addSpacing(20)
        row1.addWidget(parts.make_label("MAX RETRY", TEXT_SECONDARY, 12))
        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(1, 20)
        self._retry_spin.setValue(3)
        row1.addWidget(self._retry_spin)
        row1.addStretch()
        gl2.addLayout(row1)
        bl.addWidget(self.gw2)

        # ── 프록시 목록 카드 ──────────────────────────────
        self.pw, pl = parts.card_widget("프록시 목록")
        # 테이블 헤더 행
        hdr_row = QHBoxLayout()
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 인증 옵션 (탭 위 고정) ─────────────────
        global_w, global_l = parts.card_widget("전역 인증 옵션")
        global_w.setStyleSheet(
            global_w.styleSheet() + "border-radius:0px; border-left:none; border-right:none; border-top:none;")
        row0 = QHBoxLayout()
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
            row = QHBoxLayout()
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
        pw_row = QHBoxLayout()
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
        pw_widget = QWidget()
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
        pw_outer = QHBoxLayout()
        pw_outer.setSpacing(10)
        pw_lbl = parts.make_label("비밀번호", TEXT_SECONDARY, 12)
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
        status_row = QHBoxLayout()
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
        lp_hdr = QHBoxLayout()
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
        sw3 = QWidget()
        sl3 = QHBoxLayout(sw3)
        sl3.setContentsMargins(4, 0, 4, 0)
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
        dw = QWidget()
        dl = QHBoxLayout(dw)
        dl.setContentsMargins(4, 2, 4, 2)
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
        right_layout.addWidget(self.global_toolbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.monitor_page = MonitorPage()
        self.schedule_page = SchedulerPage()
        self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
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


