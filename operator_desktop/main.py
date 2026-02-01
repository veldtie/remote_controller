import os
import sys

from PyQt6 import QtWidgets

from .core.paths import resolve_settings_path
from .ui.window import MainWindow


def _append_chromium_flag(flag: str) -> None:
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    if flag in flags.split():
        return
    combined = f"{flags} {flag}".strip() if flags else flag
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = combined


def main() -> int:
    _append_chromium_flag("--disable-direct-composition")
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(resolve_settings_path())
    window.apply_font(window.i18n.language())
    window.show()
    return app.exec()
