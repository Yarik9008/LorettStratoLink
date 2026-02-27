"""Custom widgets for StratoLink Receiver / Transmitter."""

import math

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QFont, QPalette, QPen

STATE_EMPTY = 0
STATE_SENT = 1
STATE_OK = 2
STATE_PARITY = 3

CLR_SENT = QColor("#FFA726")
CLR_OK = QColor("#4CAF50")
CLR_PARITY = QColor("#42A5F5")


class ChunkMatrixWidget(QWidget):
    """Chunk/block matrix with four visual states.

    Renders a grid of rounded-rect cells, auto-sized to fit.
    Adapts colors to current theme via QPalette.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total = 0
        self._states: dict[int, int] = {}
        self._k_data = 0
        self.setMinimumSize(200, 140)

    def set_total(self, n: int, k_data: int = 0):
        self._total = n
        self._k_data = k_data
        self._states.clear()
        self.update()

    def mark(self, idx: int):
        self._states[idx] = STATE_OK
        self.update()

    def mark_parity(self, idx: int):
        self._states[idx] = STATE_PARITY
        self.update()

    def mark_sent(self, idx: int):
        if self._states.get(idx, STATE_EMPTY) == STATE_EMPTY:
            self._states[idx] = STATE_SENT
            self.update()

    def clear_all(self):
        self._total = 0
        self._k_data = 0
        self._states.clear()
        self.update()

    def _is_dark(self):
        return self.palette().color(QPalette.Window).lightness() < 128

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        dark = self._is_dark()
        bg = QColor("#141414") if dark else QColor("#E0E0E0")
        empty_clr = QColor("#2A2A2A") if dark else QColor("#C8C8C8")
        text_clr = QColor("#555") if dark else QColor("#999")

        p.fillRect(self.rect(), bg)

        if self._total == 0:
            p.setPen(text_clr)
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "Ожидание...")
            p.end()
            return

        state_clr = {
            STATE_EMPTY: empty_clr,
            STATE_SENT: CLR_SENT,
            STATE_OK: CLR_OK,
            STATE_PARITY: CLR_PARITY,
        }

        w, h = self.width(), self.height()
        legend_h = 20
        draw_h = h - legend_h

        aspect = w / max(draw_h, 1)
        cols = max(1, round(math.sqrt(self._total * aspect)))
        rows = max(1, math.ceil(self._total / cols))

        cell_w = w / cols
        cell_h = draw_h / rows
        cell = min(cell_w, cell_h)
        gap = max(1.0, cell * 0.1)
        s = cell - gap
        r = max(1, min(int(s * 0.2), 4))

        x0 = (w - cols * cell) / 2
        y0 = (draw_h - rows * cell) / 2

        p.setPen(Qt.NoPen)
        for i in range(self._total):
            col = i % cols
            row = i // cols
            x = x0 + col * cell + gap / 2
            y = y0 + row * cell + gap / 2
            st = self._states.get(i, STATE_EMPTY)
            p.setBrush(state_clr.get(st, empty_clr))
            p.drawRoundedRect(int(x), int(y), max(int(s), 1), max(int(s), 1), r, r)

        # Legend at bottom
        legend_y = draw_h + 2
        lf = QFont("Segoe UI", 7)
        p.setFont(lf)
        items = [
            (CLR_OK, "Data"),
            (CLR_PARITY, "Parity"),
            (CLR_SENT, "Отпр."),
            (empty_clr, "Пусто"),
        ]
        lx = 6
        for clr, label in items:
            p.setPen(Qt.NoPen)
            p.setBrush(clr)
            p.drawRoundedRect(lx, int(legend_y + 3), 10, 10, 2, 2)
            p.setPen(text_clr)
            p.drawText(lx + 14, int(legend_y + 12), label)
            lx += p.fontMetrics().horizontalAdvance(label) + 24

        p.end()
