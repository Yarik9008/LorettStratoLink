#!/usr/bin/env python3
"""LORett StratoLink — Приёмник с erasure-FEC (Reed-Solomon).

Принимает FEC-блоки по COM / TCP / симуляции.
Когда получено >= K любых блоков из N, восстанавливает файл 1:1.
"""

import sys
import math
import time
import os
import socket
import threading
from pathlib import Path
from typing import Optional

_SHARED = str(Path(__file__).resolve().parent.parent / "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from PyQt5 import uic
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QFrame, QComboBox, QSpinBox, QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap

from erasure_fec import FECPacket, ErasureEncoder, ErasureDecoder
from protocol import StreamParser, TelemInfo, build_telem
from theme_manager import Theme, load_theme, save_theme, apply_theme

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

UI_PATH = Path(__file__).parent / "mainwindow.ui"


# ═══════════════════════════════════════════════════════════════
#  Serial worker
# ═══════════════════════════════════════════════════════════════

class SerialWorker(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self._running = False
        self._ser = None

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self._running = True
            self.connection_changed.emit(True)
            while self._running:
                chunk = self._ser.read(1024)
                if chunk:
                    self.data_received.emit(chunk)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self.connection_changed.emit(False)

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  TCP server worker
# ═══════════════════════════════════════════════════════════════

class TcpServerWorker(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    client_info = pyqtSignal(str)

    def __init__(self, port: int):
        super().__init__()
        self._port = port
        self._running = False
        self._server_sock = None

    def run(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.settimeout(1.0)
            self._server_sock.bind(("0.0.0.0", self._port))
            self._server_sock.listen(1)
            self._running = True
            self.connection_changed.emit(True)
            while self._running:
                try:
                    client, addr = self._server_sock.accept()
                except socket.timeout:
                    continue
                self.client_info.emit(f"{addr[0]}:{addr[1]}")
                client.settimeout(0.2)
                try:
                    while self._running:
                        try:
                            data = client.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        self.data_received.emit(data)
                finally:
                    client.close()
                    self.client_info.emit("")
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            if self._server_sock:
                self._server_sock.close()
            self.connection_changed.emit(False)

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
#  Local FEC simulation worker
# ═══════════════════════════════════════════════════════════════

class SimulatorWorker(QThread):
    data_generated = pyqtSignal(bytes)
    sim_finished = pyqtSignal()

    def __init__(self, path: str, delay_ms: int = 30, fec_ratio: float = 0.25):
        super().__init__()
        self.path = path
        self.delay_ms = delay_ms
        self.fec_ratio = fec_ratio
        self._running = False

    def run(self):
        self._running = True
        enc = ErasureEncoder("SIMUL", int(time.time()) & 0xFF, self.fec_ratio)
        packets = enc.encode_file(self.path)
        time.sleep(0.2)
        for pkt in packets:
            if not self._running:
                return
            self.data_generated.emit(pkt.to_bytes())
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000.0)
        time.sleep(0.1)
        self.sim_finished.emit()

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _make_card(title, description=""):
    card = QFrame(); card.setProperty("class", "card")
    lay = QVBoxLayout(card); lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(12)
    h = QLabel(title); h.setProperty("class", "heading"); lay.addWidget(h)
    if description:
        d = QLabel(description); d.setProperty("class", "description")
        d.setWordWrap(True); lay.addWidget(d)
    return card, lay


# ═══════════════════════════════════════════════════════════════
#  Main window
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_PATH), self)

        self.parser = StreamParser()
        self.decoder = ErasureDecoder()
        self.serial_worker: Optional[SerialWorker] = None
        self.tcp_worker: Optional[TcpServerWorker] = None
        self.sim_worker: Optional[SimulatorWorker] = None
        self._start_time: Optional[float] = None
        self._bytes_rx = 0
        self._last_preview_cnt = 0
        self._recovery_done = False

        self._setup_tabs()
        self._connect_signals()

        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start(500)

        self.btn_connect.setEnabled(HAS_SERIAL)
        self.splitter.setSizes([420, 520])
        self.progress.setProperty("class", "rx")
        self.img_label.setStyleSheet("")
        self._refresh_ports()

    # ── tabs ─────────────────────────────────────────────────

    def _setup_tabs(self):
        main_content = self.centralWidget()
        settings_tab = self._build_settings()
        self._tabs = QTabWidget(); self._tabs.setObjectName("mainTabs")
        self._tabs.addTab(main_content, "  Приём  ")
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

        card_s, ls = _make_card("Симуляция", "Задержка и FEC overhead для локальной симуляции.")
        rs = QHBoxLayout(); rs.setSpacing(12)
        rs.addWidget(QLabel("Задержка:"))
        self.sb_delay.show(); rs.addWidget(self.sb_delay)
        rs.addWidget(QLabel("FEC:"))
        self.sb_fec_sim = QSpinBox()
        self.sb_fec_sim.setRange(5, 100); self.sb_fec_sim.setValue(25); self.sb_fec_sim.setSuffix(" %")
        rs.addWidget(self.sb_fec_sim)
        rs.addStretch(); ls.addLayout(rs)
        root.addWidget(card_s)

        root.addStretch()
        return page

    def _on_theme_changed(self):
        theme = Theme(self.cb_theme.currentData())
        save_theme(theme); apply_theme(QApplication.instance(), theme)

    def _connect_signals(self):
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._toggle_serial)
        self.btn_tcp.clicked.connect(self._toggle_tcp)
        self.btn_sim.clicked.connect(self._start_sim)
        self.btn_save.clicked.connect(self._save_image)

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _ts(): return time.strftime("%H:%M:%S")

    def _append_log(self, msg):
        self.log.append(f"<span style='color:#888'>{self._ts()}</span>  {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _refresh_ports(self):
        self.cb_port.clear()
        if HAS_SERIAL:
            for p in serial.tools.list_ports.comports():
                self.cb_port.addItem(p.device)
        if self.cb_port.count() == 0:
            self.cb_port.addItem("(нет портов)")

    # ── serial ───────────────────────────────────────────────

    def _toggle_serial(self):
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.stop(); self.serial_worker.wait(2000); return
        port = self.cb_port.currentText()
        if not port or port.startswith("("): return
        baud = int(self.cb_baud.currentText())
        self.serial_worker = SerialWorker(port, baud)
        self.serial_worker.data_received.connect(self._on_raw_data)
        self.serial_worker.error_occurred.connect(
            lambda e: self._append_log(f"<b style='color:#e57373'>COM:</b> {e}"))
        self.serial_worker.connection_changed.connect(self._on_serial_state)
        self.serial_worker.start()

    def _on_serial_state(self, connected):
        self.btn_connect.setText("Отключить" if connected else "Подключить")
        self._append_log("<b style='color:#81C784'>COM OK</b>" if connected else "COM отключено")

    # ── TCP ──────────────────────────────────────────────────

    def _toggle_tcp(self):
        if self.tcp_worker and self.tcp_worker.isRunning():
            self.tcp_worker.stop(); self.tcp_worker.wait(2000); return
        port = self.sb_tcp_port.value()
        self.tcp_worker = TcpServerWorker(port)
        self.tcp_worker.data_received.connect(self._on_raw_data)
        self.tcp_worker.error_occurred.connect(
            lambda e: self._append_log(f"<b style='color:#e57373'>TCP:</b> {e}"))
        self.tcp_worker.connection_changed.connect(self._on_tcp_state)
        self.tcp_worker.client_info.connect(self._on_tcp_client)
        self.tcp_worker.start()

    def _on_tcp_state(self, listening):
        if listening:
            self.btn_tcp.setText("Стоп")
            self._append_log(f"<b style='color:#81C784'>TCP :{self.sb_tcp_port.value()}</b>")
            self.statusbar.showMessage(f"TCP сервер :{self.sb_tcp_port.value()}")
        else:
            self.btn_tcp.setText("Слушать")
            self.statusbar.showMessage("Отключено")

    def _on_tcp_client(self, info):
        if info:
            self._append_log(f"<b style='color:#64B5F6'>Клиент:</b> {info}")
            self.statusbar.showMessage(f"Клиент: {info}")
        else:
            self._append_log("Клиент отключился")

    # ── simulation ───────────────────────────────────────────

    def _start_sim(self):
        if self.sim_worker and self.sim_worker.isRunning():
            self.sim_worker.stop(); self.sim_worker.wait(2000)
            self.btn_sim.setText("Симуляция..."); return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.jpg *.jpeg *.webp *.png *.bmp);;Все файлы (*)")
        if not path: return
        self._reset_state()
        fec = self.sb_fec_sim.value() / 100.0 if hasattr(self, "sb_fec_sim") else 0.25
        self.sim_worker = SimulatorWorker(path, self.sb_delay.value(), fec)
        self.sim_worker.data_generated.connect(self._on_raw_data)
        self.sim_worker.sim_finished.connect(self._on_sim_done)
        self.sim_worker.start()
        self.btn_sim.setText("Остановить")
        self._append_log(f"Симуляция: <b>{os.path.basename(path)}</b>")

    def _on_sim_done(self):
        self.btn_sim.setText("Симуляция...")
        self._append_log("Симуляция завершена")

    # ── packet processing ────────────────────────────────────

    def _reset_state(self):
        self.parser.reset()
        self.decoder.reset()
        self.matrix.clear_all()
        self.progress.setValue(0); self.progress.setMaximum(1)
        self._start_time = None; self._bytes_rx = 0
        self._last_preview_cnt = 0; self._recovery_done = False
        self.btn_save.setEnabled(False)
        self.img_label.clear()
        self.lbl_chunks.setText("Ожидание FEC...")

    def _on_raw_data(self, raw: bytes):
        self._bytes_rx += len(raw)
        if self._start_time is None:
            self._start_time = time.time()
        for obj in self.parser.feed(raw):
            if isinstance(obj, FECPacket):
                self._handle_fec(obj)
            elif isinstance(obj, TelemInfo):
                self._handle_telem(obj)

    def _handle_fec(self, pkt: FECPacket):
        new_image = (self.decoder.image_id is not None
                     and pkt.image_id != self.decoder.image_id)
        if new_image:
            self._reset_state(); self._start_time = time.time()

        first = self.decoder.received_count == 0
        self.decoder.add_packet(pkt)

        if first:
            self.matrix.set_total(pkt.n_total)
            self.progress.setMaximum(pkt.k_data)
            k, m = pkt.k_data, pkt.n_total - pkt.k_data
            self._append_log(
                f"<b style='color:#64B5F6'>FEC</b>  "
                f"call=<b>{pkt.callsign}</b>  image={pkt.image_id}  "
                f"K={k}  M={m}  file={pkt.file_size} Б")

        if pkt.is_parity:
            self.matrix.mark_parity(pkt.block_id)
        else:
            self.matrix.mark(pkt.block_id)

        cnt = self.decoder.received_count
        k = self.decoder.k_data
        elapsed = time.time() - (self._start_time or time.time())
        speed = self._bytes_rx / max(elapsed, 0.01)

        need = max(k - cnt, 0)
        self.progress.setValue(min(cnt, k))
        self.lbl_chunks.setText(
            f"{cnt} / {pkt.n_total}  "
            f"(ещё {need} до восстановления)  —  {speed / 1024:.1f} КБ/с")

        if self.decoder.can_decode and not self._recovery_done:
            self._try_recover()

    def _try_recover(self):
        self._append_log("Запуск RS-декодирования...")
        result = self.decoder.decode()
        if result is not None:
            self._recovery_done = True
            self._append_log(
                f"<b style='color:#81C784'>Файл восстановлен 1:1</b>  "
                f"({len(result)} Б)")
            self.btn_save.setEnabled(True)
            self.progress.setValue(self.decoder.k_data)
            self._refresh_preview()
        else:
            self._append_log("<b style='color:#e57373'>RS decode failed</b>")

    def _handle_telem(self, t: TelemInfo):
        self.lbl_rssi.setText(f"RSSI: {t.rssi} дБм")
        self.lbl_snr.setText(f"SNR: {t.snr / 4:.1f} дБ")
        self.lbl_txpower.setText(f"TX: {t.tx_power} дБм")
        self.bar_rssi.setValue(max(t.rssi, -140))

    # ── preview & save ───────────────────────────────────────

    def _refresh_preview(self):
        cnt = self.decoder.received_count
        if cnt == 0 or cnt == self._last_preview_cnt:
            return
        self._last_preview_cnt = cnt
        if self._recovery_done:
            data = self.decoder.assemble_partial()
        else:
            data = self.decoder.assemble_partial()
        if not data:
            return
        px = QPixmap()
        if px.loadFromData(data):
            self.img_label.setPixmap(px.scaled(
                self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _save_image(self):
        if self.decoder.received_count == 0: return
        data = self.decoder.assemble_partial()
        if not data: return
        ext = "*.jpg" if self.decoder.file_type == 1 else "*.webp" if self.decoder.file_type == 2 else "*.*"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить", f"received{ext[1:]}",
            f"Image ({ext});;Все файлы (*)")
        if not path: return
        with open(path, "wb") as f:
            f.write(data)
        self._append_log(f"Сохранено: <b>{path}</b> ({len(data)} Б)")

    # ── cleanup ──────────────────────────────────────────────

    def closeEvent(self, event):
        for w in (self.serial_worker, self.tcp_worker, self.sim_worker):
            if w and w.isRunning():
                w.stop(); w.wait(2000)
        event.accept()


def main():
    app = QApplication(sys.argv); app.setStyle("Fusion")
    apply_theme(app, load_theme())
    win = MainWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
