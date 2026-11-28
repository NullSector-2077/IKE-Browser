#!/usr/bin/env python3
"""The web technologies page on http://localhost:PORT/ (a secure context):
static files, POST /upload echoes what it got, /file.bin is a download."""
import http.server
import sys
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm",
                      ".js": "text/javascript", ".webm": "video/webm", ".mp4": "video/mp4", ".ogg": "audio/ogg",
                      ".pdf": "application/pdf"}

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"upload ok %d bytes, has file: %s" % (len(body), b"yes" if b"ike upload test" in body else b"no"))

    def do_GET(self):
        if self.path.startswith("/file.bin"):
            data = b"ike" * 50000
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="ike-file.bin"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def end_headers(self):
        # conformance.html?csp=noblob: a site policy without blob: workers (1.1.32)
        if "csp=noblob" in self.path:
            self.send_header("Content-Security-Policy", "worker-src 'self'; script-src 'self' 'unsafe-inline'")
        super().end_headers()

    def log_message(self, *a):
        pass


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(H, directory=str(HERE))).serve_forever()
