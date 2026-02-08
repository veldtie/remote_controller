from typing import Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.theme import Theme, THEMES
from ..common import GlassFrame, make_button
from ..dialogs import AddMemberDialog, EditMemberDialog


class TeamsPage(QtWidgets.QWidget):
    teams_updated = QtCore.pyqtSignal()
    TAG_COLORS = [
        ("Ocean", "#3b82f6"),
        ("Mint", "#22c55e"),
        ("Amber", "#f59e0b"),
        ("Rose", "#ef4444"),
        ("Violet", "#8b5cf6"),
        ("Teal", "#14b8a6"),
        ("Gold", "#eab308"),
        ("Pink", "#ec4899"),
        ("Indigo", "#6366f1"),
        ("Slate", "#64748b"),
    ]

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
        self.teams = []
        self.clients = self.settings.get("clients", [])
        self.settings.set("teams", [])
        self.current_role = settings.get("role", "operator")
        self.current_team_id = None
        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])
        self._load_teams_from_api()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)

        self.list_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.list_card.setObjectName("Card")
        list_layout = QtWidgets.QVBoxLayout(self.list_card)
        self.list_title = QtWidgets.QLabel()
        self.list_title.setStyleSheet("font-weight: 600;")
        list_layout.addWidget(self.list_title)
        team_actions = QtWidgets.QHBoxLayout()
        self.add_team_button = make_button("", "ghost")
        self.add_team_button.clicked.connect(self.create_team)
        self.delete_team_button = make_button("", "danger")
        self.delete_team_button.clicked.connect(self.delete_team)
        team_actions.addWidget(self.add_team_button)
        team_actions.addWidget(self.delete_team_button)
        team_actions.addStretch()
        list_layout.addLayout(team_actions)
        self.team_list = QtWidgets.QListWidget()
        self.team_list.setMouseTracking(True)
        self.team_list.itemSelectionChanged.connect(self.on_team_selected)
        list_layout.addWidget(self.team_list, 1)
        self.list_card.setMinimumWidth(200)
        self.list_card.setMaximumWidth(280)
        body.addWidget(self.list_card, 1)

        self.details_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.details_card.setObjectName("Card")
        details_layout = QtWidgets.QVBoxLayout(self.details_card)

        self.details_stack = QtWidgets.QStackedWidget()
        placeholder = QtWidgets.QLabel()
        placeholder.setObjectName("Muted")
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label = placeholder
        self.details_stack.addWidget(placeholder)

        details_container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(details_container)
        container_layout.setSpacing(12)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        self.team_name_label = QtWidgets.QLabel()
        self.team_name_input = QtWidgets.QLineEdit()
        self.team_name_input.editingFinished.connect(self.commit_team_name)
        self.team_name_input.setPlaceholderText(self.i18n.t("team_name_placeholder"))

        self.team_status_label = QtWidgets.QLabel()
        self.team_status_value = QtWidgets.QLabel()
        self.team_status_value.setStyleSheet("font-weight: 600;")

        self.team_subscription_label = QtWidgets.QLabel()
        self.team_subscription_value = QtWidgets.QLabel()

        form.addWidget(self.team_name_label, 0, 0)
        form.addWidget(self.team_name_input, 0, 1, 1, 3)
        form.addWidget(self.team_status_label, 1, 0)
        form.addWidget(self.team_status_value, 1, 1)
        form.addWidget(self.team_subscription_label, 1, 2)
        form.addWidget(self.team_subscription_value, 1, 3)

        container_layout.addLayout(form)

        self.renew_button = make_button("", "primary")
        self.renew_button.clicked.connect(self.renew_subscription)
        container_layout.addWidget(self.renew_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.section_tabs = QtWidgets.QTabWidget()
        self.section_tabs.setDocumentMode(True)
        self.section_tabs.setMovable(False)
        self.section_tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)

        self.unassigned_tab = QtWidgets.QWidget()
        unassigned_layout = QtWidgets.QVBoxLayout(self.unassigned_tab)
        unassigned_layout.setContentsMargins(0, 0, 0, 0)
        unassigned_layout.setSpacing(8)

        self.unassigned_table = QtWidgets.QTableWidget(0, 5)
        self.unassigned_table.verticalHeader().setVisible(False)
        self.unassigned_table.setAlternatingRowColors(True)
        self.unassigned_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.unassigned_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.unassigned_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.unassigned_table.setMouseTracking(True)
        unassigned_header = self.unassigned_table.horizontalHeader()
        unassigned_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        unassigned_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        unassigned_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        unassigned_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        unassigned_header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.unassigned_table.verticalHeader().setDefaultSectionSize(40)
        unassigned_layout.addWidget(self.unassigned_table, 1)

        self.members_tab = QtWidgets.QWidget()
        members_layout = QtWidgets.QVBoxLayout(self.members_tab)
        members_layout.setContentsMargins(0, 0, 0, 0)
        members_layout.setSpacing(8)

        self.members_table = QtWidgets.QTableWidget(0, 4)
        self.members_table.verticalHeader().setVisible(False)
        self.members_table.setAlternatingRowColors(True)
        self.members_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.members_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.members_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.members_table.setMouseTracking(True)
        header = self.members_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.members_table.verticalHeader().setDefaultSectionSize(40)
        members_layout.addWidget(self.members_table, 1)

        member_actions = QtWidgets.QHBoxLayout()
        self.add_member_button = make_button("", "ghost")
        self.add_member_button.clicked.connect(self.add_member)
        self.edit_member_button = make_button("", "ghost")
        self.edit_member_button.clicked.connect(self.edit_member)
        self.remove_member_button = make_button("", "ghost")
        self.remove_member_button.clicked.connect(self.remove_member)
        member_actions.addWidget(self.add_member_button)
        member_actions.addWidget(self.edit_member_button)
        member_actions.addWidget(self.remove_member_button)
        member_actions.addStretch()
        members_layout.addLayout(member_actions)

        self.tags_tab = QtWidgets.QWidget()
        tags_layout = QtWidgets.QVBoxLayout(self.tags_tab)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(8)

        self.tags_list = QtWidgets.QListWidget()
        self.tags_list.setMouseTracking(True)
        self.tags_list.setMinimumHeight(120)
        tags_layout.addWidget(self.tags_list, 1)

        tag_controls = QtWidgets.QHBoxLayout()
        self.tag_name_input = QtWidgets.QLineEdit()
        self.tag_name_input.setPlaceholderText("")
        self.tag_color_combo = QtWidgets.QComboBox()
        for name, color in self.TAG_COLORS:
            self.tag_color_combo.addItem(name, color)
        self._sync_tag_color_icons()
        self.tag_add_button = make_button("", "ghost")
        self.tag_add_button.clicked.connect(self.create_tag)
        self.tag_clear_button = make_button("", "ghost")
        self.tag_clear_button.clicked.connect(self._reset_tag_editor)
        self.tag_delete_button = make_button("", "danger")
        self.tag_delete_button.clicked.connect(self.delete_tag)
        tag_controls.addWidget(self.tag_name_input, 2)
        tag_controls.addWidget(self.tag_color_combo, 1)
        tag_controls.addWidget(self.tag_add_button)
        tag_controls.addWidget(self.tag_clear_button)
        tag_controls.addWidget(self.tag_delete_button)
        tag_controls.addStretch()
        tags_layout.addLayout(tag_controls)

        self.section_tabs.addTab(self.members_tab, "")
        self.section_tabs.addTab(self.unassigned_tab, "")
        self.section_tabs.addTab(self.tags_tab, "")
        container_layout.addWidget(self.section_tabs, 1)

        self._editing_tag_id: str | None = None
        self.tags_list.itemSelectionChanged.connect(self._handle_tag_selected)

        self.details_stack.addWidget(details_container)
        details_layout.addWidget(self.details_stack, 1)
        body.addWidget(self.details_card, 6)

        layout.addLayout(body, 1)

        self.apply_translations()
        self.populate_team_list()
        self.update_role_controls()

    def _load_teams_from_api(self) -> None:
        if not self.api:
            return
        try:
            api_teams = self.api.fetch_teams()
        except Exception:
            return
        self.teams = api_teams
        self.settings.set("teams", self.teams)
        self.settings.save()
        self.teams_updated.emit()

    def _load_clients_from_api(self) -> None:
        if not self.api:
            return
        try:
            api_clients = self.api.fetch_clients()
        except Exception:
            return
        self.clients = api_clients
        self.settings.set("clients", self.clients)
        self.settings.save()

    def refresh_from_api(self, select_team_id: Optional[str] = None) -> None:
        self._load_teams_from_api()
        self._load_clients_from_api()
        if select_team_id:
            self.current_team_id = select_team_id
        self.populate_team_list(select_team_id or self.current_team_id)
        self.render_team_details()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("teams_title"))
        self.subtitle_label.setText(self.i18n.t("teams_subtitle"))
        self.list_title.setText(self.i18n.t("teams_list_title"))
        self.add_team_button.setText(self.i18n.t("team_add"))
        self.delete_team_button.setText(self.i18n.t("team_remove"))
        self.placeholder_label.setText(self.i18n.t("teams_select_hint"))
        self.team_name_label.setText(self.i18n.t("team_name"))
        self.team_name_input.setPlaceholderText(self.i18n.t("team_name_placeholder"))
        self.team_status_label.setText(self.i18n.t("team_status"))
        self.team_subscription_label.setText(self.i18n.t("team_activity"))
        self.renew_button.setText(self.i18n.t("team_toggle_activity"))
        self.section_tabs.setTabText(self.section_tabs.indexOf(self.members_tab), self.i18n.t("team_members"))
        self.section_tabs.setTabText(
            self.section_tabs.indexOf(self.unassigned_tab),
            self.i18n.t("unassigned_clients_title"),
        )
        self.section_tabs.setTabText(
            self.section_tabs.indexOf(self.tags_tab),
            self.i18n.t("team_tags_title"),
        )
        self.unassigned_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("table_name"),
                self.i18n.t("table_id"),
                self.i18n.t("table_ip"),
                self.i18n.t("table_assign"),
                self.i18n.t("table_delete"),
            ]
        )
        self.add_member_button.setText(self.i18n.t("team_add_member"))
        self.edit_member_button.setText(self.i18n.t("team_edit_member"))
        self.remove_member_button.setText(self.i18n.t("team_remove_member"))
        self.tag_name_input.setPlaceholderText(self.i18n.t("tags_name_placeholder"))
        self._update_tag_controls_text()
        self.members_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("team_member_name"),
                self.i18n.t("team_member_login"),
                self.i18n.t("team_member_tag"),
                self.i18n.t("team_member_clients"),
            ]
        )
        self.populate_team_list(self.current_team_id)
        self.render_team_details()

    def set_role(self, role: str) -> None:
        self.current_role = role
        self.update_role_controls()
        self.populate_team_list(self.current_team_id)
        self.render_team_details()

    def update_role_controls(self) -> None:
        is_moderator = self.current_role == "moderator"
        is_admin = self.current_role == "administrator"
        allow_api = self.api is not None
        can_manage_teams = is_moderator and allow_api
        can_manage_members = (is_moderator or is_admin) and allow_api
        can_toggle_activity = is_moderator and allow_api
        show_unassigned = (is_moderator or is_admin)
        show_team_info = self.current_role != "operator"
        can_manage_tags = (is_moderator or is_admin) and allow_api
        show_member_login = is_moderator or is_admin

        self.list_card.setVisible(is_moderator)
        self.team_name_input.setReadOnly(not can_manage_teams)
        self.team_name_label.setVisible(show_team_info)
        self.team_name_input.setVisible(show_team_info)
        self.team_status_label.setVisible(show_team_info)
        self.team_status_value.setVisible(show_team_info)
        self.team_subscription_label.setVisible(show_team_info)
        self.team_subscription_value.setVisible(show_team_info)
        self.renew_button.setVisible(is_moderator)
        self.renew_button.setEnabled(can_toggle_activity)
        self.add_member_button.setVisible(can_manage_members)
        self.edit_member_button.setVisible(can_manage_members)
        self.remove_member_button.setVisible(can_manage_members)
        self.add_member_button.setEnabled(can_manage_members)
        self.edit_member_button.setEnabled(can_manage_members)
        self.remove_member_button.setEnabled(can_manage_members)
        self.add_team_button.setVisible(is_moderator)
        self.add_team_button.setEnabled(can_manage_teams)
        self.delete_team_button.setVisible(is_moderator)
        self.delete_team_button.setEnabled(can_manage_teams and self.selected_team() is not None)
        self._set_tab_visible(self.unassigned_tab, show_unassigned)
        self.unassigned_table.setVisible(show_unassigned)
        self.tag_name_input.setVisible(can_manage_tags)
        self.tag_color_combo.setVisible(can_manage_tags)
        self.tag_add_button.setVisible(can_manage_tags)
        self.tag_clear_button.setVisible(can_manage_tags)
        self.tag_delete_button.setVisible(can_manage_tags)
        self.tag_name_input.setEnabled(can_manage_tags)
        self.tag_color_combo.setEnabled(can_manage_tags)
        self.tag_add_button.setEnabled(can_manage_tags)
        self.tag_clear_button.setEnabled(can_manage_tags and self._editing_tag_id is not None)
        self.tag_delete_button.setEnabled(can_manage_tags and self._editing_tag_id is not None)
        if hasattr(self, "members_table"):
            self.members_table.setColumnHidden(1, not show_member_login)

    def _set_tab_visible(self, tab: QtWidgets.QWidget, visible: bool) -> None:
        index = self.section_tabs.indexOf(tab)
        if index < 0:
            return
        if hasattr(self.section_tabs, "setTabVisible"):
            self.section_tabs.setTabVisible(index, visible)
        else:
            self.section_tabs.setTabEnabled(index, visible)
            tab.setVisible(visible)
        if not visible and self.section_tabs.currentIndex() == index:
            for next_index in range(self.section_tabs.count()):
                if next_index == index:
                    continue
                if hasattr(self.section_tabs, "isTabVisible"):
                    if not self.section_tabs.isTabVisible(next_index):
                        continue
                elif not self.section_tabs.isTabEnabled(next_index):
                    continue
                self.section_tabs.setCurrentIndex(next_index)
                break

    def visible_teams(self) -> List[Dict]:
        if self.current_role == "moderator":
            return self.teams
        account_id = self.settings.get("account_id", "")
        for team in self.teams:
            for member in team.get("members", []):
                if member.get("account_id") == account_id:
                    return [team]
        return []

    def populate_team_list(self, select_team_id: Optional[str] = None) -> None:
        self.team_list.clear()
        teams = self.visible_teams()
        for team in teams:
            item = QtWidgets.QListWidgetItem(team["name"])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, team["id"])
            self.team_list.addItem(item)
            if select_team_id and team["id"] == select_team_id:
                self.team_list.setCurrentItem(item)
        if self.team_list.count() > 0 and self.team_list.currentItem() is None:
            self.team_list.setCurrentRow(0)

    def on_team_selected(self) -> None:
        self.render_team_details()

    def render_team_details(self) -> None:
        team = self.selected_team()
        can_manage_teams = self.current_role == "moderator" and self.api is not None
        self.delete_team_button.setEnabled(can_manage_teams and team is not None)
        if team is None:
            self.details_stack.setCurrentIndex(0)
            return
        self.details_stack.setCurrentIndex(1)
        self.current_team_id = team["id"]
        self.team_name_input.blockSignals(True)
        self.team_name_input.setText(team.get("name", ""))
        self.team_name_input.blockSignals(False)
        self.update_subscription_display(team)
        self.render_unassigned_clients(team)
        self.render_members(team)
        self.render_tags(team)

    def selected_team(self) -> Optional[Dict]:
        item = self.team_list.currentItem()
        if not item:
            return None
        team_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        for team in self.teams:
            if team["id"] == team_id:
                return team
        return None

    def update_subscription_display(self, team: Dict) -> None:
        is_active = bool(team.get("activity", True))
        status_key = "team_status_active" if is_active else "team_status_inactive"
        self.team_status_value.setText(self.i18n.t(status_key))
        color = self.theme.colors["accent"] if is_active else self.theme.colors["danger"]
        self.team_status_value.setStyleSheet(f"font-weight: 600; color: {color};")
        activity_key = "team_activity_on" if is_active else "team_activity_off"
        self.team_subscription_value.setText(self.i18n.t(activity_key))

    def client_count_for_member(self, member: Dict) -> int:
        account_id = member.get("account_id")
        if not account_id:
            return 0
        clients = self.clients or self.settings.get("clients", [])
        count = 0
        for client in clients:
            assigned = client.get("assigned_operator_id")
            if assigned == account_id:
                count += 1
        return count

    def render_members(self, team: Dict) -> None:
        members = team.get("members", [])
        self.members_table.setRowCount(0)
        if not members:
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            item = QtWidgets.QTableWidgetItem(self.i18n.t("teams_no_members"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.members_table.setItem(row, 0, item)
            self.members_table.setSpan(row, 0, 1, 4)
            return
        for member in members:
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(member["name"])
            login_item = QtWidgets.QTableWidgetItem(member.get("account_id", ""))
            tag_label = self.i18n.t(f"tag_{member['tag']}")
            tag_item = QtWidgets.QTableWidgetItem(tag_label)
            clients_item = QtWidgets.QTableWidgetItem(str(self.client_count_for_member(member)))
            self.members_table.setItem(row, 0, name_item)
            self.members_table.setItem(row, 1, login_item)
            self.members_table.setItem(row, 2, tag_item)
            self.members_table.setItem(row, 3, clients_item)

    def render_tags(self, team: Dict) -> None:
        self.tags_list.clear()
        tags = team.get("tags", []) if team else []
        if not tags:
            item = QtWidgets.QListWidgetItem(self.i18n.t("tags_empty"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.tags_list.addItem(item)
            self._reset_tag_editor()
            return
        for tag in tags:
            name = str(tag.get("name") or "").strip()
            if not name:
                continue
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(tag.get("id") or ""))
            color = str(tag.get("color") or "").strip()
            if color:
                qcolor = QtGui.QColor(color)
                qcolor.setAlpha(90)
                item.setBackground(QtGui.QBrush(qcolor))
            self.tags_list.addItem(item)
        self._reset_tag_editor()

    def _selected_tag_id(self) -> str | None:
        item = self.tags_list.currentItem()
        if not item:
            return None
        tag_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        return str(tag_id) if tag_id else None

    def _handle_tag_selected(self) -> None:
        tag_id = self._selected_tag_id()
        if not tag_id:
            self._reset_tag_editor()
            return
        team = self.selected_team()
        if not team:
            self._reset_tag_editor()
            return
        tag = next(
            (entry for entry in team.get("tags", []) if str(entry.get("id")) == tag_id),
            None,
        )
        if not tag:
            self._reset_tag_editor()
            return
        self._editing_tag_id = tag_id
        self.tag_name_input.setText(str(tag.get("name") or ""))
        color = str(tag.get("color") or "")
        if color:
            index = self.tag_color_combo.findData(color)
            if index >= 0:
                self.tag_color_combo.setCurrentIndex(index)
        self._update_tag_controls_text()
        if hasattr(self, "tag_delete_button"):
            self.tag_delete_button.setEnabled(True)
        if hasattr(self, "tag_clear_button"):
            self.tag_clear_button.setEnabled(True)

    def _reset_tag_editor(self) -> None:
        self._editing_tag_id = None
        if hasattr(self, "tags_list"):
            self.tags_list.blockSignals(True)
            self.tags_list.clearSelection()
            self.tags_list.blockSignals(False)
        if hasattr(self, "tag_name_input"):
            self.tag_name_input.clear()
        if hasattr(self, "tag_color_combo") and self.tag_color_combo.count() > 0:
            self.tag_color_combo.setCurrentIndex(0)
        self._update_tag_controls_text()
        if hasattr(self, "tag_delete_button"):
            self.tag_delete_button.setEnabled(False)
        if hasattr(self, "tag_clear_button"):
            self.tag_clear_button.setEnabled(False)

    def _update_tag_controls_text(self) -> None:
        if not hasattr(self, "tag_add_button"):
            return
        if self._editing_tag_id:
            self.tag_add_button.setText(self.i18n.t("tags_update_button"))
        else:
            self.tag_add_button.setText(self.i18n.t("tags_add_button"))
        if hasattr(self, "tag_clear_button"):
            self.tag_clear_button.setText(self.i18n.t("tags_cancel_button"))
        if hasattr(self, "tag_delete_button"):
            self.tag_delete_button.setText(self.i18n.t("tags_delete_button"))

    def _sync_tag_color_icons(self) -> None:
        for index in range(self.tag_color_combo.count()):
            color = self.tag_color_combo.itemData(index)
            if not color:
                continue
            pixmap = QtGui.QPixmap(12, 12)
            pixmap.fill(QtGui.QColor(color))
            self.tag_color_combo.setItemIcon(index, QtGui.QIcon(pixmap))

    def render_unassigned_clients(self, team: Dict) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            self.unassigned_table.setRowCount(0)
            return
        self.unassigned_table.setRowCount(0)
        team_id = team.get("id", "")
        clients = self.clients or self.settings.get("clients", [])
        unassigned = [
            client
            for client in clients
            if client.get("assigned_team_id") == team_id
            and not client.get("assigned_operator_id")
        ]
        if not unassigned:
            row = self.unassigned_table.rowCount()
            self.unassigned_table.insertRow(row)
            item = QtWidgets.QTableWidgetItem(self.i18n.t("unassigned_clients_empty"))
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.unassigned_table.setItem(row, 0, item)
            self.unassigned_table.setSpan(row, 0, 1, self.unassigned_table.columnCount())
            return
        for client in unassigned:
            row = self.unassigned_table.rowCount()
            self.unassigned_table.insertRow(row)
            self.unassigned_table.setRowHeight(row, 40)
            name_item = QtWidgets.QTableWidgetItem(client.get("name", ""))
            id_item = QtWidgets.QTableWidgetItem(client.get("id", ""))
            ip_item = QtWidgets.QTableWidgetItem(client.get("ip", ""))
            for item in (name_item, id_item, ip_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.unassigned_table.setItem(row, 0, name_item)
            self.unassigned_table.setItem(row, 1, id_item)
            self.unassigned_table.setItem(row, 2, ip_item)

            assign_button = make_button(self.i18n.t("button_assign"), "ghost")
            assign_button.setEnabled(bool(team.get("members")) and self.api is not None)
            assign_button.clicked.connect(
                lambda _, btn=assign_button, cid=client.get("id", ""), tid=team_id: self.show_assign_menu(
                    btn,
                    cid,
                    tid,
                )
            )
            self.unassigned_table.setCellWidget(row, 3, assign_button)

            delete_button = make_button(self.i18n.t("button_delete"), "danger")
            delete_button.setEnabled(self.api is not None)
            delete_button.clicked.connect(
                lambda _, cid=client.get("id", ""), tid=team_id: self.delete_unassigned_client(
                    cid,
                    tid,
                )
            )
            self.unassigned_table.setCellWidget(row, 4, delete_button)

    def show_assign_menu(self, button: QtWidgets.QWidget, client_id: str, team_id: str) -> None:
        if not self.api or not client_id:
            return
        team = self.selected_team()
        if not team or team.get("id") != team_id:
            return
        members = team.get("members", [])
        if not members:
            return
        menu = QtWidgets.QMenu(button)
        for member in members:
            name = member.get("name") or member.get("account_id") or ""
            if not name:
                continue
            action = menu.addAction(name)
            action.triggered.connect(
                lambda _, m=member: self.assign_client_to_member(client_id, team_id, m)
            )
        if not menu.actions():
            return
        menu.exec(button.mapToGlobal(QtCore.QPoint(0, button.height())))

    def assign_client_to_member(self, client_id: str, team_id: str, member: Dict) -> None:
        if not self.api or not client_id:
            return
        operator_id = member.get("account_id")
        if not operator_id:
            return
        try:
            self.api.assign_client(client_id, operator_id, team_id)
        except Exception:
            return
        self.refresh_from_api(team_id)

    def delete_unassigned_client(self, client_id: str, team_id: str) -> None:
        if not self.api or not client_id:
            return
        try:
            self.api.delete_client(client_id)
        except Exception:
            return
        self.refresh_from_api(team_id)

    def resolve_operator_name(self, account_id: str) -> Optional[str]:
        if not account_id:
            return None
        for team in self.teams:
            for member in team.get("members", []):
                if member.get("account_id") == account_id:
                    return member.get("name")
        return None

    def commit_team_name(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        name = self.team_name_input.text().strip()
        if not name:
            return
        if not self.api:
            return
        try:
            self.api.update_team_name(team["id"], name)
        except Exception:
            self.team_name_input.blockSignals(True)
            self.team_name_input.setText(team.get("name", ""))
            self.team_name_input.blockSignals(False)
            return
        self.refresh_from_api(team["id"])

    def renew_subscription(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        if not self.api:
            return
        new_activity = not team.get("activity", True)
        try:
            self.api.update_team_activity(team["id"], new_activity)
        except Exception:
            return
        self.refresh_from_api(team["id"])

    def add_member(self) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            return
        team = self.selected_team()
        if team is None:
            return
        allowed_roles = ["operator"] if self.current_role == "administrator" else None
        dialog = AddMemberDialog(self.i18n, self, allowed_roles=allowed_roles)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        data = dialog.member_data()
        if not data["name"] or not data["account_id"] or not data["password"]:
            return
        if not self.api:
            return
        try:
            self.api.upsert_operator(
                data["account_id"],
                data["name"],
                data["password"],
                data["tag"],
                team["id"],
            )
        except Exception:
            return
        self.refresh_from_api(team["id"])

    def edit_member(self) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            return
        team = self.selected_team()
        if team is None:
            return
        row = self.members_table.currentRow()
        members = team.get("members", [])
        if row < 0 or row >= len(members):
            return
        member = members[row]
        allowed_roles = ["operator"] if self.current_role == "administrator" else None
        dialog = EditMemberDialog(self.i18n, member, self, allowed_roles=allowed_roles)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        data = dialog.member_data()
        name = data.get("name", "").strip()
        account_id = data.get("account_id", "").strip()
        password = data.get("password", "")
        role = data.get("tag", "")
        if not name or not account_id:
            return
        if not self.api:
            return
        original_id = str(member.get("account_id") or "")
        original_role = str(member.get("tag") or "")
        role_changed = role and role != original_role
        if role_changed and not password:
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("team_edit_dialog_title"),
                self.i18n.t("team_edit_password_required"),
            )
            return
        try:
            if account_id and original_id and account_id != original_id:
                self.api.update_operator_login(original_id, account_id)
            if role_changed:
                self.api.upsert_operator(
                    account_id,
                    name,
                    password,
                    role,
                    team["id"],
                )
            else:
                name_update = name if name != member.get("name") else None
                password_update = password or None
                if name_update is not None or password_update is not None:
                    self.api.update_operator_profile(
                        account_id, name=name_update, password=password_update
                    )
        except Exception:
            return
        self.refresh_from_api(team["id"])

    def remove_member(self) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            return
        team = self.selected_team()
        if team is None:
            return
        row = self.members_table.currentRow()
        members = team.get("members", [])
        if row < 0 or row >= len(members):
            return
        member = members[row]
        account_id = member.get("account_id")
        if not account_id:
            return
        if not self.api:
            return
        try:
            self.api.delete_operator(account_id)
        except Exception:
            return
        self.refresh_from_api(team["id"])

    def create_team(self) -> None:
        if self.current_role != "moderator" or not self.api:
            return
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle(self.i18n.t("team_add_title"))
        dialog.setLabelText(self.i18n.t("team_add_label"))
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        name = dialog.textValue().strip()
        if not name:
            return
        try:
            team_id = self.api.create_team(name)
        except Exception:
            return
        self.refresh_from_api(team_id or None)

    def create_tag(self) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            return
        team = self.selected_team()
        if team is None or not self.api:
            return
        name = self.tag_name_input.text().strip()
        if not name:
            return
        color = self.tag_color_combo.currentData() or ""
        try:
            if self._editing_tag_id:
                self.api.update_team_tag(self._editing_tag_id, name=name, color=color)
            else:
                self.api.create_team_tag(team["id"], name, color)
        except Exception:
            return
        self._reset_tag_editor()
        self.refresh_from_api(team["id"])

    def delete_tag(self) -> None:
        if self.current_role not in {"moderator", "administrator"}:
            return
        team = self.selected_team()
        if team is None or not self.api:
            return
        tag_id = self._editing_tag_id or self._selected_tag_id()
        if not tag_id:
            return
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.i18n.t("tags_delete_title"))
        dialog.setText(self.i18n.t("tags_delete_body"))
        confirm = dialog.addButton(
            self.i18n.t("tags_delete_confirm"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.addButton(
            self.i18n.t("tags_delete_cancel"),
            QtWidgets.QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(confirm)
        dialog.exec()
        if dialog.clickedButton() != confirm:
            return
        try:
            self.api.delete_team_tag(tag_id)
        except Exception:
            return
        self._reset_tag_editor()
        self.refresh_from_api(team["id"])

    def delete_team(self) -> None:
        if self.current_role != "moderator" or not self.api:
            return
        team = self.selected_team()
        if team is None:
            return
        dialog = QtWidgets.QMessageBox(self)
        dialog.setOption(QtWidgets.QMessageBox.Option.DontUseNativeDialog, True)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.i18n.t("team_remove_title"))
        dialog.setText(self.i18n.t("team_remove_body", name=team.get("name", "")))
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
            "border-radius: 10px;"
            "padding: 6px 12px;"
            "}"
            "QPushButton:hover {"
            f"border-color: {self.theme.colors['accent']};"
            "}"
        )
        confirm = dialog.addButton(
            self.i18n.t("team_remove_confirm"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.addButton(
            self.i18n.t("team_remove_cancel"),
            QtWidgets.QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(confirm)
        dialog.exec()
        if dialog.clickedButton() != confirm:
            return
        try:
            self.api.delete_team(team["id"])
        except Exception:
            return
        if self.current_team_id == team["id"]:
            self.current_team_id = None
        self.refresh_from_api()

    def save_teams(self) -> None:
        self.settings.set("teams", self.teams)
        self.settings.save()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        team = self.selected_team()
        if team is not None:
            self.update_subscription_display(team)
