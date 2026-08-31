# layout/single/__init__.py
# 단일 수집 레이아웃 서브패키지의 facade — 공개 클래스만 재export한다.
# layout.multi가 이 심볼들을 상속 목적으로 import한다.

from .toolbar import GlobalToolbarSingle
from .sidebar import SidebarSingle
from .dashboard import DashboardPageSingle
from .monitor import MonitorPageSingle
from .main_window import MainWindowSingle

__all__ = [
    "GlobalToolbarSingle", "SidebarSingle",
    "DashboardPageSingle", "MonitorPageSingle",
    "MainWindowSingle",
]
