import os
import sys


def _append_chromium_flag(flag: str) -> None:
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    if flag in flags.split():
        return
    combined = f"{flags} {flag}".strip() if flags else flag
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = combined


# Apply Chromium flags before QtWebEngine imports (prevents mDNS host candidates).
_append_chromium_flag("--disable-direct-composition")
_append_chromium_flag("--disable-features=WebRtcHideLocalIpsWithMdns")

from PyQt6 import QtWidgets  # noqa: E402

from .core.paths import resolve_settings_path  # noqa: E402
from .ui.window import MainWindow  # noqa: E402


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(resolve_settings_path())
    window.apply_font(window.i18n.language())
    window.show()
    return app.exec()
