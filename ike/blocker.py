"""Content blocker: filter lists download, matching engine, daily updates.

Uses Brave's adblock engine (python-adblock) when available and falls back
to a pure Python domain matcher otherwise.
"""

import base64
import hashlib
import os
import re
import time
import urllib.request
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import background
from .config import CACHE_DIR, DATA_DIR
from .scriptlets import preprocess

try:
    import adblock
except Exception:  # pragma: no cover - optional dependency
    adblock = None

LISTS_DIR = DATA_DIR / "lists"
UPDATE_INTERVAL = 24 * 3600
# lists that carry urgent fixes (video-ad rules change within hours)
FAST_INTERVAL = 4 * 3600
FAST_MARKERS = ("quick-fixes",)
MAX_LIST_BYTES = 32 * 1024 * 1024
RETRY_FAILED_AFTER = 3600
_DOMAIN_RULE = re.compile(r"^\|\|([a-z0-9.-]+)\^(\$third-party|\$3p)?$")
_GHIDE = re.compile(r"^@@.*\$.*\b(?:ghide|generichide)\b.*$", re.M)


def sanitize(text):
    """Work around an engine bug: a generichide exception whose domain= option
    mixes plain and negated domains is applied to every site, which would
    switch off generic element hiding everywhere. Drop the negated entries."""
    def fix(m):
        line = m.group(0)
        if "domain=" not in line or "~" not in line:
            return line
        head, _, tail = line.partition("domain=")
        doms, sep, rest = tail.partition(",")
        kept = [d for d in doms.split("|") if d and not d.startswith("~")]
        if not kept:
            return "! " + line
        return head + "domain=" + "|".join(kept) + sep + rest
    return _GHIDE.sub(fix, text)


def list_path(url):
    return LISTS_DIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")


def _trusted_scriptlet_source(url):
    """Only trust scriptlet lists served from the two official source origins."""
    try:
        parts = urlsplit(url)
        if parts.scheme != "https":
            return False
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
        return (host == "ublockorigin.github.io" or
                (host == "raw.githubusercontent.com" and
                 path.startswith("/uBlockOrigin/")))
    except (TypeError, ValueError):
        return False


def _install_redirect_resources(engine):
    """Register the small, inert resources referenced by common ABP redirect rules."""
    if not hasattr(engine, "add_resource"):
        return
    gif_1x1 = bytes.fromhex(
        "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")
    png_1x1 = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")
    resources = (
        ("noopjs", "application/javascript", b"/* I.K.E. noop */", ["noopjs", "empty.js"]),
        ("noopcss", "text/css", b"/* I.K.E. noop */", ["noopcss", "empty.css"]),
        ("nooptext", "text/plain", b"", ["nooptext"]),
        ("noopframe", "text/html", b"<!doctype html><html><head><meta charset=utf-8></head><body></body></html>", ["noopframe"]),
        ("noopmp3", "audio/mpeg", b"", ["noopmp3"]),
        ("1x1.gif", "image/gif", gif_1x1, ["1x1.gif", "1x1"]),
        ("1x1.png", "image/png", png_1x1, ["1x1.png"]),
    )
    for name, mime, content, aliases in resources:
        try:
            engine.add_resource(name, mime, base64.b64encode(content).decode("ascii"), aliases)
        except Exception:
            # A resource already supplied by a serialized engine is harmless.
            continue


class _Downloader(QThread):
    done = pyqtSignal(int, int)  # ok, failed

    def __init__(self, urls, parent=None):
        super().__init__(parent)
        self.urls = urls

    @staticmethod
    def _with_includes(url, data):
        """Append the sub-lists a list names with "!#include file.txt".

        uBlock's main list keeps most of its rules in such files. Only plain
        file names next to the list itself are followed, one level deep; a
        sub-list that cannot be fetched is skipped.
        """
        names = []
        for raw in data.split(b"\n"):
            if raw.startswith(b"!#include "):
                name = raw[10:].strip().decode("ascii", "ignore")
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.txt", name) and name not in names:
                    names.append(name)
        if not names:
            return data
        base = url.rsplit("/", 1)[0] + "/"
        host = (urlsplit(url).hostname or "").lower()
        parts = [data]
        for name in names[:24]:
            try:
                req = urllib.request.Request(base + name,
                                             headers={"User-Agent": "I.K.E. filter updater"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    final = urlsplit(r.geturl())
                    if final.scheme != "https" or (final.hostname or "").lower() != host:
                        continue
                    sub = r.read(MAX_LIST_BYTES + 1)
                if 20 <= len(sub) <= MAX_LIST_BYTES and b"\x00" not in sub[:4096]:
                    parts.append(b"! --- included: " + name.encode() + b"\n" + sub)
            except Exception:
                continue
            if sum(len(x) for x in parts) > MAX_LIST_BYTES:
                parts.pop()
                break
        return b"\n".join(parts)

    def run(self):
        ok = failed = 0
        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        for url in self.urls:
            try:
                parts = urlsplit(url)
                if parts.scheme != "https" or not parts.hostname:
                    raise ValueError("filter lists must use HTTPS")
                req = urllib.request.Request(url, headers={"User-Agent": "I.K.E. filter updater"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    final = urlsplit(r.geturl())
                    if final.scheme != "https":
                        raise ValueError("refusing insecure redirect")
                    # A trusted scriptlet list must not silently change origin
                    # during download; otherwise its original URL would confer
                    # trust on content served by an unrelated host.
                    if (_trusted_scriptlet_source(url) and
                            (final.hostname or "").lower() != (parts.hostname or "").lower()):
                        raise ValueError("trusted scriptlet source redirected to another host")
                    length = r.headers.get("Content-Length")
                    if length and int(length) > MAX_LIST_BYTES:
                        raise ValueError("filter list exceeds size limit")
                    data = r.read(MAX_LIST_BYTES + 1)
                if len(data) > MAX_LIST_BYTES:
                    raise ValueError("filter list exceeds size limit")
                if len(data) < 20 or b"\x00" in data[:4096]:
                    raise ValueError("empty or binary filter list")
                data = self._with_includes(url, data)
                tmp = list_path(url).with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(list_path(url))
                ok += 1
            except Exception:
                failed += 1
        self.done.emit(ok, failed)


class _FallbackEngine:
    """Domain-only matcher used when python-adblock is not installed."""

    def __init__(self, texts):
        self.domains = set()
        for text in texts:
            for line in text.splitlines():
                m = _DOMAIN_RULE.match(line.strip())
                if m:
                    self.domains.add(m.group(1))

    def blocked(self, url, source, _rtype):
        host = urlsplit(url).hostname or ""
        src = urlsplit(source).hostname or ""
        if host == src or host.endswith("." + src):
            return False
        while host:
            if host in self.domains:
                return True
            if "." not in host:
                return False
            host = host.split(".", 1)[1]
        return False


class Blocker(QObject):
    """Owns the matching engine. All matching happens on the UI thread."""

    updated = pyqtSignal(int, int)   # ok, failed downloads
    rebuilt = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = None
        self.fallback = None
        self._thread = None
        self.native = adblock is not None
        self._method_support = None
        # requests and pages the engine failed on this session (they were let
        # through: blocking everything would break browsing); Help -> About
        self.errors = 0
        from .scriptlets import Scriptlets
        self.scriptlets = Scriptlets()

    # --- lists -------------------------------------------------------
    def _active_lists(self):
        cfg = self.config
        out = []
        for entry in cfg["filter_lists"]:
            if not entry.get("enabled", True):
                continue
            group = entry.get("group", "ads")
            if group == "consent" and not cfg["comp_consent"]:
                continue
            if group != "consent" and not cfg["comp_adblock"]:
                continue
            out.append(entry)
        return out

    def _texts(self):
        texts = []
        for entry in self._active_lists():
            try:
                texts.append(sanitize(preprocess(
                    list_path(entry["url"]).read_text("utf-8", "replace"))))
            except OSError:
                pass
        if self.config["comp_adblock"] and self.config["custom_filters"].strip():
            texts.append(self.config["custom_filters"])
        return texts

    def _signature(self):
        h = hashlib.sha1()
        for entry in self._active_lists():
            p = list_path(entry["url"])
            try:
                st = p.stat()
                h.update(("%s:%d:%d;" % (p.name, st.st_size, st.st_mtime_ns)).encode())
            except OSError:
                pass
        h.update(self.config["custom_filters"].encode())
        h.update(str(self.config["comp_adblock"]).encode())
        h.update(b"pp1")                 # list preprocessing version
        return h.hexdigest()[:20]

    def _load_scriptlets(self):
        """Index the "+js(...)" rules of the lists (cached next to the engine)."""
        self.scriptlets.clear()
        if not self.config["comp_adblock"]:
            return
        from .scriptlets import LIBRARY
        cache = CACHE_DIR / ("scriptlets-v4-%s-%s.json" % (self._signature(), LIBRARY.lib_version()))
        try:
            if cache.exists():
                self.scriptlets.load(cache.read_text("utf-8"))
                return
        except Exception:
            self.scriptlets.clear()
        for entry in self._active_lists():
            if entry.get("group") == "consent":
                continue
            try:
                text = list_path(entry["url"]).read_text("utf-8", "replace")
            except OSError:
                continue
            self.scriptlets.add_list(text, _trusted_scriptlet_source(entry["url"]))
        if self.config["custom_filters"].strip():
            self.scriptlets.add_list(self.config["custom_filters"], True)
        try:
            for old in CACHE_DIR.glob("scriptlets-*.json"):
                old.unlink()
            cache.write_text(self.scriptlets.dump(), "utf-8")
        except OSError:
            pass

    def load(self):
        """Build the engine from cached lists (uses a serialized cache)."""
        self.engine = self.fallback = None
        texts = None
        self._load_scriptlets()
        if adblock is not None:
            cache = CACHE_DIR / ("engine-%s-%s.dat" % (
                getattr(adblock, "ENGINE_VERSION", "0"), self._signature()))
            try:
                if cache.exists():
                    eng = adblock.Engine(adblock.FilterSet())
                    eng.deserialize_from_file(str(cache))
                    self.engine = eng
            except Exception:
                self.engine = None
            if self.engine is None:
                texts = self._texts()
                if texts:
                    fs = adblock.FilterSet()
                    for t in texts:
                        try:
                            fs.add_filter_list(t)
                        except Exception as exc:        # one unreadable list: the others still count
                            self._engine_error("a filter list", "", exc)
                    try:
                        self.engine = adblock.Engine(fs)
                    except Exception as exc:
                        # no engine this time: pages load unfiltered rather than not at all
                        self._engine_error("building the engine", "", exc)
                        self.engine = None
                if self.engine is not None:
                    try:
                        for old in CACHE_DIR.glob("engine-*.dat"):
                            old.unlink()
                        self.engine.serialize_to_file(str(cache))
                    except Exception:
                        pass
        else:
            texts = self._texts()
            if texts:
                self.fallback = _FallbackEngine(texts)
        if self.engine is not None:
            _install_redirect_resources(self.engine)
        self.rebuilt.emit()

    def have_lists(self):
        return any(list_path(e["url"]).exists() for e in self.config["filter_lists"])

    def needs_update(self):
        if not self.have_lists():
            return True
        if not self.config["auto_update"]:
            return False
        return time.time() - self.config["last_lists_update"] > UPDATE_INTERVAL

    def _fast_urls(self):
        return [e["url"] for e in self.config["filter_lists"]
                if e.get("enabled", True) and any(m in e["url"] for m in FAST_MARKERS)]

    def needs_fast_update(self):
        """The urgent-fix lists are refreshed every few hours, not once a day."""
        if not self.config["auto_update"] or not self.have_lists() or not self._fast_urls():
            return False
        last = max(self.config["last_fast_update"], self.config["last_lists_update"])
        return time.time() - last > FAST_INTERVAL

    def update(self, fast=False):
        """Download the enabled lists in the background, then rebuild.

        fast=True downloads only the urgent-fix lists.
        """
        if self._thread is not None:
            return
        urls = self._fast_urls() if fast else \
            [e["url"] for e in self.config["filter_lists"] if e.get("enabled", True)]
        if not urls:
            return
        self._fast = fast
        self._thread = _Downloader(urls, self)
        self._thread.done.connect(self._downloaded)
        background.start(self._thread)

    def _downloaded(self, ok, failed):
        self._thread = None
        if ok:
            # A partial refresh must not suppress retries for a full day.
            now = int(time.time())
            if getattr(self, "_fast", False):
                self.config["last_fast_update"] = now
            else:
                self.config["last_lists_update"] = now if not failed else now - UPDATE_INTERVAL + RETRY_FAILED_AFTER
                self.config["last_fast_update"] = now
            self.config.save()
            self.load()
        self.updated.emit(ok, failed)

    # --- matching ----------------------------------------------------
    def request_action(self, url, source, rtype, method="GET"):
        """Return allow/block/redirect and an optional validated redirect URL.

        Newer adblock-rust bindings expose Request/check_network_request and
        understand method-specific rules. Keep compatibility with the bundled
        0.6 Python binding, whose API predates HTTP-method matching.
        """
        method = (method or "GET").upper()
        if self.engine is not None:
            try:
                result = None
                request_cls = getattr(adblock, "Request", None) if adblock else None
                check_request = getattr(self.engine, "check_network_request", None)
                if request_cls is not None and callable(check_request):
                    request = request_cls(url, source, rtype, method)
                    result = check_request(request)
                else:
                    check_urls = getattr(self.engine, "check_network_urls", None)
                    if not callable(check_urls):
                        return "allow", None
                    # Some intermediate bindings added method as a fourth
                    # argument; the packaged 0.6.0 binding accepts three.
                    if self._method_support is not False:
                        try:
                            result = check_urls(url, source, rtype, method)
                            self._method_support = True
                        except TypeError:
                            self._method_support = False
                    if result is None:
                        result = check_urls(url, source, rtype)
                important = bool(getattr(result, "important", False))
                if getattr(result, "exception", None) and not important:
                    return "allow", None
                matched = getattr(result, "matched", None)
                if matched is None:
                    matched = bool(getattr(result, "should_block", False))
                redirect = getattr(result, "redirect", None)
                if redirect and matched:
                    # Redirect resources are generated by the bundled engine;
                    # the interceptor independently restricts them to data:.
                    return "redirect", str(redirect)
                if matched:
                    return "block", None
                rewritten = getattr(result, "rewritten_url", None)
                if rewritten and rewritten != url:
                    return "rewrite", str(rewritten)      # $removeparam rules
            except Exception as exc:
                self._engine_error("request", url, exc)
                return "allow", None
        elif self.fallback is not None and self.fallback.blocked(url, source, rtype):
            return "block", None
        return "allow", None

    def _engine_error(self, what, url, exc):
        """The engine failed: the request (or page) goes on unfiltered, as before;
        the error is counted and, with IKE_DEBUG, logged."""
        self.errors += 1
        if os.environ.get("IKE_DEBUG"):
            print("[adblock] %s failed for %s: %s: %s" % (what, url[:200], exc.__class__.__name__, exc))

    def should_block(self, url, source, rtype, method="GET"):
        """Compatibility helper for callers that only need a boolean."""
        action, _target = self.request_action(url, source, rtype, method)
        return action in ("block", "redirect")

    def cosmetic_css(self, url):
        """CSS that hides ad/banner elements on this page ('' if none)."""
        if self.engine is None:
            return "", set(), False
        try:
            res = self.engine.url_cosmetic_resources(url)
        except Exception as exc:
            self._engine_error("cosmetic filters", url, exc)
            return "", set(), False
        sels = list(res.hide_selectors)
        css_parts = [_hide_css(sels)]
        css_parts.append(_style_css(getattr(res, "style_selectors", {}) or {}))
        css = "\n".join(part for part in css_parts if part)
        return css, set(res.exceptions), bool(res.generichide)

    def generic_css(self, classes, ids, exceptions):
        if self.engine is None:
            return ""
        try:
            sels = self.engine.hidden_class_id_selectors(classes, ids, exceptions)
        except Exception as exc:
            self._engine_error("generic cosmetic filters", "", exc)
            return ""
        return _hide_css(list(sels))


def _hide_css(selectors):
    # Selectors originate in remote filter lists. Never let an invalid selector
    # terminate the generated rule and append arbitrary CSS declarations.
    safe = [s for s in selectors if isinstance(s, str) and 0 < len(s) <= 4000
            and "{" not in s and "}" not in s and ";" not in s]
    out = []
    for i in range(0, len(safe), 200):
        chunk = safe[i:i + 200]
        if chunk:
            out.append(",".join(chunk) + "{display:none!important}")
    return "\n".join(out)


def _style_css(style_selectors):
    """Render safe cosmetic style declarations returned by adblock-rust."""
    allowed = {
        "background-color", "border", "color", "display", "font-size", "height",
        "max-height", "max-width", "min-height", "min-width", "opacity", "overflow",
        "pointer-events", "position", "visibility", "width", "z-index",
    }
    safe_value = re.compile(r"^[A-Za-z0-9#%.,()+\-\s!]+$")
    out = []
    for selector, declarations in list(style_selectors.items())[:500]:
        if (not isinstance(selector, str) or not selector or len(selector) > 2000
                or any(char in selector for char in "{};")):
            continue
        if not isinstance(declarations, (list, tuple)):
            continue
        rules = []
        for declaration in declarations[:20]:
            if not isinstance(declaration, str) or len(declaration) > 300:
                continue
            match = re.fullmatch(r"\s*([a-z-]+)\s*:\s*([^;{}]+?)\s*;?\s*", declaration, re.I)
            if not match:
                continue
            prop, value = match.group(1).lower(), match.group(2).strip()
            if prop in allowed and safe_value.fullmatch(value) and not re.search(
                    r"url|expression|@import|javascript", value, re.I):
                rules.append(f"{prop}:{value}")
        if rules:
            out.append(selector + "{" + ";".join(rules) + "}")
    return "\n".join(out)
