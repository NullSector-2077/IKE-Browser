"""Main browser window."""

import os
import re
import time

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import APP_LONG_NAME, APP_NAME, __version__, effects
from .config import LEVEL_NAMES, LEVELS
from .features import WindowFeatures, tab_icon
from .i18n import T
from .shieldpanel import TOOLBAR_SHIELD_GROW, ShieldPanel, shield_icon
from .tabs import AUDIO_ROLE, VTabDelegate
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
        nxt = QToolButton(self)
        nxt.setIcon(icon("go-down", QStyle.StandardPixmap.SP_ArrowDown))
        nxt.setAutoRaise(True)
        self.case = QCheckBox(T("Match case"), self)
        close = QToolButton(self)
        close.setIcon(icon("window-close", QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setAutoRaise(True)
        for w in (self.edit, prev, nxt, self.case, self.info):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(close)
        self.edit.textChanged.connect(lambda _t: self.find())
        self.edit.returnPressed.connect(self.find)
        nxt.clicked.connect(self.find)
        prev.clicked.connect(lambda: self.find(back=True))
        close.clicked.connect(self.close_bar)
        self.hide()

    def open_bar(self):
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
            self.info.setText("%d / %d" % (res.activeMatch(), n) if self.edit.text() else "")
        v.page().findText(self.edit.text(), flags, result)

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
        self.tabbar = QTabBar(self)
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setElideMode(Qt.TextElideMode.ElideRight)
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

        self.vtabs = QListWidget(self)
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
        vplus.clicked.connect(lambda: self.add_tab())
        self.ws_btn_v = self._make_ws_button(self.vtab_panel)
        head = QWidget(self.vtab_panel)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(2)
        hl.addWidget(self.ws_btn_v)
        hl.addStretch(1)
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
        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.htab_row)
        rl.addWidget(self.repair_bar)
        self.content = QSplitter(Qt.Orientation.Horizontal, self)
        self.content.addWidget(self.stack)
        self.content.addWidget(self._build_split_holder())
        self.content.setChildrenCollapsible(False)
        rl.addWidget(self.content, 1)
        rl.addWidget(self.findbar)
        from .loadingline import LoadingLine
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
        tb.setIconSize(QSize(20, 20))
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tb.customContextMenuRequested.connect(self._toolbar_menu)
        self.addToolBar(tb)
        self.nav = tb
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
        for a in (self.act_back, self.act_fwd, self.act_home):
            tb.addAction(a)
        self.home_sep_act = tb.addSeparator()      # fixed: always right after Home, never moved

        def spacer():
            w = QWidget(self)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            return w
        # free room on both sides of the address bar (see _fit_urlbar)
        self._nav_spacers = [spacer(), spacer()]
        self.space_left_act = tb.addWidget(self._nav_spacers[0])
        self.urlbar = UrlBar(self)
        self.urlbar.returnPressed.connect(lambda: self.navigate(self.urlbar.text()))
        self.urlbar_act = tb.addWidget(self.urlbar)

        # Shield: protection level selector, right of the address bar.
        self.shield_btn = QToolButton(self)
        self.shield_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shield_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.shield_btn.clicked.connect(self.shield_btn.showMenu)
        self.shield_btn.setToolTip(T("I.K.E. Shield: choose the protection level"))
        self.shield_menu = QMenu(self)
        self.shield_panel = ShieldPanel(self)
        wa = QWidgetAction(self.shield_menu)
        wa.setDefaultWidget(self.shield_panel)
        self.shield_menu.addAction(wa)
        self.shield_menu.aboutToShow.connect(self.shield_panel.refresh)
        effects.fading(self.shield_menu, self.app.config)
        self.shield_btn.setMenu(self.shield_menu)
        self.shield_act = tb.addWidget(self.shield_btn)

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
        self.act_tb_translate = A(T("Translate page"), self.translate_page, None,
                                  icon(("translate", "crow-translate-tray", "preferences-desktop-locale")),
                                  T("Translate this page through an external web service"))
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
        for a in (self.act_tb_translate, self.act_tb_reader, self.act_tb_shot, self.act_tb_pip,
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
        self.menu_act = tb.addWidget(self.menu_btn)
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
        right = self._win_btns[0]
        self._nav_items = [("shield", self.shield_act, right),
                           ("reload", self.act_reload, right),
                           ("translate", self.act_tb_translate, right),
                           ("reader", self.act_tb_reader, right),
                           ("screenshot", self.act_tb_shot, right),
                           ("pip", self.act_tb_pip, right),
                           ("split", self.act_tb_split, right),
                           ("dark", self.act_dark, right),
                           ("private", self.act_tb_private, right),
                           ("cleansite", self.act_tb_clean, right),
                           ("downloads", self.act_downloads, right),
                           ("menu", self.menu_act, right)]

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
        if v and v.url().scheme() in ("http", "https"):
            return v.url().host().lower()
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
        look = getattr(self, "_cyber", None)
        if look and prefix == "🔊 ":
            # the Cyber theme: a small equaliser on the tab instead of the loudspeaker sign
            from . import cyber
            eq = self._equaliser
            ic = cyber.audio_icon(ic, eq.phase, look["look"].accent, effects.on(self.app.config))
            eq.wake()
            h_prefix = ""
        else:
            h_prefix = prefix
        self.tabbar.setTabText(i, h_prefix + (title if len(title) < 28 else title[:27] + "…"))
        self.tabbar.setTabToolTip(i, tip)
        self.tabbar.setTabIcon(i, ic)
        item = self.vtabs.item(i)
        if item:
            # sound is shown by the speaker button of the row, not in the title
            audio = {"🔇 ": "muted", "🔊 ": "on"}.get(prefix, "")
            item.setText(title if audio else prefix + title)
            item.setData(AUDIO_ROLE, audio)
            item.setToolTip(tip)
            item.setIcon(ic)
        if view is self.current_view():
            self._update_title()

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
        from . import cyber
        cyber.style_preview(prev, self.app.config)
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

    def navigate(self, text):
        url = self.resolve(text)
        if url is None:
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

    def zoom(self, direction):
        v = self.current_view()
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
        self.statusBar().showMessage(T("Zoom: %d%%") % round(v.zoomFactor() * 100), 1500)
        self.statusBar().show()
        QTimer.singleShot(1600, self._hide_status)

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
        if v is not None and getattr(v, "loading", False):
            self.loading_line.set_state(True, getattr(v, "progress", 0))
        else:
            self.loading_line.hide()
        self.sync_urlbar()
        self._update_title()
        self._update_nav()
        self.update_shield()
        self._update_bookbar()
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
        if loading:
            self.act_reload.setIcon(icon("process-stop", SP.SP_BrowserStop))
            self.act_reload.setText(T("Stop"))
        else:
            self.act_reload.setIcon(icon("view-refresh", SP.SP_BrowserReload))
            self.act_reload.setText(T("Reload"))

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
        marked = bool(v) and self.app.storage.is_bookmarked(url.toString())
        self.urlbar.star.setIcon(icon("bookmarks" if marked else "bookmark-new",
                                      SP.SP_DialogApplyButton if marked else SP.SP_DialogOpenButton))
        self.urlbar.star.setToolTip(T("Remove bookmark") if marked else T("Bookmark this page"))

    def _url_changed(self, view):
        if view is self.current_view():
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
            self.tabbar.setTabIcon(i, ic)
            item = self.vtabs.item(i)
            if item:
                item.setIcon(ic)
        if not again:
            self._spin.stop()

    def _load_progress(self, view, percent):
        view.progress = percent
        if view is self.current_view() and getattr(view, "loading", False):
            self.loading_line.set_state(True, percent)

    def _load_finished(self, view, ok):
        self._load_state(view, False)
        if ok and view.url().scheme() == "ike":
            self.app.push_weather(view)
        if ok and not self.private:
            self.app.storage.add_visit(view.url().toString(), view.title())
        if ok:
            view.reader = False
        if view is self.current_view():
            self.update_shield()

    def _hide_status(self):
        self.statusBar().clearMessage()
        self.statusBar().hide()

    def _blocked(self, host):
        if host == self.current_host():
            self.update_shield()
            look = getattr(self, "_cyber", None)
            if look:
                look["pulse"].fire()         # the Cyber theme: the shield pulses once

    def update_shield(self):
        host = self.current_host()
        cfg = self.app.config
        level = cfg.level_for(host) if host else cfg["shield_level"]
        n = self.app.shields.total(host) if host else 0
        self.shield_btn.setIcon(shield_icon(level, grow=TOOLBAR_SHIELD_GROW))
        self.shield_btn.setText(str(n) if n and level != "off" else "")
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
        if st.is_bookmarked(url):
            st.remove_bookmark(url)
        else:
            st.add_bookmark(url, v.title())
        self.app.refresh_windows()
        self.sync_urlbar()

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

    def about_text(self):
        """Help → About: versions, and the state of what protects the user."""
        from PyQt6.QtCore import QT_VERSION_STR
        from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

        from .app import INTERNAL_ERRORS, sandbox_off
        chromium = qWebEngineChromiumVersion()
        try:
            from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
            patched = qWebEngineChromiumSecurityPatchVersion()
            if patched and patched != chromium:
                chromium += ", " + T("security fixes up to %s") % patched
        except ImportError:                      # Qt older than 6.3
            pass
        lines = ["%s: Qt WebEngine %s (Chromium %s)" % (T("Engine"), QT_VERSION_STR, chromium),
                 T("Engine sandbox: OFF (switched off by the environment, or I.K.E. was started as administrator)")
                 if sandbox_off() else T("Engine sandbox: on"),
                 "%s: %s" % (T("Content blocker"), self._engine_about(self.app.blocker)),
                 T("Chrome extensions: not usable with this engine version (enabling one crashes it)"),
                 self._drm_about()]
        if INTERNAL_ERRORS:
            from .config import CACHE_DIR
            lines.append(T("Internal errors this session: %d (details in %s)")
                         % (len(INTERNAL_ERRORS), CACHE_DIR / "errors.log"))
        return "<h2>%s</h2><p>%s %s</p><p>%s</p><p>%s</p>" % (
            APP_LONG_NAME, T("Version"), __version__, "<br>".join(lines),
            T("An independent, privacy-first browser. No telemetry, no accounts, no sponsored content."))

    def show_about(self):
        QMessageBox.about(self, T("About I.K.E."), self.about_text())

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
        width = max(self.URLBAR_LEAST, min(int(self.width() * share), room))
        self.urlbar.setFixedWidth(width)
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
        half = centre - start
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
        for key, act in (("back", self.act_back), ("forward", self.act_fwd), ("home", self.act_home)) \
                + tuple((key, act) for key, act, _anchor in self._nav_items):
            if key in ("shield", "menu"):
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
        if state == "idle":
            self.act_downloads.setIcon(self._dl_icon)
            return
        from .downloadring import ring_icon
        self.act_downloads.setIcon(ring_icon(self._dl_icon, fraction, state == "done"))

    def apply_theme(self, theme):
        """Colour the toolbars and tabs for an interface theme (None = none)."""
        if theme is None and not getattr(self, "_themed", False):
            return                       # "Follow the system": nothing to undo
        from . import cyber, themes
        # The Cyber theme's shapes first, or their removal: taking a style sheet off a
        # widget gives it back the colours it had before, which the theme then replaces.
        cyber.apply(self)
        themes.style_window(self, theme)
        self._themed = theme is not None

    def changeEvent(self, event):
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
