# layout/multi/statistics.py

from PyQt6.QtWidgets import QStackedWidget
from PyQt6.QtCore import Qt

from ..common import build_master_detail_splitter
from ..statistics import StatisticsPanel, StatisticsPageBase
from .monitor_target_list import MonitorTargetListPage

TARGET_LIST_STRETCH = (25, 75)     # 좌 "수집 대상" : 우 통계 = 2.5 : 7.5 (데이터 정제 화면과 동일)
TARGET_LIST_INITIAL_SIZES = [250, 750]


class StatisticsPageMulti(StatisticsPageBase):
    """다중 레이아웃의 통계 분석 페이지 — 좌측 "수집 대상" 목록에서 고른 블루프린트의
    통계만 우측에 보여준다. 패널은 처음 선택될 때 만든다. 목록 클릭(target_list.
    blueprint_selected)은 메인 창이 활성 블루프린트 전환으로 받아 select_blueprint를 호출한다."""

    def __init__(self):
        self.target_list = MonitorTargetListPage()
        self._panel_slot = QStackedWidget()
        self._panels = {}
        self._active_seq_no = None

        split = build_master_detail_splitter(
            self.target_list, self._panel_slot, Qt.Orientation.Horizontal,
            stretch=TARGET_LIST_STRETCH,
        )
        split.setSizes(TARGET_LIST_INITIAL_SIZES)
        super().__init__(split)

    def select_blueprint(self, seq_no) -> None:
        """선택 블루프린트의 패널로 전환하고 목록 강조를 맞춘다."""
        if seq_no not in self._panels:
            panel = StatisticsPanel(seq_no)
            panel.set_collecting(self._collecting)
            self._panels[seq_no] = panel
            self._panel_slot.addWidget(panel)
        self._active_seq_no = seq_no
        self.target_list.set_active_seq_no(seq_no)
        self._panel_slot.setCurrentWidget(self._panels[seq_no])
        self._panels[seq_no].reload()

    def _iter_panels(self):
        return self._panels.values()

    def _active_panel(self):
        return self._panels.get(self._active_seq_no)

    def set_status(self, seq_no, status: str) -> None:
        self.target_list.set_status(seq_no, status)
