# layout/multi/main_window.py

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget

from conf import BlueprintStorage
from trigger import LogViewerDialog, MainWindowTriggersMulti
from ..common import build_status_bar
from ..scheduler import SchedulerPage
from ..statistics import StatisticsPage
from ..session import SessionSettingsPage
from ..tray import TrayManager
from .toolbar import GlobalToolbarMulti
from .sidebar import SidebarMulti
from .blueprint_list import BlueprintListPage, BlueprintPageBundle


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
