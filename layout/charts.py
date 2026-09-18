# layout/charts.py
# StatisticsPage 전용 미니 차트 위젯 (RankedBarChart/HeatStripChart/GroupedBarChart).

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from .common import BORDER, TEXT_MUTED, TEXT_SECONDARY, TEXT_PRIMARY, BG_PRIMARY


class RankedBarChart(QWidget):
    """segments = [(label, value, color)] — 값 내림차순 가로 막대 순위 리스트.
    값 옆에 전체 대비 비율을 괄호로 함께 표시한다."""

    # 라벨 열의 최소 폭 — 상태 코드(3자리) 기준값. 이보다 넓은 라벨은
    # paintEvent에서 실제 문자열 폭을 재서 열을 넓힌다.
    LABEL_COL_MIN_W = 46

    def __init__(self, segments=None, parent=None):
        super().__init__(parent)
        self.segments = segments or []
        # statistics.py Row2 카드("상태 코드 분포") 전용 — STATUS_CODE_COLORS
        # (trigger/common.py)가 구분하는 상태 코드 6종(200/301/404/429/500/000)이
        # 모두 표시돼도 행당 26px 정도로 여유 있게 보이도록 6×26=156으로 잡았다.
        # setMinimumHeight가 아니라 setFixedHeight인 이유는 이 값보다 커지면
        # (형제 카드가 더 커서 강제로 늘어나는 등) 카드 안에 빈 공백만 남기
        # 때문 — 집계 표 카드에도 같은 이유로 적용했다.
        self.setFixedHeight(156)

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
        # 한글 라벨("정상 수집" 등)은 3자리 상태 코드보다 넓어 고정 폭으로는 잘리므로,
        # 실제 문자열 폭을 재서 최소 폭과 넓은 쪽을 쓴다
        label_font = QFont("Consolas", 10, QFont.Weight.Bold)
        label_fm = QFontMetrics(label_font)
        label_w = max(self.LABEL_COL_MIN_W,
                      max(label_fm.horizontalAdvance(str(lb)) for lb, _, _ in rows))
        count_w, track_h = 92, 10
        track_x0, track_x1 = label_w + 8, W - count_w

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
        # statistics.py Row2 카드("응답 시간 분포 (s)") 전용 — 옆 "상태 코드 분포"
        # 카드와 높이를 맞추기 위해 같은 156을 쓴다. 고정 비율 밴드 하나만
        # 그려서 어떤 높이든 자연스럽게 늘어난다. setFixedHeight를 쓰는 이유는
        # RankedBarChart와 같다(주석 참고).
        self.setFixedHeight(156)

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

        value_font = QFont("Consolas", 7)
        value_fm = QFontMetrics(value_font)
        value_gap = 4  # 막대 상단-값 라벨 사이 고정 간격(px)

        pad_l, pad_r, pad_b = 8, 8, 20
        pad_t = 22 + value_gap + value_fm.height()  # 기존 범례 여백 + 값 라벨 공간
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals, default=0) or 1

        lx = pad_l
        for label, _, color in self.datasets:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(lx), 4, 8, 8, 2, 2)
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 8))
            p.drawText(int(lx) + 12, 2, 60, 12, Qt.AlignmentFlag.AlignVCenter, str(label))
            lx += 12 + 8 + len(label) * 7 + 6

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

                # 값 라벨 — 막대 상단에서 value_gap만큼 띄운 자리에 계열 색상으로 표시
                text = str(v)
                text_w = value_fm.horizontalAdvance(text)
                label_x = x + bar_w / 2 - text_w / 2
                label_y = y - value_gap - value_fm.height()
                p.setPen(QColor(color))
                p.setFont(value_font)
                p.drawText(int(label_x), int(label_y), text_w, value_fm.height(),
                           Qt.AlignmentFlag.AlignCenter, text)

            # 시간대 라벨 — 12개가 좁은 폭에 들어가도록 눈에 보일 정도로만 작게(7pt)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 7))
            p.drawText(int(pad_l + i * group_w), int(pad_t + chart_h + 4), int(group_w), 14,
                       Qt.AlignmentFlag.AlignCenter, str(self.x_labels[i]))

        p.setPen(QColor(BORDER))
        p.drawLine(int(pad_l), int(pad_t + chart_h), int(W - pad_r), int(pad_t + chart_h))
        p.end()
