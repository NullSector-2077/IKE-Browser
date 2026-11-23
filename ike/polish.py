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

import functools
import math

from PyQt6.QtCore import QEasingCurve, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QIcon, QIconEngine, QImage, QLinearGradient, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QLabel, QProxyStyle, QStyle, QStyledItemDelegate, QStyleOptionTab, QToolButton, QWidget

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
    "vtabs_edge": True,      # 1.1.19: the sliding vertical tabs' panel ends in a separator line, as in Dolphin
    # 1.1.7
    "toasts": True,          # short messages (zoom, notes) in a rounded pill over the page, not the status bar
    "find_pill": True,       # find bar: "3 of 12" in a pill, the field tinted when nothing is found
    "shield_count": True,    # a small "+N" rises from the shield when its number grows
    "panel_icons": True,     # the site's icon beside its name in the shield and site panels
    "settings_fade": True,   # Settings: the pages change with a short fade
    # 1.1.9
    "star_pop": True,        # the bookmark star fills with a small pop when a page is saved
    "shield_fade": True,     # the shield's icon fades from one protection level to the next
    "tab_unseen": True,      # a dot on a background tab that finished loading, until it is opened
    "vtab_close": True,      # vertical tabs: a closed row fades out
    "toolbar_hover": True,   # toolbar buttons: a soft round highlight under the mouse, as the window buttons
    "bars_grow": True,       # the shield panel's bars grow from zero when it opens
    # 1.1.23
    "tab_hover": True,       # horizontal tabs: the hover colour comes and goes softly
    "tab_enter": True,       # horizontal tabs: a new tab's title and icon fade in
    "tab_close": True,       # horizontal tabs: a closed tab fades out
}

MARK_MS = 180
# 1.1.23: one corner radius for everything I.K.E. draws (Breeze's frame
# radius); thin bars take half of it
RADIUS = 5.0
FRAME_MS = 1 / 30            # the "+N" and the ring of the shield: 30 pictures a second
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
        self.square = False          # square ends (the horizontal tabs, as Breeze's line)

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
        if self.square:
            painter.fillRect(r, accent(self.widget))
            painter.restore()
            return
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

    _TAB_PARTS = (QStyle.ControlElement.CE_TabBarTab, QStyle.ControlElement.CE_TabBarTabShape,
                  QStyle.ControlElement.CE_TabBarTabLabel)

    def __init__(self):
        super().__init__()
        self.audio_phase = None      # None: no pulse
        self.faded = 0               # how many titles were faded (for the tests)
        self.skipped = 0             # tabs not drawn: outside the part being painted (for the tests)
        self._shape_drawn = False

    # what a style may draw of a tab beyond its own rectangle (the current
    # tab of some styles overlaps its neighbours)
    BEYOND = 8

    # A note for whoever changes these methods: the option the style is given
    # lives on the caller's stack. Its parts (opt.rect, opt.palette...) are
    # read from a copy made here (QStyleOptionTab(opt)), or asked of the
    # widget: in PyQt 6.12 a part read from the given option at every paint
    # left a Python object of a dead option behind, which a later option at
    # the same place then became (a button's text read as garbage, and a
    # crash) (1.1.23).
    def drawControl(self, element, opt, p, widget=None):
        if element in self._TAB_PARTS and isinstance(opt, QStyleOptionTab):
            area = getattr(widget, "painting", None)
            if area is not None and not area.intersects(widget.tabRect(opt.tabIndex).adjusted(
                    -self.BEYOND, -self.BEYOND, self.BEYOND, self.BEYOND)):
                self.skipped += 1
                return                 # outside the part being painted (1.1.23)
            if element != QStyle.ControlElement.CE_TabBarTabLabel and getattr(widget, "hovering", False):
                self._tab_with_hover(element, opt, p, widget)
                return
        if element == QStyle.ControlElement.CE_TabBarTabLabel and isinstance(opt, QStyleOptionTab) \
                and getattr(widget, "_enter", None) is not None:
            k = widget.enter_level(opt.tabIndex)
            if k < 1.0:                # a new tab: its title and icon fade in (1.1.23)
                p.save()
                p.setOpacity(p.opacity() * k)
                try:
                    self._label(element, opt, p, widget)
                finally:
                    p.restore()
                return
        self._label(element, opt, p, widget)

    def _tab_with_hover(self, element, opt, p, widget):
        """The tab as the desktop draws it without its own hover, and Breeze's
        hover colour over its shape, at the level its fade has reached (1.1.23:
        the desktop's hover came and went at once)."""
        o = QStyleOptionTab(opt)
        o.state &= ~QStyle.StateFlag.State_MouseOver
        level = 0.0
        if not opt.state & QStyle.StateFlag.State_Selected and opt.state & QStyle.StateFlag.State_Enabled:
            level = widget.hover_level(opt.tabIndex)
        if element == QStyle.ControlElement.CE_TabBarTab:
            self._shape_drawn = False
            super().drawControl(element, o, p, widget)
            if not self._shape_drawn and level > 0:
                self._hover_over(o, p, widget, level)       # a style that draws the shape itself
            return
        super().drawControl(element, o, p, widget)
        self._shape_drawn = True
        if level > 0:
            self._hover_over(o, p, widget, level)

    @staticmethod
    def _hover_over(opt, p, widget, level):
        fill, _edge = hover_fill(widget.palette(), level)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(opt.rect).adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        p.restore()

    def _label(self, element, opt, p, widget):
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
        self._anim.valueChanged.connect(self._frame)
        self._anim.finished.connect(self.hide)
        self._last = -1e9
        self._painted_at = -1e9
        self.fired = 0
        self.hide()

    def resting(self):
        """True while the ring may not open again (PULSE_REST after the last one)."""
        import time
        return time.monotonic() - self._last < PULSE_REST

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

    def _frame(self, _v):
        # 30 pictures a second (1.1.23): each one repaints the address field
        # and the toolbar under the ring
        import time
        now = time.monotonic()
        if now - self._painted_at >= FRAME_MS:
            self._painted_at = now
            self.update()

    STEPS = 32               # pictures of the ring per pulse, drawn once and kept (1.1.18)

    def paintEvent(self, _event):
        t = float(self._anim.currentValue() or 0.0)
        # the ring at the nearest of STEPS moments (about one frame apart: the same
        # to the eye as drawing it anew at each frame, and much cheaper)
        step = max(0, min(self.STEPS, round(t * self.STEPS)))
        dpr = self.devicePixelRatioF()
        button = self.parentWidget()
        icon = button.iconSize().width() if button is not None else 0
        key = (self.width(), self.height(), icon, dpr, QColor(accent(self)).rgba())
        if getattr(self, "_rings_key", None) != key:
            self._rings_key, self._rings = key, {}
        pm = self._rings.get(step)
        if pm is None:
            pm = self._rings[step] = self._ring(step / self.STEPS, dpr)
        p = QPainter(self)
        p.drawPixmap(0, 0, pm)
        p.end()

    def _ring(self, t, dpr):
        button = self.parentWidget()
        side = min(self.width(), self.height())
        # the ring opens around the icon, which sits at the left of the button (its number beside it)
        icon = button.iconSize().width() if button is not None else side
        cx = min(self.width() / 2.0, 4 + icon / 2.0 + 2)
        radius = side * (0.30 + 0.22 * t)
        colour = QColor(accent(self))
        colour.setAlpha(round(200 * (1.0 - t)))
        pm = QPixmap(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(colour, 2.0))
        p.drawEllipse(QPointF(cx, self.height() / 2.0), radius, radius)
        p.end()
        return pm


class BlockBars(QWidget):
    """What the shield blocked on this site, one bar per kind (the longest
    kind fills the width), in the accent colour of the theme."""

    ROW = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []               # [(label, count)]
        self.setMinimumWidth(240)
        self.k = 1.0                 # how far the bars have grown (1.1.9: from 0 when the panel opens)
        self._grow = None

    def grow(self, config, ms=380):
        """The bars grow from zero to their length (when the shield panel opens)."""
        if self._grow is not None:
            self._grow.stop()
        if not moving(config, "bars_grow") or self.isHidden() or not any(n for _l, n in self.rows):
            self.k = 1.0             # nothing to show (no blocks here): no animation either
            return
        a = self._grow = QVariantAnimation(self)
        a.setDuration(ms)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.valueChanged.connect(lambda v: (setattr(self, "k", float(v)), self.update()))
        self.k = 0.0
        a.start()

    def hideEvent(self, event):
        # the panel closed: nothing goes on growing out of sight
        if self._grow is not None:
            self._grow.stop()
        self.k = 1.0
        super().hideEvent(event)

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
            p.drawRoundedRect(bar, RADIUS / 2, RADIUS / 2)
            if n:
                p.setBrush(accent(self))
                p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(6.0, bar.width() * n / top * self.k), 6),
                                  RADIUS / 2, RADIUS / 2)
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
    apart from the page a little better, in the colour of Breeze's separators.

    1.1.23: the page area keeps its first pixel row for it (it was drawn over
    the page's first row: every frame of a scrolling page, a video or an
    animation repainted it, 60 times a second)."""

    def __init__(self, anchor):
        super().__init__(anchor.parentWidget())
        from PyQt6.QtCore import QEvent
        self._resize = QEvent.Type.Resize, QEvent.Type.Move
        self.anchor = anchor
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        anchor.installEventFilter(self)
        if part("chrome_edge"):
            m = anchor.contentsMargins()
            anchor.setContentsMargins(m.left(), 1, m.right(), m.bottom())
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
        p = QPainter(self)
        p.fillRect(self.rect(), separator(self.palette()))
        p.end()


class VTabsEdge(QWidget):
    """The right edge of the vertical tabs' panel (1.1.19, the owner's request):
    a one-pixel separator in the colour Breeze gives its separators (a quarter
    of the way from the window's background to its text, as in Dolphin's side
    panels), shown whenever the panel is (pinned, or opened from its hidden
    edge). A plain line: no animation, no timer, drawn once per resize."""

    def __init__(self, panel):
        super().__init__(panel)
        from PyQt6.QtCore import QEvent
        self._resize = QEvent.Type.Resize, QEvent.Type.Show
        self.panel = panel
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        panel.installEventFilter(self)
        self._place()
        self.setVisible(part("vtabs_edge"))

    def _place(self):
        self.setGeometry(QRect(self.panel.width() - 1, 0, 1, self.panel.height()))
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.panel and event.type() in self._resize:
            self._place()
        return False

    @staticmethod
    def colour(palette):
        return separator(palette)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.colour(self.palette()))
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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(separator(pal), 1.0))
        p.setBrush(bg)
        p.drawRoundedRect(r, TOAST_RADIUS, TOAST_RADIUS)
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

    def __init__(self, button, config, host=None):
        super().__init__(host or button.parentWidget())
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
        # 1.1.18: only the column of the "+N" is painted again at each step;
        # the whole widget made the window repaint the address field and the
        # shield under it at every frame while a page loaded
        # 1.1.23: 30 pictures a second, not one per frame of the screen
        self._anim.valueChanged.connect(self._frame)
        self._anim.finished.connect(self._finished)
        self._painted_at = -1e9
        self.frames = 0                # pictures asked for (for the tests)
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
        b = self.button
        at = b.mapTo(self.parentWidget(), QPoint(0, 0)) if b.parentWidget() is not self.parentWidget() else b.pos()
        self.setGeometry(at.x(), at.y(), b.width() + self.ROOM, b.height())
        self.show()
        self.raise_()
        if not running:
            self.shown += 1
            self._anim.start()
        return True

    def _frame(self, v):
        import time
        now = time.monotonic()
        if now - self._painted_at >= FRAME_MS or float(v) >= 1.0:
            self._painted_at = now
            self.frames += 1
            self.update(self._band())

    def _finished(self):
        self.delta = 0
        self.hide()

    def text_left(self):
        """Where the "+N" starts: right of the shield icon and of the number."""
        from PyQt6.QtGui import QFontMetrics
        b = self.button
        fm = QFontMetrics(b.font())
        return b.iconSize().width() + 8 + fm.horizontalAdvance(b.text() or "0") + 3

    def _band(self):
        """The part of the widget the "+N" moves through."""
        x = max(0, self.text_left() - 4)
        return QRect(x, 0, max(0, self.width() - x), self.height())

    def alpha(self, t):
        return 1.0 if t <= self.HOLD else max(0.0, 1.0 - (t - self.HOLD) / (1.0 - self.HOLD))

    def paintEvent(self, _event):
        from PyQt6.QtGui import QFontMetrics
        t = float(self._anim.currentValue() or 0.0)
        a = self.alpha(t)
        if a <= 0:
            return
        f = self.button.font()
        f.setBold(True)
        fm = QFontMetrics(f)
        h = self.height()
        # from just below the middle up towards the top edge
        base = round(h * 0.5 + fm.ascent() / 2 - t * h * 0.32)
        pm, ox, oy = self._picture(f)
        p = QPainter(self)
        p.setOpacity(a)
        p.drawPixmap(self.text_left() + ox, base + oy, pm)
        p.end()

    def _picture(self, f):
        """The "+N" with its halo, drawn once per number and look and then
        only moved and faded (1.1.18: it was drawn as shapes at every frame of
        the animation). Returns the picture and where it starts from the baseline."""
        from PyQt6.QtGui import QPainterPath
        text = "+%d" % self.delta
        halo = QColor(self.button.palette().color(QPalette.ColorRole.Window))
        halo.setAlphaF(0.85)
        c = QColor(accent(self.button))
        dpr = self.devicePixelRatioF()
        key = (text, f.key(), halo.rgba(), c.rgba(), dpr)
        if getattr(self, "_pic_key", None) != key:
            path = QPainterPath()
            path.addText(QPointF(0, 0), f, text)
            r = path.boundingRect().adjusted(-3, -3, 3, 3)
            ox, oy = math.floor(r.x()), math.floor(r.y())
            w, h = math.ceil(r.right()) - ox, math.ceil(r.bottom()) - oy
            pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(-ox, -oy)
            p.setPen(QPen(halo, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawPath(path)
            p.end()
            self._pic_key, self._pic = key, (pm, ox, oy)
        return self._pic


# --- 1.1.9 ------------------------------------------------------------------------
class PopIconEngine(QIconEngine):
    """An icon coming in with a small pop: it grows past its size and settles,
    while a thin ring in the accent colour opens around it and fades."""

    def __init__(self, base, t, colour):
        super().__init__()
        self.base, self.t, self.colour = QIcon(base), max(0.0, min(1.0, t)), QColor(colour)

    def clone(self):
        return PopIconEngine(self.base, self.t, self.colour)

    def paint(self, painter, rect, mode, state):
        t = self.t
        # 0.55 -> 1.18 -> 1.0 (a quick grow past the size, then back)
        k = 0.55 + 0.63 * min(1.0, t / 0.6) if t < 0.6 else 1.18 - 0.18 * (t - 0.6) / 0.4
        side = min(rect.width(), rect.height())
        c = QPointF(rect.center())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QColor(self.colour)
        ring.setAlphaF(max(0.0, 0.8 * (1.0 - t)))
        painter.setPen(QPen(ring, max(1.2, side / 14.0)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rad = side * (0.3 + 0.22 * t)
        painter.drawEllipse(c, rad, rad)
        s = side * k
        self.base.paint(painter, QRect(round(c.x() - s / 2), round(c.y() - s / 2), round(s), round(s)),
                        Qt.AlignmentFlag.AlignCenter, mode, state)
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


def pop_in(owner, key, new, config, apply, ms=380):
    """Show the icon new with a small pop (star_pop); without effects at once."""
    anims = owner.__dict__.setdefault("_ike_pops", {})
    old = anims.pop(key, None)
    if old is not None:
        old.stop()
    if not moving(config, "star_pop"):
        apply(new)
        return None
    colour = accent(owner)
    anim = QVariantAnimation(owner)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.valueChanged.connect(lambda v: apply(QIcon(PopIconEngine(new, float(v), colour))))

    def done():
        if anims.get(key) is anim:
            anims.pop(key, None)
        apply(new)
    anim.finished.connect(done)
    anims[key] = anim
    anim.start()
    return anim


def popping(owner, key):
    a = owner.__dict__.get("_ike_pops", {}).get(key)
    return a is not None and a.state() == QVariantAnimation.State.Running


class UnseenIconEngine(QIconEngine):
    """A tab's icon with a small dot in the accent colour: the page finished
    loading in the background and was not looked at yet."""

    def __init__(self, base, colour, edge):
        super().__init__()
        self.base, self.colour, self.edge = QIcon(base), QColor(colour), QColor(edge)

    def clone(self):
        return UnseenIconEngine(self.base, self.colour, self.edge)

    def paint(self, painter, rect, mode, state):
        self.base.paint(painter, rect, Qt.AlignmentFlag.AlignCenter, mode, state)
        side = min(rect.width(), rect.height())
        d = max(5.0, side * 0.42)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.edge, max(1.2, side / 12.0)))
        painter.setBrush(self.colour)
        painter.drawEllipse(QRectF(rect.right() + 1 - d, rect.bottom() + 1 - d, d - 1, d - 1))
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


def unseen_icon(base, palette):
    return QIcon(UnseenIconEngine(base, palette.color(QPalette.ColorRole.Highlight),
                                  palette.color(QPalette.ColorRole.Window)))


def ghost_out(view, rect, config, ms=170, name="vtab_close"):
    """A picture of rect of view (a list's viewport, the tab bar) laid over it,
    fading out: a closed row or tab goes away softly while the list itself
    changes at once."""
    from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel
    if not moving(config, name) or not view.isVisible() or rect.isEmpty():
        return None
    shot = QLabel(view)
    shot.setObjectName("ike_row_ghost")
    shot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    shot.setPixmap(view.grab(rect))
    shot.setGeometry(rect)
    effect = QGraphicsOpacityEffect(shot)
    shot.setGraphicsEffect(effect)
    anim = QVariantAnimation(shot)
    anim.setDuration(ms)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def step(v):
        try:
            effect.setOpacity(float(v))
        except RuntimeError:
            anim.stop()
    anim.valueChanged.connect(step)
    anim.finished.connect(shot.deleteLater)
    shot.show()
    shot.raise_()
    anim.start()
    return shot


HOVER_RADIUS = RADIUS    # 1.1.16: flat on top and bottom, soft corners (1.1.23: Breeze's radius, was 6)
TOAST_RADIUS = RADIUS    # 1.1.23: was 8


def separator(palette):
    """Breeze's separator colour: the window's background mixed a quarter of
    the way to its text, as in Dolphin's side panels (1.1.19); every line
    I.K.E. draws between parts of the window has it (1.1.23)."""
    bg = palette.color(QPalette.ColorRole.Window)
    fg = palette.color(QPalette.ColorRole.WindowText)
    mix = 0.25
    return QColor(round(bg.red() + (fg.red() - bg.red()) * mix),
                  round(bg.green() + (fg.green() - bg.green()) * mix),
                  round(bg.blue() + (fg.blue() - bg.blue()) * mix))


def keyboard_focus(widget, opt=None):
    """True when widget has the focus and it came from the keyboard (Tab):
    a mouse click shows no ring, as in Breeze."""
    if opt is not None:
        return bool(opt.state & QStyle.StateFlag.State_HasFocus
                    and opt.state & QStyle.StateFlag.State_KeyboardFocusChange)
    return bool(widget is not None and widget.hasFocus()
                and widget.window().testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange))


def focus_ring(painter, rect, palette, radius=None):
    """Breeze's focus: a 1-px ring in the Highlight colour around the shape
    (radius None: a circle)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    r = QRectF(rect)
    if radius is None:
        painter.drawEllipse(r)
    else:
        painter.drawRoundedRect(r, radius, radius)
    painter.restore()


def hover_fill(palette, level):
    """Breeze's hover on a flat button: the Highlight colour mixed a fifth into
    the background (a little more while pressed), with a 1-px outline."""
    fill = QColor(palette.color(QPalette.ColorRole.Highlight))
    fill.setAlphaF(max(0.0, min(0.3, 0.2 * level)))
    edge = QColor(palette.color(QPalette.ColorRole.Highlight))
    edge.setAlphaF(max(0.0, min(1.0, 0.85 * level)))
    return fill, edge


def soft_edge(rect, colour, strength):
    """A thin outline that fades from the top down: discreet, in the theme's colour."""
    from PyQt6.QtGui import QLinearGradient
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    top, bottom = QColor(colour), QColor(colour)
    top.setAlphaF(max(0.0, min(1.0, strength)))
    bottom.setAlphaF(max(0.0, min(1.0, strength * 0.25)))
    g.setColorAt(0.0, top)
    g.setColorAt(1.0, bottom)
    return QPen(g, 1.0)


# --- a private window (1.1.23) ------------------------------------------------------
PRIVATE_PURPLE = QColor("#8e44ad")   # Plasma's purple, mixed into the theme's own colours
PRIVATE_MIX = 0.15


def private_tint():
    """The toolbar of a private window: Plasma's purple laid over the theme's
    own toolbar at PRIVATE_MIX, so it is mixed into it, light or dark."""
    c = QColor(PRIVATE_PURPLE)
    c.setAlphaF(PRIVATE_MIX)
    return c


class PrivateBadge(QLabel):
    """"Private" in a rounded badge on the toolbar of a private window: the
    private-browsing icon of the desktop's theme before the text, a fill of
    purple mixed into the highlight colour, and a 1-px border a shade darker
    (light themes) or lighter (dark themes) than the fill. A label: its text
    is measured as every other text of the window (the text-fit tests)."""

    PAD_X, PAD_Y, GAP, ICON = 10, 3, 6, 16

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        from .icons import themed
        self.setObjectName("privateWindowBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = themed(("view-private", "security-high"))
        self._restyle()

    def colours(self):
        pal = self.palette()
        fill = effects.blend(pal.color(QPalette.ColorRole.Highlight), PRIVATE_PURPLE, 0.35)
        dark_theme = pal.color(QPalette.ColorRole.Window).lightnessF() < 0.5
        edge = fill.lighter(140) if dark_theme else fill.darker(135)
        from .uistyle import readable
        text = readable(pal.color(QPalette.ColorRole.HighlightedText), fill, QColor("#ffffff"))
        return fill, edge, text

    def _restyle(self):
        fill, edge, text = self.colours()
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        icon_room = self.PAD_X + self.ICON + self.GAP
        sheet = ("#privateWindowBadge { background: %s; color: %s; border: 1px solid %s; border-radius: %dpx;"
                 " font-weight: 600; padding: %dpx %dpx %dpx %dpx; }" % (
                     fill.name(), text.name(), edge.name(), round(RADIUS + 2), self.PAD_Y,
                     icon_room if rtl else self.PAD_X, self.PAD_Y, self.PAD_X if rtl else icon_room))
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)

    def changeEvent(self, event):
        super().changeEvent(event)
        from PyQt6.QtCore import QEvent
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.LayoutDirectionChange):
            self._restyle()          # a theme changed: the colours follow (the same sheet is not set again)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        r = QRect(self.PAD_X + 1, (self.height() - self.ICON) // 2, self.ICON, self.ICON)
        self.icon.paint(p, QStyle.visualRect(self.layoutDirection(), self.rect(), r),
                        Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Selected)
        p.end()


# --- popups: one radius and a light shadow (1.1.23) ---------------------------------
POPUP_SHADOW = 6             # px of soft shadow around a popup I.K.E. paints itself


def _base_style_name():
    from PyQt6.QtWidgets import QApplication
    st = QApplication.style()
    base = st.baseStyle() if hasattr(st, "baseStyle") else st
    return (base.name() if base is not None else "").lower()


def native_popups():
    """True where the widget style draws the menus' own rounded frame and has
    the compositor draw their shadow (Breeze and Oxygen ask KWin for it,
    Kvantum's themes have their own): those menus are left as they are."""
    name = _base_style_name()
    return name in ("breeze", "oxygen") or "kvantum" in name


def translucent_popups():
    """A popup can be see-through around its shape (Wayland, and the tests'
    offscreen screen); on X11 the corners are cut instead, without a shadow
    (an X11 desktop may have no compositor: see-through would be black)."""
    from PyQt6.QtGui import QGuiApplication
    return QGuiApplication.platformName() != "xcb"


def paint_popup_panel(p, rect, palette, shadow):
    """The rounded panel of a popup inside rect, its light shadow around it
    (shadow px), and the separators' colour on its edge."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inner = QRectF(rect).adjusted(shadow + 0.5, shadow + 0.5, -shadow - 0.5, -shadow - 0.5)
    if shadow:
        p.setPen(Qt.PenStyle.NoPen)
        dark = palette.color(QPalette.ColorRole.Window).lightnessF() < 0.5
        for i in range(shadow, 0, -1):
            c = QColor(0, 0, 0, round((40 if dark else 26) * (1 - (i - 1) / shadow) ** 2))
            p.setBrush(c)
            p.drawRoundedRect(inner.adjusted(-i, -i + 1, i, i + 1), RADIUS + i, RADIUS + i)
    p.setPen(QPen(separator(palette), 1.0))
    p.setBrush(palette.color(QPalette.ColorRole.Window))
    p.drawRoundedRect(inner, RADIUS, RADIUS)
    p.restore()


def _rounded_mask(widget, shadow):
    from PyQt6.QtGui import QPainterPath, QRegion
    path = QPainterPath()
    path.addRoundedRect(QRectF(widget.rect()).adjusted(shadow, shadow, -shadow, -shadow), RADIUS, RADIUS)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


class PopupPanelStyle(QProxyStyle):
    """The style of a menu that holds one of I.K.E.'s panels (the shield, the
    site information): the desktop's, except its panel, which is the rounded
    panel with its shadow (paint_popup_panel). Only for styles whose menus
    have no shadow of their own (native_popups)."""

    def __init__(self, shadow):
        super().__init__()
        self.shadow = shadow

    def drawPrimitive(self, element, opt, p, widget=None):
        if element == QStyle.PrimitiveElement.PE_PanelMenu and widget is not None:
            paint_popup_panel(p, widget.rect(), widget.palette(), self.shadow)
            return
        if element == QStyle.PrimitiveElement.PE_FrameMenu and widget is not None:
            return
        super().drawPrimitive(element, opt, p, widget)

    def pixelMetric(self, metric, opt=None, widget=None):
        v = super().pixelMetric(metric, opt, widget)
        if metric == QStyle.PixelMetric.PM_MenuPanelWidth:
            return max(v, 1) + self.shadow
        return v


class _RoundMenu(QObject):
    def __init__(self, menu):
        super().__init__(menu)
        self.menu = menu
        self.shadow = POPUP_SHADOW if translucent_popups() else 0
        self.style = PopupPanelStyle(self.shadow)        # kept here: a widget does not own its style
        menu.setStyle(self.style)
        menu.setProperty("_KDE_NET_WM_SKIP_SHADOW", True)       # its shadow is painted: none from KWin
        if self.shadow:
            menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.menu and event.type() == QEvent.Type.Resize and not self.shadow:
            _rounded_mask(self.menu, 0)
        return False


def round_menu(menu):
    """The menu of a panel with the one radius and Breeze's light shadow,
    where the widget style does not give its menus their own (1.1.23)."""
    if native_popups() or getattr(menu, "_ike_round", None) is not None:
        return menu
    menu._ike_round = _RoundMenu(menu)
    return menu


class _RoundList(QObject):
    """The address bar's suggestions: the rounded panel with its shadow
    painted around the list; the list keeps the size and place the
    completer gives it, the panel's room is added around it."""

    def __init__(self, view):
        super().__init__(view)
        from PyQt6.QtWidgets import QFrame
        self.view = view
        self.shadow = POPUP_SHADOW if translucent_popups() else 0
        self.room = self.shadow + 1
        self._busy = False
        self._given = None
        view.setProperty("_KDE_NET_WM_SKIP_SHADOW", True)
        if self.shadow:
            view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.viewport().setAutoFillBackground(False)
        view.setViewportMargins(self.room, self.room, self.room, self.room)
        view.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        t = event.type()
        if obj is not self.view:
            return False
        if t == QEvent.Type.Paint:
            p = QPainter(self.view)
            paint_popup_panel(p, self.view.rect(), self.view.palette(), self.shadow)
            p.end()
            return False
        if t in (QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.Resize) and not self._busy:
            g = self.view.geometry()
            if g != self._given:
                # the completer placed the list: the room for the panel around it
                self._busy = True
                try:
                    self._given = g.adjusted(-self.room, -self.room, self.room, self.room)
                    self.view.setGeometry(self._given)
                    if not self.shadow:
                        _rounded_mask(self.view, 0)
                finally:
                    self._busy = False
        elif t == QEvent.Type.Hide:
            self._given = None
        return False


def round_list_popup(view):
    """The address bar's suggestions with the one radius and the light
    shadow, in every style (1.1.23)."""
    if getattr(view, "_ike_round", None) is None:
        view._ike_round = _RoundList(view)
    return view


class RoundHoverStyle(QProxyStyle):
    """Toolbar buttons with the desktop's style, except their hover: a soft
    highlight in the theme's colour, a rectangle with rounded corners and a
    faint fading outline, comes in and goes (its level is the button's
    "ike_hover" property, set by HoverGlides). The window buttons keep their
    own round one.

    1.1.23 (the owner): a button whose menu opens with a click (the ☰ menu,
    dark mode for pages: their property "ike_no_arrow", opening at once)
    shows its icon only, with no arrow and no part of its own for one, in
    every widget style: the style is given the button as one without a
    menu (Qt's own styles draw a small arrow in a corner otherwise)."""

    NO_ARROW = "ike_no_arrow"

    @staticmethod
    def _plain(opt, widget):
        """A copy of the option of a button that shows no arrow, as one without a
        menu (the given option itself is never changed nor read further)."""
        from PyQt6.QtWidgets import QStyleOptionToolButton
        if widget is None or not widget.property(RoundHoverStyle.NO_ARROW) \
                or not isinstance(opt, QStyleOptionToolButton):
            return opt
        o = QStyleOptionToolButton(opt)
        F = QStyleOptionToolButton.ToolButtonFeature
        o.features &= ~(F.HasMenu | F.MenuButtonPopup | F.PopupDelay)
        return o

    def sizeFromContents(self, ct, opt, size, widget=None):
        if ct == QStyle.ContentsType.CT_ToolButton and widget is not None and widget.property(self.NO_ARROW):
            plain = self._plain(opt, widget)
            if plain is not opt:
                # QToolButton added the arrow's part to the size it asks for
                # (a button with its menu on a part of its own): taken off
                if isinstance(widget, QToolButton) and \
                        widget.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup:
                    size = QSize(max(0, size.width() - super().pixelMetric(
                        QStyle.PixelMetric.PM_MenuButtonIndicator, opt, widget)), size.height())
                opt = plain
        return super().sizeFromContents(ct, opt, size, widget)

    def subControlRect(self, cc, opt, sc, widget=None):
        if cc == QStyle.ComplexControl.CC_ToolButton and widget is not None and widget.property(self.NO_ARROW):
            if sc == QStyle.SubControl.SC_ToolButtonMenu:
                return QRect()
            opt = self._plain(opt, widget)
        return super().subControlRect(cc, opt, sc, widget)

    def drawComplexControl(self, cc, opt, p, widget=None):
        from PyQt6.QtWidgets import QStyleOptionToolButton
        if (cc != QStyle.ComplexControl.CC_ToolButton or widget is None or not part("toolbar_hover")
                or not isinstance(opt, QStyleOptionToolButton)):
            super().drawComplexControl(cc, opt, p, widget)
            return
        level = float(widget.property("ike_hover") or 0.0)
        sunken = bool(opt.state & QStyle.StateFlag.State_Sunken)
        if sunken:
            level = 1.4
        # the button's own rectangle (see TabLabelStyle.drawControl: nothing
        # of the given option is read at every paint)
        r = QRectF(widget.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        radius = min(HOVER_RADIUS, r.height() / 3)
        if level > 0 and opt.state & QStyle.StateFlag.State_Enabled:
            # 1.1.23: Breeze's hover, the Highlight mixed into the background
            # with a 1-px outline (was up to 45 % with a fading outline)
            fill, edge = hover_fill(widget.palette(), level)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(edge, 1.0))
            p.setBrush(fill)
            p.drawRoundedRect(r, radius, radius)
            p.restore()
        focus = keyboard_focus(widget, opt)
        if focus:                    # reached with Tab: Breeze's ring, 2 px outside the shape
            focus_ring(p, r.adjusted(-2, -2, 2, 2), widget.palette(), radius + 2)
        o = QStyleOptionToolButton(self._plain(opt, widget))
        if focus:
            o.state &= ~QStyle.StateFlag.State_HasFocus
        # the desktop's own hover frame and the pressed frame give way to the round one;
        # a checked (on) button keeps the desktop's look
        o.state &= ~QStyle.StateFlag.State_MouseOver
        if not opt.state & QStyle.StateFlag.State_On:
            o.state &= ~QStyle.StateFlag.State_Sunken
            o.activeSubControls = QStyle.SubControl.SC_None
        super().drawComplexControl(cc, o, p, widget)


class HoverGlides(QObject):
    """Watches the buttons of a toolbar: under the mouse their "ike_hover"
    level glides to 1 and back (drawn by RoundHoverStyle)."""

    def __init__(self, bar, config):
        super().__init__(bar)
        self.bar, self.config = bar, config
        self.style = RoundHoverStyle()
        self.glides = {}
        bar.installEventFilter(self)
        self.adopt()

    def adopt(self):
        """Take the toolbar's buttons that are not taken yet (after a change of the bar too)."""
        from PyQt6.QtWidgets import QToolButton
        if not part("toolbar_hover"):
            return
        for b in self.bar.findChildren(QToolButton):
            if b in self.glides or b.parentWidget() is not self.bar or b.property("ike_own_hover"):
                continue
            b.setStyle(self.style)
            b.installEventFilter(self)
            # the object's own methods: nothing kept on a button's wrapper
            g = effects.Glide(b, self.config, functools.partial(self._level, b))
            self.glides[b] = g
            b.destroyed.connect(functools.partial(self._forget, b))

    def take(self, b):
        """Give a button the toolbar's style at once (adopt() does it a moment
        after the button joins the toolbar): it is measured with it."""
        if part("toolbar_hover") and b.style() is not self.style:
            b.setStyle(self.style)
            b.updateGeometry()

    def _forget(self, b, _obj=None):
        self.glides.pop(b, None)

    def _level(self, b):
        g = self.glides.get(b)
        if g is not None:
            b.setProperty("ike_hover", g.value)
            b.update()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        t = event.type()
        if obj is self.bar:
            if t == QEvent.Type.ChildAdded:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self.adopt)
            return False
        g = self.glides.get(obj)
        if g is not None:
            if t == QEvent.Type.Enter:
                g.to(1)
            elif t == QEvent.Type.Leave:
                g.to(0)
        return False
