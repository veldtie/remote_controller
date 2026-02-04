from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.translations import LANGUAGE_NAMES
from ..common import GlassFrame, make_button


class LoginPage(QtWidgets.QWidget):
    login_requested = QtCore.pyqtSignal(str, str, bool)
    language_changed = QtCore.pyqtSignal(str)

    def __init__(self, i18n: I18n, settings: SettingsStore):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(140, 80, 140, 80)
        layout.addStretch()

        card = GlassFrame(radius=24, tone="card_strong", tint_alpha=180, border_alpha=80)
        card.setObjectName("HeroCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.subtitle_label)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.account_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        form_layout.addRow("", QtWidgets.QLabel())
        self.account_label = QtWidgets.QLabel()
        self.password_label = QtWidgets.QLabel()
        form_layout.addRow(self.account_label, self.account_input)
        form_layout.addRow(self.password_label, self.password_input)

        card_layout.addLayout(form_layout)

        options_row = QtWidgets.QHBoxLayout()
        self.remember_check = QtWidgets.QCheckBox()
        options_row.addWidget(self.remember_check)
        options_row.addStretch()
        self.language_label = QtWidgets.QLabel()
        self.language_combo = QtWidgets.QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.language_combo.addItem(name, code)
        options_row.addWidget(self.language_label)
        options_row.addWidget(self.language_combo)
        card_layout.addLayout(options_row)

        self.login_button = make_button("", "primary")
        self.login_button.clicked.connect(self._submit)
        card_layout.addWidget(self.login_button)

        self.hint_label = QtWidgets.QLabel()
        self.hint_label.setObjectName("Muted")
        card_layout.addWidget(self.hint_label)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        card_layout.addWidget(self.status_label)

        layout.addWidget(card, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

        self.language_combo.currentIndexChanged.connect(self._language_changed)

        self.apply_translations()
        self.load_state()

    def load_state(self) -> None:
        account_id = self.settings.get("account_id", "")
        self.account_input.setText(account_id)
        remember = self.settings.get("remember_me", False)
        self.remember_check.setChecked(remember)
        recent_ids = self.settings.get("recent_account_ids", [])
        hints = sorted(set(recent_ids + ["operator-1001", "operator-1002", "qa-team", "demo"]))
        completer = QtWidgets.QCompleter(hints)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.account_input.setCompleter(completer)
        lang = self.settings.get("language", "en")
        index = self.language_combo.findData(lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("login_title"))
        self.subtitle_label.setText(self.i18n.t("login_subtitle"))
        self.account_label.setText(self.i18n.t("login_account_id"))
        self.password_label.setText(self.i18n.t("login_password"))
        self.remember_check.setText(self.i18n.t("login_remember"))
        self.login_button.setText(self.i18n.t("login_button"))
        self.hint_label.setText(self.i18n.t("login_hint"))
        self.language_label.setText(self.i18n.t("login_language"))

    def _submit(self) -> None:
        account_id = self.account_input.text().strip()
        password = self.password_input.text()
        remember = self.remember_check.isChecked()
        if not account_id or not password:
            self.status_label.setText(self.i18n.t("login_error_empty"))
            return
        self.status_label.setText("")
        self.login_requested.emit(account_id, password, remember)

    def _language_changed(self) -> None:
        lang = self.language_combo.currentData()
        if lang:
            self.language_changed.emit(lang)
