"""Централизованное управление темой оформления (тёмная/светлая)."""

from enum import Enum
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"


def load_theme() -> Theme:
    """Загрузить сохранённую тему из QSettings (по умолчанию — тёмная)."""
    value = QSettings("LorettLink", "LorettLink").value("ui/theme", "dark")
    try:
        return Theme(value)
    except ValueError:
        return Theme.DARK


def save_theme(theme: Theme) -> None:
    """Сохранить выбранную тему в QSettings."""
    QSettings("LorettLink", "LorettLink").setValue("ui/theme", theme.value)


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Применить тему: загрузить QSS из shared/styles/{theme}.qss и установить в приложение."""
    styles_dir = Path(__file__).parent / "styles"
    qss_path = styles_dir / f"{theme.value}.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    else:
        app.setStyleSheet("")
