#!/usr/bin/env python3
"""The Dark Engine's diagnosis on the page you are looking at, in your own
running I.K.E. (signed in, scrolled to the part that looks wrong), not in a fresh
private profile as owner_check.py does.

I.K.E. is started for this once with its remote debugging on, which I.K.E. allows
only when asked on purpose (IKE_ALLOW_UNSAFE_ENGINE=1) and only on this computer
(127.0.0.1); close that window afterwards and start I.K.E. again as usual:

    IKE_ALLOW_UNSAFE_ENGINE=1 QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:9222 ike-browser
    (open the page, scroll to the part that looks wrong)
    python3 tests/dark_engine/live-diag.py [part of the address]

Written to ~/ike-live-diagnose-<date>/: diagnose.txt (the light areas, the light
texts on pictures and where their colours come from, as owner_check.py writes
it) and screen.png (what the tab shows). Nothing is sent anywhere; only this
computer's I.K.E. is asked, over its local debugging port, read-only (one script
that reads the page's colours, one picture of the tab).
"""

import ast
import base64
import datetime
import json
import os
import socket
import struct
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import owner_check  # noqa: E402

PORT = int(os.environ.get("IKE_DIAG_PORT", "9222"))


def diag_script():
    tree = ast.parse((HERE / "render.py").read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DIAG" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("render.py has no DIAG")


class Socket:
    """The smallest WebSocket client the debugging port needs (text frames)."""

    def __init__(self, url):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.rsplit(":", 1)
        self.s = socket.create_connection((host, int(port)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(4096)
            if not chunk:
                raise SystemExit("I.K.E. closed the debugging connection")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise SystemExit("I.K.E. refused the debugging connection: %s" % head.split(b"\r\n", 1)[0].decode())
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = bytes([0x81, 0x80 | n])
        elif n < 65536:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _need(self, k):
        while len(self.buf) < k:
            chunk = self.s.recv(1 << 16)
            if not chunk:
                raise SystemExit("I.K.E. closed the debugging connection")
            self.buf += chunk

    def recv(self):
        msg = b""
        while True:
            self._need(2)
            b0, b1 = self.buf[0], self.buf[1]
            n, off = b1 & 0x7F, 2
            if n == 126:
                self._need(4)
                n, off = struct.unpack(">H", self.buf[2:4])[0], 4
            elif n == 127:
                self._need(10)
                n, off = struct.unpack(">Q", self.buf[2:10])[0], 10
            self._need(off + n)
            payload, self.buf = self.buf[off:off + n], self.buf[off + n:]
            op = b0 & 0x0F
            if op in (0, 1, 2):
                msg += payload
                if b0 & 0x80:
                    return json.loads(msg.decode("utf-8", "replace"))
            elif op == 8:
                raise SystemExit("I.K.E. closed the debugging connection")

    def call(self, method, **params):
        self.n += 1
        self.send({"id": self.n, "method": method, "params": params})
        while True:
            m = self.recv()
            if m.get("id") == self.n:
                if "error" in m:
                    raise SystemExit("%s: %s" % (method, m["error"].get("message")))
                return m.get("result", {})


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=5).read())
    except OSError:
        raise SystemExit("I.K.E. is not reachable on 127.0.0.1:%d. Close I.K.E. and start it with:\n"
                         "  IKE_ALLOW_UNSAFE_ENGINE=1 QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:%d ike-browser"
                         % (PORT, PORT))
    pages = [t for t in tabs if t.get("type") == "page" and t.get("url", "").startswith(("http://", "https://"))
             and want in t.get("url", "")]
    if not pages:
        raise SystemExit("No open web page%s." % (" with %r in its address" % want if want else ""))
    if len(pages) > 1 and not want:
        print("More than one page is open; the first is looked at (give a part of its address to choose):")
        for t in pages:
            print("   ", t["url"][:100])
    tab = pages[0]
    print("Looking at:", tab["url"][:120], flush=True)
    ws = Socket(tab["webSocketDebuggerUrl"])
    res = ws.call("Runtime.evaluate", expression=diag_script(), returnByValue=True)
    d = json.loads(res.get("result", {}).get("value") or "null")
    if not d:
        raise SystemExit("The page gave no answer to the diagnosis")
    out = Path.home() / ("ike-live-diagnose-" + datetime.date.today().isoformat())
    out.mkdir(parents=True, exist_ok=True)
    shot = ws.call("Page.captureScreenshot", format="png")
    if shot.get("data"):
        (out / "screen.png").write_bytes(base64.b64decode(shot["data"]))
    lines = ["== %s: %d sheets (%d the page cannot read), %d frames"
             % (tab["url"][:100], d.get("sheets", 0), len(d.get("unreadable", [])), d.get("frames", 0))]
    wanted = set()
    for u in d.get("unreadable", []):
        lines.append("   unreadable sheet: %s" % u)
    for e in d.get("light", []):
        lines.append("   %s at %s background %s%s%s" % (e["el"], e["rect"], e["bg"],
                     " frame " + e["frame"] if e.get("frame") else "", " (shadow host)" if e.get("shadowHost") else ""))
        for r in e.get("rules", []):
            lines.append("      rule: %s" % r)
        for v in e.get("vars", []):
            lines.append("      variable %s = %s" % (v["name"], v["value"] or "(empty)"))
            for w in v.get("where", []) + v.get("property", []):
                lines.append("         %s" % w)
            for a in v.get("ancestors", []):
                lines.append("         inside %s" % a)
            wanted.add(v["name"])
        if e.get("inline"):
            lines.append("      inline style: %s" % e["inline"])
    for e in d.get("lowcontrast", []):
        u = e["under"]
        lines.append("   light text on a light %s: %r %s at %s colour %s, under it %s: %s%s" % (
            u["kind"], e["text"], e["el"], e["rect"], e["color"], u["layer"], u["value"],
            ("  [style: %s]" % u["inline"]) if u.get("inline") else ""))
        for r in u.get("rules", []):
            lines.append("      rule: %s" % r)
        lines.append("      layers: %s" % " > ".join(e.get("path", [])))
    for e in d.get("onpicture", []):
        lines.append("   light text on a picture: %r %s at %s colour %s, over %s: %s"
                     % (e["text"], e["el"], e["rect"], e["color"], e["under"], e["picture"]))
    classes = set()
    for e in d.get("lowcontrast", []):
        classes.update(c for c in e["under"]["layer"].split("::")[0].split(".")[1:] if c)
    lines.extend(owner_check._in_unreadable(d.get("unreadable", []), wanted))
    lines.extend(owner_check._sources(d.get("unreadable", []), classes))
    (out / "diagnose.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nSaved in", out, "(diagnose.txt, screen.png). Close this I.K.E. window and start I.K.E. again as usual.")


if __name__ == "__main__":
    main()
