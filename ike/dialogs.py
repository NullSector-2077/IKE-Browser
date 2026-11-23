"""Settings, history, bookmarks, downloads and clear-data dialogs."""

import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
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
from .uistyle import Switch, SwitchDelegate


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0


class _WrapLabel(QLabel):
    """The text of a check box that wraps when the room is short, and asks
    for the width of its text on one line when there is room for it (a
    wrapped QLabel would ask for about 80 characters, whatever its text)."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignTop)

    def sizeHint(self):
        s = super().sizeHint()
        m = self.contentsMargins()
        # measured as QLabel lays it out (scripts drawn with another font included)
        flags = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextShowMnemonic
        line = self.fontMetrics().boundingRect(QRect(0, 0, 100000, 1000), int(flags), self.text())
        one = line.width() + m.left() + m.right() + 2
        if one < s.width():
            return s
        return QSize(one, line.height() + m.top() + m.bottom())


def _wrapping(box):
    """A check box whose long text wraps instead of widening the page."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)                 # between the box and its text, on either side (right to left too)
    label = _WrapLabel(box.text())
    label.setWordWrap(True)
    label.setToolTip(box.toolTip())
    label.setBuddy(box)
    label.mousePressEvent = lambda _e: box.toggle()
    box.setText("")
    box.setAccessibleName(label.text().replace("&", ""))
    w.setProperty("ikeCheck", True)
    # the box in the middle of the first line of the text (1.1.21)
    box_h, line_h = box.sizeHint().height(), label.fontMetrics().height()
    label.setContentsMargins(0, max(0, (box_h - line_h) // 2), 0, 0)
    w.setProperty("ike_top", max(0, (box_h - line_h) // 2))
    col = QVBoxLayout()
    col.setContentsMargins(0, max(0, (line_h - box_h + 1) // 2), 0, 0)
    col.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)       # no stretch: the row would grow taller
    lay.addLayout(col)
    lay.addWidget(label, 0)
    lay.addStretch(1)                 # the ⓘ of the option goes before it (_with_hint)
    return w


def _tip(text, widget):
    """A tooltip that wraps its lines at a readable width (1.1.21)."""
    from html import escape
    fm = widget.fontMetrics()
    width = max(260, min(460, fm.averageCharWidth() * 50))
    body = escape(text).replace("\n", "<br>")
    if fm.horizontalAdvance(text) <= width:
        return "<p>%s</p>" % body
    return "<table width=\"%d\"><tr><td>%s</td></tr></table>" % (width, body)


class InfoButton(QToolButton):
    """The small round ⓘ after an option (1.1.21; in 1.1.20 a grey line under
    it, which a narrow window could cut). The mouse over it shows the
    explanation as a tooltip; a click, Space or Enter shows it in a small
    window that closes with a click elsewhere or Esc. Screen readers read the
    explanation as the button's name."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        from .icons import themed
        self.setObjectName("ike_info")
        self.setIcon(themed(("help-about", "dialog-information"),
                            QStyle.StandardPixmap.SP_MessageBoxInformation))
        # as tall as a line of text, so that it sits on the line of the option it explains
        side = max(16, self.fontMetrics().height())
        self.setIconSize(QSize(side - 2, side - 2))
        self.setFixedSize(side + 4, side + 2)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_text(text)
        self.clicked.connect(self.show_text)

    def set_text(self, text):
        self.setProperty("ike_text", text)
        self.setToolTip(_tip(text, self))
        self.setWhatsThis(text)
        self.setAccessibleName(text)

    def text_shown(self):
        return self.property("ike_text") or ""

    def show_text(self):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QWhatsThis
        x = 0 if self.isRightToLeft() else self.width()
        from html import escape
        # as rich text: laid out as a paragraph, in the direction of its language
        text = "<p>%s</p>" % escape(self.text_shown()).replace("\n", "<br>")
        QWhatsThis.showText(self.mapToGlobal(QPoint(x, self.height())), text, self)

    def keyPressEvent(self, event):
        # Enter shows the explanation; it must not reach the dialog (its default button)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
            self.show_text()
            return
        super().keyPressEvent(event)


class Note(QLabel):
    """A short note or a state (the last check...) in the palette's
    placeholder colour, wrapped and shown whole (1.1.21). Where that colour
    is too pale to read on the window (KDE's Breeze light, LXQt, Qt's own:
    3.7:1 and less) it is taken a little towards the text's (1.1.22)."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._fitting = False
        self.setObjectName("ike_note")
        self.setWordWrap(True)
        self.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._fit_colour()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ParentChange):
            self._fit_colour()

    def _fit_colour(self):
        if self._fitting:
            return
        from .uistyle import readable
        parent = self.parentWidget()
        src = parent.palette() if parent is not None else QApplication.palette(self)
        R, G = QPalette.ColorRole, QPalette.ColorGroup
        pal = QPalette()                # only this colour: the others come from the window
        for group in (G.Active, G.Inactive):
            # 5:1 on the window leaves 4.5:1 on a group's frame, which Fusion draws a little darker
            pal.setColor(group, R.PlaceholderText, readable(src.color(group, R.PlaceholderText),
                                                            src.color(group, R.Window),
                                                            src.color(group, R.WindowText), 5.0))
        self._fitting = True
        try:
            self.setPalette(pal)
        finally:
            self._fitting = False


def _info_row(widget, text, stretch=False):
    """widget, then the ⓘ of its explanation (and room after them unless stretch)."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    if isinstance(widget, QLayout):
        row.addLayout(widget, 1 if stretch else 0)
    else:
        row.addWidget(widget, 1 if stretch else 0)
    row.addWidget(InfoButton(text), 0, Qt.AlignmentFlag.AlignTop if isinstance(widget, QLabel)
                  else Qt.AlignmentFlag.AlignVCenter)
    if not stretch:
        row.addStretch(1)
    return row


def _with_hint(field, text, grow=None):
    """An option and the ⓘ of its explanation right after it (1.1.21).
    grow: the form's field growth policy (the field fills the row as the
    form would let it, the ⓘ after it)."""
    if not text:
        return field
    if isinstance(field, QCheckBox):
        field = _wrapping(field)
    if isinstance(field, QWidget) and field.property("ikeCheck"):
        lay = field.layout()
        col = QVBoxLayout()               # on the first line of the text
        col.setContentsMargins(0, max(0, (field.property("ike_top") or 0) - 1), 0, 0)
        col.addWidget(InfoButton(text), 0, Qt.AlignmentFlag.AlignTop)
        lay.insertLayout(lay.count() - 1, col)
        return field
    if isinstance(field, QBoxLayout) and field.count() and field.itemAt(field.count() - 1).spacerItem():
        # a row of buttons with room after them: the ⓘ right after the last button
        field.insertWidget(field.count() - 1, InfoButton(text), 0, Qt.AlignmentFlag.AlignVCenter)
        return field
    stretch = isinstance(field, QLayout)
    if isinstance(field, QWidget):
        policy = field.sizePolicy().horizontalPolicy()
        G = QFormLayout.FieldGrowthPolicy
        if grow == G.AllNonFixedFieldsGrow:
            stretch = policy != QSizePolicy.Policy.Fixed
        else:
            stretch = bool(policy.value & QSizePolicy.PolicyFlag.ExpandFlag.value)
    box = QWidget()
    box.setLayout(_info_row(field, text, stretch))
    return box


def _row(form, label, field, hint=None):
    """A row of a form: label, the option, and the ⓘ of its explanation.
    (An empty label is an empty QLabel: with "" Qt's form gives a wrapped
    text the height of its widest wrap, leaving a gap under it.)"""
    form.addRow(QLabel() if label == "" else label, _with_hint(field, hint, form.fieldGrowthPolicy()))


def fold(text):
    """A text as the Settings' search compares it (1.1.24): no "&" of a
    keyboard accelerator, no tags, small letters, accents of the Latin, Greek
    and Cyrillic letters taken off (è = e), spaces made one; other scripts
    are compared as they are written."""
    import re
    import unicodedata
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s*\(&[^&)]\)", "", text)
    text = re.sub(r"&(.)", r"\1", text)
    out = []
    for ch in unicodedata.normalize("NFKD", text.casefold()):
        if unicodedata.category(ch) == "Mn" and out and ord(out[-1]) < 0x0530:
            continue
        out.append(ch)
    return " ".join("".join(out).split())


def _texts_of(w):
    """The words a widget shows or explains (its ⓘ's explanation, a combo box's choices)."""
    if isinstance(w, InfoButton):
        return [w.text_shown()]
    if isinstance(w, QLabel):
        return [w.text()]
    if isinstance(w, QAbstractButton):
        return [w.text(), w.accessibleName()]
    if isinstance(w, QGroupBox):
        return [w.title()]
    if isinstance(w, QComboBox):
        return [w.itemText(i) for i in range(w.count())]
    if isinstance(w, QLineEdit):
        return [w.placeholderText()]
    return []


def _layout_widgets(item):
    """The widgets of a layout item, those inside its layouts too."""
    if item is None:
        return []
    if item.widget() is not None:
        return [item.widget()]
    lay = item.layout()
    if lay is None:
        return []
    out = []
    for i in range(lay.count()):
        out.extend(_layout_widgets(lay.itemAt(i)))
    return out


def _layout_holding(lay, w):
    """The layout under lay that holds w itself (None: none)."""
    if lay is None:
        return None
    if lay.indexOf(w) >= 0:
        return lay
    for i in range(lay.count()):
        found = _layout_holding(lay.itemAt(i).layout(), w)
        if found is not None:
            return found
    return None


def _search_targets(page, query):
    """What the search marks on a page: [[widgets, or a layout]], one entry per
    option found. A row of a form is one option (its name, its field and its
    ⓘ); an extension's card is one; any other text is one by itself."""
    R = QFormLayout.ItemRole
    targets, covered = [], set()

    def words(widgets):
        found = []
        for w in widgets:
            for x in [w] + w.findChildren(QWidget):
                if id(x) in covered or not x.isVisibleTo(page):
                    continue
                covered.add(id(x))
                found.extend(_texts_of(x))
        return fold(" ".join(t for t in found if t))

    for form in page.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            parts = []
            for role in (R.LabelRole, R.FieldRole, R.SpanningRole):
                parts.extend(_layout_widgets(form.itemAt(row, role)))
            parts = [w for w in parts if w.isVisibleTo(page)]
            names = [x for w in parts for x in [w] + w.findChildren(QLabel) if isinstance(x, QLabel) and x.text()]
            if len(names) > 4:
                continue        # a row of many options (the toolbar's buttons): each is marked by itself
            if parts and query in words(parts):
                targets.append(parts)
    for card in page.findChildren(QFrame, "ike_ext_card"):
        if card.isVisibleTo(page) and query in words([card]):
            targets.append([card])
    for w in page.findChildren(QWidget):
        if id(w) in covered or not w.isVisibleTo(page):
            continue
        covered.add(id(w))
        texts = [t for t in _texts_of(w) if t]
        if not texts or query not in fold(" ".join(texts)):
            continue
        if isinstance(w, InfoButton) and w.parentWidget() is not None:
            # its option: the row of widgets it stands in
            lay = _layout_holding(w.parentWidget().layout(), w)
            targets.append([lay] if lay is not None else [w])
        else:
            targets.append([w])
    return targets


class _Marks(QWidget):
    """The marks of the options found, drawn over a Settings page (1.1.24):
    the palette's highlight, light, around each one; clicks go through."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.targets = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        page.installEventFilter(self)
        self.hide()

    def show_targets(self, targets):
        self.targets = targets
        self.setGeometry(self.page.rect())
        self.setVisible(bool(targets))
        if targets:
            self.raise_()
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.page and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.page.rect())
        return False

    def rects(self):
        """Where each option found is, in the page."""
        from PyQt6.QtCore import QPoint
        out = []
        for target in self.targets:
            r = QRect()
            for part in target:
                if isinstance(part, QLayout):
                    owner = part.parentWidget()
                    g = part.geometry()
                    if owner is None or g.isEmpty():
                        continue
                    g = QRect(owner.mapTo(self.page, g.topLeft()), g.size())
                elif isinstance(part, QGroupBox):
                    from PyQt6.QtWidgets import QStyleOptionGroupBox
                    opt = QStyleOptionGroupBox()
                    part.initStyleOption(opt)
                    g = part.style().subControlRect(QStyle.ComplexControl.CC_GroupBox, opt,
                                                    QStyle.SubControl.SC_GroupBoxLabel, part)
                    g = QRect(part.mapTo(self.page, g.topLeft()), g.size())
                else:
                    if not part.isVisible():
                        continue
                    g = QRect(part.mapTo(self.page, QPoint(0, 0)), part.size())
                r = g if r.isNull() else r.united(g)
            if not r.isNull():
                out.append(r.adjusted(-4, -2, 4, 2))
        return out

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hl = self.palette().color(QPalette.ColorRole.Highlight)
        fill, line = QColor(hl), QColor(hl)
        fill.setAlpha(40)
        line.setAlpha(170)
        p.setPen(QPen(line, 1.0))
        p.setBrush(fill)
        for r in self.rects():
            p.drawRoundedRect(r.toRectF().adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        p.end()


def _align_forms(page):
    """The options of every form of a page start on one line (1.1.24): the
    names of a form whose options would start sooner (inside a group box they
    start a little farther than outside, and the longest name decides) are
    given the room that brings its options to the line of the others."""
    from PyQt6.QtCore import QPoint
    forms = [f for f in page.findChildren(QFormLayout) if f.rowCount()]
    # each name in the middle of its option's height, on the side the style puts it
    align = page.style().styleHint(QStyle.StyleHint.SH_FormLayoutLabelAlignment, None, page)
    horizontal = Qt.AlignmentFlag(align) & Qt.AlignmentFlag.AlignHorizontal_Mask
    for f in forms:
        f.setLabelAlignment(horizontal | Qt.AlignmentFlag.AlignVCenter)
    if len(forms) < 2:
        return
    R = QFormLayout.ItemRole
    for w in [page] + page.findChildren(QWidget):
        w.ensurePolished()
    size = page.size()
    page.resize(2400, 1600)                 # wide enough that no row puts its option under its name
    for w in [page] + page.findChildren(QWidget):
        if w.layout() is not None:
            w.layout().activate()
    rtl = page.isRightToLeft()
    columns = []
    for f in forms:
        labels = []
        for r in range(f.rowCount()):
            item = f.itemAt(r, R.LabelRole)
            if item is not None and item.widget() is not None:
                labels.append(item.widget())
        if not labels:
            continue
        # where the names end, from the page's edge (their options start right after)
        if rtl:
            end = max(page.width() - lab.mapTo(page, QPoint(0, 0)).x() for lab in labels)
        else:
            end = max(lab.mapTo(page, QPoint(lab.width(), 0)).x() for lab in labels)
        columns.append((end, max(lab.sizeHint().width() for lab in labels), labels, f))
    page.resize(size)
    if len(columns) < 2:
        return
    line = max(end for end, _w, _labels, _f in columns)
    for end, width, labels, _f in columns:
        if 0 < line - end <= 400:           # (more: something else went wrong, left as it was)
            for lab in labels:
                lab.setMinimumWidth(width + line - end)


class SettingsDialog(QDialog):
    # The pages, in the order of the sidebar (1.1.20). Their names are what
    # open_settings(page) takes; the names of earlier versions still work.
    WIDE_COMBO = 300      # px: a combo box with an entry wider than this is narrowed (_narrow)
    # 1.1.24: everyday browsing first (start, look, new tab, search, downloads),
    # then safety (protection, privacy), then the features, then I.K.E. itself
    # (language, updates, how it works with the computer)
    PAGES = ["general", "appearance", "newtab", "search", "downloads", "protection", "privacy",
             "extensions", "language", "updates", "system"]
    ALIASES = {"components": "extensions", "userscripts": "extensions"}

    @staticmethod
    def page_names():
        """{page: name shown in the sidebar} (also used by the command bar)."""
        return {"general": T("General"), "language": T("Language"), "appearance": T("Appearance"),
                "newtab": T("New tab page"), "search": T("Search"), "protection": T("Protection"),
                "privacy": T("Privacy"), "extensions": T("I.K.E. extensions"),
                "downloads": T("Downloads"), "updates": T("Updates"), "system": T("System")}

    def __init__(self, app, parent=None, page=None):
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.setWindowTitle(T("Settings") + " — I.K.E.")
        from .uistyle import fit_window
        fit_window(self, 1100, 700)  # room for a scroll bar beside the widest page; never past the screen
        from PyQt6.QtWidgets import QScrollArea, QStackedWidget

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
        # 1.1.24: a search field on top of the pages' list: it keeps the pages
        # that have the words typed and marks the options that have them
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(self)
        self.search.setObjectName("ike_settings_search")
        self.search.setPlaceholderText(T("Find a setting"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(themed(("edit-find", "system-search"), QStyle.StandardPixmap.SP_FileDialogContentsView),
                              QLineEdit.ActionPosition.LeadingPosition)
        self.search.installEventFilter(self)
        self.search_none = Note(T("No setting found"))
        self.search_none.setObjectName("ike_settings_none")
        self.search_none.hide()
        side.addWidget(self.search)
        side.addWidget(self.nav, 1)
        side.addWidget(self.search_none)
        body.addLayout(side)
        body.addWidget(self.stack, 1)
        self._marks = {}
        names = self.page_names()
        # page: (builder, icon names, what the page holds in one sentence)
        sections = {
            "general": (self._general, ("configure", "preferences-system"),
                        T("What I.K.E. opens when it starts, your home page, and how links of other "
                          "programs open.")),
            "language": (self._language, ("preferences-desktop-locale", "globe"),
                         T("The language of I.K.E. and the languages websites are asked for.")),
            "appearance": (self._appearance, ("preferences-desktop-theme", "preferences-desktop"),
                           T("Colours, icons, tabs, toolbar and the dark mode of pages.")),
            "newtab": (self._newtab_page, ("tab-new", "document-new"),
                       T("What the page of a new tab shows: tiles, clock, weather and a photo.")),
            "search": (self._search, ("edit-find", "system-search"),
                       T("The search engines of the address bar and of the new tab page.")),
            "protection": (self._protection, ("security-high", "preferences-security"),
                           T("What I.K.E. blocks: ads, trackers, fingerprinting and unsafe connections.")),
            "privacy": (self._privacy, ("view-private", "preferences-system-privacy"),
                        T("What is kept on this computer, and what sites are allowed to use.")),
            "extensions": (self._extensions, ("preferences-plugin", "application-x-addon"),
                           T("Features that come with I.K.E. Switch on only the ones you want.")),
            "downloads": (self._downloads, ("download", "folder-download"),
                          T("Where downloaded files are saved.")),
            "updates": (self._updates, ("system-software-update", "view-refresh"),
                        T("New versions of I.K.E. and of the blocking lists, checked by themselves.")),
            "system": (self._system, ("computer", "preferences-system", "window-new"),
                       T("How I.K.E. works with your computer: desktop, video, memory and translation.")),
        }
        widest = 0
        for key in self.PAGES:
            build, icons, about = sections[key]
            label = names[key]
            item = QListWidgetItem(themed(icons), label)
            item.setSizeHint(QSize(0, 38))
            item.setToolTip(about)
            self.nav.addItem(item)
            widest = max(widest, self.nav.fontMetrics().horizontalAdvance(label))
            area = QScrollArea(self)          # a long page scrolls instead of stretching the window
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            page_widget = self._page(label, about, build())
            _align_forms(page_widget)
            area.setWidget(page_widget)
            self.stack.addWidget(area)
        self.nav.setFixedWidth(widest + 22 + 46)
        self.search.setFixedWidth(self.nav.width())
        self.search_none.setFixedWidth(self.nav.width())
        self.search.textChanged.connect(self.find_options)
        from PyQt6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self, self.search.setFocus)
        for combo in self.findChildren(QComboBox):
            # any combo box whose longest entry would widen its page is narrowed
            # (1.1.22: in Tamil with KDE's Breeze the dark-mode one needed
            # sideways scrolling); its open list still shows every entry whole
            if not combo.property("ike_elides") and not combo.isEditable() and combo.count():
                fm = combo.fontMetrics()           # the entries themselves: the box's own size
                longest = max(fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
                if longest > self.WIDE_COMBO:      # depends on the style, known only once shown
                    self._narrow(combo)
            if combo.property("ike_elides"):
                self._whole_list(combo)
        self.nav.currentRowChanged.connect(self._show_page)
        self.show_page(page)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Apply
                              | QDialogButtonBox.StandardButton.Cancel, self)
        bb.accepted.connect(lambda: (self.apply(), self.accept()))
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        lay.addWidget(bb)

    def show_page(self, page):
        """Go to a page by its name (an earlier version's name too); unknown: the first."""
        page = self.ALIASES.get(page, page)
        self.nav.setCurrentRow(self.PAGES.index(page) if page in self.PAGES else 0)

    @staticmethod
    def _page(title, about, content):
        """A page: its name, one sentence saying what it holds, then its options."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 6, 12, 6)
        head = QLabel(title)
        head.setObjectName("ike_page_title")
        f = head.font()
        f.setBold(True)
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 1.3)
        head.setFont(f)
        lay.addWidget(head)
        if content.layout() is not None:
            content.layout().setContentsMargins(0, 4, 0, 0)
        sub = Note(about)
        sub.setObjectName("ike_page_about")
        lay.addWidget(sub)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(line)
        lay.addWidget(content, 1)
        return w

    @staticmethod
    def _group(title):
        """A titled box of options inside a page, and its form."""
        box = QGroupBox(title)
        form = QFormLayout(box)
        return box, form

    def _show_page(self, row):
        """Another page of the Settings: it comes in with a short fade (polish.py)."""
        from . import effects, polish
        if (row != self.stack.currentIndex() and self.isVisible()
                and polish.part("settings_fade")):
            effects.cross_fade([self.stack], self.cfg, ms=150)
        self.stack.setCurrentIndex(row)
        marks = self._marks.get(row)
        if marks is not None and marks.targets:
            QTimer.singleShot(0, lambda m=marks, r=row: self._reveal(r, m))

    # --- the search field (1.1.24) ------------------------------------
    def eventFilter(self, obj, event):
        # Esc in the search field empties it first; once empty, Esc closes the window as usual
        if obj is self.search and event.type() == QEvent.Type.KeyPress \
                and event.key() == Qt.Key.Key_Escape and self.search.text():
            self.search.clear()
            return True
        return super().eventFilter(obj, event)

    def find_options(self, text=None):
        """Keep the pages that have the words typed (in their names, options,
        explanations or choices) and mark those options; nothing typed: all.
        Returns {page: number of options found}."""
        query = fold(self.search.text() if text is None else text)
        found = {}
        first = None
        for row, key in enumerate(self.PAGES):
            page = self.stack.widget(row).widget()
            targets = _search_targets(page, query) if query else []
            in_name = bool(query) and query in fold(self.nav.item(row).text())
            marks = self._marks.get(row)
            if marks is None and targets:
                marks = self._marks[row] = _Marks(page)
            if marks is not None:
                marks.show_targets(targets)
            if targets or in_name:
                found[key] = len(targets)
                if first is None:
                    first = row
        nothing = bool(query) and first is None
        for row in range(self.nav.count()):
            self.nav.item(row).setHidden(bool(query) and not nothing and self.PAGES[row] not in found)
        self.search_none.setVisible(nothing)
        if first is not None and self.PAGES[self.nav.currentRow()] not in found:
            self.nav.setCurrentRow(first)
        elif first is not None:
            self._show_page(self.nav.currentRow())
        return found

    def _reveal(self, row, marks):
        """Scroll the page to its first option found."""
        if not marks.targets or self.stack.currentIndex() != row:
            return
        area = self.stack.widget(row)
        r = marks.rects()
        if r:
            top = min(x.top() for x in r)
            bar = area.verticalScrollBar()
            if top < bar.value() or top > bar.value() + area.viewport().height() - 40:
                bar.setValue(max(0, top - 20))

    # --- pages -------------------------------------------------------
    def _general(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        f = QFormLayout()
        lay.addLayout(f)
        self.startup = QComboBox()
        for key, label in (("restore", T("Restore the previous session")),
                           ("home", T("Open the home page")),
                           ("newtab", T("Open a new tab"))):
            self.startup.addItem(label, key)
        self.startup.setCurrentIndex(max(0, self.startup.findData(self.cfg["startup"])))
        self.lazy = Switch(T("Load restored tabs only when they are opened (faster start)"))
        self.lazy.setChecked(bool(self.cfg["lazy_restore"]))
        self.homepage = QLineEdit(self.cfg["homepage"])
        self.homepage.setPlaceholderText("ike:newtab")
        default_btn = QPushButton(T("Make I.K.E. the default browser"))
        default_btn.clicked.connect(self._make_default)
        from .mailto import SERVICES
        self.mail = QComboBox()
        self.mail.addItem(T("Ask each time"), "ask")
        for key, name in SERVICES:
            self.mail.addItem(name, key)
        self.mail.addItem(T("The computer's mail program"), "system")
        self.mail.setCurrentIndex(max(0, self.mail.findData(self.cfg["mail_handler"])))
        _row(f, T("At startup"), self.startup, T("What I.K.E. shows when it starts."))
        _row(f, "", _wrapping(self.lazy),
             T("Tabs of the last session wait until you open them: I.K.E. starts sooner and uses "
               "less memory."))
        _row(f, T("Home page"), self.homepage,
             T("The page of the Home button. ike:newtab is the new tab page."))
        _row(f, "", default_btn, T("Links opened in other programs will open in I.K.E."))
        _row(f, T("Email links"), self.mail, T("What happens when you click an email address on a page."))
        box, g = self._group(T("Browsing"))
        self.autoplay = Switch(T("Do not let videos and sounds start by themselves (single sites: the lock "
                                    "in the address bar)"))
        self.autoplay.setChecked(bool(self.cfg["autoplay_block"]))
        self.gestures = Switch(T("Mouse gestures: hold the right button and draw ← back, → forward, "
                                    "↑ reload, ↓→ close the tab"))
        self.gestures.setChecked(bool(self.cfg["mouse_gestures"]))
        _row(g, "", _wrapping(self.autoplay), T("Pages stay quiet until you press play."))
        _row(g, "", _wrapping(self.gestures), T("A right click without moving the mouse still opens the menu."))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _language(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
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
        _row(f, T("Interface language"), self.language,
             T("Changing the interface language takes effect after a restart."))
        _row(f, "", lang_row, T("More languages: a language pack from a file, or from I.K.E.'s list."))
        _row(f, T("Languages for websites"), self.accept_lang,
             T("Sites use it to choose the language of their pages. Empty: the languages of your system."))
        return w

    def _system(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        box, f = self._group(T("Desktop integration"))
        self.di = {}
        desktop = (
            ("di_media", T("Media controls: the media widget, the lock screen and the media keys "
                           "control the tab playing sound")),
            ("di_downloads", T("Show downloads in Plasma’s notifications")),
            ("di_krunner", T("Find open tabs and bookmarks with KRunner")),
            ("di_kdeconnect", T("“Send to device” with KDE Connect")))
        for key, label in desktop:
            c = Switch(label)
            c.setChecked(bool(self.cfg[key]))
            self.di[key] = c
            _row(f, "", _wrapping(c))
        # the note of the whole box, across its width (1.1.24: in the options'
        # column, set on one line with the other boxes', it could need three
        # lines, GNOME's font in Filipino, and Qt's form gave it two)
        f.addRow(Note(T("For KDE Plasma. All of it is off while the “Plasma integration” extension is off.")))
        lay.addWidget(box)
        box, f = self._group(T("Speed and memory"))
        self.video_hw = QComboBox()
        for key, label in (("auto", T("Automatic (recommended)")), ("on", T("On (experimental)")),
                           ("off", T("Off"))):
            self.video_hw.addItem(label, key)
        self.video_hw.setCurrentIndex(max(0, self.video_hw.findData(self.cfg["video_hw"])))
        _row(f, T("Video decoding with the graphics card"), self.video_hw,
             T("After a restart. It lightens the processor while videos play and needs the "
               "graphics card's VA-API driver (NVIDIA: libva-nvidia-driver, Intel: "
               "intel-media-driver, AMD: already there). If videos look wrong or I.K.E. "
               "closes, choose Automatic."))
        self.smooth = Switch(T("Smooth scrolling of pages (after a restart)"))
        self.smooth.setChecked(bool(self.cfg["smooth_scrolling"]))
        _row(f, "", self.smooth, T("Pages glide when you scroll with the wheel or the keys."))
        self.sleep = QSpinBox()
        self.sleep.setRange(0, 600)
        self.sleep.setSuffix(" min")
        self.sleep.setSpecialValueText(T("Never"))
        self.sleep.setValue(int(self.cfg["tab_sleep_minutes"]))
        _row(f, T("Suspend inactive tabs after"), self.sleep,
             T("Background tabs unused for this long are suspended to free memory"))
        lay.addWidget(box)
        box, f = self._group(T("Translation"))
        self.translate = QLineEdit(self.cfg["translate_url"])
        _row(f, T("Translation service"), self.translate,
             T("{url} is the page address, {lang} the interface language") + "\n\n"
             + T("Used only when you choose “Translate page”: the address of the page is sent "
                 "to this service."))
        lay.addWidget(box)
        lay.addWidget(self._drm_box())
        lay.addStretch(1)
        return w

    def _updates(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        box, f = self._group(T("I.K.E. updates"))
        self.upd = QComboBox()
        for key, label in (("auto", T("Install automatically")), ("ask", T("Ask before installing")),
                           ("off", T("Do not check"))):
            self.upd.addItem(label, key)
        self.upd.setCurrentIndex(max(0, self.upd.findData(self.cfg["app_updates"])))
        self.channel = QComboBox()
        self.channel.addItem(T("Stable"), "stable")
        self.channel.addItem(T("Experimental (beta)"), "beta")
        self.channel.setCurrentIndex(max(0, self.channel.findData(self.cfg["update_channel"])))
        _row(f, T("New versions"), self.upd,
             T("Checked once a day. Every update is verified with a digital signature before it is installed."))
        _row(f, T("Update channel"), self.channel,
             T("Experimental: new versions sooner, with a higher chance of problems."))
        check = QPushButton(T("Check now"))
        check.setIcon(QIcon.fromTheme("system-software-update"))
        check.clicked.connect(self._check_app_now)
        last = self.cfg["last_app_check"]
        self.app_last = Note(T("Last check: %s") % (
            time.strftime("%d/%m/%Y %H:%M", time.localtime(last)) if last else T("never")))
        row = QHBoxLayout()
        row.addWidget(check)
        row.addWidget(self.app_last, 1)
        _row(f, "", row)
        lay.addWidget(box)
        box, f = self._group(T("Filter lists"))
        self.auto_update = Switch(T("Update the lists automatically every day"))
        self.auto_update.setChecked(self.cfg["auto_update"])
        _row(f, "", self.auto_update,
             T("The rules of the blocker change every day. Your user scripts are checked for new "
               "versions at the same time."))
        upd = QPushButton(T("Update now"))
        upd.setIcon(QIcon.fromTheme("view-refresh"))
        upd.clicked.connect(lambda: (self.apply(), self.app.update_now()))
        last = self.cfg["last_lists_update"]
        row = QHBoxLayout()
        row.addWidget(upd)
        row.addWidget(Note(T("Last update: %s") % (
            time.strftime("%d/%m/%Y %H:%M", time.localtime(last)) if last else T("never"))), 1)
        _row(f, "", row)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _check_app_now(self):
        """Updates → Check now: the settings shown are applied, then the same
        check as Help → Check for I.K.E. updates."""
        self.apply()
        self.app.check_app_update(manual=True)

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
        # 1.1.24: written in ~/.config/mimeapps.list as the XDG specification
        # says (handoff.py); xdg-settings (xdg-utils) is no longer used
        from .handoff import set_default_browser
        try:
            set_default_browser()
            QMessageBox.information(self, "I.K.E.", T("I.K.E. is now the default browser."))
        except Exception:
            QMessageBox.warning(self, "I.K.E.", T(
                "Could not change the default browser. Set it in System Settings → Default Applications."))

    def _appearance(self):
        """1.1.24: grouped as one looks for it: the interface's colours, the
        window and its tabs, the toolbar's buttons, then the pages."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        f = QFormLayout()
        lay.addLayout(f)
        self.tabs_pos = QComboBox()
        self.tabs_pos.addItem(T("Horizontal (top bar)"), "horizontal")
        self.tabs_pos.addItem(T("Vertical (side panel)"), "vertical")
        self.tabs_pos.setCurrentIndex(max(0, self.tabs_pos.findData(self.cfg["tabs_position"])))
        self.menubar = Switch(T("Show the menu bar"))
        self.menubar.setChecked(self.cfg["show_menubar"])
        self.bookbar = QComboBox()
        for key, label in (("newtab", T("Only on a new tab")), ("always", T("Always")),
                           ("never", T("Never"))):
            self.bookbar.addItem(label, key)
        self.bookbar.setCurrentIndex(max(0, self.bookbar.findData(self.cfg["bookmarks_bar"])))
        self.titlebar = Switch(T("Use the system title bar (untick for more room: the window "
                                    "buttons move next to the address bar)"))
        self.titlebar.setChecked(bool(self.cfg["system_titlebar"]))
        self.maximized = Switch(T("Open windows maximized"))
        self.effects = Switch(T("Interface effects: short fades and the mark on tabs that are loading"))
        self.effects.setChecked(bool(self.cfg["ui_effects"]))
        self.site_tint = Switch(T("Colour the edge of the address bar with the colour of the site"))
        self.site_tint.setChecked(bool(self.cfg["site_tint"]))
        self.maximized.setChecked(bool(self.cfg["start_maximized"]))
        self.vauto = Switch(T("Hide vertical tabs; show them when the mouse touches the left edge"))
        self.vauto.setChecked(bool(self.cfg["vtabs_autohide"]))
        self.tb_btns = {}
        from PyQt6.QtWidgets import QGridLayout
        tb_row = QGridLayout()
        labels = {"back": T("Back"), "forward": T("Forward"), "reload": T("Reload"),
                  "home": T("Home"), "downloads": T("Downloads"),
                  "bookmark": T("Bookmark"), "reader": T("Reader mode"),
                  "screenshot": T("Screenshot"), "pip": T("Video in floating window"),
                  "split": T("Split view"), "dark": T("Dark mode for pages"),
                  "private": T("New private window"), "cleansite": T("Clear this site's data"),
                  "zoom": T("Zoom"), "bookmarks": T("Manage bookmarks"),
                  "print": T("Print or save as PDF"), "send": T("Send to device"),
                  "resources": T("Site resources")}
        for i, (key, _hide) in enumerate(TOOLBAR_ITEMS):
            c = Switch(labels.get(key, key))
            c.setChecked(key not in self.cfg["toolbar_hidden"])
            self.tb_btns[key] = c
            tb_row.addWidget(_wrapping(c), i // 3, i % 3)      # a long name wraps (1.1.21)
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
        _row(f, T("Interface colours"), scheme_row,
             T("With “Follow the system” colours, icons and fonts are those of your desktop. "
               "A different icon choice is fully applied when I.K.E. is restarted."))
        _row(f, T("Icons"), self.icon_theme, T("The icons of the toolbar and of the menus."))
        _row(f, "", _wrapping(self.effects), T("They are also off when the desktop is set to show no animations"))
        _row(f, "", _wrapping(self.site_tint), T("A light tint of the site's own colour around the address bar."))
        box, g = self._group(T("Window"))
        _row(g, T("Tabs"), self.tabs_pos, T("Tabs in a bar at the top, or in a list at the side."))
        _row(g, "", _wrapping(self.vauto), T("Only with vertical tabs: more room for pages."))
        _row(g, T("Bookmarks bar"), self.bookbar, T("The bar of your bookmarks under the address bar."))
        _row(g, "", self.menubar, T("The classic menus above the toolbar. Everything is also in the ☰ menu."))
        _row(g, "", _wrapping(self.titlebar), T("The bar with the window's name, drawn by the desktop."))
        _row(g, "", self.maximized, T("New windows fill the screen."))
        lay.addWidget(box)
        box, g = self._group(T("Toolbar buttons"))
        g.addRow(_with_hint(tb_row, T("Which buttons the toolbar shows. To move them, right-click the toolbar."),
                            g.fieldGrowthPolicy()))         # the whole width of the box
        lay.addWidget(box)
        box, g = self._group(T("Web pages"))
        _row(g, T("Default zoom"), self.zoom,
             T("The size of the pages you have not zoomed yourself. 1.0 is the normal size."))
        _row(g, T("Dark mode for pages"), self.dark,
             T("Makes bright pages dark. Single sites: ☰ → Dark mode for pages. Part of the "
               "“Dark mode for pages” extension."))
        _row(g, T("Dark mode method"), self.dark_engine,
             T("Dark Reader gives better colours; Chromium's own is built into the engine and lighter."))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _newtab_rows(self, f):
        """New tab page: clock and weather (see weather.py)."""
        self.nt_clock = Switch(T("Show the clock and the date"))
        self.nt_clock.setChecked(bool(self.cfg["newtab_clock"]))
        self.nt_greeting = Switch(T("Greeting on the new tab page"))
        self.nt_greeting.setChecked(bool(self.cfg["newtab_greeting"]))
        self.nt_weather = Switch(T("Show the weather"))
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
        _row(f, T("New tab page"), self.nt_clock, T("The time and the date at the bottom of the page."))
        _row(f, "", self.nt_greeting, T("A short hello at the top left, from the time of day; nothing leaves your computer."))
        self.nt_tone = QComboBox()
        self.nt_tone.addItem(T("Greetings only"), "greetings")
        self.nt_tone.addItem(T("Also friendly messages"), "friendly")
        self.nt_tone.setCurrentIndex(max(0, self.nt_tone.findData(self.cfg["newtab_greeting_tone"])))
        _row(f, T("Tone"), self.nt_tone,
             T("Friendly messages are short lines under the greeting: weather, small tips and curiosities."))
        self._holiday_rows(f)
        _row(f, "", self.nt_weather, T("The same switch as the “Weather on the new tab page” extension."))
        _row(f, T("City for the weather"), row,
             T("The weather comes from Open-Meteo (free, no account). Finding the city sends "
               "its name; after that only the coordinates of the city are sent, at most every "
               "30 minutes and only when a new tab is open. Your location is never asked."))
        f.addRow("", self.city_found)
        self._city_form = f
        self._show_found(False)
        _row(f, T("Temperature"), self.unit, T("Degrees Celsius or Fahrenheit."))
        self._background_rows(f)

    def _holiday_rows(self, f):
        """New tab page: the holidays to remember, one switch per tradition, all off at first (greeting.py)."""
        from . import greeting
        box, form = self._group(T("Holidays to remember"))
        note = QLabel(T("Choose the holidays you want remembered on the new tab page. "
                        "I.K.E. never guesses them by itself."))
        note.setWordWrap(True)
        form.addRow(note)
        chosen = self.cfg["greeting_holidays"]
        self.nt_holidays = {}
        for ident, name, hint in greeting.TRADITIONS:
            sw = Switch(T(name))
            sw.setChecked(ident in chosen)
            self.nt_holidays[ident] = sw
            _row(form, "", sw, T(hint) if hint else None)
        f.addRow(box)

    def _background_rows(self, f):
        """New tab page: a photo of the user's as its background (see newtabbg.py)."""
        from PyQt6.QtWidgets import QSlider

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
        _row(f, T("Background photo"), row, T("A copy is kept in I.K.E.'s own folder. It is never sent anywhere."))
        _row(f, T("Photo placement"), self.bg_fit, T("How the photo covers the page."))
        _row(f, T("Veil over the photo"), veil,
             T("A veil in the page's own colour over the photo, to keep the text readable"))
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
    def _whole_list(combo):
        """The open list of a narrowed combo box as wide as its longest entry
        (some styles open it only as wide as the box)."""
        view = combo.view()
        bar = view.verticalScrollBar().sizeHint().width()
        view.setMinimumWidth(min(view.sizeHintForColumn(0) + bar + 8, 900))

    @staticmethod
    def _narrow(combo):
        """A combo box with long entries must not make the page wider than the window."""
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(16)
        # Qt keeps a minimum size it worked out before (from the longest
        # entry) after the policy changes: the narrow one is set as the minimum
        combo.setMinimumWidth(combo.sizeHint().width())
        combo.setProperty("ike_elides", True)      # its entry may be cut short; its list shows it whole

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
        _row(f, T("Site tiles"), tiles,
             T("The most visited sites are worked out from the history kept on this computer"))
        _row(f, T("Blocked counter"), self.nt_counter,
             T("How many ads and trackers I.K.E. blocked, shown on the new tab page."))
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
        self._whole_list(combo)

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
        row.addWidget(InfoButton(T("Used for searches from the address bar and from the new tab page.")))
        lay.addLayout(row)
        self.suggest = Switch(T("Show search suggestions while typing"))
        self.suggest.setChecked(self.cfg["search_suggestions"])
        lay.addWidget(_with_hint(self.suggest,
                                 T("What you type is sent to the search engine, to get its suggestions.")))
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
        btns.addWidget(InfoButton(T("Type the keyword followed by a space in the address bar to "
                                    "search with that engine, e.g. “w Roma”.")))
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

    def _protection(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        f = QFormLayout()
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(T(LEVEL_NAMES[lv]), lv)
        self.level.setCurrentIndex(LEVELS.index(self.cfg["shield_level"]))
        _row(f, T("Default protection level"), self.level, T(
            "Off: nothing is blocked. Compatibility: ads, trackers and tracking links only. "
            "Balanced: also cross-site cookies and per-site noise on canvas, WebGL and audio. "
            "Strict: also generic hardware, screen, font and Client Hints values, no WebGPU. "
            "Maximum: also English as the only language. The shield in the "
            "toolbar changes the level for a single site."))
        lay.addLayout(f)
        self.checks = {}
        box, g = self._group(T("Connections and tracking"))
        for key, label, hint in (
            ("https_only", T("Upgrade connections to HTTPS when possible"),
             T("Pages open with a secure connection whenever the site offers one.")),
            ("block_third_party_cookies", T("Block cross-site (third-party) cookies"),
             T("Other sites inside a page cannot follow you from site to site with cookies.")),
            ("strip_tracking_params", T("Remove tracking parameters from links (utm_, fbclid, gclid…)"),
             T("Links lose the parts that only serve to follow you.")),
            ("trim_referrer", T("Send only the site origin as referrer to other sites"),
             T("Other sites learn which site you came from, not which page.")),
            ("send_gpc", T("Send the “Global Privacy Control” signal"),
             T("Asks sites not to sell or share your data. In some countries they must obey it.")),
            ("webrtc_hide_ip", T("Hide local IP addresses from WebRTC"),
             T("Video calls still work; sites do not see your address in the home network.")),
        ):
            c = Switch(label)
            c.setChecked(bool(self.cfg[key]))
            self.checks[key] = c
            _row(g, "", _wrapping(c), hint)
        lay.addWidget(box)
        box, g = self._group(T("Warnings and repairs"))
        for key, label, hint in (
            ("lookalike_warn", T("Warn about sites that imitate well-known ones"),
             T("A warning when an address imitates a known site, for example paypa1.com.")),
            ("repair_button", T("Show “Repair this site” in the shield"),
             T("It finds the protection that breaks a page and turns off only that one, only there.")),
        ):
            c = Switch(label)
            c.setChecked(bool(self.cfg[key]))
            self.checks[key] = c
            _row(g, "", _wrapping(c), hint)
        self.login_compat = Switch(T(
            "Make sign-in with Google, Microsoft and Apple accounts work (lighter protection on "
            "their sign-in pages only)"))
        self.login_compat.setChecked(bool(self.cfg["login_compat"]))
        _row(g, "", _wrapping(self.login_compat), T("Everywhere else the protection stays as it is."))
        lay.addWidget(box)

        fbox = QGroupBox(T("Ad and tracker blocker"))
        fl = QVBoxLayout(fbox)
        self.comp = {}
        c = Switch(T("Ad and tracker blocker — uses the uBlock Origin and EasyList filter lists"))
        c.setChecked(bool(self.cfg["comp_adblock"]))
        self.comp["comp_adblock"] = c
        fl.addWidget(_with_hint(_wrapping(c), T("Turn it off only to see whether it is what breaks a page.")))
        if not self.app.blocker.native:
            warn = QLabel(T("The I.K.E. AdBlock engine could not be loaded: only basic domain blocking is active."))
            warn.setStyleSheet("color:#c0392b")
            warn.setWordWrap(True)
            fl.addWidget(warn)
        fl.addLayout(_info_row(QLabel(T("Filter lists")), T(
            "The lists of rules the blocker uses. Untick a list to stop using it; "
            "they are updated by themselves (see Updates).")))
        self.lists = QListWidget()
        self.lists.setItemDelegate(SwitchDelegate(self.lists))       # a switch in place of the tick (1.1.21)
        self.lists.setMinimumHeight(120)
        for entry in self.cfg["filter_lists"]:
            self._add_list_item(entry)
        fl.addWidget(self.lists)
        row = QHBoxLayout()
        add = QPushButton(T("Add list from URL…"))
        rem = QPushButton(T("Remove selected"))
        reset = QPushButton(T("Restore defaults"))
        add.clicked.connect(self._add_list)
        rem.clicked.connect(lambda: self.lists.takeItem(self.lists.currentRow()))
        reset.clicked.connect(self._reset_lists)
        for b in (add, rem, reset):
            row.addWidget(b)
        row.addStretch(1)
        fl.addLayout(row)
        fl.addLayout(_info_row(QLabel(T("Your own filters (uBlock Origin / Adblock Plus syntax)")),
                               T("One rule per line. Your own rules are added to those of the lists.")))
        self.custom = QPlainTextEdit(self.cfg["custom_filters"])
        self.custom.setMaximumHeight(70)
        fl.addWidget(self.custom)
        lay.addWidget(fbox)
        lay.addStretch(1)
        return w

    def _privacy(self):
        w = QWidget()
        lay = QVBoxLayout(w)
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
        _row(f2, T("Encrypted DNS"), self.doh,
             T("Encrypted DNS (DNS over HTTPS). Pick a provider or type a custom URL."))
        self.containers = QLineEdit(", ".join(c["name"] for c in self.cfg["containers"]))
        _row(f2, T("Containers (comma separated)"), self.containers,
             T("Each container keeps its own cookies and logins"))
        lay.addLayout(f2)
        box, g = self._group(T("Permissions"))
        prow = QHBoxLayout()
        self.perm_block = {}
        labels = {"camera": T("Camera"), "microphone": T("Microphone"), "location": T("Location"),
                  "notifications": T("Notifications"), "clipboard": T("Clipboard"),
                  "screen": T("Screen"), "fonts": T("Local fonts")}
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()
        for i, kind in enumerate(PERMISSION_KINDS):
            c = Switch(labels[kind])
            c.setChecked(kind in self.cfg["perm_block"])
            self.perm_block[kind] = c
            grid.addWidget(_wrapping(c), i // 4, i % 4)
        prow.addLayout(grid)
        prow.addStretch(1)
        # 1.1.24: the name over the switches, which take the whole width of the box
        # (beside the names of the page's other options, set on one line, the
        # four columns were too narrow for "Microphone" in Tamil)
        g.addRow(QLabel(T("Always refuse:")))
        g.addRow(_with_hint(prow, T("Sites never get these, and you are not asked."), g.fieldGrowthPolicy()))
        sites = QPushButton(T("Reset per-site exceptions (%d)") % (
            len(self.cfg["site_levels"]) + len(self.cfg["site_noscript"])))
        sites.clicked.connect(lambda: (self.cfg["site_levels"].clear(),
                                       self.cfg["site_noscript"].clear(),
                                       sites.setText(T("Reset per-site exceptions (%d)") % 0)))
        perms = QPushButton(T("Site permissions…"))
        perms.clicked.connect(self.app.show_permissions)
        row = QHBoxLayout()
        row.addWidget(sites)
        row.addWidget(perms)
        row.addStretch(1)
        _row(g, "", row, T("Forget the protection levels and blocked scripts chosen for single sites, "
                           "or see what each site may use."))
        lay.addWidget(box)
        box, g = self._group(T("Browsing data"))
        c = Switch(T("Clear cookies, cache and history when I.K.E. is closed"))
        c.setChecked(bool(self.cfg["clear_on_exit"]))
        self.checks["clear_on_exit"] = c
        _row(g, "", _wrapping(c), T("Bookmarks, passwords and settings are kept."))
        clear = QPushButton(T("Clear browsing data…"))
        clear.clicked.connect(self.app.show_clear_data)
        crow = QHBoxLayout()
        crow.addWidget(clear)
        crow.addStretch(1)
        _row(g, "", crow, T("Choose what to delete now: history, cookies, cache, permissions."))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _extensions(self):
        """I.K.E. extensions: one card each (ikeextensions.py), then the experimental Chrome ones."""
        from . import ikeextensions
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(6)
        self.ext_switch = {}
        for e in ikeextensions.EXTENSIONS:
            lay.addWidget(self._ext_card(e))
        # the weather switch is also on the new tab page's own page: the two move together
        sw = self.ext_switch["weather"]
        sw.toggled.connect(lambda on: self.nt_weather.setChecked(on) if hasattr(self, "nt_weather") else None)
        if hasattr(self, "nt_weather"):
            self.nt_weather.toggled.connect(sw.setChecked)
        lay.addSpacing(8)
        lay.addWidget(self._chrome_box())
        lay.addStretch(1)
        return w

    def _ext_card(self, e):
        from . import ikeextensions
        card = QFrame()
        card.setObjectName("ike_ext_card")
        card.setProperty("ext", e.id)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 6, 10, 6)
        pic = QLabel()
        pic.setPixmap(ikeextensions.icon(e).pixmap(QSize(28, 28), self.devicePixelRatioF()))
        pic.setFixedSize(34, 34)
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        name = _WrapLabel(T(e.name))
        f = name.font()
        f.setBold(True)
        name.setFont(f)
        name.setWordWrap(True)
        text.addLayout(_info_row(name, T(e.description)))
        row.addLayout(text, 1)
        if e.options:
            b = QPushButton(T("Options…"))
            b.setToolTip(T("The options of “%s”") % T(e.name))
            b.clicked.connect(lambda _c=False, o=e.options: self._ext_options(o))
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        sw = Switch()
        sw.setChecked(ikeextensions.on(self.cfg, e.id))
        sw.setAccessibleName(T(e.name))
        sw.setToolTip(T("On or off"))
        row.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
        name.setBuddy(sw)
        self.ext_switch[e.id] = sw
        return card

    def _ext_options(self, where):
        kind, _sep, what = where.partition(":")
        if kind == "page":
            self.show_page(what)
        elif kind == "dialog":
            getattr(self.app, what)()

    def _chrome_box(self):
        ebox = QGroupBox(T("Extensions (experimental, Chrome format)"))
        el = QVBoxLayout(ebox)
        self.ext_on = Switch(T("Enable experimental support for Chrome extensions (Manifest V3)"))
        self.ext_on.setChecked(bool(self.cfg["experimental_extensions"]))
        el.addWidget(_with_hint(self.ext_on, T(
            "With the Qt WebEngine version tested (6.11) enabling an extension "
            "crashes the engine, so this is off by default. If you turn it on and "
            "the browser crashes, I.K.E. switches it off again at the next start. "
            "Only Manifest V3 extensions can be loaded: uBlock Origin, Dark Reader "
            "and Consent-O-Matic in their original form are not guaranteed to work.")))
        self._ext_mgr = self.app.extension_manager() if self.cfg["experimental_extensions"] else None
        if self._ext_mgr is None:
            return ebox
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
        return ebox

    def _drm_box(self):
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
        self._drm_refresh()
        return dbox

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
              "(update.googleapis.com, dl.google.com, gvt1.com) and stored in I.K.E.'s folder "
              "in your home directory. By installing it you accept Google's licence for it. Continue?")
        ) == QMessageBox.StandardButton.Yes

    def _drm_run(self, zip_path=None):
        from . import drm
        self.drm_install.setEnabled(False)
        self.drm_file.setEnabled(False)
        self.drm_label.setText(T("Installing Widevine…"))
        job = self._drm_job = drm.Installer(self, zip_path)
        job.finished_ok.connect(self._drm_done)
        job.up_to_date.connect(lambda v: self._drm_refresh(T("Widevine %s is already the newest version.") % v))
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
        self.dl_ask = Switch(T("Always ask where to save files"))
        self.dl_ask.setChecked(self.cfg["ask_download_location"])
        _row(f, T("Download folder"), row, T("Where files are saved. Empty: your Downloads folder."))
        _row(f, "", self.dl_ask, T("A window asks where to save each file, and under which name."))
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
        # I.K.E. extensions: each switch is its own setting (ikeextensions.py)
        from . import ikeextensions
        switched = []
        for e in ikeextensions.EXTENSIONS:
            on = self.ext_switch[e.id].isChecked()
            if ikeextensions.on(cfg, e.id) != on:
                switched.append(e.id)
            cfg[e.key] = on
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
        cfg["newtab_greeting"] = self.nt_greeting.isChecked()
        cfg["newtab_greeting_tone"] = self.nt_tone.currentData()
        cfg["greeting_holidays"] = [i for i, sw in self.nt_holidays.items() if sw.isChecked()]
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
        if switched:
            ikeextensions.changed(self.app, switched, settings_applied=True)
        if look != newtabbg.style(cfg) or page_look != newtab_look():
            self.app.reload_newtabs()


class UserScriptsDialog(QDialog):
    """The installed user scripts (I.K.E. extensions → User scripts → Options…).
    Whether they run at all is the extension's switch (userscripts_enabled)."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.setWindowTitle(T("User scripts") + " — I.K.E.")
        self.resize(780, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(self._userscripts(), 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _userscripts(self):
        us = self.app.userscripts
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(T(
            "A user script changes the pages it is written for. Install one from a file or from its "
            "address (for example from Greasy Fork), or simply open a link ending in “.user.js”. "
            "Installed scripts are checked for new versions once a day."))
        info.setWordWrap(True)
        lay.addLayout(_info_row(info, T("Whether they run at all: the “User scripts” switch in "
                                        "Settings → I.K.E. extensions."), stretch=True))
        self.us_list = QTreeWidget()
        self.us_list.setItemDelegate(SwitchDelegate(self.us_list))   # a switch in place of the tick (1.1.21)
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
        self.app.handoff.open_file(DIR, self)


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
        self.sys_font = Switch(T("Use the system font"))
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
        # the download belongs to the window: closed before the answer, the
        # request goes with it, and a late answer touches nothing of it (1.1.21:
        # a window closed while the list was coming wrote to a deleted label)
        reply.setParent(self)

        def finished():
            from PyQt6 import sip
            if sip.isdeleted(self) or sip.isdeleted(reply):
                return
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
        self.tree.currentItemChanged.connect(lambda *_a: self._handoff_buttons())
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        buttons = {}
        for key, label, slot in (("open", T("Open file"), lambda: self._open(False)),
                                 ("folder", T("Show in folder"), lambda: self._open(True)),
                                 ("app", "", self._open_with_app),
                                 ("cancel", T("Cancel download"), self._cancel),
                                 ("clear", T("Clear finished"), self._clear)):
            b = buttons[key] = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        # 1.1.24: "Show in folder" only with a file manager; an archive or a
        # calendar file also gets its app's button (Ark, the calendar)
        self.folder_button, self.app_button = buttons["folder"], buttons["app"]
        self.app_button.hide()
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
        self._handoff_buttons()

    def _handoff_buttons(self):
        """Show the handoffs the desktop has an app for (handoff.py): the file
        manager, and for a finished archive or calendar file its app."""
        from . import handoff
        S = QWebEngineDownloadRequest.DownloadState
        self.folder_button.setVisible(handoff.app_for("inode/directory") is not None)
        d = self._current()
        text = ""
        if d is not None and d.state() == S.DownloadCompleted:
            path = self.app.download_path(d)
            kind = handoff.kind_of(handoff.file_type(path)) if path.is_file() else ""
            if kind in ("archive", "calendar"):
                found = handoff.app_for(handoff.file_type(path).name())
                if found is not None:
                    text = T("Add to calendar") if kind == "calendar" else T("Open with %s") % found.name
        if self.app_button.text() != text:
            self.app_button.setText(text)
        self.app_button.setVisible(bool(text))

    def _open_with_app(self):
        d = self._current()
        if d is not None and self.app.download_path(d).is_file():
            self.app.handoff.open_file(self.app.download_path(d), self)

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
        """Open the file, or show it in its folder, through the desktop (handoff.py)."""
        d = self._current()
        handoff = self.app.handoff
        if d is None:
            if folder:        # nothing downloaded yet: show the download folder itself
                handoff.open_file(self.app.download_dir(), self)
            return
        path = self.app.download_path(d)
        if folder and path.is_file():
            handoff.show_in_folder(path, self)
            return
        target = path.parent if folder else path
        if not target.exists():
            target = path.parent if path.parent.exists() else self.app.download_dir()
        handoff.open_file(target, self)

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
        self.history = Switch(T("Browsing history"))
        self.cookies = Switch(T("Cookies and site data (you will be signed out of websites)"))
        self.cache = Switch(T("Cached images and files"))
        self.perms = Switch(T("Site permissions (camera, location, notifications…)"))
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


class AboutDialog(QDialog):
    """Help → About I.K.E. (1.1.21: in a scroll area, at most the size of the
    screen; the message box of earlier versions could run past its bottom)."""

    WIDTH = 600

    def __init__(self, icon, text, parent=None):
        from PyQt6.QtWidgets import QScrollArea
        super().__init__(parent)
        self.setWindowTitle(T("About I.K.E."))
        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        pic = QLabel(self)
        pic.setPixmap(icon.pixmap(QSize(64, 64), self.devicePixelRatioF()))
        pic.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        pic.setFixedWidth(80)
        body.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(self)
        self.label.setObjectName("ike_about_text")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                           | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeading)
        self.area = QScrollArea(self)
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setWidget(self.label)
        body.addWidget(self.area, 1)
        lay.addLayout(body, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.setText(text)

    def text(self):
        return self.label.text()

    def setText(self, text):
        """The text (the formats the engine plays come a moment later): the
        window grows with it, up to the free area of the screen."""
        from .uistyle import screen_area
        self.label.setText(text)
        area = screen_area(self.parentWidget() or self)
        width = min(self.WIDTH, area.width() - 140)
        bar = self.area.verticalScrollBar().sizeHint().width()
        need = self.label.heightForWidth(width - bar)
        chrome = 80 + self.fontMetrics().height() * 2
        height = min(need + chrome, area.height() - 60)
        self.resize(width + 110, max(220, height))
