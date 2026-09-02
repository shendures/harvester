# layout/multi/sidebar.py

from trigger.common import NAV_REFINE, NAV_SCHEDULE, NAV_STATS, NAV_SESSION, NAV_BLUEPRINT_LIST
from ..single import SidebarSingle


class SidebarMulti(SidebarSingle):
    """
    SidebarSingle의 뼈대(로고·구분선·상태줄·_add_nav_btn/_on_nav)를 그대로
    상속하고, 항목 목록만 다중 수집에 맞게 오버라이드한다.
    """

    # (아이콘, 라벨, 스택 인덱스) — 스택 인덱스는 단일 공유 코드(trigger/main_window.py의
    # _switch_page가 idx==NAV_STATS일 때 stats_page.reload()를 호출하는 등)가 전제하는
    # 고정값이며, trigger/common.py의 NAV_* 상수가 그 유일한 출처다. 표시 순서(아래 리스트
    # 순서)와 스택 인덱스가 다를 수 있으니 주의 — "대시보드"(구 "수집 목록")가 화면상
    # 첫 항목이지만 스택 인덱스는 NAV_BLUEPRINT_LIST(5)다. "인증 관리"(옛 인덱스 5)는
    # 다중 레이아웃에서 제거됐다 — 그 카드 내용은 이 페이지의 수집 목록 테이블 항목별
    # "⚙" 버튼이 여는 다이얼로그로 옮겨졌다(요구사항 3). 이 페이지는 원래 "수집 목록"
    # 이었고, 옛 "모니터링" nav 항목(NAV_MONITOR=0)이 하단 상세 패널로 통합되면서 페이지
    # 라벨도 "모니터링"을 거쳐 지금은 "대시보드"로 바뀌었다(layout/multi/blueprint_list.py의
    # attach_detail_panel 참고). NAV_MONITOR 값 자체는 단일 레이아웃과 공유하는 고정
    # 인덱스라 그대로 남아있지만 다중 사이드바에는 더 이상 대응하는 항목이 없다.
    NAV_ITEMS = [
        ("layout-dashboard", "대시보드", NAV_BLUEPRINT_LIST),
        ("funnel", "데이터 정제", NAV_REFINE),
        ("calendar-clock", "스케줄러", NAV_SCHEDULE),
        ("chart-column", "통계 분석", NAV_STATS),
    ]
    SETTINGS = [("waypoints", "세션 설정", NAV_SESSION)]

    def _nav_items(self) -> list:
        return self.NAV_ITEMS

    def _settings_items(self) -> list:
        return self.SETTINGS
