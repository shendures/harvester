# layout/single/main_window.py

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget

from trigger import LogViewerDialog, MainWindowTriggersSingle
from ..common import build_status_bar
from ..scheduler import SchedulerPage
from ..statistics import StatisticsPage
from ..session import SessionSettingsPage
from ..auth import AuthManagerPage
from ..tray import TrayManager
from ..common import _blueprint_auth_method, _blueprint_requires_auth
from .common import request_info
from .toolbar import GlobalToolbarSingle
from .sidebar import SidebarSingle
from .dashboard import DashboardPageSingle
from .monitor import MonitorPageSingle


class MainWindowSingle(QMainWindow, MainWindowTriggersSingle):
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

        # ──  왼쪽 컨텐츠 영역: SidebarSingle ──
        left_widget = QWidget()
        self.setCentralWidget(left_widget)
        layout = QHBoxLayout(left_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarSingle()
        self.sidebar.page_changed.connect(self._switch_page)
        layout.addWidget(self.sidebar)

        # ── 오른쪽 컨텐츠 영역: GlobalToolbarSingle + QStackedWidget ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 공통 Toolbar (모든 페이지 공유)
        self.global_toolbar = GlobalToolbarSingle()
        self.global_toolbar.start_requested.connect(self._start_crawl)
        self.global_toolbar.stop_requested.connect(self._stop_crawl)
        right_layout.addWidget(self.global_toolbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPageSingle()
        self.monitor_page = MonitorPageSingle()
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

        if _blueprint_requires_auth(request_info):
            self.auth_page = AuthManagerPage(
                _blueprint_auth_method(request_info),
                (request_info.get("conditions") or {}).get("login"),
            )
            self.stack.addWidget(self.auth_page)  # 5

        # GlobalToolbarSingle에 log_manager 주입 (log_manager는 __init__에서 이미 생성됨)
        self.global_toolbar.set_log_manager(self.log_manager)
        self.global_toolbar.set_pages(
            dashboard=self.dashboard,
            monitor_page=self.monitor_page,
            session_page=self.session_page,
            auth_page=getattr(self, 'auth_page', None),
        )

        right_layout.addWidget(self.stack, 1)

        # ── 메인 창 최하단 상태바 (최신 로그 한 줄 + 전체 로그 보기 버튼) ──
        status_bar, self.status_level, self.status_msg = build_status_bar(self._open_log_viewer)
        right_layout.addWidget(status_bar)

        # log_manager.last_log 시그널 → 상태바 업데이트 연결
        self.log_manager.last_log.connect(self._update_status_bar)

        layout.addWidget(right_widget, 1)


