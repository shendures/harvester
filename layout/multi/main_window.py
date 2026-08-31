# layout/multi/main_window.py

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QSplitter
from PyQt6.QtCore import Qt

from conf import BlueprintStorage
from trigger import LogViewerDialog, MainWindowTriggersMulti
from trigger.common import NAV_BLUEPRINT_LIST
from ..common import build_status_bar, center_window_on_screen
from ..scheduler import SchedulerPage
from ..statistics import StatisticsPage
from ..session import SessionSettingsPage
from ..tray import TrayManager
from .toolbar import GlobalToolbarMulti
from .sidebar import SidebarMulti
from .blueprint_list import BlueprintListPage, BlueprintPageBundle
from .monitor_target_list import MonitorTargetListPage


class MainWindowMulti(QMainWindow, MainWindowTriggersMulti):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataCrawler v2.0 — Multi Blueprint")
        self.resize(1843, 1152)
        self.setMinimumSize(960, 640)
        self._worker = None
        self._pending_queue = []   # 배치/스케줄 공용 순차 대기 큐 (FIFO)
        self._bundles: dict = {}   # seq_no -> BlueprintPageBundle (지연 생성 캐시)

        self.log_manager = LogViewerDialog(parent=self)

        self._build()
        self.tray_manager = TrayManager(self)
        self._centered_once = False

    def showEvent(self, event):
        super().showEvent(event)
        # 트레이에서 창을 복원할 때마다 다시 중앙으로 튀지 않도록 최초 1회만 정렬한다.
        if not self._centered_once:
            self._centered_once = True
            center_window_on_screen(self)

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
        self.dashboard_slot = QStackedWidget()   # 블루프린트별 대시보드(나머지 카드) — "수집 목록"(5) 하단에 통합됨
        self.step_slot = QStackedWidget()        # 블루프린트별 "작업 진행 상태" 카드 — "수집 목록"(5) 위쪽에 통합됨
        self.monitor_slot = QStackedWidget()     # 1 — 블루프린트별 데이터 정제(4탭)
        self.monitor_nav_list = MonitorTargetListPage()  # 1 좌측 — 정제 대상 선택용 경량 목록
        self.monitor_nav_list.blueprint_selected.connect(self._activate_blueprint)
        self.monitor_split = QSplitter(Qt.Orientation.Horizontal)
        self.monitor_split.addWidget(self.monitor_nav_list)
        self.monitor_split.addWidget(self.monitor_slot)
        # "수집 대상"(좌) : 정제 레이아웃(우) = 3 : 7 비율 — 창 크기가 바뀌어도
        # 두 창 폭이 늘고 줄 때 이 비율로 함께 움직이도록 스트레치 팩터도 3:7로 맞춘다
        # (setSizes는 초기 폭만 정하고, 이후 리사이즈 배분은 stretchFactor를 따른다).
        self.monitor_split.setStretchFactor(0, 3)
        self.monitor_split.setStretchFactor(1, 7)
        self.monitor_split.setSizes([300, 700])
        self.monitor_split.setChildrenCollapsible(False)
        self.schedule_page = SchedulerPage()     # 2 — 전역 단일 (단일과 동일)
        self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
        self.stats_page = StatisticsPage()       # 3 — 전역 단일
        self.session_page = SessionSettingsPage()  # 4 — 전역 단일
        self.schedule_page.session_page = self.session_page

        self.blueprint_list_page = BlueprintListPage()   # 5 — 전역 단일, 목록+모니터링 통합
        self.blueprint_list_page.row_selected.connect(self._activate_blueprint)
        self.blueprint_list_page.batch_start_requested.connect(self._start_batch)
        self.blueprint_list_page.settings_requested.connect(self._open_blueprint_settings)
        self.blueprint_list_page.stop_requested.connect(self._stop_crawl)
        self.blueprint_list_page.selection_changed.connect(self._sync_toolbar_url_for_selection)
        # "모니터링"(구 NAV_MONITOR 페이지)을 "수집 목록" 위/아래에 통합한다 — 카드
        # 순서를 "작업 진행 상태 → 수집 목록 → 대기중 상태바 → 세션 통계 → 수집
        # 모니터링"으로 맞추기 위해 step_slot(작업 진행 상태만)은 위에, dashboard_slot
        # (나머지 카드)은 아래에 붙인다. 두 슬롯의 소유권은 그대로 이 클래스가 갖고
        # (_get_or_create_bundle이 계속 addWidget으로 채움), 화면 배치만 여기서 주입한다.
        self.blueprint_list_page.attach_step_panel(self.step_slot)
        self.blueprint_list_page.attach_detail_panel(self.dashboard_slot)

        # 추가 순서가 곧 스택 인덱스이며 trigger/common.py의 NAV_* 상수와 일치해야 한다.
        # 인덱스 0(NAV_MONITOR)은 단일 레이아웃과 공유하는 고정값이라 값을 바꿀 수
        # 없지만, 다중은 위에서 "수집 목록"에 통합했으므로 이 자리는 쓰지 않는
        # 빈 위젯으로 채워 1~5 인덱스 정렬만 유지한다.
        self.stack.addWidget(QWidget())                 # 0 — NAV_MONITOR (다중 미사용, "수집 목록"에 통합됨)
        self.stack.addWidget(self.monitor_split)        # 1 — NAV_REFINE
        self.stack.addWidget(self.schedule_page)        # 2 — NAV_SCHEDULE
        self.stack.addWidget(self.stats_page)           # 3 — NAV_STATS
        self.stack.addWidget(self.session_page)         # 4 — NAV_SESSION
        self.stack.addWidget(self.blueprint_list_page)  # 5 — NAV_BLUEPRINT_LIST

        self.global_toolbar.set_log_manager(self.log_manager)

        right_layout.addWidget(self.stack, 1)

        # ── 메인 창 최하단 상태바 (단일과 공용 build_status_bar 사용) ───
        status_bar, self.status_level, self.status_msg = build_status_bar(self._open_log_viewer)
        right_layout.addWidget(status_bar)

        self.log_manager.last_log.connect(self._update_status_bar)

        layout.addWidget(right_widget, 1)

        # 최초 활성화 — 첫 번째 블루프린트 기준으로 기존 단일 동작을 재현
        self._activate_blueprint(storage.list_seq_nos()[0])
        # 다중 레이아웃은 시작 화면으로 "수집 목록"을 먼저 보여준다
        self._activate_nav_page(NAV_BLUEPRINT_LIST)

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
            # 생성 즉시 슬롯에 편입 — 페이지 내부의 self.window() 참조가 항상
            # 동작하게 한다. auth_page는 어떤 슬롯에도 마운트하지 않는다 — 더
            # 이상 별도 화면이 아니라 "⚙" 다이얼로그가 열릴 때만 잠깐 그
            # 다이얼로그에 얹혔다가 떼어지는 방식으로 쓰인다(_open_blueprint_settings).
            self.dashboard_slot.addWidget(bundle.dashboard)
            self.step_slot.addWidget(bundle.dashboard.step_card_widget)
            self.monitor_slot.addWidget(bundle.monitor_page)
        return self._bundles[seq_no]

    def _open_blueprint_settings(self, seq_no) -> None:
        """"수집 목록" 테이블의 "⚙" 버튼 클릭 — 화면 전환 없이 그 블루프린트의
        "수집 설정" 다이얼로그(수집 설정 + 추출 설정 + 인증 관리)만 모달로 띄운다."""
        bundle = self._get_or_create_bundle(seq_no)
        bundle.monitor_page._open_output_settings_dialog(
            collect=bundle.collect_settings, auth_page=bundle.auth_page,
        )

    def _broadcast_blueprint_status(self, seq_no, status: str) -> None:
        """"수집 목록"과 "데이터 정제" 좌측 목록 양쪽의 상태 컬럼을 함께 갱신한다."""
        self.blueprint_list_page.set_status(seq_no, status)
        self.monitor_nav_list.set_status(seq_no, status)

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
        self.monitor_nav_list.set_active_seq_no(seq_no)

        self.dashboard_slot.setCurrentWidget(bundle.dashboard)
        self.step_slot.setCurrentWidget(bundle.dashboard.step_card_widget)
        self.monitor_slot.setCurrentWidget(bundle.monitor_page)

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
