from datetime import datetime

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ..common import load_icon, make_button


class ClientDetailsPage(QtWidgets.QWidget):
    back_requested = QtCore.pyqtSignal()
    connect_requested = QtCore.pyqtSignal(str, bool)
    storage_requested = QtCore.pyqtSignal(str)
    extra_action_requested = QtCore.pyqtSignal(str, str)
    delete_requested = QtCore.pyqtSignal(str)
    rename_requested = QtCore.pyqtSignal(str)

    def __init__(self, i18n: I18n, settings: SettingsStore):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.client: dict | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        hero = QtWidgets.QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QtWidgets.QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        self.back_button = QtWidgets.QToolButton()
        self.back_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.back_button.setAutoRaise(True)
        self.back_button.setToolTip(self.i18n.t("client_details_back"))
        back_icon = load_icon("back", "dark")
        if not back_icon.isNull():
            self.back_button.setIcon(back_icon)
            self.back_button.setIconSize(QtCore.QSize(16, 16))
        else:
            self.back_button.setText("<")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(4)
        status_row = QtWidgets.QHBoxLayout()
        self.status_dot = QtWidgets.QLabel()
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setFixedSize(8, 8)
        self.status_text = QtWidgets.QLabel()
        self.status_text.setObjectName("Muted")
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        status_row.addStretch()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        title_box.addLayout(status_row)
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box, 1)

        self.rename_button = QtWidgets.QToolButton()
        self.rename_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.rename_button.setToolTip(self.i18n.t("button_edit_name"))
        self.rename_button.setAutoRaise(True)
        rename_icon = load_icon("rename", "dark")
        if not rename_icon.isNull():
            self.rename_button.setIcon(rename_icon)
            self.rename_button.setIconSize(QtCore.QSize(16, 16))
        else:
            self.rename_button.setText("?")
        self.rename_button.clicked.connect(self._emit_rename)
        header.addWidget(self.rename_button)

        hero_layout.addLayout(header)

        actions = QtWidgets.QHBoxLayout()
        self.connect_button = make_button("", "primary")
        self.connect_button.clicked.connect(self._toggle_connection)
        self.storage_button = make_button("", "ghost")
        self.storage_button.clicked.connect(self._open_storage)
        self.cookies_button = make_button("", "ghost")
        self.proxy_button = make_button("", "ghost")
        self.proxy_button.clicked.connect(self._export_proxy)
        self.delete_button = make_button("", "danger")
        self.delete_button.clicked.connect(self._delete_client)
        actions.addWidget(self.connect_button)
        actions.addWidget(self.storage_button)
        actions.addWidget(self.cookies_button)
        actions.addWidget(self.proxy_button)
        actions.addStretch()
        actions.addWidget(self.delete_button)
        hero_layout.addLayout(actions)

        layout.addWidget(hero)

        self.tabs = QtWidgets.QTabWidget()
        self.main_tab = QtWidgets.QWidget()
        self.cookies_tab = QtWidgets.QWidget()
        self.proxy_tab = QtWidgets.QWidget()
        self.storage_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.main_tab, "")
        self.tabs.addTab(self.cookies_tab, "")
        self.tabs.addTab(self.proxy_tab, "")
        self.tabs.addTab(self.storage_tab, "")
        layout.addWidget(self.tabs, 1)

        self._build_main_tab()
        self._build_cookies_tab()
        self._build_proxy_tab()
        self._build_storage_tab()
        self.apply_translations()

    def apply_translations(self) -> None:
        self.connect_button.setText(self.i18n.t("button_connect"))
        self.storage_button.setText(self.i18n.t("button_storage"))
        self.cookies_button.setText(self.i18n.t("menu_cookies_title"))
        self.proxy_button.setText(self.i18n.t("menu_proxy_download"))
        self.delete_button.setText(self.i18n.t("button_delete"))
        self.tabs.setTabText(0, self.i18n.t("client_tab_main"))
        self.tabs.setTabText(1, self.i18n.t("client_tab_cookies"))
        self.tabs.setTabText(2, self.i18n.t("client_tab_proxy"))
        self.tabs.setTabText(3, self.i18n.t("client_tab_storage"))
        self.client_info_title.setText(self.i18n.t("client_info_title"))
        self.system_info_title.setText(self.i18n.t("client_system_title"))
        self.cookies_title.setText(self.i18n.t("client_cookies_title"))
        self.proxy_title.setText(self.i18n.t("client_proxy_title"))
        self.proxy_body.setText(self.i18n.t("client_proxy_body"))
        self.proxy_action.setText(self.i18n.t("menu_proxy_download"))
        self.storage_title.setText(self.i18n.t("client_storage_title"))
        self.storage_body.setText(self.i18n.t("client_storage_body"))
        self.storage_action.setText(self.i18n.t("button_storage"))
        self._build_cookies_menu()
        self._update_view()

    def set_client(self, client: dict) -> None:
        self.client = dict(client)
        self._update_view()

    def _build_main_tab(self) -> None:
        layout = QtWidgets.QHBoxLayout(self.main_tab)
        layout.setSpacing(16)

        self.client_info_card = QtWidgets.QFrame()
        self.client_info_card.setObjectName("Card")
        client_layout = QtWidgets.QVBoxLayout(self.client_info_card)
        client_layout.setContentsMargins(14, 14, 14, 14)
        self.client_info_title = QtWidgets.QLabel()
        self.client_info_title.setStyleSheet("font-weight: 600;")
        client_layout.addWidget(self.client_info_title)
        self.client_info_form = QtWidgets.QFormLayout()
        self.client_info_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.client_info_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        client_layout.addLayout(self.client_info_form)

        self.system_info_card = QtWidgets.QFrame()
        self.system_info_card.setObjectName("Card")
        system_layout = QtWidgets.QVBoxLayout(self.system_info_card)
        system_layout.setContentsMargins(14, 14, 14, 14)
        self.system_info_title = QtWidgets.QLabel()
        self.system_info_title.setStyleSheet("font-weight: 600;")
        system_layout.addWidget(self.system_info_title)
        self.system_info_form = QtWidgets.QFormLayout()
        self.system_info_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.system_info_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        system_layout.addLayout(self.system_info_form)

        layout.addWidget(self.client_info_card, 1)
        layout.addWidget(self.system_info_card, 1)

    def _build_cookies_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.cookies_tab)
        layout.setSpacing(12)
        self.cookies_card = QtWidgets.QFrame()
        self.cookies_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.cookies_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.cookies_title = QtWidgets.QLabel()
        self.cookies_title.setStyleSheet("font-weight: 600;")
        card_layout.addWidget(self.cookies_title)
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        self.cookie_buttons: dict[str, QtWidgets.QPushButton] = {}
        for key in ["all", "chrome", "edge", "brave", "opera", "firefox"]:
            button = make_button("", "ghost")
            button.clicked.connect(
                lambda _, browser=key: self._emit_cookie(browser)
            )
            buttons.addWidget(button)
            self.cookie_buttons[key] = button
        buttons.addStretch()
        card_layout.addLayout(buttons)
        layout.addWidget(self.cookies_card)

    def _build_proxy_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.proxy_tab)
        layout.setSpacing(12)
        self.proxy_card = QtWidgets.QFrame()
        self.proxy_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.proxy_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.proxy_title = QtWidgets.QLabel()
        self.proxy_title.setStyleSheet("font-weight: 600;")
        self.proxy_body = QtWidgets.QLabel()
        self.proxy_body.setObjectName("Muted")
        self.proxy_body.setWordWrap(True)
        card_layout.addWidget(self.proxy_title)
        card_layout.addWidget(self.proxy_body)
        self.proxy_action = make_button("", "primary")
        self.proxy_action.clicked.connect(self._export_proxy)
        card_layout.addWidget(self.proxy_action, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.proxy_card)

    def _build_storage_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.storage_tab)
        layout.setSpacing(12)
        self.storage_card = QtWidgets.QFrame()
        self.storage_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.storage_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.storage_title = QtWidgets.QLabel()
        self.storage_title.setStyleSheet("font-weight: 600;")
        self.storage_body = QtWidgets.QLabel()
        self.storage_body.setObjectName("Muted")
        self.storage_body.setWordWrap(True)
        card_layout.addWidget(self.storage_title)
        card_layout.addWidget(self.storage_body)
        self.storage_action = make_button("", "primary")
        self.storage_action.clicked.connect(self._open_storage)
        card_layout.addWidget(self.storage_action, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.storage_card)

    def _build_cookies_menu(self) -> None:
        menu = QtWidgets.QMenu(self.cookies_button)
        cookie_actions = [
            ("all", self.i18n.t("menu_cookies_all")),
            ("chrome", self.i18n.t("menu_cookies_chrome")),
            ("edge", self.i18n.t("menu_cookies_edge")),
            ("brave", self.i18n.t("menu_cookies_brave")),
            ("opera", self.i18n.t("menu_cookies_opera")),
            ("firefox", self.i18n.t("menu_cookies_firefox")),
        ]
        for key, label in cookie_actions:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _, browser=key: self._emit_cookie(browser)
            )
        self.cookies_button.setMenu(menu)
        for key, button in self.cookie_buttons.items():
            label = dict(cookie_actions).get(key, key)
            button.setText(label)

    def _update_view(self) -> None:
        if not self.client:
            self.title_label.setText(self.i18n.t("client_details_title"))
            self.subtitle_label.setText("--")
            self.status_text.setText(self.i18n.t("top_status_unknown"))
            self._set_status_color(None)
            return
        name = self.client.get("name") or self.client.get("id") or "--"
        self.title_label.setText(name)
        self.subtitle_label.setText(self.client.get("id", ""))
        connected = self.client.get("status") == "connected" or self.client.get("connected")
        self.status_text.setText(
            self.i18n.t("top_status_online") if connected else self.i18n.t("top_status_offline")
        )
        self._set_status_color(connected)
        self._update_actions(connected)
        self._render_client_info()
        self._render_system_info()

    def _render_client_info(self) -> None:
        def _add_row(label: str, value: str) -> None:
            row = self.client_info_form.rowCount()
            self.client_info_form.insertRow(row, QtWidgets.QLabel(label), QtWidgets.QLabel(value))

        self._clear_form(self.client_info_form)
        client = self.client or {}
        region = self._safe_text(client.get("region"))
        if region != "--":
            region = self.i18n.t(region)
        _add_row(self.i18n.t("client_info_region"), region)
        _add_row(self.i18n.t("client_info_id"), self._safe_text(client.get("id")))
        _add_row(self.i18n.t("client_info_ip"), self._safe_text(client.get("ip")))
        _add_row(self.i18n.t("client_info_last_seen"), self._format_last_seen(client.get("last_seen")))
        _add_row(self.i18n.t("client_info_status"), self.status_text.text())
        _add_row(
            self.i18n.t("client_info_team"),
            self._resolve_team_name(client.get("assigned_team_id")),
        )
        _add_row(
            self.i18n.t("client_info_operator"),
            self._resolve_operator_name(client.get("assigned_operator_id")),
        )

    def _render_system_info(self) -> None:
        def _add_row(label: str, value: str) -> None:
            row = self.system_info_form.rowCount()
            self.system_info_form.insertRow(row, QtWidgets.QLabel(label), QtWidgets.QLabel(value))

        self._clear_form(self.system_info_form)
        client = self.client or {}
        config = client.get("client_config") if isinstance(client.get("client_config"), dict) else {}
        _add_row(self.i18n.t("client_system_pc"), self._safe_text(self._config_value(config, ["pc", "pc_name", "device", "device_name"])) )
        _add_row(self.i18n.t("client_system_cpu"), self._safe_text(self._config_value(config, ["cpu", "cpu_name"])))
        _add_row(self.i18n.t("client_system_ram"), self._safe_text(self._config_value(config, ["ram", "memory"])))
        _add_row(self.i18n.t("client_system_gpu"), self._safe_text(self._config_value(config, ["gpu", "graphics"])))
        _add_row(self.i18n.t("client_system_storage"), self._safe_text(self._config_value(config, ["storage", "disk"])))

    def _config_value(self, config: dict, keys: list[str]) -> str:
        for key in keys:
            value = config.get(key)
            if value:
                return str(value)
        return "--"

    def _resolve_team_name(self, team_id: object) -> str:
        value = str(team_id or "").strip()
        if not value:
            return "--"
        for team in self.settings.get("teams", []):
            if team.get("id") == value:
                return team.get("name") or value
        return value

    def _resolve_operator_name(self, operator_id: object) -> str:
        value = str(operator_id or "").strip()
        if not value:
            return "--"
        for team in self.settings.get("teams", []):
            for member in team.get("members", []):
                if member.get("account_id") == value:
                    return member.get("name") or value
        return value

    def _update_actions(self, connected: bool) -> None:
        if connected:
            self.connect_button.setText(self.i18n.t("button_connected"))
        else:
            self.connect_button.setText(self.i18n.t("button_connect"))

    def _set_status_color(self, connected: bool | None) -> None:
        if connected is None:
            status = "unknown"
        elif connected:
            status = "online"
        else:
            status = "offline"
        self.status_dot.setProperty("status", status)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _emit_cookie(self, browser: str) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.extra_action_requested.emit(client_id, f"cookies:{browser}")

    def _export_proxy(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.extra_action_requested.emit(client_id, "proxy")

    def _open_storage(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.storage_requested.emit(client_id)

    def _delete_client(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.delete_requested.emit(client_id)

    def _toggle_connection(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if not client_id:
            return
        connected = self.client.get("status") == "connected" or self.client.get("connected")
        self.connect_requested.emit(client_id, bool(connected))

    def _emit_rename(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.rename_requested.emit(client_id)

    @staticmethod
    def _clear_form(form: QtWidgets.QFormLayout) -> None:
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _safe_text(value: object) -> str:
        text = str(value or "").strip()
        return text or "--"

    @staticmethod
    def _format_last_seen(value: object) -> str:
        if value is None:
            return "--"
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            try:
                parsed = datetime.fromtimestamp(value)
            except Exception:
                return "--"
        else:
            text = str(value).strip()
            if not text:
                return "--"
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return "--"
        if parsed.tzinfo:
            parsed = parsed.astimezone()
            now = datetime.now(parsed.tzinfo)
        else:
            now = datetime.now()
        if parsed.date() == now.date():
            return parsed.strftime("%H:%M:%S")
        return parsed.strftime("%Y-%m-%d %H:%M")
