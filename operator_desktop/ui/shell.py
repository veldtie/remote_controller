from typing import Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.api import RemoteControllerApi
from ..core.i18n import I18n
from ..core.logging import EventLogger
from ..core.settings import SettingsStore
from .common import animate_widget, make_button
from .dialogs import StorageDialog
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
        self.dashboard.delete_requested.connect(self.handle_delete_request)
        self.dashboard.ping_updated.connect(self.update_ping)
        self.dashboard.server_status_changed.connect(self.handle_server_status)
        self.settings_page.logout_requested.connect(self.logout_requested.emit)
        self.settings_page.theme_changed.connect(self.emit_theme_change)
        self.settings_page.language_changed.connect(self.emit_language_change)
        self.settings_page.role_changed.connect(self.handle_role_change)
        self.teams_page.teams_updated.connect(self.update_operator_label)

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
        self.banner_text.setText(self.i18n.t("server_connection_lost"))
        self.banner_retry.setText(self.i18n.t("server_connection_retry"))
        self._render_status_label()
        self.update_operator_label()
        self.dashboard.apply_translations()
        self.teams_page.apply_translations()
        self.compiler.apply_translations()
        self.settings_page.apply_translations()
        self.instructions_page.apply_translations()
        self._render_ping_label()
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
        if key == "teams":
            self.teams_page.refresh_from_api()
        animate_widget(self.stack.currentWidget())

    def update_role_visibility(self) -> None:
        self.nav_buttons["teams"].setVisible(True)

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

    def handle_delete_request(self, client_id: str) -> None:
        client = next((c for c in self.dashboard.clients if c["id"] == client_id), None)
        client_name = client["name"] if client else client_id
        self.logger.log("log_delete_requested", client=client_name)
        self.send_silent_uninstall(client_id, client_name)

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
        self.operator_label.setText(f'{self.i18n.t("operator_label")}: {label}')

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
