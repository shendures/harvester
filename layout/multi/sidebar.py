# layout/multi/sidebar.py

from style import NavItem
from ..single import SidebarSingle


class SidebarMulti(SidebarSingle):
    """
    SidebarSingle의 뼈대(로고·구분선·상태줄·_add_nav_btn/_on_nav)를 그대로
    상속하고, 항목 목록만 다중 수집에 맞게 오버라이드한다.
    """

    # (아이콘, 라벨, 스택 인덱스) — 스택 인덱스는 단일 공유 코드(trigger/main_window.py의
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
