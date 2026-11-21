"""Window features layered on the core tab model: workspaces, tab groups,
containers, split view, tab suspension, reader mode, translation, floating
video, site permissions and session (de)serialisation."""

import json
import time
from urllib.parse import quote

from PyQt6.QtCore import QRect, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import i18n
from .config import RES_DIR, list_profiles
from .i18n import T

GROUP_COLORS = ["#3daee9", "#27ae60", "#f67400", "#da4453", "#9b59b6",
                "#fdbc4b", "#1abc9c", "#7f8c8d"]
_PERM_LABELS = None


def tab_icon(base, group_color=None, container_color=None):
    """Favicon with a coloured bar (tab group) and/or dot (container)."""
    if not group_color and not container_color:
        return base
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    h = 25 if group_color else 32
    base.paint(p, QRect((32 - h) // 2, 0, h, h))
    p.setPen(Qt.PenStyle.NoPen)
    if group_color:
        p.setBrush(QColor(group_color))
        p.drawRoundedRect(0, 27, 32, 5, 2, 2)
    if container_color:
        p.setBrush(QColor(container_color))
        p.drawEllipse(19, 0, 13, 13)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def _theme(name, fallback):
    from .icons import themed
    return themed(name, fallback)


class TabSearch(QDialog):
    """Find an open tab, in any window, by typing part of its title or address."""

    def __init__(self, window):
        super().__init__(window)
        from PyQt6.QtWidgets import QLineEdit, QListWidget
        self.win = window
        self.setWindowTitle(T("Search open tabs"))
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(T("Type part of a title or address"))
        self.edit.setClearButtonEnabled(True)
        self.list = QListWidget(self)
        lay.addWidget(self.edit)
        lay.addWidget(self.list, 1)
        self.rows = []
        for w in window.app.windows:
            if w.popup:
                continue
            for v in w.views:
                title = v.title() or getattr(v, "saved_title", "") or T("New tab")
                url = v.url().toDisplayString() or (getattr(v, "pending_url", "") or "")
                self.rows.append((w, v, title, url))
        self.edit.textChanged.connect(self._filter)
        self.edit.returnPressed.connect(self._go)
        self.list.itemActivated.connect(lambda _i: self._go())
        self.list.itemClicked.connect(lambda _i: self._go())
        self.edit.installEventFilter(self)
        self._filter("")

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == event.Type.KeyPress \
                and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.list.count():
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            self.list.setCurrentRow((self.list.currentRow() + step) % self.list.count())
            return True
        return super().eventFilter(obj, event)

    def _filter(self, text):
        words = text.lower().split()
        self.list.clear()
        for w, v, title, url in self.rows:
            hay = (title + " " + url).lower()
            if all(word in hay for word in words):
                item = QListWidgetItem(v.last_icon if not v.last_icon.isNull() else QIcon(),
                                       "%s\n%s" % (title, url))
                item.setData(Qt.ItemDataRole.UserRole, (w, v))
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _go(self):
        item = self.list.currentItem()
        if item is None:
            return
        w, v = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if v in w.views:
            w.set_current(v)
            w.raise_()
            w.activateWindow()


class FloatingVideo(QWidget):
    """Small always-on-top window that hosts a tab while its video plays."""

    CSS = ("video.ike-float{position:fixed!important;left:0!important;top:0!important;"
           "width:100vw!important;height:100vh!important;max-width:none!important;"
           "max-height:none!important;z-index:2147483647!important;background:#000!important;"
           "object-fit:contain!important;transform:none!important}"
           "html.ike-float,html.ike-float body{overflow:hidden!important}")
    JS_ON = """(function(css){
      var vids=[].slice.call(document.querySelectorAll('video'));
      if(!vids.length)return false;
      vids.sort(function(a,b){return (b.clientWidth*b.clientHeight+(b.paused?0:1e9))-(a.clientWidth*a.clientHeight+(a.paused?0:1e9));});
      var s=document.createElement('style');s.id='ike-float-style';s.textContent=css;document.documentElement.appendChild(s);
      vids[0].classList.add('ike-float');document.documentElement.classList.add('ike-float');return true;})(%r);"""
    JS_OFF = """(function(){var s=document.getElementById('ike-float-style');if(s)s.remove();
      [].forEach.call(document.querySelectorAll('.ike-float'),function(e){e.classList.remove('ike-float');});})();"""

    def __init__(self, window, view):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.win = window
        self.view = view
        self.setWindowTitle(view.title() or "I.K.E.")
        self.setWindowIcon(window.app.icon)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(view, 1)
        view.show()
        self.resize(480, 270)
        view.page().runJavaScript(self.JS_ON % self.CSS, 0)

    def closeEvent(self, event):
        view, self.view = self.view, None
        if view is not None:
            view.page().runJavaScript(self.JS_OFF, 0)
            self.layout().removeWidget(view)
            try:
                self.win._adopt_view(view)
            except RuntimeError:        # main window already gone
                view.deleteLater()
        super().closeEvent(event)


class WindowFeatures:
    """Mixin for BrowserWindow."""

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _init_features(self):
        self._floating = []
        self.toolbar_spilled = set()     # buttons listed under » because the window is narrow
        self._tool_widths = {}           # key -> width its button takes in the toolbar
        self._restoring = False
        self.app.qapp.focusChanged.connect(self._focus_changed)
        self._update_ws_buttons()

    def _build_split_holder(self):
        self.split_holder = QWidget(self)
        lay = QVBoxLayout(self.split_holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget(self.split_holder)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 2, 4, 2)
        self.split_title = QLabel(bar)
        close = QToolButton(bar)
        close.setAutoRaise(True)
        close.setIcon(_theme("view-close", QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip(T("Close split view"))
        close.clicked.connect(self.unsplit)
        bl.addWidget(self.split_title, 1)
        bl.addWidget(close)
        lay.addWidget(bar)
        self.split_holder.hide()
        return self.split_holder

    def _make_ws_button(self, parent):
        b = QToolButton(parent)
        b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setIcon(_theme("view-list-icons", QStyle.StandardPixmap.SP_FileDialogListView))
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setToolTip(T("Workspaces: separate sets of tabs in this window"))
        m = QMenu(b)
        m.aboutToShow.connect(lambda m=m: self._fill_ws_menu(m))
        b.setMenu(m)
        return b

    def _build_feature_actions(self):
        """The actions and submenus of the window's features; window.py puts
        them in the menu bar and in the ☰ menu (_build_menus)."""
        A = self._action
        self.m_containers = QMenu(T("New tab in container"), self)
        self.m_containers.setIcon(_theme("folder-lock", QStyle.StandardPixmap.SP_DirIcon))
        self.m_containers.aboutToShow.connect(self._fill_containers)
        self.m_profiles = QMenu(T("Profiles"), self)
        self.m_profiles.setIcon(_theme("user-identity", QStyle.StandardPixmap.SP_DirHomeIcon))
        self.m_profiles.aboutToShow.connect(self._fill_profiles)
        self.act_import = A(T("Import from another browser…"), self.app.show_import, None, "document-import",
                            T("Copy bookmarks, history and passwords from Firefox or Chromium browsers"))
        self.act_backup = A(T("Back up I.K.E. data…"), self.app.backup, None, "document-save-as",
                            T("Save settings, bookmarks, history and the password vault to one file"))
        self.act_restore = A(T("Restore a backup…"), self.app.restore_backup, None, "document-revert",
                             T("Replace the current data with a backup file"))
        self.act_split = A(T("Split view"), self.toggle_split, "Ctrl+Shift+2", "view-split-left-right",
                           T("Show two tabs side by side"), checkable=True)
        self.act_reader = A(T("Reader mode"), self.toggle_reader, "F9", "view-readermode",
                            T("Show only the article text, without clutter"))
        ws = self.m_workspaces = QMenu(T("Workspaces"), self)
        ws.setIcon(_theme("view-list-icons", QStyle.StandardPixmap.SP_FileDialogListView))
        ws.aboutToShow.connect(lambda: self._fill_ws_menu(ws))
        self.act_passwords = A(T("Passwords…"), self.app.show_passwords, "Ctrl+Shift+K", "dialog-password",
                               T("Saved logins, password generator, import and export"))
        self.act_fill_login = A(T("Fill login on this page"), self.fill_login, "Ctrl+Shift+L",
                                "password-show-on", T("Fill the saved user name and password for this site"))
        # no shortcut of its own: Ctrl+Shift+A opens the extensions (owner's
        # decision for 1.1.20; with both, Qt ran neither)
        self.act_search_tabs = A(T("Search open tabs…"), self.search_tabs, None, "edit-find",
                                 T("Find an open tab by its title or address"))
        self.act_translate = A(T("Translate page…"), self.translate_page, None, "translate",
                               T("Translate this page through an external web service"))
        self.act_float = A(T("Video in floating window"), self.float_video, "Ctrl+Shift+V",
                           "media-playback-start",
                           T("Keep the video of this tab on top of other windows (picture in picture)"))
        self.act_suspend = A(T("Suspend inactive tabs now"), lambda: self.app.sleep_tabs(force=True), None,
                             "system-suspend", T("Free the memory used by background tabs"))
        self.act_resources = A(T("Site resources…"), self.app.show_resources, "Shift+Esc",
                               "utilities-system-monitor",
                               T("Memory, CPU and network used by each site, with optional limits"))
        self.act_watches = A(T("Watched pages…"), self.app.show_watches, None, "view-visible",
                             T("Pages and parts of pages you get notified about when they change"))
        self.act_permissions = A(T("Site permissions…"), self.app.show_permissions, None,
                                 ("preferences-security", "object-locked"),
                                 T("Camera, microphone, location, notifications and clipboard access per site"))
        self.act_store = A(T("Chrome Web Store"), self.open_web_store, None, "plugins",
                           T("Browse extensions; on an extension page use “Install in I.K.E.”"))

    def ext_on(self, ext_id):
        """Is one of I.K.E.'s own extensions switched on? (see ikeextensions.py)"""
        from . import ikeextensions
        return ikeextensions.on(self.app.config, ext_id)

    # ------------------------------------------------------------------
    # vertical tabs that hide and come back at the left edge
    # ------------------------------------------------------------------
    def _build_vtabs_root(self):
        root = QWidget(self)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.vtab_edge = QWidget(root)          # thin strip that senses the mouse
        self.vtab_edge.setFixedWidth(4)
        self.vtab_edge.setMouseTracking(True)
        self.vtab_edge.installEventFilter(self)
        self.vtab_edge.hide()
        lay.addWidget(self.vtab_edge)
        lay.addWidget(self.splitter, 1)
        self.setCentralWidget(root)
        self._vtabs_floating = False
        self._vtabs_timer = QTimer(self)
        self._vtabs_timer.setInterval(250)
        self._vtabs_timer.timeout.connect(self._vtabs_check)

    def _toggle_vtabs_autohide(self):
        cfg = self.app.config
        cfg["vtabs_autohide"] = not cfg["vtabs_autohide"]
        cfg.save()
        self.app.refresh_windows()

    VTABS_ICONS_WIDTH = 48          # the panel with only the tabs' icons (1.1.16)

    def _toggle_vtabs_icons(self):
        cfg = self.app.config
        cfg["vtabs_icons_only"] = not cfg["vtabs_icons_only"]
        cfg.save()
        self.app.refresh_windows()

    def vtabs_width_now(self):
        """The width the tab panel has: narrow with only icons, else the user's."""
        if self.app.config["vtabs_icons_only"]:
            return self.VTABS_ICONS_WIDTH
        return int(self.app.config["vtabs_width"])

    def _apply_vtabs_icons(self):
        on = bool(self.app.config["vtabs_icons_only"])
        SP = QStyle.StandardPixmap
        self.vicons_btn.setIcon(_theme("view-list-details", SP.SP_FileDialogDetailedView) if on
                                else _theme("view-grid", SP.SP_FileDialogListView))
        self.vicons_btn.setToolTip(T("Show the titles of the tabs") if on else
                                   T("Show only the icons of the tabs"))
        self._vhead.setDirection(QBoxLayout.Direction.TopToBottom if on else QBoxLayout.Direction.LeftToRight)
        self.ws_btn_v.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if on
                                         else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.vplus.setText("" if on else T("New tab"))
        if on:
            self.vtab_panel.setMinimumWidth(self.VTABS_ICONS_WIDTH)
            self.vtab_panel.setMaximumWidth(self.VTABS_ICONS_WIDTH)
        else:
            self.vtab_panel.setMaximumWidth(16777215)
            self.vtab_panel.setMinimumWidth(120)
        if getattr(self, "_vtabs_icons_state", None) != on:
            self._vtabs_icons_state = on
            if not self._vtabs_floating:
                w = self.vtabs_width_now()
                self.splitter.setSizes([w, max(200, self.width() - w)])
            elif self.vtab_panel.isVisible():
                self.vtab_panel.resize(self.vtabs_width_now(), self.vtab_panel.height())
            self.vtabs.doItemsLayout()
            self.vtabs.viewport().update()

    def _apply_vtabs(self, show):
        """show: vertical tabs are in use and the window chrome is visible."""
        self._apply_vtabs_icons()
        auto = bool(self.app.config["vtabs_autohide"])
        SP = QStyle.StandardPixmap
        self.vhide_btn.setIcon(_theme("window-pin", SP.SP_ArrowRight) if auto
                               else _theme("sidebar-collapse-left", SP.SP_ArrowLeft))
        self.vhide_btn.setToolTip(T("Keep the tabs always visible") if auto else
                                  T("Hide the tabs (they come back when the mouse touches "
                                    "the left edge)"))
        if show and auto:
            if not self._vtabs_floating:
                if self.vtab_panel.width() > 100 and not self.app.config["vtabs_icons_only"]:
                    self.app.config["vtabs_width"] = self.vtab_panel.width()
                self.vtab_panel.setParent(self.centralWidget())
                self._vtabs_floating = True
                self.vtab_panel.hide()
            self.vtab_edge.show()
            # the panel slides in over the page: its own separator line (1.1.19);
            # pinned, the splitter's handle already parts it from the page
            from .polish import part
            self.vtabs_edge.setVisible(part("vtabs_edge"))
        else:
            self._vtabs_timer.stop()
            self._vtabs_hiding = False
            if getattr(self, "_vtabs_anim", None) is not None:
                self._vtabs_anim.stop()
            if self._vtabs_floating:
                self.splitter.insertWidget(0, self.vtab_panel)
                self.splitter.setStretchFactor(0, 0)
                w = self.vtabs_width_now()
                self.splitter.setSizes([w, max(200, self.width() - w)])
                self._vtabs_floating = False
            self.vtab_edge.hide()
            self.vtabs_edge.hide()
            self.vtab_panel.setVisible(show)

    def _vtabs_resized(self, *_a):
        """Remember the width the user gave to the tab panel."""
        if self._vtabs_floating or not self.vtab_panel.isVisible() or self.app.config["vtabs_icons_only"]:
            return
        w = self.vtab_panel.width()
        if w < 60 or w == self.app.config["vtabs_width"]:
            return
        self.app.config["vtabs_width"] = w
        timer = getattr(self, "_vtabs_save", None)
        if timer is None:
            from PyQt6.QtCore import QTimer
            timer = self._vtabs_save = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(800)
            timer.timeout.connect(self.app.config.save)
        timer.start()

    def _vtabs_slide(self, x, then=None):
        """Move the floating tab panel to x with a short, easing animation."""
        from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation

        from . import effects
        ms = 0 if effects.reduced_motion() else int(self.app.config["vtabs_anim_ms"])
        anim = getattr(self, "_vtabs_anim", None)
        if anim is None:
            anim = self._vtabs_anim = QPropertyAnimation(self.vtab_panel, b"pos", self)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.stop()
        try:
            anim.finished.disconnect()
        except TypeError:
            pass
        if ms <= 0:
            self.vtab_panel.move(x, 0)
            if then:
                then()
            return
        anim.setDuration(ms)
        anim.setStartValue(self.vtab_panel.pos())
        anim.setEndValue(QPoint(x, 0))
        if then:
            anim.finished.connect(then)
        anim.start()

    def _vtabs_reveal(self):
        if not self._vtabs_floating:
            return
        hiding = getattr(self, "_vtabs_hiding", False)
        if self.vtab_panel.isVisible() and not hiding:
            return
        root = self.centralWidget()
        w = self.VTABS_ICONS_WIDTH if self.app.config["vtabs_icons_only"] else \
            max(160, min(int(self.app.config["vtabs_width"]), root.width() // 2))
        if not hiding:
            self.vtab_panel.setGeometry(-w, 0, w, root.height())
        self._vtabs_hiding = False
        self.vtab_panel.show()
        self.vtab_panel.raise_()
        self._vtabs_slide(0)
        self._vtabs_timer.start()

    def _vtabs_check(self):
        """Hide the floating tab panel once the mouse has left it."""
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication
        if not self._vtabs_floating or not self.vtab_panel.isVisible():
            self._vtabs_timer.stop()
            return
        if QApplication.activePopupWidget() is not None or QApplication.mouseButtons():
            return                       # a menu is open or a tab is being dragged
        if getattr(self, "_vtabs_hiding", False):
            return
        pos = self.vtab_panel.mapFromGlobal(QCursor.pos())
        if not self.vtab_panel.rect().adjusted(-6, -6, 14, 6).contains(pos):
            self._vtabs_hiding = True
            self._vtabs_timer.stop()

            def gone():
                if getattr(self, "_vtabs_hiding", False) and self._vtabs_floating:
                    self.vtab_panel.hide()
                self._vtabs_hiding = False
            self._vtabs_slide(-self.vtab_panel.width(), gone)

    def _apply_toolbar(self):
        """Put the toolbar's buttons where the settings say (see toolbar.py)."""
        from .toolbar import FIXED, ToolbarLayout, ToolbarMover
        cfg = self.app.config
        by_key = {key: act for key, act, _anchor in self._nav_items}
        self.toolbar_layout = ToolbarLayout.from_config(cfg, list(by_key))
        # the button of an extension that is off is not shown; its place and
        # the user's own choice (toolbar_hidden) stay as they are (1.1.20)
        from . import ikeextensions
        self.toolbar_layout.hidden |= ikeextensions.toolbar_keys_off(cfg)
        if getattr(self, "toolbar_mover", None) is None:
            self.toolbar_mover = ToolbarMover(self)
        # Back, Forward, Home, Reload: fixed place, can only be shown or hidden
        hidden = cfg["toolbar_hidden"] if isinstance(cfg["toolbar_hidden"], list) else []
        fixed = dict(zip(FIXED, (self.act_back, self.act_fwd, self.act_home, self.act_reload)))
        for key, act in fixed.items():
            act.setVisible(key not in hidden)
        self.home_sep_act.setVisible(any(key not in hidden for key in fixed))
        self._fit_urlbar(place=True)        # puts the buttons that fit in place
        QTimer.singleShot(0, self.toolbar_mover.refresh)

    def _place_toolbar_buttons(self):
        """Make the toolbar hold exactly the buttons to show that fit, in order."""
        from .toolbar import LEFT, RIGHT
        nav, layout, spilled = self.nav, self.toolbar_layout, self.toolbar_spilled
        by_key = {key: act for key, act, _anchor in self._nav_items}
        want_left = [by_key[k] for k in layout.shown(LEFT) if k not in spilled]
        want_right = [by_key[k] for k in layout.shown(RIGHT) if k not in spilled]
        movable = set(by_key.values())
        actions = nav.actions()
        split = actions.index(self.urlbar_act)
        have_left = [a for a in actions[:split] if a in movable]
        have_right = [a for a in actions[split:] if a in movable]
        if have_left != want_left or have_right != want_right:
            nav.setUpdatesEnabled(False)
            try:
                for act in have_left + have_right:
                    nav.removeAction(act)
                for act in want_left:
                    nav.insertAction(self.space_left_act, act)
                for act in want_right:
                    nav.insertAction(self.more_act, act)
            finally:
                nav.setUpdatesEnabled(True)
        # the toolbar builds a new button whenever an action is inserted
        for key, act in by_key.items():
            if act in want_left or act in want_right:
                button = nav.widgetForAction(act)
                self.toolbar_mover.attach(key, button)
                if button is not None:
                    self._tool_widths[key] = button.sizeHint().width() + 2
        btn = nav.widgetForAction(self.act_dark)
        if isinstance(btn, QToolButton):
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            if not btn.property("ikeMenuClickConnected"):
                btn.clicked.connect(btn.showMenu)
                btn.setProperty("ikeMenuClickConnected", True)
        # what did not fit is listed under the » button
        shown = layout.shown(LEFT) + layout.shown(RIGHT)
        self.more_menu.clear()
        for key in shown:
            if key in spilled:
                self.more_menu.addAction(by_key[key])
        self.more_act.setVisible(bool(spilled))

    def toolbar_layout_changed(self):
        """A button was moved: save the arrangement and show it in every window."""
        cfg = self.app.config
        self.toolbar_layout.store(cfg)
        cfg.save()
        QTimer.singleShot(0, self.app.refresh_toolbars)     # not while a button handles its own event

    def toolbar_metrics_changed(self):
        """The style, the font or the screen scale changed: measure the buttons again."""
        self._tool_widths.clear()
        self._fit_urlbar(place=True)

    def toolbar_zone_start(self, zone):
        """x, in the toolbar, where the first button of an empty zone goes."""
        from .toolbar import LEFT
        if zone == LEFT:
            w = self._nav_spacers[0]
            return w.mapTo(self.nav, w.rect().topLeft()).x() + 1
        w = self.nav.widgetForAction(self.win_sep_act)
        if w is not None and w.isVisible():
            return w.mapTo(self.nav, w.rect().topLeft()).x() - 2
        return self.nav.width() - 4

    def toolbar_hint(self, on):
        """Tell in the status bar that a button is ready to be moved."""
        bar = self.statusBar()
        if on:
            bar.showMessage(T("Move button to a new position"))
            bar.show()
        elif bar.currentMessage() == T("Move button to a new position"):
            self._hide_status()

    def customise_toolbar(self, on=True):
        """Enter or leave the mode in which the toolbar buttons are arranged."""
        on = bool(on) and not self._fullscreen_page
        self.custom_bar.setVisible(on)
        self.act_customise_done.setEnabled(on)
        self.toolbar_mover.set_customising(on)

    def reset_toolbar(self):
        """Back to the buttons, sides and order of a new installation."""
        from .config import DEFAULTS, TOOLBAR_ITEMS
        from .toolbar import default_layout
        cfg = self.app.config
        first = default_layout(self.toolbar_layout.keys, DEFAULTS, TOOLBAR_ITEMS)
        first.store(cfg)
        cfg["toolbar_hidden"] = [key for key, hide in TOOLBAR_ITEMS if hide]
        cfg.save()
        self.app.refresh_toolbars()

    # ------------------------------------------------------------------
    # window without the system title bar
    # ------------------------------------------------------------------
    EDGE = 5

    WINDOW_BUTTON_SCALE = 1.2         # the window buttons, a little larger than the toolbar icons

    def _build_window_buttons(self, toolbar):
        SP = QStyle.StandardPixmap
        # 1.1.16: a fixed separator, then the menu, fixed right before the window
        # buttons; both stay with the system's title bar, where the menu is last
        self.win_sep_act = toolbar.addSeparator()
        self.menu_act = toolbar.addWidget(self.menu_btn)
        self._win_btns = []
        # the window buttons keep the size they had with 20-pixel toolbar icons (1.1.6 made those 24)
        side = round(20 * self.WINDOW_BUTTON_SCALE)
        for name, fallback, tip, slot in (
                ("window-minimize", SP.SP_TitleBarMinButton, T("Minimize"), self.showMinimized),
                ("window-maximize", SP.SP_TitleBarMaxButton, T("Maximize"), self._toggle_max),
                ("window-close", SP.SP_TitleBarCloseButton, T("Close window"), self.close)):
            if name == "window-close":
                from .closebutton import CloseButtonStyle, WindowCloseButton  # like the tab close button
                b = WindowCloseButton(self, round(CloseButtonStyle.SIZE * self.WINDOW_BUTTON_SCALE))
            else:
                b = WindowButton(self, side, getattr(self.app, "config", None))
                b.setAutoRaise(True)
                b.setIcon(_theme(name, fallback))
                if name == "window-maximize":
                    self._max_btn = b
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self._win_btns.append(toolbar.addWidget(b))
        self._frameless = False
        for w in (toolbar, self.menuBar()):
            w.installEventFilter(self)
        self.setMouseTracking(True)

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _update_max_button(self):
        """Maximized or full screen: the "restore" sign (the diamond of Plasma's
        Breeze, as in Dolphin); a window of its own size: "maximize"."""
        b = getattr(self, "_max_btn", None)
        if b is None:
            return
        big = self.isMaximized() or self.isFullScreen()
        SP = QStyle.StandardPixmap
        b.setIcon(_theme("window-restore", SP.SP_TitleBarNormalButton) if big
                  else _theme("window-maximize", SP.SP_TitleBarMaxButton))
        b.setToolTip(T("Restore") if big else T("Maximize"))

    def _toggle_titlebar(self):
        cfg = self.app.config
        cfg["system_titlebar"] = not cfg["system_titlebar"]
        cfg.save()
        self.app.refresh_windows()

    def _apply_titlebar(self):
        want = not self.app.config["system_titlebar"] and not self.popup
        self.act_titlebar.setChecked(not want)
        for a in self._win_btns:
            a.setVisible(want and not self._fullscreen_page)
        if want != self._frameless:
            self._frameless = want
            visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, want)
            if visible:
                self.show()       # changing the flag hides the window
        # a thin border we own, so the window can still be resized by its edges
        m = self.EDGE if (want and not self.isMaximized() and not self.isFullScreen()) else 0
        self.setContentsMargins(m, 0, m, m)

    def _drag_filter(self, obj, event):
        """Drag the window by empty toolbar / tab bar / menu bar space."""
        if obj is getattr(self, "vtab_edge", None):
            if event.type() in (event.Type.Enter, event.Type.MouseMove):
                self._vtabs_reveal()
            return False
        if not getattr(self, "_frameless", False):
            return False
        t = event.type()
        if t not in (event.Type.MouseButtonPress, event.Type.MouseButtonDblClick):
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = event.position().toPoint()
        if obj is self.tabbar:
            empty = self.tabbar.tabAt(pos) < 0
            if t == event.Type.MouseButtonDblClick:
                return False                      # double click there opens a tab
        elif obj is self.menuBar():
            empty = self.menuBar().actionAt(pos) is None
        elif obj is self.nav:
            child = self.nav.childAt(pos)
            empty = (child is None and self.nav.actionAt(pos) is None) \
                or child in getattr(self, "_nav_spacers", ())
        else:
            return False
        if not empty:
            return False
        if t == event.Type.MouseButtonDblClick:
            self._toggle_max()
            return True
        handle = self.windowHandle()
        return bool(handle and handle.startSystemMove())

    def _edges_at(self, pos):
        if not getattr(self, "_frameless", False) or self.isMaximized() or self.isFullScreen():
            return Qt.Edge(0)
        e = Qt.Edge(0)
        if pos.x() <= self.EDGE:
            e |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - self.EDGE:
            e |= Qt.Edge.RightEdge
        if pos.y() >= self.height() - self.EDGE:
            e |= Qt.Edge.BottomEdge
        return e

    def mouseMoveEvent(self, event):
        e = self._edges_at(event.position().toPoint())
        L, R, Bm = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.BottomEdge
        if e == (L | Bm):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif e == (R | Bm):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif e in (L, R):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif e == Bm:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        e = self._edges_at(event.position().toPoint())
        if e and event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemResize(e)
            return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Chrome Web Store
    # ------------------------------------------------------------------
    def open_web_store(self):
        from .extensions import STORE_HOME
        self.add_tab(STORE_HOME)

    def install_store_extension(self):
        from .extensions import store_id
        v = self.current_view()
        ext = store_id(v.url().toString()) if v else None
        if not ext:
            self.open_web_store()
            return
        cfg = self.app.config
        if not cfg["experimental_extensions"]:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(T("Extensions"))
            box.setText(T("Extension support is experimental: with some engine versions "
                          "switching an extension on closes the browser. If that happens, "
                          "I.K.E. turns the extension off at the next start. Enable it and "
                          "install?"))
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            cfg["experimental_extensions"] = True
            cfg.save()
        self.app._notify(T("Downloading the extension…"))
        self.app.store.install(ext)

    # ------------------------------------------------------------------
    # helpers shared by several features
    # ------------------------------------------------------------------
    def _take_view(self, view):
        """Remove a view from the tab strip without destroying it."""
        if view is self.split:
            self.unsplit()
        i = self.views.index(view)
        was_current = view is self.current_view()
        self.views.pop(i)
        for w, remove in ((self.tabbar, lambda: self.tabbar.removeTab(i)),
                          (self.vtabs, lambda: self.vtabs.takeItem(i))):
            w.blockSignals(True)
            remove()
            w.blockSignals(False)
        self.stack.removeWidget(view)
        if not self.views:
            self.add_tab()
        elif was_current:
            self.set_current(self.views[min(i, len(self.views) - 1)])
        else:
            self.set_current(self.current_view() or self.views[0])
        self._apply_groups()

    def _adopt_view(self, view):
        view.setParent(self)
        self._insert_view(view, len(self.views))
        self._tab_changed(view)
        self.set_current(view)

    # ------------------------------------------------------------------
    # workspaces
    # ------------------------------------------------------------------
    def _update_ws_buttons(self):
        many = len(self.workspaces) > 1
        for b in (self.ws_btn_h, self.ws_btn_v):
            b.setText(self.workspace if many else "")

    def _fill_ws_menu(self, m):
        m.clear()
        for name in self.workspaces:
            a = m.addAction("%s  (%d)" % (name, len(self.workspaces[name])))
            a.setCheckable(True)
            a.setChecked(name == self.workspace)
            a.triggered.connect(lambda _c=False, n=name: self.switch_workspace(n))
        m.addSeparator()
        m.addAction(T("New workspace…"), self.new_workspace)
        m.addAction(T("Rename workspace…"), self.rename_workspace)
        d = m.addAction(T("Delete workspace"), self.delete_workspace)
        d.setEnabled(len(self.workspaces) > 1)

    def _activate_ws(self, name):
        self.unsplit()
        self._ws_current[self.workspace] = self.stack.currentWidget()
        self.workspace = name
        self.views = self.workspaces[name]
        self._rebuild(self.tabbar)
        self._rebuild(self.vtabs)
        self._update_ws_buttons()

    def switch_workspace(self, name):
        if name == self.workspace or name not in self.workspaces:
            return
        self._activate_ws(name)
        if not self.views:
            self.add_tab()
        else:
            cur = self._ws_current.get(name)
            self.set_current(cur if cur in self.views else self.views[0])

    def new_workspace(self, name=None):
        if not name:
            name, ok = QInputDialog.getText(self, T("New workspace"), T("Name:"))
            if not ok:
                return
        name = name.strip()
        if not name or name in self.workspaces:
            return
        self.workspaces[name] = []
        self.switch_workspace(name)

    def rename_workspace(self, name=None):
        if not name:
            name, ok = QInputDialog.getText(self, T("Rename workspace"), T("Name:"),
                                            text=self.workspace)
            if not ok:
                return
        name = name.strip()
        if not name or name in self.workspaces:
            return
        self.workspaces = {(name if k == self.workspace else k): v
                           for k, v in self.workspaces.items()}
        self.workspace = name
        self.views = self.workspaces[name]
        self._update_ws_buttons()

    def delete_workspace(self):
        if len(self.workspaces) < 2:
            return
        old = self.workspace
        other = next(n for n in self.workspaces if n != old)
        doomed = list(self.views)
        self.switch_workspace(other)
        for v in doomed:
            self._destroy_view(v)
        del self.workspaces[old]
        self._ws_current.pop(old, None)
        self._update_ws_buttons()

    def move_to_workspace(self, view, name):
        if name not in self.workspaces or name == self.workspace or view not in self.views:
            return
        self._take_view(view)
        self.workspaces[name].append(view)
        self.stack.addWidget(view)

    # ------------------------------------------------------------------
    # tab groups
    # ------------------------------------------------------------------
    def group_add(self, view, name=None):
        if not name:
            name, ok = QInputDialog.getText(self, T("New tab group"), T("Name:"))
            if not ok:
                return
        name = name.strip()
        if not name:
            return
        if name not in self.groups:
            self.groups[name] = {"color": GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)],
                                 "collapsed": False}
        view.group = name
        members = [v for v in self.views if v.group == name and v is not view]
        if members and view in self.views:
            self.views.remove(view)
            self.views.insert(self.views.index(members[-1]) + 1, view)
            self._rebuild(self.tabbar)
            self._rebuild(self.vtabs)
        else:
            self._tab_changed(view)
            self._apply_groups()

    def group_remove(self, view):
        view.group = None
        self._tab_changed(view)
        self._apply_groups()

    def group_toggle(self, name):
        g = self.groups.get(name)
        if g:
            g["collapsed"] = not g["collapsed"]
            self._apply_groups()

    def group_close(self, name):
        for v in [v for v in self.views if v.group == name]:
            self.close_tab(v)
        self.groups.pop(name, None)

    def _apply_groups(self):
        used = {v.group for v in self.all_views() if v.group}
        for name in [n for n in self.groups if n not in used]:
            del self.groups[name]
        seen = set()
        cur = self.current_view()
        jump = None
        for i, v in enumerate(self.views):
            g = self.groups.get(v.group) if v.group else None
            hidden = bool(g and g.get("collapsed") and v.group in seen)
            if g and v.group not in seen:
                seen.add(v.group)
                first = v
            if hidden and v is cur:
                jump = first
            self.tabbar.setTabVisible(i, not hidden)
            item = self.vtabs.item(i)
            if item:
                item.setHidden(hidden)
        for v in self.views:
            if v.group:
                self._tab_changed(v)
        if jump is not None:
            self.set_current(jump)

    def _tab_menu_extra(self, m, view):
        g = m.addMenu(_theme("tab-duplicate", QStyle.StandardPixmap.SP_DirIcon), T("Tab group"))
        for name in self.groups:
            a = g.addAction(name)
            a.setCheckable(True)
            a.setChecked(view.group == name)
            a.triggered.connect(lambda _c=False, n=name: self.group_add(view, n))
        g.addAction(T("New group…"), lambda: self.group_add(view))
        if view.group:
            g.addSeparator()
            g.addAction(T("Remove from group"), lambda: self.group_remove(view))
            collapsed = self.groups[view.group]["collapsed"]
            g.addAction(T("Expand group") if collapsed else T("Collapse group"),
                        lambda: self.group_toggle(view.group))
            g.addAction(T("Close group"), lambda: self.group_close(view.group))
        if len(self.workspaces) > 1:
            w = m.addMenu(T("Move to workspace"))
            for name in self.workspaces:
                if name != self.workspace:
                    w.addAction(name, lambda n=name: self.move_to_workspace(view, n))
        if not self.private and self.ext_on("containers"):
            c = m.addMenu(T("Reopen in container"))
            c.addAction(T("No container"), lambda: self._reopen_in(view, None))
            for cont in self.app.config["containers"]:
                c.addAction(tab_icon(QIcon(), None, cont["color"]), cont["name"],
                            lambda n=cont["name"]: self._reopen_in(view, n))
        if view is self.split:
            m.addAction(T("Close split view"), self.unsplit)
        elif self.ext_on("split"):
            m.addAction(_theme("view-split-left-right", QStyle.StandardPixmap.SP_ArrowRight),
                        T("Show on the right (split view)"), lambda: self.split_with(view))
        m.addAction(_theme("system-suspend", QStyle.StandardPixmap.SP_MediaPause),
                    T("Suspend tab"), lambda: self._suspend(view))

    # ------------------------------------------------------------------
    # containers / profiles
    # ------------------------------------------------------------------
    def _fill_containers(self):
        m = self.m_containers
        m.clear()
        for cont in self.app.config["containers"]:
            m.addAction(tab_icon(QIcon(), None, cont["color"]), cont["name"],
                        lambda n=cont["name"]: self.add_tab(container=n))
        m.addSeparator()
        m.addAction(T("Manage containers…"), lambda: self.open_settings("privacy"))

    def _reopen_in(self, view, container):
        url = view.pending_url or view.url().toString()
        self.add_tab(url, after=view, container=container, group=view.group)
        self.close_tab(view)

    def _fill_profiles(self):
        from .config import PROFILE
        m = self.m_profiles
        m.clear()
        for name in list_profiles():
            a = m.addAction(name)
            a.setCheckable(True)
            a.setChecked(name == PROFILE)
            a.triggered.connect(lambda _c=False, n=name: self.app.launch_profile(n))
        m.addSeparator()
        m.addAction(T("New profile…"), self._new_profile)

    def _new_profile(self):
        name, ok = QInputDialog.getText(self, T("New profile"),
                                        T("Name (letters, digits, - and _):"))
        name = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_")
        if ok and name:
            self.app.launch_profile(name)

    # ------------------------------------------------------------------
    # split view
    # ------------------------------------------------------------------
    def toggle_split(self):
        if self.split is not None:
            self.unsplit()
            return
        if not self.ext_on("split"):
            return
        cur = self.current_view()
        if cur is None:
            return
        i = self.views.index(cur)
        visible = [v for j, v in enumerate(self.views) if self.tabbar.isTabVisible(j)]
        after = [v for v in visible if self.views.index(v) > i]
        other = after[0] if after else self.add_tab(background=True, after=cur)
        self.split_with(other)

    def split_with(self, view):
        if view is None or view not in self.views or not self.ext_on("split"):
            return
        self.unsplit()
        if self.stack.currentWidget() is view:
            others = [v for v in self.views if v is not view]
            left = others[0] if others else self.add_tab(background=True)
            self.set_current(left)
        if view.pending_url:
            url, view.pending_url = view.pending_url, None
            view.load(QUrl(url))
        self.stack.removeWidget(view)
        self.split_holder.layout().addWidget(view, 1)
        view.show()
        self.split_holder.show()
        self.split = view
        self._split_active = False
        w = max(200, self.content.width() // 2)
        self.content.setSizes([w, w])
        self.split_title.setText(view.title())
        self.act_split.setChecked(True)

    def unsplit(self):
        view = self.split
        if view is None:
            return
        self.split = None
        active, self._split_active = self._split_active, False
        self.split_holder.layout().removeWidget(view)
        self.stack.addWidget(view)
        self.split_holder.hide()
        self.act_split.setChecked(False)
        if active and view in self.views:
            self.set_current(view)

    def _focus_changed(self, _old, new):
        if new is None or self.split is None or self._restoring:
            return
        try:
            if new is self.split or self.split.isAncestorOf(new):
                if not self._split_active:
                    self.set_current(self.split)
            elif self._split_active:
                cur = self.stack.currentWidget()
                if cur is not None and (cur is new or cur.isAncestorOf(new)):
                    self.set_current(cur)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # suspension of inactive tabs
    # ------------------------------------------------------------------
    def _suspend(self, view):
        if (view is self.stack.currentWidget() or view is self.split or view.sleeping
                or view.pending_url or getattr(view, "loading", False)):
            return False
        page = view.page()
        if page.recentlyAudible() or view.url().scheme() not in ("http", "https", "file"):
            return False
        try:
            page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
        except Exception:
            return False
        if page.lifecycleState() != QWebEnginePage.LifecycleState.Discarded:
            return False
        view.sleeping = True
        self._tab_changed(view)
        return True

    def sleep_inactive(self, minutes, force=False):
        now = time.time()
        n = 0
        for v in self.all_views():
            if force or now - v.last_active >= minutes * 60:
                n += self.sleep_view(v)
        return n

    def sleep_view(self, v):
        """Suspend one tab (of any workspace) if it may be; True when it was."""
        if v in self.views:
            return bool(self._suspend(v))
        # a tab of another workspace: the same checks as _suspend (1.1.18,
        # independent review: one playing sound or loading was suspended too)
        if v.sleeping or v.pending_url or getattr(v, "loading", False):
            return False
        try:
            page = v.page()
            if page.recentlyAudible() or v.url().scheme() not in ("http", "https", "file"):
                return False
            page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
            v.sleeping = True
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # reader mode / translation / floating video
    # ------------------------------------------------------------------
    def search_tabs(self):
        TabSearch(self).exec()

    def toggle_reader(self):
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https", "file"):
            return
        if v.reader:
            v.reload()
            return
        src = (RES_DIR / "reader.js").read_text("utf-8")
        from . import polish
        from .webview import READER_PREFIX
        cfg = self.app.config
        prefs = {"theme": cfg["reader_theme"], "size": cfg["reader_size"], "tools": polish.part("reader_tools"),
                 "prefix": READER_PREFIX,
                 "labels": {"smaller": T("Zoom out"), "larger": T("Zoom in"), "light": T("Light"),
                            "sepia": T("Sepia"), "dark": T("Dark"), "minutes": T("%d min read")}}
        src = "var IKE_READER = %s;\n%s" % (json.dumps(prefs), src)

        def done(ok):
            if ok:
                v.reader = True
            else:
                self.app._notify(T("No article text was found on this page."))
        # in I.K.E.'s own world: the page's scripts do not see the settings
        v.page().runJavaScript(src, 1, done)

    def translate_page(self):
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https") or not self.ext_on("translate"):
            return
        cfg = self.app.config
        if not cfg["translate_confirmed"]:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(T("Translate page"))
            box.setText(T("I.K.E. has no built-in translator. The page address will be sent to "
                          "an external translation service (Google Translate by default; you "
                          "can change it in the settings). Continue?"))
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            cfg["translate_confirmed"] = True
            cfg.save()
        target = (cfg["translate_url"].replace("{lang}", i18n.current())
                  .replace("{url}", quote(v.url().toString(), safe="")))
        v.load(QUrl(target))

    def float_video(self):
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https", "file") or not self.ext_on("pip"):
            return

        def found(has_video):
            if not has_video:
                self.app._notify(T("No video was found on this page."))
                return
            self._take_view(v)
            win = FloatingVideo(self, v)
            self._floating.append(win)
            win.destroyed.connect(lambda _o=None, w=win: self._floating.remove(w)
                                  if w in self._floating else None)
            win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            win.show()
        v.page().runJavaScript("document.querySelector('video')!==null", 0, found)

    def fill_login(self):
        v = self.current_view()
        if v and self.ext_on("passwords"):
            self.app.passwords.fill(v, interactive=True)

    # ------------------------------------------------------------------
    # permissions of the current site
    # ------------------------------------------------------------------
    def site_permissions(self, reset=False):
        global _PERM_LABELS
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https"):
            return []
        from PyQt6.QtWebEngineCore import QWebEnginePermission as P
        if _PERM_LABELS is None:
            PT = P.PermissionType
            _PERM_LABELS = {
                PT.Geolocation: "location", PT.MediaAudioCapture: "microphone",
                PT.MediaVideoCapture: "camera", PT.MediaAudioVideoCapture: "camera and microphone",
                PT.Notifications: "notifications", PT.DesktopVideoCapture: "screen",
                PT.DesktopAudioVideoCapture: "screen and audio",
                PT.ClipboardReadWrite: "clipboard", PT.LocalFontsAccess: "fonts",
            }
        out = []
        try:
            origin = QUrl(v.url().toString(QUrl.UrlFormattingOption.RemovePath
                                           | QUrl.UrlFormattingOption.RemoveQuery
                                           | QUrl.UrlFormattingOption.RemoveFragment))
            for perm in v.page().profile().listPermissionsForOrigin(origin):
                if perm.state() == P.State.Ask:
                    continue
                if reset:
                    perm.reset()
                    continue
                mark = "✓" if perm.state() == P.State.Granted else "✗"
                out.append("%s %s" % (T(_PERM_LABELS.get(perm.permissionType(), "other")), mark))
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------
    # session
    # ------------------------------------------------------------------
    def session_data(self):
        out = []
        for name, views in self.workspaces.items():
            tabs = []
            cur = 0
            active = self._ws_current.get(name) if name != self.workspace else self.current_view()
            for v in views:
                url = v.pending_url or v.url().toString()
                if not url:
                    continue
                if v is active:
                    cur = len(tabs)
                tabs.append({"url": url, "title": v.title() or v.saved_title or "",
                             "group": v.group, "container": v.container})
            out.append({"name": name, "tabs": tabs, "current": cur})
        return {"workspaces": out, "active": self.workspace, "groups": self.groups}

    def restore_session(self, data):
        """Fill a new, empty window from session_data() output."""
        if "workspaces" not in data:            # an older format
            data = {"workspaces": [{"name": self.workspace, "current": data.get("current", 0),
                                    "tabs": [{"url": u} for u in data.get("urls", []) if u]}]}
        lazy = bool(self.app.config["lazy_restore"])
        self.groups = {k: dict(v) for k, v in (data.get("groups") or {}).items()}
        containers = {c["name"] for c in self.app.config["containers"]}
        self._restoring = True
        first = True
        currents = {}
        for ws in data["workspaces"]:
            tabs = [t for t in ws.get("tabs", []) if t.get("url")]
            if not tabs:
                continue
            name = ws.get("name") or T("Main")
            if first:
                self.workspaces = {name: self.views}
                self.workspace = name
                first = False
            else:
                self.workspaces[name] = []
                self._activate_ws(name)
            for t in tabs:
                cont = t.get("container") if t.get("container") in containers else None
                self.add_tab(t["url"], background=True, lazy=True, title=t.get("title"),
                             group=t.get("group"), container=cont)
            currents[name] = min(max(ws.get("current", 0), 0), len(self.views) - 1)
        self._restoring = False
        if first:
            return False
        for name, views in self.workspaces.items():
            self._ws_current[name] = views[currents.get(name, 0)]
        active = data.get("active") if data.get("active") in self.workspaces else self.workspace
        if active != self.workspace:
            self._activate_ws(active)
        cur = self._ws_current[self.workspace]
        if not lazy:
            for v in self.all_views():
                if v.pending_url and v is not cur:
                    url, v.pending_url = v.pending_url, None
                    v.load(QUrl(url))
        self.set_current(cur)
        self._apply_groups()
        self._update_ws_buttons()
        return True


class WindowButton(QToolButton):
    """Minimize / maximize: a tool button whose icon keeps its own size (inside a
    toolbar Qt would draw it at the toolbar's icon size). Under the mouse a soft
    circle in the theme's colour comes in, as the close button's red one (1.1.6)."""

    def __init__(self, parent, side, config=None):
        super().__init__(parent)
        self.setProperty("ike_own_hover", True)      # its own circle (polish.HoverGlides leaves it)
        self._side = side
        from .effects import Glide
        self._glide = Glide(self, config, self.update)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._glide.to(1)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._glide.to(0)

    def _option(self):
        from PyQt6.QtWidgets import QStyleOptionToolButton
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        opt.iconSize = QSize(self._side, self._side)
        return opt

    def sizeHint(self):
        opt = self._option()
        return self.style().sizeFromContents(QStyle.ContentsType.CT_ToolButton, opt, opt.iconSize, self)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        from . import polish
        if not polish.part("window_hover"):
            from PyQt6.QtWidgets import QStylePainter
            p = QStylePainter(self)
            p.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, self._option())
            return
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        level = self._glide.value
        if self.isDown():
            level = 1.4
        if level > 0:
            c = QColor(self.palette().color(QPalette.ColorRole.Highlight))
            c.setAlphaF(min(0.45, 0.22 * level))
            d = min(self.width(), self.height()) - 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF((self.width() - d) / 2, (self.height() - d) / 2, d, d))
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        s = self._side
        self.icon().paint(p, QRect((self.width() - s) // 2, (self.height() - s) // 2, s, s),
                          Qt.AlignmentFlag.AlignCenter, mode)
        p.end()
