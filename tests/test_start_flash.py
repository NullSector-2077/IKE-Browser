"""No white flash at the start (1.1.23, the owner's request): before the new
tab page paints, its view showed the engine's white for about 0.1 s, at every
start and every new tab, on a dark interface too. The page's colour before it
paints is now the new tab page's own (the interface's window colour, or the
I.K.E. theme's behind I.K.E.'s own photo), whatever the dark mode; a site in
light mode keeps white between pages.

The frames are taken from the first turn of the event loop after the window
is shown (IKE_TEST_DELAY=0), every few milliseconds, until well after the
page has loaded."""

import http.server
import threading

import pytest

from ike.uistyle import contrast

FRAMES = r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    t0 = time.monotonic()
    win = ike.windows[0]

    def look(v):
        img = v.grab().toImage()
        if img.isNull():
            return []
        w, h = img.width(), img.height()
        # the page's own background, away from the search box and the tiles
        return [img.pixelColor(w // 20, h * k // 4).name() for k in (1, 2, 3)]

    def watch(v, until):
        done = {}
        v.loadFinished.connect(lambda ok: done.setdefault("t", time.monotonic()))
        frames = []
        start = time.monotonic()
        while time.monotonic() - start < 8:
            frames.append([round(time.monotonic() - t0, 3), look(v), v.page().backgroundColor().name(),
                           [v.width(), v.height()]])
            if "t" in done and time.monotonic() > done["t"] + until:
                break
            yield 5
        out.setdefault("frames", []).append(frames)
        out.setdefault("loaded", []).append("t" in done)

    v = win.current_view()
    out["first_backdrop"] = v.page().backgroundColor().name()
    yield from watch(v, 1.0)
    # a new tab later, as the "+" button opens it
    v2 = win.add_tab()
    out["new_backdrop"] = v2.page().backgroundColor().name()
    yield from watch(v2, 1.0)
    out["newtab_bg"] = ike.shields.newtab_background().name()
    # a site from the new tab page: white between pages in light mode, as before
    v2.load(QUrl("http://127.0.0.1:%d/"))
    yield 1500
    out["site_backdrop"] = v2.page().backgroundColor().name()
'''


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<title>p</title><p>a page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _lightness(name):
    r, g, b = (int(name[i:i + 2], 16) for i in (1, 3, 5))
    return (max(r, g, b) + min(r, g, b)) / 2


def _run(run_ike, site, **settings):
    out = run_ike(FRAMES % site, settings=dict({"https_only": False}, **settings),
                  # Two 4K background images can exceed a headless container's shared memory.
                  env={"IKE_TEST_DELAY": "0", "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-dev-shm-usage"}, timeout=90)
    assert out["loaded"] == [True, True], out["loaded"]
    assert all(len(f) > 5 for f in out["frames"]), out["frames"]
    # The page never jumps (1.1.23): the bookmarks bar of the new tab page
    # went away when the page started loading and came back a moment later,
    # so the view grew by its height and shrank again; a frame taken in
    # between showed what the engine had not painted yet at the new size
    # (transparent, or a foreign colour such as #dee246). Once the window
    # has its width, the view keeps one size.
    for frames in out["frames"]:
        final = frames[-1][3]
        sizes = [f[3] for f in frames if f[3][0] == final[0]]
        assert all(size == final for size in sizes), [(f[0], f[3]) for f in frames]
    return out


@pytest.mark.parametrize("scheme,photo,dark", [
    ("theme:night", "", "off"),           # a dark interface (Breeze Dark and the like)
    ("theme:night", "", "on"),
    ("system", "default", "off"),         # I.K.E.'s own photo on a light interface: a dark page
    ("theme:night", "default", "off"),
])
def test_a_dark_new_tab_page_is_dark_from_the_first_frame(run_ike, site, scheme, photo, dark):
    out = _run(run_ike, site, ui_scheme=scheme, newtab_bg=photo, dark_mode=dark)
    bg = out["newtab_bg"]
    assert _lightness(bg) < 60, bg
    assert out["first_backdrop"] == bg and out["new_backdrop"] == bg, out
    for frames in out["frames"]:
        for t, seen, backdrop, _size in frames:
            assert backdrop == bg, (t, backdrop)
            if photo:
                # Saturated blue pixels can have high HSL lightness while remaining visibly dark.
                # White and the bright unpainted colours still fail this check.
                assert all(contrast(c, "#ffffff") >= 7 for c in seen), (t, seen, frames[:5])
            else:
                assert all(_lightness(c) < 60 for c in seen), (t, seen, frames[:5])
    assert out["site_backdrop"] == ("#181a1b" if dark == "on" else "#ffffff"), out["site_backdrop"]


@pytest.mark.parametrize("dark", ["off", "on"])
def test_a_light_new_tab_page_starts_in_its_own_colour(run_ike, site, dark):
    """A light interface without the photo: the page's own light grey from
    the first frame, never the engine's white before it; sites in light mode
    keep white between pages."""
    out = _run(run_ike, site, ui_scheme="system", newtab_bg="", dark_mode=dark)
    bg = out["newtab_bg"]
    assert bg != "#ffffff" and out["first_backdrop"] == bg and out["new_backdrop"] == bg, out
    for frames in out["frames"]:
        for t, seen, backdrop, _size in frames:
            assert backdrop == bg and all(c == bg for c in seen), (t, seen, backdrop)
    assert out["site_backdrop"] == ("#181a1b" if dark == "on" else "#ffffff"), out["site_backdrop"]
