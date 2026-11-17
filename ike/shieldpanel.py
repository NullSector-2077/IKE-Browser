"""The shield: its toolbar icon and the panel that opens from it."""


from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from .config import LEVEL_NAMES, LEVELS, rank
from .i18n import T

LEVEL_LETTER = {"compatibility": "C", "balanced": "B", "strict": "S", "maximum": "M"}


# The toolbar's shield is drawn larger than the plain glyph, inside the same
# icon box: the button and its click area keep their size.
TOOLBAR_SHIELD_GROW = 1.18


def paint_shield(p, rect, level, grow=1.0):
    """Draw the shield for a protection level into rect (any size, any scale)."""
    from PyQt6.QtGui import QFont, QGuiApplication, QLinearGradient, QPalette
    side = min(rect.width(), rect.height())
    s = side / 24.0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.x() + (rect.width() - side) / 2.0, rect.y() + (rect.height() - side) / 2.0)

    def pt(x, y):
        return QPointF((12 + (x - 12) * grow) * s, (12 + (y - 12) * grow) * s)
    path = QPainterPath()
    path.moveTo(pt(12, 2))
    path.lineTo(pt(20, 5))
    path.lineTo(pt(20, 11.5))
    path.cubicTo(pt(20, 16.5), pt(16.6, 20.3), pt(12, 22))
    path.cubicTo(pt(7.4, 20.3), pt(4, 16.5), pt(4, 11.5))
    path.lineTo(pt(4, 5))
    path.closeSubpath()
    pal = QGuiApplication.palette()
    p.setPen(Qt.PenStyle.NoPen)
    if level == "off":
        p.setBrush(pal.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText))
        p.drawPath(path)
        pen = p.pen()
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setColor(pal.color(QPalette.ColorRole.Window))
        pen.setWidthF(2.0 * s * grow)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(pt(9, 9), pt(15, 15))
        p.drawLine(pt(15, 9), pt(9, 15))
    else:
        # the colours of the I.K.E. icon: a light-blue rim around a dark-blue
        # centre, so the white letter is readable on any theme
        rim = QLinearGradient(pt(4, 2), pt(20, 22))
        rim.setColorAt(0.0, QColor("#7df3ff"))
        rim.setColorAt(0.45, QColor("#19c3e6"))
        rim.setColorAt(1.0, QColor("#2f6bff"))
        p.setBrush(rim)
        p.drawPath(path)
        inner = QPainterPath()
        inner.moveTo(pt(12, 4.1))
        inner.lineTo(pt(18.2, 6.4))
        inner.lineTo(pt(18.2, 11.5))
        inner.cubicTo(pt(18.2, 15.6), pt(15.5, 18.7), pt(12, 20.1))
        inner.cubicTo(pt(8.5, 18.7), pt(5.8, 15.6), pt(5.8, 11.5))
        inner.lineTo(pt(5.8, 6.4))
        inner.closeSubpath()
        core = QLinearGradient(pt(12, 4), pt(12, 20))
        core.setColorAt(0.0, QColor("#12324a"))
        core.setColorAt(1.0, QColor("#07131f"))
        p.setBrush(core)
        p.drawPath(inner)
        f = QFont(p.font())
        f.setBold(True)
        f.setPixelSize(max(7, round(11 * s * grow)))
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        # the letter sits a little above the middle, where the shield is widest
        box = QRectF(pt(4, 0.3), pt(20, 18.3))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, LEVEL_LETTER.get(level, "B"))
    p.restore()


class _ShieldEngine(QIconEngine):
    """The shield drawn as shapes each time it is needed, so it is sharp at
    every size and screen scale and follows the palette."""

    def __init__(self, level, grow):
        super().__init__()
        self.level, self.grow = level, grow

    def clone(self):
        return _ShieldEngine(self.level, self.grow)

    def paint(self, painter, rect, mode, state):
        if mode == QIcon.Mode.Disabled:
            painter.save()
            painter.setOpacity(painter.opacity() * 0.45)
        paint_shield(painter, QRectF(rect), self.level, self.grow)
        if mode == QIcon.Mode.Disabled:
            painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def availableSizes(self, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        return [QSize(s, s) for s in (16, 20, 22, 24, 32, 48)]


def shield_icon(level, size=22, grow=1.0):
    """Shield glyph for a protection level. `size` is kept for callers that
    name one; the icon draws itself at whatever size it is shown."""
    return QIcon(_ShieldEngine(level, grow))


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
        "maximum": "Strict plus English as the only language shown to sites. "
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
        self.fp = QCheckBox(T("Fingerprinting protection"), self.adv)
        self.https = QCheckBox(T("Upgrade connections to HTTPS"), self.adv)
        self.noscript = QCheckBox(T("Block scripts on this site"), self.adv)
        self.dark = QCheckBox(T("Dark mode on this site"), self.adv)
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
                                          self.win.open_settings("privacy")))

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
        self.hint.setText(T(self.HINTS[level]))
        self.ads.setCurrentIndex(1 if cfg.site_opt(host, "ads") is False else 0)
        self.cookies.setCurrentIndex(max(0, self.cookies.findData(cfg.site_opt(host, "cookies"))))
        self.fp.setChecked(rank(level) >= 2 and cfg.site_opt(host, "fp") is not False)
        self.fp.setEnabled(web and rank(level) >= 2)
        self.https.setChecked(bool(cfg["https_only"]) and cfg.site_opt(host, "https") is not False)
        self.https.setEnabled(web and on and bool(cfg["https_only"]))
        self.noscript.setChecked(web and not sh.scripts_allowed(host))
        self.dark.setVisible(web)
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
