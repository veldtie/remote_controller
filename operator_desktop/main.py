import sys

from PyQt6 import QtWidgets

from .core.paths import resolve_settings_path
from .ui.window import MainWindow


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(resolve_settings_path())
    window.apply_font(window.i18n.language())
    window.show()
    return app.exec()
