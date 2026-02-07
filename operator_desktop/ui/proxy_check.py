from __future__ import annotations

import time
from PyQt6 import QtCore

from ..core.proxy_check import check_socks5_proxy


class ProxyCheckWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(str, bool, str, int)

    def __init__(self, client_id: str, host: str, port: int | str, timeout: float = 4.0):
        super().__init__()
        self.client_id = client_id
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self) -> None:
        started = time.monotonic()
        ok, detail = check_socks5_proxy(self.host, self.port, self.timeout)
        latency_ms = int((time.monotonic() - started) * 1000)
        self.finished.emit(self.client_id, ok, detail, latency_ms)
