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
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyledItemDelegate, QStyleOptionTab

from . import effects

PARTS = {
    "tab_mark": True,        # the line under the current tab, gliding to the new one
    "title_fade": True,      # long tab titles fade out instead of ending in "…"
    "icon_fade": True,       # a tab's icon changes with a short fade
    "row_hover": True,       # vertical tabs: the hover colour comes and goes softly
    "row_enter": True,       # vertical tabs: a new row fades in
    "audio_pulse": True,     # the speaker of a tab playing sound pulses gently
    "url_pill": True,        # the address field: rounded, its edge lights up when used
    "url_popup": True,       # suggestions: taller rows with the site's icon
    "zoom_mark": True,       # a sign in the address field when the page is not at its usual zoom
    "reload_fade": True,     # Reload and Stop change with a short fade
    "bar_fade": True,        # find bar, repair bar and full-screen notice fade in
    "preview_fade": True,    # the tab preview fades in and changes softly
    "line_ends": True,       # the loading line has soft ends
    "download_pop": True,    # a finished download shows a tick with a small pop
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
