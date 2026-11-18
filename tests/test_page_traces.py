"""What a page can see of I.K.E. (1.1.12).

Anti-abuse checks (Google's sign-in and AI Studio, banks, payments) compare
the page's functions with the ones of a fresh frame and read error stacks: a
changed function or a script named in a stack makes them refuse operations
("permission denied"). Here, on local pages, with the same checks:

- the media commands of the desktop (mediahook.js) change nothing outside the
  media sites, even with the shield off; on a listed media site they are there;
- with the shield off, a page finds nothing changed at all;
- the sensitive Google services get "Compatibility", unless the user chose a
  level for them;
- the lighter frame guard of the fingerprinting protection still protects every
  frame a page adds: appended, inside a container, through innerHTML,
  insertAdjacentHTML or a fragment (same canvas noise as the page, not the real
  canvas);
- the bundled AdBlock engine (ike/_engine, carried by the self-update) is used
  first, and the installed one when the bundled one cannot be loaded.
"""

import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PAGE = rb"""<!doctype html><title>traces</title><body><div id=box></div><script>
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function canvasHash(doc) {
  var c = doc.createElement('canvas'); c.width = 200; c.height = 40;
  var x = c.getContext('2d');
  x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
  x.fillStyle = '#069'; x.fillText('I.K.E. traces', 2, 10);
  return hash(c.toDataURL());
}
window.traces = function () {
  var r = {};
  var f = document.createElement('iframe'); document.body.appendChild(f);
  var nts = f.contentWindow.Function.prototype.toString;
  r.toString = nts.call(Function.prototype.toString);
  r.setActionHandler = nts.call(MediaSession.prototype.setActionHandler);
  try { Function.prototype.toString.call({}); } catch (e) { r.stack = String(e.stack); }
  try { MediaSession.prototype.setActionHandler.call({}, 'play', null); } catch (e) { r.stack2 = String(e.stack); }
  return JSON.stringify(r);
};
window.frames_ = function () {
  var box = document.getElementById('box'), r = {top: canvasHash(document)};
  var a = document.createElement('iframe'); box.appendChild(a);
  r.appended = canvasHash(a.contentWindow.document);
  var div = document.createElement('div'); div.appendChild(document.createElement('iframe'));
  box.appendChild(div);
  r.container = canvasHash(window[window.length - 1].document);
  box.insertAdjacentHTML('beforeend', '<p><iframe></iframe></p>');
  r.adjacent = canvasHash(window[window.length - 1].document);
  var holder = document.createElement('section'); box.appendChild(holder);
  holder.innerHTML = '<iframe></iframe>';
  r.innerhtml = canvasHash(window[window.length - 1].document);
  var frag = document.createDocumentFragment(); frag.appendChild(document.createElement('iframe'));
  box.appendChild(frag);
  r.fragment = canvasHash(window[window.length - 1].document);
  return JSON.stringify(r);
};
</script>traces</body>"""


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl

def ask(v, js, res, key):
    v.page().runJavaScript(js, lambda x: res.setdefault(key, x))

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl("http://127.0.0.1:%d/"))
    while "ok" not in done:
        yield 20
    yield 300
    res = {}
    ask(v, "traces()", res, "traces")
    ask(v, "frames_()", res, "frames")
    while len(res) < 2:
        yield 20
    out["traces"] = json.loads(res["traces"])
    out["frames"] = json.loads(res["frames"])
    c = ike.config
    out["levels"] = [c.level_for(h) for h in ("aistudio.google.com", "console.cloud.google.com",
                                               "www.google.com", "youtube.com", "chose.example")]
    fp = [s.sourceCode() for s in ike.profile.scripts().find("ike-fp")]
    out["fp_compat"] = bool(fp) and '"aistudio.google.com": "compatibility"' in fp[0]
'''

NATIVE_TS = "function toString() { [native code] }"
NATIVE_AH = "function setActionHandler() { [native code] }"


def test_nothing_to_see_with_the_shield_off(run_ike, site):
    out = run_ike(STEPS % site, settings={"shield_level": "off"})
    t = out["traces"]
    assert t["toString"] == NATIVE_TS
    assert t["setActionHandler"] == NATIVE_AH
    assert "userscript" not in t["stack"] and "ike" not in t["stack"].lower(), t["stack"]
    assert "userscript" not in t["stack2"], t["stack2"]
    assert out["levels"][:2] == ["off", "off"]       # the user's "off" stays off


def test_media_commands_only_on_media_sites(run_ike, site):
    # the local page counted as a media site: the commands are there (the hook
    # is the one of 1.1.11 and before, its own tests are in test_plasma.py)
    out = run_ike(STEPS % site, settings={"shield_level": "off", "media_sites": ["127.0.0.1"]})
    t = out["traces"]
    assert t["setActionHandler"] != NATIVE_AH and "ike-media" in t["stack"]


def test_balanced_frames_protected_and_google_services_in_compatibility(run_ike, site):
    real = run_ike(STEPS % site, settings={"shield_level": "off"})["frames"]["top"]
    out = run_ike(STEPS % site, settings={"shield_level": "balanced"})
    t, f = out["traces"], out["frames"]
    assert t["toString"] == NATIVE_TS and t["setActionHandler"] == NATIVE_AH
    assert f["top"] != real, "the canvas is not protected at all"
    for how in ("appended", "container", "adjacent", "innerhtml", "fragment"):
        assert f[how] == f["top"], (how, f)             # the same noise as the page
    assert out["levels"] == ["compatibility", "compatibility", "balanced", "balanced", "balanced"]
    assert out["fp_compat"]
    # a level the user chose for the site is kept
    chosen = run_ike(STEPS % site, settings={"shield_level": "balanced",
                                             "site_levels": {"aistudio.google.com": "strict"}})
    assert chosen["levels"][0] == "strict"


# --- the AdBlock engine carried by the self-update --------------------------------

ENGINE = ROOT / "vendor" / "adblock"
needs_engine = pytest.mark.skipif(not (ENGINE / "ike_adblock.abi3.so").is_file(),
                                  reason="the AdBlock engine is not built (see BUILDING.md)")

PROBE = r"""
import sys
sys.path.insert(0, sys.argv[1])
sys.path.append(sys.argv[2])
import ike.blocker as b
print(b.adblock.__file__ if b.adblock else "none", getattr(b.adblock, "MODERN", None))
"""


def _copy_ike(tmp_path):
    app = tmp_path / "app"
    shutil.copytree(ROOT / "ike", app / "ike", ignore=shutil.ignore_patterns("__pycache__", "_engine"))
    return app


def _probe(app, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    env.update({"HOME": str(tmp_path / "home"), "QT_QPA_PLATFORM": "offscreen"})
    out = subprocess.run([sys.executable, "-c", PROBE, str(app), str(ROOT / "vendor")], env=env,
                         capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.split()


@needs_engine
def test_bundled_engine_comes_first(tmp_path):
    app = _copy_ike(tmp_path)
    shutil.copytree(ENGINE, app / "ike" / "_engine" / "adblock", ignore=shutil.ignore_patterns("__pycache__"))
    path, modern = _probe(app, tmp_path)
    assert Path(path).resolve().is_relative_to((app / "ike" / "_engine").resolve()), path
    assert modern == "True"


@needs_engine
def test_installed_engine_when_the_bundled_one_is_broken(tmp_path):
    app = _copy_ike(tmp_path)
    broken = app / "ike" / "_engine" / "adblock"
    shutil.copytree(ENGINE, broken, ignore=shutil.ignore_patterns("__pycache__"))
    (broken / "ike_adblock.abi3.so").write_bytes(b"not an engine")
    path, modern = _probe(app, tmp_path)
    assert Path(path).resolve().is_relative_to(ENGINE.resolve()), path
    assert modern == "True"
    # without any bundled engine: the installed one, as before
    shutil.rmtree(app / "ike" / "_engine")
    path, _modern = _probe(app, tmp_path)
    assert Path(path).resolve().is_relative_to(ENGINE.resolve()), path
