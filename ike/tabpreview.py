"""Tab previews: a small picture of the page when the mouse rests on a tab.

The picture is taken when the user leaves a tab and is kept in memory only
(never written to disk); it goes away with the tab.
"""

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QGuiApplication, QPalette
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

WIDTH = 240
MAX_HEIGHT = 180


def capture(view):
    """Remember a small picture of what the tab shows."""
    try:
        if not view.isVisible() or view.width() < 50 or view.height() < 50:
            return
        pm = view.grab()
    except RuntimeError:
        return
    if pm.isNull():
        return
    pm = pm.scaledToWidth(WIDTH, Qt.TransformationMode.SmoothTransformation)
    if pm.height() > MAX_HEIGHT:              # a tall window: the top of the page
        pm = pm.copy(0, 0, WIDTH, MAX_HEIGHT)
    view.preview = pm


class TabPreview(QFrame):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setFrameShape(QFrame.Shape.Box)
        self.setForegroundRole(QPalette.ColorRole.ToolTipText)
        self.setBackgroundRole(QPalette.ColorRole.ToolTipBase)
        self.setAutoFillBackground(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.picture = QLabel(self)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.text.setFixedWidth(WIDTH)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.picture)
        lay.addWidget(self.text)
        self.index = -1

    def show_for(self, index, pixmap, text, global_pos):
        from . import effects, polish
        config = getattr(getattr(self.parentWidget(), "app", None), "config", None)
        if self.isVisible() and self.index != index and polish.moving(config, "preview_fade"):
            self._cross(self.picture.pixmap(), pixmap)       # from one tab to the next: the picture blends
        elif not self.isVisible() and polish.part("preview_fade"):
            effects.fade_in(self, config)
        self.index = index
        self.picture.setPixmap(pixmap)
        self.text.setText(text)
        self.adjustSize()
        pos = global_pos + QPoint(0, 22)
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            pos.setX(max(area.left(), min(pos.x(), area.right() - self.width())))
            if pos.y() + self.height() > area.bottom():
                pos.setY(global_pos.y() - self.height() - 8)
        self.move(pos)
        self.show()

    def _cross(self, old, new, ms=120):
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation
        from PyQt6.QtGui import QPainter, QPixmap
        anim = getattr(self, "_blend", None)
        if anim is not None:
            anim.stop()
        if old is None or old.isNull() or new is None or new.isNull():
            return

        def step(t):
            pm = QPixmap(new.size())
            pm.setDevicePixelRatio(new.devicePixelRatio())
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.drawPixmap(0, 0, new)
            p.setOpacity(1.0 - float(t))
            p.drawPixmap(0, 0, old)
            p.end()
            self.picture.setPixmap(pm)
        anim = self._blend = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(step)
        anim.finished.connect(lambda: self.picture.setPixmap(new))
        anim.start()

    def hide_preview(self):
        self.index = -1
        self.hide()
