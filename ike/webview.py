"""Web page and view classes."""

import os
import time

from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout

from .config import rank
from .i18n import T

_A = QWebEngineSettings.WebAttribute

_COSMETIC_JS = """(function(css){
 var id='ike-cosmetic-%s';
 function add(){
  var root=document.head||document.documentElement;
  if(!root){new MutationObserver(function(m,o){if(document.documentElement){o.disconnect();add();}})
   .observe(document,{childList:true});return;}
  var s=document.getElementById(id);
  if(!s){s=document.createElement('style');s.id=id;root.appendChild(s);}
  if(s.textContent!==css)s.textContent=css;
 }
 add();
})(%s);"""


_COLLECT_JS = """(function(){
 var c=new Set(), i=new Set(), n=document.querySelectorAll('[class],[id]');
 for(var k=0;k<n.length&&k<6000;k++){var e=n[k];
  if(e.id)i.add(e.id);
  if(e.classList)for(var j=0;j<e.classList.length;j++)c.add(e.classList[j]);}
 return [Array.from(c).slice(0,5000),Array.from(i).slice(0,3000)];
})();"""


def origin_text(url):
    """scheme://host[:port] of a page or a request, as shown to the user."""
    url = QUrl(url)
    if url.scheme() in ("http", "https") and url.host():
        port = url.port()
        return "%s://%s%s" % (url.scheme(), url.host(), (":%d" % port) if port > 0 else "")
    return url.toString() or T("this page")


def permission_text(ptype):
    from PyQt6.QtWebEngineCore import QWebEnginePermission as P
    PT = P.PermissionType
    names = {
        PT.Geolocation: T("know your location"),
        PT.MediaAudioCapture: T("use your microphone"),
        PT.MediaVideoCapture: T("use your camera"),
        PT.MediaAudioVideoCapture: T("use your camera and microphone"),
        PT.Notifications: T("show notifications"),
        PT.DesktopVideoCapture: T("capture your screen"),
        PT.DesktopAudioVideoCapture: T("capture your screen and audio"),
        PT.MouseLock: T("lock the mouse pointer"),
        PT.ClipboardReadWrite: T("read the clipboard"),
        PT.LocalFontsAccess: T("list the fonts installed on this computer"),
    }
    return names.get(ptype, T("use a protected feature"))


# the colour of an empty page in dark mode, before it paints
DARK_BLANK = "#181a1b"


def is_newtab(url):
    """Is url (a QUrl) the new tab page, ike:newtab?"""
    return url.scheme() == "ike" and url.path() == "newtab"


# reader mode reports the reader settings chosen on the page with this console prefix
# (with a token of the session: a site cannot change them)
READER_PREFIX = "\u0001ike-reader:%s:" % __import__("secrets").token_hex(8)


# A page can ask for something exactly when the user presses Enter or Space
# ("press Enter to start"): the question would take the key as an answer. So
# the safe answer is the default (Enter, Esc), and "yes" can be clicked only
# a moment after the question shows (review of 1.1.19, M2).
SAFE_DELAY_MS = 700


def careful(box, yes, no):
    """Make `no` the default and the Esc answer, and `yes` usable only
    SAFE_DELAY_MS after the box is shown."""
    from PyQt6.QtCore import QTimer
    box.setDefaultButton(no)
    box.setEscapeButton(no)
    yes.setEnabled(False)

    def enable():
        try:
            yes.setEnabled(True)
        except RuntimeError:
            pass                   # answered ("No") and closed before the delay ended
    QTimer.singleShot(SAFE_DELAY_MS, enable)


def permission_box(parent, origin, ptype):
    """The permission question: (box, allow button, block button)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(T("Permission request"))
    box.setText(T("%s wants to %s.") % (origin, permission_text(ptype)))
    allow = box.addButton(T("Allow"), QMessageBox.ButtonRole.AcceptRole)
    block = box.addButton(T("Block"), QMessageBox.ButtonRole.RejectRole)
    careful(box, allow, block)
    return box, allow, block

class WebPage(QWebEnginePage):
    def __init__(self, profile, window, parent=None):
        super().__init__(profile, parent)
        self.window_ref = window
        self.app = window.app
        self._exceptions = set()
        self._generichide = False
        self.mouse_locked = False
        self.loadStarted.connect(lambda: setattr(self, "mouse_locked", False))
        self._loaded_url = None                     # the address the last finished load showed
        self._backdrop = None                       # the colour shown before the page paints
        if self.app.config["dark_mode"] == "on" and self.app.config.get("comp_dark", True):
            # dark from the first moment: a window a site opens shows an empty
            # page before its address loads (1.1.19: it was white)
            self.set_backdrop(DARK_BLANK)
        self.loadStarted.connect(lambda: setattr(self, "_loaded_url", None))
        self.permissionRequested.connect(self._permission)
        self.fullScreenRequested.connect(self._fullscreen)
        self.urlChanged.connect(self._inject_cosmetics)
        self.loadFinished.connect(self._load_finished)
        self.loadingChanged.connect(self._loading_changed)
        try:
            self.desktopMediaRequested.connect(self._desktop_media)
        except AttributeError:
            pass
        try:
            from .passwords import handle_webauthn
            self.webAuthUxRequested.connect(lambda req: handle_webauthn(self, req))
        except AttributeError:
            pass
        self.app.passwords.attach(self)

    # --- navigation --------------------------------------------------
    # addresses the engine shows itself; every other kind ("mailto:", "tel:",
    # "magnet:", the private ones of installed programs) is handed to the desktop
    OWN_SCHEMES = frozenset(("http", "https", "file", "ike", "data", "blob", "about", "javascript",
                             "view-source", "chrome", "chrome-extension", "chrome-error", "devtools",
                             "qrc", "filesystem", "ws", "wss", ""))

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme().lower() not in self.OWN_SCHEMES:
            # A link that starts another program. The engine would hand it over
            # after any click on the page, without a word; other browsers ask
            # first, because the address goes to that program as the page wrote it.
            self._external_link(url)
            return False
        if (is_main_frame and url.scheme() in ("http", "https")
                and url.path().lower().endswith(".user.js")
                and self.app.config["userscripts_enabled"]):
            # a user script: offer to install it instead of showing its text.
            # Only for the user's own act (an address typed, a click or a key
            # just now), and from a public page never from this computer or
            # the home network: a page's own navigation made I.K.E. fetch any
            # address, the router's included (review of 1.1.19, M1)
            from .userscripts import is_local_name
            typed = nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped
            if not typed:
                # a click or key on this page (after it opened), just now,
                # and each one worth a single offer
                user = max(getattr(self, "_ike_input", -99.0), getattr(self, "_ike_opener_input", -99.0))
                if (time.monotonic() - user > 3 or user <= getattr(self, "_ike_page_since", -99.0)
                        or user == getattr(self, "_ike_offer_input", None)):
                    return False
                self._ike_offer_input = user
            home_ok = typed or is_local_name(self.url().host())
            self.app.userscripts.offer(self.window_ref, url.toString(), home_ok=home_ok)
            return False
        if is_main_frame:
            # bounce tracking (1.1.24, bounce.py): a site that only redirected onward
            acted = getattr(self, "_ike_input", -99.0) > getattr(self, "_ike_page_since", -99.0)
            self.app.bounce.navigation(self, url, nav_type, acted)
            self._ike_page_since = time.monotonic()
            self.nav_scheme = url.scheme().lower()      # where it goes (the loading line, 1.1.23)
            host = url.host().lower()
            sh = self.app.shields
            st = self.settings()
            st.setAttribute(_A.JavascriptEnabled, sh.scripts_allowed(host))
            # video and audio that start by themselves: as the user chose, for all sites or this one
            st.setAttribute(_A.PlaybackRequiresUserGesture, sh.autoplay_blocked(host))
            self._reset_scripts()
            self._set_dark(url, host)
            self._set_scriptlets(url, host)
        return True

    def _external_link(self, url):
        if not self.visible_tab():
            return                           # a tab in the background starts nothing
        if url.scheme().lower() == "mailto":
            # an email: the web mail or program the user chose
            from . import mailto
            mailto.open_link(self.app, url, self.window_ref, page=self)
            return
        if self.ask_external(origin_text(self.url()), url):
            # the desktop portal, else the desktop's own opener (handoff.py, 1.1.24)
            self.app.handoff.open_uri(url, self.window_ref)

    def ask_external(self, origin, url):
        """Ask before a link is handed to another application; True to open it."""
        text = bytes(url.toEncoded()).decode("ascii", "replace")     # exactly what the application gets
        if len(text) > 300:
            text = text[:300] + "…"
        box = QMessageBox(self.window_ref)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(T("Open with another application"))
        box.setText(T("%s wants to open this link with another application:") % origin)
        box.setInformativeText(text)
        box.setTextFormat(Qt.TextFormat.PlainText)
        opened = box.addButton(T("Open"), QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(T("Cancel"), QMessageBox.ButtonRole.RejectRole)
        careful(box, opened, cancel)
        box.exec()
        return box.clickedButton() is opened

    def _add_script(self, name, source, main_world, subframes=True):
        """Install a DocumentCreation script in the page or its subframes."""
        from PyQt6.QtWebEngineCore import QWebEngineScript
        s = QWebEngineScript()
        s.setName(name)
        s.setSourceCode(source)
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld if main_world
                     else QWebEngineScript.ScriptWorldId.ApplicationWorld)
        s.setRunsOnSubFrames(bool(subframes))
        self.scripts().insert(s)
        self._ike_scripts.append(name)

    def _video_host(self, host):
        cfg = self.app.config
        return bool(cfg["video_ad_skip"]) and any(
            host == h or host.endswith("." + h) for h in cfg["video_ad_skip_hosts"])

    def _reset_scripts(self):
        """Remove the scripts installed for the previous page."""
        scripts = self.scripts()
        for name in getattr(self, "_ike_scripts", ()):
            for old in scripts.find(name):
                scripts.remove(old)
        self._ike_scripts = []

    def _reader_prefs(self, text):
        """Light, sepia or dark, the text size, the column's width and serif or
        sans-serif type chosen in reader mode (reader.js)."""
        import json
        try:
            d = json.loads(text)
            theme, size = d["theme"], int(d["size"])
            width, font = d.get("width", "medium"), d.get("font", "serif")
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        if (theme not in ("auto", "light", "sepia", "dark") or not 14 <= size <= 28
                or width not in ("narrow", "medium", "wide") or font not in ("serif", "sans")):
            return
        cfg = self.app.config
        keys = ("reader_theme", "reader_size", "reader_width", "reader_font")
        if tuple(cfg[k] for k in keys) != (theme, size, width, font):
            for k, v in zip(keys, (theme, size, width, font)):
                cfg[k] = v
            cfg.save()

    def _loading_changed(self, info):
        """A site that cannot be reached: I.K.E.'s own error page (errorpage.py)."""
        from . import errorpage
        try:
            if not errorpage.wanted(info):
                return
            from PyQt6.QtWidgets import QApplication
            self.error_info = (info.errorCode(), info.url().toString())
            self.runJavaScript(errorpage.script(info, QApplication.palette()), 1)
        except RuntimeError:
            pass

    def _set_dark(self, url, host):
        """Apply the selected dark renderer to this page, respecting site overrides."""
        from PyQt6.QtGui import QColor
        cfg = self.app.config
        page_url = url.scheme() in ("http", "https", "file")
        on = page_url and self.app.shields.dark_for(host)
        engine = cfg["dark_engine"]
        # 1.1.29: the I.K.E. Dark Engine (darkengine.py, in ApplicationWorld) or
        # Chromium's own dark mode; Dark Reader is no longer part of I.K.E.
        from . import darkengine
        native_on = on and engine == "engine"
        own_on = on and engine != "engine"

        # Qt 6.7+ exposes ForceDarkMode as a page-level WebAttribute.  This lets
        # users exempt a single site instead of forcing Chromium's filter over
        # every site in the profile (which can produce dark boxes in widgets).
        self.settings().setAttribute(_A.ForceDarkMode, bool(native_on))

        # an empty page (a window a site opens, before its address loads) is
        # dark too while dark mode is on for every site (1.1.19: it was white)
        blank = ((url.isEmpty() or url.toString() == "about:blank") and cfg["dark_mode"] == "on"
                 and cfg.get("comp_dark", True))
        # the colour shown before the page paints and between two pages: no
        # white flash. The new tab page's own colour for the new tab page,
        # whatever the dark mode (1.1.23: white for about 0.1 s at every start
        # and every new tab, the owner's "white flash")
        if own_on or (blank and engine != "engine"):
            self.set_backdrop(QColor(darkengine.background(cfg["dark_engine_look"])))
        elif blank:
            self.set_backdrop(DARK_BLANK)
        elif is_newtab(url):
            self.set_backdrop(self.app.shields.newtab_background())
        else:
            self.set_backdrop(QColor(Qt.GlobalColor.white))
        self._dark_on = on
        self._dark_engine = "ike" if engine != "engine" else engine
        profile = self.profile()
        if engine == "engine" or not cfg.get("comp_dark", True):
            darkengine.forget(profile)
        if not page_url or engine == "engine":
            return
        # the page sees its address in ASCII (xn--...): the site is registered so
        ace = bytes(QUrl.toAce(host)).decode("ascii", "replace") if host else ""
        darkengine.prepare(profile, url.toString(), ace or url.scheme() + ":", own_on,
                           self.app.shields.dark_chosen(host), cfg["dark_engine_look"])

    def set_backdrop(self, colour):
        """The page's background colour, the one shown before it paints."""
        from PyQt6.QtGui import QColor
        colour = QColor(colour)
        if colour.rgba() != self._backdrop:
            self._backdrop = colour.rgba()
            self.setBackgroundColor(colour)

    def _set_scriptlets(self, url, host):
        """Install the list-provided scriptlets for the page about to load.

        They go in the profile (see Shields.site_scripts): a script added to
        this page alone would reach the page being left, not the new one. The
        video sites have theirs installed permanently.
        """
        if url.scheme() not in ("http", "https"):
            return
        self.app.shields.site_scripts(self.profile(), host)

    def trusted_click(self, x, y, allow_embedded=False):
        """Dispatch a Qt mouse input event at a validated video-player point.

        Direct YouTube pages use the normal bridge. A separate relay may request
        the same action for a cross-origin YouTube iframe after validating the
        frame origin and contentWindow in the isolated world.
        """
        import json
        import time
        now = time.monotonic()
        if now - getattr(self, "_last_click", 0.0) < 0.5:
            return False
        direct = self._video_host(self.url().host().lower())
        if not direct and not allow_embedded:
            return False
        if direct:
            return self._dispatch_click(x, y, now)
        # a video of another site embedded in this page (review of 1.1.19,
        # L5; the owner chose to harden it): only when the page really holds a
        # frame of a video site, at most once every 3 seconds, and only if the
        # point is still on that frame when the click is made: the page hears
        # the player's request too and could put something of its own there,
        # to get a real click (pop-ups, full screen) without the user
        if now - getattr(self, "_last_embedded", -99.0) < 3 or not self._has_video_frame():
            return False
        if not self._click_point_ok(x, y):
            return False
        self._last_embedded = now
        hosts = [h.lower() for h in self.app.config["video_ad_skip_hosts"]]
        js = ("(function (x, y, hosts) { var e = document.elementFromPoint(x, y);"
              " if (!e || e.tagName !== 'IFRAME') return false; var h;"
              " try { h = new URL(e.src || e.getAttribute('src') || '', document.baseURI).hostname.toLowerCase(); }"
              " catch (err) { return false; }"
              " return hosts.some(function (b) { return h === b || h.endsWith('.' + b); });"
              " })(%s, %s, %s)" % (json.dumps(float(x)), json.dumps(float(y)), json.dumps(hosts)))
        self.runJavaScript(js, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                           lambda ok: self._dispatch_click(x, y, time.monotonic()) if ok is True else None)
        return True

    def _has_video_frame(self):
        """A frame of a video site among this page's frames (Qt 6.8+)."""
        try:
            todo = list(self.mainFrame().children())
        except (AttributeError, RuntimeError):
            return True                  # an engine without the frame list: the other checks remain
        seen = 0
        while todo and seen < 500:
            f = todo.pop()
            seen += 1
            if self._video_host(f.url().host().lower()):
                return True
            todo.extend(f.children())
        return False

    def _click_point_ok(self, x, y):
        view = self.window_ref.view_of(self)
        if view is None or not view.isVisible() or self.window_ref.current_view() is not view:
            return False
        zoom = self.zoomFactor() or 1.0
        return 0 <= x * zoom < view.width() and 0 <= y * zoom < view.height()

    def _dispatch_click(self, x, y, now):
        from PyQt6.QtCore import QCoreApplication, QPointF
        from PyQt6.QtGui import QMouseEvent
        view = self.window_ref.view_of(self)
        if view is None or not view.isVisible() or self.window_ref.current_view() is not view:
            return False
        zoom = self.zoomFactor() or 1.0
        pos = QPointF(x * zoom, y * zoom)
        if not (0 <= pos.x() < view.width() and 0 <= pos.y() < view.height()):
            return False
        self._last_click = now
        target = view.focusProxy() or view
        global_point = view.mapToGlobal(pos.toPoint())
        target_pos = QPointF(target.mapFromGlobal(global_point))
        global_pos = QPointF(global_point)
        left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
        mod = Qt.KeyboardModifier.NoModifier
        # these clicks are I.K.E.'s, not the user's: they must not count as
        # the user's action (downloads, 1.1.17)
        self._ike_synthetic = True
        try:
            for etype, buttons in ((QEvent.Type.MouseMove, none),
                                   (QEvent.Type.MouseButtonPress, left),
                                   (QEvent.Type.MouseButtonRelease, none)):
                button = none if etype == QEvent.Type.MouseMove else left
                event = QMouseEvent(etype, target_pos, global_pos, button, buttons, mod)
                QCoreApplication.sendEvent(target, event)
        finally:
            self._ike_synthetic = False
        return True

    def createWindow(self, wtype):
        page = self._create_window(wtype)
        # a user script opened in a new tab by the user's click can still be
        # offered there (the click happened on this page)
        page._ike_opener_input = getattr(self, "_ike_input", -99.0)
        return page

    def _create_window(self, wtype):
        W = QWebEnginePage.WebWindowType
        win = self.window_ref
        if wtype == W.WebBrowserWindow:
            win = self.app.new_window(private=win.private, open_default=False)
            return win.add_tab(None).page()
        if wtype == W.WebDialog:
            win = self.app.new_window(private=win.private, open_default=False, popup=True)
            return win.add_tab(None).page()
        cur = win.view_of(self)
        view = win.add_tab(None, background=(wtype == W.WebBrowserBackgroundTab), after=cur,
                           container=getattr(cur, "container", None),
                           group=getattr(cur, "group", None))
        return view.page()

    def download(self, url, filename=""):
        """A download I.K.E. itself starts (Save, a context menu, a user
        script's GM_download): the user's own, never held back as a burst."""
        self._ike_input = time.monotonic()
        super().download(url, filename)

    def certificateError(self, error):
        from .osinfo import test_switch
        if test_switch("IKE_TEST_INSECURE") == "1":
            error.acceptCertificate()
            return True
        return False

    def _lan_engine_block(self):
        """The engine's own home-network protection stopped a part of this
        page (1.1.19): the window says so, as for the parts I.K.E. stops
        itself. Only a notice, no button (nothing to allow: the engine has no
        per-site exception), so a page printing the same text gains nothing."""
        from .shields import site_of
        from .userscripts import is_local_name
        page = self.url()
        if page.scheme() not in ("http", "https") or is_local_name(page.host()):
            return
        site = site_of(page.host().lower())
        view = self.window_ref.view_of(self)
        n = getattr(view, "secure_notice", None) if view is not None else None
        if view is None or (n and n.get("url") == page.toString()):
            return
        if self._loaded_url != page.toString():
            self.app.shields.lan_blocked["frame:" + page.toString()] = site     # shown when it loads
            return
        from .securebar import set_notice
        set_notice(view, "lan", page, site)
        view.secure_notice["frame"] = True
        if view is self.window_ref.current_view():
            self.window_ref.secure_bar.show_for(view)

    def javaScriptConsoleMessage(self, level, message, line, source):
        from .userscripts import PREFIX
        if "address space" in message and ("more-private" in message or "Permission was denied" in message):
            self._lan_engine_block()
        if message.startswith(READER_PREFIX):
            self._reader_prefs(message[len(READER_PREFIX):])
            return
        if message.startswith(PREFIX):
            self.app.userscripts.receive(self, message)
            return
        if os.environ.get("IKE_DEBUG"):
            print("[js] %s:%s %s" % (source, line, message))

    # --- protections -------------------------------------------------
    def _protected(self):
        cfg = self.app.config
        url = self.url()
        return (url.scheme() in ("http", "https")
                and (cfg["comp_adblock"] or cfg["comp_consent"])
                and cfg.level_for(url.host()) != "off"
                and not cfg.sensitive_hands_off(url.host().lower())
                and cfg.site_opt(url.host(), "ads") is not False)

    def _inject_cosmetics(self, *_):
        if not self._protected():
            return
        css, self._exceptions, self._generichide = \
            self.app.blocker.cosmetic_css(self.url().toString())
        if css:
            import json
            self.runJavaScript(_COSMETIC_JS % ("a", json.dumps(css)), 1)

    def _load_finished(self, ok):
        url = self.url()
        sh = self.app.shields
        self._loaded_url = url.toString() if ok else None
        if not ok and url.scheme() == "https" and url.host().lower() in sh.upgraded:
            # The secure address of a page asked for over http did not answer.
            # Until 1.1.17 the browser went back to http by itself; someone on
            # the network can make the secure address fail on purpose. Now the
            # page stops and the window says so (securebar.py): only the user
            # can go on without protection.
            sh.upgraded.discard(url.host().lower())
            self._secure_notice("nohttps", url)
            return
        if not ok and url.toString() in sh.lan_blocked:
            site = sh.lan_blocked.pop(url.toString())
            from .securebar import set_notice
            view = self.window_ref.view_of(self)
            if view is not None:
                set_notice(view, "lan", url, site)
                if view is self.window_ref.current_view():
                    self.window_ref.secure_bar.show_for(view)
            return
        if not ok and url.toString() in sh.blocked_pages:
            sh.blocked_pages.discard(url.toString())
            self._secure_notice("blocked", url)
            return
        if ok:
            sh.upgraded.discard(url.host().lower())
            view = self.window_ref.view_of(self)
            if view is not None and getattr(view, "secure_notice", None):
                view.secure_notice = None          # a page that loads is no longer stopped
                if view is self.window_ref.current_view():
                    self.window_ref.secure_bar.show_for(view)
            site = sh.lan_blocked.pop("frame:" + url.toString(), None)
            if site and view is not None:
                # a frame of this page asked for the home network and was stopped
                from .securebar import set_notice
                set_notice(view, "lan", url, site)
                view.secure_notice["frame"] = True
                if view is self.window_ref.current_view():
                    self.window_ref.secure_bar.show_for(view)
        if not ok or not self._protected():
            return
        self._inject_cosmetics()
        if not self._generichide:
            self.runJavaScript(_COLLECT_JS, 1, self._generic)

    def _secure_notice(self, kind, url):
        from .securebar import set_notice
        win = self.window_ref
        view = win.view_of(self)
        if view is None:
            return
        set_notice(view, kind, url)
        if view is win.current_view():
            win.secure_bar.show_for(view)

    def _generic(self, result):
        if not result or len(result) != 2:
            return
        import json
        css = self.app.blocker.generic_css(result[0], result[1], self._exceptions)
        if css:
            self.runJavaScript(_COSMETIC_JS % ("b", json.dumps(css)), 1)

    # --- requests from the page --------------------------------------
    def _permission(self, perm):
        from PyQt6.QtWebEngineCore import QWebEnginePermission as P
        if perm.permissionType() == P.PermissionType.MouseLock:
            # granted at once (games), but never to a tab that is not in view,
            # and always with a notice saying which site has the pointer
            if not self.visible_tab():
                perm.deny()
                return
            perm.grant()
            self.mouse_locked = True
            self.window_ref.show_exclusive_notice(origin_text(perm.origin()), "mouse")
            return
        PT = P.PermissionType
        kinds = {PT.Geolocation: ("location",), PT.MediaAudioCapture: ("microphone",),
                 PT.MediaVideoCapture: ("camera",),
                 PT.MediaAudioVideoCapture: ("camera", "microphone"),
                 PT.Notifications: ("notifications",), PT.ClipboardReadWrite: ("clipboard",),
                 PT.DesktopVideoCapture: ("screen",), PT.DesktopAudioVideoCapture: ("screen",),
                 PT.LocalFontsAccess: ("fonts",)}
        blocked = self.app.config["perm_block"]
        origin = perm.origin().host() or perm.origin().toString()
        if (perm.permissionType() == PT.LocalFontsAccess and
                rank(self.app.config.level_for(origin)) >= rank("strict")):
            perm.deny()
            return
        if any(k in blocked for k in kinds.get(perm.permissionType(), ())):
            perm.deny()
            return
        from .osinfo import test_switch
        if test_switch("IKE_TEST_PERMS") in ("grant", "deny"):
            perm.grant() if test_switch("IKE_TEST_PERMS") == "grant" else perm.deny()
            return
        from . import quietperms
        if quietperms.handle(self, perm):
            return                       # a sign in the address bar instead of a window (1.1.24)
        if not self.visible_tab():
            # a tab in the background waits: its question would appear over the
            # page the user is looking at, which is easy to answer by mistake
            self._wait_for_view(perm)
            return
        self._ask(perm)

    def _ask(self, perm):
        # (the engine remembers the answer for the site: a page that was told
        # no is not asked about again until the user resets the site's permissions)
        origin = perm.origin().host() or perm.origin().toString()
        if self.ask_permission(origin, perm.permissionType()):
            perm.grant()
        else:
            perm.deny()

    def _wait_for_view(self, perm):
        """Keep a permission question until this tab is shown (checked twice a
        second, only while a question waits). Nothing is answered meanwhile:
        the engine would remember a "no" given on the user's behalf."""
        waiting = self.__dict__.setdefault("_perm_waiting", [])
        if len(waiting) >= 8:
            return                       # left unanswered: the page keeps waiting
        # a copy: the object handed to the signal belongs to the engine and is
        # gone once the handler returns
        waiting.append(type(perm)(perm))
        timer = getattr(self, "_perm_timer", None)
        if timer is None:
            from PyQt6.QtCore import QTimer
            timer = self._perm_timer = QTimer(self)
            timer.setInterval(500)
            timer.timeout.connect(self._perm_check)
            # a page that goes elsewhere takes its questions with it
            self.loadStarted.connect(self._perm_drop)
        timer.start()

    def _perm_drop(self):
        self._perm_waiting = []
        if getattr(self, "_perm_timer", None) is not None:
            self._perm_timer.stop()

    def _perm_check(self):
        if not self.visible_tab():
            return
        self._perm_timer.stop()
        waiting, self._perm_waiting = getattr(self, "_perm_waiting", []), []
        answered = {}                    # one question per site and kind, however often it asked
        for w in waiting:
            if not w.isValid():
                continue
            key = (w.origin().toString(), w.permissionType())
            if key not in answered:
                origin = w.origin().host() or w.origin().toString()
                answered[key] = self.ask_permission(origin, w.permissionType())
            w.grant() if answered[key] else w.deny()

    def ask_permission(self, origin, ptype):
        """Ask the user; True to allow."""
        box, allow, _block = permission_box(self.window_ref, origin, ptype)
        box.exec()
        return box.clickedButton() is allow

    def _desktop_media(self, request):
        """Require an explicit user choice before sharing a screen or window."""
        sources = []
        try:
            if "screen" in self.app.config["perm_block"]:
                request.cancel()
                return
            models = (("screen", request.screensModel()),
                      ("window", request.windowsModel()))
            for kind, model in models:
                if model is None:
                    continue
                for row in range(model.rowCount()):
                    index = model.index(row, 0)
                    label = model.data(index, Qt.ItemDataRole.DisplayRole)
                    if not label:
                        label = (T("Screen %d") if kind == "screen" else T("Window %d")) % (row + 1)
                    sources.append((kind, model, row, str(label)))
            if not sources:
                request.cancel()
                return
            origin = self.url().host() or self.url().toString()
            dialog = QDialog(self.window_ref)
            dialog.setWindowTitle(T("Share screen or window"))
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(T("%s wants to capture your screen. Choose exactly what to share.")
                                    % origin, dialog))
            combo = QComboBox(dialog)
            combo.addItem(T("Choose a source…"), None)
            for kind, _model, row, label in sources:
                prefix = T("Screen") if kind == "screen" else T("Window")
                combo.addItem(f"{prefix}: {label}", (kind, row))
            layout.addWidget(combo)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel, parent=dialog)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(T("Share"))
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            combo.currentIndexChanged.connect(
                lambda i: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(i > 0))
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted or combo.currentData() is None:
                request.cancel()
                return
            kind, row = combo.currentData()
            model = next(m for k, m in models if k == kind)
            index = model.index(row, 0)
            if kind == "screen":
                request.selectScreen(index)
            else:
                request.selectWindow(index)
        except Exception:
            request.cancel()

    def visible_tab(self):
        """True if this page is the tab in view (or one side of the split view)."""
        win = self.window_ref
        view = win.view_of(self)
        return (view is not None and view.isVisible() and win.isVisible()
                and not win.isMinimized())

    def _fullscreen(self, request):
        on = request.toggleOn()
        if on and not self.visible_tab():
            request.reject()             # a tab in the background cannot take the screen
            return
        request.accept()
        self.window_ref.set_page_fullscreen(on)
        if on:
            self.window_ref.show_exclusive_notice(origin_text(request.origin()), "fullscreen")
        else:
            self.window_ref.hide_exclusive_notice("fullscreen")

    def release_pointer(self):
        """End a mouse lock in every frame (Esc). The engine also does it when the
        page receives Esc; this covers Esc taken by the browser in full screen."""
        js = "document.pointerLockElement && document.exitPointerLock();"
        self.mouse_locked = False
        self.window_ref.hide_exclusive_notice("mouse")
        main = self.mainFrame() if hasattr(self, "mainFrame") else None
        if main is None:
            self.runJavaScript(js, 1)
            return
        frames = [main]
        while frames:
            f = frames.pop()
            try:
                f.runJavaScript(js, 1)
                frames.extend(f.children())
            except RuntimeError:
                pass


class WebView(QWebEngineView):
    def __init__(self, window, profile):
        super().__init__(window)
        self.window_ref = window
        self.setPage(WebPage(profile, window, self))
        self.muted_by_user = False
        self._watched = None
        self.loadFinished.connect(lambda _ok: self._watch_keys())
        for wa in (QWebEnginePage.WebAction.Copy, QWebEnginePage.WebAction.Cut):
            self.page().action(wa).triggered.connect(self._ensure_copied)
        self._menu_selection = ""
        self._watch_keys()

    def load(self, url):
        # an address the browser opens (address bar, bookmarks, links of its
        # own menus) is the user's act, as a click on the page is
        self.page()._ike_input = time.monotonic()
        super().load(url)

    # --- clipboard safety net ---------------------------------------
    # On some Wayland set-ups the engine's own copy does not reach the system
    # clipboard. After every copy/cut we check and, if needed, write the
    # selected text through Qt ourselves.
    def _watch_keys(self):
        fp = self.focusProxy()
        if fp is not None and fp is not self._watched:
            fp.installEventFilter(self)
            self._watched = fp

    # --- Ctrl + wheel and mouse gestures, on the page itself -----------
    GESTURE_STEP = 30            # pixels of a stroke
    GESTURES = {"L": "back", "R": "forward", "U": "reload", "DR": "close"}

    def _wheel(self, event):
        """Ctrl + wheel: the zoom steps of the Page menu, remembered for the site."""
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False
        self._wheel_sum = getattr(self, "_wheel_sum", 0) + event.angleDelta().y()
        while abs(self._wheel_sum) >= 120:
            step = 1 if self._wheel_sum > 0 else -1
            self._wheel_sum -= 120 * step
            self.window_ref.zoom(step, self)
        return True

    def _gesture(self, obj, event):
        """Right button held and dragged: a gesture; a right click alone still opens the menu."""
        t = event.type()
        right = Qt.MouseButton.RightButton
        if getattr(self, "_replaying", False):
            return False
        if t == QEvent.Type.MouseButtonPress and event.button() == right:
            p = event.position()
            self._stroke = {"anchor": p, "start": p, "global": event.globalPosition(), "dirs": ""}
            return True
        stroke = getattr(self, "_stroke", None)
        if stroke is None:
            return False
        if t == QEvent.Type.MouseMove:
            p = event.position()
            dx, dy = p.x() - stroke["anchor"].x(), p.y() - stroke["anchor"].y()
            if max(abs(dx), abs(dy)) >= self.GESTURE_STEP:
                d = ("R" if dx > 0 else "L") if abs(dx) > abs(dy) else ("D" if dy > 0 else "U")
                if not stroke["dirs"].endswith(d):
                    stroke["dirs"] += d
                stroke["anchor"] = p
            return True
        if t == QEvent.Type.MouseButtonRelease and event.button() == right:
            self._stroke = None
            if stroke["dirs"]:
                self._do_gesture(stroke["dirs"])
                return True
            # no stroke: the press goes to the page after all, and the menu opens as always
            from PyQt6.QtGui import QMouseEvent
            self._replaying = True
            try:
                for kind, buttons in ((QEvent.Type.MouseButtonPress, right), (QEvent.Type.MouseButtonRelease,
                                                                              Qt.MouseButton.NoButton)):
                    QCoreApplication.sendEvent(obj, QMouseEvent(kind, stroke["start"], stroke["global"], right,
                                                                buttons, event.modifiers()))
            finally:
                self._replaying = False
            return True
        return False

    # --- "Open selected text with middle click" (ikeextensions.py, 1.1.20) ---
    def _middle_click(self, event):
        """A middle click (press and release in place) on an empty part of the
        page opens the desktop's selected text, as an address or a search, in
        this tab. Links, fields, buttons, frames and media keep their own
        middle click; with "Automatic scrolling" on, that one takes it."""
        from . import ikeextensions
        cfg = self.window_ref.app.config
        if not ikeextensions.on(cfg, "middleclick") or ikeextensions.on(cfg, "autoscroll"):
            return
        p = event.position()
        if event.type() == QEvent.Type.MouseButtonPress:
            self._mid_press = p
            return
        start, self._mid_press = getattr(self, "_mid_press", None), None
        if start is None or abs(p.x() - start.x()) + abs(p.y() - start.y()) > 6 \
                or event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return
        if self.url().scheme() not in ("http", "https", "file", "ike"):
            return
        text = " ".join(ikeextensions.primary_selection().split())
        if not text or len(text) > ikeextensions.MAX_SELECTION:
            return
        zoom = self.zoomFactor() or 1.0
        self.page().runJavaScript(ikeextensions.EMPTY_AT_JS % (p.x() / zoom, p.y() / zoom),
                                  QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                  lambda empty, t=text: self._open_selection(t) if empty is True else None)

    def _open_selection(self, text):
        win = self.window_ref
        try:
            url = win.resolve(text)
        except RuntimeError:
            return
        if url is None:
            return
        if url.scheme().lower() not in ("http", "https"):
            # never code (javascript:), data or a file of this computer: a search instead
            url = QUrl(win.app.shields.search_url(text))
        self.last_middle_open = url.toString()
        self.load(url)

    def _do_gesture(self, dirs):
        action = self.GESTURES.get(dirs)
        self.last_gesture = action or ""
        if action == "back":
            self.back()
        elif action == "forward":
            self.forward()
        elif action == "reload":
            self.reload()
        elif action == "close":
            QTimer.singleShot(0, lambda: self.window_ref.close_tab(self))

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress) \
                and not getattr(self.page(), "_ike_synthetic", False):
            self.page()._ike_input = time.monotonic()   # the user acts on the page (downloads)
            self.window_ref.app.bounce.used(self.page())     # a site the user used (bounce.py)
        if t == QEvent.Type.Wheel and self._wheel(event):
            return True
        if t == QEvent.Type.NativeGesture:                # touchpad: swipe and pinch (1.1.24)
            from .gestures import handle
            if handle(self, event):
                return True
        if (t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)
                and self.window_ref.app.config["mouse_gestures"] and self._gesture(obj, event)):
            return True
        if (t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease)
                and event.button() == Qt.MouseButton.MiddleButton):
            self._middle_click(event)           # never taken from the page: links still open
        if event.type() == QEvent.Type.KeyPress:
            mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            key = event.key()
            if key == Qt.Key.Key_Escape and self.page().mouse_locked:
                self.page().release_pointer()
            if mods == Qt.KeyboardModifier.ControlModifier and key in (
                    Qt.Key.Key_C, Qt.Key.Key_X, Qt.Key.Key_Insert):
                text = self.selectedText()
                if text:
                    QTimer.singleShot(150, lambda t=text: self._ensure_copied(text=t))
        return False

    def _ensure_copied(self, *_a, text=None, final=False):
        """Called after a copy/cut from the keyboard, the Edit menu or the
        right-click menu. Checks twice: right after a menu closes the window may
        not have the keyboard focus back yet, and Wayland then drops the copy."""
        if text is None:
            text = self.selectedText()
            if not text:
                return
            QTimer.singleShot(150, lambda t=text: self._ensure_copied(text=t))
            return
        cb = QGuiApplication.clipboard()
        if cb.text() != text and cb.text().replace("\r", "") != text:
            if os.environ.get("IKE_DEBUG"):
                print("[clipboard] engine copy did not arrive, writing it via Qt")
            cb.setText(text)
        if not final:
            QTimer.singleShot(550, lambda t=text: self._ensure_copied(text=t, final=True))

    def _osd_for(self, menu):
        """The quick actions of the page's menu say they were done (1.1.24):
        an address copied, a link bookmarked (window.osd)."""
        said = {T("Copy link address"): (T("Link copied"), "edit-copy"),
                T("Copy image address"): (T("Link copied"), "edit-copy"),
                T("Copy media address"): (T("Link copied"), "edit-copy"),
                T("Bookmark this link"): (T("Bookmark added"), "bookmark-new")}
        win = self.window_ref
        for a in menu.actions():
            done = said.get(a.text())
            if done is not None:
                a.triggered.connect(lambda _c=False, d=done: win.osd(*d))

    def contextMenuEvent(self, event):
        from .contextmenu import build
        old = getattr(self, "_ctx_menu", None)
        if old is not None:
            try:
                old.close()
                old.deleteLater()
            except RuntimeError:
                pass
        # Keep a reference: a menu held only by a local variable is destroyed
        # as soon as this method returns, and nothing would be shown.
        self._ctx_menu = build(self, self.lastContextMenuRequest())
        self._osd_for(self._ctx_menu)
        self._ctx_menu.popup(event.globalPos())
        event.accept()


# Dark PDFs (1.1.24, off by default): the engine's PDF viewer is a plugin in
# an <embed> of a page of its own (document.contentType "application/pdf");
# its colours turned around, the hues kept. Run in I.K.E.'s own world, only
# when the switch is on (nothing on other pages' loads while it is off).
DARK_PDF_JS = ("(function(on){if(document.contentType!=='application/pdf')return false;"
               "var e=document.querySelector('embed[type=\"application/pdf\"]')||document.documentElement;"
               "e.style.filter=on?'invert(0.9) hue-rotate(180deg)':'';return true;})(%s)")


def dark_pdf(view, on, done=None):
    """Dark colours for a PDF shown in the engine's viewer (Settings →
    Web pages → Show PDFs with dark colours); any other page is left alone."""
    try:
        page = view.page()
    except RuntimeError:
        return
    if page is None:
        return
    js = DARK_PDF_JS % ("true" if on else "false")
    if done is None:
        page.runJavaScript(js, 1)
    else:
        page.runJavaScript(js, 1, done)


def notify(notification):
    """Web notifications through the desktop notification service."""
    from .osinfo import notify as desktop_notify
    try:
        desktop_notify(notification.title(), notification.message())
        notification.show()
    except (OSError, RuntimeError):
        pass
