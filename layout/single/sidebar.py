# layout/single/sidebar.py

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import pyqtSignal

from style import NavItem, Divider
from trigger.common import NAV_MONITOR, NAV_REFINE, NAV_SCHEDULE, NAV_STATS, NAV_SESSION, NAV_AUTH
from ..common import (
    parts, BG_SECONDARY, ACCENT_LIGHT, TEXT_MUTED, GREEN, BORDER, STATUS_BAR_HEIGHT,
    _blueprint_requires_auth,
)
from .common import request_info


class SidebarSingle(QWidget):
    """
    사이드바 뼈대(로고·구분선·NAVIGATOR/SETTINGS 섹션·하단 연결 상태줄)를 구성한다.
    SidebarMulti(layout_multi.py)가 이 클래스를 상속해 항목 목록(_nav_items/
    _settings_items)만 오버라이드하므로, 뼈대를 고치면 양쪽에 함께 반영된다.
    """
    page_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._build()

    def _nav_items(self) -> list:
        """(아이콘, 라벨, 스택 인덱스) 목록 — 상단 NAVIGATOR 섹션."""
        return [
            ("layout-dashboard", "대시보드", NAV_MONITOR), ("funnel", "데이터 정제", NAV_REFINE),
            ("calendar-clock", "스케줄러", NAV_SCHEDULE), ("chart-column", "통계 분석", NAV_STATS),
        ]

    def _settings_items(self) -> list:
        """(아이콘, 라벨, 스택 인덱스) 목록 — 하단 SETTINGS 섹션.
        첫번째 수집 정보 기준으로 인증 관리 항목 포함 여부를 결정한다."""
        items = [("waypoints", "세션 설정", NAV_SESSION)]
        if _blueprint_requires_auth(request_info):
            items.append(("key-round", "인증 관리", NAV_AUTH))
        return items

    def _build(self):

        self.setFixedWidth(190)
        self.setStyleSheet(f"background:{BG_SECONDARY}; border-right:1px solid {BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(2)

        logo = parts.make_label("DataCrawler", ACCENT_LIGHT, 15, True)
        logo.setStyleSheet(logo.styleSheet() + " padding:0 16px 12px;")
        lay.addWidget(logo)
        lay.addWidget(Divider())

        nav_lbl = parts.make_label("NAVIGATOR", TEXT_MUTED, 9)
        nav_lbl.setStyleSheet(nav_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(nav_lbl)

        self._btns = []
        self._nav_idx_by_btn = {}   # NavItem -> 그 버튼이 가리키는 스택 인덱스
        for icon, label, stack_idx in self._nav_items():
            self._add_nav_btn(lay, icon, label, stack_idx)

        lay.addSpacing(8)
        lay.addWidget(Divider())

        set_lbl = parts.make_label("SETTINGS", TEXT_MUTED, 9)
        set_lbl.setStyleSheet(set_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(set_lbl)

        for icon, label, stack_idx in self._settings_items():
            self._add_nav_btn(lay, icon, label, stack_idx)

        lay.addStretch()

        # 이 창 최하단 구분선(우측 콘텐츠 영역의 build_status_bar가 그리는
        # border-top)과 한 줄로 맞추기 위해, Divider를 폰트 메트릭에 따라
        # 흔들리는 콘텐츠 높이 위가 아니라 STATUS_BAR_HEIGHT로 고정한 컨테이너
        # 맨 위에 둔다 — 그러면 두 선 모두 "창 높이 − STATUS_BAR_HEIGHT"로
        # 결정되어 플랫폼별 폰트 해석 차이와 무관하게 항상 일치한다.
        status_footer = QWidget()
        status_footer.setFixedHeight(STATUS_BAR_HEIGHT)
        footer_lay = QVBoxLayout(status_footer)
        footer_lay.setContentsMargins(0, 0, 0, 0)
        footer_lay.setSpacing(0)
        footer_lay.addWidget(Divider())

        status_row = QHBoxLayout()
        status_row.setContentsMargins(16, 8, 16, 0)
        dot = parts.make_label("●", GREEN, 10)
        st = parts.make_label("연결됨", GREEN, 12)
        status_row.addWidget(dot)
        status_row.addWidget(st)
        status_row.addStretch()
        footer_lay.addLayout(status_row)
        footer_lay.addStretch()

        lay.addWidget(status_footer)

        self._btns[0].setChecked(True)

    def _add_nav_btn(self, lay, icon, label, stack_idx) -> NavItem:
        """NavItem을 만들어 레이아웃에 추가하고, 클릭 시 이동할 스택 인덱스를
        버튼 자체에 매핑해둔다 — SidebarMulti처럼 표시 순서와 스택 인덱스가
        다른 항목("수집 목록" 등)도 안전하게 지원하기 위함."""
        btn = NavItem(icon, label)
        btn.clicked.connect(lambda _, idx=stack_idx: self._on_nav(idx))
        lay.addWidget(btn)
        self._btns.append(btn)
        self._nav_idx_by_btn[btn] = stack_idx
        return btn

    def _on_nav(self, idx):
        for b in self._btns:
            b.setChecked(self._nav_idx_by_btn[b] == idx)
        self.page_changed.emit(idx)
