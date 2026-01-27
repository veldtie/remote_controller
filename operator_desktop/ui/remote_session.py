from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover - optional dependency
    QWebEngineView = None


def webengine_available() -> bool:
    return QWebEngineView is not None


def build_session_url(base_url: str, session_id: str, token: str | None) -> QtCore.QUrl:
    parsed = urlsplit(base_url)
    query = {"session_id": session_id, "autoconnect": "1", "mode": "view", "desktop": "1"}
    if token:
        query["token"] = token
    url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            urlencode(query),
            "",
        )
    )
    return QtCore.QUrl(url)


class RemoteSessionDialog(QtWidgets.QDialog):
    closed = QtCore.pyqtSignal(str)

    def __init__(self, session_id: str, url: QtCore.QUrl, parent=None):
        super().__init__(parent)
        if QWebEngineView is None:
            raise RuntimeError("PyQt6-WebEngine is not available")
        self.session_id = session_id
        self.setWindowTitle(f"RemDesk - {session_id}")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(1200, 720)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView()
        self.view.setUrl(url)
        layout.addWidget(self.view)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit(self.session_id)
        super().closeEvent(event)
