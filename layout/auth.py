# layout/auth.py
# 인증 관리 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout,
    QCheckBox, QLineEdit, QLabel, QPushButton, QTableWidgetItem,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from trigger import AuthManagerPageTriggers
from style import Divider
from .common import (
    parts, build_scroll_body, make_header_table,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BG_HOVER,
    ACCENT, ACCENT_HOVER, GREEN, AMBER, RED, BLUE, PURPLE,
)


class AuthManagerPage(QWidget, AuthManagerPageTriggers):
    def __init__(self, auth_method=None, login_info=None):
        super().__init__()
        self._auth_method = auth_method
        self._login_info = login_info or {}
        self._auth_rows = []
        self._build()

    def _build(self):

        bl = build_scroll_body(self)

        # ── 전역 인증 옵션 (탭 위 고정) ─────────────────
        global_w, global_l = parts.card_widget("전역 인증 옵션")
        global_w.setStyleSheet(
            global_w.styleSheet() + "border-radius:0px; border-left:none; border-right:none; border-top:none;")
        row0 = QHBoxLayout()
        row0.setSpacing(16)
        self._tls_cb = QCheckBox("TLS/SSL 인증서 검증")
        self._tls_cb.setChecked(False)
        self._tls_cb.stateChanged.connect(self._on_tls_toggle)
        row0.addWidget(self._tls_cb)
        self._store_cb = QCheckBox("인증 정보 암호화 저장")
        self._store_cb.setChecked(False)
        row0.addWidget(self._store_cb)
        self._rotate_cb = QCheckBox("세션 자동 갱신")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        row0.addStretch()
        self._cert_lbl = parts.make_label("● TLS 검증 활성화", GREEN, 12)
        row0.addWidget(self._cert_lbl)
        global_l.addLayout(row0)
        bl.addWidget(global_w)

        if self._auth_method == "api_key":
            # ── 인증 자격증명 목록 ──────────────────────────
            cw, cl = parts.card_widget("자격증명 목록")
            hdr_row = QHBoxLayout()
            hdr_row.addStretch()
            self._add_cred_btn = parts.action_btn("+ 자격증명 추가", ACCENT, ACCENT_HOVER)
            self._add_cred_btn.clicked.connect(self._add_cred_dialog)
            self._export_btn = parts.outline_btn("내보내기 (암호화)")
            self._export_btn.clicked.connect(self._export_creds)
            hdr_row.addWidget(self._export_btn)
            hdr_row.addWidget(self._add_cred_btn)
            cl.addLayout(hdr_row)

            self._cred_table = self._make_cred_table()
            cl.addWidget(self._cred_table)
            bl.addWidget(cw)

        if self._auth_method == "login":
            # ── 로그인 대상 설정 카드 ────────────────────────
            lc_w, lc_l = parts.card_widget("로그인 대상 설정")

            def _field(label, widget, layout):
                row = QHBoxLayout()
                row.setSpacing(10)
                lbl = parts.make_label(label, TEXT_SECONDARY, 12)
                lbl.setFixedWidth(90)
                row.addWidget(lbl)
                row.addWidget(widget, 1)
                layout.addLayout(row)

            self._login_url = QLineEdit()
            self._login_url.setPlaceholderText("https://example.com/login")
            self._login_url.setToolTip("로그인 폼이 있는 페이지 URL")
            self._login_url.setText(self._login_info.get("loginUrl") or "")
            self._login_url.setCursorPosition(0)

            self._login_id = QLineEdit()
            self._login_id.setPlaceholderText("아이디 / 이메일")
            self._login_id.setText(self._login_info.get("id") or "")

            self._login_pw = QLineEdit()
            self._login_pw.setPlaceholderText("비밀번호")
            self._login_pw.setEchoMode(QLineEdit.EchoMode.Password)
            self._login_pw.setText(self._login_info.get("password") or "")

            self._login_selector = QLineEdit()
            # 좁은 화면(다중 레이아웃 "⚙" 다이얼로그)에서도 잘리지 않도록 예시만
            # 짧게 두고, 부가 설명("비워두면 자동 탐지")은 툴팁으로 옮겼다.
            self._login_selector.setPlaceholderText("예: #login-btn")
            self._login_selector.setToolTip("로그인 버튼 CSS 셀렉터 (선택사항 — 비워두면 자동 탐지)")

            self._login_success_kw = QLineEdit()
            self._login_success_kw.setPlaceholderText("예: 마이페이지, dashboard")
            self._login_success_kw.setToolTip("로그인 성공 판별 키워드 — 로그인 후 응답 페이지에서 이 텍스트를 찾습니다")

            _field("사이트 URL", self._login_url, lc_l)
            _field("아이디", self._login_id, lc_l)
            _field("비밀번호", self._login_pw, lc_l)

            lc_l.addWidget(Divider())
            _field("로그인 셀렉터", self._login_selector, lc_l)
            _field("성공 판별 키워드", self._login_success_kw, lc_l)
            bl.addWidget(lc_w)

        bl.addStretch(1)

    # ══════════════════════════════════════════════
    #  Login Info — 액션 메서드
    # ══════════════════════════════════════════════


    def _make_cred_table(self):
        headers = ["이름", "타입", "키 (마스킹)", "만료일", "상태", "액션"]
        return make_header_table(self, headers)

    def _insert_table_row(self, data: dict):

        r = self._cred_table.rowCount()
        self._cred_table.insertRow(r)
        self._cred_table.setRowHeight(r, 36)

        type_colors = {"API Key": BLUE, "Cookie": AMBER, "OAuth2": PURPLE, "Basic Auth": GREEN, "Bearer Token": RED}
        st_colors = {"유효": GREEN, "만료임박": AMBER, "만료": RED}

        vals_colors = [
            (data["name"], TEXT_PRIMARY),
            (data["type"], type_colors.get(data["type"], TEXT_SECONDARY)),
            (data["key"], TEXT_MUTED),
            (data["expires"], TEXT_SECONDARY),
        ]
        for col, (val, color) in enumerate(vals_colors):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._cred_table.setItem(r, col, item)

        # 상태 칩
        sc = st_colors.get(data["status"], TEXT_MUTED)
        bg_map = {"유효": "#052e16", "만료임박": "#451a03", "만료": "#450a0a"}
        bg = bg_map.get(data["status"], BG_HOVER)
        status_lbl = QLabel(data["status"])
        status_lbl.setStyleSheet(f"color:{sc}; background:{bg}; border-radius:10px; padding:2px 10px; font-size:11px;")
        sw3 = QWidget()
        sl3 = QHBoxLayout(sw3)
        sl3.setContentsMargins(4, 0, 4, 0)
        sl3.addWidget(status_lbl)
        self._cred_table.setCellWidget(r, 4, sw3)

        # 삭제 버튼
        del_btn = QPushButton("삭제")
        del_btn.setFixedHeight(28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};border:1px solid {RED};
            border-radius:4px;padding:0 8px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        del_btn.clicked.connect(lambda _, ri=r: self._delete_cred_row(ri))
        dw = QWidget()
        dl = QHBoxLayout(dw)
        dl.setContentsMargins(4, 2, 4, 2)
        dl.addWidget(del_btn)
        self._cred_table.setCellWidget(r, 5, dw)
