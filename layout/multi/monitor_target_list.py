# layout/multi/monitor_target_list.py

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal

from conf import BlueprintStorage
from style import EqualSpacingTable
from ..common import parts, row_of_seq
from .blueprint_list import BLUEPRINT_STATUS_LABELS


class MonitorTargetListPage(QWidget):
    """
    "데이터 정제" 페이지 좌측에 놓이는 경량 블루프린트 목록.

    "수집 목록"(BlueprintListPage)과 달리 체크박스·⚙ 설정·수집 버튼 등 관리
    기능은 전혀 없고, 제목·상태만 보여주며 행 클릭으로 우측 4탭(Raw/정제규칙/
    정제결과/Before-After)이 보여줄 블루프린트를 고르는 용도로만 쓰인다.
    블루프린트는 런타임에 추가/삭제되지 않으므로(BlueprintListPage와 동일한
    전제) refresh()는 생성 시 1회만 호출한다.
    """

    blueprint_selected = pyqtSignal(str)

    _COLUMNS = ["Title", "Status"]
    _SEQ_NO_COL = 0

    def __init__(self):
        super().__init__()
        self._active_seq_no = None
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        # 좌우 14px — "수집 목록"(blueprint_list.py의 bl.setContentsMargins)과
        # 동일한 규칙으로, 카드 좌측 끝을 대시보드 페이지 카드들과 맞춘다.
        # 하단 14px — 오른쪽 "선택 항목 상세" 카드(build_scroll_body의 콘텐츠 하단
        # 여백 14px)와 이 카드의 하단선을 맞추기 위함. monitor_split(QSplitter)의
        # 좌/우 패널은 항상 같은 높이를 공유하므로, 여기서 하단 여백을 오른쪽과
        # 동일하게 맞추면 두 카드의 하단선이 정확히 일직선이 된다.
        root.setContentsMargins(14, 0, 14, 14)
        root.setSpacing(0)

        tcw, tc = parts.card_widget("수집 대상")

        self.table = EqualSpacingTable(parent=self, row_height=28, col_padding=10)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setColumnCount(len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.itemClicked.connect(self._on_item_clicked)
        tc.addWidget(self.table)

        root.addWidget(tcw, 1)

    def refresh(self) -> None:
        """BlueprintStorage에서 읽어 테이블을 재구성한다."""
        blueprints = BlueprintStorage().list_blueprints()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for bp in blueprints:
            seq_no = bp.get("seq_no")
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [bp.get("title") or "", BLUEPRINT_STATUS_LABELS["idle"]]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setForeground(Qt.GlobalColor.white if col == 0 else Qt.GlobalColor.lightGray)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == self._SEQ_NO_COL:
                    item.setData(Qt.ItemDataRole.UserRole, seq_no)
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        if self._active_seq_no is not None:
            self._apply_active_shade()

    def set_active_seq_no(self, seq_no) -> None:
        """활성 블루프린트가 바뀔 때(이 목록 클릭뿐 아니라 "수집 목록" 클릭이나
        실행 완료 후 자동 전환 등 다른 경로로 바뀐 경우도 포함) 강조를 갱신한다."""
        previous = self._active_seq_no
        self._active_seq_no = seq_no
        if previous is not None and previous != seq_no:
            self._set_row_shaded(self._row_of_seq(previous), False)
        self._apply_active_shade()

    def set_status(self, seq_no, status: str) -> None:
        """실행 상태(idle/running/done)를 상태 컬럼에 반영한다."""
        label = BLUEPRINT_STATUS_LABELS.get(status, BLUEPRINT_STATUS_LABELS["idle"])
        row = self._row_of_seq(seq_no)
        if row != -1:
            self.table.item(row, self._COLUMNS.index("Status")).setText(label)

    def _apply_active_shade(self) -> None:
        row = self._row_of_seq(self._active_seq_no)
        if row != -1:
            self._set_row_shaded(row, True)

    def _set_row_shaded(self, row: int, shaded: bool) -> None:
        if row == -1:
            return
        for col in range(len(self._COLUMNS)):
            item = self.table.item(row, col)
            if item:
                item.setSelected(shaded)

    def _row_of_seq(self, seq_no) -> int:
        return row_of_seq(self.table, seq_no, self._SEQ_NO_COL)

    def _on_item_clicked(self, item: QTableWidgetItem) -> None:
        id_item = self.table.item(item.row(), self._SEQ_NO_COL)
        seq_no = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if seq_no:
            self.blueprint_selected.emit(seq_no)
