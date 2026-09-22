# layout/single/main_window.py

from PyQt6.QtWidgets import QStackedWidget

from trigger import MainWindowTriggersSingle
from ..window_base import MainWindowBase
from ..scheduler import SchedulerPage
from ..session import SessionSettingsPage
from ..auth import AuthManagerPage
from ..common import _blueprint_auth_method, _blueprint_requires_auth
from .common import request_info
from .toolbar import GlobalToolbarSingle
from .sidebar import SidebarSingle
from .dashboard import DashboardPageSingle
from .monitor import MonitorPageSingle
from .statistics import StatisticsPageSingle


class MainWindowSingle(MainWindowBase, MainWindowTriggersSingle):
    _WINDOW_TITLE = "DataCrawler v2.0"

    def _build(self):
        self.sidebar = SidebarSingle()
        self.global_toolbar = GlobalToolbarSingle()

        self.stack = QStackedWidget()
        self.dashboard = DashboardPageSingle()
        self.monitor_page = MonitorPageSingle()
        self.schedule_page = SchedulerPage()
        self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
        self.stats_page = StatisticsPageSingle()
        self.global_toolbar.running_changed.connect(self.stats_page.set_collecting)
        self.session_page = SessionSettingsPage()
        self.schedule_page.session_page = self.session_page

        # Navigator 순서 — 추가 순서가 곧 스택 인덱스이며 trigger/common.py의
        # NAV_* 상수와 일치해야 한다.
        self.stack.addWidget(self.dashboard)  # 0 — NAV_MONITOR
        self.stack.addWidget(self.monitor_page)  # 1 — NAV_REFINE
        self.stack.addWidget(self.schedule_page)  # 2 — NAV_SCHEDULE
        self.stack.addWidget(self.stats_page)  # 3 — NAV_STATS
        self.stack.addWidget(self.session_page)  # 4 — NAV_SESSION

        if _blueprint_requires_auth(request_info):
            self.auth_page = AuthManagerPage(
                _blueprint_auth_method(request_info),
                (request_info.get("conditions") or {}).get("login"),
            )
            self.stack.addWidget(self.auth_page)  # 5 — NAV_AUTH

        self.global_toolbar.set_pages(
            dashboard=self.dashboard,
            monitor_page=self.monitor_page,
            session_page=self.session_page,
            auth_page=getattr(self, 'auth_page', None),
        )

        self._assemble_shell()
