"""Diagnosis of incompatibilities: when a protection of I.K.E. most likely
breaks a site (1.1.32, the owner's brief "Ripara sito").

Philosophy: protect as much as possible, interfere as little as possible, and
act only on a protection that really breaks a site. Nothing here turns a
protection off: a finding only makes the shield's octagon show the
interference animation and the shield panel propose "Repair this site",
with the probable cause and the smallest change when one is known. The
user decides; the change is for that site only, kept with the site's repairs
and undone from the shield.

A finding needs, together:

1. a protection that really acted on this page, as the request check saw it
   (trusted: shields.Interceptor notes it in the ledger below, per profile
   and site, from the page's main request on); a page cannot make the
   request check act on something it did not ask for, and it cannot report
   anything into the ledger itself;
2. an error coherent with it (a worker refused by the level, the protected
   copy of a worker refused by the site's own policy, a first-party script
   or media blocked by the lists...);
3. a sign that something important does not work: the refusal of a worker
   the page itself asked for and waits on, or a page that stays empty, or a
   player in error, looked at once by a probe in I.K.E.'s own world a few
   seconds after the load (the page can draw what it likes, but it cannot
   run or answer the probe);
4. a repair narrower than "everything off" where one exists.

What the page itself reports (through fingerprint.js's channel, a console
message with a key of the profile's own that the page cannot read) is weak
evidence: it can add to a trusted intervention, never replace it. A page
that fakes a breakage can at most make I.K.E. propose, to the user, the one
narrow change for that same site that its own requests made relevant.

Ordinary blocks (ads, trackers, third-party cookies, a single non-essential
worker, the site's own script errors, network errors) never raise anything.
The detectors are small classes: a new incompatibility is one more class in
DETECTORS, the rest stays as it is.

Cost: nothing at all on a page where no protection acted; otherwise one
evaluation of a few dictionary lookups per new kind of intervention, and at
most one probe of the page (a single DOM pass) a few seconds after its load,
a few per load at most. No timer runs while nothing is pending.
"""

import json
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

PROBE_DELAY_MS = 4000          # after the load: the page has drawn what it draws by itself
EVIDENCE_DELAY_MS = 1500       # after new evidence: the page reacts to it first
MAX_PROBES = 4                 # per page load
LEDGER_SITES = 300             # sites kept per profile scope (the oldest go first)

# How serious a finding is (the owner's colours, 1.1.32): ATTENTION, yellow,
# when a protection most likely stops a feature but the site stays usable;
# SERIOUS, orange, when it most likely stops something essential (an empty
# page, a player that cannot play, an app waiting on a refused worker). The
# red of a real danger is not a finding: it comes only from I.K.E.'s safety
# warnings (window.danger_of), never from this module.
ATTENTION = "attention"
SERIOUS = "serious"
RANK = {ATTENTION: 1, SERIOUS: 2}


class Evidence:
    """What the protections did on one site since its last page started."""

    __slots__ = ("trusted", "weak", "since")

    def __init__(self):
        self.trusted = {}       # kind -> count, from the request check only
        self.weak = {}          # kind -> count, reported by the page's world
        self.since = time.monotonic()

    def n(self, prefix):
        return sum(c for k, c in self.trusted.items() if k.startswith(prefix))

    def w(self, kind):
        return self.weak.get(kind, 0)


class Ledger:
    """Evidence per (scope, site): scope is the profile's request check, so a
    private window's sites never mix with the normal ones."""

    def __init__(self):
        self._ev = {}

    def _get(self, scope, host, create=True):
        key = (scope, (host or "").lower())
        ev = self._ev.get(key)
        if ev is None and create:
            if len(self._ev) >= LEDGER_SITES:
                self._ev.pop(next(iter(self._ev)))
            ev = self._ev[key] = Evidence()
        return ev

    def note(self, scope, host, kind):
        """A protection acted (the request check). True for the first of its kind."""
        ev = self._get(scope, host)
        first = kind not in ev.trusted
        ev.trusted[kind] = ev.trusted.get(kind, 0) + 1
        return first

    def weak(self, scope, host, kind):
        ev = self._get(scope, host)
        first = kind not in ev.weak
        if ev.weak.get(kind, 0) < 50:
            ev.weak[kind] = ev.weak.get(kind, 0) + 1
        return first

    def reset(self, scope, host):
        self._ev.pop((scope, (host or "").lower()), None)

    def get(self, scope, host):
        return self._get(scope, host, create=False)


class Finding:
    """A probable incompatibility of one site in one tab."""

    __slots__ = ("detector", "host", "keys", "cause", "severity")

    def __init__(self, detector, host, keys, cause, severity=SERIOUS):
        self.detector = detector      # the detector's id
        self.host = host
        self.keys = tuple(keys)       # repair keys to turn off ("workers"...); () = a full diagnosis
        self.cause = cause            # the probable cause, a source text for T()
        self.severity = severity      # ATTENTION or SERIOUS (the octagon's yellow or orange)

    def __repr__(self):
        return "Finding(%s, %s, %s, %s)" % (self.detector, self.host, self.keys, self.severity)


class Context:
    def __init__(self, app, host):
        from . import repair
        self.app = app
        self.cfg = app.config
        self.host = host
        self.active = repair.active(app.config, host)
        self.video_site = host in app.shields.video_hosts() if hasattr(app.shields, "video_hosts") else False


# ---- the detectors ------------------------------------------------------------
class Detector:
    """One kind of incompatibility. relevant() is cheap and decides whether a
    probe of the page is worth it; judge() gives the finding, or None."""

    id = ""
    needs_probe = True

    def relevant(self, ev, ctx):
        return False

    def judge(self, ev, probe, ctx):
        return None


class SiteWorkers(Detector):
    """Maximum refused the site's own workers and the page waits on them
    (WhatsApp, Telegram; Kontrol lets them run since 1.1.32)."""

    id = "workers"
    CAUSE = "Probable cause: this level blocks the site's own background workers."

    def relevant(self, ev, ctx):
        return "workers" in ctx.active and ev.n("worker:") > 0

    def judge(self, ev, probe, ctx):
        # a worker the page itself asked for and waits on could not start
        page_worker = ev.n("worker:shared") > 0 or ev.n("worker:dedicated") > 0
        # its protected copy was refused by the site's own policy (weak), with
        # a refused service worker of the same site (trusted): WhatsApp
        copy_refused = ev.w("protected_worker_refused") > 0 and ev.n("worker:service") > 0
        empty = bool(probe and (probe.get("blank") or probe.get("sparse")))
        if empty and (page_worker or copy_refused or probe.get("blank")):
            # the app does not start: something essential is missing
            return Finding(self.id, ctx.host, ("workers",), self.CAUSE, SERIOUS)
        if page_worker or copy_refused:
            # the page shows its content: some features may be missing
            return Finding(self.id, ctx.host, ("workers",), self.CAUSE, ATTENTION)
        return None                    # a service worker alone, the page fine: nothing to say


class EmptyPage(Detector):
    """The page stays empty after a protection blocked one of the site's own
    scripts (Kontrol and Maximum check them against the lists)."""

    id = "empty"
    CAUSE = "Probable cause: a protection blocked something the page needs."

    def relevant(self, ev, ctx):
        return not ctx.video_site and ev.n("own:script") > 0

    def judge(self, ev, probe, ctx):
        if probe and probe.get("blank"):
            return Finding(self.id, ctx.host, (), self.CAUSE, SERIOUS)
        return None


class BrokenPlayer(Detector):
    """A player of the page in error after the lists blocked one of the site's
    own media requests. Never on the video sites, whose ads come from the site
    itself and are blocked on purpose."""

    id = "player"
    CAUSE = "Probable cause: a protection blocked something the page needs."

    def relevant(self, ev, ctx):
        return not ctx.video_site and (ev.n("own:media") > 0 or ev.n("own:xhr") > 0)

    def judge(self, ev, probe, ctx):
        if probe and probe.get("mediaError"):
            return Finding(self.id, ctx.host, (), self.CAUSE, SERIOUS)
        return None


DETECTORS = [SiteWorkers(), EmptyPage(), BrokenPlayer()]


# The probe, in I.K.E.'s own world (the page cannot reach or answer it): is
# the page empty, is a player in error? One pass, a few hundred elements at
# most; nothing stays behind.
PROBE_JS = r"""(function () {
  var b = document.body, out = {blank: false, sparse: false, mediaError: false, text: 0, big: 0};
  if (!b) { out.blank = true; return JSON.stringify(out); }
  out.text = (b.innerText || '').replace(/\s+/g, '').length;
  var area = Math.max(1, innerWidth * innerHeight), els = b.querySelectorAll('img,video,canvas,svg,iframe,embed,object');
  for (var i = 0; i < els.length && i < 300; i++) {
    var r = els[i].getBoundingClientRect();
    if (r.width * r.height > area * 0.04 && r.bottom > 0 && r.top < innerHeight) out.big++;
  }
  var media = document.querySelectorAll('video,audio');
  for (var j = 0; j < media.length && j < 20; j++) {
    var m = media[j];
    if (m.error || (m.networkState === 3 && m.currentSrc)) out.mediaError = true;
  }
  out.blank = out.text < 30 && out.big === 0;
  out.sparse = out.text < 300 && out.big === 0;
  return JSON.stringify(out);
})()"""


class Diagnosis(QObject):
    """The findings of the open tabs. One per application (app.diagnosis)."""

    changed = pyqtSignal(object)          # the view whose finding changed

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.ledger = Ledger()
        self._views = []                  # the views attached (weakly: they go when destroyed)

    # --- evidence ------------------------------------------------------------
    def note(self, scope, host, kind):
        """From the request check (trusted)."""
        if self.ledger.note(scope, host, kind):
            self._soon(scope, host)

    def weak(self, scope, host, kind):
        """From the page's world (fingerprint.js's channel)."""
        if self.ledger.weak(scope, host, kind):
            self._soon(scope, host)

    def page_started(self, scope, host):
        """A new page of host starts in this scope (its main request)."""
        self.ledger.reset(scope, host)

    # --- the views -----------------------------------------------------------
    def attach(self, view):
        st = view._ike_diag = {"host": "", "finding": None, "probes": 0, "timer": None, "pending": False,
                                "ended": None, "quiet": set()}
        self._views.append(view)
        view.destroyed.connect(lambda *_a, v=view: self._gone(v))
        view.loadStarted.connect(lambda v=view: self._load_started(v))
        view.loadFinished.connect(lambda ok, v=view: self._load_finished(v, ok))
        view.urlChanged.connect(lambda u, v=view: self._url_changed(v, u))
        return st

    def _gone(self, view):
        try:
            self._views.remove(view)
        except ValueError:
            pass

    @staticmethod
    def scope_of(view):
        try:
            profile = view.page().profile()
        except RuntimeError:
            return None
        return id(getattr(profile, "_ike_interceptor", None) or view.window_ref.app.shields.interceptor)

    @staticmethod
    def host_of(view):
        try:
            url = view.url()
        except RuntimeError:
            return ""
        return url.host().lower() if url.scheme() in ("http", "https") else ""

    def finding(self, view):
        st = getattr(view, "_ike_diag", None)
        return st["finding"] if st else None

    def _url_changed(self, view, url):
        st = view._ike_diag
        host = url.host().lower() if url.scheme() in ("http", "https") else ""
        if host != st["host"]:
            st["host"] = host
            st["probes"] = 0
            st["quiet"] = set()
            if st["finding"] is not None:
                st["finding"] = None            # another site: its own story
                st["ended"] = "left"
                self.changed.emit(view)

    def _load_started(self, view):
        view._ike_diag["probes"] = 0

    def _load_finished(self, view, ok):
        # nothing to look at where no protection acted and nothing is shown
        if ok and (view._ike_diag["finding"] is not None
                   or self.ledger.get(self.scope_of(view), self.host_of(view)) is not None):
            self._schedule(view, PROBE_DELAY_MS)

    def _soon(self, scope, host):
        for v in list(self._views):
            try:
                if self.host_of(v) == host and self.scope_of(v) == scope:
                    self._schedule(v, EVIDENCE_DELAY_MS)
            except RuntimeError:
                continue

    def _schedule(self, view, ms):
        st = view._ike_diag
        if st["pending"]:
            return
        st["pending"] = True
        QTimer.singleShot(ms, lambda v=view: self._evaluate(v))

    # --- evaluation ------------------------------------------------------------
    def _evaluate(self, view):
        st = getattr(view, "_ike_diag", None)
        if st is None:
            return
        st["pending"] = False
        try:
            host, scope = self.host_of(view), self.scope_of(view)
        except RuntimeError:
            return
        if not host or scope is None:
            return
        ev = self.ledger.get(scope, host)
        ctx = Context(self.app, host)
        f = st["finding"]
        # a repair of the finding's own cause was kept for this site: look
        # whether the page works now (verified by the probe, not by the page)
        verify = f is not None and f.keys and not any(k in ctx.active for k in f.keys)
        dets = [d for d in DETECTORS if d.relevant(ev, ctx)] if ev is not None else []
        if not dets and not verify:
            return
        if any(d.needs_probe for d in dets) and st["probes"] < MAX_PROBES:
            st["probes"] += 1
            from PyQt6.QtWebEngineCore import QWebEngineScript
            try:
                view.page().runJavaScript(PROBE_JS, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                          lambda r, v=view, h=host, d=dets, c=verify: self._judged(v, h, d, r, c))
            except RuntimeError:
                pass
            return
        self._judged(view, host, dets, None, verify)

    def _judged(self, view, host, dets, raw, verify=False):
        st = getattr(view, "_ike_diag", None)
        if st is None or self.host_of(view) != host:
            return
        probe = None
        if isinstance(raw, str):
            try:
                probe = json.loads(raw)
            except ValueError:
                probe = None
        ev = self.ledger.get(self.scope_of(view), host)
        ctx = Context(self.app, host)
        if ev is not None:
            for d in dets:
                f = d.judge(ev, probe, ctx)
                if f is not None:
                    self._set(view, f)
                    return
        if verify and probe is not None and not probe.get("sparse") and not probe.get("mediaError"):
            # the repair is kept, the page has its content, nothing found again
            self.resolved(view)

    def _set(self, view, finding):
        st = view._ike_diag
        old = st["finding"]
        if (finding.host, finding.detector) in st["quiet"]:
            return                      # settled in this tab for this site (resolved below)
        # a finding stays until the site works again (a repair verified, or
        # the user's word), or the user leaves the site; one with a known
        # cause is not replaced by a vaguer one, and it only grows more serious
        if old is not None:
            if old.keys and not finding.keys:
                return
            if bool(old.keys) == bool(finding.keys) and RANK[finding.severity] <= RANK[old.severity]:
                return
        st["finding"] = finding
        st["ended"] = None
        self.changed.emit(view)

    # --- the user's answers ----------------------------------------------------------
    def resolved(self, view):
        """The user confirmed the site works (after a repair, or as it is)."""
        st = getattr(view, "_ike_diag", None)
        if st is not None and st["finding"] is not None:
            f = st["finding"]
            st["quiet"].add((f.host, f.detector))   # not raised again here for this site
            st["finding"] = None
            st["ended"] = "resolved"            # the octagon fades back to itself
            self.changed.emit(view)

    def ended(self, view):
        """Why the last finding ended: "resolved", "left" (another site) or None."""
        st = getattr(view, "_ike_diag", None)
        return st["ended"] if st else None
