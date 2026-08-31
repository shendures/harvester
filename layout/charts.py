# layout/charts.py
# StatisticsPage 전용 미니 차트 위젯 (BarChart/LineChart/DonutChart).

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient

from .common import ACCENT, BORDER, TEXT_MUTED, TEXT_SECONDARY, TEXT_PRIMARY, BG_PRIMARY, BG_SECONDARY


class BarChart(QWidget):
    """레이블 + 값 배열을 받아 수직 막대 차트를 그림"""

    def __init__(self, labels=None, values=None, color=ACCENT, parent=None):
        super().__init__(parent)
        self.labels = labels or []
        self.values = values or []
        self.color = QColor(color)
        self.setMinimumHeight(160)

    def set_data(self, labels, values, color=None):
        self.labels = labels
        self.values = values
        if color:
            self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        if not self.values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 28
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        max_v = max(self.values) or 1
        n = len(self.values)
        bar_w = max(4, chart_w // n - 4)

        # grid lines
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pad_t + chart_h - int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y + 4, pad_l - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        # bars + labels
        for i, (lbl, val) in enumerate(zip(self.labels, self.values)):
            x = pad_l + i * (chart_w // n) + (chart_w // n - bar_w) // 2
            bar_h = int(chart_h * val / max_v)
            y = pad_t + chart_h - bar_h

            grad = QLinearGradient(x, y, x, y + bar_h)
            grad.setColorAt(0, self.color.lighter(130))
            grad.setColorAt(1, self.color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 3, 3)

            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, H - pad_b + 4, bar_w + 8, 20,
                       Qt.AlignmentFlag.AlignCenter, str(lbl))

            # value on top
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, max(y - 14, 0), bar_w + 8, 14,
                       Qt.AlignmentFlag.AlignCenter, str(val))

        p.end()


class LineChart(QWidget):
    """시계열 선 그래프"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets = []  # list of (label, values, color)
        self.x_labels = []
        self.setMinimumHeight(160)

    def set_data(self, x_labels, datasets):
        self.x_labels = x_labels
        self.datasets = datasets
        self.update()

    def paintEvent(self, e):
        if not self.datasets:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt, pb = 40, 10, 14, 30
        cw, ch = W - pl - pr, H - pt - pb

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals) if all_vals else 1

        # grid
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pt + ch - int(ch * i / 4)
            p.drawLine(pl, y, W - pr, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y - 6, pl - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        n = max(len(self.x_labels), 1)
        step = cw / max(n - 1, 1)

        for label, vals, color in self.datasets:
            if not vals:
                continue
            qc = QColor(color)
            points = []
            for i, v in enumerate(vals):
                x = int(pl + i * step)

                if max_v == 0:
                    y = pt + ch
                else:
                    y = int(pt + ch - ch * v / max_v)
                points.append(QPoint(x, y))

            # line
            p.setPen(QPen(qc, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i + 1])

            # dots
            p.setBrush(QBrush(qc))
            p.setPen(QPen(QColor(BG_PRIMARY), 2))
            for pt2 in points:
                p.drawEllipse(pt2, 4, 4)

        # x labels
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Consolas", 8))
        for i, lbl in enumerate(self.x_labels):
            x = int(pl + i * step)
            p.drawText(x - 20, H - pb + 4, 40, 20, Qt.AlignmentFlag.AlignCenter, str(lbl))

        p.end()



class DonutChart(QWidget):
    """도넛 차트: segments = [(label, value, color)]"""

    def __init__(self, segments=None, parent=None):
        super().__init__(parent)
        self.segments = segments or []
        self.setMinimumSize(140, 140)
        self.setMaximumSize(180, 180)

    def set_data(self, segments):
        self.segments = segments
        self.update()

    def paintEvent(self, e):
        # [수정] 데이터가 없으면 아무것도 그리지 않고 리턴합니다.
        if not self.segments or sum(v for _, v, _ in self.segments) == 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        size = min(W, H) - 16
        x = (W - size) // 2
        y = (H - size) // 2

        total = sum(v for _, v, _ in self.segments)
        start = -90 * 16

        # 1. 파이 조각 그리기
        for label, val, color in self.segments:
            span = int(360 * 16 * val / total)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(QPen(QColor(BG_PRIMARY), 3))
            p.drawPie(x, y, size, size, start, span)
            start += span

        # 2. 가운데 구멍 뚫기 (Donut 형태)
        hole = int(size * 0.52)
        hx = (W - hole) // 2
        hy = (H - hole) // 2
        p.setBrush(QBrush(QColor(BG_SECONDARY)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(hx, hy, hole, hole)

        # 3. 센터 텍스트 (총합) 표시
        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        p.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter, str(total))

        p.end()
