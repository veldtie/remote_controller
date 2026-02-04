import uuid
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.constants import APP_NAME, APP_VERSION, DEBUG_LOG_CREDENTIALS
from ..core.api import DEFAULT_API_TOKEN, DEFAULT_API_URL, RemoteControllerApi
from ..core.i18n import I18n
from ..core.logging import EventLogger
from ..core.settings import SettingsStore
from ..core.theme import THEMES, build_stylesheet, select_font_for_language
from .common import BackgroundWidget, GlassFrame, animate_widget
from .pages.login import LoginPage
from .shell import MainShell


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, settings_path):
        super().__init__()
        self.settings = SettingsStore(settings_path)
        self.i18n = I18n(self.settings)
        self.logger = EventLogger(self.settings, self.i18n)
        api_url, api_token = self._ensure_api_settings()
        self.api = RemoteControllerApi(base_url=api_url, token=api_token)
        self._reset_server_cache()

        title = APP_NAME
        if APP_VERSION:
            title = f"{title} v{APP_VERSION}"
        self.setWindowTitle(title)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icons" / "icon.ico"
        if icon_path.exists():
            icon = QtGui.QIcon(str(icon_path))
            self.setWindowIcon(icon)
            app = QtWidgets.QApplication.instance()
            if app:
                app.setWindowIcon(icon)
        self.resize(1280, 800)

        self.theme = THEMES["dark"]
        self.background = BackgroundWidget(self.theme)
        self.setCentralWidget(self.background)

        self.window_frame = GlassFrame(radius=30, tone="card_strong", tint_alpha=190, border_alpha=80)
        self.window_frame.setObjectName("WindowFrame")
        frame_layout = QtWidgets.QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(18, 18, 18, 18)
        frame_layout.setSpacing(14)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.window_frame)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 20)
        shadow.setColor(QtGui.QColor(0, 0, 0, 155))
        self.window_frame.setGraphicsEffect(shadow)

        self.header_row = QtWidgets.QFrame()
        self.header_row.setObjectName("HeaderRow")
        header_layout = QtWidgets.QHBoxLayout(self.header_row)
        header_layout.setContentsMargins(6, 0, 6, 0)
        header_layout.setSpacing(8)
        self.header_title = QtWidgets.QLabel()
        self.header_title.setObjectName("ChromeTitle")
        header_layout.addWidget(self.header_title)
        header_layout.addStretch()
        frame_layout.addWidget(self.header_row)

        self.stack = QtWidgets.QStackedWidget()
        self.login_page = LoginPage(self.i18n, self.settings)
        self.shell = MainShell(self.i18n, self.settings, self.logger, api=self.api)
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.shell)
        frame_layout.addWidget(self.stack, 1)

        bg_layout = QtWidgets.QVBoxLayout(self.background)
        bg_layout.setContentsMargins(24, 24, 24, 24)
        bg_layout.addWidget(self.window_frame)

        self.login_page.login_requested.connect(self.handle_login)
        self.login_page.language_changed.connect(self.set_language)
        self.shell.logout_requested.connect(self.logout)
        self.shell.page_changed.connect(self.handle_shell_event)

        self.apply_theme("dark")
        self.apply_translations()
        self.restore_session()

    def apply_font(self, language: str) -> None:
        font_name = select_font_for_language(language)
        QtWidgets.QApplication.instance().setFont(QtGui.QFont(font_name, 10))

    def apply_theme(self, theme_name: str) -> None:
        self.theme = THEMES["dark"]
        self.background.set_theme(self.theme)
        self.settings.set("theme", "dark")
        self.setStyleSheet(build_stylesheet(self.theme))
        self.shell.teams_page.apply_theme(self.theme)
        self.shell.dashboard.apply_theme(self.theme)

    def apply_translations(self) -> None:
        self.set_header(APP_NAME)
        self.login_page.apply_translations()
        self.shell.apply_translations()

    def set_header(self, title: str, subtitle: str | None = None) -> None:
        if self.header_title:
            self.header_title.setText(title)

    def _reset_server_cache(self) -> None:
        self.settings.set("clients", [])
        self.settings.set("teams", [])
        self.settings.set("operators", [])
        self.settings.save()

    def _ensure_api_settings(self) -> tuple[str, str]:
        api_url = str(self.settings.get("api_url", "") or "").strip()
        api_token = str(self.settings.get("api_token", "") or "").strip()
        updated = False
        if not api_url:
            api_url = DEFAULT_API_URL
            self.settings.set("api_url", api_url)
            updated = True
        if not api_token and DEFAULT_API_TOKEN:
            api_token = DEFAULT_API_TOKEN
            self.settings.set("api_token", api_token)
            updated = True
        if updated:
            self.settings.save()
        return api_url, api_token

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
        team_id = operator.get("team", "")
        self.settings.set("role", role)
        self.settings.set("operator_name", name)
        self.settings.set("operator_team_id", team_id)
        self.shell.settings_page.set_role_value(role)
        self.shell.handle_role_change(role)
        self.shell.update_operator_label()

    def _authenticate_operator(self, account_id: str, password: str) -> dict | None:
        if not account_id or not password:
            return None
        try:
            operator = self.api.authenticate_operator(account_id, password)
        except Exception:
            return None
        if not operator or not operator.get("role"):
            return None
        return operator

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
        operator = self._authenticate_operator(account_id, password)
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
        self.shell.settings_page.set_session_password(password)
        self.logger.log("log_login", account=account_id)
        self.stack.setCurrentWidget(self.shell)
        self.login_page.password_input.clear()
        animate_widget(self.shell)

    def logout(self) -> None:
        self.settings.set("session_token", "")
        self.settings.set("remember_me", False)
        self.settings.save()
        self.shell.settings_page.set_session_password(None)
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
        if event.startswith("lang:"):
            self.set_language(event.split(":", 1)[1])
            return

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.settings.save()
        super().closeEvent(event)
