from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit

import json
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover - optional dependency
    QWebEngineView = None
try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except Exception:  # pragma: no cover - optional dependency
    QWebEngineSettings = None


def webengine_available() -> bool:
    return QWebEngineView is not None


def build_session_url(
    base_url: str,
    session_id: str,
    token: str | None,
    open_storage: bool = False,
) -> QtCore.QUrl:
    if "://" not in base_url:
        base_url = f"http://{base_url}"
    parsed = urlsplit(base_url)
    query = {
        "session_id": session_id,
        "autoconnect": "1",
        "mode": "manage",
        "desktop": "1",
        "server": base_url,
        "v": uuid.uuid4().hex,
    }
    if open_storage:
        query["storage"] = "1"
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

    def __init__(
        self,
        session_id: str,
        url: QtCore.QUrl,
        server_url: str,
        token: str | None,
        open_storage: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        if QWebEngineView is None:
            raise RuntimeError("PyQt6-WebEngine is not available")
        self.session_id = session_id
        self.server_url = server_url
        self.token = token or ""
        self._open_storage_on_load = open_storage
        self._page_ready = False
        self._pending_cookie_requests: list[dict[str, object]] = []
        self._download_override_dir: str | None = None
        self._download_override_name: str | None = None
        self._last_download_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DownloadLocation
        )
        self.setWindowTitle(f"RemDesk - {session_id}")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(1200, 720)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView()
        if QWebEngineSettings is not None:
            settings = self.view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        self.view.page().profile().downloadRequested.connect(self._handle_download_request)
        self.view.loadFinished.connect(self._handle_load_finished)
        self.view.setUrl(url)
        layout.addWidget(self.view)
        QtCore.QTimer.singleShot(800, self._fallback_apply)

    def open_storage_drawer(self) -> None:
        if not self.view:
            return
        self.apply_context(auto_connect=True, open_storage=True)

    def request_cookie_export(
        self,
        browsers: list[str] | None,
        filename: str | None = None,
        download_dir: str | None = None,
    ) -> None:
        if download_dir:
            self._download_override_dir = download_dir
            self._download_override_name = filename
        self._pending_cookie_requests.append(
            {"browsers": list(browsers or []), "filename": filename}
        )
        self._flush_cookie_requests()

    def apply_context(
        self,
        server_url: str | None = None,
        token: str | None = None,
        session_id: str | None = None,
        auto_connect: bool = True,
        open_storage: bool = False,
    ) -> None:
        if server_url is not None:
            self.server_url = server_url
        if token is not None:
            self.token = token
        if session_id is not None:
            self.session_id = session_id
        self._apply_desktop_overrides(auto_connect=auto_connect, open_storage=open_storage)

    def _handle_download_request(self, download) -> None:
        if download.isFinished():
            return
        filename = download.suggestedFileName() or "download"
        directory = None
        if self._download_override_dir and (
            self._download_override_name is None
            or self._download_override_name == filename
        ):
            directory = self._download_override_dir
            self._download_override_dir = None
            self._download_override_name = None
        is_cookie_download = filename.lower().startswith("cookies_")
        if not directory and is_cookie_download:
            start_dir = self._last_download_dir or ""
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Select download folder", start_dir
            )
            if not folder:
                if hasattr(download, "cancel"):
                    download.cancel()
                return
            directory = folder
        if not directory:
            directory = self._last_download_dir or QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.DownloadLocation
            )
        self._last_download_dir = directory
        download.setDownloadDirectory(directory)
        download.setDownloadFileName(filename)
        download.accept()

    def _handle_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        self._page_ready = True
        self._apply_desktop_overrides(auto_connect=True, open_storage=self._open_storage_on_load)
        self._open_storage_on_load = False
        self._flush_cookie_requests()

    def _fallback_apply(self) -> None:
        if not self.view:
            return
        self._page_ready = True
        self._apply_desktop_overrides(auto_connect=True, open_storage=self._open_storage_on_load)
        self._open_storage_on_load = False
        self._flush_cookie_requests()

    def _flush_cookie_requests(self) -> None:
        if not self.view or not self._page_ready or not self._pending_cookie_requests:
            return
        pending = self._pending_cookie_requests[:]
        self._pending_cookie_requests.clear()
        for entry in pending:
            payload = json.dumps(entry)
            script = f"""
(() => {{
  const req = {payload};
  if (window.remdeskDownloadCookies) {{
    window.remdeskDownloadCookies(req.browsers || [], req.filename || null);
    return;
  }}
  window.__remdeskCookieQueue = window.__remdeskCookieQueue || [];
  window.__remdeskCookieQueue.push(req);
}})();
"""
            self.view.page().runJavaScript(script)

    def _apply_desktop_overrides(self, auto_connect: bool, open_storage: bool) -> None:
        if not self.view:
            return
        payload = json.dumps(
            {
                "serverUrl": self.server_url,
                "sessionId": self.session_id,
                "token": self.token,
                "autoConnect": auto_connect,
                "openStorage": open_storage,
                "desktop": True,
                "manage": True,
            }
        )
        script = f"""
(() => {{
  const data = {payload};
  const applyInputs = () => {{
    const setValue = (id, value) => {{
      const el = document.getElementById(id);
      if (!el || value === undefined || value === null) return;
      el.value = value;
      el.dispatchEvent(new Event("input", {{ bubbles: true }}));
      el.dispatchEvent(new Event("change", {{ bubbles: true }}));
    }};
    setValue("serverUrl", data.serverUrl || "");
    setValue("sessionId", data.sessionId || "");
    setValue("authToken", data.token || "");
    if (data.manage) {{
      const toggle = document.getElementById("interactionToggle");
      if (toggle && !toggle.checked) {{
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change", {{ bubbles: true }}));
      }}
    }}
    if (data.openStorage) {{
      const storageButton = document.getElementById("storageToggle");
      if (storageButton) {{
        storageButton.click();
      }}
    }}
    if (data.autoConnect) {{
      const connectButton = document.getElementById("connectButton");
      if (connectButton) {{
        connectButton.click();
      }}
    }}
  }};
  window.__remdeskBootstrapPayload = data;
  if (window.remdeskBootstrap) {{
    window.remdeskBootstrap(data);
    return;
  }}
  let tries = 0;
  const timer = setInterval(() => {{
    tries += 1;
    if (window.remdeskBootstrap) {{
      clearInterval(timer);
      window.remdeskBootstrap(data);
    }} else if (window.__remdeskReady) {{
      clearInterval(timer);
      applyInputs();
    }} else if (tries > 40) {{
      clearInterval(timer);
      applyInputs();
    }}
  }}, 100);
}})();
"""
        self.view.page().runJavaScript(script)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit(self.session_id)
        super().closeEvent(event)
