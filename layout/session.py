# layout/session.py
# 세션(프록시) 설정 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QCheckBox, QSpinBox, QTableWidgetItem,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from trigger import SessionSettingsPageTriggers
from style import EqualSpacingTable, NoFocusDelegate
from .common import theme, parts, TEXT_SECONDARY, TEXT_PRIMARY, ACCENT, ACCENT_HOVER, BLUE, PURPLE, AMBER


class SessionSettingsPage(QWidget, SessionSettingsPageTriggers):
    def __init__(self):
        super().__init__()
        self._proxy_rows = []  # list of dict
        self._proxy_test_thread = None  # "연결 테스트" 진행 중인 QThread(없으면 None)
        self._build()

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 스크롤 바디 ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 옵션 카드 ──────────────────────────────
        gw1, gl1 = parts.card_widget("세션 설정")
        row0 = QHBoxLayout()
        row0.setSpacing(16)

        self.ua_check = QCheckBox("UA 랜덤")
        self.ua_check.setToolTip("요청마다 User-Agent를 무작위로 변경")
        self.ua_check.setChecked(True)

        self.cookie_check = QCheckBox("Cookie 랜덤")
        self.cookie_check.setChecked(True)
        self.cookie_check.setToolTip("요청마다 Cookie 세션을 무작위로 순환")

        self._global_cb = QCheckBox("전역 프록시 사용")
        self._global_cb.setChecked(False)

        row0.addWidget(self.ua_check)
        row0.addWidget(self.cookie_check)
        row0.addWidget(self._global_cb)
        row0.addStretch()
        gl1.addLayout(row0)
        bl.addWidget(gw1)

        self.gw2, gl2 = parts.card_widget("프록시 옵션")
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(parts.make_label("분당 IP 허용 갯수", TEXT_SECONDARY, 12))
        self._allow_ip_cnts = QSpinBox()
        self._allow_ip_cnts.setRange(1, 15)
        self._allow_ip_cnts.setValue(10)
        row1.addWidget(self._allow_ip_cnts)
        row1.addSpacing(20)
        row1.addWidget(parts.make_label("MAX RETRY", TEXT_SECONDARY, 12))
        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(1, 20)
        self._retry_spin.setValue(3)
        row1.addWidget(self._retry_spin)
        row1.addStretch()
        gl2.addLayout(row1)
        bl.addWidget(self.gw2)

        # ── 프록시 목록 카드 ──────────────────────────────
        self.pw, pl = parts.card_widget("프록시 목록")
        # 테이블 헤더 행
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)
        hdr_row.addStretch()

        self._test_btn = parts.outline_btn("🔌 연결 테스트")
        self._test_btn.setToolTip("프록시 목록의 모든 IP에 연결을 시도해 상태를 확인합니다")
        self._test_btn.clicked.connect(self._test_all_proxies)
        self._import_btn = parts.outline_btn("📂 Import")
        self._import_btn.setToolTip("텍스트/CSV 파일에서 IP:PORT 형식의 프록시 목록을 불러옵니다")
        self._import_btn.clicked.connect(self._import_proxy_file)
        self._add_btn = parts.action_btn("+ 추가", ACCENT, ACCENT_HOVER)
        self._add_btn.clicked.connect(self._add_proxy_dialog)
        hdr_row.addWidget(self._test_btn)
        hdr_row.addWidget(self._import_btn)
        hdr_row.addWidget(self._add_btn)
        pl.addLayout(hdr_row)
        self._proxy_table = self._make_proxy_table()
        pl.addWidget(self._proxy_table)
        bl.addWidget(self.pw)

        # 연결 부분
        self._global_cb.toggled.connect(self._activate_proxy_option)
        self._activate_proxy_option(self._global_cb.isChecked())

    # ── 프록시 활성/비활성 시각 전환 ────────────────────
    def _set_card_visual(self, card: QWidget, enabled: bool) -> None:
        """
        카드 컨테이너의 테두리·배경·자식 위젯 색상을 enabled 상태에 맞게 전환합니다.
        QSS는 THEME.PROXY_CARD_ENABLED_QSS / PROXY_CARD_DISABLED_QSS 프로퍼티에서 관리합니다.
        """
        if enabled:
            card.setStyleSheet(theme.PROXY_CARD_ENABLED_QSS)
        else:
            card.setStyleSheet(theme.PROXY_CARD_DISABLED_QSS)

    def _make_proxy_table(self):
        headers = ["NO", "프로토콜", "호스트", "포트", "상태"]
        t = EqualSpacingTable(
            parent=self,
            row_height=36,
            col_padding=8,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._proxy_table_context_menu)
        # itemChanged: 체크박스 직접 클릭 시 상태 동기화
        t.itemChanged.connect(self._on_proxy_item_changed)
        # itemClicked: 행 어디를 클릭해도 활성/비활성 토글
        t.itemClicked.connect(self._on_proxy_row_clicked)
        t.setStyleSheet(t.styleSheet() + theme.PROXY_TABLE_INDICATOR_QSS)
        # "상태" 체크박스 컬럼은 체크박스만 보이도록 — 현재 셀이 되어도 포커스 사각형을 그리지 않음
        t.setItemDelegateForColumn(4, NoFocusDelegate(t))
        return t

    def _insert_table_row(self, data: dict):
        """
        QTableWidgetItem만 사용 — setCellWidget 완전 제거.
        체크박스·상태칩·삭제버튼을 텍스트 셀로 대체하여 대량 삽입 성능을 확보합니다.
        삭제는 우클릭 컨텍스트 메뉴(_proxy_table_context_menu)로 처리합니다.
        """
        t = self._proxy_table
        r = t.rowCount()
        t.insertRow(r)
        t.setRowHeight(r, 36)

        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        # col 0 — NO (테이블 내 순번, 1-base). _delete_row에서 삭제 시 재넘버링됨.
        no_item = QTableWidgetItem(str(r + 1))
        no_item.setForeground(QColor(TEXT_SECONDARY))
        no_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 0, no_item)

        # col 1 — 프로토콜
        color_map = {"HTTP": BLUE, "HTTPS": BLUE, "SOCKS5": PURPLE, "SOCKS4": AMBER}
        proto_item = QTableWidgetItem(data["protocol"])
        proto_item.setForeground(QColor(color_map.get(data["protocol"], TEXT_SECONDARY)))
        proto_item.setTextAlignment(align)
        proto_item.setFlags(proto_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 1, proto_item)

        # col 2 — 호스트
        host_item = QTableWidgetItem(data["host"])
        host_item.setForeground(QColor(TEXT_PRIMARY))
        host_item.setTextAlignment(align)
        host_item.setFlags(host_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 2, host_item)

        # col 3 — 포트
        port_item = QTableWidgetItem(data["port"])
        port_item.setForeground(QColor(TEXT_SECONDARY))
        port_item.setTextAlignment(align)
        port_item.setFlags(port_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 3, port_item)

        # col 4 — 상태 (사용 여부 체크박스. ItemIsUserCheckable — setCellWidget 없이 렌더링)
        status_item = QTableWidgetItem()
        status_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsUserCheckable   # 체크박스 렌더링 플래그
        )
        status_item.setCheckState(
            Qt.CheckState.Checked if data["enabled"] else Qt.CheckState.Unchecked
        )
        t.setItem(r, 4, status_item)
