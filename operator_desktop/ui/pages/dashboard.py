import ipaddress
import logging
import sys
import time
from datetime import datetime
from typing import Dict, List
from pathlib import Path

import requests
from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import RemoteControllerApi
from ...core.i18n import I18n
from ...core.constants import APP_VERSION
from ...core.logging import EventLogger
from ...core.settings import SettingsStore
from ...core.theme import THEMES
from ..common import GlassFrame, load_icon, make_button
from ..browser_catalog import browser_choices_from_config

logger = logging.getLogger(__name__)


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


class ServerPingWorker(QtCore.QThread):
    succeeded = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, api: RemoteControllerApi):
        super().__init__()
        self.api = api

    def run(self) -> None:
        started = time.monotonic()
        try:
            self.api.ping()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        latency_ms = int((time.monotonic() - started) * 1000)
        self.succeeded.emit(latency_ms)


def _normalize_ip(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    elif raw.count(":") == 1 and "." in raw:
        raw = raw.rsplit(":", 1)[0]
    return raw.strip()


def _is_public_ip(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return False
    if parsed.is_private or parsed.is_loopback or parsed.is_link_local:
        return False
    if parsed.is_multicast or parsed.is_reserved:
        return False
    return True


def _normalize_country_code(value: str | None) -> str:
    code = str(value or "").strip().upper()
    if len(code) == 2 and code.isalpha():
        return code
    return ""


def _lookup_country_code(ip_value: str) -> str:
    normalized_ip = _normalize_ip(ip_value)
    if not normalized_ip or not _is_public_ip(normalized_ip):
        return ""
    headers = {"User-Agent": "RemDesk/1.0"}
    timeouts = (2, 4)
    services: list[tuple[str, str]] = [
        (f"https://ipapi.co/{normalized_ip}/country/", "text"),
        (f"https://ipwho.is/{normalized_ip}", "json"),
        (f"https://ipinfo.io/{normalized_ip}/country", "text"),
        (f"http://ip-api.com/json/{normalized_ip}?fields=status,countryCode", "json"),
    ]
    for url, kind in services:
        try:
            response = requests.get(url, headers=headers, timeout=timeouts)
        except Exception:
            continue
        if response.status_code != 200:
            continue
        if kind == "text":
            code = _normalize_country_code(response.text)
        else:
            try:
                payload = response.json()
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if "success" in payload and payload.get("success") is False:
                continue
            if payload.get("status") not in (None, "success"):
                continue
            code = _normalize_country_code(
                payload.get("country_code") or payload.get("countryCode")
            )
        if code:
            return code
    return ""


class IpCountryWorker(QtCore.QThread):
    resolved = QtCore.pyqtSignal(str, str)

    def __init__(self, ip_value: str):
        super().__init__()
        self.ip_value = ip_value

    def run(self) -> None:
        code = _lookup_country_code(self.ip_value)
        self.resolved.emit(self.ip_value, code)


def _resolve_flag_asset_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    candidates = [base_dir / "assets" / "flags"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_path = Path(meipass)
        candidates.append(meipass_path / "operator_desktop" / "assets" / "flags")
        candidates.append(meipass_path / "assets" / "flags")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


FLAG_ASSET_DIR = _resolve_flag_asset_dir()
TWEMOJI_BASE_URL = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"


class DashboardPage(QtWidgets.QWidget):
    storage_requested = QtCore.pyqtSignal(str)
    connect_requested = QtCore.pyqtSignal(str, bool)
    extra_action_requested = QtCore.pyqtSignal(str, str)
    delete_requested = QtCore.pyqtSignal(str)
    client_selected = QtCore.pyqtSignal(str)
    ping_updated = QtCore.pyqtSignal(object)
    server_status_changed = QtCore.pyqtSignal(bool)
    clients_refreshed = QtCore.pyqtSignal(list)

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
        self.current_role = settings.get("role", "operator")
        self.account_id = settings.get("account_id", "")
        self._fetch_in_progress = False
        self._client_fetch_worker: ClientFetchWorker | None = None
        self._server_online: bool | None = None
        self._ping_in_progress = False
        self._ping_worker: ServerPingWorker | None = None
        self._ping_failures = 0
        self._ping_failure_threshold = 3
        self._ping_base_interval_ms = 500
        self._ping_max_interval_ms = 5000
        self.column_keys: list[str] = []
        self._menu_open_count = 0
        self._clients_timer_was_active = False
        self._pending_render = False
        self._ip_country_cache: dict[str, str] = {}
        self._ip_lookup_inflight: set[str] = set()
        self._ip_lookup_workers: dict[str, IpCountryWorker] = {}
        self._flag_pixmap_cache: dict[str, QtGui.QPixmap | None] = {}
        self._logs_visible = False
        self._ensure_client_state()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = GlassFrame(radius=18, tone="card_alt", tint_alpha=160, border_alpha=70)
        toolbar.setObjectName("ToolbarCard")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setSpacing(12)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(6)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)

        self.last_sync_label = None
        self.status_label = None

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

        self.activity_button = make_button("", "ghost")
        self.activity_button.setCheckable(True)
        self.activity_button.clicked.connect(self.toggle_logs)
        toolbar_layout.addWidget(self.activity_button)

        layout.addWidget(toolbar)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(8)
        self.table_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        self.table_card.setObjectName("Card")
        table_layout = QtWidgets.QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMouseTracking(True)
        self.table.setShowGrid(False)
        table_font = self.table.font()
        table_font.setPointSize(max(12, table_font.pointSize() + 1))
        self.table.setFont(table_font)
        self.table.viewport().installEventFilter(self)
        self.table.cellDoubleClicked.connect(self._emit_client_selected)
        header = self.table.horizontalHeader()
        header_font = header.font()
        header_font.setPointSize(max(11, header_font.pointSize() + 1))
        header.setFont(header_font)
        header.setStretchLastSection(False)
        self._configure_columns()
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.itemChanged.connect(self.handle_item_changed)
        table_layout.addWidget(self.table)
        self.splitter.addWidget(self.table_card)

        self.log_card = GlassFrame(radius=20, tone="card_strong", tint_alpha=180, border_alpha=70)
        self.log_card.setObjectName("DrawerCard")
        log_layout = QtWidgets.QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(14, 14, 14, 14)
        log_layout.setSpacing(10)
        log_header = QtWidgets.QHBoxLayout()
        self.log_title = QtWidgets.QLabel()
        self.log_title.setStyleSheet("font-weight: 600;")
        log_header.addWidget(self.log_title)
        log_header.addStretch()
        self.log_close = make_button("", "ghost")
        self.log_close.clicked.connect(lambda: self.set_logs_visible(False))
        log_header.addWidget(self.log_close)
        log_layout.addLayout(log_header)
        self.log_list = QtWidgets.QListWidget()
        self.log_list.setMouseTracking(True)
        log_layout.addWidget(self.log_list, 1)
        self.splitter.addWidget(self.log_card)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.log_card.setVisible(False)

        layout.addWidget(self.splitter, 1)

        self.set_logs_visible(False)
        self.logger.updated.connect(self.refresh_logs)
        self.ping_timer = QtCore.QTimer(self)
        self.ping_timer.setInterval(self._ping_base_interval_ms)
        self.ping_timer.timeout.connect(self.poll_server_status)
        self.ping_timer.start()

        self.clients_timer = QtCore.QTimer(self)
        self.clients_timer.setInterval(500)
        self.clients_timer.timeout.connect(self.poll_clients)
        self.clients_timer.start()
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
            if "work_status" not in client:
                client["work_status"] = "planning"
                updated = True
            if "server_connected" in client:
                client.pop("server_connected", None)
                updated = True
        if updated:
            self.settings.set("clients", self.clients)
            self.settings.save()

    def set_role(self, role: str) -> None:
        self.current_role = role
        self.account_id = self.settings.get("account_id", "")
        self._configure_columns()
        self._render_current_clients()

    def _build_column_keys(self) -> list[str]:
        return ["name", "work_status", "tags", "ip", "region", "team", "operator"]

    def _column_labels(self) -> dict[str, str]:
        return {
            "name": self.i18n.t("table_name"),
            "work_status": self.i18n.t("table_work_status"),
            "tags": self.i18n.t("table_tags"),
            "team": self.i18n.t("table_team"),
            "operator": self.i18n.t("table_operator"),
            "region": self.i18n.t("table_region"),
            "ip": self.i18n.t("table_ip"),
        }

    def _configure_columns(self) -> None:
        self.column_keys = self._build_column_keys()
        self.table.setColumnCount(len(self.column_keys))
        labels = self._column_labels()
        self.table.setHorizontalHeaderLabels([labels[key] for key in self.column_keys])
        self.configure_table_layout()

    def _column_index(self) -> dict[str, int]:
        return {key: index for index, key in enumerate(self.column_keys)}

    def _render_current_clients(self) -> None:
        search_text = self.search_input.text() if hasattr(self, "search_input") else ""
        if search_text.strip():
            self.filter_clients(search_text)
        else:
            self.render_clients(self._visible_clients(self.clients))

    def _set_menu_active(self, active: bool) -> None:
        if active:
            self._menu_open_count += 1
            if self._menu_open_count == 1:
                if hasattr(self, "clients_timer") and self.clients_timer.isActive():
                    self._clients_timer_was_active = True
                    self.clients_timer.stop()
                else:
                    self._clients_timer_was_active = False
            return
        if self._menu_open_count:
            self._menu_open_count -= 1
        if self._menu_open_count == 0:
            if (
                self._clients_timer_was_active
                and hasattr(self, "clients_timer")
                and self._server_online is not False
            ):
                self.clients_timer.start()
            if self._pending_render:
                self._pending_render = False
                self._render_current_clients()

    def set_logs_visible(self, visible: bool) -> None:
        self._logs_visible = visible
        self.log_card.setVisible(visible)
        self.activity_button.setChecked(visible)
        if visible:
            self.splitter.setSizes([680, 280])
        else:
            self.splitter.setSizes([1, 0])

    def toggle_logs(self) -> None:
        self.set_logs_visible(not self._logs_visible)

    def _visible_clients(self, clients: list[Dict]) -> list[Dict]:
        if self.current_role == "moderator":
            return clients
        if self.current_role == "administrator":
            team_id = self.settings.get("operator_team_id", "")
            if not team_id:
                return []
            return [client for client in clients if client.get("assigned_team_id") == team_id]
        account_id = self.account_id or self.settings.get("account_id", "")
        if not account_id:
            return []
        return [client for client in clients if client.get("assigned_operator_id") == account_id]

    def _resolve_team_name(self, team_id: str | None) -> str:
        if not team_id:
            return self.i18n.t("unassigned_label")
        for team in self.settings.get("teams", []):
            if team.get("id") == team_id:
                return team.get("name", team_id)
        return team_id

    def _resolve_operator_name(self, operator_id: str | None) -> str:
        if not operator_id:
            return self.i18n.t("unassigned_label")
        for team in self.settings.get("teams", []):
            for member in team.get("members", []):
                if member.get("account_id") == operator_id:
                    return member.get("name", operator_id)
        return operator_id

    def _resolve_country_name(self, code: str) -> str:
        normalized = str(code or "").strip().lower()
        if not normalized:
            return "--"
        key = f"country_{normalized}"
        label = self.i18n.t(key)
        return label if label != key else code.upper()

    def _extract_flag_codes(self, client: Dict) -> list[str]:
        ip_value = _normalize_ip(client.get("ip"))
        if not ip_value:
            return []
        cached = self._ip_country_cache.get(ip_value)
        if cached is None:
            self._schedule_ip_lookup(ip_value)
            return []
        return [cached] if cached else []

    @staticmethod
    def _flag_from_code(code: str) -> str:
        normalized = str(code).strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            return normalized or "--"
        base = 0x1F1E6
        return chr(base + ord(normalized[0]) - 65) + chr(base + ord(normalized[1]) - 65)

    def _format_flags(self, codes: list[str]) -> str:
        if not codes:
            return "--"
        return " ".join(self._flag_from_code(code) for code in codes)

    @staticmethod
    def _parse_last_seen(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except (OverflowError, OSError, ValueError):
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

    def _format_last_seen(self, value: object) -> str:
        parsed = self._parse_last_seen(value)
        if not parsed:
            return "--"
        if parsed.tzinfo:
            parsed = parsed.astimezone()
            now = datetime.now(parsed.tzinfo)
        else:
            now = datetime.now()
        if parsed.date() == now.date():
            return parsed.strftime("%H:%M:%S")
        return parsed.strftime("%Y-%m-%d %H:%M")

    def _resolve_region_display(self, client: Dict) -> str:
        region_value = str(client.get("region") or "").strip()
        codes = self._extract_flag_codes(client)
        if codes:
            country_name = self._resolve_country_name(codes[0])
            if country_name and country_name != codes[0]:
                return country_name
            if region_value:
                return self.i18n.t(region_value)
            return codes[0]
        if region_value:
            return self.i18n.t(region_value)
        return "--"

    @staticmethod
    def _normalize_work_status(value: object) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"planning", "in_work", "worked_out"}:
            return raw
        return "planning"

    def _format_work_status(self, value: object) -> str:
        status = self._normalize_work_status(value)
        key = f"work_status_{status}"
        label = self.i18n.t(key)
        return label if label != key else status.replace("_", " ").title()

    @staticmethod
    def _format_tag_labels(tags: object) -> str:
        if not tags:
            return ""
        if isinstance(tags, list):
            names = []
            for tag in tags:
                if isinstance(tag, dict):
                    name = str(tag.get("name") or "").strip()
                else:
                    name = str(tag or "").strip()
                if name:
                    names.append(name)
            return ", ".join(names)
        return str(tags)

    def apply_work_status_style(self, item: QtWidgets.QTableWidgetItem, status: str) -> None:
        palette = {
            "planning": ("#f6c970", 90),
            "in_work": (self.theme.colors.get("accent", "#0091FF"), 110),
            "worked_out": ("#2dd4bf", 100),
        }
        color, alpha = palette.get(status, palette["planning"])
        fg = QtGui.QColor(color)
        bg = QtGui.QColor(color)
        bg.setAlpha(alpha)
        item.setForeground(QtGui.QBrush(fg))
        item.setBackground(QtGui.QBrush(bg))

    def build_tags_cell(self, tags: list[dict]) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        max_visible = 3
        safe_tags: list[dict] = []
        for tag in tags:
            if isinstance(tag, dict) and tag.get("name"):
                safe_tags.append(tag)
        for tag in safe_tags[:max_visible]:
            label = QtWidgets.QLabel(str(tag.get("name")))
            color = str(tag.get("color") or "#64748b")
            label.setStyleSheet(
                "QLabel {"
                f"background: {color};"
                "color: #0b0f16;"
                "padding: 2px 8px;"
                "border-radius: 8px;"
                "font-size: 11px;"
                "font-weight: 600;"
                "}"
            )
            layout.addWidget(label)
        remaining = len(safe_tags) - max_visible
        if remaining > 0:
            more = QtWidgets.QLabel(f"+{remaining}")
            more.setObjectName("Muted")
            more.setStyleSheet("font-size: 11px;")
            layout.addWidget(more)
        layout.addStretch()
        return container

    def _emoji_font(self) -> QtGui.QFont:
        if hasattr(self, "_cached_emoji_font"):
            return self._cached_emoji_font
        font = QtGui.QFont()
        for family in ("Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", "Apple Color Emoji"):
            if family in QtGui.QFontDatabase.families():
                font = QtGui.QFont(family)
                break
        self._cached_emoji_font = font
        return font

    def _flag_pixmap(self, code: str) -> QtGui.QPixmap | None:
        normalized = _normalize_country_code(code)
        if not normalized:
            return None
        key = normalized.lower()
        if key in self._flag_pixmap_cache:
            return self._flag_pixmap_cache[key]
        paths = [FLAG_ASSET_DIR / f"{key}.png"]
        cache_dir = self._flag_cache_dir()
        if cache_dir:
            paths.append(cache_dir / f"{key}.png")
        pixmap = None
        for path in paths:
            if path.exists():
                loaded = QtGui.QPixmap(str(path))
                if not loaded.isNull():
                    pixmap = loaded
                    break
        if pixmap is None:
            pixmap = self._download_flag_pixmap(key, cache_dir)
        if pixmap.isNull():
            self._flag_pixmap_cache[key] = None
            return None
        target_height = 16
        scaled = pixmap.scaledToHeight(
            target_height, QtCore.Qt.TransformationMode.SmoothTransformation
        )
        self._flag_pixmap_cache[key] = scaled
        return scaled

    def _flag_cache_dir(self) -> Path | None:
        base = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.AppDataLocation
        )
        if not base:
            return None
        path = Path(base) / "flags"
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        return path

    def _twemoji_filename(self, code: str) -> str:
        normalized = _normalize_country_code(code)
        if not normalized:
            return ""
        first = ord(normalized[0]) - 65
        second = ord(normalized[1]) - 65
        if first < 0 or first > 25 or second < 0 or second > 25:
            return ""
        hex1 = f"{0x1F1E6 + first:x}"
        hex2 = f"{0x1F1E6 + second:x}"
        return f"{hex1}-{hex2}.png"

    def _download_flag_pixmap(self, code: str, cache_dir: Path | None) -> QtGui.QPixmap:
        filename = self._twemoji_filename(code)
        if not filename:
            return QtGui.QPixmap()
        url = f"{TWEMOJI_BASE_URL}/{filename}"
        try:
            response = requests.get(url, timeout=(2, 4))
        except Exception:
            return QtGui.QPixmap()
        if response.status_code != 200:
            return QtGui.QPixmap()
        data = response.content
        if cache_dir:
            try:
                (cache_dir / f"{code}.png").write_bytes(data)
            except OSError:
                pass
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        return pixmap

    def _schedule_ip_lookup(self, ip_value: str) -> None:
        normalized = _normalize_ip(ip_value)
        if not normalized or normalized in self._ip_country_cache:
            return
        if normalized in self._ip_lookup_inflight:
            return
        if not _is_public_ip(normalized):
            self._ip_country_cache[normalized] = ""
            return
        worker = IpCountryWorker(normalized)
        worker.resolved.connect(self._handle_ip_country_resolved)
        worker.finished.connect(lambda ip=normalized: self._cleanup_ip_worker(ip))
        self._ip_lookup_inflight.add(normalized)
        self._ip_lookup_workers[normalized] = worker
        worker.start()

    def _cleanup_ip_worker(self, ip_value: str) -> None:
        self._ip_lookup_inflight.discard(ip_value)
        self._ip_lookup_workers.pop(ip_value, None)

    def _handle_ip_country_resolved(self, ip_value: str, country_code: str) -> None:
        normalized = _normalize_ip(ip_value)
        if not normalized:
            return
        self._ip_country_cache[normalized] = _normalize_country_code(country_code)
        self._render_current_clients()

    def _merge_clients(self, api_clients: List[Dict]) -> List[Dict]:
        if not api_clients:
            return []
        local_by_id = {client["id"]: client for client in self.clients}
        merged = []
        for api_client in api_clients:
            client_id = api_client.get("id", "")
            local = local_by_id.get(client_id, {})
            assigned_operator_id = api_client.get("assigned_operator_id")
            if assigned_operator_id is None:
                assigned_operator_id = local.get("assigned_operator_id", "")
            assigned_team_id = api_client.get("assigned_team_id")
            if assigned_team_id is None:
                assigned_team_id = local.get("assigned_team_id", "")
            client_config = api_client.get("client_config")
            if client_config is None:
                client_config = local.get("client_config")
            session_status = api_client.get("session_status")
            if session_status is None:
                session_status = local.get("session_status")
            created_at = api_client.get("created_at")
            if created_at is None:
                created_at = local.get("created_at")
            merged_client = {
                "id": client_id,
                "name": api_client.get("name", ""),
                "status": api_client.get("status", "disconnected"),
                "connected_time": api_client.get("connected_time", 0),
                "ip": api_client.get("ip", ""),
                "region": api_client.get("region", ""),
                "last_seen": api_client.get("last_seen"),
                "created_at": created_at,
                "connected": local.get("connected", False),
                "assigned_operator_id": assigned_operator_id or "",
                "assigned_team_id": assigned_team_id or "",
                "client_config": client_config,
                "session_status": session_status,
            }
            merged.append(merged_client)
        return merged

    def _start_client_fetch(self) -> None:
        if not self.api or self._fetch_in_progress:
            return
        self._fetch_in_progress = True
        worker = ClientFetchWorker(self.api)
        worker.fetched.connect(self._handle_client_fetch)
        worker.failed.connect(self._handle_client_fetch_error)
        worker.finished.connect(self._handle_client_fetch_finished)
        self._client_fetch_worker = worker
        worker.start()

    def _handle_client_fetch(self, api_clients: List[Dict]) -> None:
        """Обработка списка клиентов от API (исправленная версия)."""
        if not api_clients:
            self.clients = []
            self.refresh_view()
            return

        merged = self._merge_clients(api_clients)
        self.clients = merged
        self.settings.set("clients", self.clients)
        self.settings.save()
        if self._server_online is None:
            self._set_server_online(True)
        self.refresh_view()
        self.clients_refreshed.emit(self.clients)

        logger.info("Fetched %s clients from API", len(api_clients))

    def _handle_client_fetch_error(self, message: str) -> None:
        self._render_current_clients()

    def _handle_client_fetch_finished(self) -> None:
        self._fetch_in_progress = False
        self._client_fetch_worker = None

    def _set_server_online(self, online: bool) -> None:
        if self._server_online is online:
            return
        self._server_online = online
        self.server_status_changed.emit(online)
        if online:
            if hasattr(self, "clients_timer") and not self.clients_timer.isActive():
                self.clients_timer.start()
            self._start_client_fetch()
        else:
            if hasattr(self, "clients_timer"):
                self.clients_timer.stop()

    def _apply_ping_interval(self) -> None:
        interval = self._ping_base_interval_ms * (2 ** min(self._ping_failures, 3))
        interval = min(interval, self._ping_max_interval_ms)
        if self.ping_timer.interval() != interval:
            self.ping_timer.setInterval(interval)

    def _start_ping(self) -> None:
        if not self.api or self._ping_in_progress:
            return
        self._ping_in_progress = True
        worker = ServerPingWorker(self.api)
        worker.succeeded.connect(self._handle_ping_success)
        worker.failed.connect(self._handle_ping_error)
        worker.finished.connect(self._handle_ping_finished)
        self._ping_worker = worker
        worker.start()

    def _handle_ping_success(self, latency_ms: int) -> None:
        self._ping_failures = 0
        self._apply_ping_interval()
        self.ping_updated.emit(latency_ms)
        self._set_server_online(True)

    def _handle_ping_error(self, message: str) -> None:
        self._ping_failures += 1
        self._apply_ping_interval()
        self.ping_updated.emit(None)
        if self._ping_failures >= self._ping_failure_threshold:
            self._set_server_online(False)

    def _handle_ping_finished(self) -> None:
        self._ping_in_progress = False
        self._ping_worker = None

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

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source is self.table.viewport() and event.type() == QtCore.QEvent.Type.Resize:
            self.update_adaptive_columns()
        return super().eventFilter(source, event)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("main_title"))
        self.subtitle_label.setText(self.i18n.t("main_subtitle"))
        self.search_input.setPlaceholderText(self.i18n.t("main_search_placeholder"))
        self.refresh_button.setText(self.i18n.t("main_refresh_button"))
        self.activity_button.setText(self.i18n.t("log_title"))
        self._configure_columns()
        self.log_title.setText(self.i18n.t("log_title"))
        self.log_close.setText(self.i18n.t("storage_close"))
        if self.status_label is not None:
            self.status_label.setText(self.i18n.t("main_status_ready"))
        self.update_last_sync_label()
        self._render_current_clients()

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
        if self.last_sync_label is None:
            return
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
            self.render_clients(self._visible_clients(self.clients))
            return
        filtered = []
        for client in self._visible_clients(self.clients):
            tags_label = self._format_tag_labels(client.get("tags"))
            values = [
                client["name"],
                client["id"],
                self._format_work_status(client.get("work_status")),
                tags_label,
                self._resolve_region_display(client),
                client["ip"],
                self._resolve_team_name(client.get("assigned_team_id")),
                self._resolve_operator_name(client.get("assigned_operator_id")),
            ]
            if any(text in str(value).lower() for value in values):
                filtered.append(client)
        self.render_clients(filtered)

    def render_clients(self, clients: List[Dict]) -> None:
        if self._menu_open_count > 0:
            self._pending_render = True
            return
        self._pending_render = False
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        column_index = self._column_index()
        for client in clients:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 56)
            name_item = QtWidgets.QTableWidgetItem(client["name"])
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, client["id"])
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            name_item.setText("")
            work_status = self._normalize_work_status(client.get("work_status"))
            status_item = QtWidgets.QTableWidgetItem(self._format_work_status(work_status))
            status_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.apply_work_status_style(status_item, work_status)
            status_item.setFlags(status_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            ip_item = QtWidgets.QTableWidgetItem(client["ip"])
            region_item = QtWidgets.QTableWidgetItem(self._resolve_region_display(client))
            flags_codes = self._extract_flag_codes(client)
            if flags_codes:
                flag_pixmap = self._flag_pixmap(flags_codes[0])
                if flag_pixmap:
                    region_item.setIcon(QtGui.QIcon(flag_pixmap))
                    region_item.setToolTip(flags_codes[0])
            for item in (ip_item, region_item):
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column_index["name"], name_item)
            self.table.setCellWidget(row, column_index["name"], self.build_name_cell(client))
            self.table.setItem(row, column_index["work_status"], status_item)
            tags = client.get("tags") or []
            if tags:
                self.table.setCellWidget(row, column_index["tags"], self.build_tags_cell(tags))
            else:
                tags_item = QtWidgets.QTableWidgetItem("--")
                tags_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                tags_item.setFlags(tags_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column_index["tags"], tags_item)
            self.table.setItem(row, column_index["region"], region_item)
            self.table.setItem(row, column_index["ip"], ip_item)
            team_item = QtWidgets.QTableWidgetItem(
                self._resolve_team_name(client.get("assigned_team_id"))
            )
            team_item.setFlags(team_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column_index["team"], team_item)
            operator_item = QtWidgets.QTableWidgetItem(
                self._resolve_operator_name(client.get("assigned_operator_id"))
            )
            operator_item.setFlags(operator_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column_index["operator"], operator_item)
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
        self._render_current_clients()

    def refresh_view(self) -> None:
        self._render_current_clients()

    def poll_server_status(self) -> None:
        self._start_ping()

    def poll_clients(self) -> None:
        if self._server_online is False:
            return
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

        base_config = {
            "name": (3.2, 200),
            "work_status": (1.4, 130),
            "tags": (2.2, 180),
            "ip": (1.5, 140),
            "region": (1.7, 160),
            "team": (1.6, 150),
            "operator": (1.8, 160),
        }
        header_min = self._header_min_widths()
        config = {}
        for index, key in enumerate(self.column_keys):
            if key not in base_config:
                continue
            weight, min_w = base_config[key]
            min_w = max(min_w, header_min.get(index, 0))
            config[index] = (weight, min_w)

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

    def _header_min_widths(self) -> dict[int, int]:
        header = self.table.horizontalHeader()
        metrics = header.fontMetrics()
        padding = 28
        widths: dict[int, int] = {}
        for index in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(index)
            if not item:
                continue
            text = item.text()
            if not text:
                continue
            widths[index] = metrics.horizontalAdvance(text) + padding
        return widths

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
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        status_dot = QtWidgets.QLabel()
        status_dot.setObjectName("StatusDot")
        status_dot.setFixedSize(8, 8)
        connected = client.get("status") == "connected" or client.get("connected")
        status_dot.setProperty("status", "online" if connected else "offline")
        status_dot.setToolTip(
            self.i18n.t("top_status_online") if connected else self.i18n.t("top_status_offline")
        )
        text_stack = QtWidgets.QVBoxLayout()
        name_button = QtWidgets.QPushButton(client["name"])
        name_button.setObjectName("NameLink")
        name_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        name_button.setFlat(True)
        name_font = name_button.font()
        name_font.setPointSize(max(12, name_font.pointSize() + 1))
        name_font.setWeight(QtGui.QFont.Weight.DemiBold)
        name_button.setFont(name_font)
        name_button.clicked.connect(lambda _, cid=client["id"]: self.client_selected.emit(cid))
        id_label = QtWidgets.QLabel(client.get("id", ""))
        id_label.setObjectName("Muted")
        id_label.setStyleSheet("font-size: 12px;")
        text_stack.addWidget(name_button)
        text_stack.addWidget(id_label)
        button = QtWidgets.QToolButton()
        button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        button.setAutoRaise(True)
        edit_icon = load_icon("rename", self.theme.name)
        if edit_icon.isNull():
            button.setText(self.i18n.t("button_edit_name"))
        else:
            button.setIcon(edit_icon)
            button.setIconSize(QtCore.QSize(16, 16))
        button.setToolTip(self.i18n.t("button_edit_name"))
        button.clicked.connect(lambda _, cid=client["id"]: self.edit_client_name(cid))
        layout.addWidget(status_dot, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(text_stack, 1)
        layout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        return container

    def _emit_client_selected(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if not item:
            return
        client_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if client_id:
            self.client_selected.emit(client_id)

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
            "border-radius: 12px;"
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
        menu.aboutToShow.connect(lambda: self._set_menu_active(True))
        menu.aboutToHide.connect(lambda: self._set_menu_active(False))
        cookies_menu = menu.addMenu(self.i18n.t("menu_cookies_title"))
        cookie_actions = [("all", self.i18n.t("menu_cookies_all"))]
        client = next((c for c in self.clients if c.get("id") == client_id), None)
        cookie_actions.extend(
            browser_choices_from_config(client.get("client_config") if isinstance(client, dict) else None)
        )
        for key, label in cookie_actions:
            action = cookies_menu.addAction(label)
            action.triggered.connect(
                lambda _, cid=client_id, browser=key: self.extra_action_requested.emit(
                    cid, f"cookies:{browser}"
                )
            )
        menu.addSeparator()
        proxy_action = menu.addAction(self.i18n.t("menu_proxy_download"))
        proxy_action.triggered.connect(
            lambda _, cid=client_id: self.extra_action_requested.emit(cid, "proxy")
        )
        menu.addSeparator()
        placeholder = menu.addAction(self.i18n.t("menu_more_placeholder"))
        placeholder.setEnabled(False)
        button.setMenu(menu)
        return button

    def edit_client_name(self, client_id: str) -> None:
        client = next((c for c in self.clients if c["id"] == client_id), None)
        if client is None:
            return
        dialog = QtWidgets.QInputDialog(self)
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
        self._render_current_clients()

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
            "border-radius: 10px;"
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
        self._render_current_clients()
