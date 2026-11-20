"""The languages I.K.E. asks websites for (1.1.18, docs review): the system's
own unless the user typed a list. Until 1.1.18 every new profile asked for
"it-IT,it,en-US,en" whatever the system's language - Italian pages for
everyone, and a rare combination that singled out every non-Italian user. The
old default now follows the system; a list the user typed stays. Maximum
still sends a common "en-US,en" (fingerprinting protection, unchanged)."""

import http.server
import json
import sys
import threading

import pytest
from conftest import APP

sys.path.insert(0, str(APP))
from ike import config as ike_config  # noqa: E402


def test_the_system_language_as_chrome_sends_it():
    f = ike_config.system_accept_language
    assert f("de_DE.UTF-8") == "de-DE,de,en-US,en"
    assert f("it_IT.UTF-8") == "it-IT,it,en-US,en"
    assert f("en_US.UTF-8") == "en-US,en"
    assert f("C.UTF-8") == f("") == "en-US,en"
    assert f("sr_RS@latin") == "sr-RS,sr,en-US,en"


def test_the_old_italian_default_follows_the_system(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"accept_language": "it-IT,it,en-US,en"}))
    assert ike_config.Config(p)["accept_language"] == ""
    p.write_text(json.dumps({"accept_language": "fr-FR,fr"}))
    assert ike_config.Config(p)["accept_language"] == "fr-FR,fr"           # the user's own list stays


@pytest.fixture
def server():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Accept-Language", ""))
            body = b"<title>ok</title>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


STEPS = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    v.load(QUrl("http://127.0.0.1:%d/"))
    yield 2500
'''


def test_a_german_system_asks_for_german(run_ike, server):
    port, seen = server
    run_ike(STEPS % port, env={"LANG": "de_DE.UTF-8"}, settings={"shield_level": "balanced"}, timeout=60)
    assert seen and seen[0].startswith("de-DE,de"), seen
