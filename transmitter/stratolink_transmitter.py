#!/usr/bin/env python3
"""LORett StratoLink — Передатчик с erasure-FEC (Reed-Solomon).

Кодирует JPEG/WebP в K data + M parity блоков и отправляет broadcast по TCP.
"""

import sys
import time
import os
import random
import socket
from pathlib import Path
from typing import Optional

_SHARED = str(Path(__file__).resolve().parent.parent / "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from PyQt5 import uic
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QFrame, QComboBox, QSpinBox, QTabWidget, QLineEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap

from erasure_fec import ErasureEncoder
from protocol import build_telem
from theme_manager import Theme, load_theme, save_theme, apply_theme

UI_PATH = Path(__file__).parent / "transmitter.ui"


# ═══════════════════════════════════════════════════════════════
#  FEC Transmit worker
# ═══════════════════════════════════════════════════════════════

class FECTransmitWorker(QThread):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    encoding_done = pyqtSignal(int, int, int)   # image_id, k_data, n_total
    packet_sent = pyqtSignal(int, bool)         # block_id, is_parity
    transfer_done = pyqtSignal(bool, float)
    log_message = pyqtSignal(str)

    def __init__(self, host: str, port: int, file_path: str,
                 callsign: str, image_id: int, delay_ms: int,
                 fec_ratio: float, tx_power: int = 33):
        super().__init__()
        self.host = host
        self.port = port
        self.file_path = file_path
        self.callsign = callsign
        self.image_id = image_id
        self.delay_ms = delay_ms
        self.fec_ratio = fec_ratio
        self.tx_power = tx_power
        self._running = False

    def run(self):
        self._running = True
        sock = None
        t0 = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.host, self.port))
            self.connected.emit()

            enc = ErasureEncoder(self.callsign, self.image_id, self.fec_ratio)
            packets = enc.encode_file(self.file_path)
            k = packets[0].k_data
            n = packets[0].n_total
            m = n - k
            self.encoding_done.emit(self.image_id, k, n)
            self.log_message.emit(
                f"FEC: K={k} data + M={m} parity = {n} блоков  "
                f"({os.path.getsize(self.file_path)} Б, "
                f"overhead {m / k * 100:.0f}%)")

            for pkt in packets:
                if not self._running:
                    return
                if pkt.block_id % 64 == 0:
                    rssi = random.randint(-110, -60)
                    snr = random.randint(20, 40)
                    sock.sendall(build_telem(rssi, snr, self.tx_power))
                sock.sendall(pkt.to_bytes())
                self.packet_sent.emit(pkt.block_id, pkt.is_parity)
                if self.delay_ms > 0:
                    time.sleep(self.delay_ms / 1000.0)

            self.transfer_done.emit(True, time.time() - t0)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            self.transfer_done.emit(False, time.time() - t0)
        finally:
            if sock:
                sock.close()
            self.disconnected.emit()

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _make_card(title, description=""):
    card = QFrame()
    card.setProperty("class", "card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(12)
    h = QLabel(title); h.setProperty("class", "heading"); lay.addWidget(h)
    if description:
        d = QLabel(description); d.setProperty("class", "description")
        d.setWordWrap(True); lay.addWidget(d)
    return card, lay


# ═══════════════════════════════════════════════════════════════
#  Main window
# ═══════════════════════════════════════════════════════════════

class TransmitterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_PATH), self)

        self._worker: Optional[FECTransmitWorker] = None
        self._n_total = 0
        self._sent = 0
        self._image_counter = 0

        self._setup_tabs()
        self._connect_signals()
        self.splitter.setSizes([380, 480])
        self.progress.setProperty("class", "tx")
        self.img_label.setStyleSheet("")

    def _setup_tabs(self):
        main_content = self.centralWidget()
        settings_tab = self._build_settings()
        self._tabs = QTabWidget(); self._tabs.setObjectName("mainTabs")
        self._tabs.addTab(main_content, "  Передача  ")
        self._tabs.addTab(settings_tab, "  Настройки  ")
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(0)
        wl.addWidget(self._tabs)
        self.setCentralWidget(wrapper)

    def _build_settings(self):
        page = QWidget()
        root = QVBoxLayout(page); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(16)

        card_a, la = _make_card("Внешний вид")
        ra = QHBoxLayout(); ra.addWidget(QLabel("Тема:"))
        self.cb_theme = QComboBox()
        self.cb_theme.addItem("Тёмная", Theme.DARK.value)
        self.cb_theme.addItem("Светлая", Theme.LIGHT.value)
        cur = load_theme()
        idx = self.cb_theme.findData(cur.value)
        if idx >= 0: self.cb_theme.setCurrentIndex(idx)
        self.cb_theme.currentIndexChanged.connect(self._on_theme_changed)
        ra.addWidget(self.cb_theme); ra.addStretch(); la.addLayout(ra)
        root.addWidget(card_a)

        card_s, ls = _make_card(
            "FEC / Радио",
            "Callsign — позывной (до 6 символов). "
            "FEC overhead — доля parity-блоков (25% = на каждые 4 data один parity). "
            "Задержка — пауза между пакетами.")
        r1 = QHBoxLayout(); r1.setSpacing(12)
        r1.addWidget(QLabel("Callsign:"))
        self.edit_callsign = QLineEdit("LORETT")
        self.edit_callsign.setMaxLength(6); self.edit_callsign.setMaximumWidth(120)
        r1.addWidget(self.edit_callsign); r1.addStretch(); ls.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(12)
        r2.addWidget(QLabel("FEC overhead:"))
        self.sb_fec = QSpinBox()
        self.sb_fec.setRange(5, 100); self.sb_fec.setValue(25); self.sb_fec.setSuffix(" %")
        r2.addWidget(self.sb_fec)
        r2.addWidget(QLabel("Задержка:"))
        self.sb_delay.show(); r2.addWidget(self.sb_delay)
        r2.addStretch(); ls.addLayout(r2)
        root.addWidget(card_s)

        root.addStretch()
        return page

    def _on_theme_changed(self):
        theme = Theme(self.cb_theme.currentData())
        save_theme(theme); apply_theme(QApplication.instance(), theme)

    def _connect_signals(self):
        self.btn_connect.clicked.connect(self._toggle)
        self.btn_browse.clicked.connect(self._browse_file)
        self.btn_send.clicked.connect(self._start_transfer)

    @staticmethod
    def _ts(): return time.strftime("%H:%M:%S")

    def _log(self, msg):
        self.log.append(f"<span style='color:#888'>{self._ts()}</span>  {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.jpg *.jpeg *.webp *.png *.bmp);;Все файлы (*)")
        if not path: return
        self.edit_file.setText(path)
        px = QPixmap(path)
        if not px.isNull():
            self.img_label.setPixmap(px.scaled(
                self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.btn_send.setEnabled(True)

    def _toggle(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop(); self._worker.wait(3000); return
        self._start_transfer()

    def _start_transfer(self):
        fp = self.edit_file.text()
        if not fp or not os.path.isfile(fp):
            self._log("<b style='color:#FFB74D'>Выберите файл</b>"); return
        self.matrix.clear_all(); self.progress.setValue(0); self._sent = 0

        cs = self.edit_callsign.text() if hasattr(self, "edit_callsign") else "LORETT"
        fec = self.sb_fec.value() / 100.0 if hasattr(self, "sb_fec") else 0.25

        self._worker = FECTransmitWorker(
            self.edit_ip.text(), self.sb_port.value(), fp,
            cs, self._image_counter, self.sb_delay.value(), fec)
        self._image_counter = (self._image_counter + 1) & 0xFF

        self._worker.connected.connect(lambda: self._log("<b style='color:#81C784'>TCP OK</b>"))
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.error_occurred.connect(lambda e: self._log(f"<b style='color:#e57373'>{e}</b>"))
        self._worker.encoding_done.connect(self._on_encoding_done)
        self._worker.packet_sent.connect(self._on_packet_sent)
        self._worker.transfer_done.connect(self._on_done)
        self._worker.log_message.connect(self._log)
        self._worker.start()
        self.btn_send.setEnabled(False); self.btn_connect.setText("Остановить")
        self._log(f"Подключение к {self.edit_ip.text()}:{self.sb_port.value()}...")

    def _on_disconnected(self):
        self.btn_connect.setText("Подключить")
        self.btn_send.setEnabled(bool(self.edit_file.text()))
        self.statusbar.showMessage("Отключено")

    def _on_encoding_done(self, iid, k, n):
        self._n_total = n
        self.matrix.set_total(n)
        self.progress.setMaximum(n)
        self._log(f"<b style='color:#64B5F6'>FEC</b> image={iid}  K={k}  N={n}")

    def _on_packet_sent(self, bid, is_parity):
        if is_parity:
            self.matrix.mark_parity(bid)
        else:
            self.matrix.mark_sent(bid)
        self._sent += 1
        self.progress.setValue(self._sent)
        if self._n_total:
            self.lbl_chunks.setText(
                f"{self._sent} / {self._n_total}  "
                f"({self._sent / self._n_total * 100:.1f}%)")

    def _on_done(self, ok, elapsed):
        tag = "Передано" if ok else "Прервано"
        clr = "#81C784" if ok else "#e57373"
        self._log(f"<b style='color:{clr}'>{tag}</b> за {elapsed:.1f} с")
        if ok:
            for i in range(self._n_total):
                self.matrix.mark(i)
        self.btn_send.setEnabled(True); self.btn_connect.setText("Подключить")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.stop(); self._worker.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv); app.setStyle("Fusion")
    apply_theme(app, load_theme())
    win = TransmitterWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
