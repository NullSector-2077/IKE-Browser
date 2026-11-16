"""Application object and entry point."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkProxyFactory
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (must load before QApplication)
from PyQt6.QtWidgets import QApplication, QFileDialog

from . import APP_ID, APP_LONG_NAME, APP_NAME, __version__, background
from .config import CACHE_DIR, PROFILE, RES_DIR, Config, ensure_dirs


def find_widevine(home=None):
    """Path of the Widevine library I.K.E. may use, or None (see drm.py)."""
    from .drm import library_path
    return library_path()


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
        self.shields = Shields(config, self.blocker, self)
        self.shields.theme_changed.connect(self._theme_from_newtab, Qt.ConnectionType.QueuedConnection)
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
        from .weather import Weather
        self.weather = Weather(config, self.network, self)
        self.weather.changed.connect(self._weather_changed)
        # Built from our own files: a theme lookup can return an empty icon on
        # Plasma, which then also blanks the task-bar entry.
        from PyQt6.QtCore import QSize
        self.icon = QIcon()
        for size in (48, 64, 128, 256):
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
        self.shields.apply_dns()
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
        win = BrowserWindow(self, private=private, popup=popup)
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

    def _theme_from_newtab(self):
        """The Cyber theme was tried, or left, from the new tab page."""
        from . import themes
        themes.apply(self.config)
        self.refresh_windows()

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
        from .window import NEWTAB
        self.blocker.load()
        cfg = self.config
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
        QTimer.singleShot(20000, self._healthy)

    def _healthy(self):
        from . import updater
        updater.confirm_healthy()
        notice = updater.take_rollback_notice()
        if notice:
            self._desktop_notify(self._t("I.K.E. update %s did not start correctly and was "
                                         "removed. The previous version is in use.") % notice[0])

    def open_urls(self, urls, private=False):
        """Called when a second instance forwards its arguments."""
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

    def launch_profile(self, name):
        from .updater import boot_command
        if name == PROFILE:
            return
        env = dict(os.environ)
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

    def _check_chrome_version(self):
        """Once a day: learn the current stable Chrome version (see chromever)."""
        from . import chromever
        if getattr(self, "_chrome_check", None) is not None or not chromever.due(self.config):
            return
        before = chromever.current(self.config)

        def done(major):
            self._chrome_check = None
            self.config["chrome_checked"] = int(time.time())
            if chromever.plausible(major):
                self.config["chrome_major"] = major
            self.config.save()
            if chromever.current(self.config) != before:
                self.shields.apply_settings()
        self._chrome_check = chromever.Checker(self)
        self._chrome_check.done.connect(done)
        background.start(self._chrome_check)

    # --- settings / updates ------------------------------------------
    def settings_changed(self):
        self.desktop.settings_changed()
        self.shields.apply_settings()
        self.shields.apply_dns()
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
        if self.updater.run(install=self.config["app_updates"] == "auto") and manual:
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
        elif kind == "flatpak":
            if manual:
                QMessageBox.information(win, "I.K.E.", T(
                    "This copy of I.K.E. is a Flatpak: its updates come from Flatpak (your software "
                    "centre, or the command flatpak update), not from I.K.E.'s own updater."))
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
                self.updater.run(install=True)

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
            win.statusBar().showMessage(text, 5000)
            win.statusBar().show()
            QTimer.singleShot(5200, win._hide_status)

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
        dlg.show()
        dlg.raise_()
        return dlg

    def show_settings(self, parent=None, page=None):
        from .dialogs import SettingsDialog
        return self._show("settings", lambda: SettingsDialog(self, parent or self.active_window(), page))

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


def _chromium_flags(config):
    """Build engine switches and remove inherited global dark-mode overrides.

    Both dark renderers are configured on each QWebEnginePage, so a site can
    be exempted without changing every other tab or restarting the browser.
    """
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
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
    if hasattr(os, "geteuid") and os.geteuid() == 0 and "--no-sandbox" not in flags:
        flags.append("--no-sandbox")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)


def sandbox_off():
    """True when the engine's sandbox, which keeps a web page's process away
    from the user's files, is switched off for this run."""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    return "--no-sandbox" in flags or os.environ.get("QTWEBENGINE_DISABLE_SANDBOX", "") not in ("", "0")


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
    import traceback

    def hook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
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
    import re
    import tempfile
    uid = os.getuid() if hasattr(os, "getuid") else "u"
    name = "%s-%s-%s" % (APP_ID, uid, PROFILE)
    found = []
    run = os.environ.get("XDG_RUNTIME_DIR", "")
    flatpak_id = os.environ.get("FLATPAK_ID", "")
    if run and re.fullmatch(r"[A-Za-z0-9_.-]+", flatpak_id):
        # each start of a Flatpak gets a runtime folder of its own; only the
        # app's folder inside it is shared by all its starts
        run = os.path.join(run, "app", flatpak_id)
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_LONG_NAME)
    parser.add_argument("urls", nargs="*", help="addresses to open")
    parser.add_argument("--private", action="store_true", help="open a private window")
    parser.add_argument("--profile", default="", help="use a separate named profile")
    parser.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    _wait_for_previous()
    ensure_dirs()
    from . import sitedata
    sitedata.at_start()                  # site data the user asked to clear: before the engine opens it
    config = Config()
    _chromium_flags(config)
    from .shields import register_scheme
    register_scheme()

    qapp = QApplication([sys.argv[0]] + qt_args)
    qapp.setApplicationName(APP_ID)
    qapp.setApplicationDisplayName(APP_NAME if PROFILE == "default"
                                   else "%s [%s]" % (APP_NAME, PROFILE))
    qapp.setApplicationVersion(__version__)
    from .osinfo import desktop_id
    qapp.setDesktopFileName(desktop_id())     # the Flatpak's ID inside a Flatpak
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

    ike.start(urls, args.private)
    hook = os.environ.get("IKE_TEST_HOOK")
    if hook:
        import runpy
        runpy.run_path(hook, init_globals={"ike": ike, "qapp": qapp})
    code = qapp.exec()
    background.let_go()          # a download still waiting for its server must not be destroyed
    if config["clear_on_exit"] and sitedata.asked() and not getattr(ike, "_restart", False):
        sitedata.remove()        # "clear when closed": now, and once more at the next start
    if getattr(ike, "_restart", False):
        import subprocess
        server.close()
        if server_name:
            QLocalServer.removeServer(server_name)
        boot = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ike_boot.py")
        env = dict(os.environ, IKE_WAIT_PID=str(os.getpid()))
        cmd = [sys.executable, boot] + (["--profile", args.profile] if args.profile else [])
        subprocess.Popen(cmd, env=env, start_new_session=True, stdin=subprocess.DEVNULL)
    return code
