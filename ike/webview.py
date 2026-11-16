"""Web page and view classes."""

import os

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout

from .config import RES_DIR, rank
from .i18n import T

_A = QWebEngineSettings.WebAttribute

_COSMETIC_JS = """(function(css){
 var id='ice-cosmetic-%s';
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

_DARK_SRC = None

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


class WebPage(QWebEnginePage):
    def __init__(self, profile, window, parent=None):
        super().__init__(profile, parent)
        self.window_ref = window
        self.app = window.app
        self._exceptions = set()
        self._generichide = False
        self.mouse_locked = False
        self.loadStarted.connect(lambda: setattr(self, "mouse_locked", False))
        self.permissionRequested.connect(self._permission)
        self.fullScreenRequested.connect(self._fullscreen)
        self.urlChanged.connect(self._inject_cosmetics)
        self.loadFinished.connect(self._load_finished)
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
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if (is_main_frame and url.scheme() in ("http", "https")
                and url.path().lower().endswith(".user.js")
                and self.app.config["userscripts_enabled"]):
            # a user script: offer to install it instead of showing its text
            self.app.userscripts.offer(self.window_ref, url.toString())
            return False
        if is_main_frame:
            host = url.host().lower()
            sh = self.app.shields
            st = self.settings()
            st.setAttribute(_A.JavascriptEnabled, sh.scripts_allowed(host))
            self._reset_scripts()
            self._set_dark(url, host)
            self._set_scriptlets(url, host)
        return True

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

    def _set_dark(self, url, host):
        """Apply the selected dark renderer to this page, respecting site overrides."""
        import json

        from PyQt6.QtGui import QColor
        cfg = self.app.config
        page_url = url.scheme() in ("http", "https", "file")
        on = page_url and self.app.shields.dark_for(host)
        engine = cfg["dark_engine"]
        reader_on = on and engine == "reader"
        native_on = on and engine == "engine"

        # Qt 6.7+ exposes ForceDarkMode as a page-level WebAttribute.  This lets
        # users exempt a single site instead of forcing Chromium's filter over
        # every site in the profile (which can produce dark boxes in widgets).
        self.settings().setAttribute(_A.ForceDarkMode, bool(native_on))

        if (on, engine) != (getattr(self, "_dark_on", None),
                            getattr(self, "_dark_engine", None)):
            # also the colour shown between two pages: no white flash
            self.setBackgroundColor(QColor("#181a1b") if reader_on else QColor(Qt.GlobalColor.white))
        self._dark_on = on
        self._dark_engine = engine
        if not reader_on:
            return
        global _DARK_SRC
        if _DARK_SRC is None:
            _DARK_SRC = ((RES_DIR / "darkmode.js").read_text("utf-8")
                         .replace("__IKE_DR_LIB__", (RES_DIR / "darkreader.js").read_text("utf-8")))
        theme = dict(cfg["dark_theme"]) if isinstance(cfg["dark_theme"], dict) else {}
        self._add_script("ike-dark", _DARK_SRC.replace("__IKE_DR_CFG__", json.dumps({"theme": theme})),
                         False)

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
        import time

        from PyQt6.QtCore import QCoreApplication, QPointF
        from PyQt6.QtGui import QMouseEvent
        now = time.monotonic()
        if now - getattr(self, "_last_click", 0.0) < 0.5:
            return False
        if not self._video_host(self.url().host().lower()) and not allow_embedded:
            return False
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
        for etype, buttons in ((QEvent.Type.MouseMove, none),
                               (QEvent.Type.MouseButtonPress, left),
                               (QEvent.Type.MouseButtonRelease, none)):
            button = none if etype == QEvent.Type.MouseMove else left
            event = QMouseEvent(etype, target_pos, global_pos, button, buttons, mod)
            QCoreApplication.sendEvent(target, event)
        return True

    def createWindow(self, wtype):
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

    def certificateError(self, error):
        if os.environ.get("IKE_TEST_INSECURE") == "1":
            error.acceptCertificate()
            return True
        return False

    def javaScriptConsoleMessage(self, level, message, line, source):
        from .userscripts import PREFIX
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
        if not ok and url.scheme() == "https" and url.host().lower() in sh.upgraded:
            # HTTPS upgrade failed: fall back to plain HTTP for this session.
            host = url.host().lower()
            sh.upgraded.discard(host)
            sh.http_allowed.add(host)
            plain = QUrl(url)
            plain.setScheme("http")
            self.load(plain)
            return
        if ok:
            sh.upgraded.discard(url.host().lower())
        if not ok or not self._protected():
            return
        self._inject_cosmetics()
        if not self._generichide:
            self.runJavaScript(_COLLECT_JS, 1, self._generic)

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
        if os.environ.get("IKE_TEST_PERMS"):
            perm.grant() if os.environ["IKE_TEST_PERMS"] == "grant" else perm.deny()
            return
        box = QMessageBox(self.window_ref)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(T("Permission request"))
        box.setText(T("%s wants to %s.") % (origin, permission_text(perm.permissionType())))
        allow = box.addButton(T("Allow"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(T("Block"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is allow:
            perm.grant()
        else:
            perm.deny()

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

    # --- clipboard safety net ---------------------------------------
    # On some Wayland set-ups the engine's own copy does not reach the system
    # clipboard. After every copy/cut we check and, if needed, write the
    # selected text through Qt ourselves.
    def _watch_keys(self):
        fp = self.focusProxy()
        if fp is not None and fp is not self._watched:
            fp.installEventFilter(self)
            self._watched = fp

    def eventFilter(self, obj, event):
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
        self._ctx_menu.popup(event.globalPos())
        event.accept()


def notify(notification):
    """Web notifications through the desktop notification service."""
    from .osinfo import notify as desktop_notify
    try:
        desktop_notify(notification.title(), notification.message())
        notification.show()
    except (OSError, RuntimeError):
        pass
