# layout/common.py
# layout_single.py/layout_multi.py 양쪽(및 그 서브패키지)이 공유하는
# 테마 상수·헬퍼·상태바 빌더 허브. single/·multi/ 는 이 파일만 참조하고
# 서로를 직접 import하지 않는다(단, multi는 single을 상속 목적으로 import).

from conf import DataStore
from style import THEME, Parts, EqualSpacingTable, StatCard, CenteredHandleSplitter
from trigger.common import _confirm_destructive_action, _default_dialog_qss
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QSizePolicy, QApplication,
    QDialog, QSplitter,
)

store = DataStore()

theme = THEME()
parts = Parts()

# ── THEME 색상 변수를 모듈 레벨에서 참조할 수 있도록 언패킹 ──────────────
# style.py의 THEME 클래스가 단일 정의 소스(Single Source of Truth)이며,
# 이 변수들은 그 인스턴스 속성을 그대로 바인딩한 것입니다.
# 색상을 변경할 때는 THEME 클래스만 수정하면 됩니다.
BG_PRIMARY    = theme.BG_PRIMARY
BG_SECONDARY  = theme.BG_SECONDARY
BG_HOVER      = theme.BG_HOVER
ACCENT        = theme.ACCENT
ACCENT_LIGHT  = theme.ACCENT_LIGHT
ACCENT_HOVER  = theme.ACCENT_HOVER
TEXT_PRIMARY  = theme.TEXT_PRIMARY
TEXT_SECONDARY= theme.TEXT_SECONDARY
TEXT_MUTED    = theme.TEXT_MUTED
BORDER        = theme.BORDER
BORDER_LIGHT  = theme.BORDER_LIGHT
GREEN         = theme.GREEN
AMBER         = theme.AMBER
RED           = theme.RED
BLUE          = theme.BLUE
PURPLE        = theme.PURPLE


def _blueprint_auth_method(info: dict):
    """
    이 블루프린트의 인증 방식("login"/"api_key")을 판단합니다.
    conditions.authMethod(신규, generator_conditions.html이 생성)를 우선 확인하고,
    없으면(구버전 request_info.json) conditions.login 객체 존재 여부로 "login"을 추정합니다.
    """
    conditions = info.get("conditions") or {}
    return conditions.get("authMethod") or ("login" if conditions.get("login") else None)


def _blueprint_requires_auth(info: dict) -> bool:
    """이 블루프린트가 인증 관리 화면을 필요로 하는지 판단합니다."""
    return _blueprint_auth_method(info) is not None


def build_scroll_body(widget, spacing: int = 14) -> QVBoxLayout:
    """widget에 스크롤 가능한 바디를 채우는 공통 뼈대를 만든다.
    반환된 QVBoxLayout(패딩 14, 간격 spacing)에 실제 콘텐츠를 addWidget/addLayout한다.
    auth/session/scheduler/statistics 페이지가 공유한다."""
    root = QVBoxLayout(widget)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea{border:none;}")
    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(14, 14, 14, 14)
    bl.setSpacing(spacing)
    scroll.setWidget(body)
    root.addWidget(scroll, 1)

    return bl


def make_header_table(parent, headers: list) -> EqualSpacingTable:
    """헤더 컬럼이 고정된 EqualSpacingTable을 만든다. auth/session 페이지가 공유."""
    t = EqualSpacingTable(parent=parent, row_height=36, col_padding=8, hscroll_handle=50)
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    return t


def build_stat_summary_card(parts, title: str, specs: list, help_text: str | None = None) -> tuple:
    """(label, value[, color]) 튜플 리스트로 카드 안에 StatCard를 나란히 만든다.
    (card_widget, [StatCard, ...])를 반환 — 호출부가 개별 StatCard를 self.attr에
    대입한다. dashboard/monitor 페이지의 요약 카드 행(세션 현황, 수집 결과 요약,
    정제 결과 요약 등)이 공유한다. help_text를 주면 카드명 오른쪽에 도움말 아이콘을 둔다."""
    card_w, card_l = parts.card_widget(title, help_text=help_text)
    row = QHBoxLayout()
    row.setSpacing(10)
    cards = []
    for spec in specs:
        label, value, *color = spec
        card = StatCard(label, value, *color)
        row.addWidget(card, 1)
        cards.append(card)
    card_l.addLayout(row)
    return card_w, cards


def row_of_seq(table, seq_no, seq_no_col: int) -> int:
    """table에서 seq_no_col 컬럼의 UserRole 데이터가 seq_no와 일치하는 행 번호를
    찾는다(정렬 후에도 안전). 없으면 -1. BlueprintListPage/MonitorTargetListPage가
    공유한다."""
    for row in range(table.rowCount()):
        id_item = table.item(row, seq_no_col)
        if id_item and id_item.data(Qt.ItemDataRole.UserRole) == seq_no:
            return row
    return -1


def result_columns_from_blueprint(blueprint_info: dict) -> list:
    """
    블루프린트의 conditions.items 키에서 결과 테이블 컬럼 목록을 구성합니다.
    layout.single.ActiveBlueprintMixin과 layout.multi의 Dashboard/MonitorPageMulti가
    각자 _active_blueprint_info() 훅으로 얻은 dict를 여기에 넘겨 공유합니다.
    """
    try:
        items = list(blueprint_info["conditions"]["items"].keys())
        return [c for c in items if c not in ("root", "detail_root", "main_root", "detail")]
    except (KeyError, TypeError):
        return []


# 사이드바 하단 구분선(sidebar.py의 status_footer)과 반드시 같은 값을 써야 한다 —
# 두 값이 갈라지면 사이드바 선과 이 상태바 선이 어긋난다.
STATUS_BAR_HEIGHT = 41


def build_status_bar(open_log_viewer_callback):
    """메인 창 최하단 상태바(최신 로그 한 줄 + 전체 로그 보기 버튼)를 만든다.
    MainWindowSingle/MainWindowMulti가 동일하게 사용한다.

    Returns:
        (status_bar 위젯, status_level 라벨, status_msg 라벨) — 호출부가
        self.status_level/self.status_msg에 직접 대입해 보관한다.
    """
    status_bar = QWidget()
    status_bar.setFixedHeight(STATUS_BAR_HEIGHT)
    status_bar.setStyleSheet(
        f"background:{BG_SECONDARY}; border-top:1px solid {BORDER};"
    )
    sbl = QHBoxLayout(status_bar)
    sbl.setContentsMargins(14, 0, 14, 0)
    sbl.setSpacing(8)

    status_level = parts.make_label("", TEXT_MUTED, 11)
    status_level.setFixedWidth(48)
    sbl.addWidget(status_level)

    status_msg = parts.make_label("대기 중", TEXT_MUTED, 11)
    status_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    sbl.addWidget(status_msg, 1)

    log_view_btn = parts.outline_btn("로그 전체 보기 ▲")
    log_view_btn.clicked.connect(open_log_viewer_callback)
    sbl.addWidget(log_view_btn)

    return status_bar, status_level, status_msg


def build_reset_button(parts, parent, *, title: str, text: str, on_confirmed,
                        informative_text: str = None, label: str = "RESET"):
    """"초기화"류의 되돌릴 수 없는 액션 버튼을 만든다. 클릭 시
    trigger.common._confirm_destructive_action()으로 Yes/No 재확인을 거친 뒤에만
    on_confirmed()를 실행한다 — build_status_bar()와 동일하게 실제 로직은 호출부의
    콜백이 담당하고, 이 함수는 UI 조립 + 확인 게이팅만 담당한다. 통계 분석 RESET
    외에 다른 페이지가 같은 "재확인 후 초기화" 버튼이 필요할 때도 그대로 재사용한다."""
    btn = parts.action_btn(label)

    def _on_click():
        if _confirm_destructive_action(parent, title, text, informative_text):
            on_confirmed()

    btn.clicked.connect(_on_click)
    return btn


def build_popup_dialog(parent, title: str, size: tuple, min_size: tuple) -> tuple:
    """모달리스 팝업 다이얼로그 기본 골격을 만든다(MonitorPageSingle의 Raw/비교
    팝업, StatisticsPage의 수집량 추이 전체 보기 팝업이 공유). 반환된 (dlg, lay)에
    컨텐츠를 채운 뒤 dlg.show()는 호출부 책임."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(False)
    dlg.resize(*size)
    dlg.setMinimumSize(*min_size)
    dlg.setStyleSheet(_default_dialog_qss())
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(14, 14, 14, 14)
    return dlg, lay


def build_master_detail_splitter(main_widget, detail_widget, orientation, *,
                                  handle_width: int = 9, centered: bool = False,
                                  stretch: tuple = (1, 0)):
    """main_widget/detail_widget를 담은 QSplitter(centered=True면 세로 핸들
    중앙선을 직접 그리는 CenteredHandleSplitter)를 조립한다. Raw/정제 탭의
    테이블+상세 카드, Raw/정제 비교 팝업의 좌우 카드, MainWindowMulti의 정제
    대상 목록+정제 레이아웃이 모두 이 골격(자식 접기 금지 + 핸들 폭)을
    공유하고 orientation/센터 여부/스트레치 비율만 다르다. 초기 폭(setSizes)이
    필요한 호출부는 반환된 splitter에 이어서 직접 호출한다."""
    splitter_cls = CenteredHandleSplitter if centered else QSplitter
    split = splitter_cls(orientation)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(handle_width)
    split.addWidget(main_widget)
    split.addWidget(detail_widget)
    split.setStretchFactor(0, stretch[0])
    split.setStretchFactor(1, stretch[1])
    return split


def center_window_on_screen(window) -> None:
    """창을 현재 화면(멀티 모니터면 창이 뜨는 화면)의 정중앙으로 이동시킨다.
    창이 아직 표시(show)되기 전이면 창 관리자가 배치를 덮어써 move()가
    무시될 수 있으므로, 반드시 show() 이후(예: showEvent)에 호출해야 한다.
    MainWindowSingle/MainWindowMulti가 동일하게 사용한다."""
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    frame_geo = window.frameGeometry()
    frame_geo.moveCenter(screen.availableGeometry().center())
    window.move(frame_geo.topLeft())
