from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ..core.theme import Theme

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class BackgroundWidget(QtWidgets.QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._blur_enabled = True
        self._blur_radius = 28
        self._blur_downscale = 0.5
        self._blur_cache_pixmap: QtGui.QPixmap | None = None
        self._blur_cache_key: tuple[int, int, str, float] | None = None
        self._blur_timer = QtCore.QTimer(self)
        self._blur_timer.setSingleShot(True)
        self._blur_timer.setInterval(120)
        self._blur_timer.timeout.connect(self._build_blur_cache)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._blur_cache_pixmap = None
        self._blur_cache_key = None
        self.update()

    def set_blur_enabled(self, enabled: bool) -> None:
        self._blur_enabled = enabled
        self._blur_cache_pixmap = None
        self._blur_cache_key = None
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._blur_enabled:
            self._blur_timer.start()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._paint_background(painter, self.rect())

        painter.end()

    def _paint_background(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        gradient = QtGui.QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0.0, QtGui.QColor(self.theme.colors["bg_start"]))
        gradient.setColorAt(1.0, QtGui.QColor(self.theme.colors["bg_end"]))
        painter.fillRect(rect, gradient)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        accent = QtGui.QColor(self.theme.colors["accent"])
        accent_soft = QtGui.QColor(self.theme.colors.get("accent_2", self.theme.colors["accent"]))

        glow_1 = QtGui.QRadialGradient(
            QtCore.QPointF(rect.width() * 0.12, rect.height() * -0.10),
            max(rect.width(), rect.height()) * 0.48,
        )
        glow_1.setColorAt(0.0, QtGui.QColor(accent.red(), accent.green(), accent.blue(), 70))
        glow_1.setColorAt(0.75, QtGui.QColor(accent.red(), accent.green(), accent.blue(), 12))
        glow_1.setColorAt(1.0, QtCore.Qt.GlobalColor.transparent)
        painter.setBrush(glow_1)
        painter.drawRect(rect)

        glow_2 = QtGui.QRadialGradient(
            QtCore.QPointF(rect.width() * 0.88, rect.height() * 0.02),
            max(rect.width(), rect.height()) * 0.44,
        )
        glow_2.setColorAt(
            0.0, QtGui.QColor(accent_soft.red(), accent_soft.green(), accent_soft.blue(), 56)
        )
        glow_2.setColorAt(
            0.7, QtGui.QColor(accent_soft.red(), accent_soft.green(), accent_soft.blue(), 12)
        )
        glow_2.setColorAt(1.0, QtCore.Qt.GlobalColor.transparent)
        painter.setBrush(glow_2)
        painter.drawRect(rect)

        glow_3 = QtGui.QRadialGradient(
            QtCore.QPointF(rect.width() * 0.45, rect.height() * 1.02),
            max(rect.width(), rect.height()) * 0.42,
        )
        glow_3.setColorAt(
            0.0, QtGui.QColor(accent.red(), accent.green(), accent.blue(), 38)
        )
        glow_3.setColorAt(
            0.72, QtGui.QColor(accent.red(), accent.green(), accent.blue(), 8)
        )
        glow_3.setColorAt(1.0, QtCore.Qt.GlobalColor.transparent)
        painter.setBrush(glow_3)
        painter.drawRect(rect)

        sheen = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
        sheen.setColorAt(0.0, QtGui.QColor(255, 255, 255, 22))
        sheen.setColorAt(0.33, QtCore.Qt.GlobalColor.transparent)
        sheen.setColorAt(0.72, QtGui.QColor(accent.red(), accent.green(), accent.blue(), 24))
        sheen.setColorAt(1.0, QtCore.Qt.GlobalColor.transparent)
        painter.setBrush(sheen)
        painter.drawRect(rect)

    def _build_blur_cache(self) -> None:
        if not self._blur_enabled:
            self._blur_cache_pixmap = None
            self._blur_cache_key = None
            return
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        key = (size.width(), size.height(), self.theme.name, self._blur_downscale, self._blur_radius)
        if self._blur_cache_key == key and self._blur_cache_pixmap is not None:
            return
        scale = self._blur_downscale
        if max(size.width(), size.height()) >= 2000:
            scale = min(scale, 0.4)
        scaled_w = max(1, int(size.width() * scale))
        scaled_h = max(1, int(size.height() * scale))
        image = QtGui.QImage(
            QtCore.QSize(scaled_w, scaled_h),
            QtGui.QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._paint_background(painter, QtCore.QRect(0, 0, scaled_w, scaled_h))
        painter.end()
        blurred = self._blur_image(image, self._blur_radius * scale)
        pixmap = QtGui.QPixmap.fromImage(blurred)
        self._blur_cache_pixmap = pixmap.scaled(
            size,
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._blur_cache_key = key

    def blurred_pixmap(self) -> QtGui.QPixmap | None:
        if not self._blur_enabled:
            return None
        if self._blur_cache_pixmap is None:
            self._build_blur_cache()
        return self._blur_cache_pixmap

    @staticmethod
    def _blur_image(image: QtGui.QImage, radius: float) -> QtGui.QImage:
        if radius <= 0:
            return image
        scene = QtWidgets.QGraphicsScene()
        item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        blur = QtWidgets.QGraphicsBlurEffect()
        blur.setBlurRadius(radius)
        blur.setBlurHints(QtWidgets.QGraphicsBlurEffect.BlurHint.PerformanceHint)
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        result = QtGui.QImage(
            image.size(),
            QtGui.QImage.Format.Format_ARGB32_Premultiplied,
        )
        result.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(result)
        scene.render(painter, QtCore.QRectF(result.rect()), QtCore.QRectF(image.rect()))
        painter.end()
        return result


def _qcolor_from_token(value: str) -> QtGui.QColor:
    token = str(value or "").strip()
    if token.startswith("rgba") and "(" in token and ")" in token:
        payload = token[token.find("(") + 1 : token.find(")")]
        parts = [p.strip() for p in payload.split(",") if p.strip()]
        if len(parts) >= 4:
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
            alpha_raw = float(parts[3])
            alpha = int(alpha_raw * 255) if alpha_raw <= 1 else int(alpha_raw)
            return QtGui.QColor(r, g, b, max(0, min(255, alpha)))
    return QtGui.QColor(token)


class GlassFrame(QtWidgets.QFrame):
    def __init__(
        self,
        theme: Theme | None = None,
        radius: int = 18,
        tone: str = "card",
        tint_alpha: int | None = None,
        border_alpha: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._theme = theme
        self._radius = radius
        self._tone = tone
        self._tint_alpha = tint_alpha
        self._border_alpha = border_alpha
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = max(0, self._radius)
        path = QtGui.QPainterPath()
        rectf = QtCore.QRectF(rect)
        rectf.adjust(0.5, 0.5, -0.5, -0.5)
        path.addRoundedRect(rectf, radius, radius)
        painter.setClipPath(path)

        background = self._find_background()
        pixmap = background.blurred_pixmap() if background else None
        if pixmap:
            origin = self.mapTo(background, QtCore.QPoint(0, 0))
            source = QtCore.QRect(origin, rect.size())
            painter.drawPixmap(rect, pixmap, source)

        tint = self._resolve_tint_color()
        painter.fillPath(path, tint)
        painter.setClipping(False)

        pen = QtGui.QPen(self._resolve_border_color())
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    def _resolve_tint_color(self) -> QtGui.QColor:
        theme = self._resolve_theme()
        token = theme.colors.get(self._tone, theme.colors.get("card", "#10141b"))
        color = _qcolor_from_token(token)
        if self._tint_alpha is not None:
            color.setAlpha(self._tint_alpha)
        return color

    def _resolve_border_color(self) -> QtGui.QColor:
        theme = self._resolve_theme()
        token = theme.colors.get("border", "rgba(255,255,255,0.12)")
        color = _qcolor_from_token(token)
        if self._border_alpha is not None:
            color.setAlpha(self._border_alpha)
        return color

    def _resolve_theme(self) -> Theme:
        if self._theme is not None:
            return self._theme
        window = self.window()
        if window and hasattr(window, "theme"):
            theme = getattr(window, "theme")
            if isinstance(theme, Theme):
                return theme
        background = self._find_background()
        if background:
            return background.theme
        return Theme("fallback", {"card": "#10141b", "border": "rgba(255,255,255,0.12)"})

    def _find_background(self) -> BackgroundWidget | None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, BackgroundWidget):
                return parent
            parent = parent.parentWidget()
        return None

def animate_widget(widget: QtWidgets.QWidget) -> None:
    if widget.graphicsEffect() is not None:
        widget.setGraphicsEffect(None)
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(340)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
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


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent: QtWidgets.QWidget | None = None, spacing: int = 6):
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientation:
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height + margins.bottom() - rect.y()
