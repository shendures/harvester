# layout/single/toolbar.py

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal

from trigger import GlobalToolbarTriggers
from ..common import parts, BG_SECONDARY, ACCENT_LIGHT, BORDER
from .common import request_info


class GlobalToolbarSingle(QWidget, GlobalToolbarTriggers):
    """
    SidebarSingle 오른쪽 콘텐츠 영역 최상단에 고정 표시되는 공통 툴바.
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
        # 실제 페이지 인스턴스는 MainWindowSingle._build()에서 set_pages()로 주입됩니다.
        self.dashboard = None
        self.monitor_page = None
        self.session_page = None
        self.auth_page = None
        self.log_manager = None  # MainWindowSingle 생성 후 set_log_manager()로 주입
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
        method, url = self._toolbar_display_info()
        self._method_label = parts.make_label(method, ACCENT_LIGHT, 12, True)
        self._configure_method_label(self._method_label)
        lay.addWidget(self._method_label)

        # URL 입력창
        self.url_input = QLineEdit(url)
        self.url_input.setCursorPosition(0)
        lay.addWidget(self.url_input, 1)

        # URL 복사 버튼
        self._copy_btn = parts.outline_btn("URL 복사")
        self._copy_btn.clicked.connect(self._copy_url)
        lay.addWidget(self._copy_btn)

        self._build_run_controls(lay)

    def _build_run_controls(self, lay):
        """시작/중지 버튼 + 추출 설정 버튼 — GlobalToolbarMulti가 오버라이드해
        생략한다(다중 레이아웃은 이 두 기능을 "수집 목록" 테이블의 항목별
        ▶/⚙ 버튼으로 옮겼다)."""
        # 시작 / 중지 버튼
        self.run_btn = QPushButton("▶  시작")
        self.run_btn.setFixedWidth(90)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._toggle_run)
        self._style_run_btn(False)
        lay.addWidget(self.run_btn)

        # 추출 설정 버튼 (Raw/정제 탭에 각각 있던 동일 다이얼로그 진입점을 통합)
        self._output_settings_btn = parts.settings_btn("⚙  추출 설정")
        self._output_settings_btn.clicked.connect(self._open_output_settings)
        lay.addWidget(self._output_settings_btn)

    def _toolbar_display_info(self):
        """(수집 방식 라벨 텍스트, URL 입력창 초기값) — GlobalToolbarMulti가 오버라이드.

        구 layout_single.py:119,122 표현식을 그대로 유지한다 — request_info에
        conditions.method가 없는 손상된 데이터에서는 지금까지와 동일하게
        KeyError로 즉시 실패해야 하며, Multi처럼 .get()으로 조용히 통과시키면
        안 된다(동작 변경 금지).
        """
        return request_info["conditions"]["method"], (request_info["url"] if request_info else "")

    def _configure_method_label(self, label):
        """method 라벨 위젯 후처리 훅 — Single은 폭 고정을 하지 않던 기존 동작을 유지한다."""
        pass
