# layout/multi/blueprint_list.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QScrollArea, QTableWidgetItem, QTableWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from conf import BlueprintStorage
from style import EqualSpacingTable
from ..common import parts, _blueprint_auth_method, _blueprint_requires_auth
from ..auth import AuthManagerPage
from .dashboard import DashboardPageMulti
from .monitor import MonitorPageMulti

# 블루프린트 실행 상태 라벨 — BlueprintListPage 상태 컬럼에서 사용
BLUEPRINT_STATUS_LABELS = {"idle": "대기", "running": "실행 중", "done": "완료"}


class BlueprintListPage(QWidget):
    """
    request_info.json에 등록된 모든 블루프린트를 한 화면에 표로 보여준다.
    URL·수집 방식·인증 방식 등 상세 정보를 한눈에 비교하는 목록이면서,
    동시에 순차 수집 대상을 고르는 화면이기도 하다.

    - 선택 컬럼이 아닌 셀 클릭: 그 블루프린트를 활성 블루프린트로 전환한다(화면은
      이 페이지에 그대로 머무름) → row_selected emit. 이후 우측 상단
      GlobalToolbarMulti의 "시작" 버튼을 누르면 그 블루프린트가 실행된다. 동시에
      그 행의 선택 컬럼 체크박스를 토글한다(클릭할 때마다 on/off 반전) — 다른
      행의 체크 상태에는 영향 없음.
    - 선택 컬럼: 여러 행을 동시에 체크할 수 있다(행 클릭으로도, 체크박스 직접
      클릭으로도 토글 가능). 행의 음영(배경 강조)은 Qt의 선택 상태가 아니라 이
      체크 상태로 직접 구동되어(_set_row_shaded), 체크된 행 여러 개가 동시에
      음영 처리될 수 있고 체크 해제 즉시 그 행의 음영도 함께 사라진다. 순차
      수집에 포함할 블루프린트를 체크 → "전체 수집" 클릭 시
      batch_start_requested emit. "모두 선택"은 현재 전체 체크 여부에 따라
      전체 선택/전체 해제를 토글한다. 체크 개수가 바뀔 때마다 selection_changed
      emit → 2개 이상 체크되면 MainWindowMulti가 상단 URL 입력창을 비운다
      (대상이 하나로 특정되지 않으므로).
    """

    row_selected = pyqtSignal(str)
    batch_start_requested = pyqtSignal(list)
    selection_changed = pyqtSignal()   # 선택 컬럼 체크 개수가 바뀔 때마다 emit

    _COLUMNS = ["NO", "제목", "URL", "방식", "데이터 형식", "인증", "렌더링", "상태", "선택"]
    _SEQ_NO_COL = 0   # seq_no를 Qt.ItemDataRole.UserRole로 보관하는 컬럼 (정렬돼도 유효)
    _CHECK_COL = 8

    def __init__(self):
        super().__init__()
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        tcw, tc = parts.card_widget("수집 목록")

        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()
        self._select_all_btn = parts.outline_btn("모두 선택")
        self._select_all_btn.clicked.connect(self._toggle_select_all)
        ctrl_row.addWidget(self._select_all_btn)
        self._batch_btn = parts.action_btn("전체 수집")
        self._batch_btn.setEnabled(False)
        self._batch_btn.clicked.connect(self._emit_batch_start)
        ctrl_row.addWidget(self._batch_btn)
        tc.addLayout(ctrl_row)

        self.table = EqualSpacingTable(parent=self, row_height=32, col_padding=10, hscroll_handle=50)
        # 행 음영은 Qt의 선택 상태가 아니라 체크박스 상태로 직접 구동한다
        # (_set_row_shaded) — 체크는 여러 행 동시에 가능하므로 Qt의 단일 선택
        # 하이라이트로는 표현할 수 없다. 네이티브 선택 하이라이트는 꺼둔다.
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setColumnCount(len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.itemClicked.connect(self._on_item_clicked)
        tc.addWidget(self.table)
        bl.addWidget(tcw, 1)

    def refresh(self) -> None:
        """BlueprintStorage에서 다시 읽어 테이블을 재구성한다."""
        blueprints = BlueprintStorage().list_blueprints()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for i, bp in enumerate(blueprints):
            conditions = bp.get("conditions") or {}
            auth_method = _blueprint_auth_method(bp) or "-"
            rendering = "Y" if conditions.get("rendering") else "N"

            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                str(i + 1),
                bp.get("title") or "",
                bp.get("url") or "",
                conditions.get("method") or "",
                conditions.get("dataFormat") or "",
                auth_method,
                rendering,
                BLUEPRINT_STATUS_LABELS["idle"],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setForeground(Qt.GlobalColor.white if col == 1 else Qt.GlobalColor.lightGray)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == self._SEQ_NO_COL:
                    # 정렬 후에도 item.row()로 항상 올바른 seq_no를 찾을 수 있도록
                    # 실제 식별자를 UserRole에 보관 (표시 텍스트인 NO와는 별개).
                    item.setData(Qt.ItemDataRole.UserRole, bp.get("seq_no"))
                self.table.setItem(row, col, item)

            # 체크박스를 컬럼 가운데 정렬하기 위해 아이템(ItemIsUserCheckable) 대신
            # 실제 QCheckBox를 setCellWidget으로 배치한다 — QAbstractItemView의 체크
            # 인디케이터는 항상 셀의 왼쪽 가장자리에 고정 배치되어 QSS(subcontrol-position)로도
            # 가운데 정렬이 불가능하기 때문(위젯 레이아웃 정렬만이 확실하게 동작함).
            checkbox = QCheckBox()
            check_wrap = QWidget()
            check_wrap.checkbox = checkbox  # _checkbox_at()/_row_of()가 탐색 없이 바로 꺼내 씀
            # QWidget은 기본적으로 QSS의 background를 그리지 않고(WA_StyledBackground
            # 필요), 그걸 켜도 parts.card_widget()가 카드에 건 범용 QWidget{border:...;
            # background:...} 규칙이 자기 스타일시트 없는 자식까지 상속시켜 캡슐형
            # 배경으로 보일 수 있다 — 두 문제를 한번에 인스턴스 단위 리셋으로 막는다.
            check_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            check_wrap.setStyleSheet("QWidget { background: transparent; border: none; }")
            # 헤더 클릭으로 테이블이 재정렬되면 행 번호가 바뀌므로, 토글 시점마다
            # 이 위젯이 "현재" 몇 번째 행에 있는지 다시 찾는다(row를 직접 캡처하면
            # 정렬 후 엉뚱한 행이 반응하는 버그가 생김).
            checkbox.toggled.connect(lambda checked, w=check_wrap: self._on_check_toggled(self._row_of(w), checked))
            wrap_layout = QHBoxLayout(check_wrap)
            wrap_layout.setContentsMargins(0, 0, 0, 0)
            # 양쪽에 stretch를 둬야 체크박스(기본 Minimum 정책 — stretch가 없으면
            # 셀 전체 너비로 늘어나 버림)가 제 크기를 유지한 채 정중앙에 위치한다.
            wrap_layout.addStretch()
            wrap_layout.addWidget(checkbox)
            wrap_layout.addStretch()
            self.table.setCellWidget(row, self._CHECK_COL, check_wrap)

        self.table.setSortingEnabled(True)
        self._update_batch_btn()
        self.selection_changed.emit()   # 재구성으로 선택 개수가 0으로 리셋됐음을 알림

    def set_status(self, seq_no, status: str) -> None:
        """실행 상태를 이 테이블의 상태 컬럼에 반영한다 (idle/running/done)."""
        label = BLUEPRINT_STATUS_LABELS.get(status, BLUEPRINT_STATUS_LABELS["idle"])
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, self._SEQ_NO_COL)
            if id_item and id_item.data(Qt.ItemDataRole.UserRole) == seq_no:
                status_item = self.table.item(row, self._COLUMNS.index("상태"))
                if status_item is not None:
                    status_item.setText(label)
                return

    def _checkbox_at(self, row: int) -> QCheckBox | None:
        """선택 컬럼 셀 위젯(래퍼) 안의 실제 QCheckBox를 반환한다."""
        wrap = self.table.cellWidget(row, self._CHECK_COL)
        return wrap.checkbox if wrap else None

    def _row_of(self, wrap: QWidget) -> int:
        """정렬로 행 순서가 바뀌어도 이 셀 위젯이 현재 위치한 행 번호를 찾는다."""
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, self._CHECK_COL) is wrap:
                return row
        return -1

    def checked_seq_nos(self) -> list:
        """파일 순서를 보존한, 순차 수집에 포함(체크)된 seq_no 목록."""
        result = []
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_at(row)
            if checkbox and checkbox.isChecked():
                id_item = self.table.item(row, self._SEQ_NO_COL)
                if id_item:
                    result.append(id_item.data(Qt.ItemDataRole.UserRole))
        return result

    def _toggle_select_all(self) -> None:
        """현재 전체가 체크된 상태면 전체 해제, 아니면 전체 선택."""
        row_count = self.table.rowCount()
        if row_count == 0:
            return
        checkboxes = [self._checkbox_at(row) for row in range(row_count)]
        all_checked = all(cb.isChecked() for cb in checkboxes if cb)
        new_state = not all_checked
        for cb in checkboxes:
            if cb:
                cb.setChecked(new_state)

    def _update_batch_btn(self) -> None:
        self._batch_btn.setEnabled(len(self.checked_seq_nos()) > 0)

    def _emit_batch_start(self) -> None:
        self.batch_start_requested.emit(self.checked_seq_nos())

    def _set_row_shaded(self, row: int, shaded: bool) -> None:
        """
        체크박스 상태에 맞춰 그 행 전체(선택 컬럼 포함)의 배경 음영을 켜거나 끈다.

        QTableWidgetItem.setBackground()(BackgroundRole)는 이 테이블처럼 QSS에
        ::item 규칙이 걸려 있으면 무시된다 — 대신 앱 전역 QSS에 이미 정의된
        QTableWidget::item:selected 스타일(style.py GLOBAL_QSS)이 확실히 반영되는
        것을 이용해, Qt의 아이템 selected 상태를 체크 여부로 직접 구동한다.
        SelectionMode는 NoSelection이라 사용자의 클릭이 이 상태를 직접 바꾸지
        않고, 오직 이 메서드(=체크박스 상태)만이 selected 여부를 결정한다.
        """
        for col in range(self._CHECK_COL):
            item = self.table.item(row, col)
            if item:
                item.setSelected(shaded)
        wrap = self.table.cellWidget(row, self._CHECK_COL)
        if wrap:
            bg = self.table.theme.BG_HOVER if shaded else "transparent"
            wrap.setStyleSheet(f"QWidget {{ background: {bg}; border: none; }}")

    def _on_check_toggled(self, row: int, checked: bool) -> None:
        """선택 컬럼 체크박스 상태가 바뀔 때마다 호출 (체크박스 직접 클릭이든, 행 클릭에 의한 토글이든)."""
        self._set_row_shaded(row, checked)
        self._update_batch_btn()
        self.selection_changed.emit()

    def _on_item_clicked(self, item: QTableWidgetItem) -> None:
        # 선택 컬럼은 이제 setCellWidget(QCheckBox)라 이 아이템 자체가 없어
        # itemClicked가 그 컬럼에 대해선 애초에 발생하지 않는다 — 별도 가드 불필요.
        row = item.row()

        # 클릭한 행의 체크박스를 토글 — 다른 행의 체크 상태는 건드리지 않는다.
        checkbox = self._checkbox_at(row)
        if checkbox:
            checkbox.toggle()

        id_item = self.table.item(row, self._SEQ_NO_COL)
        seq_no = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if seq_no:
            self.row_selected.emit(seq_no)



class BlueprintPageBundle:
    """하나의 블루프린트(seq_no)에 귀속된 Dashboard/Monitor/Auth 페이지 묶음."""

    def __init__(self, blueprint_info: dict):
        self.seq_no = blueprint_info.get("seq_no")
        self.dashboard = DashboardPageMulti(blueprint_info)
        self.monitor_page = MonitorPageMulti(blueprint_info)
        self.auth_page = (
            AuthManagerPage(
                _blueprint_auth_method(blueprint_info),
                (blueprint_info.get("conditions") or {}).get("login"),
            )
            if _blueprint_requires_auth(blueprint_info) else None
        )
