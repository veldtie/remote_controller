from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.theme import Theme

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class BackgroundWidget(QtWidgets.QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        gradient = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.0, QtGui.QColor(self.theme.colors["bg_start"]))
        gradient.setColorAt(1.0, QtGui.QColor(self.theme.colors["bg_end"]))
        painter.fillRect(rect, gradient)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        glow = QtGui.QColor(self.theme.colors["accent"])
        glow.setAlpha(28)
        painter.setBrush(glow)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.2), int(rect.height() * 0.12)),
            240,
            240,
        )

        glow.setAlpha(20)
        painter.setBrush(glow)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.82), int(rect.height() * 0.1)),
            220,
            220,
        )

        glow.setAlpha(14)
        painter.setBrush(glow)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.68), int(rect.height() * 0.8)),
            320,
            320,
        )

        painter.end()


def animate_widget(widget: QtWidgets.QWidget) -> None:
    if widget.graphicsEffect() is not None:
        widget.setGraphicsEffect(None)
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(260)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def make_button(text: str, variant: str = "ghost") -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
    return button


def load_icon(name: str, theme_name: str | None = None) -> QtGui.QIcon:
    variants = []
    if theme_name:
        variants.append(f"{name}_{theme_name}")
    variants.append(name)
    for base in variants:
        for ext in (".svg", ".png", ".ico"):
            path = ICON_DIR / f"{base}{ext}"
            if path.exists():
                return QtGui.QIcon(str(path))
    return QtGui.QIcon()
