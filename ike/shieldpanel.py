"""The shield: its toolbar icon and the panel that opens from it."""


from math import sqrt

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFontMetricsF,
    QGuiApplication,
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionToolButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from .config import LEVEL_NAMES, LEVELS, rank
from .i18n import T
from .uistyle import Switch

LEVEL_LETTER = {"compatibility": "C", "balanced": "B", "strict": "K", "maximum": "M"}
# The letter's colour for each level (1.1.27, the owner: a colour of its own
# for each level, readable inside the octagon: each one has a contrast of 7:1
# or more with its dark centre, tests/test_launcher_icons.py). Off: a white X.
LEVEL_COLOUR = {"compatibility": "#FFD54F",     # yellow: the lightest protection
                "balanced": "#69F0AE",          # green: the everyday level
                "strict": "#65C2EF",            # Kontrol: the light blue of the logo's K (1.1.29)
                "maximum": "#FF9EE8"}           # pink: the strongest
CENTRE_COLOUR = "#061E37"
# the octagon in the address bar (1.1.29, the owner: a little smaller, so its
# rim no longer nearly touches the bar's border, and its letter a little
# smaller inside it; it was 1.15 and the letter half the octagon)
TOOLBAR_SHIELD_GROW = 1.08
TOOLBAR_LETTER = 0.92


def paint_shield(p, rect, level, grow=1.0, letter=1.0):
    """Draw the Breeze octagon and the glyph of the applied protection level
    (its letter in the level's colour; a white X when off)."""
    side = min(rect.width(), rect.height()) * 0.84 * grow
    if side <= 0:
        return
    centre = rect.center()
    # The SVG references use a 21-unit polygon and a 1.7-unit round stroke.
    stroke = side * (1.7 / 22.7)
    edge = (side - stroke) / 2
    cut = edge * (sqrt(2) - 1)
    polygon = QPolygonF([centre + QPointF(x, y) for x, y in
                         ((-cut, -edge), (cut, -edge), (edge, -cut), (edge, cut),
                          (cut, edge), (-cut, edge), (-edge, cut), (-edge, -cut))])

    off = level == "off"
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#C4CBD3" if off else "#3DAEE9"), stroke,
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor("#343C46" if off else CENTRE_COLOUR))
    p.drawPolygon(polygon)

    ink = QColor("#F1F3F6")
    if off:
        arm = side * 0.14
        p.setPen(QPen(ink, side * 0.09, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(centre + QPointF(-arm, -arm), centre + QPointF(arm, arm))
        p.drawLine(centre + QPointF(-arm, arm), centre + QPointF(arm, -arm))
    else:
        paint_cyber_letter(p, centre, side, LEVEL_LETTER.get(level, "B"),
                           QColor(LEVEL_COLOUR.get(level, "#F1F3F6")), letter)
    p.restore()


# The level letters in a "cyber" cut (1.1.27, the owner): drawn as strokes on a
# 4 x 7 grid, straight lines with corners cut at 45 degrees and square ends,
# the same at every size (no font: the same letters on every computer). Each
# letter is a list of strokes; each stroke a list of grid points.
CYBER = {
    "C": [[(4, 0), (1, 0), (0, 1), (0, 6), (1, 7), (4, 7)]],
    "B": [[(0, 3.5), (3, 3.5), (4, 2.5), (4, 1), (3, 0), (0, 0), (0, 7), (3, 7), (4, 6), (4, 4.5), (3, 3.5)]],
    # 1.1.29: Kontrol (the owner's name for Strict): the K of the logo, a stem and two arms
    # at 45 degrees that meet on it
    "K": [[(0, 0), (0, 7)], [(4, 0), (0.5, 3.5), (4, 7)], [(0, 3.5), (0.5, 3.5)]],
    "M": [[(0, 7), (0, 0), (2, 2.8), (4, 0), (4, 7)]],
}
# where each letter gets its "cyber" notch: a short cut across one stroke
CYBER_NOTCH = {"C": ((0, 3.5), "h"), "B": ((0, 3.5), "h"), "K": ((0, 5.25), "h"), "M": ((2, 2.8), "v")}


def paint_cyber_letter(p, centre, side, letter, colour, scale=1.0):
    """One level letter, cyber cut, centred in the octagon of size `side`.
    Every point of the letter sits on the screen's pixel grid and its strokes
    are a whole number of pixels wide, so the letter is sharp at 16, 22 and
    24 px too (no stroke spread over two pixels)."""
    from PyQt6.QtGui import QPainterPathStroker
    strokes = CYBER.get(letter)
    if not strokes:
        return
    dev = p.device()
    dpr = dev.devicePixelRatioF() if dev is not None else 1.0
    tf = p.worldTransform()
    dpr *= max(tf.m11(), 1e-6)                    # a painter that scales (an icon drawn larger)
    height = side * 0.50 * scale
    unit = height / 7.0
    # thick enough to read at 16 px, not heavier than the octagon's own rim at large sizes
    pen_px = max(1, round(max(1.25, min(unit * 1.25, side * 0.085)) * dpr))
    pen_w = pen_px / dpr
    half = 0.5 / dpr if pen_px % 2 else 0.0       # an odd width: on the pixels' centres
    x0, y0 = centre.x() - 2 * unit, centre.y() - 3.5 * unit

    def at(gx, gy):
        return QPointF(round((x0 + gx * unit) * dpr) / dpr + half, round((y0 + gy * unit) * dpr) / dpr + half)
    path = QPainterPath()
    for stroke in strokes:
        path.moveTo(at(*stroke[0]))
        for x, y in stroke[1:]:
            path.lineTo(at(x, y))
    stroker = QPainterPathStroker()
    stroker.setWidth(pen_w)
    stroker.setCapStyle(Qt.PenCapStyle.SquareCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    stroker.setMiterLimit(2.0)
    outline = stroker.createStroke(path).simplified()
    # centred on the letter as drawn (its square ends included), by whole pixels
    d = centre - outline.boundingRect().center()
    shift = QPointF(round(d.x() * dpr) / dpr, round(d.y() * dpr) / dpr)
    outline.translate(shift)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(outline, colour)
    # the notch only where there is room for it to be seen (26 px and up)
    notch = CYBER_NOTCH.get(letter)
    if notch and side >= 26:
        (nx, ny), way = notch
        c = at(nx, ny) + shift
        gap = max(1.0, round(pen_px * 0.45)) / dpr
        reach = pen_w * 0.9
        rect = (QRectF(c.x() - reach, c.y() - gap / 2, 2 * reach, gap) if way == "h"
                else QRectF(c.x() - gap / 2, c.y() - reach, gap, 2 * reach))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(rect, QColor(CENTRE_COLOUR))
    p.restore()


_PIXMAPS = {}


class _ShieldEngine(QIconEngine):
    """The protection icon rendered at the requested resolution."""

    def __init__(self, level, grow, letter=1.0):
        super().__init__()
        self.level, self.grow, self.letter = level, grow, letter

    def clone(self):
        return _ShieldEngine(self.level, self.grow, self.letter)

    def paint(self, painter, rect, mode, state):
        if mode == QIcon.Mode.Disabled:
            painter.save()
            painter.setOpacity(painter.opacity() * 0.45)
        paint_shield(painter, QRectF(rect), self.level, self.grow, self.letter)
        if mode == QIcon.Mode.Disabled:
            painter.restore()

    def pixmap(self, size, mode, state):
        # The toolbar asks for the shield at each repaint of the address bar
        # (dozens of times while a page loads); the same picture is drawn
        # once and kept, for each size and state (1.1.18).
        key = (self.level, self.grow, self.letter, size.width(), size.height(), mode, state,
               QGuiApplication.font().key())
        pm = _PIXMAPS.get(key)
        if pm is None:
            pm = QPixmap(size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
            p.end()
            if len(_PIXMAPS) > 64:
                _PIXMAPS.clear()
            _PIXMAPS[key] = pm
        return QPixmap(pm)

    def availableSizes(self, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        return [QSize(s, s) for s in (16, 20, 22, 24, 32, 48)]


def shield_icon(level, size=22, grow=1.0, letter=1.0):
    """Shield glyph for a protection level. `size` is kept for callers that
    name one; the icon draws itself at whatever size it is shown."""
    return QIcon(_ShieldEngine(level, grow, letter))


class ShieldButton(QToolButton):
    """Draw both the icon and the counter on the same vertical centre line."""

    GAP = 4

    def icon_rect(self):
        """Where the octagon is drawn (the pulse ring opens around it, 1.1.27)."""
        side = min(self.width(), self.height(), self.iconSize().height())
        x = self.width() - side if self.isRightToLeft() else 0
        return QRectF(x, (self.height() - side) / 2, side, side)

    def count_end(self):
        """Where the number beside the octagon ends (the "+N" rises after it)."""
        r = self.icon_rect()
        text = self.text()
        if not text:
            return r.right()
        return r.right() + self.GAP + self.fontMetrics().horizontalAdvance(text)

    def sizeHint(self):
        side = self.iconSize().height()
        text = self.text()
        count_width = self.GAP + self.fontMetrics().horizontalAdvance(text) if text else 0
        return QSize(side + count_width, side)

    def paintEvent(self, event):
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.icon = QIcon()
        option.text = ""
        p = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option, p, self)
        side = min(self.width(), self.height(), self.iconSize().height())
        rtl = self.isRightToLeft()
        x = self.width() - side if rtl else 0
        pm = self.icon().pixmap(QSize(side, side), self.devicePixelRatioF())
        p.drawPixmap(QPointF(x, (self.height() - pm.deviceIndependentSize().height()) / 2), pm)
        text = self.text()
        if text:
            fm = p.fontMetrics()
            left = x - self.GAP - fm.horizontalAdvance(text) if rtl else x + side + self.GAP
            p.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
            bounds = QFontMetricsF(p.font()).tightBoundingRect(text)
            baseline = self.height() / 2 - bounds.center().y()
            p.drawText(QPointF(left, baseline), text)
        p.end()


class ShieldPanel(QWidget):
    """Popup of the shield button: master switch, level and per-site controls."""

    HINTS = {
        "off": "Nothing is blocked or altered on this site.",
        "compatibility": "Blocks known ads and trackers and cleans tracking links. Cookies and "
                         "device data are left alone: for sites that break otherwise.",
        "balanced": "Also blocks cross-site cookies and adds per-site noise to canvas, WebGL "
                    "and audio fingerprints. Recommended.",
        "strict": "Balanced plus generic hardware, screen, font and Client Hints values, and "
                  "no WebGPU. Some sites may misbehave.",
        "maximum": "Kontrol plus English as the only language shown to sites. "
                   "Some sites may misbehave.",
    }

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self.title = QLabel(self)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.master = QPushButton(self)
        self.master.setCheckable(True)
        self.master.setMinimumHeight(38)
        self.master.setIconSize(QSize(22, 22))
        self.master.setToolTip(T("Switch every protection on or off for this site"))
        self.count = QLabel(self)
        cf = self.count.font()
        cf.setPointSizeF(cf.pointSizeF() * 2.2)
        cf.setBold(True)
        self.count.setFont(cf)
        self.count_label = QLabel(T("trackers and ads blocked on this page"), self)
        self.site_level = QComboBox(self)
        self.global_level = QComboBox(self)
        for combo in (self.site_level, self.global_level):
            for lv in LEVELS:
                combo.addItem(shield_icon(lv, 16), T(LEVEL_NAMES[lv]), lv)
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(320)

        self.adv_btn = QToolButton(self)
        self.adv_btn.setText(T("Advanced controls"))
        self.adv_btn.setCheckable(True)
        self.adv_btn.setAutoRaise(True)
        self.adv_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.adv = QWidget(self)
        al = QVBoxLayout(self.adv)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self.ads = QComboBox(self.adv)
        self.ads.addItem(T("Block ads and trackers"), None)
        self.ads.addItem(T("Allow ads and trackers"), False)
        self.cookies = QComboBox(self.adv)
        self.cookies.addItem(T("Cookies: as set by the level"), None)
        self.cookies.addItem(T("Block cross-site cookies"), "3p")
        self.cookies.addItem(T("Block all cookies"), "all")
        self.cookies.addItem(T("Allow all cookies"), "allow")
        self.fp = Switch(T("Fingerprinting protection"), self.adv)
        self.https = Switch(T("Upgrade connections to HTTPS"), self.adv)
        self.noscript = Switch(T("Block scripts on this site"), self.adv)
        self.dark = Switch(T("Dark mode on this site"), self.adv)
        self.detail = QLabel(self.adv)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.perms = QLabel(self.adv)
        self.perms.setWordWrap(True)
        self.perms_reset = QPushButton(T("Reset this site's permissions"), self.adv)
        self.perms_reset.clicked.connect(self._reset_perms)
        for wdg in (self.ads, self.cookies, self.fp, self.https, self.noscript, self.dark,
                    self.detail, self.perms, self.perms_reset):
            al.addWidget(wdg)

        self.repair_btn = QPushButton(T("Repair this site…"), self)
        self.repair_btn.setToolTip(T("Find the protection that breaks this page and turn off "
                                     "only that one, for this site only"))
        self.repair_btn.clicked.connect(self._repair)
        self.repaired = QLabel(self)
        self.repaired.setWordWrap(True)
        self.repaired_undo = QPushButton(T("Undo the repair"), self)
        self.repaired_undo.clicked.connect(self._undo_repair)
        # the protected time zone (1.1.24, timezone.py): for every site, after a restart
        # 1.1.29: each explanation in the ⓘ after its switch, as in Settings (two
        # lines of text under them made the closed panel taller than the room
        # below the shield on a small screen, tests/test_engines_110.py)
        from .dialogs import InfoButton
        self.zone = Switch(T("Protected time zone"), self)
        self.zone_hint = InfoButton(T("Sites see the time zone UTC, not yours. Some sites will show "
                                      "wrong times. After a restart."), self)
        self.zone.clicked.connect(self._zone_changed)
        # common English (1.1.29): sites are told en-US at every level
        self.english = Switch(T("Common English language"), self)
        self.english_hint = InfoButton(T("Sites see American English, the most common language, not "
                                         "yours. I.K.E. keeps your language. Fully after a restart."), self)
        self.english.clicked.connect(self._english_changed)
        settings = QPushButton(T("Protection settings…"), self)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        # the site's icon beside its name (polish.py)
        self.site_icon = QLabel(self)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.site_icon)
        head.addWidget(self.title, 1)
        lay.addLayout(head)
        lay.addWidget(self.master)
        lay.addWidget(self.count)
        lay.addWidget(self.count_label)
        from .polish import BlockBars
        self.kinds = BlockBars(self)             # what was blocked here, by kind (polish.py)
        lay.addWidget(self.kinds)
        lay.addWidget(QLabel(T("Protection on this site"), self))
        lay.addWidget(self.site_level)
        lay.addWidget(self.hint)
        lay.addWidget(self.repair_btn)
        lay.addWidget(self.repaired)
        lay.addWidget(self.repaired_undo)
        lay.addWidget(self.adv_btn)
        lay.addWidget(self.adv)
        lay.addWidget(sep)
        lay.addWidget(QLabel(T("Default for all sites"), self))
        lay.addWidget(self.global_level)
        for switch, info in ((self.zone, self.zone_hint), (self.english, self.english_hint)):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(switch)
            row.addWidget(info, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addStretch(1)
            lay.addLayout(row)
        lay.addWidget(settings)
        self.master.clicked.connect(self._master_clicked)
        self.adv_btn.toggled.connect(self._adv_toggled)
        self.site_level.currentIndexChanged.connect(self._site_changed)
        self.global_level.currentIndexChanged.connect(self._global_changed)
        self.ads.currentIndexChanged.connect(lambda _i: self._opt("ads", self.ads.currentData()))
        self.cookies.currentIndexChanged.connect(
            lambda _i: self._opt("cookies", self.cookies.currentData()))
        self.fp.clicked.connect(lambda on: self._opt("fp", None if on else False))
        self.https.clicked.connect(lambda on: self._opt("https", None if on else False))
        self.noscript.clicked.connect(self._noscript_changed)
        self.dark.clicked.connect(self._dark_changed)
        settings.clicked.connect(lambda: (self.win.shield_menu.hide(),
                                          self.win.open_settings("protection")))

    def _adv_toggled(self, on):
        self.adv.setVisible(on)
        self.adv_btn.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        cfg = self.win.app.config
        if not self._busy and cfg.get("shield_advanced") != on:
            cfg["shield_advanced"] = on
            cfg.save()
        QTimer.singleShot(0, self._resize_popup)

    def _resize_popup(self):
        # taller or shorter: the menu follows, stays on the screen and scrolls if needed (1.1.10)
        self.win.fit_shield_menu()

    def refresh(self):
        self._busy = True
        cfg = self.win.app.config
        host = self.win.current_host()
        web = bool(host)
        sh = self.win.app.shields
        level = cfg.level_for(host) if web else cfg["shield_level"]
        on = level != "off"
        self.title.setText(host or APP_NAME)
        from . import polish
        v = self.win.current_view()
        show = polish.part("panel_icons") and web and v is not None
        if show:
            self.site_icon.setPixmap(self.win.site_icon(v.url().toString()).pixmap(18, 18))
        self.site_icon.setVisible(show)
        self.master.setChecked(on)
        self.master.setIcon(shield_icon(level, 22))
        self.master.setText(T("Protection is ON for this site") if on
                            else T("Protection is OFF for this site"))
        st = sh.site_stats(host)
        self.count.setText(str(st["ads"] + st["scripts"]))
        self.site_level.setCurrentIndex(LEVELS.index(level))
        self.global_level.setCurrentIndex(LEVELS.index(cfg["shield_level"]))
        self.zone.setChecked(bool(cfg.get("protect_timezone")))
        self.english.setChecked(bool(cfg.get("common_english")))
        self.hint.setText(T(self.HINTS[level]))
        self.ads.setCurrentIndex(1 if cfg.site_opt(host, "ads") is False else 0)
        self.cookies.setCurrentIndex(max(0, self.cookies.findData(cfg.site_opt(host, "cookies"))))
        self.fp.setChecked(rank(level) >= 2 and cfg.site_opt(host, "fp") is not False)
        self.fp.setEnabled(web and rank(level) >= 2)
        self.https.setChecked(bool(cfg["https_only"]) and cfg.site_opt(host, "https") is not False)
        self.https.setEnabled(web and on and bool(cfg["https_only"]))
        self.noscript.setChecked(web and not sh.scripts_allowed(host))
        self.dark.setVisible(web and bool(cfg.get("comp_dark", True)))
        self.dark.setChecked(web and sh.dark_for(host))
        rows = ((T("Ads and trackers"), st["ads"]), (T("Scripts blocked"), st["scripts"]),
                (T("Cross-site cookies refused"), st["cookies"]),
                (T("Upgrades to HTTPS"), st["https"]),
                (T("Tracking parameters removed"), st["params"]))
        self.kinds.show_stats(rows if web else [])
        self.detail.setText("<table>%s</table>" % "".join(
            "<tr><td>%s&nbsp;&nbsp;&nbsp;</td><td align='right'><b>%d</b></td></tr>" % r
            for r in rows))
        perms = self.win.site_permissions()
        self.perms.setText(T("Permissions: %s") % (", ".join(perms) if perms else T("none granted")))
        self.perms_reset.setVisible(bool(perms))
        for w in (self.master, self.site_level, self.noscript, self.dark):
            w.setEnabled(web)
        for w in (self.ads, self.cookies):
            w.setEnabled(web and on)
        from . import repair
        self.repair_btn.setVisible(web and on and bool(cfg["repair_button"]))
        fixed = repair.repaired(cfg, host) if web else []
        self.repaired.setText(T("Repaired: turned off here: %s.") % ", ".join(
            T(repair.NAMES[k]) for k in fixed) if fixed else "")
        self.repaired.setVisible(bool(fixed))
        self.repaired_undo.setVisible(bool(fixed))
        adv = bool(cfg.get("shield_advanced"))
        self.adv_btn.setChecked(adv)
        self.adv.setVisible(adv)
        self.adv_btn.setArrowType(Qt.ArrowType.DownArrow if adv else Qt.ArrowType.RightArrow)
        self._busy = False
        QTimer.singleShot(0, self._resize_popup)     # rows may have appeared or gone

    def _repair(self):
        self.win.shield_menu.hide()
        self.win.repair_site()

    def _undo_repair(self):
        from . import repair
        repair.undo(self.win.app.config, self.win.current_host())
        self._apply()

    def _reset_perms(self):
        self.win.site_permissions(reset=True)
        self.refresh()

    def _apply(self, reload=True):
        app = self.win.app
        app.config.save()
        app.shields.apply_settings()
        app.refresh_windows()
        self.refresh()
        if reload:
            v = self.win.current_view()
            if v:   # skip the cache so already-loaded trackers are checked again
                v.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)

    def _master_clicked(self, on):
        cfg = self.win.app.config
        host = self.win.current_host()
        if on:
            cfg.set_site_level(host, None)
            if cfg.level_for(host) == "off":       # the global default itself is off
                cfg.set_site_level(host, "balanced")
        else:
            cfg.set_site_level(host, "off")
        self._apply()

    def _opt(self, key, value):
        if self._busy:
            return
        self.win.app.config.set_site_opt(self.win.current_host(), key, value)
        self._apply()

    def _site_changed(self, _i):
        if self._busy:
            return
        self.win.app.config.set_site_level(self.win.current_host(),
                                           self.site_level.currentData())
        self._apply()

    def _global_changed(self, _i):
        if self._busy:
            return
        cfg = self.win.app.config
        cfg["shield_level"] = self.global_level.currentData()
        host = self.win.current_host()
        if cfg["site_levels"].get(host) == cfg["shield_level"]:
            cfg["site_levels"].pop(host, None)
        self._apply()

    def _zone_changed(self, on):
        if self._busy:
            return
        cfg = self.win.app.config
        cfg["protect_timezone"] = bool(on)
        cfg.save()
        from . import timezone
        if timezone.active() != bool(on):
            self.win.toast(T("Restart I.K.E. to use it."), 5000)

    def _english_changed(self, on):
        if self._busy:
            return
        cfg = self.win.app.config
        cfg["common_english"] = bool(on)
        cfg.save()
        # the request header and the pages at once; workers, Intl and the
        # engine's own texts follow --lang, read at start
        self.win.app.shields.apply_settings()
        self.win.toast(T("Restart I.K.E. to use it."), 5000)

    def _toggle_list(self, key, host, present):
        lst = self.win.app.config[key]
        if present and host not in lst:
            lst.append(host)
        elif not present and host in lst:
            lst.remove(host)

    def _noscript_changed(self, on):
        if self._busy:
            return
        self._toggle_list("site_noscript", self.win.current_host(), on)
        self._apply()

    def _dark_changed(self, on):
        if self._busy:
            return
        self.win.app.set_site_dark(self.win.current_host(), on)
