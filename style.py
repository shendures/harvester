from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout,
    QLabel, QPushButton, QTableWidget,
    QFrame,
    QHeaderView
)

from PyQt6.QtCore import ( Qt, QTimer )
from PyQt6.QtGui import ( QColor, QPalette, QFontMetrics )


# ══════════════════════════════════════════════════════
#  THEME
# ══════════════════════════════════════════════════════
class THEME:
    def __init__(self):
        self.BG_PRIMARY = "#0f1117"
        self.BG_SECONDARY = "#161820"
        self.BG_HOVER = "#1e2030"
        self.ACCENT = "#4f46e5"
        self.ACCENT_LIGHT = "#818cf8"
        self.ACCENT_HOVER = "#4338ca"
        self.TEXT_PRIMARY = "#e5e7eb"
        self.TEXT_SECONDARY = "#9ca3af"
        self.TEXT_MUTED = "#6b7280"
        self.BORDER = "#2a2d3a"
        self.BORDER_LIGHT = "#374151"
        self.GREEN = "#10b981"
        self.AMBER = "#fbbf24"
        self.RED = "#f87171"
        self.BLUE = "#60a5fa"
        self.PURPLE = "#a78bfa"

    @property
    def GLOBAL_QSS(self) -> str:
        return f"""
        QMainWindow, QWidget {{
            background-color: {self.BG_PRIMARY};
            color: {self.TEXT_PRIMARY};
            font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
            font-size: 13px;
        }}
        QScrollBar:vertical {{
            background: {self.BG_SECONDARY}; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: {self.BORDER_LIGHT}; border-radius: 3px; min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: {self.BG_SECONDARY}; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: {self.BORDER_LIGHT}; border-radius: 3px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QToolTip {{
            background-color: {self.BG_SECONDARY}; color: {self.TEXT_PRIMARY};
            border: 1px solid {self.BORDER}; padding: 4px 8px;
            border-radius: 4px; font-size: 12px;
        }}
        QHeaderView::section {{
            background: {self.BG_PRIMARY}; color: {self.TEXT_MUTED};
            border: none; border-bottom: 1px solid {self.BORDER};
            padding: 6px 10px; font-size: 10px; letter-spacing: 1px;
        }}
        QTableWidget {{
            background: {self.BG_PRIMARY}; color: {self.TEXT_PRIMARY};
            border: none; gridline-color: {self.BG_HOVER}; font-size: 12px;
        }}
        QTableWidget::item {{ padding: 6px 10px; }}
        QTableWidget::item:selected {{
            background: {self.BG_HOVER}; color: {self.TEXT_PRIMARY};
        }}
        QComboBox {{
            background: {self.BG_PRIMARY}; color: {self.TEXT_PRIMARY};
            border: 1px solid {self.BORDER_LIGHT}; border-radius: 4px;
            padding: 4px 8px; font-size: 12px;
        }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background: {self.BG_SECONDARY}; color: {self.TEXT_PRIMARY};
            border: 1px solid {self.BORDER}; selection-background-color: {self.BG_HOVER};
        }}
        QLineEdit {{
            background: {self.BG_PRIMARY}; color: {self.TEXT_PRIMARY};
            border: 1px solid {self.BORDER_LIGHT}; border-radius: 6px;
            padding: 6px 10px; font-size: 12px;
        }}
        QLineEdit:focus {{ border-color: {self.ACCENT}; }}
        QSpinBox, QDoubleSpinBox, QTimeEdit {{
            background: {self.BG_PRIMARY}; color: {self.TEXT_PRIMARY};
            border: 1px solid {self.BORDER_LIGHT}; border-radius: 4px;
            padding: 3px 6px; font-size: 12px;
        }}
        QCheckBox {{ color: {self.TEXT_SECONDARY}; spacing: 6px; }}
        QCheckBox::indicator {{
            width: 14px; height: 14px; border-radius: 3px;
            border: 1px solid {self.BORDER_LIGHT}; background: {self.BG_PRIMARY};
        }}
        QCheckBox::indicator:checked {{
            background: {self.ACCENT}; border-color: {self.ACCENT};
        }}
        """

    @property
    def CB_STYLE(self):
        return f"""
                QComboBox {{
                    background:{self.BG_PRIMARY}; color:{self.TEXT_PRIMARY};
                    border:1px solid {self.BORDER_LIGHT}; border-radius:4px;
                    padding:4px 8px; font-size:12px;
                }}
                QComboBox::drop-down {{ border:none; width:18px; }}
                QComboBox QAbstractItemView {{
                    background:{self.BG_SECONDARY}; color:{self.TEXT_PRIMARY};
                    border:1px solid {self.BORDER}; selection-background-color:{self.BG_HOVER};
                }}
            """

    # ── SessionSettingsPage 전용 QSS 프로퍼티 ────────────
    @property
    def PROXY_CARD_ENABLED_QSS(self) -> str:
        """프록시 카드 — 활성 상태 스타일 (기본 카드 외형)"""
        return f"""
            QWidget {{
                background: {self.BG_SECONDARY};
                border: 1px solid {self.BORDER};
                border-radius: 8px;
            }}
        """

    @property
    def PROXY_CARD_DISABLED_QSS(self) -> str:
        """
        프록시 카드 — 비활성 상태 스타일.
        전역 프록시 사용 체크박스가 꺼졌을 때 카드 내 모든 위젯을
        흐린 색상으로 일괄 전환합니다.
        인라인 setStyleSheet()가 GLOBAL_QSS :disabled 규칙을 덮어쓰는 문제를
        카드 컨테이너 단위 QSS 주입으로 해결합니다.
        """
        return f"""
            QWidget {{
                background: {self.BG_PRIMARY};
                border: 1px solid {self.BORDER};
                border-radius: 8px;
                color: {self.TEXT_MUTED};
            }}
            QCheckBox {{
                color: {self.TEXT_MUTED};
            }}
            QCheckBox::indicator {{
                background: {self.BG_HOVER};
                border: 1px solid {self.BORDER};
                border-radius: 3px;
                width: 14px; height: 14px;
            }}
            QCheckBox::indicator:checked {{
                background: {self.BORDER};
                border-color: {self.BORDER};
            }}
            QLabel {{
                color: {self.TEXT_MUTED};
                background: transparent;
                border: none;
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {self.BG_HOVER};
                color: {self.TEXT_MUTED};
                border: 1px solid {self.BORDER};
                border-radius: 4px;
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background: {self.BG_HOVER};
                border: none;
            }}
            QPushButton {{
                background: {self.BG_HOVER};
                color: {self.TEXT_MUTED};
                border: 1px solid {self.BORDER};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: normal;
            }}
            QTableWidget {{
                background: {self.BG_PRIMARY};
                color: {self.TEXT_MUTED};
                border: none;
                gridline-color: {self.BG_HOVER};
            }}
            QTableWidget::item {{
                color: {self.TEXT_MUTED};
                padding: 6px 10px;
            }}
            QHeaderView::section {{
                background: {self.BG_PRIMARY};
                color: {self.BORDER_LIGHT};
                border: none;
                border-bottom: 1px solid {self.BORDER};
                padding: 6px 10px;
                font-size: 10px;
            }}
        """

    @property
    def PROXY_TABLE_INDICATOR_QSS(self) -> str:
        """
        프록시 테이블 — QTableWidget::indicator 체크박스 스타일.
        setCellWidget(QCheckBox) 없이 기존 체크박스 외형을 재현합니다.
        EqualSpacingTable의 기존 QSS에 추가(t.styleSheet() +)하여 적용합니다.
        """
        return f"""
            QTableWidget::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid {self.BORDER};
                background: {self.BG_HOVER};
            }}
            QTableWidget::indicator:unchecked {{
                background: {self.BG_HOVER};
                border: 1px solid {self.BORDER};
            }}
            QTableWidget::indicator:checked {{
                background: {self.ACCENT};
                border: 1px solid {self.ACCENT};
                image: none;
            }}
        """

    @property
    def PROXY_CONTEXT_MENU_QSS(self) -> str:
        """프록시 테이블 — 우클릭 컨텍스트 메뉴 스타일"""
        return f"""
            QMenu {{
                background:{self.BG_SECONDARY}; color:{self.TEXT_PRIMARY};
                border:1px solid {self.BORDER}; border-radius:6px; padding:4px;
            }}
            QMenu::item {{ padding:6px 20px; font-size:12px; }}
            QMenu::item:selected {{ background:{self.BG_HOVER}; color:{self.ACCENT_LIGHT}; }}
        """

    def set_pallete(self, app):
        app.setStyleSheet(self.GLOBAL_QSS)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.BG_PRIMARY))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Base, QColor(self.BG_SECONDARY))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(self.BG_HOVER))
        palette.setColor(QPalette.ColorRole.Text, QColor(self.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Button, QColor(self.BG_SECONDARY))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(self.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(self.ACCENT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)


class NavItem(QPushButton):
    def __init__(self, icon_char, label):
        super().__init__()
        self.theme = THEME()
        self.setText(f"  {icon_char}   {label}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{self.theme.TEXT_SECONDARY};
                text-align:left; padding-left:12px;
                border:none; border-left:2px solid transparent; font-size:13px;
            }}
            QPushButton:hover {{ background:{self.theme.BG_HOVER}; color:{self.theme.TEXT_PRIMARY}; }}
            QPushButton:checked {{
                background:{self.theme.BG_HOVER}; color:{self.theme.ACCENT_LIGHT};
                border-left:2px solid {self.theme.ACCENT_LIGHT};
            }}
        """)

class TagButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.theme = THEME()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background:#1a1040; color:#a78bfa;
                border:1px solid #312e81; border-radius:4px;
                padding:3px 10px; font-size:11px;
            }}
            QPushButton:hover {{ background:#312e81; }}
            QPushButton:checked {{ background:{self.theme.ACCENT}; color:white; border-color:{self.theme.ACCENT}; }}
        """)


class StatCard(QWidget):
    theme = THEME()
    def __init__(self, label, value, color=theme.TEXT_PRIMARY):
        super().__init__()
        self.setStyleSheet(f"background:{self.theme.BG_PRIMARY}; border-radius:6px; border:1px solid {self.theme.BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"color:{color}; font-size:20px; font-weight:bold; border:none; background:transparent;")
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f"color:{self.theme.TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)

    def update_value(self, v):
        self._val.setText(str(v))


# class StatCard(QWidget):
#     def __init__(self, label, value, color=TEXT_PRIMARY):
#         super().__init__()
#         self.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
#         lay = QVBoxLayout(self)
#         lay.setContentsMargins(10, 8, 10, 8)
#         lay.setSpacing(2)
#         self._val = QLabel(value)
#         self._val.setStyleSheet(
#             f"color:{color}; font-size:20px; font-weight:bold; border:none; background:transparent;")
#         self._lbl = QLabel(label)
#         self._lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
#         lay.addWidget(self._val)
#         lay.addWidget(self._lbl)
#
#     def update_value(self, v):
#         self._val.setText(str(v))


# ──────────────────────────────────────────────────────
#  EqualSpacingTable
#  — Initial Equal distribution · Free resize + H-scroll · Double-click auto-fit
# ──────────────────────────────────────────────────────
class EqualSpacingTable(QTableWidget):
    """
    초기 Equal 분배 + 자유 리사이즈 + 가로 스크롤 테이블

    ─────────────────────────────────────────────────────
    동작 원칙
    ─────────
    • 초기(컬럼 수 확정 / 창 최초 표시): viewport 너비를 균등 분배
    • 컬럼 드래그: 해당 컬럼 너비만 변경, 나머지 컬럼은 Fixed 유지
      → 전체 컬럼 합산이 viewport 초과 시 가로 스크롤바 자동 활성화
    • 창 리사이즈: 컬럼들이 이미 사용자 지정된 경우 그대로 유지
      (초기 equal 분배 상태인 경우에만 재분배)
    • 헤더 구분선 더블클릭: 해당 컬럼의 모든 셀 + 헤더 텍스트 중
      가장 긴 것에 맞춰 Auto-fit

    Public API
    ──────────
    set_column_spacing(px)   셀 좌우 padding 변경 (시각적 간격)
    set_hscroll_handle(px)   가로 스크롤바 핸들 최소 너비
    set_row_height(px)       모든 행 높이 변경
    reset_equal()            현재 viewport 기준으로 Equal 너비 재초기화
    fit_column(logical)      지정 컬럼 Auto-fit (더블클릭과 동일)
    """

    MIN_COL_W = 30  # 컬럼 최소 너비 (px)
    H_PADDING = 20  # auto-fit 시 텍스트 양쪽 여유 패딩 (px, 한쪽 10)

    def __init__(
            self,
            parent=None,
            row_height: int = 28,
            col_padding: int = 10,
            hscroll_handle: int = 24,
    ):
        super().__init__(parent)

        self._row_height = row_height
        self._col_padding = col_padding
        self._hscroll_handle = hscroll_handle

        # True: 아직 사용자가 드래그한 적 없음 → 창 리사이즈 시 재분배
        self._is_equal_state = True
        # sectionResized 재진입 방지
        self._resizing = False

        self.theme = THEME()

        self._init_table()
        self._apply_style()

    # ── 초기 설정 ─────────────────────────────────────
    def _init_table(self):
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.verticalHeader().setDefaultSectionSize(self._row_height)

        # 가로 스크롤바: 컬럼 합산이 viewport 초과 시 자동 표시
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(self.MIN_COL_W)

        # 드래그 리사이즈 — 해당 컬럼만 변경 (다른 컬럼 고정)
        hdr.sectionResized.connect(self._on_section_resized)

        # 헤더 구분선 더블클릭 → Auto-fit
        hdr.sectionHandleDoubleClicked.connect(self.fit_column)

    # ── viewport 총 너비 계산 ─────────────────────────
    def _viewport_total(self) -> int:
        vscroll = self.verticalScrollBar()
        sb_w = vscroll.width() if vscroll.isVisible() else 0
        return max(1, self.viewport().width() - sb_w)

    # ── Equal width 초기 분배 ─────────────────────────
    def _redistribute(self):
        """
        viewport 너비를 컬럼 수로 균등 분할합니다.
        나머지 픽셀은 마지막 컬럼에 흡수합니다.
        """
        n = self.columnCount()
        if n <= 0:
            return

        total = self._viewport_total()
        base_w = max(self.MIN_COL_W, total // n)
        rem = total - base_w * n

        self._resizing = True
        try:
            for c in range(n):
                self.setColumnWidth(c, base_w + (rem if c == n - 1 else 0))
        finally:
            self._resizing = False

        self._is_equal_state = True

    # ── 드래그 핸들러 — 해당 컬럼만 변경 ──────────────
    def _on_section_resized(self, logical: int, old_w: int, new_w: int):
        """
        드래그된 컬럼의 너비만 변경합니다.
        다른 컬럼은 Fixed 유지 → 전체 합산 증가 시 H-scrollbar 활성화.
        MIN_COL_W 미만으로는 줄일 수 없습니다.
        """
        if self._resizing:
            return

        # MIN_COL_W 클램프
        if new_w < self.MIN_COL_W:
            self._resizing = True
            try:
                self.setColumnWidth(logical, self.MIN_COL_W)
            finally:
                self._resizing = False

        # 사용자가 직접 조작 → equal 상태 해제 (창 리사이즈 시 재분배 안 함)
        self._is_equal_state = False

    # ── Auto-fit (더블클릭 / 공개 API) ────────────────
    def fit_column(self, logical: int):
        """
        지정 컬럼의 너비를 해당 컬럼 내 가장 긴 텍스트에 맞춥니다.

        측정 대상
        ─────────
        • 헤더 텍스트
        • 모든 행의 셀 텍스트 (QTableWidgetItem)
        • CellWidget이 있는 경우 위젯의 sizeHint().width()

        폰트
        ────
        • 헤더: horizontalHeader().font()
        • 셀:   self.font()
        """
        hdr = self.horizontalHeader()
        hdr_font = hdr.font()
        cell_font = self.font()

        hdr_fm = QFontMetrics(hdr_font)
        cell_fm = QFontMetrics(cell_font)

        # 헤더 텍스트 너비
        hdr_text = self.horizontalHeaderItem(logical)
        max_w = hdr_fm.horizontalAdvance(hdr_text.text() if hdr_text else "") + self.H_PADDING

        # 셀 텍스트 / 위젯 너비
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, logical)
            if widget:
                max_w = max(max_w, widget.sizeHint().width() + self.H_PADDING)
            else:
                item = self.item(row, logical)
                if item and item.text():
                    tw = cell_fm.horizontalAdvance(item.text()) + self._col_padding * 2 + self.H_PADDING
                    max_w = max(max_w, tw)

        target_w = max(self.MIN_COL_W, max_w)

        self._resizing = True
        try:
            self.setColumnWidth(logical, target_w)
        finally:
            self._resizing = False

        # auto-fit 도 사용자 조작으로 간주 → equal 상태 해제
        self._is_equal_state = False

    # ── Qt 이벤트 오버라이드 ──────────────────────────
    def resizeEvent(self, event):
        """
        창 크기 변경 시:
          - equal 상태이면 재분배 (초기 상태 유지)
          - 사용자가 이미 드래그한 경우 컬럼 너비 그대로 유지
        """
        super().resizeEvent(event)
        if self._is_equal_state and self.columnCount() > 0:
            self._redistribute()

    def setColumnCount(self, count: int):
        """컬럼 수 확정 직후 Equal 재분배 예약."""
        super().setColumnCount(count)
        if count > 0:
            self._is_equal_state = True
            QTimer.singleShot(0, self._redistribute)

    # ── StyleSheet ────────────────────────────────────
    def _apply_style(self):
        p = self._col_padding
        self.setShowGrid(False)
        self.setStyleSheet(f"""
            QTableWidget::item {{
                padding-left:  {p}px;
                padding-right: {p}px;
                border-right: 1px solid {self.theme.BORDER};
            }}
            QTableWidget::item:last-child {{
                border-right: none;
            }}
            QHeaderView::section {{
                background: {self.theme.BG_PRIMARY}; color: {self.theme.TEXT_MUTED};
                border: none;
                border-right: 1px solid {self.theme.BORDER};
                border-bottom: 1px solid {self.theme.BORDER};
                padding: 6px {p}px;
                font-size: 10px; letter-spacing: 1px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QScrollBar:vertical {{
                background: {self.theme.BG_SECONDARY}; width: 4px; border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.theme.BORDER_LIGHT}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {self.theme.BG_SECONDARY}; height: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: {self.theme.BORDER_LIGHT}; border-radius: 3px;
                min-width: {self._hscroll_handle}px;
                max-width: {self._hscroll_handle}px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

    # ── Public API ────────────────────────────────────
    def set_column_spacing(self, padding_px: int):
        """셀 좌우 padding 변경 (시각적 간격)."""
        self._col_padding = padding_px
        self._apply_style()

    def set_hscroll_handle(self, width_px: int):
        """가로 스크롤바 핸들 최소 너비 변경."""
        self._hscroll_handle = width_px
        self._apply_style()

    def set_row_height(self, height_px: int):
        """모든 행의 기본 높이 변경."""
        self._row_height = height_px
        self.verticalHeader().setDefaultSectionSize(height_px)
        for r in range(self.rowCount()):
            self.setRowHeight(r, height_px)

    def reset_equal(self):
        """현재 viewport 기준으로 Equal 너비를 재초기화합니다."""
        self._redistribute()


class Divider(QFrame):
    def __init__(self, orientation="h", parent=None):
        super().__init__(parent)
        self.theme = THEME()
        self.setFrameShape(QFrame.Shape.HLine if orientation == "h" else QFrame.Shape.VLine)
        self.setStyleSheet(f"color:{self.theme.BORDER}; background:{self.theme.BORDER};")
        if orientation == "h":
            self.setFixedHeight(1)
        else:
            self.setFixedWidth(1)

class Parts:
    def __init__(self):
        self.theme = THEME()

    def make_label(self, text, color=None, size=13, bold=False):
        # 버그 수정: 기본 컬러를 인스턴스 변수(self.theme)에서 참조하도록 변경
        if color is None:
            color = self.theme.TEXT_SECONDARY

        lbl = QLabel(text)
        lbl.setContentsMargins(0, 0, 5, 0)
        weight = "bold" if bold else "normal"
        lbl.setStyleSheet(f"""
            color: {color}; 
            font-size: {size}px; 
            font-weight: {weight}; 
            background: transparent; 
            border: none;
        """)
        return lbl


    def card_widget(self, title="", parent=None):
        """어두운 테두리 카드. (widget, inner_layout) 반환"""
        w = QWidget(parent)
        w.setStyleSheet(f"""
            QWidget {{
                background:{self.theme.BG_SECONDARY};
                border:1px solid {self.theme.BORDER};
                border-radius:8px;
            }}
        """)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        if title:
            lbl = self.make_label(title.upper(), self.theme.TEXT_MUTED, 10)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1px;")
            outer.addWidget(lbl)
            outer.addWidget(Divider())
        return w, outer

    def action_btn(self, text, color=None, hover=None, text_color="white", parent=None):
        """강조형 주요 액션 버튼 생성"""
        # 버그 수정: 기본 컬러를 인스턴스 변수에서 안전하게 바인딩
        if color is None:
            color = self.theme.ACCENT
        if hover is None:
            hover = self.theme.ACCENT_HOVER

        btn = QPushButton(text, parent)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color}; color: {text_color};
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:disabled {{
                background: {self.theme.BG_HOVER};
                color: {self.theme.TEXT_MUTED};
                border: 1px solid {self.theme.BORDER};
            }}
        """)
        return btn


    def outline_btn(self, text, parent=None):
        btn = QPushButton(text, parent)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{self.theme.TEXT_SECONDARY};
                border:1px solid {self.theme.BORDER_LIGHT}; border-radius:6px;
                padding:5px 12px; font-size:12px;
            }}
            QPushButton:hover {{ color:{self.theme.TEXT_PRIMARY}; border-color:{self.theme.TEXT_MUTED}; }}
            QPushButton:disabled {{
                background:{self.theme.BG_HOVER};
                color:{self.theme.TEXT_MUTED};
                border:1px solid {self.theme.BORDER};
            }}
        """)
        return btn