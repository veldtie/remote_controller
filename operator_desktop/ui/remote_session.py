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
<<<<<<< HEAD
    mode: str = "manage",
    storage_only: bool = False,
=======
    region: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    flags: list[str] | None = None,
>>>>>>> 45ab282d56f3c92e79484b2ae578ee91c3965eb3
) -> QtCore.QUrl:
    if "://" not in base_url:
        base_url = f"http://{base_url}"
    parsed = urlsplit(base_url)
    query = {
        "session_id": session_id,
        "autoconnect": "1",
        "mode": mode,
        "desktop": "1",
        "server": base_url,
        "v": uuid.uuid4().hex,
    }
    if open_storage:
        query["storage"] = "1"
    if storage_only:
        query["storage_only"] = "1"
    if token:
        query["token"] = token
    if region:
        query["region"] = region
    if country:
        query["country"] = country
    if country_code:
        query["country_code"] = country_code
    if flags:
        query["flags"] = ",".join([str(code) for code in flags if str(code).strip()])
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
<<<<<<< HEAD
        manage_mode: bool = True,
        storage_only: bool = False,
        show_window: bool = True,
=======
        region: str | None = None,
        country: str | None = None,
        country_code: str | None = None,
        flags: list[str] | None = None,
>>>>>>> 45ab282d56f3c92e79484b2ae578ee91c3965eb3
        parent=None,
    ):
        super().__init__(parent)
        if QWebEngineView is None:
            raise RuntimeError("PyQt6-WebEngine is not available")
        self.session_id = session_id
        self.server_url = server_url
        self.token = token or ""
        self.region = region or ""
        self.country = country or ""
        self.country_code = country_code or ""
        self.flags = list(flags or [])
        self._open_storage_on_load = open_storage
        self._manage_mode = manage_mode
        self._storage_only = storage_only
        self._page_ready = False
        self._session_chip: QtWidgets.QLabel | None = None
        self._region_chip: QtWidgets.QLabel | None = None
        self._flags_chip: QtWidgets.QLabel | None = None
        self._pending_cookie_requests: list[dict[str, object]] = []
        self._pending_proxy_requests: list[dict[str, object]] = []
        self._download_override_dir: str | None = None
        self._download_override_name: str | None = None
        self._last_download_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DownloadLocation
        )
        self.setWindowTitle(f"RemDesk - {session_id}")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        if not show_window:
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.resize(1200, 720)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._window_controls = self._build_window_controls()
        layout.addWidget(self._window_controls, 0)
        self._refresh_top_info()

        self.view = QWebEngineView()
        if QWebEngineSettings is not None:
            settings = self.view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            if hasattr(QWebEngineSettings.WebAttribute, "FullScreenSupportEnabled"):
                settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            if hasattr(QWebEngineSettings.WebAttribute, "PointerLockEnabled"):
                settings.setAttribute(QWebEngineSettings.WebAttribute.PointerLockEnabled, True)
        self.view.page().profile().downloadRequested.connect(self._handle_download_request)
        if hasattr(self.view.page(), "fullScreenRequested"):
            self.view.page().fullScreenRequested.connect(self._handle_fullscreen_request)
        self.view.loadFinished.connect(self._handle_load_finished)
        self.view.setUrl(url)
        layout.addWidget(self.view, 1)
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

    def request_proxy_export(
        self,
        client_id: str | None = None,
        filename: str | None = None,
        download_dir: str | None = None,
    ) -> None:
        if download_dir:
            self._download_override_dir = download_dir
            self._download_override_name = filename
        self._pending_proxy_requests.append(
            {"clientId": client_id or self.session_id, "filename": filename}
        )
        self._flush_proxy_requests()

    def apply_context(
        self,
        server_url: str | None = None,
        token: str | None = None,
        session_id: str | None = None,
        region: str | None = None,
        country: str | None = None,
        country_code: str | None = None,
        flags: list[str] | None = None,
        auto_connect: bool = True,
        open_storage: bool = False,
        manage_mode: bool | None = None,
        storage_only: bool | None = None,
    ) -> None:
        if server_url is not None:
            self.server_url = server_url
        if token is not None:
            self.token = token
        if session_id is not None:
            self.session_id = session_id
<<<<<<< HEAD
        if manage_mode is not None:
            self._manage_mode = manage_mode
        if storage_only is not None:
            self._storage_only = storage_only
        self._apply_desktop_overrides(
            auto_connect=auto_connect,
            open_storage=open_storage,
            manage_mode=self._manage_mode,
            storage_only=self._storage_only,
        )
=======
        if region is not None:
            self.region = region
        if country is not None:
            self.country = country
        if country_code is not None:
            self.country_code = country_code
        if flags is not None:
            self.flags = list(flags)
        self._refresh_top_info()
        self._apply_desktop_overrides(auto_connect=auto_connect, open_storage=open_storage)
>>>>>>> 45ab282d56f3c92e79484b2ae578ee91c3965eb3

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
        self._apply_desktop_overrides(
            auto_connect=True,
            open_storage=self._open_storage_on_load,
            manage_mode=self._manage_mode,
            storage_only=self._storage_only,
        )
        self._open_storage_on_load = False
        self._flush_cookie_requests()
        self._flush_proxy_requests()

    def _fallback_apply(self) -> None:
        if not self.view:
            return
        self._page_ready = True
        self._apply_desktop_overrides(
            auto_connect=True,
            open_storage=self._open_storage_on_load,
            manage_mode=self._manage_mode,
            storage_only=self._storage_only,
        )
        self._open_storage_on_load = False
        self._flush_cookie_requests()
        self._flush_proxy_requests()

    def _build_window_controls(self) -> QtWidgets.QFrame:
        bar = QtWidgets.QFrame(self)
        bar.setObjectName("SessionControlBar")
        bar.setStyleSheet(
            "QFrame#SessionControlBar {"
            "background: rgba(12, 14, 18, 0.92);"
            "border-bottom: 1px solid rgba(255, 255, 255, 0.08);"
            "}"
        )
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 8, 10, 8)
        bar_layout.setSpacing(10)

        bar_layout.addStretch()

        controls = QtWidgets.QFrame(bar)
        controls.setObjectName("SessionControls")
        controls.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        controls.setStyleSheet(
            "QFrame#SessionControls {"
            "background: rgba(12, 16, 22, 0.82);"
            "border: 1px solid rgba(255, 255, 255, 0.14);"
            "border-radius: 10px;"
            "}"
            "QToolButton {"
            "color: #f5f2ea;"
            "border: none;"
            "padding: 4px;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255, 255, 255, 0.12);"
            "border-radius: 8px;"
            "}"
        )
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.setSpacing(6)

        self._minimize_button = QtWidgets.QToolButton(controls)
        self._minimize_button.setAutoRaise(True)
        self._minimize_button.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarMinButton)
        )
        self._minimize_button.setToolTip("Minimize")
        self._minimize_button.clicked.connect(self.showMinimized)

        self._fullscreen_button = QtWidgets.QToolButton(controls)
        self._fullscreen_button.setAutoRaise(True)
        self._fullscreen_button.setToolTip("Fullscreen")
        self._fullscreen_button.clicked.connect(self._toggle_fullscreen)

        controls_layout.addWidget(self._minimize_button)
        controls_layout.addWidget(self._fullscreen_button)
        self._update_fullscreen_button()
        bar_layout.addWidget(controls, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        return bar

    def _refresh_top_info(self) -> None:
        return

    def _format_flags(self) -> str:
        codes = [code for code in (self.flags or []) if str(code).strip()]
        if not codes and self.country_code:
            codes = [self.country_code]
        if not codes:
            return "--"
        rendered = []
        for code in codes[:6]:
            rendered.append(self._flag_from_code(str(code)))
        return " ".join(rendered)

    @staticmethod
    def _flag_from_code(code: str) -> str:
        normalized = (code or "").strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            return normalized or "--"
        base = 0x1F1E6
        first = ord(normalized[0]) - 65
        second = ord(normalized[1]) - 65
        if first < 0 or first > 25 or second < 0 or second > 25:
            return normalized
        return chr(base + first) + chr(base + second)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._update_fullscreen_button()

    def _update_fullscreen_button(self) -> None:
        if not hasattr(self, "_fullscreen_button"):
            return
        if self.isFullScreen():
            icon = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_TitleBarNormalButton
            )
            tooltip = "Exit fullscreen"
        else:
            icon = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_TitleBarMaxButton
            )
            tooltip = "Fullscreen"
        self._fullscreen_button.setIcon(icon)
        self._fullscreen_button.setToolTip(tooltip)

    def _handle_fullscreen_request(self, request) -> None:
        request.accept()
        if request.toggleOn():
            self.showFullScreen()
        else:
            self.showNormal()
        self._update_fullscreen_button()

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

    def _flush_proxy_requests(self) -> None:
        if not self.view or not self._page_ready or not self._pending_proxy_requests:
            return
        pending = self._pending_proxy_requests[:]
        self._pending_proxy_requests.clear()
        for entry in pending:
            payload = json.dumps(entry)
            script = f"""
(() => {{
  const req = {payload};
  if (window.remdeskDownloadProxy) {{
    window.remdeskDownloadProxy(req.clientId || null, req.filename || null);
    return;
  }}
  window.__remdeskProxyQueue = window.__remdeskProxyQueue || [];
  window.__remdeskProxyQueue.push(req);
}})();
"""
            self.view.page().runJavaScript(script)

    def _apply_desktop_overrides(
        self,
        auto_connect: bool,
        open_storage: bool,
        manage_mode: bool,
        storage_only: bool,
    ) -> None:
        if not self.view:
            return
        payload = json.dumps(
            {
                "serverUrl": self.server_url,
                "sessionId": self.session_id,
                "token": self.token,
                "region": self.region,
                "country": self.country,
                "country_code": self.country_code,
                "flags": self.flags,
                "autoConnect": auto_connect,
                "openStorage": open_storage,
                "desktop": True,
                "manage": manage_mode,
                "storageOnly": storage_only,
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
    if (data.manage === true) {{
      const toggle = document.getElementById("interactionToggle");
      if (toggle && !toggle.checked) {{
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change", {{ bubbles: true }}));
      }}
    }} else if (data.manage === false) {{
      const toggle = document.getElementById("interactionToggle");
      if (toggle && toggle.checked) {{
        toggle.checked = false;
        toggle.dispatchEvent(new Event("change", {{ bubbles: true }}));
      }}
    }}
    if (data.storageOnly) {{
      document.body.classList.add("storage-only");
    }} else {{
      document.body.classList.remove("storage-only");
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

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self._update_fullscreen_button()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit(self.session_id)
        super().closeEvent(event)
