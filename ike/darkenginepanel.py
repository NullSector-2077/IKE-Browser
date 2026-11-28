"""The panel of the toolbar's Dark mode button (1.1.28; since 1.1.30, when Dark
Reader left I.K.E., the only one: with Chromium's own dark mode as the method,
its look is greyed and a line says it belongs to the I.K.E. Dark Engine).

It opens under the button as the other panels do (window.show_dark_panel), in
I.K.E.'s Plasma look: the engine's name with its moon, dark mode for every site
and for this one, four styles drawn in their own colours (Graphite, Midnight,
Warm, Nordic), how dark the backgrounds are, how bright the text is, how much
photos and videos are dimmed, whether sites that are dark already are left as
they are, and I.K.E.'s own Settings. A slider moved shows its effect on the
page of this tab at once (the engine takes the new look without the page being
loaded again); let go, the look is kept and every open page gets it.

Every value is checked by darkengine.clean_look before it is kept or reaches a
page. Nothing runs while the panel is closed.
"""

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import darkengine
from .i18n import T
from .panelkit import MARGINS, WIDTH, dim, link_button, title_row

LIVE_MS = 120          # a slider moved: the page of this tab shows it after this pause
KEEP_MS = 500          # moved with the keys or by a click beside its handle: then it is kept

STYLE_NAMES = {"graphite": "Graphite", "midnight": "Midnight", "warm": "Warm", "nordic": "Nordic"}
SLIDERS = (("depth", "Background depth"), ("text", "Text brightness"), ("pictures", "Dim pictures"))


def _icon(names):
    from .icons import themed
    return themed(names)


class StyleCards(QWidget):
    """The four styles side by side, each drawn as a small page in its own
    colours (its background, a line of text and a link), its name under it; the
    chosen one framed in the accent colour. Tab reaches it; the arrow keys,
    Space and a click choose."""

    changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.styles = list(darkengine.STYLES)
        self.current = "graphite"
        self.look = dict(darkengine.LOOK)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(T("Style"))

    def set_look(self, look):
        self.look = darkengine.clean_look(look)
        self.current = self.look["style"]
        self.setAccessibleDescription(T(STYLE_NAMES[self.current]))
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        names = max(fm.horizontalAdvance(T(n)) for n in STYLE_NAMES.values()) + 8
        return QSize(max(4 * 64, 4 * names), 46 + fm.height() + 10)

    def minimumSizeHint(self):
        return QSize(4 * 56, self.sizeHint().height())

    def _cells(self):
        n = len(self.styles)
        gap = 8
        w = (self.width() - gap * (n - 1)) / n
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        cells = []
        for i in range(n):
            col = n - 1 - i if rtl else i
            cells.append(QRectF(col * (w + gap), 0, w, self.height()))
        return cells

    def _choose(self, i, emit=True):
        i = max(0, min(len(self.styles) - 1, i))
        style = self.styles[i]
        if style != self.current:
            self.current = style
            self.setAccessibleDescription(T(STYLE_NAMES[style]))
            self.update()
            if emit:
                self.changed.emit(style)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            return
        for i, c in enumerate(self._cells()):
            if c.contains(e.position()):
                self._choose(i)
                return

    def keyPressEvent(self, e):
        k = e.key()
        i = self.styles.index(self.current)
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._choose(i + (1 if (k == Qt.Key.Key_Right) != rtl else -1))
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._choose((i + 1) % len(self.styles))
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _e):
        from . import polish
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        R = QPalette.ColorRole
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        fm = self.fontMetrics()
        radius = polish.RADIUS
        for style, cell in zip(self.styles, self._cells()):
            bg, fg, link = darkengine.colours(dict(self.look, style=style))
            chosen = style == self.current
            card = QRectF(cell.left() + 2, 2, cell.width() - 4, 42)
            # the card: the style's own page
            p.setPen(QPen(QColor(pal.color(group, R.Highlight)) if chosen else polish.separator(pal),
                          2 if chosen else 1))
            p.setBrush(QColor(bg))
            p.drawRoundedRect(card, radius, radius)
            # "Aa" in its text colour, a line of text and a link under it
            f = QFont(self.font())
            f.setBold(True)
            f.setPointSizeF(max(7.0, (f.pointSizeF() if f.pointSizeF() > 0 else 9) * 1.05))
            p.setFont(f)
            p.setPen(QColor(fg))
            p.drawText(card.adjusted(8, 3, -4, -20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Aa")
            p.setPen(Qt.PenStyle.NoPen)
            line = QColor(fg)
            line.setAlphaF(0.55)
            p.setBrush(line)
            p.drawRoundedRect(QRectF(card.left() + 8, card.bottom() - 15, card.width() * 0.45, 3), 1.5, 1.5)
            p.setBrush(QColor(link))
            p.drawRoundedRect(QRectF(card.left() + 8, card.bottom() - 9, card.width() * 0.3, 3), 1.5, 1.5)
            if chosen:                                   # a small check in the accent colour
                p.setBrush(pal.color(group, R.Highlight))
                p.drawEllipse(QRectF(card.right() - 14, card.top() + 5, 9, 9))
            # the style's name under its card
            f = QFont(self.font())
            f.setBold(chosen)
            p.setFont(f)
            p.setPen(pal.color(group, R.WindowText))
            name = fm.elidedText(T(STYLE_NAMES[style]), Qt.TextElideMode.ElideRight, int(cell.width()))
            p.drawText(QRectF(cell.left(), card.bottom() + 4, cell.width(), fm.height() + 2),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name)
        if self.hasFocus():
            p.setPen(QPen(pal.color(group, R.Highlight), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.end()


class EnginePanel(QWidget):
    """Popup of the toolbar's Dark mode button with the I.K.E. Dark Engine."""

    def __init__(self, window):
        super().__init__(window)
        from .uistyle import Switch
        self.win = window
        self._busy = False
        self._dirty = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*MARGINS)
        lay.setSpacing(8)

        # 1. the engine's name and its moon, dark mode for every site
        head, self.head_icon, self.title = title_row(
            self, _icon(("weather-clear-night", "weather-clear-night-symbolic")), T("I.K.E. Dark Engine"))
        self.master = Switch(self)
        self.master.setToolTip(T("On everywhere"))
        self.master.setAccessibleName(T("On everywhere"))
        head.addWidget(self.master)
        lay.addLayout(head)
        self.tagline = dim(QLabel(T("I.K.E.'s own dark mode: light and fast"), self))
        self.tagline.setWordWrap(True)
        lay.addWidget(self.tagline)

        # 2. this site
        site = QHBoxLayout()
        site.setSpacing(8)
        self.site_label = QLabel(self)
        self.site = Switch(self)
        self.site.setToolTip(T("On for this site"))
        self.site.setAccessibleName(T("On for this site"))
        self.site_label.setBuddy(self.site)
        site.addWidget(self.site_label, 1)
        site.addWidget(self.site)
        lay.addLayout(site)

        # 3. the styles
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)
        self.style_label = QLabel(T("Style"), self)
        f = self.style_label.font()
        f.setBold(True)
        self.style_label.setFont(f)
        lay.addWidget(self.style_label)
        self.cards = StyleCards(self)
        self.style_label.setBuddy(self.cards)
        lay.addWidget(self.cards)

        # 4. the sliders
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.sliders, self.values, self.slider_labels = {}, {}, {}
        value_w = self.fontMetrics().horizontalAdvance("100%") + 4
        for row, (key, text) in enumerate(SLIDERS):
            lo, hi = darkengine.RANGES[key]
            name = QLabel(T(text), self)
            s = QSlider(Qt.Orientation.Horizontal, self)
            s.setRange(lo, hi)
            s.setSingleStep(1)
            s.setPageStep(10)
            s.setMinimumWidth(120)
            s.setAccessibleName(T(text))
            name.setBuddy(s)
            v = QLabel(self)
            v.setMinimumWidth(value_w)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s.valueChanged.connect(lambda n, k=key: self._slider_moved(k, n))
            s.sliderReleased.connect(self.commit)
            grid.addWidget(name, row, 0)
            grid.addWidget(s, row, 1)
            grid.addWidget(v, row, 2)
            self.sliders[key], self.values[key], self.slider_labels[key] = s, v, name
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # 5. sites dark already; back to the defaults
        detect = QHBoxLayout()
        detect.setSpacing(8)
        self.detect_label = QLabel(T("Leave sites that are dark already as they are"), self)
        self.detect_label.setWordWrap(True)
        self.detect = Switch(self)
        self.detect.setAccessibleName(self.detect_label.text())
        self.detect_label.setBuddy(self.detect)
        detect.addWidget(self.detect_label, 1)
        detect.addWidget(self.detect, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(detect)
        reset_row = QHBoxLayout()
        self.note = dim(QLabel(T("The style is the I.K.E. Dark Engine's: Chromium's own dark mode has none"), self))
        self.note.setWordWrap(True)
        reset_row.addWidget(self.note, 1)
        reset_row.addStretch(0)
        self.reset = QPushButton(_icon(("edit-undo",)), T("Reset"), self)
        self.reset.setToolTip(T("Style, depth, text and pictures back to their defaults"))
        self.reset.clicked.connect(self._reset)
        reset_row.addWidget(self.reset)
        lay.addLayout(reset_row)

        # 6. I.K.E.'s own Settings (nothing outside I.K.E.)
        sep2 = QFrame(self)
        sep2.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep2)
        self.settings = link_button(self, _icon(("configure", "preferences-system")), T("Dark mode settings…"))
        lay.addWidget(self.settings, 0, Qt.AlignmentFlag.AlignLeft)
        self.setMinimumWidth(WIDTH)

        self._live = QTimer(self)
        self._live.setSingleShot(True)
        self._live.setInterval(LIVE_MS)
        self._live.timeout.connect(self._show_live)
        self._keep = QTimer(self)
        self._keep.setSingleShot(True)
        self._keep.setInterval(KEEP_MS)
        self._keep.timeout.connect(self.commit)

        self.master.clicked.connect(self._master_clicked)
        self.site.clicked.connect(self._site_clicked)
        self.cards.changed.connect(self._style_chosen)
        self.detect.clicked.connect(self._detect_clicked)
        self.settings.clicked.connect(self._open_settings)

    # --- what the panel shows -------------------------------------------
    @property
    def cfg(self):
        return self.win.app.config

    def look(self):
        """The look in the settings itself, checked first."""
        self.cfg["dark_engine_look"] = darkengine.clean_look(self.cfg["dark_engine_look"])
        return self.cfg["dark_engine_look"]

    def host(self):
        return self.win.current_host()

    def web(self):
        v = self.win.current_view()
        return bool(v) and v.url().scheme() in ("http", "https", "file")

    def refresh(self):
        """Show the settings as they are now (each time the panel opens)."""
        self._busy = True
        cfg = self.cfg
        host = self.host()
        web = self.web()
        look = self.look()
        self.master.setChecked(cfg["dark_mode"] == "on")
        self.site_label.setText(T("This site: %s") % (host or "—"))
        self.site.setEnabled(web and bool(host))
        self.site.setChecked(web and bool(host) and self.win.app.shields.dark_for(host))
        self.cards.set_look(look)
        for key, s in self.sliders.items():
            s.setValue(look[key])
            self.values[key].setText("%d%%" % look[key])
        self.detect.setChecked(look["detect"])
        own = cfg["dark_engine"] != "engine"
        for w in ([self.style_label, self.cards, self.detect, self.detect_label, self.reset]
                  + list(self.sliders.values()) + list(self.values.values()) + list(self.slider_labels.values())):
            w.setEnabled(own)
        self.note.setVisible(not own)
        self._busy = False

    # --- what the panel changes -----------------------------------------
    def _master_clicked(self, on):
        if self._busy:
            return
        self.win._set_dark("on" if on else "off")
        self.refresh()

    def _site_clicked(self, on):
        if self._busy:
            return
        self.win.app.set_site_dark(self.host(), on)
        self.refresh()

    def _changed(self, key, value):
        """A value of the look changed: kept and given to every page at once."""
        self.look()[key] = value
        self._dirty = True
        self.commit()

    def _style_chosen(self, style):
        if self._busy:
            return
        self._changed("style", style)
        self.cards.set_look(self.look())

    def _detect_clicked(self, on):
        if self._busy:
            return
        self._changed("detect", bool(on))

    def _slider_moved(self, key, value):
        self.values[key].setText("%d%%" % value)
        if self._busy:
            return
        self.look()[key] = value
        self.cards.set_look(self.look())             # the previews follow depth and text
        self._dirty = True
        self._live.start()                            # this tab, after a short pause
        if not self.sliders[key].isSliderDown():
            self._keep.start()                        # the keys, or a click beside the handle

    def _show_live(self):
        self.win.app.push_engine_look(self.win.current_view(), self.look())

    def commit(self):
        """Keep the changed look and give it to every open page."""
        self._live.stop()
        self._keep.stop()
        if not self._dirty:
            return
        self._dirty = False
        self.win.app.engine_look_changed()

    def _reset(self):
        self.cfg["dark_engine_look"] = dict(darkengine.LOOK)
        self._dirty = True
        self.commit()
        self.refresh()

    def _open_settings(self):
        if self.win.dark_menu is not None:
            self.win.dark_menu.hide()
        self.win.open_dark_settings()
