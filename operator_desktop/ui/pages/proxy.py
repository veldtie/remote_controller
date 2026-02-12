from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.theme import THEMES
from ..common import GlassFrame, load_icon, make_button
from ..proxy_check import ProxyCheckWorker
from .dashboard import ClientFetchWorker


class ProxyPage(QtWidgets.QWidget):
    extra_action_requested = QtCore.pyqtSignal(str, str)
    client_selected = QtCore.pyqtSignal(str)

    def __init__(
        self,
        i18n: I18n,
        settings: SettingsStore,
        api: RemoteControllerApi | None = None,
    ):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.api = api
        self.clients: list[dict] = []
        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])
        self._fetch_worker: ClientFetchWorker | None = None
        self._check_workers: dict[str, ProxyCheckWorker] = {}
        self._status_items: dict[str, QtWidgets.QTableWidgetItem] = {}
        self._check_buttons: dict[str, QtWidgets.QPushButton] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = GlassFrame(radius=18, tone="card_alt", tint_alpha=160, border_alpha=70)
        toolbar.setObjectName("ToolbarCard")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setSpacing(12)

        title_box = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        toolbar_layout.addLayout(title_box)
        toolbar_layout.addStretch()

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setMinimumWidth(280)
        self.search_input.setClearButtonEnabled(True)
        search_icon = load_icon("search", self.theme.name)
        if not search_icon.isNull():
            self.search_input.addAction(
                search_icon,
                QtWidgets.QLineEdit.ActionPosition.LeadingPosition,
            )
        self.search_input.textChanged.connect(self.filter_clients)
        toolbar_layout.addWidget(self.search_input)

        self.refresh_button = make_button("", "ghost")
        self.refresh_button.clicked.connect(self.refresh_clients)
        toolbar_layout.addWidget(self.refresh_button)

        layout.addWidget(toolbar)

        self.table_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.table_card.setObjectName("Card")
        table_layout = QtWidgets.QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMouseTracking(True)
        self.table.setShowGrid(False)
        self.table.viewport().installEventFilter(self)
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setMinimumSectionSize(52)
        for index in range(self.table.columnCount()):
            header_view.setSectionResizeMode(index, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.cellDoubleClicked.connect(self._emit_client_selected)
        table_layout.addWidget(self.table)
        self.table_overflow_hint = QtWidgets.QLabel("Horizontal scroll indicates hidden columns")
        self.table_overflow_hint.setObjectName("TableOverflowHint")
        table_layout.addWidget(self.table_overflow_hint)
        layout.addWidget(self.table_card, 1)

        self.apply_translations()
        self.refresh_from_settings()
        QtCore.QTimer.singleShot(0, self.update_adaptive_columns)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("proxy_title"))
        self.subtitle_label.setText(self.i18n.t("proxy_subtitle"))
        self.search_input.setPlaceholderText(self.i18n.t("proxy_search_placeholder"))
        self.refresh_button.setText(self.i18n.t("main_refresh_button"))
        self.table_overflow_hint.setText("Horizontal scroll indicates hidden columns")
        self.table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("table_id"),
                self.i18n.t("proxy_host_label"),
                self.i18n.t("proxy_port_label"),
                self.i18n.t("proxy_type_label"),
                self.i18n.t("proxy_status_label"),
                self.i18n.t("table_actions"),
            ]
        )
        self.update_adaptive_columns()

    def refresh_from_settings(self) -> None:
        self.clients = list(self.settings.get("clients", []) or [])
        self.render_clients(self.clients)

    def refresh_clients(self) -> None:
        if not self.api:
            self.refresh_from_settings()
            return
        if self._fetch_worker and self._fetch_worker.isRunning():
            return
        self._fetch_worker = ClientFetchWorker(self.api)
        self._fetch_worker.fetched.connect(self._handle_clients_fetched)
        self._fetch_worker.failed.connect(self._handle_clients_failed)
        self._fetch_worker.start()

    def _handle_clients_fetched(self, clients: list) -> None:
        self.clients = list(clients or [])
        self.settings.set("clients", self.clients)
        self.settings.save()
        self.render_clients(self.clients)

    def _handle_clients_failed(self, _message: str) -> None:
        self.refresh_from_settings()

    def filter_clients(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self.render_clients(self.clients)
            return
        filtered: list[dict] = []
        for client in self.clients:
            payload = self._proxy_payload(client)
            values = [
                client.get("name", ""),
                client.get("id", ""),
                client.get("ip", ""),
                (payload or {}).get("host", ""),
                (payload or {}).get("port", ""),
            ]
            if any(text in str(value).lower() for value in values):
                filtered.append(client)
        self.render_clients(filtered)

    @staticmethod
    def _proxy_payload(client: dict) -> dict | None:
        config = client.get("client_config") if isinstance(client.get("client_config"), dict) else {}
        proxy = config.get("proxy")
        if not isinstance(proxy, dict):
            return None
        host = proxy.get("host") or client.get("ip") or ""
        return {
            "enabled": bool(proxy.get("enabled") or proxy.get("port")),
            "host": host,
            "port": proxy.get("port"),
            "type": proxy.get("type") or "socks5",
            "udp": proxy.get("udp"),
        }

    def _resolve_status_label(self, payload: dict | None) -> str:
        if not payload:
            return self.i18n.t("proxy_status_disabled")
        host = payload.get("host") or ""
        port = payload.get("port")
        if not host or not port:
            return self.i18n.t("proxy_status_disabled")
        return self.i18n.t("proxy_status_ready")

    def render_clients(self, clients: list[dict]) -> None:
        self.table.setRowCount(0)
        self._status_items = {}
        self._check_buttons = {}
        for client in clients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 46)
            client_id = client.get("id", "")
            payload = self._proxy_payload(client)

            name_item = QtWidgets.QTableWidgetItem(client.get("name", ""))
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, client_id)
            id_item = QtWidgets.QTableWidgetItem(client_id)
            host_item = QtWidgets.QTableWidgetItem((payload or {}).get("host", "") or "--")
            port_item = QtWidgets.QTableWidgetItem(
                str((payload or {}).get("port", "") or "--")
            )
            type_item = QtWidgets.QTableWidgetItem((payload or {}).get("type", "") or "--")
            status_item = QtWidgets.QTableWidgetItem(self._resolve_status_label(payload))
            for item in (name_item, id_item, host_item, port_item, type_item, status_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, host_item)
            self.table.setItem(row, 3, port_item)
            self.table.setItem(row, 4, type_item)
            self.table.setItem(row, 5, status_item)
            if client_id:
                self._status_items[client_id] = status_item

            actions = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(6)

            download_button = make_button(self.i18n.t("menu_proxy_download"), "ghost")
            download_button.clicked.connect(
                lambda _, cid=client_id: self.extra_action_requested.emit(cid, "proxy")
            )
            actions_layout.addWidget(download_button)

            check_button = make_button(self.i18n.t("proxy_check_button"), "ghost")
            check_button.clicked.connect(
                lambda _, c=client: self._start_proxy_check(c)
            )
            actions_layout.addWidget(check_button)
            actions_layout.addStretch()
            self.table.setCellWidget(row, 6, actions)
            if client_id:
                self._check_buttons[client_id] = check_button
        self.update_adaptive_columns()

    def _start_proxy_check(self, client: dict) -> None:
        client_id = str(client.get("id") or "")
        if not client_id:
            return
        if client_id in self._check_workers and self._check_workers[client_id].isRunning():
            return
        payload = self._proxy_payload(client)
        if not payload:
            self._update_status(client_id, self.i18n.t("proxy_status_disabled"))
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("nav_proxy"),
                self.i18n.t("proxy_status_disabled"),
            )
            return
        host = payload.get("host") or ""
        port = payload.get("port")
        if not host or not port:
            self._update_status(client_id, self.i18n.t("proxy_status_disabled"))
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("nav_proxy"),
                self.i18n.t("proxy_status_disabled"),
            )
            return
        self._update_status(client_id, self.i18n.t("proxy_checking"))
        button = self._check_buttons.get(client_id)
        if button:
            button.setEnabled(False)
        worker = ProxyCheckWorker(client_id, host, port)
        worker.finished.connect(self._handle_check_finished)
        self._check_workers[client_id] = worker
        worker.start()

    def _handle_check_finished(self, client_id: str, ok: bool, detail: str, latency_ms: int) -> None:
        self._check_workers.pop(client_id, None)
        button = self._check_buttons.get(client_id)
        if button:
            button.setEnabled(True)
        if ok:
            status = f"{self.i18n.t('proxy_check_ok')} ({latency_ms} ms)"
        else:
            suffix = detail.strip() if isinstance(detail, str) else ""
            status = self.i18n.t("proxy_check_failed")
            if suffix:
                status = f"{status}: {suffix}"
        self._update_status(client_id, status)

    def _update_status(self, client_id: str, text: str) -> None:
        item = self._status_items.get(client_id)
        if not item or item.tableWidget() is None:
            return
        item.setText(text)
        if text and text != self.i18n.t("proxy_status_ready"):
            item.setToolTip(text)

    def _emit_client_selected(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if not item:
            return
        client_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if client_id:
            self.client_selected.emit(client_id)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update_adaptive_columns()

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source is self.table.viewport() and event.type() == QtCore.QEvent.Type.Resize:
            self.update_adaptive_columns()
        return super().eventFilter(source, event)

    def update_adaptive_columns(self) -> None:
        header = self.table.horizontalHeader()
        total = self.table.viewport().width()
        if total <= 0:
            return
        config = {
            0: (1.9, 170),
            1: (2.2, 220),
            2: (1.3, 140),
            3: (0.9, 90),
            4: (0.9, 90),
            5: (1.4, 170),
            6: (1.5, 220),
        }
        min_total = sum(min_w for _, min_w in config.values())
        if total <= min_total:
            for column, (_, min_w) in config.items():
                header.resizeSection(column, min_w)
            return
        extra = total - min_total
        weight_total = sum(weight for weight, _ in config.values())
        allocated = 0
        widths: dict[int, int] = {}
        for column, (weight, min_w) in config.items():
            width = min_w + int(extra * (weight / weight_total))
            widths[column] = width
            allocated += width
        widths[0] += total - allocated
        for column, width in widths.items():
            header.resizeSection(column, width)
