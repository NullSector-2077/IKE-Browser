"""Tab previews: a small picture of the page when the mouse rests on a tab.

The picture is taken when the user leaves a tab and is kept in memory only
(never written to disk); it goes away with the tab.

Since 1.1.21 the preview is a card I.K.E. paints itself: fully opaque (it
was a tooltip window, which some desktop styles, Breeze among them, draw
partly transparent), with rounded corners, and under the title the tab's
CPU and memory, read from its page's process (/proc, as the "Site
resources" window does) once a second while the card is shown and never
otherwise.
"""

import time

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

WIDTH = 240
MAX_HEIGHT = 180
RADIUS = 8
PAD = 6
REFRESH_MS = 1000


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
    # in the screen's own pixels: on a scaled screen (2x) the picture was
    # half the card's width (1.1.21)
    dpr = pm.devicePixelRatio() or 1.0
    width, top = int(round(WIDTH * dpr)), int(round(MAX_HEIGHT * dpr))
    pm = pm.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    if pm.height() > top:                     # a tall window: the top of the page
        pm = pm.copy(0, 0, width, top)
    pm.setDevicePixelRatio(dpr)
    view.preview = pm


def _level_colour(fraction):
    """Green, amber or red for a load from 0 to 1."""
    if fraction < 0.34:
        return QColor(76, 175, 80)
    if fraction < 0.67:
        return QColor(255, 179, 0)
    return QColor(229, 57, 53)


class _Picture(QWidget):
    """The page's picture, its top corners following the card's."""

    def __init__(self, parent):
        super().__init__(parent)
        self._pm = None

    def pixmap(self):
        return self._pm

    def setPixmap(self, pm):
        self._pm = pm
        if pm is not None and not pm.isNull() and pm.width() > 0:
            # always the card's width, whatever the pixels of the picture
            self.setFixedSize(WIDTH, max(1, min(MAX_HEIGHT, int(round(WIDTH * pm.height() / pm.width())))))
        self.update()

    def paintEvent(self, _event):
        if self._pm is None or self._pm.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        inner = RADIUS - 2
        path.addRoundedRect(r, inner, inner)
        p.setClipPath(path)
        p.drawPixmap(self.rect(), self._pm)
        p.end()


class _Meter(QWidget):
    """One value with a short coloured bar: "CPU 3 %" and its load."""

    def __init__(self, parent):
        super().__init__(parent)
        self.label = ""
        self.value = ""
        self.fraction = None
        self.setMinimumHeight(30)

    def set(self, label, value, fraction):
        self.label, self.value, self.fraction = label, value, fraction
        self.update()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        fm = self.fontMetrics()
        return QSize(WIDTH, fm.height() + 12)

    def shown_value(self):
        """The value as drawn: always whole (1.1.22: "182 MB" ended in "…"
        with the owner's font); only the name gives way, and only when a
        language's word is too long for the card."""
        return self.value

    def shown_label(self):
        fm = self.fontMetrics()
        room = self.width() - fm.horizontalAdvance(self.value) - fm.horizontalAdvance("  ")
        return fm.elidedText(self.label, Qt.TextElideMode.ElideRight, max(fm.horizontalAdvance("…"), room))

    def colours(self):
        """(name, value) colours: the value in the window's text colour, the
        name a little dimmer but readable, 4.5:1 at least (1.1.22: 1.9:1 in
        GNOME). The active window's colours: the card is read as one, though
        its window never is (GNOME's text of an inactive window is grey)."""
        from .uistyle import readable
        pal = self.palette()
        G, R = QPalette.ColorGroup.Active, QPalette.ColorRole
        text, bg = pal.color(G, R.WindowText), pal.color(G, R.Window)
        dim = QColor(text)
        dim.setAlphaF(0.65)
        return readable(dim, bg, text), text

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = self.fontMetrics()
        dim, text = self.colours()
        w = self.width()
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        label, value = self.shown_label(), self.shown_value()
        # the name at the start, the value at the end of the same line
        p.setPen(dim)
        p.drawText(w - fm.horizontalAdvance(label) if rtl else 0, fm.ascent(), label)
        p.setPen(text)
        p.drawText(0 if rtl else w - fm.horizontalAdvance(value), fm.ascent(), value)
        y = fm.height() + 4
        track = QColor(text)
        track.setAlphaF(0.15)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, y, w, 5), 2.5, 2.5)
        if self.fraction is not None:
            f = max(0.03, min(1.0, self.fraction))
            p.setBrush(_level_colour(self.fraction))
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                p.drawRoundedRect(QRectF(w * (1 - f), y, w * f, 5), 2.5, 2.5)
            else:
                p.drawRoundedRect(QRectF(0, y, w * f, 5), 2.5, 2.5)
        p.end()


class TabPreview(QWidget):
    # the bars: a whole core for CPU, 1 GB for memory
    CPU_FULL = 100.0
    MEM_FULL = 1024 ** 3

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setForegroundRole(QPalette.ColorRole.WindowText)
        self.setBackgroundRole(QPalette.ColorRole.Window)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(PAD, PAD, PAD, PAD + 2)
        lay.setSpacing(6)
        self.picture = _Picture(self)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.text.setFixedWidth(WIDTH)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setForegroundRole(QPalette.ColorRole.WindowText)
        f = self.text.font()
        f.setBold(True)
        self.text.setFont(f)
        lay.addWidget(self.picture)
        lay.addWidget(self.text)
        # CPU and memory one under the other, each the card's whole width
        # (1.1.22: side by side, half the width each, the value was cut)
        self.cpu = _Meter(self)
        self.mem = _Meter(self)
        self.cpu.setFixedWidth(WIDTH)
        self.mem.setFixedWidth(WIDTH)
        lay.addWidget(self.cpu)
        lay.addWidget(self.mem)
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self.note.setFixedWidth(WIDTH)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setForegroundRole(QPalette.ColorRole.WindowText)
        lay.addWidget(self.note)
        self.index = -1
        self.view = None
        self._last = {}               # pid -> (ticks, time)
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)

    # ---- painting -----------------------------------------------------------
    def _shape(self):
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        return path

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        # the window's colours, which follow I.K.E.'s theme (a tooltip's are
        # often a pale yellow of the style's own); those of an active window,
        # as the values on the card (_Meter.colours)
        G = QPalette.ColorGroup.Active
        bg = QColor(pal.color(G, QPalette.ColorRole.Window))
        bg.setAlpha(255)                      # always full, whatever the style's colour says
        border = QColor(pal.color(G, QPalette.ColorRole.WindowText))
        border.setAlphaF(0.22)
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawPath(self._shape())
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # a desktop that draws no transparency (X11 without a compositor)
        # shows the corners through a mask instead
        if QGuiApplication.platformName() == "xcb":
            from PyQt6.QtGui import QRegion
            self.setMask(QRegion(self._shape().toFillPolygon().toPolygon()))

    # ---- the tab's numbers ------------------------------------------------
    def stats(self, view):
        """{"state": "", "Suspended" or "Frozen"; "cpu": % or None; "memory":
        bytes or None; "shared": tabs sharing the process}"""
        from . import resources
        out = {"state": "", "cpu": None, "memory": None, "shared": 1}
        if view is None:
            return out
        if getattr(view, "sleeping", False):
            out["state"] = "Suspended"
            return out
        pid = resources.pid_of(view)
        if not pid:
            out["state"] = "Suspended"
            return out
        if getattr(view, "frozen", False):
            out["state"] = "Frozen"
        out["memory"] = resources.proc_memory(pid)
        ticks, now = resources.proc_cpu_ticks(pid), time.monotonic()
        before = self._last.get(pid)
        if ticks is not None:
            self._last[pid] = (ticks, now)
            if before is not None and now - before[1] > 0.2:
                out["cpu"] = max(0.0, (ticks - before[0]) / resources._TICKS / (now - before[1]) * 100.0)
        app = getattr(self.parentWidget(), "app", None)
        if app is not None:
            n = 0
            for w in list(getattr(app, "windows", [])):
                for v in w.all_views():
                    if resources.pid_of(v) == pid:
                        n += 1
            out["shared"] = max(1, n)
        return out

    def refresh(self):
        from .i18n import T
        from .resources import _size
        s = self.stats(self.view)
        if s["state"] == "Suspended":
            self.cpu.set(T("CPU"), "—", None)
            self.mem.set(T("Memory"), "—", None)
        else:
            cpu = s["cpu"]
            self.cpu.set(T("CPU"), "…" if cpu is None else "%.0f %%" % cpu,
                         None if cpu is None else cpu / self.CPU_FULL)
            mem = s["memory"]
            self.mem.set(T("Memory"), _size(mem), None if mem is None else mem / self.MEM_FULL)
        notes = []
        if s["state"]:
            notes.append(T(s["state"]))
        if s["shared"] > 1:
            notes.append(T("Shared by %d tabs of this site") % s["shared"])
        self.note.setText(" · ".join(notes))
        self.note.setVisible(bool(notes))
        if s["cpu"] is None and s["state"] == "" and self.isVisible():
            QTimer.singleShot(400, self._first_cpu)   # the first reading needs two samples

    def _first_cpu(self):
        if self.isVisible() and self.view is not None:
            self.refresh()

    # ---- showing ----------------------------------------------------------
    def show_for(self, index, pixmap, text, global_pos, view=None):
        from . import effects, polish
        config = getattr(getattr(self.parentWidget(), "app", None), "config", None)
        if self.isVisible() and self.index != index and polish.moving(config, "preview_fade"):
            self._cross(self.picture.pixmap(), pixmap)       # from one tab to the next: the picture blends
        elif not self.isVisible() and polish.part("preview_fade"):
            effects.fade_in(self, config)
        self.index = index
        self.view = view
        self.picture.setPixmap(pixmap)
        self.text.setText(text)
        self.refresh()
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
        self.timer.start()

    def _cross(self, old, new, ms=120):
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation
        from PyQt6.QtGui import QPixmap
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

    def hideEvent(self, event):
        self.timer.stop()
        self._last.clear()
        super().hideEvent(event)

    def hide_preview(self):
        self.index = -1
        self.view = None
        self.timer.stop()
        self.hide()
