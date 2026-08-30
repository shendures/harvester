# layout/multi/dashboard.py

from copy import deepcopy

from ..single import DashboardPageSingle


class DashboardPageMulti(DashboardPageSingle):
    def __init__(self, blueprint_info: dict):
        # super().__init__() 내부의 _build()가 _get_result_columns()를 호출할
        # 수 있으므로 순수 파이썬 속성을 먼저 바인딩한다 (Qt 메서드 호출 없음).
        self.blueprint_info = deepcopy(blueprint_info)
        super().__init__()

    def _active_blueprint_info(self) -> dict:
        return self.blueprint_info
