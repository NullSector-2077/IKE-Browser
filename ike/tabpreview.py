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
        self.setObjectName("iceTabPreview")
        self.setFrameShape(QFrame.Shape.Box)
        self.setForegroundRole(QPalette.ColorRole.ToolTipText)
        self.setBackgroundRole(QPalette.ColorRole.ToolTipBase)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "#iceTabPreview { border: 1px solid palette(mid); border-radius: 8px; }"
            "#iceTabPreview QLabel { color: palette(tool-tip-text); }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)
        self.picture = QLabel(self)
        self.picture.setObjectName("tabPreviewPicture")
        self.text = QLabel(self)
        self.text.setObjectName("tabPreviewText")
        self.text.setWordWrap(True)
        self.text.setFixedWidth(WIDTH)
        self.text.setMargin(2)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.picture)
        lay.addWidget(self.text)
        self.index = -1

    def show_for(self, index, pixmap, text, global_pos):
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

    def hide_preview(self):
        self.index = -1
        self.hide()
