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
    _DEFAULT_WINDOW_SIZE = QtCore.QSize(1280, 800)
    _MIN_WINDOW_SIZE = QtCore.QSize(1100, 700)
    _RESIZE_MARGIN = 8

    def __init__(self, settings_path):
        super().__init__()
        self._drag_active = False
        self._drag_offset = QtCore.QPoint()
        self._resize_active = False
        self._resize_edges: str | None = None
        self._resize_start_pos = QtCore.QPoint()
        self._resize_start_geom = QtCore.QRect()
        self._last_normal_size: QtCore.QSize | None = None
        self._chrome_buttons: list[QtWidgets.QToolButton] = []
        self.chrome_bar: QtWidgets.QFrame | None = None

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

        self.header_title = QtWidgets.QLabel()
        self.header_title.setObjectName("ChromeTitle")
        self.chrome_bar = self._build_chrome_bar()
        frame_layout.addWidget(self.chrome_bar)

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

        self._configure_window_chrome()
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

    def _configure_window_chrome(self) -> None:
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._enable_mouse_tracking(self)
        self.setMinimumSize(self._MIN_WINDOW_SIZE)
        self._apply_saved_window_size()
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _enable_mouse_tracking(self, widget: QtWidgets.QWidget) -> None:
        widget.setMouseTracking(True)
        for child in widget.findChildren(QtWidgets.QWidget):
            child.setMouseTracking(True)

    def _build_chrome_bar(self) -> QtWidgets.QFrame:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ChromeBar")
        bar.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        controls = QtWidgets.QFrame(bar)
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self._close_button = self._make_chrome_button("close", self.close, "Close")
        self._min_button = self._make_chrome_button("minimize", self.showMinimized, "Minimize")
        self._max_button = self._make_chrome_button("zoom", self._toggle_maximize, "Maximize")

        controls_layout.addWidget(self._close_button)
        controls_layout.addWidget(self._min_button)
        controls_layout.addWidget(self._max_button)

        layout.addWidget(controls, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.header_title, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch()
        return bar

    def _make_chrome_button(
        self, role: str, callback, tooltip: str | None = None
    ) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setObjectName("ChromeDot")
        button.setProperty("dot", role)
        button.setAutoRaise(True)
        button.setFixedSize(12, 12)
        button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(callback)
        self._chrome_buttons.append(button)
        return button

    def _apply_saved_window_size(self) -> None:
        size = self.settings.get("window_size", {}) or {}
        width = int(size.get("width") or 0)
        height = int(size.get("height") or 0)
        if width > 0 and height > 0:
            width = max(width, self._MIN_WINDOW_SIZE.width())
            height = max(height, self._MIN_WINDOW_SIZE.height())
            self.resize(width, height)
        else:
            self.resize(self._DEFAULT_WINDOW_SIZE)
        self._last_normal_size = self.size()

    def _persist_window_size(self) -> None:
        size = self._last_normal_size or self.size()
        self.settings.set(
            "window_size",
            {"width": int(size.width()), "height": int(size.height())},
        )

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _event_global_pos(self, event: QtGui.QMouseEvent) -> QtCore.QPoint:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def _hit_test_edges(self, pos: QtCore.QPoint) -> str | None:
        if self.isMaximized() or self.isFullScreen():
            return None
        margin = self._RESIZE_MARGIN
        width = self.rect().width()
        height = self.rect().height()
        left = pos.x() <= margin
        right = pos.x() >= width - margin
        top = pos.y() <= margin
        bottom = pos.y() >= height - margin
        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _update_resize_cursor(self, edges: str | None) -> None:
        if self._resize_active or self._drag_active:
            return
        if edges is None:
            self.unsetCursor()
            return
        if edges in ("left", "right"):
            shape = QtCore.Qt.CursorShape.SizeHorCursor
        elif edges in ("top", "bottom"):
            shape = QtCore.Qt.CursorShape.SizeVerCursor
        elif edges in ("top_left", "bottom_right"):
            shape = QtCore.Qt.CursorShape.SizeFDiagCursor
        elif edges in ("top_right", "bottom_left"):
            shape = QtCore.Qt.CursorShape.SizeBDiagCursor
        else:
            self.unsetCursor()
            return
        self.setCursor(QtGui.QCursor(shape))

    def _perform_resize(self, global_pos: QtCore.QPoint) -> None:
        if not self._resize_edges:
            return
        delta = global_pos - self._resize_start_pos
        geom = QtCore.QRect(self._resize_start_geom)
        if "left" in self._resize_edges:
            geom.setLeft(geom.left() + delta.x())
        if "right" in self._resize_edges:
            geom.setRight(geom.right() + delta.x())
        if "top" in self._resize_edges:
            geom.setTop(geom.top() + delta.y())
        if "bottom" in self._resize_edges:
            geom.setBottom(geom.bottom() + delta.y())

        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        if geom.width() < min_w:
            if "left" in self._resize_edges:
                geom.setLeft(geom.right() - min_w + 1)
            else:
                geom.setRight(geom.left() + min_w - 1)
        if geom.height() < min_h:
            if "top" in self._resize_edges:
                geom.setTop(geom.bottom() - min_h + 1)
            else:
                geom.setBottom(geom.top() + min_h - 1)
        self.setGeometry(geom)

    def _is_chrome_button(self, obj: QtCore.QObject) -> bool:
        for button in self._chrome_buttons:
            if obj is button:
                return True
        return False

    def _is_drag_area(self, obj: QtCore.QObject) -> bool:
        if self.isMaximized() or self.isFullScreen():
            return False
        if self.chrome_bar is None:
            return False
        if obj is self.chrome_bar or self.chrome_bar.isAncestorOf(obj):
            return not self._is_chrome_button(obj)
        return False

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not isinstance(obj, QtWidgets.QWidget) or obj.window() is not self:
            return super().eventFilter(obj, event)

        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            if (
                isinstance(event, QtGui.QMouseEvent)
                and event.button() == QtCore.Qt.MouseButton.LeftButton
                and self._is_drag_area(obj)
            ):
                self._toggle_maximize()
                return True

        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if not isinstance(event, QtGui.QMouseEvent):
                return super().eventFilter(obj, event)
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                if self._is_chrome_button(obj):
                    return super().eventFilter(obj, event)
                global_pos = self._event_global_pos(event)
                pos = self.mapFromGlobal(global_pos)
                edges = self._hit_test_edges(pos)
                if edges:
                    self._resize_active = True
                    self._resize_edges = edges
                    self._resize_start_pos = global_pos
                    self._resize_start_geom = self.geometry()
                    return True
                if self._is_drag_area(obj):
                    self._drag_active = True
                    self._drag_offset = global_pos - self.frameGeometry().topLeft()
                    return True

        if event.type() == QtCore.QEvent.Type.MouseMove:
            if not isinstance(event, QtGui.QMouseEvent):
                return super().eventFilter(obj, event)
            global_pos = self._event_global_pos(event)
            pos = self.mapFromGlobal(global_pos)
            if self._resize_active:
                self._perform_resize(global_pos)
                return True
            if self._drag_active:
                self.move(global_pos - self._drag_offset)
                return True
            self._update_resize_cursor(self._hit_test_edges(pos))

        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            if not isinstance(event, QtGui.QMouseEvent):
                return super().eventFilter(obj, event)
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                if self._resize_active or self._drag_active:
                    self._resize_active = False
                    self._drag_active = False
                    self._resize_edges = None
                    self._update_resize_cursor(None)
                    return True

        if event.type() == QtCore.QEvent.Type.Leave:
            if not self._resize_active and not self._drag_active:
                self._update_resize_cursor(None)

        return super().eventFilter(obj, event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self.isMaximized() and not self.isFullScreen():
            self._last_normal_size = self.size()

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
        self._persist_window_size()
        self.settings.save()
        super().closeEvent(event)
