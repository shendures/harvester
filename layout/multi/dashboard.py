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

    def _place_step_card(self, bl) -> None:
        """"작업 진행 상태" 행을 이 페이지 자신의 스크롤 영역에 넣지 않는다 — 대신
        main_window가 step_card_widget을 "수집 목록" 위쪽의 별도 스택(step_slot)에
        직접 마운트해, 모니터링 페이지 카드 순서를 "작업 진행 상태 → 수집 목록 →
        (이 페이지에 남은 나머지 카드들)"로 만든다."""
        # cfg(QHBoxLayout)의 기본 여백(9px)을 걷어내되, 좌우 14px은 다른 카드들
        # (bl.setContentsMargins(14, ..., 14, ...))과 동일하게 맞춰 왼쪽/오른쪽 끝선이
        # 일직선으로 정렬되게 한다. 위아래는 0으로 둔다 — main_window의
        # root.setSpacing()이 카드 사이 세로 간격을 전담한다.
        self.step_card_widget.layout().setContentsMargins(14, 0, 14, 0)

    def _configure_body_margins(self, bl) -> None:
        """다중은 위쪽 여백을 없앤다 — "수집 목록" 카드와의 경계 간격은
        main_window(step_slot 등이 붙는 root 레이아웃)의 spacing이 대신 공급한다."""
        bl.setContentsMargins(14, 0, 14, 14)
