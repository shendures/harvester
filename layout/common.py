# layout/common.py
# layout_single.py/layout_multi.py 양쪽(및 그 서브패키지)이 공유하는
# 테마 상수·헬퍼·상태바 빌더 허브. single/·multi/ 는 이 파일만 참조하고
# 서로를 직접 import하지 않는다(단, multi는 single을 상속 목적으로 import).

from conf import DataStore
from style import THEME, Parts, EqualSpacingTable
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QSizePolicy, QApplication,
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


def make_header_table(parent, headers: list, row_height: int = 36,
                       col_padding: int = 8, hscroll_handle: int = 50) -> EqualSpacingTable:
    """헤더 컬럼이 고정된 EqualSpacingTable을 만든다. auth/session 페이지가 공유."""
    t = EqualSpacingTable(
        parent=parent, row_height=row_height,
        col_padding=col_padding, hscroll_handle=hscroll_handle,
    )
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    return t


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

    # 레벨 태그 (색상 표시)
    status_level = parts.make_label("", TEXT_MUTED, 11)
    status_level.setFixedWidth(48)
    sbl.addWidget(status_level)

    # 최신 로그 메시지 한 줄
    status_msg = parts.make_label("대기 중", TEXT_MUTED, 11)
    status_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    sbl.addWidget(status_msg, 1)

    # 전체 로그 보기 버튼
    log_view_btn = parts.outline_btn("로그 전체 보기 ▲")
    log_view_btn.clicked.connect(open_log_viewer_callback)
    sbl.addWidget(log_view_btn)

    return status_bar, status_level, status_msg


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
