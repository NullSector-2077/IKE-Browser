"""A photo of the user's behind the new tab page (ike/newtabbg.py): choosing,
replacing and removing it, files that cannot be used, how it is shown, that
the interface colours do not change, that it survives a restart, and that a
web page cannot get at it."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")

MAKE = r'''
import json, os
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QImage, QPainter

WORK = os.environ["IKE_BG_WORK"]

def picture(name, w, h, colour="#c02020", alpha=False, fmt=None):
    img = QImage(w, h, QImage.Format.Format_ARGB32 if alpha else QImage.Format.Format_RGB32)
    img.fill(QColor(0, 0, 0, 0) if alpha else QColor(colour))
    p = QPainter(img)
    p.fillRect(w // 4, h // 4, w // 2, h // 2, QColor(colour))
    p.end()
    path = os.path.join(WORK, name)
    assert img.save(path, fmt) if fmt else img.save(path), name
    return path

def js(view, code):
    box = {}
    view.page().runJavaScript(code, lambda r: box.setdefault("r", r))
    while "r" not in box:
        yield 20
    return box["r"]

LOOK = """JSON.stringify((function () {
    var h = getComputedStyle(document.documentElement), b = getComputedStyle(document.body),
        v = getComputedStyle(document.body, "::before"), root = getComputedStyle(document.documentElement);
    return {image: h.backgroundImage, size: h.backgroundSize, repeat: h.backgroundRepeat,
            position: h.backgroundPosition, attachment: h.backgroundAttachment,
            veil: v.content === "none" ? null : v.opacity, veilColour: v.backgroundColor,
            body: b.backgroundColor, text: b.color,
            vars: ["--bg", "--fg", "--mute", "--card", "--line", "--acc"].map(function (n) {
                return root.getPropertyValue(n).trim(); }),
            input: getComputedStyle(document.querySelector("input")).backgroundColor,
            clock: getComputedStyle(document.querySelector(".corner")).color};
})())"""
'''


def test_files_that_can_and_cannot_be_used(run_ike, tmp_path):
    work = tmp_path / "pictures"
    work.mkdir()
    (work / "notes.jpg").write_text("this is not a picture, whatever its name says\n" * 50)
    (work / "empty.png").write_bytes(b"")
    (work / "cut.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    (work / "drawing.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    (work / "folder.jpg").mkdir()
    out = run_ike(MAKE + r'''
def steps(ike, qapp, out):
    yield 300
    from pathlib import Path
    from ike import newtabbg
    cfg, data = ike.config, Path(os.environ["XDG_DATA_HOME"]) / "ike-browser"
    def stored():
        return sorted(p.name for p in data.iterdir() if p.name.startswith(newtabbg.NAME))
    def size_of(name):
        img = QImage(str(data / name))
        return [img.width(), img.height(), img.hasAlphaChannel()]
    out["none"] = [newtabbg.current(cfg) is None, newtabbg.style(cfg), newtabbg.content(cfg) == (None, None)]

    # a photo from a camera: far larger than the screen
    big = picture("big.jpg", 6000, 4000)
    out["big"] = [newtabbg.set_photo(cfg, big), cfg["newtab_bg"], stored(), size_of("newtab-background.jpg"),
                  os.path.getsize(big) > 0]
    # tall, with transparency, in another format: kept as PNG, the JPEG removed
    tall = picture("tall.png", 1200, 5000, alpha=True)
    out["tall"] = [newtabbg.set_photo(cfg, tall), cfg["newtab_bg"], stored(), size_of("newtab-background.png")]
    # small pictures are not enlarged; other formats are converted
    small = picture("small.bmp", 320, 200)
    out["small"] = [newtabbg.set_photo(cfg, small), cfg["newtab_bg"], stored(), size_of("newtab-background.jpg")]
    # a picture with the wrong ending is recognised by its content
    wrong = picture("really-a-png.jpg", 640, 480, fmt="PNG")
    out["wrong_name"] = [newtabbg.set_photo(cfg, wrong), size_of("newtab-background.jpg")[:2]]
    # the user's own files are never touched
    out["originals"] = sorted(os.listdir(WORK))

    # files that cannot be used: refused with a reason, the photo in use stays
    before = (cfg["newtab_bg"], (data / cfg["newtab_bg"]).read_bytes())
    out["refused"] = {}
    for name in ("notes.jpg", "empty.png", "cut.png", "drawing.svg", "folder.jpg", "missing.jpg", "", "\x00bad"):
        path = os.path.join(WORK, name) if name else ""
        out["refused"][name or "(empty)"] = [newtabbg.set_photo(cfg, path),
                                            (cfg["newtab_bg"], (data / cfg["newtab_bg"]).read_bytes()) == before,
                                            stored()]
    limit = newtabbg.MAX_FILE
    newtabbg.MAX_FILE = 1000
    out["too_large"] = [newtabbg.set_photo(cfg, big), (cfg["newtab_bg"], (data / cfg["newtab_bg"]).read_bytes()) == before]
    newtabbg.MAX_FILE = limit
    # the folder cannot be written: said, and nothing changes
    blocked = Path(WORK) / "no-folder" / "file-in-the-way"
    blocked.parent.mkdir()
    blocked.write_text("x")
    out["not_saved"] = [newtabbg.set_photo(cfg, small, folder=blocked), cfg["newtab_bg"] == before[0]]

    # only I.K.E.'s own two file names are ever read
    real = cfg["newtab_bg"]
    out["names"] = {}
    for name in ("../../../etc/passwd", "/etc/passwd", "vault.bin", "newtab-background.jpg/../vault.bin",
                 "newtab-background.gif", ["newtab-background.jpg"], None, 5):
        cfg["newtab_bg"] = name
        out["names"][str(name)] = [newtabbg.current(cfg) is None, newtabbg.style(cfg), newtabbg.content(cfg)[0] is None]
    cfg["newtab_bg"] = real
    # the stored file disappears (deleted by hand): no background, no error
    (data / real).rename(data / "moved-away")
    out["gone"] = [newtabbg.current(cfg) is None, newtabbg.style(cfg)]
    (data / "moved-away").rename(data / real)
    # bad values of the other settings fall back
    for fit, veil in (("stretch", 500), (None, "abc"), (7, -20), ("fit", 40)):
        cfg["newtab_bg_fit"], cfg["newtab_bg_veil"] = fit, veil
        out.setdefault("styles", []).append(newtabbg.style(cfg))
    newtabbg.remove_photo(cfg)
    out["removed"] = [cfg["newtab_bg"], stored(), newtabbg.style(cfg)]
    ''', env={"IKE_BG_WORK": str(work)}, timeout=150)
    assert out["none"] == [True, "", True]
    problem, name, files, (w, h, alpha), _ = out["big"]
    assert problem == "" and name == "newtab-background.jpg" and files == [name]
    assert (w, h) == (3840, 2560) and not alpha                # scaled once, same proportions
    problem, name, files, (w, h, alpha) = out["tall"]
    assert problem == "" and name == "newtab-background.png" and files == [name]
    assert (w, h) == (922, 3840) and alpha
    problem, name, files, (w, h, alpha) = out["small"]
    assert problem == "" and files == ["newtab-background.jpg"] and (w, h) == (320, 200)
    assert out["wrong_name"] == ["", [640, 480]]
    assert out["originals"] == sorted(["big.jpg", "tall.png", "small.bmp", "really-a-png.jpg", "notes.jpg",
                                       "empty.png", "cut.png", "drawing.svg", "folder.jpg"])
    for name, (problem, unchanged, files) in out["refused"].items():
        assert problem and unchanged and files == ["newtab-background.jpg"], (name, problem)
    assert out["refused"]["notes.jpg"][0] == "This file is not a picture I.K.E. can open."
    assert out["refused"]["drawing.svg"][0] == "This file is not a picture I.K.E. can open."
    assert out["refused"]["missing.jpg"][0] == "The file was not found."
    assert out["refused"]["folder.jpg"][0] == "The file was not found."
    assert out["too_large"] == ["This picture is too large.", True]
    assert out["not_saved"] == ["The picture could not be saved.", True]
    for name, (none, style, no_content) in out["names"].items():
        assert none and style == "" and no_content, name
    assert out["gone"] == [True, ""]
    a, b, c, d = out["styles"]
    assert "/ cover " in a and "opacity:0.90" in a
    assert "/ cover " in b and "opacity:0.00" in b
    assert "/ cover " in c and "opacity:0.00" in c
    assert "/ contain " in d and "opacity:0.40" in d
    assert out["removed"] == ["", [], ""]


def test_settings_page_and_restart(run_ike, tmp_path):
    work = tmp_path / "pictures"
    work.mkdir()
    (work / "notes.jpg").write_text("not a picture")
    script = MAKE + r'''
def colours(win):
    from PyQt6.QtGui import QPalette
    pal = win.palette()
    return [pal.color(r).name() for r in (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText,
                                          QPalette.ColorRole.Highlight, QPalette.ColorRole.Base)] + \
           [win.nav.palette().color(QPalette.ColorRole.Window).name(), win.font().family()]

def steps(ike, qapp, out):
    yield 1200
    from pathlib import Path
    from ike import newtabbg
    win = ike.windows[0]
    view = win.current_view()
    data = Path(os.environ["XDG_DATA_HOME"]) / "ike-browser"
    out["plain"] = json.loads((yield from js(view, LOOK)))
    out["colours_plain"] = colours(win)
    scheme_before = ike.config["ui_scheme"]

    dlg = ike.show_settings(win)
    yield 300
    out["controls_off"] = [dlg.bg_remove.isEnabled(), dlg.bg_fit.isEnabled(), dlg.bg_veil.isEnabled(),
                           dlg.bg_info.text(), dlg.bg_preview.pixmap().isNull()]
    # a file that is not a picture: said in place, nothing chosen
    out["bad"] = [dlg._set_background(os.path.join(WORK, "notes.jpg")), dlg.bg_info.text(), dlg._bg_choice]
    photo = picture("photo.jpg", 2000, 1000, colour="#c02020")
    out["chosen"] = [dlg._set_background(photo), dlg.bg_info.text(), dlg.bg_preview.pixmap().isNull(),
                     dlg.bg_remove.isEnabled(), ike.config["newtab_bg"],
                     sorted(p.name for p in data.iterdir() if p.name.startswith("newtab"))]
    dlg.bg_fit.setCurrentIndex(dlg.bg_fit.findData("fit"))
    dlg.bg_veil.setValue(20)
    dlg.apply()
    yield 1500                     # the open new tab page shows it without being reopened
    out["applied"] = [ike.config["newtab_bg"], ike.config["newtab_bg_fit"], ike.config["newtab_bg_veil"],
                      sorted(p.name for p in data.iterdir() if p.name.startswith("newtab"))]
    out["shown"] = json.loads((yield from js(view, LOOK)))
    out["colours_photo"] = colours(win)
    out["scheme_same"] = ike.config["ui_scheme"] == scheme_before
    if os.environ.get("IKE_TEST_SHOTS"):
        win.grab().save(os.path.join(os.environ["IKE_TEST_SHOTS"], "newtab-photo.png"))
    # what the page really paints: the photo's red in the middle, veiled; the page colour outside "fit"
    shot = view.grab().toImage()
    mid = QColor(shot.pixel(int(shot.width() * 0.1), shot.height() // 2))
    edge = QColor(shot.pixel(int(shot.width() * 0.1), int(shot.height() * 0.03)))
    out["pixel"] = [mid.red(), mid.green(), mid.blue()]
    out["pixel_outside"] = [edge.red(), edge.green(), edge.blue()]
    # fill, no veil
    dlg.bg_fit.setCurrentIndex(dlg.bg_fit.findData("fill"))
    dlg.bg_veil.setValue(0)
    dlg.apply()
    yield 1500
    out["fill"] = json.loads((yield from js(view, LOOK)))
    shot = view.grab().toImage()
    mid = QColor(shot.pixel(int(shot.width() * 0.1), int(shot.height() * 0.03)))
    out["pixel_fill"] = [mid.red(), mid.green(), mid.blue()]
    # another photo takes its place
    second = picture("second.png", 800, 800, colour="#2020c0", alpha=True)
    dlg._set_background(second)
    dlg.bg_fit.setCurrentIndex(dlg.bg_fit.findData("centre"))
    dlg.apply()
    yield 1500
    out["second"] = [ike.config["newtab_bg"], sorted(p.name for p in data.iterdir() if p.name.startswith("newtab")),
                     json.loads((yield from js(view, LOOK)))["size"]]
    # a new tab gets it too
    other = win.add_tab("ike:newtab")
    yield 1200
    out["new_tab"] = json.loads((yield from js(other, LOOK)))["image"]
    dlg.close()
    '''
    out = run_ike(script, env={"IKE_BG_WORK": str(work), "IKE_TEST_SHOTS": SHOTS}, timeout=180)
    plain = out["plain"]
    assert plain["image"] == "none" and plain["veil"] is None
    assert out["controls_off"] == [False, False, False, "No photo", True]
    assert out["bad"] == [False, "This file is not a picture I.K.E. can open.", None]
    ok, info, no_preview, can_remove, cfg_name, files = out["chosen"]
    assert ok and info == "2000 × 1000" and not no_preview and can_remove
    assert cfg_name == "" and files == []                       # nothing is copied before Apply
    assert out["applied"] == ["newtab-background.jpg", "fit", 20, ["newtab-background.jpg"]]
    shown = out["shown"]
    assert shown["image"].startswith('url("ike:background?') and shown["size"] == "contain"
    assert shown["repeat"] == "no-repeat" and shown["attachment"] == "fixed"
    assert shown["veil"] == "0.2" and shown["veilColour"] == plain["body"]
    # the page's own colours and the interface are exactly as without a photo
    for key in ("vars", "text", "input", "clock"):
        assert shown[key] == plain[key], key
    assert out["colours_photo"] == out["colours_plain"] and out["scheme_same"]
    r, g, b = out["pixel"]
    assert r > g + 60 and r > b + 60, out["pixel"]             # the photo, seen through the veil
    r, g, b = out["pixel_outside"]                             # "fit": the page's colour around the photo
    assert abs(r - g) < 12 and abs(g - b) < 12, out["pixel_outside"]
    assert out["fill"]["size"] == "cover" and out["fill"]["veil"] == "0"
    r, g, b = out["pixel_fill"]
    assert r > 150 and g < 80 and b < 80, out["pixel_fill"]
    name, files, size = out["second"]
    assert name == "newtab-background.png" and files == [name] and size == "auto"
    assert out["new_tab"].startswith('url("ike:background?')

    # after a restart the choice is still there; then it is removed in Settings
    again = run_ike(MAKE + r'''
def steps(ike, qapp, out):
    yield 1200
    from pathlib import Path
    win = ike.windows[0]
    view = win.current_view()
    data = Path(os.environ["XDG_DATA_HOME"]) / "ike-browser"
    look = json.loads((yield from js(view, LOOK)))
    out["kept"] = [ike.config["newtab_bg"], ike.config["newtab_bg_fit"], look["image"][:20], look["size"]]
    dlg = ike.show_settings(win)
    yield 300
    out["controls_on"] = [dlg.bg_remove.isEnabled(), dlg.bg_info.text(), dlg.bg_preview.pixmap().isNull()]
    dlg.bg_remove.click()
    out["remove_pending"] = [dlg.bg_info.text(), ike.config["newtab_bg"]]
    dlg.apply()
    yield 1500
    look = json.loads((yield from js(view, LOOK)))
    out["removed"] = [ike.config["newtab_bg"], look["image"], look["veil"],
                      sorted(p.name for p in data.iterdir() if p.name.startswith("newtab"))]
    dlg.close()
    ''', env={"IKE_BG_WORK": str(work)}, keep_profile=True, timeout=120)
    assert again["kept"] == ["newtab-background.png", "centre", 'url("ike:background?', "auto"]
    assert again["controls_on"] == [True, "800 × 800", False]
    assert again["remove_pending"] == ["No photo", "newtab-background.png"]
    assert again["removed"] == ["", "none", None, []]


ATTACK = b"""<!doctype html><title>page</title><body>
<img id="i" src="ike:background"><iframe id="f" src="ike:background" width="50" height="50"></iframe>
<div id="d" style="width:40px;height:40px;background:url('ike:background')"></div>
<script>
window.res = {};
var i = document.getElementById("i");
function note() { res.img = i.complete ? [i.naturalWidth, i.naturalHeight] : "pending"; }
i.addEventListener("load", note); i.addEventListener("error", function () { res.img = "error"; });
if (i.complete) note();
fetch("ike:background").then(function (r) { return r.blob(); })
    .then(function (b) { res.fetch = b.size; }).catch(function () { res.fetch = "error"; });
var x = new XMLHttpRequest();
try { x.open("GET", "ike:background"); x.onload = function () { res.xhr = x.status + ":" + x.response.length; };
      x.onerror = function () { res.xhr = "error"; }; x.send(); } catch (e) { res.xhr = "error"; }
var c = document.createElement("canvas"), img2 = new Image();
img2.onload = function () { try { c.getContext("2d").drawImage(img2, 0, 0); res.canvas = c.toDataURL().length; }
                           catch (e) { res.canvas = "error"; } };
img2.onerror = function () { res.canvas = "error"; };
img2.src = "ike:background?1";
</script></body>"""


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = ATTACK
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_a_web_page_cannot_get_the_photo(run_ike, tmp_path, site):
    work = tmp_path / "pictures"
    work.mkdir()
    out = run_ike(MAKE + r'''
def steps(ike, qapp, out):
    yield 500
    from ike import newtabbg, shields
    out["set"] = newtabbg.set_photo(ike.config, picture("photo.jpg", 900, 600))
    served = []
    original = shields.IkeSchemeHandler.requestStarted
    def watch(self, job):
        url, who = job.requestUrl().toString(), job.initiator().toString()
        answer = []
        reply, fail = job.reply, job.fail
        original(self, job)
        served.append([url.split("?")[0], who.split(":")[0]])
    shields.IkeSchemeHandler.requestStarted = watch
    win = ike.windows[0]
    view = win.current_view()
    view.reload()
    yield 1200
    look = json.loads((yield from js(view, LOOK)))
    out["newtab_has_it"] = look["image"][:20]
    yield from js(view, """(function () { var i = new Image();
        i.onload = function () { window.again = [i.naturalWidth, i.naturalHeight]; };
        i.onerror = function () { window.again = "error"; };
        i.src = "ike:background?again"; return 1; })()""")
    yield 600
    out["newtab_loads"] = yield from js(view, "window.again")
    # a web page tries every way
    view.load(QUrl("http://127.0.0.1:%d/" % int(os.environ["IKE_BG_PORT"])))
    yield 3000
    for _ in range(50):                  # a slow computer: the page may not have answered yet
        page = yield from js(view, "window.res && ['img', 'fetch', 'xhr', 'canvas'].every(function (k) "
                                   "{ return k in res; }) ? JSON.stringify(res) : ''")
        if page:
            break
        yield 200
    out["page"] = json.loads((yield from js(view, "JSON.stringify(window.res || null)")))
    out["frame"] = yield from js(view, "document.getElementById('f').contentDocument === null ? 'cross' : 'same'")
    # ... and tries to send the tab there
    yield from js(view, "location.href = 'ike:background'; 1")
    yield 1500
    out["after_navigation"] = [view.url().toString(), view.title()]
    shot = view.grab().toImage()
    mid = QColor(shot.pixel(shot.width() // 2, shot.height() // 2))
    out["navigation_pixel"] = [mid.red(), mid.green(), mid.blue()]
    out["asked_by"] = sorted(set(who for url, who in served if url == "ike:background"))
    ''', env={"IKE_BG_WORK": str(work), "IKE_BG_PORT": str(site)}, timeout=150)
    assert out["set"] == ""
    assert out["newtab_has_it"] == 'url("ike:background?' and out["newtab_loads"] == [900, 600]
    page = out["page"]
    assert page["img"] == "error", page
    assert page["fetch"] == "error" and page["xhr"] == "error" and page["canvas"] == "error", page
    # the tab does not end up showing the photo
    r, g, b = out["navigation_pixel"]
    assert not (r > 150 and g < 80 and b < 80), out["navigation_pixel"]
    assert "http" in out["asked_by"] and "ike" in out["asked_by"]      # both really asked; only one was served


def test_settings_keys_listed():
    keys = json.loads((__import__("pathlib").Path(__file__).parent / "settings-keys.json").read_text())
    assert {"newtab_bg", "newtab_bg_fit", "newtab_bg_veil"} <= set(keys)
