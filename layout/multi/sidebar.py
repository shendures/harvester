# layout/multi/sidebar.py

from ..single import SidebarSingle


class SidebarMulti(SidebarSingle):
    """
    SidebarSingle의 뼈대(로고·구분선·상태줄·_add_nav_btn/_on_nav)를 그대로
    상속하고, 항목 목록만 다중 수집에 맞게 오버라이드한다.
    """

    # (아이콘, 라벨, 스택 인덱스) — 스택 인덱스는 단일 공유 코드(trigger/main_window.py의
    # _switch_page가 idx==3일 때 stats_page.reload()를 호출하는 등)가 전제하는
    # 고정값(0 대시보드/1 모니터링/2 스케줄러/3 통계 분석/4 세션 설정)과 반드시
    # 일치해야 한다. "인증 관리"(옛 인덱스 5)는 다중 레이아웃에서 제거됐다 — 그
    # 카드 내용은 "수집 목록" 테이블의 항목별 "⚙" 버튼이 여는 다이얼로그로
    # 옮겨졌다(요구사항 3). "수집 목록"은 그 뒤를 이어 인덱스 5로 당겨졌다.
    NAV_ITEMS = [
        ("⬡", "대시보드", 0),
        ("▤", "수집 목록", 5),
        ("≡", "모니터링", 1),
        ("◷", "스케줄러", 2),
        ("▲", "통계 분석", 3),
    ]
    SETTINGS = [("◎", "세션 설정", 4)]

    def _nav_items(self) -> list:
        return self.NAV_ITEMS

    def _settings_items(self) -> list:
        return self.SETTINGS
