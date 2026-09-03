# layout/multi/blueprint_list.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QMessageBox,
    QScrollArea, QTableWidgetItem, QTableWidget, QMenu, QToolTip, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

from conf import BlueprintStorage, DEFAULT_COLLECT_SETTINGS
from style import EqualSpacingTable
from trigger.common import _default_msgbox_qss
from ..common import (
    parts, theme, RED, BG_HOVER, ACCENT, ACCENT_LIGHT, GREEN,
    _blueprint_auth_method, _blueprint_requires_auth, row_of_seq,
)
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

    수집 실행 트리거는 "전체"/"비전체"/"단일 행" 3가지다("비전체"는 몇 개를
    골랐는지 구분하지 않는다 — 1개든 여러 개든 동일하게 다룬다. "단일 행"은
    체크 여부와 무관하게 그 행 하나만 즉시 실행한다):

    - 선택 컬럼이 아닌 셀 클릭: 그 블루프린트를 활성 블루프린트로 전환한다(화면은
      이 페이지에 그대로 머무름) → row_selected emit. 체크박스는 전혀 건드리지
      않는다 — "보기"와 "수집 대상 선택"은 완전히 독립된 동작이다(여러 후보를
      체크해 둔 채 각각을 훑어봐도 선택이 사라지지 않는다).
    - 선택 컬럼 체크박스를 "직접" 클릭하면 다중 선택이 가능하다(독립 토글) —
      "비전체" 수집 대상을 고르는 유일한 방법이다.
    - "Run/Manage" 컬럼: "▶"(실행)·"⚙"(설정) 버튼이 이 순서로 나란히 들어있다.
      "▶"는 체크 상태와 무관하게 그 행의 블루프린트 하나만 즉시 실행한다 —
      batch_start_requested를 seq_no 1개짜리 리스트로 emit해 "선택 수집"/
      "전체 수집"과 동일한 순차 실행 큐를 그대로 공유한다(이미 다른 작업이
      실행 중이면 MainWindowMulti._start_batch가 이미 하는 대로 그 큐 뒤에
      순서대로 대기 — 이 버튼 자체에는 "중지" 토글이 없다). "⚙"는
      settings_requested(seq_no)를 emit — 그 블루프린트의 "수집 설정"
      (Delay/Threads/Timeout/Retry/Auto Save + 추출 설정 + 인증 관리)
      다이얼로그를 연다(화면 전환 없이 현재 페이지 위에 모달로만 뜬다).
    - 셀 우클릭: 컨텍스트 메뉴에서 "'<컬럼명>' 복사" 선택 시 그 셀의 텍스트만
      클립보드에 복사한다(행 전체가 아니라 클릭한 셀 하나). "Run/Manage"/"Select"
      컬럼은 텍스트 아이템이 없어 메뉴 자체가 뜨지 않는다.
    - "선택 수집" 버튼: 체크된 블루프린트만 순차 실행("비전체"). 체크 0개면 비활성화.
    - "전체 수집" 버튼: 체크 여부와 무관하게 먼저 모든 행을 체크 상태로 바꾼 뒤
      테이블의 모든 블루프린트를 순차 실행("전체").
    - 두 버튼 모두 실행을 시작하면 자기 자신이 "⬛ 중지"로 바뀌고(반대쪽 버튼은
      혼동을 막기 위해 잠시 비활성화), 자신이 시작한 대상들이 모두 끝나면
      (set_status로 감지) 원래 라벨로 되돌아온다 — 단일 레이아웃의 "▶ 시작"/
      "⬛ 중지" 토글(trigger/toolbar.py의 _toggle_run)과 동일한 관례. "중지" 클릭은
      stop_requested를 emit하고 완료 확인을 기다리지 않고 즉시 원래 라벨로
      되돌아간다(낙관적 UI).
    - 행의 음영(배경 강조)은 Qt의 선택 상태가 아니라 체크 상태로 직접
      구동된다(_set_row_shaded). 상단 URL 입력창은 체크 개수와 무관하며,
      "Run/Manage" 컬럼이 아닌 셀 클릭(row_selected)으로만 갱신된다.
    """

    row_selected = pyqtSignal(str)
    batch_start_requested = pyqtSignal(list)
    settings_requested = pyqtSignal(str)   # "Run/Manage" 컬럼의 "⚙" 버튼 클릭 시 emit(seq_no)
    stop_requested = pyqtSignal()          # 실행 중이던 [수집]/[전체 수집] 재클릭 시 emit

    _COLUMNS = ["NO", "Title", "URL", "Method", "Format", "Auth", "Render", "Status", "Run/Manage", "Select"]
    _SEQ_NO_COL = 0   # seq_no를 Qt.ItemDataRole.UserRole로 보관하는 컬럼 (정렬돼도 유효)
    _CHECK_COL = 9

    # 실행 중 버튼 스타일 — trigger/toolbar.py::_style_run_btn의 "중지" 배색과 동일.
    _STOP_QSS = f"""
        QPushButton {{
            background:#7f1d1d; color:{RED}; border:none; border-radius:6px;
            padding:6px 14px; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background:#991b1b; }}
    """

    # "설정"(⚙) 버튼 강조 스타일 — 무채색 outline_btn보다 눈에 띄도록 액센트
    # 테두리/글자색을 상시 적용하되, 반복되는 컬럼이라 꽉 찬 색상 블록은 피한다.
    _SETTINGS_BTN_QSS = f"""
        QPushButton {{
            background:{BG_HOVER}; color:{ACCENT_LIGHT}; border:1px solid {ACCENT_LIGHT};
            border-radius:6px; padding:0; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background:{ACCENT}; color:white; border-color:{ACCENT}; }}
    """

    # "실행"(▶) 버튼 강조 스타일 — "설정"(⚙, ACCENT)과 한눈에 구분되도록 GREEN
    # 계열로 색만 바꾼 동일 구조(둘 다 "행 단위 즉시 동작"이라는 성격은 같음).
    _RUN_BTN_QSS = f"""
        QPushButton {{
            background:{BG_HOVER}; color:{GREEN}; border:1px solid {GREEN};
            border-radius:6px; padding:0; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background:{GREEN}; color:white; border-color:{GREEN}; }}
    """

    # 행의 "▶"가 실행 중일 때 바뀌는 "■" 배색 — _STOP_QSS와 같은 배색이지만
    # 30x20 고정 아이콘 버튼에 맞춰 padding을 0으로 둔다(_STOP_QSS는 풀사이즈
    # 배치 버튼용이라 그대로 쓰면 패딩이 버튼 크기를 넘친다).
    _ROW_STOP_BTN_QSS = f"""
        QPushButton {{
            background:#7f1d1d; color:{RED}; border:none;
            border-radius:6px; padding:0; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background:#991b1b; }}
    """

    def __init__(self):
        super().__init__()
        self._active_run_btn = None        # 실행 중이라 "⬛ 중지"로 바뀐 버튼(없으면 None)
        self._pending_run_seq_nos = set()  # _active_run_btn이 책임지는, 아직 안 끝난 seq_no
        self._active_view_seq_no = None    # 마지막으로 클릭(보기)한 블루프린트 — 음영 표시용
        self._active_row_seq_no = None     # 지금 "■"로 바뀐 행(Run/Manage ▶ 버튼)의 seq_no
        self._run_btn_by_seq_no = {}       # seq_no -> 그 행의 ▶/■ 버튼(refresh()마다 재구성)
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        # "작업 진행 상태"·"수집 목록"·모니터링 상세 사이의 카드 간격을 모두
        # 통일한다(다중 대시보드의 카드 간 기준 간격인 bl.setSpacing(12)와 동일).
        root.setSpacing(12)
        self._root = root  # attach_step_panel이 맨 위에 끼워 넣을 때 참조

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        # 위/아래 여백은 0으로 둔다 — root.setSpacing(12)가 위(작업 진행 상태)·
        # 아래(모니터링 상세) 카드와의 간격을 전담하므로, 여기서 추가하면 간격이
        # 중복으로 벌어진다. 좌우 여백만 페이지 가장자리 여백으로 유지한다.
        bl.setContentsMargins(14, 0, 14, 0)
        bl.setSpacing(12)
        scroll.setWidget(body)

        # 목록(위, 고정 높이) / 모니터링 상세(아래, attach_detail_panel로 주입,
        # 나머지 공간 차지) — 사용자가 드래그로 비율을 바꿀 수 없도록 스플리터
        # 대신 고정 배치를 쓴다.
        scroll.setMaximumHeight(380)
        root.addWidget(scroll)

        tcw, tc = parts.card_widget("수집 목록")

        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()
        self._collect_btn = parts.action_btn("선택 수집")
        self._collect_btn_idle_qss = self._collect_btn.styleSheet()
        self._collect_btn.clicked.connect(self._on_collect_clicked)
        ctrl_row.addWidget(self._collect_btn)
        self._batch_btn = parts.action_btn("전체 수집")
        self._batch_btn_idle_qss = self._batch_btn.styleSheet()
        self._batch_btn.clicked.connect(self._on_collect_all_clicked)
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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_cell_context_menu)
        tc.addWidget(self.table)
        bl.addWidget(tcw, 1)

    def attach_step_panel(self, widget: QWidget) -> None:
        """활성 블루프린트의 "작업 진행 상태"(main_window의 step_slot)를 목록 위쪽에
        결합한다 — attach_progress_panel이 반드시 이 호출 뒤에 다시 맨 위(0)에 끼워
        넣어야 최종 카드 순서가 "대기중 상태바 → 작업 진행 상태 → 수집 목록 →
        (나머지)"가 된다."""
        self._root.insertWidget(0, widget)

    def attach_progress_panel(self, widget: QWidget) -> None:
        """활성 블루프린트의 "대기중 상태바"(main_window의 progress_slot)를 맨 위(0)에
        결합한다 — attach_step_panel보다 나중에 호출해야 "작업 진행 상태" 카드보다
        위에 놓인다."""
        self._root.insertWidget(0, widget)

    def attach_detail_panel(self, widget: QWidget) -> None:
        """활성 블루프린트의 모니터링 상세(main_window의 dashboard_slot)를 목록 아래에
        결합한다 — 남는 세로 공간을 모두 차지한다(stretch=1)."""
        self._root.addWidget(widget, 1)

    def refresh(self) -> None:
        """BlueprintStorage에서 다시 읽어 테이블을 재구성한다."""
        blueprints = BlueprintStorage().list_blueprints()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        # setRowCount(0)이 기존 셀 위젯을 모두 파괴하므로, 그 안의 ▶/■ 버튼을
        # 가리키던 참조도 함께 무효화된다 — 새로 만들며 채운다.
        self._run_btn_by_seq_no = {}

        for i, bp in enumerate(blueprints):
            conditions = bp.get("conditions") or {}
            auth_method = _blueprint_auth_method(bp) or "-"
            rendering = "Y" if conditions.get("rendering") else "N"
            seq_no = bp.get("seq_no")

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
                    item.setData(Qt.ItemDataRole.UserRole, seq_no)
                self.table.setItem(row, col, item)

            # "Run/Manage" 컬럼 — "▶"(실행)·"⚙"(설정) 두 아이콘 버튼을 이 순서로 한
            # 셀에 나란히 배치한다. "▶"는 체크 여부와 무관하게 이 블루프린트
            # 하나만 즉시 실행한다(batch_start_requested를 seq_no 1개짜리
            # 리스트로 emit해 "선택 수집"/"전체 수집"과 동일한 순차 실행 큐를
            # 그대로 재사용 — 새 실행 로직 불필요). 이 블루프린트가 실제로
            # 실행 중이면 같은 버튼이 "■"(중지)로 바뀐다(_on_row_run_btn_clicked/
            # set_status 참고). "⚙"는 수집 설정 다이얼로그를 연다. seq_no를
            # 클로저로 직접 캡처해 동작하므로(체크박스와 달리) 정렬로 행 순서가
            # 바뀌어도 재탐색이 필요 없다.
            action_wrap, action_buttons = self._make_action_button_cell([
                ("▶", "이 블루프린트만 즉시 수집",
                 lambda _, s=seq_no: self._on_row_run_btn_clicked(s), self._RUN_BTN_QSS),
                ("⚙", "수집 설정",
                 lambda _, s=seq_no: self.settings_requested.emit(s), self._SETTINGS_BTN_QSS),
            ])
            self.table.setCellWidget(row, self._COLUMNS.index("Run/Manage"), action_wrap)
            run_btn = action_buttons[0]
            self._run_btn_by_seq_no[seq_no] = run_btn
            self._style_row_run_btn(run_btn, running=(seq_no == self._active_row_seq_no))

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
        has_rows = self.table.rowCount() > 0
        self._collect_btn.setEnabled(has_rows)
        self._batch_btn.setEnabled(has_rows)
        if self._active_view_seq_no is not None:
            row = self._row_of_seq(self._active_view_seq_no)
            if row != -1:
                self._apply_row_shade(row)
            else:
                self._active_view_seq_no = None  # 목록에서 사라진 블루프린트면 추적 해제

    def set_status(self, seq_no, status: str) -> None:
        """실행 상태를 이 테이블의 상태 컬럼에 반영한다(idle/running/done). 이
        seq_no가 지금 실행 중인 [수집]/[전체 수집] 버튼이 책임지는 대상이었다면,
        완료(done/idle) 시 그 버튼을 원래 라벨로 되돌리는 트리거로도 쓰인다.
        같은 seq_no의 행 자체(▶/■) 버튼도 이 상태를 그대로 따라간다 — running이면
        "■"로, done/idle이면(자연 종료) "▶"로. 상단 배치 버튼과 달리 이 행의
        복귀는 다른 대기 seq_no와 무관하게 독립적으로 일어난다(_pending_run_seq_nos
        전체가 아니라 이 seq_no 하나만 보면 되므로)."""
        label = BLUEPRINT_STATUS_LABELS.get(status, BLUEPRINT_STATUS_LABELS["idle"])
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, self._SEQ_NO_COL)
            if id_item and id_item.data(Qt.ItemDataRole.UserRole) == seq_no:
                status_item = self.table.item(row, self._COLUMNS.index("Status"))
                if status_item is not None:
                    status_item.setText(label)
                break

        if status == "running":
            self._active_row_seq_no = seq_no
            run_btn = self._run_btn_by_seq_no.get(seq_no)
            if run_btn is not None:
                self._style_row_run_btn(run_btn, running=True)
        elif status in ("done", "idle"):
            if seq_no == self._active_row_seq_no:
                self._revert_row_run_btn()
            self._pending_run_seq_nos.discard(seq_no)
            if self._active_run_btn is not None and not self._pending_run_seq_nos:
                self._revert_active_run_btn()

    def _make_action_button_cell(self, specs: list) -> tuple[QWidget, list]:
        """아이콘 전용 버튼 1개 이상(예: ▶ 실행 + ⚙ 설정)을 체크박스와 동일한
        방식(투명 배경 래퍼 + 좌우 stretch로 중앙 정렬)으로 한 셀에 나란히
        배치한다. specs는 (text, tooltip, on_click, qss) 튜플 목록이며, 순서
        그대로 왼쪽부터 배치된다. (래퍼 위젯, specs 순서와 동일한 QPushButton
        리스트)를 반환한다 — 호출부가 버튼 참조를 보관해 나중에 텍스트/스타일을
        바꿀 수 있도록 한다(행의 ▶→■ 토글 등)."""
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet("QWidget { background: transparent; border: none; }")
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(4)
        wrap_layout.addStretch()
        buttons = []
        for text, tooltip, on_click, qss in specs:
            btn = parts.outline_btn(text)
            # 셀 위젯은 Qt가 행 높이(row_height=32)에서 상하 여백을 뺀 자리에
            # 배치하므로 실사용 가능한 높이는 32px가 아니라 약 20px다 — 24px로
            # 고정하면 버튼 하단이 그 여백에 가려 잘려 보인다(체크박스는 16px라
            # 문제없었음). 20px로 맞춰 잘림 없이 셀 안에 온전히 들어가게 한다.
            btn.setFixedSize(30, 20)
            btn.setToolTip(tooltip)
            btn.clicked.connect(on_click)
            btn.setStyleSheet(qss)
            wrap_layout.addWidget(btn)
            buttons.append(btn)
        wrap_layout.addStretch()
        return wrap, buttons

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

    def _warn_no_selection(self) -> None:
        """"선택 수집" 클릭 시 체크된 대상이 없으면 안내 — 앱 전역에서 반복 쓰이는
        다크 테마 QMessageBox 스타일(_default_msgbox_qss)을 그대로 재사용한다."""
        msg = QMessageBox(self)
        msg.setWindowTitle("수집 대상 없음")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("수집 대상을 선택한 뒤 수집을 진행해 주세요.")
        msg.setStyleSheet(_default_msgbox_qss())
        msg.exec()

    def _on_collect_clicked(self) -> None:
        """"선택 수집" 버튼 — 평소엔 체크된 것만 실행("비전체"), 자기 자신이 실행 중
        (="⬛ 중지" 상태)일 땐 같은 버튼이 중지 역할을 한다(trigger/toolbar.py의
        _toggle_run과 동일한 토글 패턴). 체크된 게 없으면 막는 대신(비활성화)
        선택을 안내한다 — 버튼은 항상 눌러볼 수 있게 열어둔다."""
        if self._active_run_btn is self._collect_btn:
            self.stop_requested.emit()
            self._revert_run_controls()
            return
        seq_nos = self.checked_seq_nos()
        if not seq_nos:
            self._warn_no_selection()
            return
        self._activate_run_btn(self._collect_btn, seq_nos)
        self.batch_start_requested.emit(seq_nos)

    def _on_collect_all_clicked(self) -> None:
        """"전체 수집" 버튼 — 평소엔 체크 여부와 무관하게 먼저 모든 행을 체크
        상태로 바꾼 뒤("전체가 선택됨"을 화면에 반영) 테이블 전체를 실행("전체").
        자기 자신이 실행 중일 땐 중지 역할."""
        if self._active_run_btn is self._batch_btn:
            self.stop_requested.emit()
            self._revert_run_controls()
            return
        all_seq_nos = []
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_at(row)
            if checkbox:
                checkbox.setChecked(True)
            id_item = self.table.item(row, self._SEQ_NO_COL)
            if id_item:
                all_seq_nos.append(id_item.data(Qt.ItemDataRole.UserRole))
        self._activate_run_btn(self._batch_btn, all_seq_nos)
        self.batch_start_requested.emit(all_seq_nos)

    def _activate_run_btn(self, btn, seq_nos: list) -> None:
        """실행을 시작한 버튼을 "⬛ 중지" 상태로 바꾸고, 반대쪽 버튼은 혼동을
        막기 위해 잠시 비활성화한다. seq_nos에 대한 완료 소식이 모두 도착하면
        (set_status) 자동으로 원래대로 되돌아간다."""
        self._active_run_btn = btn
        self._pending_run_seq_nos = set(seq_nos)
        other = self._batch_btn if btn is self._collect_btn else self._collect_btn
        other.setEnabled(False)
        btn.setText("⬛  중지")
        btn.setStyleSheet(self._STOP_QSS)

    def _revert_active_run_btn(self) -> None:
        """실행 중이던 버튼을 원래 라벨/스타일로 되돌린다 — 배치가 자연 종료됐거나
        (set_status로 감지) 사용자가 직접 "중지"를 눌렀을 때(즉시, 낙관적으로) 호출."""
        btn = self._active_run_btn
        if btn is None:
            return
        self._active_run_btn = None
        self._pending_run_seq_nos = set()
        if btn is self._collect_btn:
            btn.setText("선택 수집")
            btn.setStyleSheet(self._collect_btn_idle_qss)
        else:
            btn.setText("전체 수집")
            btn.setStyleSheet(self._batch_btn_idle_qss)
        has_rows = self.table.rowCount() > 0
        self._collect_btn.setEnabled(has_rows)
        self._batch_btn.setEnabled(has_rows)

    def _style_row_run_btn(self, btn, running: bool) -> None:
        """행의 ▶/■ 버튼 모양을 실행/중지 상태에 맞춰 맞춘다 — 상단 배치 버튼의
        "⬛ 중지" 배색(_STOP_QSS)과 동일한 관례를 30x20 아이콘 버튼에 적용한다."""
        if running:
            btn.setText("■")
            btn.setToolTip("이 블루프린트 수집 중지")
            btn.setStyleSheet(self._ROW_STOP_BTN_QSS)
        else:
            btn.setText("▶")
            btn.setToolTip("이 블루프린트만 즉시 수집")
            btn.setStyleSheet(self._RUN_BTN_QSS)

    def _on_row_run_btn_clicked(self, seq_no) -> None:
        """"Run/Manage" 컬럼의 ▶ 버튼 — 이 행이 이미 실행 중(="■"로 바뀐 상태)이면
        그 버튼 자체가 중지 역할을 한다(선택 수집/전체 수집과 동일한 토글 관례,
        전역 중지와 완전히 동일하게 동작 — 워커가 하나뿐이라 "이 행만 중지"는
        곧 "지금 도는 작업을 중지"와 같다). 아니면 이 블루프린트 하나만 즉시
        실행 큐에 넣는다. 지금 아무것도 실행 중이 아니라 이 클릭이 대기 없이
        바로 시작으로 이어지는 경우에는(다른 배치/행이 하나도 활성 상태가
        아닐 때) 상단 배치 버튼과 동일하게 낙관적으로 먼저 "■"로 바꿔 둔다 —
        이미 무언가 실행 중이라 이번 클릭이 대기열에만 쌓이는 경우에는 실제로
        그 차례가 와 set_status("running")을 받을 때까지 "▶"를 유지한다."""
        if seq_no == self._active_row_seq_no:
            self.stop_requested.emit()
            self._revert_run_controls()
            return
        if self._active_row_seq_no is None and self._active_run_btn is None:
            self._active_row_seq_no = seq_no
            run_btn = self._run_btn_by_seq_no.get(seq_no)
            if run_btn is not None:
                self._style_row_run_btn(run_btn, running=True)
        self.batch_start_requested.emit([seq_no])

    def _revert_row_run_btn(self) -> None:
        """실행 중이던 행 버튼만 원래 "▶" 상태로 되돌린다."""
        if self._active_row_seq_no is None:
            return
        run_btn = self._run_btn_by_seq_no.get(self._active_row_seq_no)
        if run_btn is not None:
            self._style_row_run_btn(run_btn, running=False)
        self._active_row_seq_no = None

    def _revert_run_controls(self) -> None:
        """상단 배치 버튼과 행 버튼을 한꺼번에 원래 상태로 되돌린다 — 워커가
        하나뿐이라 사용자가 무엇을 눌러 중지했든(행의 ■든 배치 버튼의 ⬛든)
        항상 함께 되돌아간다. 사용자가 직접 중지를 눌렀을 때만 쓴다(낙관적
        UI, 완료 확인을 기다리지 않음) — 수집이 자연 종료됐을 때는 set_status()가
        각자 알아서(_revert_active_run_btn/_revert_row_run_btn을 독립적으로) 처리한다."""
        self._revert_active_run_btn()
        self._revert_row_run_btn()

    def _set_row_shaded(self, row: int, shaded: bool) -> None:
        """
        체크 또는 열람 상태에 맞춰 그 행 전체(선택 컬럼 포함)의 배경 음영을
        켜거나 끈다(_apply_row_shade가 두 상태를 하나로 합쳐 이 메서드를 호출).

        QTableWidgetItem.setBackground()(BackgroundRole)는 이 테이블처럼 QSS에
        ::item 규칙이 걸려 있으면 무시된다 — 대신 앱 전역 QSS에 이미 정의된
        QTableWidget::item:selected 스타일(style.py GLOBAL_QSS)이 확실히 반영되는
        것을 이용해, Qt의 아이템 selected 상태를 직접 구동한다. SelectionMode는
        NoSelection이라 사용자의 클릭이 이 상태를 직접 바꾸지 않고, 오직 이
        메서드만이 selected 여부를 결정한다.
        """
        for col in range(self._CHECK_COL):
            item = self.table.item(row, col)
            if item:
                item.setSelected(shaded)
        wrap = self.table.cellWidget(row, self._CHECK_COL)
        if wrap:
            bg = self.table.theme.BG_HOVER if shaded else "transparent"
            wrap.setStyleSheet(f"QWidget {{ background: {bg}; border: none; }}")

    def _row_of_seq(self, seq_no) -> int:
        """seq_no가 위치한 현재 행 번호를 찾는다(정렬 후에도 안전). 없으면 -1."""
        return row_of_seq(self.table, seq_no, self._SEQ_NO_COL)

    def _apply_row_shade(self, row: int) -> None:
        """지금 보고 있는 행(_active_view_seq_no)일 때만 음영을 켠다 — 체크박스
        선택 여부는 체크 표시 자체로 이미 드러나므로 음영에 영향을 주지 않는다."""
        id_item = self.table.item(row, self._SEQ_NO_COL)
        seq_no = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        is_viewing = seq_no is not None and seq_no == self._active_view_seq_no
        self._set_row_shaded(row, is_viewing)

    def _on_check_toggled(self, row: int, checked: bool) -> None:
        """선택 컬럼 체크박스 상태가 바뀔 때마다 호출(체크박스 직접 클릭으로만
        발생 — 행 클릭은 더 이상 체크박스를 건드리지 않는다)."""
        self._apply_row_shade(row)

    def _on_item_clicked(self, item: QTableWidgetItem) -> None:
        # 선택 컬럼은 이제 setCellWidget(QCheckBox)라 이 아이템 자체가 없어
        # itemClicked가 그 컬럼에 대해선 애초에 발생하지 않는다 — 별도 가드 불필요.
        row = item.row()

        # 행(체크박스 제외 셀) 클릭은 그 블루프린트를 보여주면서 그 행 전체를
        # 음영으로 표시한다("지금 보고 있는 행" 피드백) — 체크박스는 전혀
        # 건드리지 않는다("보기"와 "수집 대상 선택"을 완전히 독립시켜, 여러
        # 후보를 체크해 둔 채 각각을 훑어봐도 선택이 사라지지 않게 함).
        id_item = self.table.item(row, self._SEQ_NO_COL)
        seq_no = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None

        previous = self._active_view_seq_no
        self._active_view_seq_no = seq_no
        if previous and previous != seq_no:
            prev_row = self._row_of_seq(previous)
            if prev_row != -1:
                self._apply_row_shade(prev_row)
        self._apply_row_shade(row)

        if seq_no:
            self.row_selected.emit(seq_no)

    def _show_cell_context_menu(self, pos) -> None:
        """셀 우클릭 — 클릭한 셀 하나의 텍스트만 클립보드에 복사하는 메뉴를 띄운다
        (프록시 테이블의 우클릭 메뉴 패턴과 동일한 뼈대: trigger/session.py의
        _proxy_table_context_menu 참고). "Run/Manage"/"Select" 컬럼은 cellWidget이라
        텍스트 아이템이 없으므로(item is None) 메뉴 자체를 띄우지 않는다."""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row, col = index.row(), index.column()
        item = self.table.item(row, col)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(theme.PROXY_CONTEXT_MENU_QSS)
        copy_act = menu.addAction(f"'{self._COLUMNS[col]}' 복사")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == copy_act:
            QApplication.clipboard().setText(item.text())
            QToolTip.showText(QCursor.pos(), "클립보드에 복사되었습니다", self.table)


class BlueprintPageBundle:
    """하나의 블루프린트(seq_no)에 귀속된 Dashboard/Monitor/Auth 페이지 묶음.

    collect_settings: "수집 & 저장 설정"(Delay/Threads/Timeout/Retry/Auto Save) 값을
    보관하는 dict — 다중 대시보드에는 이 카드가 없으므로(요구사항 2), "⚙" 다이얼로그가
    열릴 때마다 이 dict을 읽고, 적용 시 이 dict에 되써넣는다(monitor_page.output_info
    ["extract"]와 동일한 패턴). auth_page는 인증 관리 사이드바 페이지로는 더 이상
    쓰이지 않고(요구사항 3), "⚙" 다이얼로그가 열릴 때만 그 위젯을 다이얼로그에
    잠깐 얹었다가(reparent) 닫힐 때 다시 떼어내는 방식으로 재사용된다."""

    def __init__(self, blueprint_info: dict):
        self.seq_no = blueprint_info.get("seq_no")
        self.dashboard = DashboardPageMulti(blueprint_info)
        self.monitor_page = MonitorPageMulti(blueprint_info)
        self.collect_settings = blueprint_info.get("collect_settings") or dict(DEFAULT_COLLECT_SETTINGS)
        self.auth_page = (
            AuthManagerPage(
                _blueprint_auth_method(blueprint_info),
                (blueprint_info.get("conditions") or {}).get("login"),
            )
            if _blueprint_requires_auth(blueprint_info) else None
        )
