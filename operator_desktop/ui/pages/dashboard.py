import random
from datetime import datetime
from typing import Dict, List

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.data import DEFAULT_CLIENTS, deep_copy
from ...core.i18n import I18n
from ...core.logging import EventLogger
from ...core.settings import SettingsStore
from ...core.theme import THEMES
from ..common import load_icon, make_button


class DashboardPage(QtWidgets.QWidget):
    storage_requested = QtCore.pyqtSignal(str)
    connect_requested = QtCore.pyqtSignal(str, bool)
    extra_action_requested = QtCore.pyqtSignal(str, str)
    delete_requested = QtCore.pyqtSignal(str)

    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.clients = deep_copy(settings.get("clients", DEFAULT_CLIENTS))
        self.last_sync = None
        self.theme = THEMES.get(settings.get("theme", "dark"), THEMES["dark"])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box)
        header.addStretch()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setMinimumWidth(220)
        self.search_input.textChanged.connect(self.filter_clients)
        header.addWidget(self.search_input)
        self.refresh_button = make_button("", "ghost")
        self.refresh_button.clicked.connect(self.refresh_clients)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        split.setHandleWidth(8)
        self.table_card = QtWidgets.QFrame()
        self.table_card.setObjectName("Card")
        table_layout = QtWidgets.QVBoxLayout(self.table_card)
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        self.configure_table_layout()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.itemChanged.connect(self.handle_item_changed)
        table_layout.addWidget(self.table)
        split.addWidget(self.table_card)

        self.log_card = QtWidgets.QFrame()
        self.log_card.setObjectName("Card")
        log_layout = QtWidgets.QVBoxLayout(self.log_card)
        self.log_title = QtWidgets.QLabel()
        self.log_title.setStyleSheet("font-weight: 600;")
        log_layout.addWidget(self.log_title)
        self.log_list = QtWidgets.QListWidget()
        log_layout.addWidget(self.log_list, 1)
        split.addWidget(self.log_card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        layout.addWidget(split, 1)

        footer = QtWidgets.QHBoxLayout()
        self.last_sync_label = QtWidgets.QLabel()
        self.last_sync_label.setObjectName("Muted")
        footer.addWidget(self.last_sync_label)
        footer.addStretch()
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        footer.addWidget(self.status_label)
        layout.addLayout(footer)

        self.logger.updated.connect(self.refresh_logs)
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.setInterval(10_000)
        self.poll_timer.timeout.connect(self.poll_server_status)
        self.poll_timer.start()
        self.apply_translations()
        self.refresh_clients()
        self.refresh_logs()
        self.poll_server_status()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_adaptive_columns()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("main_title"))
        self.subtitle_label.setText(self.i18n.t("main_subtitle"))
        self.search_input.setPlaceholderText(self.i18n.t("main_search_placeholder"))
        self.refresh_button.setText(self.i18n.t("main_refresh_button"))
        self.table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("table_id"),
                self.i18n.t("table_status"),
                self.i18n.t("table_region"),
                self.i18n.t("table_ip"),
                self.i18n.t("table_storage"),
                self.i18n.t("table_connect"),
                self.i18n.t("table_more"),
                self.i18n.t("table_delete"),
            ]
        )
        self.configure_table_layout()
        self.log_title.setText(self.i18n.t("log_title"))
        self.status_label.setText(self.i18n.t("main_status_ready"))
        self.update_last_sync_label()
        self.render_clients(self.clients)

    def refresh_logs(self) -> None:
        scrollbar = self.log_list.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 1
        self.log_list.clear()
        entries = self.logger.entries()
        if not entries:
            self.log_list.addItem(self.i18n.t("log_empty"))
            if at_bottom:
                self.log_list.scrollToBottom()
            return
        for entry in entries[-100:]:
            self.log_list.addItem(entry)
        if at_bottom:
            self.log_list.scrollToBottom()

    def update_last_sync_label(self) -> None:
        if not self.last_sync:
            last_sync = self.i18n.t("main_last_sync_never")
        else:
            last_sync = self.last_sync.strftime("%H:%M:%S")
        self.last_sync_label.setText(f'{self.i18n.t("main_last_sync")}: {last_sync}')

    def refresh_clients(self) -> None:
        self.last_sync = datetime.now()
        self.update_last_sync_label()
        self.render_clients(self.clients)

    def filter_clients(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self.render_clients(self.clients)
            return
        filtered = []
        for client in self.clients:
            status_key = "status_connected" if client.get("server_connected") else "status_disconnected"
            values = [
                client["name"],
                client["id"],
                self.i18n.t(status_key),
                self.i18n.t(client["region"]),
                client["ip"],
            ]
            if any(text in str(value).lower() for value in values):
                filtered.append(client)
        self.render_clients(filtered)

    def render_clients(self, clients: List[Dict]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for client in clients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 44)
            name_item = QtWidgets.QTableWidgetItem(client["name"])
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, client["id"])
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            name_item.setText("")
            id_item = QtWidgets.QTableWidgetItem(client["id"])
            status_key = "status_connected" if client.get("server_connected") else "status_disconnected"
            status_item = QtWidgets.QTableWidgetItem(self.i18n.t(status_key))
            status_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.apply_status_style(status_item, client.get("server_connected"))
            region_item = QtWidgets.QTableWidgetItem(self.i18n.t(client["region"]))
            ip_item = QtWidgets.QTableWidgetItem(client["ip"])
            for item in (id_item, status_item, region_item, ip_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setCellWidget(row, 0, self.build_name_cell(client))
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, region_item)
            self.table.setItem(row, 4, ip_item)

            storage_button = make_button(self.i18n.t("button_storage"), "ghost")
            storage_button.clicked.connect(lambda _, cid=client["id"]: self.storage_requested.emit(cid))
            self.table.setCellWidget(row, 5, storage_button)

            connect_text = self.i18n.t("button_connected") if client["connected"] else self.i18n.t("button_connect")
            connect_button = make_button(connect_text, "primary")
            connect_button.clicked.connect(
                lambda _, cid=client["id"], state=client["connected"]: self.connect_requested.emit(cid, state)
            )
            self.table.setCellWidget(row, 6, connect_button)

            more_button = self.build_more_button(client["id"])
            self.table.setCellWidget(row, 7, self.wrap_cell_widget(more_button))

            delete_button = QtWidgets.QToolButton()
            delete_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
            delete_button.setToolTip(self.i18n.t("button_delete"))
            delete_button.setAutoRaise(True)
            delete_button.setFixedSize(40, 30)
            delete_icon = load_icon("delete", self.theme.name)
            if delete_icon.isNull():
                delete_button.setText("X")
            else:
                delete_button.setIcon(delete_icon)
                delete_button.setIconSize(QtCore.QSize(16, 16))
            delete_button.setStyleSheet(
                "QToolButton {"
                f"background: {self.theme.colors['danger']};"
                "border: none;"
                "border-radius: 8px;"
                "color: #ffffff;"
                "}"
                "QToolButton:hover {"
                f"background: {self.theme.colors['danger']};"
                "}"
            )
            delete_button.clicked.connect(lambda _, cid=client["id"]: self.confirm_delete_client(cid))
            self.table.setCellWidget(row, 8, self.wrap_cell_widget(delete_button))
        self.table.blockSignals(False)

    def handle_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        client_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        for client in self.clients:
            if client["id"] == client_id:
                client["name"] = item.text().strip() or client["name"]
                break
        self.settings.set("clients", self.clients)
        self.settings.save()

    def apply_theme(self, theme) -> None:
        self.theme = theme
        self.render_clients(self.clients)

    def poll_server_status(self) -> None:
        for client in self.clients:
            if "server_connected" not in client:
                client["server_connected"] = True
                continue
            if random.random() < 0.15:
                client["server_connected"] = not client["server_connected"]
        self.render_clients(self.clients)

    def apply_status_style(self, item: QtWidgets.QTableWidgetItem, connected: bool) -> None:
        if connected:
            fg = QtGui.QColor(self.theme.colors["accent"])
            bg = QtGui.QColor(self.theme.colors["accent_soft"])
            bg.setAlpha(140)
        else:
            fg = QtGui.QColor(self.theme.colors["danger"])
            bg = QtGui.QColor(self.theme.colors["danger"])
            bg.setAlpha(90)
        item.setForeground(QtGui.QBrush(fg))
        item.setBackground(QtGui.QBrush(bg))

    def configure_table_layout(self) -> None:
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(50)
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.update_adaptive_columns()

    def update_adaptive_columns(self) -> None:
        header = self.table.horizontalHeader()
        total = max(self.table.viewport().width(), 0)
        if total == 0:
            return

        config = {
            0: (3.5, 170),  # name
            1: (1.4, 80),   # id
            2: (1.6, 110),  # status
            3: (1.4, 100),  # region
            4: (1.4, 100),  # ip
            5: (1.4, 110),  # storage
            6: (1.8, 140),  # connect
            7: (0.8, 60),   # more
            8: (0.8, 60),   # delete
        }

        min_total = sum(min_w for _, min_w in config.values())
        if total <= min_total:
            for col, (_, min_w) in config.items():
                header.resizeSection(col, min_w)
            return

        extra = total - min_total
        weight_total = sum(weight for weight, _ in config.values())
        widths = {}
        allocated = 0
        for col, (weight, min_w) in config.items():
            width = min_w + int(extra * (weight / weight_total))
            widths[col] = width
            allocated += width
        remainder = total - allocated
        widths[0] = max(widths[0] + remainder, config[0][1])

        for col, width in widths.items():
            header.resizeSection(col, width)

    @staticmethod
    def wrap_cell_widget(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addWidget(widget)
        layout.addStretch()
        return container

    def build_name_cell(self, client: Dict) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(8, 0, 6, 0)
        layout.setSpacing(6)
        label = QtWidgets.QLabel(client["name"])
        label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        button = QtWidgets.QToolButton()
        button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        button.setAutoRaise(True)
        edit_icon = load_icon("edit", self.theme.name)
        if edit_icon.isNull():
            button.setText("✎")
        else:
            button.setIcon(edit_icon)
            button.setIconSize(QtCore.QSize(16, 16))
        button.setToolTip(self.i18n.t("button_edit_name"))
        button.clicked.connect(lambda _, cid=client["id"]: self.edit_client_name(cid))
        layout.addWidget(label, 1)
        layout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        container.setLayout(layout)
        return container

    def build_more_button(self, client_id: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QToolButton()
        button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        button.setToolTip(self.i18n.t("button_more"))
        button.setAutoRaise(True)
        button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setFixedSize(40, 30)
        button.setArrowType(QtCore.Qt.ArrowType.NoArrow)
        button.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0px; }"
            "QToolButton {"
            f"background: {self.theme.colors['card_alt']};"
            f"border: 1px solid {self.theme.colors['border']};"
            "border-radius: 8px;"
            "padding: 0;"
            "}"
            "QToolButton:hover {"
            f"border-color: {self.theme.colors['accent']};"
            "}"
        )
        more_icon = load_icon("more", self.theme.name)
        if more_icon.isNull():
            button.setText("...")
        else:
            button.setIcon(more_icon)
            button.setIconSize(QtCore.QSize(16, 16))
        menu = QtWidgets.QMenu(button)
        placeholder = menu.addAction(self.i18n.t("menu_more_placeholder"))
        placeholder.setEnabled(False)
        button.setMenu(menu)
        return button

    def edit_client_name(self, client_id: str) -> None:
        client = next((c for c in self.clients if c["id"] == client_id), None)
        if client is None:
            return
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.i18n.t("dialog_edit_name_title"),
            self.i18n.t("dialog_edit_name_label"),
            text=client.get("name", ""),
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        client["name"] = name
        self.settings.set("clients", self.clients)
        self.settings.save()
        search_text = self.search_input.text()
        if search_text.strip():
            self.filter_clients(search_text)
        else:
            self.render_clients(self.clients)

    def confirm_delete_client(self, client_id: str) -> None:
        client = next((c for c in self.clients if c["id"] == client_id), None)
        if client is None:
            return
        dialog = QtWidgets.QMessageBox(self)
        dialog.setOption(QtWidgets.QMessageBox.Option.DontUseNativeDialog, True)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.i18n.t("dialog_delete_title"))
        dialog.setText(self.i18n.t("dialog_delete_body"))
        dialog.setStyleSheet(
            "QMessageBox {"
            f"background: {self.theme.colors['card']};"
            f"color: {self.theme.colors['text']};"
            "}"
            "QLabel {"
            f"color: {self.theme.colors['text']};"
            "}"
            "QPushButton {"
            f"background: {self.theme.colors['card_alt']};"
            f"border: 1px solid {self.theme.colors['border']};"
            "border-radius: 8px;"
            "padding: 6px 12px;"
            "}"
            "QPushButton:hover {"
            f"border-color: {self.theme.colors['accent']};"
            "}"
        )
        confirm = dialog.addButton(
            self.i18n.t("dialog_delete_confirm"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.addButton(
            self.i18n.t("dialog_delete_cancel"),
            QtWidgets.QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(confirm)
        dialog.exec()
        if dialog.clickedButton() != confirm:
            return
        self.delete_client(client_id)

    def delete_client(self, client_id: str) -> None:
        self.clients = [c for c in self.clients if c["id"] != client_id]
        self.settings.set("clients", self.clients)
        self.settings.save()
        self.delete_requested.emit(client_id)
        search_text = self.search_input.text()
        if search_text.strip():
            self.filter_clients(search_text)
        else:
            self.render_clients(self.clients)
