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
            "bg_start": "#0b0f16",
            "bg_end": "#0c1422",
            "card": "rgba(20, 26, 38, 0.62)",
            "card_alt": "rgba(18, 24, 36, 0.72)",
            "card_strong": "rgba(14, 20, 30, 0.86)",
            "border": "rgba(255, 255, 255, 0.12)",
            "border_strong": "rgba(255, 255, 255, 0.2)",
            "text": "#eef3ff",
            "muted": "#9fb0c3",
            "accent": "#0091FF",
            "accent_soft": "rgba(0, 145, 255, 0.18)",
            "accent_glow": "rgba(0, 145, 255, 0.45)",
            "danger": "#ff6b6b",
            "glow": "#0091FF",
            "table_alt": "rgba(255, 255, 255, 0.03)",
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
    preferred = ["SF Pro Display", "SF Pro Text", "Segoe UI Variable", "Segoe UI"]
    if language == "zh":
        preferred = [
            "PingFang SC",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Noto Sans CJK SC",
        ] + preferred
    return choose_font(preferred)


def build_stylesheet(theme: Theme) -> str:
    c = theme.colors
    return f"""
    QWidget {{
        color: {c["text"]};
        font-size: 12px;
        font-family: "SF Pro Display", "Segoe UI Variable", "Segoe UI";
    }}
    QFrame#WindowFrame {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(24, 30, 42, 0.72),
            stop:1 rgba(12, 18, 28, 0.88));
        border: 1px solid {c["border_strong"]};
        border-radius: 30px;
    }}
    QFrame#ChromeBar {{
        background: rgba(16, 20, 30, 0.6);
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QLabel#ChromeTitle {{
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#ChromeSubtitle {{
        color: {c["muted"]};
        font-size: 10px;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    QLabel#ChromeDot,
    QToolButton#ChromeDot {{
        border-radius: 5px;
        border: 1px solid rgba(0, 0, 0, 0.25);
        background: rgba(255, 255, 255, 0.2);
    }}
    QToolButton#ChromeDot {{
        padding: 0px;
    }}
    QLabel#ChromeDot[dot="close"],
    QToolButton#ChromeDot[dot="close"] {{
        background: #ff5f57;
    }}
    QLabel#ChromeDot[dot="minimize"],
    QToolButton#ChromeDot[dot="minimize"] {{
        background: #febc2e;
    }}
    QLabel#ChromeDot[dot="zoom"],
    QToolButton#ChromeDot[dot="zoom"] {{
        background: #28c840;
    }}
    QLabel#PageTitle {{
        font-size: 24px;
        font-weight: 700;
    }}
    QLabel#PageSubtitle {{
        color: {c["muted"]};
        font-size: 11px;
    }}
    QLabel#CardTitle {{
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#ClientCardTitle {{
        font-size: 24px;
        font-weight: 700;
    }}
    QLabel#DetailLabel {{
        color: {c["muted"]};
        font-size: 13px;
    }}
    QLabel#DetailValue {{
        font-weight: 600;
        font-size: 13px;
    }}
    QLabel#BrowserChip {{
        padding: 4px 10px;
        border-radius: 10px;
        border: 1px solid {c["border"]};
        background: rgba(255, 255, 255, 0.06);
        font-size: 11px;
        font-weight: 600;
    }}
    QFrame#Sidebar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(26, 34, 48, 0.62),
            stop:1 rgba(14, 20, 30, 0.72));
        border: 1px solid {c["border"]};
        border-radius: 22px;
    }}
    QFrame#SidebarHeader {{
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QLabel#SidebarSection {{
        color: {c["muted"]};
        font-size: 10px;
        letter-spacing: 1.4px;
        text-transform: uppercase;
    }}
    QFrame#TopBar {{
        background: {c["card_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QDialog {{
        background: {c["card_strong"]};
    }}
    QFrame#ConnectionBanner {{
        background: rgba(40, 16, 20, 0.68);
        border: 1px solid rgba(255, 107, 107, 0.5);
        border-radius: 14px;
    }}
    QFrame#ToolbarCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(24, 30, 44, 0.72),
            stop:1 rgba(14, 20, 30, 0.82));
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QFrame#HeroCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(26, 34, 48, 0.74),
            stop:1 rgba(16, 22, 34, 0.9));
        border: 1px solid {c["border_strong"]};
        border-radius: 24px;
    }}
    QFrame#DrawerCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(20, 26, 38, 0.78),
            stop:1 rgba(12, 18, 28, 0.9));
        border: 1px solid {c["border"]};
        border-radius: 20px;
    }}
    QFrame#Card {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(26, 32, 46, 0.64),
            stop:1 rgba(14, 20, 30, 0.82));
        border: 1px solid {c["border"]};
        border-radius: 20px;
    }}
    QFrame#SettingsCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(24, 30, 44, 0.66),
            stop:1 rgba(12, 18, 28, 0.86));
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QScrollArea#TagArea {{
        background: transparent;
    }}
    QWidget#TagContainer {{
        background: transparent;
    }}
    QLabel#Muted {{
        color: {c["muted"]};
    }}
    QLabel#TagHint {{
        color: {c["muted"]};
        font-size: 13px;
    }}
    QLabel#InfoPill {{
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid {c["border"]};
        color: {c["muted"]};
        font-size: 11px;
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
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(0, 145, 255, 0.95),
            stop:1 rgba(78, 187, 255, 0.92));
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 16px;
    }}
    QLabel#StatusDot {{
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.2);
    }}
    QLabel#StatusDot[status="online"] {{
        background: {c["accent"]};
    }}
    QLabel#StatusDot[status="offline"] {{
        background: {c["danger"]};
    }}
    QLabel#SectionTitle {{
        font-weight: 700;
        font-size: 11px;
        color: {c["muted"]};
        letter-spacing: 0.6px;
    }}
    QPushButton {{
        padding: 8px 14px;
        border-radius: 12px;
        border: 1px solid {c["border"]};
        background: rgba(255, 255, 255, 0.04);
    }}
    QPushButton:hover {{
        border-color: rgba(255, 255, 255, 0.2);
        background: rgba(255, 255, 255, 0.08);
    }}
    QPushButton:focus {{
        border-color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background: rgba(255, 255, 255, 0.04);
    }}
    QPushButton[variant="primary"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]}, stop:1 rgba(78, 187, 255, 0.95));
        color: #04101f;
        border: none;
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {c["accent_glow"]};
    }}
    QPushButton[variant="primary"]:pressed {{
        background: {c["accent"]};
    }}
    QPushButton[variant="ghost"] {{
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid {c["border"]};
    }}
    QPushButton[variant="ghost"]:hover {{
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.2);
    }}
    QPushButton[variant="ghost"]:checked {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
        color: {c["text"]};
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
        background: rgba(255, 255, 255, 0.05);
        color: {c["text"]};
        border: 1px solid {c["border"]};
        font-weight: 600;
    }}
    QPushButton[variant="island"]:hover {{
        background: rgba(255, 255, 255, 0.08);
        border-color: {c["accent"]};
    }}
    QPushButton[variant="island"]:pressed {{
        background: rgba(255, 255, 255, 0.04);
    }}
    QPushButton[nav="true"],
    QPushButton[variant="nav"] {{
        background: transparent;
        border: 1px solid transparent;
        text-align: left;
        padding: 8px 12px;
        border-radius: 12px;
    }}
    QPushButton[nav="true"]:hover,
    QPushButton[variant="nav"]:hover {{
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(255, 255, 255, 0.12);
    }}
    QPushButton[nav="true"]:checked,
    QPushButton[variant="nav"]:checked {{
        background: {c["accent_soft"]};
        border-color: rgba(0, 145, 255, 0.45);
        color: {c["text"]};
        font-weight: 600;
    }}
    QPushButton#DangerText {{
        color: {c["danger"]};
        background: transparent;
        border: none;
        padding: 6px 8px;
        text-align: left;
    }}
    QPushButton#DangerText:hover {{
        background: rgba(255, 107, 107, 0.12);
        border-radius: 10px;
    }}
    QPushButton#NameLink {{
        background: transparent;
        border: none;
        padding: 0;
        text-align: left;
        font-weight: 600;
    }}
    QPushButton#NameLink:hover {{
        color: {c["accent"]};
    }}
    QPushButton:disabled {{
        background: {c["border"]};
        color: {c["muted"]};
        border: none;
    }}
    QToolButton {{
        border: 1px solid transparent;
        padding: 4px;
        border-radius: 10px;
    }}
    QToolButton[variant="icon"] {{
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid transparent;
        padding: 4px;
        border-radius: 10px;
    }}
    QToolButton[variant="icon"]:hover {{
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.12);
    }}
    QToolButton[nav="true"] {{
        background: transparent;
        border: 1px solid transparent;
        padding: 8px 12px;
        border-radius: 12px;
        text-align: left;
    }}
    QToolButton[nav="true"]:hover {{
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(255, 255, 255, 0.12);
    }}
    QToolButton:hover {{
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.12);
    }}
    QToolButton:pressed {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
    }}
    QFrame#SessionControlBar {{
        background: rgba(16, 20, 30, 0.86);
        border-bottom: 1px solid {c["border"]};
    }}
    QFrame#SessionControls {{
        background: rgba(20, 26, 36, 0.72);
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    QFrame#SessionControls QToolButton {{
        color: {c["text"]};
        border: none;
        padding: 4px;
    }}
    QFrame#SessionControls QToolButton:hover {{
        background: rgba(255, 255, 255, 0.12);
        border-radius: 8px;
    }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QTextBrowser {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(12, 16, 26, 0.62),
            stop:1 rgba(10, 14, 22, 0.78));
        border: 1px solid {c["border"]};
        border-radius: 14px;
        padding: 8px 12px;
    }}
    QComboBox#StatusSelect {{
        padding-right: 28px;
        min-width: 150px;
        font-size: 13px;
    }}
    QComboBox#StatusSelect::drop-down {{
        border: none;
        width: 22px;
    }}
    QLineEdit#SearchInput {{
        padding-left: 34px;
        background: rgba(10, 14, 22, 0.6);
        border-radius: 16px;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus {{
        border-color: {c["accent"]};
    }}
    QTableWidget {{
        background: transparent;
        alternate-background-color: {c["table_alt"]};
        border: none;
        gridline-color: transparent;
    }}
    QTableWidget QAbstractScrollArea::viewport {{
        background: transparent;
    }}
    QHeaderView::section {{
        background: rgba(255, 255, 255, 0.05);
        border: none;
        padding: 8px 10px;
        font-weight: 600;
    }}
    QHeaderView {{
        background: transparent;
    }}
    QTableCornerButton::section {{
        background: rgba(255, 255, 255, 0.04);
        border: none;
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QTableWidget::item:hover {{
        background: rgba(255, 255, 255, 0.06);
    }}
    QTableWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QSplitter::handle {{
        background: rgba(255, 255, 255, 0.06);
        border-radius: 4px;
    }}
    QSplitter::handle:hover {{
        background: rgba(255, 255, 255, 0.12);
    }}
    QMenu {{
        background: {c["card_alt"]};
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
        padding: 6px 4px;
        border-bottom: 1px dashed {c["border"]};
    }}
    QListWidget::item:hover {{
        background: rgba(255, 255, 255, 0.06);
    }}
    QListWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QFrame#TagRow {{
        border: 1px dashed {c["border"]};
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.04);
    }}
    QFrame#TagRow:hover {{
        background: rgba(255, 255, 255, 0.06);
    }}
    QLabel#TagDot {{
        border-radius: 5px;
    }}
    QListWidget#TagList {{
        background: transparent;
    }}
    QListWidget#TagList::item {{
        border: 1px dashed {c["border"]};
        border-radius: 12px;
        padding: 6px 10px;
        margin-bottom: 6px;
        background: rgba(255, 255, 255, 0.04);
    }}
    QListWidget#TagList::item:hover {{
        background: rgba(255, 255, 255, 0.06);
    }}
    QListWidget#TagList::item:selected {{
        background: rgba(255, 255, 255, 0.04);
        color: {c["text"]};
    }}
    QListWidget#TagList::indicator {{
        width: 14px;
        height: 14px;
    }}
    QListWidget#TagList::indicator:unchecked {{
        border: 1px solid {c["border"]};
        background: rgba(255, 255, 255, 0.06);
        border-radius: 4px;
    }}
    QListWidget#TagList::indicator:checked {{
        border: 1px solid {c["accent"]};
        background: {c["accent"]};
        border-radius: 4px;
    }}
    QAbstractItemView::item:focus {{
        outline: none;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QCheckBox::indicator:unchecked {{
        border: 1px solid {c["border"]};
        background: rgba(255, 255, 255, 0.06);
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{
        border: 1px solid {c["accent"]};
        background: {c["accent"]};
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 6px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(255, 255, 255, 0.34);
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
        background: rgba(255, 255, 255, 0.06);
        border-top-right-radius: 12px;
        border-bottom-right-radius: 12px;
    }}
    QComboBox::down-arrow {{
        width: 9px;
        height: 9px;
    }}
    QComboBox QAbstractItemView {{
        border-radius: 12px;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 26px;
        border-radius: 6px;
    }}
    QTabWidget::pane {{
        border: none;
        margin-top: 8px;
    }}
    QTabBar::tab {{
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid {c["border"]};
        padding: 6px 16px;
        border-radius: 12px;
        margin-right: 6px;
        min-height: 26px;
    }}
    QTabBar::tab:selected {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
        color: {c["text"]};
        font-weight: 600;
    }}
    QTabBar::tab:hover {{
        border-color: rgba(255, 255, 255, 0.2);
    }}
    QPushButton::menu-indicator {{
        image: none;
        width: 0px;
    }}
    QToolTip {{
        background: rgba(16, 20, 30, 0.92);
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 6px 8px;
    }}
    """
