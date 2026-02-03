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
        gradient = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.0, QtGui.QColor(self.theme.colors["bg_start"]))
        gradient.setColorAt(1.0, QtGui.QColor(self.theme.colors["bg_end"]))
        painter.fillRect(rect, gradient)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        accent = QtGui.QColor(self.theme.colors["accent"])
        accent.setAlpha(36)
        painter.setBrush(accent)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.18), int(rect.height() * 0.12)),
            260,
            260,
        )

        accent.setAlpha(26)
        painter.setBrush(accent)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.82), int(rect.height() * 0.18)),
            240,
            240,
        )

        accent.setAlpha(20)
        painter.setBrush(accent)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.7), int(rect.height() * 0.78)),
            340,
            340,
        )

        highlight = QtGui.QColor(255, 255, 255, 18)
        painter.setBrush(highlight)
        painter.drawEllipse(
            QtCore.QPoint(int(rect.width() * 0.45), int(rect.height() * -0.05)),
            520,
            520,
        )

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
