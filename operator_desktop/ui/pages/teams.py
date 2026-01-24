from typing import Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.data import DEFAULT_TEAMS, deep_copy
from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.theme import Theme, THEMES
from ..common import make_button
from ..dialogs import AddMemberDialog


class TeamsPage(QtWidgets.QWidget):
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
        self.teams = deep_copy(settings.get("teams", DEFAULT_TEAMS))
        self.current_role = settings.get("role", "operator")
        self.current_team_id = None
        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])
        self._load_teams_from_api()

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

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)

        self.list_card = QtWidgets.QFrame()
        self.list_card.setObjectName("Card")
        list_layout = QtWidgets.QVBoxLayout(self.list_card)
        self.list_title = QtWidgets.QLabel()
        self.list_title.setStyleSheet("font-weight: 600;")
        list_layout.addWidget(self.list_title)
        self.team_list = QtWidgets.QListWidget()
        self.team_list.itemSelectionChanged.connect(self.on_team_selected)
        list_layout.addWidget(self.team_list, 1)
        body.addWidget(self.list_card, 2)

        self.details_card = QtWidgets.QFrame()
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

        self.members_label = QtWidgets.QLabel()
        self.members_label.setStyleSheet("font-weight: 600;")
        container_layout.addWidget(self.members_label)

        self.members_table = QtWidgets.QTableWidget(0, 3)
        self.members_table.verticalHeader().setVisible(False)
        self.members_table.setAlternatingRowColors(True)
        self.members_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.members_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.members_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.members_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.members_table.verticalHeader().setDefaultSectionSize(36)
        container_layout.addWidget(self.members_table, 1)

        member_actions = QtWidgets.QHBoxLayout()
        self.add_member_button = make_button("", "ghost")
        self.add_member_button.clicked.connect(self.add_member)
        self.remove_member_button = make_button("", "ghost")
        self.remove_member_button.clicked.connect(self.remove_member)
        member_actions.addWidget(self.add_member_button)
        member_actions.addWidget(self.remove_member_button)
        member_actions.addStretch()
        container_layout.addLayout(member_actions)

        self.details_stack.addWidget(details_container)
        details_layout.addWidget(self.details_stack, 1)
        body.addWidget(self.details_card, 5)

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

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("teams_title"))
        self.subtitle_label.setText(self.i18n.t("teams_subtitle"))
        self.list_title.setText(self.i18n.t("teams_list_title"))
        self.placeholder_label.setText(self.i18n.t("teams_select_hint"))
        self.team_name_label.setText(self.i18n.t("team_name"))
        self.team_name_input.setPlaceholderText(self.i18n.t("team_name_placeholder"))
        self.team_status_label.setText(self.i18n.t("team_status"))
        self.team_subscription_label.setText(self.i18n.t("team_activity"))
        self.renew_button.setText(self.i18n.t("team_toggle_activity"))
        self.members_label.setText(self.i18n.t("team_members"))
        self.add_member_button.setText(self.i18n.t("team_add_member"))
        self.remove_member_button.setText(self.i18n.t("team_remove_member"))
        self.members_table.setHorizontalHeaderLabels(
            [
                self.i18n.t("team_member_name"),
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
        self.team_name_input.setReadOnly(not is_moderator)
        self.renew_button.setEnabled(is_moderator)
        self.add_member_button.setEnabled(is_moderator)
        self.remove_member_button.setEnabled(is_moderator)

    def visible_teams(self) -> List[Dict]:
        if self.current_role == "moderator":
            return self.teams
        account_id = self.settings.get("account_id", "")
        for team in self.teams:
            for member in team.get("members", []):
                if member.get("account_id") == account_id:
                    return [team]
        return self.teams[:1] if self.teams else []

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
        if team is None:
            self.details_stack.setCurrentIndex(0)
            return
        self.details_stack.setCurrentIndex(1)
        self.current_team_id = team["id"]
        self.team_name_input.blockSignals(True)
        self.team_name_input.setText(team.get("name", ""))
        self.team_name_input.blockSignals(False)
        self.update_subscription_display(team)
        self.render_members(team)

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
        clients = self.settings.get("clients", [])
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
            self.members_table.setSpan(row, 0, 1, 3)
            return
        for member in members:
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(member["name"])
            tag_label = self.i18n.t(f"tag_{member['tag']}")
            tag_item = QtWidgets.QTableWidgetItem(tag_label)
            clients_item = QtWidgets.QTableWidgetItem(str(self.client_count_for_member(member)))
            self.members_table.setItem(row, 0, name_item)
            self.members_table.setItem(row, 1, tag_item)
            self.members_table.setItem(row, 2, clients_item)

    def commit_team_name(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        name = self.team_name_input.text().strip()
        if not name:
            return
        team["name"] = name
        if self.api:
            try:
                self.api.update_team_name(team["id"], name)
            except Exception:
                pass
        self.save_teams()
        self.populate_team_list(team["id"])

    def renew_subscription(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        team["activity"] = not team.get("activity", True)
        self.save_teams()
        if self.api:
            try:
                self.api.update_team_activity(team["id"], team["activity"])
            except Exception:
                pass
        self.update_subscription_display(team)

    def add_member(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        dialog = AddMemberDialog(self.i18n, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        data = dialog.member_data()
        if not data["name"] or not data["account_id"] or not data["password"]:
            return
        team.setdefault("members", []).append(data)
        if self.api:
            try:
                self.api.upsert_operator(
                    data["account_id"],
                    data["name"],
                    data["password"],
                    data["tag"],
                    team["id"],
                )
            except Exception:
                pass
        self.save_teams()
        self.render_members(team)
        self.populate_team_list(team["id"])

    def remove_member(self) -> None:
        if self.current_role != "moderator":
            return
        team = self.selected_team()
        if team is None:
            return
        row = self.members_table.currentRow()
        if row < 0 or row >= len(team.get("members", [])):
            return
        member = team["members"].pop(row)
        if self.api:
            try:
                self.api.delete_operator(member.get("account_id", ""))
            except Exception:
                pass
        self.save_teams()
        self.render_members(team)
        self.populate_team_list(team["id"])

    def save_teams(self) -> None:
        self.settings.set("teams", self.teams)
        self.settings.save()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        team = self.selected_team()
        if team is not None:
            self.update_subscription_display(team)
