"""The panel of the toolbar's Dark mode button (1.1.25).

It opens under the button, as the shield's panel opens under the shield
(window.show_dark_panel): dark mode for every site and for this one, Dark or
Light, Dark Reader's brightness, contrast, sepia and grayscale, and under
"More" its font, text stroke, colours, scroll bars and selection colour, for
every site or for this site only. A slider moved shows its effect on the page
of this tab at once (Dark Reader takes the new colours without the page being
loaded again); let go, the colours are kept and every open page gets them.

Every value is checked by darktheme.py before it is kept or reaches a page.
The panel has no links outside I.K.E.: its last button opens I.K.E.'s own
Settings. Nothing runs while it is closed.
"""

from PyQt6.QtCore import QLocale, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
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

from . import darktheme
from .i18n import T
from .uistyle import TEXT_ROOM, Switch

LIVE_MS = 120          # a slider moved: the page of this tab shows it after this pause
KEEP_MS = 500          # moved with the keys or by a click beside its handle: then it is kept

SLIDER_NAMES = {"brightness": "Brightness", "contrast": "Contrast", "sepia": "Sepia",
                "grayscale": "Grayscale"}


def _icon(names):
    from .icons import themed
    return themed(names)


def trim_left(pm):
    """The picture without the empty columns on its left: its drawing starts on
    the panel's left edge, as the texts under it do."""
    img = pm.toImage()
    for x in range(img.width()):
        if any(img.pixelColor(x, y).alpha() > 40 for y in range(img.height())):
            return pm.copy(x, 0, img.width() - x, img.height()) if x else pm
    return pm


def triangle(down, size=10):
    """The arrow of "More": a small triangle in the text's colour, drawn from the
    panel's left edge (the style's own arrow is drawn a few pixels in)."""
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QGuiApplication.palette().color(QPalette.ColorRole.WindowText))
    from PyQt6.QtGui import QPolygonF
    if down:
        pts = [QPointF(0, 2), QPointF(size, 2), QPointF(size / 2, size - 2)]
    else:
        pts = [QPointF(1, 0), QPointF(size - 2, size / 2), QPointF(1, size)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    return QIcon(pm)


def chip(colour, size=16):
    """A small square of a colour, with a thin line around it."""
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    line = QColor(QGuiApplication.palette().color(QPalette.ColorRole.WindowText))
    line.setAlphaF(0.45)
    p.setPen(QPen(line, 1))
    p.setBrush(QColor(colour))
    p.drawRoundedRect(QRectF(1.5, 1.5, size - 3, size - 3), 3, 3)
    p.end()
    return QIcon(pm)


class Segmented(QWidget):
    """Two choices side by side in one frame, the chosen one in the accent
    colour. Tab reaches it; the arrow keys and Space change the choice."""

    changed = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.labels = list(labels)
        self.current = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(" / ".join(self.labels))
        self._describe()

    def _describe(self):
        self.setAccessibleDescription(self.labels[self.current])

    def setCurrent(self, i, emit=False):
        i = max(0, min(len(self.labels) - 1, i))
        if i != self.current:
            self.current = i
            self._describe()
            self.update()
            if emit:
                self.changed.emit(i)

    def sizeHint(self):
        fm = self.fontMetrics()
        bold = self.font()
        bold.setBold(True)
        from PyQt6.QtGui import QFontMetrics
        bm = QFontMetrics(bold)
        w = sum(max(fm.horizontalAdvance(t), bm.horizontalAdvance(t)) + 2 * TEXT_ROOM + 8 for t in self.labels)
        return QSize(w, fm.height() + 12)

    def minimumSizeHint(self):
        return self.sizeHint()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setCurrent(int(e.position().x() * len(self.labels) / max(1, self.width())), emit=True)

    def keyPressEvent(self, e):
        k = e.key()
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = 1 if (k == Qt.Key.Key_Right) != rtl else -1
            self.setCurrent(self.current + step, emit=True)
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setCurrent((self.current + 1) % len(self.labels), emit=True)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _e):
        from . import polish
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        R = QPalette.ColorRole
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = polish.RADIUS - 1
        edge = pal.color(group, R.Highlight) if self.hasFocus() else polish.separator(pal)
        p.setPen(QPen(edge, 1))
        p.setBrush(pal.color(group, R.Button))
        p.drawRoundedRect(r, radius, radius)
        n = len(self.labels)
        seg = r.width() / n
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        for i, text in enumerate(self.labels):
            col = n - 1 - i if rtl else i
            cell = QRectF(r.left() + col * seg, r.top(), seg, r.height())
            if i == self.current:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(pal.color(group, R.Highlight))
                p.drawRoundedRect(cell.adjusted(2, 2, -2, -2), radius - 1.5, radius - 1.5)
                p.setPen(pal.color(group, R.HighlightedText))
            else:
                if col > 0 and abs(i - self.current) != 1:
                    p.setPen(QPen(polish.separator(pal), 1))
                    p.drawLine(QPointF(cell.left(), cell.top() + 5), QPointF(cell.left(), cell.bottom() - 5))
                p.setPen(pal.color(group, R.ButtonText))
            f = self.font()
            f.setBold(i == self.current)
            p.setFont(f)
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class DarkPanel(QWidget):
    """Popup of the toolbar's Dark mode button."""

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self._busy = False
        self._dirty = False
        self._fonts_filled = False
        self._more_open = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)          # the shield panel's
        lay.setSpacing(8)

        # 1. the title and dark mode for every site
        head = QHBoxLayout()
        head.setSpacing(8)
        self.head_icon = QLabel(self)
        self.head_icon.setPixmap(trim_left(_icon(("weather-clear-night",)).pixmap(18, 18)))
        self.title = QLabel(T("Dark mode for pages"), self)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.master = Switch(self)
        self.master.setToolTip(T("On everywhere"))
        self.master.setAccessibleName(T("On everywhere"))
        head.addWidget(self.head_icon)
        head.addWidget(self.title, 1)
        head.addWidget(self.master)
        lay.addLayout(head)

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

        # 3. dark | light (Dark Reader's mode 1 | 0)
        self.mode = Segmented([T("Dark"), T("Light")], self)
        lay.addWidget(self.mode)

        # 4. the sliders
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.sliders, self.values, self.slider_labels = {}, {}, {}
        value_w = self.fontMetrics().horizontalAdvance("150%") + 4
        for row, key in enumerate(darktheme.SLIDERS):
            lo, hi = darktheme.RANGES[key]
            name = QLabel(T(SLIDER_NAMES[key]), self)
            s = QSlider(Qt.Orientation.Horizontal, self)
            s.setRange(lo, hi)
            s.setSingleStep(1)
            s.setPageStep(10)
            s.setMinimumWidth(130)
            s.setAccessibleName(T(SLIDER_NAMES[key]))
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
        reset_row = QHBoxLayout()
        self.note = QLabel(T("The sliders work with Dark Reader"), self)
        self.note.setWordWrap(True)
        nf = self.note.font()
        if nf.pointSizeF() > 0:
            nf.setPointSizeF(nf.pointSizeF() * 0.9)
        self.note.setFont(nf)
        self.note.setEnabled(False)                 # the dimmed text of the palette
        self.reset = QPushButton(_icon(("edit-undo",)), T("Reset"), self)
        self.reset.setToolTip(T("Brightness, contrast, sepia and grayscale back to their defaults"))
        self.reset.clicked.connect(self._reset)
        reset_row.addWidget(self.note, 1)
        reset_row.addStretch(0)
        reset_row.addWidget(self.reset, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(reset_row)

        # 5. More
        self.more_btn = QPushButton(triangle(False), T("More"), self)
        self.more_btn.setCheckable(True)
        self.more_btn.setFlat(True)
        self.more_btn.setIconSize(QSize(10, 10))
        # its arrow on the panel's one left edge, open or closed (the owner: everything aligned)
        self.more_btn.setStyleSheet("QPushButton { border: none; background: transparent; text-align: left;"
                                    " padding: 4px 8px 4px 0px; }")
        self.more = QWidget(self)
        g = QGridLayout(self.more)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.font_switch = Switch(self.more)
        self.font_switch.setToolTip(T("Use another font for the pages"))
        self.font_switch.setAccessibleName(T("Use another font for the pages"))
        self.font_combo = QComboBox(self.more)
        self.font_combo.setAccessibleName(T("Text font"))
        self.font_combo.setMaxVisibleItems(15)
        self.font_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(10)
        self.font_combo.setProperty("ike_elides", True)    # a long name may be cut; its list shows it whole
        self.stroke = QComboBox(self.more)
        point = QLocale().decimalPoint() or "."
        for s in darktheme.STROKES:
            self.stroke.addItem(T("None") if s == 0 else ("%g" % s).replace(".", point), s)
        self.stroke.setAccessibleName(T("Text stroke"))
        self.bg = QPushButton(self.more)
        self.fg = QPushButton(self.more)
        for b, name in ((self.bg, "Background colour"), (self.fg, "Text colour")):
            b.setIconSize(QSize(16, 16))
            b.setAccessibleName(T(name))
        self.bars = QComboBox(self.more)
        self.bars.setAccessibleName(T("Scrollbars"))
        self.selection = QComboBox(self.more)
        self.selection.setAccessibleName(T("Selection colour"))
        font_box = QHBoxLayout()
        font_box.setSpacing(8)
        font_box.addWidget(self.font_switch)
        font_box.addWidget(self.font_combo, 1)
        self.more_labels = []
        rows = (("Text font", font_box, self.font_switch), ("Text stroke", self.stroke, self.stroke),
                ("Background colour", self.bg, self.bg), ("Text colour", self.fg, self.fg),
                ("Scrollbars", self.bars, self.bars), ("Selection colour", self.selection, self.selection))
        for r, (text, field, buddy) in enumerate(rows):
            lab = QLabel(T(text), self.more)
            lab.setBuddy(buddy)
            self.more_labels.append(lab)
            g.addWidget(lab, r, 0)
            if isinstance(field, QHBoxLayout):
                g.addLayout(field, r, 1)
            else:
                g.addWidget(field, r, 1)
        g.setColumnStretch(1, 1)
        self.only_site = Switch(T("Only for this site"), self.more)
        g.addWidget(self.only_site, len(rows), 0, 1, 2)
        self.more.hide()
        lay.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.more)

        # 6. I.K.E.'s own Settings (nothing outside I.K.E.)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)
        self.settings = QPushButton(_icon(("configure", "preferences-system")), T("Dark mode settings…"), self)
        self.settings.setFlat(True)
        self.settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings.setStyleSheet("QPushButton { text-align: left; color: palette(link); border: none;"
                                    " padding: 4px 8px 4px 0px; }"
                                    "QPushButton:hover { text-decoration: underline; }"
                                    "QPushButton:focus { text-decoration: underline; }")
        lay.addWidget(self.settings, 0, Qt.AlignmentFlag.AlignLeft)
        self.setMinimumWidth(320 + 28)                  # as wide as the shield's panel

        # the pause before the page shows a slider's value, and before it is kept
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
        self.mode.changed.connect(self._mode_changed)
        self.more_btn.toggled.connect(self._more_toggled)
        self.font_switch.clicked.connect(self._font_switched)
        self.font_combo.activated.connect(self._font_chosen)
        self.stroke.activated.connect(self._stroke_chosen)
        self.bg.clicked.connect(lambda: self._pick(self._colour_key("Background")))
        self.fg.clicked.connect(lambda: self._pick(self._colour_key("Text")))
        self.bars.activated.connect(lambda i: self._choice("scrollbarColor", self.bars, i))
        self.selection.activated.connect(lambda i: self._choice("selectionColor", self.selection, i))
        self.only_site.clicked.connect(self._only_site_clicked)
        self.settings.clicked.connect(self._open_settings)

    # --- what the panel shows -------------------------------------------
    @property
    def cfg(self):
        return self.win.app.config

    def host(self):
        return self.win.current_host()

    def web(self):
        v = self.win.current_view()
        return bool(v) and v.url().scheme() in ("http", "https", "file")

    def theme(self):
        """(the theme the panel changes, its own for this site?): the dictionary in
        the settings itself, checked first."""
        cfg = self.cfg
        host = self.host()
        sites = cfg["dark_site_themes"]
        if host and host in sites:
            sites[host] = darktheme.clean(sites[host])
            return sites[host], True
        cfg["dark_theme"] = darktheme.clean(cfg["dark_theme"])
        return cfg["dark_theme"], False

    def _colour_key(self, what):
        theme, _own = self.theme()
        scheme = "darkScheme" if theme["mode"] == 1 else "lightScheme"
        return "%s%sColor" % (scheme, what)

    def refresh(self):
        """Show the settings as they are now (each time the panel opens)."""
        self._busy = True
        cfg = self.cfg
        host = self.host()
        web = self.web()
        reader = cfg["dark_engine"] != "engine"
        theme, own = self.theme()
        self.master.setChecked(cfg["dark_mode"] == "on")
        self.site_label.setText(T("This site: %s") % (host or "—"))
        self.site.setEnabled(web and bool(host))
        self.site.setChecked(web and bool(host) and self.win.app.shields.dark_for(host))
        self.mode.setCurrent(0 if theme["mode"] == 1 else 1)
        for key, s in self.sliders.items():
            s.setValue(theme[key])
            self.values[key].setText("%d%%" % theme[key])
        self.font_switch.setChecked(theme["useFont"])
        if self._fonts_filled:
            self._show_font(theme)
        self.stroke.setCurrentIndex(max(0, self.stroke.findData(theme["textStroke"])))
        self._show_colours(theme)
        self.only_site.setEnabled(bool(host))
        self.only_site.setChecked(own)
        self.only_site.setToolTip(T("These choices for %s only") % host if host else "")
        # Chromium's own dark mode has no colours to choose (1.1.25: greyed, with a note)
        for w in ([self.mode, self.reset, self.more_btn, self.more] + list(self.sliders.values())
                  + list(self.values.values()) + list(self.slider_labels.values())):
            w.setEnabled(reader)
        self.note.setVisible(not reader)
        self.more_btn.setChecked(self._more_open)
        self._show_more(self._more_open)
        self._busy = False

    def _show_font(self, theme):
        i = self.font_combo.findText(theme["fontFamily"])
        if i < 0 and self.font_combo.count():
            i = max(0, self.font_combo.findText(QGuiApplication.font().family()))
        self.font_combo.setCurrentIndex(i)
        self.font_combo.setEnabled(theme["useFont"])

    def _fill_fonts(self):
        """The fonts of this computer, listed the first time "More" opens."""
        if self._fonts_filled:
            return
        self._fonts_filled = True
        self.font_combo.addItems(darktheme.system_fonts())
        view = self.font_combo.view()
        bar = view.verticalScrollBar().sizeHint().width()
        view.setMinimumWidth(min(view.sizeHintForColumn(0) + bar + 8, 600))
        self._show_font(self.theme()[0])

    def _show_colours(self, theme):
        scheme = "darkScheme" if theme["mode"] == 1 else "lightScheme"
        for b, what in ((self.bg, "Background"), (self.fg, "Text")):
            c = theme["%s%sColor" % (scheme, what)]
            b.setText(c)
            b.setIcon(chip(c))
        for combo, key, hidden in ((self.bars, "scrollbarColor", True),
                                   (self.selection, "selectionColor", False)):
            combo.clear()
            combo.addItem(T("Automatic"), "auto")
            if hidden:
                combo.addItem(T("Hidden"), "hidden")
            value = theme[key]
            custom = darktheme.colour(value)
            if custom:
                combo.addItem(chip(custom), custom, "colour")
            else:
                combo.addItem(T("Colour…"), "colour")
            combo.setCurrentIndex(combo.count() - 1 if custom else max(0, combo.findData(value)))

    def _show_more(self, on):
        self.more.setVisible(on)
        self.more_btn.setIcon(triangle(on))
        if on:
            self._fill_fonts()

    def _more_toggled(self, on):
        if self._busy:
            return
        self._more_open = on
        self._show_more(on)
        QTimer.singleShot(0, self.win.fit_dark_menu)

    # --- changes ---------------------------------------------------------
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
        """A value of the theme changed: kept and given to every page at once."""
        theme, _own = self.theme()
        theme[key] = value
        self._dirty = True
        self.commit()

    def _mode_changed(self, i):
        if self._busy:
            return
        self._changed("mode", 1 if i == 0 else 0)
        self._busy = True
        self._show_colours(self.theme()[0])          # the colours of the other scheme
        self._busy = False

    def _slider_moved(self, key, value):
        self.values[key].setText("%d%%" % value)
        if self._busy:
            return
        theme, _own = self.theme()
        theme[key] = value
        self._dirty = True
        self._live.start()                            # this tab, after a short pause
        if not self.sliders[key].isSliderDown():
            self._keep.start()                        # the keys, or a click beside the handle

    def _show_live(self):
        self.win.app.push_dark_theme(self.win.current_view())

    def commit(self):
        """Keep the changed values and give them to every open page."""
        self._live.stop()
        self._keep.stop()
        if not self._dirty:
            return
        self._dirty = False
        self.win.app.dark_theme_changed()

    def _reset(self):
        theme, _own = self.theme()
        for key in darktheme.SLIDERS:
            theme[key] = darktheme.DEFAULTS[key]
        self._busy = True
        for key, s in self.sliders.items():
            s.setValue(theme[key])
        self._busy = False
        self._dirty = True
        self.commit()

    def _font_switched(self, on):
        if self._busy:
            return
        self._fill_fonts()
        self.font_combo.setEnabled(on)
        theme, _own = self.theme()
        name = self.font_combo.currentText()
        if on and name in darktheme.system_fonts():
            theme["fontFamily"] = name
        self._changed("useFont", bool(on))

    def _font_chosen(self, i):
        if self._busy or i < 0:
            return
        name = self.font_combo.itemText(i)
        if name in darktheme.system_fonts():        # only a font of this computer
            self._changed("fontFamily", name)

    def _stroke_chosen(self, i):
        if self._busy or i < 0:
            return
        self._changed("textStroke", self.stroke.itemData(i))

    def _choice(self, key, combo, i):
        if self._busy or i < 0:
            return
        what = combo.itemData(i)
        if what == "colour":
            self._pick(key)
        else:
            self._changed(key, what)

    def _only_site_clicked(self, on):
        if self._busy:
            return
        host = self.host()
        if not host:
            return
        cfg = self.cfg
        sites = dict(cfg["dark_site_themes"])
        if on:
            sites[host] = darktheme.clean(cfg["dark_theme"])     # starts from every site's
        else:
            sites.pop(host, None)
        cfg["dark_site_themes"] = sites
        self._dirty = True
        self.commit()
        self.refresh()

    def _pick(self, key):
        """A colour chosen in a window of its own: the page of this tab shows each
        colour tried; Cancel puts back the one before. The panel opens again after."""
        menu = self.win.dark_menu
        if menu is not None:
            menu.hide()
        QTimer.singleShot(0, lambda: self._pick_now(key))

    def _pick_now(self, key):
        theme, _own = self.theme()
        before = theme[key]
        start = darktheme.colour(before)
        if not start:
            start = theme["darkSchemeTextColor" if key == "scrollbarColor" else "darkSchemeBackgroundColor"]
            if key == "selectionColor":
                start = "#004daa"                     # the blue Dark Reader gives selected text
        names = {"scrollbarColor": "Scrollbars", "selectionColor": "Selection colour"}
        title = T(names.get(key) or ("Background colour" if "Background" in key else "Text colour"))
        dlg = QColorDialog(QColor(start), self.win)
        dlg.setWindowTitle(title)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)

        def tried(c):
            hexa = darktheme.colour(c.name())
            if hexa:
                self.theme()[0][key] = hexa
                self._live.start()
        dlg.currentColorChanged.connect(tried)
        ok = dlg.exec()
        chosen = darktheme.colour(dlg.selectedColor().name()) if ok else None
        dlg.deleteLater()
        self.theme()[0][key] = chosen or before
        self._dirty = True
        self.commit()
        self.win.show_dark_panel()

    def _open_settings(self):
        if self.win.dark_menu is not None:
            self.win.dark_menu.hide()
        self.win.open_dark_settings()
