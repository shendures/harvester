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

    def _build_collect_settings_card(self, cfg) -> None:
        """"수집 & 저장 설정" 카드를 만들지 않는다 — 다중 레이아웃은 같은 설정을
        "수집 목록" 테이블의 "⚙" 버튼이 여는 다이얼로그로 옮겼다(BlueprintPageBundle.
        collect_settings 참고)."""
        pass
