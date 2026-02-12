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
            "bg_start": "#090d14",
            "bg_end": "#0b111b",
            "card": "rgba(18, 24, 34, 0.58)",
            "card_alt": "rgba(24, 30, 42, 0.5)",
            "card_strong": "rgba(18, 24, 34, 0.78)",
            "border": "rgba(255, 255, 255, 0.14)",
            "border_strong": "rgba(255, 255, 255, 0.24)",
            "text": "#eef3ff",
            "muted": "#9eb0c3",
            "accent": "#0091FF",
            "accent_2": "#4db8ff",
            "accent_3": "#0077d9",
            "accent_soft": "rgba(0, 145, 255, 0.18)",
            "accent_glow": "rgba(77, 184, 255, 0.45)",
            "good": "#2dd4bf",
            "warn": "#f6c970",
            "danger": "#ff6b6b",
            "glow": "#0091FF",
            "table_alt": "rgba(255, 255, 255, 0.035)",
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
            stop:0 rgba(24, 30, 44, 0.70),
            stop:0.52 rgba(14, 20, 30, 0.78),
            stop:1 rgba(12, 18, 28, 0.90));
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
    QLabel#CardSectionTitle {{
        font-size: 14px;
        font-weight: 650;
    }}
    QLabel#CardSectionLead {{
        font-size: 12px;
        color: {c["muted"]};
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
            stop:0 rgba(24, 30, 44, 0.66),
            stop:1 rgba(14, 20, 30, 0.78));
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
            stop:0 rgba(24, 30, 44, 0.68),
            stop:1 rgba(14, 20, 30, 0.80));
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QFrame#HeroCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(26, 34, 48, 0.72),
            stop:1 rgba(16, 22, 34, 0.88));
        border: 1px solid {c["border_strong"]};
        border-radius: 24px;
    }}
    QFrame#DrawerCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(20, 26, 38, 0.76),
            stop:1 rgba(12, 18, 28, 0.88));
        border: 1px solid {c["border"]};
        border-radius: 20px;
    }}
    QFrame#Card {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(24, 32, 46, 0.62),
            stop:1 rgba(14, 20, 30, 0.82));
        border: 1px solid {c["border"]};
        border-radius: 20px;
    }}
    QFrame#SettingsCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(24, 30, 44, 0.64),
            stop:1 rgba(12, 18, 28, 0.84));
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QWidget#LocalDesktopRoot {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["bg_start"]},
            stop:1 {c["bg_end"]});
    }}
    QScrollArea#TagArea {{
        background: transparent;
    }}
    QScrollArea#PageScroll {{
        background: transparent;
        border: none;
    }}
    QWidget#PageScrollViewport,
    QWidget#PageScrollContent {{
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
            stop:0 {c["accent"]}, stop:1 {c["accent_2"]});
        color: #04101f;
        border: 1px solid rgba(255, 255, 255, 0.08);
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent_3"]}, stop:1 {c["accent_2"]});
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
    QPushButton[variant="soft"] {{
        background: rgba(255, 255, 255, 0.05);
        color: {c["text"]};
        border: 1px solid {c["border"]};
        font-weight: 500;
    }}
    QPushButton[variant="soft"]:hover {{
        background: rgba(255, 255, 255, 0.1);
        border-color: {c["border_strong"]};
    }}
    QPushButton[variant="soft"]:pressed {{
        background: rgba(255, 255, 255, 0.07);
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
        background: rgba(255, 255, 255, 0.08);
        color: {c["muted"]};
        border: 1px solid rgba(255, 255, 255, 0.06);
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
            stop:0 rgba(12, 18, 28, 0.66),
            stop:1 rgba(10, 14, 22, 0.82));
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
        background: rgba(10, 14, 22, 0.68);
        border-radius: 16px;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus {{
        border-color: {c["accent"]};
    }}
    QTextBrowser[flat="true"] {{
        background: transparent;
        border: none;
        padding: 0;
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
        background: rgba(255, 255, 255, 0.06);
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
    QLabel#TableOverflowHint {{
        color: {c["muted"]};
        font-size: 11px;
        padding: 2px 2px 0 2px;
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
    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 2px 6px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(255, 255, 255, 0.34);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
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
    QLabel#InlineStatus {{
        color: {c["muted"]};
        padding: 2px 0;
    }}
    QLabel#InlineStatus[state="ok"] {{
        color: {c["good"]};
    }}
    QLabel#InlineStatus[state="warn"] {{
        color: {c["warn"]};
    }}
    QLabel#InlineStatus[state="error"] {{
        color: {c["danger"]};
    }}
    QLabel#InlineHint {{
        color: {c["muted"]};
        font-size: 12px;
    }}
    QLabel#TagText {{
        font-size: 11px;
        font-weight: 600;
        color: {c["text"]};
        padding: 2px 8px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.05);
    }}
    QGroupBox {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(18, 24, 34, 0.56),
            stop:1 rgba(12, 18, 28, 0.76));
        border: 1px solid {c["border"]};
        border-radius: 14px;
        margin-top: 14px;
        padding-top: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c["text"]};
        font-weight: 600;
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


def build_dialog_stylesheet(theme: Theme) -> str:
    c = theme.colors
    return f"""
    QMessageBox {{
        background: {c["card_strong"]};
        color: {c["text"]};
    }}
    QMessageBox QLabel {{
        color: {c["text"]};
    }}
    QMessageBox QPushButton {{
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 7px 12px;
        min-width: 72px;
    }}
    QMessageBox QPushButton:hover {{
        border-color: {c["border_strong"]};
        background: rgba(255, 255, 255, 0.1);
    }}
    QMessageBox QPushButton:pressed {{
        background: rgba(255, 255, 255, 0.06);
    }}
    """
