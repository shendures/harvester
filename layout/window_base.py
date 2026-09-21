# layout/window_base.py
# MainWindowSingle/MainWindowMulti가 공유하는 창 골격 — 기본 창 설정, 최초 1회 중앙 정렬,
# "사이드바 | (툴바 / 페이지 스택 / 상태바)" 조립과 공통 시그널 연결.

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout

from trigger import LogViewerDialog
from .common import build_status_bar, center_window_on_screen
from .tray import TrayManager


class MainWindowBase(QMainWindow):
    """서브클래스는 _WINDOW_TITLE을 지정하고, _build()에서 self.sidebar/self.global_toolbar/
    self.stack을 만들어 페이지를 등록한 뒤 _assemble_shell()을 호출한다."""

    _WINDOW_TITLE = ""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self._WINDOW_TITLE)
        self.resize(1843, 1152)
        self.setMinimumSize(960, 640)
        self._worker = None
        self._pending_queue = []   # 스케줄/배치 공용 순차 대기 큐 (FIFO)

        # _build() 안에서 만들어지는 모든 페이지가 self.window().log_manager로 즉시
        # 참조할 수 있도록 _build()보다 먼저 생성한다.
        self.log_manager = LogViewerDialog(parent=self)

        self._build()
        self.tray_manager = TrayManager(self)
        self._centered_once = False

    def showEvent(self, event):
        super().showEvent(event)
        # 트레이에서 창을 복원할 때마다 다시 중앙으로 튀지 않도록 최초 1회만 정렬한다.
        if not self._centered_once:
            self._centered_once = True
            center_window_on_screen(self)

    def _assemble_shell(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.global_toolbar)
        right_layout.addWidget(self.stack, 1)

        status_bar, self.status_level, self.status_msg = build_status_bar(self._open_log_viewer)
        right_layout.addWidget(status_bar)
        layout.addWidget(right_widget, 1)

        self.sidebar.page_changed.connect(self._switch_page)
        self.global_toolbar.start_requested.connect(self._start_crawl)
        self.global_toolbar.stop_requested.connect(self._stop_crawl)
        self.log_manager.last_log.connect(self._update_status_bar)
