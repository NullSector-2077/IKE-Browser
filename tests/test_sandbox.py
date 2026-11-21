"""The engine's sandbox really on (1.1.18, security audit: every other test
runs with the sandbox off, because containers and GitHub's runners refuse its
namespaces).

Only with IKE_TEST_SANDBOX=1, on a system where the sandbox can work (the
"sandbox" CI job, or a user's Arch / CachyOS computer as a normal user).
Fails if any web page process runs without the sandbox: every renderer must
have Chromium's seccomp filter (Seccomp: 2, no new privileges) and a PID
namespace of its own, I.K.E. must say the sandbox is on, no switch may have taken a
protection away, and each site gets its own process.
"""

import http.server
import os
import threading

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("IKE_TEST_SANDBOX") != "1",
                                reason="IKE_TEST_SANDBOX=1 only (needs a system where the sandbox works)")


@pytest.fixture
def sites():
    servers = []

    def serve(host, body):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                b = body.replace(b"PORT", str(servers[0].server_address[1]).encode()) if servers else body
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer((host, 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv
    serve("127.0.0.2", b"<title>B</title>")
    top = serve("127.0.0.1", b"<title>A</title><iframe src='http://127.0.0.2:PORT/'></iframe>")
    yield top.server_address[1]
    for s in servers:
        s.shutdown()


STEPS = r'''
import os, re
from PyQt6.QtCore import QUrl

def nspid(status):
    m = re.search(r"NSpid:\s*([\d\s]+)", status)
    return len(m.group(1).split()) if m else 0

def mine(pid):
    """A process of this browser (another Chromium running must not count)."""
    me, p = os.getpid(), int(pid)
    for _ in range(20):
        if p == me:
            return True
        try:
            p = int(re.search(r"PPid:\s*(\d+)", open("/proc/%%d/status" %% p).read()).group(1))
        except (OSError, AttributeError):
            return False
        if p <= 1:
            return False
    return False

def renderers():
    # read from /proc/<pid>/status, which stays readable: the namespace links
    # of a sandboxed process are not (that is the sandbox at work)
    res = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            # renderers forked from the zygote carry their switches as one
            # text (set as the process title), not one argument each
            cmd = open("/proc/%%s/cmdline" %% pid, "rb").read().replace(b"\0", b" ")
            if b"QtWebEngineProcess" not in cmd or b"--type=renderer" not in cmd or not mine(pid):
                continue
            st = open("/proc/%%s/status" %% pid).read()
            res.append({"pid": pid, "seccomp": re.search(r"Seccomp:\s*(\d+)", st).group(1),
                        "nnp": re.search(r"NoNewPrivs:\s*(\d+)", st).group(1),
                        "depth": nspid(st), "no_sandbox": b"--no-sandbox" in cmd,
                        "cmd": cmd[:160].decode("ascii", "replace")})
        except (OSError, AttributeError):
            pass
    return res

def steps(ike, qapp, out):
    from ike.app import ENGINE_SAFETY, sandbox_off, site_isolated
    v = ike.windows[0].current_view()
    v.load(QUrl("http://127.0.0.1:%d/"))
    # until the page is there (a fixed 4 s was too short on a busy runner)
    for _ in range(75):
        yield 200
        if v.title() == "A":
            break
    yield 1000
    out["title"] = v.title()
    out["mine"] = nspid(open("/proc/self/status").read())
    # a process that is just starting has no sandbox yet: only those seen in
    # two readings 1.5 s apart count
    first = {p["pid"] for p in renderers()}
    yield 1500
    out["renderers"] = [p for p in renderers() if p["pid"] in first]
    out["sandbox_off"] = sandbox_off()
    out["site_isolated"] = site_isolated()
    out["safety"] = ENGINE_SAFETY
    out["euid"] = os.geteuid()
'''


def test_every_page_process_is_sandboxed(run_ike, sites):
    out = run_ike(STEPS % sites, timeout=90)
    assert out["euid"] != 0 and out["title"] == "A", out
    assert out["sandbox_off"] is False and out["site_isolated"] is True, out
    assert out["safety"] == {"dropped": [], "kept": []}, out
    r = out["renderers"]
    assert len(r) >= 2, r                                     # the page and the other site's frame
    for p in r:
        assert p["seccomp"] == "2" and p["nnp"] == "1" and not p["no_sandbox"], p    # seccomp filter on
        assert p["depth"] > out["mine"], (p, out["mine"])          # in a PID namespace of its own


def test_a_switch_that_turns_isolation_off_is_dropped(run_ike, sites):
    """Without IKE_ALLOW_UNSAFE_ENGINE=1, a --disable-site-isolation-trials or
    a --no-sandbox inherited from the environment does nothing."""
    out = run_ike(STEPS % sites, timeout=90,
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": '"--no-sandbox" -disable-site-isolation-trials',
                       "QTWEBENGINE_REMOTE_DEBUGGING": "9229", "QTWEBENGINE_DISABLE_SANDBOX": "0"})
    assert out["sandbox_off"] is False and out["site_isolated"] is True, out
    assert set(out["safety"]["dropped"]) == {"--no-sandbox", "--disable-site-isolation-trials",
                                             "QTWEBENGINE_REMOTE_DEBUGGING", "QTWEBENGINE_DISABLE_SANDBOX"}, out
    assert out["renderers"] and all(p["seccomp"] == "2" for p in out["renderers"]), out["renderers"]
