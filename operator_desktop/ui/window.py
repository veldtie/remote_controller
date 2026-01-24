import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.constants import APP_NAME, DEBUG_LOG_CREDENTIALS
from ..core.api import RemoteControllerApi
from ..core.i18n import I18n
from ..core.logging import EventLogger
from ..core.settings import SettingsStore
from ..core.theme import THEMES, build_stylesheet, select_font_for_language
from .common import BackgroundWidget, animate_widget
from .pages.login import LoginPage
from .shell import MainShell


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, settings_path):
        super().__init__()
        self.settings = SettingsStore(settings_path)
        self.i18n = I18n(self.settings)
        self.logger = EventLogger(self.settings, self.i18n)
        self.api = RemoteControllerApi()
        self._reset_server_cache()

        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)

        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])
        self.background = BackgroundWidget(self.theme)
        self.setCentralWidget(self.background)

        self.stack = QtWidgets.QStackedWidget()
        self.login_page = LoginPage(self.i18n, self.settings)
        self.shell = MainShell(self.i18n, self.settings, self.logger, api=self.api)
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
        self.shell.dashboard.apply_theme(self.theme)

    def apply_translations(self) -> None:
        self.login_page.apply_translations()
        self.shell.apply_translations()

    def _reset_server_cache(self) -> None:
        self.settings.set("clients", [])
        self.settings.set("teams", [])
        self.settings.set("operators", [])
        self.settings.save()

    def _fetch_operator_profile(self, account_id: str) -> dict | None:
        if not account_id:
            return None
        try:
            operator = self.api.fetch_operator(account_id)
        except Exception:
            return None
        if not operator or not operator.get("role"):
            return None
        return operator

    def _apply_operator_profile(self, operator: dict) -> None:
        role = operator.get("role", "operator")
        name = operator.get("name", "")
        self.settings.set("role", role)
        self.settings.set("operator_name", name)
        self.shell.settings_page.set_role_value(role)
        self.shell.handle_role_change(role)
        self.shell.update_operator_label()

    def restore_session(self) -> None:
        remember = self.settings.get("remember_me", False)
        token = self.settings.get("session_token", "")
        account = self.settings.get("account_id", "")
        if remember and token and account:
            operator = self._fetch_operator_profile(account)
            if not operator:
                self.stack.setCurrentWidget(self.login_page)
                return
            self._apply_operator_profile(operator)
            self.settings.save()
            self.logger.log("log_login", account=account)
            self.stack.setCurrentWidget(self.shell)
            self.shell.dashboard.refresh_logs()
        else:
            self.stack.setCurrentWidget(self.login_page)

    def handle_login(self, account_id: str, password: str, remember: bool) -> None:
        if not account_id or not password:
            self.login_page.status_label.setText(self.i18n.t("login_error_empty"))
            return
        operator = self._fetch_operator_profile(account_id)
        if not operator:
            self.login_page.status_label.setText(self.i18n.t("login_error_failed"))
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
        self._apply_operator_profile(operator)
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
