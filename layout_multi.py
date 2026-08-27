# layout_multi.py
# 다중 블루프린트(2개 이상 순차 배치 수집) 레이아웃 — 단일 수집 레이아웃
# (layout_single.py)과의 크로스체크를 위한 병행 구현입니다. 단일 수집
# 레이아웃은 수정하지 않고 그대로 유지하며, 이 파일은 그 페이지 클래스를
# 상속해 "블루프린트별 인스턴스(번들)"로 확장합니다. 실행: python main.py --multi
#
# 구조 요약
#   - DashboardPageMulti/MonitorPageMulti : 결과 컬럼을 전역 request_info가 아닌
#     생성 시 주입된 blueprint_info 기준으로 구성
#   - GlobalToolbarMulti                  : 활성 블루프린트 전환 시 URL/method 갱신
#   - BlueprintListPage                   : 등록된 모든 블루프린트 표시 + 배치 선택/시작
#   - SidebarMulti                        : 네비게이터 전용(블루프린트 목록/선택은 위 페이지로 이전)
#   - BlueprintPageBundle                 : seq_no 1개에 귀속된 페이지 묶음
#   - MainWindowMulti                     : 번들 캐시 + QStackedWidget 슬롯 교체
from copy import deepcopy

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QCheckBox,
    QStackedWidget, QMessageBox,
    QScrollArea, QTableWidgetItem, QTableWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from conf import BlueprintStorage
from style import NavItem, EqualSpacingTable
from trigger import LogViewerDialog, MainWindowTriggersMulti
from layout_single import (
    DashboardPageSingle, MonitorPageSingle, AuthManagerPage, SchedulerPage,
    SessionSettingsPage, StatisticsPage, GlobalToolbarSingle, SidebarSingle,
    TrayManager, build_status_bar,
    _blueprint_auth_method, _blueprint_requires_auth,
    parts,
    BG_SECONDARY, ACCENT_LIGHT, BORDER,
)

# 블루프린트 실행 상태 라벨 — BlueprintListPage 상태 컬럼에서 사용
BLUEPRINT_STATUS_LABELS = {"idle": "대기", "running": "실행 중", "done": "완료"}


def result_columns_from_blueprint(blueprint_info: dict) -> list:
    """
    블루프린트의 conditions.items 키에서 결과 테이블 컬럼 목록을 구성합니다.
    (단일 DashboardPageSingle/MonitorPageSingle._get_result_columns()와 동일 규칙 —
    다중에서는 전역 request_info 대신 인자로 받은 블루프린트를 사용)
    """
    try:
        items = list(blueprint_info["conditions"]["items"].keys())
        return [c for c in items if c not in ("root", "detail_root", "main_root", "detail")]
    except (KeyError, TypeError):
        return []


# ══════════════════════════════════════════════════════
#  블루프린트 귀속 페이지 (단일 페이지 상속)
# ══════════════════════════════════════════════════════
class DashboardPageMulti(DashboardPageSingle):
    def __init__(self, blueprint_info: dict):
        # super().__init__() 내부의 _build()가 _get_result_columns()를 호출할
        # 수 있으므로 순수 파이썬 속성을 먼저 바인딩한다 (Qt 메서드 호출 없음).
        self.blueprint_info = deepcopy(blueprint_info)
        super().__init__()

    def _get_result_columns(self):
        return result_columns_from_blueprint(self.blueprint_info)


class MonitorPageMulti(MonitorPageSingle):
    def __init__(self, blueprint_info: dict):
        self.blueprint_info = deepcopy(blueprint_info)
        super().__init__()

    def _get_result_columns(self):
        return result_columns_from_blueprint(self.blueprint_info)

    def preprocess(self, task):
        """
        단일과 동일하되 무인 판정에 "배치 실행"을 추가 — 배치 도중 블로킹
        모달이 떠서 다음 순번이 시작되지 못하는 것을 방지합니다.
        """
        self._current_task = task or {}
        self._cleaning_warned = False

        if not self._collected_data:
            if (task or {}).get("job") in ("스케줄 실행", "배치 실행"):
                lm = getattr(self.window(), "log_manager", None)
                if lm:
                    lm.append_log("warn", "무인 실행 — 수집된 데이터가 없어 추출/정제를 건너뜁니다.")
            else:
                QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return


# ══════════════════════════════════════════════════════
#  BLUEPRINT LIST PAGE — 등록된 모든 블루프린트를 표로 표시
# ══════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════
#  GLOBAL TOOLBAR (다중) — 활성 블루프린트 전환 지원
# ══════════════════════════════════════════════════════
class GlobalToolbarMulti(GlobalToolbarSingle):
    """
    단일과 동일한 구성이지만, method 라벨을 인스턴스 속성으로 보관해
    activate_blueprint()로 활성 블루프린트 전환 시 갱신할 수 있게 합니다.
    """

    def _build(self):
        info = BlueprintStorage().read()

        self.setFixedHeight(49)
        self.setStyleSheet(
            f"background:{BG_SECONDARY}; border-bottom:1px solid {BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # 수집 방식 라벨 (전환 갱신을 위해 참조 보관 — 단일과의 차이점)
        # 2개 이상 선택 시 빈 값으로 바뀌는데, 폭을 고정해두지 않으면 라벨이
        # 줄어들면서 옆 URL 입력창이 왼쪽으로 밀려온다 — 최장 메서드
        # 문자열("OPTIONS") 기준으로 폭을 고정해 빈 값이어도 자리를 유지한다.
        self._method_label = parts.make_label(
            (info.get("conditions") or {}).get("method") or "", ACCENT_LIGHT, 12, True)
        self._method_label.setFixedWidth(60)
        lay.addWidget(self._method_label)

        # URL 입력창
        self.url_input = QLineEdit(info.get("url") or "")
        self.url_input.setCursorPosition(0)
        lay.addWidget(self.url_input, 1)

        # URL 복사 버튼
        self._copy_btn = parts.outline_btn("URL 복사")
        self._copy_btn.clicked.connect(self._copy_url)
        lay.addWidget(self._copy_btn)

        # 시작 / 중지 버튼
        self.run_btn = QPushButton("▶  시작")
        self.run_btn.setFixedWidth(90)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._toggle_run)
        self._style_run_btn(False)
        lay.addWidget(self.run_btn)

        # 추출 설정 버튼 (Raw/정제 탭에 각각 있던 동일 다이얼로그 진입점을 통합)
        self._output_settings_btn = parts.settings_btn("⚙  추출 설정")
        self._output_settings_btn.clicked.connect(self._open_output_settings)
        lay.addWidget(self._output_settings_btn)

    def activate_blueprint(self, blueprint_info: dict) -> None:
        """활성 블루프린트 전환 시 상단 method 라벨/URL 입력창만 갱신합니다."""
        self._method_label.setText(
            (blueprint_info.get("conditions") or {}).get("method") or "")
        self.url_input.setText(blueprint_info.get("url") or "")
        self.url_input.setCursorPosition(0)


# ══════════════════════════════════════════════════════
#  SIDEBAR (다중) — 네비게이터 (블루프린트 목록/선택은 BlueprintListPage로 이전)
# ══════════════════════════════════════════════════════
class SidebarMulti(SidebarSingle):
    """
    SidebarSingle의 뼈대(로고·구분선·상태줄·_add_nav_btn/_on_nav)를 그대로
    상속하고, 항목 목록만 다중 수집에 맞게 오버라이드한다.
    """

    # (아이콘, 라벨, 스택 인덱스) — 스택 인덱스는 단일 공유 코드(trigger.py의
    # _switch_page가 idx==3일 때 stats_page.reload()를 호출하는 등)가 전제하는
    # 고정값(0 대시보드/1 모니터링/2 스케줄러/3 통계 분석/4 세션 설정/5 인증
    # 관리)과 반드시 일치해야 한다. "수집 목록"은 그 전제를 건드리지 않도록
    # 기존 값들 뒤에 새 인덱스(6)로 추가하고, 사이드바 표시 순서(대시보드
    # 바로 아래)만 이 리스트의 나열 순서로 별도 조정한다.
    NAV_ITEMS = [
        ("⬡", "대시보드", 0),
        ("▤", "수집 목록", 6),
        ("≡", "모니터링", 1),
        ("◷", "스케줄러", 2),
        ("▲", "통계 분석", 3),
    ]
    SETTINGS = [("◎", "세션 설정", 4), ("⬡", "인증 관리", 5)]
    AUTH_NAV_INDEX = 5

    def _nav_items(self) -> list:
        return self.NAV_ITEMS

    def _settings_items(self) -> list:
        # 인증 관리 항목은 항상 생성해 두고 활성 블루프린트에 따라
        # setVisible()로만 토글 — 재빌드로 인한 시그널 재연결 누락을 방지.
        return self.SETTINGS

    def _add_nav_btn(self, lay, icon, label, stack_idx) -> NavItem:
        btn = super()._add_nav_btn(lay, icon, label, stack_idx)
        if stack_idx == self.AUTH_NAV_INDEX:
            self._auth_btn = btn
        return btn

    def set_auth_visible(self, visible: bool) -> None:
        self._auth_btn.setVisible(visible)


# ══════════════════════════════════════════════════════
#  MAIN WINDOW (다중)
# ══════════════════════════════════════════════════════
class MainWindowMulti(QMainWindow, MainWindowTriggersMulti):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataCrawler v2.0 — Multi Blueprint")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self._worker = None
        self._pending_queue = []   # 배치/스케줄 공용 순차 대기 큐 (FIFO)
        self._bundles: dict = {}   # seq_no -> BlueprintPageBundle (지연 생성 캐시)

        self.log_manager = LogViewerDialog(parent=self)

        self._build()
        self.tray_manager = TrayManager(self)

    def _build(self):
        storage = BlueprintStorage()

        left_widget = QWidget()
        self.setCentralWidget(left_widget)
        layout = QHBoxLayout(left_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarMulti()
        self.sidebar.page_changed.connect(self._switch_page)
        layout.addWidget(self.sidebar)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.global_toolbar = GlobalToolbarMulti()
        self.global_toolbar.start_requested.connect(self._start_crawl)
        self.global_toolbar.stop_requested.connect(self._stop_crawl)
        right_layout.addWidget(self.global_toolbar)

        # ── QStackedWidget: 페이지 종류별 인덱스는 단일과 동일하게 고정하고,
        #    블루프린트별 페이지는 각 슬롯(내부 QStackedWidget)에서 교체한다.
        self.stack = QStackedWidget()
        self.dashboard_slot = QStackedWidget()   # 0 — 블루프린트별 대시보드
        self.monitor_slot = QStackedWidget()     # 1 — 블루프린트별 모니터링
        self.schedule_page = SchedulerPage()     # 2 — 전역 단일 (단일과 동일)
        self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
        self.stats_page = StatisticsPage()       # 3 — 전역 단일
        self.session_page = SessionSettingsPage()  # 4 — 전역 단일
        self.schedule_page.session_page = self.session_page
        self.auth_slot = QStackedWidget()        # 5 — 블루프린트별 인증 관리
        # 인증이 없는 블루프린트용 빈 자리 표시 위젯 (index 0)
        self._auth_placeholder = QWidget()
        self.auth_slot.addWidget(self._auth_placeholder)

        self.blueprint_list_page = BlueprintListPage()   # 6 — 전역 단일, 목록 전용
        self.blueprint_list_page.row_selected.connect(self._activate_blueprint)
        self.blueprint_list_page.batch_start_requested.connect(self._start_batch)
        self.blueprint_list_page.selection_changed.connect(self._sync_toolbar_url_for_selection)

        self.stack.addWidget(self.dashboard_slot)       # 0
        self.stack.addWidget(self.monitor_slot)         # 1
        self.stack.addWidget(self.schedule_page)        # 2
        self.stack.addWidget(self.stats_page)           # 3
        self.stack.addWidget(self.session_page)         # 4
        self.stack.addWidget(self.auth_slot)            # 5
        self.stack.addWidget(self.blueprint_list_page)  # 6

        self.global_toolbar.set_log_manager(self.log_manager)

        right_layout.addWidget(self.stack, 1)

        # ── 메인 창 최하단 상태바 (단일과 공용 build_status_bar 사용) ───
        status_bar, self.status_level, self.status_msg = build_status_bar(self._open_log_viewer)
        right_layout.addWidget(status_bar)

        self.log_manager.last_log.connect(self._update_status_bar)

        layout.addWidget(right_widget, 1)

        # 최초 활성화 — 첫 번째 블루프린트 기준으로 기존 단일 동작을 재현
        self._activate_blueprint(storage.list_seq_nos()[0])

    # ── 번들 캐시 ─────────────────────────────────────
    def _resolve_seq_no(self, seq_no):
        """알 수 없는 seq_no(구버전 스케줄 등)는 현재 활성 블루프린트로 폴백."""
        storage = BlueprintStorage()
        return seq_no if seq_no in storage.list_seq_nos() else storage.active_seq_no

    def _get_or_create_bundle(self, seq_no) -> BlueprintPageBundle:
        seq_no = self._resolve_seq_no(seq_no)
        if seq_no not in self._bundles:
            bundle = BlueprintPageBundle(BlueprintStorage().get(seq_no))
            self._bundles[seq_no] = bundle
            # 생성 즉시 슬롯에 편입 — 페이지 내부의 self.window() 참조
            # (예: AuthManagerPage의 log_manager 조회)가 항상 동작하게 한다.
            self.dashboard_slot.addWidget(bundle.dashboard)
            self.monitor_slot.addWidget(bundle.monitor_page)
            if bundle.auth_page is not None:
                self.auth_slot.addWidget(bundle.auth_page)
        return self._bundles[seq_no]

    # ── 활성 블루프린트 전환 ───────────────────────────
    def _activate_blueprint(self, seq_no):
        """
        사이드바 선택/실행 시작 시 호출 — 각 슬롯의 표시 페이지를 해당
        블루프린트 번들로 교체하고, 상속받은 단일 트리거 코드가 참조하는
        self.dashboard/self.monitor_page/self.auth_page를 함께 갱신합니다.
        """
        seq_no = self._resolve_seq_no(seq_no)
        bundle = self._get_or_create_bundle(seq_no)
        BlueprintStorage().set_active(seq_no)

        self.dashboard_slot.setCurrentWidget(bundle.dashboard)
        self.monitor_slot.setCurrentWidget(bundle.monitor_page)
        if bundle.auth_page is not None:
            self.auth_slot.setCurrentWidget(bundle.auth_page)
        else:
            self.auth_slot.setCurrentWidget(self._auth_placeholder)
            # 인증 화면을 보던 중 인증 없는 블루프린트로 전환하면 대시보드로
            if self.stack.currentIndex() == SidebarMulti.AUTH_NAV_INDEX:
                self.stack.setCurrentIndex(0)
                for i, btn in enumerate(self.sidebar._btns):
                    btn.setChecked(i == 0)

        # 상속(단일) 트리거 호환 — "활성 번들"의 페이지를 가리키는 별칭 유지
        self.dashboard = bundle.dashboard
        self.monitor_page = bundle.monitor_page
        self.auth_page = bundle.auth_page

        # bundle.dashboard.blueprint_info는 번들 생성 시 이미 deepcopy된
        # 동일 블루프린트 — 여기서 BlueprintStorage().get()을 또 호출해
        # deepcopy를 반복할 필요가 없다.
        self.global_toolbar.activate_blueprint(bundle.dashboard.blueprint_info)
        # 수집 목록에서 2개 이상 체크된 상태로 행을 클릭했을 수 있으므로,
        # 방금 위에서 채운 URL을 선택 개수 기준으로 다시 확정한다.
        self._sync_toolbar_url_for_selection()
        self.global_toolbar.set_pages(
            dashboard=bundle.dashboard,
            monitor_page=bundle.monitor_page,
            session_page=self.session_page,
            auth_page=bundle.auth_page,
        )
        # set_pages()는 None을 무시하므로 인증 없는 블루프린트로 전환 시
        # 이전 번들의 auth_page가 남지 않도록 직접 재할당한다.
        self.global_toolbar.auth_page = bundle.auth_page

        self.sidebar.set_auth_visible(bundle.auth_page is not None)

    def _sync_toolbar_url_for_selection(self) -> None:
        """
        수집 목록의 선택 컬럼 체크 개수에 따라 상단 URL 입력창(과 방식 라벨)을
        갱신한다 — 실제 활성 블루프린트를 전환하지는 않고 표시만 바꾼다.
        - 2개 이상 체크: 대상이 하나로 특정되지 않으므로 빈 값
        - 정확히 1개 체크: 체크된 그 블루프린트의 URL
        - 0개 체크: 현재 활성 블루프린트의 URL로 복원
        """
        checked = self.blueprint_list_page.checked_seq_nos()
        if len(checked) >= 2:
            self.global_toolbar.url_input.setText("")
            self.global_toolbar._method_label.setText("")
        elif len(checked) == 1:
            checked_info = BlueprintStorage().get(checked[0])
            self.global_toolbar.activate_blueprint(checked_info or {})
        else:
            self.global_toolbar.activate_blueprint(self.dashboard.blueprint_info)
