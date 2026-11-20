"""The fallback for video ads that get past the lists (ike/resources/videoads.js), 1.1.18.

SIMULATION: a local page shaped like YouTube's player (an element with the
class "html5-video-player" holding a <video>), served from 127.0.0.1, which the
test makes a video site (video_ad_skip_hosts). It checks I.K.E.'s own behaviour
only; it says nothing about YouTube's servers or its anti-adblock checks.

- No ad: the page's ad boxes (#player-ads...) are left to the filter lists,
  which keep some of them on purpose (YouTube refuses playback when they are
  hidden): the script hides nothing by itself.
- During an ad: muted and sped up or sent to its end; afterwards sound and
  speed come back as the user had them.
- An ad that cannot be sought: at most one jump a second, not hundreds.
"""

import http.server
import shutil
import subprocess
import threading

import pytest

PAGE = b"""<!doctype html><title>player</title><body>
<div id="player-ads" style="height:30px">sponsored box</div>
<div id="masthead-ad" style="height:30px">masthead</div>
<div class="html5-video-player" id="p"><video id="v" src="/c.webm" preload="auto"></video></div>
<script>
window.jumps = 0;
window.stubborn = false;
var v = document.getElementById('v');
v.addEventListener('seeking', function () {
  if (v.currentTime > 1) window.jumps++;                   // a jump towards the end (the fallback's)
  if (window.stubborn && v.currentTime > 1) v.currentTime = 0;   // an ad that will not be sought
});
</script></body>"""


@pytest.fixture
def site(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    clip = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "20", "-c:v", "libvpx", "-b:v", "50k",
                    "-c:a", "libvorbis", str(clip)], check=True, timeout=120)
    data = clip.read_bytes()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, kind = (PAGE, "text/html") if self.path == "/" else (data, "video/webm")
            rng = self.headers.get("Range", "")
            if kind == "video/webm" and rng.startswith("bytes="):      # as a real video server
                a, _, z = rng[6:].partition("-")
                a = int(a or 0)
                z = min(int(z) if z else len(body) - 1, len(body) - 1)
                part = body[a:z + 1]
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (a, z, len(body)))
                body = part
            else:
                self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def js(view, code):
    res = {}
    view.page().runJavaScript(code, 0, lambda r: res.setdefault("r", r))
    while "r" not in res:
        yield 20
    return res["r"]

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    done = {}
    view.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    view.load(QUrl("http://127.0.0.1:%d/"))
    while "ok" not in done:
        yield 20
    for _ in range(100):
        if (yield from js(view, "isFinite(v.duration) && v.duration > 1")):
            break
        yield 100
    yield 500
    out["boxes"] = json.loads((yield from js(view, "JSON.stringify(['player-ads', 'masthead-ad'].map("
                                                 "function (i) { return getComputedStyle(document.getElementById(i)).display; }))")))
    out["styles"] = (yield from js(view, "document.querySelectorAll('style').length"))
    # an ad that can be sought: muted, sent to its end
    yield from js(view, "v.muted = false; v.playbackRate = 1; v.play().catch(function () {}); "
                        "document.getElementById('p').classList.add('ad-showing'); 1")
    yield 800
    out["during"] = json.loads((yield from js(view, "JSON.stringify([v.muted, v.currentTime > 15])")))
    yield from js(view, "document.getElementById('p').classList.remove('ad-showing'); 1")
    yield 800
    out["after"] = json.loads((yield from js(view, "JSON.stringify([v.muted, v.playbackRate])")))
    # an ad that cannot be sought: the page puts every jump back
    yield from js(view, "v.currentTime = 0; window.jumps = 0; window.stubborn = true; "
                        "document.getElementById('p').classList.add('ad-showing'); 1")
    yield 3000
    out["jumps"] = (yield from js(view, "window.jumps"))
    yield from js(view, "window.stubborn = false; document.getElementById('p').classList.remove('ad-showing'); 1")
    yield 500
'''


def test_the_video_ad_fallback(run_ike, site):
    out = run_ike(STEPS % site, settings={"video_ad_skip_hosts": ["127.0.0.1"], "video_ad_skip": True},
                  timeout=120)
    assert out["boxes"] == ["block", "block"], out          # nothing hidden by I.K.E. itself
    assert out["during"] == [True, True], out               # muted and sent to its end
    assert out["after"] == [False, 1], out                  # sound and speed back
    assert 1 <= out["jumps"] <= 5, out                      # 3 s of a stubborn ad: about one jump a second
