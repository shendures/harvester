# layout/charts.py
# StatisticsPage 전용 미니 차트 위젯 (RankedBarChart/HeatStripChart/GroupedBarChart).

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from .common import BORDER, TEXT_MUTED, TEXT_SECONDARY, TEXT_PRIMARY, BG_PRIMARY


class RankedBarChart(QWidget):
    """segments = [(label, value, color)] — 값 내림차순 가로 막대 순위 리스트.
    값 옆에 전체 대비 비율을 괄호로 함께 표시한다."""

    def __init__(self, segments=None, parent=None):
        super().__init__(parent)
        self.segments = segments or []
        self.setMinimumHeight(170)

    def set_data(self, segments):
        self.segments = segments
        self.update()

    def paintEvent(self, e):
        if not self.segments:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        rows = sorted(self.segments, key=lambda s: s[1], reverse=True)
        total = sum(v for _, v, _ in rows) or 1
        max_v = max(v for _, v, _ in rows) or 1
        n = len(rows)
        row_h = H / n
        label_w, count_w, track_h = 46, 92, 10
        track_x0, track_x1 = label_w + 8, W - count_w

        for i, (label, val, color) in enumerate(rows):
            y = i * row_h
            cy = y + row_h / 2

            p.setPen(QColor(TEXT_PRIMARY))
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.drawText(0, int(y), label_w, int(row_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(label))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BG_PRIMARY))
            p.drawRoundedRect(int(track_x0), int(cy - track_h / 2), int(track_x1 - track_x0), track_h, 3, 3)

            w = max((val / max_v) * (track_x1 - track_x0), 3)
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(track_x0), int(cy - track_h / 2), int(w), track_h, 3, 3)

            pct = val / total * 100
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 9))
            p.drawText(int(track_x1) + 6, int(y), count_w, int(row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{val} ({pct:.1f}%)")

        p.end()


class HeatStripChart(QWidget):
    """레이블 + 값 배열을 단일 색상 농도 스트립으로 그림. 제목 옆에 평균 응답 시간을
    소수점 3자리까지 괄호로 함께 표시한다."""

    def __init__(self, labels=None, values=None, avg=0.0, color=BORDER, parent=None):
        super().__init__(parent)
        self.labels = labels or []
        self.values = values or []
        self.avg = avg
        self.color = QColor(color)
        self.setMinimumHeight(170)

    def set_data(self, labels, values, avg, color=None):
        self.labels = labels
        self.values = values
        self.avg = avg
        if color:
            self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        if not self.values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        n = len(self.values)
        max_v = max(self.values) or 1
        pad_l, pad_r, gap = 10, 10, 3
        strip_y, strip_h = H * 0.36, H * 0.3
        cell_w = (W - pad_l - pad_r - gap * (n - 1)) / n

        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Consolas", 8))
        p.drawText(pad_l, int(strip_y - 22), W - pad_l - pad_r, 16, Qt.AlignmentFlag.AlignLeft,
                   f"버킷별 밀집도 (평균 {self.avg:.3f}s)")

        for i, v in enumerate(self.values):
            t = v / max_v
            x = pad_l + i * (cell_w + gap)
            cell_color = QColor(self.color)
            cell_color.setAlphaF(0.14 + t * 0.86)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cell_color)
            p.drawRoundedRect(int(x), int(strip_y), int(cell_w), int(strip_h), 4, 4)

        for i in (0, n // 2, n - 1):
            x = pad_l + i * (cell_w + gap) + cell_w / 2
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(int(x - 22), int(strip_y + strip_h + 6), 44, 16,
                       Qt.AlignmentFlag.AlignCenter, f"{self.labels[i]}s")

        p.end()


class GroupedBarChart(QWidget):
    """x_labels + datasets(=[(label, values, color), ...])를 카테고리별 그룹 막대로 그림"""

    def __init__(self, x_labels=None, datasets=None, parent=None):
        super().__init__(parent)
        self.x_labels = x_labels or []
        self.datasets = datasets or []
        self.setMinimumHeight(170)

    def set_data(self, x_labels, datasets):
        self.x_labels = x_labels
        self.datasets = datasets
        self.update()

    def paintEvent(self, e):
        if not self.datasets or not self.x_labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 8, 8, 22, 20
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals) if all_vals else 1
        max_v = max_v or 1

        # 범례
        lx = pad_l
        for label, _, color in self.datasets:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(lx), 4, 8, 8, 2, 2)
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 8))
            p.drawText(int(lx) + 12, 2, 60, 12, Qt.AlignmentFlag.AlignVCenter, str(label))
            lx += 12 + 8 + len(label) * 7 + 6

        # 격자선
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pad_t + chart_h - int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)

        # 막대 (시간대별 그룹)
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

            # 시간대 라벨 — 12개가 좁은 폭에 들어가도록 눈에 보일 정도로만 작게(7pt)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 7))
            p.drawText(int(pad_l + i * group_w), int(pad_t + chart_h + 4), int(group_w), 14,
                       Qt.AlignmentFlag.AlignCenter, str(self.x_labels[i]))

        p.setPen(QColor(BORDER))
        p.drawLine(int(pad_l), int(pad_t + chart_h), int(W - pad_r), int(pad_t + chart_h))
        p.end()
