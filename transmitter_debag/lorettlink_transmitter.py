#!/usr/bin/env python3
"""LorettLink — Передатчик с erasure-FEC (Reed-Solomon).

Кодирует JPEG/WebP в K data + M parity блоков и отправляет broadcast по TCP.
Используется как наземный тестовый передатчик (подключение к приёмнику по IP:порт).
"""

import sys
import time
import os
import random
import socket
from pathlib import Path
from typing import Optional

# Подключаем общую папку shared (erasure_fec, protocol, theme_manager)
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
#  Воркер передачи FEC-пакетов по TCP
# ═══════════════════════════════════════════════════════════════

class FECTransmitWorker(QThread):
    # Сигналы для обновления UI из потока
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    encoding_done = pyqtSignal(int, int, int)   # image_id, k_data, n_total
    packet_sent = pyqtSignal(int, bool)         # block_id, is_parity
    transfer_done = pyqtSignal(bool, float)     # успех, время в секундах
    log_message = pyqtSignal(str)

    def __init__(self, host: str, port: int, file_path: str,
                 callsign: str, image_id: int, delay_ms: int,
                 fec_ratio: float, drop_percent: float = 0.0, tx_power: int = 33):
        super().__init__()
        self.host = host
        self.port = port
        self.file_path = file_path
        self.callsign = callsign
        self.image_id = image_id
        self.delay_ms = delay_ms
        self.fec_ratio = fec_ratio
        self.drop_percent = max(0.0, min(100.0, drop_percent))  # симуляция потерь, %
        self.tx_power = tx_power
        self._running = False

    def run(self):
        """Подключение по TCP, FEC-кодирование файла, отправка пакетов."""
        self._running = True
        sock = None
        t0 = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.host, self.port))
            self.connected.emit()

            # Кодируем файл в K data + M parity блоков (Reed-Solomon)
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
            if self.drop_percent > 0:
                self.log_message.emit(
                    f"Пропуск блоков: {self.drop_percent:.0f}% (случайный порядок)")

            for pkt in packets:
                if not self._running:
                    return
                # Случайный пропуск блока (симуляция потерь в эфире)
                if self.drop_percent > 0 and random.random() * 100.0 < self.drop_percent:
                    continue
                # Каждые 64 блока вставляем телеметрию (RSSI/SNR) для совместимости с парсером приёмника
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
        """Остановка цикла передачи по запросу пользователя."""
        self._running = False


# ═══════════════════════════════════════════════════════════════
#  Вспомогательные функции
# ═══════════════════════════════════════════════════════════════

def _make_card(title, description=""):
    """Создаёт карточку (QFrame) с заголовком и опциональным описанием для вкладки настроек."""
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
#  Главное окно передатчика
# ═══════════════════════════════════════════════════════════════

class TransmitterWindow(QMainWindow):
    """Окно приложения: выбор файла, настройки FEC/TCP, матрица блоков, лог."""

    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_PATH), self)

        self._worker: Optional[FECTransmitWorker] = None
        self._n_total = 0      # всего блоков (K + M)
        self._sent = 0        # отправлено пакетов
        self._image_counter = 0  # счётчик image_id для нескольких файлов подряд

        self._setup_tabs()
        self._connect_signals()
        self.splitter.setSizes([380, 480])
        self.progress.setProperty("class", "tx")
        self.img_label.setStyleSheet("")

    def _setup_tabs(self):
        """Вкладки: «Передача» (основной контент из .ui) и «Настройки»."""
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
        """Страница настроек: тема, callsign, FEC overhead, пропуск блоков, задержка."""
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
            "FEC overhead — доля parity-блоков. "
            "Пропуск блоков — доля пакетов, случайно не отправляемых (симуляция потерь). "
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
        r2.addWidget(QLabel("Пропуск блоков:"))
        self.sb_drop = QSpinBox()
        self.sb_drop.setRange(0, 80); self.sb_drop.setValue(0); self.sb_drop.setSuffix(" %")
        r2.addWidget(self.sb_drop)
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
    def _ts():
        """Время для лога в формате ЧЧ:ММ:СС."""
        return time.strftime("%H:%M:%S")

    def _log(self, msg):
        """Добавить строку в лог с временной меткой и прокруткой вниз."""
        self.log.append(f"<span style='color:#888'>{self._ts()}</span>  {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _browse_file(self):
        """Выбор файла изображения через диалог, предпросмотр в img_label."""
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
        """Кнопка «Подключить»/«Остановить»: запуск или остановка передачи."""
        if self._worker and self._worker.isRunning():
            self._worker.stop(); self._worker.wait(3000); return
        self._start_transfer()

    def _start_transfer(self):
        """Проверка файла, создание воркера, подключение сигналов и старт потока."""
        fp = self.edit_file.text()
        if not fp or not os.path.isfile(fp):
            self._log("<b style='color:#FFB74D'>Выберите файл</b>"); return
        self.matrix.clear_all(); self.progress.setValue(0); self._sent = 0

        cs = self.edit_callsign.text() if hasattr(self, "edit_callsign") else "LORETT"
        fec = self.sb_fec.value() / 100.0 if hasattr(self, "sb_fec") else 0.25
        drop = self.sb_drop.value() if hasattr(self, "sb_drop") else 0

        self._worker = FECTransmitWorker(
            self.edit_ip.text(), self.sb_port.value(), fp,
            cs, self._image_counter, self.sb_delay.value(), fec, drop)
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
        """После FEC-кодирования: задаём размер матрицы и прогресс-бара."""
        self._n_total = n
        self.matrix.set_total(n)
        self.progress.setMaximum(n)
        self._log(f"<b style='color:#64B5F6'>FEC</b> image={iid}  K={k}  N={n}")

    def _on_packet_sent(self, bid, is_parity):
        """Обновление ячейки матрицы (отправлен data или parity) и счётчика."""
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
        """Передача завершена: лог, при успехе — отметить все блоки как полученные, вернуть кнопки."""
        tag = "Передано" if ok else "Прервано"
        clr = "#81C784" if ok else "#e57373"
        self._log(f"<b style='color:{clr}'>{tag}</b> за {elapsed:.1f} с")
        if ok:
            for i in range(self._n_total):
                self.matrix.mark(i)
        self.btn_send.setEnabled(True); self.btn_connect.setText("Подключить")

    def closeEvent(self, event):
        """При закрытии окна останавливаем воркер передачи."""
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
