from typing import Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.i18n import I18n
from ..core.logging import EventLogger
from .common import make_button


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
        self.remote_card = QtWidgets.QFrame()
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
        self.remote_table.verticalHeader().setDefaultSectionSize(36)
        header = self.remote_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.remote_table.setColumnWidth(2, 120)
        remote_layout.addWidget(self.remote_table, 1)

        self.remote_status = QtWidgets.QLabel()
        self.remote_status.setObjectName("Muted")
        remote_layout.addWidget(self.remote_status)

        self.local_card = QtWidgets.QFrame()
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
            self.remote_table.setRowHeight(row, 36)
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
