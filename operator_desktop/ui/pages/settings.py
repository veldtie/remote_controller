from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.translations import LANGUAGE_NAMES
from ..common import make_button


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
