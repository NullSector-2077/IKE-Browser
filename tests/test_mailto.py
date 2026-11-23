"""Email links (1.1.16): a "mailto:" link is written with the web mail or the
mail program the user chose, as other browsers do; I.K.E. asks until a choice
is remembered, and can also take the email links of other programs."""

import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT))
from ike import mailto  # noqa: E402

LINK = "mailto:arc@example.it,b@example.org?subject=Ciao%20mondo&body=riga1%0Ariga2%20%26%20altro&cc=c@example.org"


def test_the_parts_of_an_email_link():
    f = mailto.fields(LINK)
    assert f == {"to": "arc@example.it,b@example.org", "cc": "c@example.org", "bcc": "",
                 "subject": "Ciao mondo", "body": "riga1\nriga2 & altro"}
    assert mailto.fields("mailto:?To=x@y.it&SUBJECT=a")["to"] == "x@y.it"
    assert mailto.fields("http://x.it/") == dict.fromkeys(mailto.FIELDS, "")


def test_each_service_gets_the_whole_email():
    gmail = mailto.compose_url("gmail", LINK)
    assert gmail.startswith("https://mail.google.com/mail/?extsrc=mailto&url=mailto%3A")
    assert mailto.compose_url("proton", LINK).startswith("https://mail.proton.me/inbox/#mailto=mailto%3A")
    for key, base in (("outlook", "https://outlook.live.com/mail/0/deeplink/compose?"),
                      ("yahoo", "https://compose.mail.yahoo.com/?")):
        url = mailto.compose_url(key, LINK)
        assert url == base + ("to=arc%40example.it%2Cb%40example.org&cc=c%40example.org"
                              "&subject=Ciao%20mondo&body=riga1%0Ariga2%20%26%20altro"), url
    # nothing from the link can change the service's address
    trick = "mailto:x@y.it?body=a#@evil.example/&to=z"
    for key, _name in mailto.SERVICES:
        url = mailto.compose_url(key, trick)
        assert url.split("?")[0].split("#")[0] in (
            "https://mail.google.com/mail/", "https://mail.proton.me/inbox/",
            "https://outlook.live.com/mail/0/deeplink/compose", "https://compose.mail.yahoo.com/"), url
    assert mailto.compose_url("elsewhere", LINK) is None
    assert len(mailto.compose_url("gmail", "mailto:a@b.it?body=" + "x" * 50000)) < 3 * mailto.MAX_LEN


def test_the_desktop_can_hand_email_links_to_ike():
    desktop = (ROOT / "data" / "ike-browser.desktop").read_text("utf-8")
    assert "x-scheme-handler/mailto;" in desktop


STEPS = r'''
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl, pyqtSlot
from PyQt6.QtGui import QMouseEvent

class Desktop(QObject):
    def __init__(self):
        super().__init__()
        self.started = []
    @pyqtSlot(QUrl)
    def handle(self, url):
        self.started.append(bytes(url.toEncoded()).decode())

def click(view, x, y):
    target = view.focusProxy() or view
    for kind, held in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                       (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(target, QMouseEvent(kind, QPointF(x, y), QPointF(view.mapToGlobal(QPointF(x, y).toPoint())),
                                                       Qt.MouseButton.LeftButton, held, Qt.KeyboardModifier.NoModifier))

PAGE = ("<body style='margin:0'><a href='mailto:arc@example.it?subject=Ciao' "
        "style='display:block;width:400px;height:120px;background:#ccc'>write</a>")

def steps(ike, qapp, out):
    from ike import mailto, webview
    desktop = Desktop()
    ike._desktop_stand_in = desktop
    # 1.1.24: links of other kinds go to the desktop portal (handoff.py), never through
    # Qt's QDesktopServices (xdg-open): the stand-in takes the portal's place
    ike.handoff.open_uri = lambda url, parent=None: desktop.handle(QUrl(url))
    win = ike.windows[0]
    opened = []
    real_add = win.add_tab
    def add_tab(url="ike:newtab", **kw):
        opened.append(str(url))
        return real_add("ike:newtab", **kw)          # no real web mail in the tests
    win.add_tab = add_tab
    chosen = []
    answer = [("proton", True)]
    def choose(parent, address, from_desktop=False):
        chosen.append([address, from_desktop])
        return answer[0]
    mailto.choose = choose
    asked = []
    webview.WebPage.ask_external = lambda self, origin, url: asked.append(origin) or True

    # the link given at start-up by another program (I.K.E. as the system's handler),
    # with Proton Mail chosen in the settings
    yield 1200
    out["start"] = [v.url().toString() for v in win.views]
    for v in list(win.views):
        if v.url().host() == "mail.proton.me":
            win.close_tab(v)
    yield 300

    view = win.current_view()
    view.setHtml(PAGE, QUrl("http://site.example/page"))
    yield 800
    # chosen in the settings: Proton Mail, without asking
    click(view, 60, 60)
    yield 500
    out["proton"] = [list(chosen), list(opened), ike.config["mail_handler"]]
    del opened[:]

    # the computer's mail program: the usual question, then the desktop
    ike.config["mail_handler"] = "system"
    win.set_current(view)
    yield 300
    click(view, 60, 60)
    yield 500
    out["system"] = [list(asked), list(desktop.started), list(opened)]

    # asked each time; cancelled: nothing at all
    ike.config["mail_handler"] = "ask"
    answer[0] = (None, False)
    click(view, 60, 60)
    yield 500
    out["cancel"] = [len(chosen), list(opened), len(desktop.started), ike.config["mail_handler"]]

    # from another program with "the computer's mail program" chosen: never handed back
    ike.config["mail_handler"] = "system"
    ike.open_urls(["mailto:x@example.it"])
    yield 400
    out["loop"] = [chosen[-1], len(desktop.started)]

    # asked, then remembered
    ike.config["mail_handler"] = "ask"
    answer[0] = ("gmail", True)
    del opened[:]
    win.set_current(view)
    yield 300
    click(view, 60, 60)
    yield 500
    out["remembered"] = [ike.config["mail_handler"], list(opened)]

    # the setting
    dlg = ike.show_settings(win)
    yield 200
    out["combo"] = [dlg.mail.itemData(i) for i in range(dlg.mail.count())]
    dlg.mail.setCurrentIndex(dlg.mail.findData("gmail"))
    dlg.apply()
    out["saved"] = ike.config["mail_handler"]
    dlg.close()
'''


def test_email_links_go_to_the_chosen_service(run_ike):
    out = run_ike(STEPS, args=["mailto:start@example.it?subject=Da%20Dolphin"], timeout=120,
                  settings={"mail_handler": "proton"})
    assert any(u.startswith("https://mail.proton.me/inbox/#mailto=mailto%3Astart%40example.it")
               for u in out["start"]), out["start"]
    assert out["proton"][0] == [] and out["proton"][2] == "proton", out["proton"]
    assert out["proton"][1] == [mailto.compose_url("proton", "mailto:arc@example.it?subject=Ciao")]
    asked, started, opened = out["system"]
    assert asked == ["http://site.example"] and started == ["mailto:arc@example.it?subject=Ciao"] and opened == []
    assert out["cancel"] == [1, [], 1, "ask"], out["cancel"]
    assert out["loop"] == [["x@example.it", True], 1], out["loop"]
    assert out["remembered"] == ["gmail", [mailto.compose_url("gmail", "mailto:arc@example.it?subject=Ciao")]]
    assert out["combo"] == ["ask", "gmail", "outlook", "proton", "yahoo", "system"]
    assert out["saved"] == "gmail"
