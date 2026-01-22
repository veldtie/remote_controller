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

        glow = QtGui.QColor(self.theme.colors["glow"])
        glow.setAlpha(60)
        painter.setBrush(glow)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.2), int(rect.height() * 0.1)), 220, 220)

        accent = QtGui.QColor(self.theme.colors["accent"])
        accent.setAlpha(40)
        painter.setBrush(accent)
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.85), int(rect.height() * 0.2)), 180, 180)

        painter.setBrush(QtGui.QColor(self.theme.colors["accent_soft"]))
        painter.drawEllipse(QtCore.QPoint(int(rect.width() * 0.7), int(rect.height() * 0.9)), 260, 260)

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
