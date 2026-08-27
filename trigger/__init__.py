# trigger/__init__.py
# 각 페이지 클래스의 기능(액션) 메서드를 Mixin 클래스로 분리 관리하는 trigger 패키지.
# layout_single.py/layout_multi.py 양쪽의 각 클래스가 해당 Mixin을 다중상속하여
# 메서드를 주입받습니다 — 단일 수집 레이아웃과 다중 수집 레이아웃이 이 패키지를
# 공유합니다. 서브모듈은 기존 trigger.py 내 섹션 구분과 1:1로 대응합니다
# (log_viewer/toolbar/dashboard/monitor/statistics/scheduler/session/auth/main_window).
#
# MRO(메서드 탐색 순서):  PageClass → QWidget → ... → PageMixin → object
# QWidget 계열 메서드와 충돌하지 않으며, self.xxx 속성은 layout_single.py의
# _build()에서 이미 생성되어 있으므로 참조 안전합니다.
#
# 이 파일은 기존 `from trigger import X` 호출부(layout_single.py, layout_multi.py)가
# 그대로 동작하도록 서브모듈의 공개 클래스만 재-export하는 facade입니다.

from .log_viewer import SearchLineEdit, LogViewerDialog
from .toolbar import GlobalToolbarTriggers
from .dashboard import DashboardPageTriggers
from .monitor import MonitorPageTriggers
from .statistics import StatisticsPageTriggers
from .scheduler import SchedulerPageTriggers
from .session import ProxyHealthCheckThread, ProxyTestProgressDialog, SessionSettingsPageTriggers
from .auth import AuthManagerPageTriggers
from .main_window import TrayManagerTriggers, MainWindowTriggersSingle, MainWindowTriggersMulti

__all__ = [
    "SearchLineEdit", "LogViewerDialog",
    "GlobalToolbarTriggers",
    "DashboardPageTriggers",
    "MonitorPageTriggers",
    "StatisticsPageTriggers",
    "SchedulerPageTriggers",
    "ProxyHealthCheckThread", "ProxyTestProgressDialog", "SessionSettingsPageTriggers",
    "AuthManagerPageTriggers",
    "TrayManagerTriggers", "MainWindowTriggersSingle", "MainWindowTriggersMulti",
]
