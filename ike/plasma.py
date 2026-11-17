"""Desktop integration through D-Bus, built in (what the Plasma Browser
Integration extension does, with nothing to install):

- media controls (MPRIS): the tab playing sound appears in Plasma's media
  widget, on the lock screen and answers the media keys (play, pause, stop,
  seek); also used by GNOME and other desktops;
- downloads in Plasma's notifications, with progress, speed and cancel;
- open tabs and bookmarks in KRunner (the search of Plasma's launcher);
- "Send to device": a page or link to a phone paired with KDE Connect.

Keeping the screen on while a video plays needs nothing from I.K.E.: the web
engine itself asks the desktop (org.freedesktop.ScreenSaver).

Each part can be switched off in Settings → General. Nothing is started when
there is no session bus or jeepney is not installed. Pages are only read from
I.K.E.'s own isolated script world: nothing is added to the pages' scripts.
"""

import json
import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript

from . import APP_ID, APP_NAME
from .desktopbus import Bus, BusError, introspection

MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS = "org.mpris.MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"
PROPS = "org.freedesktop.DBus.Properties"
RUNNER_PATH = "/runner"
KDECONNECT = "org.kde.kdeconnect"
JOBS = "org.kde.JobViewServer"
_WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld
_WORLD_ID = int(_WORLD.value)
POLL_MS = 1000
FRAMES_MAX = 16             # embedded players: how many frames of a page are looked at
LAUNCHER = "com.canonical.Unity.LauncherEntry"

# Read the media of the page from I.K.E.'s isolated world: the elements are the
# page's own, the session metadata is what the site declared.
_MEDIA_JS = r"""(function () {
  var ms = Array.prototype.slice.call(document.querySelectorAll('video, audio'));
  if (!ms.length) return null;
  var m = ms.filter(function (e) { return !e.paused && !e.ended; })[0]
       || ms.filter(function (e) { return e.currentTime > 0; })[0] || ms[0];
  var md = navigator.mediaSession && navigator.mediaSession.metadata, art = '', acts = '';
  try {      // "next" / "previous" offered by the page (mediahook.js, main world)
    var ans = 'ike-media-answer-__TOKEN__', f = function (e) { acts = String(e.detail || ''); };
    window.addEventListener(ans, f);
    window.dispatchEvent(new CustomEvent('ike-media-__TOKEN__', {detail: 'query'}));
    window.removeEventListener(ans, f);
  } catch (e) {}
  if (md && md.artwork && md.artwork.length) art = md.artwork[md.artwork.length - 1].src || '';
  return {playing: !m.paused && !m.ended, video: m.tagName === 'VIDEO',
          pos: m.currentTime || 0, dur: isFinite(m.duration) ? m.duration : 0,
          title: (md && md.title) || document.title || '', artist: (md && md.artist) || '',
          album: (md && md.album) || '', art: art, volume: m.muted ? 0 : m.volume,
          next: acts.indexOf('n') >= 0, prev: acts.indexOf('p') >= 0};
})()"""

_CMD_JS = r"""(function (cmd, arg) {
  var ms = Array.prototype.slice.call(document.querySelectorAll('video, audio'));
  var m = ms.filter(function (e) { return !e.paused && !e.ended; })[0]
       || ms.filter(function (e) { return e.currentTime > 0; })[0] || ms[0];
  if (!m) return false;
  if (cmd === 'play') m.play();
  else if (cmd === 'pause') m.pause();
  else if (cmd === 'toggle') { if (m.paused) m.play(); else m.pause(); }
  else if (cmd === 'stop') { m.pause(); m.currentTime = 0; }
  else if (cmd === 'seek') m.currentTime = Math.max(0, m.currentTime + arg);
  else if (cmd === 'pos') m.currentTime = Math.max(0, arg);
  else if (cmd === 'volume') { m.muted = false; m.volume = Math.max(0, Math.min(1, arg)); }
  return true;
})(%s, %s)"""

_ACTION_JS = "window.dispatchEvent(new CustomEvent('ike-media-%s', {detail: %s})); true"

_MPRIS_XML = introspection({
    MPRIS: '<method name="Raise"/><method name="Quit"/>'
           '<property name="CanQuit" type="b" access="read"/><property name="CanRaise" type="b" access="read"/>'
           '<property name="HasTrackList" type="b" access="read"/><property name="Identity" type="s" access="read"/>'
           '<property name="DesktopEntry" type="s" access="read"/>'
           '<property name="SupportedUriSchemes" type="as" access="read"/>'
           '<property name="SupportedMimeTypes" type="as" access="read"/>',
    PLAYER: '<method name="Next"/><method name="Previous"/><method name="Pause"/><method name="PlayPause"/>'
            '<method name="Stop"/><method name="Play"/><method name="Seek"><arg type="x" name="Offset"/></method>'
            '<method name="SetPosition"><arg type="o" name="TrackId"/><arg type="x" name="Position"/></method>'
            '<method name="OpenUri"><arg type="s" name="Uri"/></method>'
            '<signal name="Seeked"><arg type="x" name="Position"/></signal>'
            '<property name="PlaybackStatus" type="s" access="read"/><property name="Rate" type="d" access="readwrite"/>'
            '<property name="Metadata" type="a{sv}" access="read"/><property name="Volume" type="d" access="readwrite"/>'
            '<property name="Position" type="x" access="read"/><property name="MinimumRate" type="d" access="read"/>'
            '<property name="MaximumRate" type="d" access="read"/><property name="CanGoNext" type="b" access="read"/>'
            '<property name="CanGoPrevious" type="b" access="read"/><property name="CanPlay" type="b" access="read"/>'
            '<property name="CanPause" type="b" access="read"/><property name="CanSeek" type="b" access="read"/>'
            '<property name="CanControl" type="b" access="read"/>',
    PROPS: '<method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/>'
           '<arg type="v" direction="out"/></method><method name="GetAll"><arg type="s" direction="in"/>'
           '<arg type="a{sv}" direction="out"/></method><method name="Set"><arg type="s" direction="in"/>'
           '<arg type="s" direction="in"/><arg type="v" direction="in"/></method>'
           '<signal name="PropertiesChanged"><arg type="s"/><arg type="a{sv}"/><arg type="as"/></signal>',
})

RUNNER_DESKTOP = """[Desktop Entry]
Name=I.K.E. tabs and bookmarks
Comment=Switch to an open tab or open a bookmark of I.K.E.
Type=Service
Icon=ike-browser
X-KDE-ServiceTypes=Plasma/Runner
X-KDE-PluginInfo-Name=ike-browser
X-KDE-PluginInfo-EnabledByDefault=true
X-Plasma-API=DBus
X-Plasma-API-Minimum-Version=2.0
X-Plasma-DBusRunner-Service={service}
X-Plasma-DBusRunner-Path={path}
X-Plasma-Request-Actions-Once=true
X-Plasma-Runner-Min-Letter-Count=3
"""


def runner_file():
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "krunner" / "dbusplugins" / "ike-browser.desktop"


def _member(msg):
    from jeepney import HeaderFields
    f = msg.header.fields
    return f.get(HeaderFields.interface), f.get(HeaderFields.member)


class DesktopIntegration(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.bus = None
        self.mpris_name = "org.mpris.MediaPlayer2.ike_browser.instance%d" % os.getpid()
        self.runner_name = "org.kde.ike_browser.krunner.instance%d" % os.getpid()
        self.player = None          # the view whose media is shown
        self.player_frame = None    # its frame with the media, None for the main frame
        self.state = None           # last media state read from it
        self._track = 0
        self._track_key = None
        self._mpris_on = False
        self._runner_on = False
        self.devices = {}           # KDE Connect: id -> name (paired and reachable)
        self.jobs = {}              # id(download) -> [item, job path or "", last update time]
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._poll_media)
        self._connect_tried = False
        QTimer.singleShot(0, self.settings_changed)

    def opt(self, key):
        return bool(self.app.config.get(key, True))

    # --- start / stop --------------------------------------------------------
    def _ensure_bus(self):
        if self.bus is not None and self.bus.connected:
            return True
        if self._connect_tried and self.bus is None:
            return False
        self._connect_tried = True
        bus = Bus(self)
        if not bus.connect():
            self.bus = None
            return False
        self.bus = bus
        bus.export(MPRIS_PATH, self._mpris_call)
        bus.export(RUNNER_PATH, self._runner_call)
        bus.on_signal(KDECONNECT, "/modules/kdeconnect", "org.kde.kdeconnect.daemon", None,
                      lambda _m: self._refresh_devices())
        bus.on_signal("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                      "NameOwnerChanged", self._owner_changed)
        bus.on_signal(JOBS, None, "org.kde.JobViewV3", None, self._job_signal)
        return True

    def settings_changed(self):
        wanted = any(self.opt(k) for k in ("di_media", "di_downloads", "di_krunner", "di_kdeconnect"))
        if not wanted:
            self._set_runner(False)
            self._release_player()
            return
        if not self._ensure_bus():
            return
        self._set_runner(self.opt("di_krunner"))
        if not self.opt("di_media"):
            self._release_player()
        if self.opt("di_kdeconnect"):
            self._refresh_devices()
        else:
            self.devices = {}

    def shutdown(self):
        self._release_player()
        for key in list(self.jobs):
            item = self.jobs[key][0]
            self.download_done(item, False, "")
        if self.bus is not None:
            self.bus.close()

    # --- media (MPRIS) -------------------------------------------------------
    def watch_view(self, view):
        """Called for every new tab: a tab that starts playing sound becomes the player."""
        page = view.page()
        page.recentlyAudibleChanged.connect(lambda on, v=view: on and self._candidate(v))
        view.destroyed.connect(lambda *_a, v=view: self._view_gone(v))

    def _candidate(self, view):
        if not self.opt("di_media") or getattr(view.window_ref, "private", False):
            return
        if not self._ensure_bus():
            return
        self.player = view
        self.player_frame = None
        self._poll.start()
        self._poll_media()

    def _view_gone(self, view):
        if self.player is view:
            self.player = None
            self._release_player()

    def _poll_media(self):
        v = self.player
        if v is None:
            self._release_player()
            return
        try:
            page = v.page()
        except RuntimeError:
            self._release_player()
            return
        if page is None:
            self._release_player()
            return
        js = _MEDIA_JS.replace("__TOKEN__", self._token(page))
        frame = self.player_frame
        if frame is not None and frame.isValid():
            # the embedded player found before: ask it first
            frame.runJavaScript(js, _WORLD_ID, lambda st, v=v, f=frame: self._frame_state(v, st, f, js))
        else:
            self.player_frame = None
            page.mainFrame().runJavaScript(js, _WORLD_ID, lambda st, v=v: self._frame_state(v, st, None, js))

    def _token(self, page):
        try:
            return self.app.shields.media_token(page.profile())
        except Exception:
            return ""

    def _frames(self, page):
        """The frames of a page below the main one, nearest first (at most FRAMES_MAX)."""
        out, todo = [], list(page.mainFrame().children())
        while todo and len(out) < FRAMES_MAX:
            f = todo.pop(0)
            if f.isValid():
                out.append(f)
                todo.extend(f.children())
        return out

    def _frame_state(self, view, st, frame, js, rest=None):
        """The media of the page's main frame, else of its frames (embedded
        players, e.g. a video inside an article): the first that has one."""
        if view is not self.player:
            return
        if st:
            self.player_frame = frame
            self._media_state(view, st)
            return
        if rest is None:
            try:
                rest = [f for f in self._frames(view.page()) if f != frame]
            except RuntimeError:
                rest = []
            if frame is not None:           # the frame's player is gone: try the main frame too
                rest.insert(0, view.page().mainFrame())
        if not rest:
            self.player_frame = None
            self._media_state(view, None)
            return
        f = rest.pop(0)
        f.runJavaScript(js, _WORLD_ID, lambda st2, v=view, f=f, r=rest: self._frame_state(
            v, st2, None if f.isMainFrame() else f, js, r))

    def _target(self):
        """Where the player's media is: its frame, or the page's main frame."""
        f = self.player_frame
        if f is not None and f.isValid():
            return f
        return self.player.page().mainFrame()

    def _media_state(self, view, st):
        if view is not self.player:
            return
        if not st:
            self.player = None
            self._release_player()
            return
        old = self.state or {}
        key = (st.get("title"), st.get("artist"), view.url().toString())
        if key != self._track_key:
            self._track_key = key
            self._track += 1
        self.state = st
        if not self._mpris_on:
            self._mpris_on = True
            self.bus.request_name(self.mpris_name)
            return
        changed = {}
        if old.get("playing") != st.get("playing"):
            changed["PlaybackStatus"] = self._prop_player("PlaybackStatus")
        if any(old.get(k) != st.get(k) for k in ("title", "artist", "album", "art", "dur")) \
                or key != getattr(self, "_sent_key", None):
            self._sent_key = key
            changed["Metadata"] = self._prop_player("Metadata")
            changed["CanSeek"] = self._prop_player("CanSeek")
        if old.get("volume") != st.get("volume"):
            changed["Volume"] = self._prop_player("Volume")
        for key, prop in (("next", "CanGoNext"), ("prev", "CanGoPrevious")):
            if bool(old.get(key)) != bool(st.get(key)):
                changed[prop] = self._prop_player(prop)
        if changed:
            self.bus.emit(MPRIS_PATH, PROPS, "PropertiesChanged", "sa{sv}as", (PLAYER, changed, []))

    def _release_player(self):
        self._poll.stop()
        self.player = None
        self.player_frame = None
        self.state = None
        if self._mpris_on and self.bus is not None:
            self.bus.release_name(self.mpris_name)
        self._mpris_on = False

    def _command(self, cmd, arg=0):
        v = self.player
        if v is None:
            return
        self._target().runJavaScript(_CMD_JS % (json.dumps(cmd), json.dumps(arg)), _WORLD_ID,
                                     lambda _r: QTimer.singleShot(150, self._poll_media))

    def _action(self, name):
        """The page's own "next" / "previous" (declared with the Media Session API)."""
        v = self.player
        if v is None:
            return
        token = self._token(v.page())
        if token:
            self._target().runJavaScript(_ACTION_JS % (token, json.dumps(name)), _WORLD_ID,
                                         lambda _r: QTimer.singleShot(400, self._poll_media))

    def _prop_mpris(self, name):
        return {"CanQuit": ("b", False), "CanRaise": ("b", True), "HasTrackList": ("b", False),
                "Identity": ("s", APP_NAME), "DesktopEntry": ("s", APP_ID),
                "SupportedUriSchemes": ("as", ["http", "https"]),
                "SupportedMimeTypes": ("as", [])}.get(name)

    def _metadata(self):
        st = self.state or {}
        md = {"mpris:trackid": ("o", "/org/ike/track/%d" % self._track),
              "xesam:title": ("s", st.get("title") or ""),
              "xesam:url": ("s", self.player.url().toString() if self.player else "")}
        if st.get("artist"):
            md["xesam:artist"] = ("as", [st["artist"]])
        if st.get("album"):
            md["xesam:album"] = ("s", st["album"])
        if st.get("art"):
            md["mpris:artUrl"] = ("s", st["art"])
        if st.get("dur"):
            md["mpris:length"] = ("x", int(st["dur"] * 1e6))
        return md

    def _prop_player(self, name):
        st = self.state or {}
        values = {
            "PlaybackStatus": ("s", "Playing" if st.get("playing") else "Paused"),
            "Rate": ("d", 1.0), "MinimumRate": ("d", 1.0), "MaximumRate": ("d", 1.0),
            "Metadata": ("a{sv}", self._metadata()),
            "Volume": ("d", float(st.get("volume") or 0.0)),
            "Position": ("x", int(float(st.get("pos") or 0) * 1e6)),
            "CanGoNext": ("b", bool(st.get("next"))), "CanGoPrevious": ("b", bool(st.get("prev"))),
            "CanPlay": ("b", True), "CanPause": ("b", True),
            "CanSeek": ("b", bool(st.get("dur"))), "CanControl": ("b", True),
        }
        return values.get(name)

    def _mpris_call(self, msg):
        iface, member = _member(msg)
        body = msg.body
        if member == "Introspect":
            return "s", (_MPRIS_XML,)
        if iface == PROPS or member in ("Get", "GetAll", "Set") and iface is None:
            if member == "Get":
                v = self._prop_mpris(body[1]) if body[0] == MPRIS else self._prop_player(body[1])
                if v is None:
                    raise BusError("org.freedesktop.DBus.Error.InvalidArgs", "No such property")
                return "v", (v,)
            if member == "GetAll":
                names = (("CanQuit", "CanRaise", "HasTrackList", "Identity", "DesktopEntry",
                          "SupportedUriSchemes", "SupportedMimeTypes") if body[0] == MPRIS else
                         ("PlaybackStatus", "Rate", "MinimumRate", "MaximumRate", "Metadata", "Volume",
                          "Position", "CanGoNext", "CanGoPrevious", "CanPlay", "CanPause", "CanSeek",
                          "CanControl") if body[0] == PLAYER else ())
                get = self._prop_mpris if body[0] == MPRIS else self._prop_player
                return "a{sv}", ({n: get(n) for n in names},)
            if member == "Set":
                if body[1] == "Volume":
                    self._command("volume", float(body[2][1]))
                return "", ()
            return None
        if member == "Raise":
            v = self.player
            if v is not None:
                win = v.window_ref
                win.set_current(v) if v in win.views else None
                win.showNormal() if win.isMinimized() else None
                win.raise_()
                win.activateWindow()
            return "", ()
        if member == "Quit":
            return "", ()
        cmds = {"Play": "play", "Pause": "pause", "PlayPause": "toggle", "Stop": "stop"}
        if member in cmds:
            self._command(cmds[member])
            return "", ()
        if member in ("Next", "Previous"):
            st = self.state or {}
            if st.get("next" if member == "Next" else "prev"):
                self._action("nexttrack" if member == "Next" else "previoustrack")
            return "", ()
        if member == "Seek":
            self._command("seek", body[0] / 1e6)
            pos = float((self.state or {}).get("pos") or 0) + body[0] / 1e6
            self.bus.emit(MPRIS_PATH, PLAYER, "Seeked", "x", (int(max(0, pos) * 1e6),))
            return "", ()
        if member == "SetPosition":
            if body[0] == "/org/ike/track/%d" % self._track:
                self._command("pos", body[1] / 1e6)
                self.bus.emit(MPRIS_PATH, PLAYER, "Seeked", "x", (int(body[1]),))
            return "", ()
        if member == "OpenUri":
            win = self.app.active_window()
            if win is not None and QUrl(body[0]).scheme() in ("http", "https"):
                win.add_tab(body[0])
            return "", ()
        return None

    # --- KRunner -------------------------------------------------------------
    def _set_runner(self, on):
        f = runner_file()
        if on and self.bus is not None and self.bus.connected:
            if not self._runner_on:
                self._runner_on = True
                self.bus.request_name(self.runner_name)
            text = RUNNER_DESKTOP.format(service="org.kde.ike_browser.krunner.*", path=RUNNER_PATH)
            try:
                if not f.exists() or f.read_text("utf-8") != text:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(text, "utf-8")
                    self._runner_reload()
            except OSError:
                pass
        else:
            if self._runner_on and self.bus is not None:
                self.bus.release_name(self.runner_name)
            self._runner_on = False
            if not on:
                try:
                    f.unlink()
                    self._runner_reload()
                except OSError:
                    pass

    def _runner_reload(self):
        """Tell KRunner its plugins changed, as System Settings does when a
        search plugin is switched on or off: it looks at the plugin folders
        again, so I.K.E. is found without logging out the first time."""
        if self.bus is not None and self.bus.connected:
            self.bus.emit("/krunnerrc", "org.kde.kconfig.notify", "ConfigChanged", "a{saay}",
                          ({"Plugins": [b"ike-browserEnabled"]},))

    def matches(self, query):
        """Open tabs and bookmarks whose title or address contains every word."""
        words = [w for w in query.lower().split() if w]
        if not words or len(query.strip()) < 3:
            return []
        out = []
        for wi, w in enumerate(self.app.windows):
            if w.private:
                continue
            for v in w.all_views():
                url = (getattr(v, "pending_url", None) or v.url().toString())
                title = v.title() or url
                hay = (title + " " + url).lower()
                if all(x in hay for x in words):
                    rel = 0.9 if words[0] in title.lower() else 0.7
                    page = v.page()
                    acts = ["close"]
                    if page.isAudioMuted():
                        acts.insert(0, "unmute")
                    elif page.recentlyAudible():
                        acts.insert(0, "mute")
                    out.append(("tab:%d:%d" % (wi, id(v)), title, "ike-browser", 70, rel,
                                {"subtext": ("s", url), "actions": ("as", acts)}))
        seen = {m[5]["subtext"][1] for m in out}
        try:
            marks = self.app.storage.bookmarks()
        except Exception:
            marks = []
        for url, title, _folder in marks:
            title = title or url
            if not url or url in seen:
                continue
            if all(x in (title + " " + url).lower() for x in words):
                out.append(("bm:" + url, title, "bookmarks", 50, 0.5, {"subtext": ("s", url)}))
            if len(out) >= 30:
                break
        return out[:30]

    def _run_match(self, match_id, action=""):
        if match_id.startswith("tab:"):
            _t, _wi, vid = match_id.split(":", 2)
            for w in self.app.windows:
                for v in w.all_views():
                    if str(id(v)) == vid:
                        if action in ("mute", "unmute"):
                            if v.page().isAudioMuted() != (action == "mute"):
                                w.toggle_mute(v)
                            return
                        if action == "close":
                            w.close_tab(v)
                            return
                        if v not in w.views and hasattr(w, "switch_workspace"):
                            for name, views in w.workspaces.items():
                                if v in views:
                                    w.switch_workspace(name)
                        w.set_current(v)
                        if w.isMinimized():
                            w.showNormal()
                        w.raise_()
                        w.activateWindow()
                        return
        elif match_id.startswith("bm:"):
            url = match_id[3:]
            win = self.app.active_window() or self.app.new_window(open_default=False)
            win.add_tab(url)
            win.raise_()
            win.activateWindow()

    def _runner_call(self, msg):
        _iface, member = _member(msg)
        if member == "Match":
            return "a(sssida{sv})", (self.matches(msg.body[0]),)
        if member == "Actions":
            from .i18n import T
            return "a(sss)", ([("mute", T("Mute tab"), "audio-volume-muted"),
                               ("unmute", T("Unmute tab"), "audio-volume-high"),
                               ("close", T("Close tab"), "tab-close")],)
        if member == "Run":
            body = msg.body
            QTimer.singleShot(0, lambda m=body[0], a=(body[1] if len(body) > 1 else ""): self._run_match(m, a))
            return "", ()
        if member == "Teardown":
            return "", ()
        if member == "Config":
            return "a{sv}", ({},)
        if member == "Introspect":
            return "s", (introspection({"org.kde.krunner1": (
                '<method name="Actions"><arg type="a(sss)" direction="out"/></method>'
                '<method name="Match"><arg type="s" direction="in"/>'
                '<arg type="a(sssida{sv})" direction="out"/></method>'
                '<method name="Run"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>'
                '<method name="Teardown"/>')}),)
        return None

    # --- KDE Connect ---------------------------------------------------------
    def _owner_changed(self, msg):
        name = msg.body[0] if msg.body else ""
        if name == KDECONNECT and self.opt("di_kdeconnect"):
            self._refresh_devices()

    def _refresh_devices(self):
        if self.bus is None or not self.opt("di_kdeconnect"):
            return

        def got(names):
            self.devices = dict(names or {})

        self.bus.call(KDECONNECT, "/modules/kdeconnect", "org.kde.kdeconnect.daemon", "deviceNames",
                      "bb", (True, True), got, lambda _e: setattr(self, "devices", {}))

    def send_to_device(self, device_id, url):
        name = self.devices.get(device_id, device_id)
        from .i18n import T

        def ok(*_a):
            self.app._notify(T("Sent to %s.") % name)

        def fail(e):
            self.app._notify(T("Could not send to %s: %s") % (name, e))

        self.bus.call(KDECONNECT, "/modules/kdeconnect/devices/%s/share" % device_id,
                      "org.kde.kdeconnect.device.share", "shareUrl", "s", (url,), ok, fail)

    def add_send_menu(self, menu, url):
        """'Send to device' submenu for a page or link (only with paired devices)."""
        from .i18n import T
        if not url or not self.devices or not self.opt("di_kdeconnect") or self.bus is None:
            return
        if QUrl(url).scheme() not in ("http", "https"):
            return
        from .icons import themed
        sub = menu.addMenu(themed("kdeconnect"), T("Send to device"))
        for dev_id, name in sorted(self.devices.items(), key=lambda kv: kv[1].lower()):
            a = sub.addAction(name)
            a.triggered.connect(lambda _c=False, d=dev_id: self.send_to_device(d, url))

    # --- downloads in the notifications ----------------------------------------
    def download_started(self, item):
        if not self.opt("di_downloads") or not self._ensure_bus():
            return
        import time
        key = id(item)
        self.jobs[key] = [item, "", 0.0, 0, time.monotonic()]
        from .i18n import T
        hints = self._job_state(item)
        hints["title"] = ("s", T("Downloading"))
        hints["immediate"] = ("b", True)

        def got(path):
            job = self.jobs.get(key)
            if job is None:          # finished before the view existed
                self.bus.call(JOBS, path, "org.kde.JobViewV3", "terminate", "usa{sv}", (0, "", {}))
                return
            job[1] = path
            self.download_progress(item, force=True)

        self.bus.call(JOBS, "/JobViewServer", "org.kde.JobViewServerV2", "requestView", "sia{sv}",
                      (APP_ID, 1, hints), got, lambda _e: self.jobs.pop(key, None))

    def _job_state(self, item):
        from .i18n import T
        done, total = int(item.receivedBytes()), int(item.totalBytes())
        path = self.app.download_path(item)
        # One file, its folder as the destination, as KIO's own copy jobs: Plasma then
        # offers "Open" (the file) and "Open Containing Folder" (the file shown in
        # the file manager). With no file count it took the job for several files
        # and tried to open the destination as a folder - which was the file.
        st = {"descriptionLabel1": ("s", T("Source")), "descriptionValue1": ("s", item.url().toString()),
              "descriptionLabel2": ("s", T("Destination")), "descriptionValue2": ("s", str(path)),
              "destUrl": ("s", QUrl.fromLocalFile(str(path.parent)).toString()),
              "infoMessage": ("s", path.name),
              "totalFiles": ("u", 1), "processedFiles": ("u", 1 if item.isFinished() else 0),
              "processedBytes": ("t", max(0, done))}
        if total > 0:
            st["totalBytes"] = ("t", total)
            st["percent"] = ("u", max(0, min(100, int(done * 100 / total))))
        return st

    def download_progress(self, item, force=False):
        import time
        job = self.jobs.get(id(item))
        if job is None or not job[1]:
            return
        now = time.monotonic()
        if not force and now - job[2] < 1.0:
            return
        st = self._job_state(item)
        done = int(item.receivedBytes())
        if job[2]:
            st["speed"] = ("t", max(0, int((done - job[3]) / max(0.001, now - job[2]))))
        job[2], job[3] = now, done
        self.bus.call(JOBS, job[1], "org.kde.JobViewV3", "update", "a{sv}", (st,))
        self._launcher()

    def download_done(self, item, ok, message=""):
        job = self.jobs.pop(id(item), None)
        if job is None or self.bus is None:
            return
        if job[1]:
            if ok:
                self.bus.call(JOBS, job[1], "org.kde.JobViewV3", "update", "a{sv}", (self._job_state(item),))
            # error codes as KJob: 0 none, 1 killed (cancelled by the user), 100+ user-defined error
            code = 0 if ok else (1 if not message else 100)
            self.bus.call(JOBS, job[1], "org.kde.JobViewV3", "terminate", "usa{sv}", (code, message, {}))
        self._launcher()

    def _launcher(self):
        """Progress and number of the downloads on I.K.E.'s icon in the task
        manager (the LauncherEntry signal Plasma's task manager follows)."""
        if self.bus is None or not self.bus.connected:
            return
        items = [j[0] for j in self.jobs.values()]
        got = sum(max(0, int(i.receivedBytes())) for i in items if int(i.totalBytes()) > 0)
        total = sum(int(i.totalBytes()) for i in items if int(i.totalBytes()) > 0)
        props = {"count": ("x", len(items)), "count-visible": ("b", bool(items)),
                 "progress": ("d", min(1.0, got / total) if total else 0.0),
                 "progress-visible": ("b", bool(items) and total > 0)}
        if props == getattr(self, "_launcher_last", None):
            return
        self._launcher_last = props
        self.bus.emit("/org/ike/launcher", LAUNCHER, "Update", "sa{sv}",
                      ("application://%s.desktop" % APP_ID, props))

    def _job_signal(self, msg):
        from jeepney import HeaderFields
        f = msg.header.fields
        path, member = f.get(HeaderFields.path), f.get(HeaderFields.member)
        for job in list(self.jobs.values()):
            if job[1] == path:
                item = job[0]
                if member == "cancelRequested":
                    item.cancel()
                elif member == "suspendRequested":
                    item.pause()
                elif member == "resumeRequested":
                    item.resume()
