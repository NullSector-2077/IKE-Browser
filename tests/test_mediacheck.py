"""Help → About tells which video and audio formats the engine plays and how
old the engine is (ike/mediacheck.py). The engine is asked in a blank page of
a throw-away private profile, never in a web page: a page that tampers with
its own media functions changes nothing."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# a page that lies about every format and tries to reach the probe
HOSTILE = b"""<!doctype html><html><body><script>
HTMLMediaElement.prototype.canPlayType = function () { return "probably"; };
if (window.MediaSource) MediaSource.isTypeSupported = function () { return true; };
JSON.stringify = function () { return '{"video/mp4; codecs=\\"avc1.42E01E\\"": true}'; };
</script>hostile</body></html>"""


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HOSTILE)))
            self.end_headers()
            self.wfile.write(HOSTILE)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_parse_takes_only_true_answers():
    import ike.mediacheck as mc
    names = [n for n, _m in mc.FORMATS]
    assert mc.parse("not json") == {} and mc.parse("[1, 2]") == {} and mc.parse(None) == {}
    everything = {m: True for _n, m in mc.FORMATS}
    assert mc.parse(__import__("json").dumps(everything)) == {n: True for n in names}
    odd = {mc.FORMATS[0][1]: "yes", mc.FORMATS[1][1]: 1, mc.FORMATS[2][1]: True}
    got = mc.parse(__import__("json").dumps(odd))
    assert got[names[0]] is False and got[names[1]] is False and got[names[2]] is True
    assert set(got) == set(names)
    yes, no = mc.split({"VP9": True, "H.264": False})
    assert yes == ["VP9"] and no[0] == "H.264" and "VP9" not in no


def test_about_shows_formats_and_engine_age(run_ike, site):
    out = run_ike("""
        def steps(ike, qapp, out):
            from PyQt6.QtCore import Qt, QTimer, QUrl
            from PyQt6.QtTest import QTest
            import ike.mediacheck as mc
            from ike import chromever
            win = ike.windows[0]
            # a hostile page is open in the current tab
            win.current_view().load(QUrl("http://127.0.0.1:%d/"))
            yield 1500
            out["before"] = mc.known()
            out["text_before"] = win.about_text()
            menu = win.burger
            out["entries"] = [a.text() for a in menu.actions()]
            out["help"] = [a.text() for a in win.m_help_burger.actions()]
            menu.popup(win.mapToGlobal(win.rect().center()))
            yield 300
            menu.setActiveAction(win.act_about)
            # Return opens the dialog, which runs its own loop.
            QTimer.singleShot(0, lambda: QTest.keyClick(menu, Qt.Key.Key_Return))
            box = None
            for _ in range(40):
                yield 100
                box = getattr(win, "_about_box", None)
                if box is not None:
                    break
            out["opened"] = box is not None
            out["text_open"] = box.text() if box else ""
            for _ in range(150):
                yield 100
                if mc.known() is not None:
                    break
            yield 200
            out["text_answered"] = box.text() if box else ""
            out["known"] = mc.known()
            out["probes_left"] = len([o for o in win.children() if o.__class__.__name__ == "Probe"])
            QTest.keyClick(box, Qt.Key.Key_Escape)
            yield 300
            out["closed"] = getattr(win, "_about_box", None) is None and not box.isVisible()
            # a second About asks nothing again
            out["text_again"] = win.about_text()
            out["behind"] = chromever.latest(ike.config) - chromever.security_major()     # 1.1.18: by the security fixes
            # 1.1.14: sites see the engine's own version, the same everywhere
            out["ua"] = ike.profile.httpUserAgent()
            out["engine"] = chromever.engine_major()
            out["presented"] = chromever.current(ike.config)
    """ % site)
    assert out["entries"][-2:] == ["About I.K.E.", "Quit"]
    assert "About I.K.E." not in out["help"]
    assert out["before"] is None
    assert "Video and audio formats: checking…" in out["text_before"]
    assert out["opened"]
    known = out["known"]
    assert known is not None, "the engine did not answer"
    # these play in every build of Qt WebEngine (royalty-free formats)
    for name in ("VP9", "AV1", "Opus", "MP3"):
        assert known[name] is True, name
    # each format named once, on the right line
    answered = out["text_answered"]
    plays = answered.split("Plays: ")[1].split("<br>")[0]
    for name, ok in known.items():
        assert (name in plays) == ok, name
    if not all(known.values()):
        assert "Does not play: " in answered
    assert out["probes_left"] == 0
    assert out["closed"]
    assert "checking" not in out["text_again"] and "Plays: " in out["text_again"]
    # 1.1.14: the components I.K.E. is built on, with their licences
    assert "Components and licences" in answered and "adblock-rust (Brave Software)" in answered
    assert "MPL-2.0" in answered and "Dark Reader" in answered
    assert out["presented"] == out["engine"]
    assert ("Chrome/%d.0.0.0 " % out["engine"]) in out["ua"], out["ua"]
    behind = out["behind"]
    if behind > 0:
        assert ("Engine age: %d Chrome versions behind the current one" % behind) in answered
    else:
        assert "Engine age: as recent as the current Chrome" in answered


def test_answer_is_the_engines_not_the_pages(run_ike, site):
    """The engine of the tests (Qt's own build, PyPI) does not play H.264 / AAC;
    with a page claiming the opposite open, the report still says no."""
    out = run_ike("""
        def steps(ike, qapp, out):
            from PyQt6.QtCore import QUrl
            import ike.mediacheck as mc
            win = ike.windows[0]
            win.current_view().load(QUrl("http://127.0.0.1:%d/"))
            yield 1500
            got = []
            mc.ask(win, got.append)
            for _ in range(150):
                yield 100
                if got:
                    break
            out["got"] = got
            # the page's own answer, for comparison
            res = []
            win.current_view().page().runJavaScript(
                'document.createElement("video").canPlayType(\\'video/mp4; codecs="avc1.42E01E"\\')', res.append)
            yield 500
            out["page_says"] = res
    """ % site)
    assert out["got"] and out["got"][0]
    assert out["page_says"] == ["probably"]          # the page did lie
    from importlib.metadata import PackageNotFoundError, version
    try:
        version("PyQt6-WebEngine-Qt6")
        pypi_qt = True
    except PackageNotFoundError:
        pypi_qt = False
    if pypi_qt:
        assert out["got"][0]["H.264"] is False and out["got"][0]["AAC"] is False
