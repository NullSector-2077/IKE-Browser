"""Settings, history, bookmarks, downloads and clear-data dialogs."""

import time
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import (
    DEFAULT_ENGINES,
    DEFAULT_LISTS,
    DEFAULTS,
    DOH_PROVIDERS,
    LEVEL_NAMES,
    LEVELS,
    PERMISSION_KINDS,
    TOOLBAR_ITEMS,
)
from .i18n import T


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0


def _wrapping(box):
    """A check box whose long text wraps instead of widening the page."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    label = QLabel(box.text())
    label.setContentsMargins(4, 1, 0, 0)
    label.setWordWrap(True)
    label.setToolTip(box.toolTip())
    label.mousePressEvent = lambda _e: box.toggle()
    box.setText("")
    lay.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)
    lay.addWidget(label, 1, Qt.AlignmentFlag.AlignTop)
    return w


class SettingsDialog(QDialog):
    PAGES = ["general", "appearance", "newtab", "search", "privacy", "components", "userscripts", "downloads"]

    def __init__(self, app, parent=None, page=None):
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.setWindowTitle(T("Settings") + " — I.K.E.")
        self.resize(1100, 680)       # room for a scroll bar beside the widest page (German)
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QFrame, QScrollArea, QStackedWidget

        from .icons import themed
        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        lay.addLayout(body, 1)
        self.nav = QListWidget(self)
        self.nav.setObjectName("settingsNav")
        self.nav.setIconSize(QSize(22, 22))
        self.nav.setSpacing(2)
        self.nav.setUniformItemSizes(True)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget(self)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        sections = (
            (self._general, T("General"), ("configure", "preferences-system")),
            (self._appearance, T("Appearance"), ("preferences-desktop-theme", "preferences-desktop")),
            (self._newtab_page, T("New tab page"), ("tab-new", "document-new")),
            (self._search, T("Search"), ("edit-find", "system-search")),
            (self._privacy, T("Privacy and protection"), ("security-high", "preferences-security")),
            (self._components, T("Components and extensions"), ("preferences-plugin", "application-x-addon")),
            (self._userscripts, T("User scripts"), ("text-x-script", "application-x-javascript")),
            (self._downloads, T("Downloads"), ("download", "folder-download")),
        )
        widest = 0
        for build, label, names in sections:
            item = QListWidgetItem(themed(names), label)
            item.setSizeHint(QSize(0, 38))
            self.nav.addItem(item)
            widest = max(widest, self.nav.fontMetrics().horizontalAdvance(label))
            area = QScrollArea(self)          # a long page scrolls instead of stretching the window
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(build())
            self.stack.addWidget(area)
        self.nav.setFixedWidth(widest + 22 + 46)
        self.nav.currentRowChanged.connect(self._show_page)
        self.nav.setCurrentRow(self.PAGES.index(page) if page in self.PAGES else 0)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Apply
                              | QDialogButtonBox.StandardButton.Cancel, self)
        bb.accepted.connect(lambda: (self.apply(), self.accept()))
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        lay.addWidget(bb)

    def _show_page(self, row):
        """Another page of the Settings: it comes in with a short fade (polish.py)."""
        from . import effects, polish
        if (row != self.stack.currentIndex() and self.isVisible()
                and polish.part("settings_fade")):
            effects.cross_fade([self.stack], self.cfg, ms=150)
        self.stack.setCurrentIndex(row)

    # --- pages -------------------------------------------------------
    def _general(self):
        w = QWidget()
        f = QFormLayout(w)
        self.language = QComboBox()
        self._fill_languages()
        lang_row = QHBoxLayout()
        lang_file = QPushButton(T("Install language from file…"))
        lang_net = QPushButton(T("Download languages…"))
        lang_file.clicked.connect(self._lang_from_file)
        lang_net.clicked.connect(self._lang_download)
        lang_row.addWidget(lang_file)
        lang_row.addWidget(lang_net)
        lang_row.addStretch(1)
        self.language.setCurrentIndex(max(0, self.language.findData(self.cfg["language"])))
        self.accept_lang = QLineEdit(self.cfg["accept_language"])
        from .config import system_accept_language
        self.accept_lang.setPlaceholderText(system_accept_language())      # empty: the system's (1.1.18)
        self.accept_lang.setToolTip(T("Languages requested from websites, in order of preference"))
        self.startup = QComboBox()
        for key, label in (("restore", T("Restore the previous session")),
                           ("home", T("Open the home page")),
                           ("newtab", T("Open a new tab"))):
            self.startup.addItem(label, key)
        self.startup.setCurrentIndex(max(0, self.startup.findData(self.cfg["startup"])))
        self.homepage = QLineEdit(self.cfg["homepage"])
        self.homepage.setPlaceholderText("ike:newtab")
        default_btn = QPushButton(T("Make I.K.E. the default browser"))
        default_btn.clicked.connect(self._make_default)
        f.addRow(T("Interface language"), self.language)
        f.addRow("", lang_row)
        f.addRow("", QLabel(T("Changing the interface language takes effect after a restart.")))
        f.addRow(T("Languages for websites"), self.accept_lang)
        f.addRow(T("At startup"), self.startup)
        f.addRow(T("Home page"), self.homepage)
        f.addRow("", default_btn)
        from .mailto import SERVICES
        self.mail = QComboBox()
        self.mail.addItem(T("Ask each time"), "ask")
        for key, name in SERVICES:
            self.mail.addItem(name, key)
        self.mail.addItem(T("The computer's mail program"), "system")
        self.mail.setCurrentIndex(max(0, self.mail.findData(self.cfg["mail_handler"])))
        f.addRow(T("Email links"), self.mail)
        self.lazy = QCheckBox(T("Load restored tabs only when they are opened (faster start)"))
        self.lazy.setChecked(bool(self.cfg["lazy_restore"]))
        self.sleep = QSpinBox()
        self.sleep.setRange(0, 600)
        self.sleep.setSuffix(" min")
        self.sleep.setSpecialValueText(T("Never"))
        self.sleep.setValue(int(self.cfg["tab_sleep_minutes"]))
        self.sleep.setToolTip(T("Background tabs unused for this long are suspended to free memory"))
        self.upd = QComboBox()
        for key, label in (("auto", T("Install automatically")), ("ask", T("Ask before installing")),
                           ("off", T("Do not check"))):
            self.upd.addItem(label, key)
        self.upd.setCurrentIndex(max(0, self.upd.findData(self.cfg["app_updates"])))
        self.channel = QComboBox()
        self.channel.addItem(T("Stable"), "stable")
        self.channel.addItem(T("Experimental (beta)"), "beta")
        self.channel.setCurrentIndex(max(0, self.channel.findData(self.cfg["update_channel"])))
        self.translate = QLineEdit(self.cfg["translate_url"])
        self.translate.setToolTip(T("{url} is the page address, {lang} the interface language"))
        f.addRow("", _wrapping(self.lazy))
        f.addRow(T("Suspend inactive tabs after"), self.sleep)
        f.addRow(T("I.K.E. updates"), self.upd)
        f.addRow(T("Update channel"), self.channel)
        f.addRow(T("Translation service"), self.translate)
        self.autoplay = QCheckBox(T("Do not let videos and sounds start by themselves (single sites: the lock "
                                    "in the address bar)"))
        self.autoplay.setChecked(bool(self.cfg["autoplay_block"]))
        self.gestures = QCheckBox(T("Mouse gestures: hold the right button and draw ← back, → forward, "
                                    "↑ reload, ↓→ close the tab"))
        self.gestures.setChecked(bool(self.cfg["mouse_gestures"]))
        self.smooth = QCheckBox(T("Smooth scrolling of pages (after a restart)"))
        self.smooth.setChecked(bool(self.cfg["smooth_scrolling"]))
        f.addRow("", _wrapping(self.autoplay))
        f.addRow("", _wrapping(self.gestures))
        f.addRow("", self.smooth)
        self.video_hw = QComboBox()
        for key, label in (("auto", T("Automatic (recommended)")), ("on", T("On (experimental)")),
                           ("off", T("Off"))):
            self.video_hw.addItem(label, key)
        self.video_hw.setCurrentIndex(max(0, self.video_hw.findData(self.cfg["video_hw"])))
        f.addRow(T("Video decoding with the graphics card"), self.video_hw)
        video_note = QLabel(T("After a restart. It lightens the processor while videos play and needs the "
                              "graphics card's VA-API driver (NVIDIA: libva-nvidia-driver, Intel: "
                              "intel-media-driver, AMD: already there). If videos look wrong or I.K.E. "
                              "closes, choose Automatic."))
        video_note.setWordWrap(True)
        f.addRow("", video_note)
        self.di = {}
        desktop = (
            ("di_media", T("Media controls: the media widget, the lock screen and the media keys "
                           "control the tab playing sound")),
            ("di_downloads", T("Show downloads in Plasma’s notifications")),
            ("di_krunner", T("Find open tabs and bookmarks with KRunner")),
            ("di_kdeconnect", T("“Send to device” with KDE Connect")))
        for i, (key, label) in enumerate(desktop):
            c = QCheckBox(label)
            c.setChecked(bool(self.cfg[key]))
            self.di[key] = c
            f.addRow(T("Desktop integration") if i == 0 else "", _wrapping(c) if i == 0 else c)
        return w

    def _fill_languages(self):
        from . import i18n
        cur = self.language.currentData() or self.cfg["language"]
        self.language.clear()
        packs = [(k, v) for k, v in i18n.installed_packs() if k != "it"]
        for key, label in [("auto", T("System language")), ("it", "Italiano"),
                           ("en", "English")] + packs:
            self.language.addItem(label, key)
        self.language.setCurrentIndex(max(0, self.language.findData(cur)))

    def _lang_from_file(self):
        from . import i18n
        path, _f = QFileDialog.getOpenFileName(self, T("Language pack"), "", "JSON (*.json)")
        if not path:
            return
        try:
            code = i18n.install_pack(Path(path).read_bytes())
        except Exception as exc:
            QMessageBox.warning(self, "I.K.E.", T("This is not a valid language pack: %s") % exc)
            return
        self._fill_languages()
        self.language.setCurrentIndex(max(0, self.language.findData(code)))

    def _lang_download(self):
        dlg = LanguageDownloadDialog(self.app, self)
        dlg.exec()
        self._fill_languages()
        if dlg.installed:
            self.language.setCurrentIndex(max(0, self.language.findData(dlg.installed)))

    def _make_default(self):
        import subprocess
        try:
            subprocess.run(["xdg-settings", "set", "default-web-browser", "ike-browser.desktop"],
                           check=True, timeout=10)
            QMessageBox.information(self, "I.K.E.", T("I.K.E. is now the default browser."))
        except Exception:
            QMessageBox.warning(self, "I.K.E.", T(
                "Could not change the default browser. Set it in System Settings → Default Applications."))

    def _appearance(self):
        w = QWidget()
        f = QFormLayout(w)
        self.tabs_pos = QComboBox()
        self.tabs_pos.addItem(T("Horizontal (top bar)"), "horizontal")
        self.tabs_pos.addItem(T("Vertical (side panel)"), "vertical")
        self.tabs_pos.setCurrentIndex(max(0, self.tabs_pos.findData(self.cfg["tabs_position"])))
        self.menubar = QCheckBox(T("Show the menu bar"))
        self.menubar.setChecked(self.cfg["show_menubar"])
        self.bookbar = QComboBox()
        for key, label in (("newtab", T("Only on a new tab")), ("always", T("Always")),
                           ("never", T("Never"))):
            self.bookbar.addItem(label, key)
        self.bookbar.setCurrentIndex(max(0, self.bookbar.findData(self.cfg["bookmarks_bar"])))
        self.titlebar = QCheckBox(T("Use the system title bar (untick for more room: the window "
                                    "buttons move next to the address bar)"))
        self.titlebar.setChecked(bool(self.cfg["system_titlebar"]))
        self.maximized = QCheckBox(T("Open windows maximized"))
        self.effects = QCheckBox(T("Interface effects: short fades and the mark on tabs that are loading"))
        self.effects.setToolTip(T("They are also off when the desktop is set to show no animations"))
        self.effects.setChecked(bool(self.cfg["ui_effects"]))
        self.site_tint = QCheckBox(T("Colour the edge of the address bar with the colour of the site"))
        self.site_tint.setChecked(bool(self.cfg["site_tint"]))
        self.maximized.setChecked(bool(self.cfg["start_maximized"]))
        self.vauto = QCheckBox(T("Hide vertical tabs; show them when the mouse touches the left edge"))
        self.vauto.setChecked(bool(self.cfg["vtabs_autohide"]))
        self.tb_btns = {}
        from PyQt6.QtWidgets import QGridLayout
        tb_row = QGridLayout()
        labels = {"back": T("Back"), "forward": T("Forward"), "reload": T("Reload"),
                  "home": T("Home"), "downloads": T("Downloads"),
                  "bookmark": T("Bookmark"), "reader": T("Reader mode"),
                  "screenshot": T("Screenshot"), "pip": T("Video in floating window"),
                  "split": T("Split view"), "dark": T("Dark mode for pages"),
                  "private": T("New private window"), "cleansite": T("Clear this site's data")}
        for i, (key, _hide) in enumerate(TOOLBAR_ITEMS):
            c = QCheckBox(labels.get(key, key))
            c.setChecked(key not in self.cfg["toolbar_hidden"])
            self.tb_btns[key] = c
            tb_row.addWidget(c, i // 3, i % 3)
        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(0.5, 3.0)
        self.zoom.setSingleStep(0.1)
        self.zoom.setValue(self.cfg["default_zoom"])
        self.dark = QComboBox()
        for key, label in (("on", T("On")), ("off", T("Off"))):
            self.dark.addItem(label, key)
        self.dark.setCurrentIndex(max(0, self.dark.findData(self.cfg["dark_mode"])))
        self.dark_engine = QComboBox()
        self.dark_engine.addItem(T("Dark Reader (can be set per site, immediate)"), "reader")
        self.dark_engine.addItem(T("Chromium Auto Dark Mode (can be set per site, immediate)"), "engine")
        self.dark_engine.setCurrentIndex(max(0, self.dark_engine.findData(self.cfg["dark_engine"])))
        from . import icons
        self.icon_theme = QComboBox()
        self._narrow(self.icon_theme)          # long set names in some languages must not widen the page
        self.icon_theme.addItem(T("Follow the system"), "system")
        for key, label in icons.SETS:
            self.icon_theme.addItem(T("%s (included with I.K.E.)") % label, "set:" + key)
        for folder, label in icons.installed_themes():
            self.icon_theme.addItem(label, "theme:" + folder)
        self.icon_theme.setCurrentIndex(max(0, self.icon_theme.findData(self.cfg["icon_theme"])))
        self.ui_scheme = QComboBox()
        self._narrow(self.ui_scheme)
        self._fill_schemes(self.cfg["ui_scheme"])
        custom = QPushButton(T("Customize…"))
        custom.setToolTip(T("Colours and font of the interface"))
        custom.clicked.connect(self._edit_theme)
        scheme_row = QHBoxLayout()
        scheme_row.addWidget(self.ui_scheme, 1)
        scheme_row.addWidget(custom)
        f.addRow(T("Interface colours"), scheme_row)
        f.addRow(T("Icons"), self.icon_theme)
        f.addRow(T("Tabs"), self.tabs_pos)
        f.addRow("", self.menubar)
        f.addRow(T("Bookmarks bar"), self.bookbar)
        f.addRow("", _wrapping(self.vauto))
        f.addRow("", _wrapping(self.titlebar))
        f.addRow("", self.maximized)
        f.addRow("", _wrapping(self.effects))
        f.addRow("", _wrapping(self.site_tint))
        f.addRow(T("Toolbar buttons"), tb_row)
        f.addRow(T("Default zoom"), self.zoom)
        f.addRow(T("Dark mode for pages"), self.dark)
        f.addRow(T("Dark mode method"), self.dark_engine)
        note = QLabel(T("With “Follow the system” colours, icons and fonts are those of your desktop. "
                        "A different icon choice is fully applied when I.K.E. is restarted."))
        note.setWordWrap(True)
        f.addRow("", note)
        return w

    def _newtab_rows(self, f):
        """New tab page: clock and weather (see weather.py)."""
        self.nt_clock = QCheckBox(T("Show the clock and the date"))
        self.nt_clock.setChecked(bool(self.cfg["newtab_clock"]))
        self.nt_weather = QCheckBox(T("Show the weather"))
        self.nt_weather.setChecked(bool(self.cfg["newtab_weather"]))
        self.city = QLineEdit(self.cfg["weather_city"])
        self.city.setPlaceholderText(T("City name"))
        self.city.setClearButtonEnabled(True)
        find = QPushButton(T("Find"))
        self.city_found = QWidget()               # results of "Find", shown when there are some
        found = QVBoxLayout(self.city_found)
        found.setContentsMargins(0, 0, 0, 0)
        self.city_results = QComboBox()
        self.city_status = QLabel("")
        found.addWidget(self.city_results)
        found.addWidget(self.city_status)
        self._city_pick = None
        self.city.returnPressed.connect(self._find_city)
        find.clicked.connect(self._find_city)
        self.city_results.activated.connect(self._city_chosen)
        self.app.weather.found.connect(self._cities_found)
        row = QHBoxLayout()
        row.addWidget(self.city, 1)
        row.addWidget(find)
        self.unit = QComboBox()
        self.unit.addItem("°C", "celsius")
        self.unit.addItem("°F", "fahrenheit")
        self.unit.setCurrentIndex(max(0, self.unit.findData(self.cfg["weather_unit"])))
        f.addRow(T("New tab page"), self.nt_clock)
        f.addRow("", self.nt_weather)
        f.addRow(T("City for the weather"), row)
        f.addRow("", self.city_found)
        self._city_form = f
        self._show_found(False)
        f.addRow(T("Temperature"), self.unit)
        info = QLabel(T("The weather comes from Open-Meteo (free, no account). Finding the city sends "
                        "its name; after that only the coordinates of the city are sent, at most every "
                        "30 minutes and only when a new tab is open. Your location is never asked."))
        info.setWordWrap(True)
        f.addRow("", info)
        self._background_rows(f)

    def _background_rows(self, f):
        """New tab page: a photo of the user's as its background (see newtabbg.py)."""
        from PyQt6.QtWidgets import QFrame, QSlider

        from . import newtabbg
        self._bg_choice = None            # None: as it is; "": remove it; DEFAULT: I.K.E.'s own; a path: that file
        self.bg_preview = QLabel()
        self.bg_preview.setFixedSize(96, 54)
        self.bg_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bg_preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.bg_info = QLabel("")
        self.bg_info.setWordWrap(True)
        choose = QPushButton(T("Choose…"))
        choose.setToolTip(T("A copy is kept in I.K.E.'s own folder. It is never sent anywhere."))
        choose.clicked.connect(self._choose_background)
        self.bg_remove = QPushButton(T("Remove"))
        self.bg_remove.clicked.connect(lambda: self._set_background(""))
        self.bg_default = QPushButton(T("Default"))
        self.bg_default.setToolTip(T("I.K.E.'s own photo"))
        self.bg_default.clicked.connect(lambda: self._set_background(newtabbg.DEFAULT))
        row = QHBoxLayout()
        row.addWidget(self.bg_preview)
        row.addWidget(self.bg_info, 1)
        row.addWidget(choose)
        row.addWidget(self.bg_default)
        row.addWidget(self.bg_remove)
        self.bg_fit = QComboBox()
        for key, label in (("fill", T("Fill the page")), ("fit", T("Show the whole photo")),
                           ("centre", T("Centre at its own size"))):
            self.bg_fit.addItem(label, key)
        self.bg_fit.setCurrentIndex(max(0, self.bg_fit.findData(self.cfg["newtab_bg_fit"])))
        self.bg_veil = QSlider(Qt.Orientation.Horizontal)
        self.bg_veil.setRange(0, newtabbg.VEIL_MAX)
        self.bg_veil.setPageStep(10)
        try:
            self.bg_veil.setValue(int(self.cfg["newtab_bg_veil"]))
        except (TypeError, ValueError):
            self.bg_veil.setValue(35)
        self.bg_veil.setToolTip(T("A veil in the page's own colour over the photo, to keep the text readable"))
        veil_value = QLabel("")
        veil_value.setMinimumWidth(veil_value.fontMetrics().horizontalAdvance("100%"))
        self.bg_veil.valueChanged.connect(lambda v: veil_value.setText("%d%%" % v))
        veil_value.setText("%d%%" % self.bg_veil.value())
        veil = QHBoxLayout()
        veil.addWidget(self.bg_veil, 1)
        veil.addWidget(veil_value)
        f.addRow(T("Background photo"), row)
        f.addRow(T("Photo placement"), self.bg_fit)
        f.addRow(T("Veil over the photo"), veil)
        self._show_background(self._bg_shown(self.cfg))

    @staticmethod
    def _bg_shown(cfg):
        from . import newtabbg
        if newtabbg.is_default(cfg):
            return newtabbg.DEFAULT
        current = newtabbg.current(cfg)
        return str(current) if current else ""

    def _show_background(self, path):
        """Preview and controls for the photo at path ("" = none, DEFAULT = I.K.E.'s own)."""
        from PyQt6.QtGui import QPixmap

        from . import newtabbg
        default = path == newtabbg.DEFAULT
        if default:
            path = str(newtabbg.DEFAULT_FILE)
        image = None
        if path:
            image, _problem = newtabbg.load_scaled(path, 192)
        if image is None:
            self.bg_preview.setPixmap(QPixmap())
            self.bg_preview.setText("—")
            self.bg_info.setText(T("No photo"))
        else:
            size, _problem = newtabbg.probe(path)
            ratio = self.devicePixelRatioF()
            pm = QPixmap.fromImage(image).scaled(
                round(96 * ratio), round(54 * ratio), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(ratio)
            self.bg_preview.setText("")
            self.bg_preview.setPixmap(pm)
            self.bg_info.setText(T("I.K.E.'s own photo") if default else ("%d × %d" % size if size else ""))
        on = image is not None
        self.bg_default.setEnabled(not default)
        self.bg_remove.setEnabled(on)
        self.bg_fit.setEnabled(on)
        self.bg_veil.setEnabled(on)

    def _choose_background(self):
        from . import newtabbg
        path, _f = QFileDialog.getOpenFileName(self, T("Choose a photo"), str(Path.home()),
                                               "%s (%s)" % (T("Pictures"), newtabbg.filters()))
        if path:
            self._set_background(path)

    def _set_background(self, path):
        """Take a file as the photo to use when the settings are applied ("" = none)."""
        from . import newtabbg
        if path and path != newtabbg.DEFAULT:
            _size, problem = newtabbg.probe(path)
            if not problem:
                _image, problem = newtabbg.load_scaled(path, 192)
            if problem:
                self.bg_info.setText(T(problem))          # said in place; the choice made before stays
                return False
        self._bg_choice = path
        self._show_background(path)
        return True

    def _show_found(self, on):
        try:
            self._city_form.setRowVisible(self.city_found, on)     # Qt 6.4: no empty gap
        except AttributeError:
            self.city_found.setVisible(on)

    def _find_city(self):
        from . import i18n
        name = self.city.text().strip()
        if len(name) < 2:
            return
        self.city_status.setText(T("Searching…"))
        self.city_status.setVisible(True)
        self.city_results.setVisible(False)
        self._show_found(True)
        self.app.weather.find(name, i18n.current())

    def _cities_found(self, results):
        self.city_results.clear()
        for r in results:
            self.city_results.addItem(r["label"], r)
        self.city_results.setVisible(bool(results))
        self._show_found(True)
        self.city_status.setText("" if results else T("No city found with this name."))
        self.city_status.setVisible(not results)
        if results:
            self._city_chosen(0)

    def _city_chosen(self, i):
        self._city_pick = self.city_results.itemData(i)

    @staticmethod
    def _narrow(combo):
        """A combo box with long entries must not make the page wider than the window."""
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(16)

    def _newtab_page(self):
        """Everything about the new tab page in one place."""
        w = QWidget()
        f = QFormLayout(w)
        self.nt_tiles = QComboBox()
        for key, label in (("bookmarks", T("My bookmarks")), ("visited", T("The sites I visit most")),
                           ("none", T("None"))):
            self.nt_tiles.addItem(label, key)
        self.nt_tiles.setCurrentIndex(max(0, self.nt_tiles.findData(self.cfg["newtab_tiles"])))
        self.nt_tiles.setToolTip(T("The most visited sites are worked out from the history kept on this computer"))
        self.nt_unhide = QPushButton(T("Show the hidden tiles again"))
        self.nt_unhide.setEnabled(bool(self.cfg["newtab_tiles_hidden"]))
        self.nt_unhide.clicked.connect(lambda: (self.nt_unhide.setProperty("clear", True),
                                                self.nt_unhide.setEnabled(False)))
        tiles = QHBoxLayout()
        tiles.addWidget(self.nt_tiles, 1)
        tiles.addWidget(self.nt_unhide)
        self.nt_counter = QComboBox()
        self.nt_counter.addItem(T("This month (starts again on the first of each month)"), "month")
        self.nt_counter.addItem(T("Since I.K.E. was installed"), "total")
        self.nt_counter.setCurrentIndex(max(0, self.nt_counter.findData(self.cfg["blocked_counter"])))
        self._narrow(self.nt_counter)
        self._narrow(self.nt_tiles)
        f.addRow(T("Site tiles"), tiles)
        f.addRow(T("Blocked counter"), self.nt_counter)
        self._newtab_rows(f)
        return w

    def _fill_schemes(self, selected):
        """System / light / dark, the ready-made themes and the user's own."""
        from . import themes
        combo = self.ui_scheme
        combo.clear()
        for key, label in (("system", T("Follow the system")), ("light", T("Light")), ("dark", T("Dark"))):
            combo.addItem(label, key)
        combo.insertSeparator(combo.count())
        for key, label in themes.names():
            combo.addItem(label, "theme:" + key)
        mine = sorted((self.cfg["ui_themes"] or {}), key=str.lower)
        if mine:
            combo.insertSeparator(combo.count())
            for name in mine:
                combo.addItem(name, "user:" + name)
        combo.setCurrentIndex(max(0, combo.findData(selected)))

    def _edit_theme(self):
        dlg = ThemeEditor(self.app, self.ui_scheme.currentData(), self)
        dlg.exec()
        self._fill_schemes(self.cfg["ui_scheme"])

    def _search(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel(T("Default search engine")))
        self.default_engine = QComboBox()
        row.addWidget(self.default_engine, 1)
        lay.addLayout(row)
        self.suggest = QCheckBox(T("Show search suggestions while typing"))
        self.suggest.setChecked(self.cfg["search_suggestions"])
        lay.addWidget(self.suggest)
        self.engines = QTableWidget(0, 4)
        self.engines.setHorizontalHeaderLabels(
            [T("Name"), T("Keyword"), T("Search URL ({q} = query)"), T("Suggestions URL")])
        hh = self.engines.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for e in self.cfg["search_engines"]:
            self._add_engine_row(e)
        self.engines.itemChanged.connect(lambda _i: self._refresh_default())
        lay.addWidget(self.engines, 1)
        lay.addWidget(QLabel(T("Type the keyword followed by a space in the address bar to "
                               "search with that engine, e.g. “w Roma”.")))
        btns = QHBoxLayout()
        add = QPushButton(T("Add engine"))
        rem = QPushButton(T("Remove selected"))
        reset = QPushButton(T("Restore defaults"))
        add.clicked.connect(lambda: (self._add_engine_row(
            {"name": T("New engine"), "keyword": "", "url": "https://example.com/?q={q}", "suggest": ""}),
            self._refresh_default()))
        rem.clicked.connect(lambda: (self.engines.removeRow(self.engines.currentRow()),
                                     self._refresh_default()))
        reset.clicked.connect(self._reset_engines)
        for b in (add, rem, reset):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        self._refresh_default(self.cfg["default_engine"])
        return w

    def _add_engine_row(self, e):
        r = self.engines.rowCount()
        self.engines.insertRow(r)
        for c, key in enumerate(("name", "keyword", "url", "suggest")):
            self.engines.setItem(r, c, QTableWidgetItem(e.get(key, "")))

    def _reset_engines(self):
        self.engines.setRowCount(0)
        for e in DEFAULT_ENGINES:
            self._add_engine_row(e)
        self._refresh_default(DEFAULTS["default_engine"])

    def _engine_rows(self):
        out = []
        for r in range(self.engines.rowCount()):
            vals = [(self.engines.item(r, c).text().strip() if self.engines.item(r, c) else "")
                    for c in range(4)]
            if vals[0] and "{q}" in vals[2]:
                out.append(dict(zip(("name", "keyword", "url", "suggest"), vals)))
        return out

    def _refresh_default(self, want=None):
        want = want or self.default_engine.currentText()
        self.default_engine.blockSignals(True)
        self.default_engine.clear()
        names = [e["name"] for e in self._engine_rows()]
        self.default_engine.addItems(names)
        if want in names:
            self.default_engine.setCurrentText(want)
        self.default_engine.blockSignals(False)

    def _privacy(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        f = QFormLayout()
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(T(LEVEL_NAMES[lv]), lv)
        self.level.setCurrentIndex(LEVELS.index(self.cfg["shield_level"]))
        f.addRow(T("Default protection level"), self.level)
        lay.addLayout(f)
        info = QLabel(T(
            "Off: nothing is blocked. Compatibility: ads, trackers and tracking links only. "
            "Balanced: also cross-site cookies and per-site noise on canvas, WebGL and audio. "
            "Strict: also generic hardware, screen, font and Client Hints values, no WebGPU. "
            "Maximum: also English as the only language. The shield in the "
            "toolbar changes the level for a single site."))
        info.setWordWrap(True)
        lay.addWidget(info)
        self.checks = {}
        for key, label in (
            ("https_only", T("Upgrade connections to HTTPS when possible")),
            ("block_third_party_cookies", T("Block cross-site (third-party) cookies")),
            ("strip_tracking_params", T("Remove tracking parameters from links (utm_, fbclid, gclid…)")),
            ("trim_referrer", T("Send only the site origin as referrer to other sites")),
            ("send_gpc", T("Send the “Global Privacy Control” signal")),
            ("webrtc_hide_ip", T("Hide local IP addresses from WebRTC")),
            ("clear_on_exit", T("Clear cookies, cache and history when I.K.E. is closed")),
            ("repair_button", T("Show “Repair this site” in the shield")),
            ("lookalike_warn", T("Warn about sites that imitate well-known ones")),
        ):
            c = QCheckBox(label)
            c.setChecked(bool(self.cfg[key]))
            self.checks[key] = c
            lay.addWidget(c)
        self.login_compat = QCheckBox(T(
            "Make sign-in with Google, Microsoft and Apple accounts work (lighter protection on "
            "their sign-in pages only)"))
        self.login_compat.setChecked(bool(self.cfg["login_compat"]))
        lay.addWidget(self.login_compat)
        f2 = QFormLayout()
        self.doh = QComboBox()
        self.doh.setEditable(True)
        self.doh.addItem(T("Off (system DNS)"), "off")
        for name in DOH_PROVIDERS:
            self.doh.addItem(name, name)
        cur = self.cfg["doh"]
        idx = self.doh.findData(cur)
        if idx >= 0:
            self.doh.setCurrentIndex(idx)
        else:
            self.doh.setEditText(cur)
        self.doh.setToolTip(T("Encrypted DNS (DNS over HTTPS). Pick a provider or type a custom URL."))
        f2.addRow(T("Encrypted DNS"), self.doh)
        self.containers = QLineEdit(", ".join(c["name"] for c in self.cfg["containers"]))
        self.containers.setToolTip(T("Each container keeps its own cookies and logins"))
        f2.addRow(T("Containers (comma separated)"), self.containers)
        lay.addLayout(f2)
        prow = QHBoxLayout()
        prow.addWidget(QLabel(T("Always refuse:")))
        self.perm_block = {}
        labels = {"camera": T("Camera"), "microphone": T("Microphone"), "location": T("Location"),
                  "notifications": T("Notifications"), "clipboard": T("Clipboard"),
                  "screen": T("Screen"), "fonts": T("Local fonts")}
        for kind in PERMISSION_KINDS:
            c = QCheckBox(labels[kind])
            c.setChecked(kind in self.cfg["perm_block"])
            self.perm_block[kind] = c
            prow.addWidget(c)
        prow.addStretch(1)
        lay.addLayout(prow)
        sites = QPushButton(T("Reset per-site exceptions (%d)") % (
            len(self.cfg["site_levels"]) + len(self.cfg["site_noscript"])))
        sites.clicked.connect(lambda: (self.cfg["site_levels"].clear(),
                                       self.cfg["site_noscript"].clear(),
                                       sites.setText(T("Reset per-site exceptions (%d)") % 0)))
        clear = QPushButton(T("Clear browsing data…"))
        clear.clicked.connect(self.app.show_clear_data)
        row = QHBoxLayout()
        row.addWidget(sites)
        row.addWidget(clear)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _components(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox(T("Built-in components (untick to remove)"))
        bl = QVBoxLayout(box)
        self.comp = {}
        for key, label in (
            ("comp_adblock", T("Ad and tracker blocker — uses the uBlock Origin and EasyList filter lists")),
            ("comp_consent", T("Cookie banner handler — refuses consent and hides the banners")),
        ):
            c = QCheckBox(label)
            c.setChecked(bool(self.cfg[key]))
            self.comp[key] = c
            bl.addWidget(c)
        self.yt_skip = QCheckBox(T("Skip video ads automatically on YouTube (mute, fast-forward, press “skip”)"))
        self.yt_skip.setChecked(bool(self.cfg["video_ad_skip"]))
        bl.addWidget(self.yt_skip)
        if not self.app.blocker.native:
            warn = QLabel(T("The I.K.E. AdBlock engine could not be loaded: only basic domain blocking is active."))
            warn.setStyleSheet("color:#c0392b")
            bl.addWidget(warn)
        lay.addWidget(box)

        dbox = QGroupBox(T("DRM video (Widevine)"))
        dl = QVBoxLayout(dbox)
        self.drm_label = QLabel()
        self.drm_label.setWordWrap(True)
        dl.addWidget(self.drm_label)
        drow = QHBoxLayout()
        self.drm_install = QPushButton()
        self.drm_install.clicked.connect(self._drm_download)
        self.drm_file = QPushButton(T("Install from a file…"))
        self.drm_file.clicked.connect(self._drm_from_file)
        self.drm_remove = QPushButton(T("Remove"))
        self.drm_remove.clicked.connect(self._drm_remove)
        for b_ in (self.drm_install, self.drm_file, self.drm_remove):
            drow.addWidget(b_)
        drow.addStretch(1)
        dl.addLayout(drow)
        lay.addWidget(dbox)
        self._drm_refresh()

        fbox = QGroupBox(T("Filter lists"))
        fl = QVBoxLayout(fbox)
        self.lists = QListWidget()
        for entry in self.cfg["filter_lists"]:
            self._add_list_item(entry)
        fl.addWidget(self.lists)
        row = QHBoxLayout()
        add = QPushButton(T("Add list from URL…"))
        rem = QPushButton(T("Remove selected"))
        reset = QPushButton(T("Restore defaults"))
        upd = QPushButton(T("Update now"))
        add.clicked.connect(self._add_list)
        rem.clicked.connect(lambda: self.lists.takeItem(self.lists.currentRow()))
        reset.clicked.connect(self._reset_lists)
        upd.clicked.connect(lambda: (self.apply(), self.app.update_now()))
        for b in (add, rem, reset, upd):
            row.addWidget(b)
        row.addStretch(1)
        fl.addLayout(row)
        self.auto_update = QCheckBox(T("Update the lists automatically every day"))
        self.auto_update.setChecked(self.cfg["auto_update"])
        fl.addWidget(self.auto_update)
        last = self.cfg["last_lists_update"]
        fl.addWidget(QLabel(T("Last update: %s") % (
            time.strftime("%d/%m/%Y %H:%M", time.localtime(last)) if last else T("never"))))
        fl.addWidget(QLabel(T("Your own filters (uBlock Origin / Adblock Plus syntax)")))
        self.custom = QPlainTextEdit(self.cfg["custom_filters"])
        self.custom.setMaximumHeight(70)
        fl.addWidget(self.custom)
        lay.addWidget(fbox, 1)

        ebox = QGroupBox(T("Extensions (experimental, Chrome format)"))
        el = QVBoxLayout(ebox)
        lay.addWidget(ebox)
        self.ext_on = QCheckBox(T("Enable experimental support for Chrome extensions (Manifest V3)"))
        self.ext_on.setChecked(bool(self.cfg["experimental_extensions"]))
        el.addWidget(self.ext_on)
        note = QLabel(T("With the Qt WebEngine version tested (6.11) enabling an extension "
                        "crashes the engine, so this is off by default. If you turn it on and "
                        "the browser crashes, I.K.E. switches it off again at the next start. "
                        "Only Manifest V3 extensions can be loaded: uBlock Origin, Dark Reader "
                        "and Consent-O-Matic in their original form are not guaranteed to work."))
        note.setWordWrap(True)
        el.addWidget(note)
        self._ext_mgr = self.app.extension_manager() if self.cfg["experimental_extensions"] else None
        if self._ext_mgr is None:
            return w
        self.ext_list = QListWidget()
        self.ext_list.setMaximumHeight(90)
        el.addWidget(self.ext_list)
        erow = QHBoxLayout()
        self.ext_add = QPushButton(T("Install from folder…"))
        self.ext_zip = QPushButton(T("Install from ZIP…"))
        self.ext_rem = QPushButton(T("Remove selected"))
        self.ext_toggle = QPushButton(T("Turn on / off"))
        self.ext_panel = QPushButton(T("Open its panel"))
        self.ext_store = QPushButton(T("Chrome Web Store"))
        self.ext_toggle.clicked.connect(self._toggle_ext)
        self.ext_panel.clicked.connect(self._panel_ext)
        self.ext_store.clicked.connect(lambda: (self.app.active_window().open_web_store(),
                                                self.reject()))
        for b in (self.ext_store, self.ext_add, self.ext_zip, self.ext_toggle, self.ext_panel,
                  self.ext_rem):
            erow.addWidget(b)
        erow.addStretch(1)
        el.addLayout(erow)
        self.ext_add.clicked.connect(lambda: self._install_ext(True))
        self.ext_zip.clicked.connect(lambda: self._install_ext(False))
        self.ext_rem.clicked.connect(self._remove_ext)
        self._ext_mgr.installFinished.connect(self._ext_done)
        self._ext_mgr.uninstallFinished.connect(self._ext_done)
        self._fill_ext()
        return w

    def _add_list_item(self, entry):
        it = QListWidgetItem("%s  —  %s" % (entry["name"], entry["url"]))
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked if entry.get("enabled", True)
                         else Qt.CheckState.Unchecked)
        it.setData(Qt.ItemDataRole.UserRole, dict(entry))
        self.lists.addItem(it)

    def _add_list(self):
        url, ok = QInputDialog.getText(self, T("Add list"), T("URL of the filter list:"))
        url = url.strip()
        if ok and url.startswith(("http://", "https://")):
            name = url.rsplit("/", 1)[-1] or url
            self._add_list_item({"name": name, "url": url, "group": "ads", "enabled": True})

    def _reset_lists(self):
        self.lists.clear()
        for entry in DEFAULT_LISTS:
            self._add_list_item(entry)

    def _fill_ext(self):
        self.ext_list.clear()
        for info in self._ext_mgr.extensions():
            if not info.isInstalled():
                continue  # engine-internal helpers (PDF viewer etc.)
            it = QListWidgetItem("%s %s%s" % ("●" if info.isEnabled() else "○", info.name(),
                                              ("  —  " + info.description())
                                              if info.description() else ""))
            it.setData(Qt.ItemDataRole.UserRole, info.id())
            self.ext_list.addItem(it)

    def _install_ext(self, folder):
        if folder:
            path = QFileDialog.getExistingDirectory(self, T("Extension folder (contains manifest.json)"))
        else:
            path, _f = QFileDialog.getOpenFileName(self, T("Extension archive"), "", "ZIP (*.zip)")
        if path:
            self._ext_mgr.installExtension(path)

    def _remove_ext(self):
        it = self.ext_list.currentItem()
        if not it:
            return
        for info in self._ext_mgr.extensions():
            if info.id() == it.data(Qt.ItemDataRole.UserRole):
                self._ext_mgr.uninstallExtension(info)

    def _selected_ext(self):
        it = self.ext_list.currentItem()
        if it:
            for info in self._ext_mgr.extensions():
                if info.id() == it.data(Qt.ItemDataRole.UserRole):
                    return info
        return None

    def _toggle_ext(self):
        info = self._selected_ext()
        if info is not None:
            self.app.enable_extension(self._ext_mgr, info, not info.isEnabled())
            self._fill_ext()

    def _panel_ext(self):
        info = self._selected_ext()
        if info is not None and not info.actionPopupUrl().isEmpty():
            win = self.app.new_window(urls=[info.actionPopupUrl()], popup=True)
            win.resize(420, 620)

    def _ext_done(self, info):
        if info.error():
            QMessageBox.warning(self, T("Extensions"), info.error())
        elif info.isInstalled() and not info.isEnabled():
            self.app.enable_extension(self._ext_mgr, info)
        self._fill_ext()

    # --- DRM -----------------------------------------------------------
    def _drm_refresh(self, note=""):
        import os

        from . import drm
        st = drm.status()
        if st["source"] == "ike":
            text = T("Widevine %s is installed in I.K.E.'s own folder.") % (st["version"] or "?")
        elif st["source"] == "system":
            text = T("Widevine %s from a system package is in use.") % (st["version"] or "?")
        else:
            text = T("Widevine is not installed: Netflix, Prime Video and similar services will not play. "
                     "I.K.E. can download it from Google's server into its own folder.")
        if st["path"] and os.environ.get("IKE_WIDEVINE") != st["path"]:
            text += " " + T("Restart I.K.E. to use it.")
        if note:
            text += "\n" + note
        self.drm_label.setText(text)
        self.drm_install.setText(T("Check for a newer version") if st["source"] == "ike"
                                 else T("Download and install"))
        self.drm_install.setEnabled(True)
        self.drm_file.setEnabled(True)
        self.drm_remove.setEnabled(st["source"] == "ike")

    def _drm_consent(self):
        return QMessageBox.question(
            self, T("DRM video (Widevine)"),
            T("Widevine is proprietary software by Google, needed by services such as Netflix. "
              "It is not part of I.K.E.: it will be downloaded from Google's server "
              "(dl.google.com) and stored in I.K.E.'s folder in your home directory. "
              "By installing it you accept Google's licence for it. Continue?")
        ) == QMessageBox.StandardButton.Yes

    def _drm_run(self, zip_path=None):
        from . import drm
        self.drm_install.setEnabled(False)
        self.drm_file.setEnabled(False)
        self.drm_label.setText(T("Installing Widevine…"))
        job = self._drm_job = drm.Installer(self, zip_path)
        job.finished_ok.connect(self._drm_done)
        job.failed.connect(lambda why: self._drm_refresh(T("Not installed: %s") % why))
        from . import background
        background.start(job)

    def _drm_download(self):
        if self._drm_consent():
            self._drm_run()

    def _drm_from_file(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Widevine archive"), "", "ZIP (*.zip)")
        if path and self._drm_consent():
            self._drm_run(path)

    def _drm_done(self, version):
        self._drm_refresh(T("Version %s installed.") % version)
        if QMessageBox.question(
                self, T("DRM video (Widevine)"),
                T("Widevine %s is installed. I.K.E. has to restart to use it; your tabs will be "
                  "reopened. Restart now?") % version) == QMessageBox.StandardButton.Yes:
            self.app.restart()

    def _drm_remove(self):
        from . import drm
        drm.remove()
        self._drm_refresh()

    def _userscripts(self):
        us = self.app.userscripts
        w = QWidget()
        lay = QVBoxLayout(w)
        self.us_on = QCheckBox(T("Run user scripts (the Greasemonkey, Tampermonkey and Violentmonkey kind)"))
        self.us_on.setChecked(bool(self.cfg["userscripts_enabled"]))
        lay.addWidget(self.us_on)
        info = QLabel(T(
            "A user script changes the pages it is written for. Install one from a file or from its "
            "address (for example from Greasy Fork), or simply open a link ending in “.user.js”. "
            "Installed scripts are checked for new versions once a day."))
        info.setWordWrap(True)
        lay.addWidget(info)
        self.us_list = QTreeWidget()
        self.us_list.setRootIsDecorated(False)
        self.us_list.setHeaderLabels([T("Script"), T("Version"), T("Runs on")])
        self.us_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.us_list.itemChanged.connect(self._us_toggled)
        lay.addWidget(self.us_list, 1)
        row = QHBoxLayout()
        for label, slot in ((T("Install from file…"), self._us_file),
                            (T("Install from address…"), self._us_url),
                            (T("Remove"), self._us_remove),
                            (T("Check for updates now"), lambda: us.check_updates(force=True)),
                            (T("Open the scripts folder"), self._us_folder)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        us.changed.connect(self._us_fill)
        self.destroyed.connect(lambda *_: self._us_disconnect(us))
        self._us_fill()
        return w

    def _us_disconnect(self, us):
        try:
            us.changed.disconnect(self._us_fill)
        except (TypeError, RuntimeError):
            pass

    def _us_fill(self):
        us = self.app.userscripts
        self.us_list.blockSignals(True)
        self.us_list.clear()
        for sid, s in us.listing():
            where = s.get("match", []) + s.get("include", [])
            it = QTreeWidgetItem([s["name"], s.get("version", ""),
                                  ", ".join(where[:3]) + (" …" if len(where) > 3 else "")
                                  if where else T("every site")])
            it.setData(0, Qt.ItemDataRole.UserRole, sid)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if s.get("enabled", True) else Qt.CheckState.Unchecked)
            it.setToolTip(0, s.get("description", ""))
            self.us_list.addTopLevelItem(it)
        self.us_list.blockSignals(False)

    def _us_toggled(self, item, column):
        if column == 0:
            self.app.userscripts.set_enabled(item.data(0, Qt.ItemDataRole.UserRole),
                                             item.checkState(0) == Qt.CheckState.Checked)

    def _us_file(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Install a user script"), "",
                                               T("User scripts (*.user.js *.js)"))
        if not path:
            return
        try:
            text = Path(path).read_text("utf-8", "replace")
        except OSError as exc:
            QMessageBox.warning(self, "I.K.E.", str(exc))
            return
        self.app.userscripts.offer(self, text=text)

    def _us_url(self):
        url, ok = QInputDialog.getText(self, "I.K.E.", T("Address of the user script:"))
        if ok and url.strip():
            self.app.userscripts.offer(self, url=url.strip())

    def _us_remove(self):
        it = self.us_list.currentItem()
        if it is None:
            return
        if QMessageBox.question(self, "I.K.E.", T("Remove the user script “%s”?") % it.text(0)) \
                == QMessageBox.StandardButton.Yes:
            self.app.userscripts.remove(it.data(0, Qt.ItemDataRole.UserRole))

    def _us_folder(self):
        from .userscripts import DIR
        DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DIR)))

    def _downloads(self):
        w = QWidget()
        f = QFormLayout(w)
        self.dl_dir = QLineEdit(self.cfg["download_dir"])
        self.dl_dir.setPlaceholderText(str(self.app.download_dir()))
        browse = QPushButton(T("Choose…"))
        browse.clicked.connect(lambda: self.dl_dir.setText(
            QFileDialog.getExistingDirectory(self, T("Download folder")) or self.dl_dir.text()))
        row = QHBoxLayout()
        row.addWidget(self.dl_dir, 1)
        row.addWidget(browse)
        self.dl_ask = QCheckBox(T("Always ask where to save files"))
        self.dl_ask.setChecked(self.cfg["ask_download_location"])
        f.addRow(T("Download folder"), row)
        f.addRow("", self.dl_ask)
        return w

    # --- apply -------------------------------------------------------
    def apply(self):
        cfg = self.cfg
        cfg["language"] = self.language.currentData()
        cfg["accept_language"] = self.accept_lang.text().strip()          # empty: the system's languages
        cfg["startup"] = self.startup.currentData()
        cfg["mail_handler"] = self.mail.currentData()
        cfg["video_hw"] = self.video_hw.currentData()
        cfg["homepage"] = self.homepage.text().strip() or "ike:newtab"
        cfg["tabs_position"] = self.tabs_pos.currentData()
        def looks():
            return [cfg[k] for k in ("icon_theme", "ui_scheme")]

        def newtab_look():
            return [cfg[k] for k in ("newtab_tiles", "blocked_counter", "ui_scheme")] + [list(cfg["newtab_tiles_hidden"])]
        look, page_look = looks(), newtab_look()
        cfg["icon_theme"] = self.icon_theme.currentData()
        cfg["ui_scheme"] = self.ui_scheme.currentData()
        cfg["newtab_tiles"] = self.nt_tiles.currentData()
        cfg["blocked_counter"] = self.nt_counter.currentData()
        if self.nt_unhide.property("clear"):
            cfg["newtab_tiles_hidden"] = []
            self.nt_unhide.setProperty("clear", False)
        if look != looks():
            from . import icons, themes
            icons.apply_scheme(cfg)
            themes.apply(cfg)
            icons.setup(cfg)
        scripts_on = cfg["userscripts_enabled"]
        cfg["userscripts_enabled"] = self.us_on.isChecked()
        if scripts_on != cfg["userscripts_enabled"]:
            self.app.userscripts.apply_all()
        cfg["show_menubar"] = self.menubar.isChecked()
        cfg["bookmarks_bar"] = self.bookbar.currentData()
        cfg["system_titlebar"] = self.titlebar.isChecked()
        cfg["vtabs_autohide"] = self.vauto.isChecked()
        cfg["start_maximized"] = self.maximized.isChecked()
        cfg["ui_effects"] = self.effects.isChecked()
        cfg["site_tint"] = self.site_tint.isChecked()
        cfg["toolbar_hidden"] = [k for k, c in self.tb_btns.items() if not c.isChecked()]
        cfg["default_zoom"] = round(self.zoom.value(), 2)
        dark_choice, dark_engine = self.dark.currentData(), self.dark_engine.currentData()
        if dark_choice != cfg["dark_mode"] or dark_engine != cfg["dark_engine"]:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.app.set_dark_mode(dark_choice, self.parent(), dark_engine))
        engines = self._engine_rows()
        if engines:
            cfg["search_engines"] = engines
            cfg["default_engine"] = self.default_engine.currentText() or engines[0]["name"]
        cfg["search_suggestions"] = self.suggest.isChecked()
        cfg["shield_level"] = self.level.currentData()
        for key, c in self.checks.items():
            cfg[key] = c.isChecked()
        idx = self.doh.findText(self.doh.currentText())
        cfg["doh"] = self.doh.itemData(idx) if idx >= 0 else self.doh.currentText().strip()
        for key, c in self.comp.items():
            cfg[key] = c.isChecked()
        lists = []
        for i in range(self.lists.count()):
            it = self.lists.item(i)
            entry = it.data(Qt.ItemDataRole.UserRole)
            entry["enabled"] = it.checkState() == Qt.CheckState.Checked
            lists.append(entry)
        cfg["filter_lists"] = lists
        cfg["custom_filters"] = self.custom.toPlainText()
        cfg["auto_update"] = self.auto_update.isChecked()
        cfg["video_ad_skip"] = self.yt_skip.isChecked()
        cfg["login_compat"] = self.login_compat.isChecked()
        cfg["lazy_restore"] = self.lazy.isChecked()
        for key, c in self.di.items():
            cfg[key] = c.isChecked()
        cfg["tab_sleep_minutes"] = self.sleep.value()
        cfg["app_updates"] = self.upd.currentData()
        cfg["update_channel"] = self.channel.currentData()
        if "{url}" in self.translate.text():
            cfg["translate_url"] = self.translate.text().strip()
        cfg["autoplay_block"] = self.autoplay.isChecked()
        cfg["mouse_gestures"] = self.gestures.isChecked()
        cfg["smooth_scrolling"] = self.smooth.isChecked()
        cfg["perm_block"] = [k for k, c in self.perm_block.items() if c.isChecked()]
        cfg["experimental_extensions"] = self.ext_on.isChecked()
        old = {c["name"]: c["color"] for c in cfg["containers"]}
        palette = ["#3daee9", "#f67400", "#27ae60", "#9b59b6", "#da4453", "#fdbc4b", "#1abc9c"]
        names = [n.strip() for n in self.containers.text().split(",") if n.strip()]
        cfg["containers"] = [{"name": n, "color": old.get(n, palette[i % len(palette)])}
                             for i, n in enumerate(dict.fromkeys(names))]
        cfg["newtab_clock"] = self.nt_clock.isChecked()
        cfg["newtab_weather"] = self.nt_weather.isChecked()
        before = (cfg["weather_city"], cfg["weather_lat"], cfg["weather_lon"], cfg["weather_unit"])
        cfg["weather_unit"] = self.unit.currentData()
        if self._city_pick is not None:
            cfg["weather_city"] = self._city_pick["name"]
            cfg["weather_lat"] = round(self._city_pick["lat"], 2)
            cfg["weather_lon"] = round(self._city_pick["lon"], 2)
            self.city.setText(cfg["weather_city"])
            self._city_pick = None
            self._show_found(False)
        elif not self.city.text().strip():
            cfg["weather_city"], cfg["weather_lat"], cfg["weather_lon"] = "", None, None
        if before != (cfg["weather_city"], cfg["weather_lat"], cfg["weather_lon"], cfg["weather_unit"]):
            self.app.weather.forget()
        cfg["download_dir"] = self.dl_dir.text().strip()
        cfg["ask_download_location"] = self.dl_ask.isChecked()
        from . import newtabbg
        look = newtabbg.style(cfg)
        problem = ""
        if self._bg_choice == "":
            newtabbg.remove_photo(cfg)
        elif self._bg_choice == newtabbg.DEFAULT:
            newtabbg.use_default(cfg)
        elif self._bg_choice:
            problem = newtabbg.set_photo(cfg, self._bg_choice)
        self._bg_choice = None
        self._show_background(self._bg_shown(cfg))
        if problem:
            self.bg_info.setText(T(problem))
        cfg["newtab_bg_fit"] = self.bg_fit.currentData()
        cfg["newtab_bg_veil"] = self.bg_veil.value()
        cfg.save()
        self.app.settings_changed()
        if look != newtabbg.style(cfg) or page_look != newtab_look():
            self.app.reload_newtabs()


class ThemeEditor(QDialog):
    """Colours and font of the interface, shown live; saved as a user theme."""

    LABELS = (("background", "Background"), ("text", "Text"), ("accent", "Accent"),
              ("toolbar", "Toolbars"), ("tabs", "Tabs"))

    def __init__(self, app, start, parent=None):
        from PyQt6.QtWidgets import QFontComboBox

        from . import themes
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.setWindowTitle(T("Customize the interface"))
        self.user_name = start[5:] if (start or "").startswith("user:") else ""
        theme = None
        if start.startswith("theme:"):
            theme = themes.BUILTIN.get(start[6:])
        elif self.user_name:
            theme = (self.cfg["ui_themes"] or {}).get(self.user_name)
        if not themes.valid(theme):
            theme = self._from_palette()
        self.theme = {k: theme[k] for k in themes.COLOURS}
        self.theme["font_family"] = theme.get("font_family", "")
        self.theme["font_size"] = int(theme.get("font_size") or 0)

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.swatches = {}
        for key, label in self.LABELS:
            b = QPushButton()
            b.setMinimumWidth(140)
            b.clicked.connect(lambda _c=False, k=key: self._pick(k))
            self.swatches[key] = b
            form.addRow(T(label), b)
        self.sys_font = QCheckBox(T("Use the system font"))
        self.sys_font.setChecked(not self.theme["font_family"])
        self.family = QFontComboBox()
        if self.theme["font_family"]:
            from PyQt6.QtGui import QFont
            self.family.setCurrentFont(QFont(self.theme["font_family"]))
        self.size = QSpinBox()
        self.size.setRange(0, 32)
        self.size.setSpecialValueText(T("System size"))
        self.size.setValue(self.theme["font_size"])
        form.addRow(T("Font"), self.sys_font)
        form.addRow("", self.family)
        form.addRow(T("Font size"), self.size)
        lay.addLayout(form)
        note = QLabel(T("Changes are shown at once. Save them as a theme to keep them."))
        note.setWordWrap(True)
        lay.addWidget(note)
        box = QDialogButtonBox()
        self.save_btn = box.addButton(T("Save as…"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.del_btn = box.addButton(T("Delete"), QDialogButtonBox.ButtonRole.DestructiveRole)
        self.del_btn.setEnabled(bool(self.user_name))
        box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.save_btn.clicked.connect(self._save)
        self.del_btn.clicked.connect(self._delete)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self.sys_font.toggled.connect(self._changed)
        self.family.currentFontChanged.connect(self._changed)
        self.size.valueChanged.connect(self._changed)
        self._changed()

    @staticmethod
    def _from_palette():
        """Start from the colours on screen now."""
        from PyQt6.QtGui import QGuiApplication, QPalette
        pal = QGuiApplication.palette()
        R = QPalette.ColorRole
        bg = pal.color(R.Window).name()
        return {"background": bg, "text": pal.color(R.WindowText).name(),
                "accent": pal.color(R.Highlight).name(), "toolbar": bg, "tabs": bg}

    def _paint_swatches(self):
        from PyQt6.QtGui import QColor
        for key, b in self.swatches.items():
            from .themes import _on
            c = QColor(self.theme[key])
            fg = _on(c).name()
            b.setText(c.name())
            b.setStyleSheet("QPushButton { background:%s; color:%s; border:1px solid %s;"
                            " border-radius:4px; padding:4px 10px; }" % (c.name(), fg, fg))

    def _pick(self, key):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.theme[key]), self, T(dict(self.LABELS)[key]))
        if c.isValid():
            self.theme[key] = c.name()
            self._changed()

    def _changed(self, *_):
        from . import themes
        self.family.setEnabled(not self.sys_font.isChecked())
        self.theme["font_family"] = "" if self.sys_font.isChecked() else self.family.currentFont().family()
        self.theme["font_size"] = self.size.value()
        self._paint_swatches()
        themes.apply(self.cfg, preview=dict(self.theme))      # live preview

    def _save(self):
        from . import themes
        builtin = {label.lower() for _k, label in themes.names()}
        name, ok = QInputDialog.getText(self, T("Save as…"), T("Theme name:"), text=self.user_name)
        name = name.strip()[:60]
        if not ok or not name:
            return
        mine = dict(self.cfg["ui_themes"] or {})
        if name.lower() in builtin:
            QMessageBox.warning(self, T("Customize the interface"),
                                T("This name belongs to a ready-made theme. Choose another one."))
            return
        if name in mine and name != self.user_name and QMessageBox.question(
                self, T("Customize the interface"),
                T("A theme called “%s” already exists. Replace it?") % name) \
                != QMessageBox.StandardButton.Yes:
            return
        mine[name] = dict(self.theme)
        self.cfg["ui_themes"] = mine
        self.cfg["ui_scheme"] = "user:" + name
        self.cfg.save()
        themes.apply(self.cfg)
        self.accept()

    def _delete(self):
        from . import themes
        if QMessageBox.question(self, T("Customize the interface"),
                                T("Delete the theme “%s”?") % self.user_name) \
                != QMessageBox.StandardButton.Yes:
            return
        mine = dict(self.cfg["ui_themes"] or {})
        mine.pop(self.user_name, None)
        self.cfg["ui_themes"] = mine
        if self.cfg["ui_scheme"] == "user:" + self.user_name:
            self.cfg["ui_scheme"] = "system"
        self.cfg.save()
        themes.apply(self.cfg)
        self.accept()

    def reject(self):
        from . import themes
        themes.apply(self.cfg)          # undo the preview
        super().reject()


class LanguageDownloadDialog(QDialog):
    """Lists the language packs published next to the program updates."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        from .updater import source
        self.app = app
        self.installed = None
        self.setWindowTitle(T("Download languages"))
        self.resize(420, 420)
        lay = QVBoxLayout(self)
        self.info = QLabel(T("Loading the list…"))
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        self.go = QPushButton(T("Install selected language"))
        self.go.clicked.connect(self._install)
        self.go.setEnabled(False)
        lay.addWidget(self.go)
        base = app.config["lang_url"] or (source().get("url", "").rstrip("/") + "/lang"
                                          if source().get("url") else "")
        self.base = base.rstrip("/")
        if not self.base:
            self.info.setText(T("No download address for language packs is configured yet "
                                "(it is published together with the program updates). You can "
                                "install a pack from a file instead."))
            return
        self._get(self.base + "/index.json", self._index)

    def _get(self, url, done):
        from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.app.network.get(req)

        def finished():
            ok = reply.error() == QNetworkReply.NetworkError.NoError
            data = bytes(reply.readAll()) if ok else None
            reply.deleteLater()
            done(data)
        reply.finished.connect(finished)

    def _index(self, data):
        import json
        try:
            entries = json.loads(data.decode("utf-8"))
        except Exception:
            self.info.setText(T("Could not load the list of languages."))
            return
        self.info.setText(T("Languages available for download:"))
        for e in entries:
            if isinstance(e, dict) and e.get("code") and e.get("file"):
                it = QListWidgetItem("%s (%s)" % (e.get("name") or e["code"], e["code"]))
                it.setData(Qt.ItemDataRole.UserRole, e["file"])
                self.list.addItem(it)
        self.go.setEnabled(self.list.count() > 0)

    def _install(self):
        it = self.list.currentItem()
        if it:
            self.go.setEnabled(False)
            self._get(self.base + "/" + it.data(Qt.ItemDataRole.UserRole), self._pack)

    def _pack(self, data):
        from . import i18n
        self.go.setEnabled(True)
        try:
            self.installed = i18n.install_pack(data)
        except Exception as exc:
            QMessageBox.warning(self, "I.K.E.", T("This is not a valid language pack: %s") % exc)
            return
        self.accept()


class HistoryDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("History") + " — I.K.E.")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(T("Search history"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Title"), T("Address"), T("Last visit")])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 340)
        self.tree.itemActivated.connect(lambda it, _c: self._open(it))
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        dele = QPushButton(T("Delete selected"))
        clear = QPushButton(T("Clear all history"))
        dele.clicked.connect(self._delete)
        clear.clicked.connect(lambda: (self.app.storage.clear_history(), self.fill()))
        row.addWidget(dele)
        row.addWidget(clear)
        row.addStretch(1)
        lay.addLayout(row)
        self.fill()

    def fill(self, *_):
        self.tree.clear()
        for url, title, last in self.app.storage.history(self.search.text()):
            QTreeWidgetItem(self.tree, [title or url, url,
                                        time.strftime("%d/%m/%Y %H:%M", time.localtime(last))])

    def _open(self, item):
        win = self.app.active_window()
        if win:
            win.add_tab(item.text(1))
            win.activateWindow()

    def _delete(self):
        for it in self.tree.selectedItems():
            self.app.storage.delete_history(it.text(1))
        self.fill()


class BookmarksDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("Bookmarks") + " — I.K.E.")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Title"), T("Address")])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 320)
        self.tree.itemActivated.connect(lambda it, _c: self._open(it))
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for label, slot in ((T("Add…"), self._add), (T("Rename…"), self._rename),
                            (T("Remove selected"), self._remove),
                            (T("Import HTML…"), self._import), (T("Export HTML…"), self._export)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.fill()

    def fill(self):
        self.tree.clear()
        for url, title, _folder in self.app.storage.bookmarks():
            it = QTreeWidgetItem(self.tree, [title or url, url])
            ic = self.app.favicons.icon(url)
            if not ic.isNull():
                it.setIcon(0, ic)
        self.app.refresh_windows()

    def _open(self, item):
        win = self.app.active_window()
        if win:
            win.add_tab(item.text(1))
            win.activateWindow()

    def _add(self):
        url, ok = QInputDialog.getText(self, T("Add bookmark"), T("Address:"))
        if ok and url.strip():
            u = QUrl.fromUserInput(url.strip()).toString()
            self.app.storage.add_bookmark(u, u)
            self.fill()

    def _rename(self):
        it = self.tree.currentItem()
        if not it:
            return
        title, ok = QInputDialog.getText(self, T("Rename bookmark"), T("Title:"), text=it.text(0))
        if ok and title.strip():
            self.app.storage.add_bookmark(it.text(1), title.strip())
            self.fill()

    def _remove(self):
        it = self.tree.currentItem()
        if it:
            self.app.storage.remove_bookmark(it.text(1))
            self.fill()

    def _import(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Import bookmarks"), "", "HTML (*.html *.htm)")
        if path:
            n = self.app.storage.import_bookmarks_html(
                Path(path).read_text("utf-8", "replace"))
            self.fill()
            QMessageBox.information(self, "I.K.E.", T("%d bookmarks imported.") % n)

    def _export(self):
        path, _f = QFileDialog.getSaveFileName(self, T("Export bookmarks"), "bookmarks.html",
                                               "HTML (*.html)")
        if path:
            Path(path).write_text(self.app.storage.export_bookmarks_html(), "utf-8")


class DownloadsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("Downloads") + " — I.K.E.")
        self.resize(720, 420)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("File"), T("Progress"), T("Status")])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 360)
        self.tree.setColumnWidth(1, 190)
        from .polish import ProgressDelegate
        self.tree.setItemDelegateForColumn(1, ProgressDelegate(self.tree))    # a bar under the size
        self.tree.setIconSize(QSize(24, 24))
        self._icons = {}
        self.tree.itemActivated.connect(lambda _i, _c: self._open(False))
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for label, slot in ((T("Open file"), lambda: self._open(False)),
                            (T("Open folder"), lambda: self._open(True)),
                            (T("Cancel download"), self._cancel),
                            (T("Clear finished"), self._clear)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fill)
        self.timer.start(700)
        self.fill()

    def _state(self, d):
        S = QWebEngineDownloadRequest.DownloadState
        return {S.DownloadInProgress: T("In progress"), S.DownloadCompleted: T("Completed"),
                S.DownloadCancelled: T("Cancelled"), S.DownloadInterrupted: T("Failed"),
                S.DownloadRequested: T("Waiting")}.get(d.state(), "")

    def fill(self):
        cur = self.tree.indexOfTopLevelItem(self.tree.currentItem())
        self.tree.clear()
        from .polish import FRACTION_ROLE, part
        S = QWebEngineDownloadRequest.DownloadState
        for d in self.app.downloads:
            total = d.totalBytes()
            got = d.receivedBytes()
            prog = ("%s / %s" % (_fmt_size(got), _fmt_size(total))) if total > 0 else _fmt_size(got)
            name = self.app.download_path(d).name
            item = QTreeWidgetItem(self.tree, [name, prog, self._state(d)])
            if part("download_rows"):
                item.setIcon(0, self._file_icon(name))
                if d.state() == S.DownloadCompleted:
                    item.setData(1, FRACTION_ROLE, 1.0)
                elif d.state() == S.DownloadInProgress and total > 0:
                    item.setData(1, FRACTION_ROLE, got / total)
        if cur >= 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(cur))

    def _file_icon(self, name):
        """The icon of the file's kind, from the icon theme (kept: the list is filled often)."""
        from PyQt6.QtCore import QMimeDatabase
        mime = QMimeDatabase().mimeTypeForFile(name, QMimeDatabase.MatchMode.MatchExtension)
        key = mime.name()
        if key not in self._icons:
            ic = QIcon.fromTheme(mime.iconName())
            if ic.isNull():
                ic = QIcon.fromTheme(mime.genericIconName())
            if ic.isNull():
                ic = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            self._icons[key] = ic
        return self._icons[key]

    def _current(self):
        """The selected download, or the most recent one when nothing is selected."""
        i = self.tree.indexOfTopLevelItem(self.tree.currentItem())
        if 0 <= i < len(self.app.downloads):
            return self.app.downloads[i]
        return self.app.downloads[0] if self.app.downloads else None

    def _open(self, folder):
        d = self._current()
        if d is None:
            if folder:        # nothing downloaded yet: show the download folder itself
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.download_dir())))
            return
        path = self.app.download_path(d)
        target = path.parent if folder else path
        if not target.exists():
            target = path.parent if path.parent.exists() else self.app.download_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _cancel(self):
        d = self._current()
        if d:
            d.cancel()

    def _clear(self):
        S = QWebEngineDownloadRequest.DownloadState
        self.app.downloads[:] = [d for d in self.app.downloads
                                 if d.state() == S.DownloadInProgress]
        self.fill()


class ClearDataDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("Clear browsing data"))
        lay = QVBoxLayout(self)
        self.history = QCheckBox(T("Browsing history"))
        self.cookies = QCheckBox(T("Cookies and site data (you will be signed out of websites)"))
        self.cache = QCheckBox(T("Cached images and files"))
        self.perms = QCheckBox(T("Site permissions (camera, location, notifications…)"))
        for c in (self.history, self.cookies, self.cache):
            c.setChecked(True)
        for c in (self.history, self.cookies, self.cache, self.perms):
            lay.addWidget(c)
        note = QLabel(T("Cookies are deleted at once. The other data stored by sites (local storage, "
                        "databases) is removed when I.K.E. is started again."))
        note.setWordWrap(True)
        note.setEnabled(False)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Clear"))
        bb.accepted.connect(self._clear)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _clear(self):
        self.app.clear_data(self.history.isChecked(), self.cookies.isChecked(),
                            self.cache.isChecked(), self.perms.isChecked())
        self.accept()
