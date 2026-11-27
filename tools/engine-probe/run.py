#!/usr/bin/env python3
"""Engine probe: what websites can observe of a browser's engine, collected
the same way from several browsers on the same computer (the Engine Privacy
Layer study, 2026-11; since 1.1.29 the weekly check engine-identity.yml).
Not part of the browser, not in the package.

    python3 tools/engine-probe/run.py OUT_DIR TARGET [TARGET...]

TARGET is one of
    qt                    Qt WebEngine as it is (a bare PyQt6 window, no I.K.E.)
    qt+FLAGS              the same with QTWEBENGINE_CHROMIUM_FLAGS=FLAGS
    ike:LEVEL             I.K.E. of this checkout at a protection level
                          (off, compatibility, balanced, strict, maximum)
    ike:LEVEL+FLAGS       the same with extra engine switches
    chrome:NAME=BINARY    a Chromium-family browser (Chromium, Chrome, Brave...)
optionally followed by "@label" to name the result file.

Each target opens http://127.0.0.1:PORT/probe.html under the current X
display; the page posts what it found, the local server adds the request
headers it received, the TLS ClientHello and the HTTP/2 preface (a fetch to
https://localhost:TLSPORT). One JSON file per target in OUT_DIR.

The engine's sandbox is off for every target (the tests run as root in a
container); it is not visible to web pages. --ignore-certificate-errors is
used only so that the local HTTPS probe can complete its handshake.
"""

import hashlib
import json
import os
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("PROBE_REPO") or HERE.parent.parent)
TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "150"))
PDF = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")

STATE = {"results": {}, "headers": {}, "tls": {}, "current": None}
LOCK = threading.Lock()


# ---- HTTP: the probe's files, the request headers, the results ------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _record(self):
        path = self.path.split("?")[0]
        name = STATE["current"]
        with LOCK:
            STATE["headers"].setdefault(name, []).append(
                {"path": path, "method": self.command, "headers": list(self.headers.items())})

    def _send(self, code, body, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # every client hint, to see which ones each engine sends on the next request
        self.send_header("Accept-CH", "Sec-CH-UA-Arch, Sec-CH-UA-Bitness, Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List, "
                         "Sec-CH-UA-Model, Sec-CH-UA-Platform-Version, Sec-CH-UA-WoW64, Sec-CH-UA-Form-Factors, Sec-CH-Prefers-Color-Scheme, "
                         "Sec-CH-Prefers-Reduced-Motion, Sec-CH-Prefers-Reduced-Transparency, Sec-CH-Viewport-Width, Sec-CH-Viewport-Height, "
                         "Sec-CH-DPR, Sec-CH-Device-Memory, Device-Memory, DPR, Viewport-Width, RTT, Downlink, ECT, Save-Data")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        path = self.path.split("?")[0]
        files = {"/probe.html": "text/html", "/probe-core.js": "text/javascript", "/probe-worker.js": "text/javascript",
                 "/vendor/wasm-feature-detect.js": "text/javascript", "/behaviour.html": "text/html", "/extra.html": "text/html", "/chrome-shape.html": "text/html"}
        if path in files and (HERE / path.lstrip("/")).is_file():
            self._send(200, (HERE / path.lstrip("/")).read_bytes(), files[path] + "; charset=utf-8")
        elif path.startswith("/ara/"):
            # an advertiser's response: does the engine store an attribution source, ask for topics?
            body = b"GIF89a"
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Attribution-Reporting-Register-Source",
                             '{"destination":"https://shop.example","source_event_id":"12345","expiry":"604800"}')
            self.send_header("Observe-Browsing-Topics", "?1")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/x.pdf":
            self._send(200, PDF, "application/pdf")
        elif path == "/hdr/img":
            self._send(200, bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"), "image/gif")
        elif path == "/hdr/script":
            self._send(200, b"/* */", "text/javascript")
        elif path == "/hdr/style":
            self._send(200, b"/* */", "text/css")
        elif path == "/favicon.ico":
            self._send(404, b"", "text/plain")
        else:
            self._send(200, b"ok", "text/plain")

    def do_POST(self):
        self._record()
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if self.path.startswith("/result"):
            try:
                data = json.loads(body)
            except ValueError:
                data = {"fatal": "unreadable result"}
            with LOCK:
                STATE["results"][STATE["current"]] = data
        self._send(200, b"ok", "text/plain")

    def log_message(self, *a):
        pass


# ---- TLS: the ClientHello and the HTTP/2 preface ----------------------------

def grease(v):
    return (v & 0x0f0f) == 0x0a0a and (v >> 8) == (v & 0xff)


def parse_client_hello(rec):
    """The fields of a TLS ClientHello (one record)."""
    p = 5 + 4                       # record header, handshake header
    out = {"record_version": "%04x" % struct.unpack(">H", rec[1:3])[0]}
    out["legacy_version"] = "%04x" % struct.unpack(">H", rec[p:p + 2])[0]
    p += 2 + 32
    sid = rec[p]
    p += 1 + sid
    out["session_id_len"] = sid
    n = struct.unpack(">H", rec[p:p + 2])[0]
    p += 2
    ciphers = [struct.unpack(">H", rec[p + i:p + i + 2])[0] for i in range(0, n, 2)]
    p += n
    out["ciphers"] = ["GREASE" if grease(c) else "%04x" % c for c in ciphers]
    n = rec[p]
    p += 1 + n
    n = struct.unpack(">H", rec[p:p + 2])[0]
    p += 2
    end = p + n
    exts, info = [], {}
    while p + 4 <= end:
        t, ln = struct.unpack(">HH", rec[p:p + 4])
        d = rec[p + 4:p + 4 + ln]
        p += 4 + ln
        exts.append("GREASE" if grease(t) else t)
        if t == 10:
            info["groups"] = ["GREASE" if grease(g) else "%04x" % g for g in struct.unpack(">%dH" % (len(d[2:]) // 2), d[2:])]
        elif t == 13:
            info["sigalgs"] = ["GREASE" if grease(g) else "%04x" % g for g in struct.unpack(">%dH" % (len(d[2:]) // 2), d[2:])]
        elif t == 16:
            q, protos = 2, []
            while q < len(d):
                ln2 = d[q]
                protos.append(d[q + 1:q + 1 + ln2].decode("latin-1"))
                q += 1 + ln2
            info["alpn"] = protos
        elif t == 43:
            info["versions"] = ["GREASE" if grease(g) else "%04x" % g for g in struct.unpack(">%dH" % (d[0] // 2), d[1:1 + d[0]])]
        elif t == 51:
            q, shares = 2, []
            while q + 4 <= len(d):
                g, ln2 = struct.unpack(">HH", d[q:q + 4])
                shares.append(("GREASE" if grease(g) else "%04x" % g) + "/%d" % ln2)
                q += 4 + ln2
            info["key_shares"] = shares
        elif t in (17513, 17613):
            q, protos = 2, []
            while q < len(d):
                ln2 = d[q]
                protos.append(d[q + 1:q + 1 + ln2].decode("latin-1"))
                q += 1 + ln2
            info["alps_%d" % t] = protos
        elif t == 27:
            info["cert_compression"] = ["%04x" % g for g in struct.unpack(">%dH" % (d[0] // 2), d[1:1 + d[0]])]
        elif t == 45:
            info["psk_modes"] = list(d[1:])
        elif t == 11:
            info["ec_point_formats"] = list(d[1:])
        elif t == 0xfe0d:
            info["ech_len"] = ln
        elif t == 21:
            info["padding_len"] = ln
        elif t == 28:
            info["record_size_limit"] = struct.unpack(">H", d)[0]
    out["extensions"] = exts
    out.update(info)
    real = [e for e in exts if e != "GREASE"]
    out["extensions_sorted"] = sorted(real)
    # JA4 (FoxIO), computed from the fields above
    cs = sorted(c for c in out["ciphers"] if c != "GREASE")
    ex = sorted("%04x" % e for e in real if e not in (0, 16))
    alpn = (info.get("alpn") or ["00"])[0]
    ver = max((v for v in info.get("versions", []) if v != "GREASE"), default="0303")
    vtag = {"0304": "13", "0303": "12"}.get(ver, "00")
    a = "t%s%s%02d%02d%s" % (vtag, "d" if 0 in real else "i", min(len(cs), 99), min(len(real), 99), alpn[0] + alpn[-1])
    b = hashlib.sha256(",".join(cs).encode()).hexdigest()[:12]
    c = hashlib.sha256((",".join(ex) + "_" + ",".join(x for x in info.get("sigalgs", []) if x != "GREASE")).encode()).hexdigest()[:12]
    out["ja4"] = "%s_%s_%s" % (a, b, c)
    # JA3 with the extensions sorted (Chrome shuffles their order since 110)
    ja3n = "771,%s,%s,%s,%s" % ("-".join(str(int(c, 16)) for c in out["ciphers"] if c != "GREASE"),
                                "-".join(str(e) for e in sorted(real)),
                                "-".join(str(int(g, 16)) for g in info.get("groups", []) if g != "GREASE"),
                                "-".join(str(x) for x in info.get("ec_point_formats", [])))
    out["ja3n"] = ja3n
    out["ja3n_md5"] = hashlib.md5(ja3n.encode()).hexdigest()
    return out


STATIC = {1: ":authority", 2: ":method", 3: ":method", 4: ":path", 5: ":path", 6: ":scheme", 7: ":scheme",
          8: ":status", 9: ":status", 10: ":status", 11: ":status", 12: ":status", 13: ":status", 14: ":status"}


def h2_preface(conn):
    """SETTINGS, WINDOW_UPDATE, PRIORITY and the first HEADERS frame of an
    HTTP/2 client (Akamai's fingerprint)."""
    buf = b""
    conn.settimeout(5)
    out = {"settings": [], "window_update": None, "priority": [], "headers": None}
    try:
        while len(buf) < 24:
            chunk = conn.recv(65536)
            if not chunk:
                return out
            buf += chunk
        if buf[:24] != b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n":
            return {"not_h2": buf[:40].decode("latin-1")}
        buf = buf[24:]
        conn.sendall(b"\x00\x00\x00\x04\x00\x00\x00\x00\x00")          # our empty SETTINGS
        while True:
            while len(buf) < 9:
                chunk = conn.recv(65536)
                if not chunk:
                    return out
                buf += chunk
            ln = int.from_bytes(buf[:3], "big")
            typ, flags = buf[3], buf[4]
            sid = int.from_bytes(buf[5:9], "big") & 0x7fffffff
            while len(buf) < 9 + ln:
                chunk = conn.recv(65536)
                if not chunk:
                    return out
                buf += chunk
            payload, buf = buf[9:9 + ln], buf[9 + ln:]
            if typ == 4 and not flags & 1:
                out["settings"] = ["%d:%d" % struct.unpack(">HI", payload[i:i + 6]) for i in range(0, len(payload), 6)]
            elif typ == 8:
                out["window_update"] = struct.unpack(">I", payload[:4])[0] & 0x7fffffff
            elif typ == 2:
                out["priority"].append([sid, payload.hex()])
            elif typ == 1:
                p = 0
                pad = 0
                if flags & 0x8:
                    pad = payload[0]
                    p = 1
                prio = None
                if flags & 0x20:
                    dep = struct.unpack(">I", payload[p:p + 4])[0]
                    prio = {"exclusive": bool(dep >> 31), "depends": dep & 0x7fffffff, "weight": payload[p + 4] + 1}
                    p += 5
                block = payload[p:len(payload) - pad]
                order, q = [], 0
                while q < len(block) and len(order) < 4:
                    b = block[q]
                    if b & 0x80:                        # indexed
                        idx = b & 0x7f
                        order.append(STATIC.get(idx, "idx%d" % idx))
                        q += 1
                        continue
                    if b & 0x40:
                        idx = b & 0x3f
                    elif b & 0x20:                      # table size update
                        q += 1
                        continue
                    else:
                        idx = b & 0x0f
                    if idx == 0:
                        break
                    order.append(STATIC.get(idx, "idx%d" % idx))
                    q += 1
                    vlen = block[q] & 0x7f
                    q += 1 + vlen
                out["headers"] = {"flags": flags, "priority": prio, "pseudo_order": order}
                s = out
                s["akamai"] = "%s|%s|%s|%s" % (
                    ";".join(s["settings"]), s["window_update"] or "00",
                    ",".join("%d:%s" % (a, b) for a, b in s["priority"]) or "0",
                    ",".join(x[1] for x in order if x.startswith(":")))
                return out
    except (socket.timeout, OSError) as e:
        out["error"] = str(e)
        return out


def tls_server(cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)

    def one(conn):
        name = STATE["current"]
        try:
            conn.settimeout(5)
            data = b""
            while True:
                data = conn.recv(65536, socket.MSG_PEEK)
                if len(data) >= 5 and len(data) >= 5 + struct.unpack(">H", data[3:5])[0]:
                    break
                time.sleep(0.02)
            hello = parse_client_hello(data)
            entry = {"hello": hello}
            try:
                s = ctx.wrap_socket(conn, server_side=True)
                entry["alpn"] = s.selected_alpn_protocol()
                entry["tls_version"] = s.version()
                if entry["alpn"] == "h2":
                    entry["h2"] = h2_preface(s)
                s.close()
            except (ssl.SSLError, OSError) as e:
                entry["handshake"] = str(e)
            with LOCK:
                STATE["tls"].setdefault(name, []).append(entry)
        except Exception as e:                  # noqa: BLE001 (a diagnostic: record and go on)
            with LOCK:
                STATE["tls"].setdefault(name, []).append({"error": repr(e)})
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def loop():
        while True:
            c, _ = srv.accept()
            threading.Thread(target=one, args=(c,), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    return srv.getsockname()[1]


# ---- the browsers -------------------------------------------------------------

QT_SCRIPT = r'''
import sys, os
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
app = QApplication(sys.argv)
prof = QWebEngineProfile("probe")
prof.setPersistentStoragePath(os.environ["PROBE_PROFILE"])
prof.setCachePath(os.environ["PROBE_PROFILE"] + "/cache")
page = QWebEnginePage(prof)
page.certificateError.connect(lambda e: e.acceptCertificate())
view = QWebEngineView()
view.setPage(page)
view.resize(1280, 800)
view.show()
view.titleChanged.connect(lambda t: t == "probe done" and QTimer.singleShot(300, app.quit))
view.load(QUrl(sys.argv[1]))
QTimer.singleShot(%d * 1000, app.quit)
app.exec()
'''

IKE_STEPS = r'''
from PyQt6.QtCore import QUrl
import os

def steps(ike, qapp, out):
    w = ike.windows[0]
    w.resize(1280, 800)
    view = w.current_view()
    view.load(QUrl(os.environ["PROBE_URL"]))
    for _ in range(%d * 10):
        if view.page().title() == "probe done":
            break
        yield 100
    out["title"] = view.page().title()
'''


def run_target(target, url, outdir):
    label = None
    if "@" in target:
        target, label = target.rsplit("@", 1)
    flags = ""
    base = target
    if "+" in target:
        base, flags = target.split("+", 1)
    name = label or target.replace("/", "_").replace(" ", "_")[:80]
    tmp = Path(tempfile.mkdtemp(prefix="probe-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("IKE_", "QTWEBENGINE_"))}
    env.update({"LANG": "en_US.UTF-8", "LANGUAGE": "en_US", "TZ": "Europe/Rome", "HOME": str(tmp / "home")})
    (tmp / "home").mkdir()
    full = url + "&name=" + name
    if base == "qt":
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = ("--no-sandbox --ignore-certificate-errors " + flags).strip()
        env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
        env["PROBE_PROFILE"] = str(tmp / "profile")
        (tmp / "qt.py").write_text(QT_SCRIPT % TIMEOUT)
        cmd = [sys.executable, str(tmp / "qt.py"), full]
    elif base.startswith("ike:"):
        level = base.split(":", 1)[1]
        sys.path.insert(0, str(REPO / "tests"))
        from conftest import write_profile               # the automatic tests' quiet profile
        settings = {"shield_level": level}
        settings.update(json.loads(os.environ.get("PROBE_SETTINGS", "{}")))
        write_profile(tmp / "home/.config/ike-browser", tmp / "home/.local/share/ike-browser", settings)
        (tmp / "steps.py").write_text(IKE_STEPS % TIMEOUT)
        (tmp / "run").mkdir(mode=0o700)
        env.update({"XDG_CONFIG_HOME": str(tmp / "home/.config"), "XDG_DATA_HOME": str(tmp / "home/.local/share"),
                    "XDG_CACHE_HOME": str(tmp / "home/.cache"), "XDG_RUNTIME_DIR": str(tmp / "run"),
                    "QTWEBENGINE_CHROMIUM_FLAGS": ("--no-sandbox " + flags).strip(), "QTWEBENGINE_DISABLE_SANDBOX": "1",
                    "IKE_ALLOW_UNSAFE_ENGINE": "1", "IKE_NO_SINGLE": "1", "IKE_TEST_NOASK": "1", "IKE_TEST_INSECURE": "1",
                    "IKE_TEST_HOOK": str(REPO / "tests/harness.py"), "IKE_TEST_SCRIPT": str(tmp / "steps.py"),
                    "IKE_TEST_OUT": str(tmp / "out.json"), "PROBE_URL": full, "DBUS_SESSION_BUS_ADDRESS": ""})
        cmd = [sys.executable, str(REPO / "ike_boot.py")]
    elif base.startswith("chrome:"):
        nm, binary = base.split(":", 1)[1].split("=", 1)
        extra = flags.split() if flags else []
        cmd = [binary, "--user-data-dir=%s" % (tmp / "profile"), "--no-first-run", "--no-default-browser-check",
               "--no-sandbox", "--ignore-certificate-errors", "--password-store=basic", "--disable-dev-shm-usage",
               "--window-size=1280,800", *extra, full]
        if " " in binary:
            cmd = binary.split() + cmd[1:]
    else:
        raise SystemExit("unknown target " + target)
    STATE["current"] = name
    t0 = time.time()
    proc = subprocess.Popen(cmd, env=env, cwd=str(tmp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    end = t0 + TIMEOUT
    while time.time() < end and name not in STATE["results"] and proc.poll() is None:
        time.sleep(0.25)
    took = time.time() - t0
    time.sleep(1.0)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    log = proc.stdout.read().decode("utf-8", "replace")[-6000:]
    res = {"target": target, "cmd": cmd, "seconds": round(took, 1), "result": STATE["results"].get(name),
           "headers": STATE["headers"].get(name, []), "tls": STATE["tls"].get(name, []), "log": log}
    try:            # what the engine kept in the profile: advertising and network state
        res["profile_files"] = sorted(str(p.relative_to(tmp)) + ":" + str(p.stat().st_size) for p in tmp.rglob("*") if p.is_file()
                                      and any(x in p.name for x in ("Conversions", "InterestGroups", "SharedStorage", "BrowsingTopics",
                                                                    "Network Persistent State", "AggregationService")))
        import sqlite3
        for p in tmp.rglob("Conversions"):
            try:
                res["conversions_sources"] = sqlite3.connect(str(p)).execute("select count(*) from sources").fetchone()[0]
            except Exception as e:                     # noqa: BLE001
                res["conversions_err"] = repr(e)
    except Exception as e:                             # noqa: BLE001
        res["profile_err"] = repr(e)
    (Path(outdir) / (name + ".json")).write_text(json.dumps(res, indent=1, default=str))
    shutil.rmtree(tmp, ignore_errors=True)
    ok = "ok" if res["result"] else "NO RESULT"
    print("%-40s %s (%.0f s)" % (name, ok, took), flush=True)
    return res


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    certdir = Path(tempfile.mkdtemp(prefix="probe-cert-"))
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "2",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                    "-keyout", str(certdir / "k.pem"), "-out", str(certdir / "c.pem")], check=True, capture_output=True)
    tls_port = tls_server(str(certdir / "c.pem"), str(certdir / "k.pem"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    page = os.environ.get("PROBE_PAGE", "probe.html")
    url = "http://127.0.0.1:%d/%s?tls=%d" % (srv.server_address[1], page, tls_port)
    for t in sys.argv[2:]:
        run_target(t, url, outdir)


if __name__ == "__main__":
    main()
