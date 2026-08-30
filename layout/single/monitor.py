# layout/single/monitor.py

import customized_settings

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QTabWidget, QCheckBox, QMessageBox,
)

from trigger import MonitorPageTriggers
from style import StatCard, EqualSpacingTable, build_refine_rule_rows
from ..common import (
    parts,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BORDER, ACCENT, ACCENT_LIGHT,
    TEXT_MUTED, TEXT_SECONDARY, GREEN, AMBER, RED,
)
from .common import ActiveBlueprintMixin


class MonitorPageSingle(QWidget, MonitorPageTriggers, ActiveBlueprintMixin):
    _SILENT_JOBS = ("스케줄 실행",)

    def __init__(self):
        super().__init__()
        self._all_rows       = []
        self._collected_data = []   # raw 수집 데이터
        self._existing_keys  = set()   # _collected_data 중복판정용 캐시(증분 갱신)
        self._refined_data   = []   # 정제 후 데이터
        self._current_task   = {}   # 최근 완료된 수집의 task(seq_no/needs_cleaning 등 포함)
        self._cleaning_warned = False   # 이번 수집에 대해 "규칙 없음" 팝업을 이미 띄웠는지
        self._out_mode       = None
        self.output_info     = customized_settings.get_output_settings()

        # 정제 규칙 기본값 — True: 활성화 / False: 비활성화
        self._refine_rules = {
            "remove_null_row":   True,   # 모든 필드 null 행 제거
            "custom_rule":       True,   # 커스텀 규칙(seq_no) 적용
            "trim_whitespace":   True,   # 문자열 앞뒤 공백 trim
            "remove_duplicate":  True,   # 중복 행 제거
            "drop_columns":      False,  # 선택 필드 제외 (비활성 기본)
            "fill_null":         False,  # null → 지정값 치환 (비활성 기본)
            "cast_numeric":      False,  # 숫자 타입 변환 (비활성 기본)
        }
        self._drop_column_names: list[str] = []   # 제외할 컬럼명 목록
        self._fill_null_value: str = ""            # null 치환값 (기본: 빈 값)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── QTabWidget (4탭 구조) ─────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background: {BG_SECONDARY};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 6px 18px;
                font-size: 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {BG_PRIMARY};
                color: {ACCENT_LIGHT};
                border-bottom: 2px solid {ACCENT};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background: {BG_HOVER};
                color: {TEXT_SECONDARY};
            }}
        """)
        root.addWidget(self.tab_widget)

        # ── 탭 ① Raw 수집 결과 ────────────────────────────────────────
        self._build_raw_tab()
        # ── 탭 ② 정제 규칙 설정 ───────────────────────────────────────
        self._build_refine_rules_tab()
        # ── 탭 ③ 정제 결과 ────────────────────────────────────────────
        self._build_refined_tab()
        # ── 탭 ④ Before / After 비교 ──────────────────────────────────
        self._build_compare_tab()

        # 탭 전환 시 "② 정제 규칙 설정" 진입을 감지해 규칙 미설정 여부를 알림
        self.tab_widget.currentChanged.connect(self._on_monitor_tab_changed)

    # ── 탭 ① Raw 수집 결과 ────────────────────────────────────────────
    def _build_raw_tab(self):
        raw_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        raw_layout = QVBoxLayout(raw_widget)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.addWidget(scroll)

        # 수집 결과 요약 카드 (4칸)
        sum_card_w, sum_card_l = parts.card_widget("수집 결과 요약")
        sg = QHBoxLayout()
        sg.setSpacing(10)
        self.sum_total = StatCard("전체 항목",  "0")
        self.sum_ok    = StatCard("정상 행",     "0", GREEN)
        self.sum_err   = StatCard("전체 null",   "0", AMBER)
        self.sum_warn  = StatCard("중복 행",     "0", RED)
        for card in [self.sum_total, self.sum_ok, self.sum_err, self.sum_warn]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            sg.addWidget(card, 1)
        sum_card_l.addLayout(sg)
        bl.addWidget(sum_card_w)

        # 실시간 수집 결과 테이블
        tcw, tc = parts.card_widget("실시간 수집 결과 (RAW)")
        tbl_ctrl = QHBoxLayout()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 검색")
        self.search_box.setFixedWidth(220)
        self.search_box.textChanged.connect(self._apply_filter)
        tbl_ctrl.addWidget(self.search_box)

        self.count_lbl = QLabel("0 rows")
        self.count_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        tbl_ctrl.addWidget(self.count_lbl)
        tbl_ctrl.addStretch()

        raw_exp_btn = parts.action_btn("EXTRACT")
        raw_exp_btn.clicked.connect(lambda: self._extract_result_table(source="raw"))
        tbl_ctrl.addWidget(raw_exp_btn)
        tc.addLayout(tbl_ctrl)

        # null·중복 안내
        info_lbl = parts.make_label(
            "● 주황색 배경: 전체 null 행  ● 빨간색 배경: 중복 행",
            AMBER, 11
        )
        tc.addWidget(info_lbl)

        self.result_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.result_table.itemClicked.connect(self._show_detail)
        self.result_table.currentItemChanged.connect(self._on_current_item_changed)
        tc.addWidget(self.result_table)
        bl.addWidget(tcw, 1)

        # 선택 항목 상세
        dw, dl = parts.card_widget("선택 항목 상세")
        self.detail_lbl = parts.make_label("테이블에서 행을 클릭하세요.", TEXT_MUTED, 12)
        dl.addWidget(self.detail_lbl)
        bl.addWidget(dw)

        self.tab_widget.addTab(raw_widget, "① Raw 수집 결과")

    # ── 탭 ② 정제 규칙 설정 ──────────────────────────────────────────
    def _build_refine_rules_tab(self):
        rules_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        rules_layout.addWidget(scroll)

        # ── 기본 정제 규칙 카드 ──────────────────────────────────────
        rw, rl = parts.card_widget("정제 규칙")
        # 화면 표시 순서는 실제 처리 순서와 무관하므로(style.REFINE_RULE_DEFS 참고)
        # "위에서 아래 순서로 적용됩니다" 같은 안내는 혼란을 줄 수 있어 넣지 않음
        desc = parts.make_label(
            "설정 후 [정제 실행] 버튼을 눌러주세요.",
            TEXT_MUTED, 11
        )
        rl.addWidget(desc)
        rl.addSpacing(8)

        self._rule_checkboxes: dict[str, QCheckBox] = {}
        initial_drop_summary = (
            f"{len(self._drop_column_names)}개 필드 제외 중" if self._drop_column_names else "제외 필드 없음"
        )

        # 체크박스 행 생성은 style.build_refine_rule_rows()가 전담(스케줄 등록
        # 다이얼로그의 정제 규칙 설정과 공유하는 빌더, guidelines/PREPROCESS.md 참고)
        result = build_refine_rule_rows(
            parts, rl, self._rule_checkboxes, self._refine_rules,
            include_keys=None,   # 전체 7개 규칙
            on_drop_columns_click=self._open_drop_columns_dialog,
            on_drop_columns_check=lambda: bool(self._collected_data),
            on_drop_columns_warn=self._has_collected_data_or_warn,
            drop_columns_initial_summary=initial_drop_summary,
            fit_desc_one_line=True,   # 탭 폭이 넉넉해 두 행만 줄바꿈되던 문제 해결
        )
        self.fill_null_input = result["fill_null_input"]
        self.drop_columns_summary_lbl = result["drop_columns_summary_lbl"]

        # 커스텀 정제 규칙 체크 시 규칙 ①③④(remove_null_row/trim_whitespace/
        # remove_duplicate)를 자동으로 켬 (fill_null 제외, 2026-07-17. 해제 시에는 영향 없음)
        self._rule_checkboxes["custom_rule"].stateChanged.connect(self._on_custom_rule_toggled)

        rl.addSpacing(12)

        run_row = QHBoxLayout()
        run_row.addStretch()
        run_btn = parts.action_btn("정제 실행")
        run_btn.setFixedWidth(120)
        run_btn.clicked.connect(lambda: self._run_refine())
        run_row.addWidget(run_btn)
        rl.addLayout(run_row)

        bl.addWidget(rw)
        bl.addStretch()
        self.tab_widget.addTab(rules_widget, "② 정제 규칙 설정")

    # ── 탭 ③ 정제 결과 ────────────────────────────────────────────────
    def _build_refined_tab(self):
        refined_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        ref_layout = QVBoxLayout(refined_widget)
        ref_layout.setContentsMargins(0, 0, 0, 0)
        ref_layout.addWidget(scroll)

        # 정제 결과 요약 카드
        ref_sum_w, ref_sum_l = parts.card_widget("정제 결과 요약")
        rsg = QHBoxLayout()
        rsg.setSpacing(10)
        self.ref_total  = StatCard("정제 후 행 수", "—")
        self.ref_removed = StatCard("제거된 행",    "—", RED)
        self.ref_filled  = StatCard("치환된 값",    "—", AMBER)
        self.ref_rate    = StatCard("정제율",        "—", GREEN)
        for card in [self.ref_total, self.ref_removed, self.ref_filled, self.ref_rate]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            rsg.addWidget(card, 1)
        ref_sum_l.addLayout(rsg)
        bl.addWidget(ref_sum_w)

        # 정제 데이터 테이블
        rtcw, rtc = parts.card_widget("정제 데이터 (REFINED)")
        ref_ctrl = QHBoxLayout()

        self.refined_search_box = QLineEdit()
        self.refined_search_box.setPlaceholderText("🔍 검색")
        self.refined_search_box.setFixedWidth(220)
        self.refined_search_box.textChanged.connect(self._apply_refined_filter)
        ref_ctrl.addWidget(self.refined_search_box)

        self.refined_count_lbl = QLabel("— rows")
        self.refined_count_lbl.setStyleSheet(
            f"color:{GREEN}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        ref_ctrl.addWidget(self.refined_count_lbl)
        ref_ctrl.addStretch()

        exp_btn = parts.action_btn("EXTRACT")
        exp_btn.clicked.connect(lambda: self._extract_result_table(source="refined"))
        ref_ctrl.addWidget(exp_btn)
        rtc.addLayout(ref_ctrl)

        self.refined_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.refined_table.itemClicked.connect(self._show_refined_detail)
        self.refined_table.currentItemChanged.connect(self._on_refined_current_item_changed)
        rtc.addWidget(self.refined_table)
        bl.addWidget(rtcw, 1)

        # 정제 결과 상세
        rdw, rdl = parts.card_widget("선택 항목 상세 (정제 후)")
        self.refined_detail_lbl = parts.make_label("테이블에서 행을 클릭하세요.", TEXT_MUTED, 12)
        rdl.addWidget(self.refined_detail_lbl)
        bl.addWidget(rdw)

        self.tab_widget.addTab(refined_widget, "③ 정제 결과")

    # ── 탭 ④ Before / After 비교 ─────────────────────────────────────
    def _build_compare_tab(self):
        cmp_widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(12)
        scroll.setWidget(body)
        cmp_layout = QVBoxLayout(cmp_widget)
        cmp_layout.setContentsMargins(0, 0, 0, 0)
        cmp_layout.addWidget(scroll)

        # 정제 요약 카드
        cmp_sum_w, cmp_sum_l = parts.card_widget("정제 요약")
        csg = QHBoxLayout()
        csg.setSpacing(10)
        self.cmp_raw_total  = StatCard("Raw 행 수",    "—")
        self.cmp_ref_total  = StatCard("정제 후 행 수", "—", GREEN)
        self.cmp_removed    = StatCard("제거된 행",     "—", RED)
        self.cmp_rate       = StatCard("정제율",        "—", ACCENT_LIGHT)
        for card in [self.cmp_raw_total, self.cmp_ref_total, self.cmp_removed, self.cmp_rate]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            csg.addWidget(card, 1)
        cmp_sum_l.addLayout(csg)
        bl.addWidget(cmp_sum_w)

        # 좌우 비교 테이블 (Raw | Refined)
        side_w = QWidget()
        side_l = QHBoxLayout(side_w)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(10)

        # 좌: Raw
        raw_cmp_w, raw_cmp_l = parts.card_widget("Raw 데이터")
        self.cmp_raw_count = QLabel("— rows")
        self.cmp_raw_count.setStyleSheet(
            f"color:{AMBER}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        raw_cmp_l.addWidget(self.cmp_raw_count)
        self.cmp_raw_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        raw_cmp_l.addWidget(self.cmp_raw_table)
        side_l.addWidget(raw_cmp_w, 1)

        # 우: Refined
        ref_cmp_w, ref_cmp_l = parts.card_widget("정제 데이터")
        self.cmp_ref_count = QLabel("— rows")
        self.cmp_ref_count.setStyleSheet(
            f"color:{GREEN}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        ref_cmp_l.addWidget(self.cmp_ref_count)
        self.cmp_ref_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        ref_cmp_l.addWidget(self.cmp_ref_table)
        side_l.addWidget(ref_cmp_w, 1)

        bl.addWidget(side_w, 1)

        # 좌우 테이블 세로 스크롤 동기화
        self.cmp_raw_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_cmp_vscroll(self.cmp_raw_table, self.cmp_ref_table, v))
        self.cmp_ref_table.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_cmp_vscroll(self.cmp_ref_table, self.cmp_raw_table, v))

        # 좌우 테이블 정렬 동기화 (같은 컬럼명·방향)
        self.cmp_raw_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_raw_table, self.cmp_ref_table, idx, order))
        self.cmp_ref_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_ref_table, self.cmp_raw_table, idx, order))

        self.tab_widget.addTab(cmp_widget, "④ Before / After 비교")

    # ── 워커 시그널 수신: 실시간 수집 결과 테이블 행 추가 ────────────
    def _reset_monitor_page(self):
        """중지 또는 수집 시작 시 — 모든 탭의 데이터 및 위젯 초기화"""
        # ① Raw 탭
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        self.result_table.setColumnCount(0)
        self.result_table.setSortingEnabled(True)
        self._all_rows       = []
        self._collected_data = []
        self._existing_keys  = set()
        self.count_lbl.setText("0 rows")
        self.sum_total.update_value(0)
        self.sum_ok.update_value(0)
        self.sum_err.update_value(0)
        self.sum_warn.update_value(0)
        self.detail_lbl.setText("테이블에서 행을 클릭하세요.")

        # ② 정제 결과 탭
        self._refined_data = []
        self.refined_table.setSortingEnabled(False)
        self.refined_table.setRowCount(0)
        self.refined_table.setColumnCount(0)
        self.refined_table.setSortingEnabled(True)
        self.refined_count_lbl.setText("— rows")
        self.ref_total.update_value("—")
        self.ref_removed.update_value("—")
        self.ref_filled.update_value("—")
        self.ref_rate.update_value("—")
        self.refined_detail_lbl.setText("테이블에서 행을 클릭하세요.")

        # ③ 비교 탭
        self.cmp_raw_table.setSortingEnabled(False)
        self.cmp_raw_table.setRowCount(0)
        self.cmp_raw_table.setColumnCount(0)
        self.cmp_raw_table.setSortingEnabled(True)
        self.cmp_ref_table.setSortingEnabled(False)
        self.cmp_ref_table.setRowCount(0)
        self.cmp_ref_table.setColumnCount(0)
        self.cmp_ref_table.setSortingEnabled(True)
        self.cmp_raw_count.setText("— rows")
        self.cmp_ref_count.setText("— rows")
        self.cmp_raw_total.update_value("—")
        self.cmp_ref_total.update_value("—")
        self.cmp_removed.update_value("—")
        self.cmp_rate.update_value("—")


    # ── 추출 관련 메서드 ──────────────────────────────────────────────
    def preprocess(self, task):
        """정제 단계 진입 직전 상태 준비 — 실제 FILE/DB 추출은 _extract_result_table()이 수행."""
        # seq_no/needs_cleaning 등 정제 시 참조할 현재 작업 정보 보관
        self._current_task = task or {}
        self._cleaning_warned = False   # 새 수집 결과 — 팝업 안내 여부 초기화

        if not self._collected_data:
            if (task or {}).get("job") in self._SILENT_JOBS:
                # 무인 실행 중 블로킹 모달 방지 — 로그만 남기고 조용히 스킵 (이슈 ⑱)
                lm = getattr(self.window(), "log_manager", None)
                if lm:
                    lm.append_log("warn", "무인 실행 — 수집된 데이터가 없어 추출/정제를 건너뜁니다.")
            else:
                QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return
