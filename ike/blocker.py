"""Content blocker: filter lists download, matching engine, daily updates.

Uses the adblock-rust engine (python-adblock) when available and falls back
to a pure Python domain matcher otherwise.
"""

import base64
import hashlib
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import background, doh, osinfo
from .config import CACHE_DIR, DATA_DIR
from .scriptlets import preprocess

ENGINE_DIR = Path(__file__).resolve().parent / "_engine"


def _load_engine():
    """The AdBlock engine module. The one that came with this version of I.K.E.
    comes first: a self-update carries it in ike/_engine/ (1.1.12), so a new
    engine reaches every user without a new package. Without it, or when it
    cannot be loaded, the one installed with the package (vendor/adblock)."""
    import sys
    bundled = ENGINE_DIR / "adblock"
    if (bundled / "__init__.py").is_file():
        sys.path.insert(0, str(ENGINE_DIR))
        try:
            import adblock as mod
            if getattr(mod, "MODERN", False):
                return mod
        except Exception:
            pass
        finally:
            try:
                sys.path.remove(str(ENGINE_DIR))
            except ValueError:
                pass
        for name in [m for m in sys.modules if m == "adblock" or m.startswith("adblock.")]:
            del sys.modules[name]
    try:
        import adblock as mod
        return mod
    except Exception:  # pragma: no cover - optional dependency
        return None


adblock = _load_engine()

LISTS_DIR = DATA_DIR / "lists"
UPDATE_INTERVAL = 24 * 3600
# lists that carry urgent fixes (video-ad rules change within hours)
FAST_INTERVAL = 4 * 3600
FAST_MARKERS = ("quick-fixes",)
MAX_LIST_BYTES = 32 * 1024 * 1024
RETRY_FAILED_AFTER = 3600
# I.K.E.'s own rules, always with the lists when ad blocking is on (1.1.13):
# telemetry of YouTube and Google that the lists above still let through on
# a video page. Only reports about the user are blocked, never what a page
# needs: not the watch history and "continue watching" (api/stats/watchtime,
# api/stats/playback), not the video servers (googlevideo.com, generate_204
# there opens the connection of the video), not the page's own API calls.
# 1.1.18: no rule of its own where the lists decided otherwise on purpose.
# YouTube's player checks some of its own requests and refuses playback
# ("ad blockers violate YouTube's Terms of Service") when they fail: the
# lists' maintainers un-blocked api/stats/atr for that reason (uBlock
# quick-fixes $badfilter, EasyPrivacy commented out, uAssets #27415) and keep
# api/stats/qoe blocked only in one narrow form. I.K.E. had blocked atr, every
# qoe request, delayplay, get_midroll_ and error_204 by itself: those are now
# left to the lists, as in uBlock Origin. Other companies' ad and tracking
# hosts and the reports below stay blocked.
BUILTIN_RULES = """\
! I.K.E. - YouTube and Google telemetry
||youtube.com/api/stats/ads^
||youtube.com/ptracking^
||youtube.com/pagead/
||youtube.com/csi_204^
||youtube.com/youtubei/v1/log_event^
||play.google.com/log^$third-party
||googleads.g.doubleclick.net^
||static.doubleclick.net/instream/
"""
_DOMAIN_RULE = re.compile(r"^\|\|([a-z0-9.-]+)\^(\$third-party|\$3p)?$")
# "@@" first: the search jumps from one "@@" to the next instead of trying
# every position of the lists' 5 MB (1.1.22: 31-33 ms -> 7-10 ms); a match that
# does not start a line is given back unchanged, so the lines changed are those
# of the former "^@@.*\$.*\b(?:ghide|generichide)\b.*$" (re.M).
_GHIDE = re.compile(r"@@[^\n]*\$[^\n]*\b(?:ghide|generichide)\b[^\n]*")


def sanitize(text):
    """Work around an engine bug: a generichide exception whose domain= option
    mixes plain and negated domains is applied to every site, which would
    switch off generic element hiding everywhere. Drop the negated entries."""
    # Accept any non-empty csp= value (uBlock Origin allows script-src-attr,
    # connect-src, font-src, etc., not only the common ones).
    _CSP_RE = re.compile(r"csp=([^,\s]+)")
    def _fix_csp(m):
        return m.group(0)  # keep as-is; the engine handles it
    # No change needed here; the fix is in the option parser below.
    def fix(m):
        line = m.group(0)
        if m.start() and text[m.start() - 1] != "\n":
            return line                   # not the start of a line
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
                import urllib.request  # only when lists are fetched (start-up: review L3)
                req = urllib.request.Request(base + name,
                                             headers={"User-Agent": osinfo.browser_user_agent()})
                with doh.urlopen(req, timeout=40) as r:
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
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": osinfo.browser_user_agent()})
                with doh.urlopen(req, timeout=40) as r:
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


class _BuildThread:
    """The one thread every engine build runs in, kept for the whole session
    so the memory a build needs is reused (see Blocker._work). It does what
    concurrent.futures' ThreadPoolExecutor(max_workers=1) did until 1.1.21
    without importing that module, which brings in logging, traceback and,
    on Python 3.14, dataclasses and inspect: about 15 ms of every start
    before the window (1.1.22). submit() gives a job whose result() waits for
    it and raises what the build raised."""

    def __init__(self):
        import queue
        import threading
        self._jobs = queue.SimpleQueue()
        # a daemon, as Python waits for no thread at exit; close() waits for
        # a build that is running then, as the pool did
        self._thread = threading.Thread(target=self._serve, name="ike-adblock", daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            job.run()

    def submit(self, fn, *args):
        job = _Job(fn, args)
        self._jobs.put(job)
        return job

    def close(self, timeout=None):
        """No more builds: the one running (and any waiting) ends first."""
        self._jobs.put(None)
        self._thread.join(timeout)


class _Job:
    def __init__(self, fn, args):
        import threading
        self._fn, self._args = fn, args
        self._done = threading.Event()
        self._value = self._error = None

    def run(self):
        try:
            self._value = self._fn(*self._args)
        except BaseException as exc:      # handed to whoever waits for it
            self._error = exc
        self._fn = self._args = None
        self._done.set()

    def result(self):
        self._done.wait()
        if self._error is not None:
            raise self._error
        return self._value


def _give_back_memory():
    """Hand the memory freed by the engine just replaced back to the system
    (glibc keeps it otherwise; elsewhere nothing happens)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


class Blocker(QObject):
    """Owns the matching engine. All matching happens on the UI thread."""

    updated = pyqtSignal(int, int)   # ok, failed downloads
    rebuilt = pyqtSignal()
    _built_sig = pyqtSignal(object, str)    # from the build thread to this one

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = None
        self.fallback = None
        self._thread = None
        self.native = adblock is not None
        self._method_support = None
        self._way = None                 # (engine, how it matches a request): request_action
        # requests and pages the engine failed on this session (they were let
        # through: blocking everything would break browsing); Help -> About
        self.errors = 0
        from .scriptlets import Scriptlets
        self.scriptlets = Scriptlets()
        self._builder = None             # a background build (see load)
        self._again = False
        self._pool = None                # one thread, kept for every build: its memory is reused
        self._built_sig.connect(self._built)

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

    def _snapshot(self):
        """What a build reads from the settings, copied in the interface's
        thread: the build itself may run in another one."""
        cfg = self.config
        return {"lists": [dict(e) for e in self._active_lists()],
                "comp_adblock": bool(cfg["comp_adblock"]),
                "custom": cfg["custom_filters"] or ""}

    @staticmethod
    def _list_text(url, read):
        """A list's text, its "!#if" branches already chosen; read once per
        build for the engine and the scriptlets alike (`read` keeps it)."""
        if url not in read:
            read[url] = preprocess(list_path(url).read_text("utf-8", "replace"))
        return read[url]

    def _texts(self, snap=None, read=None):
        snap = snap or self._snapshot()
        read = {} if read is None else read
        texts = []
        for entry in snap["lists"]:
            try:
                texts.append(sanitize(self._list_text(entry["url"], read)))
            except OSError:
                pass
        if snap["comp_adblock"]:
            texts.append(BUILTIN_RULES)
            if snap["custom"].strip():
                texts.append(snap["custom"])
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
        h.update(hashlib.sha1(BUILTIN_RULES.encode()).digest())     # I.K.E.'s own rules
        return h.hexdigest()[:20]

    def _build_scriptlets(self, snap, signature, read=None):
        """Index the "+js(...)" rules of the lists (cached next to the engine)."""
        from .scriptlets import LIBRARY, Scriptlets
        out = Scriptlets()
        if not snap["comp_adblock"]:
            return out
        cache = CACHE_DIR / ("scriptlets-v4-%s-%s.json" % (signature, LIBRARY.lib_version()))
        try:
            if cache.exists():
                out.load(cache.read_text("utf-8"))
                return out
        except Exception:
            out.clear()
        read = {} if read is None else read
        for entry in snap["lists"]:
            if entry.get("group") == "consent":
                continue
            try:
                text = self._list_text(entry["url"], read)
            except OSError:
                continue
            # add_list chooses the "!#if" branches itself: on a text where
            # they are already chosen that changes nothing
            out.add_list(text, _trusted_scriptlet_source(entry["url"]))
        if snap["custom"].strip():
            out.add_list(snap["custom"], True)
        try:
            for old in CACHE_DIR.glob("scriptlets-*.json"):
                old.unlink()
            cache.write_text(out.dump(), "utf-8")
        except OSError:
            pass
        return out

    def _build(self, snap, signature):
        """(engine, fallback, scriptlets) for these settings: from the cache
        when it is there, otherwise from the lists. Reads only `snap` and the
        files, so it can run in a thread of its own."""
        engine = fallback = None
        read = {}                        # each list read and prepared once (1.1.22)
        scriptlets = self._build_scriptlets(snap, signature, read)
        if adblock is not None:
            cache = CACHE_DIR / ("engine-%s-%s.dat" % (getattr(adblock, "ENGINE_VERSION", "0"), signature))
            try:
                if cache.exists():
                    eng = adblock.Engine(adblock.FilterSet())
                    eng.deserialize_from_file(str(cache))
                    engine = eng
            except Exception:
                engine = None
            if engine is None:
                texts = self._texts(snap, read)
                if texts:
                    fs = adblock.FilterSet()
                    for t in texts:
                        try:
                            fs.add_filter_list(t)
                        except Exception as exc:        # one unreadable list: the others still count
                            self._engine_error("a filter list", "", exc)
                    try:
                        engine = adblock.Engine(fs)
                    except Exception as exc:
                        # no engine this time: pages load unfiltered rather than not at all
                        self._engine_error("building the engine", "", exc)
                        engine = None
                if engine is not None:
                    try:
                        for old in CACHE_DIR.glob("engine-*.dat"):
                            old.unlink()
                        engine.serialize_to_file(str(cache))
                    except Exception:
                        pass
            if engine is not None:
                _install_redirect_resources(engine)
        else:
            texts = self._texts(snap, read)
            if texts:
                fallback = _FallbackEngine(texts)
        return engine, fallback, scriptlets

    @property
    def building(self):
        """A new engine is being built in the background (the one in use keeps working)."""
        return self._builder is not None

    def prepare(self):
        """Start building the session's first engine in the build thread while
        the rest of I.K.E. is set up (performance review of 1.1.20, L2: 37 ms
        warm, about 245 ms cold, all before the window). load() at start
        waits for it, as before any page can make a request."""
        if self.engine is not None or self.fallback is not None or self._builder is not None:
            return
        try:
            signature, snap = self._signature(), self._snapshot()
            if self._pool is None:
                self._pool = _BuildThread()
            self._first = (self._pool.submit(self._build, snap, signature), signature)
        except Exception as exc:              # load() builds it as before
            self._engine_error("preparing the engine", "", exc)

    def load(self):
        """Build the engine from cached lists (uses a serialized cache).

        Called at start, after every list update and whenever the settings
        are applied; when neither the lists nor the filter settings changed
        since the last time, the engine in use is kept. The first engine of a
        session is made at once (11 ms from its cache); a later one, after a
        list update (186 ms from the lists, in the interface's thread until
        1.1.17), is built in a thread while the engine in use keeps blocking,
        then takes its place in one step."""
        first = getattr(self, "_first", None)
        if first is not None:
            # the first engine, started by prepare(): taken here, before anything loads
            self._first = None
            try:
                result = first[0].result()
            except Exception as exc:
                self._engine_error("building the engine", "", exc)
                result = None
            if result is not None:
                self._install(result, first[1])
        signature = self._signature()
        if getattr(self, "_loaded", None) == signature and (self.engine is not None or self.fallback is not None):
            return
        if self._builder is not None:
            self._again = True               # once this build is done, look again
            return
        snap = self._snapshot()
        if self.engine is None and self.fallback is None:
            self._install(self._build(snap, signature), signature)
            return
        if self._pool is None:
            self._pool = _BuildThread()
        self._builder = self._pool.submit(self._work, snap, signature)

    def _work(self, snap, signature):
        """In the build thread: always the same one, so the memory the engine
        needs while it is built is reused, not taken anew each time (a new
        thread per build left about 25 MB more after every list update)."""
        try:
            result = self._build(snap, signature)
        except Exception as exc:              # the engine in use stays
            self._engine_error("building the engine", "", exc)
            result = None
        self._built_sig.emit(result, signature)

    def close(self):
        """At exit: a build still running finishes (and writes its cache)
        before Python ends, as with the thread pool of 1.1.21."""
        if self._pool is not None:
            self._pool.close()

    def _built(self, result, signature):
        self._builder = None
        if result is not None:
            self._install(result, signature)
        if self._again:
            self._again = False
            self.load()

    def _install(self, result, signature):
        self.engine, self.fallback, self.scriptlets = result
        self._way = None
        self._loaded = signature
        self.rebuilt.emit()
        _give_back_memory()

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
        engine = self.engine
        if engine is not None:
            try:
                result = None
                # every request of every page comes here, in the interface's
                # thread: the engine's way of matching is looked up once per engine
                way = self._way
                if way is None or way[0] is not engine:
                    request_cls = getattr(adblock, "Request", None) if adblock else None
                    check_request = getattr(engine, "check_network_request", None)
                    if request_cls is None or not callable(check_request):
                        request_cls = check_request = None
                    check_urls = getattr(engine, "check_network_urls", None)
                    way = self._way = (engine, request_cls, check_request,
                                       check_urls if callable(check_urls) else None)
                _, request_cls, check_request, check_urls = way
                if check_request is not None:
                    result = check_request(request_cls(url, source, rtype, method))
                else:
                    if check_urls is None:
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
