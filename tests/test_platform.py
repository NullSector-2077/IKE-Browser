"""Operating-system details (ike/osinfo.py, ike/drm.py)."""

import io
import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import ROOT

from ike import drm, osinfo


def test_folders(monkeypatch):
    for v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(v, raising=False)
    home = Path.home()
    assert osinfo.app_dir("config") == home / ".config" / "ike-browser"
    assert osinfo.app_dir("data") == home / ".local/share" / "ike-browser"
    assert osinfo.app_dir("cache") == home / ".cache" / "ike-browser"


def test_folders_follow_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert osinfo.app_dir("data") == tmp_path / "xdg" / "ike-browser"


def test_update_folder_agrees(tmp_path):
    """ike_boot.py (a system part, which cannot import ike/) and the updater
    must use the same folder for updates."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    code = ("import sys; sys.path.insert(0, %r); import ike_boot, ike.updater; "
            "print(ike_boot.UPDATES == ike.updater.UPDATES, ike_boot.UPDATES)" % str(ROOT))
    env["QT_QPA_PLATFORM"] = "offscreen"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert res.stdout.startswith("True"), res.stdout + res.stderr


def test_identity():
    ident = osinfo.identity()
    assert osinfo.chrome_user_agent(140) == (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36")
    # 1.1.25: no kernel version, as the engine itself gives it to service and shared workers
    assert (ident["platform"], ident["platform_version"]) == ("Linux", "")


# ---- Widevine module checks -------------------------------------------------

def pe(machine=0x8664, size=4096):
    """A Windows library: never accepted."""
    data = bytearray(size)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, machine, 1, 0, 0, 0, 0xF0, 0x2022)
    return bytes(data)


def elf(machine=62):
    data = bytearray(4096)
    data[:4] = b"\x7fELF"
    data[4], data[5] = 2, 1
    struct.pack_into("<HH", data, 16, 3, machine)
    return bytes(data)


def test_widevine_library_checks():
    drm.check_library(elf())
    for bad in (pe(), elf(machine=183), b"\x7fELF" + b"\0" * 100, b"not a library" * 10):
        with pytest.raises(drm.DrmError):
            drm.check_library(bad)


def test_widevine_archive(tmp_path, monkeypatch):
    """A Linux archive installs; one with another kind of library, or with
    names that try to leave the folder, does not write outside it."""
    monkeypatch.setattr(drm, "OWN_DIR", tmp_path / "WidevineCdm")
    lib, other = elf(), pe()

    def archive(name, data, extra=()):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("manifest.json", json.dumps({"version": "4.10.9999.0", "arch": "x64"}))
            z.writestr(name, data)
            for n, d in extra:
                z.writestr(n, d)
        return buf.getvalue()

    assert drm.install_from_zip(archive("_platform_specific/x/" + drm.LIB_NAME, lib)) == "4.10.9999.0"
    assert (tmp_path / "WidevineCdm" / "_platform_specific" / drm.PLATFORM_DIR / drm.LIB_NAME).is_file()
    with pytest.raises(drm.DrmError):
        drm.install_from_zip(archive(drm.LIB_NAME, other))
    drm.install_from_zip(archive("../../" + drm.LIB_NAME, lib, [("../../evil.txt", b"x")]))
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()
    assert sorted(p.name for p in (tmp_path / "WidevineCdm").rglob("*") if p.is_file()) == sorted([
        drm.LIB_NAME, "manifest.json"])


# ---- Widevine from Chrome's component updater (1.1.23) -----------------------
# Offline: a fake update service and fake download servers answer the requests.

PROD = "140.0.7339.264"


def _pb(number, payload):
    """One length-delimited protocol buffer field."""
    def varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            out += bytes([b | (0x80 if n else 0)])
            if not n:
                return out
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def _widevine_zip(version="4.10.9999.0", arch="x64", lib=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"name": "WidevineCdm", "version": version, "arch": arch}))
        z.writestr("_platform_specific/linux_x64/" + drm.LIB_NAME, lib or elf())
        z.writestr("LICENSE", "Google's licence")
    return buf.getvalue()


@pytest.fixture(scope="module")
def component_key():
    """A signing key standing in for Widevine's own (the real one is Google's)."""
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(65537, 2048)
    pub = key.public_key().public_bytes(serialization.Encoding.DER,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    digest = hashlib.sha256(pub).digest()[:16]
    app_id = "".join("abcdefghijklmnop"[c >> 4] + "abcdefghijklmnop"[c & 15] for c in digest)
    return key, pub, app_id


def _crx3(archive, key, pub, named=None):
    """A CRX3 package signed as Chrome's components are (the component's key)."""
    import hashlib

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    signed = _pb(1, hashlib.sha256(named or pub).digest()[:16])
    message = b"CRX3 SignedData\x00" + struct.pack("<I", len(signed)) + signed + archive
    sig = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    header = _pb(2, _pb(1, pub) + _pb(2, sig)) + _pb(10000, signed)
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + archive


def _answer(app_id, package=b"", version="4.10.9999.0", status="ok",
            codebases=("https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/",),
            sha256=None, name=None):
    """The update service's answer, with its XSSI prefix."""
    import hashlib
    check = {"status": status}
    if status == "ok":
        check["urls"] = {"url": [{"codebase": c} for c in codebases]}
        check["manifest"] = {"version": version, "packages": {"package": [{
            "name": name or "%s_%s_linux_x64.crx3" % (app_id, version),
            "hash_sha256": sha256 or hashlib.sha256(package).hexdigest(),
            "size": len(package), "required": True}]}}
    body = {"response": {"server": "prod", "protocol": "3.1",
                         "app": [{"appid": app_id, "status": "ok", "updatecheck": check}]}}
    return (")]}'\n" + json.dumps(body)).encode()


class _Server:
    """Stands in for the network: answers by address, records every request."""

    def __init__(self, pages, redirect=None):
        self.pages, self.redirect, self.seen = pages, redirect or {}, []

    def __call__(self, req):
        import urllib.error
        url = req.full_url
        self.seen.append((req.get_method(), url, req.data, dict(req.header_items())))
        if url not in self.pages:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        server = self

        class Reply(io.BytesIO):
            def geturl(self):
                return server.redirect.get(url, url)
        return Reply(self.pages[url])

    def urls(self):
        return [u for _m, u, _d, _h in self.seen]


@pytest.fixture
def widevine(tmp_path, monkeypatch, component_key):
    """drm with I.K.E.'s folder in tmp_path, Widevine's id that of the test key
    and the engine's version fixed; returns (key, pub, app_id, serve)."""
    from ike import chromever
    key, pub, app_id = component_key
    monkeypatch.setattr(drm, "OWN_DIR", tmp_path / "WidevineCdm")
    monkeypatch.setattr(drm, "OWN_LIB", tmp_path / "WidevineCdm" / "_platform_specific" / drm.PLATFORM_DIR
                        / drm.LIB_NAME)
    monkeypatch.setattr(drm, "SYSTEM_LIBS", ())
    monkeypatch.setattr(drm, "APP_ID", app_id)
    monkeypatch.setattr(chromever, "engine_full", lambda: PROD)

    def serve(pages, redirect=None):
        server = _Server(pages, redirect)
        monkeypatch.setattr(drm, "_open", server)
        return server
    return key, pub, app_id, serve


def _offer(widevine, package, **kw):
    key, pub, app_id, serve = widevine
    answer = _answer(app_id, package, **kw)
    name = kw.get("name") or "%s_%s_linux_x64.crx3" % (app_id, kw.get("version", "4.10.9999.0"))
    pages = {drm.UPDATE_URL: answer}
    for base in kw.get("codebases", ("https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/",)):
        pages[base + name] = package
    return serve(pages)


def test_widevine_update_request_says_nothing_more(widevine):
    """The update check names only Widevine, a Chromium on x64 Linux and the
    engine's version: no cookies, no user or installation id, no other
    component, and never the installed copy's version."""
    key, pub, app_id, serve = widevine
    server = serve({drm.UPDATE_URL: _answer(app_id, status="noupdate")})
    with pytest.raises(drm.NotOffered):
        drm.query()
    [(method, url, body, headers)] = server.seen
    assert (method, url) == ("POST", "https://update.googleapis.com/service/update2/json")
    req = json.loads(body)["request"]
    assert sorted(req) == sorted(["protocol", "@updater", "@os", "updaterversion", "prodversion", "acceptformat",
                                  "arch", "nacl_arch", "os", "dedup", "ismachine", "requestid", "sessionid", "app"])
    assert (req["protocol"], req["@os"], req["arch"], req["nacl_arch"]) == ("3.1", "linux", "x64", "x86-64")
    assert req["os"] == {"platform": "Linux", "arch": "x86_64"}
    assert (req["prodversion"], req["acceptformat"]) == (PROD, "crx3")
    assert req["app"] == [{"appid": app_id, "version": "0.0.0.0", "enabled": True,
                           "installsource": "ondemand", "updatecheck": {}}]
    assert json.loads(drm.update_request(PROD))["request"]["requestid"] != req["requestid"]   # new each time
    names = {h.lower() for h in headers}
    assert "cookie" not in names and "authorization" not in names
    assert headers["User-agent"] == osinfo.browser_user_agent()
    assert headers["Content-type"] == "application/json"


def test_widevine_from_the_component_updater(widevine):
    key, pub, app_id, serve = widevine
    package = _crx3(_widevine_zip(), key, pub)
    server = _offer(widevine, package, codebases=(
        "http://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/",       # plain http: never used
        "https://evil.example/edgedl/",                                        # not Google's: never used
        "https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/"))
    assert drm.download() == "4.10.9999.0"
    assert server.urls() == [drm.UPDATE_URL, "https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/%s_"
                             "4.10.9999.0_linux_x64.crx3" % app_id]
    assert drm.status() == {"path": str(drm.OWN_LIB), "version": "4.10.9999.0", "source": "ike"}
    assert sorted(p.name for p in drm.OWN_DIR.rglob("*") if p.is_file()) == sorted(
        [drm.LIB_NAME, "manifest.json", "LICENSE.txt"])
    # asked again: already the newest, nothing downloaded
    server.seen.clear()
    assert drm.download("4.10.9999.0") == ""
    assert server.urls() == [drm.UPDATE_URL]
    assert drm.update_available() == ""
    assert drm.parse_answer(_answer(app_id, package, version="4.10.10000.0"))["version"] == "4.10.10000.0"


REFUSED = {"checksum": "checksum", "host": "no https address", "http": "no https address",
           "magic": "not a Chrome component package", "version3": "CRX3", "arch": "another architecture",
           "machine": "x86-64", "signature": "Widevine's own key", "other key": "Widevine's own key",
           "noupdate": '"noupdate"', "size": "size", "name": "unexpected file", "redirect": "insecure redirect"}


@pytest.mark.parametrize("case", ["checksum", "host", "http", "magic", "version3", "arch", "machine",
                                  "signature", "other key", "noupdate", "size", "name", "redirect"])
def test_widevine_refused(widevine, case):
    """Every one of these ends with nothing installed, and the old download
    folder tried after the component updater (it answers 404 here too)."""
    key, pub, app_id, serve = widevine
    good = _crx3(_widevine_zip(), key, pub)
    base = "https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/x/"
    kw = {}
    package = good
    if case == "checksum":
        kw["sha256"] = "0" * 64
    elif case == "host":
        kw["codebases"] = ("https://dl.google.com.evil.example/", "https://evilgoogle.com/")
    elif case == "http":
        kw["codebases"] = ("http://dl.google.com/release2/",)
    elif case == "magic":
        package = b"Cr25" + good[4:]
    elif case == "version3":
        package = b"Cr24" + struct.pack("<I", 2) + good[8:]
    elif case == "arch":
        package = _crx3(_widevine_zip(arch="arm64"), key, pub)
    elif case == "machine":
        package = _crx3(_widevine_zip(lib=elf(machine=183)), key, pub)
    elif case == "signature":
        package = good[:-40] + bytes([good[-40] ^ 1]) + good[-39:]
    elif case == "other key":                  # signed, but not by Widevine's key
        package = _crx3(_widevine_zip(), key, pub, named=b"Widevine's real key")
    elif case == "noupdate":
        kw["status"] = "noupdate"
    elif case == "size":
        package = _crx3(_widevine_zip(lib=elf() + b"\0" * 100), key, pub)
    elif case == "name":
        kw["name"] = "../../evil.crx3"
    server = _offer(widevine, package, **kw)
    if case == "size":
        server.pages[drm.UPDATE_URL] = _answer(app_id, good)
        server.pages[base + "%s_4.10.9999.0_linux_x64.crx3" % app_id] = package
    if case == "redirect":                    # the download ends up on plain http
        server.redirect[base + "%s_4.10.9999.0_linux_x64.crx3" % app_id] = "http://edgedl.me.gvt1.com/x.crx3"
    with pytest.raises(drm.NotOffered) as why:
        drm.download()
    assert REFUSED[case] in str(why.value), why.value
    assert drm.status()["source"] == ""
    assert not drm.OWN_DIR.exists()
    urls = server.urls()
    assert urls[0] == drm.UPDATE_URL and urls[-1] == drm.VERSIONS_URL
    assert all(u.startswith("https://") and drm.google_https(u) for u in urls)


def test_widevine_fallback_order(widevine):
    """The component updater first; the old dl.google.com folder only when it
    offers nothing; never the other way round."""
    key, pub, app_id, serve = widevine
    old_zip = drm.SOURCE + "4.10.8888.0-linux-x64.zip"
    server = serve({
        drm.UPDATE_URL: _answer(app_id, status="noupdate"),
        drm.VERSIONS_URL: b"4.10.7777.0\n4.10.8888.0\nnot-a-version\n",
        old_zip: _widevine_zip("4.10.8888.0"),
    })
    assert drm.download() == "4.10.8888.0"
    assert server.urls() == [drm.UPDATE_URL, drm.VERSIONS_URL, old_zip]
    # the old folder has nothing newer: not "already the newest", since the
    # component updater could not say so
    with pytest.raises(drm.NotOffered):
        drm.download("4.10.8888.0")
    # when the component updater offers a package, the old folder is not asked
    package = _crx3(_widevine_zip("4.10.9999.0"), key, pub)
    server = _offer(widevine, package)
    server.pages[drm.VERSIONS_URL] = b"4.10.8888.0\n"
    assert drm.update_available() == "4.10.9999.0"
    assert drm.download("4.10.8888.0") == "4.10.9999.0"
    assert drm.VERSIONS_URL not in server.urls()


def test_widevine_installer_explains_the_alternative(widevine):
    """When Google offers nothing usable the user reads that, and that the AUR
    package chromium-widevine (found by I.K.E. by itself) is another way."""
    key, pub, app_id, serve = widevine
    serve({drm.UPDATE_URL: _answer(app_id, status="noupdate")})
    job, got = drm.Installer(), []
    job.failed.connect(got.append)
    job.finished_ok.connect(lambda v: got.append("installed " + v))
    job.run()
    assert len(got) == 1 and "did not offer" in got[0] and "chromium-widevine" in got[0], got
    assert "noupdate" in got[0]


def test_widevine_real_answer():
    """The update service's real answer to update_request() (taken on
    2026-11-22): the https addresses only, in its order, and the package."""
    base = "edgedl.me.gvt1.com/edgedl/release2/chrome_component/acqexsh26ysyu3zxeotqtsp63idq_4.10.3112.0/"
    others = ("dl.google.com/release2/chrome_component/acqexsh26ysyu3zxeotqtsp63idq_4.10.3112.0/",
              "www.google.com/dl/release2/chrome_component/acqexsh26ysyu3zxeotqtsp63idq_4.10.3112.0/")
    name = "oimompecagnajdejgnnjijobebaeigek_4.10.3112.0_linux64_ad7kyx4q7wx7xknykmkbonbbmnwq.crx3"
    sha = "1bf1f200dcccd461b2d029d000d0fcf800f0571c932db31467b9d5d301e0a98f"
    urls = [{"codebase": scheme + b} for b in (base,) + others for scheme in ("http://", "https://")]
    answer = ")]}'\n" + json.dumps({"response": {
        "server": "prod", "protocol": "3.1", "daystart": {"elapsed_seconds": 50866, "elapsed_days": 7265},
        "app": [{"appid": "oimompecagnajdejgnnjijobebaeigek", "cohort": "1:3cjr:", "status": "ok",
                 "cohortname": "Auto", "updatecheck": {"status": "ok", "urls": {"url": urls}, "manifest": {
                     "version": "4.10.3112.0", "packages": {"package": [{
                         "hash_sha256": sha, "size": 21970001, "name": name, "fp": "1." + sha, "required": True,
                         "hash": "66DvflmqR/+HhhR7cXlCBsz2ow4="}]}}}}]}})
    assert drm.APP_ID == "oimompecagnajdejgnnjijobebaeigek"
    assert drm.parse_answer(answer.encode()) == {
        "version": "4.10.3112.0", "name": name, "sha256": sha, "size": 21970001,
        "urls": ["https://" + b + name for b in (base,) + others]}


def test_widevine_only_https_on_googles_hosts(monkeypatch):
    for url in ("https://update.googleapis.com/service/update2/json", "https://dl.google.com/x",
                "https://edgedl.me.gvt1.com/edgedl/x", "https://redirector.gvt1.com/x",
                "https://r3---sn-abc.gvt1.com/x", "https://www.google.com/dl/x"):
        assert drm.google_https(url), url
    for url in ("http://dl.google.com/x", "https://google.com.evil.example/x", "https://evilgoogle.com/x",
                "https://gvt1.com.example/x", "ftp://dl.google.com/x", "https://dl.google.com:bad/x", "https://dl.google.com@evil.example/x",
                "https://user@dl.google.com/x", "", None):
        assert not drm.google_https(url), url
    with pytest.raises(drm.DrmError):
        drm._get("https://evil.example/x", 10)
    # a redirect is refused before it is followed unless it stays on Google's https
    from ike import doh
    seen = {}

    def fake_urlopen(req, timeout, handlers=()):
        seen["handlers"] = handlers
        raise OSError("offline")
    monkeypatch.setattr(doh, "urlopen", fake_urlopen)
    import urllib.request
    req = urllib.request.Request("https://redirector.gvt1.com/x")
    with pytest.raises(OSError):
        drm._open(req)
    [handler] = seen["handlers"]
    for bad in ("http://redirector.gvt1.com/x", "https://evil.example/x"):
        with pytest.raises(drm.DrmError):
            handler.redirect_request(req, None, 302, "Found", {}, bad)
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://r1---sn-x.gvt1.com/x").full_url \
        == "https://r1---sn-x.gvt1.com/x"


# ---- in the browser -----------------------------------------------------------

def test_look_and_settings(run_ike, tmp_path):
    """The window and Settings. With IKE_TEST_SHOTS=<folder> they are saved
    as pictures, to check them by eye."""
    shots = os.environ.get("IKE_TEST_SHOTS", "")
    out = run_ike("""
        import os
        SHOTS = %r

        def save(widget, name):
            if SHOTS:
                widget.grab().save(os.path.join(SHOTS, "look-%%s.png" %% name))

        def steps(ike, qapp, out):
            win = ike.windows[0]
            win.resize(1000, 700)
            yield 800
            save(win, "window")
            out["title"] = win.windowTitle()
            dlg = ike.show_settings(win)
            yield 400
            for i, name in enumerate(dlg.PAGES):
                dlg.nav.setCurrentRow(i)
                yield 150
                save(dlg, "settings-" + name)
            out["desktop_switches"] = sorted(dlg.di)
            dlg.close()
            yield 200
    """ % shots, settings={"language": "it"})
    assert out["title"]
    assert out["desktop_switches"] == ["di_downloads", "di_kdeconnect", "di_krunner", "di_media"]
