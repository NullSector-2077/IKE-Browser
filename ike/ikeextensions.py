"""I.K.E. extensions (1.1.20): the features that come with I.K.E. and can be
switched on and off one by one.

They are part of I.K.E. itself, not third-party code. The list below is read
by the menus (☰ → I.K.E. extensions, and the menu bar's Extensions menu) and
by Settings → I.K.E. extensions, so both always show the same thing.

Each switch is one setting. Where a feature already had its own setting, that
setting is the switch (its saved value keeps its meaning); a feature that had
none got one that is on by default, so nothing changes for anybody until they
turn it off. "Off" hides the feature's menu entries and toolbar button and
stops its work. The two newest ones (automatic scrolling, open the selected
text with the middle button) are off until the user turns them on.
"""

from collections import namedtuple

# name, description: English, translated with T() where shown.
# options: "page:<settings page>", "dialog:<method of the app>" or "".
# actions: attributes of the window (QAction or QMenu) hidden while the
# extension is off; toolbar: keys of toolbar buttons hidden while it is off.
# hook: what has to be done again when it is switched (see changed()).
# category: the group it is shown under (CATEGORIES below, 1.1.30).
Ext = namedtuple("Ext", "id name icon description key default options actions toolbar hook category")


def _t(text):
    """A text translated where it is shown (marked for tools/check-lang.py)."""
    return text


# 1.1.30 (the owner's grouping): the extensions under five headings, in the
# menu bar's Extensions menu, in ☰ → I.K.E. extensions and in Settings → I.K.E.
# extensions alike. (key, name, icon names)
CATEGORIES = (
    ("privacy", _t("Privacy and security"), ("security-high", "preferences-security", "object-locked")),
    ("browsing", _t("Browsing and appearance"), ("preferences-desktop-theme", "internet-web-browser", "globe")),
    ("media", _t("Audio and video"), ("applications-multimedia", "media-playback-start", "audio-volume-high")),
    ("productivity", _t("Productivity"), ("view-task", "office-calendar", "accessories-text-editor", "edit-find")),
    ("system", _t("System and resources"), ("computer", "utilities-system-monitor", "preferences-system")),
)
# which extension goes where; every extension has one (tests/test_menus_reorg.py)
_CATEGORY_OF = {
    "passwords": "privacy", "consent": "privacy", "containers": "privacy",
    "dark": "browsing", "split": "browsing", "autoscroll": "browsing", "middleclick": "browsing",
    "videoads": "media", "pip": "media",
    "watcher": "productivity", "translate": "productivity", "commandbar": "productivity",
    "userscripts": "productivity",
    "resources": "system", "weather": "system", "plasma": "system",
}


def _ext(id, name, icon, description, key, default=True, options="", actions=(), toolbar=(), hook=""):
    return Ext(id, name, icon, description, key, default, options, tuple(actions), tuple(toolbar), hook,
               _CATEGORY_OF[id])


EXTENSIONS = (
    _ext("userscripts", "User scripts", ("text-x-script", "application-x-javascript"),
         "Runs the small scripts you install to change how some sites look or work.",
         "userscripts_enabled", options="dialog:show_userscripts", hook="userscripts"),
    _ext("dark", "Dark mode for pages", ("weather-clear-night",),
         "Makes bright pages dark with the I.K.E. Dark Engine, everywhere or only on the sites you choose.",
         "comp_dark", options="page:sites", actions=("m_dark",), toolbar=("dark",), hook="dark"),
    _ext("videoads", "Skip ads in videos", ("media-skip-forward", "media-playback-start"),
         "Mutes, fast-forwards and skips the ads inside YouTube videos.",
         "video_ad_skip", hook="scripts"),
    _ext("consent", "Cookie banners", ("preferences-web-browser-cookies", "edit-delete"),
         "Says no to cookie consent requests and hides their banners.",
         "comp_consent", hook="settings"),
    _ext("passwords", "Password manager", ("dialog-password", "object-locked"),
         "Keeps your logins in an encrypted vault on this computer and fills them in for you.",
         "ext_passwords", options="dialog:show_passwords", actions=("act_passwords", "act_fill_login"),
         hook="scripts"),
    _ext("watcher", "Notify me when a page changes",
         ("view-visible", "view-history", "view-reveal-symbolic", "document-open-recent-symbolic"),
         "Checks the pages you choose from time to time and tells you when they change.",
         "page_watch_on", options="dialog:show_watches", actions=("act_watches",), hook="watcher"),
    _ext("split", "Split view", ("view-split-left-right", "view-dual-symbolic"),
         "Shows two tabs side by side in the same window.",
         "ext_split", actions=("act_split",), toolbar=("split",), hook="split"),
    _ext("pip", "Video in a floating window", ("picture-in-picture", "window-duplicate", "focus-windows-symbolic"),
         "Keeps a video on top of the other windows while you do something else.",
         "ext_pip", actions=("act_float",), toolbar=("pip",)),
    _ext("translate", "Translate page", ("translate", "preferences-desktop-locale"),
         "Sends the page to a translation service, only when you ask for it.",
         "ext_translate", options="page:language", actions=("act_translate",)),
    _ext("containers", "Containers", ("folder-locked", "folder-lock", "channel-secure-symbolic", "tab-duplicate"),
         "Tabs with their own cookies and logins, to keep accounts apart.",
         "ext_containers", options="page:privacy", actions=("m_containers",)),
    _ext("resources", "Site resources", ("utilities-system-monitor", "configure"),
         "Shows the memory and processor each site uses, with limits if you want them.",
         "ext_resources", options="dialog:show_resources", actions=("act_resources",), toolbar=("resources",),
         hook="resources"),
    _ext("weather", "Weather on the new tab page", ("weather-few-clouds", "globe"),
         "Shows the weather of the city you choose on the new tab page.",
         "newtab_weather", options="page:newtab", hook="newtab"),
    _ext("commandbar", "Command bar", ("system-search", "edit-find"),
         "F2 opens a box that finds commands, tabs, bookmarks and settings as you type.",
         "ext_command_bar", actions=("act_command_bar",)),
    _ext("plasma", "Plasma integration", ("plasma", "start-here-kde", "preferences-desktop-theme"),
         "Media keys, downloads in the notifications, KRunner and KDE Connect.",
         "ext_plasma", options="page:system", toolbar=("send",), hook="plasma"),
    _ext("autoscroll", "Automatic scrolling", ("transform-move-vertical", "go-down"),
         "Middle-click on an empty part of a page, then move the mouse to scroll. "
         "Any click or Esc stops it.",
         "ext_autoscroll", default=False, hook="scripts"),
    _ext("middleclick", "Open selected text with middle click", ("edit-paste",),
         "Middle-click on an empty part of a page opens the text you selected, "
         "as an address or as a search.",
         "ext_middleclick", default=False),
)

BY_ID = {e.id: e for e in EXTENSIONS}


def by_category():
    """[(category key, name, icon names, [extensions])], in the order of
    CATEGORIES and, inside each, in the order of the owner's list."""
    order = list(_CATEGORY_OF)
    return [(key, name, icons, sorted((e for e in EXTENSIONS if e.category == key), key=lambda e: order.index(e.id)))
            for key, name, icons in CATEGORIES]

# the settings each new switch adds to DEFAULTS (config.py)
NEW_KEYS = {e.key: e.default for e in EXTENSIONS if e.key.startswith("ext_")}


def on(config, ext_id):
    """Is this extension switched on? (A missing setting is its default.)"""
    e = BY_ID[ext_id]
    try:
        value = config.get(e.key, e.default)
    except AttributeError:
        value = config[e.key] if e.key in config else e.default
    return bool(e.default if value is None else value)


def icon(e):
    from PyQt6.QtWidgets import QStyle

    from .icons import themed
    return themed(e.icon, QStyle.StandardPixmap.SP_FileDialogDetailedView)


def toolbar_keys_off(config):
    """Keys of the toolbar buttons whose extension is off."""
    return {k for e in EXTENSIONS if e.toolbar and not on(config, e.id) for k in e.toolbar}


def apply_to_window(win):
    """Show or hide the extensions' menu entries and tick their switches."""
    cfg = win.app.config
    for e in EXTENSIONS:
        state = on(cfg, e.id)
        for name in e.actions:
            obj = getattr(win, name, None)
            if obj is None:
                continue
            act = obj.menuAction() if hasattr(obj, "menuAction") else obj
            act.setVisible(state)
            act.setEnabled(state)          # a hidden entry's shortcut does nothing either
        sw = getattr(win, "ext_actions", {}).get(e.id)
        if sw is not None and sw.isChecked() != state:
            sw.setChecked(state)
    if not on(cfg, "split") and getattr(win, "split", None) is not None:
        win.unsplit()


def set_on(app, ext_id, state):
    """Switch an extension from a menu: saved at once and applied everywhere."""
    e = BY_ID[ext_id]
    state = bool(state)
    if on(app.config, ext_id) == state:
        return
    app.config[e.key] = state
    app.config.save()
    changed(app, [ext_id])


def changed(app, ext_ids, settings_applied=False):
    """Extensions were switched: start or stop what they do.

    settings_applied: the Settings window has just applied everything
    (app.settings_changed() already ran), so only what it does not cover is
    done here."""
    hooks = {BY_ID[i].hook for i in ext_ids if i in BY_ID}
    if "userscripts" in hooks:
        app.userscripts.apply_all()
    if hooks & {"scripts", "settings"} and not settings_applied:
        if "settings" in hooks:
            app.settings_changed()
        else:
            app.shields.apply_settings()
    if "plasma" in hooks and not settings_applied:
        app.desktop.settings_changed()
    if "resources" in hooks:
        app.resources.settings_changed()
    if "watcher" in hooks:
        app.watcher.settings_changed()
    if "newtab" in hooks:
        app.reload_newtabs()
    app.refresh_windows()          # menus, toolbar buttons and the address bar's signs
    if "dark" in hooks:
        app._dark_changed()


def primary_selection():
    """The text selected last anywhere on the desktop (X11 / Wayland primary
    selection), or "" where there is none."""
    from PyQt6.QtGui import QClipboard, QGuiApplication
    cb = QGuiApplication.clipboard()
    if cb is None or not cb.supportsSelection():
        return ""
    return cb.text(QClipboard.Mode.Selection) or ""


# --- automatic scrolling (a page script in I.K.E.'s own world, unseen by the page) ---
# Middle button on a part of the page that is not a link, a field, a button or a
# frame: a small mark appears and the page scrolls towards the mouse, faster the
# farther it is. Any click, Esc, the wheel or leaving the window stops it; a
# press, drag and release stops at the release (as in Falkon's AutoScroll).
AUTOSCROLL_JS = r"""(function () {
  'use strict';
  if (window.__ikeAutoScroll) return;
  window.__ikeAutoScroll = true;
  var NOT_HERE = 'a[href],area[href],input,textarea,select,button,label,summary,option,' +
      'video,audio,iframe,frame,embed,object,[contenteditable=""],[contenteditable="true"],' +
      '[role="button"],[role="link"],[role="textbox"],[role="slider"],[draggable="true"]';
  var active = false, moved = false, sx = 0, sy = 0, mx = 0, my = 0, raf = 0, box = null, mark = null;

  function scrollable(el) {
    for (; el && el.nodeType === 1 && el !== document.body && el !== document.documentElement;
         el = el.parentElement) {
      var s = getComputedStyle(el);
      if ((/(auto|scroll|overlay)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 1) ||
          (/(auto|scroll|overlay)/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1)) return el;
    }
    var root = document.scrollingElement || document.documentElement;
    if (root.scrollHeight > root.clientHeight + 1 || root.scrollWidth > root.clientWidth + 1) return root;
    return null;
  }
  function speed(d) {
    var a = Math.abs(d) - 12;
    if (a <= 0) return 0;
    return (d < 0 ? -1 : 1) * Math.min(80, a / 8 + a * a / 2500);
  }
  function step() {
    if (!active) return;
    var dx = speed(mx - sx), dy = speed(my - sy);
    if (dx || dy) {
      if (box === (document.scrollingElement || document.documentElement)) window.scrollBy(dx, dy);
      else box.scrollBy(dx, dy);
    }
    raf = requestAnimationFrame(step);
  }
  function stop() {
    if (!active) return;
    active = false;
    cancelAnimationFrame(raf);
    if (mark && mark.parentNode) mark.parentNode.removeChild(mark);
    mark = null;
    document.documentElement.removeAttribute('data-ike-autoscroll');
  }
  function swallow(e) { e.preventDefault(); e.stopPropagation(); }
  addEventListener('mousedown', function (e) {
    if (active) { stop(); swallow(e); return; }
    if (e.button !== 1 || e.ctrlKey || e.shiftKey || e.altKey || e.metaKey) return;
    var t = e.target;
    if (!t || t.nodeType !== 1 || t.closest(NOT_HERE) || t.isContentEditable || document.designMode === 'on') return;
    box = scrollable(t);
    if (!box) return;
    swallow(e);
    active = true; moved = false;
    sx = mx = e.clientX; sy = my = e.clientY;
    mark = document.createElement('div');
    mark.setAttribute('style', 'all:initial;position:fixed;z-index:2147483647;pointer-events:none;' +
      'width:26px;height:26px;border-radius:50%;box-sizing:border-box;' +
      'border:2px solid rgba(61,174,233,.9);background:rgba(255,255,255,.75);' +
      'box-shadow:0 0 3px rgba(0,0,0,.4);left:' + (sx - 13) + 'px;top:' + (sy - 13) + 'px');
    (document.body || document.documentElement).appendChild(mark);
    document.documentElement.setAttribute('data-ike-autoscroll', '1');
    raf = requestAnimationFrame(step);
  }, true);
  addEventListener('mousemove', function (e) {
    if (!active) return;
    mx = e.clientX; my = e.clientY;
    if (Math.abs(mx - sx) + Math.abs(my - sy) > 16) moved = true;
  }, true);
  addEventListener('mouseup', function (e) {
    if (active && e.button === 1) { swallow(e); if (moved) stop(); }
  }, true);
  addEventListener('auxclick', function (e) {
    if (e.button === 1 && (active || document.documentElement.hasAttribute('data-ike-autoscroll'))) swallow(e);
  }, true);
  addEventListener('keydown', function (e) {
    if (active && e.key === 'Escape') { stop(); swallow(e); }
  }, true);
  addEventListener('wheel', stop, true);
  addEventListener('blur', stop);
  addEventListener('pagehide', stop);
})();"""

# --- open the selected text with the middle button ---
# Asked in I.K.E.'s own world at the point of a real middle click: is it an
# empty part of the page (no link, field, button, frame or media)? The page
# cannot start it: the click comes from the mouse through Qt, not from the page.
EMPTY_AT_JS = r"""(function (x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return false;
  if (document.designMode === 'on' || el.isContentEditable) return false;
  if (document.documentElement.hasAttribute('data-ike-autoscroll')) return false;
  return !el.closest('a[href],area[href],input,textarea,select,button,label,summary,option,video,audio,' +
    'iframe,frame,embed,object,canvas,[contenteditable=""],[contenteditable="true"],[role="button"],' +
    '[role="link"],[role="textbox"],[onclick]');
})(%f, %f)"""

MAX_SELECTION = 2000          # longer than this is not an address or a search
