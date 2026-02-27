#!/usr/bin/env python3
"""LorettLink — Приёмник с erasure-FEC (Reed-Solomon).

Принимает FEC-блоки по COM (USB-UART от радиомодуля) или TCP.
Парсит поток: FEC-пакеты 256 байт + TELEM 10 байт.
Когда получено >= K любых блоков из N, восстанавливает файл Reed-Solomon декодером 1:1.
"""

import sys
import time
import socket
from pathlib import Path
from typing import Optional

# Общая папка shared (erasure_fec, protocol, theme_manager)
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

from erasure_fec import FECPacket, ErasureDecoder
from protocol import StreamParser, TelemInfo
from theme_manager import Theme, load_theme, save_theme, apply_theme

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

UI_PATH = Path(__file__).parent / "mainwindow.ui"


# ═══════════════════════════════════════════════════════════════
#  Воркер чтения COM-порта (приём от радиомодуля / USB-UART)
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
        """Открытие порта, цикл чтения порциями по 1024 байт, при ошибке — сигнал и закрытие."""
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
        """Выход из цикла run()."""
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  Воркер TCP-сервера (приём от наземного передатчика по сети)
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
        """Слушаем порт, принимаем одного клиента, читаем данные до отключения, затем снова accept."""
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
        """Остановка цикла и закрытие сокета."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
#  Вспомогательные функции
# ═══════════════════════════════════════════════════════════════

def _make_card(title, description=""):
    """Карточка с заголовком и опциональным описанием для вкладки «Настройки»."""
    card = QFrame(); card.setProperty("class", "card")
    lay = QVBoxLayout(card); lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(12)
    h = QLabel(title); h.setProperty("class", "heading"); lay.addWidget(h)
    if description:
        d = QLabel(description); d.setProperty("class", "description")
        d.setWordWrap(True); lay.addWidget(d)
    return card, lay


# ═══════════════════════════════════════════════════════════════
#  Главное окно приёмника
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Окно: COM/TCP, телеметрия, матрица блоков, превью изображения, лог, сохранение файла."""

    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_PATH), self)

        self.parser = StreamParser()   # разбор потока на FEC- и TELEM-пакеты
        self.decoder = ErasureDecoder()  # накопление блоков и RS-декодирование
        self.serial_worker: Optional[SerialWorker] = None
        self.tcp_worker: Optional[TcpServerWorker] = None
        self._start_time: Optional[float] = None  # для расчёта скорости приёма
        self._bytes_rx = 0
        self._last_preview_cnt = 0   # чтобы не перерисовывать превью без изменений
        self._recovery_done = False  # флаг: файл уже восстановлен RS-декодером

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

        root.addStretch()
        return page

    def _on_theme_changed(self):
        theme = Theme(self.cb_theme.currentData())
        save_theme(theme); apply_theme(QApplication.instance(), theme)

    def _connect_signals(self):
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._toggle_serial)
        self.btn_tcp.clicked.connect(self._toggle_tcp)
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

    # ── packet processing ────────────────────────────────────

    def _reset_state(self):
        """Сброс парсера, декодера, матрицы и превью при новом изображении или переподключении."""
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
        """Сырые байты от COM/TCP: передаём в парсер, обрабатываем FEC и TELEM."""
        self._bytes_rx += len(raw)
        if self._start_time is None:
            self._start_time = time.time()
        for obj in self.parser.feed(raw):
            if isinstance(obj, FECPacket):
                self._handle_fec(obj)
            elif isinstance(obj, TelemInfo):
                self._handle_telem(obj)

    def _handle_fec(self, pkt: FECPacket):
        """Добавить FEC-пакет в декодер, обновить матрицу/прогресс, при достаточном числе блоков — восстановить файл."""
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
        """Запуск Reed-Solomon декодирования: из любых K из N блоков восстанавливаем файл."""
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
        """Обновление полей телеметрии (RSSI, SNR, мощность TX) и полоски RSSI."""
        self.lbl_rssi.setText(f"RSSI: {t.rssi} дБм")
        self.lbl_snr.setText(f"SNR: {t.snr / 4:.1f} дБ")
        self.lbl_txpower.setText(f"TX: {t.tx_power} дБм")
        self.bar_rssi.setValue(max(t.rssi, -140))

    # ── preview & save ───────────────────────────────────────

    def _refresh_preview(self):
        """Периодически (по таймеру) обновлять превью: собрать данные из декодера и отобразить как изображение."""
        cnt = self.decoder.received_count
        if cnt == 0 or cnt == self._last_preview_cnt:
            return
        self._last_preview_cnt = cnt
        data = self.decoder.assemble_partial()
        if not data:
            return
        px = QPixmap()
        if px.loadFromData(data):
            self.img_label.setPixmap(px.scaled(
                self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _save_image(self):
        """Сохранить восстановленные данные в файл через диалог выбора имени."""
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
        for w in (self.serial_worker, self.tcp_worker):
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
