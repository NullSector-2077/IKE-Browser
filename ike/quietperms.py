"""Quiet permission prompts (1.1.24, on by default; Settings -> Privacy).

A site that asks for notifications, the location, the camera or the
microphone no longer opens a window over the page: a small sign appears in
the address bar, and a click on it answers (Allow, Block, Not now). The
page keeps waiting meanwhile, as it does for an unanswered question; when it
goes elsewhere the question goes with it, unanswered.

A request for notifications made without a click or a key on the page in the
seconds before (the "Allow notifications?" that greets a visitor) is refused
at once; the refusal is not remembered, so the site may ask again after a
click, and the sign still lets the user allow it.

The answers are kept per site by the engine, as before (Settings -> Site
permissions, the shield's "Reset this site's permissions"). With the option
off, the old window is used. The other kinds (clipboard, screen, fonts, the
mouse pointer) keep their own handling.
"""

import time

from PyQt6.QtCore import QPoint, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePermission
from PyQt6.QtWidgets import QMenu, QStyle

from .i18n import T

PT = QWebEnginePermission.PermissionType
QUIET = (PT.Notifications, PT.Geolocation, PT.MediaAudioCapture, PT.MediaVideoCapture,
         PT.MediaAudioVideoCapture)
GESTURE_S = 5.0          # a click or key this recent counts as the user's act (Chromium: 5 s)
MAX_WAITING = 8

ICONS = {
    PT.Notifications: ("notifications", "preferences-desktop-notification-bell",
                       "preferences-desktop-notification"),
    PT.Geolocation: ("mark-location", "find-location", "gps"),
    PT.MediaVideoCapture: ("camera-web", "camera-video", "camera-photo"),
    PT.MediaAudioVideoCapture: ("camera-web", "camera-video", "camera-photo"),
    PT.MediaAudioCapture: ("audio-input-microphone", "mic-on", "microphone"),
}


def quiet(config, ptype):
    return bool(config.get("quiet_permissions", True)) and ptype in QUIET


def gesture(page, now=None):
    """A click or a key on this page (after it opened) in the last GESTURE_S seconds."""
    now = time.monotonic() if now is None else now
    acted = getattr(page, "_ike_input", -99.0)
    return acted > getattr(page, "_ike_page_since", -99.0) and now - acted <= GESTURE_S


def handle(page, perm):
    """Take a permission request quietly; False when it is not one of QUIET."""
    ptype = perm.permissionType()
    if not quiet(page.app.config, ptype):
        return False
    origin = QUrl(perm.origin())
    if ptype == PT.Notifications and not gesture(page):
        perm.deny()
        try:
            # not remembered: refused this time only
            page.profile().queryPermission(origin, ptype).reset()
        except (AttributeError, RuntimeError):
            pass
        hold(page, origin, ptype, None)
        return True
    # a copy: the object handed to the signal belongs to the engine and is
    # gone once the handler returns
    hold(page, origin, ptype, type(perm)(perm))
    return True


def waiting(page):
    return list(getattr(page, "_ike_quiet", None) or []) if page is not None else []


def hold(page, origin, ptype, perm):
    """Keep the question on its page and show the sign when the page is in front."""
    entries = page.__dict__.setdefault("_ike_quiet", [])
    key = origin.toString()
    for e in entries:
        if e["origin"] == key and e["type"] == ptype:
            if perm is not None:
                e["perms"].append(perm)
            break
    else:
        if len(entries) >= MAX_WAITING:
            return                      # left unanswered: the page keeps waiting
        entries.append({"origin": key, "host": origin.host() or key, "type": ptype,
                        "perms": [perm] if perm is not None else []})
    if not getattr(page, "_ike_quiet_wired", False):
        page._ike_quiet_wired = True
        # a page that goes elsewhere takes its questions with it, unanswered
        page.loadStarted.connect(lambda p=page: drop(p))
    _refresh(page)


def drop(page):
    if getattr(page, "_ike_quiet", None):
        page._ike_quiet = []
        _refresh(page)


def answer(page, allow):
    """The user's answer to every question waiting on the page."""
    entries, page._ike_quiet = waiting(page), []
    for e in entries:
        done = False
        for p in e["perms"]:
            try:
                if p.isValid():
                    p.grant() if allow else p.deny()
                    done = True
            except RuntimeError:
                continue
        if not done:
            # refused at once (notifications without a click): the answer is kept for the site
            try:
                q = page.profile().queryPermission(QUrl(e["origin"]), e["type"])
                q.grant() if allow else q.deny()
            except (AttributeError, RuntimeError):
                pass
    _refresh(page)


def _refresh(page):
    win = getattr(page, "window_ref", None)
    if win is not None:
        try:
            sign(win)
        except RuntimeError:
            pass


def sign(win):
    """Show or hide the sign in the address bar for the page in front."""
    act = getattr(getattr(win, "urlbar", None), "perm_act", None)
    if act is None:
        return
    v = win.current_view()
    entries = waiting(v.page() if v is not None else None)
    if entries:
        from .icons import themed
        e = entries[-1]
        act.setIcon(themed(ICONS.get(e["type"], ("dialog-question",)),
                           QStyle.StandardPixmap.SP_MessageBoxQuestion))
        act.setToolTip("\n".join(T("%s wants to %s.") % (x["host"], permission_text_of(x["type"]))
                                 for x in entries))
    act.setVisible(bool(entries))


def menu(win):
    """The sign was clicked: Allow, Block or Not now."""
    v = win.current_view()
    page = v.page() if v is not None else None
    entries = waiting(page)
    if not entries:
        sign(win)
        return None
    m = QMenu(win)
    for e in entries:
        a = m.addAction(T("%s wants to %s.") % (e["host"], permission_text_of(e["type"])))
        a.setEnabled(False)
    m.addSeparator()
    m.addAction(T("Allow")).triggered.connect(lambda: answer(page, True))
    m.addAction(T("Block")).triggered.connect(lambda: answer(page, False))
    m.addAction(T("Not now")).triggered.connect(lambda: drop(page))
    m.aboutToHide.connect(m.deleteLater)
    bar = win.urlbar
    where = None
    for b in bar.children():
        if (b.isWidgetType() and b.metaObject().className() == "QLineEditIconButton"
                and b.defaultAction() is bar.perm_act):
            where = b.mapToGlobal(QPoint(0, b.height()))
    m.popup(where if where is not None else bar.mapToGlobal(QPoint(bar.width() - 200, bar.height())))
    win._quiet_menu = m
    return m


def permission_text_of(ptype):
    from .webview import permission_text
    return permission_text(ptype)
