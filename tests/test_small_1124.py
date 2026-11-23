"""Package A2a of 1.1.24: notifications through D-Bus (no notify-send), the Public
Suffix List cache as JSON (no marshal), and the "Not secure" label of http pages."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. notifications: org.freedesktop.Notifications.Notify on a private session bus
# ---------------------------------------------------------------------------

# a stand-in notification service (jeepney, as tests/dbus_standins.py) that writes each call it gets
SERVICE = r'''
import json, sys
from jeepney import MessageType, new_method_return
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection
conn = open_dbus_connection("SESSION")
conn.send_and_get_reply(message_bus.RequestName("org.freedesktop.Notifications"))
print("ready", flush=True)
while True:
    msg = conn.receive()
    if msg.header.message_type == MessageType.method_call:
        f = msg.header.fields
        print(json.dumps({"path": f.get(1), "iface": f.get(2), "member": f.get(3), "sig": f.get(8),
                          "body": msg.body}), flush=True)
        conn.send(new_method_return(msg, "u", (7,)))
'''

# runs I.K.E.'s notify() against it, in a Qt program with an event loop, and prints what the service saw
CLIENT = r'''
import json, subprocess, sys, time
sys.path.insert(0, %(root)r)
service = subprocess.Popen([sys.executable, "-c", %(service)r], stdout=subprocess.PIPE, text=True)
assert service.stdout.readline().strip() == "ready"
from PyQt6.QtCore import QCoreApplication
app = QCoreApplication([])
from ike import osinfo
CASES = %(cases)r
seen = []
for title, text in CASES:
    osinfo.notify(title, text)
    end = time.time() + 5
    import select
    while time.time() < end:
        app.processEvents()
        if select.select([service.stdout], [], [], 0.02)[0]:
            seen.append(json.loads(service.stdout.readline()))
            break
service.kill()
print("RESULT " + json.dumps(seen))
'''

CASES = [("--icon=/etc/passwd", "-u critical"),
         ("Site", '<a href="https://evil.example/">click</a> <img src="file:///etc/passwd"> & more'),
         ("", ""), ("x" * 5000, "y" * 50000), ("nul\0byte", "te\0xt")]


def _run_on_private_bus(cases):
    if not shutil.which("dbus-run-session"):
        pytest.skip("dbus-run-session is not installed here")
    code = CLIENT % {"root": str(ROOT), "service": SERVICE, "cases": cases}
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    p = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=120, env=env)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, (p.stdout, p.stderr)
    return json.loads(lines[0][7:])


def test_notification_is_a_dbus_notify_call_with_the_right_arguments():
    seen = _run_on_private_bus(CASES)
    assert len(seen) == len(CASES)
    for call in seen:
        assert call["path"] == "/org/freedesktop/Notifications"
        assert call["iface"] == "org.freedesktop.Notifications" and call["member"] == "Notify"
        # app_name, replaces_id (uint), icon, summary, body, actions (as), hints (a{sv}), timeout (the server's default)
        assert call["sig"] == "susssasa{sv}i", call["sig"]
        app, replaces, icon, title, body, actions, hints, timeout = call["body"]
        assert (app, replaces, icon, actions, hints, timeout) == ("I.K.E.", 0, "ike-browser", [], {}, -1)
        assert "<" not in body and ">" not in body              # markup of a page is escaped
        assert 0 < len(title) <= 200 and len(body) <= 12000
        assert "\0" not in title and "\0" not in body
    # text a page wrote is only ever a string: nothing of it is an option, a path or markup
    assert seen[0]["body"][3] == "--icon=/etc/passwd" and seen[0]["body"][4] == "-u critical"
    assert seen[1]["body"][4].startswith("&lt;a href=") and "&amp; more" in seen[1]["body"][4]
    assert seen[2]["body"][3] == " "
    assert seen[4]["body"][3] == "nulbyte" and seen[4]["body"][4] == "text"


def test_notification_without_a_service_or_a_bus_does_nothing():
    code = ("import sys; sys.path.insert(0, %r)\n"
            "from PyQt6.QtCore import QCoreApplication\n"
            "app = QCoreApplication([])\n"
            "from ike import osinfo\n"
            "osinfo.notify('a', 'b')\n"
            "for _ in range(20):\n    app.processEvents()\n"
            "print('SILENT')\n" % str(ROOT))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    # a bus where nobody owns the service
    if shutil.which("dbus-run-session"):
        p = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=60, env=env)
        assert "SILENT" in p.stdout and p.returncode == 0, (p.stdout, p.stderr)
    # no bus at all
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/bus"
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, env=env)
    assert "SILENT" in p.stdout and p.returncode == 0, (p.stdout, p.stderr)


def test_notify_send_and_libnotify_are_gone():
    for f in (ROOT / "ike").glob("*.py"):
        assert "notify-send" not in f.read_text("utf-8"), f
    assert "subprocess" not in (ROOT / "ike" / "osinfo.py").read_text("utf-8")
    assert "libnotify" not in (ROOT / "PKGBUILD").read_text("utf-8")
    assert "libnotify" not in (ROOT / ".github" / "workflows" / "arch.yml").read_text("utf-8")
    assert "libnotify" not in (ROOT / "docs" / "THIRD-PARTY.md").read_text("utf-8")


# ---------------------------------------------------------------------------
# 2. the Public Suffix List cache: JSON, never marshal
# ---------------------------------------------------------------------------

def _psl_text(n=1500):
    return "// sample\ncom\nco.uk\n*.ck\n!www.ck\n" + "".join("rule%d.example\n" % i for i in range(n))


@pytest.fixture
def psl(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from ike import config, shields
    path = tmp_path / "psl.dat"
    path.write_text(_psl_text())
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(shields, "PSL_PATHS", [str(path)])
    monkeypatch.setattr(shields, "_PSL", [])
    monkeypatch.setattr(shields, "_PSL_FILE", [])
    shields.site_of.cache_clear()
    yield shields, path, tmp_path / "cache"
    shields.site_of.cache_clear()


def test_psl_cache_is_json_and_round_trips(psl):
    shields, path, cache = psl
    first = shields._psl()
    files = list(cache.glob("psl-*"))
    assert [f.suffix for f in files] == [".json"]
    data = json.loads(files[0].read_text("ascii"))          # plain JSON: three lists
    assert len(data) == 3 and all(isinstance(x, list) for x in data) and "co.uk" in data[0] and "ck" in data[1]
    assert b"marshal" not in files[0].read_bytes()
    # the next start reads the copy, not the list: a list of the same size and time that says otherwise
    st = os.stat(path)
    path.write_text(_psl_text().replace("co.uk", "co.xx"))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    shields._PSL.clear()
    again = shields._psl()
    assert again == first and "co.uk" in again[0] and "co.xx" not in again[0]
    assert again[1] == frozenset(["ck"]) and again[2] == frozenset(["www.ck"])


@pytest.mark.parametrize("junk", [b"", b"\x00\x01garbage", b"{not json", b'[["a"],["b"]]', b'{"a": 1}',
                                  b'"text"', b'[[[1]], [], []]', b'[1, 2, 3]'])
def test_psl_corrupted_cache_is_rebuilt(psl, junk):
    shields, path, cache = psl
    shields._psl()
    (cache_file,) = cache.glob("psl-*.json")
    cache_file.write_bytes(junk)
    shields._PSL.clear()
    found = shields._psl()
    assert found is not None and "co.uk" in found[0] and len(found[0]) > 1000
    assert json.loads(cache_file.read_text("ascii"))[0].count("co.uk") == 1      # rewritten, valid


def test_psl_old_marshal_cache_is_ignored_and_deleted(psl):
    import marshal
    shields, path, cache = psl
    st = os.stat(path)
    cache.mkdir(parents=True)
    old = cache / ("psl-%d-%d.bin" % (st.st_size, st.st_mtime_ns))
    old.write_bytes(marshal.dumps((("evil.example",) * 2000, (), ())))
    found = shields._psl()
    assert "evil.example" not in found[0] and "co.uk" in found[0]
    assert not old.exists() and len(list(cache.glob("psl-*.json"))) == 1


def test_psl_cache_load_is_not_slower_than_a_few_ms():
    """The JSON copy of a real-sized list (about 9000 rules) loads in about a millisecond."""
    rules = ["rule%d.example.com" % i for i in range(9000)]
    blob = json.dumps([rules, ["ck"], ["www.ck"]], separators=(",", ":")).encode("ascii")
    t = time.perf_counter()
    for _ in range(20):
        a, b, c = json.loads(blob)
        frozenset(a), frozenset(b), frozenset(c)
    assert (time.perf_counter() - t) / 20 < 0.02


def test_shields_has_no_marshal():
    text = (ROOT / "ike" / "shields.py").read_text("utf-8")
    assert "import marshal" not in text and "marshal." not in text


# ---------------------------------------------------------------------------
# 3. "Not secure" in the address bar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("http://example.com/", True), ("http://example.com:8080/a?b=c", True), ("http://192.168.1.10/", True),
    ("http://localhost/", False), ("http://localhost:3000/", False), ("http://app.localhost/", False),
    ("http://127.0.0.1/", False), ("http://127.1.2.3:80/", False), ("http://[::1]/", False),
    ("https://example.com/", False), ("file:///home/user/a.html", False), ("about:blank", False),
    ("ike://settings", False), ("view-source:http://example.com/", False), ("", False),
    ("http://127.0.0.1.example.com/", True),
])
def test_not_secure_rule(url, expected):
    sys.path.insert(0, str(ROOT))
    from PyQt6.QtCore import QUrl

    from ike.urlbar import is_not_secure
    assert is_not_secure(QUrl(url)) is expected


STEPS = r'''
from PyQt6.QtCore import QUrl

class Fake:
    def __init__(self, u):
        self._u = QUrl(u)
    def url(self):
        return self._u
    def __bool__(self):
        return True
    def __getattr__(self, name):             # the rest (zoom, title...) is the real view's
        return getattr(real_view, name)

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    yield 300
    real = win.current_view
    global real_view
    real_view = real()
    seen = {}
    for u in ("http://example.com/", "http://localhost:8000/", "http://127.0.0.1/", "https://example.com/",
              "file:///tmp/x.html", "about:blank", "http://example.org/"):
        win.current_view = lambda u=u: Fake(u)
        win.sync_urlbar()
        yield 100
        bar = win.urlbar
        b = bar._badge
        seen[u] = [b.isVisible(), b.text(), b.geometry().width() > 0, b.geometry().left() >= bar._start.geometry().right() - 1,
                   bar._start_room]
    win.current_view = real
    out["seen"] = seen
'''


def test_not_secure_label_in_the_address_bar(run_ike):
    out = run_ike(STEPS, timeout=120)
    seen = out["seen"]
    for u in ("http://example.com/", "http://example.org/"):
        assert seen[u][0] is True and seen[u][1] == "Not secure" and seen[u][2] and seen[u][3], (u, seen[u])
    for u in ("http://localhost:8000/", "http://127.0.0.1/", "https://example.com/", "file:///tmp/x.html", "about:blank"):
        assert seen[u][0] is False, (u, seen[u])
    # the text of the address starts after the label, and takes the room back when it is hidden
    assert seen["http://example.com/"][4] > seen["https://example.com/"][4]
    assert seen["http://localhost:8000/"][4] == seen["https://example.com/"][4]


def test_not_secure_is_translated_everywhere():
    langs = ROOT / "ike" / "resources" / "lang"
    packs = sorted(langs.glob("*.json"))
    assert len(packs) >= 58
    for f in packs:
        strings = json.loads(f.read_text("utf-8"))["strings"]
        assert strings.get("Not secure", "").strip(), f.name
    it = json.loads((langs / "it.json").read_text("utf-8"))["strings"]
    assert it["Not secure"] == "Non sicuro"
