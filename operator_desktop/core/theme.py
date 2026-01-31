from typing import Dict, List

from PyQt6 import QtGui


class Theme:
    def __init__(self, name: str, colors: Dict[str, str]):
        self.name = name
        self.colors = colors


THEMES = {
    "dark": Theme(
        "dark",
        {
            "bg_start": "#0d1117",
            "bg_end": "#151b24",
            "card": "#1a202c",
            "card_alt": "#202838",
            "border": "#2b3446",
            "text": "#e6edf6",
            "muted": "#9aa6b2",
            "accent": "#30d0a8",
            "accent_soft": "#1f564b",
            "danger": "#e05d5d",
            "glow": "#2fd6c0",
            "table_alt": "#1c2332",
        },
    ),
    "light": Theme(
        "light",
        {
            "bg_start": "#f3f5f9",
            "bg_end": "#e0e7f0",
            "card": "#ffffff",
            "card_alt": "#f5f7fb",
            "border": "#cfd6df",
            "text": "#1b2330",
            "muted": "#5c6774",
            "accent": "#1aa87a",
            "accent_soft": "#c6efe3",
            "danger": "#c94242",
            "glow": "#74d4bd",
            "table_alt": "#eef2f7",
        },
    ),
}


def choose_font(preferred: List[str]) -> str:
    try:
        available = set(QtGui.QFontDatabase.families())
    except Exception:
        try:
            available = set(QtGui.QFontDatabase().families())
        except Exception:
            return QtGui.QFont().defaultFamily()
    for name in preferred:
        if name in available:
            return name
    return QtGui.QFont().defaultFamily()


def select_font_for_language(language: str) -> str:
    preferred = ["Space Grotesk", "IBM Plex Sans", "Segoe UI"]
    if language == "zh":
        preferred = ["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC"] + preferred
    return choose_font(preferred)


def build_stylesheet(theme: Theme) -> str:
    c = theme.colors
    return f"""
    QWidget {{
        color: {c["text"]};
        font-size: 13px;
    }}
    QFrame#Sidebar {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QFrame#TopBar {{
        background: {c["card_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
    }}
    QDialog {{
        background: {c["card"]};
    }}
    QFrame#ConnectionBanner {{
        background: {c["card_alt"]};
        border: 1px solid {c["danger"]};
        border-radius: 12px;
    }}
    QFrame#Card {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QFrame#SettingsCard {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    QLabel#Muted {{
        color: {c["muted"]};
    }}
    QLabel#ProfileStatus {{
        color: {c["muted"]};
    }}
    QLabel#ProfileStatus[status="error"] {{
        color: {c["danger"]};
    }}
    QLabel#ProfileStatus[status="success"] {{
        color: {c["accent"]};
    }}
    QLabel#StatusBadge {{
        padding: 4px 10px;
        border-radius: 10px;
        font-weight: 600;
    }}
    QLabel#StatusBadge[status="online"] {{
        background: {c["accent_soft"]};
        border: 1px solid {c["accent"]};
        color: {c["accent"]};
    }}
    QLabel#StatusBadge[status="offline"] {{
        background: {c["danger"]};
        border: 1px solid {c["danger"]};
        color: #ffffff;
    }}
    QLabel#StatusBadge[status="unknown"] {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        color: {c["muted"]};
    }}
    QLabel#OperatorBadge {{
        padding: 4px 10px;
        border-radius: 10px;
        font-weight: 600;
        background: {c["card"]};
        border: 1px solid {c["border"]};
        color: {c["text"]};
    }}
    QLabel#ConnectionBannerText {{
        color: {c["text"]};
    }}
    QLabel#ConnectionBannerIcon {{
        color: {c["danger"]};
        font-weight: 700;
    }}
    QLabel#BrandIcon {{
        font-size: 18px;
        font-weight: 700;
        color: {c["text"]};
        background: transparent;
        border: none;
    }}
    QLabel#SectionTitle {{
        font-weight: 700;
        font-size: 13px;
        color: {c["muted"]};
        letter-spacing: 0.6px;
    }}
    QPushButton {{
        padding: 8px 14px;
        border-radius: 10px;
        border: 1px solid {c["border"]};
        background: {c["card_alt"]};
    }}
    QPushButton:hover {{
        border-color: {c["accent"]};
    }}
    QPushButton:focus {{
        border-color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background: {c["card"]};
    }}
    QPushButton[variant="primary"] {{
        background: {c["accent"]};
        color: #0b121a;
        border: none;
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {c["glow"]};
    }}
    QPushButton[variant="primary"]:pressed {{
        background: {c["accent"]};
    }}
    QPushButton[variant="ghost"] {{
        background: transparent;
        border: 1px solid {c["border"]};
    }}
    QPushButton[variant="ghost"]:hover {{
        background: {c["card_alt"]};
        border-color: {c["accent"]};
    }}
    QPushButton[variant="ghost"]:checked {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
        color: {c["accent"]};
        font-weight: 600;
    }}
    QPushButton[variant="ghost"]:pressed {{
        background: {c["accent_soft"]};
    }}
    QPushButton[variant="danger"] {{
        background: {c["danger"]};
        color: #ffffff;
        border: none;
    }}
    QPushButton[variant="danger"]:hover {{
        background: {c["danger"]};
    }}
    QPushButton[variant="danger"]:pressed {{
        background: {c["danger"]};
    }}
    QPushButton[variant="island"] {{
        background: {c["card_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        font-weight: 600;
    }}
    QPushButton[variant="island"]:hover {{
        background: {c["card"]};
        border-color: {c["accent"]};
    }}
    QPushButton[variant="island"]:pressed {{
        background: {c["card_alt"]};
    }}
    QPushButton:disabled {{
        background: {c["border"]};
        color: {c["muted"]};
        border: none;
    }}
    QToolButton {{
        border: 1px solid transparent;
        padding: 4px;
        border-radius: 8px;
    }}
    QToolButton:hover {{
        background: {c["card_alt"]};
        border-color: {c["border"]};
    }}
    QToolButton:pressed {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
    }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QTextBrowser {{
        background: {c["card_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 10px;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus {{
        border-color: {c["accent"]};
    }}
    QTableWidget {{
        background: {c["card"]};
        alternate-background-color: {c["table_alt"]};
        border: 1px solid {c["border"]};
        gridline-color: {c["border"]};
    }}
    QTableWidget QAbstractScrollArea::viewport {{
        background: {c["card"]};
    }}
    QHeaderView::section {{
        background: {c["card_alt"]};
        border: none;
        padding: 8px;
        font-weight: 600;
    }}
    QHeaderView {{
        background: {c["card_alt"]};
    }}
    QTableCornerButton::section {{
        background: {c["card_alt"]};
        border: none;
    }}
    QTableWidget::item {{
        padding: 4px;
    }}
    QTableWidget::item:hover {{
        background: {c["card_alt"]};
    }}
    QTableWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QMenu {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        padding: 6px;
    }}
    QMenu::item {{
        color: {c["text"]};
        padding: 6px 10px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {c["accent_soft"]};
    }}
    QMenu::item:disabled {{
        color: {c["muted"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c["border"]};
        margin: 4px 2px;
    }}
    QListWidget {{
        background: transparent;
        border: none;
    }}
    QListWidget::item {{
        color: {c["text"]};
    }}
    QListWidget::item:hover {{
        background: {c["card_alt"]};
    }}
    QListWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QAbstractItemView::item:focus {{
        outline: none;
    }}
    QListWidget::item {{
        padding: 6px 4px;
        border-bottom: 1px dashed {c["border"]};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QCheckBox::indicator:unchecked {{
        border: 1px solid {c["border"]};
        background: {c["card_alt"]};
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{
        border: 1px solid {c["accent"]};
        background: {c["accent"]};
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 6px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]};
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QComboBox QAbstractItemView {{
        background: {c["card"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        selection-background-color: {c["accent_soft"]};
        selection-color: {c["text"]};
        outline: 0;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 8px;
    }}
    QComboBox {{
        padding: 6px 28px 6px 10px;
    }}
    QComboBox::drop-down {{
        width: 26px;
        border-left: 1px solid {c["border"]};
        background: {c["card_alt"]};
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
    }}
    QComboBox::down-arrow {{
        width: 9px;
        height: 9px;
    }}
    QComboBox QAbstractItemView {{
        border-radius: 10px;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 26px;
        border-radius: 6px;
    }}
    """
