# layout/multi/monitor.py

from copy import deepcopy

from ..single import MonitorPageSingle


class MonitorPageMulti(MonitorPageSingle):
    """단일과 동일하되 활성 블루프린트 조회만 오버라이드합니다."""

    def __init__(self, blueprint_info: dict):
        self.blueprint_info = deepcopy(blueprint_info)
        super().__init__()

    def _active_blueprint_info(self) -> dict:
        return self.blueprint_info
