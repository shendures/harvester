# trigger/log_viewer.py
# 전체 로그 확인 모달리스 다이얼로그(LogViewerDialog)와 그 검색창(SearchLineEdit).

from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextDocument, QTextCursor

from .common import (
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, ACCENT, ACCENT_LIGHT, ACCENT_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER, GREEN, AMBER, RED,
)


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
        외부(Worker, GlobalToolbarSingle 등)에서 호출 — 이력 버퍼에 누적하고
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
