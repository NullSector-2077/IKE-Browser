"""Small touches of the interface (1.1.3): the mark of the current tab that
glides, titles that fade out at the edge, icons that change with a short
fade, a rounded address field, suggestions with site icons, the zoom sign,
bars that fade in.

Everything uses the colours of the theme in use (the desktop's, or an
interface theme): no colour of its own. Nothing keeps running while the
interface is still; the speaker of a tab that plays sound is the only thing
that moves for a while, and only while the sound plays. The moving parts
follow "Interface effects" and the desktop's reduced-motion choice
(effects.on): without them everything changes at once.

Each touch can be switched off on its own in PARTS, without touching the
others.
"""

import math

from PyQt6.QtCore import QEasingCurve, QObject, QPointF, QRect, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QIcon, QIconEngine, QImage, QLinearGradient, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyledItemDelegate, QStyleOptionTab, QWidget

from . import effects

PARTS = {
    "tab_mark": True,        # the line under the current tab, gliding to the new one
    "title_fade": True,      # long tab titles fade out instead of ending in "…"
    "icon_fade": True,       # a tab's icon changes with a short fade
    "row_hover": True,       # vertical tabs: the hover colour comes and goes softly
    "row_enter": True,       # vertical tabs: a new row fades in
    "audio_pulse": True,     # the speaker of a tab playing sound pulses gently
    "url_pill": False,       # the address field: rounded, its edge lights up when used (off: the owner preferred the system's field, 1.1.6)
    "url_popup": True,       # suggestions: taller rows with the site's icon
    "zoom_mark": True,       # a sign in the address field when the page is not at its usual zoom
    "reload_fade": True,     # Reload and Stop change with a short fade
    "bar_fade": True,        # find bar, repair bar and full-screen notice fade in
    "preview_fade": True,    # the tab preview fades in and changes softly
    "line_ends": True,       # the loading line has soft ends
    "download_pop": True,    # a finished download shows a tick with a small pop
    # 1.1.5
    "shield_pulse": True,    # a ring opens once around the shield when it blocks something
    "shield_bars": True,     # the shield panel: what was blocked on the site, as bars by kind
    "download_rows": True,   # the downloads window: file icons and a progress bar in each row
    "engine_icon": True,     # suggestions: the search engine's own icon on the search rows
    "reader_tools": True,    # reader mode: light, sepia or dark, and the size of the text
    # 1.1.6
    "window_hover": True,    # minimize / maximize: a soft circle under the mouse, as the close button
    "download_arrow": True,  # the arrow of the Downloads button moves while files arrive
    "chrome_edge": True,     # a thin line between the bars and the page
    # 1.1.7
    "toasts": True,          # short messages (zoom, notes) in a rounded pill over the page, not the status bar
    "find_pill": True,       # find bar: "3 of 12" in a pill, the field tinted when nothing is found
    "shield_count": True,    # a small "+N" rises from the shield when its number grows
    "panel_icons": True,     # the site's icon beside its name in the shield and site panels
    "settings_fade": True,   # Settings: the pages change with a short fade
}

MARK_MS = 180
ICON_MS = 180
ENTER_MS = 170
FADE_PX = 24                 # how long the fade at the end of a cut title is
AUDIO_PERIOD = 1.4           # seconds of one pulse of the speaker
AUDIO_TICK = 90              # ms between two steps of the pulse


def part(name):
    return bool(PARTS.get(name))


def moving(config, name):
    """Is this touch on and allowed to move now?"""
    return part(name) and effects.on(config)


def accent(widget):
    return widget.palette().color(QPalette.ColorRole.Highlight)


# --- two icons in one, for the fades -------------------------------------
class BlendIconEngine(QIconEngine):
    """a, fading into b: t = 0 shows a, t = 1 shows b."""

    def __init__(self, a, b, t):
        super().__init__()
        self.a, self.b, self.t = QIcon(a), QIcon(b), max(0.0, min(1.0, t))

    def clone(self):
        return BlendIconEngine(self.a, self.b, self.t)

    def paint(self, painter, rect, mode, state):
        painter.save()
        base = painter.opacity()
        if self.t < 1 and not self.a.isNull():
            painter.setOpacity(base * (1 - self.t))
            self.a.paint(painter, rect, Qt.AlignmentFlag.AlignCenter, mode, state)
        if self.t > 0 and not self.b.isNull():
            painter.setOpacity(base * self.t)
            self.b.paint(painter, rect, Qt.AlignmentFlag.AlignCenter, mode, state)
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def actualSize(self, size, mode, state):
        return QSize(size)


def blend_icon(a, b, t):
    return QIcon(BlendIconEngine(a, b, t))


def fade_icon(owner, key, old, new, config, apply, ms=ICON_MS, name="icon_fade"):
    """Show new in place of old with a short fade: apply(icon) is called at each
    step and, at the end, with new itself. Without effects: new at once."""
    fades = owner.__dict__.setdefault("_ike_icon_fades", {})
    anim = fades.get(key)
    running = anim is not None and anim.state() == QVariantAnimation.State.Running
    if (old is None or old.isNull()) and running and moving(config, name):
        anim.ike_to = new                # the same fade goes on, to the newest icon
        return anim
    if anim is not None:
        anim.stop()
        fades.pop(key, None)
    if old is None or old.isNull() or not moving(config, name):
        apply(new)
        return None
    anim = QVariantAnimation(owner)
    anim.ike_to = new
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.ike_last = 0.0

    def step(v):
        # a handful of steps is enough for a 16-pixel icon, and each one asks the tab bar to lay out again
        v = float(v)
        if v - anim.ike_last >= 0.2:
            anim.ike_last = v
            apply(blend_icon(old, anim.ike_to, v))
    anim.valueChanged.connect(step)

    def done():
        if fades.get(key) is anim:
            fades.pop(key, None)
            apply(anim.ike_to)
    anim.finished.connect(done)
    fades[key] = anim
    apply(blend_icon(old, new, 0.0))
    anim.start()
    return anim


# --- a widget inside the window that fades in -----------------------------
def fade_child(widget, config, ms=140):
    """A bar or notice inside the window appears with a short fade (an opacity
    effect that is taken off again at the end)."""
    from PyQt6.QtWidgets import QGraphicsOpacityEffect
    if not moving(config, "bar_fade"):
        return None
    old = getattr(widget, "_ike_child_fade", None)
    if old is not None:
        old.stop()
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QVariantAnimation(widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def step(v):
        try:
            effect.setOpacity(float(v))
        except RuntimeError:               # the effect went with the widget
            anim.stop()

    def done():
        widget._ike_child_fade = None
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)  # nothing left between the bar and the screen
    anim.valueChanged.connect(step)
    anim.finished.connect(done)
    widget._ike_child_fade = anim
    anim.start()
    return anim


# --- the mark of the current tab -------------------------------------------
class MarkGlide(QObject):
    """Where the mark of the current tab is drawn: the target's rectangle, or on
    the way to it after the current tab changed."""

    def __init__(self, widget, config, target):
        super().__init__(widget)
        self.widget, self.config, self.target = widget, config, target
        self._from = None
        self._t = 1.0
        self._shown = None
        self._anim = None

    @property
    def gliding(self):
        return self._anim is not None and self._anim.state() == QVariantAnimation.State.Running

    def current_changed(self, *_):
        start = self._shown
        if start is None or not moving(self.config, "tab_mark") or not self.widget.isVisible():
            if self._anim is not None:
                self._anim.stop()
            self._from = None
            self.widget.update()
            return
        if self._anim is None:
            self._anim = QVariantAnimation(self)
            self._anim.setDuration(MARK_MS)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.valueChanged.connect(self._step)
            self._anim.finished.connect(self._end)
        self._anim.stop()
        self._from, self._t = QRectF(start), 0.0
        self._anim.start()

    def _step(self, v):
        self._t = float(v)
        band = self._band()
        if band is None:
            self.widget.update()
        else:
            self.widget.update(band)

    def _band(self):
        """The part of the widget the mark moves through (only that is painted again)."""
        target = self.target()
        if target is None or self._from is None:
            return None
        return self._from.united(QRectF(target)).adjusted(-2, -2, 2, 2).toAlignedRect()

    def _end(self):
        self._from = None
        self.widget.update()

    def rect(self):
        target = self.target()
        if target is None:
            self._shown = None
            return None
        r = QRectF(target)
        if self._from is not None and self.gliding:
            f, t = self._from, self._t
            r = QRectF(f.x() + (r.x() - f.x()) * t, f.y() + (r.y() - f.y()) * t,
                       f.width() + (r.width() - f.width()) * t, f.height() + (r.height() - f.height()) * t)
        self._shown = r
        return r

    def paint(self, painter):
        if not part("tab_mark"):
            return
        r = self.rect()
        if r is None or r.width() <= 0 or r.height() <= 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent(self.widget))
        radius = min(r.width(), r.height()) / 2
        painter.drawRoundedRect(r, radius, radius)
        painter.restore()


# --- text that fades out at its end ------------------------------------------
_faded = {}                  # titles already drawn faded, for the next paint (a few kB each)

def draw_faded_text(painter, rect, text, colour, font, align, fade=FADE_PX, flags=0, cut=False):
    """Text in rect; when it is wider than rect, or was cut before (cut=True),
    its end fades out instead of ending with "…". Returns True when it faded."""
    from PyQt6.QtGui import QFontMetrics
    rect = QRect(rect)
    if rect.width() <= 0 or rect.height() <= 0 or not text:
        return False
    fm = QFontMetrics(font)
    wide = cut or fm.horizontalAdvance(text) > rect.width()
    painter.save()
    painter.setFont(font)
    painter.setPen(colour)
    if not wide or not part("title_fade"):
        if wide:
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, int(align) | int(flags), text)
        painter.restore()
        return False
    ratio = 1.0
    try:
        ratio = painter.device().devicePixelRatioF() or 1.0
    except AttributeError:
        pass
    key = (text, rect.width(), rect.height(), QColor(colour).rgba(), font.key(), int(align), int(flags), ratio, fade)
    img = _faded.get(key)
    if img is not None:
        painter.drawImage(rect.topLeft(), img)
        painter.restore()
        return True
    img = QImage(max(1, round(rect.width() * ratio)), max(1, round(rect.height() * ratio)),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(ratio)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHints(painter.renderHints())
    p.setFont(font)
    p.setPen(colour)
    left = (int(align) & ~int(Qt.AlignmentFlag.AlignHorizontal_Mask)) | int(Qt.AlignmentFlag.AlignLeft)
    # a cut title ends at the edge of its room: the fade covers its last letters
    p.drawText(QRect(0, 0, rect.width(), rect.height()), (int(align) if cut and fm.horizontalAdvance(text) <= rect.width()
               else left) | int(flags), text)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    g = QLinearGradient(QPointF(max(0, rect.width() - fade), 0), QPointF(rect.width(), 0))
    g.setColorAt(0.0, QColor(0, 0, 0, 255))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(QRectF(0, 0, rect.width(), rect.height()), g)
    p.end()
    if len(_faded) >= 200:
        _faded.clear()
    _faded[key] = img
    painter.drawImage(rect.topLeft(), img)
    painter.restore()
    return True


def pulse(phase):
    """Opacity of the speaker at this point of its pulse (0.45 .. 1)."""
    return 0.45 + 0.55 * (0.5 + 0.5 * math.cos(2 * math.pi * phase))


class TabLabelStyle(QProxyStyle):
    """The desktop's style for the horizontal tabs, except their title: a long
    title fades out at its end, and the speaker of a tab playing sound pulses."""

    def __init__(self):
        super().__init__()
        self.audio_phase = None      # None: no pulse
        self.faded = 0               # how many titles were faded (for the tests)

    def drawControl(self, element, opt, p, widget=None):
        if element != QStyle.ControlElement.CE_TabBarTabLabel or not isinstance(opt, QStyleOptionTab) \
                or not opt.text:
            super().drawControl(element, opt, p, widget)
            return
        text = opt.text
        bare = QStyleOptionTab(opt)
        bare.text = ""
        super().drawControl(element, bare, p, widget)          # the icon, as the desktop draws it
        r = self.baseStyle().subElementRect(QStyle.SubElement.SE_TabBarTabText, opt, widget)
        if self.audio_phase is not None and text.startswith("🔊 ") and part("audio_pulse"):
            from .icons import themed
            side = min(16, r.height())
            box = QRect(r.left(), r.center().y() - side // 2 + 1, side, side)
            p.save()
            p.setOpacity(p.opacity() * pulse(self.audio_phase))
            themed("audio-volume-high").paint(p, box, Qt.AlignmentFlag.AlignCenter)
            p.restore()
            r.setLeft(box.right() + 5)
            text = text[2:].lstrip()
        enabled = bool(opt.state & QStyle.StateFlag.State_Enabled)
        group = QPalette.ColorGroup.Normal if enabled else QPalette.ColorGroup.Disabled
        colour = opt.palette.color(group, QPalette.ColorRole.WindowText)
        flags = Qt.TextFlag.TextShowMnemonic if self.styleHint(QStyle.StyleHint.SH_UnderlineShortcut, opt, widget) \
            else Qt.TextFlag.TextHideMnemonic
        font = widget.font() if widget is not None else p.font()
        cut = widget is not None and opt.tabIndex >= 0 and widget.tabData(opt.tabIndex) == "cut"
        if draw_faded_text(p, r, text, colour, font, Qt.AlignmentFlag.AlignCenter, flags=int(flags), cut=cut):
            self.faded += 1


# --- the address field ---------------------------------------------------------
def field_palette(widget):
    """The colours around the address field (its own Base is see-through)."""
    from PyQt6.QtWidgets import QApplication
    parent = widget.parentWidget()
    return parent.palette() if parent is not None else QApplication.palette(widget)


def paint_pill(widget, level):
    """The rounded frame of the address field; level 0..1: how lit its edge is."""
    pal = field_palette(widget)
    r = QRectF(widget.rect()).adjusted(1, 1, -1, -1)
    radius = r.height() / 2
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(pal.color(QPalette.ColorRole.Base))
    p.drawRoundedRect(r, radius, radius)
    edge = effects.blend(pal.color(QPalette.ColorRole.Mid), pal.color(QPalette.ColorRole.Highlight), level)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(edge, 1.0 + 0.6 * level))
    inset = 0.5 + 0.3 * level
    p.drawRoundedRect(r.adjusted(inset, inset, -inset, -inset), radius - inset, radius - inset)
    if level > 0:                    # a soft ring inside the edge
        ring = QColor(pal.color(QPalette.ColorRole.Highlight))
        ring.setAlphaF(0.22 * level)
        p.setPen(QPen(ring, 2.0))
        d = inset + 1.6
        p.drawRoundedRect(r.adjusted(d, d, -d, -d), radius - d, radius - d)
    p.end()


class SuggestionDelegate(QStyledItemDelegate):
    """Rows of the address suggestions: a little taller, with the site's icon
    (a magnifier for searches)."""

    ROW = 30

    def __init__(self, parent, icon_for):
        super().__init__(parent)
        self.icon_for = icon_for
        self._icons = {}

    def clear(self):
        self._icons.clear()

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        text = index.data() or ""
        ic = self._icons.get(text)
        if ic is None:
            ic = self._icons[text] = self.icon_for(text)
        if ic is not None and not ic.isNull():
            from PyQt6.QtWidgets import QStyleOptionViewItem
            option.icon = ic
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
            option.decorationSize = QSize(16, 16)

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), self.ROW))


# --- the shield (1.1.5) ---------------------------------------------------------
PULSE_MS = 420
PULSE_REST = 1.5             # seconds between two pulses, at least: a page that blocks a lot does not flicker


class ShieldPulse(QWidget):
    """A ring in the accent colour that opens once around the shield when it
    blocks something on the page in view (the touch of the old Cyber theme,
    in the colours of the theme in use)."""

    def __init__(self, button, config):
        super().__init__(button)
        self.config = config
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(PULSE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda _v: self.update())
        self._anim.finished.connect(self.hide)
        self._last = -1e9
        self.fired = 0
        self.hide()

    def fire(self):
        import time
        now = time.monotonic()
        button = self.parentWidget()
        if (now - self._last < PULSE_REST or not moving(self.config, "shield_pulse")
                or button is None or not button.isVisible()):
            return False
        self._last = now
        self.fired += 1
        self.setGeometry(button.rect())
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.start()
        return True

    def paintEvent(self, _event):
        t = float(self._anim.currentValue() or 0.0)
        button = self.parentWidget()
        side = min(self.width(), self.height())
        # the ring opens around the icon, which sits at the left of the button (its number beside it)
        icon = button.iconSize().width() if button is not None else side
        cx = min(self.width() / 2.0, 4 + icon / 2.0 + 2)
        radius = side * (0.30 + 0.22 * t)
        colour = QColor(accent(self))
        colour.setAlpha(round(200 * (1.0 - t)))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(colour, 2.0))
        p.drawEllipse(QPointF(cx, self.height() / 2.0), radius, radius)
        p.end()


class BlockBars(QWidget):
    """What the shield blocked on this site, one bar per kind (the longest
    kind fills the width), in the accent colour of the theme."""

    ROW = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []               # [(label, count)]
        self.setMinimumWidth(240)

    def show_stats(self, rows):
        self.rows = [(label, int(n)) for label, n in rows]
        visible = part("shield_bars") and any(n for _l, n in self.rows)
        self.setFixedHeight(self.ROW * len(self.rows) + 4 if visible else 0)
        self.setVisible(visible)
        self.update()

    def paintEvent(self, _event):
        from PyQt6.QtGui import QFontMetrics
        if not self.rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = QFontMetrics(self.font())
        pal = self.palette()
        text = pal.color(QPalette.ColorRole.WindowText)
        track = QColor(text)
        track.setAlphaF(0.10)
        label_w = min(self.width() // 2, max(fm.horizontalAdvance(lb) for lb, _n in self.rows) + 10)
        num_w = max(fm.horizontalAdvance(str(n)) for _l, n in self.rows) + 8
        top = max(1, max(n for _l, n in self.rows))
        bar_x, bar_w = label_w, max(10, self.width() - label_w - num_w)
        for i, (label, n) in enumerate(self.rows):
            y = 2 + i * self.ROW
            p.setPen(text)
            p.drawText(QRect(0, y, label_w - 6, self.ROW), int(Qt.AlignmentFlag.AlignVCenter), fm.elidedText(
                label, Qt.TextElideMode.ElideRight, label_w - 6))
            bar = QRectF(bar_x, y + self.ROW / 2 - 3, bar_w, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track)
            p.drawRoundedRect(bar, 3, 3)
            if n:
                p.setBrush(accent(self))
                p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(6.0, bar.width() * n / top), 6), 3, 3)
            p.setPen(text)
            p.drawText(QRect(int(bar_x + bar_w), y, num_w, self.ROW),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(n))
        p.end()


# --- the downloads window (1.1.5) ------------------------------------------------
FRACTION_ROLE = Qt.ItemDataRole.UserRole + 11


class ProgressDelegate(QStyledItemDelegate):
    """The progress column: a slim rounded bar under the size, in the accent colour."""

    ROW = 34

    def paint(self, painter, option, index):
        fraction = index.data(FRACTION_ROLE)
        if fraction is None or not part("download_rows"):
            super().paint(painter, option, index)
            return
        from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        r = QRect(option.rect).adjusted(6, 3, -8, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        colour = option.palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(colour)
        painter.drawText(QRect(r.x(), r.y(), r.width(), r.height() - 8),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        bar = QRectF(r.x(), r.bottom() - 5, r.width(), 4)
        track = QColor(colour)
        track.setAlphaF(0.15)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, 2, 2)
        f = max(0.0, min(1.0, float(fraction)))
        if f > 0:
            painter.setBrush(option.palette.color(QPalette.ColorRole.Highlight) if not selected else colour)
            painter.drawRoundedRect(QRectF(bar.x(), bar.y(), max(4.0, bar.width() * f), bar.height()), 2, 2)
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), self.ROW if part("download_rows") else 0))


# --- the edge between the bars and the page (1.1.6) ------------------------------
class ChromeEdge(QWidget):
    """A thin line along the top of the page area: the bars of the window stand
    apart from the page a little better. Drawn over the page's first pixel row,
    under the loading line."""

    def __init__(self, anchor):
        super().__init__(anchor.parentWidget())
        from PyQt6.QtCore import QEvent
        self._resize = QEvent.Type.Resize, QEvent.Type.Move
        self.anchor = anchor
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        anchor.installEventFilter(self)
        self._place()
        self.setVisible(part("chrome_edge"))

    def _place(self):
        g = self.anchor.geometry()
        self.setGeometry(QRect(g.x(), g.y(), g.width(), 1))
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.anchor and event.type() in self._resize:
            self._place()
        return False

    def paintEvent(self, _event):
        c = QColor(self.palette().color(QPalette.ColorRole.Mid))
        c.setAlphaF(0.55)
        p = QPainter(self)
        p.fillRect(self.rect(), c)
        p.end()


# --- short messages in a pill (1.1.7) ---------------------------------------------
class Toast(QWidget):
    """A short message in a rounded pill at the bottom of the page area, which
    fades in and out (in place of the status bar line)."""

    MARGIN = 26

    def __init__(self, anchor, config):
        super().__init__(anchor.parentWidget())
        from PyQt6.QtCore import QEvent, QTimer
        self._events = QEvent.Type.Resize, QEvent.Type.Move
        self.anchor, self.config = anchor, config
        self.text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(self._fade_out)
        self._opacity = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_opacity)
        self._anim.finished.connect(self._done)
        anchor.installEventFilter(self)
        self.hide()

    def _set_opacity(self, v):
        self._opacity = float(v)
        self.update()

    def show_text(self, text, ms=1800):
        from PyQt6.QtGui import QFontMetrics
        self.text = text
        f = self.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(self.parentWidget().font().pointSizeF() * 1.05)
            self.setFont(f)
        fm = QFontMetrics(self.font())
        w = min(fm.horizontalAdvance(text) + 36, max(120, self.anchor.width() - 40))
        self.resize(w, fm.height() + 18)
        self._place()
        self._anim.stop()
        if moving(self.config, "toasts") and not self.isVisible():
            self._fading_out = False
            self._anim.setDuration(140)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._opacity = 0.0
            self._anim.start()
        else:
            self._opacity = 1.0
        self.show()
        self.raise_()
        self.update()
        self._hide.start(ms)

    def _fade_out(self):
        if not moving(self.config, "toasts"):
            self.hide()
            return
        self._fading_out = True
        self._anim.stop()
        self._anim.setDuration(220)
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _done(self):
        if getattr(self, "_fading_out", False):
            self._fading_out = False
            self.hide()

    def _place(self):
        g = self.anchor.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + g.height() - self.height() - self.MARGIN)

    def eventFilter(self, obj, event):
        if obj is self.anchor and event.type() in self._events and self.isVisible():
            self._place()
        return False

    def paintEvent(self, _event):
        pal = self.palette()
        bg = effects.blend(pal.color(QPalette.ColorRole.Window), pal.color(QPalette.ColorRole.WindowText), 0.08)
        bg.setAlphaF(0.96)
        edge = QColor(pal.color(QPalette.ColorRole.Mid))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(edge, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(pal.color(QPalette.ColorRole.WindowText))
        from PyQt6.QtGui import QFontMetrics
        p.drawText(self.rect().adjusted(16, 0, -16, 0), int(Qt.AlignmentFlag.AlignCenter),
                   QFontMetrics(self.font()).elidedText(self.text, Qt.TextElideMode.ElideRight, self.width() - 32))
        p.end()


# --- "+N" over the shield (1.1.7) ---------------------------------------------------
class ShieldCount(QWidget):
    """When the shield's number grows, a small "+N" in the accent colour rises
    beside the number and fades (several blocks close together count as one).
    It is drawn right of the number, never over the shield icon (1.1.8: over
    the icon, in the colour of the icon's edge, it could not be seen)."""

    MS = 1100
    HOLD = 0.4          # fully visible for the first part, then it fades
    ROOM = 34           # px right of the button for the "+N"

    def __init__(self, button, config):
        super().__init__(button.parentWidget())
        self.button, self.config = button, config
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.delta = 0
        self.last = None
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda _v: self.update())
        self._anim.finished.connect(self._finished)
        self.shown = 0                 # how many times it rose (for the tests)
        self.hide()

    def count(self, n, key=None):
        """The shield shows n now, for key (the site in view: another site's
        number is no growth)."""
        old, self.last = self.last, n
        same, self.key = getattr(self, "key", None) == key, key
        if (old is None or not same or n <= old or not moving(self.config, "shield_count")
                or not self.button.isVisible()):
            return False
        running = self._anim.state() == QVariantAnimation.State.Running
        self.delta = (self.delta if running else 0) + (n - old)
        b = self.button.geometry()
        self.setGeometry(b.x(), b.y(), b.width() + self.ROOM, b.height())
        self.show()
        self.raise_()
        if not running:
            self.shown += 1
            self._anim.start()
        return True

    def _finished(self):
        self.delta = 0
        self.hide()

    def text_left(self):
        """Where the "+N" starts: right of the shield icon and of the number."""
        from PyQt6.QtGui import QFontMetrics
        b = self.button
        fm = QFontMetrics(b.font())
        return b.iconSize().width() + 8 + fm.horizontalAdvance(b.text() or "0") + 3

    def alpha(self, t):
        return 1.0 if t <= self.HOLD else max(0.0, 1.0 - (t - self.HOLD) / (1.0 - self.HOLD))

    def paintEvent(self, _event):
        from PyQt6.QtGui import QFontMetrics, QPainterPath
        t = float(self._anim.currentValue() or 0.0)
        a = self.alpha(t)
        if a <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = self.button.font()
        f.setBold(True)
        fm = QFontMetrics(f)
        text = "+%d" % self.delta
        h = self.height()
        # from just below the middle up towards the top edge
        base = round(h * 0.5 + fm.ascent() / 2 - t * h * 0.32)
        path = QPainterPath()
        path.addText(QPointF(self.text_left(), base), f, text)
        halo = QColor(self.button.palette().color(QPalette.ColorRole.Window))
        halo.setAlphaF(0.85 * a)
        p.setPen(QPen(halo, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        c = QColor(accent(self.button))
        c.setAlphaF(a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPath(path)
        p.end()
