# trigger/monitor.py
# MonitorPageSingle의 필터·상세·추출·다이얼로그 메서드(MonitorPageTriggers).

import os
import csv
import json
import sys
import subprocess

from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QWidget,
    QTableWidgetItem, QGridLayout, QStackedWidget, QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import db_conn
import utility
import customized_settings
from conf import get_spider_mode, BlueprintStorage
from style import TagButton, Divider, apply_render_safety_limits
from preprocess import DataRefiner, RefineStats, load_custom_rule, custom_rule_exists

from .common import (
    parts, BG_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER, GREEN, AMBER, RED, VALUE_COLORS, _normalize_save_type,
    _build_db_settings_fields, _build_output_file_page, _wire_db_test_button,
    _build_collect_settings_fields, _default_dialog_qss,
    _warn_custom_rule_missing as _common_warn_custom_rule_missing,
    _warn_needs_cleaning_false as _common_warn_needs_cleaning_false,
    _handle_custom_rule_toggle,
)


def _make_cell_item(val) -> QTableWidgetItem:
    """값이 숫자면 DisplayRole로, 아니면 텍스트로 QTableWidgetItem을 만든다
    (숫자는 정렬 시 문자열이 아닌 값으로 비교되도록 setData를 사용).
    전경색/배경색은 호출 측이 필요에 따라 이어서 설정한다."""
    item = QTableWidgetItem()
    if isinstance(val, (int, float)):
        item.setData(Qt.ItemDataRole.DisplayRole, val)
    else:
        item.setText(str(val) if val is not None else "—")
    return item


def _next_available_name(base_name: str, suffix_fmt: str, exists) -> str:
    """base_name이 이미 존재하면(exists) suffix_fmt(예: "{base} ({count})")로
    접미사를 붙여가며 존재하지 않는 이름을 찾을 때까지 반복합니다.
    CSV/JSON 파일명, DB 테이블명의 "새로 만들기(중복 회피)" 저장 경로가 공유합니다."""
    if not exists(base_name):
        return base_name
    count = 1
    while True:
        candidate = suffix_fmt.format(base=base_name, count=count)
        if not exists(candidate):
            return candidate
        count += 1


class MonitorPageTriggers:
    """MonitorPageSingle의 필터·상세·추출·다이얼로그 메서드"""

    def _add_realtime_row(self, row: dict):
        self._all_rows.append(row)
        resp = row.get("resp_info", {})
        data = resp.get("data", [])
        if not isinstance(data, list) or not data:
            return
        columns = self._get_result_columns()
        if self.result_table.columnCount() == 0:
            self.result_table.setColumnCount(len(columns) + 1)
            self.result_table.setHorizontalHeaderLabels(["NO"] + columns)
        self.result_table.setSortingEnabled(False)

        # 중복 감지용 키 집합은 self._existing_keys에 증분 유지(매 호출마다 재구축하지 않음)
        for entry in data:
            if not isinstance(entry, dict):
                continue
            entry_key = str(tuple(str(entry.get(c, "")) for c in columns))
            is_dup = entry_key in self._existing_keys
            is_empty_row = all(
                entry.get(c) in (None, "", "null", "None")
                for c in columns
            )
            self._collected_data.append(entry)
            self._existing_keys.add(entry_key)

            current_row = self.result_table.rowCount()
            self.result_table.insertRow(current_row)

            # 행 배경색 — 중복: 빨강, 전체 컬럼 빈 값: 주황, 정상(1개 이상 값 존재): 기본
            if is_dup:
                row_bg = QColor(RED).darker(180)
            elif is_empty_row:
                row_bg = QColor(AMBER).darker(220)
            else:
                row_bg = QColor(0, 0, 0, 0)

            no_item = QTableWidgetItem()
            no_item.setData(Qt.ItemDataRole.DisplayRole, current_row)
            no_item.setForeground(QColor(TEXT_MUTED))
            if row_bg.alpha() > 0:
                no_item.setBackground(row_bg)
            self.result_table.setItem(current_row, 0, no_item)

            for col_idx, col_name in enumerate(columns, start=1):
                val = entry.get(col_name, "—")
                item = _make_cell_item(val)
                item.setForeground(QColor(TEXT_PRIMARY))
                if row_bg.alpha() > 0:
                    item.setBackground(row_bg)
                self.result_table.setItem(current_row, col_idx, item)

        self.result_table.setSortingEnabled(True)
        self.count_lbl.setText(f"{self.result_table.rowCount()} rows")
        self._update_summary_cards()

    def _update_summary_cards(self):
        """Raw 탭 요약 카드: 전체 / 정상 / 전체 null / 중복 집계"""
        columns = self._get_result_columns()
        total = len(self._collected_data)
        empty_rows = 0
        dup_rows  = 0
        seen_keys: set = set()
        for entry in self._collected_data:
            is_empty_row = all(
                entry.get(c) in (None, "", "null", "None") for c in columns
            )
            key = tuple(str(entry.get(c, "")) for c in columns)
            is_dup = key in seen_keys
            seen_keys.add(key)
            if is_empty_row:
                empty_rows += 1
            if is_dup:
                dup_rows += 1
        normal = total - empty_rows - dup_rows
        self.sum_total.update_value(total)
        self.sum_ok.update_value(max(normal, 0))
        self.sum_err.update_value(empty_rows)
        self.sum_warn.update_value(dup_rows)

    def _apply_filter(self):
        keyword = self.search_box.text().lower().strip()
        if not keyword:
            for r in range(self.result_table.rowCount()):
                self.result_table.setRowHidden(r, False)
            self.count_lbl.setText(f"{self.result_table.rowCount()} rows")
            return
        visible = 0
        for r in range(self.result_table.rowCount()):
            matched = any(
                self.result_table.item(r, c) and
                keyword in self.result_table.item(r, c).text().lower()
                for c in range(self.result_table.columnCount())
            )
            self.result_table.setRowHidden(r, not matched)
            if matched:
                visible += 1
        self.count_lbl.setText(f"{visible} rows")

    def _apply_refined_filter(self):
        """정제 결과 탭 검색 필터"""
        keyword = self.refined_search_box.text().lower().strip()
        if not keyword:
            for r in range(self.refined_table.rowCount()):
                self.refined_table.setRowHidden(r, False)
            self.refined_count_lbl.setText(f"{self.refined_table.rowCount()} rows")
            return
        visible = 0
        for r in range(self.refined_table.rowCount()):
            matched = any(
                self.refined_table.item(r, c) and
                keyword in self.refined_table.item(r, c).text().lower()
                for c in range(self.refined_table.columnCount())
            )
            self.refined_table.setRowHidden(r, not matched)
            if matched:
                visible += 1
        self.refined_count_lbl.setText(f"{visible} rows")

    # ── 탭 전환 감지 — 정제 규칙 미설정 안내 ───────────────────────────
    def _on_monitor_tab_changed(self, index: int):
        """
        "② 정제 규칙 설정" 탭(index=1)에 들어올 때마다 needs_cleaning(블루프린트가
        DB에서 내려주는 "정제 필요" 플래그)과 refine/{seq_no}.py 존재 여부를
        함께 확인해 "커스텀 정제 규칙 적용" 체크박스를 무조건 재설정합니다.
        활성화 판정 로직 자체는 최초 진입이든 재진입이든 동일합니다:

        - needs_cleaning=True AND 스크립트 있음 → 체크(활성화).
        - needs_cleaning=False → 체크 해제(비활성화)
          (스크립트 존재 여부는 보지 않음 — pass/fail을 가르는 STEP 01).
        - needs_cleaning=True인데 스크립트 없음 → 체크 해제(비활성화)
          (STEP 01 통과 후 STEP 02에서 탈락).

        다만 "경고 안내창을 띄우는지"는 최초 진입 여부에 따라 다릅니다:

        - 최초 진입(이 페이지 인스턴스에서 이 탭에 처음 들어왔을 때, 1회뿐):
          비활성화로 판정되어도 경고를 띄우지 않습니다.
        - 재진입(2회차부터): 비활성화로 판정될 때마다 원인에 맞는 경고를
          띄웁니다(needs_cleaning=False → "정제 대상 아님",
          needs_cleaning=True인데 스크립트 없음 → "정제 규칙 없음"). 같은
          수집 결과 내 반복 방문이라도 게이팅하지 않고 매번 띄웁니다.

        체크박스는 blockSignals로 감싸 setChecked한다 — 그냥 setChecked를
        부르면 stateChanged가 _on_custom_rule_toggled → _handle_custom_rule_toggle로
        이어지며 그 안에서 (스크립트 존재 여부만으로) 별도 경고를 다시 띄워
        중복 팝업이 뜬다.

        seq_no는 _current_task가 아니라 _active_blueprint_info()에서 읽는다 —
        수집을 아직 한 번도 안 돌린 시점에도(=_current_task가 비어 있어도)
        이 블루프린트 고유의 값을 즉시 알 수 있어야, 처음 탭을 열었을 때도
        정상적으로 동작한다.
        """
        if index != 1:
            return

        seq_no = self._active_blueprint_info().get("seq_no")
        if not seq_no:
            return

        needs_cleaning = bool(self._active_blueprint_info().get("needs_cleaning"))
        exists = custom_rule_exists(seq_no) if needs_cleaning else False
        should_enable = needs_cleaning and exists

        cb = self._rule_checkboxes.get("custom_rule")
        if cb is not None:
            cb.blockSignals(True)
            cb.setChecked(should_enable)
            cb.blockSignals(False)

        is_first_entry = not self._refine_tab_entered
        self._refine_tab_entered = True

        if should_enable or is_first_entry:
            return
        if not needs_cleaning:
            self._warn_needs_cleaning_false(seq_no)
        else:
            self._warn_custom_rule_missing(seq_no)

    # ── 커스텀 정제 규칙 체크박스 연동 ───────────────────────────────
    def _warn_custom_rule_missing(self, seq_no) -> None:
        """"커스텀 정제 규칙 적용"에 필요한 refine/{seq_no}.py 정제 스크립트가
        없을 때 공통으로 띄우는 경고 — 체크박스를 직접 켤 때
        (_on_custom_rule_toggled)와 "② 정제 규칙 설정" 탭에 들어올 때마다
        (_on_monitor_tab_changed) 양쪽에서 동일한 문구를 쓰기 위해 하나로
        묶는다. 문구 자체는 trigger/common.py에 있다 — 스케줄 등록 다이얼로그
        (trigger/scheduler.py)도 그 함수를 그대로 재사용한다(이 메서드는
        self._active_blueprint_info()로 title을 얻어 전달만 함)."""
        title = self._active_blueprint_info().get("title") or seq_no
        _common_warn_custom_rule_missing(self, title)

    def _warn_needs_cleaning_false(self, seq_no) -> None:
        """"커스텀 정제 규칙 적용"을 쓰려는 수집 대상이 애초에 "정제 필요"로
        설정되어 있지 않을 때 띄우는 경고 — "② 정제 규칙 설정" 탭에 들어올
        때마다(_on_monitor_tab_changed) 사용한다. 문구 자체는
        trigger/common.py에 있다(정제 스크립트 없음 경고와 동일한 패턴)."""
        title = self._active_blueprint_info().get("title") or seq_no
        _common_warn_needs_cleaning_false(self, title)

    def _on_custom_rule_toggled(self, state):
        """"커스텀 정제 규칙 적용"(②) 체크박스의 stateChanged 핸들러 — 실제
        검증/자동 연동 로직은 trigger/common.py의 _handle_custom_rule_toggle이
        전담하며(스케줄 등록 다이얼로그와 공유), 여기서는 seq_no와 경고 콜백만
        이 클래스의 컨텍스트(_active_blueprint_info/_rule_checkboxes)로
        채워 넘긴다. fill_null(⑥, 결측값 치환)은 자동 연동 대상에서 제외된다
        (2026-07-17, 사용자 요청 — 커스텀 규칙이 정규화한 데이터라도 결측값
        치환 여부는 별도로 판단해야 한다는 판단).
        """
        seq_no = self._active_blueprint_info().get("seq_no")
        _handle_custom_rule_toggle(
            state, seq_no, self._rule_checkboxes,
            lambda: self._warn_custom_rule_missing(seq_no),
        )

    # ── 정제 실행 ─────────────────────────────────────────────────────
    def _run_refine(
        self,
        rules_override: dict[str, bool] | None = None,
        skip_ui_update: bool = False,
        fill_value_override: str | None = None,
    ):
        """
        규칙 탭의 체크박스 상태를 읽어 DataRefiner를 구성하고 정제를 실행합니다.
        preprocess.DataRefiner가 실제 정제 로직을 전담합니다.

        rules_override: 전달되면 체크박스 상태 대신 이 규칙 dict를 그대로 사용합니다
            (스케줄 자동 저장 등 — 실행 시점의 화면 상태에 의존하지 않도록 고정 규칙을
            적용할 때 사용. 체크박스·제외 컬럼 등 화면 상태는 전혀 읽지 않음).
        skip_ui_update: True면 정제 결과 테이블/요약/비교 탭 갱신과 탭 자동 전환을
            건너뜁니다 (무인 실행 중 화면을 건드리지 않기 위함).
        fill_value_override: rules_override와 함께 전달되는 null 치환값(⑥fill_null).
            None이면(rules_override 경로에서) 빈 값을 사용합니다. rules_override가
            None일 때는(수동 실행) 무시되고 화면 입력값(fill_null_input)이 사용됩니다.
        """
        lm = getattr(self.window(), 'log_manager', None)

        if not self._collected_data:
            if skip_ui_update:
                # 무인 실행 중 블로킹 모달 방지 — 로그만 남기고 조용히 스킵 (이슈 ⑱)
                if lm:
                    lm.append_log("warn", "무인 실행 — 수집된 데이터가 없어 정제를 건너뜁니다.")
            else:
                QMessageBox.warning(self, "정제 불가", "수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return

        if rules_override is not None:
            active_rules  = dict(rules_override)
            drop_columns  = []
            fill_value    = fill_value_override if fill_value_override is not None else ""
        else:
            # 체크박스 → _refine_rules 동기화
            for key, cb in self._rule_checkboxes.items():
                self._refine_rules[key] = cb.isChecked()

            # 제외 컬럼 — "제외 필드 지정" 다이얼로그의 적용 시 self._drop_column_names에
            # 이미 반영되어 있으므로 여기서는 그대로 사용

            # null 치환값 파싱 (입력창 기본값은 빈 문자열 — 비워두면 빈 값으로 치환)
            raw_fill = getattr(self, 'fill_null_input', None)
            if raw_fill is not None:
                self._fill_null_value = raw_fill.text()

            active_rules = self._refine_rules
            drop_columns = self._drop_column_names
            fill_value   = self._fill_null_value

        # ── 사용자 정의 정제 규칙(있으면) 로드 — 실행은 DataRefiner의 ② custom_rule step이 담당 ──
        # seq_no/needs_cleaning은 현재 수집(task)에 귀속된 값이라 수집마다 다름
        seq_no         = self._current_task.get("seq_no")
        needs_cleaning = self._current_task.get("needs_cleaning", False)
        custom_rule_fn = None

        if needs_cleaning and seq_no:
            try:
                custom_rule_fn = load_custom_rule(seq_no)
            except Exception as e:
                custom_rule_fn = None
                if lm:
                    lm.append_log("err", f"사용자 정의 정제 규칙 로드 실패 (seq_no={seq_no}): {e}")

            if custom_rule_fn is None and lm:
                lm.append_log(
                    "warn",
                    f"사용자 정의 정제 규칙 파일을 찾을 수 없습니다 (seq_no={seq_no}). "
                    f"범용 규칙만 적용합니다."
                )

        # DataRefiner 구성 및 실행
        refiner = DataRefiner(
            rules        = active_rules,
            drop_columns = drop_columns,
            custom_rule  = custom_rule_fn,
            fill_value   = fill_value,
        )
        try:
            refined, stats = refiner.run(self._collected_data)
        except (TypeError, ValueError) as e:
            QMessageBox.critical(self, "정제 오류", f"정제 중 오류가 발생했습니다.\n\n{e}")
            return

        self._refined_data = refined

        custom_rule_note = ""
        if stats.custom_rule_applied:
            custom_rule_note = ", 사용자 정의 규칙 적용됨"
        elif stats.custom_rule_error:
            custom_rule_note = ", 사용자 정의 규칙 실행 실패"
            if lm:
                lm.append_log(
                    "err",
                    f"사용자 정의 정제 규칙 실행 실패 (seq_no={seq_no}): {stats.custom_rule_error}. "
                    f"원본 데이터로 계속합니다."
                )

        if not skip_ui_update:
            # UI 갱신
            self._populate_refined_table(refined)
            self._update_refined_summary(stats)
            self._update_compare_tab(self._collected_data, refined, stats)

            # 정제 결과 탭으로 자동 이동
            self.tab_widget.setCurrentIndex(2)

        # 로그 기록
        if lm:
            lm.append_log(
                "ok",
                f"정제 완료 — Raw {stats.raw_count}행 → 정제 후 {stats.refined_count}행 "
                f"(제거 {stats.removed}행, 치환 {stats.filled}건, 정제율 {stats.refine_rate}"
                f"{custom_rule_note})"
            )

    # ── 정제 규칙 설정 영속화 ─────────────────────────────────────────
    def _persist_refine_settings(self):
        """"정제 규칙 설정" 탭의 체크박스/입력값을 블루프린트에 영속화한다 —
        출력 설정(_open_output_settings_dialog)과 동일하게 BlueprintStorage에
        저장해 다음에 이 수집 대상을 열었을 때 그대로 복원되도록 한다.
        custom_rule은 탭 진입마다 needs_cleaning/스크립트 존재 여부로 항상
        재계산되므로(_on_monitor_tab_changed) 저장 대상에서 제외한다."""
        seq_no = self._active_blueprint_info().get("seq_no")
        if not seq_no:
            return
        refine_settings = {
            key: cb.isChecked()
            for key, cb in self._rule_checkboxes.items()
            if key != "custom_rule"
        }
        refine_settings["fill_null_value"] = self.fill_null_input.text()
        refine_settings["drop_column_names"] = self._drop_column_names
        BlueprintStorage().update_settings(seq_no, refine_settings=refine_settings)

    # ── "제외 필드 지정"(⑤) 요약 라벨 갱신 ───────────────────────────
    def _update_drop_columns_summary(self):
        n = len(self._drop_column_names)
        self.drop_columns_summary_lbl.setText(f"{n}개 필드 제외 중" if n else "제외 필드 없음")

    # ── Raw 수집 결과 존재 여부 확인 (없으면 경고) ───────────────────
    def _has_collected_data_or_warn(self) -> bool:
        """self._collected_data가 있으면 True, 없으면 경고를 띄우고 False를 반환합니다.

        "제외 필드 지정" 체크박스 활성화 시(layout_single.py)와 "⚙ 필드 선택" 버튼
        클릭 시(_open_drop_columns_dialog) 양쪽에서 공유하는 헬퍼입니다.
        """
        if self._collected_data:
            return True
        QMessageBox.warning(
            self, "필드 선택 불가",
            "수집된 데이터가 없습니다.\n수집을 먼저 진행한 후 필드를 선택해 주세요."
        )
        return False

    # ── "제외 필드 지정"(⑤) 필드 다중 선택 Dialog ───────────────────
    def _open_drop_columns_dialog(self):
        """제외할 필드를 선택하는 별도 Dialog — 필드 수십 개도 그리드+스크롤로 대응.

        체크 상태의 source of truth는 self._drop_column_names(list[str])이며,
        이 다이얼로그의 버튼은 열 때마다 새로 만들어 그 값으로 초기화하고
        [적용] 시에만 다시 self._drop_column_names에 반영합니다 — 다이얼로그를
        닫아도(취소) 값이 유지되도록.
        """
        if not self._has_collected_data_or_warn():
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("제외 필드 선택")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(_default_dialog_qss())

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(22, 18, 22, 18)
        vl.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.addWidget(parts.make_label("제외 필드 선택", TEXT_PRIMARY, 14, True))
        title_row.addStretch()
        vl.addLayout(title_row)
        vl.addSpacing(10)
        vl.addWidget(Divider())
        vl.addSpacing(14)

        vl.addWidget(parts.make_label("추출 결과에서 제외할 필드를 선택하세요.", TEXT_MUTED, 11))
        vl.addSpacing(10)

        field_names = self._get_result_columns()
        field_buttons: dict[str, TagButton] = {}

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(6)

        if field_names:
            cols = 4
            for i, field in enumerate(field_names):
                btn = TagButton(field)
                btn.setChecked(field in self._drop_column_names)
                field_buttons[field] = btn
                grid.addWidget(btn, i // cols, i % cols)
        else:
            grid.addWidget(parts.make_label("설정된 필드가 없습니다.", TEXT_MUTED, 11), 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(200)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{BG_PRIMARY}; border:1px solid {BORDER}; border-radius:6px;}}"
        )
        scroll.setWidget(container)
        vl.addWidget(scroll)
        vl.addSpacing(16)
        vl.addWidget(Divider())
        vl.addSpacing(12)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def _apply():
            self._drop_column_names = [name for name, btn in field_buttons.items() if btn.isChecked()]
            self._update_drop_columns_summary()
            self._persist_refine_settings()
            dlg.accept()

        apply_btn = parts.action_btn("적용")
        apply_btn.clicked.connect(_apply)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(cancel_btn)
        vl.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()

    def _populate_refined_table(self, data: list):
        """정제 결과 탭 테이블에 데이터 채우기"""
        columns = self._get_result_columns()
        if self._refine_rules.get("drop_columns") and self._drop_column_names:
            columns = [c for c in columns if c not in self._drop_column_names]
        self.refined_table.setSortingEnabled(False)
        self.refined_table.setRowCount(0)
        self.refined_table.setColumnCount(len(columns) + 1)
        self.refined_table.setHorizontalHeaderLabels(["NO"] + columns)
        for row_idx, entry in enumerate(data):
            self.refined_table.insertRow(row_idx)
            no_item = QTableWidgetItem()
            no_item.setData(Qt.ItemDataRole.DisplayRole, row_idx + 1)
            no_item.setForeground(QColor(TEXT_MUTED))
            self.refined_table.setItem(row_idx, 0, no_item)
            for col_idx, col_name in enumerate(columns, start=1):
                val = entry.get(col_name, "—")
                item = _make_cell_item(val)
                item.setForeground(QColor(TEXT_PRIMARY))
                self.refined_table.setItem(row_idx, col_idx, item)
        self.refined_table.setSortingEnabled(True)
        self.refined_count_lbl.setText(f"{len(data)} rows")

    def _update_refined_summary(self, stats: RefineStats):
        """정제 결과 탭 요약 카드 갱신 (RefineStats 객체 수신)"""
        self.ref_total.update_value(stats.refined_count)
        self.ref_removed.update_value(stats.removed)
        self.ref_filled.update_value(stats.filled)
        self.ref_rate.update_value(stats.refine_rate)

    def _update_compare_tab(self, raw_data: list, refined_data: list, stats=None):
        """비교 탭 Raw / Refined 테이블 및 요약 카드 갱신.

        stats(RefineStats)가 주어지면 삭제된 Raw 행은 빨간 음영,
        값이 변경된 Refined 행만 초록 음영으로 표시됩니다.
        """
        CLR_DEL_FG = QColor(RED)
        CLR_REF_FG = QColor(GREEN)

        deleted_set      = set(stats.deleted_indices) if stats else set()
        modified_rows_set = set(stats.modified_rows)  if stats else set()

        columns = self._get_result_columns()
        ref_columns = (
            [c for c in columns if c not in self._drop_column_names]
            if self._refine_rules.get("drop_columns") and self._drop_column_names
            else columns
        )

        # ── 좌: Raw 테이블 — 삭제 행 빨간 음영, 생존 행 기본색 ────────
        self.cmp_raw_table.setSortingEnabled(False)
        self.cmp_raw_table.setRowCount(0)
        self.cmp_raw_table.setColumnCount(len(columns) + 1)
        self.cmp_raw_table.setHorizontalHeaderLabels(["NO"] + columns)
        for row_idx, entry in enumerate(raw_data):
            self.cmp_raw_table.insertRow(row_idx)
            is_deleted = row_idx in deleted_set

            no_item = QTableWidgetItem()
            no_item.setData(Qt.ItemDataRole.DisplayRole, row_idx + 1)
            no_item.setForeground(QColor(TEXT_MUTED))
            self.cmp_raw_table.setItem(row_idx, 0, no_item)

            for col_idx, col_name in enumerate(columns, start=1):
                val  = entry.get(col_name, "—")
                item = QTableWidgetItem()
                item.setText(str(val) if val is not None else "—")
                if is_deleted:
                    item.setForeground(CLR_DEL_FG)
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                self.cmp_raw_table.setItem(row_idx, col_idx, item)
        self.cmp_raw_table.setSortingEnabled(True)
        self.cmp_raw_count.setText(f"{len(raw_data)} rows")

        # ── 우: Refined 테이블 — 변경된 행만 초록 음영 ─────────────────
        self.cmp_ref_table.setSortingEnabled(False)
        self.cmp_ref_table.setRowCount(0)
        self.cmp_ref_table.setColumnCount(len(ref_columns) + 1)
        self.cmp_ref_table.setHorizontalHeaderLabels(["NO"] + ref_columns)
        for row_idx, entry in enumerate(refined_data):
            self.cmp_ref_table.insertRow(row_idx)
            is_modified = row_idx in modified_rows_set

            no_item = QTableWidgetItem()
            no_item.setData(Qt.ItemDataRole.DisplayRole, row_idx + 1)
            no_item.setForeground(QColor(TEXT_MUTED))
            # 팝업(layout/single/monitor.py의 _apply_refined_text_color)이 글자색을
            # 보고 "정제됨"을 역추론하지 않고 이 값을 그대로 읽도록 명시적으로
            # 저장해 둔다 — 화면 표시 방식(색)과 데이터(정제 여부)를 분리.
            no_item.setData(Qt.ItemDataRole.UserRole, is_modified)
            self.cmp_ref_table.setItem(row_idx, 0, no_item)

            for col_idx, col_name in enumerate(ref_columns, start=1):
                val  = entry.get(col_name, "—")
                item = _make_cell_item(val)
                if is_modified:
                    item.setForeground(CLR_REF_FG)
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                item.setData(Qt.ItemDataRole.UserRole, is_modified)
                self.cmp_ref_table.setItem(row_idx, col_idx, item)
        self.cmp_ref_table.setSortingEnabled(True)
        self.cmp_ref_count.setText(f"{len(refined_data)} rows")

        # ── 요약 카드 ────────────────────────────────────────────────────
        raw_total = len(raw_data)
        ref_total = len(refined_data)
        removed   = raw_total - ref_total
        rate = f"{ref_total / raw_total * 100:.1f}%" if raw_total else "—"
        self.cmp_raw_total.update_value(raw_total)
        self.cmp_ref_total.update_value(ref_total)
        self.cmp_removed.update_value(removed)
        self.cmp_rate.update_value(rate)

    # ── 비교 탭 좌우 테이블 스크롤·정렬 동기화 ──────────────────────────
    def _sync_cmp_vscroll(self, source, target, value):
        """비교 탭 좌우 테이블의 세로 스크롤 위치를 상호 동기화합니다."""
        if target.verticalScrollBar().value() == value:
            return
        target.verticalScrollBar().setValue(value)

    def _link_vscroll_group(self, tables: list) -> None:
        """여러 테이블의 세로 스크롤을 하나의 그룹으로 묶어, 그중 하나를
        움직이면 나머지 전부가 같은 위치로 따라 움직이게 한다(원본 Raw/정제
        비교 카드 + 팝업 Raw/정제 테이블처럼 개수가 2개보다 많아져도 동작).
        _sync_cmp_vscroll의 "이미 같은 값이면 손대지 않는다" 가드를 그대로
        재사용하므로, 같은 쌍이 여러 번 연결돼도(예: 팝업을 열 때마다) 재귀나
        무한 루프 없이 안전하다."""
        for table in tables:
            others = [t for t in tables if t is not table]
            # src/targets를 기본 인자로 묶어야 한다 — 그냥 클로저로 table/others를
            # 참조하면 파이썬의 late binding 때문에 모든 람다가 루프의 마지막
            # table 값을 공유해버린다(지금은 _sync_cmp_vscroll이 source 인자를
            # 안 쓰고 있어 겉으로 드러나지 않을 뿐, 잠재 버그이므로 바로잡는다).
            table.verticalScrollBar().valueChanged.connect(
                lambda value, src=table, targets=others: [
                    self._sync_cmp_vscroll(src, t, value) for t in targets
                ]
            )

    def _sync_cmp_sort(self, source, target, logical_index, order):
        """비교 탭 좌우 테이블의 정렬을 같은 컬럼명·방향으로 동기화합니다.

        Raw/Refined는 행 수·컬럼 구성이 다를 수 있어(중복/null 행 제거,
        drop_columns) "같은 줄에 같은 원본 행"까지는 보장하지 않고, 같은
        컬럼명·정렬 방향만 맞춥니다. 대응 컬럼이 반대쪽에 없으면(예:
        drop_columns로 제외된 컬럼) 아무 것도 하지 않습니다.
        """
        header_item = source.horizontalHeaderItem(logical_index)
        if header_item is None:
            return
        col_name = header_item.text()

        # sortIndicatorSection()은 사용자가 아직 정렬한 적 없는 테이블에서도
        # columnCount()와 같은 범위 밖 값을 반환할 수 있어(Qt 특성, 컬럼 수 변경 후
        # 미갱신 상태) 반드시 상한까지 확인해야 함 (헤더 아이템 None 접근 방지)
        target_header  = target.horizontalHeader()
        target_sec     = target_header.sortIndicatorSection()
        if 0 <= target_sec < target.columnCount():
            target_item = target.horizontalHeaderItem(target_sec)
            if (target_item is not None and target_item.text() == col_name
                    and target_header.sortIndicatorOrder() == order):
                return  # 이미 동일 상태 — 상호 연결로 인한 재귀 호출 종료

        for i in range(target.columnCount()):
            item = target.horizontalHeaderItem(i)
            if item is not None and item.text() == col_name:
                target.sortByColumn(i, order)
                return

    def _render_detail(self, table, label, row, columns):
        """행 상세 정보를 컬럼별로 렌더링해 label에 표시한다 (_show_detail/_show_refined_detail 공용)."""
        detail_parts = []
        for col_idx, col_name in enumerate(columns):
            cell = table.item(row, col_idx + 1)
            val = cell.text() if cell else "—"
            detail_parts.append(
                f"<b style='color:{ACCENT_LIGHT};'>{col_name}:</b> "
                f"<span style='color:{VALUE_COLORS.get(col_idx, TEXT_MUTED)};'>{val}</span>"
            )
        label.setText("<br>".join(detail_parts))
        label.setTextFormat(Qt.TextFormat.RichText)

    def _show_refined_detail(self, item):
        """정제 결과 탭 행 클릭 — 상세 표시"""
        columns = self._get_result_columns()
        if self._refine_rules.get("drop_columns") and self._drop_column_names:
            columns = [c for c in columns if c not in self._drop_column_names]
        self._render_detail(self.refined_table, self.refined_detail_lbl, item.row(), columns)

    def _on_current_item_changed(self, current, previous):
        if current is not None:
            self._show_detail(current)

    def _on_refined_current_item_changed(self, current, previous):
        """정제 결과 탭 — 키보드 방향키·클릭으로 currentItemChanged 수신 시 상세 표시"""
        if current is not None:
            self._show_refined_detail(current)

    def _show_detail(self, item):
        columns = self._get_result_columns()
        self._render_detail(self.result_table, self.detail_lbl, item.row(), columns)

    def _open_output_settings_dialog(self, *, collect: dict = None, auth_page=None):
        """출력 대상 / 상세 설정(인라인) / AUTO SAVE Dialog.

        collect: 지정하면(다중 레이아웃 전용) "수집 설정"(Delay/Threads/Timeout/
            Retry/Auto Save) 섹션을 상단에 추가하고, 다이얼로그 제목도 "수집
            설정"으로 바뀐다. None이면(단일 레이아웃의 기존 호출) 이 섹션 없이
            기존과 완전히 동일하게 "추출 설정"만 노출한다.
        auth_page: 지정하면(다중 레이아웃에서 인증이 필요한 블루프린트) 그
            AuthManagerPage 위젯을 다이얼로그 하단에 통째로 얹는다 — 열려있는
            동안만 잠깐 reparent했다가 닫히면 다시 떼어낸다(캐시된 위젯이므로
            다이얼로그가 파괴될 때 함께 파괴되면 안 된다).
        """
        dlg = QDialog(self)
        title = "수집 설정" if collect is not None else "추출 설정"
        dlg.setWindowTitle(title)
        # "인증 관리" 섹션(전역 인증 옵션 체크박스 3개 + 상태 라벨)은 단일 레이아웃의
        # 전체 화면 폭을 기준으로 만들어져 있어, 기존 500px 폭에서는 라벨이 잘린다.
        # "수집 설정" 섹션도 Delay/Threads/Timeout/Retry를 한 줄로 배치하므로 동일하게
        # 넓은 폭이 필요하다. collect 또는 auth_page 중 하나라도 있으면(=다중 레이아웃
        # 호출) 폭을 넓힌다 — 단일 레이아웃 호출(collect=auth_page=None)은 계속 500px
        # 그대로.
        dlg.setFixedWidth(680 if (collect is not None or auth_page is not None) else 500)
        dlg.setStyleSheet(_default_dialog_qss())

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(22, 18, 22, 18)
        vl.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.addWidget(parts.make_label(title, TEXT_PRIMARY, 14, True))
        title_row.addStretch()
        vl.addLayout(title_row)
        vl.addSpacing(10)
        vl.addWidget(Divider())
        vl.addSpacing(14)

        def _boxed(content: QWidget, margins: int = 14) -> QWidget:
            """"상세 설정" 박스(아래 QStackedWidget#extractStack)와 동일한 프레임
            (배경/테두리/라운드)으로 다른 섹션의 내용물을 감싼다 — 다이얼로그 안
            섹션들의 시각적 통일감을 맞추기 위함. objectName으로 선택자를 좁혀서
            바레 QWidget 선택자가 스타일시트 없는 자식(체크박스 등)까지 테두리를
            상속시키는 문제를 피한다(아래 #extractStack, blueprint_list.py의
            체크박스 래퍼와 동일한 관례)."""
            box = QWidget()
            box.setObjectName("settingsBox")
            box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            box.setStyleSheet(f"""
                QWidget#settingsBox {{
                    background:{BG_PRIMARY}; border:1px solid {BORDER}; border-radius:6px;
                }}
            """)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(margins, margins, margins, margins)
            box_layout.addWidget(content)
            return box

        collect_widgets = None
        if collect is not None:
            collect_title = parts.make_label("수집 설정", TEXT_MUTED, 10)
            collect_title.setStyleSheet(collect_title.styleSheet() + " letter-spacing:1px;")
            vl.addWidget(collect_title)
            vl.addSpacing(10)

            collect_content, collect_widgets = _build_collect_settings_fields(collect, single_row=True)
            if get_spider_mode(self._active_blueprint_info()) == "html_render":
                apply_render_safety_limits(
                    collect_widgets["thread_spin"], collect_widgets["delay_spin"],
                    customized_settings.get_render_safety_limits(),
                )
            # "수집 설정" 위젯 자체는 여백 0(단일 대시보드의 parts.card_widget() 카드
            # 안에 들어갈 때를 기준으로 설계됨) — 박스가 14px 안쪽 여백을 대신 공급한다.
            vl.addWidget(_boxed(collect_content))
            vl.addSpacing(14)
            vl.addWidget(Divider())
            vl.addSpacing(14)

        out_file_btn = TagButton("FILE")
        out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        out_db_btn   = TagButton("DB")
        out_db_btn.setToolTip("데이터베이스 서버로 전송")

        self._out_mode = "FILE" if self.output_info["extract"]["file"]["enabled"] else "DB"
        out_file_btn.setChecked(self._out_mode == "FILE")
        out_db_btn.setChecked(self._out_mode == "DB")

        is_file_mode = out_file_btn.isChecked()

        out_mode_lbl = parts.make_label(
            "로컬 파일 저장 모드" if is_file_mode else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(parts.make_label("출력 대상", TEXT_SECONDARY, 12))
        out_row.addSpacing(6)
        out_row.addWidget(out_file_btn)
        out_row.addWidget(out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(out_mode_lbl)
        out_row.addStretch()
        vl.addLayout(out_row)
        vl.addSpacing(14)
        vl.addWidget(Divider())
        vl.addSpacing(14)

        detail_title = parts.make_label("상세 설정", TEXT_MUTED, 10)
        detail_title.setStyleSheet(detail_title.styleSheet() + " letter-spacing:1px;")
        vl.addWidget(detail_title)
        vl.addSpacing(10)

        stack = QStackedWidget()
        stack.setObjectName("extractStack")
        stack.setStyleSheet(f"""
            QStackedWidget#extractStack {{
                background:{BG_PRIMARY}; border:1px solid {BORDER}; border-radius:6px;
            }}
            QStackedWidget#extractStack > QWidget {{ background:{BG_PRIMARY}; border:none; }}
        """)
        stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # ── PAGE 0: FILE 설정 ─────────────────────────────
        file_page, _file_widgets, _toggle_csv_fields = _build_output_file_page(
            self.output_info["extract"]["file"], dlg
        )
        path_edit, file_nm, fmt_combo = (
            _file_widgets["path_edit"], _file_widgets["file_nm"], _file_widgets["fmt_combo"]
        )
        enc_combo, csv_delimeter = _file_widgets["enc_combo"], _file_widgets["csv_delimeter"]

        open_path_chk = QCheckBox("저장 완료 후 폴더 열기")
        open_path_chk.setChecked(self.output_info["extract"]["file"]["is_open_save_path"])
        file_page.layout().addWidget(open_path_chk)
        stack.addWidget(file_page)  # index 0

        # ── PAGE 1: DB 설정 ───────────────────────────────
        db_page = QWidget()
        dp = QVBoxLayout(db_page)
        dp.setContentsMargins(14, 14, 14, 14)
        dp.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)
        db_widgets = _build_db_settings_fields(grid, self.output_info["extract"]["db"])
        _db_type, _db_host, _db_port  = db_widgets["db_type"], db_widgets["host"], db_widgets["port"]
        _db_name, _db_schema          = db_widgets["name"], db_widgets["schema"]
        _db_user, _db_pw, _db_data    = db_widgets["user"], db_widgets["password"], db_widgets["save_data_nm"]
        dp.addLayout(grid)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        test_btn = parts.outline_btn("TEST CONNECTION")
        test_result_lbl = parts.make_label("", TEXT_MUTED, 11)
        _wire_db_test_button(test_btn, test_result_lbl, db_widgets, dlg)
        test_row.addWidget(test_btn)
        test_row.addWidget(test_result_lbl)
        test_row.addStretch()
        dp.addLayout(test_row)
        stack.addWidget(db_page)  # index 1

        stack.setCurrentIndex(0 if is_file_mode else 1)

        def update_dialog_size():
            current_page = stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                stack.setFixedHeight(current_page.layout().sizeHint().height())
            dlg.layout().activate()
            dlg.adjustSize()

        def _on_fmt_changed(fmt_text: str):
            _toggle_csv_fields(fmt_text)
            update_dialog_size()

        def _on_file_clicked():
            self._out_mode = "FILE"
            out_mode_lbl.setText("로컬 파일 저장 모드")
            out_db_btn.setChecked(False)
            stack.setCurrentIndex(0)
            stack.setMinimumHeight(0)
            stack.setMaximumHeight(16777215)
            update_dialog_size()

        def _on_db_clicked():
            self._out_mode = "DB"
            out_mode_lbl.setText("DB 서버 전송 모드")
            out_file_btn.setChecked(False)
            stack.setCurrentIndex(1)
            stack.setMinimumHeight(0)
            stack.setMaximumHeight(16777215)
            update_dialog_size()

        out_file_btn.clicked.connect(_on_file_clicked)
        out_db_btn.clicked.connect(_on_db_clicked)
        fmt_combo.currentTextChanged.connect(_on_fmt_changed)
        _on_fmt_changed(fmt_combo.currentText())

        vl.addWidget(stack)

        auth_scroll = None
        auth_body = None
        if auth_page is not None:
            vl.addSpacing(16)
            vl.addWidget(Divider())
            vl.addSpacing(14)
            auth_title = parts.make_label("인증 관리", TEXT_MUTED, 10)
            auth_title.setStyleSheet(auth_title.styleSheet() + " letter-spacing:1px;")
            vl.addWidget(auth_title)
            vl.addSpacing(10)
            # auth_page(AuthManagerPage)는 자체 QScrollArea로 감싸져 있는데(단일
            # 레이아웃에서 전체 화면 페이지로 쓰일 때를 기준으로 설계됨), 그 QScrollArea를
            # 통째로 이 다이얼로그의 QVBoxLayout 안에 넣으면 뷰포트가 세로로 충분히
            # 늘어나지 못해 내용이 작은 창에 스크롤바로 눌려 보인다. QScrollArea 안의
            # 실제 콘텐츠(body)만 꺼내(takeWidget) 박스에 직접 넣어 "수집 설정"/"상세
            # 설정"과 동일하게 내용 크기에 맞춰 자연스럽게 펼쳐지도록 한다 — dlg.exec()
            # 이후 finally에서 auth_scroll.setWidget(auth_body)로 반드시 되돌려 놓아야
            # AuthManagerPage 내부 구조가 다음 번 열람 때도 온전하다.
            auth_scroll = auth_page.layout().itemAt(0).widget()
            auth_body = auth_scroll.takeWidget()
            vl.addWidget(_boxed(auth_body, margins=0))

        vl.addSpacing(16)
        vl.addWidget(Divider())
        vl.addSpacing(12)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def _apply_file():
            try:
                if self._out_mode == "FILE":
                    file_path      = utility.to_forward_slash(os.path.normpath(path_edit.text()))
                    file_name      = utility.update_empty_value(file_nm.text())
                    file_format    = utility.update_empty_value(fmt_combo.currentText())
                    file_encoding  = utility.update_empty_value(enc_combo.currentText())
                    file_delimeter = utility.update_empty_value(csv_delimeter.text())
                    is_open_save_path = open_path_chk.isChecked()
                    self.output_info["extract"]["db"] = customized_settings.get_output_settings()["extract"]["db"]
                    self.output_info["extract"]["file"]["enabled"]           = True
                    self.output_info["extract"]["file"]["file_path"]         = file_path
                    self.output_info["extract"]["file"]["file_name"]         = file_name
                    self.output_info["extract"]["file"]["file_format"]       = file_format
                    self.output_info["extract"]["file"]["file_encoding"]     = file_encoding
                    self.output_info["extract"]["file"]["file_delimiter"]    = file_delimeter
                    self.output_info["extract"]["file"]["is_open_save_path"] = is_open_save_path
                elif self._out_mode == "DB":
                    db_env      = utility.update_empty_value(_db_type.currentText())
                    db_host     = utility.update_empty_value(_db_host.text())
                    db_port     = utility.update_empty_value(_db_port.text())
                    db_schema   = utility.update_empty_value(_db_schema.text())
                    db_name     = utility.update_empty_value(_db_name.text())
                    db_user     = utility.update_empty_value(_db_user.text())
                    db_pass     = utility.update_empty_value(_db_pw.text())
                    save_data_nm = utility.update_empty_value(_db_data.text())
                    self.output_info["extract"]["file"] = customized_settings.get_output_settings()["extract"]["file"]
                    self.output_info["extract"]["file"]["enabled"]          = False
                    self.output_info["extract"]["db"]["enabled"]            = True
                    self.output_info["extract"]["db"]["db_env"]             = db_env
                    self.output_info["extract"]["db"]["host"]               = db_host
                    self.output_info["extract"]["db"]["port"]               = db_port
                    self.output_info["extract"]["db"]["schema"]             = db_schema
                    self.output_info["extract"]["db"]["database"]           = db_name
                    self.output_info["extract"]["db"]["user"]               = db_user
                    self.output_info["extract"]["db"]["password"]           = db_pass
                    self.output_info["extract"]["db"]["save_data_nm"]       = save_data_nm

                if collect_widgets is not None:
                    collect["delay"]      = collect_widgets["delay_spin"].value()
                    collect["threads"]    = collect_widgets["thread_spin"].value()
                    collect["timeout"]    = collect_widgets["timeout_spin"].value()
                    collect["retry"]      = collect_widgets["retry_spin"].value()
                    collect["auto_save"]  = collect_widgets["auto_save_chk"].isChecked()
                    collect["auto_save_source"] = (
                        "refined" if collect_widgets["auto_src_ref_btn"].isChecked() else "raw"
                    )

                # 재시작 후에도 방금 적용한 값이 그대로 표출되도록 블루프린트에
                # 영속화한다(단일/다중 레이아웃이 이 다이얼로그를 공유하므로 두 곳
                # 모두 여기서 함께 저장된다). collect_widgets가 없으면(단일의 "⚙
                # 추출 설정" 버튼처럼 collect 인자 없이 열린 경우) 추출 설정만 저장한다.
                settings_patch = {"output_settings": self.output_info}
                if collect_widgets is not None:
                    settings_patch["collect_settings"] = collect
                BlueprintStorage().update_settings(
                    self._active_blueprint_info().get("seq_no"), **settings_patch
                )

                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "설정 저장 오류", f"{title} 저장 중 오류가 발생했습니다.\n\n{e}")

        apply_btn  = parts.action_btn("적용")
        apply_btn.clicked.connect(_apply_file)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(cancel_btn)
        vl.addLayout(btn_row)

        update_dialog_size()
        dlg.adjustSize()
        try:
            dlg.exec()
        finally:
            if auth_page is not None:
                # dlg는 이 함수를 벗어나면 곧 파괴되는 임시 객체 — auth_body는
                # BlueprintPageBundle(auth_page)에 캐시된 채 계속 살아있어야 하므로,
                # dlg가 파괴되면서 함께 파괴되지 않도록 원래의 auth_scroll로
                # 되돌려 놓는다(takeWidget()의 짝 — QScrollArea의 내부 참조도
                # 함께 정리되어 다음 번 열람 때도 온전하다).
                auth_scroll.setWidget(auth_body)

    def _extract_result_table(self, source: str, silent: bool = False, extract_override: dict = None):
        """
        source: "raw"(_collected_data) 또는 "refined"(_refined_data) — 추출 대상을
        호출부에서 명시적으로 지정합니다. "refined"인데 아직 정제를 실행하지
        않았다면 먼저 _run_refine()을 실행한 뒤 그 결과를 추출합니다.
        silent: True면 데이터가 없을 때 모달 대신 로그만 남기고 조용히 스킵합니다
            (스케줄 자동 저장 등 무인 실행 경로 전용, 이슈 ⑱). 이 경우 "refined"여도
            _run_refine() 폴백을 호출하지 않습니다 — 호출부가 이미 알맞은 고정
            규칙으로 _run_refine()을 실행한 뒤이므로, 여기서 화면 상태 기반으로
            다시 실행하면 무인 실행 취지에 어긋납니다.
        extract_override: 전달되면 self.output_info["extract"] 대신 이 dict를 저장
            목적지/DB 접속정보 소스로 사용합니다(스케줄 자신의 저장 설정 — 대시보드의
            실시간 output_info와는 무관). 이 경우 "schedule_save_type"(새로 만들기/
            덮어쓰기/추가하기)에 따라 모달 없이 결정론적으로 저장합니다. None이면
            (수동 추출 버튼 등) 기존과 동일하게 self.output_info와 확인 모달을 사용합니다.
        """
        lm = getattr(self.window(), 'log_manager', None)

        if source == "refined":
            if not self._refined_data and not silent:
                self._run_refine()
            data = self._refined_data
            if not data:
                if silent:
                    if lm:
                        lm.append_log("warn", "무인 실행 — 정제 결과가 없어 파일/DB 추출을 건너뜁니다.")
                # else: _run_refine()이 이미 "정제 불가" 경고를 띄웠음
                return
        else:
            data = self._collected_data
            if not data:
                if silent:
                    if lm:
                        lm.append_log("warn", "무인 실행 — 수집된 데이터가 없어 파일/DB 추출을 건너뜁니다.")
                else:
                    QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
                return
        headers = list(data[0].keys())

        extract_cfg = extract_override if extract_override is not None else self.output_info["extract"]
        save_type = _normalize_save_type(extract_cfg.get("schedule_save_type")) if extract_override is not None else None

        try:
            if extract_cfg["file"]["enabled"] is True:
                file_path   = extract_cfg["file"]["file_path"]
                file_name   = extract_cfg["file"]["file_name"]
                file_format = extract_cfg["file"]["file_format"]

                if file_format == "CSV":
                    delimiter = extract_cfg["file"]["file_delimiter"]
                    if save_type is None:
                        final_file_name = _next_available_name(
                            file_name, "{base} ({count})",
                            lambda name: os.path.exists(os.path.join(file_path, f"{name}.csv")),
                        )
                        with open(os.path.join(file_path, f"{final_file_name}.csv"),
                                  mode='w', encoding='utf-8-sig', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
                            writer.writeheader()
                            writer.writerows(data)
                    else:
                        self._write_csv_unattended(file_path, file_name, delimiter, headers, data, save_type)

                elif file_format == "JSON":
                    if save_type is None:
                        if os.path.exists(os.path.join(file_path, f"{file_name}.json")):
                            reply = QMessageBox.question(
                                self, '덮어쓰기 확인',
                                f"'{file_name}.json' 파일이 이미 존재합니다.\n덮어쓰시겠습니까?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No
                            )
                            if reply == QMessageBox.StandardButton.No:
                                return
                        with open(os.path.join(file_path, f"{file_name}.json"), 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=4)
                    else:
                        self._write_json_unattended(file_path, file_name, data, save_type, lm)

                # 스케줄(무인) 실행은 저장 폴더를 여는 사람이 없으므로 설정값과
                # 무관하게 항상 열지 않는다 — 고정값으로 강제. 스케줄 자체 저장
                # 설정(extract_override)에는 이 키가 애초에 없으므로(대시보드
                # output_info에만 존재) get()으로 안전하게 조회한다.
                is_open_save_path = extract_cfg["file"].get("is_open_save_path", False)
                if file_path and is_open_save_path and not silent:
                    if sys.platform == 'win32':
                        os.startfile(file_path)
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', file_path])
                    else:
                        subprocess.Popen(['xdg-open', file_path])

            elif extract_cfg["db"]["enabled"] is True:
                db_info = extract_cfg["db"]
                try:
                    if save_type is None:
                        is_exist  = db_conn._check_db_table_exists(db_info)
                        save_mode = 'append'
                        if is_exist:
                            msg_box = QMessageBox(self)
                            msg_box.setWindowTitle("DB 데이터 처리 선택")
                            msg_box.setText(
                                f"'{db_info['save_data_nm']}' 테이블이 이미 존재합니다.\n어떻게 처리하시겠습니까?")
                            msg_box.setIcon(QMessageBox.Icon.Question)
                            btn_overwrite = msg_box.addButton("덮어쓰기(새로 생성)",
                                                              QMessageBox.ButtonRole.DestructiveRole)
                            btn_append    = msg_box.addButton("추가 적재(이어 쓰기)",
                                                              QMessageBox.ButtonRole.AcceptRole)
                            msg_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
                            msg_box.setDefaultButton(btn_append)
                            msg_box.exec()
                            clicked = msg_box.clickedButton()
                            if clicked == btn_overwrite:
                                save_mode = 'overwrite'
                            elif clicked == btn_append:
                                save_mode = 'append'
                            else:
                                return
                        db_conn.save_db(db_info, data, mode=save_mode)
                    else:
                        self._save_db_unattended(db_info, data, save_type, lm)
                except Exception as e:
                    QMessageBox.critical(
                        self, "DB 저장 실패",
                        f"DB 접속 및 로그인 정보가 올바르지 않습니다.\n\n[시스템 에러 내용]\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "추출 오류", str(e))

    def _write_csv_unattended(self, file_path, file_name, delimiter, headers, data, save_type):
        """무인(스케줄) 실행 전용 — save_type("new"/"overwrite"/"append")에 따라 CSV를 모달 없이 저장합니다."""
        full_path = os.path.join(file_path, f"{file_name}.csv")
        if save_type == "new":
            final_file_name = _next_available_name(
                file_name, "{base} ({count})",
                lambda name: os.path.exists(os.path.join(file_path, f"{name}.csv")),
            )
            full_path = os.path.join(file_path, f"{final_file_name}.csv")
            mode, write_header = 'w', True
        elif save_type == "overwrite":
            mode, write_header = 'w', True
        else:  # "append"
            write_header = not os.path.exists(full_path)
            mode = 'a'
        with open(full_path, mode=mode, encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
            if write_header:
                writer.writeheader()
            writer.writerows(data)

    def _write_json_unattended(self, file_path, file_name, data, save_type, lm):
        """무인(스케줄) 실행 전용 — save_type("new"/"overwrite"/"append")에 따라 JSON을 모달 없이 저장합니다."""
        full_path = os.path.join(file_path, f"{file_name}.json")
        if save_type == "new" and os.path.exists(full_path):
            final_file_name = _next_available_name(
                file_name, "{base} ({count})",
                lambda name: os.path.exists(os.path.join(file_path, f"{name}.json")),
            )
            full_path = os.path.join(file_path, f"{final_file_name}.json")
            out_data = data
        elif save_type == "append" and os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    out_data = existing + data
                else:
                    out_data = data
                    if lm:
                        lm.append_log("warn", f"'{file_name}.json' 기존 내용이 배열이 아니어서 새 데이터로 대체합니다.")
            except Exception as e:
                out_data = data
                if lm:
                    lm.append_log("warn", f"'{file_name}.json' 읽기 실패, 새로 씁니다: {e}")
        else:  # "overwrite", 또는 파일이 없는 "new"/"append"
            out_data = data
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(out_data, f, ensure_ascii=False, indent=4)

    def _save_db_unattended(self, db_info, data, save_type, lm):
        """무인(스케줄) 실행 전용 — save_type("new"/"overwrite"/"append")에 따라 DB에 모달 없이 저장합니다."""
        if save_type == "overwrite":
            db_conn.save_db(db_info, data, mode='overwrite')
        elif save_type == "append":
            db_conn.save_db(db_info, data, mode='append')
        else:  # "new" — 기존 테이블은 건드리지 않고 이름에 접미사를 붙여 새로 생성
            base_name = db_info["save_data_nm"]
            final_name = _next_available_name(
                base_name, "{base}_{count}",
                lambda name: db_conn._check_db_table_exists({**db_info, "save_data_nm": name}),
            )
            target = dict(db_info)
            target["save_data_nm"] = final_name
            if final_name != base_name and lm:
                lm.append_log("info", f"DB 테이블 '{base_name}' 이미 존재 — '{final_name}'(으)로 새로 생성합니다.")
            db_conn.save_db(target, data, mode='overwrite')
