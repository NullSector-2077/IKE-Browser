"""Application object and entry point."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkCookieJar, QNetworkProxyFactory
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (must load before QApplication)
from PyQt6.QtWidgets import QApplication, QFileDialog

from . import APP_ID, APP_LONG_NAME, APP_NAME, __version__, background
from .config import CACHE_DIR, CONFIG_DIR, PROFILE, RES_DIR, Config, ensure_dirs

# the application icon's pictures in resources/icons (ike-browser-N.png)
ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)

def find_widevine(home=None):
    """Path of the Widevine library I.K.E. may use, or None (see drm.py)."""
    from .drm import library_path
    return library_path()



class NoCookies(QNetworkCookieJar):
    """The browser's own requests (search suggestions, site icons, weather,
    downloads of extensions and languages, dark mode's style sheets) neither
    keep nor send cookies: a search engine cannot tie together the words typed
    in the address bar, nor a site recognise the browser by its icon requests.
    The pages' cookies live in the web profiles, not here."""

    def setCookiesFromUrl(self, cookies, url):
        return False

    def cookiesForUrl(self, url):
        return []

class IkeApp(QObject):
    def __init__(self, qapp, config):
        super().__init__(qapp)
        from .blocker import Blocker
        from .shields import Shields
        from .storage import Storage
        self.qapp = qapp
        self.config = config
        self.storage = Storage()
        self.blocker = Blocker(config, self)
        self.blocker.prepare()               # built meanwhile; start() waits for it before any page
        self.shields = Shields(config, self.blocker, self)
        from .fontcheck import Checker as FontCheck
        self.font_check = FontCheck(self.shields, self)   # fonts a page could find (Strict / Maximum)
        self.font_check.start()
        self.shields.open_requested.connect(self._open_from_newtab, Qt.ConnectionType.QueuedConnection)
        self.shields.engine_chosen.connect(self._engine_from_newtab, Qt.ConnectionType.QueuedConnection)
        from .userscripts import UserScripts
        self.userscripts = UserScripts(self)
        self.shields.user_scripts = self.userscripts
        from .passwords import PasswordManager
        from .updater import Updater
        self.passwords = PasswordManager(self)
        self.shields.pw_source = self.passwords.script_source()
        self.updater = Updater(config, self)
        self.updater.finished.connect(self._app_update_done)
        self._containers = {}
        from .favicons import Favicons
        self.favicons = Favicons(self)
        self._fav_timer = QTimer(self)
        self._fav_timer.setSingleShot(True)
        self._fav_timer.setInterval(800)
        self._fav_timer.timeout.connect(self.refresh_windows)
        self.favicons.changed.connect(self._fav_timer.start)
        from .extensions import StoreInstaller
        self.store = StoreInstaller(self)
        self.store.finished.connect(lambda ok, msg: self._desktop_notify(msg))
        self.network = QNetworkAccessManager(self)
        self.network.setCookieJar(NoCookies(self.network))
        from .weather import Weather
        self.weather = Weather(config, self.network, self)
        self.weather.changed.connect(self._weather_changed)
        # Built from our own files: a theme lookup can return an empty icon on
        # Plasma, which then also blanks the task-bar entry. The sizes up to 64
        # are drawn for their own pixel grid (tools/make-small-icons.py), so a
        # panel or title bar shows readable letters instead of a scaled-down logo.
        from PyQt6.QtCore import QSize
        self.icon = QIcon()
        for size in ICON_SIZES:
            f = RES_DIR / "icons" / ("ike-browser-%d.png" % size)
            if f.exists():
                self.icon.addFile(str(f), QSize(size, size))
        if self.icon.isNull():
            self.icon = QIcon(str(RES_DIR / "ike.svg"))
        qapp.setWindowIcon(self.icon)
        self.windows = []
        self.downloads = []
        self._dialogs = {}
        self._private = None
        self._quitting = False
        self._apply_dns()
        self.profile = self.shields.make_profile(parent=self)
        self._wire_profile(self.profile)
        self.blocker.updated.connect(self._lists_updated)
        self._timer = QTimer(self)
        self._timer.setInterval(3600 * 1000)
        self._timer.timeout.connect(self.check_updates)
        self._timer.start()
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(60 * 1000)
        self._save_timer.timeout.connect(self._periodic_save)
        self._save_timer.start()
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setInterval(60 * 1000)
        self._sleep_timer.timeout.connect(self.sleep_tabs)
        self._sleep_timer.start()
        # progress ring of the Downloads button (see downloadring)
        self._dl_state = ("idle", None)
        self._dl_done = False
        self._dl_timer = QTimer(self)
        self._dl_timer.setInterval(400)
        self._dl_timer.timeout.connect(self._download_tick)
        from .resources import Monitor
        self.resources = Monitor(self)       # per-site resources (idle unless used)
        from .watcher import Watcher
        self.watcher = Watcher(self)         # watched pages (idle unless there are some)
        from .plasma import DesktopIntegration
        self.desktop = DesktopIntegration(self)   # media keys, downloads, KRunner, KDE Connect
        self._guard_extensions()

    # --- profiles ----------------------------------------------------
    def _wire_profile(self, profile):
        from .webview import notify
        profile.downloadRequested.connect(self._download)
        try:
            profile.setNotificationPresenter(notify)
        except Exception:
            pass

    def private_profile(self):
        if self._private is None:
            self._private = self.shields.make_profile(private=True, parent=self)
            self._wire_profile(self._private)
        return self._private

    def container_profile(self, name):
        if not name:
            return self.profile
        slug = "".join(ch for ch in name.lower() if ch.isalnum()) or "c"
        if slug not in self._containers:
            p = self.shields.make_profile(parent=self, container=slug)
            self._wire_profile(p)
            self._containers[slug] = p
        return self._containers[slug]

    def container_color(self, name):
        if not name:
            return None
        for c in self.config["containers"]:
            if c["name"] == name:
                return c["color"]
        return "#7f8c8d"

    def all_profiles(self):
        return [self.profile] + list(self._containers.values())

    def extension_manager(self):
        try:
            return self.profile.extensionManager()
        except Exception:
            return None

    def _guard_extensions(self):
        """Re-enable the user's extensions, but never crash twice on one."""
        cfg = self.config
        if cfg["ext_pending"]:
            # the previous run died while enabling this extension
            bad = cfg["ext_pending"]
            cfg["ext_pending"] = ""
            cfg["enabled_extensions"] = [e for e in cfg["enabled_extensions"] if e != bad]
            cfg["experimental_extensions"] = False
            cfg.save()
            QTimer.singleShot(2500, lambda: self._notify(self._t(
                "An extension made the browser crash and was switched off, together with the "
                "experimental extension support.")))
            return
        if cfg["experimental_extensions"] and cfg["enabled_extensions"]:
            QTimer.singleShot(3000, self._enable_saved_extensions)

    def _enable_saved_extensions(self):
        mgr = self.extension_manager()
        if mgr is None:
            return
        for info in mgr.extensions():
            if info.id() in self.config["enabled_extensions"] and not info.isEnabled():
                self.enable_extension(mgr, info)

    def enable_extension(self, mgr, info, on=True):
        """Enable with a crash marker written first (the engine call is unstable)."""
        cfg = self.config
        cfg["ext_pending"] = info.id()
        cfg.save()
        mgr.setExtensionEnabled(info, on)
        cfg["ext_pending"] = ""
        ids = [e for e in cfg["enabled_extensions"] if e != info.id()]
        if on:
            ids.append(info.id())
        cfg["enabled_extensions"] = ids
        cfg.save()

    # --- windows -----------------------------------------------------
    def new_window(self, private=False, urls=None, open_default=True, popup=False):
        from .window import NEWTAB, BrowserWindow
        # the first page is asked for while the window is built (1.1.23)
        first = urls[0] if urls else (NEWTAB if open_default else None)
        win = BrowserWindow(self, private=private, popup=popup, first=first)
        self.windows.append(win)
        if self._dl_state[0] != "idle":
            win.show_download_progress(*self._dl_state)
        if urls:
            for u in urls:
                win.add_tab(u)
            win.set_current(win.views[0])
        elif open_default:
            win.add_tab(NEWTAB)
        if popup:
            win.resize(900, 640)
            win.show()
        elif self.config["start_maximized"]:
            win.showMaximized()
        else:
            win.show()
        return win

    def active_window(self):
        w = self.qapp.activeWindow()
        if w in self.windows:
            return w
        return self.windows[-1] if self.windows else None

    def refresh_windows(self):
        for w in self.windows:
            w.apply_layout()
            w.sync_urlbar()
            w.refresh_lookalike()

    def _open_from_newtab(self, what):
        """The Settings button of the new tab page, or its background photo button."""
        win = self.active_window()
        if win is not None:
            win.open_settings("newtab" if what == "background" else None)

    # --- the search engines' own icons (address bar and new tab page, 1.1.10) ---
    def engine_icon(self, engine):
        """The engine's own site icon, a magnifier until it is known."""
        ic = self.favicons.icon(engine.get("url", ""))
        if ic.isNull():
            from PyQt6.QtWidgets import QStyle

            from .icons import themed
            return themed("edit-find", QStyle.StandardPixmap.SP_FileDialogContentsView)
        return ic

    def fetch_engine_icons(self, name=None):
        """Ask an engine's site for its icon, once: the engine in use (or the
        one named), never every engine at once. At the first start each
        engine, Google and Bing included, was asked within seconds; an engine
        not used is never contacted (review of 1.1.19, L3)."""
        name = name or self.config["default_engine"]
        for e in self.config["search_engines"]:
            if e.get("name") == name:
                self.favicons.fetch(e.get("url", ""))

    def set_engine(self, name):
        """An engine chosen in the address bar: the default from now on."""
        if name == self.config["default_engine"] or not any(
                e["name"] == name for e in self.config["search_engines"]):
            return
        self.config["default_engine"] = name
        self.config.save()
        self.fetch_engine_icons()
        for w in self.windows:
            w.sync_engine()
        self.reload_newtabs()

    def _engine_from_newtab(self, _name):
        """The engine was chosen on a new tab page: the address bars and the other new tab
        pages show it (the page it was chosen on is being shown again already)."""
        self.fetch_engine_icons()
        for w in self.windows:
            w.sync_engine()
            for v in w.all_views():
                if v.url().scheme() == "ike" and not v.sleeping and not getattr(v, "loading", False):
                    v.reload()

    def reload_newtabs(self):
        """The look of the new tab page changed: show it in the ones that are open."""
        for w in self.windows:
            for v in w.all_views():
                if v.url().scheme() == "ike" and not v.sleeping:
                    v.reload()

    def refresh_toolbars(self):
        """The toolbar's buttons changed: show the new arrangement in every window."""
        for w in self.windows:
            w._apply_toolbar()

    def start(self, urls=None, private=False):
        from .mailto import is_mailto
        from .window import NEWTAB
        self.blocker.load()
        cfg = self.config
        mails = [u for u in urls or () if is_mailto(u)]
        urls = [u for u in urls or () if not is_mailto(u)]
        if mails:
            QTimer.singleShot(300, lambda: self._write_emails(mails))
        if private:
            self.new_window(private=True, urls=urls)
        else:
            startup = cfg["startup"]
            once = bool(cfg["restore_once"])
            if once:
                cfg["restore_once"] = False
                cfg.save()
            session = cfg["session"] if startup == "restore" or once else []
            opened = False
            for entry in session:
                win = self.new_window(open_default=False)
                if win.restore_session(entry):
                    opened = True
                else:
                    self.windows.remove(win)
                    win.deleteLater()
            if urls:
                if opened:
                    for u in urls:
                        self.windows[-1].add_tab(u)
                else:
                    self.new_window(urls=urls)
            elif not opened:
                home = cfg["homepage"] if startup == "home" else NEWTAB
                self.new_window(urls=[home or NEWTAB])
        QTimer.singleShot(1500, self.check_updates)
        QTimer.singleShot(4000, self.fetch_engine_icons)   # the engine's own icon, once (1.1.10)
        QTimer.singleShot(20000, self._healthy)
        if cfg["video_hw"] == "on":
            QTimer.singleShot(VIDEO_TRIAL_OK_MS, lambda: _video_trial_done(CONFIG_DIR))

    def _healthy(self):
        from . import updater
        updater.confirm_healthy()
        if self.config["video_hw_fell_back"]:
            self.config["video_hw_fell_back"] = False
            self.config.save()
            self._desktop_notify(self._t("Video decoding with the graphics card is back on Automatic: "
                                         "I.K.E. did not close normally while it was on."))
        self._engine_security_notice()
        notice = updater.take_rollback_notice()
        if notice:
            self._desktop_notify(self._t("I.K.E. update %s did not start correctly and was "
                                         "removed. The previous version is in use.") % notice[0])

    def _write_emails(self, mails):
        """Email links that came from another program (I.K.E. is the system's
        handler for them): the chosen web mail writes them."""
        from . import mailto
        for m in mails:
            mailto.open_link(self, QUrl(m), self.active_window(), from_desktop=True)

    def open_urls(self, urls, private=False):
        """Called when a second instance forwards its arguments."""
        from .mailto import is_mailto
        mails = [u for u in urls if is_mailto(u)]
        urls = [u for u in urls if not is_mailto(u)]
        if mails and not urls and self.active_window() is not None:
            win = self.active_window()
            win.raise_()
            win.activateWindow()
            self._write_emails(mails)
            return
        if mails:
            QTimer.singleShot(0, lambda: self._write_emails(mails))
        win = None if private else self.active_window()
        if win is None or win.private != private:
            win = self.new_window(private=private, urls=urls or None)
        else:
            for u in urls:
                win.add_tab(u)
            if not urls:
                win = self.new_window()
        win.raise_()
        win.activateWindow()

    def _session(self):
        out = []
        for w in self.windows:
            if w.private or w.popup:
                continue
            data = w.session_data()
            if any(ws["tabs"] for ws in data["workspaces"]):
                out.append(data)
        return out

    def sleep_tabs(self, force=False):
        minutes = self.config["tab_sleep_minutes"]
        if not force and not minutes:
            return
        n = sum(w.sleep_inactive(minutes, force) for w in self.windows)
        if force:
            self._notify(self._t("%d tabs suspended.") % n)
        elif memory_low():
            self.relieve_memory()

    # When the computer runs short of memory, the tabs left alone longest are
    # suspended before their usual time (1.1.18). Each suspended tab gives back
    # about 50 MB (measured with 10, 20 and 30 tabs); a tab comes back as it
    # was when it is shown again. Only when suspending is on at all, and only
    # tabs not looked at for some minutes, a few at each check (every minute).
    PRESSURE_IDLE_S = 5 * 60
    PRESSURE_TABS = 3

    def relieve_memory(self):
        now = time.time()
        idle = sorted(((v.last_active, w, v) for w in self.windows for v in w.all_views()
                       if not v.sleeping and now - v.last_active >= self.PRESSURE_IDLE_S),
                      key=lambda t: t[0])
        n = 0
        for _t, w, v in idle:
            if n >= self.PRESSURE_TABS:
                break
            n += bool(w.sleep_view(v))
        return n

    def launch_profile(self, name):
        from .updater import boot_command
        if name == PROFILE:
            return
        from .fontallow import child_env
        env = child_env(os.environ)          # the other profile chooses its own fonts
        env.pop("IKE_TEST_HOOK", None)
        env["IKE_PROFILE"] = name
        subprocess.Popen(boot_command() + ["--profile", name], env=env,
                         start_new_session=True)

    def _periodic_save(self):
        session = self._session()
        if session:
            self.config["session"] = session
        self.config.save()

    def window_closing(self, win):
        normal = [w for w in self.windows if not w.private and not w.popup]
        if not self._quitting and win in normal and len(normal) == 1:
            self.config["session"] = self._session()
        if win in self.windows:
            self.windows.remove(win)
        if not getattr(self, "_restored", False):
            self.config.save()
        if not self.windows:
            self._shutdown()

    # --- dark mode for pages -------------------------------------------
    def set_dark_mode(self, mode, parent=None, engine=None):
        """Turn dark mode for pages on or off and apply it without restarting."""
        cfg = self.config
        cfg["dark_mode"] = "on" if mode == "on" else "off"
        if engine in ("reader", "engine"):
            cfg["dark_engine"] = engine
        cfg.save()
        self._dark_changed()

    def set_site_dark(self, host, on):
        """Make one site dark or light, whatever the global setting and renderer."""
        cfg = self.config
        host = (host or "").lower().strip(".")
        if not host:
            return
        general = cfg["dark_mode"] == "on"
        for key in ("dark_sites", "dark_exclude"):
            cfg[key] = [h for h in cfg[key] if h != host]
        if on != general:
            key = "dark_exclude" if general else "dark_sites"
            cfg[key] = cfg[key] + [host]
        cfg.save()
        self._dark_changed()

    def _dark_changed(self):
        """Reload affected open pages after a dark renderer or site rule changes."""
        self.refresh_windows()
        engine = self.config["dark_engine"]
        for w in self.windows:
            for v in w.views:
                if v.url().scheme() in ("http", "https", "file") and not getattr(v, "sleeping", False) \
                        and not getattr(v, "pending_url", None):
                    page = v.page()
                    want = self.shields.dark_for(v.url().host().lower())
                    if (want != getattr(page, "_dark_on", False)
                            or (want and engine != getattr(page, "_dark_engine", None))):
                        v.reload()

    def restart(self):
        """Close and start again, reopening the current tabs."""
        self.config["restore_once"] = True
        self._restart = True
        self.quit()

    def quit(self):
        self._quitting = True
        self.config["session"] = self._session()
        self.config.save()
        for w in list(self.windows):
            w.close()

    def _shutdown(self):
        from . import updater
        self.desktop.shutdown()
        for db in (getattr(self, "storage", None), getattr(self, "favicons", None)):
            if db is not None:
                db.flush()                 # the visits and icons of the last seconds
        updater.confirm_healthy()          # a clean exit also proves the version works
        if getattr(self, "_restored", False):
            self.config.save = lambda: None
            return
        if self.config["clear_on_exit"] and not getattr(self, "_restart", False):
            self.clear_data(True, True, True, False)
            self.config["session"] = []
        self.config.save()
        for d in list(self._dialogs.values()):
            d.close()

    def _engine_security_notice(self):
        """Once per session: the system's web engine (qt6-webengine) has gone
        months without security fixes. I.K.E. cannot update it itself; the
        system's update does (1.1.17)."""
        from . import chromever
        behind = chromever.security_behind(self.config)
        if behind >= chromever.OUTDATED_AFTER and not getattr(self, "_engine_warned", False):
            self._engine_warned = True
            self._desktop_notify(self._t(
                "The system's web engine (qt6-webengine) is %d Chrome versions behind with its "
                "security fixes. Update the system (sudo pacman -Syu) to stay protected.") % behind)
        return behind

    def _check_chrome_version(self):
        """Once a day: learn the current stable Chrome version (see chromever)."""
        from . import chromever
        if getattr(self, "_chrome_check", None) is not None or not chromever.due(self.config):
            return

        def done(major):
            # only shown in Help -> About (the engine's age); sites see the
            # engine's own version (1.1.14)
            self._chrome_check = None
            self.config["chrome_checked"] = int(time.time())
            if chromever.plausible(major):
                self.config["chrome_major"] = major
            self.config.save()
        self._chrome_check = chromever.Checker(self)
        self._chrome_check.done.connect(done)
        background.start(self._chrome_check)

    def _apply_dns(self):
        """Encrypted DNS as chosen; said when the engine refused it, instead of
        browsing on in clear without a word (review of 1.1.19, M3)."""
        from . import doh
        from .i18n import T
        doh.ON_PROBLEM[0] = lambda why: self._notify(T(
            "Encrypted DNS does not answer I.K.E.'s own requests (updates, filter lists): %s") % why)
        if not self.shields.apply_dns() and self.config["doh"] not in ("", "off", None):
            QTimer.singleShot(3000, lambda: self._notify(T(
                "Encrypted DNS could not be turned on: names are looked up by the system.")))

    # --- settings / updates ------------------------------------------
    def settings_changed(self):
        self.desktop.settings_changed()
        self.shields.apply_settings()
        self._apply_dns()
        self.blocker.load()
        self.refresh_windows()
        if self.blocker.needs_update():
            self.blocker.update()

    def check_updates(self):
        self._check_chrome_version()
        if self.config["auto_update"]:
            self.userscripts.check_updates()
        if self.blocker.needs_update():
            self.blocker.update()
        elif self.blocker.needs_fast_update():
            self.blocker.update(fast=True)
        cfg = self.config
        if (cfg["app_updates"] != "off" and self.updater.configured()
                and time.time() - cfg["last_app_check"] > 24 * 3600):
            self.updater.run(install=cfg["app_updates"] == "auto")

    def check_app_update(self, manual=False):
        from .i18n import T
        self._manual_app = manual
        if not self.updater.configured():
            if manual:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self.active_window(), "I.K.E.", T(
                    "No update channel is configured for this copy of I.K.E. (file update.json). "
                    "Filter lists still update every day; the web engine is updated by the "
                    "system package manager."))
            return
        if self.updater.run(install=self.config["app_updates"] == "auto", manual=manual) and manual:
            self._notify(T("Checking for updates…"))

    def _app_update_done(self, kind, data):
        from PyQt6.QtWidgets import QMessageBox

        from .i18n import T
        manual = getattr(self, "_manual_app", False)
        self._manual_app = False
        win = self.active_window()
        if kind == "error":
            self._desktop_notify(T("I.K.E. update check failed: %s") % data)
            if manual:
                QMessageBox.warning(win, "I.K.E.", T("I.K.E. update check failed: %s") % data)
        elif kind == "current":
            if manual:
                QMessageBox.information(win, "I.K.E.", T("I.K.E. is up to date (version %s).")
                                        % data["version"])
        elif kind == "system":
            from . import updater
            text = T("I.K.E. %s is available, but it needs a newer installation package. "
                     "Update I.K.E. with your package manager or download the new package "
                     "from the I.K.E. releases page.") % data["version"]
            state = updater.load_state()
            if state.get("system_notice") != data["version"]:     # tell once per version
                state["system_notice"] = data["version"]
                updater.save_state(state)
                self._desktop_notify(text)
            if manual:
                QMessageBox.information(win, "I.K.E.", text)
        elif kind == "installed":
            self._desktop_notify(T("I.K.E. %s was installed and will be used at the next start. "
                                   "The previous version is kept as a backup.") % data["version"])
            if manual:
                QMessageBox.information(win, "I.K.E.", T(
                    "I.K.E. %s was installed and will be used at the next start. "
                    "The previous version is kept as a backup.") % data["version"])
        elif kind == "available":
            box = QMessageBox(win)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(T("I.K.E. update"))
            box.setText(T("Version %s of I.K.E. is available. Updates are verified with a "
                          "digital signature before they are installed.") % data["version"])
            always = box.addButton(T("Install, and always update automatically"),
                                   QMessageBox.ButtonRole.AcceptRole)
            once = box.addButton(T("Install this time"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(T("Not now"), QMessageBox.ButtonRole.RejectRole)
            never = box.addButton(T("Never check"), QMessageBox.ButtonRole.DestructiveRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is always:
                self.config["app_updates"] = "auto"
            elif clicked is never:
                self.config["app_updates"] = "off"
            self.config.save()
            if clicked in (always, once):
                self._manual_app = True
                self.updater.run(install=True, manual=True)

    def _desktop_notify(self, text):
        self._notify(text)
        from .osinfo import notify
        notify("I.K.E.", text)

    def update_now(self):
        self._manual_update = True
        self.blocker.update()
        self._notify(self._t("Updating filter lists…"))

    def _lists_updated(self, ok, failed):
        from .i18n import T
        if getattr(self, "_manual_update", False) or failed:
            self._manual_update = False
            if failed and not ok:
                self._notify(T("Could not download the filter lists. Check the connection."))
            else:
                self._notify(T("Filter lists updated (%d lists).") % ok)

    @staticmethod
    def _t(text):
        from .i18n import T
        return T(text)

    def _notify(self, text):
        win = self.active_window()
        if win:
            win.toast(text, 5000)

    # --- downloads ---------------------------------------------------
    def download_dir(self):
        d = self.config["download_dir"] or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        return Path(d)

    def _download(self, item):
        """Start a download. With "ask where to save" the transfer starts at once
        into a temporary folder while a normal (non-blocking) file dialog is open;
        the file is moved to the chosen place when both are done. Waiting for the
        dialog inside this handler made downloads fail on some desktops."""
        from .i18n import T
        if self._handoff_download(item):
            return                        # a copy for a desktop app (hand_off), not the user's download
        passed = self._download_passed(item)
        if not passed and self._download_burst(item):
            return
        if not passed and self._download_risk(item):
            return
        folder = self.download_dir()
        name = item.downloadFileName()
        item._ike_tmp = item._ike_target = item._ike_final = None
        ask = self.config["ask_download_location"] and not os.environ.get("IKE_TEST_NOASK")
        if ask:
            import tempfile
            tmp_root = CACHE_DIR / "downloads-tmp"
            tmp_root.mkdir(parents=True, exist_ok=True)
            item._ike_tmp = Path(tempfile.mkdtemp(dir=str(tmp_root)))
            item.setDownloadDirectory(str(item._ike_tmp))
        else:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                folder = Path.home()
            item.setDownloadDirectory(str(folder))
        item.setDownloadFileName(name)
        item.accept()
        self.downloads.insert(0, item)
        item.isFinishedChanged.connect(lambda i=item: self._download_finished(i))
        item.isFinishedChanged.connect(self._download_tick)
        item.receivedBytesChanged.connect(lambda i=item: self.desktop.download_progress(i))
        self.desktop.download_started(item)
        self._dl_done = False
        self._download_tick()
        if ask:
            dlg = QFileDialog(self.active_window(), T("Save file"), str(folder))
            dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dlg.setFileMode(QFileDialog.FileMode.AnyFile)
            dlg.selectFile(name)
            dlg.fileSelected.connect(lambda p, i=item: self._download_target(i, p))
            dlg.rejected.connect(lambda i=item: self._download_rejected(i))
            item._ike_dialog = dlg
            dlg.open()
        else:
            self._notify(T("Download started: %s") % name)

    # a site that starts one download after another (without the user saving
    # each file) is asked about first, as in other browsers
    BURST_SECONDS = 10
    USER_SECONDS = 3                      # a download this soon after the user's input is theirs

    def _download_burst(self, item):
        """True when this download is held back: another one from the same site
        started less than BURST_SECONDS ago. The user is asked once; "Allow"
        lets the site download freely until I.K.E. closes and starts this file
        again, "Block" drops its bursts for this session. A single download,
        one a while after the last, or one right after the user clicked or
        typed on the page (or I.K.E. itself started it) never asks."""
        import time

        from .shields import site_of
        try:
            if item.isSavePageDownload():
                return False
            page = item.page()
        except (AttributeError, RuntimeError):
            page = None
        now = time.monotonic()
        user = getattr(page, "_ike_input", -99.0) if page is not None else -99.0
        if (now - user < self.USER_SECONDS
                and getattr(page, "_ike_input_used", None) != user):
            # right after a click, a key or an address of the user: that one
            # action is worth one download (1.1.17: until then every download
            # of the next 3 seconds went through, 31 in a test)
            page._ike_input_used = user
            host = page.url().host() or item.url().host()
            self.__dict__.setdefault("_dl_burst", {"times": {}, "allowed": set(), "blocked": set(),
                                                   "held": {}})["times"].setdefault(
                site_of(host.lower()), []).append(now)
            return False
        host = (page.url().host() if page is not None else "") or item.url().host()
        site = site_of(host.lower())
        if not site:
            return False
        burst = self.__dict__.setdefault("_dl_burst", {"times": {}, "allowed": set(),
                                                       "blocked": set(), "held": {}})
        times = [t for t in burst["times"].get(site, []) if now - t < self.BURST_SECONDS]
        held = bool(times) and site not in burst["allowed"]
        times.append(now)
        burst["times"][site] = times
        if not held:
            return False
        item.cancel()
        if site in burst["blocked"]:
            return True
        waiting = burst["held"].get(site)
        if waiting is not None:           # already asking: this file waits for the answer too
            if len(waiting) < 20:
                waiting.append(item.url())
            return True
        burst["held"][site] = [item.url()]

        def answered(allow):
            urls = burst["held"].pop(site, [])
            if not allow:
                burst["blocked"].add(site)
                return
            burst["allowed"].add(site)
            for url in urls:
                try:
                    if page is not None:
                        page.download(url)
                except RuntimeError:
                    break                 # the page is gone
        self._ask_download_burst(site, answered)
        return True

    def _ask_download_burst(self, site, done):
        """Non-blocking question (a dialog inside the download handler made
        downloads fail on some desktops)."""
        from PyQt6.QtWidgets import QMessageBox

        from .i18n import T
        box = QMessageBox(self.active_window())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(T("Downloads"))
        box.setText(T("%s wants to download several files.") % site)
        allow = box.addButton(T("Allow"), QMessageBox.ButtonRole.AcceptRole)
        block = box.addButton(T("Block"), QMessageBox.ButtonRole.RejectRole)
        from .webview import careful
        careful(box, allow, block)
        box.finished.connect(lambda _r: done(box.clickedButton() is allow))
        box.finished.connect(box.deleteLater)
        box.open()

    # --- safer downloads (1.1.24, safedownload.py) -----------------------
    PASS_SECONDS = 60                     # "Download anyway" lets that one address through once

    def _download_passed(self, item):
        """True once for a download the user let through ("Download anyway")."""
        passes = self.__dict__.setdefault("_dl_pass", {})
        key = item.url().toString()
        when = passes.pop(key, None)
        return when is not None and time.monotonic() - when < self.PASS_SECONDS

    def _download_risk(self, item):
        """True when this download is stopped for the user's answer: a program
        or script from a listed or never visited site, or a file over http from
        an https page. "Download anyway" starts it again, at the user's risk."""
        from . import safedownload
        try:
            if item.isSavePageDownload():
                return False
            page = item.page()
        except (AttributeError, RuntimeError):
            page = None
        try:
            page_url = page.url().toString() if page is not None else ""
        except RuntimeError:
            page, page_url = None, ""
        found = safedownload.risk(item.url().toString(), page_url, item.downloadFileName(), item.mimeType(),
                                  self.blocker, self.storage.visited_before)
        if not found:
            return False
        url, name = QUrl(item.url()), item.downloadFileName()
        item.cancel()

        def anyway():
            target = page
            if target is None:
                win = self.active_window()
                view = win.current_view() if win is not None else None
                target = view.page() if view is not None else None
            if target is None:
                return
            self.__dict__.setdefault("_dl_pass", {})[url.toString()] = time.monotonic()
            try:
                target.download(url, name)
            except RuntimeError:
                pass                      # the page is gone
        self._ask_download_risk(found, anyway)
        return True

    def _ask_download_risk(self, found, anyway):
        """Non-blocking question, "Cancel" the default (as _ask_download_burst)."""
        from PyQt6.QtWidgets import QMessageBox

        from . import safedownload
        from .i18n import T
        box = QMessageBox(self.active_window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(T("Downloads"))
        box.setText(safedownload.message(found))
        box.setInformativeText(T("If you download it anyway, it is at your own risk."))
        go = box.addButton(T("Download anyway"), QMessageBox.ButtonRole.AcceptRole)
        stop = box.addButton(T("Cancel"), QMessageBox.ButtonRole.RejectRole)
        from .webview import careful
        careful(box, go, stop)
        box.finished.connect(lambda _r: box.clickedButton() is go and anyway())
        box.finished.connect(box.deleteLater)
        self._risk_box = box
        box.open()

    # --- copies handed to a desktop app (1.1.24, handoff.py) -------------
    HANDOFF_SECONDS = 60

    @property
    def handoff(self):
        """Files, folders and links to the desktop's apps (handoff.py), made when first needed."""
        h = self.__dict__.get("_handoff")
        if h is None:
            from .handoff import Handoff
            h = self._handoff = Handoff(self)
        return h

    def hand_off(self, url, kind, page, name=""):
        """Give what `url` holds (kind "image", "pdf" or "calendar") to the
        desktop's app for it: a local file at once, else a copy fetched by the
        engine (the page's own cookies and cache) into a private folder. The
        copy is opened only when its content is of that kind."""
        from . import handoff
        url = QUrl(url)
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            if path.is_file() and handoff.kind_of(handoff.file_type(path, "content")) == kind:
                self.handoff.open_file(path, self.active_window())
            return
        if url.scheme() not in ("http", "https") or page is None:
            return
        self.__dict__.setdefault("_handoff_wait", {})[url.toString()] = (time.monotonic(), kind)
        page.download(url, handoff.safe_name(name or url.fileName(), kind))

    def _handoff_download(self, item):
        wait = self.__dict__.get("_handoff_wait")
        want = wait.pop(item.url().toString(), None) if wait else None
        if want is None or time.monotonic() - want[0] > self.HANDOFF_SECONDS:
            return False
        from . import handoff
        folder = handoff.temp_dir()
        self._handoff_n = getattr(self, "_handoff_n", 0) + 1
        name = "%d-%d-%s" % (int(time.time()), self._handoff_n, handoff.safe_name(item.downloadFileName(), want[1]))
        item.setDownloadDirectory(str(folder))
        item.setDownloadFileName(name)
        item.isFinishedChanged.connect(lambda i=item, k=want[1]: self._handoff_finished(i, k))
        item.accept()
        return True

    def _handoff_finished(self, item, kind):
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as DR

        from . import handoff
        if not item.isFinished():
            return
        path = Path(item.downloadDirectory()) / item.downloadFileName()
        if item.state() != DR.DownloadState.DownloadCompleted or not path.is_file():
            path.unlink(missing_ok=True)
            return
        mime = handoff.file_type(path, "content")
        if handoff.kind_of(mime) != kind:
            path.unlink(missing_ok=True)       # not what the menu offered: never handed over
            return
        suffix = mime.preferredSuffix()
        if suffix and not path.name.lower().endswith("." + suffix.lower()):
            try:
                path = path.rename(path.with_name(path.name + "." + suffix))
            except OSError:
                return
        self.handoff.open_file(path, self.active_window())

    def download_path(self, item):
        """Where the file of a download is (or will be)."""
        final = getattr(item, "_ike_final", None) or getattr(item, "_ike_target", None)
        return Path(final) if final else Path(item.downloadDirectory()) / item.downloadFileName()

    def _download_target(self, item, path):
        from .i18n import T
        item._ike_target = Path(path)
        item._ike_dialog = None
        if item.isFinished():
            self._download_finished(item)
        else:
            self._notify(T("Download started: %s") % item._ike_target.name)

    def _download_rejected(self, item):
        if getattr(item, "_ike_target", None) is None and getattr(item, "_ike_tmp", None):
            item._ike_dialog = None
            item.cancel()
            shutil.rmtree(item._ike_tmp, ignore_errors=True)
            item._ike_tmp = None

    def _download_finished(self, item):
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as DR

        from .i18n import T
        if not item.isFinished():
            return
        tmp = getattr(item, "_ike_tmp", None)
        if item.state() != DR.DownloadState.DownloadCompleted:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
            failed = item.state() == DR.DownloadState.DownloadInterrupted
            if failed:
                self._notify(T("Download failed: %s") % item.interruptReasonString())
            self.desktop.download_done(item, False, item.interruptReasonString() if failed else "")
            return
        if tmp:
            if item._ike_target is None:
                return                      # still waiting for the user to pick a place
            try:
                item._ike_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp / item.downloadFileName()), str(item._ike_target))
                item._ike_final = item._ike_target
            except OSError as exc:
                self._notify(T("Download failed: %s") % exc)
                self.desktop.download_done(item, False, str(exc))
                return
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
                item._ike_tmp = None
        self._notify(T("Download finished: %s") % self.download_path(item).name)
        self.desktop.download_done(item, True)

    def _weather_changed(self):
        """New weather: write it into the new tab pages that are open."""
        for w in self.windows:
            for v in w.all_views():
                self.push_weather(v)

    def push_weather(self, view):
        """Put the current weather into a new tab page (also one that finished
        loading after the weather arrived)."""
        url = view.url()
        if url.scheme() == "ike" and url.path() in ("", "newtab") and self.config["newtab_weather"]:
            text = json.dumps(self.shields.weather_text())
            view.page().runJavaScript("window.ikeWeather && ikeWeather(%s)" % text)

    def _download_tick(self):
        """Update the progress ring of the Downloads buttons."""
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as DR
        active = []
        for item in self.downloads:
            try:
                st = item.state()
            except RuntimeError:                # deleted by the engine
                continue
            if st == DR.DownloadState.DownloadInProgress:
                active.append(item)
            elif st == DR.DownloadState.DownloadCompleted and not getattr(item, "_ike_ring_seen", False):
                item._ike_ring_seen = True
                self._dl_done = True
        if active:
            total = sum(i.totalBytes() for i in active)
            known = all(i.totalBytes() > 0 for i in active)
            fraction = sum(i.receivedBytes() for i in active) / total if known and total else None
            state = ("active", fraction)
            if not self._dl_timer.isActive():
                self._dl_timer.start()
        else:
            self._dl_timer.stop()
            state = ("done", None) if self._dl_done else ("idle", None)
        if state != self._dl_state or state[0] == "active":
            self._dl_state = state
            for w in self.windows:
                w.show_download_progress(*state)

    # --- dialogs -----------------------------------------------------
    def _show(self, key, factory):
        dlg = self._dialogs.get(key)
        if dlg is not None:
            try:
                dlg.close()
                dlg.deleteLater()
            except RuntimeError:
                pass
        dlg = factory()
        dlg.setWindowIcon(self.icon)
        self._dialogs[key] = dlg
        # the size it asks for, never larger than the screen (1.1.21)
        from . import uistyle
        resized = dlg.testAttribute(Qt.WidgetAttribute.WA_Resized)
        uistyle.fit_window(dlg, dlg.width() if resized else 0, dlg.height() if resized else 0)
        dlg.show()
        dlg.raise_()
        return dlg

    def show_settings(self, parent=None, page=None):
        from .dialogs import SettingsDialog
        return self._show("settings", lambda: SettingsDialog(self, parent or self.active_window(), page))

    def show_userscripts(self):
        """The installed user scripts (Settings → I.K.E. extensions → User scripts → Options…)."""
        from .dialogs import UserScriptsDialog
        parent = self._dialogs.get("settings")
        try:
            parent = parent if parent is not None and parent.isVisible() else self.active_window()
        except RuntimeError:
            parent = self.active_window()
        return self._show("userscripts", lambda: UserScriptsDialog(self, parent))

    def show_history(self):
        from .dialogs import HistoryDialog
        return self._show("history", lambda: HistoryDialog(self, self.active_window()))

    def show_bookmarks(self):
        from .dialogs import BookmarksDialog
        return self._show("bookmarks", lambda: BookmarksDialog(self, self.active_window()))

    def show_downloads(self):
        from .dialogs import DownloadsDialog
        if self._dl_done:                       # seen: the ring is no longer green
            self._dl_done = False
            self._download_tick()
        return self._show("downloads", lambda: DownloadsDialog(self, self.active_window()))

    def show_passwords(self):
        from .passwords import PasswordsDialog
        if not self.passwords.ensure_unlocked(self.active_window()):
            return None
        return self._show("passwords", lambda: PasswordsDialog(self, self.active_window()))

    def show_import(self):
        from .importer import ImportDialog
        return self._show("import", lambda: ImportDialog(self, self.active_window()))

    def show_resources(self):
        from .resources import ResourcesDialog
        return self._show("resources", lambda: ResourcesDialog(self, self.active_window()))

    def show_watches(self):
        from .watcher import WatchesDialog
        return self._show("watches", lambda: WatchesDialog(self, self.active_window()))

    def show_permissions(self):
        from .importer import PermissionsDialog
        return self._show("permissions", lambda: PermissionsDialog(self, self.active_window()))

    def backup(self):
        from .i18n import T
        from .importer import make_backup
        name = "ike-backup-%s.zip" % time.strftime("%Y%m%d")
        path, _f = QFileDialog.getSaveFileName(self.active_window(), T("Back up I.K.E. data"),
                                               str(Path.home() / name), "ZIP (*.zip)")
        if path:
            self.config["session"] = self._session()
            self.config.save()
            make_backup(path, self.storage)
            self._notify(T("Backup saved: %s") % path)

    def restore_backup(self):
        from PyQt6.QtWidgets import QMessageBox

        from .i18n import T
        from .importer import restore_backup
        win = self.active_window()
        path, _f = QFileDialog.getOpenFileName(win, T("Restore a backup"), str(Path.home()),
                                               "ZIP (*.zip)")
        if not path:
            return
        if QMessageBox.question(win, "I.K.E.", T(
                "Settings, bookmarks, history and saved passwords will be replaced by the "
                "backup, and I.K.E. will close. Continue?")) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.storage.db.close()
            restore_backup(path)
        except Exception as exc:
            QMessageBox.warning(win, "I.K.E.", T("Restore failed: %s") % exc)
            return
        self._restored = True
        for w in list(self.windows):
            w.close()

    def show_clear_data(self):
        from .dialogs import ClearDataDialog
        return self._show("clear", lambda: ClearDataDialog(self, self.active_window()))

    def clear_data(self, history, cookies, cache, permissions):
        if history:
            self.storage.clear_history()
            self.profile.clearAllVisitedLinks()
        if cookies:
            for p in self.all_profiles():
                p.cookieStore().deleteAllCookies()
            # local storage, databases, service workers: at the next start (see sitedata.py)
            from . import sitedata
            sitedata.ask()
        if cache:
            for p in self.all_profiles():
                p.clearHttpCache()
        if permissions:
            try:
                for prof in self.all_profiles():
                    for p in prof.listAllPermissions():
                        p.reset()
            except Exception:
                pass


def _strip_dark_flags(flags):
    """Remove forced-dark-mode switches inherited from the environment.

    A system-wide QTWEBENGINE_CHROMIUM_FLAGS (often set for another Qt browser)
    would darken every page here too and override I.K.E.'s own dark mode
    setting and its per-site exclusions. Returns (flags, dark_was_forced).
    """
    out, forced = [], False
    for flag in flags:
        if flag == "--force-dark-mode":
            forced = True
            continue
        if flag.startswith("--blink-settings="):
            kept = []
            for item in flag.split("=", 1)[1].split(","):
                key = item.split("=", 1)[0].strip()
                if key.startswith("forceDarkMode") or key == "preferredColorScheme":
                    if key == "forceDarkModeEnabled" and item.lower().endswith("true"):
                        forced = True
                    continue
                if item:
                    kept.append(item)
            if not kept:
                continue
            flag = "--blink-settings=" + ",".join(kept)
        out.append(flag)
    return out, forced


# Video decoding with the graphics card (1.1.16). Qt WebEngine already uses it
# by itself where it can (Intel, AMD, with the VA-API driver installed); where
# it cannot share the frames (NVIDIA's own driver, no GBM) it switches it off,
# and "on" asks for it anyway: experimental, hence the safety net below.
VIDEO_ON = ("AcceleratedVideoDecodeLinux", "AcceleratedVideoDecodeLinuxGL",
            "VaapiIgnoreDriverChecks", "VaapiOnNvidiaGPUs")
VIDEO_TRIAL = "video-gpu-trial"         # in the profile's folder while "on" runs (removed at a good exit)
VIDEO_TRIAL_OK_MS = 30 * 60 * 1000      # ... or after half an hour without trouble


def _feature_flags(flags, enable=(), disable=()):
    """The flags with features added to the one --enable-features and the one
    --disable-features switch (the engine reads only one of each)."""
    out, on, off = [], [], []
    for f in flags:
        if f.startswith("--enable-features="):
            on += [x for x in f.split("=", 1)[1].split(",") if x]
        elif f.startswith("--disable-features="):
            off += [x for x in f.split("=", 1)[1].split(",") if x]
        else:
            out.append(f)
    for x in enable:
        off = [y for y in off if y != x]
        if x not in on:
            on.append(x)
    for x in disable:
        on = [y for y in on if y != x]
        if x not in off:
            off.append(x)
    if on:
        out.append("--enable-features=" + ",".join(on))
    if off:
        out.append("--disable-features=" + ",".join(off))
    return out


def _video_flags(flags, config, folder):
    """Flags for the user's choice of video decoding; "on" falls back to
    "auto" when the previous start with it on did not end well."""
    mode = config["video_hw"]
    trial = Path(folder) / VIDEO_TRIAL
    if mode == "on" and trial.exists():
        config["video_hw"] = mode = "auto"
        config["video_hw_fell_back"] = True
        config.save()
    if mode != "on":
        trial.unlink(missing_ok=True)
    if mode == "on":
        try:
            trial.write_text("on\n", "utf-8")
        except OSError:
            pass
        return _feature_flags(flags, enable=VIDEO_ON)
    if mode == "off":
        return _feature_flags(flags, disable=("AcceleratedVideoDecodeLinux",))
    return flags


def _video_trial_done(folder):
    (Path(folder) / VIDEO_TRIAL).unlink(missing_ok=True)


# Engine switches that take away a protection of the engine (1.1.18, security
# audit F7/F8): the sandbox, site isolation, web security, certificate checks,
# remote control of the browser. Inherited from the environment (a system-wide
# QTWEBENGINE_CHROMIUM_FLAGS set for another program, a leftover of a test)
# they are dropped, and the window says so; only IKE_ALLOW_UNSAFE_ENGINE=1
# keeps them, and then Help -> About and the window show that protections are
# off. Graphics, video and speed switches are never touched.
UNSAFE_SWITCHES = (
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox",
    "--disable-namespace-sandbox", "--single-process", "--no-zygote",
    "--disable-site-isolation-trials", "--disable-web-security", "--allow-running-insecure-content",
    "--ignore-certificate-errors", "--ignore-certificate-errors-spki-list", "--ignore-urlfetcher-cert-requests",
    "--reduce-security-for-testing", "--unsafely-treat-insecure-origin-as-secure",
    "--allow-file-access-from-files", "--disable-features-for-testing",
    "--remote-debugging-port", "--remote-debugging-pipe", "--remote-debugging-address",
    "--remote-debugging-socket-name", "--remote-allow-origins", "--auto-open-devtools-for-tabs",
    # 1.1.19: it opens devices of the home network to every site at once (the
    # engine has no per-site form of it; tried: an "exception" for one site
    # let any other site through to the same device)
    "--ip-address-space-overrides",
)
# kept (some graphics drivers need it, and the web engine chooses the
# graphics path) but shown in the window and About as a protection that is off
NOTICE_SWITCHES = ("--disable-gpu-sandbox",)
UNSAFE_FEATURES = ("isolateorigins", "site-per-process", "siteperprocess", "originkeyedprocessesbydefault",
                   "localnetworkaccesschecks", "localnetworkaccessfornavigations",
                   "localnetworkaccesscheckswebrtc")
# the engine's own home-network protection (Local Network Access, 1.1.19): a
# public page cannot reach this computer or the home network. The engine
# checks the real address when the connection is made, so a public name that
# points home (DNS rebinding) is stopped too. Without its parameter the first
# one only warns; the second covers links, scripts and forms that open a page
# of the home network, the third WebRTC. Qt has no per-site permission for it.
LNA_FEATURES = ("LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/false",
                "LocalNetworkAccessForNavigations", "LocalNetworkAccessChecksWebRTC")
# the storage quota a site is told: a fixed 10 GiB for everyone instead of
# 60 % of the disk, to the byte (fingerprinting audit, M-4); the real limits
# do not change. Not a graphics switch.
PRIVACY_FEATURES = ("StaticStorageQuota",)


def split_flags(text):
    """QTWEBENGINE_CHROMIUM_FLAGS as Qt reads it: words, with "double quotes"
    (1.1.18, adversarial review: '"--no-sandbox"' passed a plain split)."""
    import shlex
    try:
        return shlex.split(text or "")
    except ValueError:                    # an unclosed quote
        return (text or "").replace('"', " ").split()


def join_flags(flags):
    return " ".join('"%s"' % f if any(c.isspace() for c in f) else f for f in flags)


def switch_name(token):
    """The switch a word names, as Chromium reads it: "-x" is "--x" on Linux,
    and the value after "=" does not count."""
    t = token.strip().strip("'\"")
    if t.startswith("-") and not t.startswith("--"):
        t = "-" + t
    return t.split("=", 1)[0].lower()
UNSAFE_ENV = ("QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_REMOTE_DEBUGGING")
# what this run did with them: {"dropped": [...]} or {"kept": [...]} (About, window)
ENGINE_SAFETY = {"dropped": [], "kept": []}


def unsafe_allowed():
    """The user asked on purpose for engine switches that take a protection away."""
    return os.environ.get("IKE_ALLOW_UNSAFE_ENGINE", "") == "1"


def _engine_safety(flags, env=None, allowed=None):
    """flags without the switches that take an engine protection away (unless
    allowed); the environment variables of that kind removed from `env` too.
    Returns (flags, names of what was dropped or kept)."""
    env = os.environ if env is None else env
    allowed = unsafe_allowed() if allowed is None else allowed
    out, unsafe = [], []
    for f in flags:
        name = switch_name(f)
        if name in UNSAFE_SWITCHES:
            unsafe.append(name)
            if allowed:
                out.append(f)
            continue
        if name == "--disable-features" and "=" in f:
            feats = f.split("=", 1)[1].strip("'\"").split(",")
            bad = [x for x in feats if x.strip().lower().split("<", 1)[0] in UNSAFE_FEATURES]
            if bad:
                unsafe.extend("--disable-features=" + x for x in bad)
                if not allowed:
                    feats = [x for x in feats if x not in bad]
                    if feats:
                        out.append("--disable-features=" + ",".join(feats))
                    continue
        out.append(f)
    for var in UNSAFE_ENV:
        # Qt looks only at whether the variable is there: "0" and "" count
        if var in env:
            unsafe.append(var)
            if not allowed:
                env.pop(var, None)
    return out, unsafe


def refuse_root():
    """True when I.K.E. must not start: run as root (administrator), where the
    engine's sandbox cannot work, without the user asking for it on purpose
    (1.1.18, security audit F8: the sandbox was switched off silently)."""
    return hasattr(os, "geteuid") and os.geteuid() == 0 and not unsafe_allowed()


ROOT_MESSAGE = ("I.K.E. does not start as root (administrator): the engine's sandbox, which keeps web "
                "pages away from the computer, cannot work there. Start it as your normal user. "
                "To start it as root anyway, without the sandbox and at your own risk, set "
                "IKE_ALLOW_UNSAFE_ENGINE=1.")


def _chromium_flags(config):
    """Build engine switches and remove inherited global dark-mode overrides.

    Both dark renderers are configured on each QWebEnginePage, so a site can
    be exempted without changing every other tab or restarting the browser.
    """
    flags = split_flags(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
    flags, unsafe = _engine_safety(flags)
    ENGINE_SAFETY["kept" if unsafe_allowed() else "dropped"] = unsafe
    ENGINE_SAFETY["kept"] = ENGINE_SAFETY["kept"] + [n for n in map(switch_name, flags) if n in NOTICE_SWITCHES]
    if unsafe and not unsafe_allowed():
        sys.stderr.write("I.K.E.: engine switches that remove a protection were ignored: %s "
                         "(IKE_ALLOW_UNSAFE_ENGINE=1 keeps them)\n" % " ".join(unsafe))
    flags, forced = _strip_dark_flags(flags)
    changed = False
    if forced and not config["dark_env_migrated"]:
        # pages were dark because of a system-wide switch: keep them dark
        config["dark_mode"] = "on"
        config["dark_env_migrated"] = True
        changed = True
    if config["dark_mode"] not in ("on", "off"):          # "system" (before 1.0.5)
        config["dark_mode"] = "on"
        changed = True
    if changed:
        config.save()
    if not any(f.startswith("--widevine-path") for f in flags):
        lib = find_widevine()
        if lib:
            flags.append("--widevine-path=%s" % lib)
            os.environ["IKE_WIDEVINE"] = lib
    # pages scroll smoothly (wheel and keys), unless the user switched it off or chose otherwise himself
    if (config["smooth_scrolling"] and "--enable-smooth-scrolling" not in flags
            and "--disable-smooth-scrolling" not in flags):
        flags.append("--enable-smooth-scrolling")
    names = {switch_name(f) for f in flags}
    # at the global level Maximum the engine itself speaks en-US: its own texts
    # (form messages, the PDF viewer), Date's zone names and the shared and
    # service workers followed the system's language (owner's decision for
    # 1.1.20, fingerprinting audit M-7). I.K.E.'s own interface keeps the
    # user's language. Read at start: a change of level applies after a restart.
    if config["shield_level"] == "maximum" and "--lang" not in names:
        flags.append("--lang=en-US")
        names.add("--lang")
    if hasattr(os, "geteuid") and os.geteuid() == 0 and "--no-sandbox" not in names:
        # only reached with IKE_ALLOW_UNSAFE_ENGINE=1 (refuse_root): the
        # engine cannot sandbox as root, and the window says it is off
        flags.append("--no-sandbox")
        ENGINE_SAFETY["kept"].append("--no-sandbox")
    # every site in its own process, as in Chrome (1.1.18, security
    # audit F1; owner's decision): Qt WebEngine leaves it off, so a frame of
    # another site shared its page's process and one bug in the engine could
    # read the other site. A security switch, not a graphics path; about a
    # tenth more memory. Turning it off takes IKE_ALLOW_UNSAFE_ENGINE=1.
    if "--site-per-process" not in names and "--disable-site-isolation-trials" not in names:
        flags.append("--site-per-process")
    off = {x.split(":")[0].split("<")[0].lower() for f in flags if f.startswith("--disable-features=")
           for x in f.split("=", 1)[1].split(",")}
    want = [x for x in LNA_FEATURES + PRIVACY_FEATURES
            if x.split(":")[0].lower() not in off]     # off only on request
    if want:
        names_on = {x.split(":")[0] for x in want}
        flags = [f if not f.startswith("--enable-features=") else "--enable-features=" + ",".join(
                 x for x in f.split("=", 1)[1].split(",") if x.split(":")[0].split("<")[0] not in names_on)
                 for f in flags]                     # an inherited "warn only" does not win
        flags = _feature_flags([f for f in flags if f != "--enable-features="], enable=want)
    flags = _video_flags(flags, config, CONFIG_DIR)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = join_flags(flags)


def memory_low(path="/proc/meminfo"):
    """True when less than a tenth of the computer's memory is still available
    (the kernel's own estimate, MemAvailable)."""
    try:
        info = {}
        with open(path, encoding="ascii") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    info[key] = int(rest.split()[0])
        return info["MemAvailable"] < info["MemTotal"] / 10
    except (OSError, ValueError, KeyError, IndexError):
        return False


def sandbox_off():
    """True when the engine's sandbox, which keeps a web page's process away
    from the user's files, is switched off for this run."""
    names = {switch_name(f) for f in split_flags(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))}
    return "--no-sandbox" in names or "QTWEBENGINE_DISABLE_SANDBOX" in os.environ


def site_isolated():
    """True when every site runs in its own engine process for this run."""
    names = {switch_name(f) for f in split_flags(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))}
    return "--site-per-process" in names and "--disable-site-isolation-trials" not in names


def engine_safety_lines(T):
    """What Help -> About and the start-up notice say about engine switches
    that were dropped, or kept on the user's request (1.1.18)."""
    out = []
    if ENGINE_SAFETY["kept"]:
        out.append(T("Engine protections switched off on request (IKE_ALLOW_UNSAFE_ENGINE): %s")
                   % " ".join(sorted(set(ENGINE_SAFETY["kept"]))))
    if ENGINE_SAFETY["dropped"]:
        out.append(T("Engine switches that remove a protection were ignored: %s")
                   % " ".join(sorted(set(ENGINE_SAFETY["dropped"]))))
    return out


def _wait_for_previous():
    """After a restart: let the previous instance finish closing first."""
    import time
    pid = os.environ.pop("IKE_WAIT_PID", "")
    if not pid.isdigit():
        return
    for _ in range(100):
        if not os.path.exists("/proc/%s" % pid):
            return
        time.sleep(0.1)


INTERNAL_ERRORS = []          # tracebacks of errors the browser went on after (this session)


def _keep_running_after_errors():
    """PyQt ends the whole program when a Python error escapes from the
    handler of a signal (a click, a timer, a finished download). One broken
    handler must not take every open tab with it: the error is written to
    the terminal and to errors.log in the cache folder, counted (Help → About)
    and the browser goes on."""
    def hook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        # imported only when there is an error to write: on Python 3.14 the
        # module costs about 12 ms of every start (1.1.22)
        import traceback
        text = "".join(traceback.format_exception(kind, value, tb))
        INTERNAL_ERRORS.append(text)
        del INTERNAL_ERRORS[:-50]
        try:
            sys.stderr.write("I.K.E. %s: internal error, the browser goes on\n%s" % (__version__, text))
        except (OSError, ValueError, AttributeError):
            pass
        try:
            log = CACHE_DIR / "errors.log"
            old = log.read_text("utf-8", "replace")[-150_000:] if log.exists() else ""
            log.write_text("%s\n--- I.K.E. %s, %s\n%s" % (old, __version__, time.strftime("%Y-%m-%d %H:%M:%S"), text),
                           "utf-8")
        except OSError:
            pass
    sys.excepthook = hook


def instance_addresses():
    """Where the running browser of this user and profile listens for the
    addresses a second start hands over: [(address, checked)].

    First a socket in the user's own runtime folder, which no other user can
    enter. Then the name in the shared temporary folder that earlier versions
    used, which is only trusted when the socket there belongs to this user:
    anybody may create a file with that name there."""
    import tempfile
    uid = os.getuid() if hasattr(os, "getuid") else "u"
    name = "%s-%s-%s" % (APP_ID, uid, PROFILE)
    found = []
    run = os.environ.get("XDG_RUNTIME_DIR", "")
    try:
        if run and os.path.isdir(run) and os.stat(run).st_uid == uid and os.access(run, os.W_OK):
            path = os.path.join(run, name + ".sock")
            if len(path.encode()) < 100:              # a socket path cannot be longer
                found.append(path)
    except OSError:
        pass
    found.append(name)
    old = os.path.join(tempfile.gettempdir(), name)

    def own(address):
        path = address if os.path.isabs(address) else old
        try:
            return os.lstat(path).st_uid == uid
        except OSError:
            return False
    return [(a, own(a)) for a in found]


def handed_over(data):
    """(urls, private) from the message of a second start, or None if it is
    not such a message."""
    try:
        msg = json.loads(data[:1_000_000].decode("utf-8"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(msg, dict) or not isinstance(msg.get("urls", []), list):
        return None
    urls = [u for u in msg.get("urls", [])[:100] if isinstance(u, str) and 0 < len(u) < 20000]
    return urls, msg.get("private") is True


def _to_url(arg):
    if os.path.exists(arg):
        return QUrl.fromLocalFile(os.path.abspath(arg)).toString()
    return QUrl.fromUserInput(arg).toString()


def parse_args(argv):
    """(arguments, unknown options) of the command line.

    With no option at all (the usual start, or addresses handed over by
    another program) the answer is the one argparse gives, without argparse:
    on Python 3.14 it costs about 12 ms of every start (its help colours bring
    in dataclasses and inspect; 1.1.22). Anything that starts with "-" goes
    through argparse as before."""
    if not any(a.startswith("-") for a in argv):
        from types import SimpleNamespace
        return SimpleNamespace(urls=list(argv), private=False, profile=""), []
    import argparse
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_LONG_NAME)
    parser.add_argument("urls", nargs="*", help="addresses to open")
    parser.add_argument("--private", action="store_true", help="open a private window")
    parser.add_argument("--profile", default="", help="use a separate named profile")
    parser.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    return parser.parse_known_args(argv)


def main(argv=None):
    args, unknown = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if unknown:
        # not passed on to Qt: another program hands over its "address" as
        # an argument, and one that starts with "-" was read as an option of
        # Qt (review of 1.1.19, L11). The engine's switches never come this way.
        sys.stderr.write("I.K.E.: ignored: %s\n" % " ".join(unknown)[:300])

    _wait_for_previous()
    ensure_dirs()
    from . import sitedata
    sitedata.at_start()                  # site data the user asked to clear: before the engine opens it
    if refuse_root():
        sys.stderr.write("I.K.E.: %s\n" % ROOT_MESSAGE)
        if os.environ.get("QT_QPA_PLATFORM", "") == "offscreen" or not (
                os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
            return 1                      # no desktop to show the message on: the terminal has it
        try:
            box_app = QApplication([sys.argv[0]])
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, APP_NAME, ROOT_MESSAGE)
            del box_app
        except Exception:
            pass
        return 1
    config = Config()
    _chromium_flags(config)
    # at Strict and Maximum the engine sees only the most common font
    # families (1.1.21): before Qt or the engine reads fontconfig
    from . import fontallow
    fontallow.apply(config["shield_level"], CONFIG_DIR)
    from .shields import register_scheme
    register_scheme()

    qapp = QApplication([sys.argv[0]])
    qapp.setApplicationName(APP_ID)
    qapp.setApplicationDisplayName(APP_NAME if PROFILE == "default"
                                   else "%s [%s]" % (APP_NAME, PROFILE))
    qapp.setApplicationVersion(__version__)
    qapp.setDesktopFileName(APP_ID)
    qapp.setQuitOnLastWindowClosed(True)
    QNetworkProxyFactory.setUseSystemConfiguration(True)

    urls = [_to_url(u) for u in args.urls]

    # Single instance: hand the request to the running browser.
    addresses = instance_addresses()
    if not os.environ.get("IKE_NO_SINGLE"):
        for address, ours in addresses:
            if not ours:
                continue                  # nothing there, or a socket of somebody else
            sock = QLocalSocket()
            sock.connectToServer(address)
            if sock.waitForConnected(300):
                sock.write(json.dumps({"urls": urls, "private": args.private}).encode())
                sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()
                return 0

    from . import i18n
    i18n.setup(config["language"])
    if i18n.right_to_left():
        # the whole interface from right to left, as the language is written
        # (1.1.20: Arabic, Hebrew, Persian and Urdu); pages decide for themselves
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    # room around button texts and menus that scroll, over the desktop's own style (1.1.21)
    from . import uistyle
    uistyle.install(qapp)
    from . import icons
    icons.apply_scheme(config)
    from . import themes
    if themes.current(config) is not None:
        themes.apply(config)
    icons.setup(config)
    # the engine's and Qt's own texts (dialog buttons, context menus)
    from PyQt6.QtCore import QLibraryInfo, QTranslator
    qapp._translators = []
    for base in ("qtbase_", "qtwebengine_"):
        tr = QTranslator(qapp)
        # Qt names its Chinese files after the region (qtbase_zh_CN)
        qt_code = {"zh": "zh_CN"}.get(i18n.current(), i18n.current())
        if tr.load(base + qt_code,
                   QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            qapp.installTranslator(tr)
            qapp._translators.append(tr)
    _keep_running_after_errors()
    ike = IkeApp(qapp, config)

    server = QLocalServer(qapp)
    server_name = ""
    if not os.environ.get("IKE_NO_SINGLE"):
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)     # this user only
        for address, _ours in addresses:
            QLocalServer.removeServer(address)
            if server.listen(address):
                server_name = address
                break

        def incoming():
            conn = server.nextPendingConnection()
            if conn is None:
                return

            def read():
                request = handed_over(bytes(conn.readAll()))
                conn.deleteLater()
                if request is not None:
                    ike.open_urls(*request)
            conn.readyRead.connect(read)
        server.newConnection.connect(incoming)

    if not config["welcome_done"]:
        # the first start (1.1.24): a short welcome, then the first window
        from . import welcome
        welcome.show_first(ike, lambda: ike.start(urls, args.private))
    else:
        ike.start(urls, args.private)
    notice = engine_safety_lines(i18n.T)
    if notice and not os.environ.get("IKE_TEST_NOASK"):
        # protections of the engine changed by switches: the user sees it at once
        QTimer.singleShot(1500, lambda: ike._notify(" · ".join(notice)))
    hook = os.environ.get("IKE_TEST_HOOK")
    if hook:
        import runpy
        runpy.run_path(hook, init_globals={"ike": ike, "qapp": qapp})
    code = qapp.exec()
    ike.blocker.close()                  # a filter engine still being built finishes first
    _video_trial_done(CONFIG_DIR)          # a normal exit: video decoding "on" did no harm
    background.let_go()          # a download still waiting for its server must not be destroyed
    if config["clear_on_exit"] and sitedata.asked() and not getattr(ike, "_restart", False):
        sitedata.remove()        # "clear when closed": now, and once more at the next start
    if getattr(ike, "_restart", False):
        import subprocess
        server.close()
        if server_name:
            QLocalServer.removeServer(server_name)
        boot = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ike_boot.py")
        from .fontallow import child_env
        env = dict(child_env(os.environ), IKE_WAIT_PID=str(os.getpid()))
        cmd = [sys.executable, boot] + (["--profile", args.profile] if args.profile else [])
        subprocess.Popen(cmd, env=env, start_new_session=True, stdin=subprocess.DEVNULL)
    return code
