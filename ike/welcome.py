"""The first start (1.1.24): a short welcome in four steps, shown once.

1. the language of I.K.E. (the computer's, confirmed or changed);
2. how much I.K.E. blocks (Compatibility, Balanced, Strict), one plain line each;
3. the search engine;
4. I.K.E. as the default browser, only if the user wants it.

"Skip" keeps everything as it is. Every choice is also in the Settings. It
is shown before the first window, so the language chosen is the one the
windows open in; it never comes back ("welcome_done", set for every profile
that already had settings when 1.1.24 arrived: config.py).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import i18n
from .config import LEVEL_NAMES
from .i18n import T
from .uistyle import Switch

STEPS = 4
LEVELS = ("compatibility", "balanced", "strict")


def wanted(config):
    return not config["welcome_done"]


def level_line(level):
    """One plain line about a protection level, for the welcome."""
    return {"compatibility": T("Blocks ads and trackers. For sites that do not work otherwise."),
            "balanced": T("Also stops sites from recognising you. Best for most people."),
            "strict": T("Blocks even more. A few sites may not work well.")}[level]


class WelcomeDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.setObjectName("ike_welcome")
        self.setModal(True)
        self.step = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 14)
        lay.setSpacing(10)
        self.head = QLabel()
        f = self.head.font()
        f.setPointSizeF(f.pointSizeF() * 1.5)
        f.setBold(True)
        self.head.setFont(f)
        self.head.setWordWrap(True)
        lay.addWidget(self.head)
        self.count = QLabel()
        lay.addWidget(self.count)
        self.question = QLabel()
        self.question.setWordWrap(True)
        q = self.question.font()
        q.setPointSizeF(q.pointSizeF() * 1.15)
        self.question.setFont(q)
        lay.addWidget(self.question)
        self.pages = QStackedWidget(self)
        lay.addWidget(self.pages, 1)

        # 1. language
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.language = QComboBox()
        self.language.addItem("English", "en")
        for code, name in i18n.installed_packs():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(i18n.current())))
        self._start_lang = i18n.current()
        self.language.currentIndexChanged.connect(self._language_changed)
        pl.addWidget(self.language)
        pl.addStretch(1)
        self.pages.addWidget(page)

        # 2. protection
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.levels = QButtonGroup(self)
        self.level_rows = {}
        current = self.cfg["shield_level"] if self.cfg["shield_level"] in LEVELS else "balanced"
        for lv in LEVELS:
            r = QRadioButton()
            r.setChecked(lv == current)
            r.setProperty("level", lv)
            self.levels.addButton(r)
            line = QLabel()
            line.setWordWrap(True)
            line.setContentsMargins(26, 0, 0, 6)
            line.setBuddy(r)
            self.level_rows[lv] = (r, line)
            pl.addWidget(r)
            pl.addWidget(line)
        pl.addStretch(1)
        self.pages.addWidget(page)

        # 3. search engine
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.engine = QComboBox()
        for e in self.cfg["search_engines"]:
            self.engine.addItem(app.engine_icon(e), e["name"], e["name"])
        self.engine.setCurrentIndex(max(0, self.engine.findData(self.cfg.engine()["name"])))
        pl.addWidget(self.engine)
        pl.addStretch(1)
        self.pages.addWidget(page)

        # 4. default browser (never ticked by itself)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.default = Switch()
        self.default.setChecked(False)
        pl.addWidget(self.default)
        pl.addStretch(1)
        self.pages.addWidget(page)

        self.later = QLabel()
        self.later.setWordWrap(True)
        self.later.setEnabled(False)               # the quieter colour of a note
        lay.addWidget(self.later)
        row = QHBoxLayout()
        self.skip = QPushButton()
        self.skip.clicked.connect(self.skip_all)
        self.back = QPushButton()
        self.back.clicked.connect(lambda: self.go(self.step - 1))
        self.next = QPushButton()
        self.next.setDefault(True)
        self.next.clicked.connect(lambda: self.go(self.step + 1) if self.step + 1 < STEPS else self.finish())
        row.addWidget(self.skip)
        row.addStretch(1)
        row.addWidget(self.back)
        row.addWidget(self.next)
        lay.addLayout(row)
        self.chosen = False
        self.retranslate()
        self.go(0)
        from .uistyle import fit_window
        fit_window(self, 560, 400)

    def retranslate(self):
        """Every text, in the language chosen at step 1."""
        self.setWindowTitle(T("Welcome to I.K.E."))
        self.head.setText(T("Welcome to I.K.E."))
        for lv, (r, line) in self.level_rows.items():
            r.setText(T(LEVEL_NAMES[lv]))
            line.setText(level_line(lv))
        self.default.setText(T("Make I.K.E. the default browser"))
        self.later.setText(T("You can change all of this later in Settings."))
        self.skip.setText(T("Skip"))
        self.back.setText(T("Back"))
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.right_to_left()
                                else Qt.LayoutDirection.LeftToRight)
        self.go(self.step)

    @staticmethod
    def questions():
        return (T("Which language should I.K.E. use?"), T("How much should I.K.E. block?"),
                T("Which search engine should I.K.E. use?"),
                T("Should links from other programs open in I.K.E.?"))

    def go(self, step):
        self.step = max(0, min(STEPS - 1, step))
        self.pages.setCurrentIndex(self.step)
        self.count.setText(T("Step %d of %d") % (self.step + 1, STEPS))
        self.question.setText(self.questions()[self.step])
        self.back.setVisible(self.step > 0)
        self.next.setText(T("Done") if self.step == STEPS - 1 else T("Next"))

    def _language_changed(self, _i):
        code = self.language.currentData()
        i18n.setup(code)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if i18n.right_to_left() else Qt.LayoutDirection.LeftToRight)
        self.retranslate()

    def chosen_level(self):
        b = self.levels.checkedButton()
        return b.property("level") if b is not None else "balanced"

    def skip_all(self):
        """Nothing changes but the language already shown: it is the computer's."""
        if self.language.currentData() != self._start_lang:
            self.language.setCurrentIndex(max(0, self.language.findData(self._start_lang)))
        self.reject()

    def finish(self):
        cfg = self.cfg
        if self.language.currentData() != self._start_lang:
            cfg["language"] = self.language.currentData()
        level = self.chosen_level()
        if level != cfg["shield_level"]:
            cfg["shield_level"] = level
            self.app.shields.apply_settings()
        cfg["default_engine"] = self.engine.currentData() or cfg["default_engine"]
        self.chosen = True
        if self.default.isChecked():
            from .handoff import set_default_browser
            try:
                set_default_browser()
            except Exception:
                QMessageBox.warning(self, "I.K.E.", T(
                    "Could not change the default browser. Set it in System Settings → Default Applications."))
        self.accept()


def show_first(app, then):
    """Show the welcome over nothing (the first window opens after it), then
    run then(). Never shown again, whatever the answer."""
    from PyQt6.QtWidgets import QApplication
    qapp = QApplication.instance()
    quit_last = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)          # the welcome closes before the first window opens
    dlg = WelcomeDialog(app)
    app.welcome = dlg

    def done(_result):
        app.welcome = None
        app.config["welcome_done"] = True
        app.config.save()
        dlg.deleteLater()
        then()
        qapp.setQuitOnLastWindowClosed(quit_last)
    dlg.finished.connect(done)
    dlg.show()
    return dlg
