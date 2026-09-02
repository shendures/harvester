# layout/single/monitor.py

import customized_settings

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTabWidget, QCheckBox, QMessageBox, QDialog, QTableWidgetItem, QSplitter,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor

from trigger import MonitorPageTriggers
from trigger.common import _default_dialog_qss
from style import StatCard, EqualSpacingTable, build_refine_rule_rows, _load_svg_icon
from ..common import (
    parts, build_scroll_body,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BORDER, ACCENT, ACCENT_LIGHT,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, GREEN, AMBER, RED,
)
from .common import ActiveBlueprintMixin, count_badge_qss


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
        self.output_info     = self._active_blueprint_info().get("output_settings") or customized_settings.get_output_settings()

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
            QTabWidget::tab-bar {{
                left: 14px;
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
        bl = build_scroll_body(raw_widget, spacing=12)

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
        self.count_lbl.setStyleSheet(count_badge_qss(ACCENT_LIGHT))
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
        bl = build_scroll_body(rules_widget, spacing=12)

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
        bl = build_scroll_body(refined_widget, spacing=12)

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
        self.refined_count_lbl.setStyleSheet(count_badge_qss(GREEN))
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
        bl = build_scroll_body(cmp_widget, spacing=12)

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

        # "Raw 데이터"/"정제 데이터" 카드 바로 위, 카드로 감싸지 않은 독립된
        # 행에 "새 창에서 함께 보기" 버튼을 둔다 — 두 카드 중 어느 한쪽에
        # 속하지 않으면서도 그 둘과 같은 영역에 있다는 인상을 주기 위함.
        popout_row = QHBoxLayout()
        popout_row.addStretch()
        cmp_popout_btn = parts.outline_btn("")
        cmp_popout_btn.setIcon(_load_svg_icon("external-link", TEXT_SECONDARY, "2", 14))
        cmp_popout_btn.setIconSize(QSize(14, 14))
        cmp_popout_btn.setFixedSize(30, 20)
        cmp_popout_btn.setToolTip("Raw/정제 데이터를 새 창에서 함께 보기")
        cmp_popout_btn.clicked.connect(self._open_compare_popup)
        popout_row.addWidget(cmp_popout_btn)
        bl.addLayout(popout_row)

        # 좌우 비교 테이블 (Raw | Refined)
        side_w = QWidget()
        side_l = QHBoxLayout(side_w)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(10)

        # 좌: Raw
        raw_cmp_w, raw_cmp_l = parts.card_widget("Raw 데이터")
        self.cmp_raw_count = QLabel("— rows")
        self.cmp_raw_count.setStyleSheet(count_badge_qss(AMBER))
        raw_cmp_l.addWidget(self.cmp_raw_count)
        self.cmp_raw_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        raw_cmp_l.addWidget(self.cmp_raw_table)
        side_l.addWidget(raw_cmp_w, 1)

        # 우: Refined
        ref_cmp_w, ref_cmp_l = parts.card_widget("정제 데이터")
        self.cmp_ref_count = QLabel("— rows")
        self.cmp_ref_count.setStyleSheet(count_badge_qss(GREEN))
        ref_cmp_l.addWidget(self.cmp_ref_count)
        self.cmp_ref_table = EqualSpacingTable(parent=self, row_height=26, col_padding=8, hscroll_handle=50)
        ref_cmp_l.addWidget(self.cmp_ref_table)
        side_l.addWidget(ref_cmp_w, 1)

        bl.addWidget(side_w, 1)

        # 좌우 테이블 세로 스크롤 동기화
        self._link_vscroll_group([self.cmp_raw_table, self.cmp_ref_table])

        # 좌우 테이블 정렬 동기화 (같은 컬럼명·방향)
        self.cmp_raw_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_raw_table, self.cmp_ref_table, idx, order))
        self.cmp_ref_table.horizontalHeader().sortIndicatorChanged.connect(
            lambda idx, order: self._sync_cmp_sort(self.cmp_ref_table, self.cmp_raw_table, idx, order))

        self.tab_widget.addTab(cmp_widget, "④ Before / After 비교")

    @staticmethod
    def _copy_table_contents(dest: EqualSpacingTable, source: EqualSpacingTable) -> None:
        """source(Raw/정제 비교 테이블)의 헤더 라벨과 모든 셀 텍스트를 dest에
        그대로 복사한다. 위젯 자체를 옮기는 게 아니라 내용만 복사하므로
        source는 원래 자리에 그대로 남는다."""
        col_count = source.columnCount()
        dest.setColumnCount(col_count)
        dest.setHorizontalHeaderLabels([
            source.horizontalHeaderItem(c).text() if source.horizontalHeaderItem(c) else ""
            for c in range(col_count)
        ])
        dest.setRowCount(source.rowCount())
        for r in range(source.rowCount()):
            for c in range(col_count):
                src_item = source.item(r, c)
                dest.setItem(r, c, QTableWidgetItem(src_item.text() if src_item else ""))

    @staticmethod
    def _apply_refined_text_color(popup_table: EqualSpacingTable, source_table: EqualSpacingTable) -> None:
        """source_table(정제 데이터 비교 테이블)에서 정제 과정에 값이 바뀐 행을
        찾아, 복사본인 popup_table에 메인 창의 "정제 데이터" 카드
        (trigger/monitor.py:_update_compare_tab, 514-536행)와 동일한 배색
        규칙을 그대로 재현한다 — "NO" 컬럼은 항상 TEXT_MUTED, 값 컬럼은
        정제된 행이면 GREEN, 아니면 TEXT_PRIMARY(배경색이 아니라 글자색).
        "정제됨" 여부는 글자색을 보고 역추론하지 않고, _update_compare_tab이
        각 아이템에 직접 저장해 둔 Qt.ItemDataRole.UserRole 값을 그대로
        읽는다 — 화면에 보이는 색이 무엇이든 항상 정확하다."""
        col_count = source_table.columnCount()
        for r in range(source_table.rowCount()):
            no_src = source_table.item(r, 0)
            is_modified = bool(no_src.data(Qt.ItemDataRole.UserRole)) if no_src else False

            no_dest = popup_table.item(r, 0)
            if no_dest:
                no_dest.setForeground(QColor(TEXT_MUTED))

            value_fg = QColor(GREEN) if is_modified else QColor(TEXT_PRIMARY)
            for c in range(1, col_count):
                dest_item = popup_table.item(r, c)
                if dest_item:
                    dest_item.setForeground(value_fg)

    def _open_compare_popup(self) -> None:
        """Raw/정제 데이터를 한 창에서 나란히 보여주는 모달리스 팝업을 연다.
        내용은 두 원본 테이블(self.cmp_raw_table/self.cmp_ref_table)의 현재
        스냅샷을 복사한 것이라(_copy_table_contents) 원본 비교 뷰는 그대로
        유지된다. 팝업의 두 테이블끼리만 세로 스크롤을 동기화하고
        (_link_vscroll_group) 원본 Raw/정제 카드와는 서로 독립적으로
        움직인다. 행 순서가 어긋나면 스크롤 위치 동기화가 무의미해지므로
        팝업 쪽 정렬은 막아둔다. 두 카드는 QSplitter로 묶어 드래그로 폭을
        조절할 수 있다(layout/multi/main_window.py의 monitor_split과 동일한
        패턴). LogViewerDialog(trigger/log_viewer.py)와 동일한 QDialog +
        setModal(False) 패턴을 재사용한다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Raw / 정제 데이터 비교")
        dlg.setModal(False)
        dlg.resize(1400, 600)
        dlg.setMinimumSize(700, 400)
        dlg.setStyleSheet(_default_dialog_qss())
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(9)

        raw_w, raw_l = parts.card_widget("Raw 데이터")
        popup_raw_table = EqualSpacingTable(parent=dlg, row_height=26, col_padding=8, hscroll_handle=50)
        popup_raw_table.setSortingEnabled(False)
        self._copy_table_contents(popup_raw_table, self.cmp_raw_table)
        raw_l.addWidget(popup_raw_table)
        splitter.addWidget(raw_w)

        ref_w, ref_l = parts.card_widget("정제 데이터")
        popup_ref_table = EqualSpacingTable(parent=dlg, row_height=26, col_padding=8, hscroll_handle=50)
        popup_ref_table.setSortingEnabled(False)
        self._copy_table_contents(popup_ref_table, self.cmp_ref_table)
        self._apply_refined_text_color(popup_ref_table, self.cmp_ref_table)
        ref_l.addWidget(popup_ref_table)
        splitter.addWidget(ref_w)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 700])
        lay.addWidget(splitter)

        # 팝업 안의 두 테이블끼리만 묶는다 — 원본 Raw/정제 카드는 이미 자기들끼리
        # 별도로 동기화돼 있고(위 327-328행), 팝업과 원본은 서로 독립적으로
        # 스크롤돼야 하므로 여기서 원본 테이블을 함께 묶지 않는다.
        self._link_vscroll_group([popup_raw_table, popup_ref_table])

        dlg.show()

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
