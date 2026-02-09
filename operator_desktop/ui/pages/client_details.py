from datetime import datetime
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ...core.settings import SettingsStore
from ...core.api import RemoteControllerApi
from ..common import FlowLayout, GlassFrame, load_icon, make_button
from ..browser_catalog import browser_choices_from_config
from ..proxy_check import ProxyCheckWorker
from ..dialogs import AbeDiagnosticsDialog


class ClientDetailsPage(QtWidgets.QWidget):
    back_requested = QtCore.pyqtSignal()
    connect_requested = QtCore.pyqtSignal(str, bool)
    storage_requested = QtCore.pyqtSignal(str)
    extra_action_requested = QtCore.pyqtSignal(str, str)
    delete_requested = QtCore.pyqtSignal(str)
    rename_requested = QtCore.pyqtSignal(str)
    client_updated = QtCore.pyqtSignal(str, dict)

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
        self.client: dict | None = None
        self._work_status_updating = False
        self._tags_updating = False
        self._tag_icon_cache: dict[str, QtGui.QIcon] = {}
        self._tag_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._detail_label_width = 150
        self._proxy_check_worker: ProxyCheckWorker | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        hero = GlassFrame(radius=24, tone="card_strong", tint_alpha=180, border_alpha=80)
        hero.setObjectName("HeroCard")
        hero_layout = QtWidgets.QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(12)
        self.back_button = QtWidgets.QToolButton()
        self.back_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.back_button.setAutoRaise(False)
        self.back_button.setProperty("variant", "icon")
        self.back_button.setFixedSize(36, 36)
        self.back_button.setToolTip(self.i18n.t("client_details_back"))
        back_icon = load_icon("back", "dark")
        if not back_icon.isNull():
            self.back_button.setIcon(back_icon)
            self.back_button.setIconSize(QtCore.QSize(16, 16))
        else:
            self.back_button.setText("<")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(4)
        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(8)
        self.status_dot = QtWidgets.QLabel()
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setFixedSize(8, 8)
        self.status_text = QtWidgets.QLabel()
        self.status_text.setObjectName("Muted")
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        title_box.addLayout(status_row)
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box, 1)

        self.rename_button = QtWidgets.QToolButton()
        self.rename_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.rename_button.setToolTip(self.i18n.t("button_edit_name"))
        self.rename_button.setAutoRaise(False)
        self.rename_button.setProperty("variant", "icon")
        self.rename_button.setFixedSize(36, 36)
        rename_icon = load_icon("rename", "dark")
        if not rename_icon.isNull():
            self.rename_button.setIcon(rename_icon)
            self.rename_button.setIconSize(QtCore.QSize(16, 16))
        else:
            self.rename_button.setText("?")
        self.rename_button.clicked.connect(self._emit_rename)

        self.connect_button = make_button("", "primary")
        self.connect_button.clicked.connect(self._toggle_connection)
        self.delete_button = make_button("", "danger")
        self.delete_button.clicked.connect(self._delete_client)

        self.storage_button = make_button("", "ghost")
        self.storage_button.clicked.connect(self._open_storage)
        self.cookies_button = make_button("", "ghost")
        self.proxy_button = make_button("", "ghost")
        self.proxy_button.clicked.connect(self._export_proxy)

        header_actions = QtWidgets.QHBoxLayout()
        header_actions.setSpacing(8)
        header_actions.addWidget(self.rename_button)
        header_actions.addWidget(self.connect_button)
        header_actions.addWidget(self.delete_button)
        header.addLayout(header_actions)

        hero_layout.addLayout(header)

        layout.addWidget(hero)

        tabs_widget = QtWidgets.QWidget()
        tabs_layout = QtWidgets.QHBoxLayout(tabs_widget)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(8)

        self.tab_buttons: dict[str, QtWidgets.QPushButton] = {}
        self.tab_group = QtWidgets.QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_stack = QtWidgets.QStackedWidget()

        self.main_tab = QtWidgets.QWidget()
        self.cookies_tab = QtWidgets.QWidget()
        self.proxy_tab = QtWidgets.QWidget()
        self.storage_tab = QtWidgets.QWidget()
        self.activity_tab = QtWidgets.QWidget()
        self.tab_stack.addWidget(self.main_tab)
        self.tab_stack.addWidget(self.cookies_tab)
        self.tab_stack.addWidget(self.proxy_tab)
        self.tab_stack.addWidget(self.storage_tab)
        self.tab_stack.addWidget(self.activity_tab)

        for index, key in enumerate(["main", "cookies", "proxy", "storage", "activity"]):
            button = make_button("", "ghost")
            button.setCheckable(True)
            self.tab_group.addButton(button, index)
            button.clicked.connect(lambda _, i=index: self.tab_stack.setCurrentIndex(i))
            tabs_layout.addWidget(button)
            self.tab_buttons[key] = button

        tabs_layout.addStretch()
        self.tab_buttons["main"].setChecked(True)
        self.tab_stack.setCurrentIndex(0)

        layout.addWidget(tabs_widget)
        layout.addWidget(self.tab_stack, 1)

        self._build_main_tab()
        self._build_cookies_tab()
        self._build_proxy_tab()
        self._build_storage_tab()
        self._build_activity_tab()
        self.apply_translations()

    def apply_translations(self) -> None:
        self.connect_button.setText(self.i18n.t("button_connect"))
        self.storage_button.setText(self.i18n.t("button_storage"))
        self.cookies_button.setText(self.i18n.t("menu_cookies_title"))
        self.proxy_button.setText(self.i18n.t("menu_proxy_download"))
        self.delete_button.setText(self.i18n.t("button_delete"))
        self.tab_buttons["main"].setText(self.i18n.t("client_tab_main"))
        self.tab_buttons["cookies"].setText(self.i18n.t("client_tab_cookies"))
        self.tab_buttons["proxy"].setText(self.i18n.t("client_tab_proxy"))
        self.tab_buttons["storage"].setText(self.i18n.t("client_tab_storage"))
        self.tab_buttons["activity"].setText(self.i18n.t("client_tab_activity"))
        self.client_info_title.setText(self.i18n.t("client_info_title"))
        self.system_info_title.setText(self.i18n.t("client_system_title"))
        self.cookies_title.setText(self.i18n.t("client_cookies_title"))
        self.proxy_title.setText(self.i18n.t("client_proxy_title"))
        self.proxy_body.setText(self.i18n.t("client_proxy_body"))
        self.proxy_action.setText(self.i18n.t("menu_proxy_download"))
        if hasattr(self, "proxy_copy_button"):
            self.proxy_copy_button.setText(self.i18n.t("proxy_copy_button"))
        if hasattr(self, "proxy_check_button"):
            self.proxy_check_button.setText(self.i18n.t("proxy_check_button"))
        self.storage_title.setText(self.i18n.t("client_storage_title"))
        self.storage_body.setText(self.i18n.t("client_storage_body"))
        self.storage_action.setText(self.i18n.t("button_storage"))
        self.work_status_label.setText(self.i18n.t("client_work_status"))
        self.tags_label.setText(self.i18n.t("client_tags_title"))
        self.tags_hint.setText(self.i18n.t("client_tags_hint"))
        # Activity tab translations
        if hasattr(self, "activity_title"):
            self.activity_title.setText(self.i18n.t("activity_title"))
            self.activity_search.setPlaceholderText(self.i18n.t("activity_search_placeholder"))
            self.activity_refresh_btn.setText(self.i18n.t("activity_refresh"))
            self.activity_delete_all_btn.setText(self.i18n.t("activity_delete_all"))
            self._update_activity_type_filter()
        if hasattr(self, "abe_title"):
            self.abe_title.setText(self.i18n.t("abe_status_title"))
            self.abe_status_label.setText(self.i18n.t("abe_status_label"))
            self.abe_method_label.setText(self.i18n.t("abe_method_label"))
            self.abe_version_label.setText(self.i18n.t("abe_version_label"))
            self.abe_check_button.setText(self.i18n.t("abe_check_support"))
            self.abe_help_button.setText(self.i18n.t("abe_help"))
        if hasattr(self, "abe_features_title"):
            self.abe_features_title.setText(self.i18n.t("abe_features_title"))
            self.abe_feature_abe_key_detection_label.setText(self.i18n.t("abe_feature_key_detection"))
            self.abe_feature_v20_value_detection_label.setText(self.i18n.t("abe_feature_v20_detection"))
            self.abe_feature_support_check_label.setText(self.i18n.t("abe_feature_support_check"))
            self.abe_feature_aes_gcm_decryption_label.setText(self.i18n.t("abe_feature_aes_gcm"))
            self.abe_feature_dpapi_fallback_label.setText(self.i18n.t("abe_feature_dpapi_fallback"))
            self.abe_feature_logging_label.setText(self.i18n.t("abe_feature_logging"))
            self.abe_feature_statistics_label.setText(self.i18n.t("abe_feature_statistics"))
            self.abe_limitations_label.setText(self.i18n.t("abe_limitations_title"))
            self.abe_limitations_list.setText(self.i18n.t("abe_limitations_text"))
        self._populate_work_status_options()
        self._build_cookies_menu()
        self._render_cookie_buttons()
        self._update_view()

    def set_client(self, client: dict) -> None:
        self.client = dict(client)
        self._update_view()

    def _build_main_tab(self) -> None:
        layout = QtWidgets.QHBoxLayout(self.main_tab)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        self.client_info_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.client_info_card.setObjectName("Card")
        self.client_info_card.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        client_layout = QtWidgets.QVBoxLayout(self.client_info_card)
        client_layout.setContentsMargins(10, 10, 10, 16)
        client_layout.setSpacing(0)
        self.client_info_title = QtWidgets.QLabel()
        self.client_info_title.setObjectName("ClientCardTitle")
        client_layout.addWidget(self.client_info_title)
        client_layout.addSpacing(10)
        self.client_info_form = QtWidgets.QFormLayout()
        self.client_info_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.client_info_form.setFormAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.client_info_form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        self.client_info_form.setHorizontalSpacing(20)
        self.client_info_form.setVerticalSpacing(4)
        client_layout.addLayout(self.client_info_form)
        client_layout.addSpacing(15)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(self.client_info_form.horizontalSpacing())
        self.work_status_label = QtWidgets.QLabel()
        self.work_status_label.setObjectName("DetailLabel")
        self.work_status_label.setFixedWidth(self._detail_label_width)
        self.work_status_combo = QtWidgets.QComboBox()
        self.work_status_combo.setObjectName("StatusSelect")
        self.work_status_combo.setMinimumWidth(150)
        self.work_status_combo.currentIndexChanged.connect(self._handle_work_status_changed)
        status_row.addWidget(self.work_status_label)
        status_row.addWidget(self.work_status_combo)
        status_row.addStretch()
        client_layout.addLayout(status_row)

        client_layout.addSpacing(12)
        self.tags_label = QtWidgets.QLabel()
        self.tags_label.setObjectName("CardTitle")
        self.tags_area = QtWidgets.QScrollArea()
        self.tags_area.setObjectName("TagArea")
        self.tags_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.tags_area.setWidgetResizable(True)
        self.tags_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tags_area.setMinimumHeight(150)
        self.tags_area.setMaximumHeight(150)
        self.tags_container = QtWidgets.QWidget()
        self.tags_container.setObjectName("TagContainer")
        self.tags_layout = QtWidgets.QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(10)
        self.tags_area.setWidget(self.tags_container)
        self.tags_hint = QtWidgets.QLabel()
        self.tags_hint.setObjectName("TagHint")
        self.tags_hint.setWordWrap(True)
        self.tags_hint.setContentsMargins(2, 4, 2, 2)
        client_layout.addWidget(self.tags_label)
        client_layout.addSpacing(8)
        client_layout.addWidget(self.tags_area, 1)
        client_layout.addStretch()

        self.system_info_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.system_info_card.setObjectName("Card")
        self.system_info_card.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        system_layout = QtWidgets.QVBoxLayout(self.system_info_card)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_layout.setSpacing(0)
        self.system_info_title = QtWidgets.QLabel()
        self.system_info_title.setObjectName("ClientCardTitle")
        system_layout.addWidget(self.system_info_title)
        system_layout.addSpacing(10)
        self.system_info_form = QtWidgets.QFormLayout()
        self.system_info_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.system_info_form.setFormAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.system_info_form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        self.system_info_form.setHorizontalSpacing(20)
        self.system_info_form.setVerticalSpacing(4)
        system_layout.addLayout(self.system_info_form)
        system_layout.addStretch()

        layout.addWidget(self.client_info_card, 1)
        layout.addWidget(self.system_info_card, 1)
        layout.setAlignment(self.client_info_card, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setAlignment(self.system_info_card, QtCore.Qt.AlignmentFlag.AlignTop)

    def _build_cookies_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.cookies_tab)
        layout.setSpacing(12)
        self.cookies_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.cookies_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.cookies_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.cookies_title = QtWidgets.QLabel()
        self.cookies_title.setStyleSheet("font-weight: 600;")
        card_layout.addWidget(self.cookies_title)
        self.cookie_buttons_layout = QtWidgets.QGridLayout()
        self.cookie_buttons_layout.setHorizontalSpacing(8)
        self.cookie_buttons_layout.setVerticalSpacing(8)
        card_layout.addLayout(self.cookie_buttons_layout)
        self.cookie_buttons: dict[str, QtWidgets.QPushButton] = {}
        layout.addWidget(self.cookies_card)

        self.abe_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.abe_card.setObjectName("Card")
        abe_layout = QtWidgets.QVBoxLayout(self.abe_card)
        abe_layout.setContentsMargins(14, 14, 14, 14)
        self.abe_title = QtWidgets.QLabel()
        self.abe_title.setStyleSheet("font-weight: 600;")
        abe_layout.addWidget(self.abe_title)

        self.abe_form = QtWidgets.QFormLayout()
        self.abe_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.abe_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.abe_form.setHorizontalSpacing(20)
        self.abe_form.setVerticalSpacing(6)

        self.abe_status_label = QtWidgets.QLabel()
        self.abe_status_label.setObjectName("DetailLabel")
        self.abe_status_label.setFixedWidth(self._detail_label_width)
        self.abe_status_value = QtWidgets.QWidget()
        status_layout = QtWidgets.QHBoxLayout(self.abe_status_value)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        self.abe_status_dot = QtWidgets.QLabel()
        self.abe_status_dot.setFixedSize(8, 8)
        self.abe_status_text = QtWidgets.QLabel()
        self.abe_status_text.setObjectName("DetailValue")
        status_layout.addWidget(self.abe_status_dot, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(self.abe_status_text)
        status_layout.addStretch()
        self.abe_form.addRow(self.abe_status_label, self.abe_status_value)

        self.abe_method_label = QtWidgets.QLabel()
        self.abe_method_label.setObjectName("DetailLabel")
        self.abe_method_label.setFixedWidth(self._detail_label_width)
        self.abe_method_value = QtWidgets.QLabel()
        self.abe_method_value.setObjectName("DetailValue")
        self.abe_form.addRow(self.abe_method_label, self.abe_method_value)

        self.abe_version_label = QtWidgets.QLabel()
        self.abe_version_label.setObjectName("DetailLabel")
        self.abe_version_label.setFixedWidth(self._detail_label_width)
        self.abe_version_value = QtWidgets.QLabel()
        self.abe_version_value.setObjectName("DetailValue")
        self.abe_form.addRow(self.abe_version_label, self.abe_version_value)

        abe_layout.addLayout(self.abe_form)

        actions_row = QtWidgets.QHBoxLayout()
        actions_row.setSpacing(8)
        self.abe_check_button = make_button("", "ghost")
        self.abe_check_button.clicked.connect(self._show_abe_diagnostics)
        self.abe_help_button = make_button("", "ghost")
        self.abe_help_button.clicked.connect(self._show_abe_help)
        actions_row.addWidget(self.abe_check_button)
        actions_row.addWidget(self.abe_help_button)
        actions_row.addStretch()
        abe_layout.addLayout(actions_row)
        layout.addWidget(self.abe_card)

        # ABE Features status card
        self.abe_features_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.abe_features_card.setObjectName("Card")
        features_layout = QtWidgets.QVBoxLayout(self.abe_features_card)
        features_layout.setContentsMargins(14, 14, 14, 14)
        features_layout.setSpacing(8)

        self.abe_features_title = QtWidgets.QLabel()
        self.abe_features_title.setStyleSheet("font-weight: 600;")
        features_layout.addWidget(self.abe_features_title)

        self.abe_feature_items: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}
        features_form = QtWidgets.QFormLayout()
        features_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        features_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        features_form.setHorizontalSpacing(12)
        features_form.setVerticalSpacing(4)

        feature_keys = [
            "abe_key_detection",
            "v20_value_detection",
            "support_check",
            "aes_gcm_decryption",
            "dpapi_fallback",
            "logging",
            "statistics",
        ]
        for key in feature_keys:
            status_widget = QtWidgets.QWidget()
            status_layout = QtWidgets.QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(6)
            status_dot = QtWidgets.QLabel()
            status_dot.setFixedSize(8, 8)
            status_dot.setStyleSheet("border-radius: 4px; background: #9fb0c3;")
            desc_label = QtWidgets.QLabel()
            desc_label.setObjectName("Muted")
            status_layout.addWidget(status_dot, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(desc_label)
            status_layout.addStretch()
            self.abe_feature_items[key] = (status_dot, desc_label)

            func_label = QtWidgets.QLabel()
            func_label.setObjectName("DetailLabel")
            features_form.addRow(func_label, status_widget)
            setattr(self, f"abe_feature_{key}_label", func_label)

        features_layout.addLayout(features_form)

        # Limitations section
        self.abe_limitations_label = QtWidgets.QLabel()
        self.abe_limitations_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        features_layout.addWidget(self.abe_limitations_label)

        self.abe_limitations_list = QtWidgets.QLabel()
        self.abe_limitations_list.setObjectName("Muted")
        self.abe_limitations_list.setWordWrap(True)
        features_layout.addWidget(self.abe_limitations_list)

        layout.addWidget(self.abe_features_card)
        layout.addStretch()

    def _build_proxy_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.proxy_tab)
        layout.setSpacing(12)
        self.proxy_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.proxy_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.proxy_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.proxy_title = QtWidgets.QLabel()
        self.proxy_title.setStyleSheet("font-weight: 600;")
        self.proxy_body = QtWidgets.QLabel()
        self.proxy_body.setObjectName("Muted")
        self.proxy_body.setWordWrap(True)
        card_layout.addWidget(self.proxy_title)
        card_layout.addWidget(self.proxy_body)
        self.proxy_action = make_button("", "primary")
        self.proxy_action.clicked.connect(self._export_proxy)
        self.proxy_copy_button = make_button("", "ghost")
        self.proxy_copy_button.clicked.connect(self._copy_proxy)
        self.proxy_check_button = make_button("", "ghost")
        self.proxy_check_button.clicked.connect(self._check_proxy)
        actions_row = QtWidgets.QHBoxLayout()
        actions_row.setSpacing(8)
        actions_row.addWidget(self.proxy_action)
        actions_row.addWidget(self.proxy_copy_button)
        actions_row.addWidget(self.proxy_check_button)
        actions_row.addStretch()
        card_layout.addLayout(actions_row)
        layout.addWidget(self.proxy_card)

    def _proxy_payload(self) -> dict | None:
        if not self.client:
            return None
        config = (
            self.client.get("client_config")
            if isinstance(self.client.get("client_config"), dict)
            else {}
        )
        proxy = config.get("proxy")
        if not isinstance(proxy, dict):
            return None
        host = proxy.get("host") or self.client.get("ip") or ""
        return {
            "enabled": bool(proxy.get("enabled") or proxy.get("port")),
            "host": host,
            "port": proxy.get("port"),
            "type": proxy.get("type") or "socks5",
            "udp": proxy.get("udp"),
        }

    def _render_proxy_info(self) -> None:
        if not hasattr(self, "proxy_body"):
            return
        if not self.client:
            self.proxy_body.setText(self.i18n.t("client_proxy_body"))
            if hasattr(self, "proxy_copy_button"):
                self.proxy_copy_button.setEnabled(False)
            if hasattr(self, "proxy_check_button"):
                self.proxy_check_button.setEnabled(False)
            return
        payload = self._proxy_payload()
        if not payload:
            self.proxy_body.setText(self.i18n.t("proxy_status_disabled"))
            if hasattr(self, "proxy_copy_button"):
                self.proxy_copy_button.setEnabled(False)
            if hasattr(self, "proxy_check_button"):
                self.proxy_check_button.setEnabled(False)
            return
        enabled = payload.get("enabled")
        port = payload.get("port")
        if not enabled and not port:
            self.proxy_body.setText(self.i18n.t("proxy_status_disabled"))
            if hasattr(self, "proxy_copy_button"):
                self.proxy_copy_button.setEnabled(False)
            if hasattr(self, "proxy_check_button"):
                self.proxy_check_button.setEnabled(False)
            return
        host = payload.get("host") or "--"
        proxy_type = payload.get("type") or "socks5"
        udp_enabled = payload.get("udp")
        lines = [
            f"{self.i18n.t('proxy_status_label')}: {self.i18n.t('proxy_status_ready')}",
            f"{self.i18n.t('proxy_host_label')}: {host}",
            f"{self.i18n.t('proxy_port_label')}: {port or '--'}",
            f"{self.i18n.t('proxy_type_label')}: {proxy_type}",
        ]
        if udp_enabled is not None:
            lines.append(
                f"{self.i18n.t('proxy_udp_label')}: {self._format_proxy_bool(udp_enabled)}"
            )
        self.proxy_body.setText("\n".join(lines))
        if hasattr(self, "proxy_copy_button"):
            self.proxy_copy_button.setEnabled(bool(host and port))
        if hasattr(self, "proxy_check_button"):
            self.proxy_check_button.setEnabled(bool(host and port))

    def _abe_payload(self) -> dict | None:
        if not self.client:
            return None
        config = (
            self.client.get("client_config")
            if isinstance(self.client.get("client_config"), dict)
            else {}
        )
        payload = config.get("abe")
        return payload if isinstance(payload, dict) else None

    def _abe_status_label(self, status: str) -> str:
        if status == "available":
            return self.i18n.t("abe_status_available")
        if status == "detected":
            return self.i18n.t("abe_status_detected")
        if status == "blocked":
            return self.i18n.t("abe_status_blocked")
        return self.i18n.t("abe_status_unknown")

    def _abe_status_color(self, status: str) -> str:
        if status == "available":
            return "#37d67a"
        if status == "detected":
            return "#f5c542"
        if status == "blocked":
            return "#ff6b6b"
        return "#9fb0c3"

    def _render_abe_info(self) -> None:
        if not hasattr(self, "abe_title"):
            return
        payload = self._abe_payload() or {}
        status = str(payload.get("status") or "unknown").strip().lower()
        status_label = self._abe_status_label(status)
        chrome_version = payload.get("chrome_version")
        status_text = status_label
        if chrome_version:
            status_text = f"{status_label} (Chrome {chrome_version})"
        self.abe_status_text.setText(status_text)
        self.abe_status_dot.setStyleSheet(
            f"border-radius: 4px; background: {self._abe_status_color(status)};"
        )

        methods: list[str] = []
        if payload.get("dpapi_available"):
            methods.append("DPAPI")
        if payload.get("ielevator_available"):
            methods.append("IElevator")
        method_value = payload.get("method") or (" + ".join(methods) if methods else "--")
        self.abe_method_value.setText(method_value)

        version_value = "--"
        if payload.get("detected"):
            version_value = "APPB (Chrome 127+)"
        elif payload.get("chrome_version"):
            version_value = f"Chrome {payload.get('chrome_version')}"
        self.abe_version_value.setText(version_value)

        enabled = bool(payload)
        self.abe_check_button.setEnabled(enabled)
        self.abe_help_button.setEnabled(True)

        self._render_abe_features(payload)

    def _render_abe_features(self, payload: dict) -> None:
        if not hasattr(self, "abe_features_card"):
            return

        # Get diagnostic values from payload
        is_windows = bool(payload.get("windows"))
        chrome_installed = bool(payload.get("chrome_installed"))
        elevation_service = bool(payload.get("elevation_service"))
        dpapi_available = bool(payload.get("dpapi_available"))
        ielevator_available = bool(payload.get("ielevator_available"))
        detected = bool(payload.get("detected"))
        available = bool(payload.get("available"))
        cookies_v20 = payload.get("cookies_v20")
        cookies_total = payload.get("cookies_total")

        # Build dynamic descriptions with actual values
        def yes_no(val: bool) -> str:
            return self.i18n.t("proxy_bool_yes") if val else self.i18n.t("proxy_bool_no")

        feature_status = {
            "abe_key_detection": {
                "active": is_windows and chrome_installed,
                "desc": f"{self.i18n.t('abe_feature_key_detection_desc')} (Chrome: {yes_no(chrome_installed)})",
            },
            "v20_value_detection": {
                "active": isinstance(cookies_v20, int) and cookies_v20 > 0,
                "desc": f"Cookies v20: {cookies_v20 if isinstance(cookies_v20, int) else '--'} / {cookies_total if isinstance(cookies_total, int) else '--'}",
            },
            "support_check": {
                "active": is_windows,
                "desc": f"check_abe_support() → Windows: {yes_no(is_windows)}",
            },
            "aes_gcm_decryption": {
                "active": detected and available,
                "desc": f"{self.i18n.t('abe_feature_aes_gcm_desc')} ({yes_no(detected and available)})",
            },
            "dpapi_fallback": {
                "active": dpapi_available,
                "desc": f"DPAPI: {yes_no(dpapi_available)}, IElevator: {yes_no(ielevator_available)}",
            },
            "logging": {
                "active": True,
                "desc": self.i18n.t("abe_feature_logging_desc"),
            },
            "statistics": {
                "active": True,
                "desc": self.i18n.t("abe_feature_statistics_desc"),
            },
        }

        active_color = "#37d67a"
        inactive_color = "#ff6b6b"  # Red for inactive/unavailable

        for key, item in self.abe_feature_items.items():
            status_dot, desc_label = item
            info = feature_status.get(key, {"active": False, "desc": "--"})
            is_active = info.get("active", False)
            color = active_color if is_active else inactive_color
            status_dot.setStyleSheet(f"border-radius: 4px; background: {color};")
            desc_label.setText(info.get("desc", "--"))

    def _copy_proxy(self) -> None:
        payload = self._proxy_payload()
        if not payload:
            return
        host = payload.get("host") or ""
        port = payload.get("port")
        if not host or not port:
            return
        proxy_type = payload.get("type") or "socks5"
        proxy_string = f"{proxy_type}://{host}:{port}"
        QtWidgets.QApplication.clipboard().setText(proxy_string)

    def _check_proxy(self) -> None:
        payload = self._proxy_payload()
        if not payload:
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("nav_proxy"),
                self.i18n.t("proxy_status_disabled"),
            )
            return
        host = payload.get("host") or ""
        port = payload.get("port")
        if not host or not port:
            QtWidgets.QMessageBox.warning(
                self,
                self.i18n.t("nav_proxy"),
                self.i18n.t("proxy_status_disabled"),
            )
            return
        if self._proxy_check_worker and self._proxy_check_worker.isRunning():
            return
        if hasattr(self, "proxy_check_button"):
            self.proxy_check_button.setEnabled(False)
            self.proxy_check_button.setText(self.i18n.t("proxy_checking"))
        client_id = str(self.client.get("id") if self.client else "") or "client"
        worker = ProxyCheckWorker(client_id, host, port)
        worker.finished.connect(self._handle_proxy_check_finished)
        self._proxy_check_worker = worker
        worker.start()

    def _handle_proxy_check_finished(
        self, _client_id: str, ok: bool, detail: str, latency_ms: int
    ) -> None:
        self._proxy_check_worker = None
        if hasattr(self, "proxy_check_button"):
            self.proxy_check_button.setEnabled(True)
            self.proxy_check_button.setText(self.i18n.t("proxy_check_button"))
        if ok:
            message = f"{self.i18n.t('proxy_check_ok')} ({latency_ms} ms)"
            QtWidgets.QMessageBox.information(self, self.i18n.t("nav_proxy"), message)
            return
        suffix = detail.strip() if isinstance(detail, str) else ""
        message = self.i18n.t("proxy_check_failed")
        if suffix:
            message = f"{message}: {suffix}"
        QtWidgets.QMessageBox.warning(self, self.i18n.t("nav_proxy"), message)

    def _show_abe_diagnostics(self) -> None:
        payload = self._abe_payload() or {}
        dialog = AbeDiagnosticsDialog(self.i18n, payload, parent=self)
        dialog.exec()

    def _show_abe_stats(self) -> None:
        payload = self._abe_payload() or {}
        total = payload.get("cookies_total")
        v20 = payload.get("cookies_v20")
        if isinstance(total, int) and isinstance(v20, int):
            message = f"{self.i18n.t('abe_v20_count')}: {v20} / {total}"
        else:
            message = self.i18n.t("abe_stats_empty")
        QtWidgets.QMessageBox.information(self, self.i18n.t("abe_cookies_stats"), message)

    def _show_abe_help(self) -> None:
        message = self.i18n.t("abe_help_body")
        if message == "abe_help_body":
            message = "Install Chrome 127+ and required dependencies (DPAPI, comtypes) to enable ABE decryption."
        QtWidgets.QMessageBox.information(self, self.i18n.t("abe_help"), message)

    def _build_storage_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.storage_tab)
        layout.setSpacing(12)
        self.storage_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.storage_card.setObjectName("Card")
        card_layout = QtWidgets.QVBoxLayout(self.storage_card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        self.storage_title = QtWidgets.QLabel()
        self.storage_title.setStyleSheet("font-weight: 600;")
        self.storage_body = QtWidgets.QLabel()
        self.storage_body.setObjectName("Muted")
        self.storage_body.setWordWrap(True)
        card_layout.addWidget(self.storage_title)
        card_layout.addWidget(self.storage_body)
        self.storage_action = make_button("", "primary")
        self.storage_action.clicked.connect(self._open_storage)
        card_layout.addWidget(self.storage_action, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.storage_card)

    def _build_activity_tab(self) -> None:
        """Build the Activity Log tab UI."""
        layout = QtWidgets.QVBoxLayout(self.activity_tab)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with title and controls
        header = GlassFrame(radius=16, tone="card", tint_alpha=150, border_alpha=60)
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(12)

        # Title row
        title_row = QtWidgets.QHBoxLayout()
        self.activity_title = QtWidgets.QLabel()
        self.activity_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        title_row.addWidget(self.activity_title)
        title_row.addStretch()
        
        # Total count label
        self.activity_total_label = QtWidgets.QLabel()
        self.activity_total_label.setObjectName("Muted")
        title_row.addWidget(self.activity_total_label)
        header_layout.addLayout(title_row)

        # Filter row
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.setSpacing(8)

        # Search input
        self.activity_search = QtWidgets.QLineEdit()
        self.activity_search.setMinimumWidth(200)
        self.activity_search.textChanged.connect(self._on_activity_search_changed)
        filter_row.addWidget(self.activity_search)

        # Type filter dropdown
        self.activity_type_filter = QtWidgets.QComboBox()
        self.activity_type_filter.setMinimumWidth(120)
        self.activity_type_filter.currentIndexChanged.connect(self._on_activity_filter_changed)
        filter_row.addWidget(self.activity_type_filter)

        # Application filter dropdown
        self.activity_app_filter = QtWidgets.QComboBox()
        self.activity_app_filter.setMinimumWidth(150)
        self.activity_app_filter.currentIndexChanged.connect(self._on_activity_filter_changed)
        filter_row.addWidget(self.activity_app_filter)

        filter_row.addStretch()

        # Action buttons
        self.activity_refresh_btn = make_button("", "ghost")
        self.activity_refresh_btn.clicked.connect(self._refresh_activity_logs)
        filter_row.addWidget(self.activity_refresh_btn)

        self.activity_delete_all_btn = make_button("", "danger")
        self.activity_delete_all_btn.clicked.connect(self._delete_all_activity_logs)
        filter_row.addWidget(self.activity_delete_all_btn)

        header_layout.addLayout(filter_row)
        layout.addWidget(header)

        # Activity logs table
        self.activity_table = QtWidgets.QTableWidget()
        self.activity_table.setColumnCount(5)
        self.activity_table.setHorizontalHeaderLabels([
            self.i18n.t("activity_col_time"),
            self.i18n.t("activity_col_app"),
            self.i18n.t("activity_col_window"),
            self.i18n.t("activity_col_input"),
            self.i18n.t("activity_col_type"),
        ])
        self.activity_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Column widths
        header_view = self.activity_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.activity_table, 1)

        # Load more button
        self.activity_load_more_btn = make_button(self.i18n.t("activity_load_more"), "ghost")
        self.activity_load_more_btn.clicked.connect(self._load_more_activity_logs)
        self.activity_load_more_btn.setVisible(False)
        layout.addWidget(self.activity_load_more_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # Empty state label
        self.activity_empty_label = QtWidgets.QLabel()
        self.activity_empty_label.setObjectName("Muted")
        self.activity_empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.activity_empty_label.setVisible(False)
        layout.addWidget(self.activity_empty_label)

        # State
        self._activity_logs: list[dict] = []
        self._activity_total = 0
        self._activity_offset = 0
        self._activity_limit = 50

    def _update_activity_type_filter(self) -> None:
        """Populate type filter dropdown."""
        current = self.activity_type_filter.currentData()
        self.activity_type_filter.clear()
        self.activity_type_filter.addItem(self.i18n.t("activity_filter_all"), "")
        self.activity_type_filter.addItem(self.i18n.t("activity_filter_keystroke"), "keystroke")
        self.activity_type_filter.addItem(self.i18n.t("activity_filter_clipboard"), "clipboard")
        if current:
            idx = self.activity_type_filter.findData(current)
            if idx >= 0:
                self.activity_type_filter.setCurrentIndex(idx)

    def _refresh_activity_logs(self) -> None:
        """Refresh activity logs from server."""
        if not self.client or not self.api:
            return
        
        client_id = self.client.get("id")
        if not client_id:
            return

        self._activity_offset = 0
        self._load_activity_logs(reset=True)

    def _load_activity_logs(self, reset: bool = False) -> None:
        """Load activity logs from API."""
        if not self.client or not self.api:
            return

        client_id = self.client.get("id")
        if not client_id:
            return

        try:
            # Get filter values
            search = self.activity_search.text().strip() or None
            entry_type = self.activity_type_filter.currentData() or None
            app_filter = self.activity_app_filter.currentData() or None

            result = self.api.fetch_activity_logs(
                session_id=client_id,
                limit=self._activity_limit,
                offset=self._activity_offset,
                entry_type=entry_type,
                application=app_filter,
                search=search,
            )

            logs = result.get("logs", [])
            self._activity_total = result.get("total", 0)

            if reset:
                self._activity_logs = logs
            else:
                self._activity_logs.extend(logs)

            self._activity_offset += len(logs)
            self._render_activity_table()
            self._update_activity_applications()

        except Exception as e:
            self._activity_logs = []
            self._activity_total = 0
            self._render_activity_table()

    def _load_more_activity_logs(self) -> None:
        """Load more activity logs."""
        self._load_activity_logs(reset=False)

    def _on_activity_search_changed(self) -> None:
        """Handle search input change."""
        self._activity_offset = 0
        self._load_activity_logs(reset=True)

    def _on_activity_filter_changed(self) -> None:
        """Handle filter dropdown change."""
        self._activity_offset = 0
        self._load_activity_logs(reset=True)

    def _update_activity_applications(self) -> None:
        """Update application filter dropdown."""
        if not self.client or not self.api:
            return

        client_id = self.client.get("id")
        if not client_id:
            return

        try:
            current = self.activity_app_filter.currentData()
            apps = self.api.fetch_activity_applications(client_id)
            
            self.activity_app_filter.blockSignals(True)
            self.activity_app_filter.clear()
            self.activity_app_filter.addItem(self.i18n.t("activity_filter_app"), "")
            for app in apps:
                self.activity_app_filter.addItem(app, app)
            
            if current:
                idx = self.activity_app_filter.findData(current)
                if idx >= 0:
                    self.activity_app_filter.setCurrentIndex(idx)
            self.activity_app_filter.blockSignals(False)
        except Exception:
            pass

    def _render_activity_table(self) -> None:
        """Render activity logs in table."""
        self.activity_table.setRowCount(0)
        
        # Update total label
        self.activity_total_label.setText(
            self.i18n.t("activity_total").replace("{count}", str(self._activity_total))
        )

        if not self._activity_logs:
            self.activity_table.setVisible(False)
            self.activity_empty_label.setText(self.i18n.t("activity_no_logs"))
            self.activity_empty_label.setVisible(True)
            self.activity_load_more_btn.setVisible(False)
            return

        self.activity_table.setVisible(True)
        self.activity_empty_label.setVisible(False)

        for log in self._activity_logs:
            row = self.activity_table.rowCount()
            self.activity_table.insertRow(row)

            # Time
            timestamp = log.get("timestamp", "")
            time_str = self._format_activity_time(timestamp)
            time_item = QtWidgets.QTableWidgetItem(time_str)
            time_item.setData(QtCore.Qt.ItemDataRole.UserRole, log.get("id"))
            self.activity_table.setItem(row, 0, time_item)

            # Application
            app = log.get("application", "Unknown")
            self.activity_table.setItem(row, 1, QtWidgets.QTableWidgetItem(app))

            # Window title
            window = log.get("window_title", "")
            window_item = QtWidgets.QTableWidgetItem(window)
            window_item.setToolTip(window)
            self.activity_table.setItem(row, 2, window_item)

            # Input text
            input_text = log.get("input_text", "")
            input_item = QtWidgets.QTableWidgetItem(input_text)
            input_item.setToolTip(input_text)
            self.activity_table.setItem(row, 3, input_item)

            # Type
            entry_type = log.get("entry_type", "keystroke")
            type_text = "📋" if entry_type == "clipboard" else "⌨️"
            self.activity_table.setItem(row, 4, QtWidgets.QTableWidgetItem(type_text))

        # Show load more if there are more logs
        has_more = len(self._activity_logs) < self._activity_total
        self.activity_load_more_btn.setVisible(has_more)

    def _format_activity_time(self, timestamp: str) -> str:
        """Format timestamp for display."""
        if not timestamp:
            return "--"
        try:
            # Parse ISO format
            if timestamp.endswith("Z"):
                timestamp = timestamp[:-1] + "+00:00"
            dt = datetime.fromisoformat(timestamp)
            if dt.tzinfo:
                dt = dt.astimezone()
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            if dt.date() == now.date():
                return dt.strftime("%H:%M:%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(timestamp)[:19]

    def _delete_all_activity_logs(self) -> None:
        """Delete all activity logs for the client."""
        if not self.client or not self.api:
            return

        client_id = self.client.get("id")
        if not client_id:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            self.i18n.t("activity_delete_title"),
            self.i18n.t("activity_delete_all_body"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        try:
            self.api.delete_activity_logs(client_id)
            self._refresh_activity_logs()
        except Exception:
            pass

    def _build_cookies_menu(self) -> None:
        menu = QtWidgets.QMenu(self.cookies_button)
        cookie_actions = [("all", self.i18n.t("menu_cookies_all"))]
        cookie_actions.extend(
            browser_choices_from_config(self.client.get("client_config") if self.client else None)
        )
        for key, label in cookie_actions:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _, browser=key: self._emit_cookie(browser)
            )
        menu.addSeparator()
        diagnostics_action = menu.addAction(self.i18n.t("abe_diagnostics"))
        diagnostics_action.triggered.connect(self._show_abe_diagnostics)
        stats_action = menu.addAction(self.i18n.t("abe_cookies_stats"))
        stats_action.triggered.connect(self._show_abe_stats)
        self.cookies_button.setMenu(menu)
        for key, button in self.cookie_buttons.items():
            label = dict(cookie_actions).get(key, key)
            button.setText(label)

    def _render_cookie_buttons(self) -> None:
        if not hasattr(self, "cookie_buttons_layout"):
            return
        self._clear_layout(self.cookie_buttons_layout)
        self.cookie_buttons = {}
        actions = [("all", self.i18n.t("menu_cookies_all"))]
        actions.extend(
            browser_choices_from_config(self.client.get("client_config") if self.client else None)
        )
        max_cols = 4
        row = 0
        col = 0
        for key, label in actions:
            button = make_button(label, "ghost")
            button.clicked.connect(lambda _, browser=key: self._emit_cookie(browser))
            self.cookie_buttons[key] = button
            self.cookie_buttons_layout.addWidget(button, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        self.cookie_buttons_layout.setColumnStretch(max_cols, 1)

    def _update_view(self) -> None:
        if not self.client:
            self.title_label.setText(self.i18n.t("client_details_title"))
            self.subtitle_label.setText("--")
            self.status_text.setText(self.i18n.t("top_status_unknown"))
            self._set_status_color(None)
            return
        name = self.client.get("name") or self.client.get("id") or "--"
        self.title_label.setText(name)
        client_id = self._safe_text(self.client.get("id"))
        if client_id != "--":
            self.subtitle_label.setText(f"{self.i18n.t('client_info_id')}: {client_id}")
        else:
            self.subtitle_label.setText("--")
        online = self.client.get("status") == "connected"
        self.status_text.setText(
            self.i18n.t("top_status_online") if online else self.i18n.t("top_status_offline")
        )
        self._set_status_color(online)
        self._update_actions(bool(self.client.get("connected")))
        self._render_client_info()
        self._render_system_info()
        self._render_proxy_info()
        self._render_abe_info()
        self._sync_work_status()
        self._render_tags()
        self._build_cookies_menu()
        self._render_cookie_buttons()

    def _render_client_info(self) -> None:
        def _add_row(label: str, value: str | QtWidgets.QWidget) -> None:
            row = self.client_info_form.rowCount()
            label_widget = QtWidgets.QLabel(label)
            label_widget.setObjectName("DetailLabel")
            label_widget.setFixedWidth(self._detail_label_width)
            label_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            if isinstance(value, QtWidgets.QWidget):
                value_widget = value
            else:
                value_widget = QtWidgets.QLabel(value)
                value_widget.setObjectName("DetailValue")
            value_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            self.client_info_form.insertRow(row, label_widget, value_widget)

        self._clear_form(self.client_info_form)
        client = self.client or {}
        region = self._safe_text(client.get("region"))
        if region != "--":
            region = self.i18n.t(region)
        _add_row(self.i18n.t("client_info_region"), self._build_region_value(region, client))
        _add_row(self.i18n.t("client_info_ip"), self._safe_text(client.get("ip")))
        _add_row(self.i18n.t("client_info_status"), self._session_status_label(client))
        _add_row(
            self.i18n.t("client_info_team"),
            self._resolve_team_name(client.get("assigned_team_id")),
        )
        _add_row(
            self.i18n.t("client_info_operator"),
            self._resolve_operator_name(client.get("assigned_operator_id")),
        )
        _add_row(self.i18n.t("client_info_last_seen"), self._format_last_seen(client.get("last_seen")))
        _add_row(self.i18n.t("client_info_created"), self._format_created_at(client.get("created_at")))

    def _populate_work_status_options(self) -> None:
        self.work_status_combo.blockSignals(True)
        self.work_status_combo.clear()
        options = [
            ("planning", self.i18n.t("work_status_planning")),
            ("in_work", self.i18n.t("work_status_in_work")),
            ("worked_out", self.i18n.t("work_status_worked_out")),
        ]
        for value, label in options:
            self.work_status_combo.addItem(label, value)
        self.work_status_combo.blockSignals(False)

    def _sync_work_status(self) -> None:
        if not self.client:
            return
        status = self._normalize_work_status(self.client.get("work_status"))
        self._work_status_updating = True
        index = self.work_status_combo.findData(status)
        if index >= 0:
            self.work_status_combo.setCurrentIndex(index)
        self._work_status_updating = False

    def _handle_work_status_changed(self) -> None:
        if self._work_status_updating or not self.client or not self.api:
            return
        client_id = self.client.get("id")
        if not client_id:
            return
        status = self._normalize_work_status(self.work_status_combo.currentData())
        try:
            self.api.update_client_work_status(client_id, status)
        except Exception:
            self._sync_work_status()
            return
        self.client["work_status"] = status
        self.client_updated.emit(client_id, {"work_status": status})

    def _available_tags(self) -> list[dict]:
        if not self.client:
            return []
        team_id = self.client.get("assigned_team_id")
        if not team_id:
            return []
        for team in self.settings.get("teams", []):
            if team.get("id") == team_id:
                return list(team.get("tags") or [])
        return []

    def _render_tags(self) -> None:
        tags = self._available_tags()
        assigned = {
            str(tag.get("id"))
            for tag in (self.client.get("tags") or [])
            if isinstance(tag, dict) and tag.get("id")
        }
        self._tags_updating = True
        self._tag_checks = {}
        self._clear_layout(self.tags_layout)
        if not tags:
            self.tags_layout.addWidget(self._build_tag_placeholder(self.i18n.t("tags_empty")))
            if self.tags_hint.text():
                self.tags_layout.addWidget(self.tags_hint)
        else:
            for tag in tags:
                name = str(tag.get("name") or "").strip()
                if not name:
                    continue
                tag_id = str(tag.get("id") or "")
                color = str(tag.get("color") or "").strip()
                row, checkbox = self._build_tag_row(
                    name,
                    color,
                    bool(tag_id and tag_id in assigned),
                    tag_id,
                )
                self.tags_layout.addWidget(row, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
                if tag_id:
                    self._tag_checks[tag_id] = checkbox
        self.tags_layout.addStretch()
        self._tags_updating = False

    def _handle_tag_checkbox_changed(self, _state: int) -> None:
        if self._tags_updating or not self.client or not self.api:
            return
        client_id = self.client.get("id")
        if not client_id:
            return
        tag_ids = [
            tag_id for tag_id, checkbox in self._tag_checks.items() if checkbox.isChecked()
        ]
        try:
            self.api.update_client_tags(client_id, tag_ids)
        except Exception:
            self._render_tags()
            return
        tags = [tag for tag in self._available_tags() if tag.get("id") in tag_ids]
        self.client["tags"] = tags
        self.client_updated.emit(client_id, {"tags": tags})

    def _render_system_info(self) -> None:
        def _add_row(label: str, value: str | QtWidgets.QWidget) -> None:
            row = self.system_info_form.rowCount()
            label_widget = QtWidgets.QLabel(label)
            label_widget.setObjectName("DetailLabel")
            label_widget.setFixedWidth(self._detail_label_width)
            label_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            if isinstance(value, QtWidgets.QWidget):
                value_widget = value
                value_widget.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Preferred,
                )
            else:
                value_widget = QtWidgets.QLabel(value)
                value_widget.setObjectName("DetailValue")
                value_widget.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Preferred,
                )
            self.system_info_form.insertRow(row, label_widget, value_widget)

        self._clear_form(self.system_info_form)
        client = self.client or {}
        config = client.get("client_config") if isinstance(client.get("client_config"), dict) else {}
        _add_row(self.i18n.t("client_system_pc"), self._safe_text(self._config_value(config, ["pc", "pc_name", "device", "device_name"])) )
        _add_row(self.i18n.t("client_system_cpu"), self._safe_text(self._config_value(config, ["cpu", "cpu_name"])))
        _add_row(self.i18n.t("client_system_ram"), self._safe_text(self._config_value(config, ["ram", "memory"])))
        _add_row(self.i18n.t("client_system_gpu"), self._safe_text(self._config_value(config, ["gpu", "graphics"])))
        _add_row(self.i18n.t("client_system_storage"), self._safe_text(self._config_value(config, ["storage", "disk"])))
        _add_row(self.i18n.t("client_system_browsers"), self._build_browser_value(config.get("browsers")))
        updated_value = None
        for key in ("system_info_updated_at", "system_info_updated"):
            if key in config:
                updated_value = config.get(key)
                break
        _add_row(self.i18n.t("client_system_updated"), self._format_system_info_updated(updated_value))

    def _build_browser_value(self, value: object) -> QtWidgets.QWidget:
        items = self._browser_items(value)
        if not items:
            label = QtWidgets.QLabel("--")
            label.setObjectName("DetailValue")
            return label
        wrapper = QtWidgets.QWidget()
        layout = FlowLayout(wrapper, spacing=6)
        layout.setContentsMargins(0, 0, 0, 0)
        for item in items:
            chip = QtWidgets.QLabel(item)
            chip.setObjectName("BrowserChip")
            chip.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Maximum,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            layout.addWidget(chip)
        return wrapper

    def _browser_items(self, value: object) -> list[str]:
        if not value:
            return []
        items: list[str] = []
        if isinstance(value, dict):
            for name, version in value.items():
                label = str(name or "").strip()
                if not label:
                    continue
                version_text = str(version or "").strip()
                items.append(f"{label} {version_text}".strip())
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    label = str(entry.get("name") or entry.get("browser") or "").strip()
                    if not label:
                        continue
                    version_text = str(entry.get("version") or entry.get("ver") or "").strip()
                    items.append(f"{label} {version_text}".strip())
                else:
                    label = str(entry or "").strip()
                    if label:
                        items.append(label)
        else:
            text = str(value).strip()
            if text:
                items.append(text)
        return [item for item in items if item]

    def _config_value(self, config: dict, keys: list[str]) -> str:
        for key in keys:
            value = config.get(key)
            if value:
                return str(value)
        return "--"

    def _resolve_team_name(self, team_id: object) -> str:
        value = str(team_id or "").strip()
        if not value:
            return "--"
        for team in self.settings.get("teams", []):
            if team.get("id") == value:
                return team.get("name") or value
        return value

    def _resolve_operator_name(self, operator_id: object) -> str:
        value = str(operator_id or "").strip()
        if not value:
            return "--"
        for team in self.settings.get("teams", []):
            for member in team.get("members", []):
                if member.get("account_id") == value:
                    return member.get("name") or value
        return value

    def _session_status_label(self, client: dict) -> str:
        session_status = str(client.get("session_status") or "").strip().lower()
        if session_status == "busy":
            return self.i18n.t("status_busy")
        if session_status == "available":
            return self.i18n.t("status_available")
        if session_status == "offline":
            return self.i18n.t("status_offline")
        connected = bool(client.get("connected")) or client.get("status") == "connected"
        if connected:
            return self.i18n.t("status_connected")
        return self.i18n.t("status_disconnected")

    def _update_actions(self, connected: bool) -> None:
        if connected:
            self.connect_button.setText(self.i18n.t("button_connected"))
        else:
            self.connect_button.setText(self.i18n.t("button_connect"))

    def _set_status_color(self, connected: bool | None) -> None:
        if connected is None:
            status = "unknown"
        elif connected:
            status = "online"
        else:
            status = "offline"
        self.status_dot.setProperty("status", status)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _emit_cookie(self, browser: str) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.extra_action_requested.emit(client_id, f"cookies:{browser}")

    def _export_proxy(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.extra_action_requested.emit(client_id, "proxy")

    def _open_storage(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.storage_requested.emit(client_id)

    def _delete_client(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.delete_requested.emit(client_id)

    def _toggle_connection(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if not client_id:
            return
        connected = bool(self.client.get("connected"))
        self.connect_requested.emit(client_id, connected)

    def _emit_rename(self) -> None:
        if not self.client:
            return
        client_id = self.client.get("id")
        if client_id:
            self.rename_requested.emit(client_id)

    @staticmethod
    def _clear_form(form: QtWidgets.QFormLayout) -> None:
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _safe_text(value: object) -> str:
        text = str(value or "").strip()
        return text or "--"

    @staticmethod
    def _normalize_work_status(value: object) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"planning", "in_work", "worked_out"}:
            return raw
        return "planning"

    def _format_last_seen(self, value: object) -> str:
        parsed = self._parse_datetime(value)
        if not parsed:
            return "--"
        if parsed.tzinfo:
            parsed = parsed.astimezone()
            now = datetime.now(parsed.tzinfo)
        else:
            now = datetime.now()
        if parsed.date() == now.date():
            return parsed.strftime("%H:%M:%S")
        return self._format_date_value(parsed)

    def _format_created_at(self, value: object) -> str:
        parsed = self._parse_datetime(value)
        if not parsed:
            return "--"
        return self._format_date_value(parsed)

    def _format_date_value(self, parsed: datetime) -> str:
        lang = self.i18n.language()
        if lang == "ru":
            return parsed.strftime("%d.%m.%Y")
        return parsed.strftime("%Y-%m-%d")

    def _format_proxy_bool(self, value: object) -> str:
        return self.i18n.t("proxy_bool_yes") if bool(value) else self.i18n.t("proxy_bool_no")

    def _format_system_info_updated(self, value: object) -> str:
        parsed = self._parse_datetime(value)
        if not parsed:
            return "--"
        if parsed.tzinfo:
            parsed = parsed.astimezone()
            now = datetime.now(parsed.tzinfo)
        else:
            now = datetime.now()
        if parsed.date() == now.date():
            return parsed.strftime("%H:%M:%S")
        lang = self.i18n.language()
        if lang == "ru":
            return parsed.strftime("%d.%m.%Y %H:%M")
        return parsed.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except Exception:
                return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _tag_icon(self, color: str) -> QtGui.QIcon:
        key = color.strip().lower()
        if not key:
            return QtGui.QIcon()
        cached = self._tag_icon_cache.get(key)
        if cached:
            return cached
        size = 10
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(color))
        painter.drawEllipse(0, 0, size, size)
        painter.end()
        icon = QtGui.QIcon(pixmap)
        self._tag_icon_cache[key] = icon
        return icon

    def _build_region_value(self, region: str, client: dict) -> QtWidgets.QWidget:
        wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        value_label = QtWidgets.QLabel(region)
        value_label.setObjectName("DetailValue")
        layout.addWidget(value_label)
        flag_code = self._resolve_flag_code(client)
        flag_pixmap = self._load_flag_pixmap(flag_code) if flag_code else None
        if flag_pixmap is not None:
            flag_label = QtWidgets.QLabel()
            flag_label.setPixmap(flag_pixmap)
            flag_label.setFixedHeight(flag_pixmap.height())
            layout.addWidget(flag_label)
        layout.addStretch()
        return wrapper

    @staticmethod
    def _resolve_flag_code(client: dict) -> str | None:
        for key in ("country", "country_code", "region_code", "region"):
            value = str(client.get(key) or "").strip()
            if len(value) == 2 and value.isalpha():
                return value.lower()
        return None

    @staticmethod
    def _load_flag_pixmap(code: str | None) -> QtGui.QPixmap | None:
        if not code:
            return None
        base = Path(__file__).resolve().parent.parent / "assets" / "flags"
        path = base / f"{code.lower()}.png"
        if not path.exists():
            return None
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return None
        return pixmap.scaledToHeight(14, QtCore.Qt.TransformationMode.SmoothTransformation)

    def _build_tag_row(
        self, name: str, color: str, checked: bool, tag_id: str
    ) -> tuple[QtWidgets.QFrame, QtWidgets.QCheckBox]:
        row = QtWidgets.QFrame()
        row.setObjectName("TagRow")
        row.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setProperty("tag_id", tag_id)
        checkbox.stateChanged.connect(self._handle_tag_checkbox_changed)
        layout.addWidget(checkbox)

        dot = QtWidgets.QLabel()
        dot.setObjectName("TagDot")
        dot.setFixedSize(10, 10)
        if color:
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        else:
            dot.setStyleSheet("background: rgba(255, 255, 255, 0.3); border-radius: 5px;")
        layout.addWidget(dot)

        label = QtWidgets.QLabel(name)
        label.setObjectName("DetailValue")
        layout.addWidget(label)
        layout.addStretch()
        return row, checkbox

    def _build_tag_placeholder(self, text: str) -> QtWidgets.QFrame:
        row = QtWidgets.QFrame()
        row.setObjectName("TagRow")
        row.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        label = QtWidgets.QLabel(text)
        label.setObjectName("Muted")
        layout.addWidget(label)
        layout.addStretch()
        return row

    @staticmethod
    def _clear_layout(layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
