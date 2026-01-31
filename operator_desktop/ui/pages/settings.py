from PyQt6 import QtCore, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.translations import LANGUAGE_NAMES
from ..common import make_button


class SettingsPage(QtWidgets.QWidget):
    theme_changed = QtCore.pyqtSignal(str)
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

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        content = QtWidgets.QVBoxLayout()
        content.setSpacing(12)

        self.theme_card = QtWidgets.QFrame()
        self.theme_card.setObjectName("SettingsCard")
        theme_layout = QtWidgets.QHBoxLayout(self.theme_card)
        theme_layout.setContentsMargins(16, 12, 16, 12)
        theme_layout.setSpacing(12)
        self.theme_label = QtWidgets.QLabel()
        self.theme_label.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self.theme_label, 1)
        theme_buttons = QtWidgets.QHBoxLayout()
        theme_buttons.setSpacing(6)
        self.theme_dark = make_button("", "ghost")
        self.theme_light = make_button("", "ghost")
        self.theme_dark.setCheckable(True)
        self.theme_light.setCheckable(True)
        self.theme_dark.setMinimumWidth(90)
        self.theme_light.setMinimumWidth(90)
        self.theme_group = QtWidgets.QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_group.addButton(self.theme_dark)
        self.theme_group.addButton(self.theme_light)
        theme_buttons.addWidget(self.theme_dark)
        theme_buttons.addWidget(self.theme_light)
        theme_layout.addLayout(theme_buttons)
        content.addWidget(self.theme_card)

        self.language_card = QtWidgets.QFrame()
        self.language_card.setObjectName("SettingsCard")
        lang_layout = QtWidgets.QHBoxLayout(self.language_card)
        lang_layout.setContentsMargins(16, 12, 16, 12)
        lang_layout.setSpacing(12)
        self.language_label = QtWidgets.QLabel()
        self.language_label.setStyleSheet("font-weight: 600;")
        lang_layout.addWidget(self.language_label, 1)
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.setMinimumWidth(180)
        for code, name in LANGUAGE_NAMES.items():
            self.language_combo.addItem(name, code)
        lang_layout.addWidget(self.language_combo)
        content.addWidget(self.language_card)

        self.account_card = QtWidgets.QFrame()
        self.account_card.setObjectName("SettingsCard")
        account_layout = QtWidgets.QVBoxLayout(self.account_card)
        account_layout.setContentsMargins(16, 12, 16, 12)
        account_layout.setSpacing(10)
        self.account_label = QtWidgets.QLabel()
        self.account_label.setStyleSheet("font-weight: 600;")
        account_layout.addWidget(self.account_label)
        self.role_label = QtWidgets.QLabel()
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItem(self.i18n.t("settings_role_operator"), "operator")
        self.role_combo.addItem(self.i18n.t("settings_role_administrator"), "administrator")
        self.role_combo.addItem(self.i18n.t("settings_role_moderator"), "moderator")
        self.role_combo.setEnabled(False)
        self.role_combo.setMinimumWidth(180)
        role_row = QtWidgets.QHBoxLayout()
        role_row.setSpacing(12)
        role_row.addWidget(self.role_label, 1)
        role_row.addWidget(self.role_combo)
        account_layout.addLayout(role_row)
        self.profile_label = QtWidgets.QLabel()
        self.profile_label.setStyleSheet("font-weight: 600;")
        account_layout.addWidget(self.profile_label)
        self.name_label = QtWidgets.QLabel()
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setMinimumWidth(220)
        name_row = QtWidgets.QHBoxLayout()
        name_row.setSpacing(12)
        name_row.addWidget(self.name_label, 1)
        name_row.addWidget(self.name_input)
        account_layout.addLayout(name_row)
        self.password_label = QtWidgets.QLabel()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_input.setMinimumWidth(220)
        password_row = QtWidgets.QHBoxLayout()
        password_row.setSpacing(12)
        password_row.addWidget(self.password_label, 1)
        password_row.addWidget(self.password_input)
        account_layout.addLayout(password_row)
        self.password_confirm_label = QtWidgets.QLabel()
        self.password_confirm_input = QtWidgets.QLineEdit()
        self.password_confirm_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_confirm_input.setMinimumWidth(220)
        confirm_row = QtWidgets.QHBoxLayout()
        confirm_row.setSpacing(12)
        confirm_row.addWidget(self.password_confirm_label, 1)
        confirm_row.addWidget(self.password_confirm_input)
        account_layout.addLayout(confirm_row)
        self.save_profile_button = make_button("", "primary")
        self.save_profile_button.clicked.connect(self.save_profile)
        save_row = QtWidgets.QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self.save_profile_button)
        account_layout.addLayout(save_row)
        self.profile_status = QtWidgets.QLabel()
        self.profile_status.setObjectName("ProfileStatus")
        self.profile_status.setProperty("status", "idle")
        account_layout.addWidget(self.profile_status)
        account_layout.addSpacing(6)
        self.data_label = QtWidgets.QLabel()
        self.data_label.setStyleSheet("font-weight: 600;")
        self.data_button = make_button("", "ghost")
        self.data_button.clicked.connect(self.clear_data)
        self.data_status = QtWidgets.QLabel()
        self.data_status.setObjectName("Muted")
        data_row = QtWidgets.QHBoxLayout()
        data_row.setSpacing(12)
        data_row.addWidget(self.data_label, 1)
        data_row.addWidget(self.data_button)
        account_layout.addLayout(data_row)
        account_layout.addWidget(self.data_status)
        content.addWidget(self.account_card)

        self.about_card = QtWidgets.QFrame()
        self.about_card.setObjectName("SettingsCard")
        about_layout = QtWidgets.QVBoxLayout(self.about_card)
        about_layout.setContentsMargins(16, 12, 16, 12)
        about_layout.setSpacing(6)
        self.about_label = QtWidgets.QLabel()
        self.about_label.setStyleSheet("font-weight: 600;")
        self.about_body = QtWidgets.QLabel()
        self.about_body.setWordWrap(True)
        self.about_body.setObjectName("Muted")
        about_layout.addWidget(self.about_label)
        about_layout.addWidget(self.about_body)
        content.addWidget(self.about_card)

        layout.addLayout(content)
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
        self.name_input.setText(self._current_display_name())
        self.password_input.clear()
        self.password_confirm_input.clear()
        self._sync_profile_state()

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
        self.profile_label.setText(self.i18n.t("settings_profile"))
        self.name_label.setText(self.i18n.t("settings_name"))
        self.name_input.setPlaceholderText(self.i18n.t("settings_name_placeholder"))
        self.password_label.setText(self.i18n.t("settings_password"))
        self.password_input.setPlaceholderText(self.i18n.t("settings_password_placeholder"))
        self.password_confirm_label.setText(self.i18n.t("settings_password_confirm"))
        self.password_confirm_input.setPlaceholderText(
            self.i18n.t("settings_password_confirm_placeholder")
        )
        self.save_profile_button.setText(self.i18n.t("settings_save"))
        self.about_label.setText(self.i18n.t("settings_about"))
        self.about_body.setText(self.i18n.t("settings_about_body"))
        self.data_label.setText(self.i18n.t("settings_data"))
        self.data_button.setText(self.i18n.t("settings_clear"))
        self._sync_profile_state()

    def _set_profile_status(self, message: str, status: str = "idle") -> None:
        self.profile_status.setText(message)
        self.profile_status.setProperty("status", status)
        self.profile_status.style().unpolish(self.profile_status)
        self.profile_status.style().polish(self.profile_status)

    def _sync_profile_state(self) -> None:
        account_id = str(self.settings.get("account_id", "") or "").strip()
        enabled = bool(account_id) and self.api is not None
        for widget in (
            self.name_input,
            self.password_input,
            self.password_confirm_input,
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

    def save_profile(self) -> None:
        account_id = str(self.settings.get("account_id", "") or "").strip()
        if not account_id:
            self._set_profile_status(self.i18n.t("settings_profile_signin"), "error")
            return
        if self.api is None:
            self._set_profile_status(self.i18n.t("settings_profile_unavailable"), "error")
            return
        name = self.name_input.text().strip()
        password = self.password_input.text()
        confirm = self.password_confirm_input.text()
        updates: dict[str, str] = {}
        if name:
            updates["name"] = name
        if password or confirm:
            if not password or not confirm:
                self._set_profile_status(
                    self.i18n.t("settings_profile_password_required"), "error"
                )
                return
            if password != confirm:
                self._set_profile_status(self.i18n.t("settings_profile_mismatch"), "error")
                return
            updates["password"] = password
        if not updates:
            self._set_profile_status(self.i18n.t("settings_profile_missing"), "error")
            return
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
                self._set_profile_status(
                    self.i18n.t("settings_profile_legacy_password"), "error"
                )
                return
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
        self.password_input.clear()
        self.password_confirm_input.clear()
        self._set_profile_status(self.i18n.t("settings_profile_saved"), "success")
        if "name" in updates:
            self.profile_updated.emit()

    def clear_data(self) -> None:
        self.settings.clear_user_data()
        self.data_status.setText(self.i18n.t("settings_clear_done"))
        self.load_state()
