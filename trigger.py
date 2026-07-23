# trigger.py
# 각 페이지 클래스의 기능(액션) 메서드를 Mixin 클래스로 분리 관리합니다.
# layout.py의 각 클래스가 해당 Mixin을 다중상속하여 메서드를 주입받습니다.
#
# MRO(메서드 탐색 순서):  PageClass → QWidget → ... → PageMixin → object
# QWidget 계열 메서드와 충돌하지 않으며, self.xxx 속성은 layout.py의
# _build()에서 이미 생성되어 있으므로 참조 안전합니다.

import os
import re
import csv
import json
import sys
import socket
import subprocess
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QCheckBox, QWidget,
    QTableWidgetItem, QGridLayout, QStackedWidget,
    QSizePolicy, QSystemTrayIcon, QMainWindow,
    QTextEdit, QMenu, QSpinBox, QDoubleSpinBox, QDateEdit,
    QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QDate, pyqtSignal
from PyQt6.QtGui import QColor, QTextDocument, QTextCursor
from worker import MultiprocessWorker
from conf import BlueprintStorage

import db_conn
import utility
import customized_settings
from conf import DataStore
from style import THEME, TagButton, Divider, Parts, build_refine_rule_rows
from preprocess import DataRefiner, RefineStats, load_custom_rule, custom_rule_exists, DEFAULT_RULES

store    = DataStore()
theme    = THEME()
parts    = Parts()

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

# 상세 보기(_show_detail 계열)에서 값 유무에 따른 텍스트 색상
VALUE_COLORS = {0: ACCENT_LIGHT, 1: TEXT_PRIMARY, 2: GREEN, 3: RED}

# DB 타입별 기본 포트 (추출 설정/스케줄 DB 저장 다이얼로그 공용)
DB_PORTS = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}

# 스케줄(무인) 실행에서 정제 데이터 자동 저장 시 적용하는 규칙 — 원래는 모든
# 스케줄에 고정 적용되는 상수였으나(2026-07-17 이전), 이제 "새 스케줄 등록"
# 다이얼로그의 "⚙ 정제 규칙 설정"에서 스케줄별로 구성 가능해졌다. 이 상수는
# ①해당 다이얼로그를 아직 한 번도 열지 않은 신규 등록의 기본값, ②"refine_rules"
# 키가 없는 기존(구버전) 스케줄의 실행 시 폴백값으로만 쓰인다(_on_finished() 참고).
# "② 커스텀 정제 규칙 적용" 체크 시 자동으로 켜지는 조합(①③④)과는 별개 설정이다
# (2026-07-17, fill_null을 자동 연동 대상에서 제외하며 분리 — 이 상수의 fill_null
# 값은 그대로 유지해 이미 저장된 스케줄의 동작이 조용히 바뀌지 않도록 함).
SCHEDULED_REFINE_RULES = {
    "remove_null_row":  True,
    "custom_rule":      True,
    "trim_whitespace":  True,
    "remove_duplicate": True,
    "drop_columns":     False,
    "fill_null":        True,
    "cast_numeric":     False,
}

# 스케줄 정제 규칙 설정 다이얼로그의 신규 등록 기본값 — SCHEDULED_REFINE_RULES가
# 아니라 preprocess.DEFAULT_RULES(정제 엔진 자체의 기본값, MonitorPage "②
# 정제 규칙 설정" 탭의 초기 체크 상태와 값이 동일)에서 파생시킨다(2026-07-17).
# "값이 우연히 같다"가 아니라 같은 소스에서 나오도록 해, 향후 DEFAULT_RULES가
# 다시 바뀌어도 이 다이얼로그의 기본값이 자동으로 함께 맞춰지게 하기 위함.
# "제외 필드 지정"은 설정 항목 자체에서 빠지므로 키를 포함하지 않는다(Raw 수집
# 결과를 봐야 설정 가능한 규칙이라 무인 실행에는 애초에 노출하지 않음 —
# preprocess.DataRefiner는 누락된 키를 DEFAULT_RULES 기준으로 취급하므로 문제
# 없음). SCHEDULED_REFINE_RULES(실행 시 폴백값)와는 이제 별개 값이다 — fill_null이
# DEFAULT_RULES 기준 False인 반면 SCHEDULED_REFINE_RULES는 True로 유지된다.
SCHEDULED_REFINE_RULES_DIALOG_DEFAULT = {
    k: v for k, v in DEFAULT_RULES.items() if k != "drop_columns"
}


# ══════════════════════════════════════════════════════
#  SEARCH LINE EDIT  (한국어 IME 조합 중 텍스트 즉시 감지)
# ══════════════════════════════════════════════════════
class SearchLineEdit(QLineEdit):
    """
    한국어 IME 조합 중 글자도 즉시 검색에 반영하는 QLineEdit.

    기본 QLineEdit.textChanged는 IME 조합이 확정(commit)될 때만 발생하므로
    "수집"을 입력할 때 "수"를 누른 시점에는 신호가 오지 않습니다.
    inputMethodEvent를 오버라이드하여 preedit(조합 중) 텍스트 변경 시에도
    composing_changed 시그널을 emit, 실시간 검색을 가능하게 합니다.

    [조합 완료 시 중복 호출 방지]
    조합 완료 시 inputMethodEvent의 preeditString()이 ""가 되므로
    committed + "" = committed — textChanged와 동일한 값이 전달됩니다.
    _run_search() 내부에서 _last_keyword 비교로 중복 탐색을 차단합니다.
    """
    composing_changed = pyqtSignal(str)   # 조합 중 포함 전체 텍스트

    def inputMethodEvent(self, event):
        super().inputMethodEvent(event)       # 기본 IME 처리 유지 (화면 표시 등)
        preedit   = event.preeditString()     # 현재 조합 중인 글자
        committed = self.text()               # 이미 확정된 텍스트
        self.composing_changed.emit(committed + preedit)


# ══════════════════════════════════════════════════════
#  LOG VIEWER DIALOG  (전체 로그 확인 모달리스 다이얼로그)
# ══════════════════════════════════════════════════════
class LogViewerDialog(QDialog):
    """
    로그 버퍼를 직접 소유하고 표시하는 모달리스 다이얼로그.
    - LogView를 대체: _html_history 버퍼, append_log(), clear_all(), last_log 시그널 자체 보유
    - 앱 시작 시 싱글턴으로 생성되어 백그라운드에서 로그를 처음부터 축적
    - 닫기(×) 버튼은 hide()로 처리 — 실제 파괴 없이 재오픈 가능
    - 레벨 필터(ALL / INFO / OK / WARN / ERR) 및 키워드 검색 지원
    """

    # last_log: 하단 상태바에 최신 로그 한 줄을 실시간 전달하는 시그널
    last_log = pyqtSignal(str, str)   # (level, message)

    # 레벨별 색상 (THEME과 동일)
    _LEVEL_COLORS = {
        "ok":   GREEN,
        "err":  RED,
        "warn": AMBER,
        "info": ACCENT_LIGHT,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        # ── 로그 버퍼 (구 LogView._html_history) ──────────────────────────
        self._html_history: list[tuple[str, str]] = []   # [(level, html), ...]
        # ── 검색 상태 ─────────────────────────────────────────────────────
        self._active_filter = "ALL"
        self._last_keyword  = ""    # 검색어 변경 감지 — 바뀌면 커서 리셋
        self._total_matches = 0     # 현재 뷰어 기준 전체 매치 수
        self._current_match = 0     # 현재 위치 (1-based, 0=미탐색)
        self.setWindowTitle("전체 로그")
        self.setModal(False)          # 모달리스: 메인 창 조작 유지
        self.resize(760, 500)
        self.setMinimumSize(520, 320)
        self.setStyleSheet(f"""
            QDialog {{
                background:{BG_SECONDARY};
                border:1px solid {BORDER};
                border-radius:10px;
            }}
        """)
        self._build()

    # ── 로그 수신 (구 LogView.append_log) ───────────────────────────────
    def append_log(self, level: str, message: str) -> None:
        """
        외부(Worker, GlobalToolbar 등)에서 호출 — 이력 버퍼에 누적하고
        다이얼로그가 열려 있을 때는 뷰어에도 즉시 반영합니다.
        last_log 시그널로 하단 상태바에 실시간 전달합니다.
        """
        ts    = datetime.now().strftime("%H:%M:%S")
        color = self._LEVEL_COLORS.get(level, TEXT_SECONDARY)
        tag   = f"[{level.upper():4s}]"
        line_html = (
            f'<span style="color:{TEXT_MUTED};">{ts}</span> '
            f'<span style="color:{color}; font-weight:bold;">{tag}</span> '
            f'<span style="color:{TEXT_SECONDARY};">{message}</span>'
        )
        self._html_history.append((level, line_html))
        # 다이얼로그가 열려 있을 때만 뷰어에 실시간 반영
        if self.isVisible() and self._passes_filter(level):
            self._viewer.append(line_html)
            self._scroll_to_bottom()
        self.last_log.emit(level, message)

    # ── 전체 초기화 (구 LogView.clear_all) ──────────────────────────────
    def clear_all(self) -> None:
        """이력 버퍼와 뷰어 표시 내용을 동시에 초기화합니다."""
        self._html_history.clear()
        self._viewer.clear()
        self._reset_search_state()

    # ── UI 구성 ──────────────────────────────────────
    def _build(self):
        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(10)

        # 헤더 행
        hdr = QHBoxLayout()
        title = QLabel("전체 로그")
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:14px; font-weight:bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{TEXT_SECONDARY};
                border:1px solid {BORDER};border-radius:5px;padding:4px 12px;font-size:12px;}}
            QPushButton:hover{{background:{BG_HOVER};color:{ACCENT_LIGHT};border-color:{ACCENT_LIGHT};}}
        """)
        close_btn.clicked.connect(self.hide)   # 싱글턴 — destroy 대신 hide
        hdr.addWidget(close_btn)
        vl.addLayout(hdr)

        # 구분선
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{BORDER};")
        vl.addWidget(div)

        # 필터 버튼 행
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_btns: dict[str, QPushButton] = {}
        for lv in ["ALL", "INFO", "OK", "WARN", "ERR"]:
            btn = QPushButton(lv)
            btn.setCheckable(True)
            btn.setChecked(lv == "ALL")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._filter_btn_style(lv == "ALL"))
            btn.clicked.connect(lambda _, b=lv: self._apply_filter(b))
            self._filter_btns[lv] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()

        # 지우기 버튼
        clr_btn = QPushButton("지우기")
        clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clr_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};
                border:1px solid {RED};border-radius:5px;padding:3px 10px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        clr_btn.clicked.connect(self._clear_log)
        filter_row.addWidget(clr_btn)
        vl.addLayout(filter_row)

        # ── 검색 행 ──────────────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self._search_input = SearchLineEdit()
        self._search_input.setPlaceholderText("🔍  로그 검색  (Enter: 다음 ↓   Shift+Enter: 이전 ↑)")
        self._search_input.setFixedHeight(28)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER}; border-radius:5px;
                padding:0 8px; font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{ACCENT}; }}
        """)
        # textChanged: 확정 텍스트 기준 집계 (영문·숫자·조합 완료)
        self._search_input.textChanged.connect(self._update_match_count)
        # composing_changed: 한국어 IME 조합 중 텍스트 즉시 감지
        self._search_input.composing_changed.connect(self._update_match_count_with)
        # returnPressed는 keyPressEvent에서 통합 처리하므로 미연결
        search_row.addWidget(self._search_input, 1)

        _nav_btn_style = (
            f"QPushButton{{background:transparent;color:{TEXT_SECONDARY};"
            f"border:1px solid {BORDER};border-radius:5px;"
            f"padding:3px 10px;font-size:11px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{ACCENT_LIGHT};"
            f"border-color:{ACCENT_LIGHT};}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        self._btn_prev = QPushButton("▲ 이전")
        self._btn_prev.setFixedHeight(28)
        self._btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.setStyleSheet(_nav_btn_style)
        self._btn_prev.setEnabled(False)
        self._btn_prev.clicked.connect(self._search_prev)
        search_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("▼ 다음")
        self._btn_next.setFixedHeight(28)
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.setStyleSheet(_nav_btn_style)
        self._btn_next.setEnabled(False)
        self._btn_next.clicked.connect(self._search_next)
        search_row.addWidget(self._btn_next)

        self._search_count_lbl = QLabel("")
        self._search_count_lbl.setFixedWidth(90)
        self._search_count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._search_count_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        search_row.addWidget(self._search_count_lbl)

        vl.addLayout(search_row)
        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(f"""
            QTextEdit {{
                background:{BG_PRIMARY}; color:{TEXT_SECONDARY};
                border:1px solid {BORDER}; border-radius:6px;
                font-size:11px; font-family:'Consolas', monospace; padding:6px;
            }}
        """)
        vl.addWidget(self._viewer, 1)

    def _filter_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton{{background:{ACCENT};color:white;"
                f"border:none;border-radius:5px;padding:3px 10px;font-size:11px;font-weight:bold;}}"
                f"QPushButton:hover{{background:{ACCENT_HOVER};}}"
            )
        return (
            f"QPushButton{{background:transparent;color:{TEXT_SECONDARY};"
            f"border:1px solid {BORDER};border-radius:5px;padding:3px 10px;font-size:11px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{ACCENT_LIGHT};border-color:{ACCENT_LIGHT};}}"
        )

    # ── 이력 로드 및 필터 ────────────────────────────
    def _load_history(self):
        """열릴 때 기존 이력 전체 렌더링"""
        for level, html in self._html_history:
            if self._passes_filter(level):
                self._viewer.append(html)
        self._scroll_to_bottom()

    def _passes_filter(self, level: str) -> bool:
        return self._active_filter == "ALL" or level.upper() == self._active_filter

    def _apply_filter(self, level: str):
        """필터 버튼 클릭 — 선택 레벨만 재렌더링"""
        self._active_filter = level
        # 버튼 스타일 갱신
        for lv, btn in self._filter_btns.items():
            btn.setChecked(lv == level)
            btn.setStyleSheet(self._filter_btn_style(lv == level))
        # 뷰어 재렌더링
        self._viewer.clear()
        for lv, html in self._html_history:
            if self._passes_filter(lv):
                self._viewer.append(html)
        self._scroll_to_bottom()
        # 필터 변경 후 검색 상태 초기화 (재렌더링으로 커서 위치 무효화)
        self._reset_search_state()

    def _scroll_to_bottom(self):
        sb = self._viewer.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 지우기 ───────────────────────────────────────
    def _clear_log(self):
        """이력 버퍼·뷰어 동시 초기화"""
        self.clear_all()

    # ── 검색 상태 초기화 ─────────────────────────────
    def _reset_search_state(self):
        """
        검색 관련 상태를 모두 초기화합니다.
        - 필터 변경, 지우기, 다이얼로그 닫기 시 호출
        - _search_input 텍스트는 유지 (사용자가 직접 지워야 함)
        """
        self._last_keyword  = ""
        self._total_matches = 0
        self._current_match = 0
        self._search_count_lbl.setText("")
        self._search_count_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)

    # ── 실시간 개수 집계 ─────────────────────────────
    def _update_match_count(self):
        """
        textChanged 수신 — 확정된 텍스트(영문·숫자·조합 완료) 기준으로 검색합니다.
        """
        self._run_search(self._search_input.text().strip())

    def _update_match_count_with(self, full_text: str):
        """
        composing_changed 수신 — IME 조합 중 텍스트 포함 전체 기준으로 검색합니다.
        full_text = 확정 텍스트 + 현재 조합 중인 글자 (SearchLineEdit에서 전달)

        [중복 호출 방지]
        조합 완료 시 preedit이 ""가 되어 full_text == self._search_input.text()와
        동일해지므로 textChanged와 거의 동시에 같은 값으로 _run_search가 호출됩니다.
        _run_search() 내부의 _last_keyword 동일 여부 확인으로 중복 탐색을 차단합니다.
        """
        self._run_search(full_text.strip())

    def _run_search(self, keyword: str):
        """
        실제 집계·이동 로직 — _update_match_count / _update_match_count_with 공유.

        - keyword가 비어 있으면 상태 초기화 후 반환
        - keyword == _last_keyword 이면 이미 처리된 검색어 — 중복 탐색 차단
        - 매치가 있을 경우 커서를 Start로 명시 리셋 후 _do_find(forward=True) 호출
          (_do_find 내 keyword == _last_keyword 이므로 자동 리셋 분기가 발동하지 않아
           커서 리셋을 여기서 직접 처리해야 함)
        """
        if not keyword:
            self._total_matches = 0
            self._current_match = 0
            self._last_keyword  = ""
            self._search_count_lbl.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            return

        # 동일 키워드 재호출 — 중복 탐색 차단
        if keyword == self._last_keyword:
            return

        plain = self._viewer.toPlainText()
        self._total_matches = plain.lower().count(keyword.lower())
        self._last_keyword  = keyword
        self._current_match = 0

        if self._total_matches == 0:
            self._search_count_lbl.setText("0 / 0")
            self._search_count_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
        else:
            self._btn_prev.setEnabled(True)
            self._btn_next.setEnabled(True)
            # 커서를 문서 맨 앞으로 명시 리셋 후 첫 번째 결과로 즉시 이동
            cursor = self._viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._viewer.setTextCursor(cursor)
            self._do_find(forward=True)

    # ── 다음 / 이전 찾기 ─────────────────────────────
    def _search_next(self):
        self._do_find(forward=True)

    def _search_prev(self):
        self._do_find(forward=False)

    def _do_find(self, forward: bool):
        """
        QTextEdit.find()로 키워드를 탐색합니다.

        [keyword 참조]
        self._search_input.text()는 IME 조합 중인 글자를 포함하지 않습니다.
        _run_search()에서 _last_keyword를 조합 포함 전체 텍스트로 갱신하므로
        _do_find()는 self._last_keyword를 사용합니다.

        [wrap-around 처리]
        - find()가 False를 반환(끝에 도달)하면 커서를 반대쪽 끝으로 이동 후 재탐색
        - 재탐색도 실패하면 0 / 0 표기

        [_current_match 관리]
        - forward: +1 증가, total 초과 시 1로 wrap
        - backward: -1 감소, 0 미만 시 total로 wrap
        """
        keyword = self._last_keyword   # _run_search()에서 갱신된 최신 키워드 사용
        if not keyword or self._total_matches == 0:
            return

        flag = (QTextDocument.FindFlag(0) if forward
                else QTextDocument.FindFlag.FindBackward)

        found = self._viewer.find(keyword, flag)

        if not found:
            # wrap-around: 커서를 반대쪽 끝으로 이동 후 재탐색
            cursor = self._viewer.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                self._current_match = 0
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self._current_match = self._total_matches + 1
            self._viewer.setTextCursor(cursor)
            found = self._viewer.find(keyword, flag)

        if found:
            if forward:
                self._current_match = (self._current_match % self._total_matches) + 1
            else:
                self._current_match = (
                    self._total_matches
                    if self._current_match <= 1
                    else self._current_match - 1
                )
            self._search_count_lbl.setText(
                f"{self._current_match} / {self._total_matches}"
            )
            self._search_count_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        else:
            # 재탐색도 실패 — 방어 코드 (정상 경로에서는 미도달)
            self._search_count_lbl.setText("0 / 0")
            self._search_count_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")

    # ── 키보드 이벤트: Enter / Shift+Enter 처리 ──────
    def keyPressEvent(self, event):
        """
        Enter / Shift+Enter 를 검색 탐색에 사용합니다.
        - _search_input에 포커스가 있을 때만 검색 트리거
        - QDialog 기본 동작(Enter → accept())을 억제
        """
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_enter and self._search_input.hasFocus():
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._search_prev()
            else:
                self._search_next()
            return   # 기본 동작 억제
        super().keyPressEvent(event)

    # ── 닫기 이벤트: hide()로 처리 (싱글턴 — 파괴 방지) ─────────────────
    def closeEvent(self, event):
        """× 버튼 또는 닫기 클릭 시 파괴 대신 숨김 처리합니다."""
        self.hide()
        event.ignore()


# ══════════════════════════════════════════════════════
#  GlobalToolbar Mixin
# ══════════════════════════════════════════════════════
class GlobalToolbarTriggers:
    """GlobalToolbar의 버튼·시그널 콜백 메서드"""

    def _copy_url(self):
        """URL을 클립보드에 복사하고 입력창의 텍스트를 전체 선택합니다."""
        QApplication.clipboard().setText(self.url_input.text())
        self.url_input.setFocus()
        self.url_input.selectAll()

    def _toggle_run(self):
        """시작/중지 버튼 클릭 시 호출"""
        if not self._running:
            self._start_cancelled = False

            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)

            store.clear_rows()
            self.dashboard._reset_dashboard()
            self.monitor_page._reset_monitor_page()

            self.set_running(True)
            self._log("info", "수집을 시작합니다.")
            QApplication.processEvents()
            QTimer.singleShot(1000, self._step_to_setting)
        else:
            self._start_cancelled = True
            self.stop_requested.emit()
            self.set_running(False)
            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)
            self._full_reset()
            self._log("warn", "수집이 중단되었습니다. 수집 대기 상태로 초기화합니다.")

    def _step_to_setting(self):
        """[단계 1: 수집 세팅] 처리"""
        if self._start_cancelled:
            return

        mw = self._main_window()

        if self.dashboard is None or self.session_page is None or self.monitor_page is None:
            self._log("err", "페이지 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.")
            if mw is not None:
                mw.dashboard._update_step_ui(0)
            self.set_running(False)
            return

        if mw is not None:
            mw.dashboard._update_step_ui(1)

        QApplication.processEvents()
        self._log("info", "환경 설정을 로드합니다. (수집 세팅 중...)")
        QTimer.singleShot(1000, self._actual_start)

    def _actual_start(self):
        """[단계 2: 데이터 수집] 실제 시작"""
        if self._start_cancelled:
            return

        mw = self._main_window()

        try:
            dashboard_page = self.dashboard
            session_page   = self.session_page
            monitor_page   = self.monitor_page

            if dashboard_page is None or session_page is None or monitor_page is None:
                raise RuntimeError("페이지 인스턴스가 주입되지 않았습니다.")

            request_info = BlueprintStorage().read()

            self.task.update(deepcopy(request_info))

            # 로그인 인증이면 인증 관리 페이지에 입력된 현재 값으로 로그인 정보를 덮어씀
            # (request_info.json 파일에는 저장하지 않고, 이번 실행 task에만 반영)
            auth_conditions = self.task.get("conditions") or {}
            if (auth_conditions.get("authMethod") == "login"
                    and self.auth_page is not None
                    and getattr(self.auth_page, "_auth_method", None) == "login"):
                auth_conditions["login"] = {
                    "loginUrl": self.auth_page._login_url.text().strip() or None,
                    "id": self.auth_page._login_id.text().strip() or None,
                    "password": self.auth_page._login_pw.text() or None,
                    "login_method": (auth_conditions.get("login") or {}).get("login_method"),
                }

            self.task["job"]        = "수동 실행"
            self.task["delay"]      = dashboard_page.delay_spin.value()
            self.task["threads"]    = dashboard_page.thread_spin.value()
            self.task["timeout"]    = dashboard_page.timeout_spin.value()
            self.task["retry"]      = dashboard_page.retry_spin.value()
            self.task["user_agent"] = session_page.ua_check.isChecked()
            self.task["cookie"]     = session_page.cookie_check.isChecked()
            self.task["proxy"] = {
                "enabled":       session_page._global_cb.isChecked(),
                "rotate":        session_page._rotate_cb.isChecked(),
                "allow_ip_cnts": session_page._allow_ip_cnts.value(),
                "ip_list":       deepcopy(getattr(session_page, "_proxy_rows", [])),
            }
            self.task["extract"] = monitor_page.output_info["extract"]
            self.task["extract"]["auto_save"] = dashboard_page.auto_save_chk.isChecked()
            self.task["extract"]["auto_save_source"] = (
                "refined" if dashboard_page.auto_src_ref_btn.isChecked() else "raw"
            )
            self.start_requested.emit(self.task)

        except Exception as e:
            self._log("err", f"설정 로드 실패: {e}")
            self.set_running(False)
            if mw is not None:
                mw.dashboard._update_step_ui(0)

    def _full_reset(self):
        """중지 버튼 클릭 시 호출 — DataStore 및 모든 페이지 UI를 완전히 초기화합니다."""

        store.clear_rows()
        store.clear_url_maps()

        if self.dashboard is not None:
            self.dashboard._reset_dashboard()
        if self.monitor_page is not None:
            self.monitor_page._reset_monitor_page()

        mw = self._main_window()
        if mw is not None:
            mw.reset_progress()

    def set_running(self, v: bool):
        self._running = v
        self._style_run_btn(v)

    def _style_run_btn(self, running: bool):
        if running:
            self.run_btn.setText("⬛  중지")
            self.run_btn.setStyleSheet(f"""
                QPushButton{{background:#7f1d1d;color:{RED};border:none;border-radius:6px;
                padding:6px 14px;font-size:13px;font-weight:bold;}}
                QPushButton:hover{{background:#991b1b;}}""")
        else:
            self.run_btn.setText("▶  시작")
            self.run_btn.setStyleSheet(f"""
                QPushButton{{background:{ACCENT};color:white;border:none;border-radius:6px;
                padding:6px 14px;font-size:13px;font-weight:bold;}}
                QPushButton:hover{{background:{ACCENT_HOVER};}}""")

    def _log(self, level: str, message: str) -> None:
        """log_manager가 주입된 경우에만 로그를 출력합니다."""
        if self.log_manager is not None:
            self.log_manager.append_log(level, message)

    def _main_window(self):
        """부모 위젯을 순회하여 MainWindow 인스턴스를 반환합니다. 없으면 None."""

        w = self.parent()
        while w is not None:
            if isinstance(w, QMainWindow):
                return w
            w = w.parent()
        return None

    def get_url(self) -> str:
        return self.url_input.text().strip()

    def set_pages(self, dashboard=None, monitor_page=None,
                  session_page=None, auth_page=None) -> None:
        """MainWindow 초기화 후 실제 페이지 인스턴스를 주입합니다."""
        if dashboard    is not None:
            self.dashboard    = dashboard
        if monitor_page is not None:
            self.monitor_page = monitor_page
        if session_page is not None:
            self.session_page = session_page
        if auth_page    is not None:
            self.auth_page    = auth_page

    def set_log_manager(self, log_manager) -> None:
        """MainWindow 초기화 후 LogViewerDialog 싱글턴을 주입합니다."""
        self.log_manager = log_manager


# ══════════════════════════════════════════════════════
#  DashboardPage Mixin
# ══════════════════════════════════════════════════════
class DashboardPageTriggers:
    """DashboardPage의 테이블·필터·내보내기 메서드"""

    def _on_auto_save_toggled(self, checked: bool):
        """자동 저장 체크박스 — 꺼져 있으면 저장 대상(RAW/정제) 토글은 의미가 없어 비활성화"""
        self.auto_src_raw_btn.setEnabled(checked)
        self.auto_src_ref_btn.setEnabled(checked)

    def _on_auto_save_source_selected(self, is_refined: bool):
        """자동 저장 대상(RAW/정제) 토글 — 상호 배타 선택"""
        self.auto_src_raw_btn.setChecked(not is_refined)
        self.auto_src_ref_btn.setChecked(is_refined)

    def add_row(self, row: dict):
        """워커 new_row 시그널 수신 → 대시보드 수집 모니터링 테이블에 행 추가"""
        if not row or "resp_info" not in row:
            return
        resp_info = row["resp_info"]
        data = resp_info.get("data")
        if not data or isinstance(data, dict):
            return

        target_url = resp_info.get("url", "")
        self.monitor_table.setSortingEnabled(False)
        current_row = self.monitor_table.rowCount()
        self.monitor_table.insertRow(current_row)

        STATUS_COLOR = {"200": GREEN, "404": RED, "429": AMBER, "500": RED, "301": BLUE}
        vals = [
            current_row,
            target_url,
            resp_info.get("status", ""),
            resp_info.get("ip_address", ""),
            resp_info.get("user_agents", ""),
            resp_info.get("cookies", ""),
            resp_info.get("pure_latency", ""),
            resp_info.get("total_latency", ""),
            row.get("job_name", ""),
        ]
        colors = [
            TEXT_MUTED, TEXT_MUTED,
            STATUS_COLOR.get(str(resp_info.get("status", "")), TEXT_SECONDARY),
            TEXT_PRIMARY, TEXT_PRIMARY, TEXT_PRIMARY,
            TEXT_PRIMARY, ACCENT_LIGHT, TEXT_MUTED,
        ]
        for col, (val, color) in enumerate(zip(vals, colors)):
            item = QTableWidgetItem()
            if isinstance(val, (int, float)):
                item.setData(Qt.ItemDataRole.DisplayRole, val)
            else:
                item.setText(str(val))
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.monitor_table.setItem(current_row, col, item)

        self.monitor_table.setSortingEnabled(True)
        self.mon_row_count_lbl.setText(f"{self.monitor_table.rowCount()} rows")
        self._refresh_session_stats()

    def _refresh_session_stats(self):
        """수집 모니터링 테이블 집계 → 세션 통계 카드 갱신"""
        ERROR_STATUSES = {"404", "500", "503", "502", "429"}
        total_rows = self.monitor_table.rowCount()
        errors = 0
        latencies = []
        for r in range(total_rows):
            status_item = self.monitor_table.item(r, 2)
            if status_item and status_item.text().strip() in ERROR_STATUSES:
                errors += 1
            lat_item = self.monitor_table.item(r, 6)
            if lat_item:
                try:
                    latencies.append(float(lat_item.text()))
                except (ValueError, TypeError):
                    pass
        completed = total_rows - errors
        avg_latency = f"{sum(latencies) / len(latencies):.2f}s" if latencies else "—"
        self.s_total.update_value(completed)
        self.s_err.update_value(errors)
        self.s_pages.update_value(total_rows)
        self.s_speed.update_value(avg_latency)

    def _export_monitor_csv(self):
        """수집 모니터링 테이블을 CSV로 내보내기"""
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "crawl_monitor.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["NO", "URL", "STATUS", "IP_ADDRESS", "USER-AGENT",
                        "COOKIES", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
            for r in range(self.monitor_table.rowCount()):
                w.writerow([
                    self.monitor_table.item(r, c).text()
                    if self.monitor_table.item(r, c) else ""
                    for c in range(9)
                ])
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")

    def update_stats(self, stats):
        """세션 통계 시그널 수신 — 테이블 기반 집계로 처리하므로 pass."""
        pass


# ══════════════════════════════════════════════════════
#  MonitorPage Mixin
# ══════════════════════════════════════════════════════
class MonitorPageTriggers:
    """MonitorPage의 필터·상세·추출·다이얼로그 메서드"""

    def _add_realtime_row(self, row: dict):
        self._all_rows.append(row)
        resp = row.get("resp_info", {})
        data = resp.get("data", [])
        if not isinstance(data, list) or not data:
            return
        columns = self._get_result_columns()
        self.result_table.setSortingEnabled(False)

        # 중복 감지를 위해 기존 수집 데이터 문자열 집합 유지
        existing_keys = {
            str(tuple(str(e.get(c, "")) for c in columns))
            for e in self._collected_data
        }

        for entry in data:
            if not isinstance(entry, dict):
                continue
            entry_key = str(tuple(str(entry.get(c, "")) for c in columns))
            is_dup = entry_key in existing_keys
            is_empty_row = all(
                entry.get(c) in (None, "", "null", "None")
                for c in columns
            )
            self._collected_data.append(entry)
            existing_keys.add(entry_key)

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
                item = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, val)
                else:
                    item.setText(str(val) if val is not None else "—")
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
        "② 정제 규칙 설정" 탭(index=1) 진입 시, 이번 수집이 needs_cleaning=True인데
        등록된 커스텀 규칙 파일이 없으면 팝업으로 안내합니다. 이번 수집 결과당 최초
        1회만 확인하고(같은 결과를 보며 탭을 왔다갔다 해도 반복해서 뜨지 않음),
        preprocess(task)에서 새 수집 결과가 들어올 때 다시 확인 가능하도록 리셋됩니다.
        """
        if index != 1 or self._cleaning_warned:
            return

        seq_no         = self._current_task.get("seq_no")
        needs_cleaning = self._current_task.get("needs_cleaning", False)
        if not (needs_cleaning and seq_no):
            return

        self._cleaning_warned = True
        if not custom_rule_exists(seq_no):
            QMessageBox.warning(
                self, "정제 규칙 없음",
                f"이 수집물(seq_no={seq_no})은 사용자 정의 정제 규칙이 필요하도록 "
                f"표시되어 있으나(needs_cleaning=True), 등록된 규칙 파일이 없습니다.\n"
                f"범용 규칙만 적용됩니다."
            )

    # ── 커스텀 정제 규칙 체크박스 연동 ───────────────────────────────
    def _on_custom_rule_toggled(self, state):
        """"커스텀 정제 규칙 적용"(②) 체크 시 규칙 ①③④(remove_null_row/
        trim_whitespace/remove_duplicate)를 자동으로 켭니다. fill_null(⑥, 결측값
        치환)은 대상에서 제외됩니다(2026-07-17, 사용자 요청 — 커스텀 규칙이
        정규화한 데이터라도 결측값 치환 여부는 별도로 판단해야 한다는 판단).
        체크할 때마다 사용자가 개별적으로 조정해둔 상태를 덮어쓰며, 해제 시에는
        ①③④에 영향을 주지 않습니다(직전 상태 그대로 유지).
        """
        if state != Qt.CheckState.Checked.value:
            return
        for key in ("remove_null_row", "remove_duplicate", "trim_whitespace"):
            cb = self._rule_checkboxes.get(key)
            if cb is not None:
                cb.setChecked(True)

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

    # ── "제외 필드 지정"(⑤) 요약 라벨 갱신 ───────────────────────────
    def _update_drop_columns_summary(self):
        n = len(self._drop_column_names)
        self.drop_columns_summary_lbl.setText(f"{n}개 필드 제외 중" if n else "제외 필드 없음")

    # ── Raw 수집 결과 존재 여부 확인 (없으면 경고) ───────────────────
    def _has_collected_data_or_warn(self) -> bool:
        """self._collected_data가 있으면 True, 없으면 경고를 띄우고 False를 반환합니다.

        "제외 필드 지정" 체크박스 활성화 시(layout.py)와 "⚙ 필드 선택" 버튼
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
        dlg.setStyleSheet(f"""
            QDialog {{
                background:{BG_SECONDARY};
                border:1px solid {BORDER};
                border-radius:10px;
            }}
        """)

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
            dlg.accept()

        apply_btn = parts.action_btn("적용")
        apply_btn.clicked.connect(_apply)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
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
                item = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, val)
                else:
                    item.setText(str(val) if val is not None else "—")
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
            if is_deleted:
                # no_item.setBackground(CLR_DEL_BG)
                pass
            self.cmp_raw_table.setItem(row_idx, 0, no_item)

            for col_idx, col_name in enumerate(columns, start=1):
                val  = entry.get(col_name, "—")
                item = QTableWidgetItem()
                item.setText(str(val) if val is not None else "—")
                if is_deleted:
                    item.setForeground(CLR_DEL_FG)
                    # item.setBackground(CLR_DEL_BG)
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
            if is_modified:
                # no_item.setBackground(CLR_REF_BG)
                pass
            self.cmp_ref_table.setItem(row_idx, 0, no_item)

            for col_idx, col_name in enumerate(ref_columns, start=1):
                val  = entry.get(col_name, "—")
                item = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, val)
                else:
                    item.setText(str(val) if val is not None else "—")
                if is_modified:
                    item.setForeground(CLR_REF_FG)
                    # item.setBackground(CLR_REF_BG)
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
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

    def _show_refined_detail(self, item):
        """정제 결과 탭 행 클릭 — 상세 표시"""
        row = item.row()
        columns = self._get_result_columns()
        if self._refine_rules.get("drop_columns") and self._drop_column_names:
            columns = [c for c in columns if c not in self._drop_column_names]
        detail_parts = []
        for col_idx, col_name in enumerate(columns):
            cell = self.refined_table.item(row, col_idx + 1)
            val = cell.text() if cell else "—"
            detail_parts.append(
                f"<b style='color:{ACCENT_LIGHT};'>{col_name}:</b> "
                f"<span style='color:{VALUE_COLORS.get(col_idx, TEXT_MUTED)};'>{val}</span>"
            )
        self.refined_detail_lbl.setText("<br>".join(detail_parts))
        self.refined_detail_lbl.setTextFormat(Qt.TextFormat.RichText)

    def _on_current_item_changed(self, current, previous):
        if current is not None:
            self._show_detail(current)

    def _on_refined_current_item_changed(self, current, previous):
        """정제 결과 탭 — 키보드 방향키·클릭으로 currentItemChanged 수신 시 상세 표시"""
        if current is not None:
            self._show_refined_detail(current)

    def _show_detail(self, item):
        row = item.row()
        columns = self._get_result_columns()
        detail_parts = []
        for col_idx, col_name in enumerate(columns):
            cell = self.result_table.item(row, col_idx + 1)
            val = cell.text() if cell else "—"
            detail_parts.append(
                f"<b style='color:{ACCENT_LIGHT};'>{col_name}:</b> "
                f"<span style='color:{VALUE_COLORS.get(col_idx, TEXT_MUTED)};'>{val}</span>"
            )
        self.detail_lbl.setText("<br>".join(detail_parts))
        self.detail_lbl.setTextFormat(Qt.TextFormat.RichText)

    def _open_output_settings_dialog(self):
        """출력 대상 / 상세 설정(인라인) / AUTO SAVE Dialog"""
        dlg = QDialog(self)
        dlg.setWindowTitle("추출 설정")
        dlg.setFixedWidth(500)
        dlg.setStyleSheet(f"""
            QDialog {{
                background:{BG_SECONDARY};
                border:1px solid {BORDER};
                border-radius:10px;
            }}
        """)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(22, 18, 22, 18)
        vl.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.addWidget(parts.make_label("추출 설정", TEXT_PRIMARY, 14, True))
        title_row.addStretch()
        vl.addLayout(title_row)
        vl.addSpacing(10)
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
        file_page = QWidget()
        fp = QVBoxLayout(file_page)
        fp.setContentsMargins(14, 14, 14, 14)
        fp.setSpacing(10)

        path_lay = QHBoxLayout()
        path_lay.setSpacing(8)
        path_lay.addWidget(parts.make_label("경로", TEXT_SECONDARY, 12))
        path_edit = QLineEdit(self.output_info["extract"]["file"]["file_path"])
        path_edit.setReadOnly(True)
        path_lay.addWidget(path_edit, 1)
        browse_btn = parts.outline_btn("Browse")
        browse_btn.setFixedWidth(72)

        def _browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", path_edit.text() or "")
            if folder:
                path_edit.setText(folder)

        browse_btn.clicked.connect(_browse)
        path_lay.addWidget(browse_btn)
        fp.addLayout(path_lay)

        file_nm_lay = QHBoxLayout()
        file_nm_lay.setSpacing(10)
        file_nm_lay.addWidget(parts.make_label("파일명", TEXT_SECONDARY, 12))
        file_nm = QLineEdit()
        file_nm.setText(self.output_info["extract"]["file"]["file_name"])
        file_nm_lay.addWidget(file_nm)
        fp.addLayout(file_nm_lay)

        opt_lay = QHBoxLayout()
        opt_lay.setSpacing(10)
        opt_lay.addWidget(parts.make_label("형식", TEXT_SECONDARY, 12))
        fmt_combo = QComboBox()
        fmt_combo.addItems(["CSV", "JSON", "Excel"])
        fmt_combo.setCurrentText(self.output_info["extract"]["file"]["file_format"])
        opt_lay.addWidget(fmt_combo)
        opt_lay.addSpacing(10)

        enc_widget = QWidget()
        enc_lay = QHBoxLayout(enc_widget)
        enc_lay.setContentsMargins(0, 0, 0, 0)
        enc_lay.setSpacing(10)
        enc_combo = QComboBox()
        enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
        enc_combo.setCurrentText(self.output_info["extract"]["file"]["file_encoding"])
        enc_lay.addWidget(parts.make_label("인코딩", TEXT_SECONDARY, 12))
        enc_lay.addWidget(enc_combo)
        opt_lay.addWidget(enc_widget)
        opt_lay.addSpacing(10)

        delim_widget = QWidget()
        delim_lay = QHBoxLayout(delim_widget)
        delim_lay.setContentsMargins(0, 0, 0, 0)
        delim_lay.setSpacing(10)
        csv_delimeter = QLineEdit()
        csv_delimeter.setText(self.output_info["extract"]["file"]["file_delimiter"])
        delim_lay.addWidget(parts.make_label("구분자", TEXT_SECONDARY, 12))
        delim_lay.addWidget(csv_delimeter)
        opt_lay.addWidget(delim_widget)
        opt_lay.addStretch()
        fp.addLayout(opt_lay)

        open_path_chk = QCheckBox("저장 완료 후 폴더 열기")
        open_path_chk.setChecked(self.output_info["extract"]["file"]["is_open_save_path"])
        fp.addWidget(open_path_chk)
        stack.addWidget(file_page)  # index 0

        # ── PAGE 1: DB 설정 ───────────────────────────────
        db_page = QWidget()
        dp = QVBoxLayout(db_page)
        dp.setContentsMargins(14, 14, 14, 14)
        dp.setSpacing(8)

        def _lbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 11)

        def _inp(txt="", ph=""):
            e = QLineEdit(txt)
            e.setPlaceholderText(ph)
            return e

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        _db_type   = QComboBox()
        _db_type.addItems(["MySQL", "PostgreSQL", "MongoDB"])
        _db_type.setCurrentText(self.output_info["extract"]["db"]["db_env"])
        _db_host   = _inp(txt=self.output_info["extract"]["db"]["host"])
        _db_port   = _inp(txt=self.output_info["extract"]["db"]["port"])
        _db_name   = _inp(self.output_info["extract"]["db"]["database"])
        _db_schema = _inp(self.output_info["extract"]["db"]["schema"])
        _db_user   = _inp(self.output_info["extract"]["db"]["user"])
        _db_pw     = _inp(self.output_info["extract"]["db"]["password"])
        _db_pw.setEchoMode(QLineEdit.EchoMode.Password)
        _db_data   = _inp(self.output_info["extract"]["db"]["save_data_nm"])

        for row_i, (label, widget) in enumerate([
            ("DB Type", _db_type), ("HOST", _db_host), ("PORT", _db_port),
            ("DB Name", _db_name), ("SCHEMA", _db_schema),
            ("USER", _db_user), ("PASSWORD", _db_pw), ("DATA Name", _db_data),
        ]):
            grid.addWidget(_lbl(label), row_i, 0)
            grid.addWidget(widget, row_i, 1)

        _db_type.currentTextChanged.connect(lambda t: _db_port.setText(DB_PORTS.get(t, "")))
        dp.addLayout(grid)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        test_btn = parts.outline_btn("TEST CONNECTION")
        test_result_lbl = parts.make_label("", TEXT_MUTED, 11)

        def _show_conn_fail_dialog(reason: str):
            msg = QMessageBox(dlg)
            msg.setWindowTitle("연결 실패")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("<b>DB 연결에 실패했습니다.</b>")
            msg.setInformativeText(reason)
            msg.setStyleSheet(f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:12px; }}
                QPushButton {{ background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px; }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """)
            msg.exec()

        def _test_conn():
            host = _db_host.text().strip() or "localhost"
            try:
                port = int(_db_port.text().strip())
            except ValueError:
                test_result_lbl.setText("⚠ 포트 번호가 올바르지 않습니다")
                test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                _show_conn_fail_dialog("포트 번호에 숫자가 아닌 값이 입력되어 있습니다.")
                return
            test_result_lbl.setText("⏳ 연결 중...")
            test_result_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            test_btn.setEnabled(False)
            QApplication.processEvents()
            info = {
                "db_env": _db_type.currentText(), "host": host, "port": str(port),
                "database": _db_name.text().strip(), "schema": _db_schema.text().strip(),
                "user": _db_user.text().strip(), "password": _db_pw.text(),
                "save_data_nm": _db_data.text().strip() or "results",
            }
            try:
                ok, reason = db_conn._check_db_connect_info(info)
                if ok:
                    test_result_lbl.setText(f"✅ {host}:{port} 연결 성공")
                    test_result_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
                else:
                    test_result_lbl.setText("❌ 연결 실패")
                    test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_conn_fail_dialog(reason)
            except ImportError:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        test_result_lbl.setText(f"✅ {host}:{port} 소켓 연결 성공 (DB 드라이버 미설치)")
                        test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                except OSError as e:
                    test_result_lbl.setText("❌ 연결 실패")
                    test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_conn_fail_dialog(f"소켓 연결 실패: {e}")
            except Exception as e:
                test_result_lbl.setText("❌ 연결 실패")
                test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                _show_conn_fail_dialog(str(e))
            finally:
                test_btn.setEnabled(True)

        test_btn.clicked.connect(_test_conn)
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
            is_csv = (fmt_text == "CSV")
            enc_widget.setVisible(is_csv)
            delim_widget.setVisible(is_csv)
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
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "설정 저장 오류", f"추출 설정 저장 중 오류가 발생했습니다.\n\n{e}")

        apply_btn  = parts.action_btn("적용")
        apply_btn.clicked.connect(_apply_file)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        vl.addLayout(btn_row)

        update_dialog_size()
        dlg.adjustSize()
        dlg.exec()

    def _extract_result_table(self, source: str, silent: bool = False):
        """
        source: "raw"(_collected_data) 또는 "refined"(_refined_data) — 추출 대상을
        호출부에서 명시적으로 지정합니다. "refined"인데 아직 정제를 실행하지
        않았다면 먼저 _run_refine()을 실행한 뒤 그 결과를 추출합니다.
        silent: True면 데이터가 없을 때 모달 대신 로그만 남기고 조용히 스킵합니다
            (스케줄 자동 저장 등 무인 실행 경로 전용, 이슈 ⑱). 이 경우 "refined"여도
            _run_refine() 폴백을 호출하지 않습니다 — 호출부가 이미 알맞은 고정
            규칙으로 _run_refine()을 실행한 뒤이므로, 여기서 화면 상태 기반으로
            다시 실행하면 무인 실행 취지에 어긋납니다.
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

        try:
            if self.output_info["extract"]["file"]["enabled"] is True:
                file_path   = self.output_info["extract"]["file"]["file_path"]
                file_name   = self.output_info["extract"]["file"]["file_name"]
                file_format = self.output_info["extract"]["file"]["file_format"]

                if file_format == "CSV":
                    delimiter = self.output_info["extract"]["file"]["file_delimiter"]
                    final_file_name = file_name
                    if os.path.exists(os.path.join(file_path, f"{file_name}.{file_format}")):
                        count = 1
                        while True:
                            new_file_name = f"{file_name} ({count})"
                            if not os.path.exists(os.path.join(file_path, f"{new_file_name}.{file_format}")):
                                break
                            count += 1
                        final_file_name = new_file_name
                    with open(os.path.join(file_path, f"{final_file_name}.csv"),
                              mode='w', encoding='utf-8-sig', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
                        writer.writeheader()
                        writer.writerows(data)

                elif file_format == "JSON":
                    if os.path.exists(os.path.join(file_path, f"{file_name}.{file_format}")):
                        reply = QMessageBox.question(
                            self, '덮어쓰기 확인',
                            f"'{file_name}.{file_format}' 파일이 이미 존재합니다.\n덮어쓰시겠습니까?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.No:
                            return
                    with open(os.path.join(file_path, f"{file_name}.json"), 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                is_open_save_path = self.output_info["extract"]["file"]["is_open_save_path"]
                if file_path and is_open_save_path:
                    if sys.platform == 'win32':
                        os.startfile(file_path)
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', file_path])
                    else:
                        subprocess.Popen(['xdg-open', file_path])

            elif self.output_info["extract"]["db"]["enabled"] is True:
                db_info = self.output_info["extract"]["db"]
                try:
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
                except Exception as e:
                    QMessageBox.critical(
                        self, "DB 저장 실패",
                        f"DB 접속 및 로그인 정보가 올바르지 않습니다.\n\n[시스템 에러 내용]\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "추출 오류", str(e))


# ══════════════════════════════════════════════════════
#  StatisticsPage Mixin
# ══════════════════════════════════════════════════════
class StatisticsPageTriggers:
    """StatisticsPage의 데이터 로드·내보내기 메서드"""

    def _export_json(self):
        rows     = store.get_rows()
        sessions = store.get_sessions()
        if not rows and not sessions:
            QMessageBox.warning(self, "경고", "저장할 데이터가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "리포트 저장", "report.json", "JSON (*.json)")
        if not path:
            return
        report = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sessions": sessions,
            "rows": [{k: str(v) for k, v in r.items()} for r in rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")

    # ── data ───────────────────────────────────
    def reload(self):
        rows = store.get_url_maps()
        sessions = store.get_sessions()
        if not rows and not sessions:
            return

        total = len(rows)  # URL_LIST
        ok = sum(1 for r in rows if str(r["status_code"]) == "200")  # URL_LIST 중 RESPONSE = 200인 것
        rate = f"{ok / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]  # URL_LIST의 각각 URL의 순수 레이턴시
        avg_t = f"{sum(times) / len(times):.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        # Donut ( 통계 분석 - 상태 코드 분포 )
        status_cnt = defaultdict(int)
        for r in rows:
            status_cnt[str(r["status_code"])] += 1
        # ── 수정: COLOR_MAP 키를 str 로 통일하여 단일 응답 시 Gray 오류 해소 ──
        COLOR_MAP = {"200": GREEN, "301": BLUE, "404": AMBER, "429": PURPLE, "500": RED}
        segments = [(k, v, COLOR_MAP.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.donut.set_data(segments)
        # rebuild legend
        for i in reversed(range(self.legend_lay.count())):
            w = self.legend_lay.itemAt(i).widget()
            if w:
                w.deleteLater()
        for k, v, color in segments:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:12px;")
            txt = parts.make_label(f"{k}  {v}", TEXT_SECONDARY, 11)
            rl.addWidget(dot)
            rl.addWidget(txt)
            rl.addStretch()
            self.legend_lay.addWidget(row_w)
        self.legend_lay.addStretch()

        # Response bar (bucket 0.2 intervals) ( 통계 분석 - 응답 시간 분포  )
        if times:
            buckets = defaultdict(int)
            for t in times:
                b = round(round(t / 0.2) * 0.2, 1)
                buckets[b] += 1
            sorted_b = sorted(buckets.items())
            labels = [str(k) for k, _ in sorted_b]
            values = [v for _, v in sorted_b]
            self.resp_bar.set_data(labels, values, BLUE)

        # Hourly trend (last 12 hours) ( 통계분석 - 시간대별 수집량 추이 )
        hour_ok = defaultdict(int)
        hour_err = defaultdict(int)
        now = datetime.now()
        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_h = int((now - ts).total_seconds() // 3600)
                if 0 <= diff_h < 12:
                    bucket = now.hour - diff_h
                    if str(r["status_code"]) == "200":
                        hour_ok[bucket] += 1
                    else:
                        hour_err[bucket] += 1
            except (ValueError, KeyError, TypeError):
                pass
        hours = [(now - timedelta(hours=11 - i)).hour for i in range(12)]
        ok_vals = [hour_ok.get(h, 0) for h in hours]
        err_vals = [hour_err.get(h, 0) for h in hours]
        self.trend_line.set_data(
            [f"{h:02d}h" for h in hours],
            [("성공", ok_vals, GREEN), ("오류", err_vals, RED)]
        )

        # Session table ( 통계 분석 - 세션 이력 )
        self.session_table.setSortingEnabled(False)
        self.session_table.setRowCount(0)
        for s in reversed(sessions):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            vals = [s["job"], s["url"], str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"]]
            colors = [TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.session_table.setItem(r, col, item)
        self.session_table.setSortingEnabled(True)


# ══════════════════════════════════════════════════════
#  SchedulerPage Mixin
# ══════════════════════════════════════════════════════
class SchedulerPageTriggers:
    """SchedulerPage의 스케줄 등록·수정·삭제·실행·타이머 메서드"""

    # QTimer.start()는 C int(최대 2,147,483,647ms ≈ 24.8일)를 받으므로,
    # 이보다 긴 대기는 이 단위로 쪼개어 재등록한다 (월간 주기=30일 등에서 OverflowError 방지).
    _MAX_TIMER_MS = 7 * 24 * 60 * 60 * 1000

    def _apply_schedule(self, dlg, sched_info_dict):
        """다이얼로그 위젯값을 읽어 유효성 검사 → 등록 또는 수정 수행"""
        sched_task  = sched_info_dict["sched_task"]
        idx         = sched_info_dict.get("idx")
        name_val    = sched_info_dict["sched_name"].text().strip()
        url_val     = sched_info_dict["callback_url"].text().strip()
        iv_idx      = sched_info_dict["interval"].currentIndex()
        svtype_idx  = sched_info_dict["save_type"].currentIndex()
        out_mode    = self._sched_out_mode

        _msg_qss = f"""
            QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
            QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
            QPushButton {{
                background:{ACCENT}; color:white; border:none;
                border-radius:5px; padding:5px 14px; font-size:12px;
            }}
            QPushButton:hover {{ background:{ACCENT_HOVER}; }}
        """

        def _warn(title, text):
            msg = QMessageBox(dlg)
            msg.setWindowTitle(title)
            msg.setText(text)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(_msg_qss)
            msg.exec()

        errors = []
        if not name_val:
            errors.append("• Task Name을 입력해 주세요.")
        if not url_val:
            errors.append("• Target URL을 입력해 주세요.")
        if iv_idx == 0:
            errors.append("• Interval(주기)을 선택해 주세요.")
        if svtype_idx == 0:
            errors.append("• 저장 방식을 선택해 주세요.")

        if self.session_page._global_cb.isChecked():

            if not getattr(self.session_page, "_proxy_rows", []):
                errors.append(
                    "• 프록시 사용이 선택되었으나 프록시 목록이 비어 있습니다.\n"
                    "  [세션 설정] 페이지에서 프록시를 먼저 등록해 주세요."
                )

        if errors:
            _warn("입력 오류", "다음 항목을 확인해 주세요:\n\n" + "\n".join(errors))
            return

        for i2, exist in enumerate(store.get_schedules()):
            if sched_task == "수정" and i2 == idx:
                continue
            if exist.get("task_nm") == name_val:
                _warn("입력 오류",
                      f"• 동일한 작업명이 이미 등록되어 있습니다.\n"
                      f"  (작업명: '{name_val}')\n  다른 작업명을 사용해 주세요.")
                return

        def _hms(h_cb, m_cb, s_cb):
            return (int(h_cb.currentText()),
                    int(m_cb.currentText()),
                    int(s_cb.currentText()))

        candidate = None
        if iv_idx == 1:
            h, m, s = _hms(sched_info_dict["d_h"], sched_info_dict["d_m"], sched_info_dict["d_s"])
        elif iv_idx == 2:
            h, m, s = _hms(sched_info_dict["w_h"], sched_info_dict["w_m"], sched_info_dict["w_s"])
        elif iv_idx == 3:
            h, m, s = _hms(sched_info_dict["m_h"], sched_info_dict["m_m"], sched_info_dict["m_s"])
        elif iv_idx == 4:
            h, m, s = _hms(sched_info_dict["dat_h"], sched_info_dict["dat_m"], sched_info_dict["dat_s"])
        else:
            h, m, s = None, None, None

        if h is not None:
            candidate = f"{h:02d}:{m:02d}:{s:02d}"

        if candidate:
            for i2, exist in enumerate(store.get_schedules()):
                if sched_task == "수정" and i2 == idx:
                    continue
                exist_exec_str = exist.get("schedule", {}).get("exec_str", "")
                exist_time = exist_exec_str.strip().split()[-1] if exist_exec_str else ""
                if exist.get("callback_url", "") == url_val and exist_time == candidate:
                    _warn("입력 오류",
                          f"• 동일한 URL과 실행 시간의 작업이 이미 등록되어 있습니다.\n"
                          f"  (작업명: '{exist.get('task_nm', '')}' / {candidate})\n"
                          f"  URL 또는 실행 시간을 변경해 주세요.")
                    return

        now    = datetime.now()
        iv_key = "none"
        exec_str = "미설정"
        run_at   = now + timedelta(hours=1)

        if iv_idx == 1:
            h, m, s  = _hms(sched_info_dict["d_h"], sched_info_dict["d_m"], sched_info_dict["d_s"])
            exec_str = f"매일 {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "daily"
            run_at   = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=1)
        elif iv_idx == 2:
            day      = sched_info_dict["w_day"].currentText()
            h, m, s  = _hms(sched_info_dict["w_h"], sched_info_dict["w_m"], sched_info_dict["w_s"])
            exec_str = f"매주 {day} {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "weekly"
            run_at   = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=7)
        elif iv_idx == 3:
            day      = int(sched_info_dict["m_day"].currentText())
            h, m, s  = _hms(sched_info_dict["m_h"], sched_info_dict["m_m"], sched_info_dict["m_s"])
            exec_str = f"매월 {day}일 {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "monthly"
            try:
                run_at = now.replace(day=day, hour=h, minute=m, second=s, microsecond=0)
            except ValueError:
                run_at = now.replace(day=28, hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=30)
        elif iv_idx == 4:
            qd       = sched_info_dict["date_edit"].date()
            h, m, s  = _hms(sched_info_dict["dat_h"], sched_info_dict["dat_m"], sched_info_dict["dat_s"])
            exec_str = f"{qd.toString('yyyy-MM-dd')} {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "date"
            run_at   = datetime(qd.year(), qd.month(), qd.day(), h, m, s)
            if run_at <= now:
                _warn("등록 불가",
                      f"선택한 시간이 현재 시각보다 이전입니다.\n\n"
                      f"  설정 시간: {exec_str}\n"
                      f"  현재 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                      "현재 시각 이후의 시간을 설정해 주세요.")
                return

        is_file = (out_mode == "FILE")
        is_db   = (out_mode == "DB")

        def _val(widget, method="text"):
            raw = getattr(widget, method)() if widget else ""
            return utility.update_empty_value(raw) if raw else None

        common_fields = {
            "task_nm":      name_val,
            "callback_url": url_val,
            "delay":        sched_info_dict["delay"].value(),
            "threads":      sched_info_dict["threads"].value(),
            "timeout":      sched_info_dict["timeout"].value(),
            "retry":        sched_info_dict["retry"].value(),
            "user_agent":   self.session_page.ua_check.isChecked(),
            "cookie":       self.session_page.cookie_check.isChecked(),
            "proxy": {
                "enabled":       self.session_page._global_cb.isChecked(),
                "rotate":        self.session_page._rotate_cb.isChecked(),
                "allow_ip_cnts": self.session_page._allow_ip_cnts.value(),
                "ip_list":       deepcopy(getattr(self.session_page, "_proxy_rows", [])),
            },
            "extract": {
                "file": {
                    "enabled":      is_file,
                    "file_path":    (utility.to_forward_slash(
                                        os.path.normpath(sched_info_dict["path_edit"].text()))
                                     if is_file and sched_info_dict["path_edit"].text() else None),
                    "file_name":    _val(sched_info_dict["file_nm"]) if is_file else None,
                    "file_format":  _val(sched_info_dict["fmt_combo"], "currentText") if is_file else None,
                    "file_encoding":_val(sched_info_dict["enc_combo"], "currentText") if is_file else None,
                    "file_delimiter":_val(sched_info_dict["csv_delim"]) if is_file else None,
                },
                "db": {
                    "enabled":      is_db,
                    "db_env":       _val(sched_info_dict["db_type"], "currentText") if is_db else None,
                    "host":         _val(sched_info_dict["db_host"]) if is_db else None,
                    "port":         _val(sched_info_dict["db_port"]) if is_db else None,
                    "database":     _val(sched_info_dict["db_name"]) if is_db else None,
                    "schema":       _val(sched_info_dict["db_schema"]) if is_db else None,
                    "user":         _val(sched_info_dict["db_user"]) if is_db else None,
                    "password":     _val(sched_info_dict["db_pw"]) if is_db else None,
                    "save_data_nm": _val(sched_info_dict["db_data"]) if is_db else None,
                },
            },
            "schedule": {
                "enabled":            True,
                "status":             "대기",
                "interval":           iv_key,
                "exec_str":           exec_str,
                "run_at":             run_at,
                "schedule_save_type": sched_info_dict["save_type"].currentText().strip(),
            },
        }

        auto_save_source  = "refined" if sched_info_dict["auto_src_ref_btn"].isChecked() else "raw"
        refine_checkboxes = sched_info_dict["refine_checkboxes"]
        refine_fill_input = sched_info_dict["refine_fill_input"]
        refine_rules_values = {key: cb.isChecked() for key, cb in refine_checkboxes.items()}
        refine_fill_value   = refine_fill_input.text() if refine_fill_input is not None else ""

        if sched_task == "등록":
            schedule_info = customized_settings.get_schedule_settings()
            schedule_info.update(common_fields)
            schedule_info["extract"].update(common_fields["extract"])
            # 스케줄 실행은 무인 실행이라 수동으로 "추출"을 누를 사람이 없음 —
            # extract 병합 이후에 강제해야 common_fields["extract"](file/db만
            # 있고 auto_save 키가 없음)에 덮어써지지 않음
            schedule_info["extract"]["auto_save"] = True
            schedule_info["extract"]["auto_save_source"] = auto_save_source
            schedule_info["extract"]["refine_rules"] = refine_rules_values
            schedule_info["extract"]["fill_null_value"] = refine_fill_value
            schedule_info["schedule"].update(common_fields["schedule"])
            store.add_schedule(schedule_info)
            dlg.accept()
            self._refresh_table()
            self._register_timer(len(store.get_schedules()) - 1)
        else:
            target = store.get_schedules()[idx]
            for key in ("task_nm", "callback_url", "delay", "threads",
                        "timeout", "retry", "user_agent", "cookie", "proxy"):
                target[key] = common_fields[key]
            target["extract"]["file"].update(common_fields["extract"]["file"])
            target["extract"]["db"].update(common_fields["extract"]["db"])
            target["extract"]["auto_save"] = True
            target["extract"]["auto_save_source"] = auto_save_source
            target["extract"]["refine_rules"] = refine_rules_values
            target["extract"]["fill_null_value"] = refine_fill_value
            target["schedule"].update(common_fields["schedule"])
            if idx in self._timers:
                self._timers[idx].stop()
                del self._timers[idx]
            dlg.accept()
            self._refresh_table()
            self._register_timer(idx)

        self._save_schedules_to_json()

    def _delete_schedule(self, idx):
        store.remove_schedule(idx)
        self._refresh_table()
        self._save_schedules_to_json()

    def _run_now(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules):
            return
        s = schedules[idx]
        store.update_schedule_status(idx, "실행 중")
        self._refresh_table()

        self.sched_task.update(deepcopy(BlueprintStorage().read()))
        self.sched_task.update(s)
        self.schedule_run.emit(self.sched_task)

    def _register_timer(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules):
            return
        s      = schedules[idx]
        run_at = s["schedule"]["run_at"]
        if not run_at:
            return
        ms = max(0, int((run_at - datetime.now()).total_seconds() * 1000))
        t  = QTimer(self)
        t.setSingleShot(True)
        if ms > self._MAX_TIMER_MS:
            t.timeout.connect(lambda i=idx: self._register_timer(i))
            t.start(self._MAX_TIMER_MS)
        else:
            t.timeout.connect(lambda i=idx: self._run_now(i))
            t.start(ms)
        self._timers[idx] = t

    def _update_countdown(self):
        """1초마다 Next Task 라벨 + Next Runtime 컬럼 갱신"""
        schedules = store.get_schedules()
        for row, s in enumerate(schedules):
            run_at = s["schedule"]["run_at"]
            txt    = self._format_remaining(run_at) if run_at else "—"
            item   = self.sched_table.item(row, 4)
            if item:
                item.setText(txt)
            else:
                new_item = QTableWidgetItem(txt)
                new_item.setForeground(QColor(PURPLE))
                self.sched_table.setItem(row, 4, new_item)

        active = [s for s in schedules
                  if s["schedule"]["run_at"] and s["schedule"]["status"] != "완료"]
        if not active:
            self.next_task_lbl.setText("등록된 스케줄 없음")
            self.next_task_lbl.setStyleSheet(
                self.next_task_lbl.styleSheet()
                .replace(ACCENT_LIGHT, TEXT_MUTED).replace(GREEN, TEXT_MUTED))
            return
        next_s = min(active, key=lambda s: s["schedule"]["run_at"])
        diff   = (next_s["schedule"]["run_at"] - datetime.now()).total_seconds()
        remaining_txt = "실행 대기 중" if diff < 0 else self._format_remaining(next_s["schedule"]["run_at"])
        self.next_task_lbl.setText(f"{next_s['task_nm']}  —  {remaining_txt}")
        self.next_task_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; font-size:13px; font-weight:bold; "
            f"background:transparent; border:none;")

    def mark_done(self, job_name: str):
        """작업 완료 후 interval에 따라 next run_at 자동 계산하여 재스케줄링"""
        now = datetime.now()
        for i, s in enumerate(store.get_schedules()):
            if s["task_nm"] != job_name:
                continue
            iv_key = s["schedule"]["interval"]
            run_at = s["schedule"].get("run_at", now)
            if iv_key == "daily":
                next_run = run_at + timedelta(days=1)
            elif iv_key == "weekly":
                next_run = run_at + timedelta(weeks=1)
            elif iv_key == "monthly":
                next_run = run_at + timedelta(days=30)
            else:
                store.remove_schedule(i)
                self._refresh_table()
                return
            store.get_schedules()[i]["schedule"]["run_at"] = next_run
            store.update_schedule_status(i, "대기")
            self._register_timer(i)
        self._refresh_table()
        self._save_schedules_to_json()

    def _save_schedules_to_json(self):
        try:
            serializable = []
            for s in store.get_schedules():
                entry  = deepcopy(s)
                run_at = entry.get("schedule", {}).get("run_at")
                if isinstance(run_at, datetime):
                    entry["schedule"]["run_at"] = run_at.isoformat()
                serializable.append(entry)
            os.makedirs(self.app_dir, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SchedulerPage] 스케줄 저장 실패: {e}")

    def _load_schedules_from_json(self):
        target = self.file_path if os.path.exists(self.file_path) else self.default_source
        if not os.path.exists(target):
            return
        try:
            with open(target, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, list):
                return
            now = datetime.now()
            for entry in saved:
                try:
                    run_at_raw = entry.get("schedule", {}).get("run_at")
                    run_at_dt  = (datetime.fromisoformat(run_at_raw)
                                  if isinstance(run_at_raw, str) else None)
                    if (entry.get("schedule", {}).get("interval") == "date"
                            and run_at_dt and run_at_dt < now):
                        entry["schedule"]["status"] = "완료"
                        entry["schedule"]["run_at"]  = None
                    else:
                        entry["schedule"]["run_at"] = run_at_dt
                    store.add_schedule(entry)
                except Exception as e:
                    print(f"[SchedulerPage] 스케줄 항목 복원 실패: {e}")
                    continue
            for idx, s in enumerate(store.get_schedules()):
                if s["schedule"].get("status") != "완료":
                    self._register_timer(idx)
        except Exception as e:
            print(f"[SchedulerPage] 스케줄 파일 로드 실패: {e}")

    # ── 스케줄 작업 등록·수정 통합 저장 ──────────────────

    # ── 스케줄 작업 Dialog (등록 / 수정 통합) ──────────────
    def _manage_schedule_task(self, sched_task=None, idx=None):
        """
        스케줄 등록·수정 다이얼로그를 띄운다.

        Parameters
        ----------
        sched_task : str  '등록' | '수정'
        idx        : int  수정 대상 스케줄 인덱스 (수정 모드에서만 필요)
        """
        # ── 수정 모드 선가드 ──────────────────────────────
        s = None
        if sched_task == "수정":
            if idx is None:
                return
            schedules = store.get_schedules()
            if idx >= len(schedules):
                return
            s = schedules[idx]

            # 수정 모드에서 공통으로 쓰이는 기존 값을 한 번만 파싱
            output_info      = customized_settings.get_output_settings()
            existing_extract = s.get("extract", output_info.get("extract", {}))
            ef               = existing_extract.get("file", {})
            edb              = existing_extract.get("db", {})
            existing_schedule   = s.get("schedule", {})
            existing_exec_str   = existing_schedule.get("exec_str", "")
            existing_interval   = existing_schedule.get("interval", "none")
            existing_run_at     = existing_schedule.get("run_at")
        else:
            output_info = customized_settings.get_output_settings()

        # ── 정제 규칙 설정(스케줄 전용) 초기값 ─────────────
        # "refine_rules" 키가 없으면(구버전 스케줄 또는 신규 등록) 기본값으로 폴백.
        # "제외 필드 지정"(drop_columns)은 애초에 키 자체를 두지 않는다(오른쪽 정제
        # 규칙 패널 참고 — Raw 수집 결과를 봐야 설정 가능한 규칙이라 무인 실행
        # 특성상 제외).
        if sched_task == "수정":
            _saved_refine_rules = existing_extract.get("refine_rules", SCHEDULED_REFINE_RULES_DIALOG_DEFAULT)
            _saved_fill_value   = existing_extract.get("fill_null_value", "")
        else:
            _saved_refine_rules = SCHEDULED_REFINE_RULES_DIALOG_DEFAULT
            _saved_fill_value   = ""

        # ── 다이얼로그 기본 설정 ──────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("새 스케줄 등록" if sched_task == "등록" else "스케줄 수정")
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        # 좌(기존 폼)/우(정제 규칙 패널, "정제" 선택 시에만 노출) 2열 구조 —
        # 정제 규칙 설정을 세로가 아닌 가로 방향으로 확장해 다이얼로그가
        # 무한정 길어지지 않도록 함(2026-07-17, UI/UX 피드백)
        outer = QHBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_container = QWidget()
        outer.addWidget(left_container, 2)

        root = QVBoxLayout(left_container)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 공통 헬퍼 ─────────────────────────────────────
        def sec_label(text):
            lbl = parts.make_label(text.upper(), TEXT_MUTED, 9)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1.5px;")
            return lbl

        def field_row(label, widget, label_w=110):
            row = QHBoxLayout()
            row.setSpacing(8)
            lw = parts.make_label(label, TEXT_SECONDARY, 12)
            lw.setFixedWidth(label_w)
            row.addWidget(lw)
            row.addWidget(widget, 1)
            return row

        def hms_combos():
            h = QComboBox()
            h.addItems([f"{t:02d}" for t in range(24)])
            m = QComboBox()
            m.addItems([f"{t:02d}" for t in range(60)])
            sc = QComboBox()
            sc.addItems([f"{t:02d}" for t in range(60)])
            hms_style = f"""
                QComboBox {{
                    background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER_LIGHT}; border-radius:4px;
                    padding:2px 4px; font-size:12px;
                }}
                QComboBox::drop-down {{ border:none; width:14px; }}
                QComboBox QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
                }}
            """
            for cb in (h, m, sc):
                cb.setFixedWidth(52)
                cb.setStyleSheet(hms_style)
            return h, m, sc

        def time_sep():
            lbl = parts.make_label(":", TEXT_MUTED, 13, True)
            lbl.setFixedWidth(8)
            return lbl

        def iv_lbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 12)

        def _parse_hms_from_exec_str(exec_str: str):
            """exec_str 마지막 HH:MM:SS 파싱 → (h, m, s) int tuple"""
            try:
                part = exec_str.strip().split()[-1]
                h_, m_, s_ = part.split(":")
                return int(h_), int(m_), int(s_)
            except Exception:
                return 0, 0, 0

        # ── 타이틀 ────────────────────────────────────────
        root.addWidget(parts.make_label(
            "새 스케줄 등록" if sched_task == "등록" else "스케줄 수정",
            TEXT_PRIMARY, 14, True
        ))
        root.addSpacing(10)
        root.addWidget(Divider())
        root.addSpacing(14)

        # ── 기본 정보 ─────────────────────────────────────
        root.addWidget(sec_label("기본 정보"))
        root.addSpacing(8)

        if sched_task == "등록":
            sched_name   = QLineEdit("작업명을 입력하세요.")
            callback_url = QLineEdit(BlueprintStorage().read()["callback_url"])
        else:
            sched_name   = QLineEdit(s.get("task_nm", ""))
            callback_url = QLineEdit(s.get("callback_url", ""))

        callback_url.setCursorPosition(0)
        root.addLayout(field_row("Task Name", sched_name))
        root.addSpacing(6)
        root.addLayout(field_row("Target URL", callback_url))
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── 수집 설정 ─────────────────────────────────────
        root.addWidget(sec_label("수집 설정"))
        root.addSpacing(8)

        sched_delay = QDoubleSpinBox()
        sched_delay.setRange(0.5, 10.0)
        sched_delay.setSingleStep(0.5)
        sched_delay.setDecimals(1)
        sched_delay.setValue(s.get("delay", 0.5) if sched_task == "수정" else 0.5)

        sched_threads = QSpinBox()
        sched_threads.setRange(1, 16)
        sched_threads.setValue(s.get("threads", 4) if sched_task == "수정" else 4)

        sched_timeout = QSpinBox()
        sched_timeout.setRange(1, 60)
        sched_timeout.setValue(s.get("timeout", 10) if sched_task == "수정" else 10)

        sched_retry = QSpinBox()
        sched_retry.setRange(0, 5)
        sched_retry.setValue(s.get("retry", 3) if sched_task == "수정" else 3)

        cs_row = QHBoxLayout()
        cs_row.setSpacing(8)
        for lbl_txt, w in [
            ("Delay(s)", sched_delay), ("Thread", sched_threads),
            ("Timeout(s)", sched_timeout), ("Retry", sched_retry)
        ]:
            cs_row.addWidget(parts.make_label(lbl_txt, TEXT_MUTED, 11))
            cs_row.addWidget(w)
        cs_row.addStretch()
        root.addLayout(cs_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── Save Setting ──────────────────────────────────
        root.addWidget(sec_label("Save Setting"))
        root.addSpacing(8)

        if sched_task == "등록":
            self._sched_out_mode = "FILE" if output_info["extract"]["file"]["enabled"] else "DB"
        else:
            self._sched_out_mode = "FILE" if ef.get("enabled", True) else "DB"

        sched_out_file_btn = TagButton("FILE")
        sched_out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        sched_out_db_btn = TagButton("DB")
        sched_out_db_btn.setToolTip("데이터베이스 서버로 전송")
        sched_out_file_btn.setChecked(self._sched_out_mode == "FILE")
        sched_out_db_btn.setChecked(self._sched_out_mode == "DB")

        sched_out_mode_lbl = parts.make_label(
            "로컬 파일 저장 모드" if self._sched_out_mode == "FILE" else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(parts.make_label("출력 대상", TEXT_MUTED, 11))
        out_row.addSpacing(6)
        out_row.addWidget(sched_out_file_btn)
        out_row.addWidget(sched_out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(sched_out_mode_lbl)
        out_row.addStretch()
        root.addLayout(out_row)
        root.addSpacing(8)

        # ── 자동 저장 대상 (RAW / 정제) ────────────────────
        if sched_task == "등록":
            sched_auto_save_source = output_info["extract"].get("auto_save_source", "raw")
        else:
            sched_auto_save_source = existing_extract.get("auto_save_source", "raw")

        sched_auto_raw_btn = TagButton("RAW")
        sched_auto_ref_btn = TagButton("정제")
        sched_auto_raw_btn.setChecked(sched_auto_save_source != "refined")
        sched_auto_ref_btn.setChecked(sched_auto_save_source == "refined")
        sched_auto_ref_btn.setToolTip(
            "정제 선택 시 오른쪽에 이 스케줄에 적용할 정제 규칙 패널이 나타납니다. "
            "현재 화면의 '② 정제 규칙 설정' 탭 체크 상태와는 무관합니다."
        )

        auto_src_row = QHBoxLayout()
        auto_src_row.setSpacing(8)
        auto_src_row.addWidget(parts.make_label("저장 대상", TEXT_MUTED, 11))
        auto_src_row.addSpacing(6)
        auto_src_row.addWidget(sched_auto_raw_btn)
        auto_src_row.addWidget(sched_auto_ref_btn)
        auto_src_row.addStretch()
        root.addLayout(auto_src_row)
        root.addSpacing(8)

        # ── 정제 규칙 설정 패널 (오른쪽, "정제" 선택 시에만 노출) ──────
        # "제외 필드 지정"은 Raw 수집 결과를 봐야 설정 가능한 규칙이라 무인 실행
        # 특성상 제공하지 않음(나머지 6개 규칙만 구성 가능).
        sched_refine_divider = Divider(orientation="v")
        sched_refine_panel = QWidget()
        # 고정 폭 대신 최소/최대 폭만 지정 — 창을 가로로 늘리면 이 패널도 함께
        # 넓어져 규칙 설명 텍스트가 더 여유 있게 보이도록 함(2026-07-17, 텍스트
        # 잘림 피드백. wordWrap도 함께 켰지만 창 폭을 넓혀 더 여유를 줄 수 있게)
        sched_refine_panel.setMinimumWidth(260)
        sched_refine_panel.setMaximumWidth(400)
        refine_panel_layout = QVBoxLayout(sched_refine_panel)
        refine_panel_layout.setContentsMargins(16, 18, 0, 18)
        refine_panel_layout.setSpacing(8)

        refine_panel_layout.addWidget(parts.make_label("정제 규칙 설정", TEXT_PRIMARY, 12, bold=True))
        refine_panel_desc = parts.make_label(
            "무인(스케줄) 실행 시 적용할 규칙입니다. \"제외 필드 지정\"은 Raw 수집 결과를 "
            "직접 봐야 설정 가능해 여기서는 제공되지 않습니다.",
            TEXT_MUTED, 10
        )
        refine_panel_desc.setWordWrap(True)
        refine_panel_layout.addWidget(refine_panel_desc)
        refine_panel_layout.addSpacing(4)

        sched_refine_checkboxes: dict[str, QCheckBox] = {}
        _refine_panel_result = build_refine_rule_rows(
            parts, refine_panel_layout, sched_refine_checkboxes, dict(_saved_refine_rules),
            include_keys=[
                "remove_null_row", "custom_rule", "trim_whitespace",
                "remove_duplicate", "fill_null", "cast_numeric",
            ],
        )
        sched_refine_fill_input = _refine_panel_result["fill_null_input"]
        if sched_refine_fill_input is not None:
            sched_refine_fill_input.setText(_saved_fill_value)

        # "커스텀 정제 규칙 적용" 체크 시 ①③④ 자동 연동 — MonitorPage의
        # _on_custom_rule_toggled(trigger.py)와 동일 로직(fill_null 제외,
        # 2026-07-17), 이 패널의 로컬 checkboxes 딕셔너리에 대해서만 적용.
        _sched_refine_custom_cb = sched_refine_checkboxes.get("custom_rule")
        if _sched_refine_custom_cb is not None:
            def _on_sched_refine_custom_rule_toggled(chk_state):
                if chk_state != Qt.CheckState.Checked.value:
                    return
                for key in ("remove_null_row", "remove_duplicate", "trim_whitespace"):
                    cb = sched_refine_checkboxes.get(key)
                    if cb is not None:
                        cb.setChecked(True)
            _sched_refine_custom_cb.stateChanged.connect(_on_sched_refine_custom_rule_toggled)

        refine_panel_layout.addStretch()

        sched_refine_divider.setVisible(sched_auto_ref_btn.isChecked())
        sched_refine_panel.setVisible(sched_auto_ref_btn.isChecked())
        outer.addWidget(sched_refine_divider)
        outer.addWidget(sched_refine_panel, 1)

        def _sched_select_auto_src(is_refined):
            sched_auto_raw_btn.setChecked(not is_refined)
            sched_auto_ref_btn.setChecked(is_refined)
            sched_refine_divider.setVisible(is_refined)
            sched_refine_panel.setVisible(is_refined)
            dlg.layout().activate()
            # setVisible() 직후에는 dlg.sizeHint()가 아직 새 크기를 반영하지
            # 못한 경우가 있어(_update_sched_dialog_size()와 동일 원인), 이벤트
            # 루프를 한 번 처리시켜 레이아웃을 정착시킨 뒤 resize. adjustSize()는
            # 이미 show()된 다이얼로그에서는 줄어드는 방향으로 갱신되지 않아 미사용.
            QApplication.processEvents()
            dlg.layout().activate()
            dlg.resize(dlg.sizeHint())

        sched_auto_raw_btn.clicked.connect(lambda: _sched_select_auto_src(False))
        sched_auto_ref_btn.clicked.connect(lambda: _sched_select_auto_src(True))

        # ── 추출 설정 스택 (FILE / DB) ────────────────────
        sched_extract_stack = QStackedWidget()
        sched_extract_stack.setObjectName("schedExtractStack")
        sched_extract_stack.setStyleSheet(f"""
            QStackedWidget#schedExtractStack {{
                background:{BG_PRIMARY};
                border:1px solid {BORDER};
                border-radius:6px;
            }}
            QStackedWidget#schedExtractStack > QWidget {{
                background:{BG_PRIMARY};
                border:none;
            }}
        """)
        sched_extract_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # ── PAGE 0 : FILE 설정 ────────────────────────────
        sched_file_page = QWidget()
        sfp = QVBoxLayout(sched_file_page)
        sfp.setContentsMargins(14, 14, 14, 14)
        sfp.setSpacing(10)

        _fp = (ef.get("file_path") or customized_settings.set_desktop_dir()) if sched_task == "수정" \
              else (output_info["extract"]["file"]["file_path"] or customized_settings.set_desktop_dir())

        sched_path_lay = QHBoxLayout()
        sched_path_lay.setSpacing(8)
        sched_path_lay.addWidget(parts.make_label("경로", TEXT_SECONDARY, 12))
        sched_path_edit = QLineEdit(_fp)
        sched_path_edit.setReadOnly(True)
        sched_path_lay.addWidget(sched_path_edit, 1)
        sched_browse_btn = parts.outline_btn("Browse")
        sched_browse_btn.setFixedWidth(72)

        def _sched_browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", sched_path_edit.text() or "")
            if folder:
                sched_path_edit.setText(folder)

        sched_browse_btn.clicked.connect(_sched_browse)
        sched_path_lay.addWidget(sched_browse_btn)
        sfp.addLayout(sched_path_lay)

        _fn = (ef.get("file_name") or "untitled0") if sched_task == "수정" \
              else (output_info["extract"]["file"]["file_name"] or "untitled0")
        sched_fnm_lay = QHBoxLayout()
        sched_fnm_lay.setSpacing(10)
        sched_fnm_lay.addWidget(parts.make_label("파일명", TEXT_SECONDARY, 12))
        sched_file_nm = QLineEdit(_fn)
        sched_fnm_lay.addWidget(sched_file_nm)
        sfp.addLayout(sched_fnm_lay)

        sched_opt_lay = QHBoxLayout()
        sched_opt_lay.setSpacing(10)
        sched_opt_lay.addWidget(parts.make_label("형식", TEXT_SECONDARY, 12))

        sched_fmt_combo = QComboBox()
        sched_fmt_combo.addItems(["CSV", "JSON", "Excel"])
        sched_fmt_combo.setCurrentText(
            ef.get("file_format") or "CSV" if sched_task == "수정"
            else output_info["extract"]["file"]["file_format"]
        )
        sched_opt_lay.addWidget(sched_fmt_combo)
        sched_opt_lay.addSpacing(10)

        sched_enc_widget = QWidget()
        sched_enc_lay = QHBoxLayout(sched_enc_widget)
        sched_enc_lay.setContentsMargins(0, 0, 0, 0)
        sched_enc_lay.setSpacing(10)
        sched_enc_combo = QComboBox()
        sched_enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
        sched_enc_combo.setCurrentText(
            ef.get("file_encoding") or "UTF-8 BOM" if sched_task == "수정"
            else output_info["extract"]["file"]["file_encoding"]
        )
        sched_enc_lay.addWidget(parts.make_label("인코딩", TEXT_SECONDARY, 12))
        sched_enc_lay.addWidget(sched_enc_combo)
        sched_opt_lay.addWidget(sched_enc_widget)
        sched_opt_lay.addSpacing(10)

        sched_delim_widget = QWidget()
        sched_delim_lay = QHBoxLayout(sched_delim_widget)
        sched_delim_lay.setContentsMargins(0, 0, 0, 0)
        sched_delim_lay.setSpacing(10)
        sched_csv_delim = QLineEdit()
        sched_csv_delim.setText(
            ef.get("file_delimiter") or "," if sched_task == "수정"
            else (output_info["extract"]["file"]["file_delimiter"] or ",")
        )
        sched_delim_lay.addWidget(parts.make_label("구분자", TEXT_SECONDARY, 12))
        sched_delim_lay.addWidget(sched_csv_delim)
        sched_opt_lay.addWidget(sched_delim_widget)
        sched_opt_lay.addStretch()
        sfp.addLayout(sched_opt_lay)

        def _sched_on_fmt_changed(fmt_text: str):
            is_csv = (fmt_text == "CSV")
            sched_enc_widget.setVisible(is_csv)
            sched_delim_widget.setVisible(is_csv)

        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed)
        _sched_on_fmt_changed(sched_fmt_combo.currentText())

        sched_extract_stack.addWidget(sched_file_page)  # index 0

        # ── PAGE 1 : DB 설정 ──────────────────────────────
        sched_db_page = QWidget()
        sdp = QVBoxLayout(sched_db_page)
        sdp.setContentsMargins(14, 14, 14, 14)
        sdp.setSpacing(8)

        def _slbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 11)

        def _sinp(txt="", ph=""):
            e = QLineEdit(txt)
            e.setPlaceholderText(ph)
            return e

        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        sgrid.setColumnStretch(1, 1)

        _sdb_type = QComboBox()
        _sdb_type.addItems(["MySQL", "PostgreSQL", "MongoDB"])

        if sched_task == "등록":
            _sdb_type.setCurrentText(output_info["extract"]["db"]["db_env"])
            _sdb_host   = _sinp(txt=output_info["extract"]["db"]["host"])
            _sdb_port   = _sinp(txt=output_info["extract"]["db"]["port"])
            _sdb_name   = _sinp(output_info["extract"]["db"]["database"])
            _sdb_schema = _sinp(output_info["extract"]["db"]["schema"])
            _sdb_user   = _sinp(output_info["extract"]["db"]["user"])
            _sdb_pw     = _sinp(output_info["extract"]["db"]["password"])
            _sdb_data   = _sinp(output_info["extract"]["db"]["save_data_nm"])
        else:
            _sdb_type.setCurrentText(edb.get("db_env") or "MySQL")
            _sdb_host   = _sinp(edb.get("host") or "localhost")
            _sdb_port   = _sinp(edb.get("port") or "3306")
            _sdb_name   = _sinp(edb.get("database") or "")
            _sdb_schema = _sinp(edb.get("schema") or "")
            _sdb_user   = _sinp(edb.get("user") or "")
            _sdb_pw     = _sinp(edb.get("password") or "")
            _sdb_data   = _sinp(edb.get("save_data_nm") or "")

        _sdb_pw.setEchoMode(QLineEdit.EchoMode.Password)

        for _row_i, (_label, _widget) in enumerate([
            ("DB Type", _sdb_type), ("HOST", _sdb_host), ("PORT", _sdb_port),
            ("DB Name", _sdb_name), ("SCHEMA", _sdb_schema),
            ("USER", _sdb_user), ("PASSWORD", _sdb_pw), ("DATA Name", _sdb_data),
        ]):
            sgrid.addWidget(_slbl(_label), _row_i, 0)
            sgrid.addWidget(_widget, _row_i, 1)

        _sdb_type.currentTextChanged.connect(lambda t: _sdb_port.setText(DB_PORTS.get(t, "")))
        sdp.addLayout(sgrid)

        sched_test_row = QHBoxLayout()
        sched_test_row.setSpacing(10)
        sched_test_btn = parts.outline_btn("TEST CONNECTION")
        sched_test_result_lbl = parts.make_label("", TEXT_MUTED, 11)

        def _show_sched_conn_fail_dialog(reason: str):
            msg = QMessageBox(dlg)
            msg.setWindowTitle("연결 실패")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("<b>DB 연결에 실패했습니다.</b>")
            msg.setInformativeText(reason)
            msg.setStyleSheet(f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:12px; }}
                QPushButton {{
                    background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px;
                }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """)
            msg.exec()

        def _sched_test_conn():
            host = _sdb_host.text().strip() or "localhost"
            try:
                port = int(_sdb_port.text().strip())
            except ValueError:
                sched_test_result_lbl.setText("⚠ 포트 번호가 올바르지 않습니다")
                sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                _show_sched_conn_fail_dialog("포트 번호에 숫자가 아닌 값이 입력되어 있습니다.\n올바른 포트 번호를 입력하세요.")
                return
            sched_test_result_lbl.setText("⏳ 연결 중...")
            sched_test_result_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            sched_test_btn.setEnabled(False)
            QApplication.processEvents()
            info = {
                "db_env":       _sdb_type.currentText(),
                "host":         host,
                "port":         str(port),
                "database":     _sdb_name.text().strip(),
                "schema":       _sdb_schema.text().strip(),
                "user":         _sdb_user.text().strip(),
                "password":     _sdb_pw.text(),
                "save_data_nm": _sdb_data.text().strip(),
            }
            try:
                ok, reason = db_conn._check_db_connect_info(info)
                if ok:
                    sched_test_result_lbl.setText(f"✅ {host}:{port} 연결 성공")
                    sched_test_result_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
                else:
                    sched_test_result_lbl.setText("❌ 연결 실패")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_sched_conn_fail_dialog(reason)
            except ImportError:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        sched_test_result_lbl.setText(f"✅ {host}:{port} 소켓 연결 성공 (DB 드라이버 미설치)")
                        sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                except OSError as e:
                    sched_test_result_lbl.setText("❌ 연결 실패")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                    _show_sched_conn_fail_dialog(
                        f"DB 드라이버가 설치되어 있지 않아 소켓 연결을 시도했으나 실패했습니다.\n\n원인: {e}"
                    )
            except Exception as e:
                sched_test_result_lbl.setText("❌ 연결 실패")
                sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
                _show_sched_conn_fail_dialog(str(e))
            finally:
                sched_test_btn.setEnabled(True)

        sched_test_btn.clicked.connect(_sched_test_conn)
        sched_test_row.addWidget(sched_test_btn)
        sched_test_row.addWidget(sched_test_result_lbl)
        sched_test_row.addStretch()
        sdp.addLayout(sched_test_row)

        sched_extract_stack.addWidget(sched_db_page)  # index 1
        sched_extract_stack.setCurrentIndex(0 if self._sched_out_mode == "FILE" else 1)

        def _update_sched_dialog_size():
            current_page = sched_extract_stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                sched_extract_stack.setFixedHeight(current_page.layout().sizeHint().height())
            dlg.layout().activate()
            # setFixedHeight() 직후에는 dlg.sizeHint()가 아직 새 높이를 반영하지
            # 못한 상태(한 박자 뒤처진 값)를 돌려주는 경우가 있어(실측 확인 —
            # DB→FILE 전환 시 늘어난 세로 길이가 되돌아가지 않던 버그의 원인),
            # 이벤트 루프를 한 번 처리시켜 레이아웃을 완전히 정착시킨 뒤 sizeHint
            # 기준으로 resize. adjustSize()는 이미 show()된 다이얼로그에서 창을
            # 줄이는 방향으로는 갱신되지 않아 사용하지 않음.
            QApplication.processEvents()
            dlg.layout().activate()
            dlg.resize(dlg.sizeHint())

        def _sched_on_file_clicked():
            self._sched_out_mode = "FILE"
            sched_out_mode_lbl.setText("로컬 파일 저장 모드")
            sched_out_db_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(0)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        def _sched_on_db_clicked():
            self._sched_out_mode = "DB"
            sched_out_mode_lbl.setText("DB 서버 전송 모드")
            sched_out_file_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(1)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        sched_out_file_btn.clicked.connect(_sched_on_file_clicked)
        sched_out_db_btn.clicked.connect(_sched_on_db_clicked)

        sched_fmt_combo.currentTextChanged.disconnect(_sched_on_fmt_changed)
        def _sched_on_fmt_changed_with_resize(fmt_text: str):
            _sched_on_fmt_changed(fmt_text)
            _update_sched_dialog_size()
        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed_with_resize)

        root.addWidget(sched_extract_stack)
        root.addSpacing(10)

        # ── 저장 방식 콤보 ────────────────────────────────
        sched_save_type = QComboBox()
        sched_save_type.addItems(["선택하세요", "새로 만들기", "덮어쓰기", "추가하기"])
        if sched_task == "수정":
            existing_save_type = existing_schedule.get("schedule_save_type", "선택하세요")
            if existing_save_type in ["새로 만들기", "덮어쓰기", "추가하기"]:
                sched_save_type.setCurrentText(existing_save_type)
        sched_save_type.setFixedWidth(130)
        sched_save_type.setStyleSheet(theme.CB_STYLE)

        sv_row = QHBoxLayout()
        sv_row.setSpacing(8)
        sv_row.addWidget(parts.make_label("저장 방식", TEXT_MUTED, 11))
        sv_row.addWidget(sched_save_type)
        sv_row.addStretch()
        root.addLayout(sv_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        _update_sched_dialog_size()

        # ── Interval ──────────────────────────────────────
        root.addWidget(sec_label("Interval"))
        root.addSpacing(8)

        sched_interval = QComboBox()
        sched_interval.addItems(["선택하세요", "매일", "매주", "매월", "특정 날짜"])
        sched_interval.setFixedWidth(120)
        sched_interval.setStyleSheet(theme.CB_STYLE)

        container_daily   = QWidget()
        container_weekly  = QWidget()
        container_monthly = QWidget()
        container_date    = QWidget()

        # 매일
        self.d_h, self.d_m, self.d_s = hms_combos()
        dl = QHBoxLayout(container_daily)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        dl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_h, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_m, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_daily.setVisible(False)

        # 매주
        self.w_day = QComboBox()
        self.w_day.addItems(["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"])
        self.w_day.setFixedWidth(76)
        self.w_day.setStyleSheet(theme.CB_STYLE)
        self.w_h, self.w_m, self.w_s = hms_combos()
        wl = QHBoxLayout(container_weekly)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(6)
        wl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(iv_lbl("매주"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_day, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addSpacing(6)
        wl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_h, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_m, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_weekly.setVisible(False)

        # 매월
        self.m_day = QComboBox()
        self.m_day.addItems([str(d) for d in range(1, 32)])
        self.m_day.setFixedWidth(50)
        self.m_day.setStyleSheet(theme.CB_STYLE)
        self.m_h, self.m_m, self.m_s = hms_combos()
        ml = QHBoxLayout(container_monthly)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(6)
        ml.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("매월"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_day, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("일"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addSpacing(6)
        ml.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_h, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_m, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_monthly.setVisible(False)

        # 특정 날짜
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFixedWidth(110)
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_LIGHT}; border-radius:4px; padding:4px 6px; font-size:12px;
            }}
            QDateEdit::drop-down {{
                subcontrol-origin:padding; subcontrol-position:center right;
                width:20px; border-left:1px solid {BORDER_LIGHT};
                border-radius:0 4px 4px 0; background:{BG_HOVER};
            }}
            QDateEdit::down-arrow {{
                image:none; width:0; height:0;
                border-left:4px solid transparent; border-right:4px solid transparent;
                border-top:5px solid {TEXT_SECONDARY}; margin:0 4px;
            }}
        """)
        cal = self.date_edit.calendarWidget()
        if cal:
            cal.setMinimumDate(QDate.currentDate())
            cal.setStyleSheet(f"""
                QCalendarWidget QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    selection-background-color:{ACCENT}; selection-color:white;
                }}
                QCalendarWidget QAbstractItemView:disabled {{ color:{TEXT_MUTED}; background:{BG_PRIMARY}; }}
                QCalendarWidget QWidget#qt_calendar_navigationbar {{ background:{BG_PRIMARY}; }}
                QCalendarWidget QToolButton {{
                    background:transparent; color:{TEXT_PRIMARY}; font-size:12px; border:none; padding:4px;
                }}
                QCalendarWidget QToolButton:hover {{ background:{BG_HOVER}; border-radius:4px; }}
                QCalendarWidget QMenu {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}
                QCalendarWidget QSpinBox {{ background:{BG_PRIMARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER_LIGHT}; border-radius:3px; }}
            """)

        self.dat_h, self.dat_m, self.dat_s = hms_combos()
        datl = QHBoxLayout(container_date)
        datl.setContentsMargins(0, 0, 0, 0)
        datl.setSpacing(6)
        datl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(iv_lbl("날짜"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.date_edit, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addSpacing(6)
        datl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_h, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_m, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_date.setVisible(False)

        # ── 수정 모드: 기존 값을 위젯에 반영 ─────────────
        if sched_task == "수정":
            _iv_map = {"daily": 1, "weekly": 2, "monthly": 3, "date": 4}
            sched_interval.setCurrentIndex(_iv_map.get(existing_interval, 0))

            _ph, _pm, _ps = _parse_hms_from_exec_str(existing_exec_str)
            for cb, val in [
                (self.d_h, _ph), (self.d_m, _pm), (self.d_s, _ps),
                (self.w_h, _ph), (self.w_m, _pm), (self.w_s, _ps),
                (self.m_h, _ph), (self.m_m, _pm), (self.m_s, _ps),
                (self.dat_h, _ph), (self.dat_m, _pm), (self.dat_s, _ps),
            ]:
                cb.setCurrentText(f"{val:02d}")

            if existing_interval == "weekly":
                _DAY_NAMES = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
                for dn in _DAY_NAMES:
                    if dn in existing_exec_str:
                        self.w_day.setCurrentText(dn)
                        break

            if existing_interval == "monthly":
                try:
                    _day_match = re.search(r"매월\s*(\d+)일", existing_exec_str)
                    if _day_match:
                        self.m_day.setCurrentText(_day_match.group(1))
                except Exception:
                    pass

            if existing_interval == "date" and existing_run_at:
                try:
                    ra = existing_run_at if isinstance(existing_run_at, datetime) \
                         else datetime.fromisoformat(str(existing_run_at))
                    self.date_edit.setDate(QDate(ra.year, ra.month, ra.day))
                except Exception:
                    self.date_edit.setDate(QDate.currentDate())
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())

        # ── 주기 선택 행 ──────────────────────────────────
        iv_row = QHBoxLayout()
        iv_row.setSpacing(8)
        iv_row.setContentsMargins(0, 0, 0, 0)
        iv_row.addWidget(iv_lbl("주기"), 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addWidget(sched_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addStretch()

        detail_wrap = QWidget()
        detail_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detail_lay = QHBoxLayout(detail_wrap)
        detail_lay.setContentsMargins(8, 0, 0, 0)
        detail_lay.setSpacing(6)
        for c in [container_daily, container_weekly, container_monthly, container_date]:
            detail_lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)
        detail_lay.addStretch()

        def _on_iv_changed(iv_idx):
            container_daily.setVisible(iv_idx == 1)
            container_weekly.setVisible(iv_idx == 2)
            container_monthly.setVisible(iv_idx == 3)
            container_date.setVisible(iv_idx == 4)

        sched_interval.currentIndexChanged.connect(_on_iv_changed)
        _on_iv_changed(sched_interval.currentIndex())

        root.addLayout(iv_row)
        root.setSpacing(4)
        root.addWidget(detail_wrap)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── sched_info_dict 구성 ──────────────────────────
        sched_info_dict = {
            "sched_task":   sched_task,         # _apply_schedule이 모드를 구분하는 키
            "idx":          idx,                 # 수정 시 int, 등록 시 None
            "sched_name":   sched_name,
            "callback_url": callback_url,
            "delay":        sched_delay,
            "threads":      sched_threads,
            "timeout":      sched_timeout,
            "retry":        sched_retry,
            "interval":     sched_interval,
            "d_h": self.d_h,   "d_m": self.d_m,   "d_s": self.d_s,
            "w_day": self.w_day,
            "w_h": self.w_h,   "w_m": self.w_m,   "w_s": self.w_s,
            "m_day": self.m_day,
            "m_h": self.m_h,   "m_m": self.m_m,   "m_s": self.m_s,
            "date_edit":    self.date_edit,
            "dat_h": self.dat_h, "dat_m": self.dat_m, "dat_s": self.dat_s,
            "save_type":    sched_save_type,
            "auto_src_ref_btn": sched_auto_ref_btn,
            "refine_checkboxes": sched_refine_checkboxes,   # {key: QCheckBox}
            "refine_fill_input": sched_refine_fill_input,   # QLineEdit | None
            "path_edit":    sched_path_edit,
            "file_nm":      sched_file_nm,
            "fmt_combo":    sched_fmt_combo,
            "enc_combo":    sched_enc_combo,
            "csv_delim":    sched_csv_delim,
            "db_type":      _sdb_type,
            "db_host":      _sdb_host,
            "db_port":      _sdb_port,
            "db_name":      _sdb_name,
            "db_schema":    _sdb_schema,
            "db_user":      _sdb_user,
            "db_pw":        _sdb_pw,
            "db_data":      _sdb_data,
        }

        # ── 하단 버튼 ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn  = parts.action_btn("적용")
        cancel_btn = parts.outline_btn("취소")
        apply_btn.clicked.connect(lambda: self._apply_schedule(dlg=dlg, sched_info_dict=sched_info_dict))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()


# ══════════════════════════════════════════════════════
#  SessionSettingsPage Mixin
# ══════════════════════════════════════════════════════
class SessionSettingsPageTriggers:
    """SessionSettingsPage의 프록시 추가·삭제·임포트·활성화 메서드"""

    def _activate_proxy_option(self, is_checked):
        for card in (self.gw2, self.pw):
            card.setEnabled(is_checked)
            self._set_card_visual(card, is_checked)

    def _import_proxy_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "프록시 목록 파일 선택", "",
            "텍스트 파일 (*.txt *.csv *.dat *.list);;모든 파일 (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception as e:
            self._log("err", f"파일 읽기 실패: {e}")
            return

        pattern = re.compile(r'(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})(?!\d)')
        matches = pattern.findall(raw)

        if not matches:
            self._import_lbl.setText("⚠ 유효한 IP:PORT 없음")
            self._import_lbl.setStyleSheet(
                f"color:{AMBER}; font-size:10px; background:transparent; border:none;")
            self._log("warn", f"파일 파싱 완료 — 유효한 IP:PORT를 찾지 못했습니다: {path}")
            return

        existing = {f"{r['host']}:{r['port']}" for r in self._proxy_rows}
        new_rows = []
        skipped  = 0
        for host, port in matches:
            key = f"{host}:{port}"
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            new_rows.append({"host": host, "port": port, "protocol": "HTTP",
                              "enabled": True, "latency": "—", "status": "활성"})

        added = len(new_rows)
        if added:
            # 대량 삽입 전 repaint·정렬·시그널 중단 — 전체 삽입 후 한 번만 그림
            # blockSignals: 행마다 itemChanged → _on_proxy_item_changed 디스패치 차단
            t = self._proxy_table
            t.setSortingEnabled(False)
            t.setUpdatesEnabled(False)
            t.blockSignals(True)
            try:
                for data in new_rows:
                    self._proxy_rows.append(data)
                    self._insert_table_row(data)
            finally:
                # 예외 발생 시에도 반드시 복원
                t.blockSignals(False)
                t.setUpdatesEnabled(True)
                t.setSortingEnabled(True)

        summary = f"✓ {added}개 추가" + (f"  (중복 {skipped}개 제외)" if skipped else "")
        self._import_lbl.setText(summary)
        self._import_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:10px; background:transparent; border:none;")
        self._log("ok", f"Import 완료: {added}개 추가 / {skipped}개 중복 제외 ← {path}")
        if added:
            self._log("info", "Import된 프록시는 기본값 HTTP / 활성 상태로 등록됩니다. 필요 시 개별 수정하세요.")

    def _add_proxy_dialog(self):
        """새 프록시 추가 Dialog를 띄운다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("새 프록시 추가")
        dlg.setFixedWidth(350)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        root.addWidget(parts.make_label("새 프록시 추가", TEXT_PRIMARY, 14, True))
        root.addSpacing(10)
        root.addWidget(Divider())
        root.addSpacing(14)

        proto_row = QHBoxLayout()
        proto_row.setContentsMargins(0, 0, 0, 15)
        proto_row.addWidget(parts.make_label("프로토콜", TEXT_SECONDARY, 12))
        proto_cb = QComboBox()
        proto_cb.addItems(["HTTP", "HTTPS", "SOCKS4", "SOCKS5"])
        proto_row.addWidget(proto_cb, 1)
        root.addLayout(proto_row)

        host_row = QHBoxLayout()
        host_row.setContentsMargins(0, 0, 0, 15)
        host_row.addWidget(parts.make_label("호스트", TEXT_SECONDARY, 12))
        host_inp = QLineEdit()
        host_inp.setPlaceholderText("예: 10.0.0.1")
        host_row.addWidget(host_inp, 1)
        root.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 15)
        port_row.addWidget(parts.make_label("포트", TEXT_SECONDARY, 12))
        port_inp = QLineEdit()
        port_inp.setPlaceholderText("예: 8080")
        port_row.addWidget(port_inp, 1)
        root.addLayout(port_row)

        btn_row = QHBoxLayout()
        ok_btn = parts.action_btn("추가")

        def _do_add():
            host  = host_inp.text().strip() or "0.0.0.0"
            port  = port_inp.text().strip() or "8080"
            proto = proto_cb.currentText()
            data  = {"host": host, "port": port, "protocol": proto,
                     "enabled": True, "latency": "—", "status": "활성"}
            self._proxy_rows.append(data)
            self._insert_table_row(data)
            self._log("ok", f"프록시 추가됨: {proto} {host}:{port}")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.close)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)
        dlg.exec()

    def _delete_row(self, row_idx):
        if 0 <= row_idx < self._proxy_table.rowCount():
            host     = self._proxy_table.item(row_idx, 2)
            host_txt = host.text() if host else "?"
            self._proxy_table.removeRow(row_idx)
            self._log("warn", f"프록시 삭제됨: {host_txt}")

    def _on_proxy_row_clicked(self, item):
        """
        모든 컬럼의 모든 행 클릭 시 활성/비활성 토글.

        [col 0 처리]
        itemChanged 는 체크 상태가 실제로 변경될 때만 발화하므로
        이미 체크된 셀을 다시 클릭하면 itemChanged 가 발화하지 않아
        _on_proxy_item_changed 만으로는 토글이 동작하지 않습니다.
        따라서 col 0 도 itemClicked 에서 처리하고,
        _on_proxy_item_changed 는 programmatic 변경(blockSignals 해제 후 재발화)
        방지 목적으로만 남겨둡니다.
        """
        row = item.row()
        if row >= len(self._proxy_rows):
            return
        current_enabled = self._proxy_rows[row]["enabled"]
        self._proxy_table.blockSignals(True)
        try:
            self._toggle_proxy_enabled(row, not current_enabled)
        finally:
            self._proxy_table.blockSignals(False)

    def _proxy_table_context_menu(self, pos):
        """
        우클릭 컨텍스트 메뉴 — 삭제 버튼(setCellWidget) 제거 대체.
        선택된 행을 삭제하거나 활성 상태를 토글합니다.
        """
        index = self._proxy_table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        menu = QMenu(self)
        # QSS는 THEME.PROXY_CONTEXT_MENU_QSS 프로퍼티에서 관리
        menu.setStyleSheet(theme.PROXY_CONTEXT_MENU_QSS)
        # 활성 토글 — checkState() 기준 (ItemIsUserCheckable 체크박스)
        enabled_item = self._proxy_table.item(row, 0)
        is_enabled = (
            enabled_item.checkState() == Qt.CheckState.Checked
        ) if enabled_item else False
        toggle_txt = "비활성으로 전환" if is_enabled else "활성으로 전환"
        toggle_act = menu.addAction(toggle_txt)
        menu.addSeparator()
        # 삭제
        del_act = menu.addAction("🗑  이 행 삭제")
        del_act.setProperty("is_delete", True)

        action = menu.exec(self._proxy_table.viewport().mapToGlobal(pos))
        if action == del_act:
            self._delete_row(row)
        elif action == toggle_act:
            # blockSignals: _toggle_proxy_enabled 내 col 0 setCheckState 시
            # itemChanged 재발생 → _on_proxy_item_changed 중복 호출 방지
            self._proxy_table.blockSignals(True)
            try:
                self._toggle_proxy_enabled(row, not is_enabled)
            finally:
                self._proxy_table.blockSignals(False)

    def _toggle_proxy_enabled(self, row: int, enable: bool):
        """
        활성 체크박스 상태·상태 컬럼·_proxy_rows 동기화.
        호출 전 반드시 blockSignals(True)로 감싸야 itemChanged 재귀를 방지합니다.
        """
        t = self._proxy_table
        if row >= t.rowCount():
            return
        # col 0 — 체크 상태 변경 (setText/setForeground 제거 — 체크박스는 텍스트 무관)
        enabled_item = t.item(row, 0)
        if enabled_item:
            enabled_item.setCheckState(
                Qt.CheckState.Checked if enable else Qt.CheckState.Unchecked
            )
        # col 5 — 상태 텍스트·색상 동기화
        status_item = t.item(row, 5)
        if status_item:
            status_txt = "활성" if enable else "비활성"
            status_item.setText(status_txt)
            status_item.setForeground(QColor(GREEN if enable else TEXT_MUTED))
        # _proxy_rows 동기화
        if row < len(self._proxy_rows):
            self._proxy_rows[row]["enabled"] = enable
            self._proxy_rows[row]["status"]  = "활성" if enable else "비활성"

    def _on_proxy_item_changed(self, item):
        """
        itemChanged 시그널 수신 — 사용자가 체크박스를 직접 클릭했을 때 호출됩니다.

        [재귀 방지]
        col 0이 아닌 변경(상태 컬럼 등)은 즉시 return합니다.
        _toggle_proxy_enabled() 호출 전 blockSignals(True)로 감싸
        col 0 setCheckState 시 itemChanged 재발생을 차단합니다.

        [_seed / 대량 import 중 호출 방지]
        blockSignals(True)로 삽입 루프를 감싸면 이 슬롯이 호출되지 않습니다.
        방어 조건으로 row >= len(_proxy_rows)이면 return합니다.
        """
        if item.column() != 0:
            return   # 활성 컬럼(col 0) 이외 변경은 무시
        row = item.row()
        if row >= len(self._proxy_rows):
            return   # _proxy_rows 미등록 행 방어 (seed/import 중 누수 방지)
        enable = item.checkState() == Qt.CheckState.Checked
        # blockSignals: _toggle_proxy_enabled 내 setCheckState → itemChanged 재귀 차단
        self._proxy_table.blockSignals(True)
        try:
            self._toggle_proxy_enabled(row, enable)
        finally:
            self._proxy_table.blockSignals(False)

    def _log(self, level: str, message: str) -> None:
        pass


# ══════════════════════════════════════════════════════
#  AuthManagerPage Mixin
# ══════════════════════════════════════════════════════
class AuthManagerPageTriggers:
    """AuthManagerPage의 자격증명·로그인·TLS 메서드"""

    def _get_log_manager(self):
        """
        최상위 MainWindow의 log_manager(LogViewerDialog 싱글턴)를 반환합니다.
        QWidget.window()는 위젯 트리 최상단 QMainWindow를 반환하므로
        별도의 부모 순회 없이 안전하게 참조할 수 있습니다.
        log_manager가 아직 준비되지 않은 경우 None을 반환합니다.
        """
        return getattr(self.window(), 'log_manager', None)

    def _log_auth(self, level: str, message: str) -> None:
        """log_manager에 인증 관련 로그를 기록합니다."""
        lm = self._get_log_manager()
        if lm is not None:
            lm.append_log(level, message)

    def _add_cred_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("자격증명 추가")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(10)
        vl.addWidget(parts.make_label("자격증명 추가", TEXT_PRIMARY, 13, True))
        vl.addWidget(Divider())

        name_row = QHBoxLayout()
        name_row.addWidget(parts.make_label("이름", TEXT_SECONDARY, 12))
        name_inp = QLineEdit()
        name_inp.setPlaceholderText("예: Naver API")
        name_row.addWidget(name_inp, 1)
        vl.addLayout(name_row)

        type_row = QHBoxLayout()
        type_row.addWidget(parts.make_label("타입", TEXT_SECONDARY, 12))
        type_cb = QComboBox()
        type_cb.addItems(["API Key", "Cookie", "OAuth2", "Basic Auth", "Bearer Token"])
        type_row.addWidget(type_cb, 1)
        vl.addLayout(type_row)

        key_row = QHBoxLayout()
        key_row.addWidget(parts.make_label("키/값", TEXT_SECONDARY, 12))
        key_inp = QLineEdit()
        key_inp.setPlaceholderText("인증 키 또는 토큰")
        key_inp.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(key_inp, 1)
        vl.addLayout(key_row)

        exp_row = QHBoxLayout()
        exp_row.addWidget(parts.make_label("만료일", TEXT_SECONDARY, 12))
        exp_inp = QLineEdit()
        exp_inp.setPlaceholderText("YYYY-MM-DD 또는 상시")
        exp_row.addWidget(exp_inp, 1)
        vl.addLayout(exp_row)

        btn_row = QHBoxLayout()
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.close)
        ok_btn = parts.action_btn("저장")

        def _do_add():
            masked = key_inp.text()[:4] + "****" if key_inp.text() else "****"
            data   = {
                "name":    name_inp.text().strip() or "새 자격증명",
                "type":    type_cb.currentText(),
                "key":     masked,
                "expires": exp_inp.text().strip() or "상시",
                "status":  "유효",
            }
            self._auth_rows.append(data)
            self._insert_table_row(data)
            self._log_auth("ok", f"자격증명 추가됨: {data['name']} ({data['type']})")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        vl.addLayout(btn_row)
        dlg.adjustSize()
        dlg.exec()

    def _delete_cred_row(self, row_idx):
        if 0 <= row_idx < self._cred_table.rowCount():
            name_item = self._cred_table.item(row_idx, 0)
            name_txt  = name_item.text() if name_item else "?"
            self._cred_table.removeRow(row_idx)
            self._log_auth("warn", f"자격증명 삭제됨: {name_txt}")

    def _export_creds(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "자격증명 내보내기", "credentials_encrypted.json", "JSON (*.json)")
        if not path:
            return
        export_data = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note":        "실제 배포 시 AES-256 암호화 적용 필요",
            "credentials": [{"name": r["name"], "type": r["type"], "expires": r["expires"]}
                            for r in self._auth_rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        self._log_auth("ok", f"자격증명 내보내기 완료: {path}")
        QMessageBox.information(self, "완료", f"내보내기 완료:\n{path}")

    def _on_tls_toggle(self, state):
        if state == Qt.CheckState.Checked.value:
            self._cert_lbl.setText("● TLS 검증 활성화")
            self._cert_lbl.setStyleSheet(f"color:{GREEN}; font-size:12px;")
            self._log_auth("ok", "TLS 인증서 검증 활성화됨")
        else:
            self._cert_lbl.setText("● TLS 검증 비활성화")
            self._cert_lbl.setStyleSheet(f"color:{AMBER}; font-size:12px;")
            self._log_auth("warn", "TLS 인증서 검증 비활성화됨 — 보안 주의")


# ══════════════════════════════════════════════════════
#  TrayManager Mixin
# ══════════════════════════════════════════════════════
class TrayManagerTriggers:
    """TrayManager의 트레이 이벤트 메서드"""

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def restore_window(self):
        if self.main_window.isMinimized() or not self.main_window.isVisible():
            self.main_window.showNormal()
            self.main_window.show()
        self.main_window.activateWindow()
        self.main_window.raise_()


# ══════════════════════════════════════════════════════
#  MainWindow Mixin
# ══════════════════════════════════════════════════════
class MainWindowTriggers:
    """MainWindow의 페이지 전환·워커·종료 메서드"""

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 3:
            self.stats_page.reload()

    def _reset_all_pages(self):
        self.dashboard._reset_dashboard()
        self.monitor_page._reset_monitor_page()

    def _start_crawl(self, cfg: dict):
        self._launch_worker(cfg, job_name=cfg.get("job", "수동 실행"))

    def _start_crawl_from_schedule(self, cfg: dict):
        # schedule 키는 워커에 전달할 필요가 없으므로 제거 후 대기 큐 경유
        cfg = dict(cfg)   # 원본 dict 보호 (호출자의 sched_task 변형 방지)
        cfg.pop("schedule", None)
        cfg.setdefault("job", "스케줄 실행")

        if self._worker and self._worker.isRunning():
            # ── 실행 중인 작업이 있으면 대기 큐에 추가 ──
            self._pending_queue.append(cfg)
            queue_pos = len(self._pending_queue)
            self.log_manager.append_log(
                "info",
                f"[스케줄] '{cfg.get('task_nm', cfg['job'])}' 대기 등록 "
                f"(대기 순번: {queue_pos}번)"
            )
            return

        # 수동 실행과 동일하게 대시보드·모니터링 페이지 리셋 후 실행
        self.dashboard._reset_dashboard()
        self.monitor_page._reset_monitor_page()
        self._launch_worker(cfg, job_name=cfg["job"])
        self.stack.setCurrentIndex(0)
        for i, btn in enumerate(self.sidebar._btns):
            btn.setChecked(i == 0)

    def _launch_worker(self, cfg: dict, job_name="실행"):
        # 수동 실행 경로는 기존과 동일하게 기존 워커를 중단하고 교체
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1500)

        self._worker = MultiprocessWorker(cfg, job_name)
        self._worker.new_row.connect(self.dashboard.add_row)
        self._worker.new_row.connect(self.monitor_page._add_realtime_row)
        self._worker.progress.connect(self.update_progress)
        self._worker.stats_update.connect(self.dashboard.update_stats)
        self._worker.log_message.connect(self.log_manager.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self.reset_progress()
        self.global_toolbar.set_running(True)
        self.dashboard._update_step_ui(2)

    def _consume_pending_queue(self):
        """
        대기 큐에서 다음 스케줄 작업을 꺼내 실행합니다.
        큐가 비어 있으면 아무것도 하지 않습니다.
        _on_finished() 말미에서만 호출됩니다.
        """
        if not self._pending_queue:
            return
        next_cfg = self._pending_queue.pop(0)
        remaining = len(self._pending_queue)
        self.log_manager.append_log(
            "info",
            f"[스케줄] '{next_cfg.get('task_nm', next_cfg.get('job', ''))}' 대기 큐에서 실행 "
            f"(남은 대기: {remaining}건)"
        )

        self.dashboard._reset_dashboard()
        self.monitor_page._reset_monitor_page()

        self._launch_worker(next_cfg, job_name=next_cfg.get("job", "스케줄 실행"))
        self.stack.setCurrentIndex(0)
        for i, btn in enumerate(self.sidebar._btns):
            btn.setChecked(i == 0)

    def _stop_crawl(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

        store.clear_rows()

        # 수동 중지 시 대기 큐도 함께 비워 후속 스케줄이 자동 실행되지 않도록 함
        if self._pending_queue:
            cleared = len(self._pending_queue)
            self._pending_queue.clear()
            self.log_manager.append_log(
                "warn",
                f"수동 중지 — 대기 중인 스케줄 {cleared}건 취소됨"
            )
        self.dashboard.set_running(False)

    def _on_finished(self, task: dict, summary: dict):
        # 중지 직후 곧바로 재시작하면, 교체되기 전 워커의 finished 신호가
        # 새 워커 시작 이후에 뒤늦게 도착할 수 있음(QThread.wait()가 메인
        # 스레드 이벤트 루프를 막는 동안 큐잉되었다가 처리됨). 그 경우
        # 실제로 실행 중인 현재 워커의 상태를 건드리면 안 되므로 무시.
        if self.sender() is not self._worker:
            return

        self.global_toolbar.set_running(False)
        self.reset_progress()
        self.dashboard.set_running(False)

        if summary.get("interrupted"):
            row_count = self.monitor_page.result_table.rowCount()
            self.log_manager.append_log(
                "warn",
                f"수집 중단 (Collection Interrupted) — {row_count}건 수집 후 중지 "
                f"(소요: {summary['elapsed']}s)"
            )
            self.dashboard._update_step_ui(0)
            # 중단은 _stop_crawl()에서 큐를 이미 비웠으므로 큐 소비 불필요
            return

        if summary.get("total", 0) == 0:
            url_count = summary.get("url_count", 0)
            skipped   = summary.get("skipped", 0)
            elapsed   = summary.get("elapsed", 0)
            self.log_manager.append_log(
                "err",
                f"크롤링 완료 — 수집된 데이터가 없습니다 "
                f"(생성 URL {url_count}개 · URL 불일치 skip {skipped}건 · 소요 {elapsed}s)"
            )
            self.dashboard._update_step_ui(0)
            msg = QMessageBox(self)
            msg.setWindowTitle("수집 결과 없음")
            msg.setText("수집이 완료되었으나 데이터가 없습니다.\n"
                        f"생성된 URL: {url_count}개 · URL 불일치 skip: {skipped}건 · 소요 시간: {elapsed}s\n"
                        "URL 또는 수집 설정을 확인하고 다시 시도해 주세요.")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
                QPushButton {{
                    background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px;
                }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """)
            msg.exec()
            if task.get("job") == "수동 실행":
                self.stack.setCurrentIndex(1)
                for i, btn in enumerate(self.sidebar._btns):
                    btn.setChecked(i == 1)
                self.monitor_page.tab_widget.setCurrentIndex(0)
            # 결과 없어도 대기 큐 소비는 계속 진행
            self._consume_pending_queue()
            return

        self.log_manager.append_log("info", "크롤링 완료")

        # step(3) — 정제 단계 표시
        self.dashboard._update_step_ui(3)
        QApplication.processEvents()

        self.monitor_page.preprocess(task)
        self.stats_page.reload()

        # step(4) — 결과물 추출 단계 표시
        self.dashboard._update_step_ui(4)

        is_unattended = task.get("job") == "스케줄 실행"
        try:
            extract_cfg = task.get("extract", {})
            if extract_cfg.get("auto_save"):
                auto_save_source = extract_cfg.get("auto_save_source", "raw")
                if auto_save_source == "refined" and is_unattended:
                    # 무인 실행 — 화면 체크박스 상태가 아닌 스케줄별 설정(없으면
                    # SCHEDULED_REFINE_RULES 폴백, §"새 스케줄 등록"의 "⚙ 정제
                    # 규칙 설정" 참고)을 적용, 결과 테이블/탭 전환 등 화면 갱신도 건너뜀
                    sched_refine_rules = extract_cfg.get("refine_rules", SCHEDULED_REFINE_RULES)
                    sched_fill_value   = extract_cfg.get("fill_null_value", "")
                    self.monitor_page._run_refine(
                        rules_override=sched_refine_rules, skip_ui_update=True,
                        fill_value_override=sched_fill_value,
                    )
                self.monitor_page._extract_result_table(source=auto_save_source, silent=is_unattended)
        except Exception as e:
            self.log_manager.append_log("err", f"자동 저장 실패: {e}")

        self.dashboard._update_step_ui(0)

        job_name = task.get("task_nm")
        if job_name:
            self.schedule_page.mark_done(job_name)

        if task.get("job") == "수동 실행":
            self.stack.setCurrentIndex(1)
            for i, btn in enumerate(self.sidebar._btns):
                btn.setChecked(i == 1)
            self.monitor_page.tab_widget.setCurrentIndex(0)

        # ── 정상 완료 후 대기 큐 소비 ──
        self._consume_pending_queue()

    def closeEvent(self, event):
        if self.tray_manager.tray_icon.isVisible():
            self.hide()
            self.tray_manager.show_message("알림", "프로그램이 트레이에서 실행 중입니다.")
            event.ignore()
        else:
            event.accept()

    def exit_app(self):
        self._pending_queue.clear()   # 종료 시 대기 큐 비워 후속 실행 방지
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1500)
        self.tray_manager.tray_icon.hide()
        QApplication.instance().quit()

    def update_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total else 0
        self.dashboard.prog_bar.setValue(pct)
        self.dashboard.prog_pct.setText(f"{pct}%")
        self.dashboard.prog_lbl.setText(f"진행률 · {done} / {total}")

    def reset_progress(self):
        self.dashboard.prog_bar.setValue(0)
        self.dashboard.prog_pct.setText("0%")
        self.dashboard.prog_lbl.setText("대기 중")

    # ── 하단 상태바 슬롯 ─────────────────────────────
    _STATUS_COLORS = {
        "ok":   GREEN,
        "err":  RED,
        "warn": AMBER,
        "info": ACCENT_LIGHT,
    }

    def _update_status_bar(self, level: str, message: str):
        """last_log 시그널 수신 — 하단 상태바에 최신 로그 한 줄 표시"""
        color = self._STATUS_COLORS.get(level, TEXT_SECONDARY)
        tag   = f"[{level.upper():4s}]"
        self.status_level.setText(tag)
        self.status_level.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:bold;"
        )
        self.status_msg.setText(message)
        self.status_msg.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")

    # ── 전체 로그 다이얼로그 ─────────────────────────
    def _open_log_viewer(self):
        """상태바 버튼 클릭 — 이미 열려 있으면 앞으로 가져오고, 없으면 표시"""
        if self.log_manager.isVisible():
            self.log_manager.raise_()
            self.log_manager.activateWindow()
            return
        # 열릴 때 기존 이력을 뷰어에 일괄 렌더링 후 표시
        self.log_manager._viewer.clear()
        self.log_manager._load_history()
        self.log_manager.show()
