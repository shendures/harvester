# layout/charts.py
# StatisticsPage 전용 미니 차트 위젯 (RankedBarChart/GroupedBarChart).

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from .common import BORDER, TEXT_MUTED, TEXT_SECONDARY, TEXT_PRIMARY, BG_PRIMARY


class RankedBarChart(QWidget):
    """segments = [(label, value, color)] — 값 내림차순 가로 막대 순위 리스트.
    값 옆에 전체 대비 비율을 괄호로 함께 표시한다."""

    # 라벨 열의 최소 폭 — 상태 코드(3자리) 기준값. 이보다 넓은 라벨은
    # paintEvent에서 실제 문자열 폭을 재서 열을 넓힌다.
    LABEL_COL_MIN_W = 46

    ROW_H = 26           # 행당 높이 — 라벨(15px)·막대가 여유 있게 보이는 기존 설계값
    MAX_ROWS = 7         # 상태 코드 기본 6종 + "기타" 한 행
    DEFAULT_HEIGHT = ROW_H * MAX_ROWS
    COUNT_COL_W = 92     # 값(비율) 열의 최소 폭 — 더 긴 값 문자열은 실측해서 넓힌다
    TRACK_H = 10         # 막대 두께
    MIN_TRACK_W = 60     # 막대 트랙이 알아볼 수 있는 최소 폭
    LABEL_GAP = 8        # 라벨 열과 트랙 사이 간격
    COUNT_GAP = 6        # 트랙과 값 열 사이 간격

    def __init__(self, segments=None, parent=None, *, keep_order=False):
        """높이를 DEFAULT_HEIGHT(최대 7행이 행당 26px로 보이는 값)로 고정한다 — 고정하는
        이유는 이 값보다 커지면(형제 카드가 더 커서 강제로 늘어나는 등) 카드 안에 빈 공백만
        남기 때문이다. 행 수가 늘면 행 높이가 DEFAULT_HEIGHT÷행 수로 줄어 12행(15.2px)이 글자
        높이(15px)의 한계라, 호출부가 행 수를 묶어 넘겨야 한다(상태 코드 분포는 "기타" 행으로
        최대 7행). keep_order=True면 값 내림차순 정렬 대신 넘겨준 순서를 그대로 쓴다 — 응답
        속도 구간처럼 순서 자체가 의미인 카드용."""
        super().__init__(parent)
        self.segments = segments or []
        self._keep_order = keep_order
        self.setFixedHeight(self.DEFAULT_HEIGHT)

    def set_data(self, segments):
        self.segments = segments
        self.updateGeometry()
        self.update()

    @staticmethod
    def _label_font() -> QFont:
        # 모듈 import 시점에는 QApplication이 없을 수 있어 사용할 때 만든다
        return QFont("Consolas", 10, QFont.Weight.Bold)

    @staticmethod
    def _count_font() -> QFont:
        return QFont("Consolas", 9)

    @staticmethod
    def _count_texts(rows) -> list:
        """행마다 "건수 (비율%)" 문자열 — 그리기와 폭 측정이 같은 문자열을 쓴다."""
        total = sum(v for _, v, _ in rows) or 1
        return [f"{val} ({val / total * 100:.1f}%)" for _, val, _ in rows]

    def _count_col_width(self, rows) -> int:
        """값 열 폭 — 건수가 커지면(예: 1,234건 이상) 고정 폭으로는 오른쪽이 잘리므로
        가장 긴 값 문자열을 실측해 기본 폭과 넓은 쪽을 쓴다."""
        count_fm = QFontMetrics(self._count_font())
        widest = max((count_fm.horizontalAdvance(t) for t in self._count_texts(rows)), default=0)
        return max(self.COUNT_COL_W, widest + self.COUNT_GAP)

    def _label_col_width(self, rows) -> int:
        """라벨 열 폭 — 한글 라벨("정상 수집" 등)은 3자리 상태 코드보다 넓어 고정 폭으로는
        잘리므로, 실제 문자열 폭을 재서 최소 폭과 넓은 쪽을 쓴다."""
        label_fm = QFontMetrics(self._label_font())
        return max(self.LABEL_COL_MIN_W,
                   max((label_fm.horizontalAdvance(str(lb)) for lb, _, _ in rows), default=0))

    def minimumSizeHint(self) -> QSize:
        """라벨·값 열이 겹치지 않고 막대가 보이는 최소 폭 — 카드가 이보다 좁아지지 않게 한다."""
        width = (self._label_col_width(self.segments) + self.LABEL_GAP
                 + self.MIN_TRACK_W + self._count_col_width(self.segments))
        return QSize(width, super().minimumSizeHint().height())

    def paintEvent(self, e):
        if not self.segments:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        rows = self.segments if self._keep_order else sorted(self.segments, key=lambda s: s[1], reverse=True)
        max_v = max(v for _, v, _ in rows) or 1
        n = len(rows)
        row_h = H / n
        label_font = self._label_font()
        label_w = self._label_col_width(rows)
        count_w, track_h = self._count_col_width(rows), self.TRACK_H
        count_texts = self._count_texts(rows)
        track_x0, track_x1 = label_w + self.LABEL_GAP, W - count_w

        for i, (label, val, color) in enumerate(rows):
            y = i * row_h
            cy = y + row_h / 2

            p.setPen(QColor(TEXT_PRIMARY))
            p.setFont(label_font)
            p.drawText(0, int(y), label_w, int(row_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(label))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BG_PRIMARY))
            p.drawRoundedRect(int(track_x0), int(cy - track_h / 2), int(track_x1 - track_x0), track_h, 3, 3)

            w = max((val / max_v) * (track_x1 - track_x0), 3)
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(track_x0), int(cy - track_h / 2), int(w), track_h, 3, 3)

            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(self._count_font())
            p.drawText(int(track_x1) + self.COUNT_GAP, int(y), count_w, int(row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, count_texts[i])

        p.end()


class GroupedBarChart(QWidget):
    """x_labels + datasets(=[(label, values, color), ...])를 카테고리별 그룹 막대로 그림"""

    VALUE_GAP = 4        # 막대 상단-값 라벨 사이 고정 간격(px)
    LEGEND_GAP = 10      # 범례 항목 사이 간격(px)
    PAD_X = 8            # 좌우 여백(px)
    LABEL_GAP = 4        # 이웃한 구간 라벨 사이 최소 간격(px)
    LABEL_FONT_PT = 7    # 구간 라벨 — 칸이 많아도 들어가도록 눈에 보일 정도로만 작게

    def __init__(self, x_labels=None, datasets=None, parent=None):
        super().__init__(parent)
        self.x_labels = x_labels or []
        self.datasets = datasets or []
        self.setMinimumHeight(170)

    def set_data(self, x_labels, datasets):
        self.x_labels = x_labels
        self.datasets = datasets
        self.update()

    def width_for_slots(self, slots: int, sample_label: str) -> int:
        """slots칸의 구간 라벨이 서로 겹치지 않고 들어가는 최소 폭 — 칸당 폭은
        sample_label의 실측 폭 + LABEL_GAP이라 글꼴·OS가 달라도 겹치지 않는다."""
        label_w = QFontMetrics(QFont("Consolas", self.LABEL_FONT_PT)).horizontalAdvance(sample_label)
        return 2 * self.PAD_X + slots * (label_w + self.LABEL_GAP)

    def paintEvent(self, e):
        if not self.datasets or not self.x_labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        value_font = QFont("Consolas", 7)
        value_fm = QFontMetrics(value_font)

        pad_l = pad_r = self.PAD_X
        pad_b = 20
        pad_t = 22 + self.VALUE_GAP + value_fm.height()  # 범례 여백 + 값 라벨 공간
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals, default=0) or 1

        self._draw_legend(p, pad_l)

        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pad_t + chart_h - int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)

        n = len(self.x_labels)
        n_series = len(self.datasets)
        group_w = chart_w / n
        bar_gap = 2
        bar_w = max(2.0, (group_w * 0.72 - bar_gap * (n_series - 1)) / n_series)
        group_pad = (group_w - (bar_w * n_series + bar_gap * (n_series - 1))) / 2

        for i in range(n):
            gx = pad_l + i * group_w + group_pad
            for s_idx, (_, vals, color) in enumerate(self.datasets):
                v = vals[i] if i < len(vals) else 0
                bh = (v / max_v) * chart_h
                x = gx + s_idx * (bar_w + bar_gap)
                y = pad_t + chart_h - bh
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                p.drawRoundedRect(int(x), int(y), int(bar_w), int(max(bh, 1.5)), 2, 2)

                # 값 라벨 — 막대 상단에서 VALUE_GAP만큼 띄운 자리에 계열 색상으로 표시.
                # 막대 슬롯보다 넓은 라벨은 옆 막대 라벨과 겹치므로 생략한다(칸이
                # 많은 월별 뷰의 네 자리 값에서만 발동).
                text = str(v)
                text_w = value_fm.horizontalAdvance(text)
                if text_w <= bar_w + bar_gap:
                    label_x = x + bar_w / 2 - text_w / 2
                    label_y = y - self.VALUE_GAP - value_fm.height()
                    p.setPen(QColor(color))
                    p.setFont(value_font)
                    p.drawText(int(label_x), int(label_y), text_w, value_fm.height(),
                               Qt.AlignmentFlag.AlignCenter, text)

            # 구간 라벨
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", self.LABEL_FONT_PT))
            p.drawText(int(pad_l + i * group_w), int(pad_t + chart_h + 4), int(group_w), 14,
                       Qt.AlignmentFlag.AlignCenter, str(self.x_labels[i]))

        p.setPen(QColor(BORDER))
        p.drawLine(int(pad_l), int(pad_t + chart_h), int(W - pad_r), int(pad_t + chart_h))
        p.end()

    def _draw_legend(self, p, pad_l: int) -> None:
        """차트 상단 범례를 왼쪽부터 이어 그린다. 항목 폭은 QFontMetrics로
        실측해야 한글 라벨에서 다음 항목과 겹치지 않는다."""
        font = QFont("Consolas", 8)
        fm = QFontMetrics(font)
        swatch_w, text_offset = 8, 12

        lx = pad_l
        for label, _, color in self.datasets:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(lx), 4, swatch_w, swatch_w, 2, 2)
            lx = self._draw_legend_text(p, font, fm, lx + text_offset, label)

    def _draw_legend_text(self, p, font, fm, x: float, label) -> float:
        """범례 라벨을 x에 그리고 다음 항목이 시작할 x를 반환한다."""
        text = str(label)
        text_w = fm.horizontalAdvance(text)
        p.setPen(QColor(TEXT_SECONDARY))
        p.setFont(font)
        p.drawText(int(x), 2, text_w, 12, Qt.AlignmentFlag.AlignVCenter, text)
        return x + text_w + self.LEGEND_GAP
