"""Following the system, every icon of the interface is the desktop's own
(1.1.22, the owner's rule; tests/desktops.py lists the desktops).

Every window, menu and Settings page the text-fit test opens, and the
right-click menus of a page, a tab and the address bar, are opened in each
desktop, and every icon asked for through ike.icons.themed is checked:

- KDE Plasma (KDE's platform theme): it came from the theme, under a name
  Breeze itself has;
- every other desktop: Qt reports the desktop's icon theme, and the icon came
  from it, under a name that theme or a theme it inherits has (Inherits=, as
  the icon theme specification says, hicolor last); never from I.K.E.'s
  shipped glyphs, Qt's own icons or a theme outside that chain;
- no desktop (Qt alone, no icon theme): every icon is drawn, one of
  I.K.E.'s glyphs or, where I.K.E. has none, Qt's own; none is left empty.

A desktop whose platform theme or icon theme is not installed is skipped
(the Arch Linux job installs them all).
"""

from pathlib import Path

import desktops
import pytest
from conftest import screen
from test_text_fit import SCREEN, SCRIPTS, STEPS, TESTS

BREEZE_DIRS = [Path("/usr/share/icons/breeze"), Path("/usr/share/icons/breeze-dark")]


def breeze_names():
    names = set()
    for d in BREEZE_DIRS:
        if d.is_dir():
            for f in d.rglob("*"):
                if f.suffix in (".svg", ".png") or f.is_symlink():
                    names.add(f.name.rsplit(".", 1)[0])
    return names


# the menus the text-fit test does not open: a page's right-click menu (on
# the page, a link, an image, a video, a text field with a selection), a
# tab's and the address bar's
MENUS = r"""
    from ike import contextmenu, icons
    from PyQt6.QtCore import QEvent, QPoint, QTimer, QUrl
    from PyQt6.QtGui import QContextMenuEvent, QIcon
    from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as Req
    win = ike.new_window()
    win.show()
    yield 300

    class Request:                     # what contextmenu.build reads of Qt's request
        def __init__(self, **kw):
            self.kw = kw
        def linkUrl(self):
            return QUrl(self.kw.get("link", ""))
        def mediaUrl(self):
            return QUrl(self.kw.get("media", ""))
        def mediaType(self):
            return self.kw.get("kind", Req.MediaType.MediaTypeNone)
        def selectedText(self):
            return self.kw.get("text", "")
        def isContentEditable(self):
            return self.kw.get("edit", False)
        def editFlags(self):
            return Req.EditFlag(0)
        def mediaFlags(self):
            return Req.MediaFlag(0)
        def misspelledWord(self):
            return ""
        def spellCheckerSuggestions(self):
            return []
        def position(self):
            return QPoint(10, 10)
    view = win.current_view()
    for req in (None, Request(link="https://example.com/"),
                Request(kind=Req.MediaType.MediaTypeImage, media="https://example.com/a.png"),
                Request(kind=Req.MediaType.MediaTypeVideo, media="https://example.com/a.webm"),
                Request(edit=True, text="example.com")):
        contextmenu.build(view, req).deleteLater()

    def close_menu():
        shown = QApplication.activePopupWidget()
        if shown is not None:
            shown.close()
        else:
            QTimer.singleShot(50, close_menu)
    QTimer.singleShot(100, close_menu)
    win._tab_menu(0, win.mapToGlobal(QPoint(40, 40)))
    QTimer.singleShot(100, close_menu)
    win.urlbar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                                                  win.urlbar.mapToGlobal(QPoint(5, 5))))
    win.close()
    yield 50
    out["theme"] = QIcon.themeName()
    out["icons"] = [[list(k), v[0], v[1]] for k, v in icons.seen.items()]
"""


def icons_seen(run_ike, env):
    """Open everything in English; Qt's icon theme and [names, source, used] of every icon."""
    script = (STEPS.replace("TESTS", repr(str(TESTS))).replace("LANGS", repr(["en"]))
              .replace("SCRIPTS", repr(SCRIPTS))
              .replace('    out["problems"] = problems\n', '    out["problems"] = problems\n' + MENUS))
    return run_ike(script, env=env, timeout=600)


def report(wrong, what):
    lines = "\n".join("%s -> %s %s" % (", ".join(n), s, u) for n, s, u in wrong)
    return "%d icons not %s:\n%s" % (len(wrong), what, lines)


def test_every_icon_is_kdes_own_on_kde(run_ike, tmp_path):
    have = breeze_names()
    if not have or not Path("/usr/lib/qt6/plugins/platformthemes/KDEPlasmaPlatformTheme6.so").exists():
        pytest.skip("KDE's Breeze icons and platform theme are not installed here")
    env = dict(screen(tmp_path, *SCREEN), QT_QPA_PLATFORMTHEME="kde")
    out = icons_seen(run_ike, env)
    if not str(out.get("theme", "")).startswith("breeze"):
        pytest.skip("KDE's theme did not load here (icon theme %r)" % out.get("theme"))
    assert len(out["icons"]) > 40, len(out["icons"])
    wrong = [[names, source, used] for names, source, used in out["icons"]
             if source != "theme" or used not in have]
    assert not wrong, report(wrong, "from KDE's theme")


@pytest.mark.parametrize("desktop", [d for d in desktops.DESKTOPS if d != "kde"])
def test_every_icon_is_the_desktops_own(run_ike, tmp_path, desktop):
    try:
        env = desktops.prepare(desktop, tmp_path / "home")
    except desktops.Unavailable as why:
        pytest.skip(str(why))
    env.update(screen(tmp_path, *SCREEN))
    out = icons_seen(run_ike, env)
    want = desktops.DESKTOPS[desktop]["icons"]
    assert out["theme"] == want, "Qt reports the icon theme %r, not %s's %r" % (out["theme"], desktop, want)
    assert len(out["icons"]) > 40, len(out["icons"])
    if not want:                       # Qt alone: I.K.E.'s glyphs, Qt's own where it has none
        wrong = [x for x in out["icons"] if x[1] not in ("own", "qt")]
        assert not wrong, report(wrong, "drawn without an icon theme")
        return
    themes = desktops.chain(want)
    allowed = set().union(*(desktops.names(t) for t in themes))
    wrong = [[names, source, used] for names, source, used in out["icons"]
             if source != "theme" or used not in allowed]
    assert not wrong, report(wrong, "from %s (%s)" % (want, " > ".join(themes)))
