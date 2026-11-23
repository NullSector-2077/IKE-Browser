"""Safer downloads (1.1.24, ike/safedownload.py).

- A program or a script (AppImage, .run, .sh, .exe, .msi, .deb, .rpm, .jar, .py, .bat,
  .cmd, .ps1, .desktop, or its MIME type) from a site on I.K.E.'s protection lists or
  from a site the user never visited before: a question first.
- A file over http from an https page (a mixed download): stopped, with a question.

Both questions: "Cancel" is the default (and Esc), "Download anyway" works only after a
moment and lets that one download through, at the user's risk. No network lookups.
"""

import http.server
import sys
import threading

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT))
from ike import safedownload  # noqa: E402
from ike.storage import Storage  # noqa: E402


def test_programs_and_scripts_by_name_and_type():
    for name in ("tool.AppImage", "setup.run", "install.sh", "setup.exe", "pack.msi", "app.deb", "app.rpm",
                 "app.jar", "script.py", "run.bat", "run.cmd", "do.ps1", "evil.desktop", "SETUP.EXE",
                 "trick.sh.", "trick.exe  ", "two.tar.sh"):
        assert safedownload.is_executable(name), name
    for mime in ("application/x-msdownload", "application/vnd.debian.binary-package", "application/x-rpm",
                 "application/java-archive", "text/x-python", "application/x-shellscript",
                 "application/vnd.appimage", "application/x-desktop", "application/x-sh; charset=utf-8"):
        assert safedownload.is_executable("file.bin", mime), mime
    for name, mime in (("photo.png", "image/png"), ("doc.pdf", "application/pdf"), ("a.zip", "application/zip"),
                       ("notes.txt", "text/plain"), ("shell.sh.txt", "text/plain"), ("x.exe.pdf", "")):
        assert not safedownload.is_executable(name, mime), name


def test_mixed_downloads():
    assert safedownload.is_mixed("https://site.example/page", "http://cdn.example/file.zip")
    assert safedownload.is_mixed("HTTPS://site.example/", "HTTP://site.example/f")
    for page, url in (("http://a/", "http://b/f"), ("https://a/", "https://b/f"), ("", "http://b/f"),
                      ("https://a/", "blob:https://a/1"), ("https://a/", "data:text/plain,x"), ("ike:newtab", "http://b")):
        assert not safedownload.is_mixed(page, url), (page, url)


class Lists:
    def __init__(self, hosts):
        self.hosts, self.asked = hosts, []

    def should_block(self, url, source, rtype):
        self.asked.append((url, rtype))
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname or ""
        return any(host == h or host.endswith("." + h) for h in self.hosts)       # as a ||site^ rule


def test_what_is_asked_and_when():
    lists = Lists({"malware.example"})
    known = lambda site, page: site == "known.example"          # noqa: E731
    risk = safedownload.risk
    # a mixed download is stopped whatever the file
    r = risk("http://files.example/photo.png", "https://known.example/p", "photo.png", "image/png", lists, known)
    assert r == {"kind": "mixed", "site": "known.example", "name": "photo.png"}
    # a program: from a listed site (the page's or the file's), from a new site, from a known one
    assert risk("https://malware.example/x.exe", "https://known.example/p", "x.exe", "", lists, known)["kind"] == "listed"
    assert risk("https://cdn.example/x.exe", "https://www.malware.example/p", "x.exe", "", lists, known)["kind"] == "listed"
    r = risk("https://cdn.example/tool", "https://new.example/download", "tool", "application/x-msdownload",
             lists, known)
    assert r == {"kind": "new", "site": "new.example", "name": "tool"}
    assert risk("https://cdn.example/a.AppImage", "https://www.known.example/d", "a.AppImage", "", lists, known) is None
    # the name in the address counts too (a server that gives no name)
    assert risk("https://new.example/get/setup.msi", "https://new.example/", "", "", lists, known)["kind"] == "new"
    # not a program: nothing to ask
    assert risk("https://new.example/a.zip", "https://new.example/", "a.zip", "application/zip", lists, known) is None
    # typed in the address bar (no page of a site): the file's own site
    assert risk("https://new.example/i.sh", "ike:newtab", "i.sh", "", lists, known)["site"] == "new.example"
    assert risk("https://known.example/i.sh", "", "i.sh", "", lists, known) is None
    # local files are no site: nothing asked about visits
    assert risk("file:///home/u/i.sh", "file:///home/u/", "i.sh", "", lists, known) is None
    # the lists are asked about pages only, never over the network
    assert {t for _u, t in lists.asked} == {"document"}
    # a broken engine never stops a download by itself
    class Broken:
        def should_block(self, *a):
            raise RuntimeError("engine")
    assert risk("https://known.example/x.exe", "https://known.example/", "x.exe", "", Broken(), known) is None


def test_a_site_visited_before(tmp_path):
    s = Storage(tmp_path / "ike.sqlite")
    assert not s.visited_before("site.example", "https://site.example/dl")
    s.add_visit("https://site.example/dl", "Download")
    # the page that offers the file, seen once just now: not "visited before"
    assert not s.visited_before("site.example", "https://site.example/dl")
    s.add_visit("https://site.example/dl", "Download")
    assert s.visited_before("site.example", "https://site.example/dl")             # twice
    t = Storage(tmp_path / "other.sqlite")
    t.add_visit("https://www.site.example/", "Home")
    assert t.visited_before("site.example", "https://dl.site.example/get")          # another page, another host
    assert not t.visited_before("ite.example", "")                                   # not a part of a name
    t.add_visit("https://notsite.example/", "x")
    assert not t.visited_before("site.exampl", "") and not t.visited_before("e.example", "")
    t.add_visit("https://a_b.example/", "x")
    assert t.visited_before("a_b.example", "") and not t.visited_before("a%b.example", "")
    assert not t.visited_before("", "")


@pytest.fixture
def tools_site():
    files = {"/tool.sh": b"#!/bin/sh\necho hello\n", "/notes.txt": b"just text\n"}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in files:
                body = files[path]
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=%s" % path[1:])
            else:
                body = (b"<!doctype html><title>page</title><a id=a href='/tool.sh'>tool</a>"
                        b"<a id=b href='/notes.txt'>notes</a>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import os
from pathlib import Path
SITE, FOLDER = %r, %r

def load(view, url):
    from PyQt6.QtCore import QUrl
    done = {}
    view.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    view.load(QUrl(url))
    for _ in range(200):
        if "ok" in done:
            break
        yield 25
    yield 300

def click(view, element):
    view.page().runJavaScript("document.getElementById('%%s').click()" %% element)

def files():
    return sorted(p.name for p in Path(FOLDER).glob("*")) if Path(FOLDER).exists() else []

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QMessageBox
    from ike import webview
    ike.BURST_SECONDS = 0       # the clicks below are a script's: not a burst of downloads here
    win = ike.windows[0]
    view = win.current_view()
    yield 1500
    # a script on a page seen for the first time: the question, "Cancel" the default
    yield from load(view, SITE + "/first")
    click(view, "a")
    for _ in range(60):
        yield 100
        if getattr(ike, "_risk_box", None) is not None and ike._risk_box.isVisible():
            break
    box = ike._risk_box
    buttons = {b.text(): b for b in box.buttons()}
    out["first"] = {"text": box.text(), "more": box.informativeText(), "buttons": sorted(buttons),
                    "default": box.defaultButton().text(), "escape": box.escapeButton().text(),
                    "anyway_at_once": buttons["Download anyway"].isEnabled()}
    buttons["Cancel"].click()
    yield 1500
    out["after_cancel"] = [files(), len(ike.downloads)]
    # again, and this time "Download anyway" (it works after a moment)
    click(view, "a")
    for _ in range(60):
        yield 100
        if ike._risk_box is not box and ike._risk_box.isVisible():
            break
    box = ike._risk_box
    yield webview.SAFE_DELAY_MS + 200
    [b for b in box.buttons() if b.text() == "Download anyway"][0].click()
    for _ in range(40):
        yield 100
        if files():
            break
    yield 500
    out["after_anyway"] = files()
    # a site visited before (another of its pages): no question
    for p in Path(FOLDER).glob("*"):
        p.unlink()
    asked = []
    real = type(ike)._ask_download_risk
    type(ike)._ask_download_risk = lambda self, found, anyway: asked.append(found)
    yield from load(view, SITE + "/second")
    click(view, "a")
    yield 2000
    out["known"] = [asked, files()]
    # a file that is not a program, from a site never visited: never asked
    yield from load(view, "http://localhost:" + SITE.rsplit(":", 1)[1] + "/third")
    click(view, "b")
    yield 2000
    out["text_file"] = [asked, files()]
    type(ike)._ask_download_risk = real

    # a mixed download (an https page, the file over http): stopped, then let through once
    class Page:
        def __init__(self):
            self.asked = []
        def url(self):
            return QUrl("https://secure.example/page")
        def download(self, url, name):
            self.asked.append([url.toString(), name])
    class Item:
        def __init__(self, url, page):
            self._url, self._page, self.cancelled = QUrl(url), page, False
        def url(self): return self._url
        def page(self): return self._page
        def isSavePageDownload(self): return False
        def downloadFileName(self): return "photo.jpg"
        def mimeType(self): return "image/jpeg"
        def cancel(self): self.cancelled = True
    page = Page()
    item = Item("http://plain.example/photo.jpg", page)
    stopped = ike._download_risk(item)
    yield 300
    box = ike._risk_box
    out["mixed"] = [stopped, item.cancelled, box.text(), box.defaultButton().text()]
    yield webview.SAFE_DELAY_MS + 200
    [b for b in box.buttons() if b.text() == "Download anyway"][0].click()
    yield 300
    again = Item("http://plain.example/photo.jpg", page)
    out["mixed_anyway"] = [page.asked, ike._download_passed(again), ike._download_passed(again)]
'''


def test_a_program_from_a_new_site_asks_first(run_ike, tools_site, tmp_path):
    folder = tmp_path / "dl"
    out = run_ike(STEPS % (tools_site, str(folder)), timeout=150,
                  settings={"download_dir": str(folder), "ask_download_location": False})
    first = out["first"]
    assert first["text"] == ("tool.sh is a program or a script, and you have never visited 127.0.0.1 before. "
                             "Download it only if you trust the site."), first
    assert first["more"] == "If you download it anyway, it is at your own risk."
    assert first["buttons"] == ["Cancel", "Download anyway"]
    assert first["default"] == first["escape"] == "Cancel" and first["anyway_at_once"] is False
    assert out["after_cancel"] == [[], 0]
    assert out["after_anyway"] == ["tool.sh"]
    assert out["known"] == [[], ["tool.sh"]]
    assert out["text_file"] == [[], ["notes.txt", "tool.sh"]]
    stopped, cancelled, text, default = out["mixed"]
    assert stopped is True and cancelled is True and default == "Cancel"
    assert text.startswith("I.K.E. stopped the download of photo.jpg: the page is secure (https)")
    page_asked, first_pass, second_pass = out["mixed_anyway"]
    assert page_asked == [["http://plain.example/photo.jpg", "photo.jpg"]]
    assert first_pass is True and second_pass is False                # once, for that address only
