import re

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ..common import GlassFrame


class InstructionsPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n):
        super().__init__()
        self.i18n = i18n
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        self.primary_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.primary_card.setObjectName("SettingsCard")
        primary_layout = QtWidgets.QVBoxLayout(self.primary_card)
        primary_layout.setContentsMargins(16, 16, 16, 16)
        self.primary_instructions = QtWidgets.QTextBrowser()
        self.primary_instructions.setOpenExternalLinks(True)
        self.primary_instructions.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.primary_instructions.setStyleSheet("background: transparent; font-size: 14px;")
        primary_layout.addWidget(self.primary_instructions, 1)
        layout.addWidget(self.primary_card, 1)

        self.secondary_card = GlassFrame(radius=18, tone="card", tint_alpha=170, border_alpha=70)
        self.secondary_card.setObjectName("SettingsCard")
        secondary_layout = QtWidgets.QVBoxLayout(self.secondary_card)
        secondary_layout.setContentsMargins(16, 16, 16, 16)
        self.secondary_instructions = QtWidgets.QTextBrowser()
        self.secondary_instructions.setOpenExternalLinks(True)
        self.secondary_instructions.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.secondary_instructions.setStyleSheet("background: transparent; font-size: 14px;")
        secondary_layout.addWidget(self.secondary_instructions, 1)
        layout.addWidget(self.secondary_card, 1)
        self.apply_translations()

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("instructions_title"))
        self.subtitle_label.setText(self.i18n.t("instructions_subtitle"))
        sections = self._split_sections(self.i18n.t("instructions_body"))
        self.primary_instructions.setHtml(sections[0] if sections else "")
        if len(sections) > 1:
            self.secondary_instructions.setHtml(sections[1])
            self.secondary_card.setVisible(True)
        else:
            self.secondary_instructions.setHtml("")
            self.secondary_card.setVisible(False)

    @staticmethod
    def _split_sections(body: str) -> list[str]:
        if not body:
            return []
        matches = list(re.finditer(r"<h3>.*?</h3>", body, flags=re.IGNORECASE | re.DOTALL))
        if len(matches) < 2:
            return [body.strip()]
        sections: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            chunk = body[start:end].strip()
            if chunk:
                sections.append(chunk)
        return sections
