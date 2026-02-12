from PyQt6 import QtCore, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.constants import APP_VERSION
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.translations import LANGUAGE_NAMES
from ..common import GlassFrame, make_button


class SettingsPage(QtWidgets.QWidget):
    language_changed = QtCore.pyqtSignal(str)
    role_changed = QtCore.pyqtSignal(str)
    logout_requested = QtCore.pyqtSignal()
    profile_updated = QtCore.pyqtSignal()

    def __init__(self, i18n: I18n, settings: SettingsStore, api: RemoteControllerApi | None = None):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.api = api
        self._session_password: str | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(0, 0, 0, 0)

        self.save_profile_button = make_button("", "island")
        self.save_profile_button.clicked.connect(self.save_profile)
        self.data_button = make_button("", "island")
        self.data_button.clicked.connect(self.clear_data)
        self.data_status = QtWidgets.QLabel()
        self.data_status.setObjectName("Muted")
        self.error_log_button = make_button("", "island")
        self.error_log_button.clicked.connect(self.download_error_log)
        self.error_log_status = QtWidgets.QLabel()
        self.error_log_status.setObjectName("ProfileStatus")
        self.error_log_status.setProperty("status", "idle")

        toolbar = GlassFrame(radius=18, tone="card_alt", tint_alpha=160, border_alpha=70)
        toolbar.setObjectName("ToolbarCard")
        header = QtWidgets.QHBoxLayout(toolbar)
        header.setContentsMargins(16, 14, 16, 14)
        header_left = QtWidgets.QVBoxLayout()
        header_left.setSpacing(6)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        header_left.addWidget(self.title_label)
        header_left.addWidget(self.subtitle_label)
        header.addLayout(header_left, 1)
        layout.addWidget(toolbar)

        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("PageScrollViewport")
        scroll.viewport().setAutoFillBackground(False)
        scroll.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        scroll_content = QtWidgets.QWidget()
        scroll_content.setObjectName("PageScrollContent")
        scroll_content.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        content = QtWidgets.QVBoxLayout(scroll_content)
        content.setSpacing(14)
        content.setContentsMargins(0, 0, 0, 0)

        self.appearance_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.appearance_card.setObjectName("SettingsCard")
        appearance_layout = QtWidgets.QVBoxLayout(self.appearance_card)
        appearance_layout.setContentsMargins(14, 10, 14, 10)
        appearance_layout.setSpacing(8)
        self.appearance_title = QtWidgets.QLabel()
        self.appearance_title.setObjectName("CardSectionTitle")
        appearance_layout.addWidget(self.appearance_title)

        self.language_label = QtWidgets.QLabel()
        language_row = QtWidgets.QHBoxLayout()
        language_row.setSpacing(8)
        language_row.addWidget(self.language_label, 1)
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.setMinimumWidth(150)
        for code, name in LANGUAGE_NAMES.items():
            self.language_combo.addItem(name, code)
        language_row.addWidget(self.language_combo)
        appearance_layout.addLayout(language_row)
        content.addWidget(self.appearance_card)

        content.addSpacing(8)
        self.account_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.account_card.setObjectName("SettingsCard")
        account_layout = QtWidgets.QVBoxLayout(self.account_card)
        account_layout.setContentsMargins(14, 10, 14, 10)
        account_layout.setSpacing(8)
        self.account_label = QtWidgets.QLabel()
        self.account_label.setObjectName("CardSectionTitle")
        account_layout.addWidget(self.account_label)
        self.role_label = QtWidgets.QLabel()
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItem(self.i18n.t("settings_role_operator"), "operator")
        self.role_combo.addItem(self.i18n.t("settings_role_administrator"), "administrator")
        self.role_combo.addItem(self.i18n.t("settings_role_moderator"), "moderator")
        self.role_combo.setEnabled(False)
        self.role_combo.setMinimumWidth(150)
        role_row = QtWidgets.QHBoxLayout()
        role_row.setSpacing(8)
        role_row.addWidget(self.role_label, 1)
        role_row.addWidget(self.role_combo)
        account_layout.addLayout(role_row)

        self.login_label = QtWidgets.QLabel()
        self.login_input = QtWidgets.QLineEdit()
        self.login_input.setMinimumWidth(180)
        login_row = QtWidgets.QHBoxLayout()
        login_row.setSpacing(8)
        login_row.addWidget(self.login_label, 1)
        login_row.addWidget(self.login_input)
        account_layout.addLayout(login_row)

        self.name_label = QtWidgets.QLabel()
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setMinimumWidth(180)
        name_row = QtWidgets.QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(self.name_label, 1)
        name_row.addWidget(self.name_input)
        account_layout.addLayout(name_row)
        self.password_label = QtWidgets.QLabel()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_input.setMinimumWidth(180)
        password_row = QtWidgets.QHBoxLayout()
        password_row.setSpacing(8)
        password_row.addWidget(self.password_label, 1)
        password_row.addWidget(self.password_input)
        account_layout.addLayout(password_row)

        self.current_password_label = QtWidgets.QLabel()
        self.current_password_input = QtWidgets.QLineEdit()
        self.current_password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.current_password_input.setMinimumWidth(180)
        current_password_row = QtWidgets.QHBoxLayout()
        current_password_row.setSpacing(8)
        current_password_row.addWidget(self.current_password_label, 1)
        current_password_row.addWidget(self.current_password_input)
        account_layout.addLayout(current_password_row)

        self.profile_status = QtWidgets.QLabel()
        self.profile_status.setObjectName("ProfileStatus")
        self.profile_status.setProperty("status", "idle")
        account_layout.addWidget(self.profile_status)
        content.addWidget(self.account_card)

        actions_layout = QtWidgets.QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addStretch()
        actions_buttons = QtWidgets.QVBoxLayout()
        actions_buttons.setSpacing(6)
        actions_buttons.addWidget(
            self.save_profile_button,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        actions_buttons.addWidget(
            self.data_button,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        actions_buttons.addWidget(
            self.data_status,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        actions_buttons.addWidget(
            self.error_log_button,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        actions_buttons.addWidget(
            self.error_log_status,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        actions_layout.addLayout(actions_buttons)
        content.addLayout(actions_layout)

        self.about_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.about_card.setObjectName("SettingsCard")
        about_layout = QtWidgets.QVBoxLayout(self.about_card)
        about_layout.setContentsMargins(16, 12, 16, 12)
        about_layout.setSpacing(6)
        self.about_label = QtWidgets.QLabel()
        self.about_label.setObjectName("CardSectionTitle")
        self.about_body = QtWidgets.QLabel()
        self.about_body.setWordWrap(True)
        self.about_body.setObjectName("Muted")
        about_layout.addWidget(self.about_label)
        about_layout.addWidget(self.about_body)
        self.about_version = QtWidgets.QLabel()
        self.about_version.setObjectName("Muted")
        about_layout.addWidget(self.about_version)
        content.addWidget(self.about_card)
        content.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self.language_combo.currentIndexChanged.connect(self.emit_language)
        self.role_combo.currentIndexChanged.connect(self.emit_role)

        self.load_state()
        self.apply_translations()

    def load_state(self) -> None:
        lang = self.settings.get("language", "en")
        index = self.language_combo.findData(lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        role = self.settings.get("role", "operator")
        role_index = self.role_combo.findData(role)
        if role_index >= 0:
            self.role_combo.setCurrentIndex(role_index)
        self.login_input.setText(self._current_login())
        self.name_input.setText(self._current_display_name())
        self.password_input.clear()
        self.current_password_input.clear()
        self._sync_profile_state()
        self._sync_moderator_controls()

    def _current_login(self) -> str:
        return str(self.settings.get("account_id", "") or "").strip()

    def _current_display_name(self) -> str:
        display_name = str(self.settings.get("operator_name", "") or "").strip()
        if not display_name:
            display_name = str(self.settings.get("account_id", "") or "").strip()
        return display_name

    def set_session_password(self, password: str | None) -> None:
        self._session_password = password or None

    def set_role_value(self, role: str) -> None:
        role_index = self.role_combo.findData(role)
        if role_index < 0:
            return
        self.role_combo.blockSignals(True)
        self.role_combo.setCurrentIndex(role_index)
        self.role_combo.blockSignals(False)
        self._sync_moderator_controls()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("settings_title"))
        self.subtitle_label.setText(self.i18n.t("settings_subtitle"))
        self.appearance_title.setText(self.i18n.t("settings_appearance"))
        self.language_label.setText(self.i18n.t("settings_language"))
        self.account_label.setText(self.i18n.t("settings_account"))
        self.role_label.setText(self.i18n.t("settings_role"))
        self.role_combo.setItemText(0, self.i18n.t("settings_role_operator"))
        self.role_combo.setItemText(1, self.i18n.t("settings_role_administrator"))
        self.role_combo.setItemText(2, self.i18n.t("settings_role_moderator"))
        self.login_label.setText(self.i18n.t("settings_login"))
        self.login_input.setPlaceholderText(self.i18n.t("settings_login_placeholder"))
        self.name_label.setText(self.i18n.t("settings_name"))
        self.name_input.setPlaceholderText(self.i18n.t("settings_name_placeholder"))
        self.password_label.setText(self.i18n.t("settings_password"))
        self.password_input.setPlaceholderText(self.i18n.t("settings_password_placeholder"))
        self.current_password_label.setText(self.i18n.t("settings_current_password"))
        self.current_password_input.setPlaceholderText(self.i18n.t("settings_current_password_placeholder"))
        self.save_profile_button.setText(self.i18n.t("settings_save"))
        self.error_log_button.setText(self.i18n.t("settings_error_log_download"))
        self.about_label.setText(self.i18n.t("settings_about"))
        self.about_body.setText(self.i18n.t("settings_about_body"))
        self.about_version.setText(
            f'{self.i18n.t("settings_version")}: {APP_VERSION or "-"}'
        )
        self.data_button.setText(self.i18n.t("settings_clear"))
        self._sync_profile_state()
        self._sync_moderator_controls()

    def _set_profile_status(self, message: str, status: str = "idle") -> None:
        self.profile_status.setText(message)
        self.profile_status.setProperty("status", status)
        self.profile_status.style().unpolish(self.profile_status)
        self.profile_status.style().polish(self.profile_status)

    def _set_error_log_status(self, message: str, status: str = "idle") -> None:
        self.error_log_status.setText(message)
        self.error_log_status.setProperty("status", status)
        self.error_log_status.style().unpolish(self.error_log_status)
        self.error_log_status.style().polish(self.error_log_status)

    def _sync_profile_state(self) -> None:
        account_id = str(self.settings.get("account_id", "") or "").strip()
        enabled = bool(account_id) and self.api is not None
        for widget in (
            self.login_input,
            self.name_input,
            self.password_input,
            self.current_password_input,
            self.save_profile_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            if not account_id:
                self._set_profile_status(self.i18n.t("settings_profile_signin"), "idle")
            else:
                self._set_profile_status(self.i18n.t("settings_profile_unavailable"), "error")
            return
        if self.profile_status.property("status") == "idle":
            self._set_profile_status("", "idle")

    def _sync_moderator_controls(self) -> None:
        role = str(self.settings.get("role", "operator") or "operator")
        is_moderator = role == "moderator"
        self.error_log_button.setVisible(is_moderator)
        self.error_log_status.setVisible(is_moderator)
        if not is_moderator:
            return
        account_id = str(self.settings.get("account_id", "") or "").strip()
        enabled = bool(account_id) and self.api is not None
        self.error_log_button.setEnabled(enabled)
        if not enabled and self.error_log_status.text():
            self._set_error_log_status("", "idle")

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
            self._sync_moderator_controls()

    def save_profile(self) -> None:
        account_id = str(self.settings.get("account_id", "") or "").strip()
        if not account_id:
            self._set_profile_status(self.i18n.t("settings_profile_signin"), "error")
            return
        if self.api is None:
            self._set_profile_status(self.i18n.t("settings_profile_unavailable"), "error")
            return

        new_login = self.login_input.text().strip()
        name = self.name_input.text().strip()
        password = self.password_input.text()
        current_password = self.current_password_input.text()

        login_changed = new_login and new_login != account_id
        updates: dict[str, str] = {}
        if name:
            updates["name"] = name
        if password:
            updates["password"] = password

        if not updates and not login_changed:
            self._set_profile_status(self.i18n.t("settings_profile_missing"), "error")
            return

        if not current_password:
            self._set_profile_status(self.i18n.t("settings_current_password_required"), "error")
            return

        try:
            self.api.authenticate_operator(account_id, current_password)
        except Exception:
            self._set_profile_status(self.i18n.t("settings_current_password_invalid"), "error")
            return

        if login_changed:
            try:
                self.api.update_operator_login(account_id, new_login)
                self.settings.set("account_id", new_login)
                self.settings.save()
                account_id = new_login
            except Exception:
                self._set_profile_status(self.i18n.t("settings_login_update_failed"), "error")
                return

        if updates:
            legacy_fallback = False
            try:
                self.api.update_operator_profile(
                    account_id,
                    updates.get("name"),
                    updates.get("password"),
                )
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                legacy_fallback = status in (404, 405)
                if not legacy_fallback:
                    self._set_profile_status(self.i18n.t("settings_profile_failed"), "error")
                    return
            if legacy_fallback:
                if "password" not in updates and self._session_password:
                    updates["password"] = self._session_password
                if "password" not in updates:
                    updates["password"] = current_password
                fallback_name = updates.get("name") or self._current_display_name()
                role = str(self.settings.get("role", "operator") or "operator")
                team = str(self.settings.get("operator_team_id", "") or "").strip() or None
                try:
                    self.api.upsert_operator(account_id, fallback_name, updates["password"], role, team)
                except Exception:
                    self._set_profile_status(self.i18n.t("settings_profile_failed"), "error")
                    return
            if "name" in updates:
                self.settings.set("operator_name", updates["name"])
                self.settings.save()
            else:
                self.name_input.setText(self._current_display_name())
            if "password" in updates:
                self._session_password = updates["password"]

        self.login_input.setText(self._current_login())
        self.password_input.clear()
        self.current_password_input.clear()
        self._set_profile_status(self.i18n.t("settings_profile_saved"), "success")
        if "name" in updates or login_changed:
            self.profile_updated.emit()

    def clear_data(self) -> None:
        self.settings.clear_user_data()
        self.data_status.setText(self.i18n.t("settings_clear_done"))
        self.load_state()

    def download_error_log(self) -> None:
        if self.api is None:
            self._set_error_log_status(self.i18n.t("settings_error_log_unavailable"), "error")
            return
        account_id = str(self.settings.get("account_id", "") or "").strip()
        if not account_id:
            self._set_error_log_status(self.i18n.t("settings_error_log_signin"), "error")
            return
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.i18n.t("settings_error_log_download"),
            "signaling-error.log",
            "Log files (*.log);;Text files (*.txt);;All files (*.*)",
        )
        if not file_path:
            return
        try:
            payload = self.api.download_error_log()
            with open(file_path, "wb") as handle:
                handle.write(payload)
        except Exception:
            self._set_error_log_status(self.i18n.t("settings_error_log_failed"), "error")
            return
        self._set_error_log_status(self.i18n.t("settings_error_log_saved"), "success")
