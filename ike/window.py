"""Main browser window."""

import os
import re
import time

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QKeySequence
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import APP_LONG_NAME, APP_NAME, __version__, effects, polish
from .config import LEVEL_NAMES, LEVELS
from .features import WindowFeatures, tab_icon
from .i18n import T
from .shieldpanel import TOOLBAR_SHIELD_GROW, ShieldPanel, shield_icon
from .tabs import AUDIO_ROLE, TabBar, VTabDelegate, VTabList
from .urlbar import _URLISH, UrlBar
from .webview import WebView

NEWTAB = "ike:newtab"
def icon(name, fallback=None):
    from .icons import themed
    return themed(name, fallback)


class FindBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.win = window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(T("Find in page"))
        self.edit.setClearButtonEnabled(True)
        self.edit.setMaximumWidth(360)
        self.info = QLabel(self)
        prev = QToolButton(self)
        prev.setIcon(icon("go-up", QStyle.StandardPixmap.SP_ArrowUp))
        prev.setAutoRaise(True)
        prev.setToolTip(T("Previous match (Shift+Enter)"))
        nxt = QToolButton(self)
        nxt.setIcon(icon("go-down", QStyle.StandardPixmap.SP_ArrowDown))
        nxt.setAutoRaise(True)
        nxt.setToolTip(T("Next match (Enter)"))
        if polish.part("find_pill"):
            # the number of matches in a small pill, in the theme's colours
            self.info.setObjectName("ikeFindCount")
            self.info.setStyleSheet("#ikeFindCount { padding: 1px 9px; border-radius: 9px;"
                                    " background: palette(midlight); color: palette(window-text); }")
            self.info.hide()
        self.case = QCheckBox(T("Match case"), self)
        close = QToolButton(self)
        close.setIcon(icon("window-close", QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setAutoRaise(True)
        for w in (self.edit, prev, nxt, self.case, self.info):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(close)
        self.edit.textChanged.connect(lambda _t: self.find())
        # Enter: the next match; Shift+Enter: the previous one
        self.edit.returnPressed.connect(lambda: self.find(back=bool(
            QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)))
        nxt.clicked.connect(self.find)
        prev.clicked.connect(lambda: self.find(back=True))
        close.clicked.connect(self.close_bar)
        self.hide()

    def open_bar(self):
        if not self.isVisible():
            polish.fade_child(self, self.win.app.config)
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def close_bar(self):
        self.hide()
        v = self.win.current_view()
        if v:
            v.page().findText("")
            v.setFocus()

    def find(self, back=False):
        v = self.win.current_view()
        if not v:
            return
        flags = QWebEnginePage.FindFlag(0)
        if back:
            flags |= QWebEnginePage.FindFlag.FindBackward
        if self.case.isChecked():
            flags |= QWebEnginePage.FindFlag.FindCaseSensitively

        def result(res):
            n = res.numberOfMatches()
            text = self.edit.text()
            if polish.part("find_pill"):
                self.info.setText(T("%d of %d") % (res.activeMatch(), n) if text else "")
                self.info.setVisible(bool(text))
                self._nothing(bool(text) and n == 0)
            else:
                self.info.setText("%d / %d" % (res.activeMatch(), n) if text else "")
        v.page().findText(self.edit.text(), flags, result)

    def _nothing(self, nothing):
        """No match: the field is tinted red, softly, as in other browsers."""
        from PyQt6.QtGui import QColor, QPalette
        if nothing == getattr(self, "_tinted", False):
            return
        self._tinted = nothing
        pal = QPalette(self.palette())
        if nothing:
            base = pal.color(QPalette.ColorRole.Base)
            pal.setColor(QPalette.ColorRole.Base, effects.blend(base, QColor("#e5484d"), 0.22))
        self.edit.setPalette(pal)
        self.edit.setProperty("nothing_found", nothing)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
        else:
            super().keyPressEvent(event)


class BookmarksBar(QToolBar):
    """The bookmarks in a row. Those that do not fit stay out of the row and are
    listed, one under the other, in the menu of a "»" button at the right end."""

    def __init__(self, title, parent):
        super().__init__(title, parent)
        self._marks = []
        self._busy = False
        self._more = QToolButton(self)
        # the » glyph itself, as other browsers show it (an icon theme may map
        # the arrow names to a bookmarks icon)
        self._more.setText("»")
        f = self._more.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 1.3)
            self._more.setFont(f)
        self._more.setToolTip(T("More bookmarks"))
        self._more.setAutoRaise(True)
        self._more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self._menu = QMenu(self._more)
        self._menu.setToolTipsVisible(True)
        self._more.setMenu(self._menu)
        self._more_action = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._reflow)

    def set_marks(self, entries, open_url, hint=""):
        """entries: [(icon, title, url)]. hint: text shown when there are none."""
        self.clear()                     # also removes the "»" button from the row
        self._marks = []
        for icon, title, url in entries:
            a = self.addAction(icon, title[:24])
            a.setToolTip(url)
            a.setData(title)
            a.triggered.connect(lambda _c=False, u=url: open_url(u))
            self._marks.append(a)
        if not entries and hint:
            lab = QLabel("  " + hint, self)
            lab.setEnabled(False)
            self.addWidget(lab)
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)
        self._more_action = self.addWidget(self._more)
        self._more_action.setVisible(False)
        self._timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._busy:
            self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def _reflow(self):
        if self._more_action is None or self._busy:
            return
        self._busy = True
        try:
            gap = max(0, self.layout().spacing())
            widths = []
            for a in self._marks:
                btn = self.widgetForAction(a)
                widths.append((btn.sizeHint().width() if btn is not None else 80) + gap)
            room = self.contentsRect().width() - 8
            if sum(widths) > room:
                room -= self._more.sizeHint().width() + gap
            self._menu.clear()
            used, overflow = 0, False
            for a, wd in zip(self._marks, widths):
                if not overflow and used + wd <= room:
                    used += wd
                    a.setVisible(True)
                    continue
                overflow = True
                a.setVisible(False)
                title = a.data() or a.text()
                item = self._menu.addAction(a.icon(), title if len(title) <= 60 else title[:59] + "…")
                item.setToolTip(a.toolTip())
                item.triggered.connect(a.trigger)
            self._more_action.setVisible(overflow)
        finally:
            self._busy = False


class BrowserWindow(WindowFeatures, QMainWindow):
    def __init__(self, app, private=False, popup=False):
        super().__init__()
        self.app = app
        self.private = private
        self.popup = popup
        self.profile = app.private_profile() if private else app.profile
        self.workspace = T("Main")
        self.workspaces = {self.workspace: []}
        self.views = self.workspaces[self.workspace]   # tabs of the active workspace
        self._ws_current = {}
        self.groups = {}
        self.split = None
        self._split_active = False
        self.closed_tabs = []
        self._fullscreen_page = False
        self._was_maximized = False
        self._devtools = []
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(app.icon)
        self.resize(1280, 840)

        self._build_central()
        self._build_toolbar()
        self._build_menus()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().hide()
        self._init_features()
        self.apply_layout()
        from . import themes
        self.apply_theme(themes.current(app.config))
        app.shields.blocked.connect(self._blocked)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_central(self):
        self.stack = QStackedWidget(self)
        self.tabbar = TabBar(self, self.app.config)
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setIconSize(QSize(16, 16))
        self.tabbar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabbar.currentChanged.connect(self._tabbar_changed)
        self.tabbar.tabCloseRequested.connect(lambda i: self.close_tab(self.views[i]))
        self.tabbar.tabMoved.connect(self._tabbar_moved)
        self.tabbar.customContextMenuRequested.connect(
            lambda pos: self._tab_menu(self.tabbar.tabAt(pos), self.tabbar.mapToGlobal(pos)))
        self.tabbar.installEventFilter(self)

        self.htab_row = QWidget(self)
        row = QHBoxLayout(self.htab_row)
        row.setContentsMargins(4, 2, 4, 0)
        row.setSpacing(2)
        self.ws_btn_h = self._make_ws_button(self.htab_row)
        row.addWidget(self.ws_btn_h)
        row.addWidget(self.tabbar, 1)
        plus = QToolButton(self.htab_row)
        plus.setIcon(icon("tab-new", QStyle.StandardPixmap.SP_FileDialogNewFolder))
        plus.setAutoRaise(True)
        plus.setToolTip(T("New tab"))
        plus.clicked.connect(lambda: self.add_tab())
        row.addWidget(plus)

        self.vtabs = VTabList(self, self.app.config)
        self.vtabs.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.vtabs.setIconSize(QSize(16, 16))
        self.vtabs.setFrameShape(QFrame.Shape.NoFrame)
        self.vtabs.setMouseTracking(True)
        self.vtabs.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.vtabs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.vtabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        delegate = VTabDelegate(self.vtabs, self.app.config)
        delegate.close_requested.connect(
            lambda r: self.close_tab(self.views[r]) if 0 <= r < len(self.views) else None)
        delegate.mute_requested.connect(
            lambda r: self.toggle_mute(self.views[r]) if 0 <= r < len(self.views) else None)
        self.vtabs.setItemDelegate(delegate)
        self.vtabs.currentRowChanged.connect(self._vtabs_changed)
        self.vtabs.model().rowsMoved.connect(self._vtabs_moved)
        self.vtabs.customContextMenuRequested.connect(
            lambda pos: self._tab_menu(self.vtabs.row(self.vtabs.itemAt(pos))
                                       if self.vtabs.itemAt(pos) else -1,
                                       self.vtabs.viewport().mapToGlobal(pos)))
        self.vtabs.viewport().installEventFilter(self)

        self.vtab_panel = QWidget(self)
        vl = QVBoxLayout(self.vtab_panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vplus = QPushButton(icon("tab-new", QStyle.StandardPixmap.SP_FileDialogNewFolder),
                            T("New tab"), self.vtab_panel)
        vplus.setFlat(True)
        vplus.setToolTip(T("New tab"))
        vplus.clicked.connect(lambda: self.add_tab())
        self.vplus = vplus
        self.ws_btn_v = self._make_ws_button(self.vtab_panel)
        head = QWidget(self.vtab_panel)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(2)
        hl.addWidget(self.ws_btn_v)
        hl.addStretch(1)
        self._vhead = hl
        # 1.1.16: only the icons of the tabs, a narrow panel
        self.vicons_btn = QToolButton(head)
        self.vicons_btn.setAutoRaise(True)
        self.vicons_btn.clicked.connect(self._toggle_vtabs_icons)
        hl.addWidget(self.vicons_btn)
        self.vhide_btn = QToolButton(head)
        self.vhide_btn.setAutoRaise(True)
        self.vhide_btn.clicked.connect(self._toggle_vtabs_autohide)
        hl.addWidget(self.vhide_btn)
        vl.addWidget(head)
        vl.addWidget(vplus)
        vl.addWidget(self.vtabs, 1)
        self.vtab_panel.setAutoFillBackground(True)

        self.findbar = FindBar(self)
        from .repair import RepairBar
        self.repair_bar = RepairBar(self)
        from .lookalikebar import LookalikeBar
        self.lookalike_bar = LookalikeBar(self)
        from .securebar import SecureBar
        self.secure_bar = SecureBar(self)
        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.htab_row)
        rl.addWidget(self.repair_bar)
        rl.addWidget(self.lookalike_bar)
        rl.addWidget(self.secure_bar)
        self.content = QSplitter(Qt.Orientation.Horizontal, self)
        self.content.addWidget(self.stack)
        self.content.addWidget(self._build_split_holder())
        self.content.setChildrenCollapsible(False)
        rl.addWidget(self.content, 1)
        rl.addWidget(self.findbar)
        from .loadingline import LoadingLine
        self.chrome_edge = polish.ChromeEdge(self.content)       # a thin line between the bars and the page
        self.toast_pill = polish.Toast(self.content, self.app.config)  # short messages over the page
        self.loading_line = LoadingLine(self.content)
        self.loading_line.config = self.app.config

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.vtab_panel)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        vw = max(120, int(self.app.config["vtabs_width"]))
        self.splitter.setSizes([vw, max(400, 1280 - vw)])
        self.splitter.setChildrenCollapsible(False)
        self.splitter.splitterMoved.connect(self._vtabs_resized)
        self.vtab_panel.setMinimumWidth(120)
        self.vtabs_edge = polish.VTabsEdge(self.vtab_panel)          # its separator line (1.1.19)
        self._build_vtabs_root()

    def _action(self, text, slot=None, shortcut=None, ico=None, tip=None, checkable=False):
        a = QAction(text, self)
        if ico is not None:
            a.setIcon(ico if isinstance(ico, QIcon) else icon(ico))
        if shortcut:
            a.setShortcuts([QKeySequence(s) for s in shortcut] if isinstance(shortcut, (list, tuple))
                           else [QKeySequence(shortcut)])
        if tip:
            a.setStatusTip(tip)
            keys = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            a.setToolTip("%s (%s)" % (tip, keys) if keys else tip)     # what it does, and its key
        a.setCheckable(checkable)
        if slot:
            a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _build_toolbar(self):
        SP = QStyle.StandardPixmap
        tb = QToolBar(T("Navigation"), self)
        tb.setObjectName("nav")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))         # a little larger than Qt's usual 22: easier to see (1.1.6)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tb.customContextMenuRequested.connect(self._toolbar_menu)
        self.addToolBar(tb)
        self.nav = tb
        from .sitetint import SiteTint
        self.site_tint = SiteTint(self)             # the site's colour in the bar (1.1.14)
        self._hover = polish.HoverGlides(tb, self.app.config)   # round hover of the buttons (1.1.9)
        self.act_back = self._action(T("Back"), lambda: self._web(QWebEnginePage.WebAction.Back),
                                     ["Alt+Left"], icon("go-previous", SP.SP_ArrowBack),
                                     T("Go back one page"))
        self.act_fwd = self._action(T("Forward"), lambda: self._web(QWebEnginePage.WebAction.Forward),
                                    ["Alt+Right"], icon("go-next", SP.SP_ArrowForward),
                                    T("Go forward one page"))
        self.act_reload = self._action(T("Reload"), self.reload_or_stop, ["F5", "Ctrl+R"],
                                       icon("view-refresh", SP.SP_BrowserReload),
                                       T("Reload the current page"))
        self.act_home = self._action(T("Home"), self.go_home, ["Alt+Home"],
                                     icon("go-home", SP.SP_DirHomeIcon),
                                     T("Open the home page"))
        for a in (self.act_back, self.act_fwd, self.act_home, self.act_reload):
            tb.addAction(a)
        self.home_sep_act = tb.addSeparator()      # fixed: always right after Reload, never moved (1.1.9)

        def spacer():
            w = QWidget(self)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            return w
        # free room on both sides of the address bar (see _fit_urlbar)
        self._nav_spacers = [spacer(), spacer()]
        self.space_left_act = tb.addWidget(self._nav_spacers[0])
        self.urlbar = UrlBar(self)
        self.urlbar.returnPressed.connect(lambda: self.navigate(self.urlbar.text(), typed=True))
        self.urlbar_act = tb.addWidget(self.urlbar)
        # the lock opens the site information panel (siteinfo.py)
        from .siteinfo import SiteInfoPanel
        self.site_info_menu = QMenu(self)
        self.site_info = SiteInfoPanel(self)
        wa_info = QWidgetAction(self.site_info_menu)
        wa_info.setDefaultWidget(self.site_info)
        self.site_info_menu.addAction(wa_info)
        self.site_info_menu.aboutToShow.connect(self.site_info.refresh)
        effects.fading(self.site_info_menu, self.app.config)
        self.urlbar.lock.triggered.connect(self.show_site_info)

        # the search engine in use, right after the lock: a click lists the installed
        # engines with their own icons, the one chosen becomes the default (1.1.10)
        self.engine_btn = QToolButton(self.urlbar)
        self.engine_btn.setAutoRaise(True)
        self.engine_btn.setIconSize(QSize(16, 16))
        self.engine_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.engine_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.engine_menu = QMenu(self)
        self.engine_menu.aboutToShow.connect(self._fill_engine_menu)
        effects.fading(self.engine_menu, self.app.config)
        self.engine_btn.setMenu(self.engine_menu)
        self.urlbar.set_start_widget(self.engine_btn)
        self.sync_engine()

        # Shield: protection level selector, inside the address bar at its right end (1.1.10;
        # 1.1.9: before the bar). A click opens its panel; no arrow beside it.
        self.shield_btn = QToolButton(self.urlbar)
        self.shield_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shield_btn.setAutoRaise(True)
        self.shield_btn.setIconSize(QSize(20, 20))
        self.shield_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shield_btn.clicked.connect(self.show_shield_menu)
        self.shield_btn.setToolTip(T("I.K.E. Shield: choose the protection level"))
        self.shield_menu = QMenu(self)
        self.shield_panel = ShieldPanel(self)
        # the panel scrolls when it is taller than the room below the shield (1.1.10: with
        # "Advanced controls" open it went past the bottom of the screen)
        from PyQt6.QtWidgets import QScrollArea
        self.shield_scroll = QScrollArea(self)
        self.shield_scroll.setObjectName("ike_shield_scroll")
        self.shield_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.shield_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.shield_scroll.setWidgetResizable(True)
        self.shield_scroll.setWidget(self.shield_panel)
        self.shield_scroll.viewport().setAutoFillBackground(False)   # the menu's own colour behind
        self.shield_panel.setAutoFillBackground(False)
        wa = QWidgetAction(self.shield_menu)
        wa.setDefaultWidget(self.shield_scroll)
        self.shield_wa = wa
        self.shield_menu.addAction(wa)
        self.shield_menu.aboutToShow.connect(self.shield_panel.refresh)
        self.shield_menu.aboutToShow.connect(lambda: self.shield_panel.kinds.grow(self.app.config))
        self.shield_menu.aboutToShow.connect(lambda: self.fit_shield_menu(place=False))
        effects.fading(self.shield_menu, self.app.config)
        self.urlbar.set_end_widget(self.shield_btn)
        # a ring opens once around the shield when it blocks something (polish.py)
        self.shield_pulse = polish.ShieldPulse(self.shield_btn, self.app.config)
        # "+N" when it grows; on the window, as it rises right of the field's end
        self.shield_count = polish.ShieldCount(self.shield_btn, self.app.config, self)

        self.store_btn = QToolButton(self)
        self.store_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.store_btn.setIcon(icon("list-add", SP.SP_DialogApplyButton))
        self.store_btn.setText(T("Install in I.K.E."))
        self.store_btn.setToolTip(T("Install this Chrome Web Store extension in I.K.E."))
        self.store_btn.clicked.connect(self.install_store_extension)
        self.store_act = tb.addWidget(self.store_btn)
        self.store_act.setVisible(False)
        self.space_right_act = tb.addWidget(self._nav_spacers[1])
        A = self._action
        # "Bookmark this page" on the toolbar; "Translate page" is in the address bar (1.1.6)
        self.act_tb_bookmark = A(T("Bookmark this page"), self.toggle_bookmark, None, "bookmark-new",
                                 T("Add or remove this page from bookmarks"))
        self.act_tb_reader = A(T("Reader mode"), self.toggle_reader, None,
                               icon(("view-readermode", "document-preview")),
                               T("Show only the text of the article"))
        self.act_tb_shot = A(T("Screenshot"), self.screenshot, None,
                             icon(("camera-photo", "spectacle")),
                             T("Save a picture of the visible page"))
        self.act_tb_pip = A(T("Video in floating window"), self.float_video, None,
                            icon(("picture-in-picture", "window-duplicate", "media-playback-start")),
                            T("Keep the video of this tab on top of other windows"))
        self.act_tb_split = A(T("Split view"), self.toggle_split, None,
                              icon("view-split-left-right"),
                              T("Show two tabs side by side"))
        self.act_dark = A(T("Dark mode for pages"), None, None, icon("weather-clear-night"),
                          T("Dark mode: everywhere or only on this site"))
        self.act_tb_private = A(T("New private window"),
                                lambda: self.app.new_window(private=True), None,
                                icon(("view-private", "security-high")),
                                T("Open a window that keeps no history or cookies"))
        self.act_tb_clean = A(T("Clear this site's data"), self.clear_site_data, None,
                              icon(("edit-clear-history", "edit-clear-all", "edit-clear")),
                              T("Delete the cookies and stored data of the site in this tab"))
        self.act_downloads = self._action(T("Downloads"), self.app.show_downloads, "Ctrl+J",
                                          icon("download", SP.SP_ArrowDown),
                                          T("Show downloaded files"))
        self._dl_icon = self.act_downloads.icon()
        for a in (self.act_tb_bookmark, self.act_tb_reader, self.act_tb_shot, self.act_tb_pip,
                  self.act_tb_split, self.act_dark, self.act_tb_private, self.act_tb_clean,
                  self.act_downloads):
            tb.addAction(a)
        if self.private:
            lab = QLabel(T("Private"), self)
            lab.setObjectName("privateWindowBadge")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setContentsMargins(10, 3, 10, 3)
            lab.setStyleSheet(
                "#privateWindowBadge {"
                " background: palette(highlight);"
                " color: palette(highlighted-text);"
                " border: 1px solid palette(highlight);"
                " border-radius: 9px;"
                " font-weight: 600;"
                " }")
            tb.addWidget(lab)
        self.menu_btn = QToolButton(self)
        self.menu_btn.setIcon(icon("application-menu", SP.SP_TitleBarMenuButton))
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.menu_btn.clicked.connect(self.menu_btn.showMenu)
        self.menu_btn.setToolTip(T("Menu"))
        # buttons that do not fit in a narrow window (see _fit_urlbar)
        self.more_btn = QToolButton(self)
        self.more_btn.setText("»")
        f = self.more_btn.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 1.3)
            self.more_btn.setFont(f)
        self.more_btn.setToolTip(T("More buttons"))
        self.more_btn.setAutoRaise(True)
        self.more_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_btn.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.more_menu = effects.fading(QMenu(self.more_btn), self.app.config)
        self.more_btn.setMenu(self.more_menu)
        self.more_act = tb.addWidget(self.more_btn)
        self.more_act.setVisible(False)
        self._build_window_buttons(tb)
        self._update_max_button()
        right = self.win_sep_act
        self._nav_items = [("bookmark", self.act_tb_bookmark, right),
                           ("reader", self.act_tb_reader, right),
                           ("screenshot", self.act_tb_shot, right),
                           ("pip", self.act_tb_pip, right),
                           ("split", self.act_tb_split, right),
                           ("dark", self.act_dark, right),
                           ("private", self.act_tb_private, right),
                           ("cleansite", self.act_tb_clean, right),
                           ("downloads", self.act_downloads, right)]

        self.bookbar = BookmarksBar(T("Bookmarks bar"), self)
        self.bookbar.setObjectName("bookmarks")
        self.bookbar.setMovable(False)
        self.bookbar.setIconSize(QSize(16, 16))
        self.bookbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBarBreak()
        self.addToolBar(self.bookbar)
        self._build_customise_bar()

    def _build_customise_bar(self):
        """The strip shown under the toolbar while its buttons are arranged."""
        bar = self.custom_bar = QToolBar(T("Customise toolbar"), self)
        bar.setObjectName("customise")
        bar.setMovable(False)
        bar.toggleViewAction().setVisible(False)
        note = QLabel(T("Drag the buttons to arrange them. Back, Forward and Home stay in place."), bar)
        note.setContentsMargins(8, 0, 8, 0)
        bar.addWidget(note)
        gap = QWidget(bar)
        gap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(gap)
        choose = QToolButton(bar)
        choose.setText(T("Toolbar buttons"))
        choose.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(choose)
        menu.aboutToShow.connect(lambda: self._fill_toolbar_buttons(menu))
        menu.triggered.connect(self._toolbar_button_toggled)
        choose.setMenu(menu)
        bar.addWidget(choose)
        reset = QToolButton(bar)
        reset.setText(T("Reset to default layout"))
        reset.clicked.connect(self.reset_toolbar)
        bar.addWidget(reset)
        done = QToolButton(bar)
        done.setText(T("Done"))
        done.clicked.connect(lambda: self.customise_toolbar(False))
        bar.addWidget(done)
        self.insertToolBar(self.bookbar, bar)
        self.insertToolBarBreak(self.bookbar)
        bar.hide()
        self.act_customise = self._action(T("Customise toolbar…"), lambda: self.customise_toolbar(True), None,
                                          icon(("configure-toolbars", "configure")),
                                          T("Move the toolbar buttons with the mouse"))
        self.act_customise_done = self._action("customise-done", lambda: self.customise_toolbar(False),
                                               ["Escape"])
        self.act_customise_done.setEnabled(False)

    def _build_menus(self):
        A = self._action
        WA = QWebEnginePage.WebAction
        mb = self.menuBar()

        # --- File
        m_file = mb.addMenu(T("&File"))
        m_file.addAction(A(T("New tab"), lambda: self.add_tab(), "Ctrl+T", "tab-new",
                           T("Open a new tab")))
        m_file.addAction(A(T("New window"), lambda: self.app.new_window(), "Ctrl+N", "window-new",
                           T("Open a new window")))
        m_file.addAction(A(T("New private window"), lambda: self.app.new_window(private=True),
                           "Ctrl+Shift+N", "view-private",
                           T("Browse without saving history, cookies or cache")))
        m_file.addSeparator()
        m_file.addAction(A(T("Open file…"), self.open_file, "Ctrl+O", "document-open",
                           T("Open a file from this computer")))
        m_file.addAction(A(T("Save page as…"), lambda: self._web(WA.SavePage), "Ctrl+S",
                           "document-save", T("Save the page to disk")))
        m_file.addAction(A(T("Save as PDF…"), self.save_pdf, None, "application-pdf",
                           T("Export the page as a PDF document")))
        m_file.addAction(A(T("Print…"), self.print_page, "Ctrl+P", "document-print",
                           T("Print the current page")))
        m_file.addAction(A(T("Screenshot…"), self.screenshot, "Ctrl+Shift+S", "camera-photo",
                           T("Save an image of the visible page")))
        m_file.addSeparator()
        m_file.addAction(A(T("Close tab"), lambda: self.close_tab(self.current_view()),
                           "Ctrl+W", "tab-close", T("Close the current tab")))
        m_file.addAction(A(T("Close window"), self.close, "Ctrl+Shift+W", "window-close",
                           T("Close this window")))
        m_file.addAction(A(T("Quit"), self.app.quit, "Ctrl+Q", "application-exit",
                           T("Close every window and quit I.K.E.")))

        # --- Edit
        m_edit = mb.addMenu(T("&Edit"))
        for text, wa, ico in ((T("Undo"), WA.Undo, "edit-undo"), (T("Redo"), WA.Redo, "edit-redo"),
                              (None, None, None),
                              (T("Cut"), WA.Cut, "edit-cut"), (T("Copy"), WA.Copy, "edit-copy"),
                              (T("Paste"), WA.Paste, "edit-paste"),
                              (T("Select all"), WA.SelectAll, "edit-select-all")):
            if text is None:
                m_edit.addSeparator()
                continue
            a = QAction(icon(ico), text, self)
            a.triggered.connect(lambda _c=False, w=wa: self._web(w))
            m_edit.addAction(a)
        m_edit.addSeparator()
        m_edit.addAction(A(T("Find in page…"), self.findbar.open_bar, "Ctrl+F", "edit-find",
                           T("Search for text in the current page")))
        m_edit.addSeparator()
        m_edit.addAction(A(T("Settings…"), lambda: self.open_settings(), "Ctrl+,", "configure",
                           T("Configure I.K.E.")))

        # --- View
        m_view = mb.addMenu(T("&View"))
        self.act_vertical = A(T("Vertical tabs"), self._toggle_vertical, "Ctrl+Shift+E",
                              "view-sidetree", T("Show tabs in a side panel instead of a top bar"),
                              checkable=True)
        self.act_menubar = A(T("Menu bar"), self._toggle_menubar, "Ctrl+M", "show-menu",
                             T("Show or hide the menu bar"), checkable=True)
        self.act_titlebar = A(T("System title bar"), self._toggle_titlebar, None, "window",
                              T("Hide the window title bar to leave more room for pages"),
                              checkable=True)
        self.act_bookbar = A(T("Bookmarks bar"), self._toggle_bookbar, "Ctrl+Shift+B",
                             "bookmark-toolbar",
                             T("Switch between: only on a new tab, always, hidden"))
        for a in (self.act_vertical, self.act_menubar, self.act_bookbar, self.act_titlebar,
                  self.act_customise):
            m_view.addAction(a)
        m_view.addSeparator()
        m_view.addAction(A(T("Zoom in"), lambda: self.zoom(+1), ["Ctrl++", "Ctrl+="], "zoom-in",
                           T("Make the page larger")))
        m_view.addAction(A(T("Zoom out"), lambda: self.zoom(-1), "Ctrl+-", "zoom-out",
                           T("Make the page smaller")))
        m_view.addAction(A(T("Actual size"), lambda: self.zoom(0), "Ctrl+0", "zoom-original",
                           T("Reset the zoom level")))
        m_view.addSeparator()
        self.m_dark = m_view.addMenu(icon("weather-clear-night"), T("Dark mode for pages"))
        self.act_dark_all = QAction(T("On everywhere"), self, checkable=True)
        self.act_dark_all.triggered.connect(lambda on: self._set_dark("on" if on else "off"))
        self.act_dark_site = QAction(T("On for this site"), self, checkable=True)
        self.act_dark_site.triggered.connect(
            lambda on: self.app.set_site_dark(self.current_host(), on))
        self.m_dark.addAction(self.act_dark_all)
        self.m_dark.addAction(self.act_dark_site)
        self.m_dark.aboutToShow.connect(self._fill_dark_menu)
        self.act_dark.setMenu(self.m_dark)
        m_view.addAction(A(T("Full screen"), self.toggle_fullscreen, "F11", "view-fullscreen",
                           T("Show the page on the whole screen")))
        m_view.addSeparator()
        m_view.addAction(A(T("Page source"), self.view_source, "Ctrl+U", "text-html",
                           T("Show the HTML source of the page")))
        m_view.addAction(A(T("Developer tools"), lambda: self.open_devtools(), ["F12", "Ctrl+Shift+I"],
                           "tools-report-bug", T("Inspect the page, network and console")))

        # --- History
        self.m_history = mb.addMenu(T("Hi&story"))
        self.m_history.aboutToShow.connect(self._fill_history)
        self.act_reopen = A(T("Reopen closed tab"), self.reopen_tab, "Ctrl+Shift+T", "edit-undo",
                            T("Restore the tab closed most recently"))
        self.act_history = A(T("Show all history"), self.app.show_history, "Ctrl+H",
                             "view-history", T("Browse and search visited pages"))
        self.act_clear = A(T("Clear browsing data…"), self.app.show_clear_data, "Ctrl+Shift+Del",
                           "edit-clear-history", T("Delete history, cookies and cache"))

        # --- Bookmarks
        self.m_bookmarks = mb.addMenu(T("&Bookmarks"))
        self.m_bookmarks.aboutToShow.connect(self._fill_bookmarks)
        self.act_bookmark = A(T("Bookmark this page"), self.toggle_bookmark, "Ctrl+D",
                              "bookmark-new", T("Add or remove this page from bookmarks"))
        self.act_bookmarks = A(T("Manage bookmarks"), self.app.show_bookmarks, "Ctrl+Shift+O",
                               "bookmarks-organize", T("Edit, import and export bookmarks"))

        # --- Tools
        m_tools = mb.addMenu(T("&Tools"))
        self.act_command_bar = A(T("Command bar…"), self.open_command_bar, "F2", "system-search",
                                 T("Commands, open tabs, bookmarks, history and settings in one search"))
        m_tools.addAction(self.act_command_bar)
        m_tools.addAction(self.act_downloads)
        m_tools.addAction(A(T("Components and extensions"), lambda: self.open_settings("components"),
                            "Ctrl+Shift+A", "plugins",
                            T("Manage the ad blocker, cookie banners, dark mode and extensions")))
        self.m_level = m_tools.addMenu(shield_icon("balanced", 16), T("Protection level"))
        self.level_group = QActionGroup(self)
        for lv in LEVELS:
            a = QAction(shield_icon(lv, 16), T(LEVEL_NAMES[lv]), self, checkable=True)
            a.setData(lv)
            a.setStatusTip(T(ShieldPanel.HINTS[lv]))
            a.triggered.connect(lambda _c=False, k=lv: self._set_global_level(k))
            self.level_group.addAction(a)
            self.m_level.addAction(a)
        m_tools.addAction(A(T("Update filter lists now"), self.app.update_now, None,
                            "view-refresh", T("Download the latest blocking rules")))
        m_tools.addSeparator()
        m_tools.addAction(A(T("Mute tab"), self.toggle_mute, "Ctrl+Shift+M", "audio-volume-muted",
                            T("Mute or unmute the sound of the current tab")))
        m_tools.addAction(A(T("Search engines…"), lambda: self.open_settings("search"), None,
                            "edit-find", T("Choose and add search engines")))

        # --- Help
        m_help = mb.addMenu(T("&Help"))
        m_help.addAction(A(T("Keyboard shortcuts"), self.show_shortcuts, "F1",
                           "preferences-desktop-keyboard", T("List the keyboard shortcuts")))
        m_help.addAction(A(T("About I.K.E."), self.show_about, None, self.app.icon,
                           T("Version and component information")))
        about_qt = QAction(T("About Qt"), self)
        about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self))
        m_help.addAction(about_qt)

        self._build_feature_menus(m_file, m_view, m_tools)
        for m in (m_file, m_edit, m_view, self.m_history, self.m_bookmarks, m_tools, m_help):
            m.setToolTipsVisible(True)

        # Hamburger menu mirrors the menu bar.
        burger = QMenu(self)
        burger.setToolTipsVisible(True)
        for a in m_file.actions()[:3]:
            burger.addAction(a)
        burger.addSeparator()
        for m in (m_file, m_edit, m_view, self.m_history, self.m_bookmarks, m_tools, m_help):
            burger.addMenu(m)
        burger.addSeparator()
        burger.addAction(m_edit.actions()[-1])
        burger.addAction(m_file.actions()[-1])
        self.menu_btn.setMenu(effects.fading(burger, self.app.config))

        # Extra shortcuts without a menu entry.
        A("focus-url", self._focus_url, ["Ctrl+L", "Alt+D", "F6"])
        A("next-tab", lambda: self._cycle(1), ["Ctrl+Tab", "Ctrl+PgDown"])
        A("prev-tab", lambda: self._cycle(-1), ["Ctrl+Shift+Tab", "Ctrl+PgUp"])
        A("hard-reload", lambda: self._web(WA.ReloadAndBypassCache), ["Ctrl+Shift+R", "Ctrl+F5"])
        # Escape is only claimed while a page is full screen, so sites keep it.
        self.act_escape = A("exit-fullscreen", self._escape, ["Escape"])
        self.act_escape.setEnabled(False)
        for n in range(1, 10):
            A("tab-%d" % n, lambda _c=False, i=n: self._goto_tab(i), "Alt+%d" % n)

    # ------------------------------------------------------------------
    # layout / state
    # ------------------------------------------------------------------
    def apply_layout(self):
        """Apply configuration-dependent UI state."""
        cfg = self.app.config
        vertical = cfg["tabs_position"] == "vertical"
        chrome = not self._fullscreen_page and not self.popup
        self._apply_vtabs(vertical and chrome)
        self.htab_row.setVisible(not vertical and chrome)
        self.menuBar().setVisible(bool(cfg["show_menubar"]) and chrome)
        self._apply_toolbar()
        if not chrome and self.toolbar_mover.customising:
            self.customise_toolbar(False)
        self.act_store.setVisible(bool(cfg["experimental_extensions"]))
        self.nav.setVisible(not self._fullscreen_page)
        self.act_escape.setEnabled(self._fullscreen_page)
        self._apply_titlebar()
        self.act_vertical.setChecked(vertical)
        self.act_menubar.setChecked(bool(cfg["show_menubar"]))
        self.act_bookbar.setText(T("Bookmarks bar") + ": " + T(
            {"always": "always", "newtab": "only on a new tab", "never": "hidden"}[
                cfg["bookmarks_bar"] if cfg["bookmarks_bar"] in ("always", "newtab", "never")
                else "newtab"]))
        for a in self.level_group.actions():
            a.setChecked(a.data() == cfg["shield_level"])
        self._fill_bookbar()
        self._update_bookbar()
        self.update_shield()

    def _update_bookbar(self):
        """Show the bookmarks bar according to its mode and the current tab."""
        mode = self.app.config["bookmarks_bar"]
        chrome = not self._fullscreen_page and not self.popup
        if mode == "always":
            want = True
        elif mode == "newtab":
            v = self.current_view()
            url = (v.pending_url or v.url().toString()) if v else ""
            want = url in ("", NEWTAB) and not getattr(v, "loading", False) or url == NEWTAB
        else:
            want = False
        if self.bookbar.isVisible() != (want and chrome):
            self.bookbar.setVisible(want and chrome)

    def _toggle_vertical(self):
        cfg = self.app.config
        cfg["tabs_position"] = "horizontal" if cfg["tabs_position"] == "vertical" else "vertical"
        cfg.save()
        self.app.refresh_windows()

    def _toggle_menubar(self):
        cfg = self.app.config
        cfg["show_menubar"] = not cfg["show_menubar"]
        cfg.save()
        self.app.refresh_windows()

    def _toggle_bookbar(self):
        cfg = self.app.config
        order = ["newtab", "always", "never"]
        cur = cfg["bookmarks_bar"] if cfg["bookmarks_bar"] in order else "newtab"
        cfg["bookmarks_bar"] = order[(order.index(cur) + 1) % 3]
        cfg.save()
        self.app.refresh_windows()
        self.app._notify(self.act_bookbar.text())

    def _set_dark(self, mode):
        self.app.set_dark_mode(mode, self)

    @staticmethod
    def _engine_about(blocker):
        if not blocker.native:
            return T("basic (the I.K.E. AdBlock engine could not be loaded)")
        try:
            import adblock
            name = "I.K.E. AdBlock — " + adblock.BACKEND
        except Exception:
            name = "adblock-rust"
        return name + "<br>" + T("Engine errors this session (let through unfiltered): %d") % blocker.errors

    @staticmethod
    def _drm_about():
        from .drm import status
        st = status()
        if not st["path"]:
            return T("DRM video (Widevine): not installed — Netflix and similar services will not play")
        origin = T("installed by I.K.E.") if st["source"] == "ike" else T("system package")
        text = T("DRM video (Widevine): %s, %s") % (st["version"] or "?", origin)
        if not os.environ.get("IKE_WIDEVINE"):
            text += " — " + T("restart I.K.E. to use it")
        return text

    def _fill_dark_menu(self):
        cfg = self.app.config
        v = self.current_view()
        web = bool(v) and v.url().scheme() in ("http", "https", "file")
        host = self.current_host()
        self.act_dark_all.setChecked(cfg["dark_mode"] == "on")
        self.act_dark_site.setEnabled(web and bool(host))
        self.act_dark_site.setChecked(web and self.app.shields.dark_for(host))

    def _set_global_level(self, level):
        cfg = self.app.config
        cfg["shield_level"] = level
        cfg.save()
        self.app.shields.apply_settings()
        self.app.refresh_windows()
        v = self.current_view()
        if v:
            v.reload()

    # ------------------------------------------------------------------
    # tabs
    # ------------------------------------------------------------------
    def current_view(self):
        if self.split is not None and self._split_active:
            return self.split
        w = self.stack.currentWidget()
        return w if isinstance(w, WebView) else None

    def all_views(self):
        return [v for views in self.workspaces.values() for v in views]

    def view_of(self, page):
        for v in self.all_views():
            if v.page() is page:
                return v
        return None

    def current_host(self):
        v = self.current_view()
        if v:
            url = v.url()                 # asked for every blocked request: once (1.1.18)
            if url.scheme() in ("http", "https"):
                return url.host().lower()
        return ""

    def add_tab(self, url=NEWTAB, background=False, after=None, container=None,
                group=None, lazy=False, title=None):
        if self.private:
            container = None
        profile = self.app.container_profile(container) if container else self.profile
        view = WebView(self, profile)
        view.container = container
        view.group = group if group in self.groups else None
        view.pending_url = None
        view.saved_title = title
        view.sleeping = False
        view.last_icon = QIcon()
        view.reader = False
        view.last_active = time.time()
        view.loading = False
        view.setZoomFactor(self.app.config["default_zoom"])
        index = len(self.views)
        if after in self.views:
            index = self.views.index(after) + 1
        self._insert_view(view, index)

        page = view.page()
        view.titleChanged.connect(lambda _t, v=view: self._tab_changed(v))
        view.iconChanged.connect(lambda ic, v=view: self._icon_changed(v, ic))
        view.urlChanged.connect(lambda _u, v=view: self._url_changed(v))
        view.loadStarted.connect(lambda v=view: self._load_state(v, True))
        view.loadFinished.connect(lambda ok, v=view: self._load_finished(v, ok))
        view.loadProgress.connect(lambda pc, v=view: self._load_progress(v, pc))
        page.windowCloseRequested.connect(lambda v=view: self.close_tab(v))
        page.recentlyAudibleChanged.connect(lambda _a, v=view: self._tab_changed(v))
        if not self.private:
            self.app.desktop.watch_view(view)       # media controls of the desktop
        first = len(self.views) == 1
        text = url if isinstance(url, str) or url is None else url.toString()
        if lazy and text and text != NEWTAB and (self._restoring or (background and not first)):
            view.pending_url = text          # loads when the tab is first shown
        elif url is not None:
            view.load(QUrl(url) if isinstance(url, str) else url)
        if not background or first:
            self.set_current(view)
            if text == NEWTAB and not self._restoring:
                self._focus_url()
        self._tab_changed(view)
        return view

    def _icon_changed(self, view, ic):
        if view.sleeping:
            return                       # keep the icon the tab had when it went to sleep
        # detach from the engine: a plain pixmap copy stays valid whatever the page does
        view.last_icon = QIcon(ic.pixmap(32, 32)) if not ic.isNull() else QIcon()
        self.site_tint.icon_changed(view)
        if not getattr(view, "loading_marked", False):
            view._icon_fade_from = getattr(view, "shown_icon", None)
        self._tab_changed(view)
        if not self.private and not ic.isNull() and view.url().scheme() in ("http", "https"):
            self.app.favicons.store(view.url().toString(), ic)

    def _insert_view(self, view, index):
        """Put an existing view into the active workspace at index."""
        self.views.insert(index, view)
        self.stack.addWidget(view)
        self.tabbar.blockSignals(True)
        self.tabbar.insertTab(index, T("New tab"))
        self.tabbar.blockSignals(False)
        self.vtabs.blockSignals(True)
        self.vtabs.insertItem(index, QListWidgetItem(T("New tab")))
        self.vtabs.blockSignals(False)

    def set_current(self, view):
        if view not in self.views:
            return
        i = self.views.index(view)
        view.last_active = time.time()
        self.app.resources.wake(view)       # a tab frozen for using too much CPU
        if view.pending_url and not self._restoring:
            url, view.pending_url = view.pending_url, None
            view.load(QUrl(url))
        if view.sleeping:
            view.sleeping = False
            try:
                view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            except Exception:
                pass
            self._tab_changed(view)
        old = self.current_view()
        if old is not None and old is not view:
            # idle from now on, not from when it was shown (1.1.18, independent
            # review: a tab looked at for half an hour was suspended at the next
            # check after the user left it)
            old.last_active = time.time()
            from .tabpreview import capture
            capture(old)                    # for the preview shown on its tab
        if view is self.split:
            self._split_active = True
        else:
            self._split_active = False
            self.stack.setCurrentWidget(view)
        for w, setter in ((self.tabbar, self.tabbar.setCurrentIndex),
                          (self.vtabs, self.vtabs.setCurrentRow)):
            w.blockSignals(True)
            setter(i)
            w.blockSignals(False)
        self._current_changed()

    def _tabbar_changed(self, i):
        if 0 <= i < len(self.views):
            self.set_current(self.views[i])

    def _vtabs_changed(self, i):
        if 0 <= i < len(self.views):
            self.set_current(self.views[i])

    def _tabbar_moved(self, src, dst):
        view = self.views.pop(src)
        self.views.insert(dst, view)
        self._rebuild(self.vtabs)

    def _vtabs_moved(self, _p, start, _end, _d, row):
        dst = row if row < start else row - 1
        view = self.views.pop(start)
        self.views.insert(dst, view)
        self._rebuild(self.tabbar)

    def _rebuild(self, widget):
        """Re-sync one tab widget with self.views after a reorder."""
        cur = self.current_view()
        widget.blockSignals(True)
        if widget is self.tabbar:
            while self.tabbar.count():
                self.tabbar.removeTab(0)
            for _ in self.views:
                self.tabbar.addTab("")
        else:
            self.vtabs.clear()
            for _ in self.views:
                self.vtabs.addItem(QListWidgetItem(""))
        widget.blockSignals(False)
        for v in self.views:
            self._tab_changed(v)
        if cur:
            self.set_current(cur)
        self._apply_groups()

    def _tab_changed(self, view):
        if view not in self.views:
            return
        i = self.views.index(view)
        url = view.url().toString()
        title = view.title() or view.saved_title or T("New tab")
        if view.pending_url:
            title = view.saved_title or view.pending_url
        elif url == NEWTAB or not url:
            title = T("New tab")
        prefix = ""
        if view.sleeping or view.pending_url:
            prefix = "💤 "
        elif view.page().isAudioMuted():
            prefix = "🔇 "
        elif view.page().recentlyAudible():
            prefix = "🔊 "
        tip = title
        g = self.groups.get(view.group) if view.group else None
        if g:
            tip += "\n" + T("Group: %s") % view.group
            members = [v for v in self.views if v.group == view.group]
            if g.get("collapsed") and members and members[0] is view:
                title = "▸ %s (%d)" % (view.group, len(members))
                prefix = ""
        if view.container:
            tip += "\n" + T("Container: %s") % view.container
        # Never ask the engine for the icon here: on a suspended (discarded) page
        # that call crashes Qt WebEngine. We keep our own copy instead.
        ic = view.last_icon
        if ic.isNull():
            ic = self.app.icon if view.url().scheme() == "ike" else icon(
                "globe", QStyle.StandardPixmap.SP_FileIcon)
        ic = view.tab_icon = tab_icon(ic, g["color"] if g else None, self.app.container_color(view.container))
        if getattr(view, "loading_marked", False):
            ic = effects.loading_icon(ic, getattr(self, "_spin_angle", 45), self.tabbar.palette())
        elif getattr(view, "unseen", False):
            ic = polish.unseen_icon(ic, self.tabbar.palette())
        # a long title fades out at the edge of the tab (tabs.TabBar.set_title)
        self.tabbar.set_title(i, prefix + title)
        self.tabbar.setTabToolTip(i, tip)
        view.audible = prefix == "🔊 "
        item = self.vtabs.item(i)
        if item:
            # sound is shown by the speaker button of the row, not in the title
            audio = {"🔇 ": "muted", "🔊 ": "on"}.get(prefix, "")
            item.setText(title if audio else prefix + title)
            item.setData(AUDIO_ROLE, audio)
            item.setToolTip(tip)
        # a new icon (the site's, or the end of the loading mark) comes in with a short fade
        old = getattr(view, "_icon_fade_from", None)
        view._icon_fade_from = None
        polish.fade_icon(self, id(view), old, ic, self.app.config, lambda icon, v=view: self._show_tab_icon(v, icon))
        self._audio_check()
        if view is self.current_view():
            self._update_title()

    def _show_tab_icon(self, view, ic):
        """Put ic on the tab of view, in both tab bars."""
        if view not in self.views:
            return
        i = self.views.index(view)
        view.shown_icon = ic
        self.tabbar.setTabIcon(i, ic)
        item = self.vtabs.item(i)
        if item:
            item.setIcon(ic)

    def _audio_check(self):
        """The speaker of a tab playing sound pulses gently, only while some tab plays."""
        timer = getattr(self, "_audio_timer", None)
        wanted = (any(getattr(v, "audible", False) for v in self.views)
                  and polish.moving(self.app.config, "audio_pulse"))
        if wanted:
            if timer is None:
                timer = self._audio_timer = QTimer(self)
                timer.timeout.connect(self._audio_tick)
            if not timer.isActive():
                timer.start(polish.AUDIO_TICK)
            return
        if timer is not None and timer.isActive():
            timer.stop()
        if self.tabbar.label_style.audio_phase is not None:
            self.tabbar.label_style.audio_phase = None
            self.vtabs.itemDelegate().audio_phase = None
            self.tabbar.update()
            self.vtabs.viewport().update()

    def _audio_tick(self):
        if not self.isVisible() or not polish.moving(self.app.config, "audio_pulse"):
            self._audio_check()
            return
        phase = (time.monotonic() % polish.AUDIO_PERIOD) / polish.AUDIO_PERIOD
        self.tabbar.label_style.audio_phase = phase
        delegate = self.vtabs.itemDelegate()
        delegate.audio_phase = phase
        for i, v in enumerate(self.views):
            if getattr(v, "audible", False):
                self.tabbar.update(self.tabbar.tabRect(i))
                item = self.vtabs.item(i)
                if item is not None:
                    self.vtabs.viewport().update(self.vtabs.visualItemRect(item))

    def close_tab(self, view):
        if view is None:
            return
        if view not in self.views:
            # tab of a workspace that is not shown
            for views in self.workspaces.values():
                if view in views:
                    views.remove(view)
                    self._destroy_view(view)
            return
        if view is self.split:
            self.unsplit()
        i = self.views.index(view)
        url = view.pending_url or view.url().toString()
        if url and url != NEWTAB and not self.private:
            self.closed_tabs.append(url)
            del self.closed_tabs[:-25]
        was_current = view is self.current_view()
        item = self.vtabs.item(i)
        if item is not None and self.vtabs.isVisible():
            # the row fades out while the list changes at once (1.1.9)
            polish.ghost_out(self.vtabs.viewport(), self.vtabs.visualItemRect(item), self.app.config)
        self.views.pop(i)
        for w, remove in ((self.tabbar, lambda: self.tabbar.removeTab(i)),
                          (self.vtabs, lambda: self.vtabs.takeItem(i))):
            w.blockSignals(True)
            remove()
            w.blockSignals(False)
        self._destroy_view(view)
        if not self.views:
            others = any(self.workspaces[n] for n in self.workspaces)
            if not others and (self.popup or self.private or len(self.app.windows) > 1):
                self.close()
            else:
                self.add_tab()
            return
        if was_current:
            self.set_current(self.views[min(i, len(self.views) - 1)])
        else:
            self.set_current(self.current_view() or self.views[0])
        self._apply_groups()

    def _destroy_view(self, view):
        self.stack.removeWidget(view)
        page = view.page()
        view.setPage(None)
        page.deleteLater()
        view.deleteLater()

    def reopen_tab(self):
        if self.closed_tabs:
            self.add_tab(self.closed_tabs.pop())

    def _cycle(self, step):
        if self.views:
            i = self.views.index(self.current_view()) if self.current_view() else 0
            self.set_current(self.views[(i + step) % len(self.views)])

    def _goto_tab(self, n):
        if not self.views:
            return
        self.set_current(self.views[-1] if n == 9 else self.views[min(n, len(self.views)) - 1])

    def _tab_menu(self, index, pos):
        if index < 0 or index >= len(self.views):
            return
        view = self.views[index]
        m = QMenu(self)
        m.addAction(icon("view-refresh"), T("Reload"), view.reload)
        m.addAction(icon("tab-duplicate"), T("Duplicate tab"),
                    lambda: self.add_tab(view.url(), after=view))
        m.addAction(icon("audio-volume-muted"),
                    T("Unmute tab") if view.page().isAudioMuted() else T("Mute tab"),
                    lambda: self.toggle_mute(view))
        m.addAction(icon("window-new"), T("Move to new window"), lambda: self._detach(view))
        if not self.private:
            self.app.desktop.add_send_menu(m, view.pending_url or view.url().toString())
        self._tab_menu_extra(m, view)
        m.addSeparator()
        m.addAction(icon("tab-close"), T("Close tab"), lambda: self.close_tab(view))
        m.addAction(icon("tab-close-other"), T("Close other tabs"),
                    lambda: [self.close_tab(v) for v in list(self.views) if v is not view])
        m.addAction(self.act_reopen)
        m.addSeparator()
        m.addAction(self.act_vertical)
        m.exec(pos)

    def _detach(self, view):
        url = QUrl(view.pending_url) if view.pending_url else view.url()
        self.close_tab(view)
        self.app.new_window(private=self.private, urls=[url])

    def _tab_preview_event(self, obj, event):
        """Show the picture of a tab when the mouse rests on it (instead of
        its tooltip); True when the event was used."""
        t = event.type()
        prev = getattr(self, "_preview", None)
        if t in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel,
                 QEvent.Type.Hide):
            if prev is not None:
                prev.hide_preview()
            return False
        if t not in (QEvent.Type.ToolTip, QEvent.Type.MouseMove):
            return False
        if t == QEvent.Type.MouseMove and (prev is None or not prev.isVisible()):
            return False
        pos = event.position().toPoint() if t == QEvent.Type.MouseMove else event.pos()
        if obj is self.tabbar:
            i = self.tabbar.tabAt(pos)
        else:
            item = self.vtabs.itemAt(pos)
            i = self.vtabs.row(item) if item else -1
        view = self.views[i] if 0 <= i < len(self.views) else None
        pm = getattr(view, "preview", None)
        if view is None or pm is None or view is self.current_view():
            if prev is not None:
                prev.hide_preview()
            return False
        if prev is None:
            from .tabpreview import TabPreview
            prev = self._preview = TabPreview(self)
        if t == QEvent.Type.MouseMove and prev.index == i:
            return False
        tip = self.tabbar.tabToolTip(i) or view.title()
        prev.show_for(i, pm, tip, obj.mapToGlobal(pos))
        return t == QEvent.Type.ToolTip

    def eventFilter(self, obj, event):
        vtabs = getattr(self, "vtabs", None)       # events can come while the window is built
        if (vtabs is not None and (obj is self.tabbar or obj is vtabs.viewport())
                and self._tab_preview_event(obj, event)):
            return True
        if (event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.MiddleButton
                and obj in (self.tabbar, self.vtabs.viewport())):
            pos = event.position().toPoint()
            if obj is self.tabbar:
                i = self.tabbar.tabAt(pos)
            else:
                item = self.vtabs.itemAt(pos)
                i = self.vtabs.row(item) if item else -1
            if 0 <= i < len(self.views):
                self.close_tab(self.views[i])
                return True
        if self._drag_filter(obj, event):
            return True
        if event.type() == QEvent.Type.MouseButtonDblClick and obj is self.tabbar:
            if self.tabbar.tabAt(event.position().toPoint()) < 0:
                self.add_tab()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def resolve(self, text):
        """Turn address bar input into a URL."""
        text = text.strip()
        if not text:
            return None
        cfg = self.app.config
        if " " in text:
            kw, rest = text.split(" ", 1)
            for e in cfg["search_engines"]:
                if e.get("keyword") and kw.lower() in (e["keyword"].lower(), "!" + e["keyword"].lower()):
                    return QUrl(self.app.shields.search_url(rest.strip(), e["name"]))
        if " " not in text and _URLISH.match(text):
            url = QUrl.fromUserInput(text)
            if url.isValid():
                return url
        return QUrl(self.app.shields.search_url(text))

    def navigate(self, text, typed=False):
        """typed=True: words the user typed or pasted in the address bar. Code
        there ("javascript:...") is never run: a scam that says "paste this in
        the address bar" would run it inside the site that is open, with the
        user's account. Bookmarks (bookmarklets) still run theirs."""
        url = self.resolve(text)
        if url is None:
            return
        if typed and url.scheme().lower() == "javascript":
            self.toast(T("For safety, code written in the address bar is not run."), 5000)
            return
        view = self.current_view() or self.add_tab(None)
        view.load(url)
        view.setFocus()

    def _web(self, action):
        v = self.current_view()
        if v:
            if action in (QWebEnginePage.WebAction.Copy, QWebEnginePage.WebAction.Cut):
                text = v.selectedText()      # read before a cut removes it
                v.page().triggerAction(action)
                if text:
                    v._ensure_copied(text=text)
                return
            v.page().triggerAction(action)

    def reload_or_stop(self):
        v = self.current_view()
        if not v:
            return
        if getattr(v, "loading", False):
            v.stop()
        else:
            v.reload()

    def go_home(self):
        self.navigate(self.app.config["homepage"] or NEWTAB)

    def _escape(self):
        """Esc while a page is full screen: leave full screen and free the mouse."""
        v = self.current_view()
        if v is not None and v.page().mouse_locked:
            v.page().release_pointer()
        if self._fullscreen_page:
            self._web(QWebEnginePage.WebAction.ExitFullScreen)

    def show_exclusive_notice(self, origin, kind):
        """The bubble shown for a few seconds when a site takes the whole screen
        ("fullscreen") or the mouse pointer ("mouse"), as other browsers do."""
        from PyQt6.QtWidgets import QLabel
        label = getattr(self, "_notice", None)
        if label is None:
            label = self._notice = QLabel(self)
            label.setObjectName("ikeExclusiveNotice")
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("#ikeExclusiveNotice { background: rgba(32, 33, 36, 235); color: white;"
                                " border-radius: 10px; padding: 12px 20px; }")
            f = label.font()
            f.setPointSizeF(f.pointSizeF() * 1.15)
            label.setFont(f)
            self._notice_timer = QTimer(self)
            self._notice_timer.setSingleShot(True)
            self._notice_timer.timeout.connect(label.hide)
        if kind == "fullscreen":
            text = T("%s is full screen — press Esc to exit") % origin
        else:
            text = T("%s controls the mouse pointer — press Esc to show the cursor") % origin
        label.setText(text)
        label.kind = kind
        label.adjustSize()
        self._place_notice()
        if not label.isVisible():
            polish.fade_child(label, self.app.config)
        label.show()
        label.raise_()
        QTimer.singleShot(150, self._place_notice)      # after the window went full screen
        self._notice_timer.start(4000)

    def _place_notice(self):
        label = getattr(self, "_notice", None)
        if label is None:
            return
        area = self.centralWidget().geometry() if self.centralWidget() else self.rect()
        label.move(area.x() + (area.width() - label.width()) // 2, area.y() + 24)
        label.raise_()

    def hide_exclusive_notice(self, kind):
        label = getattr(self, "_notice", None)
        if label is not None and getattr(label, "kind", None) == kind:
            label.hide()

    def _focus_url(self):
        self.urlbar.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.urlbar.selectAll()

    def open_file(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Open file"))
        if path:
            self.add_tab(QUrl.fromLocalFile(path))

    def view_source(self):
        v = self.current_view()
        if v and v.url().scheme() in ("http", "https", "file"):
            self.add_tab(QUrl("view-source:" + v.url().toString()), after=v)

    def open_devtools(self, view=None):
        view = view or self.current_view()
        if not view:
            return
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        dev = QWebEngineView()
        dev.setWindowTitle(T("Developer tools") + " - " + view.title())
        dev.setWindowIcon(self.app.icon)
        dev.resize(1000, 640)
        dev.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        view.page().setDevToolsPage(dev.page())
        dev.show()
        self._devtools.append(dev)
        dev.destroyed.connect(lambda _o=None, d=dev: self._devtools.remove(d)
                              if d in self._devtools else None)

    def zoom(self, direction, view=None):
        """direction +1 / -1: one step; 0: the usual zoom. The choice is kept for
        the site (not in a private window): its pages open at that zoom again."""
        v = view or self.current_view()
        if not v:
            return
        steps = [0.3, 0.5, 0.67, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
        if direction == 0:
            v.setZoomFactor(self.app.config["default_zoom"])
        else:
            cur = v.zoomFactor()
            cands = [s for s in steps if (s > cur + 0.01 if direction > 0 else s < cur - 0.01)]
            if cands:
                v.setZoomFactor(cands[0] if direction > 0 else cands[-1])
        self._remember_zoom(v)
        self._zoom_sign()
        self.toast(T("Zoom: %d%%") % round(v.zoomFactor() * 100), 1500)

    def toast(self, text, ms=1800):
        """A short message for the user: in a pill over the page (polish.py), or the status bar."""
        if polish.part("toasts"):
            self.toast_pill.show_text(text, ms)
            return
        self.statusBar().showMessage(text, ms)
        self.statusBar().show()
        QTimer.singleShot(ms + 100, self._hide_status)

    def open_command_bar(self):
        from . import palette
        return palette.open_bar(self)

    def show_site_info(self):
        """The panel of the site in the current tab, under the lock."""
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https"):
            return
        self.site_info_menu.popup(self.urlbar.mapToGlobal(self.urlbar.rect().bottomLeft()))

    def _remember_zoom(self, view):
        cfg = self.app.config
        url = view.url()
        host = url.host().lower()
        if self.private or not host or url.scheme() not in ("http", "https"):
            return
        sites = cfg["site_zoom"] if isinstance(cfg["site_zoom"], dict) else {}
        factor = view.zoomFactor()
        if abs(factor - cfg["default_zoom"]) < 0.005:
            sites.pop(host, None)
        else:
            sites[host] = round(factor, 3)
        cfg["site_zoom"] = sites
        cfg.save()

    def _site_zoom(self, view):
        """A page of another site: the zoom chosen for that site, or the usual one."""
        host = view.url().host().lower()
        if host == getattr(view, "_zoom_host", None):
            return
        view._zoom_host = host
        cfg = self.app.config
        sites = cfg["site_zoom"] if isinstance(cfg["site_zoom"], dict) else {}
        want = sites.get(host, cfg["default_zoom"]) if host else cfg["default_zoom"]
        try:
            want = min(5.0, max(0.25, float(want)))
        except (TypeError, ValueError):
            want = cfg["default_zoom"]
        if abs(view.zoomFactor() - want) > 0.001:
            view.setZoomFactor(want)

    def _zoom_sign(self):
        """The sign in the address field while the page is not at its usual zoom."""
        v = self.current_view()
        usual = self.app.config["default_zoom"]
        factor = v.zoomFactor() if v else usual
        away = polish.part("zoom_mark") and abs(factor - usual) > 0.005
        act = self.urlbar.zoom_act
        if away:
            SP = QStyle.StandardPixmap
            act.setIcon(icon("zoom-in" if factor > usual else "zoom-out",
                             SP.SP_ArrowUp if factor > usual else SP.SP_ArrowDown))
            act.setToolTip("%s\n%s (Ctrl+0)" % (T("Zoom: %d%%") % round(factor * 100), T("Actual size")))
        act.setVisible(away)

    def toggle_mute(self, view=None):
        v = view if isinstance(view, WebView) else self.current_view()
        if v:
            v.page().setAudioMuted(not v.page().isAudioMuted())
            self._tab_changed(v)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if self._was_maximized else self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def set_page_fullscreen(self, on):
        self._fullscreen_page = on
        if on:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
        else:
            self.showMaximized() if self._was_maximized else self.showNormal()
        self.apply_layout()

    # ------------------------------------------------------------------
    # page signals
    # ------------------------------------------------------------------
    def _current_changed(self):
        v = self.current_view()
        if v is not None and getattr(v, "unseen", False):
            v.unseen = False
            self._tab_changed(v)
        if v is not None and getattr(v, "loading", False):
            self.loading_line.set_state(True, getattr(v, "progress", 0))
        else:
            self.loading_line.hide()
        self.sync_urlbar()
        self._update_title()
        self._update_nav()
        self.update_shield()
        self._update_bookbar()
        self.lookalike_bar.show_for(v)
        self.secure_bar.show_for(v)
        self.site_tint.update(v)
        if self.findbar.isVisible():
            self.findbar.close_bar()

    def _update_title(self):
        v = self.current_view()
        title = v.title() if v else ""
        if not title or (v and v.url().toString() == NEWTAB):
            title = T("New tab")
        suffix = APP_NAME + (" (" + T("Private") + ")" if self.private else "")
        self.setWindowTitle("%s — %s" % (title, suffix))

    def _update_nav(self):
        v = self.current_view()
        h = v.history() if v else None
        self.act_back.setEnabled(bool(h and h.canGoBack()))
        self.act_fwd.setEnabled(bool(h and h.canGoForward()))
        loading = bool(v and getattr(v, "loading", False))
        SP = QStyle.StandardPixmap
        new = icon("process-stop", SP.SP_BrowserStop) if loading else icon("view-refresh", SP.SP_BrowserReload)
        self.act_reload.setText(T("Stop") if loading else T("Reload"))
        changed = getattr(self, "_reload_shows_stop", None) not in (None, loading)
        self._reload_shows_stop = loading
        # Reload and Stop change with a short fade; otherwise the icon is simply set again
        polish.fade_icon(self, "reload", self.act_reload.icon() if changed else None, new, self.app.config,
                         self.act_reload.setIcon, ms=140, name="reload_fade")

    def sync_urlbar(self):
        v = self.current_view()
        url = v.url() if v else QUrl()
        text = url.toDisplayString()
        if text == NEWTAB or url.scheme() == "ike":
            text = ""
        if not self.urlbar.hasFocus() or not self.urlbar.isModified():
            self.urlbar.setText(text)
            self.urlbar.setCursorPosition(0)
        SP = QStyle.StandardPixmap
        scheme = url.scheme()
        if scheme == "https":
            self.urlbar.lock.setIcon(icon("object-locked", SP.SP_DialogYesButton))
            self.urlbar.lock.setToolTip(T("Secure connection (HTTPS)"))
        elif scheme == "http":
            self.urlbar.lock.setIcon(icon("security-low", SP.SP_MessageBoxWarning))
            self.urlbar.lock.setToolTip(T("Connection is not encrypted"))
        else:
            self.urlbar.lock.setIcon(icon("globe", SP.SP_FileIcon))
            self.urlbar.lock.setToolTip("")
        from .extensions import store_id
        self.store_act.setVisible(bool(store_id(url.toString()))
                                  and bool(self.app.config["experimental_extensions"]))
        self._zoom_sign()
        marked = bool(v) and self.app.storage.is_bookmarked(url.toString())
        if not polish.popping(self, "star"):
            self.act_tb_bookmark.setIcon(icon("bookmarks" if marked else "bookmark-new",
                                              SP.SP_DialogApplyButton if marked else SP.SP_DialogOpenButton))
        self.act_tb_bookmark.setToolTip(T("Remove bookmark") if marked else T("Bookmark this page"))
        self.urlbar.translate_act.setVisible(scheme in ("http", "https"))
        self.sync_engine()

    def refresh_lookalike(self):
        """Settings changed (Sosia on or off, sites marked as fine, site tint):
        look at the page in front again."""
        from .lookalikebar import check_view
        v = self.current_view()
        if v is not None:
            v.lookalike_host = None
            check_view(self.app.config, v)
            if self.app.config["site_tint"] and getattr(v, "site_colour", None) is None \
                    and not getattr(v, "loading", False):
                self.site_tint.page_loaded(v)
        self.lookalike_bar.show_for(v)
        self.secure_bar.show_for(v)
        self.site_tint.update(v)

    def _url_changed(self, view):
        self._site_zoom(view)
        from .lookalikebar import check_view
        check_view(self.app.config, view)            # Sosia (1.1.14)
        host = view.url().host().lower()
        if getattr(view, "site_colour_host", None) != host:
            view.site_colour_host = host             # another site: its own colour comes with it
            view.site_colour = None
        if view is self.current_view():
            self.lookalike_bar.show_for(view)
            self.secure_bar.show_for(view)
            self.site_tint.update(view)
            self._update_bookbar()
            self.urlbar.setModified(False)
            self.sync_urlbar()
            self._update_nav()
            self.update_shield()
        self._tab_changed(view)

    def _load_state(self, view, loading):
        view.loading = loading
        if not loading:
            view.progress = 100
        self._loading_mark(view, loading)
        if view is self.current_view():
            self._update_nav()
            self._update_bookbar()
            self.loading_line.set_state(loading, getattr(view, "progress", 0))

    # the mark on the tab of a page that is loading (see effects.py)
    MARK_AFTER = 0.25            # seconds: pages that load at once show no mark
    MARK_TURNS_FOR = 30          # seconds: after that the mark stays, but still

    def _loading_mark(self, view, loading):
        view.loading_since = time.monotonic() if loading else None
        if loading:
            timer = getattr(self, "_spin", None)
            if timer is None:
                timer = self._spin = QTimer(self)
                timer.timeout.connect(self._spin_step)
                self._spin_angle = 45
            if not timer.isActive():
                timer.start(effects.SPIN_MS if effects.on(self.app.config) else 250)
        elif getattr(view, "loading_marked", False):
            view.loading_marked = False
            view._icon_fade_from = getattr(view, "shown_icon", None)     # the mark fades into the icon
            self._tab_changed(view)

    def _spin_step(self):
        """Show or turn the mark of the tabs that are loading; stop when there is nothing to do."""
        turning = effects.on(self.app.config)
        now = time.monotonic()
        again = False
        if turning:
            self._spin_angle = (self._spin_angle + effects.SPIN_STEP) % 360
        for i, view in enumerate(self.views):
            since = getattr(view, "loading_since", None)
            if since is None or not getattr(view, "loading", False):
                continue
            marked = getattr(view, "loading_marked", False)
            turns = turning and now - since < self.MARK_TURNS_FOR
            if now - since < self.MARK_AFTER:
                again = True
                continue
            if marked and not turns:
                continue
            again = again or turns
            view.loading_marked = True
            base = getattr(view, "tab_icon", None)
            if base is None:
                continue
            ic = effects.loading_icon(base, self._spin_angle, self.tabbar.palette())
            self._show_tab_icon(view, ic)
        if not again:
            self._spin.stop()

    def _load_progress(self, view, percent):
        view.progress = percent
        if view is self.current_view() and getattr(view, "loading", False):
            self.loading_line.set_state(True, percent)

    def _load_finished(self, view, ok):
        self._load_state(view, False)
        if ok:
            self.site_tint.page_loaded(view)
        if ok and view.url().scheme() == "ike":
            self.app.push_weather(view)
        if ok and not self.private:
            self.app.storage.add_visit(view.url().toString(), view.title())
        if ok:
            view.reader = False
        if (ok and view is not self.current_view() and view in self.views
                and view.url().scheme() in ("http", "https") and polish.part("tab_unseen")):
            view.unseen = True                  # a dot on its tab until it is opened (1.1.9)
            self._tab_changed(view)
        if view is self.current_view():
            self.update_shield()

    def _hide_status(self):
        self.statusBar().clearMessage()
        self.statusBar().hide()

    def sync_engine(self):
        """The icon and the tooltip of the engine button: the default engine."""
        e = self.app.config.engine()
        self.engine_btn.setIcon(self.app.engine_icon(e))
        self.engine_btn.setToolTip("%s: %s" % (T("Default search engine"), e["name"]))

    def _fill_engine_menu(self):
        m = self.engine_menu
        m.clear()
        cfg = self.app.config
        current = cfg.engine()["name"]
        group = QActionGroup(m)
        group.setExclusive(True)
        for e in cfg["search_engines"]:
            a = m.addAction(self.app.engine_icon(e), e["name"].replace("&", "&&"))
            a.setCheckable(True)
            a.setChecked(e["name"] == current)
            if e["name"] == current:          # the one in use stands out, also where the tick is faint
                f = a.font()
                f.setBold(True)
                a.setFont(f)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, name=e["name"]: self.app.set_engine(name))

    def fit_shield_menu(self, place=True):
        """The shield's panel as tall as its content, but never past the bottom of the
        screen: there it scrolls. place: the open menu is resized and kept on the screen."""
        from PyQt6.QtGui import QActionEvent
        panel, scroll, menu = self.shield_panel, self.shield_scroll, self.shield_menu
        panel.adjustSize()
        want = panel.sizeHint()
        screen = self.shield_btn.screen() or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        top = (menu.geometry().top() if menu.isVisible()
               else self.shield_btn.mapToGlobal(QPoint(0, self.shield_btn.height())).y())
        room = area.bottom() - max(area.top(), top) - 16
        height = min(want.height(), max(220, room))
        bar = scroll.verticalScrollBar().sizeHint().width() if height < want.height() else 0
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if bar
                                          else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedSize(want.width() + bar, height)
        # the menu measures its items again (it keeps the old size of the panel otherwise)
        QCoreApplication.sendEvent(menu, QActionEvent(QEvent.Type.ActionChanged, self.shield_wa))
        if place and menu.isVisible():
            size = menu.sizeHint()
            g = menu.geometry()
            x = min(max(area.left(), g.right() + 1 - size.width()), area.right() + 1 - size.width())
            y = min(g.top(), area.bottom() + 1 - size.height())
            menu.setGeometry(x, max(area.top(), y), size.width(), size.height())

    def show_shield_menu(self):
        """The shield's panel, under the shield, its right edge at the shield's."""
        b = self.shield_btn
        menu = self.shield_menu
        self.fit_shield_menu(place=False)
        x = max(0, b.width() - menu.sizeHint().width())
        menu.popup(b.mapToGlobal(QPoint(x, b.height())))

    SHIELD_EVERY_MS = 100

    def _blocked(self, host):
        """Something was blocked on `host`. A page full of ads blocks dozens
        of things in a second: the shield's number is redrawn at most ten
        times a second (each redraw also lays out the address bar again), and
        it always ends on the exact count (1.1.17)."""
        if getattr(self, "_shield_due", False) and self.shield_pulse.resting():
            return               # already on its way, and the ring cannot open again yet (1.1.18)
        if host == self.current_host():
            if not getattr(self, "_shield_due", False):
                self._shield_due = True
                QTimer.singleShot(self.SHIELD_EVERY_MS, self._shield_now)
            self.shield_pulse.fire()

    def _shield_now(self):
        self._shield_due = False
        self.update_shield()

    def update_shield(self):
        host = self.current_host()
        cfg = self.app.config
        level = cfg.level_for(host) if host else cfg["shield_level"]
        n = self.app.shields.total(host) if host else 0
        new = shield_icon(level, grow=TOOLBAR_SHIELD_GROW)
        shown = getattr(self, "_shield_shown", None)
        fading = self.__dict__.get("_ike_icon_fades", {}).get("shield")
        if shown is not None and shown != level:
            # another level: the icon fades into the new one (1.1.9)
            polish.fade_icon(self, "shield", self.shield_btn.icon(), new, cfg, self.shield_btn.setIcon,
                             ms=260, name="shield_fade")
        elif fading is None or fading.state() != fading.State.Running:
            self.shield_btn.setIcon(new)
        self._shield_shown = level
        text = str(n) if n and level != "off" else ""
        if text != self.shield_btn.text():
            self.shield_btn.setText(text)
            self.urlbar.place_end()          # wider or narrower: the text stops before it (1.1.10)
        self.shield_count.count(n if level != "off" else 0, (id(self.current_view()), host))
        self.m_level.setIcon(shield_icon(cfg["shield_level"], 16))
        if self.shield_menu.isVisible():
            self.shield_panel.count.setText(str(n))

    # ------------------------------------------------------------------
    # bookmarks / history menus
    # ------------------------------------------------------------------
    def toggle_bookmark(self):
        v = self.current_view()
        if not v or v.url().scheme() == "ike":
            return
        url = v.url().toString()
        st = self.app.storage
        added = not st.is_bookmarked(url)
        if added:
            st.add_bookmark(url, v.title())
        else:
            st.remove_bookmark(url)
        self.app.refresh_windows()
        self.sync_urlbar()
        if added:          # the star fills with a small pop (1.1.9)
            polish.pop_in(self, "star", self.act_tb_bookmark.icon(), self.app.config, self.act_tb_bookmark.setIcon)

    def site_icon(self, url, fetch=False):
        """Stored icon of the site, or the generic globe."""
        fav = self.app.favicons
        ic = fav.icon(url)
        if ic.isNull():
            if fetch and not self.private:
                fav.fetch(url)
            return icon("globe", QStyle.StandardPixmap.SP_FileIcon)
        return ic

    def _open_action(self, menu, url, title):
        label = (title or url).replace("&", "&&")
        a = menu.addAction(self.site_icon(url), label if len(label) < 60 else label[:59] + "…")
        a.setToolTip(url)
        a.setStatusTip(url)
        a.triggered.connect(lambda _c=False, u=url: self.navigate(u))
        return a

    def _fill_history(self):
        m = self.m_history
        m.clear()
        m.addAction(self.act_back)
        m.addAction(self.act_fwd)
        m.addAction(self.act_home)
        m.addAction(self.act_reopen)
        m.addSeparator()
        m.addAction(self.act_history)
        m.addAction(self.act_clear)
        m.addSeparator()
        for url, title, _last in self.app.storage.history(limit=15):
            self._open_action(m, url, title)

    def _fill_bookmarks(self):
        m = self.m_bookmarks
        m.clear()
        m.addAction(self.act_bookmark)
        m.addAction(self.act_bookmarks)
        m.addAction(self.act_bookbar)
        m.addSeparator()
        for url, title, _folder in self.app.storage.bookmarks()[:40]:
            self._open_action(m, url, title)

    def _fill_bookbar(self):
        if self.app.config["bookmarks_bar"] == "never":
            self.bookbar.set_marks([], self.navigate)
            return
        marks = self.app.storage.bookmarks()
        self.bookbar.set_marks(
            [(self.site_icon(url, fetch=True), title or url, url) for url, title, _folder in marks[:200]],
            self.navigate, T("Bookmarks you add with Ctrl+D appear here"))

    # ------------------------------------------------------------------
    # file actions
    # ------------------------------------------------------------------
    def save_pdf(self):
        v = self.current_view()
        if not v:
            return
        name = re.sub(r"[^\w .-]", "_", v.title() or "page")[:80] + ".pdf"
        path, _f = QFileDialog.getSaveFileName(
            self, T("Save as PDF"), str(self.app.download_dir() / name), "PDF (*.pdf)")
        if path:
            v.page().printToPdf(path)

    def print_page(self):
        v = self.current_view()
        if not v:
            return
        try:
            from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            self.save_pdf()
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec():
            self._printer = printer
            v.print(printer)

    def screenshot(self):
        v = self.current_view()
        if not v:
            return
        pm = v.grab()
        path, _f = QFileDialog.getSaveFileName(
            self, T("Save screenshot"), str(self.app.download_dir() / "screenshot.png"),
            "PNG (*.png)")
        if path:
            pm.save(path if path.lower().endswith(".png") else path + ".png", "PNG")

    def open_settings(self, page=None):
        self.app.show_settings(self, page)

    def show_shortcuts(self):
        rows = []
        seen = set()
        for a in self.actions():
            keys = ", ".join(k.toString(QKeySequence.SequenceFormat.NativeText)
                             for k in a.shortcuts())
            text = a.text().replace("&", "").rstrip("…")
            if keys and text not in seen and " " in text + " " and not re.match(r"^[a-z0-9-]+$", text):
                seen.add(text)
                rows.append("<tr><td>%s&nbsp;&nbsp;</td><td><b>%s</b></td></tr>" % (text, keys))
        rows.append("<tr><td>%s&nbsp;&nbsp;</td><td><b>Ctrl+L</b></td></tr>" % T("Focus the address bar"))
        rows.append("<tr><td>%s&nbsp;&nbsp;</td><td><b>Ctrl+Tab</b></td></tr>" % T("Next tab"))
        box = QMessageBox(self)
        box.setWindowTitle(T("Keyboard shortcuts"))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText("<table>%s</table>" % "".join(rows))
        box.exec()

    def _engine_age(self):
        from . import chromever
        # measured by the security fixes, not by the Chromium base (140 with
        # the fixes of 157 is not "17 versions behind": docs review of 1.1.18)
        behind = chromever.latest(self.app.config) - chromever.security_major()
        if behind <= 0:
            text = T("Engine age: as recent as the current Chrome")
        else:
            text = T("Engine age: %d Chrome versions behind the current one") % behind
        ref = chromever.latest(self.app.config)
        text += "<br>" + T("Current stable Chrome: %d (%s)") % (ref, T(
            "checked with Google's version list") if chromever.latest_checked(self.app.config) else T(
            "estimated from the calendar: Google's version list could not be reached"))
        late = chromever.security_behind(self.app.config)
        if late >= chromever.OUTDATED_AFTER:
            text += "<br><b>" + T("Security fixes: %d Chrome versions behind. Update the system "
                                  "(sudo pacman -Syu).") % late + "</b>"
        return text

    @staticmethod
    def _media_about(media):
        """media: {format: bool} from ike.mediacheck, None while it is asked,
        {} when the engine did not answer."""
        from . import mediacheck
        if media is None:
            return T("Video and audio formats: checking…")
        if not media:
            return T("Video and audio formats: the engine did not answer")
        yes, no = mediacheck.split(media)
        text = T("Plays: %s") % (", ".join(yes) or "—")
        if no:
            text += "<br>" + T("Does not play: %s — this depends on the engine installed on this system; "
                               "videos offered only in these formats will not play") % ", ".join(no)
        return text

    def about_text(self, media=None):
        """Help → About: versions, and the state of what protects the user.
        media: the formats the engine plays (see _media_about); by default
        what this session already knows."""
        if media is None:
            from . import mediacheck
            media = mediacheck.known()
        from PyQt6.QtCore import QT_VERSION_STR
        from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

        from .app import INTERNAL_ERRORS, engine_safety_lines, sandbox_off, site_isolated
        chromium = qWebEngineChromiumVersion()
        try:
            from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
            patched = qWebEngineChromiumSecurityPatchVersion()
            if patched and patched != chromium:
                chromium += ", " + T("security fixes up to %s") % patched
        except ImportError:                      # Qt older than 6.3
            pass
        lines = ["%s: Qt WebEngine %s (Chromium %s)" % (T("Engine"), QT_VERSION_STR, chromium),
                 self._engine_age(),
                 T("Engine sandbox: OFF (switched off by the environment, or I.K.E. was started as administrator)")
                 if sandbox_off() else T("Engine sandbox: on"),
                 T("Site isolation: every site in its own process") if site_isolated()
                 else T("Site isolation: OFF (switched off on request)"),
                 *engine_safety_lines(T),
                 self._media_about(media),
                 "%s: %s" % (T("Content blocker"), self._engine_about(self.app.blocker)),
                 T("Chrome extensions: not usable with this engine version (enabling one crashes it)"),
                 self._drm_about()]
        if INTERNAL_ERRORS:
            from .config import CACHE_DIR
            lines.append(T("Internal errors this session: %d (details in %s)")
                         % (len(INTERNAL_ERRORS), CACHE_DIR / "errors.log"))
        return "<h2>%s</h2><p>%s %s</p><p>%s</p><p>%s</p>%s" % (
            APP_LONG_NAME, T("Version"), __version__, "<br>".join(lines),
            T("An independent, privacy-first browser. No telemetry, no accounts, no sponsored content."),
            self._credits())

    # Who I.K.E. stands on (1.1.14): names and licences, shown in Help -> About.
    # The full list, with the Rust libraries, is docs/THIRD-PARTY.md; the texts
    # are installed in /usr/share/licenses/ike-browser (1.1.18).
    CREDITS = (
        ("adblock-rust (Brave Software)", "MPL-2.0"),
        ("Rust libraries of the AdBlock engine (licences in /usr/share/licenses/ike-browser)",
         "MIT / Apache-2.0 / MPL-2.0 / Unicode-3.0 / Unlicense"),
        ("uBlock Origin scriptlets and filters (Raymond Hill and contributors)", "GPL-3.0"),
        ("EasyList, EasyPrivacy, EasyList Italy (The EasyList authors)", "GPL-3.0 / CC BY-SA 3.0"),
        ("EasyList Cookie List (The EasyList authors)", "CC BY 3.0"),
        ("Malicious URL Blocklist (curben, from abuse.ch URLhaus)", "CC0 1.0 / MIT"),
        ("Dark Reader (Dark Reader Ltd)", "MIT"),
        ("Qt, Qt WebEngine (The Qt Company), Chromium (The Chromium Authors)", "LGPL-3.0 / BSD"),
        ("PyQt6 (Riverbank Computing)", "GPL-3.0"),
        ("Lucide icons", "ISC"),
        ("Phosphor Icons", "MIT"),
        ("Orbitron typeface (The Orbitron Project Authors)", "SIL OFL 1.1"),
    )

    def _credits(self):
        from html import escape
        rows = "<br>".join("%s%s" % (escape(name), (" — " + escape(lic)) if lic else "")
                           for name, lic in self.CREDITS)
        return "<p><b>%s</b><br><small>%s<br>%s</small></p>" % (
            T("Components and licences"), rows,
            T("I.K.E. is free software (GPL-3.0). Every component keeps its own licence."))

    def show_about(self):
        from . import mediacheck
        box = QMessageBox(self)
        box.setWindowTitle(T("About I.K.E."))
        box.setIconPixmap(self.app.icon.pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(self.about_text())
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        self._about_box = box

        def answered(result):
            if self._about_box is box:
                box.setText(self.about_text(result))
        if mediacheck.known() is None:
            mediacheck.ask(self, answered)
        box.exec()
        self._about_box = None

    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_urlbar()

    URLBAR_MIN = 180            # the address bar is not made narrower while buttons can give way
    URLBAR_LEAST = 120          # ... and never narrower than this

    def _fit_urlbar(self, place=False):
        """Address bar: a share of the window width, with free room on both
        sides. Buttons that would leave it less than URLBAR_MIN are moved
        under the » button, the last ones first (see toolbar.spill).
        place=True: the arrangement changed, put the buttons in place anyway."""
        if not hasattr(self, "urlbar") or not hasattr(self, "toolbar_layout"):
            return
        from .toolbar import LEFT, RIGHT, spill
        nav, layout = self.nav, self.toolbar_layout
        movable = {act for _key, act, _anchor in self._nav_items}
        skip = (self.urlbar_act, self.space_left_act, self.space_right_act, self.more_act)
        fixed = 0                                # everything that is neither a movable button nor the bar
        for a in nav.actions():
            if a in skip or a in movable or not a.isVisible():
                continue
            w = nav.widgetForAction(a)
            if w is not None:
                fixed += w.sizeHint().width() + 2
        back = nav.widgetForAction(self.act_back)
        usual = (back.sizeHint().width() if back is not None else nav.iconSize().width() + 14) + 2
        more = self.more_btn.sizeHint().width() + 2
        shown = layout.shown(LEFT) + layout.shown(RIGHT)
        for _attempt in (1, 2):                  # a button is measured once the toolbar has built it
            known = dict(self._tool_widths)
            widths = [(key, known.get(key, usual)) for key in shown]
            space = nav.width() - fixed - 16     # for the buttons and the address bar
            spilled = set()
            if sum(w for _k, w in widths) > space - self.URLBAR_MIN:
                space -= more
                spilled = set(spill(widths, space - self.URLBAR_MIN))
            if place or spilled != self.toolbar_spilled:
                place = False
                self.toolbar_spilled = spilled
                self._place_toolbar_buttons()
                self.toolbar_mover.refresh()
            if self._tool_widths == known:
                break
        room = space - sum(w for key, w in widths if key not in spilled)
        share = max(30, min(100, int(self.app.config["urlbar_width"]))) / 100.0
        # in a very narrow window the fixed buttons (Back to Reload, the shield, the menu, the
        # window buttons) come first: the bar then takes what is left, down to 80 px (1.1.9)
        least = self.URLBAR_LEAST if room >= self.URLBAR_LEAST else max(80, room)
        width = max(least, min(int(self.width() * share), room))
        narrower = width < self.urlbar.width()
        self.urlbar.setFixedWidth(width)
        if narrower:
            # the toolbar may have put its last items under Qt's own overflow button while the
            # bar was still wider (1.1.9: with the shield before the bar it stayed so): look again
            self.nav.layout().invalidate()
        self._urlbar_width, self._urlbar_room = width, room
        QTimer.singleShot(0, self._centre_urlbar)        # after the toolbar's layout

    def _centre_urlbar(self):
        """Put the middle of the address bar in the middle of the window.

        The free room left of the address bar gets the width that does it; the
        room on the right takes the rest. When the buttons on one side leave
        too little room, the address bar is made narrower to stay centred, but
        not under half the window: otherwise it keeps its width and moves only
        as far towards the middle as it can, as before."""
        try:
            left = self._nav_spacers[0]
            ub = self.urlbar
            # Measure the spacer in toolbar coordinates; its parent may be an action wrapper.
            start = left.mapTo(self.nav, QPoint(0, 0)).x()
            centre = self.nav.mapFrom(self, QPoint(self.width() // 2, 0)).x()
        except (RuntimeError, AttributeError):
            return
        room = getattr(self, "_urlbar_room", 0)            # both free rooms and the bar
        # what stands between the left free room and the bar (nothing since 1.1.10), from the
        # sizes of the items (their positions may still be those of the last layout)
        acts = self.nav.actions()
        gap = max(0, self.nav.layout().spacing())
        between = gap
        for a in acts[acts.index(self.space_left_act) + 1:acts.index(self.urlbar_act)]:
            w = self.nav.widgetForAction(a)
            if w is not None and a.isVisible():
                between += w.sizeHint().width() + gap
        half = centre - start - between
        if room <= 0 or half <= 0:
            return
        wanted = getattr(self, "_urlbar_width", ub.width())
        centred = min(wanted, 2 * half, 2 * (room - half))
        width = centred if centred >= min(wanted, self.width() // 2) else wanted
        pad = max(0, min(half - width // 2, room - width))
        if ub.width() != width:
            ub.setFixedWidth(width)
        if left.width() != pad or left.maximumWidth() != pad:
            left.setFixedWidth(pad)

    def _toolbar_menu(self, pos):
        """Right click on the toolbar: choose which buttons it shows, or arrange them."""
        child = self.nav.childAt(pos)
        if child is not None and child not in self._nav_spacers \
                and not isinstance(child, QToolButton):
            return
        m = effects.fading(QMenu(self), self.app.config)
        title = m.addAction(T("Toolbar buttons"))
        title.setEnabled(False)
        m.addSeparator()
        self._fill_toolbar_buttons(m, clear=False)
        m.addSeparator()
        m.addAction(self.act_customise)
        reset = m.addAction(T("Reset to default layout"))
        chosen = m.exec(self.nav.mapToGlobal(pos))
        if chosen is reset:
            self.reset_toolbar()
        elif chosen is not None and chosen.data():
            self._toolbar_button_toggled(chosen)
        m.deleteLater()

    def _fill_toolbar_buttons(self, menu, clear=True):
        """One checkable entry for each button that can be shown or hidden."""
        if clear:
            menu.clear()
        hidden = self.app.config["toolbar_hidden"]
        for key, act in (("back", self.act_back), ("forward", self.act_fwd), ("home", self.act_home),
                         ("reload", self.act_reload)) \
                + tuple((key, act) for key, act, _anchor in self._nav_items):
            if key == "menu":
                continue
            a = menu.addAction(act.icon(), act.text())
            a.setCheckable(True)
            a.setChecked(key not in hidden)
            a.setData(key)

    def _toolbar_button_toggled(self, chosen):
        cfg = self.app.config
        key = chosen.data()
        if not key:
            return
        hidden = [k for k in cfg["toolbar_hidden"] if k != key]
        if not chosen.isChecked():
            hidden.append(key)
        cfg["toolbar_hidden"] = hidden
        cfg.save()
        self.app.refresh_toolbars()

    def clear_site_data(self):
        """Delete cookies and stored data of the site in the current tab."""
        v = self.current_view()
        host = self.current_host()
        if not v or not host or v.url().scheme() not in ("http", "https"):
            return
        from .shields import site_of
        site = site_of(host)
        if QMessageBox.question(
                self, APP_NAME,
                T("Delete the cookies and the data stored by %s? You will be signed out of "
                  "this site.") % site) != QMessageBox.StandardButton.Yes:
            return
        profile = v.page().profile()
        store = profile.cookieStore()
        for cookie in self.app.shields.site_cookies(profile, site):
            store.deleteCookie(cookie)
        v.page().runJavaScript(
            "(async function(){try{localStorage.clear();sessionStorage.clear();}catch(e){}"
            "try{var d=await indexedDB.databases();d.forEach(function(x){indexedDB.deleteDatabase(x.name);});}catch(e){}"
            "try{var k=await caches.keys();await Promise.all(k.map(function(x){return caches.delete(x);}));}catch(e){}"
            "try{var r=await navigator.serviceWorker.getRegistrations();r.forEach(function(x){x.unregister();});}catch(e){}"
            "})();", 0, lambda _r: QTimer.singleShot(300, v.reload) if v in self.views else None)
        self.app._notify(T("Data of %s deleted.") % site)

    def show_download_progress(self, state, fraction=None):
        """state: "idle", "active" (fraction 0..1 or None) or "done"."""
        self._dl_fraction = fraction
        self._download_arrow(state == "active")
        if state == "idle":
            self._dl_state = "idle"
            self.act_downloads.setIcon(self._dl_icon)
            return
        from .downloadring import ring_icon
        was, self._dl_state = getattr(self, "_dl_state", "idle"), state
        if state == "done" and was != "done" and polish.moving(self.app.config, "download_pop"):
            from PyQt6.QtCore import QEasingCurve, QVariantAnimation
            old = getattr(self, "_dl_pop", None)
            if old is not None:
                old.stop()
            anim = self._dl_pop = QVariantAnimation(self)
            anim.setDuration(320)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutBack)
            anim.valueChanged.connect(lambda t: self._dl_state == "done" and self.act_downloads.setIcon(
                ring_icon(self._dl_icon, None, True, pop=float(t))))
            anim.start()
            return
        self.act_downloads.setIcon(ring_icon(self._dl_icon, fraction, state == "done",
                                             bob=getattr(self, "_dl_bob", None) if state == "active" else None))

    def _download_arrow(self, active):
        """While files arrive the arrow of the Downloads button moves gently (polish.py)."""
        timer = getattr(self, "_dl_arrow", None)
        if active and polish.moving(self.app.config, "download_arrow"):
            if timer is None:
                timer = self._dl_arrow = QTimer(self)
                timer.setInterval(80)
                timer.timeout.connect(self._download_arrow_step)
            if not timer.isActive():
                timer.start()
            return
        self._dl_bob = None
        if timer is not None:
            timer.stop()

    def _download_arrow_step(self):
        if getattr(self, "_dl_state", "idle") != "active" or not self.isVisible():
            return
        from .downloadring import ring_icon
        self._dl_bob = (time.monotonic() % 1.2) / 1.2
        self.act_downloads.setIcon(ring_icon(self._dl_icon, getattr(self, "_dl_fraction", None), False,
                                             bob=self._dl_bob))

    def apply_theme(self, theme):
        """Colour the toolbars and tabs for an interface theme (None = none)."""
        if theme is None and not getattr(self, "_themed", False):
            return                       # "Follow the system": nothing to undo
        from . import themes
        themes.style_window(self, theme)
        self._themed = theme is not None

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_max_button()           # the diamond while maximized, the arrow otherwise
        # Follow a change of the desktop theme / colour scheme at once.
        if (event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange)
                and hasattr(self, "shield_panel") and hasattr(self, "level_group")):
            for combo in (self.shield_panel.site_level, self.shield_panel.global_level):
                for i, lv in enumerate(LEVELS):
                    combo.setItemIcon(i, shield_icon(lv, 16))
            for a in self.level_group.actions():
                a.setIcon(shield_icon(a.data(), 16))
            self.update_shield()
            for v in self.all_views():
                if v.url().scheme() == "ike":
                    v.reload()
        super().changeEvent(event)

    def repair_site(self):
        """Start "Repair this site" on the current tab (see repair.py)."""
        view, host = self.current_view(), self.current_host()
        if view is not None and host:
            self.repair_bar.start(view, host)

    def closeEvent(self, event):
        self.repair_bar.cancel()           # nothing half-done is saved
        self.app.window_closing(self)
        for d in list(self._devtools):
            d.close()
        self.unsplit()
        for v in self.all_views():
            page = v.page()
            v.setPage(None)
            page.deleteLater()
        for views in self.workspaces.values():
            views.clear()
        super().closeEvent(event)
