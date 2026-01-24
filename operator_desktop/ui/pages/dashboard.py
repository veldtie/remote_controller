import time
from datetime import datetime
from typing import Dict, List

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.logging import EventLogger
from ...core.settings import SettingsStore
from ...core.theme import THEMES
from ..common import load_icon, make_button


class ClientFetchWorker(QtCore.QThread):
    fetched = QtCore.pyqtSignal(list)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, api: RemoteControllerApi):
        super().__init__()
        self.api = api

    def run(self) -> None:
        try:
            clients = self.api.fetch_clients()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.fetched.emit(clients)


class DashboardPage(QtWidgets.QWidget):
    storage_requested = QtCore.pyqtSignal(str)
    connect_requested = QtCore.pyqtSignal(str, bool)
    extra_action_requested = QtCore.pyqtSignal(str, str)
    delete_requested = QtCore.pyqtSignal(str)
    ping_updated = QtCore.pyqtSignal(object)
    server_status_changed = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        i18n: I18n,
        settings: SettingsStore,
        logger: EventLogger,
        api: RemoteControllerApi | None = None,
    ):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.api = api
        self.clients = []
        self.settings.set("clients", [])
        self.last_sync = None
        self.theme = THEMES.get(settings.get("theme", "dark"), THEMES["dark"])
        self._fetch_in_progress = False
        self._client_fetch_worker: ClientFetchWorker | None = None
        self._fetch_started_at: float | None = None
        self._server_online: bool | None = None
        self._ensure_client_state()

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
        self.poll_timer.setInterval(500)
        self.poll_timer.timeout.connect(self.poll_server_status)
        self.poll_timer.start()
        self.apply_translations()
        self.refresh_clients()
        self.refresh_logs()
        self.poll_server_status()

    def _ensure_client_state(self) -> None:
        updated = False
        for client in self.clients:
            if "status" not in client:
                if "server_connected" in client:
                    client["status"] = "connected" if client.get("server_connected") else "disconnected"
                else:
                    client["status"] = "disconnected"
                updated = True
            if "connected_time" not in client:
                client["connected_time"] = 0
                updated = True
            if "connected" not in client:
                client["connected"] = False
                updated = True
            if "server_connected" in client:
                client.pop("server_connected", None)
                updated = True
        if updated:
            self.settings.set("clients", self.clients)
            self.settings.save()

    def _merge_clients(self, api_clients: List[Dict]) -> List[Dict]:
        if not api_clients:
            return []
        local_by_id = {client["id"]: client for client in self.clients}
        merged = []
        for api_client in api_clients:
            client_id = api_client.get("id", "")
            local = local_by_id.get(client_id, {})
            merged_client = {
                "id": client_id,
                "name": api_client.get("name", ""),
                "status": api_client.get("status", "disconnected"),
                "connected_time": api_client.get("connected_time", 0),
                "ip": api_client.get("ip", ""),
                "region": api_client.get("region", ""),
                "connected": local.get("connected", False),
            }
            if "assigned_operator_id" in local:
                merged_client["assigned_operator_id"] = local.get("assigned_operator_id", "")
            merged.append(merged_client)
        return merged

    def _start_client_fetch(self) -> None:
        if not self.api or self._fetch_in_progress:
            return
        self._fetch_in_progress = True
        self._fetch_started_at = time.monotonic()
        worker = ClientFetchWorker(self.api)
        worker.fetched.connect(self._handle_client_fetch)
        worker.failed.connect(self._handle_client_fetch_error)
        worker.finished.connect(self._handle_client_fetch_finished)
        self._client_fetch_worker = worker
        worker.start()

    def _handle_client_fetch(self, api_clients: List[Dict]) -> None:
        merged = self._merge_clients(api_clients)
        self.clients = merged
        self.settings.set("clients", self.clients)
        self.settings.save()
        if self._fetch_started_at is not None:
            latency_ms = int((time.monotonic() - self._fetch_started_at) * 1000)
        else:
            latency_ms = None
        if latency_ms is not None:
            self.ping_updated.emit(latency_ms)
        self._set_server_online(True)
        self.render_clients(self.clients)

    def _handle_client_fetch_error(self, message: str) -> None:
        self.clients = []
        self.settings.set("clients", self.clients)
        self.settings.save()
        self.ping_updated.emit(None)
        self._set_server_online(False)
        self.render_clients(self.clients)

    def _handle_client_fetch_finished(self) -> None:
        self._fetch_in_progress = False
        self._client_fetch_worker = None
        self._fetch_started_at = None

    def _set_server_online(self, online: bool) -> None:
        if self._server_online is online:
            return
        self._server_online = online
        self.server_status_changed.emit(online)

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        total_seconds = max(0, int(total_seconds))
        days, remainder = divmod(total_seconds, 86_400)
        hours, remainder = divmod(remainder, 3_600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"

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
        self._start_client_fetch()

    def filter_clients(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self.render_clients(self.clients)
            return
        filtered = []
        for client in self.clients:
            connected = client.get("status") == "connected"
            status_key = "status_connected" if connected else "status_disconnected"
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
            connected = client.get("status") == "connected"
            status_key = "status_connected" if connected else "status_disconnected"
            time_value = int(client.get("connected_time") or 0)
            if connected:
                time_value = max(1, time_value)
            status_text = f"{self.i18n.t(status_key)} / {self._format_duration(time_value)}"
            status_item = QtWidgets.QTableWidgetItem(status_text)
            status_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.apply_status_style(status_item, connected)
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
                if self.api:
                    try:
                        self.api.update_client_name(client_id, client["name"])
                    except Exception:
                        pass
                break
        self.settings.set("clients", self.clients)
        self.settings.save()

    def apply_theme(self, theme) -> None:
        self.theme = theme
        self.render_clients(self.clients)

    def poll_server_status(self) -> None:
        self._start_client_fetch()

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
        header.setMinimumSectionSize(40)
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.update_adaptive_columns()

    def update_adaptive_columns(self) -> None:
        header = self.table.horizontalHeader()
        total = max(self.table.viewport().width(), 0)
        if total == 0:
            return

        config = {
            0: (3.2, 170),  # name
            1: (1.2, 80),   # id
            2: (2.1, 160),  # status + time
            3: (1.3, 100),  # region
            4: (1.3, 100),  # ip
            5: (1.3, 110),  # storage
            6: (1.6, 140),  # connect
            7: (0.8, 60),   # more
            8: (0.8, 60),   # delete
        }

        min_total = sum(min_w for _, min_w in config.values())
        if total <= min_total:
            scale = total / min_total if min_total else 1
            widths = {}
            allocated = 0
            min_size = header.minimumSectionSize()
            for col, (_, min_w) in config.items():
                width = max(int(min_w * scale), min_size)
                widths[col] = width
                allocated += width
            remainder = total - allocated
            if widths:
                widths[0] = max(widths[0] + remainder, min_size)
            for col, width in widths.items():
                header.resizeSection(col, width)
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
        dialog = QtWidgets.QInputDialog(self)
        dialog.setOption(QtWidgets.QInputDialog.Option.DontUseNativeDialog, True)
        dialog.setWindowTitle(self.i18n.t("dialog_edit_name_title"))
        dialog.setLabelText(self.i18n.t("dialog_edit_name_label"))
        dialog.setTextValue(client.get("name", ""))
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        name = dialog.textValue().strip()
        if not name:
            return
        client["name"] = name
        self.settings.set("clients", self.clients)
        self.settings.save()
        if self.api:
            try:
                self.api.update_client_name(client_id, name)
            except Exception:
                pass
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
        if self.api:
            try:
                self.api.delete_client(client_id)
            except Exception:
                pass
        self.delete_requested.emit(client_id)
        search_text = self.search_input.text()
        if search_text.strip():
            self.filter_clients(search_text)
        else:
            self.render_clients(self.clients)
