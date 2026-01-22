from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n


class InstructionsPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n):
        super().__init__()
        self.i18n = i18n
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        self.instructions = QtWidgets.QTextBrowser()
        self.instructions.setOpenExternalLinks(True)
        layout.addWidget(self.instructions, 1)
        self.apply_translations()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("instructions_title"))
        self.subtitle_label.setText(self.i18n.t("instructions_subtitle"))
        self.instructions.setHtml(self.i18n.t("instructions_body"))
