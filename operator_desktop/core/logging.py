from datetime import datetime
from typing import List

from PyQt6 import QtCore

from .i18n import I18n
from .settings import SettingsStore


class EventLogger(QtCore.QObject):
    updated = QtCore.pyqtSignal()

    def __init__(self, settings: SettingsStore, i18n: I18n):
        super().__init__()
        self.settings = settings
        self.i18n = i18n

    def log(self, key: str, **kwargs) -> None:
        message = self.i18n.t(key, **kwargs)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp}  {message}"
        logs = self.settings.get("session_logs", [])
        logs.append(entry)
        self.settings.set("session_logs", logs[-200:])
        self.settings.save()
        self.updated.emit()

    def entries(self) -> List[str]:
        return list(self.settings.get("session_logs", []))
