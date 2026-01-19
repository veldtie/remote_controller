import importlib.util
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

APP_NAME = "Remote Controller Operator"
APP_VERSION = "0.1"
DEBUG_LOG_CREDENTIALS = True

LANGUAGE_NAMES = {
    "en": "English",
    "zh": "中文",
    "es": "Español",
    "ru": "Русский",
}

TRANSLATIONS = {
    "en": {
        "app_title": "Operator Console",
        "app_subtitle": "Remote Controller",
        "nav_main": "Clients",
        "nav_compiler": "Compiler",
        "nav_settings": "Settings",
        "nav_instructions": "Instructions",
        "top_status_label": "Status",
        "top_status_mock": "Mock",
        "top_refresh": "Refresh",
        "top_logout": "Log out",
        "login_title": "Welcome back",
        "login_subtitle": "Sign in with your operator account",
        "login_account_id": "Account ID",
        "login_password": "Password",
        "login_remember": "Remind me",
        "login_button": "Sign in",
        "login_hint": "Use your operator ID and password",
        "login_language": "Language",
        "login_error_empty": "Enter account ID and password.",
        "login_error_failed": "Authentication failed. Check your credentials.",
        "login_success": "Signed in.",
        "main_title": "Connected clients",
        "main_subtitle": "Manage active remote sessions",
        "main_search_placeholder": "Search by name, ID, region, or IP",
        "main_refresh_button": "Refresh",
        "main_add_mock_button": "Add mock",
        "main_last_sync": "Last sync",
        "main_last_sync_never": "Never",
        "main_status_ready": "Ready",
        "table_name": "Name",
        "table_id": "ID",
        "table_region": "Region",
        "table_ip": "IP",
        "table_storage": "Storage",
        "table_connect": "Connect",
        "button_storage": "Storage",
        "button_connect": "Connect",
        "button_connected": "Connected",
        "button_disconnect": "Disconnect",
        "region_na": "North America",
        "region_eu": "Europe",
        "region_apac": "Asia Pacific",
        "region_sa": "South America",
        "region_mea": "Middle East & Africa",
        "region_ru": "Russia & CIS",
        "log_title": "Session log",
        "log_empty": "No activity yet",
        "log_login": "Signed in as {account}",
        "log_logout": "Logged out",
        "log_connect": "Connecting to {client}",
        "log_connected": "Connected to {client}",
        "log_disconnect": "Disconnected from {client}",
        "log_storage_open": "Opened storage for {client}",
        "log_storage_download": "Queued download: {file}",
        "log_build_start": "Build started for {entry}",
        "log_build_done": "Build completed: {output}",
        "log_build_failed": "Build failed",
        "log_build_missing": "PyInstaller is not installed.",
        "storage_title": "Remote storage",
        "storage_subtitle": "Browse and download files from the remote device",
        "storage_remote_title": "Remote device",
        "storage_local_title": "Local downloads",
        "storage_path_label": "Path",
        "storage_go": "Go",
        "storage_up": "Up",
        "storage_refresh": "Refresh",
        "storage_action": "Action",
        "storage_size": "Size",
        "storage_download": "Download",
        "storage_empty": "No files found",
        "storage_local_empty": "No downloads yet",
        "storage_status_idle": "Idle",
        "storage_status_loading": "Loading...",
        "storage_status_ready": "Ready",
        "storage_close": "Close",
        "compiler_title": "EXE builder",
        "compiler_subtitle": "Package a Windows client from a selected folder",
        "compiler_source": "Source folder",
        "compiler_entry": "Entrypoint",
        "compiler_output_name": "Output name",
        "compiler_output_dir": "Output folder",
        "compiler_icon": "Icon (.ico)",
        "compiler_mode": "Build mode",
        "compiler_console": "Console",
        "compiler_mode_onefile": "Single file",
        "compiler_mode_onedir": "Folder",
        "compiler_console_show": "Show console",
        "compiler_console_hide": "Hide console",
        "compiler_browse": "Browse",
        "compiler_build": "Build",
        "compiler_clear": "Clear log",
        "compiler_status_idle": "Idle",
        "compiler_status_building": "Building...",
        "compiler_status_done": "Completed",
        "compiler_status_failed": "Failed",
        "compiler_log_placeholder": "Build output will appear here.",
        "settings_title": "Settings",
        "settings_subtitle": "Personalize your operator console",
        "settings_theme": "Theme",
        "settings_theme_dark": "Dark",
        "settings_theme_light": "Light",
        "settings_language": "Language",
        "settings_account": "Account",
        "settings_logout": "Log out",
        "settings_about": "About",
        "settings_about_body": "Operator Console for authorized remote support on Windows 10/11.",
        "settings_data": "Data",
        "settings_clear": "Clear saved data",
        "settings_clear_done": "Saved data cleared.",
        "instructions_title": "Instructions",
        "instructions_subtitle": "How to use the operator console",
        "instructions_body": """
            <h3>Quick start</h3>
            <ol>
              <li>Sign in with your operator account ID and password.</li>
              <li>Open Clients to view connected devices.</li>
              <li>Click Connect to start a remote session.</li>
              <li>Use Storage to browse and download files with permission.</li>
              <li>Use Compiler to build a Windows client from the selected folder.</li>
              <li>Open Settings to change theme or language, or log out.</li>
            </ol>
            <h3>Security &amp; compliance</h3>
            <ul>
              <li>Only access devices you are authorized to manage.</li>
              <li>Protect session tokens and IDs like passwords.</li>
              <li>Keep audit logs for support sessions.</li>
            </ul>
        """,
        "nav_teams": "Teams",
        "teams_title": "Teams",
        "teams_subtitle": "Manage operator teams and subscriptions",
        "teams_list_title": "Team list",
        "teams_select_hint": "Select a team to view details",
        "team_name": "Team name",
        "team_name_placeholder": "Enter team name",
        "team_status": "Status",
        "team_status_active": "Active",
        "team_status_expired": "Expired",
        "team_subscription": "Subscription ends",
        "team_renew": "Renew subscription",
        "team_members": "Team members",
        "team_member_name": "Name",
        "team_member_tag": "Tag",
        "team_member_clients": "Remote clients",
        "team_add_member": "Add member",
        "team_remove_member": "Remove member",
        "team_add_dialog_title": "Add team member",
        "team_add_name": "Name",
        "team_add_account_id": "Account ID",
        "team_add_password": "Password",
        "team_add_tag": "Role",
        "team_add_confirm": "Add",
        "team_add_cancel": "Cancel",
        "teams_no_members": "No members yet",
        "tag_operator": "Operator",
        "tag_administrator": "Administrator",
        "tag_moderator": "Moderator",
        "settings_role": "Role",
        "settings_role_operator": "Operator",
        "settings_role_administrator": "Administrator",
        "settings_role_moderator": "Moderator",
    },
}

TRANSLATIONS.update(
    {
        "zh": {
            "app_title": "操作员控制台",
            "app_subtitle": "远程控制",
            "nav_main": "客户端",
            "nav_compiler": "编译器",
            "nav_settings": "设置",
            "nav_instructions": "使用说明",
            "top_status_label": "状态",
            "top_status_mock": "模拟",
            "top_refresh": "刷新",
            "top_logout": "退出登录",
            "login_title": "欢迎回来",
            "login_subtitle": "使用操作员账户登录",
            "login_account_id": "账户 ID",
            "login_password": "密码",
            "login_remember": "记住我",
            "login_button": "登录",
            "login_hint": "请输入操作员 ID 和密码",
            "login_language": "语言",
            "login_error_empty": "请输入账户 ID 和密码。",
            "login_error_failed": "认证失败，请检查凭据。",
            "login_success": "已登录。",
            "main_title": "已连接客户端",
            "main_subtitle": "管理活动的远程会话",
            "main_search_placeholder": "按名称、ID、区域或 IP 搜索",
            "main_refresh_button": "刷新",
            "main_add_mock_button": "添加示例",
            "main_last_sync": "上次同步",
            "main_last_sync_never": "从未",
            "main_status_ready": "就绪",
            "table_name": "名称",
            "table_id": "ID",
            "table_region": "区域",
            "table_ip": "IP",
            "table_storage": "存储",
            "table_connect": "连接",
            "button_storage": "存储",
            "button_connect": "连接",
            "button_connected": "已连接",
            "button_disconnect": "断开",
            "region_na": "北美",
            "region_eu": "欧洲",
            "region_apac": "亚太",
            "region_sa": "南美",
            "region_mea": "中东和非洲",
            "region_ru": "俄罗斯与独联体",
            "log_title": "会话日志",
            "log_empty": "暂无活动",
            "log_login": "已登录：{account}",
            "log_logout": "已退出登录",
            "log_connect": "正在连接：{client}",
            "log_connected": "已连接：{client}",
            "log_disconnect": "已断开：{client}",
            "log_storage_open": "已打开存储：{client}",
            "log_storage_download": "已加入下载：{file}",
            "log_build_start": "开始构建：{entry}",
            "log_build_done": "构建完成：{output}",
            "log_build_failed": "构建失败",
            "log_build_missing": "未安装 PyInstaller。",
            "storage_title": "远程存储",
            "storage_subtitle": "浏览并下载远程设备文件",
            "storage_remote_title": "远程设备",
            "storage_local_title": "本地下载",
            "storage_path_label": "路径",
            "storage_go": "前往",
            "storage_up": "上级",
            "storage_refresh": "刷新",
            "storage_action": "操作",
            "storage_size": "大小",
            "storage_download": "下载",
            "storage_empty": "未找到文件",
            "storage_local_empty": "暂无下载",
            "storage_status_idle": "空闲",
            "storage_status_loading": "加载中...",
            "storage_status_ready": "就绪",
            "storage_close": "关闭",
            "compiler_title": "EXE 编译器",
            "compiler_subtitle": "从所选文件夹打包 Windows 客户端",
            "compiler_source": "源文件夹",
            "compiler_entry": "入口文件",
            "compiler_output_name": "输出名称",
            "compiler_output_dir": "输出文件夹",
            "compiler_icon": "图标 (.ico)",
            "compiler_mode": "构建模式",
            "compiler_console": "控制台",
            "compiler_mode_onefile": "单文件",
            "compiler_mode_onedir": "文件夹",
            "compiler_console_show": "显示控制台",
            "compiler_console_hide": "隐藏控制台",
            "compiler_browse": "浏览",
            "compiler_build": "构建",
            "compiler_clear": "清空日志",
            "compiler_status_idle": "空闲",
            "compiler_status_building": "构建中...",
            "compiler_status_done": "已完成",
            "compiler_status_failed": "失败",
            "compiler_log_placeholder": "构建输出将显示在此处。",
            "settings_title": "设置",
            "settings_subtitle": "个性化你的操作员控制台",
            "settings_theme": "主题",
            "settings_theme_dark": "深色",
            "settings_theme_light": "浅色",
            "settings_language": "语言",
            "settings_account": "账户",
            "settings_logout": "退出登录",
            "settings_about": "关于",
            "settings_about_body": "用于 Windows 10/11 授权远程支持的操作员控制台。",
            "settings_data": "数据",
            "settings_clear": "清除保存的数据",
            "settings_clear_done": "已清除保存的数据。",
            "instructions_title": "使用说明",
            "instructions_subtitle": "如何使用操作员控制台",
            "instructions_body": """
            <h3>快速开始</h3>
            <ol>
              <li>使用操作员账户 ID 和密码登录。</li>
              <li>在“客户端”查看已连接设备。</li>
              <li>点击“连接”开始远程会话。</li>
              <li>使用“存储”在授权下浏览并下载文件。</li>
              <li>在“编译器”从选定文件夹构建 Windows 客户端。</li>
              <li>在“设置”中切换主题或语言，或退出登录。</li>
            </ol>
            <h3>安全与合规</h3>
            <ul>
              <li>仅访问你被授权管理的设备。</li>
              <li>妥善保护会话令牌和 ID，等同于密码。</li>
              <li>为支持会话保留审计日志。</li>
            </ul>
        """,
        "nav_teams": "团队",
        "teams_title": "团队",
        "teams_subtitle": "管理操作员团队与订阅",
        "teams_list_title": "团队列表",
        "teams_select_hint": "选择团队查看详情",
        "team_name": "团队名称",
        "team_name_placeholder": "输入团队名称",
        "team_status": "状态",
        "team_status_active": "有效",
        "team_status_expired": "已过期",
        "team_subscription": "订阅到期",
        "team_renew": "续订订阅",
        "team_members": "团队成员",
        "team_member_name": "姓名",
        "team_member_tag": "角色",
        "team_member_clients": "远程客户端",
        "team_add_member": "添加成员",
        "team_remove_member": "移除成员",
        "team_add_dialog_title": "添加团队成员",
        "team_add_name": "姓名",
        "team_add_account_id": "账号 ID",
        "team_add_password": "密码",
        "team_add_tag": "角色",
        "team_add_confirm": "添加",
        "team_add_cancel": "取消",
        "teams_no_members": "暂无成员",
        "tag_operator": "操作员",
        "tag_administrator": "管理员",
        "tag_moderator": "版主",
        "settings_role": "角色",
        "settings_role_operator": "操作员",
        "settings_role_administrator": "管理员",
        "settings_role_moderator": "版主",
        }
    }
)


DEFAULT_CLIENTS = [
    {
        "id": "RC-2031",
        "name": "PC-RC-2031",
        "region": "region_eu",
        "ip": "192.168.32.10",
        "connected": False,
        "assigned_operator_id": "OP-1002",
    },
    {
        "id": "RC-1184",
        "name": "PC-RC-1184",
        "region": "region_na",
        "ip": "10.0.5.77",
        "connected": False,
        "assigned_operator_id": "OP-1001",
    },
    {
        "id": "RC-3920",
        "name": "PC-RC-3920",
        "region": "region_apac",
        "ip": "172.16.4.18",
        "connected": False,
        "assigned_operator_id": "OP-2002",
    },
    {
        "id": "RC-4420",
        "name": "PC-RC-4420",
        "region": "region_sa",
        "ip": "192.168.12.54",
        "connected": False,
        "assigned_operator_id": "OP-2001",
    },
]

DEFAULT_TEAMS = [
    {
        "id": "TEAM-01",
        "name": "Northline Support",
        "subscription_end": "2025-12-31",
        "members": [
            {
                "name": "Avery Grant",
                "tag": "administrator",
                "account_id": "OP-1001",
                "password": "Passw0rd!",
            },
            {
                "name": "Leo Martinez",
                "tag": "operator",
                "account_id": "OP-1002",
                "password": "Passw0rd!",
            },
            {
                "name": "Mia Chen",
                "tag": "moderator",
                "account_id": "MOD-2001",
                "password": "Passw0rd!",
            },
        ],
    },
    {
        "id": "TEAM-02",
        "name": "Atlas Helpdesk",
        "subscription_end": "2025-10-15",
        "members": [
            {
                "name": "Nora Patel",
                "tag": "administrator",
                "account_id": "OP-2001",
                "password": "Passw0rd!",
            },
            {
                "name": "Ivan Volkov",
                "tag": "operator",
                "account_id": "OP-2002",
                "password": "Passw0rd!",
            },
        ],
    },
]

DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "role": "operator",
    "remember_me": False,
    "account_id": "",
    "session_token": "",
    "recent_account_ids": [],
    "session_logs": [],
    "teams": DEFAULT_TEAMS,
    "clients": DEFAULT_CLIENTS,
    "builder": {
        "source_dir": "",
        "entrypoint": "",
        "output_name": "RemoteControllerClient",
        "output_dir": "",
        "icon_path": "",
        "mode": "onefile",
        "console": "hide",
    },
}


def deep_copy(value):
    return json.loads(json.dumps(value))


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = deep_copy(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._merge(self.data, raw)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _merge(self, target: Dict, source: Dict) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge(target[key], value)
            else:
                target[key] = value

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def clear_user_data(self) -> None:
        self.data["remember_me"] = False
        self.data["account_id"] = ""
        self.data["session_token"] = ""
        self.data["recent_account_ids"] = []
        self.data["session_logs"] = []
        self.data["role"] = "operator"
        self.save()


class I18n:
    def __init__(self, settings: SettingsStore):
        self.settings = settings

    def language(self) -> str:
        return self.settings.get("language", "en")

    def set_language(self, lang: str) -> None:
        self.settings.set("language", lang)

    def t(self, key: str, **kwargs) -> str:
        lang = self.language()
        text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
        return text.format(**kwargs)


class EventLogger(QtCore.QObject):
    updated = QtCore.pyqtSignal()

    def __init__(self, settings: SettingsStore, i18n: I18n):
        super().__init__()
        self.settings = settings
        self.i18n = i18n

    def log(self, key: str, **kwargs) -> None:
        message = self.i18n.t(key, **kwargs)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp}  {message}"
        logs = self.settings.get("session_logs", [])
        logs.append(entry)
        self.settings.set("session_logs", logs[-200:])
        self.settings.save()
        self.updated.emit()

    def entries(self) -> List[str]:
        return list(self.settings.get("session_logs", []))


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
        background: transparent;
        border: none;
        gridline-color: {c["border"]};
    }}
    QHeaderView::section {{
        background: {c["card_alt"]};
        border: none;
        padding: 8px;
        font-weight: 600;
    }}
    QTableWidget::item {{
        padding: 6px;
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


class BackgroundWidget(QtWidgets.QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        gradient = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.0, QtGui.QColor(self.theme.colors["bg_start"]))
        gradient.setColorAt(1.0, QtGui.QColor(self.theme.colors["bg_end"]))
        painter.fillRect(rect, gradient)

        glow = QtGui.QColor(self.theme.colors["glow"])
        glow.setAlpha(60)
        painter.setBrush(glow)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.2), int(rect.height() * 0.1)), 220, 220)

        accent = QtGui.QColor(self.theme.colors["accent"])
        accent.setAlpha(40)
        painter.setBrush(accent)
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.85), int(rect.height() * 0.2)), 180, 180)

        painter.setBrush(QtGui.QColor(self.theme.colors["accent_soft"]))
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.7), int(rect.height() * 0.9)), 260, 260)

        painter.end()


def animate_widget(widget: QtWidgets.QWidget) -> None:
    if widget.graphicsEffect() is not None:
        widget.setGraphicsEffect(None)
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(260)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def make_button(text: str, variant: str = "ghost") -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
    return button


class StorageDialog(QtWidgets.QDialog):
    def __init__(self, i18n: I18n, logger: EventLogger, client_name: str, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.logger = logger
        self.client_name = client_name
        self.remote_files = [
            {"name": "Documents", "size": "-", "type": "dir"},
            {"name": "Support_Log.txt", "size": "48 KB", "type": "file"},
            {"name": "Report_Q4.pdf", "size": "1.2 MB", "type": "file"},
            {"name": "Screenshots", "size": "-", "type": "dir"},
        ]

        self.setWindowTitle(self.i18n.t("storage_title"))
        self.setMinimumSize(720, 520)
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box)
        header.addStretch()
        self.close_button = make_button("", "ghost")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        body = QtWidgets.QHBoxLayout()
        self.remote_card = QtWidgets.QFrame()
        self.remote_card.setObjectName("Card")
        remote_layout = QtWidgets.QVBoxLayout(self.remote_card)
        self.remote_title = QtWidgets.QLabel()
        self.remote_title.setStyleSheet("font-weight: 600;")
        remote_layout.addWidget(self.remote_title)

        path_row = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel()
        self.path_input = QtWidgets.QLineEdit(".")
        self.go_button = make_button("", "ghost")
        path_row.addWidget(self.path_label)
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.go_button)
        remote_layout.addLayout(path_row)

        path_actions = QtWidgets.QHBoxLayout()
        self.up_button = make_button("", "ghost")
        self.refresh_button = make_button("", "ghost")
        path_actions.addWidget(self.up_button)
        path_actions.addWidget(self.refresh_button)
        path_actions.addStretch()
        remote_layout.addLayout(path_actions)

        self.remote_table = QtWidgets.QTableWidget(0, 3)
        self.remote_table.verticalHeader().setVisible(False)
        self.remote_table.setAlternatingRowColors(True)
        self.remote_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.remote_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        remote_layout.addWidget(self.remote_table, 1)

        self.remote_status = QtWidgets.QLabel()
        self.remote_status.setObjectName("Muted")
        remote_layout.addWidget(self.remote_status)

        self.local_card = QtWidgets.QFrame()
        self.local_card.setObjectName("Card")
        local_layout = QtWidgets.QVBoxLayout(self.local_card)
        self.local_title = QtWidgets.QLabel()
        self.local_title.setStyleSheet("font-weight: 600;")
        local_layout.addWidget(self.local_title)

        self.download_list = QtWidgets.QListWidget()
        local_layout.addWidget(self.download_list, 1)
        self.download_status = QtWidgets.QLabel()
        self.download_status.setObjectName("Muted")
        local_layout.addWidget(self.download_status)

        body.addWidget(self.remote_card, 3)
        body.addWidget(self.local_card, 2)
        layout.addLayout(body, 1)

        self.go_button.clicked.connect(self.refresh_files)
        self.refresh_button.clicked.connect(self.refresh_files)
        self.up_button.clicked.connect(self.move_up)

        self.apply_translations()
        self.refresh_files()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("storage_title"))
        self.subtitle_label.setText(self.i18n.t("storage_subtitle"))
        self.remote_title.setText(self.i18n.t("storage_remote_title"))
        self.local_title.setText(self.i18n.t("storage_local_title"))
        self.path_label.setText(self.i18n.t("storage_path_label"))
        self.go_button.setText(self.i18n.t("storage_go"))
        self.up_button.setText(self.i18n.t("storage_up"))
        self.refresh_button.setText(self.i18n.t("storage_refresh"))
        self.close_button.setText(self.i18n.t("storage_close"))
        self.remote_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("storage_size"),
                self.i18n.t("storage_action"),
            ]
        )
        self.remote_status.setText(self.i18n.t("storage_status_idle"))
        self.download_status.setText(self.i18n.t("storage_local_empty"))
        self.setWindowTitle(self.i18n.t("storage_title"))

    def refresh_files(self) -> None:
        self.remote_table.setRowCount(0)
        if not self.remote_files:
            row = self.remote_table.rowCount()
            self.remote_table.insertRow(row)
            item = QtWidgets.QTableWidgetItem(self.i18n.t("storage_empty"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.remote_table.setItem(row, 0, item)
            self.remote_table.setSpan(row, 0, 1, 3)
            return
        for entry in self.remote_files:
            row = self.remote_table.rowCount()
            self.remote_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(entry["name"])
            size_item = QtWidgets.QTableWidgetItem(entry["size"])
            self.remote_table.setItem(row, 0, name_item)
            self.remote_table.setItem(row, 1, size_item)
            action_button = make_button(self.i18n.t("storage_download"), "primary")
            if entry["type"] != "file":
                action_button.setEnabled(False)
            action_button.clicked.connect(
                lambda _, filename=entry["name"]: self.queue_download(filename)
            )
            self.remote_table.setCellWidget(row, 2, action_button)
        self.remote_table.resizeColumnsToContents()
        self.remote_status.setText(self.i18n.t("storage_status_ready"))

    def move_up(self) -> None:
        self.path_input.setText("..")
        self.refresh_files()

    def queue_download(self, filename: str) -> None:
        if self.download_list.count() == 0:
            self.download_list.clear()
        self.download_list.addItem(filename)
        self.download_status.setText(self.i18n.t("storage_status_ready"))
        self.logger.log("log_storage_download", file=filename)


@dataclass
class BuildOptions:
    source_dir: Path
    entrypoint: Path
    output_name: str
    output_dir: Path
    icon_path: Optional[Path]
    mode: str
    console: str


class BuilderWorker(QtCore.QThread):
    log_line = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool, str, str)

    def __init__(self, options: BuildOptions):
        super().__init__()
        self.options = options

    def run(self) -> None:
        if importlib.util.find_spec("PyInstaller") is None:
            self.log_line.emit("PyInstaller is not installed.")
            self.finished.emit(False, "", "missing")
            return

        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            self.options.output_name,
        ]
        cmd.append("--onefile" if self.options.mode == "onefile" else "--onedir")
        if self.options.console == "hide":
            cmd.append("--noconsole")
        if self.options.icon_path:
            cmd.extend(["--icon", str(self.options.icon_path)])
        cmd.extend(["--distpath", str(self.options.output_dir)])
        cmd.append(str(self.options.entrypoint))

        self.log_line.emit(" ".join(cmd))
        process = subprocess.Popen(
            cmd,
            cwd=str(self.options.source_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.stdout:
            for line in process.stdout:
                self.log_line.emit(line.rstrip())
        exit_code = process.wait()
        if exit_code == 0:
            output = str(self.options.output_dir / f"{self.options.output_name}.exe")
            self.finished.emit(True, output, "")
        else:
            self.finished.emit(False, "", "failed")


class LoginPage(QtWidgets.QWidget):
    login_requested = QtCore.pyqtSignal(str, str, bool)
    language_changed = QtCore.pyqtSignal(str)

    def __init__(self, i18n: I18n, settings: SettingsStore):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(120, 60, 120, 60)
        layout.addStretch()

        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.subtitle_label)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.account_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        form_layout.addRow("", QtWidgets.QLabel())
        self.account_label = QtWidgets.QLabel()
        self.password_label = QtWidgets.QLabel()
        form_layout.addRow(self.account_label, self.account_input)
        form_layout.addRow(self.password_label, self.password_input)

        card_layout.addLayout(form_layout)

        options_row = QtWidgets.QHBoxLayout()
        self.remember_check = QtWidgets.QCheckBox()
        options_row.addWidget(self.remember_check)
        options_row.addStretch()
        self.language_label = QtWidgets.QLabel()
        self.language_combo = QtWidgets.QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.language_combo.addItem(name, code)
        options_row.addWidget(self.language_label)
        options_row.addWidget(self.language_combo)
        card_layout.addLayout(options_row)

        self.login_button = make_button("", "primary")
        self.login_button.clicked.connect(self._submit)
        card_layout.addWidget(self.login_button)

        self.hint_label = QtWidgets.QLabel()
        self.hint_label.setObjectName("Muted")
        card_layout.addWidget(self.hint_label)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        card_layout.addWidget(self.status_label)

        layout.addWidget(card, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

        self.language_combo.currentIndexChanged.connect(self._language_changed)

        self.apply_translations()
        self.load_state()

    def load_state(self) -> None:
        account_id = self.settings.get("account_id", "")
        self.account_input.setText(account_id)
        remember = self.settings.get("remember_me", False)
        self.remember_check.setChecked(remember)
        recent_ids = self.settings.get("recent_account_ids", [])
        hints = sorted(set(recent_ids + ["operator-1001", "operator-1002", "qa-team", "demo"]))
        completer = QtWidgets.QCompleter(hints)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.account_input.setCompleter(completer)
        lang = self.settings.get("language", "en")
        index = self.language_combo.findData(lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("login_title"))
        self.subtitle_label.setText(self.i18n.t("login_subtitle"))
        self.account_label.setText(self.i18n.t("login_account_id"))
        self.password_label.setText(self.i18n.t("login_password"))
        self.remember_check.setText(self.i18n.t("login_remember"))
        self.login_button.setText(self.i18n.t("login_button"))
        self.hint_label.setText(self.i18n.t("login_hint"))
        self.language_label.setText(self.i18n.t("login_language"))

    def _submit(self) -> None:
        account_id = self.account_input.text().strip()
        password = self.password_input.text()
        remember = self.remember_check.isChecked()
        if not account_id or not password:
            self.status_label.setText(self.i18n.t("login_error_empty"))
            return
        self.status_label.setText("")
        self.login_requested.emit(account_id, password, remember)

    def _language_changed(self) -> None:
        lang = self.language_combo.currentData()
        if lang:
            self.language_changed.emit(lang)


class DashboardPage(QtWidgets.QWidget):
    storage_requested = QtCore.pyqtSignal(str)
    connect_requested = QtCore.pyqtSignal(str, bool)

    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.clients = deep_copy(settings.get("clients", DEFAULT_CLIENTS))
        self.last_sync = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box)
        header.addStretch()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setMinimumWidth(220)
        self.search_input.textChanged.connect(self.filter_clients)
        header.addWidget(self.search_input)
        self.refresh_button = make_button("", "ghost")
        self.refresh_button.clicked.connect(self.refresh_clients)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        split.setHandleWidth(8)
        self.table_card = QtWidgets.QFrame()
        self.table_card.setObjectName("Card")
        table_layout = QtWidgets.QVBoxLayout(self.table_card)
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self.handle_item_changed)
        table_layout.addWidget(self.table)
        split.addWidget(self.table_card)

        self.log_card = QtWidgets.QFrame()
        self.log_card.setObjectName("Card")
        log_layout = QtWidgets.QVBoxLayout(self.log_card)
        self.log_title = QtWidgets.QLabel()
        self.log_title.setStyleSheet("font-weight: 600;")
        log_layout.addWidget(self.log_title)
        self.log_list = QtWidgets.QListWidget()
        log_layout.addWidget(self.log_list, 1)
        split.addWidget(self.log_card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        layout.addWidget(split, 1)

        footer = QtWidgets.QHBoxLayout()
        self.last_sync_label = QtWidgets.QLabel()
        self.last_sync_label.setObjectName("Muted")
        footer.addWidget(self.last_sync_label)
        footer.addStretch()
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        footer.addWidget(self.status_label)
        layout.addLayout(footer)

        self.logger.updated.connect(self.refresh_logs)
        self.apply_translations()
        self.refresh_clients()
        self.refresh_logs()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("main_title"))
        self.subtitle_label.setText(self.i18n.t("main_subtitle"))
        self.search_input.setPlaceholderText(self.i18n.t("main_search_placeholder"))
        self.refresh_button.setText(self.i18n.t("main_refresh_button"))
        self.table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("table_id"),
                self.i18n.t("table_region"),
                self.i18n.t("table_ip"),
                self.i18n.t("table_storage"),
                self.i18n.t("table_connect"),
            ]
        )
        self.log_title.setText(self.i18n.t("log_title"))
        self.status_label.setText(self.i18n.t("main_status_ready"))
        self.update_last_sync_label()
        self.render_clients(self.clients)

    def refresh_logs(self) -> None:
        self.log_list.clear()
        entries = self.logger.entries()
        if not entries:
            self.log_list.addItem(self.i18n.t("log_empty"))
            return
        for entry in entries[-100:]:
            self.log_list.addItem(entry)

    def update_last_sync_label(self) -> None:
        if not self.last_sync:
            last_sync = self.i18n.t("main_last_sync_never")
        else:
            last_sync = self.last_sync.strftime("%H:%M:%S")
        self.last_sync_label.setText(f'{self.i18n.t("main_last_sync")}: {last_sync}')

    def refresh_clients(self) -> None:
        self.last_sync = datetime.now()
        self.update_last_sync_label()
        self.render_clients(self.clients)

    def filter_clients(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self.render_clients(self.clients)
            return
        filtered = []
        for client in self.clients:
            values = [client["name"], client["id"], self.i18n.t(client["region"]), client["ip"]]
            if any(text in str(value).lower() for value in values):
                filtered.append(client)
        self.render_clients(filtered)

    def render_clients(self, clients: List[Dict]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for client in clients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(client["name"])
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, client["id"])
            id_item = QtWidgets.QTableWidgetItem(client["id"])
            region_item = QtWidgets.QTableWidgetItem(self.i18n.t(client["region"]))
            ip_item = QtWidgets.QTableWidgetItem(client["ip"])
            for item in (id_item, region_item, ip_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, region_item)
            self.table.setItem(row, 3, ip_item)

            storage_button = make_button(self.i18n.t("button_storage"), "ghost")
            storage_button.clicked.connect(lambda _, cid=client["id"]: self.storage_requested.emit(cid))
            self.table.setCellWidget(row, 4, storage_button)

            connect_text = self.i18n.t("button_connected") if client["connected"] else self.i18n.t("button_connect")
            connect_button = make_button(connect_text, "primary")
            connect_button.clicked.connect(
                lambda _, cid=client["id"], state=client["connected"]: self.connect_requested.emit(cid, state)
            )
            self.table.setCellWidget(row, 5, connect_button)
        self.table.blockSignals(False)

    def handle_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        client_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        for client in self.clients:
            if client["id"] == client_id:
                client["name"] = item.text().strip() or client["name"]
                break
        self.settings.set("clients", self.clients)
        self.settings.save()


class AddMemberDialog(QtWidgets.QDialog):
    def __init__(self, i18n: I18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.setWindowTitle(self.i18n.t("team_add_dialog_title"))
        self.setMinimumWidth(360)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.name_input = QtWidgets.QLineEdit()
        self.account_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.tag_combo = QtWidgets.QComboBox()
        self.tag_combo.addItem(self.i18n.t("tag_operator"), "operator")
        self.tag_combo.addItem(self.i18n.t("tag_administrator"), "administrator")
        self.tag_combo.addItem(self.i18n.t("tag_moderator"), "moderator")

        form.addRow(self.i18n.t("team_add_name"), self.name_input)
        form.addRow(self.i18n.t("team_add_account_id"), self.account_input)
        form.addRow(self.i18n.t("team_add_password"), self.password_input)
        form.addRow(self.i18n.t("team_add_tag"), self.tag_combo)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = make_button(self.i18n.t("team_add_cancel"), "ghost")
        self.confirm_button = make_button(self.i18n.t("team_add_confirm"), "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def member_data(self) -> Dict[str, str]:
        return {
            "name": self.name_input.text().strip(),
            "account_id": self.account_input.text().strip(),
            "password": self.password_input.text(),
            "tag": self.tag_combo.currentData(),
        }


class TeamsPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n, settings: SettingsStore):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.teams = deep_copy(settings.get("teams", DEFAULT_TEAMS))
        self.current_role = settings.get("role", "operator")
        self.current_team_id = None
        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)

        self.list_card = QtWidgets.QFrame()
        self.list_card.setObjectName("Card")
        list_layout = QtWidgets.QVBoxLayout(self.list_card)
        self.list_title = QtWidgets.QLabel()
        self.list_title.setStyleSheet("font-weight: 600;")
        list_layout.addWidget(self.list_title)
        self.team_list = QtWidgets.QListWidget()
        self.team_list.itemSelectionChanged.connect(self.on_team_selected)
        list_layout.addWidget(self.team_list, 1)
        body.addWidget(self.list_card, 2)

        self.details_card = QtWidgets.QFrame()
        self.details_card.setObjectName("Card")
        details_layout = QtWidgets.QVBoxLayout(self.details_card)

        self.details_stack = QtWidgets.QStackedWidget()
        placeholder = QtWidgets.QLabel()
        placeholder.setObjectName("Muted")
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label = placeholder
        self.details_stack.addWidget(placeholder)

        details_container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(details_container)
        container_layout.setSpacing(12)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        self.team_name_label = QtWidgets.QLabel()
        self.team_name_input = QtWidgets.QLineEdit()
        self.team_name_input.editingFinished.connect(self.commit_team_name)
        self.team_name_input.setPlaceholderText(self.i18n.t("team_name_placeholder"))

        self.team_status_label = QtWidgets.QLabel()
        self.team_status_value = QtWidgets.QLabel()
        self.team_status_value.setStyleSheet("font-weight: 600;")

        self.team_subscription_label = QtWidgets.QLabel()
        self.team_subscription_value = QtWidgets.QLabel()

        form.addWidget(self.team_name_label, 0, 0)
        form.addWidget(self.team_name_input, 0, 1, 1, 3)
        form.addWidget(self.team_status_label, 1, 0)
        form.addWidget(self.team_status_value, 1, 1)
        form.addWidget(self.team_subscription_label, 1, 2)
        form.addWidget(self.team_subscription_value, 1, 3)

        container_layout.addLayout(form)

        self.renew_button = make_button("", "primary")
        self.renew_button.clicked.connect(self.renew_subscription)
        container_layout.addWidget(self.renew_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.members_label = QtWidgets.QLabel()
        self.members_label.setStyleSheet("font-weight: 600;")
        container_layout.addWidget(self.members_label)

        self.members_table = QtWidgets.QTableWidget(0, 3)
        self.members_table.verticalHeader().setVisible(False)
        self.members_table.setAlternatingRowColors(True)
        self.members_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.members_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.members_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.members_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.members_table.verticalHeader().setDefaultSectionSize(36)
        container_layout.addWidget(self.members_table, 1)

        member_actions = QtWidgets.QHBoxLayout()
        self.add_member_button = make_button("", "ghost")
        self.add_member_button.clicked.connect(self.add_member)
        self.remove_member_button = make_button("", "ghost")
        self.remove_member_button.clicked.connect(self.remove_member)
        member_actions.addWidget(self.add_member_button)
        member_actions.addWidget(self.remove_member_button)
        member_actions.addStretch()
        container_layout.addLayout(member_actions)

        self.details_stack.addWidget(details_container)
        details_layout.addWidget(self.details_stack, 1)
        body.addWidget(self.details_card, 5)

        layout.addLayout(body, 1)

        self.apply_translations()
        self.populate_team_list()
        self.update_role_controls()

    @staticmethod
    def parse_date(value: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return datetime.now()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("teams_title"))
        self.subtitle_label.setText(self.i18n.t("teams_subtitle"))
        self.list_title.setText(self.i18n.t("teams_list_title"))
        self.placeholder_label.setText(self.i18n.t("teams_select_hint"))
        self.team_name_label.setText(self.i18n.t("team_name"))
        self.team_name_input.setPlaceholderText(self.i18n.t("team_name_placeholder"))
        self.team_status_label.setText(self.i18n.t("team_status"))
        self.team_subscription_label.setText(self.i18n.t("team_subscription"))
        self.renew_button.setText(self.i18n.t("team_renew"))
        self.members_label.setText(self.i18n.t("team_members"))
        self.add_member_button.setText(self.i18n.t("team_add_member"))
        self.remove_member_button.setText(self.i18n.t("team_remove_member"))
        self.members_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("team_member_name"),
                self.i18n.t("team_member_tag"),
                self.i18n.t("team_member_clients"),
            ]
        )
        self.populate_team_list(self.current_team_id)
        self.render_team_details()

    def set_role(self, role: str) -> None:
        self.current_role = role
        self.update_role_controls()
        self.populate_team_list(self.current_team_id)
        self.render_team_details()

    def update_role_controls(self) -> None:
        is_moderator = self.current_role == "moderator"
        self.team_name_input.setReadOnly(not is_moderator)
        self.renew_button.setEnabled(is_moderator)
        self.add_member_button.setEnabled(is_moderator)
        self.remove_member_button.setEnabled(is_moderator)

    def visible_teams(self) -> List[Dict]:
        if self.current_role == "moderator":
            return self.teams
        account_id = self.settings.get("account_id", "")
        for team in self.teams:
            for member in team.get("members", []):
                if member.get("account_id") == account_id:
                    return [team]
        return self.teams[:1] if self.teams else []

    def populate_team_list(self, select_team_id: Optional[str] = None) -> None:
        self.team_list.clear()
        teams = self.visible_teams()
        for team in teams:
            item = QtWidgets.QListWidgetItem(team["name"])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, team["id"])
            self.team_list.addItem(item)
            if select_team_id and team["id"] == select_team_id:
                self.team_list.setCurrentItem(item)
        if self.team_list.count() > 0 and self.team_list.currentItem() is None:
            self.team_list.setCurrentRow(0)

    def on_team_selected(self) -> None:
        self.render_team_details()

    def render_team_details(self) -> None:
        team = self.selected_team()
        if team is None:
            self.details_stack.setCurrentIndex(0)
            return
        self.details_stack.setCurrentIndex(1)
        self.current_team_id = team["id"]
        self.team_name_input.blockSignals(True)
        self.team_name_input.setText(team.get("name", ""))
        self.team_name_input.blockSignals(False)
        self.update_subscription_display(team)
        self.render_members(team)

    def selected_team(self) -> Optional[Dict]:
        item = self.team_list.currentItem()
        if not item:
            return None
        team_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        for team in self.teams:
            if team["id"] == team_id:
                return team
        return None

    def update_subscription_display(self, team: Dict) -> None:
        end_date = self.parse_date(team.get("subscription_end", "")).date()
        today = datetime.now().date()
        is_active = end_date >= today
        status_key = "team_status_active" if is_active else "team_status_expired"
        self.team_status_value.setText(self.i18n.t(status_key))
        color = self.theme.colors["accent"] if is_active else self.theme.colors["danger"]
        self.team_status_value.setStyleSheet(f"font-weight: 600; color: {color};")
        self.team_subscription_value.setText(end_date.strftime("%Y-%m-%d"))

    def client_count_for_member(self, member: Dict) -> int:
        account_id = member.get("account_id")
        if not account_id:
            return 0
        clients = self.settings.get("clients", [])
        count = 0
        for client in clients:
            assigned = client.get("assigned_operator_id")
            if assigned == account_id:
                count += 1
        return count

    def render_members(self, team: Dict) -> None:
        members = team.get("members", [])
        self.members_table.setRowCount(0)
        if not members:
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            item = QtWidgets.QTableWidgetItem(self.i18n.t("teams_no_members"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.members_table.setItem(row, 0, item)
            self.members_table.setSpan(row, 0, 1, 3)
            return
        for member in members:
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(member["name"])
            tag_label = self.i18n.t(f"tag_{member['tag']}")
            tag_item = QtWidgets.QTableWidgetItem(tag_label)
            clients_item = QtWidgets.QTableWidgetItem(str(self.client_count_for_member(member)))
            self.members_table.setItem(row, 0, name_item)
            self.members_table.setItem(row, 1, tag_item)
            self.members_table.setItem(row, 2, clients_item)

    def commit_team_name(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        name = self.team_name_input.text().strip()
        if not name:
            return
        team["name"] = name
        self.save_teams()
        self.populate_team_list(team["id"])

    def renew_subscription(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        end_date = self.parse_date(team.get("subscription_end", "")).date()
        today = datetime.now().date()
        base_date = end_date if end_date >= today else today
        new_end = base_date + timedelta(days=30)
        team["subscription_end"] = new_end.strftime("%Y-%m-%d")
        self.save_teams()
        self.update_subscription_display(team)

    def add_member(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        dialog = AddMemberDialog(self.i18n, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        data = dialog.member_data()
        if not data["name"] or not data["account_id"] or not data["password"]:
            return
        team.setdefault("members", []).append(data)
        self.save_teams()
        self.render_members(team)
        self.populate_team_list(team["id"])

    def remove_member(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        row = self.members_table.currentRow()
        if row < 0 or row >= len(team.get("members", [])):
            return
        team["members"].pop(row)
        self.save_teams()
        self.render_members(team)
        self.populate_team_list(team["id"])

    def save_teams(self) -> None:
        self.settings.set("teams", self.teams)
        self.settings.save()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        team = self.selected_team()
        if team is not None:
            self.update_subscription_display(team)


class CompilerPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.worker: Optional[BuilderWorker] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        form_card = QtWidgets.QFrame()
        form_card.setObjectName("Card")
        form_layout = QtWidgets.QGridLayout(form_card)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(12)

        self.source_label = QtWidgets.QLabel()
        self.source_input = QtWidgets.QLineEdit()
        self.source_button = make_button("", "ghost")
        self.source_button.clicked.connect(self.pick_source_dir)

        self.entry_label = QtWidgets.QLabel()
        self.entry_input = QtWidgets.QLineEdit()
        self.entry_button = make_button("", "ghost")
        self.entry_button.clicked.connect(self.pick_entrypoint)

        self.output_name_label = QtWidgets.QLabel()
        self.output_name_input = QtWidgets.QLineEdit()

        self.output_dir_label = QtWidgets.QLabel()
        self.output_dir_input = QtWidgets.QLineEdit()
        self.output_dir_button = make_button("", "ghost")
        self.output_dir_button.clicked.connect(self.pick_output_dir)

        self.icon_label = QtWidgets.QLabel()
        self.icon_input = QtWidgets.QLineEdit()
        self.icon_button = make_button("", "ghost")
        self.icon_button.clicked.connect(self.pick_icon)

        self.mode_label = QtWidgets.QLabel()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem(self.i18n.t("compiler_mode_onefile"), "onefile")
        self.mode_combo.addItem(self.i18n.t("compiler_mode_onedir"), "onedir")

        self.console_check = QtWidgets.QCheckBox()

        form_layout.addWidget(self.source_label, 0, 0)
        form_layout.addWidget(self.source_input, 0, 1)
        form_layout.addWidget(self.source_button, 0, 2)
        form_layout.addWidget(self.entry_label, 1, 0)
        form_layout.addWidget(self.entry_input, 1, 1)
        form_layout.addWidget(self.entry_button, 1, 2)
        form_layout.addWidget(self.output_name_label, 2, 0)
        form_layout.addWidget(self.output_name_input, 2, 1, 1, 2)
        form_layout.addWidget(self.output_dir_label, 3, 0)
        form_layout.addWidget(self.output_dir_input, 3, 1)
        form_layout.addWidget(self.output_dir_button, 3, 2)
        form_layout.addWidget(self.icon_label, 4, 0)
        form_layout.addWidget(self.icon_input, 4, 1)
        form_layout.addWidget(self.icon_button, 4, 2)
        form_layout.addWidget(self.mode_label, 5, 0)
        form_layout.addWidget(self.mode_combo, 5, 1)
        form_layout.addWidget(self.console_check, 5, 2)

        layout.addWidget(form_card)

        actions = QtWidgets.QHBoxLayout()
        self.build_button = make_button("", "primary")
        self.build_button.clicked.connect(self.start_build)
        self.clear_button = make_button("", "ghost")
        self.clear_button.clicked.connect(self.clear_log)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        actions.addWidget(self.build_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.status_label)
        layout.addLayout(actions)

        log_card = QtWidgets.QFrame()
        log_card.setObjectName("Card")
        log_layout = QtWidgets.QVBoxLayout(log_card)
        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_card, 1)

        self.load_state()
        self.apply_translations()

    def load_state(self) -> None:
        builder = self.settings.get("builder", {})
        self.source_input.setText(builder.get("source_dir", ""))
        self.entry_input.setText(builder.get("entrypoint", ""))
        self.output_name_input.setText(builder.get("output_name", "RemoteControllerClient"))
        self.output_dir_input.setText(builder.get("output_dir", ""))
        self.icon_input.setText(builder.get("icon_path", ""))
        mode = builder.get("mode", "onefile")
        self.mode_combo.setCurrentIndex(0 if mode == "onefile" else 1)
        console = builder.get("console", "hide")
        self.console_check.setChecked(console == "show")

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("compiler_title"))
        self.subtitle_label.setText(self.i18n.t("compiler_subtitle"))
        self.source_label.setText(self.i18n.t("compiler_source"))
        self.entry_label.setText(self.i18n.t("compiler_entry"))
        self.output_name_label.setText(self.i18n.t("compiler_output_name"))
        self.output_dir_label.setText(self.i18n.t("compiler_output_dir"))
        self.icon_label.setText(self.i18n.t("compiler_icon"))
        self.mode_label.setText(self.i18n.t("compiler_mode"))
        self.console_check.setText(self.i18n.t("compiler_console_show"))
        self.source_button.setText(self.i18n.t("compiler_browse"))
        self.entry_button.setText(self.i18n.t("compiler_browse"))
        self.output_dir_button.setText(self.i18n.t("compiler_browse"))
        self.icon_button.setText(self.i18n.t("compiler_browse"))
        self.build_button.setText(self.i18n.t("compiler_build"))
        self.clear_button.setText(self.i18n.t("compiler_clear"))
        self.status_label.setText(self.i18n.t("compiler_status_idle"))
        self.mode_combo.setItemText(0, self.i18n.t("compiler_mode_onefile"))
        self.mode_combo.setItemText(1, self.i18n.t("compiler_mode_onedir"))
        if self.log_output.toPlainText().strip() == "":
            self.log_output.setPlaceholderText(self.i18n.t("compiler_log_placeholder"))

    def pick_source_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, self.i18n.t("compiler_source"))
        if path:
            self.source_input.setText(path)
            guessed = self.guess_entrypoint(Path(path))
            if guessed and not self.entry_input.text().strip():
                self.entry_input.setText(str(guessed))

    def pick_entrypoint(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.i18n.t("compiler_entry"), filter="Python Files (*.py)"
        )
        if path:
            self.entry_input.setText(path)

    def pick_output_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, self.i18n.t("compiler_output_dir"))
        if path:
            self.output_dir_input.setText(path)

    def pick_icon(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.i18n.t("compiler_icon"), filter="Icon Files (*.ico)"
        )
        if path:
            self.icon_input.setText(path)

    def guess_entrypoint(self, source_dir: Path) -> Optional[Path]:
        candidates = ["client.py", "main.py", "app.py", "remote_client/main.py"]
        for candidate in candidates:
            candidate_path = source_dir / candidate
            if candidate_path.exists():
                return candidate_path
        return None

    def start_build(self) -> None:
        source_dir = Path(self.source_input.text().strip())
        entrypoint = Path(self.entry_input.text().strip())
        output_name = self.output_name_input.text().strip()
        output_dir_text = self.output_dir_input.text().strip() or str(source_dir / "dist")
        output_dir = Path(output_dir_text)
        icon_path = Path(self.icon_input.text().strip()) if self.icon_input.text().strip() else None
        mode = self.mode_combo.currentData()
        console = "show" if self.console_check.isChecked() else "hide"

        if not source_dir.exists() or not entrypoint.exists():
            self.log_output.appendPlainText(self.i18n.t("log_build_failed"))
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
            return

        options = BuildOptions(
            source_dir=source_dir,
            entrypoint=entrypoint,
            output_name=output_name or "RemoteControllerClient",
            output_dir=output_dir,
            icon_path=icon_path,
            mode=mode,
            console=console,
        )
        self.persist_builder_state(options)
        self.status_label.setText(self.i18n.t("compiler_status_building"))
        self.build_button.setEnabled(False)
        self.log_output.clear()
        self.logger.log("log_build_start", entry=entrypoint.name)

        self.worker = BuilderWorker(options)
        self.worker.log_line.connect(self.log_output.appendPlainText)
        self.worker.finished.connect(self.finish_build)
        self.worker.start()

    def finish_build(self, success: bool, output: str, reason: str) -> None:
        self.build_button.setEnabled(True)
        if success:
            self.status_label.setText(self.i18n.t("compiler_status_done"))
            self.logger.log("log_build_done", output=output)
        else:
            if reason == "missing":
                self.log_output.appendPlainText(self.i18n.t("log_build_missing"))
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
            self.logger.log("log_build_failed")

    def clear_log(self) -> None:
        self.log_output.clear()
        self.status_label.setText(self.i18n.t("compiler_status_idle"))

    def persist_builder_state(self, options: BuildOptions) -> None:
        self.settings.set(
            "builder",
            {
                "source_dir": str(options.source_dir),
                "entrypoint": str(options.entrypoint),
                "output_name": options.output_name,
                "output_dir": str(options.output_dir),
                "icon_path": str(options.icon_path) if options.icon_path else "",
                "mode": options.mode,
                "console": options.console,
            },
        )
        self.settings.save()


class SettingsPage(QtWidgets.QWidget):
    theme_changed = QtCore.pyqtSignal(str)
    language_changed = QtCore.pyqtSignal(str)
    role_changed = QtCore.pyqtSignal(str)
    logout_requested = QtCore.pyqtSignal()

    def __init__(self, i18n: I18n, settings: SettingsStore):
        super().__init__()
        self.i18n = i18n
        self.settings = settings

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        self.theme_card = QtWidgets.QFrame()
        self.theme_card.setObjectName("Card")
        theme_layout = QtWidgets.QVBoxLayout(self.theme_card)
        self.theme_label = QtWidgets.QLabel()
        self.theme_label.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self.theme_label)
        theme_buttons = QtWidgets.QHBoxLayout()
        self.theme_dark = make_button("", "ghost")
        self.theme_light = make_button("", "ghost")
        self.theme_dark.setCheckable(True)
        self.theme_light.setCheckable(True)
        self.theme_group = QtWidgets.QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_group.addButton(self.theme_dark)
        self.theme_group.addButton(self.theme_light)
        theme_buttons.addWidget(self.theme_dark)
        theme_buttons.addWidget(self.theme_light)
        theme_layout.addLayout(theme_buttons)
        grid.addWidget(self.theme_card, 0, 0)

        self.language_card = QtWidgets.QFrame()
        self.language_card.setObjectName("Card")
        lang_layout = QtWidgets.QVBoxLayout(self.language_card)
        self.language_label = QtWidgets.QLabel()
        self.language_label.setStyleSheet("font-weight: 600;")
        lang_layout.addWidget(self.language_label)
        self.language_combo = QtWidgets.QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.language_combo.addItem(name, code)
        lang_layout.addWidget(self.language_combo)
        grid.addWidget(self.language_card, 0, 1)

        self.account_card = QtWidgets.QFrame()
        self.account_card.setObjectName("Card")
        account_layout = QtWidgets.QVBoxLayout(self.account_card)
        self.account_label = QtWidgets.QLabel()
        self.account_label.setStyleSheet("font-weight: 600;")
        account_layout.addWidget(self.account_label)
        self.role_label = QtWidgets.QLabel()
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItem(self.i18n.t("settings_role_operator"), "operator")
        self.role_combo.addItem(self.i18n.t("settings_role_administrator"), "administrator")
        self.role_combo.addItem(self.i18n.t("settings_role_moderator"), "moderator")
        account_layout.addWidget(self.role_label)
        account_layout.addWidget(self.role_combo)
        self.logout_button = make_button("", "danger")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        account_layout.addWidget(self.logout_button)
        account_layout.addSpacing(12)
        self.data_label = QtWidgets.QLabel()
        self.data_label.setStyleSheet("font-weight: 600;")
        self.data_button = make_button("", "ghost")
        self.data_button.clicked.connect(self.clear_data)
        self.data_status = QtWidgets.QLabel()
        self.data_status.setObjectName("Muted")
        account_layout.addWidget(self.data_label)
        account_layout.addWidget(self.data_button)
        account_layout.addWidget(self.data_status)
        grid.addWidget(self.account_card, 1, 0)

        self.about_card = QtWidgets.QFrame()
        self.about_card.setObjectName("Card")
        about_layout = QtWidgets.QVBoxLayout(self.about_card)
        self.about_label = QtWidgets.QLabel()
        self.about_label.setStyleSheet("font-weight: 600;")
        self.about_body = QtWidgets.QLabel()
        self.about_body.setWordWrap(True)
        self.about_body.setObjectName("Muted")
        about_layout.addWidget(self.about_label)
        about_layout.addWidget(self.about_body)
        grid.addWidget(self.about_card, 1, 1)

        layout.addLayout(grid)
        layout.addStretch()

        self.theme_group.buttonToggled.connect(self.emit_theme)
        self.language_combo.currentIndexChanged.connect(self.emit_language)
        self.role_combo.currentIndexChanged.connect(self.emit_role)

        self.load_state()
        self.apply_translations()

    def load_state(self) -> None:
        theme = self.settings.get("theme", "dark")
        self.theme_dark.setChecked(theme == "dark")
        self.theme_light.setChecked(theme == "light")
        lang = self.settings.get("language", "en")
        index = self.language_combo.findData(lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        role = self.settings.get("role", "operator")
        role_index = self.role_combo.findData(role)
        if role_index >= 0:
            self.role_combo.setCurrentIndex(role_index)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("settings_title"))
        self.subtitle_label.setText(self.i18n.t("settings_subtitle"))
        self.theme_label.setText(self.i18n.t("settings_theme"))
        self.theme_dark.setText(self.i18n.t("settings_theme_dark"))
        self.theme_light.setText(self.i18n.t("settings_theme_light"))
        self.language_label.setText(self.i18n.t("settings_language"))
        self.account_label.setText(self.i18n.t("settings_account"))
        self.role_label.setText(self.i18n.t("settings_role"))
        self.role_combo.setItemText(0, self.i18n.t("settings_role_operator"))
        self.role_combo.setItemText(1, self.i18n.t("settings_role_administrator"))
        self.role_combo.setItemText(2, self.i18n.t("settings_role_moderator"))
        self.logout_button.setText(self.i18n.t("settings_logout"))
        self.about_label.setText(self.i18n.t("settings_about"))
        self.about_body.setText(self.i18n.t("settings_about_body"))
        self.data_label.setText(self.i18n.t("settings_data"))
        self.data_button.setText(self.i18n.t("settings_clear"))

    def emit_theme(self) -> None:
        if self.theme_dark.isChecked():
            self.theme_changed.emit("dark")
        elif self.theme_light.isChecked():
            self.theme_changed.emit("light")

    def emit_language(self) -> None:
        lang = self.language_combo.currentData()
        if lang:
            self.language_changed.emit(lang)

    def emit_role(self) -> None:
        role = self.role_combo.currentData()
        if role:
            self.settings.set("role", role)
            self.settings.save()
            self.role_changed.emit(role)

    def clear_data(self) -> None:
        self.settings.clear_user_data()
        self.data_status.setText(self.i18n.t("settings_clear_done"))


class InstructionsPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n):
        super().__init__()
        self.i18n = i18n
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        self.instructions = QtWidgets.QTextBrowser()
        self.instructions.setOpenExternalLinks(True)
        layout.addWidget(self.instructions, 1)
        self.apply_translations()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("instructions_title"))
        self.subtitle_label.setText(self.i18n.t("instructions_subtitle"))
        self.instructions.setHtml(self.i18n.t("instructions_body"))


class MainShell(QtWidgets.QWidget):
    page_changed = QtCore.pyqtSignal(str)
    logout_requested = QtCore.pyqtSignal()

    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.current_role = self.settings.get("role", "operator")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(16)

        brand = QtWidgets.QFrame()
        brand_layout = QtWidgets.QVBoxLayout(brand)
        self.brand_icon = QtWidgets.QLabel("RC")
        self.brand_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.brand_icon.setFixedSize(56, 56)
        self.brand_icon.setObjectName("BrandIcon")
        self.brand_title = QtWidgets.QLabel()
        self.brand_title.setStyleSheet("font-weight: 700; font-size: 16px;")
        self.brand_subtitle = QtWidgets.QLabel()
        self.brand_subtitle.setObjectName("Muted")
        brand_layout.addWidget(self.brand_icon, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        brand_layout.addWidget(self.brand_title)
        brand_layout.addWidget(self.brand_subtitle)
        sidebar_layout.addWidget(brand)

        self.nav_buttons = {}
        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for key in ["main", "teams", "compiler", "settings", "instructions"]:
            button = make_button("", "ghost")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            sidebar_layout.addWidget(button)
            button.clicked.connect(lambda _, page_key=key: self.switch_page(page_key))

        sidebar_layout.addStretch()
        self.sidebar_footer = QtWidgets.QLabel("Windows 10/11")
        self.sidebar_footer.setObjectName("Muted")
        sidebar_layout.addWidget(self.sidebar_footer)

        layout.addWidget(self.sidebar)

        content = QtWidgets.QVBoxLayout()
        self.top_bar = QtWidgets.QFrame()
        self.top_bar.setObjectName("TopBar")
        top_layout = QtWidgets.QHBoxLayout(self.top_bar)
        self.page_title = QtWidgets.QLabel()
        self.page_title.setStyleSheet("font-weight: 600; font-size: 16px;")
        top_layout.addWidget(self.page_title)
        top_layout.addStretch()
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        top_layout.addWidget(self.status_label)
        self.refresh_button = make_button("", "ghost")
        self.refresh_button.clicked.connect(lambda: self.page_changed.emit("refresh"))
        top_layout.addWidget(self.refresh_button)
        self.logout_button = make_button("", "ghost")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        top_layout.addWidget(self.logout_button)
        content.addWidget(self.top_bar)

        self.stack = QtWidgets.QStackedWidget()
        self.dashboard = DashboardPage(i18n, settings, logger)
        self.teams_page = TeamsPage(i18n, settings)
        self.compiler = CompilerPage(i18n, settings, logger)
        self.settings_page = SettingsPage(i18n, settings)
        self.instructions_page = InstructionsPage(i18n)
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.teams_page)
        self.stack.addWidget(self.compiler)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.instructions_page)
        content.addWidget(self.stack, 1)

        layout.addLayout(content, 1)

        self.dashboard.storage_requested.connect(self.open_storage)
        self.dashboard.connect_requested.connect(self.toggle_connection)
        self.settings_page.logout_requested.connect(self.logout_requested.emit)
        self.settings_page.theme_changed.connect(self.emit_theme_change)
        self.settings_page.language_changed.connect(self.emit_language_change)
        self.settings_page.role_changed.connect(self.handle_role_change)

        self.apply_translations()
        self.update_role_visibility()
        self.nav_buttons["main"].setChecked(True)
        self.switch_page("main")

    def apply_translations(self) -> None:
        self.brand_title.setText(self.i18n.t("app_title"))
        self.brand_subtitle.setText(self.i18n.t("app_subtitle"))
        self.nav_buttons["main"].setText(self.i18n.t("nav_main"))
        self.nav_buttons["teams"].setText(self.i18n.t("nav_teams"))
        self.nav_buttons["compiler"].setText(self.i18n.t("nav_compiler"))
        self.nav_buttons["settings"].setText(self.i18n.t("nav_settings"))
        self.nav_buttons["instructions"].setText(self.i18n.t("nav_instructions"))
        self.refresh_button.setText(self.i18n.t("top_refresh"))
        self.logout_button.setText(self.i18n.t("top_logout"))
        self.status_label.setText(f'{self.i18n.t("top_status_label")}: {self.i18n.t("top_status_mock")}')
        self.dashboard.apply_translations()
        self.teams_page.apply_translations()
        self.compiler.apply_translations()
        self.settings_page.apply_translations()
        self.instructions_page.apply_translations()
        self.update_page_title()

    def update_page_title(self) -> None:
        index = self.stack.currentIndex()
        titles = [
            self.i18n.t("nav_main"),
            self.i18n.t("nav_teams"),
            self.i18n.t("nav_compiler"),
            self.i18n.t("nav_settings"),
            self.i18n.t("nav_instructions"),
        ]
        self.page_title.setText(titles[index])

    def switch_page(self, key: str) -> None:
        if key == "teams" and self.current_role != "moderator":
            key = "main"
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
        mapping = {
            "main": 0,
            "teams": 1,
            "compiler": 2,
            "settings": 3,
            "instructions": 4,
        }
        index = mapping.get(key, 0)
        self.stack.setCurrentIndex(index)
        self.update_page_title()
        animate_widget(self.stack.currentWidget())

    def update_role_visibility(self) -> None:
        is_moderator = self.current_role == "moderator"
        self.nav_buttons["teams"].setVisible(is_moderator)
        if not is_moderator and self.stack.currentIndex() == 1:
            self.switch_page("main")

    def open_storage(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        self.logger.log("log_storage_open", client=client_name)
        dialog = StorageDialog(self.i18n, self.logger, client_name, self)
        dialog.exec()

    def toggle_connection(self, client_id: str, currently_connected: bool) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        if not client:
            return
        if currently_connected:
            client["connected"] = False
            self.logger.log("log_disconnect", client=client["name"])
        else:
            self.logger.log("log_connect", client=client["name"])
            client["connected"] = True
            self.logger.log("log_connected", client=client["name"])
        self.dashboard.render_clients(self.dashboard.clients)
        self.settings.set("clients", self.dashboard.clients)
        self.settings.save()

    def emit_theme_change(self, theme: str) -> None:
        self.page_changed.emit(f"theme:{theme}")

    def emit_language_change(self, lang: str) -> None:
        self.page_changed.emit(f"lang:{lang}")

    def handle_role_change(self, role: str) -> None:
        self.current_role = role
        self.teams_page.set_role(role)
        self.update_role_visibility()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, settings_path: Path):
        super().__init__()
        self.settings = SettingsStore(settings_path)
        self.i18n = I18n(self.settings)
        self.logger = EventLogger(self.settings, self.i18n)

        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)

        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])
        self.background = BackgroundWidget(self.theme)
        self.setCentralWidget(self.background)

        self.stack = QtWidgets.QStackedWidget()
        self.login_page = LoginPage(self.i18n, self.settings)
        self.shell = MainShell(self.i18n, self.settings, self.logger)
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.shell)

        bg_layout = QtWidgets.QVBoxLayout(self.background)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.addWidget(self.stack)

        self.login_page.login_requested.connect(self.handle_login)
        self.login_page.language_changed.connect(self.set_language)
        self.shell.logout_requested.connect(self.logout)
        self.shell.page_changed.connect(self.handle_shell_event)

        self.apply_theme(self.settings.get("theme", "dark"))
        self.apply_translations()
        self.restore_session()

    def apply_font(self, language: str) -> None:
        font_name = select_font_for_language(language)
        QtWidgets.QApplication.instance().setFont(QtGui.QFont(font_name, 10))

    def apply_theme(self, theme_name: str) -> None:
        self.theme = THEMES.get(theme_name, THEMES["dark"])
        self.background.set_theme(self.theme)
        self.settings.set("theme", theme_name)
        self.setStyleSheet(build_stylesheet(self.theme))
        self.shell.teams_page.apply_theme(self.theme)

    def apply_translations(self) -> None:
        self.login_page.apply_translations()
        self.shell.apply_translations()

    def restore_session(self) -> None:
        remember = self.settings.get("remember_me", False)
        token = self.settings.get("session_token", "")
        account = self.settings.get("account_id", "")
        if remember and token and account:
            self.logger.log("log_login", account=account)
            self.stack.setCurrentWidget(self.shell)
            self.shell.dashboard.refresh_logs()
        else:
            self.stack.setCurrentWidget(self.login_page)

    def handle_login(self, account_id: str, password: str, remember: bool) -> None:
        if not account_id or not password:
            self.login_page.status_label.setText(self.i18n.t("login_error_empty"))
            return
        if DEBUG_LOG_CREDENTIALS:
            print(f"TEST LOGIN -> account_id: {account_id} password: {password}")
        token = f"session-{uuid.uuid4().hex[:10]}"
        self.settings.set("account_id", account_id)
        self.settings.set("session_token", token)
        self.settings.set("remember_me", remember)
        recent = self.settings.get("recent_account_ids", [])
        recent.append(account_id)
        self.settings.set("recent_account_ids", list(dict.fromkeys(recent))[-10:])
        self.settings.save()
        self.logger.log("log_login", account=account_id)
        self.stack.setCurrentWidget(self.shell)
        self.login_page.password_input.clear()
        animate_widget(self.shell)

    def logout(self) -> None:
        self.settings.set("session_token", "")
        self.settings.set("remember_me", False)
        self.settings.save()
        self.logger.log("log_logout")
        self.stack.setCurrentWidget(self.login_page)
        self.login_page.load_state()
        animate_widget(self.login_page)

    def set_language(self, lang: str) -> None:
        self.i18n.set_language(lang)
        self.settings.set("language", lang)
        self.settings.save()
        self.apply_font(lang)
        self.apply_translations()

    def handle_shell_event(self, event: str) -> None:
        if event == "refresh":
            self.shell.dashboard.refresh_clients()
            return
        if event.startswith("theme:"):
            self.apply_theme(event.split(":", 1)[1])
            self.settings.save()
            return
        if event.startswith("lang:"):
            self.set_language(event.split(":", 1)[1])
            return

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.settings.save()
        super().closeEvent(event)


def resolve_settings_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        path = Path(base) / "RemoteControllerOperator" / "settings.json"
    else:
        path = Path(__file__).resolve().parent / "data" / "settings.json"
    return path


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(resolve_settings_path())
    window.apply_font(window.i18n.language())
    window.show()
    return app.exec()


TRANSLATIONS.update(
    {
        "es": {
            "app_title": "Consola del operador",
            "app_subtitle": "Control remoto",
            "nav_main": "Clientes",
            "nav_compiler": "Compilador",
            "nav_settings": "Ajustes",
            "nav_instructions": "Instrucciones",
            "top_status_label": "Estado",
            "top_status_mock": "Simulado",
            "top_refresh": "Actualizar",
            "top_logout": "Cerrar sesión",
            "login_title": "Bienvenido de nuevo",
            "login_subtitle": "Inicia sesión con tu cuenta de operador",
            "login_account_id": "ID de cuenta",
            "login_password": "Contraseña",
            "login_remember": "Recuérdame",
            "login_button": "Iniciar sesión",
            "login_hint": "Usa tu ID de operador y contraseña",
            "login_language": "Idioma",
            "login_error_empty": "Introduce el ID de cuenta y la contraseña.",
            "login_error_failed": "Autenticación fallida. Revisa tus credenciales.",
            "login_success": "Sesión iniciada.",
            "main_title": "Clientes conectados",
            "main_subtitle": "Administra las sesiones remotas activas",
            "main_search_placeholder": "Buscar por nombre, ID, región o IP",
            "main_refresh_button": "Actualizar",
            "main_add_mock_button": "Añadir ejemplo",
            "main_last_sync": "Última sincronización",
            "main_last_sync_never": "Nunca",
            "main_status_ready": "Listo",
            "table_name": "Nombre",
            "table_id": "ID",
            "table_region": "Región",
            "table_ip": "IP",
            "table_storage": "Almacenamiento",
            "table_connect": "Conectar",
            "button_storage": "Almacenamiento",
            "button_connect": "Conectar",
            "button_connected": "Conectado",
            "button_disconnect": "Desconectar",
            "region_na": "Norteamérica",
            "region_eu": "Europa",
            "region_apac": "Asia-Pacífico",
            "region_sa": "Sudamérica",
            "region_mea": "Oriente Medio y África",
            "region_ru": "Rusia y CEI",
            "log_title": "Registro de sesión",
            "log_empty": "Sin actividad todavía",
            "log_login": "Sesión iniciada como {account}",
            "log_logout": "Sesión cerrada",
            "log_connect": "Conectando a {client}",
            "log_connected": "Conectado a {client}",
            "log_disconnect": "Desconectado de {client}",
            "log_storage_open": "Almacenamiento abierto para {client}",
            "log_storage_download": "Descarga en cola: {file}",
            "log_build_start": "Compilación iniciada para {entry}",
            "log_build_done": "Compilación completada: {output}",
            "log_build_failed": "Falló la compilación",
            "log_build_missing": "PyInstaller no está instalado.",
            "storage_title": "Almacenamiento remoto",
            "storage_subtitle": "Explora y descarga archivos del dispositivo remoto",
            "storage_remote_title": "Dispositivo remoto",
            "storage_local_title": "Descargas locales",
            "storage_path_label": "Ruta",
            "storage_go": "Ir",
            "storage_up": "Arriba",
            "storage_refresh": "Actualizar",
            "storage_action": "Acción",
            "storage_size": "Tamaño",
            "storage_download": "Descargar",
            "storage_empty": "No se encontraron archivos",
            "storage_local_empty": "Sin descargas",
            "storage_status_idle": "Inactivo",
            "storage_status_loading": "Cargando...",
            "storage_status_ready": "Listo",
            "storage_close": "Cerrar",
            "compiler_title": "Compilador EXE",
            "compiler_subtitle": "Empaqueta un cliente Windows desde una carpeta seleccionada",
            "compiler_source": "Carpeta de origen",
            "compiler_entry": "Archivo de entrada",
            "compiler_output_name": "Nombre de salida",
            "compiler_output_dir": "Carpeta de salida",
            "compiler_icon": "Icono (.ico)",
            "compiler_mode": "Modo de compilación",
            "compiler_console": "Consola",
            "compiler_mode_onefile": "Archivo único",
            "compiler_mode_onedir": "Carpeta",
            "compiler_console_show": "Mostrar consola",
            "compiler_console_hide": "Ocultar consola",
            "compiler_browse": "Buscar",
            "compiler_build": "Compilar",
            "compiler_clear": "Limpiar registro",
            "compiler_status_idle": "Inactivo",
            "compiler_status_building": "Compilando...",
            "compiler_status_done": "Completado",
            "compiler_status_failed": "Fallido",
            "compiler_log_placeholder": "La salida de la compilación aparecerá aquí.",
            "settings_title": "Ajustes",
            "settings_subtitle": "Personaliza tu consola de operador",
            "settings_theme": "Tema",
            "settings_theme_dark": "Oscuro",
            "settings_theme_light": "Claro",
            "settings_language": "Idioma",
            "settings_account": "Cuenta",
            "settings_logout": "Cerrar sesión",
            "settings_about": "Acerca de",
            "settings_about_body": "Consola del operador para soporte remoto autorizado en Windows 10/11.",
            "settings_data": "Datos",
            "settings_clear": "Borrar datos guardados",
            "settings_clear_done": "Datos guardados borrados.",
            "instructions_title": "Instrucciones",
            "instructions_subtitle": "Cómo usar la consola del operador",
            "instructions_body": """
            <h3>Inicio rápido</h3>
            <ol>
              <li>Inicia sesión con tu ID de operador y contraseña.</li>
              <li>Abre Clientes para ver los dispositivos conectados.</li>
              <li>Haz clic en Conectar para iniciar una sesión remota.</li>
              <li>Usa Almacenamiento para explorar y descargar archivos con permiso.</li>
              <li>Usa Compilador para crear un cliente Windows desde la carpeta seleccionada.</li>
              <li>En Ajustes cambia tema o idioma, o cierra sesión.</li>
            </ol>
            <h3>Seguridad y cumplimiento</h3>
            <ul>
              <li>Accede solo a dispositivos que estés autorizado a gestionar.</li>
              <li>Protege tokens e IDs de sesión como contraseñas.</li>
              <li>Conserva registros de auditoría de las sesiones.</li>
            </ul>
        """,
        "nav_teams": "Equipos",
        "teams_title": "Equipos",
        "teams_subtitle": "Gestiona equipos de operadores y suscripciones",
        "teams_list_title": "Lista de equipos",
        "teams_select_hint": "Selecciona un equipo para ver detalles",
        "team_name": "Nombre del equipo",
        "team_name_placeholder": "Introduce el nombre del equipo",
        "team_status": "Estado",
        "team_status_active": "Activo",
        "team_status_expired": "Vencido",
        "team_subscription": "Vence la suscripción",
        "team_renew": "Renovar suscripción",
        "team_members": "Miembros del equipo",
        "team_member_name": "Nombre",
        "team_member_tag": "Rol",
        "team_member_clients": "Clientes remotos",
        "team_add_member": "Añadir miembro",
        "team_remove_member": "Eliminar miembro",
        "team_add_dialog_title": "Añadir miembro del equipo",
        "team_add_name": "Nombre",
        "team_add_account_id": "ID de cuenta",
        "team_add_password": "Contraseña",
        "team_add_tag": "Rol",
        "team_add_confirm": "Añadir",
        "team_add_cancel": "Cancelar",
        "teams_no_members": "Sin miembros aún",
        "tag_operator": "Operador",
        "tag_administrator": "Administrador",
        "tag_moderator": "Moderador",
        "settings_role": "Rol",
        "settings_role_operator": "Operador",
        "settings_role_administrator": "Administrador",
        "settings_role_moderator": "Moderador",
        }
    }
)

TRANSLATIONS.update(
    {
        "ru": {
            "app_title": "Консоль оператора",
            "app_subtitle": "Удаленный контроллер",
            "nav_main": "Клиенты",
            "nav_compiler": "Сборщик",
            "nav_settings": "Настройки",
            "nav_instructions": "Инструкции",
            "top_status_label": "Статус",
            "top_status_mock": "Демо",
            "top_refresh": "Обновить",
            "top_logout": "Выйти",
            "login_title": "С возвращением",
            "login_subtitle": "Войдите в учетную запись оператора",
            "login_account_id": "ID аккаунта",
            "login_password": "Пароль",
            "login_remember": "Запомнить меня",
            "login_button": "Войти",
            "login_hint": "Используйте ID оператора и пароль",
            "login_language": "Язык",
            "login_error_empty": "Введите ID аккаунта и пароль.",
            "login_error_failed": "Не удалось войти. Проверьте учетные данные.",
            "login_success": "Вход выполнен.",
            "main_title": "Подключенные клиенты",
            "main_subtitle": "Управление активными удаленными сессиями",
            "main_search_placeholder": "Поиск по имени, ID, региону или IP",
            "main_refresh_button": "Обновить",
            "main_add_mock_button": "Добавить пример",
            "main_last_sync": "Последняя синхронизация",
            "main_last_sync_never": "Никогда",
            "main_status_ready": "Готово",
            "table_name": "Имя",
            "table_id": "ID",
            "table_region": "Регион",
            "table_ip": "IP",
            "table_storage": "Хранилище",
            "table_connect": "Подключение",
            "button_storage": "Хранилище",
            "button_connect": "Подключить",
            "button_connected": "Подключено",
            "button_disconnect": "Отключить",
            "region_na": "Северная Америка",
            "region_eu": "Европа",
            "region_apac": "Азиатско-Тихоокеанский регион",
            "region_sa": "Южная Америка",
            "region_mea": "Ближний Восток и Африка",
            "region_ru": "Россия и СНГ",
            "log_title": "Журнал сессии",
            "log_empty": "Пока нет активности",
            "log_login": "Вход: {account}",
            "log_logout": "Выход из системы",
            "log_connect": "Подключение к {client}",
            "log_connected": "Подключено: {client}",
            "log_disconnect": "Отключено: {client}",
            "log_storage_open": "Открыто хранилище: {client}",
            "log_storage_download": "Скачивание в очереди: {file}",
            "log_build_start": "Сборка началась: {entry}",
            "log_build_done": "Сборка завершена: {output}",
            "log_build_failed": "Ошибка сборки",
            "log_build_missing": "PyInstaller не установлен.",
            "storage_title": "Удаленное хранилище",
            "storage_subtitle": "Просматривайте и скачивайте файлы с удаленного устройства",
            "storage_remote_title": "Удаленное устройство",
            "storage_local_title": "Локальные загрузки",
            "storage_path_label": "Путь",
            "storage_go": "Перейти",
            "storage_up": "Вверх",
            "storage_refresh": "Обновить",
            "storage_action": "Действие",
            "storage_size": "Размер",
            "storage_download": "Скачать",
            "storage_empty": "Файлы не найдены",
            "storage_local_empty": "Загрузок пока нет",
            "storage_status_idle": "Ожидание",
            "storage_status_loading": "Загрузка...",
            "storage_status_ready": "Готово",
            "storage_close": "Закрыть",
            "compiler_title": "Сборщик EXE",
            "compiler_subtitle": "Соберите Windows-клиент из выбранной папки",
            "compiler_source": "Папка исходников",
            "compiler_entry": "Точка входа",
            "compiler_output_name": "Имя файла",
            "compiler_output_dir": "Папка вывода",
            "compiler_icon": "Иконка (.ico)",
            "compiler_mode": "Режим сборки",
            "compiler_console": "Консоль",
            "compiler_mode_onefile": "Один файл",
            "compiler_mode_onedir": "Папка",
            "compiler_console_show": "Показывать консоль",
            "compiler_console_hide": "Скрыть консоль",
            "compiler_browse": "Обзор",
            "compiler_build": "Собрать",
            "compiler_clear": "Очистить лог",
            "compiler_status_idle": "Ожидание",
            "compiler_status_building": "Сборка...",
            "compiler_status_done": "Готово",
            "compiler_status_failed": "Ошибка",
            "compiler_log_placeholder": "Здесь появится вывод сборки.",
            "settings_title": "Настройки",
            "settings_subtitle": "Персонализируйте консоль оператора",
            "settings_theme": "Тема",
            "settings_theme_dark": "Темная",
            "settings_theme_light": "Светлая",
            "settings_language": "Язык",
            "settings_account": "Аккаунт",
            "settings_logout": "Выйти",
            "settings_about": "О программе",
            "settings_about_body": "Консоль оператора для авторизованной удаленной поддержки Windows 10/11.",
            "settings_data": "Данные",
            "settings_clear": "Очистить сохраненные данные",
            "settings_clear_done": "Сохраненные данные очищены.",
            "instructions_title": "Инструкции",
            "instructions_subtitle": "Как пользоваться консолью оператора",
            "instructions_body": """
            <h3>Быстрый старт</h3>
            <ol>
              <li>Войдите, используя ID оператора и пароль.</li>
              <li>Откройте «Клиенты», чтобы увидеть подключенные устройства.</li>
              <li>Нажмите «Подключить», чтобы начать удаленную сессию.</li>
              <li>Используйте «Хранилище» для просмотра и скачивания файлов с разрешения.</li>
              <li>В «Сборщике» создайте Windows-клиент из выбранной папки.</li>
              <li>В «Настройках» меняйте тему, язык или выходите из аккаунта.</li>
            </ol>
            <h3>Безопасность и соответствие</h3>
            <ul>
              <li>Доступ только к устройствам, которыми вы уполномочены управлять.</li>
              <li>Защищайте токены и ID сессий как пароли.</li>
              <li>Сохраняйте аудит-логи для сессий поддержки.</li>
            </ul>
        """,
        "nav_teams": "Команда",
        "teams_title": "Команда",
        "teams_subtitle": "Управление командами и подписками",
        "teams_list_title": "Список команд",
        "teams_select_hint": "Выберите команду для просмотра",
        "team_name": "Название команды",
        "team_name_placeholder": "Введите название команды",
        "team_status": "Статус",
        "team_status_active": "Активна",
        "team_status_expired": "Истекла",
        "team_subscription": "Подписка до",
        "team_renew": "Продлить подписку",
        "team_members": "Участники",
        "team_member_name": "Имя",
        "team_member_tag": "Роль",
        "team_member_clients": "Удаленные клиенты",
        "team_add_member": "Добавить участника",
        "team_remove_member": "Удалить участника",
        "team_add_dialog_title": "Добавить участника",
        "team_add_name": "Имя",
        "team_add_account_id": "ID аккаунта",
        "team_add_password": "Пароль",
        "team_add_tag": "Роль",
        "team_add_confirm": "Добавить",
        "team_add_cancel": "Отмена",
        "teams_no_members": "Участников пока нет",
        "tag_operator": "Оператор",
        "tag_administrator": "Администратор",
        "tag_moderator": "Модератор",
        "settings_role": "Роль",
        "settings_role_operator": "Оператор",
        "settings_role_administrator": "Администратор",
        "settings_role_moderator": "Модератор",
        }
    }
)

if __name__ == "__main__":
    raise SystemExit(main())
