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
    QFrame#Card {{
        background: {c["card"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QLabel#Muted {{
        color: {c["muted"]};
    }}
    QLabel#BrandIcon {{
        background: {c["accent_soft"]};
        border: 1px solid {c["accent"]};
        border-radius: 14px;
        font-size: 18px;
        font-weight: 700;
        color: {c["text"]};
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
    QPushButton[variant="primary"] {{
        background: {c["accent"]};
        color: #0b121a;
        border: none;
        font-weight: 600;
    }}
    QPushButton[variant="ghost"] {{
        background: transparent;
        border: 1px solid {c["border"]};
    }}
    QPushButton[variant="danger"] {{
        background: {c["danger"]};
        color: #ffffff;
        border: none;
    }}
    QPushButton:disabled {{
        background: {c["border"]};
        color: {c["muted"]};
        border: none;
    }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
        background: {c["card_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 10px;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {c["accent"]};
    }}
    QTableWidget {{
        background: {c["card"]};
        alternate-background-color: {c["table_alt"]};
        border: 1px solid {c["border"]};
        gridline-color: {c["border"]};
    }}
    QHeaderView::section {{
        background: {c["card_alt"]};
        border: none;
        padding: 8px;
        font-weight: 600;
    }}
    QTableWidget::item {{
        padding: 4px;
    }}
    QTableWidget::item:selected {{
        background: {c["accent_soft"]};
    }}
    QListWidget {{
        background: transparent;
        border: none;
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
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
