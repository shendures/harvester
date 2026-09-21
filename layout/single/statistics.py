# layout/single/statistics.py

from ..statistics import StatisticsPanel, StatisticsPageBase


class StatisticsPageSingle(StatisticsPageBase):
    """단일 레이아웃의 통계 분석 페이지 — 전체 합산 패널 하나를 그대로 보여준다."""

    def __init__(self):
        self.panel = StatisticsPanel()
        super().__init__(self.panel)

    def _active_panel(self):
        return self.panel
