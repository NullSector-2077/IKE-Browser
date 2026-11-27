"""The panel of the toolbar's Zoom button (1.1.25).

It opens under the button, as the dark mode's panel does (window.show_zoom_panel),
and stays open while the zoom is changed: − and + one step, a slider over the
same steps (30% to 400%, window.ZOOM_STEPS), "Actual size" (Ctrl+0), and the
zoom of the pages not zoomed by hand (the same setting as Settings →
Appearance → Default zoom). The page of the tab follows at once; the zoom is
kept for the site as Ctrl and +/− keep it (not in a private window). Nothing
runs while it is closed.
"""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import panelkit
from .i18n import T

DEFAULT_RANGE = (0.5, 3.0)          # Settings → Appearance → Default zoom takes these


def _icon(names):
    from .icons import themed
    return themed(names)


def percent(factor):
    return "%d%%" % round(factor * 100)


class Marks(QWidget):
    """The values under the slider: its first step at its left edge, its last at
    its right edge, 100% under its own tick."""

    def __init__(self, slider, steps, parent=None):
        super().__init__(parent)
        self.slider, self.steps = slider, steps
        panelkit.dim(self, 0.85)
        self.setFixedHeight(self.fontMetrics().height())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def tick_x(self, index):
        """x, in this widget, of the slider's tick for a step (as the style draws it)."""
        s = self.slider
        opt = QStyleOptionSlider()
        s.initStyleOption(opt)
        st = s.style()
        length = st.pixelMetric(QStyle.PixelMetric.PM_SliderLength, opt, s)
        room = st.pixelMetric(QStyle.PixelMetric.PM_SliderSpaceAvailable, opt, s)
        x = QStyle.sliderPositionFromValue(s.minimum(), s.maximum(), index, room) + length // 2
        return s.mapTo(self.parentWidget(), s.rect().topLeft()).x() + x - self.x()

    def places(self):
        """[(text, QRect)] of the three values."""
        fm = self.fontMetrics()
        h = self.height()
        s0 = self.slider.mapTo(self.parentWidget(), self.slider.rect().topLeft()).x() - self.x()
        s1 = s0 + self.slider.width()
        first, last = percent(self.steps[0]), percent(self.steps[-1])
        one = self.steps.index(1.0) if 1.0 in self.steps else len(self.steps) // 2
        mid = percent(self.steps[one])
        wm = fm.horizontalAdvance(mid)
        cx = self.tick_x(one)
        return [(first, QRect(s0, 0, fm.horizontalAdvance(first), h)),
                (mid, QRect(cx - wm // 2, 0, wm, h)),
                (last, QRect(s1 - fm.horizontalAdvance(last), 0, fm.horizontalAdvance(last), h))]

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        p.setFont(self.font())
        for text, r in self.places():
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class ZoomPanel(QWidget):
    """Popup of the toolbar's Zoom button."""

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.steps = list(window.ZOOM_STEPS)
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*panelkit.MARGINS)
        lay.setSpacing(8)

        # 1. the title, and the site whose zoom it is
        head, self.head_icon, self.title = panelkit.title_row(self, _icon(("zoom-in",)), T("Zoom"))
        self.host = panelkit.dim(QLabel(self), 1.0)
        self.host.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.host)
        lay.addLayout(head)

        # 2. − 110% +
        row = QHBoxLayout()
        row.setSpacing(8)
        self.minus = QToolButton(self)
        self.minus.setIcon(_icon(("zoom-out",)))
        self.plus = QToolButton(self)
        self.plus.setIcon(_icon(("zoom-in",)))
        for b, name, keys in ((self.minus, "Zoom out", "Ctrl+-"), (self.plus, "Zoom in", "Ctrl++")):
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(34, 34)
            b.setAutoRaise(False)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setToolTip("%s (%s)" % (T(name), keys))
            b.setAccessibleName(T(name))
        self.value = QLabel(self)
        f = self.value.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 1.6)
        f.setBold(True)
        self.value.setFont(f)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.minus)
        row.addWidget(self.value, 1)
        row.addWidget(self.plus)
        lay.addLayout(row)

        # 3. the slider over the zoom's steps, and their values under it
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, len(self.steps) - 1)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.setAccessibleName(T("Zoom"))
        self.marks = Marks(self.slider, self.steps, self)
        lay.addWidget(self.slider)
        lay.addWidget(self.marks)

        # 4. kept for the site?  Actual size
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.note = panelkit.dim(QLabel(self))
        self.note.setWordWrap(True)
        self.reset = QPushButton(_icon(("zoom-original",)), T("Actual size"), self)
        self.reset.setToolTip("%s (Ctrl+0)" % T("Reset the zoom level"))
        bottom.addWidget(self.note, 1)
        bottom.addStretch(0)                    # (the note hidden: Actual size stays on the right)
        bottom.addWidget(self.reset)
        lay.addLayout(bottom)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # 5. the default zoom (Settings → Appearance has the same)
        default = QHBoxLayout()
        default.setSpacing(8)
        self.default_label = QLabel(T("Default zoom"), self)
        self.default = QComboBox(self)
        self.default.setAccessibleName(T("Default zoom"))
        self.default_label.setBuddy(self.default)
        default.addWidget(self.default_label, 1)
        default.addWidget(self.default)
        lay.addLayout(default)
        self.hint = panelkit.dim(QLabel(T("Also with Ctrl and the mouse wheel"), self))
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.setMinimumWidth(panelkit.WIDTH)

        self.minus.clicked.connect(lambda: self._step(-1))
        self.plus.clicked.connect(lambda: self._step(+1))
        self.slider.valueChanged.connect(self._slid)
        self.reset.clicked.connect(lambda: self._step(0))
        self.default.activated.connect(self._default_chosen)

    # --- what the panel shows -------------------------------------------
    def view(self):
        return self.win.current_view()

    def factor(self):
        v = self.view()
        return v.zoomFactor() if v else self.win.app.config["default_zoom"]

    def nearest(self, factor):
        return min(range(len(self.steps)), key=lambda i: abs(self.steps[i] - factor))

    def refresh(self):
        """Show the zoom as it is now (each time the panel opens, and after each change)."""
        self._busy = True
        cfg = self.win.app.config
        v = self.view()
        f = self.factor()
        usual = cfg["default_zoom"]
        self.value.setText(percent(f))
        self.value.setAccessibleName(T("Zoom: %d%%") % round(f * 100))
        self.slider.setValue(self.nearest(f))
        url = v.url() if v else None
        host = url.host().lower() if url is not None and url.scheme() in ("http", "https") else ""
        self.host.setText(host)
        self.host.setVisible(bool(host))
        if self.win.private:
            self.note.setText(T("Not remembered in a private window"))
        else:
            self.note.setText(T("Remembered for this site") if host else "")
        self.note.setVisible(bool(self.note.text()))
        self.minus.setEnabled(bool(v) and f > self.steps[0] + 0.01)
        self.plus.setEnabled(bool(v) and f < self.steps[-1] - 0.01)
        self.reset.setEnabled(bool(v) and abs(f - usual) > 0.005)
        self.slider.setEnabled(bool(v))
        lo, hi = DEFAULT_RANGE
        values = [s for s in self.steps if lo - 0.001 <= s <= hi + 0.001]
        if all(abs(s - usual) > 0.005 for s in values):
            values = sorted(values + [round(usual, 2)])
        self.default.clear()
        for s in values:
            self.default.addItem(percent(s), s)
        self.default.setCurrentIndex(min(range(len(values)), key=lambda i: abs(values[i] - usual)))
        self._busy = False

    # --- changes ---------------------------------------------------------
    def _step(self, direction):
        self.win.zoom(direction, osd=False)
        self.refresh()

    def _slid(self, i):
        if self._busy:
            return
        self.win.set_zoom(self.steps[i])
        self.refresh()

    def _default_chosen(self, i):
        if self._busy or i < 0:
            return
        new = float(self.default.itemData(i))
        cfg = self.win.app.config
        old = cfg["default_zoom"]
        if abs(new - old) < 0.001:
            return
        cfg["default_zoom"] = round(new, 2)
        cfg.save()
        # the pages at the old default zoom (not zoomed by hand) take the new one
        for w in self.win.app.windows:
            for v in w.all_views():
                if abs(v.zoomFactor() - old) < 0.005:
                    v.setZoomFactor(cfg["default_zoom"])
            w._zoom_sign()
        self.refresh()
