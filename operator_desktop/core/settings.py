import json
from pathlib import Path
from typing import Dict

from .data import DEFAULT_SETTINGS, deep_copy


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = deep_copy(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._merge(self.data, raw)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _merge(self, target: Dict, source: Dict) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge(target[key], value)
            else:
                target[key] = value

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def clear_user_data(self) -> None:
        self.data["remember_me"] = False
        self.data["account_id"] = ""
        self.data["operator_name"] = ""
        self.data["operator_team_id"] = ""
        self.data["session_token"] = ""
        self.data["recent_account_ids"] = []
        self.data["session_logs"] = []
        self.data["role"] = "operator"
        self.save()
