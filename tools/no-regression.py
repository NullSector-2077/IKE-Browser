#!/usr/bin/env python3
"""Nothing gets worse: a behaviour snapshot of I.K.E., and main's against a candidate's.

The owner's goal (2026-11-22): every verified update and AI fix reaches main by
itself, and a person only signs. Tests can miss a subtle weakening, so this
tool measures what I.K.E. does for its users, the same way, on the same fixed
inputs, on main's commit and on the candidate's, in the same job, and fails on
anything that got worse:

- ad and tracker blocking: a fixed corpus of requests (tests/data/no-regression/
  corpus.json) run through I.K.E.'s own request check (shields.Interceptor,
  which asks ike/blocker.py and the AdBlock engine) at every protection level,
  with the default filter lists replaced by small local fixtures; pages whose ad
  elements must stay hidden, loaded in the real engine; the scriptlets of the
  video sites and of the pages; the element-hiding rules of fixed addresses.
  Worse: a request blocked on main and allowed here (unless the filter list
  data that decides it changed: _by_lists), an element hidden on main and
  shown here, a rule or scriptlet lost. YouTube's requests are in the corpus,
  read only;
- the fingerprinting surface: what a probe page's scripts read (navigator,
  screen, fonts, canvas, WebGL, audio, matchMedia, Client Hints, workers,
  frames, permissions...) at every level, in the real engine on a local page,
  with a noise key, and again with a second key (a second session); each
  noised value read twice, in another site's frame, and on two starts with the
  browser's own keys. What the protection disguises (FP_JUDGED: canvas, audio,
  WebGL, navigator, screen, fonts, Client Hints, time zone and language...) is
  judged by what protects, against the Off level's real value: worse when it
  is the real value again or nearer it, no longer changes with the session,
  has a smaller noise (NOISE, against the larger of main's and a person's
  floor), or shows more of a real list (_judge_fingerprint); a change that
  keeps the protection passes. Values with a protective direction
  (PROTECTIVE) must stay protected; anything else that changes cannot be
  judged, and is worse;
- the network: the hosts the browser contacts by itself, with a fresh profile,
  at start and while loading the probe page (a local proxy for the engine and
  Qt, a Python audit hook for I.K.E.'s own code; nothing leaves the computer).
  Worse: a host main does not contact, unless it is declared in
  tests/data/no-regression/endpoints.json and this change's own code names it
  (_by_registry);
- the security settings: the engine switches I.K.E. adds and what it drops from
  a hostile environment, its lists of unsafe switches and hands-off sites, the
  WebEngine settings, permissions and scripts of every level, the protective
  defaults, the request headers it sets. Worse: anything weaker, missing or
  changed in a way the rules cannot judge; no evidence ever accepts it.

What the rules cannot judge is worse ("when in doubt, worse"). The owner's
principle of 2026-11-24 (a change needed for I.K.E. to work and for its
protections to keep working is approved by the chain itself) lets one kind
pass by evidence: a fingerprinting value main left real, now disguised in both
sessions, when a test a person bound to it (NECESSITY_MAP) fails on main and
passes here, confirmed by running it CONFIRM_RUNS times on each side, and the
change touches the binding's files (_by_necessity). No evidence accepts a
weakening; only a person does, in main's tests/data/no-regression/
allowlist.json. The report says why each difference passed: the rule, the
evidence, or the person.

    no-regression.py snapshot --repo DIR --out FILE [--levels ...] [--sections ...]
    no-regression.py compare --base FILE --candidate FILE [--allowlist FILE] [--json OUT] [--markdown OUT]
        [--diff FILE] [--main-junit FILE ...] [--candidate-junit FILE ...] [--confirmed TEST ...]
        [--necessity FILE] [--endpoints FILE]
    no-regression.py check --base-repo DIR --candidate-repo DIR [--out-dir DIR] [--allowlist FILE]
        [--diff FILE] [--main-junit FILE ...] [--candidate-junit FILE ...] [--necessity FILE] [--endpoints FILE]

compare and check print "pass" or "fail" and exit 1 on "fail". Offline (local
fixtures, a local server and proxy) and headless (offscreen), like the
automatic tests; the probe's names and, in check, the noise keys are random for
each run (the same keys on both sides), so the code measured cannot know them
in advance. tests.yml runs main's copy of this tool (the step "Nothing gets
worse"), so a candidate never judges itself with its own copy.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURES = ROOT / "tests" / "data" / "no-regression"
ALLOWLIST = FIXTURES / "allowlist.json"
FORMAT = 1
LEVELS = ("off", "compatibility", "balanced", "strict", "maximum")
SECTIONS = ("requests", "cosmetic", "scriptlets", "fingerprint", "security", "network")
# the noise of the fingerprint protection, the same on both sides (a real profile has a random one)
FIXED_KEY = "6e6f2d72656772657373696f6e2d6b31"
# the key of a second session (a new start has a new key): what the protection randomises must change
FIXED_KEY_2 = "6e6f2d72656772657373696f6e2d6b32"
# another real machine for the "env." marks: what a fixed disguise shows must not follow it
OTHER_MACHINE = {"tz": "Pacific/Auckland", "lang": "de_DE.UTF-8", "screen": {"width": 1366, "height": 768},
                 "cpus": 3, "memory_gb": 2}
# the other machine's memory (N7): a small library loaded first (LD_PRELOAD) gives the engine another
# amount of memory; built with the computer's C compiler, or not at all (then a notice in the report)
MEMORY_SHIM = r"""#define _GNU_SOURCE
#include <dlfcn.h>
#include <unistd.h>
#include <sys/sysinfo.h>
long sysconf(int name) {
  static long (*real)(int) = 0;
  if (!real) real = (long (*)(int))dlsym(RTLD_NEXT, "sysconf");
  if (name == _SC_PHYS_PAGES) { long ps = real(_SC_PAGESIZE); return ps > 0 ? (__GB__L << 30) / ps : real(name); }
  return real(name);
}
int sysinfo(struct sysinfo *info) {
  static int (*real)(struct sysinfo *) = 0;
  if (!real) real = (int (*)(struct sysinfo *))dlsym(RTLD_NEXT, "sysinfo");
  int r = real(info);
  if (r == 0 && info->mem_unit) info->totalram = (__GB__UL << 30) / info->mem_unit;
  return r;
}
"""


def _memory_shim(workdir):
    """The other machine's memory library, built in workdir; None when no compiler builds it."""
    src, lib = Path(workdir) / "m.c", Path(workdir) / "m.so"
    try:
        src.write_text(MEMORY_SHIM.replace("__GB__", str(int(OTHER_MACHINE["memory_gb"]))), "utf-8")
        subprocess.run(["cc", "-shared", "-fPIC", "-O1", "-o", str(lib), str(src), "-ldl"], capture_output=True,
                       timeout=60, check=True)
        return str(lib)
    except (OSError, subprocess.SubprocessError):
        return None


def fixed_keys(n):
    """The fixed noise keys of n sessions (a snapshot by hand; check draws random ones)."""
    return [FIXED_KEY, FIXED_KEY_2] + [hashlib.sha256(("%s %d" % (FIXED_KEY, i)).encode()).hexdigest()[:32]
                                       for i in range(3, n + 1)]
# graphics switches given to the engine (software WebGL, as the tests); what I.K.E. adds is compared
INPUT_FLAGS = ["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
THIRD = "nr-third.example"           # a third-party host of the probe page (headers, Referer)
# a hostile environment: every switch and variable that takes a protection of the engine away
HOSTILE_FLAGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox", "--disable-namespace-sandbox",
    "--single-process", "--no-zygote", "--disable-site-isolation-trials", "--disable-web-security",
    "--allow-running-insecure-content", "--ignore-certificate-errors", "--ignore-certificate-errors-spki-list=x",
    "--ignore-urlfetcher-cert-requests", "--reduce-security-for-testing",
    "--unsafely-treat-insecure-origin-as-secure=http://x.example", "--allow-file-access-from-files",
    "--disable-features-for-testing", "--remote-debugging-port=9222", "--remote-debugging-pipe",
    "--remote-debugging-address=0.0.0.0", "--remote-debugging-socket-name=x", "--remote-allow-origins=*",
    "--auto-open-devtools-for-tabs", "--ip-address-space-overrides=1.2.3.4:80=private",
    "--disable-features=IsolateOrigins,site-per-process,OriginKeyedProcessesByDefault,LocalNetworkAccessChecks,"
    "LocalNetworkAccessForNavigations,LocalNetworkAccessChecksWebRTC,StaticStorageQuota",
    "--enable-features=LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/true",
]
HOSTILE_ENV = {"QTWEBENGINE_DISABLE_SANDBOX": "1", "QTWEBENGINE_REMOTE_DEBUGGING": "9222"}
# an engine switch added by a candidate that reads like one taking a protection away
WEAK_SWITCH = re.compile(r"^--(disable-|no-|allow-|ignore-|unsafely|reduce-security|remote-|single-process|"
                         r"auto-open-devtools|ip-address-space|user-data-dir|proxy-)")
# I.K.E.'s protective defaults (ike/config.py DEFAULTS) and the direction that protects
SAFE_DEFAULTS = {
    "shield_level": "level", "https_only": True, "strip_tracking_params": True, "send_gpc": True,
    "trim_referrer": True, "webrtc_hide_ip": True, "block_third_party_cookies": True, "comp_adblock": True,
    "comp_consent": True, "video_ad_skip": True, "lookalike_warn": True, "clear_on_exit": "same",
    "search_suggestions": "same", "login_compat": "same", "doh": "same", "app_updates": "same",
    "auto_update": True, "perm_block": "kept", "video_ad_skip_hosts": "kept", "translate_url": "same",
    "crx_url": "same", "lang_url": "same", "default_engine": "same", "userscripts_enabled": "same",
}
# what a request does with each value of the corpus: anything but "allow" protects
STOPPED = ("block", "redirect-data")
# response headers that say nothing about I.K.E. (or change from one run to the next)
VOLATILE_HEADERS = {"host", "connection", "proxy-connection", "cache-control", "pragma", "if-none-match",
                    "if-modified-since", "content-length", "content-type", "keep-alive", "te"}
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
# What a page reads that the fingerprinting protection disguises (spoofs or noises): judged by what
# protects the user (_judge_fingerprint), not by equality. Anything else the probe reads (whether an
# API is offered, permissions, the native look of the replaced functions, the third-party image...)
# keeps the exact rule: any change is worse.
FP_JUDGED = re.compile(
    r"^(canvas|canvas_blob|canvas_offset|canvas_flat|canvas_offscreen|audio|audio_copy|audio_analyser|video_frame"
    r"|frame|frame_x|frame_html|frame_srcdoc|worker|shared_worker|file_worker|media_queries"
    r"|webgl2?\.(vendor|renderer|unmasked_vendor|unmasked_renderer|max_texture|extensions|read_pixels)"
    r"|navigator\.(userAgent|appVersion|platform|vendor|product|productSub|oscpu|hardwareConcurrency|deviceMemory"
    r"|language|languages|plugins|mimeTypes|maxTouchPoints|pdfViewerEnabled)"
    r"|screen\.\w+|hints\.\w+|intl\.\w+|fonts_(measured|check|generic|computed))$")
# lists of names (comma separated): a disguised list that shows more of the real one (Off's), or comes
# closer to it, is worse; one randomised on main may change fewer names only by chance: by more than
# NOISE_Z times the spread of the difference of two draws (each name hidden or not by half a chance:
# the variance of a session's count is half its mean) it is worse
FP_LISTS = {"fonts_measured", "fonts_check", "navigator.languages", "navigator.plugins", "webgl.extensions",
            "webgl2.extensions"}

# what the probe hands over only for the size of the noise (no observation of its own): pictures of
# known bytes as read back, the PNG of the canvases and of the blob, text widths, the audio samples;
# and the canvas and sound of another site's frame (the "site." marks)
SAMPLES = {"canvas_pixels", "canvas_offset_pixels", "canvas_flat_pixels", "webgl_pixels", "worker_pixels",
           "frame_pixels", "frame_widths", "text_widths", "audio_samples", "png", "third_frame", "webgl2_pixels",
           "audio_copy_samples"}
# the size of the noise of each noised value, against Off's real one, from SAMPLES: (kind, field, sub)
# Only pictures of varied known bytes: a flat area is noised all or nothing for a given key, so its
# size would be chance (the canvas's own picture has a flat rectangle: its size comes from the
# picture of known bytes drawn the same way; the flat stripes have no size, only their marks).
NOISE = {
    "canvas": (("pixels", "canvas_pixels", None), ("png", "png", "known"), ("widths", "text_widths", None),
               ("site", "third_frame", None)),
    "canvas_blob": (("png", "png", "blob"),),
    "canvas_offset": (("pixels", "canvas_offset_pixels", None),),
    "canvas_flat": (("stripes", "canvas_flat_pixels", None),),
    "webgl.read_pixels": (("pixels", "webgl_pixels", None),),
    "frame": (("pixels", "frame_pixels", None), ("png", "png", "frame_known"), ("widths", "frame_widths", None)),
    "worker": (("pixels", "worker_pixels", None),),
    "audio": (("samples", "audio_samples", None),),
    "fonts_generic": (("widths", "text_widths", None),),
    # the fourth review (N3): the APIs and realms a page has besides the ones above
    "webgl2.read_pixels": (("pixels", "webgl2_pixels", None),),
    "audio_copy": (("samples", "audio_copy_samples", None),),
    "canvas_offscreen": (("png", "png", "offscreen"),),
}
# values whose ".noised" mark (differs from Off) is kept
NOISED = ("canvas", "canvas_blob", "canvas_offset", "canvas_flat", "audio", "audio_copy", "audio_analyser",
          "canvas_offscreen", "video_frame")
# the size of the noise (the two sessions' average) may shrink by this share before it is worse (more
# where few elements changed: _tolerance)
NOISE_TOLERANCE = 0.2
# a false "worse" from chance is at most 3e-5 per measure (one-sided normal, z = 4): with about fifty
# measures judged when a noise is rewritten, under 0.2 % for a whole run
NOISE_Z = 4.0
# the tolerance of chance never above this: where it would be, more readings are taken, not a looser rule
TOLERANCE_CAP = 0.35
# sessions measured at every level but Off (each a page load with its own noise key): enough for what
# is drawn per session to be told from chance (CHANCE, COUNT_Z)
SESSIONS = 8
# a value drawn from a few common ones the same in all sessions is worse only when chance explains it
# less often than this (_chance_alike, an exact permutation test of main's draws and the candidate's)
CHANCE = 1e-4
# the values drawn from a few common ones read again on a small page with this many more keys per level
# (8 + 16 draws on each side: the card's name the same in all of them is 1e-10 by chance, its maker,
# one of two, 1e-3: only the first can be judged, and it is)
PICK_DRAWS = 16
PICK_DRAWN = ("webgl.unmasked_renderer", "webgl.unmasked_vendor", "webgl.extensions", "navigator.hardwareConcurrency",
              "navigator.plugins", "webgl2.unmasked_renderer", "webgl2.unmasked_vendor", "webgl2.extensions",
              "worker", "frame_x")
# a count lower here than on main (names changed, a distance from the real value) is worse beyond
# COUNT_Z times the spread of the difference of the sessions' means (Student's t with 14 degrees of
# freedom for 8 + 8 sessions: 1e-4), the variance at least COUNT_VAR_FLOOR (a count that never varies)
COUNT_Z = 5.0
COUNT_VAR_FLOOR = 0.1
# parts that are lists of names, besides FP_LISTS (the workers' and the frames' WebGL extensions)
LIST_PARTS = {("worker", "[6][1]"), ("shared_worker", "[6][1]"), ("file_worker", "[6][1]"), ("frame_x", "[2]"),
              ("frame_html", "[2]"), ("frame_srcdoc", "[2]")}
# the probe's shape, the same on both sides of a check and random from one check to the next (N3 of
# the fourth review: a code that knew the probe's sizes, text or sound could leave just them alone)
SHAPE = {"pw": 96, "gl": 48, "len": 5000, "freq": 10000, "seed": 12345, "text": "Sphinx of black quartz",
         "word": "mo"}
WORDS = ("amber", "birch", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "juniper", "kelp",
         "lumen", "maple", "nectar", "onyx", "prairie", "quartz", "rowan", "sable", "tundra", "umber", "violet",
         "willow", "zephyr")


def random_shape():
    """A shape of the probe for one check: sizes, text and sound of its own (both sides the same)."""
    import secrets
    r = secrets.SystemRandom()
    return {"pw": r.randrange(80, 113), "gl": r.randrange(40, 57), "len": r.randrange(4096, 6145),
            "freq": r.randrange(7000, 12001), "seed": r.randrange(1000, 99999),
            "text": " ".join(r.choice(WORDS).capitalize() if i == 0 else r.choice(WORDS) for i in range(4)),
            "word": r.choice(WORDS)}
# the new values of a fixed disguise a person counts among the common ones (a fixed disguise that
# changes to anything else is worse); under tests/, as the allowlist
COMMON_VALUES = FIXTURES / "common-values.json"
# the least noise sizes a person keeps (so merges cannot lower the noise step by step); under tests/
NOISE_FLOORS = FIXTURES / "noise-floor.json"
LEVEL_NAMES = {"off": "Off", "compatibility": "Compatibility", "balanced": "Balanced", "strict": "Strict",
               "maximum": "Maximum"}


# --- the probe page --------------------------------------------------------------------------
# what the probe page, the page of the drawn values and the page of the sites share (COMMON_JS): this
# run's shape (SHAPE), pictures of known varied bytes, WebGL and audio reads, the frames' and the
# workers' reads. The workers' source (WORKER_JS) is also served as a file (a dedicated file worker).
WORKER_JS = r"""function run(send){var c=null;try{var oc=new OffscreenCanvas(60,20),x=oc.getContext('2d');
x.fillText('ike',2,10);c=Array.from(x.getImageData(0,0,60,20).data).join(',').length}catch(e){c='e'}
var g=null;try{var gc=new OffscreenCanvas(4,4).getContext('webgl'),gd=gc&&gc.getExtension('WEBGL_debug_renderer_info');
g=gc?[gd?gc.getParameter(gd.UNMASKED_RENDERER_WEBGL):null,(gc.getSupportedExtensions()||[]).join(',')]:'none'}catch(e){g='e '+e}
var kb=null;try{var kc=new OffscreenCanvas(64,64),kx=kc.getContext('2d'),ki=kx.createImageData(64,64),st=99;
for(var i=0;i<ki.data.length;i++){st=(Math.imul(st,1103515245)+12345)>>>0;ki.data[i]=i%4===3?255:st>>>24}
kx.putImageData(ki,0,0);var kd=kx.getImageData(0,0,64,64).data,s='';
for(var j=0;j<kd.length;j+=8192){s+=String.fromCharCode.apply(null,Array.from(kd.subarray(j,j+8192)))}kb=btoa(s)}
catch(e){kb=null}
send([navigator.userAgent,navigator.platform,navigator.hardwareConcurrency,navigator.deviceMemory,
(navigator.languages||[]).join(','),c,g,kb])}
"""
COMMON_JS = r"""
  var SHAPE = __SHAPE__;
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
  // what the pictures, the frame's and the blob give, kept for the size of their noise (SAMPLES)
  var PNG = {};
  function canvasHash(doc) {
    var c = doc.createElement('canvas'); c.width = 220; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText(SHAPE.text + ' ☺', 2, 10);
    x.strokeStyle = 'rgba(102,204,0,0.7)'; x.arc(160, 20, 15, 0, Math.PI * 2); x.stroke();
    var url = c.toDataURL(), at = doc === document ? 'canvas' : 'frame';
    if (!PNG[at]) PNG[at] = url;
    return [hash(url), hash(Array.from(x.getImageData(0, 0, 220, 40).data.slice(0, 4000)).join(',')),
            x.measureText(SHAPE.text).width];
  }
  function settle(p, ms, late) { return Promise.race([p, new Promise(function (ok) { setTimeout(function () { ok(late); }, ms); })]); }
  function b64(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i += 8192) s += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + 8192)));
    return btoa(s);
  }
  // varied opaque bytes the page knows (the protection's noise skips nothing opaque)
  function knownBytes(n, seed) {
    var a = new Uint8ClampedArray(n * 4), st = seed;
    for (var i = 0; i < a.length; i++) { st = (Math.imul(st, 1103515245) + 12345) >>> 0; a[i] = i % 4 === 3 ? 255 : st >>> 24; }
    return a;
  }
  // a picture of known varied bytes (seed), with another block of known bytes put at (dx, dy) when kw is
  // given; doc: the document it belongs to (a frame's)
  function picture(w, h, seed, kw, kh, dx, dy, seed2, doc) {
    var c = (doc || document).createElement('canvas'); c.width = w; c.height = h;
    var x = c.getContext('2d'), img = x.createImageData(w, h);
    img.data.set(knownBytes(w * h, seed)); x.putImageData(img, 0, 0);
    if (kw) { var b = x.createImageData(kw, kh); b.data.set(knownBytes(kw * kh, seed2)); x.putImageData(b, dx, dy); }
    return x;
  }
  function readAll(x) { return b64(x.getImageData(0, 0, x.canvas.width, x.canvas.height).data); }
  function dataUrl(b) {
    return new Promise(function (ok) { var fr = new FileReader(); fr.onload = function () { ok(String(fr.result)); };
      fr.onerror = function () { ok('error'); }; fr.readAsDataURL(b); });
  }
  function blobOf(c) {
    return settle(new Promise(function (ok) { c.toBlob(function (b) { dataUrl(b).then(ok); }); }), 3000, 'timeout');
  }
  // a WebGL context (kind: webgl or webgl2) of a document: its identity, and what readPixels gives of
  // a texture of known varied bytes (a cleared, flat picture is noised all or nothing for a given key)
  function glRead(kind, doc) {
    var g = (doc || document).createElement('canvas').getContext(kind);
    if (!g) return null;
    var dbg = g.getExtension('WEBGL_debug_renderer_info');
    var out = {vendor: g.getParameter(g.VENDOR), renderer: g.getParameter(g.RENDERER),
      unmasked_vendor: dbg ? g.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      unmasked_renderer: dbg ? g.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      max_texture: g.getParameter(g.MAX_TEXTURE_SIZE), extensions: (g.getSupportedExtensions() || []).join(',')};
    var N = SHAPE.gl, tex = g.createTexture();
    g.bindTexture(g.TEXTURE_2D, tex);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, N, N, 0, g.RGBA, g.UNSIGNED_BYTE, new Uint8Array(knownBytes(N * N, SHAPE.seed + 4).buffer));
    g.bindFramebuffer(g.FRAMEBUFFER, g.createFramebuffer());
    g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, tex, 0);
    var px = new Uint8Array(N * N * 4);
    g.readPixels(0, 0, N, N, g.RGBA, g.UNSIGNED_BYTE, px);
    out.pixels = b64(px);
    return out;
  }
  function oscillate(W, node) {
    var ac = new W.OfflineAudioContext(1, SHAPE.len, 44100), o = ac.createOscillator(), n = node(ac);
    o.type = 'triangle'; o.frequency.value = SHAPE.freq; o.connect(n); n.connect(ac.destination); o.start(0);
    return ac;
  }
  // the sound of a window (a frame's): its last 500 samples, read by getChannelData
  async function render(win) {
    var ac = oscillate(win || window, function (a) { return a.createDynamicsCompressor(); }), len = SHAPE.len;
    var buf = await ac.startRendering(), d = buf.getChannelData(0), sum = 0;
    for (var i = len - 500; i < len; i++) sum += Math.abs(d[i]);
    return [sum.toFixed(10), Array.from(d.slice(len - 500, len))];
  }
  // the same samples read by copyFromChannel of a buffer whose getChannelData was never called
  async function renderCopy() {
    var ac = oscillate(window, function (a) { return a.createDynamicsCompressor(); }), len = SHAPE.len;
    var buf = await ac.startRendering(), cp = new Float32Array(500), sum = 0;
    buf.copyFromChannel(cp, 0, len - 500);
    for (var i = 0; i < 500; i++) sum += Math.abs(cp[i]);
    return [sum.toFixed(10), Array.from(cp)];
  }
  // what an AnalyserNode gives of the same sound, halfway
  async function analyse() {
    var an = null, ac = oscillate(window, function (a) { an = a.createAnalyser(); return an; });
    var f = new Float32Array(an.frequencyBinCount), b = new Uint8Array(an.frequencyBinCount), t = new Float32Array(an.fftSize);
    ac.suspend(Math.floor(SHAPE.len / 256) * 128 / 44100).then(function () {
      an.getFloatFrequencyData(f); an.getByteFrequencyData(b); an.getFloatTimeDomainData(t); ac.resume(); });
    await ac.startRendering();
    return hash(Array.from(f).map(function (v) { return v.toFixed(4); }).join(',') + '|' + Array.from(b).join(',') + '|' +
      Array.from(t).map(function (v) { return v.toFixed(6); }).join(','));
  }
  // a frame's own reads: its canvas, card, extensions, sound, languages, cores, readPixels
  async function frameRead(fw) {
    var g = null, a = null;
    try { g = glRead('webgl', fw.document); } catch (e) { g = null; }
    try { a = (await render(fw))[0]; } catch (e) { a = 'error ' + e; }
    return [canvasHash(fw.document)[0], g ? g.unmasked_renderer : null, g ? g.extensions : null, a,
      (fw.navigator.languages || []).join(','), fw.navigator.hardwareConcurrency, g ? hash(g.pixels) : null];
  }
  var WORKER = __WORKER__;
  // a worker's reads (dedicated from a blob, shared, or dedicated from a file of the site)
  function worker(kind) {
    return new Promise(function (ok) {
      try {
        var w;
        if (kind === 'shared') {
          w = new SharedWorker(URL.createObjectURL(new Blob([WORKER +
            'onconnect=function(e){var p=e.ports[0];run(function(m){p.postMessage(m)})};'], {type: 'text/javascript'})));
          w.port.onmessage = function (e) { ok(e.data); };
          w.port.start();
        } else {
          w = kind === 'file' ? new Worker('/__WFILE__.js') : new Worker(URL.createObjectURL(new Blob([WORKER +
            'run(function(m){postMessage(m)});'], {type: 'text/javascript'})));
          w.onmessage = function (e) { ok(e.data); };
          w.onerror = function () { ok('worker error'); };
        }
      } catch (e) { ok('worker error ' + e); }
      setTimeout(function () { ok('worker timeout'); }, 4000);
    });
  }
"""
PROBE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="unsafe-url">
<title>__TITLE__</title></head><body><p>__TITLE__</p>
<script>
(async function () {
  var R = {};
  __COMMON__
  // each noised value read twice in this session: it must read the same (ST, "stable" in the tool)
  var ST = {};
  try { R.canvas = canvasHash(document); ST.canvas = JSON.stringify(canvasHash(document)) === JSON.stringify(R.canvas); }
  catch (e) { R.canvas = 'error ' + e; }
  try {
    var px = picture(SHAPE.pw, SHAPE.pw, SHAPE.seed);
    R.canvas_pixels = readAll(px); ST.canvas_pixels = readAll(px) === R.canvas_pixels;
    var ox = picture(64, 48, 555, 40, 40, 7, 3, 777);
    R.canvas_offset_pixels = readAll(ox); R.canvas_offset = hash(R.canvas_offset_pixels);
    ST.canvas_offset = readAll(ox) === R.canvas_offset_pixels;
    // flat colours: a stripe of one colour is noised all or nothing for a given key (1 in 8), so 896
    // stripes, each of a colour of its own (the noise reads a byte without its lowest bit: the colours
    // differ in the other bits; 448 stripes repeating every 256 were noised alike in pairs, and the count
    // of stripes changed varied more than its tolerance of chance allowed, measured 2026-11-24): none
    // noised at all by chance is (7/8)^896, and the count changed (about 1 in 8, 8 sessions) rests on
    // enough for a tolerance of 20 %
    var fc = document.createElement('canvas'); fc.width = 16; fc.height = 896;
    var fx = fc.getContext('2d');
    for (var fr = 0; fr < 896; fr++) {
      var fa = fr & 127, fb = fr >> 7;
      fx.fillStyle = 'rgb(' + (((fa * 37 + 11) & 127) << 1) + ',' + (((fb * 91 + fa * 13 + 40) & 127) << 1) + ',' +
        (((fa * 53 + fb * 29 + 90) & 127) << 1) + ')';
      fx.fillRect(0, fr, 16, 1);
    }
    var flat = readAll(fx); R.canvas_flat = hash(flat); R.canvas_flat_pixels = flat;
    ST.canvas_flat = readAll(fx) === flat;
    // what toDataURL gives of a picture of known bytes (its noise has a size; the canvas's own
    // picture has a flat rectangle)
    PNG.known = picture(64, 64, 8642).canvas.toDataURL();
  } catch (e) { R.canvas_offset = R.canvas_flat = 'error ' + e; }
  try {
    // enough varied opaque pixels that a noise always shows (a flat picture had a few bytes changed:
    // a start with no change at all was likely)
    var bc = picture(64, 64, 2468).canvas;
    var bx = bc.getContext('2d'); bx.fillStyle = '#fff'; bx.fillText('ike', 2, 7);
    PNG.blob = await blobOf(bc);
    R.canvas_blob = PNG.blob === 'timeout' ? 'timeout' : hash(PNG.blob);
    ST.canvas_blob = (await blobOf(bc)) === PNG.blob;
  } catch (e) { R.canvas_blob = 'error ' + e; }
  // an OffscreenCanvas of known bytes by convertToBlob, and a VideoFrame of a canvas copied out (N3)
  try {
    var offBlob = async function () {
      var oc = new OffscreenCanvas(64, 64), ox = oc.getContext('2d'), oi = ox.createImageData(64, 64);
      oi.data.set(knownBytes(64 * 64, SHAPE.seed + 7)); ox.putImageData(oi, 0, 0);
      return dataUrl(await oc.convertToBlob());
    };
    PNG.offscreen = await settle(offBlob(), 3000, 'timeout');
    R.canvas_offscreen = PNG.offscreen === 'timeout' ? 'timeout' : hash(PNG.offscreen);
    ST.canvas_offscreen = (await settle(offBlob(), 3000, 'timeout')) === PNG.offscreen;
  } catch (e) { R.canvas_offscreen = 'error ' + e; }
  try {
    var vfc = picture(32, 32, SHAPE.seed + 9).canvas, vf = new VideoFrame(vfc, {timestamp: 0});
    var vbuf = new Uint8Array(vf.allocationSize());
    await vf.copyTo(vbuf); vf.close();
    R.video_frame = hash(b64(vbuf));
  } catch (e) { R.video_frame = 'error ' + e; }
  try {
    var tw = document.createElement('canvas').getContext('2d');
    tw.font = '16px sans-serif';
    R.text_widths = [];
    for (var ti = 0; ti < 128; ti++) R.text_widths.push(tw.measureText(SHAPE.word + ' ' + ti + ' gy ' + (ti * 37) + ' kAy').width);
  } catch (e) { R.text_widths = null; }
  // WebGL and WebGL2: the card, its limits and extensions, readPixels of a texture of known bytes
  ['webgl', 'webgl2'].forEach(function (kind) {
    try {
      var gr = glRead(kind);
      if (gr) {
        R[kind + '_pixels'] = gr.pixels; delete gr.pixels;
        gr.read_pixels = hash(R[kind + '_pixels']);
        var again = glRead(kind);
        ST[kind + '_pixels'] = !!again && again.pixels === R[kind + '_pixels'];
      }
      R[kind] = gr;
    } catch (e) { R[kind] = 'error ' + e; }
  });
  try {
    var a1 = await render();
    R.audio = a1[0]; R.audio_samples = a1[1];
    ST.audio = (await render())[0] === R.audio;
  } catch (e) { R.audio = 'error ' + e; }
  try {
    var a2 = await renderCopy();
    R.audio_copy = a2[0]; R.audio_copy_samples = a2[1];
    ST.audio_copy = (await renderCopy())[0] === R.audio_copy;
  } catch (e) { R.audio_copy = 'error ' + e; }
  try { R.audio_analyser = await analyse(); ST.audio_analyser = (await analyse()) === R.audio_analyser; }
  catch (e) { R.audio_analyser = 'error ' + e; }
  var n = navigator;
  R.navigator = {userAgent: n.userAgent, appVersion: n.appVersion, platform: n.platform, vendor: n.vendor,
    product: n.product, productSub: n.productSub, oscpu: n.oscpu === undefined ? 'undefined' : n.oscpu,
    hardwareConcurrency: n.hardwareConcurrency, deviceMemory: n.deviceMemory, language: n.language,
    languages: (n.languages || []).join(','), plugins: Array.from(n.plugins).map(function (p) { return p.name; }).join(','),
    mimeTypes: n.mimeTypes.length, webdriver: n.webdriver, maxTouchPoints: n.maxTouchPoints,
    pdfViewerEnabled: n.pdfViewerEnabled, doNotTrack: n.doNotTrack, globalPrivacyControl: n.globalPrivacyControl,
    cookieEnabled: n.cookieEnabled, connection: typeof n.connection, getBattery: typeof n.getBattery,
    keyboard: typeof n.keyboard, gpu: typeof n.gpu, bluetooth: typeof n.bluetooth, usb: typeof n.usb,
    hid: typeof n.hid, serial: typeof n.serial};
  R.screen = {width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight,
    availLeft: screen.availLeft, availTop: screen.availTop, colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
    devicePixelRatio: devicePixelRatio, orientation: screen.orientation ? screen.orientation.type : null,
    screenX: screenX, screenY: screenY, outerIsInnerWidth: outerWidth === innerWidth,
    outerIsInnerHeight: outerHeight === innerHeight};
  try {
    var ua = n.userAgentData;
    R.hints = ua ? {brands: JSON.stringify(ua.brands), mobile: ua.mobile, platform: ua.platform,
      high: JSON.stringify(await ua.getHighEntropyValues(['architecture', 'bitness', 'model', 'platformVersion',
        'fullVersionList', 'uaFullVersion', 'wow64', 'formFactors']))} : null;
  } catch (e) { R.hints = 'error ' + e; }
  try {
    var devs = await n.mediaDevices.enumerateDevices();
    R.media_devices = devs.map(function (d) { return d.kind + ':' + d.deviceId + ':' + d.label; }).join('|');
  } catch (e) { R.media_devices = 'error ' + e; }
  try {
    if (n.gpu) {
      var ad = await settle(n.gpu.requestAdapter(), 5000, 'timeout');
      R.webgpu = ad === 'timeout' ? 'timeout' : ad ? [ad.info ? [ad.info.vendor, ad.info.architecture, ad.info.device, ad.info.description].join('/') : '',
        Array.from(ad.features || []).sort().join(',')] : 'no adapter';
    } else R.webgpu = 'none';
  } catch (e) { R.webgpu = 'error ' + e; }
  try {
    var wd = await worker('dedicated');
    if (Array.isArray(wd) && wd.length === 8) { R.worker_pixels = wd[7]; wd = wd.slice(0, 7); }
    R.worker = wd;
  } catch (e) { R.worker = 'error ' + e; }
  // a shared worker, and a dedicated worker from a file of the site (N3): the same reads, the known
  // picture's hash last
  for (var wk of ['shared', 'file']) {
    try {
      var wr = await worker(wk);
      if (Array.isArray(wr) && wr.length === 8) wr[7] = wr[7] ? hash(wr[7]) : null;
      R[wk + '_worker'] = wr;
    } catch (e) { R[wk + '_worker'] = 'error ' + e; }
  }
  try {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    var fw = f.contentWindow;
    R.frame = [fw.navigator.hardwareConcurrency, fw.navigator.userAgent, fw.navigator.plugins.length,
      fw.screen.width, canvasHash(fw.document)];
    var fpic = picture(64, 64, 1357, 0, 0, 0, 0, 0, fw.document);
    R.frame_pixels = readAll(fpic);
    PNG.frame_known = fpic.canvas.toDataURL();
    var fwx = fw.document.createElement('canvas').getContext('2d');
    fwx.font = '16px sans-serif';
    R.frame_widths = [];
    for (var fi = 0; fi < 64; fi++) R.frame_widths.push(fwx.measureText('Fr ' + fi + ' qz ' + (fi * 29) + ' Wy').width);
    R.frame_x = await frameRead(fw);
  } catch (e) { R.frame = 'error ' + e; }
  // frames made other ways (N3): by innerHTML, and from srcdoc (loaded)
  try {
    var hd = document.createElement('div'); hd.innerHTML = '<iframe></iframe>'; document.body.appendChild(hd);
    R.frame_html = await frameRead(hd.firstChild.contentWindow);
  } catch (e) { R.frame_html = 'error ' + e; }
  try {
    var sw = await settle(new Promise(function (ok) {
      var sf = document.createElement('iframe'); sf.onload = function () { ok(sf.contentWindow); };
      sf.srcdoc = '<!doctype html><p>' + SHAPE.word + '</p>'; document.body.appendChild(sf); }), 3000, null);
    R.frame_srcdoc = sw ? await frameRead(sw) : 'timeout';
  } catch (e) { R.frame_srcdoc = 'error ' + e; }
  var FONTS = ['Arial', 'Times New Roman', 'Courier New', 'Helvetica', 'Verdana', 'Georgia', 'Comic Sans MS', 'Impact',
    'Trebuchet MS', 'Tahoma', 'DejaVu Sans', 'DejaVu Serif', 'DejaVu Sans Mono', 'Liberation Sans', 'Liberation Serif',
    'Liberation Mono', 'Noto Sans', 'Noto Serif', 'Noto Color Emoji', 'Ubuntu', 'Cantarell', 'Roboto', 'Open Sans',
    'Segoe UI', 'Calibri', 'Cambria', 'Monaco', 'Menlo', 'Wingdings', 'Lucida Console', 'Palatino Linotype',
    'Garamond', 'Bitstream Vera Sans', 'Nimbus Sans', 'FreeSans', 'Source Code Pro', 'Fira Sans', 'Hack'];
  try {
    var c2 = document.createElement('canvas').getContext('2d'), s = 'mmmmmmmmmmlli WIW 0123';
    var wd = function (fam) { c2.font = '72px ' + fam; return c2.measureText(s).width; };
    var base = {monospace: wd('monospace'), serif: wd('serif'), 'sans-serif': wd('sans-serif')};
    R.fonts_measured = FONTS.filter(function (fam) { return ['monospace', 'serif', 'sans-serif'].some(function (b) {
      return wd("'" + fam + "', " + b) !== base[b]; }); }).join(',');
    R.fonts_check = FONTS.filter(function (fam) { try { return document.fonts.check("12px '" + fam + "'"); } catch (e) { return false; } }).join(',');
    R.fonts_generic = [base.monospace, base.serif, base['sans-serif']];
  } catch (e) { R.fonts_measured = 'error ' + e; }
  try {
    var span = document.createElement('span'); span.textContent = 'I.K.E.'; document.body.appendChild(span);
    R.fonts_computed = [getComputedStyle(span).fontFamily, (function () { span.style.fontFamily = 'serif'; return getComputedStyle(span).fontFamily; })()];
  } catch (e) { R.fonts_computed = 'error ' + e; }
  try {
    R.local_fonts = await settle(window.queryLocalFonts ? window.queryLocalFonts().then(function (l) { return 'fonts ' + l.length; },
      function (e) { return 'refused ' + e.name; }) : Promise.resolve('none'), 3000, 'timeout');
  } catch (e) { R.local_fonts = 'error ' + e.name; }
  var MQ = ['(prefers-color-scheme: dark)', '(prefers-reduced-motion: reduce)', '(prefers-contrast: more)',
    '(forced-colors: active)', '(pointer: fine)', '(pointer: coarse)', '(any-pointer: coarse)', '(hover: hover)',
    '(any-hover: hover)', '(color-gamut: srgb)', '(color-gamut: p3)', '(dynamic-range: high)',
    '(inverted-colors: inverted)', '(monochrome)', '(prefers-reduced-transparency: reduce)',
    '(display-mode: browser)', '(orientation: landscape)', '(min-resolution: 2dppx)', '(scripting: enabled)',
    '(update: fast)', '(min-device-width: 1920px)', '(max-device-width: 1024px)', '(min-device-height: 1080px)',
    '(device-aspect-ratio: 16/9)'];
  R.media_queries = MQ.map(function (q) { try { return q + '=' + matchMedia(q).matches; } catch (e) { return q + '=error'; } }).join(' ');
  try {
    var o2 = Intl.DateTimeFormat().resolvedOptions();
    R.intl = {timeZone: o2.timeZone, locale: o2.locale, calendar: o2.calendar, numbering: o2.numberingSystem,
      offset: new Date(0).getTimezoneOffset(), number: Intl.NumberFormat().resolvedOptions().locale,
      dateText: new Date(0).toString().replace(/^.*?GMT/, 'GMT')};
  } catch (e) { R.intl = 'error ' + e; }
  try {
    var est = await settle(navigator.storage.estimate(), 10000, null);   // 3 s ran out once in 20 checks of a busy computer
    R.storage_quota = est ? est.quota : 'timeout';
  } catch (e) { R.storage_quota = 'error ' + e; }
  try { R.voices = window.speechSynthesis ? speechSynthesis.getVoices().length : 'none'; } catch (e) { R.voices = 'error ' + e; }
  try {
    var bat = n.getBattery ? await settle(n.getBattery(), 3000, null) : null;
    R.battery = bat ? [bat.charging, bat.level, bat.chargingTime, String(bat.dischargingTime)] : 'none';
  } catch (e) { R.battery = 'error ' + e.name; }
  try {
    R.keyboard = n.keyboard && n.keyboard.getLayoutMap ? await settle(n.keyboard.getLayoutMap().then(function (m) {
      return 'map ' + m.size; }, function (e) { return 'refused ' + e.name; }), 3000, 'timeout') : 'none';
  } catch (e) { R.keyboard = 'error ' + e.name; }
  R.permissions = {};
  var PERMS = ['geolocation', 'notifications', 'camera', 'microphone', 'clipboard-read', 'clipboard-write',
    'local-fonts', 'midi', 'persistent-storage', 'screen-wake-lock', 'storage-access', 'window-management'];
  for (var pi = 0; pi < PERMS.length; pi++) {
    try { R.permissions[PERMS[pi]] = (await settle(n.permissions.query({name: PERMS[pi]}), 2000, {state: 'timeout'})).state; }
    catch (e) { R.permissions[PERMS[pi]] = 'error ' + e.name; }
  }
  try { R.permissions['Notification.permission'] = window.Notification ? Notification.permission : 'none'; } catch (e) {}
  var natives = {
    toDataURL: HTMLCanvasElement.prototype.toDataURL, getImageData: CanvasRenderingContext2D.prototype.getImageData,
    getParameter: WebGLRenderingContext.prototype.getParameter, getChannelData: AudioBuffer.prototype.getChannelData,
    hardwareConcurrency: Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency').get,
    toString: Function.prototype.toString, matchMedia: window.matchMedia,
    enumerateDevices: MediaDevices.prototype.enumerateDevices
  };
  R.natives = {};
  Object.keys(natives).forEach(function (k) {
    var fn = natives[k], src = '';
    try { src = Function.prototype.toString.call(fn); } catch (e) { src = 'error'; }
    R.natives[k] = [/\{\s*\[native code\]\s*\}\s*$/.test(src), fn && fn.name, fn && fn.length].join(':');
  });
  R.ike_scheme = await settle(new Promise(function (ok) {
    var im = new Image(); im.onload = function () { ok('loaded'); }; im.onerror = function () { ok('refused'); };
    im.src = 'ike:logo'; }), 3000, 'timeout');
  R.third_party = await settle(new Promise(function (ok) {
    var im = new Image(); im.onload = function () { ok('loaded'); }; im.onerror = function () { ok('error'); };
    im.src = location.protocol + '//__THIRD__/pixel.png?__LVP__=__LV__'; document.body.appendChild(im); }), 4000, 'timeout');
  // the same canvas and sound in a frame of another site: its noise must differ from this site's
  R.third_frame = await settle(new Promise(function (ok) {
    window.addEventListener('message', function (e) { if (e.data && e.data.k === '__TAG__') ok(e.data.v); });
    var tf = document.createElement('iframe');
    tf.src = location.protocol + '//__THIRD__/__FRAME__?__LVP__=__LV__'; document.body.appendChild(tf); }), 6000, 'timeout');
  R.stable = ST;
  R.png = PNG;
  window['__GLOBAL__'] = JSON.stringify(R);
})();
</script></body></html>"""


# --- inside the browser (IKE_TEST_HOOK) ------------------------------------------------------
HOOK = r'''
import hashlib
import json
import os
import shlex
import sys
import time
import traceback

from PyQt6.QtCore import QTimer, QUrl

PLAN = json.load(open(os.environ["__PLAN_ENV__"], encoding="utf-8"))
OUT = {"errors": []}
_gen = None
_FONT_WAIT = [0]


def _finish():
    try:
        net = sys.modules.get(PLAN["netmod"])
        OUT["python_hosts"] = sorted(set(net.hosts)) if net is not None else None
    except Exception:
        OUT["python_hosts"] = None
    with open(PLAN["out"], "w", encoding="utf-8") as f:
        json.dump(OUT, f, default=str)
    for w in list(ike.windows):           # noqa: F821  (given by the browser)
        w.close()
    QTimer.singleShot(200, qapp.quit)       # noqa: F821


def _step():
    try:
        wait = next(_gen)
    except StopIteration:
        _finish()
        return
    except Exception:
        OUT["errors"].append({"section": "hook", "error": traceback.format_exc()[-3000:]})
        _finish()
        return
    QTimer.singleShot(int(wait or 0), _step)


def _err(section, exc=None):
    OUT["errors"].append({"section": section, "error": (traceback.format_exc() if exc is None else str(exc))[-3000:]})


class Fake:
    """What I.K.E.'s request check reads of a request, without a network."""
    def __init__(self, q):
        from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as I
        self.q = q
        self.url = QUrl(q["url"])
        self.rtype = getattr(I.ResourceType, "ResourceType" + q["type"])
        self.first = QUrl(q.get("source") or "")
        self.init = QUrl(q.get("initiator") or "")
        self.nav = getattr(I.NavigationType, "NavigationType" + q.get("nav", "Other"))
        self.method = q.get("method", "GET").encode("ascii")
        self.given = {}
        if q.get("referer"):
            self.given[b"Referer"] = q["referer"].encode("latin-1")
        for k, v in (q.get("headers") or {}).items():
            self.given[k.encode("latin-1")] = v.encode("latin-1")
        self.redirected = None
        self.blocked = False
        self.headers = {}

    def requestUrl(self): return self.url
    def resourceType(self): return self.rtype
    def firstPartyUrl(self): return self.first
    def initiator(self): return self.init
    def navigationType(self): return self.nav
    def requestMethod(self): return self.method
    def httpHeaders(self): return dict(self.given)
    def redirect(self, u): self.redirected = u.toString()
    def block(self, b): self.blocked = bool(b)
    def setHttpHeader(self, k, v): self.headers[bytes(k).decode("latin-1").lower()] = bytes(v).decode("latin-1")

    def result(self):
        if self.blocked:
            action = "block"
        elif self.redirected:
            target = self.redirected
            u = QUrl(self.q["url"])
            t = QUrl(target)
            if target.startswith("data:"):
                action = "redirect-data"
            elif t.scheme() == "https" and u.scheme() == "http" and t.host() == u.host() and t.path() == u.path():
                action = "https-upgrade"
            elif t.scheme() == u.scheme() and t.host() == u.host() and t.path() == u.path():
                action = "clean " + target
            else:
                action = "redirect " + target
        else:
            action = "allow"
        return {"action": action, "headers": self.headers}


def _load(view, url, out, key, limit=20):
    done = {}
    page = view.page()

    def finished(ok, done=done):
        done.setdefault("ok", ok)
    page.loadFinished.connect(finished)
    view.load(QUrl(url))
    end = time.monotonic() + limit
    while "ok" not in done and time.monotonic() < end:
        yield 20
    try:
        page.loadFinished.disconnect(finished)
    except Exception:
        pass
    out[key] = done.get("ok", "timeout")


def _js(view, code, box, limit=10):
    res = {}
    view.page().runJavaScript(code, 0, lambda r, res=res: res.setdefault("r", r))
    end = time.monotonic() + limit
    while "r" not in res and time.monotonic() < end:
        yield 20
    box["r"] = res.get("r")


def _settings(st):
    from PyQt6.QtWebEngineCore import QWebEngineSettings as S
    out = {}
    for name, attr in S.WebAttribute.__members__.items():
        try:
            out[name] = bool(st.testAttribute(attr))
        except Exception as exc:
            out[name] = "error " + type(exc).__name__
    for name, fam in S.FontFamily.__members__.items():
        try:
            out["font:" + name] = st.fontFamily(fam)
        except Exception:
            pass
    try:
        out["unknownUrlSchemePolicy"] = st.unknownUrlSchemePolicy().name
    except Exception:
        pass
    return out


def _profile(p):
    out = {}
    for name in ("httpUserAgent", "httpAcceptLanguage", "isOffTheRecord", "httpCacheType",
                 "persistentCookiesPolicy", "persistentPermissionsPolicy", "isSpellCheckEnabled",
                 "isPushServiceEnabled"):
        fn = getattr(p, name, None)
        if fn is None:
            continue
        try:
            v = fn()
            out[name] = v.name if hasattr(v, "name") else v
        except Exception as exc:
            out[name] = "error " + type(exc).__name__
    scripts, fpcfg = [], None
    for s in p.scripts().toList():
        scripts.append("%s|world %s|%s|subframes %s" % (s.name(), int(s.worldId()), s.injectionPoint().name,
                                                        s.runsOnSubFrames()))
        src = s.sourceCode()
        if "I.K.E. fingerprinting protection" in src[:400] and fpcfg is None:
            at = src.find("var CFG = ")
            if at >= 0:
                try:
                    fpcfg = json.JSONDecoder().raw_decode(src, at + len("var CFG = "))[0]
                except ValueError:
                    fpcfg = "unreadable"
    if isinstance(fpcfg, dict):
        fpcfg.pop("key", None)
        if "fonts" in fpcfg:
            # the names masked (None: the whole list of fingerprint.js), judged against the fonts a page
            # can find, measured by the tool in the same run (fonts_findable)
            out["fonts_masked"] = fpcfg["fonts"] if isinstance(fpcfg["fonts"], list) else None
        for big in ("psl", "fonts"):
            if big in fpcfg:
                fpcfg[big] = "sha256 " + hashlib.sha256(json.dumps(fpcfg[big]).encode()).hexdigest()[:16]
    out["scripts"] = sorted(scripts)
    out["fingerprint_config"] = fpcfg
    return out


COSMETIC_JS = r"""(function(keys, probes, attr){var out={}; keys.forEach(function(k){
 var e=document.querySelector('['+attr+'="'+k+'"]'); if(!e){out[k]='removed';return;}
 var cs=getComputedStyle(e), r=e.getBoundingClientRect();
 out[k]=(cs.display==='none'||cs.visibility==='hidden'||cs.opacity==='0'||(r.width===0&&r.height===0))?'hidden':'shown';});
 var p={}; Object.keys(probes).forEach(function(k){try{p[k]=String((0,eval)(probes[k]))}catch(e){p[k]='error '+e.name}});
 return JSON.stringify({elements:out, probes:p});})(%s, %s, %s)"""


def _keys(sh, key):
    for p in list(sh.profiles):
        sh.profile_keys[id(p)] = key


def _probe(view, tag, limit=40, page=None, host=None):
    """The probe page (or another of the server's) loaded at the level tag, on the run's first site or
    on `host`; (loaded, what its scripts read or None)."""
    state, box, found = {}, {}, None
    base = ("%s://%s" % (PLAN.get("scheme") or "http", host)) if host else PLAN["base"]
    yield from _load(view, "%s/%s?%s=%s" % (base, page or PLAN["path"], PLAN["param"], tag), state, "ok")
    end = time.monotonic() + limit
    while time.monotonic() < end:
        yield from _js(view, "window[%s] || ''" % json.dumps(PLAN["global"]), box)
        if box.get("r"):
            found = json.loads(box["r"])
            break
        yield 100
    return state.get("ok"), found


def _list_verdicts():
    """What the filter lists' own data says of each request of the corpus: an engine of this
    checkout built from the lists alone (not I.K.E.'s own rules), keeping the rules' text, gives the
    rule that blocks it, or the exception that lets it through, and the list each comes from; with
    a digest of each list's data. Only evidence (the comparison accepts a request newly let
    through when the list data that decides it changed): what cannot be read here is left out."""
    OUT["list_verdicts"] = OUT["list_data"] = None
    try:
        from ike import blocker as bmod
        from ike import shields as smod
        ab = bmod.adblock
        raw = {url: open(path, encoding="utf-8").read() for url, path in PLAN["lists"].items()}
        clean = getattr(bmod, "sanitize", lambda t: t)
        texts = {url: clean(t) for url, t in raw.items()}
        fs = ab.FilterSet(debug=True)
        for t in texts.values():
            fs.add_filter_list(t)
        eng = ab.Engine(fs, optimize=False)
        lines = {url: {x.strip() for x in t.splitlines()} for url, t in texts.items()}

        def source(rule):
            return next((u for u in sorted(lines) if rule in lines[u]), None) if rule else None
        types = getattr(smod, "_TYPES", {})
        out = {}
        for q in PLAN["requests"]:
            r = eng.check_network_urls(q["url"], q.get("source") or "", types.get(Fake(q).rtype, "other"))
            rule, exc = getattr(r, "filter", None), getattr(r, "exception", None)
            stops = bool(r.matched) and not (exc and not getattr(r, "important", False))
            out[q["id"]] = {"verdict": "block" if stops else "allow", "rule": rule, "rule_list": source(rule),
                            "exception": exc, "exception_list": source(exc)}
        OUT["list_verdicts"] = out
        OUT["list_data"] = {url: hashlib.sha256(t.encode("utf-8")).hexdigest() for url, t in raw.items()}
    except Exception:
        OUT["list_verdicts"] = OUT["list_data"] = None


# the tool's own test of which fonts a page can find (a text's width in the font against the default
# fonts), in a page of its own, in a profile with none of I.K.E.'s scripts
FONTS_JS = r"""(function (names) {
  var s = 'mmmmmmmmmmlli1WQ@#&ABCxyz', out = [], box = document.createElement('div');
  document.body.appendChild(box);
  function w(f) {
    var e = document.createElement('span');
    e.style.cssText = 'font-size:72px;position:absolute;white-space:nowrap;font-family:' + f;
    e.textContent = s; box.appendChild(e);
    var r = e.offsetWidth + 'x' + e.offsetHeight; box.removeChild(e); return r;
  }
  var base = {}; ['monospace', 'serif', 'sans-serif'].forEach(function (b) { base[b] = w(b); });
  names.forEach(function (n) {
    if (['monospace', 'serif', 'sans-serif'].some(function (b) {
      return w("'" + n.replace(/'/g, '') + "'," + b) !== base[b];
    })) out.push(n);
  });
  return out;
})"""


# the fonts a page can find, tested inside the protected page itself and in a frame of it (N4 of the
# fourth review): at Strict and Maximum none of the fonts a page can find on this computer may keep its
# own width there
FONTS_IN_PAGE_JS = r"""(function (names) {
  function test(doc) {
    var s = 'mmmmmmmmmmlli1WQ@#&ABCxyz', out = [], box = doc.createElement('div');
    doc.body.appendChild(box);
    function w(f) {
      var e = doc.createElement('span');
      e.style.cssText = 'font-size:72px;position:absolute;white-space:nowrap;font-family:' + f;
      e.textContent = s; box.appendChild(e);
      var r = e.offsetWidth + 'x' + e.offsetHeight; box.removeChild(e); return r;
    }
    var base = {}; ['monospace', 'serif', 'sans-serif'].forEach(function (b) { base[b] = w(b); });
    names.forEach(function (n) {
      if (['monospace', 'serif', 'sans-serif'].some(function (b) {
        return w("'" + n.replace(/'/g, '') + "'," + b) !== base[b];
      })) out.push(n);
    });
    box.remove();
    return out;
  }
  var r = {page: test(document)};
  try {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    r.frame = test(f.contentWindow.document); f.remove();
  } catch (e) { r.frame = 'error ' + e; }
  return JSON.stringify(r);
})"""


def _fonts_findable():
    """OUT["fonts_findable"]: the names a page can find on this computer among those fingerprint.js
    masks (main's list and this one's: PLAN["fonts_main"]) and the families installed; OUT["fonts_list"]:
    fingerprint.js's list (what is masked when the settings carry none). Every level's masked names are
    judged against them (the tool's rule "fonts"), not by the names' digest, which follows the computer
    and the time of the answer; and at Strict and Maximum each is tested in the protected page."""
    import re as _re
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from ike.config import RES_DIR
    try:
        text = open(os.path.join(str(RES_DIR), "fingerprint.js"), encoding="utf-8").read()
        found = _re.search(r"var MASKED_FONTS = (\[.*?\]);", text, _re.S)
        listed = json.loads(found.group(1)) if found else []
        names, seen = [], set()
        for n in list(listed) + list(PLAN.get("fonts_main") or ()) + \
                [_re.sub(r"\s*\[[^\]]*\]$", "", str(f)).strip() for f in QFontDatabase.families()]:
            if n and n.lower() not in seen:
                seen.add(n.lower())
                names.append(n)
        OUT["fonts_list"] = listed
        got, state = {}, {}
        prof = QWebEngineProfile(qapp)              # noqa: F821  (off the record, none of I.K.E.'s scripts)
        page = QWebEnginePage(prof, qapp)           # noqa: F821
        page.loadFinished.connect(lambda ok: state.update(loaded=ok))
        page.setHtml("<!doctype html><body></body>", QUrl("about:blank"))
        end = time.monotonic() + 30
        while "loaded" not in state and time.monotonic() < end:
            yield 100
        page.runJavaScript(FONTS_JS + "(%s)" % json.dumps(names), 0, lambda r: got.update(r=r))
        end = time.monotonic() + 60
        while "r" not in got and time.monotonic() < end:
            yield 100
        if isinstance(got.get("r"), list):
            OUT["fonts_findable"] = [str(x) for x in got["r"]]
        else:
            _err("fonts", "the fonts a page can find could not be measured")
        page.deleteLater()
    except Exception:
        _err("fonts")


def measure():
    yield 300
    b, sh, cfg = ike.blocker, ike.shields, ike.config        # noqa: F821
    sections = set(PLAN["sections"])
    from ike import blocker as bmod
    late = []
    for url, path in PLAN["lists"].items():
        text = open(path, encoding="utf-8").read()
        p = bmod.list_path(url)
        try:
            if not p.exists() or p.read_text("utf-8") != text:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, "utf-8")
                late.append(url)
        except Exception:
            _err("lists")
    if late:
        b.load()
    yield 100
    end = time.monotonic() + 60
    while b.building and time.monotonic() < end:
        yield 50
    OUT["engine"] = {"native": bool(b.native), "built": b.engine is not None, "errors": b.errors,
                     "lists_written_late": late}
    # the fonts a page could find (fontcheck.py) were asked and awaited before measure() (_start, the
    # one wait): a check with no answer would let a level be measured before it and another after it
    fcm = sys.modules.get("ike.fontcheck")
    if getattr(ike, "font_check", None) is not None and fcm is not None and \
            getattr(fcm, "findable", lambda: True)() is None:  # noqa: F821
        _err("fonts", "the check of the fonts a page could find gave no answer in 60 s")
    if sections & {"fingerprint", "security"}:
        yield from _fonts_findable()
    if "requests" in sections:
        _list_verdicts()
    try:
        _keys(sh, PLAN["keys"][0])
    except Exception:
        _err("fingerprint")
    view = ike.windows[0].current_view()            # noqa: F821
    OUT["levels"] = {}
    for lv in PLAN["levels"]:
        cfg["shield_level"] = lv
        try:
            sh.apply_settings()
        except Exception:
            _err("security")
        yield 50
        here = OUT["levels"][lv] = {}
        if "requests" in sections:
            icp = sh.interceptor
            res = here["requests"] = {}
            for q in PLAN["requests"]:
                f = Fake(q)
                try:
                    icp.interceptRequest(f)
                    res[q["id"]] = f.result()
                except Exception as exc:
                    res[q["id"]] = {"action": "error %s" % type(exc).__name__, "headers": {}}
        if sections & {"fingerprint", "security"}:
            here["loaded"], here["probe"] = yield from _probe(view, lv)
            if "fingerprint" in sections and OUT.get("fonts_findable") is not None:
                box = {}
                yield from _js(view, FONTS_IN_PAGE_JS + "(%s)" % json.dumps(OUT["fonts_findable"]), box, limit=30)
                try:
                    here["fonts_found"] = json.loads(box.get("r") or "null")
                except ValueError:
                    here["fonts_found"] = None
            try:
                here["page_settings"] = _settings(view.page().settings())
                prof = view.page().profile()
                here["profile_settings"] = _settings(prof.settings())
                here["profile"] = _profile(prof)
            except Exception:
                _err("security")
        if "fingerprint" in sections and PLAN.get("keys"):
            # more sessions: other noise keys, as new starts of the browser have; what the protection
            # randomises must differ between them (Off: one more, for its stability). Each with its own
            # tag ("<level>.s<n>"), so the headers the server keeps for the level are the first session's.
            here["probe_sessions"] = []
            for n, key in enumerate(PLAN["keys"][1:2] if lv == "off" else PLAN["keys"][1:], 2):
                got = None
                try:
                    _keys(sh, key)
                    sh.apply_settings()
                except Exception:
                    _err("fingerprint")
                else:
                    yield 50
                    _loaded, got = yield from _probe(view, "%s.s%d" % (lv, n))
                here["probe_sessions"].append(got)
            here["probe_session2"] = here["probe_sessions"][0] if here["probe_sessions"] else None
            if lv != "off":
                # the values drawn from a few common ones, read with more keys on a small page: enough
                # draws for their being the same in every session to be told from chance
                here["picks"] = []
                for n, key in enumerate(PLAN.get("pick_keys") or (), 1):
                    got = None
                    try:
                        _keys(sh, key)
                        sh.apply_settings()
                    except Exception:
                        _err("fingerprint")
                    else:
                        yield 20
                        _loaded, got = yield from _probe(view, "%s.p%d" % (lv, n), page=PLAN["pick"], limit=15)
                    here["picks"].append(got)
            try:
                _keys(sh, PLAN["keys"][0])
                sh.apply_settings()
            except Exception:
                _err("fingerprint")
            yield 50
            # N1 of the fourth review: the page of the sites on the run's hosts (Off: the first one, its
            # real values), the first key: other sites differ, two hosts of one site agree
            if PLAN.get("sites") and PLAN.get("site"):
                here["sites"] = {}
                for name in (["a"] if lv == "off" else PLAN.get("site_order") or sorted(PLAN["sites"])):
                    _loaded, got = yield from _probe(view, "%s.%s" % (lv, name), page=PLAN["site"], limit=15,
                                                     host=PLAN["sites"][name])
                    here["sites"][name] = got
            # N2: the first key once more on the probe page: what is noised must read as it did then
            if lv != "off" and PLAN.get("again", True):
                _loaded, here["probe_again"] = yield from _probe(view, "%s.again" % lv)
        if "cosmetic" in sections:
            pages = here["pages"] = {}
            for pg in PLAN["pages"]:
                state = {}
                yield from _load(view, "http://%s%s" % (pg["host"], pg["path"]), state, "ok")
                keys = [e["key"] for e in pg["elements"]]
                code = COSMETIC_JS % (json.dumps(keys), json.dumps(pg.get("probes") or {}), json.dumps(PLAN["attr"]))
                last, same, seen = None, 0, None
                start = time.monotonic()
                while time.monotonic() - start < 5:
                    box = {}
                    yield from _js(view, code, box)
                    seen = box.get("r")
                    same = same + 1 if seen == last else 0
                    last = seen
                    if same >= 4 and time.monotonic() - start > 0.6:
                        break
                    yield 100
                pages[pg["id"]] = {"loaded": state.get("ok"), "result": json.loads(seen) if seen else None}
    if "scriptlets" in sections:
        try:
            OUT["scriptlets"] = {h: b.scriptlets.for_host(h) for h in PLAN["scriptlet_hosts"]}
            OUT["video_hosts"] = sh.video_hosts()
        except Exception:
            _err("scriptlets")
    if "cosmetic" in sections:
        try:
            cos = OUT["cosmetic_rules"] = {}
            classes, ids = set(), set()
            import re as _re
            for pg in PLAN["pages"]:
                for e in pg["elements"]:
                    classes.update(c for m in _re.findall(r'class="([^"]*)"', e["html"]) for c in m.split())
                    ids.update(_re.findall(r'id="([^"]*)"', e["html"]))
            for url in PLAN["cosmetic_urls"]:
                css, exceptions, generichide = b.cosmetic_css(url)
                res = b.engine.url_cosmetic_resources(url)
                hide = sorted(s for s in set(res.hide_selectors) if s in css)
                generic = b.generic_css(sorted(classes), sorted(ids), exceptions)
                gsel = sorted(s for s in set(b.engine.hidden_class_id_selectors(sorted(classes), sorted(ids),
                                                                                 exceptions)) if s in generic)
                cos[url] = {"hide": hide, "generic": gsel, "generichide": bool(generichide),
                            "styles": sorted(line for line in css.splitlines() if "display:none" not in line)}
        except Exception:
            _err("cosmetic")
    if "security" in sections:
        yield from security()


def security():
    from ike import app as A
    sec = OUT["security"] = {}
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    sec["flags"] = shlex.split(flags)
    try:
        sec["sandbox_off"] = A.sandbox_off()
        sec["site_isolated"] = A.site_isolated()
        sec["engine_safety"] = {k: sorted(set(v)) for k, v in A.ENGINE_SAFETY.items()}
    except Exception:
        _err("security")
    lists = sec["lists"] = {}
    for mod, names in (("app", ("UNSAFE_SWITCHES", "NOTICE_SWITCHES", "UNSAFE_FEATURES", "LNA_FEATURES",
                                 "PRIVACY_FEATURES", "UNSAFE_ENV")),
                       ("config", ("LOGIN_HOSTS", "SENSITIVE_HOSTS", "PAYMENT_SITES")),
                       ("shields", ("TRACKING_PARAMS", "TRACKING_PREFIXES")),
                       ("blocker", ("BUILTIN_RULES",))):
        try:
            m = __import__("ike." + mod, fromlist=["x"])
        except Exception:
            _err("security")
            continue
        for name in names:
            v = getattr(m, name, None)
            if v is None:
                lists["%s.%s" % (mod, name)] = None
            elif isinstance(v, str):
                lists["%s.%s" % (mod, name)] = sorted({x.strip() for x in v.splitlines()
                                                      if x.strip() and not x.startswith("!")})
            else:
                lists["%s.%s" % (mod, name)] = sorted(str(x) for x in v)
    try:
        from ike import config as C
        sec["defaults"] = {k: C.DEFAULTS.get(k, "(missing)") for k in PLAN["defaults"]}
        sec["default_lists"] = sorted("%s|%s|%s" % (e.get("url"), e.get("group", "ads"),
                                                    "on" if e.get("enabled", True) else "off")
                                      for e in C.DEFAULT_LISTS)
    except Exception:
        _err("security")
    try:
        from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
        sec["ike_scheme_flags"] = int(QWebEngineUrlScheme.schemeByName(b"ike").flags().value)
    except Exception:
        try:
            from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
            sec["ike_scheme_flags"] = int(QWebEngineUrlScheme.schemeByName(b"ike").flags())
        except Exception:
            _err("security")
    # what I.K.E. makes of a hostile environment, without IKE_ALLOW_UNSAFE_ENGINE (and not as root)
    keep = {k: os.environ.get(k) for k in ("QTWEBENGINE_CHROMIUM_FLAGS", "IKE_ALLOW_UNSAFE_ENGINE",
                                           "QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_REMOTE_DEBUGGING",
                                           "IKE_WIDEVINE")}
    safety = {k: list(v) for k, v in A.ENGINE_SAFETY.items()}
    euid = getattr(os, "geteuid", None)
    try:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(shlex.quote(f) for f in PLAN["hostile_flags"])
        os.environ.pop("IKE_ALLOW_UNSAFE_ENGINE", None)
        os.environ.update(PLAN["hostile_env"])
        if euid is not None:
            os.geteuid = lambda: 1000
        A._chromium_flags(ike.config)        # noqa: F821
        sec["hostile_result"] = shlex.split(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
        sec["hostile_env_left"] = sorted(k for k in PLAN["hostile_env"] if k in os.environ)
    except Exception:
        _err("security")
    finally:
        if euid is not None:
            os.geteuid = euid
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        A.ENGINE_SAFETY.clear()
        A.ENGINE_SAFETY.update(safety)
    yield 0


def network():
    yield 300
    start = time.monotonic()
    while time.monotonic() - start < PLAN["settle"]:
        yield 200
    view = ike.windows[0].current_view()            # noqa: F821
    loaded, found = yield from _probe(view, "network", limit=30)
    OUT["probe_loaded"] = loaded
    OUT["probe_done"] = found is not None
    # what the protection gives with this start's own random key (no key of the tool's): two starts
    # must differ from each other and from Off ("natural" in the tool)
    OUT["probe"] = {k: found.get(k) for k in ("canvas", "canvas_blob", "audio")} if found else None
    yield 1500


def _start():
    global _gen
    # a fresh profile shows the welcome of the first start (1.1.24) before any window: it is
    # skipped as a new user skips it (the defaults kept), and the run waits for the first window.
    # This hook runs from main against the candidate, so it must know the welcome before the
    # version that brings it can pass the comparison.
    dlg = getattr(ike, "welcome", None)
    if dlg is not None:
        (getattr(dlg, "skip_all", None) or dlg.reject)()
        QTimer.singleShot(500, _start)
        return
    # the fonts a page can find (ike/fontcheck.py) are asked once, about 15 s after the start;
    # until then Strict and Maximum mask the whole list, afterwards only the fonts found here.
    # Both protect the same, but a level measured before the answer and the same level measured
    # after it differ: the run asks at once and waits for the answer (at most 60 s), so the
    # base and the candidate are measured in the same state (2026-11-24, a false "worse" on
    # fingerprint-config/maximum/fonts that stopped every pull request).
    fc = getattr(ike, "font_check", None)
    fcm = sys.modules.get("ike.fontcheck")
    if fc is not None and fcm is not None and getattr(fcm, "findable", lambda: True)() is None \
            and _FONT_WAIT[0] < 120:
        if _FONT_WAIT[0] == 0:
            try:
                fc._run()
            except Exception:
                _FONT_WAIT[0] = 120
        _FONT_WAIT[0] += 1
        QTimer.singleShot(500, _start)
        return
    _gen = measure() if PLAN["mode"] == "measure" else network()
    _step()


QTimer.singleShot(300, _start)
'''

# the browser's own process: a Python audit hook records (and refuses) every connection I.K.E.'s
# own code tries to a host that is not this computer, before ike_boot.py runs
WRAPPER = r'''
import os
import runpy
import sys
import types

_hosts = []
_mod = types.ModuleType("__NETMOD__")
_mod.hosts = _hosts
sys.modules["__NETMOD__"] = _mod


def _name(h):
    return (h.decode("ascii", "replace") if isinstance(h, (bytes, bytearray)) else str(h)).lower().strip("[]")


def _local(h):
    h = _name(h)
    return not h or h in ("localhost", "::1", "0.0.0.0", "::") or h.startswith("127.") or h.endswith(".localhost")


def _audit(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
        if host is not None and not _local(host):
            _hosts.append(_name(host))
            raise OSError(101, "Network is unreachable")
    elif event == "socket.connect":
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr and isinstance(addr[0], (str, bytes)) and not _local(addr[0]):
            _hosts.append(_name(addr[0]))
            raise OSError(101, "Network is unreachable")


sys.addaudithook(_audit)
boot = sys.argv[1]
sys.argv = [boot] + sys.argv[2:]
sys.path[0] = os.path.dirname(os.path.abspath(boot))
runpy.run_path(boot, run_name="__main__")
'''


# the values drawn from a few common ones (PICK_DRAWN), alone: read with PICK_DRAWS more keys per level
PICK_PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title></head><body>
<script>
(async function () {
  var R = {webgl: {}, webgl2: {}, navigator: {}};
  __COMMON__
  ['webgl', 'webgl2'].forEach(function (kind) {
    try {
      var gl = document.createElement('canvas').getContext(kind);
      var dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
      R[kind].unmasked_vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null;
      R[kind].unmasked_renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null;
      R[kind].extensions = gl ? (gl.getSupportedExtensions() || []).join(',') : null;
    } catch (e) { R[kind] = 'error ' + e; }
  });
  R.navigator.hardwareConcurrency = navigator.hardwareConcurrency;
  R.navigator.plugins = Array.from(navigator.plugins).map(function (p) { return p.name; }).join(',');
  // the worker's and a frame's card and extensions too, with the same draws (N8)
  try {
    var wd = await worker('dedicated');
    R.worker = Array.isArray(wd) && wd.length === 8 ? wd.slice(0, 7) : wd;
  } catch (e) { R.worker = 'error ' + e; }
  try {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    R.frame_x = await frameRead(f.contentWindow);
  } catch (e) { R.frame_x = 'error ' + e; }
  window['__GLOBAL__'] = JSON.stringify(R);
})();
</script></body></html>"""

# the page of the sites (N1 of the fourth review): read on two hosts of one site and on hosts of other
# sites (one under a public suffix of two labels): different sites must differ, two hosts of one site
# agree, and every host is noised
SITE_PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title></head><body>
<script>
(async function () {
  var R = {};
  __COMMON__
  try { R.pic = hash(readAll(picture(SHAPE.pw, SHAPE.pw, SHAPE.seed + 11))); } catch (e) { R.pic = 'error ' + e; }
  try { R.url = hash(picture(48, 48, SHAPE.seed + 13).canvas.toDataURL()); } catch (e) { R.url = 'error ' + e; }
  try { R.audio = (await render())[0]; } catch (e) { R.audio = 'error ' + e; }
  try { var g = glRead('webgl'); R.gl = g ? hash(g.pixels) : null; } catch (e) { R.gl = 'error ' + e; }
  try {
    var tw = document.createElement('canvas').getContext('2d'), ws = [];
    tw.font = '16px sans-serif';
    for (var i = 0; i < 32; i++) ws.push(tw.measureText(SHAPE.word + ' ' + i + ' ' + SHAPE.text).width);
    R.width = hash(ws.join(','));
  } catch (e) { R.width = 'error ' + e; }
  window['__GLOBAL__'] = JSON.stringify(R);
})();
</script></body></html>"""
SITE_READS = ("pic", "url", "audio", "gl", "width")


# the probe's canvas and sound drawn the same way in a frame of another site (R.third_frame): with a
# per-site noise they must differ from the probe page's own
FRAME = r"""<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title></head><body>
<script>
(async function () {
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
  function canvasHash(doc) {
    var c = doc.createElement('canvas'); c.width = 220; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText(__TEXT__ + ' ☺', 2, 10);
    x.strokeStyle = 'rgba(102,204,0,0.7)'; x.arc(160, 20, 15, 0, Math.PI * 2); x.stroke();
    return hash(c.toDataURL());
  }
  async function render() {
    var len = __LEN__, ac = new OfflineAudioContext(1, len, 44100), o = ac.createOscillator(), comp = ac.createDynamicsCompressor();
    o.type = 'triangle'; o.frequency.value = __FREQ__; o.connect(comp); comp.connect(ac.destination); o.start(0);
    var buf = await ac.startRendering(), d = buf.getChannelData(0), sum = 0;
    for (var i = len - 500; i < len; i++) sum += Math.abs(d[i]);
    return sum.toFixed(10);
  }
  // the page's picture of known bytes, read here too: its noise must differ where it is per site
  function known() {
    var P = __PW__, c = document.createElement('canvas'); c.width = P; c.height = P;
    var x = c.getContext('2d'), img = x.createImageData(P, P), st = __SEED__;
    for (var i = 0; i < img.data.length; i++) { st = (Math.imul(st, 1103515245) + 12345) >>> 0; img.data[i] = i % 4 === 3 ? 255 : st >>> 24; }
    x.putImageData(img, 0, 0);
    var d = x.getImageData(0, 0, P, P).data, s = '';
    for (var j = 0; j < d.length; j += 8192) s += String.fromCharCode.apply(null, Array.from(d.subarray(j, j + 8192)));
    return btoa(s);
  }
  var v = null;
  try { v = [canvasHash(document), await render(), known()]; } catch (e) { v = 'error ' + e; }
  parent.postMessage({k: '__TAG__', v: v}, '*');
})();
</script></body></html>"""


def run_names(seed=None):
    """This run's own names for what the code measured could see (the probe's path, its query, title,
    global, the frame's host and path, the hook's files and variable...): random, nothing that says
    "no regression". What is kept is written back with the fixed ones (Server._plain). seed: the same
    names every time (a snapshot made on its own, as fixed_keys(): two of them compare)."""
    import random
    import secrets
    r = secrets.SystemRandom() if seed is None else random.Random(seed)
    t = lambda: "%010x" % r.getrandbits(40)  # noqa: E731

    def word():
        """A name that reads like a real site's: syllables of a consonant and a vowel."""
        return "".join(r.choice("bcdfgklmnprstvz") + r.choice("aeiou") for _ in range(r.randrange(2, 5)))
    # the probe on hosts of real-looking sites (N1 of the fourth review: an address of this computer
    # told the code measured where it was, and every page was one site): "a" and a host of the same
    # site ("a2"), two sites under a public suffix of two labels ("b", "c": not one site), a .com ("d")
    # and another common top-level domain ("e")
    tlds = ["com", "net", "org", "de", "fr", "it", "nl", "es", "io", "eu", "pl", "ch", "at", "se"]
    first, other = r.sample(tlds, 2)
    words = []
    while len(words) < 6:
        w = word()
        if w not in words:
            words.append(w)
    a = "%s.%s" % (words[0], first)
    sites = {"a": a, "a2": "%s.%s" % (r.choice(("www", "shop", "news", "m", "app")), a),
             "b": "%s.co.uk" % words[1], "c": "%s.co.uk" % words[2], "d": "%s.com" % words[3],
             "e": "%s.%s" % (words[4], other)}
    return {"path": t(), "param": "q" + t(), "title": t(), "global": "_" + t(), "frame": t(), "tag": t(),
            "third": "%s.%s" % (words[5], r.choice(tlds)), "attr": "data-" + t(), "hook": "h" + t(),
            "wrapper": "w" + t(), "out": "o" + t(), "plan": "p" + t(), "env": "Q" + t().upper(), "netmod": "_" + t(),
            "dirs": ["d" + t() for _ in range(3)], "pick": t(), "site": t(), "wfile": t(), "sites": sites}


# the fixed names a recorded value gets back for this run's sites (Server._plain)
SITE_NAMES = {"a": "site-a.test", "a2": "www.site-a.test", "b": "site-b.test", "c": "site-c.test",
              "d": "site-d.test", "e": "site-e.test"}


# --- the local server: probe pages, and the proxy every other address goes to ------------
class Server:
    """127.0.0.1: the probe page (direct) and, as the engine's and Qt's proxy, the pages of the corpus's
    hosts; any other host the browser asks for is recorded and refused (nothing leaves the computer)."""

    def __init__(self, corpus, names=None, shape=None):
        self.pages = {p["host"]: p for p in corpus["pages"]}
        self.names = names or run_names()
        self.shape = dict(SHAPE, **(shape or {}))
        self.sites = set((self.names.get("sites") or {}).values())
        self.tls = None
        self.ca = None
        self.contacted = []
        self.headers = {}
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def do_CONNECT(self):
                host = self.path.rsplit(":", 1)[0].strip("[]").lower()
                if outer.tls is not None and self.path.endswith(":443") and \
                        (host in outer.sites or host == outer.names["third"]):
                    # the run's sites over https (N1 of the fourth review: secure contexts with real-looking
                    # names): the tunnel ends here, with a certificate of this run's own authority
                    self.send_response(200, "Connection established")
                    self.end_headers()
                    self.wfile.flush()
                    try:
                        conn = outer.tls.wrap_socket(self.connection, server_side=True)
                    except OSError:
                        self.close_connection = True
                        return
                    self.connection = conn
                    self.rfile = conn.makefile("rb", -1)
                    self.wfile = conn.makefile("wb", 0)
                    self.tls_host = host
                    self.close_connection = False
                    self.handle_one_request()
                    self.close_connection = True
                    return
                outer._record(host, "CONNECT")
                self.send_error(403)

            def _any(self):
                if getattr(self, "tls_host", None) and not self.path.startswith(("http://", "https://")):
                    u = urlsplit(self.path)
                    host, path, query = self.tls_host, u.path or "/", u.query
                elif self.path.startswith(("http://", "https://", "ws://", "wss://")):
                    u = urlsplit(self.path)
                    host = (u.hostname or "").lower()
                    if host not in outer.pages and host != outer.names["third"] and host not in outer.sites:
                        outer._record(host, self.command)
                        self.send_error(502)
                        return
                    path, query = u.path or "/", u.query
                else:
                    host = "127.0.0.1"
                    u = urlsplit(self.path)
                    path, query = u.path, u.query
                body, kind = outer.serve(host, path, parse_qs(query), self.headers)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            do_GET = do_POST = do_HEAD = _any

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def _record(self, host, how):
        with self.lock:
            self.contacted.append(host)

    def take(self):
        with self.lock:
            out, self.contacted = sorted(set(self.contacted)), []
        return out

    def _plain(self, v):
        """A recorded value with this run's random names given back their fixed ones (THIRD, /fp, lv),
        so what is kept is the same from one run to the next."""
        v = re.sub(r":%s\b" % self.port, ":PORT", v)
        n = self.names
        for k, host in sorted((n.get("sites") or {}).items(), key=lambda kv: -len(kv[1])):
            v = v.replace(host, SITE_NAMES.get(k, "site.test"))
        return v.replace(n["third"], THIRD).replace("/%s?%s=" % (n["path"], n["param"]), "/fp?lv=")

    def _keep(self, which, lv, headers):
        kept = {}
        for k, v in headers.items():
            k = k.lower()
            if k in VOLATILE_HEADERS:
                continue
            kept[k] = self._plain(v)
        with self.lock:
            self.headers.setdefault(lv, {})[which] = kept

    def _common(self, text):
        n, s = self.names, self.shape
        return text.replace("__COMMON__", COMMON_JS).replace("__SHAPE__", json.dumps(s)) \
            .replace("__WORKER__", json.dumps(WORKER_JS)).replace("__WFILE__", n.get("wfile", "w")) \
            .replace("__GLOBAL__", n["global"]).replace("__TITLE__", n["title"])

    def page(self, lv):
        n = self.names
        return self._common(PROBE.replace("__THIRD__", n["third"]).replace("__LVP__", n["param"])
                            .replace("__LV__", lv).replace("__FRAME__", n["frame"]).replace("__TAG__", n["tag"]))

    def serve(self, host, path, query, headers):
        n, s = self.names, self.shape
        lv = (query.get(n["param"]) or ["?"])[0]
        ours = host == "127.0.0.1" or host in self.sites
        if ours and path == "/" + n["path"]:
            if lv.split(".")[0] in LEVELS and "." not in lv:
                self._keep("page", lv, headers)
            return self.page(lv).encode("utf-8"), "text/html; charset=utf-8"
        if host == n["third"] and path == "/pixel.png":
            self._keep("third-party", lv, headers)
            return PNG, "image/png"
        if ours and path == "/" + n["pick"]:
            return self._common(PICK_PAGE).encode("utf-8"), "text/html; charset=utf-8"
        if ours and path == "/" + n.get("site", "-"):
            return self._common(SITE_PAGE).encode("utf-8"), "text/html; charset=utf-8"
        if ours and path == "/%s.js" % n.get("wfile", "-"):
            return (WORKER_JS + "run(function(m){postMessage(m)});").encode("utf-8"), "text/javascript"
        if host == n["third"] and path == "/" + n["frame"]:
            return FRAME.replace("__TAG__", n["tag"]).replace("__TITLE__", n["title"]) \
                .replace("__PW__", str(int(s["pw"]))).replace("__SEED__", str(int(s["seed"]))) \
                .replace("__TEXT__", json.dumps(s["text"])).replace("__LEN__", str(int(s["len"]))) \
                .replace("__FREQ__", str(int(s["freq"]))).encode("utf-8"), "text/html; charset=utf-8"
        page = self.pages.get(host)
        if page and path == page["path"]:
            parts = []
            for e in page["elements"]:
                html = e["html"]
                at = html.index(">")
                parts.append(html[:at] + ' %s="%s"' % (n["attr"], e["key"]) + html[at:])
            body = "<!doctype html><html><head><meta charset=\"utf-8\"><title>%s</title></head><body>%s</body></html>" \
                % (page["id"], "\n".join(parts))
            return body.encode("utf-8"), "text/html; charset=utf-8"
        return None, None

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def https(self, folder):
        """The run's own certificate authority and a certificate for its sites (openssl): the authority's
        file to trust in the browser's profile, or None (the sites then over http, not secure contexts)."""
        import ssl
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        hosts = sorted(self.sites | {self.names["third"]})
        try:
            def run(*cmd):
                subprocess.run(["openssl", *cmd], cwd=str(folder), capture_output=True, timeout=60, check=True)
            run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem", "-days", "2",
                "-subj", "/CN=%s" % self.names["title"], "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign")
            run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "leaf.key", "-out", "leaf.csr",
                "-subj", "/CN=%s" % hosts[0])
            (folder / "ext.cnf").write_text("subjectAltName=%s\nbasicConstraints=CA:FALSE\n"
                                            "extendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
                                            % ",".join("DNS:%s" % h for h in hosts), "utf-8")
            run("x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
                "-out", "leaf.pem", "-days", "2", "-extfile", "ext.cnf")
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(folder / "leaf.pem"), str(folder / "leaf.key"))
        except (OSError, subprocess.SubprocessError, ssl.SSLError):
            return None
        self.tls = ctx
        return str(folder / "ca.pem")


# --- the snapshot ------------------------------------------------------------------------------
def load_corpus(fixtures=FIXTURES):
    corpus = json.loads((Path(fixtures) / "corpus.json").read_text("utf-8"))
    for url, rel in corpus["lists"].items():
        corpus["lists"][url] = str((Path(fixtures) / rel).resolve())
    return corpus


def _lists_version(repo):
    m = re.search(r'"lists_version":\s*(\d+)', (Path(repo) / "ike" / "config.py").read_text("utf-8", "replace"))
    return int(m.group(1)) if m else 5


def _git(repo, *args):
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def run_browser(repo, mode, plan, settings, server, workdir, timeout, other_machine=False):
    """Start the checkout's I.K.E. with a profile of its own in workdir; returns the hook's output.
    other_machine: another real environment (OTHER_MACHINE: time zone, language, screen size)."""
    workdir = Path(workdir)
    home = workdir / "home"
    cfg = home / ".config" / "ike-browser"
    cfg.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        (cfg / "settings.json").write_text(json.dumps(settings), "utf-8")
        lists = home / ".local/share/ike-browser/lists"
        lists.mkdir(parents=True, exist_ok=True)
        for url, path in plan.get("lists", {}).items():
            name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt"
            (lists / name).write_text(Path(path).read_text("utf-8"), "utf-8")
    # names of this run's own, nothing that says what runs: the code measured can see its files and
    # environment (a partial measure; docs/MAINTENANCE.md)
    n = server.names
    hook, wrapper = workdir / ("%s.py" % n["hook"]), workdir / ("%s.py" % n["wrapper"])
    hook.write_text(HOOK.replace("__PLAN_ENV__", n["env"]), "utf-8")
    wrapper.write_text(WRAPPER.replace("__NETMOD__", n["netmod"]), "utf-8")
    out = workdir / ("%s.json" % n["out"])
    # the probe on the run's first site (a fresh profile of the "network" mode upgrades a site to https,
    # which the local server does not answer: there the address of this computer, as before)
    sites = n.get("sites") or {}
    scheme = "https" if server.ca else "http"
    base = "%s://%s" % (scheme, sites["a"]) if mode == "measure" and sites.get("a") else server.base
    plan = dict(plan, mode=mode, out=str(out), base=base, path=n["path"], param=n["param"], pick=n["pick"],
                attr=n["attr"], netmod=n["netmod"], site=n.get("site"), wfile=n.get("wfile"),
                **{"global": n["global"]})
    if "sites" not in plan:
        plan["sites"] = sites if mode == "measure" else {}
    plan["site_order"] = [k for k in ("a", "a2", "b", "c", "d", "e") if k in plan["sites"]]
    plan["scheme"] = scheme
    if server.ca and mode == "measure":
        # the run's own certificate authority, trusted in this profile only (its NSS database)
        nss = home / ".pki" / "nssdb"
        nss.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["certutil", "-d", "sql:%s" % nss, "-N", "--empty-password"], capture_output=True,
                           timeout=60, check=True)
            subprocess.run(["certutil", "-d", "sql:%s" % nss, "-A", "-t", "C,,", "-n", n["title"], "-i", server.ca],
                           capture_output=True, timeout=60, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"errors": [{"section": mode, "error": "the run's certificate authority could not be trusted in the "
                                                          "profile (certutil, libnss3-tools): %s" % exc}]}
    (workdir / ("%s.json" % n["plan"])).write_text(json.dumps(plan), "utf-8")
    (workdir / "run").mkdir(mode=0o700, exist_ok=True)
    proxy = "http://127.0.0.1:%d" % server.port
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("XDG_", "IKE_", "LANG", "LC_", "QTWEBENGINE_")) and k.lower() not in
           ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ftp_proxy")}
    env.update({
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_CACHE_HOME": str(home / ".cache"), "XDG_RUNTIME_DIR": str(workdir / "run"),
        "QT_QPA_PLATFORM": "offscreen", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "QTWEBENGINE_CHROMIUM_FLAGS": " ".join(INPUT_FLAGS + ["--proxy-server=%s" % proxy]),
        "QTWEBENGINE_DISABLE_SANDBOX": "1", "IKE_ALLOW_UNSAFE_ENGINE": "1",
        "IKE_NO_SINGLE": "1", "IKE_TEST_NOASK": "1", "IKE_TEST_HOOK": str(hook),
        n["env"]: str(workdir / ("%s.json" % n["plan"])),
        "DBUS_SESSION_BUS_ADDRESS": "",
        "http_proxy": proxy, "https_proxy": proxy, "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy,
        "all_proxy": proxy, "ALL_PROXY": proxy, "no_proxy": "127.0.0.1,localhost", "NO_PROXY": "127.0.0.1,localhost",
    })
    preexec, shim = None, None
    if other_machine:
        screen = workdir / ("%s.json" % n["out"].replace("o", "s", 1))
        screen.write_text(json.dumps({"screens": [dict(OTHER_MACHINE["screen"], name="s", x=0, y=0, logicalDpi=96,
                                                       logicalBaseDpi=96, dpr=1)]}), "utf-8")
        env.update({"TZ": OTHER_MACHINE["tz"], "LANG": OTHER_MACHINE["lang"],
                    "QT_QPA_PLATFORM": "offscreen:configfile=%s" % screen})
        # N7 of the fourth review: other processors and memory too, so a disguise that equals this
        # computer's real value (4 cores, 8 GB, as GitHub's runners) is told from the real one
        cpus = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
        if len(cpus) >= 2:
            keep = cpus[:OTHER_MACHINE["cpus"]] if len(cpus) > OTHER_MACHINE["cpus"] else cpus[:1]
            preexec = lambda keep=keep: os.sched_setaffinity(0, keep)  # noqa: E731
        shim = _memory_shim(workdir)
        if shim:
            env["LD_PRELOAD"] = shim
    cmd = [sys.executable, str(wrapper), str(Path(repo).resolve() / "ike_boot.py")]
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, preexec_fn=preexec)
        code, stderr = proc.returncode, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code, stderr = "timeout", (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) \
            else (exc.stderr or "")
    if not out.exists():
        return {"errors": [{"section": mode, "error": "the browser ended without results (exit %s): %s"
                            % (code, stderr[-2000:])}]}
    data = json.loads(out.read_text("utf-8"))
    data["exit"] = code
    if other_machine and not shim:
        # no other memory on the other machine: a disguise equal to this computer's could not be told
        data.setdefault("errors", []).append({"section": "fingerprint", "error": "the other machine's memory could "
                                              "not be set (no C compiler for its small library)"})
    return data


def masked_fonts(repo):
    """The names fingerprint.js masks (its MASKED_FONTS), of a checkout; [] when it has none."""
    try:
        text = (Path(repo) / "ike" / "resources" / "fingerprint.js").read_text("utf-8")
        m = re.search(r"var MASKED_FONTS = (\[.*?\]);", text, re.S)
        return [str(x) for x in json.loads(m.group(1))] if m else []
    except (OSError, ValueError):
        return []


def snapshot(repo, levels=LEVELS, sections=SECTIONS, fixtures=FIXTURES, keep=None, settle=6.0, keys=None,
             shape=None, fonts_main=None, names=None):
    """The behaviour snapshot of the checkout in `repo` (a dict, see FORMAT). keys: the noise keys of
    the measured sessions, SESSIONS of them (default fixed_keys(); `check` gives both sides the same
    random ones, so the code measured cannot know them in advance). shape: the probe's sizes, text and
    sound (default SHAPE; `check` gives both sides the same random one), names: the run's random names
    and sites (run_names(); `check` gives both sides the same: the noise is per site). fonts_main: main's names of
    fingerprint.js's MASKED_FONTS, tested here too (N4: a name taken out of the list is still tested)."""
    repo = Path(repo).resolve()
    corpus = load_corpus(fixtures)
    t0 = time.monotonic()
    keys = list(keys or fixed_keys(SESSIONS + PICK_DRAWS))
    plan = {"levels": list(levels), "sections": list(sections), "lists": corpus["lists"],
            "requests": corpus["requests"], "pages": corpus["pages"], "cosmetic_urls": corpus["cosmetic_urls"],
            "scriptlet_hosts": corpus["scriptlet_hosts"], "keys": keys[:SESSIONS],
            "pick_keys": keys[SESSIONS:SESSIONS + PICK_DRAWS],
            "defaults": sorted(SAFE_DEFAULTS),
            "hostile_flags": HOSTILE_FLAGS, "hostile_env": HOSTILE_ENV, "settle": settle,
            "fonts_main": list(fonts_main or ())}
    server = Server(corpus, names=names or run_names(seed=FIXED_KEY), shape=shape)
    quiet = {"lists_version": _lists_version(repo), "last_lists_update": 4102444800,
             "last_fast_update": 4102444800, "chrome_checked": 4102444800, "app_updates": "off",
             "auto_update": False, "newtab_bg": "", "newtab_bg_118": True, "app_updates_1113": True,
             "site_opts": dict({p["host"]: {"https": False} for p in corpus["pages"]},
                               **{h: {"https": False} for h in server.sites})}
    dirs = server.names["dirs"]
    raw = {}
    tmp = tempfile.mkdtemp() if keep is None else str(keep)
    server.ca = server.https(Path(tmp) / ("%s-t" % dirs[0]))
    try:
        if server.ca is None and set(sections) & {"fingerprint", "security"}:
            raw["tls"] = {"errors": [{"section": "fingerprint", "error": "the run's sites could not be served over "
                                                                        "https (openssl): not secure contexts"}]}
        measured = [s for s in sections if s != "network"]
        if measured:
            raw["measure"] = run_browser(repo, "measure", plan, quiet, server, Path(tmp) / dirs[0], timeout=420)
            raw["measure"]["proxy_hosts"] = server.take()
            with server.lock:
                raw["measure"]["headers"] = server.headers
                server.headers = {}
        if "fingerprint" in sections:
            # the same page on another real machine (time zone, language, screen): a fixed disguise
            # must not follow the real one (the "env." marks); one session, the first key
            raw["env2"] = run_browser(repo, "measure", dict(plan, sections=["fingerprint"], keys=keys[:1], pick_keys=[],
                                                            sites={}, again=False),
                                      quiet,
                                      server, Path(tmp) / (dirs[0] + "e"), timeout=300, other_machine=True)
            raw["env2"]["proxy_hosts"] = server.take()
            with server.lock:
                server.headers = {}
        if "network" in sections:
            # a fresh profile, every default as a new user has it: what the browser contacts by itself;
            # twice, two starts, each with its own random noise key ("natural" in observations)
            for part, where in (("network", dirs[1]), ("network2", dirs[2])):
                raw[part] = run_browser(repo, "network", dict(plan, lists={}), None, server, Path(tmp) / where,
                                        timeout=180)
                raw[part]["proxy_hosts"] = server.take()
    finally:
        server.close()
        if keep is None:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    snap = {"format": FORMAT, "tool": "tools/no-regression.py",
            "repo": {"commit": _git(repo, "rev-parse", "HEAD"), "version": _version(repo)},
            "levels": list(levels), "sections": list(sections),
            "corpus": {"requests": len(corpus["requests"]),
                       "elements": sum(len(p["elements"]) for p in corpus["pages"]),
                       "cosmetic_urls": len(corpus["cosmetic_urls"]), "scriptlet_hosts": len(corpus["scriptlet_hosts"]),
                       "lists": len(corpus["lists"])},
            "seconds": round(time.monotonic() - t0, 1)}
    snap["errors"], snap["observations"] = observations(raw, levels, sections, corpus)
    # the samples are in the observations as the noise's sizes and references: not kept twice
    for part in ("measure", "env2"):
        for here in ((raw.get(part) or {}).get("levels") or {}).values():
            for p in [here.get("probe"), here.get("probe_again")] + list(here.get("probe_sessions") or []):
                for k in SAMPLES - {"third_frame"}:
                    (p or {}).pop(k, None)
                if isinstance((p or {}).get("third_frame"), list):
                    p["third_frame"] = p["third_frame"][:2]
            here.pop("probe_session2", None)
    # the digest of each filter list's data the requests were measured with (evidence for a request
    # newly let through: the list data that decides it changed)
    snap["list_data"] = (raw.get("measure") or {}).get("list_data")
    snap["raw"] = raw
    return snap


def _change(repo, since):
    """git's diff of the checkout's HEAD from where it left `since` (their merge base: what this
    change itself brings, not what main gained since); None when git cannot give it."""
    if not since:
        return None
    try:
        base = subprocess.run(["git", "-C", str(repo), "merge-base", since, "HEAD"], capture_output=True, text=True,
                              timeout=60)
        if base.returncode != 0 or not base.stdout.strip():
            return None
        proc = subprocess.run(["git", "-C", str(repo), "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                               base.stdout.strip(), "HEAD"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _pytest_once(repo, test, timeout=600):
    """pytest's exit code for one test of the checkout `repo` (1: it failed, 0: it passed), or None."""
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN")}
    try:
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                               test], cwd=str(repo), env=env, capture_output=True, timeout=timeout).returncode
    except (OSError, subprocess.SubprocessError):
        return None


def confirm(tests, base_repo, cand_repo, runs=None, run=_pytest_once):
    """{test: {"main": [exit codes], "candidate": [...]}} and the tests confirmed: failing on main in
    each of `runs` runs (main's checkout) and passing here in each of `runs` runs. A test that fails
    by chance once is no evidence."""
    record, confirmed, runs = {}, set(), runs or CONFIRM_RUNS
    for t in tests:
        m, c = [], []
        for _ in range(runs):
            m.append(run(base_repo, t))
            if m[-1] != 1:
                break
        if len(m) == runs and all(x == 1 for x in m):
            for _ in range(runs):
                c.append(run(cand_repo, t))
                if c[-1] != 0:
                    break
            if len(c) == runs and all(x == 0 for x in c):
                confirmed.add(t)
        record[t] = {"main": m, "candidate": c}
    return record, confirmed


def _version(repo):
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (Path(repo) / "ike" / "__init__.py").read_text("utf-8", "replace"))
    return m.group(1) if m else ""


def _flat(prefix, value, out, rule):
    if isinstance(value, dict):
        for k, v in value.items():
            _flat("%s.%s" % (prefix, k) if prefix else str(k), v, out, rule)
    else:
        out[prefix] = {"rule": rule, "value": value}


def _feature_set(flags, which):
    out = set()
    for f in flags:
        if f.startswith(which + "="):
            out.update(x.strip() for x in f.split("=", 1)[1].strip("'\"").split(",") if x.strip())
    return out


def _env_marks(lv, probe, flats, off, env2):
    """{value: True | False}: for each value whose real one (Off) changed in the other real environment,
    whether what this level shows stayed the same there (False: it follows the real machine). Only
    parts fixed in every session are asked (a value drawn per session is judged otherwise); a value
    that equals the real one here and stays when the real one changes is a fixed disguise too."""
    levels2 = (env2.get("levels") or {})
    p2, off2 = (levels2.get(lv) or {}).get("probe") or {}, (levels2.get("off") or {}).get("probe") or {}
    if not p2 or not off2:
        return {}
    one, two, real1, real2 = {}, {}, {}, {}
    for src, out in ((probe, one), (p2, two), (off, real1), (off2, real2)):
        _flat("", {k: v for k, v in src.items() if k not in SAMPLES}, out, "exact")
    marks = {}
    for k, o in one.items():
        if not FP_JUDGED.match(k) or k not in two or k not in real1 or k not in real2:
            continue
        parts = _parts(o["value"], k)
        sessions = [_parts(f[k]["value"], k) for f in flats if k in f]
        here2, r1, r2 = _parts(two[k]["value"], k), _parts(real1[k]["value"], k), _parts(real2[k]["value"], k)
        held = None
        for path, v in parts.items():
            if any(s.get(path, MISSING) != v for s in sessions):
                continue                    # drawn per session: not a fixed disguise (a pick the same in every
                #                             session is one: the cores at Strict, N7 of the fourth review)
            if r1.get(path, MISSING) == r2.get(path, MISSING):
                continue                    # the environment did not change the real one
            held = (held is not False) and here2.get(path, MISSING) == v
        if held is not None:
            marks[k] = held
    return marks


def _again_marks(lv, here, fp, errors):
    """N2 of the fourth review: the first key once more on the probe page, in another load: each judged
    value reads as in the first session ("again.<value>"; a noise drawn anew at every load fails)."""
    again = here.get("probe_again")
    if "probe_again" not in here:
        return {}
    if not isinstance(again, dict):
        errors.append({"section": "fingerprint", "error": "the probe page gave no result at %s with the first "
                                                          "key again" % lv})
        return {}
    fa, out = {}, {}
    _flat("", {k: v for k, v in again.items() if k not in SAMPLES}, fa, "exact")
    for k, o in fp.items():
        if FP_JUDGED.match(k) and k in fa:
            out["again.%s" % k] = {"rule": "safer-true", "value": fa[k]["value"] == o["value"]}
    return out


def _site_marks(sites, off_sites):
    """N1 of the fourth review: the page of the sites on the run's hosts. For each read: other sites
    differ ("sites.differ."; under a public suffix of two labels too), two hosts of one site agree
    ("sites.agree."), every host differs from the real value ("sites.noised."). None where a host gave
    nothing (it cannot be judged)."""
    if not isinstance(sites, dict):
        return {}
    real = (off_sites or {}).get("a") if isinstance(off_sites, dict) else None
    out = {}
    for v in SITE_READS:
        vals = {n: (s.get(v) if isinstance(s, dict) else None) for n, s in sites.items()}
        ok = len(vals) >= 6 and all(x is not None and not (isinstance(x, str) and FAILED.match(x))
                                    for x in vals.values())
        others = [vals.get(n) for n in ("a", "b", "c", "d", "e")]
        out["sites.differ.%s" % v] = {"rule": "safer-true", "value": len({_id(x) for x in others}) == len(others)
                                      if ok else None}
        out["sites.agree.%s" % v] = {"rule": "safer-true", "value": vals.get("a") == vals.get("a2") if ok else None}
        r = real.get(v) if isinstance(real, dict) else None
        out["sites.noised.%s" % v] = {"rule": "safer-true", "value": all(x != r for x in vals.values())
                                      if ok and r is not None else None}
    return out


def _frame_agrees(probes):
    """True when the same-origin frame's canvas hash is the page's in every session read."""
    read = 0
    for p in probes:
        if not isinstance(p, dict):
            continue
        f, c = p.get("frame"), p.get("canvas")
        fh = f[4][0] if isinstance(f, list) and len(f) > 4 and isinstance(f[4], list) and f[4] else None
        ch = c[0] if isinstance(c, list) and c else None
        if fh is None or ch is None:
            return None
        if fh != ch:
            return False
        read += 1
    return True if read else None


def observations(raw, levels, sections, corpus):
    """(errors, {key: {"rule", "value"}}) from what the browser recorded."""
    errors, obs = [], {}
    for part in ("measure", "env2", "network", "network2", "tls"):
        if part in raw and (raw[part] or {}).get("python_hosts", None) is None and "errors" in (raw[part] or {}) \
                and not (raw[part] or {}).get("errors"):
            # the audit hook that records I.K.E.'s own connections did not report: not measured
            errors.append({"section": "network", "error": "the hosts I.K.E.'s own code contacted were not "
                                                          "recorded (%s)" % part})
        for e in (raw.get(part) or {}).get("errors") or ():
            errors.append({"section": e.get("section", part), "error": e.get("error", "")[-1500:]})
    m = raw.get("measure") or {}
    if m and not (m.get("engine") or {}).get("built") and set(sections) & {"requests", "cosmetic", "scriptlets"}:
        errors.append({"section": "requests", "error": "the AdBlock engine was not built from the fixture lists"})
    req_ids = [q["id"] for q in corpus["requests"]]
    for lv in levels:
        here = (m.get("levels") or {}).get(lv) or {}
        if "requests" in sections:
            got = here.get("requests") or {}
            for rid in req_ids:
                r = got.get(rid)
                obs["requests/%s/%s" % (lv, rid)] = {"rule": "block", "value": r["action"] if r else None}
                if isinstance(m.get("list_verdicts"), dict) and rid in m["list_verdicts"]:
                    obs["requests/%s/%s" % (lv, rid)]["lists"] = m["list_verdicts"][rid]
                for h, v in sorted(((r or {}).get("headers") or {}).items()):
                    obs["request-headers/%s/%s/%s" % (lv, rid, h)] = {"rule": "exact", "value": v}
        if "cosmetic" in sections:
            for pg in corpus["pages"]:
                res = ((here.get("pages") or {}).get(pg["id"]) or {}).get("result") or {}
                for e in pg["elements"]:
                    obs["cosmetic/%s/%s/%s" % (lv, pg["id"], e["key"])] = {
                        "rule": "hidden", "value": (res.get("elements") or {}).get(e["key"])}
                for k in sorted(pg.get("probes") or {}):
                    obs["page-scriptlets/%s/%s/%s" % (lv, pg["id"], k)] = {
                        "rule": "exact", "value": (res.get("probes") or {}).get(k)}
        if "fingerprint" in sections:
            probe = here.get("probe")
            others = here.get("probe_sessions")
            if others is None and "probe_session2" in here:
                others = [here.get("probe_session2")]           # a hook of an older copy
            others = others or []
            if probe is None:
                errors.append({"section": "fingerprint", "error": "the probe page gave no result at %s" % lv})
            else:
                for n, p in enumerate(others, 2):
                    if p is None:
                        errors.append({"section": "fingerprint", "error": "the probe page gave no result at %s in "
                                                                          "session %d" % (lv, n)})
                fp, flats, picks = {}, [], []
                for n, p in enumerate(here.get("picks") or (), 1):
                    if p is None:
                        errors.append({"section": "fingerprint", "error": "the page of the drawn values gave no "
                                                                          "result at %s (draw %d)" % (lv, n)})
                    f = {}
                    _flat("", p or {}, f, "exact")
                    picks.append({k: v["value"] for k, v in f.items()})
                _flat("", {k: v for k, v in probe.items() if k not in SAMPLES}, fp, "exact")
                for p in others:
                    f = {}
                    _flat("", {k: v for k, v in (p or {}).items() if k not in SAMPLES}, f, "exact")
                    flats.append(f)
                off = ((m.get("levels") or {}).get("off") or {}).get("probe") or {}
                for k, o in fp.items():
                    if flats and k in flats[0]:
                        o["session2"] = flats[0][k]["value"]
                    if len(flats) > 1 and all(k in f for f in flats):
                        o["sessions"] = [o["value"]] + [f[k]["value"] for f in flats]
                        if k in PICK_DRAWN and picks:
                            o["sessions"] += [p.get(k, "error not read") for p in picks]
                    if lv != "off" and FP_JUDGED.match(k):
                        o["rule"] = "fingerprint"
                    if MARKS.search(k):
                        o["rule"] = "safer-true"
                    if lv != "off" and k in NOISE and off:
                        o["noise"] = _noise(k, [probe] + [p for p in others if p is not None], off)
                    if lv == "off" and k in NOISE:
                        o["samples_ref"] = _samples_ref(k, probe)
                if lv != "off" and off:
                    for k in NOISED:
                        fp["%s.noised" % k] = {"rule": "safer-true", "value": probe.get(k) != off.get(k)}
                # the same canvas and sound in another site's frame: different where the noise is per site
                tf, top = probe.get("third_frame"), probe.get("canvas")
                read = isinstance(tf, list) and len(tf) >= 2
                fp["site.canvas"] = {"rule": "safer-true", "value": tf[0] != top[0]
                                     if read and isinstance(top, list) and top else None}
                fp["site.audio"] = {"rule": "safer-true", "value": tf[1] != probe.get("audio") if read else None}
                # another real environment (time zone, language, screen): a fixed disguise must not follow it
                if lv != "off" and raw.get("env2"):
                    for k, v in _env_marks(lv, probe, flats, off, raw["env2"]).items():
                        fp["env.%s" % k] = {"rule": "safer-true", "value": v}
                if lv != "off":
                    fp.update(_again_marks(lv, here, fp, errors))
                    fp.update(_site_marks(here.get("sites"), ((m.get("levels") or {}).get("off") or {}).get("sites")))
                    # a frame shares its page's noise: its canvas is the page's in every session
                    fp["frame.agrees.canvas"] = {"rule": "safer-true", "value": _frame_agrees([probe] + others)}
                if lv in ("strict", "maximum") and m.get("fonts_findable") is not None:
                    found = here.get("fonts_found")
                    for where, name in (("page", "fonts_found"), ("frame", "fonts_found_frame")):
                        got = found.get(where) if isinstance(found, dict) else None
                        fp[name] = {"rule": "masked-fonts", "value": sorted(
                            {str(x).lower() for x in got} - FONTS_KEPT) if isinstance(got, list) else None}
                for k, v in fp.items():
                    obs["fingerprint/%s/%s" % (lv, k)] = v
        if "security" in sections:
            for which in ("page_settings", "profile_settings"):
                for k, v in sorted((here.get(which) or {}).items()):
                    obs["webengine/%s/%s/%s" % (lv, which.split("_")[0], k)] = {"rule": "setting", "value": v}
            prof = here.get("profile") or {}
            for k, v in sorted(prof.items()):
                if k == "scripts":
                    obs["scripts/%s" % lv] = {"rule": "kept", "value": v}
                elif k == "fonts_masked":
                    continue                # with the fonts' digest below
                elif k == "fingerprint_config":
                    fc = {}
                    _flat("", v if isinstance(v, dict) else {"config": v}, fc, "exact")
                    for kk, vv in fc.items():
                        if kk == "fonts" and "fonts_masked" in prof:
                            # judged by what protects (_judge_fonts): every font a page can find masked
                            vv = dict(vv, rule="fonts", masked=prof["fonts_masked"],
                                      findable=m.get("fonts_findable"))
                            if prof["fonts_masked"] is None:
                                vv["listed"] = m.get("fonts_list")
                        obs["fingerprint-config/%s/%s" % (lv, kk)] = vv
                else:
                    obs["profile/%s/%s" % (lv, k)] = {"rule": "exact", "value": v}
            if "probe" in here and here["probe"] is not None:
                for k, v in sorted((here["probe"].get("permissions") or {}).items()):
                    obs["permissions/%s/%s" % (lv, k)] = {"rule": "permission", "value": v}
                obs["ike-scheme/%s/from-a-page" % lv] = {"rule": "exact", "value": here["probe"].get("ike_scheme")}
            heads = (m.get("headers") or {}).get(lv) or {}
            for which in ("page", "third-party"):
                for k, v in sorted((heads.get(which) or {}).items()):
                    obs["headers/%s/%s/%s" % (lv, which, k)] = {"rule": "exact", "value": v}
                if which not in heads:
                    errors.append({"section": "security", "error": "no %s request reached the server at %s"
                                   % (which, lv)})
    if "cosmetic" in sections:
        for url, v in sorted((m.get("cosmetic_rules") or {}).items()):
            for k in ("hide", "generic", "styles"):
                obs["cosmetic-rules/%s/%s" % (url, k)] = {"rule": "kept", "value": v.get(k) or []}
            obs["cosmetic-rules/%s/generichide" % url] = {"rule": "safer-false", "value": v.get("generichide")}
        for url in corpus["cosmetic_urls"]:
            obs.setdefault("cosmetic-rules/%s/hide" % url, {"rule": "kept", "value": None})
    if "scriptlets" in sections:
        for h in corpus["scriptlet_hosts"]:
            rules = (m.get("scriptlets") or {}).get(h)
            obs["scriptlets/%s" % h] = {"rule": "kept", "value": None if rules is None else
                                        sorted(json.dumps(r, ensure_ascii=False) for r in rules)}
        obs["video-hosts"] = {"rule": "kept", "value": sorted(m.get("video_hosts") or [])}
    if "security" in sections:
        sec = m.get("security") or {}
        flags = sec.get("flags") or []
        given = set(INPUT_FLAGS) | {f for f in flags if f.startswith("--proxy-server=")}
        mine = [f for f in flags if f not in given and not f.startswith(("--enable-features=", "--disable-features="))]
        obs["switches/added"] = {"rule": "switches", "value": sorted(mine)}
        obs["switches/enabled-features"] = {"rule": "kept", "value": sorted(_feature_set(flags, "--enable-features"))}
        obs["switches/disabled-features"] = {"rule": "exact-set",
                                             "value": sorted(_feature_set(flags, "--disable-features"))}
        hostile = sec.get("hostile_result")
        if hostile is not None:
            kept = [f for f in hostile if f in HOSTILE_FLAGS or f.split("=", 1)[0] in
                    {h.split("=", 1)[0] for h in HOSTILE_FLAGS if not h.startswith(("--enable-features",
                                                                                     "--disable-features"))}]
            obs["switches/hostile-kept"] = {"rule": "no-new", "value": sorted(kept)}
            obs["switches/hostile-disabled-features"] = {"rule": "no-new",
                                                        "value": sorted(_feature_set(hostile, "--disable-features"))}
            obs["switches/hostile-enabled-features"] = {"rule": "kept",
                                                       "value": sorted(_feature_set(hostile, "--enable-features"))}
            obs["switches/hostile-env-left"] = {"rule": "no-new", "value": sec.get("hostile_env_left") or []}
        else:
            obs["switches/hostile-kept"] = {"rule": "no-new", "value": None}
        for k in ("sandbox_off", "site_isolated"):
            obs["engine/%s" % k] = {"rule": "safer-false" if k == "sandbox_off" else "safer-true", "value": sec.get(k)}
        for name, v in sorted((sec.get("lists") or {}).items()):
            weaker_if_new = name.startswith("config.") or name == "app.NOTICE_SWITCHES"
            obs["lists/%s" % name] = {"rule": "no-new" if weaker_if_new else "kept", "value": v}
        for k, v in sorted((sec.get("defaults") or {}).items()):
            how = SAFE_DEFAULTS.get(k, "same")
            rule = {True: "safer-true", False: "safer-false", "level": "level", "kept": "kept",
                    "same": "exact"}[how]
            if rule == "kept" and isinstance(v, list):
                v = sorted(str(x) for x in v)
            obs["defaults/%s" % k] = {"rule": rule, "value": v}
        obs["defaults/filter_lists"] = {"rule": "kept", "value": sec.get("default_lists")}
        obs["ike-scheme/flags"] = {"rule": "exact", "value": sec.get("ike_scheme_flags")}
    if "network" in sections:
        hosts = set()
        for part in ("network", "network2"):
            n = raw.get(part) or {}
            hosts |= set(n.get("proxy_hosts") or []) | set(n.get("python_hosts") or [])
            if part in raw and not n.get("probe_done"):
                errors.append({"section": "network", "error": "the probe page did not finish in the fresh profile"})
        obs["network/fresh-profile"] = {"rule": "no-new", "value": sorted(hosts)}
        if "fingerprint" in sections:
            # two starts with their own random noise keys (no key of the tool's): what the protection
            # gives differs from one start to the next and from Off
            n1, n2 = ((raw.get(p) or {}).get("probe") or {} for p in ("network", "network2"))
            off = (((m.get("levels") or {}).get("off") or {}).get("probe") or {}) if "off" in levels else {}
            for k in ("canvas", "canvas_blob", "audio"):
                a, b = n1.get(k), n2.get(k)
                known = a is not None and b is not None
                obs["fingerprint/natural/%s.differs" % k] = {"rule": "safer-true", "value": a != b if known else None}
                obs["fingerprint/natural/%s.noised" % k] = {
                    "rule": "safer-true", "value": a != off.get(k) and b != off.get(k)
                    if known and off.get(k) is not None else None}
    if m:
        hosts = set(m.get("proxy_hosts") or []) | set(m.get("python_hosts") or [])
        for e in ("env2",):
            hosts |= set((raw.get(e) or {}).get("proxy_hosts") or []) | set((raw.get(e) or {}).get("python_hosts") or [])
        obs["network/while-measuring"] = {"rule": "no-new", "value": sorted(hosts)}
    return errors, obs


# --- the comparison -----------------------------------------------------------------------------
def _section(key):
    head = key.split("/", 1)[0]
    return {"requests": "blocking", "request-headers": "security", "cosmetic": "blocking",
            "cosmetic-rules": "blocking", "page-scriptlets": "blocking", "scriptlets": "blocking",
            "video-hosts": "blocking", "fingerprint": "fingerprinting", "fingerprint-config": "fingerprinting",
            "network": "network"}.get(head, "security")


def _judge(rule, base, cand, key=""):
    """(kind, detail): kind one of "same", "stricter", "changed", "worse" (weaker by the rule) or
    "unjudged" (a change the rule cannot judge: worse too, unless evidence accepts it)."""
    if base == cand:
        return "same", ""
    if cand is None and (rule != "no-new" or base is not None):
        return "unjudged", "not measured on the candidate"
    if rule == "block":
        if base is None:
            return "changed", "not measured on main"
        if base != "allow" and cand == "allow":
            return "worse", "%s on main, allowed here" % base
        if base == "allow":
            return "stricter", "allowed on main, %s here" % cand
        if base in STOPPED and cand in STOPPED:
            return "changed", "%s on main, %s here (stopped either way)" % (base, cand)
        return "worse", "%s on main, %s here" % (base, cand)
    if rule == "hidden":
        hid = ("hidden", "removed")
        if base in hid and cand not in hid:
            return "worse", "hidden on main, %s here" % cand
        if base not in hid and cand in hid:
            return "stricter", "%s on main, hidden here" % base
        return "changed", "%s on main, %s here" % (base, cand)
    if rule in ("kept", "no-new", "exact-set", "switches"):
        b, c = set(base or []), set(cand or [])
        lost, new = sorted(b - c), sorted(c - b)
        if rule == "kept":
            if lost:
                return "worse", "lost here: %s" % ", ".join(map(str, lost[:8]))
            return "stricter", "new here: %s" % ", ".join(map(str, new[:8]))
        if rule == "no-new":
            if new:
                return "worse", "new here: %s" % ", ".join(map(str, new[:8]))
            return "stricter", "no longer here: %s" % ", ".join(map(str, lost[:8]))
        if rule == "switches":
            weak = [f for f in new if WEAK_SWITCH.match(f)]
            if lost or weak:
                return "worse", "; ".join(x for x in ("lost here: %s" % ", ".join(lost[:8]) if lost else "",
                                                      "added here: %s" % ", ".join(weak[:8]) if weak else "") if x)
            return "changed", "added here: %s" % ", ".join(new[:8])
        return "worse", "; ".join(x for x in ("lost here: %s" % ", ".join(lost[:8]) if lost else "",
                                              "new here: %s" % ", ".join(new[:8]) if new else "") if x)
    if rule == "masked-fonts":
        # the fonts a page can find on this computer that the protected page (or its frame) still finds
        # (N4 of the fourth review): one more than on main is worse
        if not isinstance(cand, list):
            return "unjudged", "the fonts a page finds could not be measured here (%s)" % _short(cand, 60)
        extra = sorted(set(cand) - set(base or []))
        if extra or not isinstance(base, list):
            return "worse", "a font a page can find on this computer is not masked here: %s" % ", ".join(
                extra[:8] or cand[:8])
        return "stricter", "masked here, found on main: %s" % ", ".join(sorted(set(base) - set(cand))[:8])
    if rule == "safer-true":
        return ("worse", "%s on main, %s here" % (base, cand)) if base is True else \
            ("stricter", "%s on main, %s here" % (base, cand)) if cand is True else ("worse", "%r -> %r" % (base, cand))
    if rule == "safer-false":
        return ("worse", "%s on main, %s here" % (base, cand)) if base is False else \
            ("stricter", "%s on main, %s here" % (base, cand)) if cand is False else ("worse", "%r -> %r" % (base, cand))
    if rule == "level":
        try:
            return ("stricter" if LEVELS.index(cand) > LEVELS.index(base) else "worse"), \
                "%s on main, %s here" % (base, cand)
        except ValueError:
            return "worse", "%r on main, %r here" % (base, cand)
    if rule == "permission":
        order = {"denied": 0, "prompt": 1, "granted": 2}
        if base in order and cand in order and order[cand] < order[base]:
            return "stricter", "%s on main, %s here" % (base, cand)
        return "worse", "%s on main, %s here" % (base, cand)
    if rule == "setting":
        safer = SAFER_SETTINGS.get(key.rsplit("/", 1)[-1])
        if safer is not None and cand is safer:
            return "stricter", "%s on main, %s here" % (base, cand)
        return "worse", "%s on main, %s here" % (base, cand)
    return "unjudged", "%s on main, %s here" % (_short(base), _short(cand))


# WebEngine attributes whose safer value is known (anything else: any change is worse)
SAFER_SETTINGS = {
    "JavascriptCanOpenWindows": False, "JavascriptCanAccessClipboard": False, "JavascriptCanPaste": False,
    "LocalContentCanAccessRemoteUrls": False, "LocalContentCanAccessFileUrls": False,
    "AllowRunningInsecureContent": False, "AllowGeolocationOnInsecureOrigins": False,
    "AllowWindowActivationFromJavaScript": False, "HyperlinkAuditingEnabled": False, "DnsPrefetchEnabled": False,
    "WebRTCPublicInterfacesOnly": True, "XSSAuditingEnabled": True, "ScreenCaptureEnabled": False,
    "WebGLEnabled": False, "Accelerated2dCanvasEnabled": None, "PluginsEnabled": False,
    "NavigateOnDropEnabled": False, "ReadingFromCanvasEnabled": False, "ForceDarkMode": None,
}

# --- the fingerprinting values, judged by what protects ------------------------------------------
def _png_bytes(url):
    """The pixels (RGBA or RGB bytes, unfiltered) of a PNG data: address as a canvas gives it; None for
    anything else (another format, depth or interlacing)."""
    import base64
    import struct
    import zlib
    try:
        if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
            return None
        data = base64.b64decode(url.split(",", 1)[1])
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        pos, idat, head = 8, [], None
        while pos + 8 <= len(data):
            n, kind = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + n]
            pos += 12 + n
            if kind == b"IHDR":
                head = struct.unpack(">IIBBBBB", body)
            elif kind == b"IDAT":
                idat.append(body)
            elif kind == b"IEND":
                break
        w, h, depth, ctype, _c, _f, interlaced = head
        bpp = {6: 4, 2: 3}.get(ctype)
        if depth != 8 or interlaced or not bpp:
            return None
        raw, stride, out = zlib.decompress(b"".join(idat)), w * bpp, bytearray()
        prev = bytearray(stride)
        for y in range(h):
            f = raw[y * (stride + 1)]
            line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                if f == 1:
                    line[i] = (line[i] + a) & 255
                elif f == 2:
                    line[i] = (line[i] + b) & 255
                elif f == 3:
                    line[i] = (line[i] + (a + b) // 2) & 255
                elif f == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
                elif f != 0:
                    return None
            out += line
            prev = line
        return bytes(out)
    except Exception:
        return None


def _decoded(kind, value):
    import base64
    try:
        if kind == "png":
            return _png_bytes(value)
        if kind in ("pixels", "stripes"):
            return base64.b64decode(value) if isinstance(value, str) else None
        if kind == "site":
            return base64.b64decode(value[2]) if isinstance(value, list) and len(value) > 2 and \
                isinstance(value[2], str) else None
        if isinstance(value, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value):
            return [float(x) for x in value]
    except (TypeError, ValueError):
        pass
    return None


def _measure(kind, got, real):
    """(size, share changed, elements) of one session's noise against Off's real values; None if not
    measurable. stripes: the rows of a picture of flat stripes (16 pixels wide) changed at all."""
    if got is None or real is None or len(got) != len(real) or not len(got):
        return None
    if kind == "stripes":
        rows = [got[i:i + 64] != real[i:i + 64] for i in range(0, len(got), 64)]
        return sum(rows) / len(rows), sum(rows) / len(rows), len(rows)
    share = sum(1 for a, b in zip(got, real) if a != b) / len(got)
    if kind in ("png", "pixels"):
        return sum(abs(a - b) for a, b in zip(got, real)) / len(got), share, len(got)
    pairs = [(a, b) for a, b in zip(got, real) if b != 0.0]
    if not pairs:
        return None
    ratios = [a / b for a, b in pairs]
    if kind == "widths":
        return sum(abs(r - 1.0) for r in ratios) / len(ratios), share, len(got)
    # the audio: how much the factors differ from one sample to the next (around their median); a
    # constant gain changes every sample and has none
    mid = sorted(ratios)[len(ratios) // 2]
    return sum(abs(r - mid) for r in ratios) / len(ratios), share, len(got)


def _between(kind, a, b):
    """(share of elements that differ between two sessions' readings, elements); None if not measurable."""
    if a is None or b is None or len(a) != len(b) or not len(a):
        return None
    if kind == "stripes":
        rows = [a[i:i + 64] != b[i:i + 64] for i in range(0, len(a), 64)]
        return sum(rows) / len(rows), len(rows)
    return sum(1 for x, y in zip(a, b) if x != y) / len(a), len(a)


def _sample(p, field, sub):
    v = (p or {}).get(field)
    return (v.get(sub) if isinstance(v, dict) else None) if sub else v


def _noise(key, probes, off):
    """The size of the noise of a value (NOISE), from every session's readings: for each kind
    ("png", "pixels", "widths", "stripes", "dispersion" for the audio) the size against Off's real
    values and the share of elements changed, and "<kind>_between": the share of elements that differ
    from one session to the next (a noise drawn the same in every session, or at the same places,
    has less); "site": the share of the known picture that differs in another site's frame. Each
    measure "m" with "m_k", the number of elements it rests on (for its tolerance). None where a
    measure cannot be read."""
    out = {}
    for kind, field, sub in NOISE[key]:
        if kind == "site":
            got = [_between("pixels", _decoded("pixels", (p or {}).get("canvas_pixels")), _decoded("site", p.get(field)))
                   for p in probes]
            if got and all(g is not None for g in got):
                out["site"] = float("%.6g" % (sum(g[0] for g in got) / len(got)))
                out["site_k"] = max(1, round(out["site"] * sum(g[1] for g in got)))
            else:
                out["site"] = None
            continue
        real = _decoded(kind, _sample(off, field, sub))
        reads = [_decoded(kind, _sample(p, field, sub)) for p in probes]
        got = [_measure(kind, r, real) for r in reads]
        name = "dispersion" if kind == "samples" else kind
        share = "share" if kind == "samples" else kind + "_share"
        between = "between" if kind == "samples" else kind + "_between"
        if got and all(g is not None for g in got):
            count = sum(g[2] for g in got)
            out[name] = float("%.6g" % (sum(g[0] for g in got) / len(got)))
            out[share] = float("%.6g" % (sum(g[1] for g in got) / len(got)))
            out[name + "_k"] = out[share + "_k"] = max(1, round(out[share] * count))
            if kind == "widths":
                # the session with the fewest widths changed: a single width is judged against how
                # often chance leaves it real (_real_chance), so a session with no noise is caught
                # here; its elements for the tolerance: the share's spread in one session,
                # sqrt(p (1 - p) / n), as 1 / sqrt(k)
                least = min(got, key=lambda g: g[1])
                p, n = least[1], max(1, least[2])
                out["widths_least"] = float("%.6g" % p)
                out["widths_least_k"] = max(1, round(p * n / max(1 - p, 1 / n)))
        else:
            out[name] = out[share] = None
            if kind == "widths":
                out["widths_least"] = None
        pairs = [_between(kind, a, b) for a, b in zip(reads, reads[1:])]
        if pairs and all(x is not None for x in pairs):
            out[between] = float("%.6g" % (sum(x[0] for x in pairs) / len(pairs)))
            out[between + "_k"] = max(1, round(out[between] * sum(x[1] for x in pairs)))
        elif len(reads) > 1:
            out[between] = None
    return out


def _samples_ref(key, off):
    """A digest of Off's real values a value's noise is measured against: the two sides' noise can be
    compared only against the same real values."""
    h = hashlib.sha256()
    for kind, field, sub in NOISE[key]:
        if kind == "site":
            continue
        d = _decoded(kind, _sample(off, field, sub))
        h.update(json.dumps(list(d) if d is not None else None).encode())
    return h.hexdigest()[:16]


def _tolerance(m, nb):
    """How much smaller a noise measure may be than main's before it is worse: NOISE_Z times the
    chance spread of the difference between two independent draws of the same noise (another key, or
    a rewrite of the same strength), Z * sqrt(2) * cv / sqrt(k), k the elements the measure rests on
    (main's "m_k"), cv the spread of one element (1 for counts and +-1 changes, 0.6 for the uniform
    magnitudes of widths and of the audio's factors); never below NOISE_TOLERANCE, never above
    TOLERANCE_CAP (more readings, not a looser rule, where it would be). A false "worse" from chance:
    3e-5 per measure; the floor is applied with no tolerance."""
    k = nb.get(m + "_k")
    if not isinstance(k, (int, float)) or isinstance(k, bool) or k <= 0:
        return NOISE_TOLERANCE
    cv = 0.6 if m in ("widths", "dispersion") else 1.0
    return min(TOLERANCE_CAP, max(NOISE_TOLERANCE, NOISE_Z * 2 ** 0.5 * cv / k ** 0.5))


def load_floors(path=None):
    """{value: {measure: the least noise size}} kept by a person (NOISE_FLOORS): the noise is judged
    against the larger of main's (less the tolerance of chance) and this floor (with no tolerance), so
    merges cannot lower it step by step. None when the file cannot be read, and when any floor is not a
    number above 0 (a floor written as text was dropped before: N6 of the fourth review): an error,
    never no floor."""
    try:
        data = json.loads(Path(path or NOISE_FLOORS).read_text("utf-8"))
        floors = data["floors"]
        out = {}
        for k, v in floors.items():
            if not isinstance(v, dict):
                return None
            for m, x in v.items():
                if not isinstance(x, (int, float)) or isinstance(x, bool) or not x > 0:
                    return None
            out[k] = {m: float(x) for m, x in v.items()}
        return out
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


# a floor under this share of what main measures is stale (N6 of the fourth review: the audio's stayed at
# half of the noise before #148, a tenth of the noise after it): the report says so
FLOOR_STALE = 0.6


def stale_floors(snap, floors):
    """The floors far under what main measures (FLOOR_STALE): ["value measure: floor F, main M"]."""
    out = []
    for key, o in sorted((snap.get("observations") or {}).items()):
        name = key.split("/", 2)[-1]
        noise = o.get("noise") if isinstance(o, dict) else None
        if not key.startswith("fingerprint/") or not isinstance(noise, dict) or name not in (floors or {}):
            continue
        for m, f in sorted(floors[name].items()):
            v = noise.get(m)
            if _number(v) and v > 0 and f < FLOOR_STALE * v:
                out.append("%s %s: floor %g, main %g" % (key.split("/", 1)[1], m, f, v))
    return out


def _judge_noise(name, nb, nc, floors):
    """The noise sizes of one value, main's against the candidate's: (kind, detail), or None when main
    has none. A measure below main's less the tolerance of chance (_tolerance), or below the floor
    (no tolerance), is worse; one main has and the candidate not is unjudged."""
    if not isinstance(nb, dict):
        return None
    nc = nc if isinstance(nc, dict) else {}
    floor = (floors or {}).get(name) or {}
    smaller, larger, unread, kept = [], [], [], []
    for m, vb in sorted(nb.items()):
        if m.endswith("_k") or not isinstance(vb, (int, float)) or isinstance(vb, bool) or vb <= 0:
            continue
        vc = nc.get(m)
        need = max(vb * (1 - _tolerance(m, nb)), floor.get(m, 0.0))
        if not isinstance(vc, (int, float)) or isinstance(vc, bool):
            unread.append(m)
        elif vc < need:
            smaller.append("%s %g on main%s, %g here" % (m, vb, " (floor %g)" % floor[m] if m in floor else "", vc))
        elif vc > vb * (1 + NOISE_TOLERANCE):
            larger.append("%s %g on main, %g here (x%.3g)" % (m, vb, vc, vc / vb))
        else:
            kept.append(m)
    if smaller:
        return "worse", "the noise is smaller: " + "; ".join(smaller)
    if unread:
        return "unjudged", "the size of the noise could not be measured here: " + ", ".join(unread)
    if larger:
        return "stricter", "still protected, the noise larger: " + "; ".join(larger)
    if kept:
        return "changed", "still protected, the noise as large (%s)" % ", ".join(kept)
    return None


MISSING = object()          # a part a snapshot does not have (not the same as a value null)
FAILED = re.compile(r"^(error\b|worker (error|timeout)$|timeout$|e$|e )")   # what the probe writes when a read fails


def _parts(value, name):
    """{path: leaf}: a disguised value judged part by part (a list by its items, a JSON text or a
    mapping by its fields, the media queries one by one), so a part that went back to the real value
    is not hidden by another part that changed. A plain value is its only part, path ""."""
    if name == "media_queries" and isinstance(value, str):
        found = re.findall(r"(\([^()]*\))=(\w+)", value)
        if found:
            value = dict(found)
    elif isinstance(value, str) and value[:1] in "[{":
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, (list, dict)) and value:
        out = {}
        for k, v in (enumerate(value) if isinstance(value, list) else sorted(value.items())):
            for path, leaf in _parts(v, "").items():
                out["[%s]%s" % (k, path)] = leaf
        return out
    return {"": value}


def _names(v):
    return {x.strip() for x in v.split(",") if x.strip()} if isinstance(v, str) else set()


def _far(v, real):
    """How many names a list shows differently from the real one (added or left out)."""
    return len(_names(v) ^ _names(real))


def _number(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _tokens(v):
    return set(re.findall(r"[A-Za-z0-9]+", v))


# The parts of the disguised values by how they are drawn. "noise": a large space (a picture's or a
# sound's hash, random plugin names): two sessions alike, or the real value, by chance is negligible,
# so they must change with the session. "pick": one of a few common values per session (a card's
# name, a list of extensions, a number of cores, a text width with its 61 steps): two sessions
# alike, or a common real value, can be chance; they are judged only on what chance cannot explain.
# Any other part: a fixed disguise or an unknown kind, judged strictly.
FRAMES = ("frame_x", "frame_html", "frame_srcdoc")         # frameRead: canvas, card, extensions, sound, ...
WORKERS = ("worker", "shared_worker", "file_worker")
NOISE_PARTS = {("canvas", "[0]"), ("canvas_blob", ""), ("canvas_offset", ""), ("canvas_flat", ""), ("audio", ""),
               ("webgl.read_pixels", ""), ("navigator.plugins", ""), ("frame", "[4][0]"),
               ("webgl2.read_pixels", ""), ("audio_copy", ""), ("audio_analyser", ""), ("canvas_offscreen", ""),
               ("video_frame", ""), ("shared_worker", "[7]"), ("file_worker", "[7]")} | \
    {(f, p) for f in FRAMES for p in ("[0]", "[3]", "[6]")}
PICK_VALUES = {"webgl.unmasked_renderer", "webgl.unmasked_vendor", "webgl.extensions", "navigator.hardwareConcurrency",
               "fonts_generic", "webgl2.unmasked_renderer", "webgl2.unmasked_vendor", "webgl2.extensions"}
PICK_PARTS = {("canvas", "[2]"), ("frame", "[0]"), ("frame", "[4][2]")} | \
    {(w, p) for w in WORKERS for p in ("[2]", "[5]", "[6]")} | {(f, p) for f in FRAMES for p in ("[1]", "[2]", "[5]")}
# single text widths: their noise has 61 steps and one of them is none, so the real width comes back
# by chance (about 1 in 61 a session); how often is measured on main's 128 (the frame: 64) widths of
# every session (the value's "widths" noise), and the real width here is judged against that
WIDTH_PARTS = {("canvas", "[2]"), ("frame", "[4][2]")}
WIDTH_VALUES = {"fonts_generic"}
# a list disguised by the same rule as another value read in more sessions: how often that rule leaves
# the real list is measured on the other (the worker's WebGL extensions: the page's, 24 draws a level)
LIST_PEERS = {("worker", "[6][1]"): "webgl.extensions", ("shared_worker", "[6][1]"): "webgl.extensions",
              ("file_worker", "[6][1]"): "webgl.extensions", ("frame_x", "[2]"): "webgl.extensions",
              ("frame_html", "[2]"): "webgl.extensions", ("frame_srcdoc", "[2]"): "webgl.extensions"}


def _role(name, path):
    if (name, path) in NOISE_PARTS:
        return "noise"
    if name in PICK_VALUES or any(name == n and path.startswith(p) for n, p in PICK_PARTS):
        return "pick"
    return None


def _id(v):
    return json.dumps(v, sort_keys=True, default=str)


def _chance_alike(main, here):
    """The chance that the candidate's draws, all alike, are so by chance: with main's and the
    candidate's draws from the same distribution (a rewrite of the same noise), the share of the ways
    to choose the candidate's n draws among all m + n that pick only that value (an exact permutation
    test; it assumes nothing of the distribution)."""
    import math
    n, m = len(here), len(main)
    k = sum(1 for x in main if _id(x) == _id(here[0]))
    return math.comb(k + n, n) / math.comb(m + n, n)


def _tail(n, q, r):
    """The chance of r or more of n sessions showing the real value when each does with chance q."""
    import math
    return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(r, n + 1))


def _more_often(rb, nb, rc, nc):
    """The chance that the candidate's sessions hold rc or more of the rb + rc real values of both
    sides' nb + nc sessions, with both drawn alike (an exact permutation test, hypergeometric)."""
    import math
    k, total = rb + rc, nb + nc
    return sum(math.comb(k, i) * math.comb(total - k, nc - i)
               for i in range(rc, min(k, nc) + 1)) / math.comb(total, nc)


def _real_chance(name, path, sb, ob, noise, peer=None):
    """How often a disguise drawn anew shows the real value by chance, per session, as measured on main;
    None where it is not measured (a picture's hash, a card's name: the real value then never comes by
    chance). A text width (WIDTH_PARTS): the share of main's widths of every session left unchanged
    (Laplace's estimate, never 0). A list that only leaves names out (the extensions): for each real
    name main left out in some sessions, the share of main's sessions that showed it, multiplied (the
    names are drawn apart); peer: (main's sessions, Off) of the list disguised by the same rule and
    read in more sessions (LIST_PEERS), measured there instead."""
    if (name, path) in WIDTH_PARTS or name in WIDTH_VALUES:
        n = noise if isinstance(noise, dict) else {}
        share, k = n.get("widths_share"), n.get("widths_share_k")
        if _number(share, k) and share > 0 and k > 0:
            count = max(k, round(k / share))
            return (count - k + 1) / (count + 2)
        return None
    if (not path and name in FP_LISTS or (name, path) in LIST_PARTS) and len(sb) >= 3 and \
            all(isinstance(y, str) for y in sb + [ob]):
        if peer and len(peer[0]) > len(sb) and all(isinstance(y, str) for y in list(peer[0]) + [peer[1]]):
            sb, ob = peer
        real = _names(ob)
        if any(_names(y) - real for y in sb):
            return None                     # it adds names too: how often it adds none is not measured
        q = 1.0
        for x in real:
            shown = sum(1 for y in sb if x in _names(y))
            if shown < len(sb):
                q *= (shown + 1) / (len(sb) + 2)
        return q
    return None


def _count_drop(main, here):
    """Whether a count (names changed from the real list, a distance from the real value) is lower
    here than on main beyond chance: the difference of the sessions' means against COUNT_Z times its
    spread (the pooled variance of both sides' sessions, at least COUNT_VAR_FLOOR)."""
    nb, nc = len(main), len(here)
    if nb < 2 or nc < 2:
        return False
    mb, mc = sum(main) / nb, sum(here) / nc
    pooled = (sum((x - mb) ** 2 for x in main) + sum((x - mc) ** 2 for x in here)) / (nb + nc - 2)
    return mb - mc > COUNT_Z * (max(pooled, COUNT_VAR_FLOOR) * (1.0 / nb + 1.0 / nc)) ** 0.5


def _judge_part(name, path, b, c, common=None, noise=None, peer=None):
    """One part of a disguised value. b = (main's first session, main's sessions, Off on main, Off's
    second session on main), c = the same here; a session's part MISSING where not measured; the
    sessions list has one value where only one session was measured (an older snapshot). (kind, why):
    "same", "changed" (still protected), "worse" (weaker), "unjudged" (it cannot be judged: worse) or
    "neutral" (a value main left real now disguised, every session away from the real one: worse,
    unless a test proves it needed). common: {(name, path): [values]} a person keeps (COMMON_VALUES).
    noise: main's noise sizes of the value (how often a text width stays real by chance: _real_chance);
    peer: main's sessions and Off of the list disguised by the same rule (LIST_PEERS)."""
    vb, sb, ob, ob2 = b
    vc, sc, oc, oc2 = c
    if len(sb) > 1 and len(sc) < len(sb):
        return "unjudged", "fewer sessions measured here (%d) than on main (%d)" % (len(sc), len(sb))
    if vb == vc and (sb == sc or len(sb) == 1):           # an older main: its one session
        return "same", ""
    if vc is MISSING or any(x is MISSING for x in sc):
        return "unjudged", "not read here"
    failed = [x for x in sc if isinstance(x, str) and FAILED.match(x)]
    if failed:
        return "unjudged", "could not be read here (%s)" % _short(failed[0], 60)
    if ob is MISSING or oc is MISSING:
        return "unjudged", "cannot be judged: the Off level was not measured"
    if (ob2 is not MISSING and ob2 != ob) or (oc2 is not MISSING and oc2 != oc):
        return "unjudged", "cannot be judged: it changes from one session to the next at Off too"
    sb = [x for x in sb if x is not MISSING] or [vb]
    role = _role(name, path)
    drawn_b, drawn_c = len({_id(x) for x in sb}), len({_id(x) for x in sc})
    if all(x == ob for x in sb):
        # main gave the real value every time: not disguised there at all
        if oc == ob and len(sc) > 1 and all(x != oc for x in sc):
            return "neutral", "main gave the real value; here a disguise, in every session"
        return "unjudged", "main gave the real value (Off's): a change of it cannot be judged"
    reals = (oc, ob)
    rb, rc = sum(1 for x in sb if x in reals), sum(1 for x in sc if x in reals)
    if rc:
        # the real value in a session: worse unless chance, as measured, explains it
        q = _real_chance(name, path, sb, ob, noise, peer)
        if q is None and not rb:
            return "worse", "the real value (Off's) here, in a session where main never gave it"
        if q is None and _more_often(rb, len(sb), rc, len(sc)) < CHANCE:
            return "worse", "the real value (Off's) in %d of %d sessions here, %d of %d on main" % (
                rc, len(sc), rb, len(sb))
        if q is not None and _tail(len(sc), q, rc) < CHANCE:
            return "worse", "the real value (Off's) in %d of %d sessions here: more than chance gives " \
                            "(%.2g a session, measured on main)" % (rc, len(sc), q)
    if all(x is None for x in sb) and any(x is not None for x in sc):
        return "worse", "hidden on main, readable here"
    names = (not path and name in FP_LISTS or (name, path) in LIST_PARTS) and \
        all(isinstance(x, str) for x in sb + sc + [ob, oc])
    if not names and all(isinstance(x, str) for x in sb + sc + [ob, oc]):
        # a text: never the real one in it, never more of its words than main's draws had
        if oc and any(oc in x for x in sc) and not any(ob and ob in y for y in sb):
            return "worse", "the real value (Off's) is in it here"
        most = max(len(_tokens(y) & _tokens(ob)) for y in sb)
        more = max(len(_tokens(x) & _tokens(oc)) for x in sc)
        if more > most:
            return "worse", "more of the real value's words here (%d) than in any of main's sessions (%d)" % (
                more, most)
    numbers = all(_number(x) for x in sb + sc + [ob, oc])
    if names:
        if drawn_b == 1:
            # a fixed list on main: no name of the real list main did not show, no closer to it
            shown = sorted(set().union(*(_names(x) for x in sc)) & _names(oc) - _names(vb))
            if shown:
                return "worse", "shows more of the real list: %s" % ", ".join(shown[:8])
            if min(_far(x, oc) for x in sc) < _far(vb, ob):
                return "worse", "closer to the real list: %d names differ from it on main, %d here" % (
                    _far(vb, ob), min(_far(x, oc) for x in sc))
        elif len(sb) < 3 or len(sc) < 3:
            return "unjudged", "a list drawn per session, read in too few sessions to judge its count"
        else:
            # a list randomised on main: as many names changed (beyond chance), as many different lists
            if _count_drop([_far(y, ob) for y in sb], [_far(x, oc) for x in sc]):
                return "worse", "fewer names changed from the real list: %.3g on main, %.3g here (sessions' mean)" % (
                    sum(_far(y, ob) for y in sb) / len(sb), sum(_far(x, oc) for x in sc) / len(sc))
            if drawn_b >= 3 and drawn_c < 3:
                return "worse", "%d different lists in %d sessions here, %d on main" % (drawn_c, len(sc), drawn_b)
    elif numbers and role != "pick":
        if drawn_b == 1:
            if min(abs(x - oc) for x in sc) < abs(vb - ob):
                return "worse", "closer to the real value: %g from it on main, %g here" % (
                    abs(vb - ob), min(abs(x - oc) for x in sc))
        elif len(sb) < 3 or len(sc) < 3:
            return "unjudged", "a number drawn per session, read in too few sessions to judge it"
        elif _count_drop([abs(y - ob) for y in sb], [abs(x - oc) for x in sc]):
            return "worse", "closer to the real value (sessions' mean): %.3g on main, %.3g here" % (
                sum(abs(y - ob) for y in sb) / len(sb), sum(abs(x - oc) for x in sc) / len(sc))
    if role == "pick":
        # one of a few common values, drawn per session: alike, or the real value, by chance is
        # judged above; the same in every session where chance can hardly explain it is worse
        if drawn_b > 1 and len(sc) > 2 and drawn_c == 1 and _chance_alike(sb, sc) < CHANCE:
            return "worse", "the same in every one of the %d sessions here (on main it changed)" % len(sc)
        return "changed", "another of the few common values this disguise is drawn from, not the real one"
    if drawn_b == 1 and len(sb) > 1:
        # a fixed disguise on main: a new fixed value only when a person counts it among the common ones
        new = [x for x in sc if x != vb]
        if new and role is None:
            known = (common or {}).get((name, path), [])
            if not all(any(x == k for k in known) for x in new):
                return "unjudged", "a new disguise (%s) that is not among the common values a person keeps " \
                                   "(tests/data/no-regression/common-values.json)" % _short(new[0], 60)
        return "changed", "another disguise, a common one, no closer to the real value"
    if len(sb) == 1:
        if len(sc) > 1 and drawn_c > 1:
            return "changed", "still not the real value, and different in each session"
        return "unjudged", "cannot be judged: main's other sessions were not measured"
    if drawn_c == 1:
        return "worse", "the same in every session here (on main it changed with the session)"
    if role == "noise" and len(sb) > 2 and drawn_b == len(sb) and drawn_c < len(sc):
        # N2 of the fourth review: a large space drawn from a few keys (8 noises for 8 sessions: alike in
        # two of them 99.8 % of the time); on main every session differed
        return "worse", "only %d different in %d sessions here (on main all %d differed)" % (drawn_c, len(sc), len(sb))
    return "changed", "still noised (not the real value) and different in each session"


def _sessions(o, field="value"):
    """A value's readings in every session measured (an older snapshot: the first one or two)."""
    if o is None or field not in o:
        return None
    if isinstance(o.get("sessions"), list) and o["sessions"]:
        return o["sessions"]
    return [o["value"], o["session2"]] if "session2" in o else [o["value"]]


def _judge_fingerprint(key, b, c, bo, co, floors=None, common=None):
    """A value the fingerprinting protection disguises (FP_JUDGED), judged by what protects, part by
    part (_parts) and over every session measured (SESSIONS), on main and here, each against the Off
    level of its own snapshot (the real value; both Offs count):
    - randomised on main: the real value in no more sessions than chance gives it (where chance never
      does, in none where main never gave it; otherwise as measured on main: _real_chance); a large space
      (NOISE_PARTS) still different with the session; a list changing as many names and as many
      different lists, a number as far from the real one (beyond chance: _count_drop); a value drawn
      from a few common ones (PICK_*) never the same in all sessions where chance cannot explain it;
    - a fixed disguise on main: not the real value, no closer to it (a list, a number, a text's
      words), and a new value only among the common ones a person keeps (COMMON_VALUES);
    - its noise (NOISE) not below main's less the tolerance of chance, nor below the floor
      (NOISE_FLOORS, no tolerance), measured against the same real values on both sides;
    - what cannot be judged (fewer sessions here, Off not measured or unstable, a part that could
      not be read, a value main left real) is "unjudged" (worse); a value main left real now
      disguised in every session is "neutral" (worse, unless a test proves it needed).
    (kind, detail): a weaker part or a smaller noise makes it "worse" whatever the rest is."""
    if c is None:
        return "unjudged", "not measured on the candidate"
    if b is None:
        return "unjudged", "not measured on main: a new value cannot be judged"
    head, _, name = key.split("/", 2)
    offkey = "%s/off/%s" % (head, name)
    offb, offc = bo.get(offkey), co.get(offkey)

    def split(o, field):
        return _parts(o[field], name) if o is not None and field in o else None

    def at(parts, path):
        return MISSING if parts is None else parts.get(path, MISSING)

    sb = [_parts(x, name) for x in _sessions(b)]
    sc = [_parts(x, name) for x in _sessions(c)]
    ob, ob2, oc, oc2 = split(offb, "value"), split(offb, "session2"), split(offc, "value"), split(offc, "session2")
    found = {"worse": [], "unjudged": [], "neutral": [], "changed": []}

    def peer(path):
        other = LIST_PEERS.get((name, path))
        level = key.split("/")[1]
        po, pf = bo.get("%s/%s/%s" % (head, level, other)), bo.get("%s/off/%s" % (head, other))
        if not other or not po or not pf or "value" not in pf:
            return None
        return _sessions(po), pf["value"]
    for path in sorted(set(sb[0]) | set(sc[0])):
        kind, why = _judge_part(name, path, (sb[0].get(path, MISSING), [s.get(path, MISSING) for s in sb],
                                             at(ob, path), at(ob2, path)),
                                (sc[0].get(path, MISSING), [s.get(path, MISSING) for s in sc], at(oc, path),
                                 at(oc2, path)), common, b.get("noise"), peer(path))
        if kind != "same":
            found[kind].append(("%s %s" % (path, why)) if path else why)

    def said(*kinds):
        why = [w for k in kinds for w in found[k]]
        return "; ".join(why[:6]) + ("; and %d more parts" % (len(why) - 6) if len(why) > 6 else "")
    noise = _judge_noise(name, b.get("noise"), c.get("noise"), floors)
    if noise and (offb or {}).get("samples_ref") != (offc or {}).get("samples_ref"):
        noise = ("unjudged", "the real values (Off) the noise is measured against differ between main and "
                             "here: the noise cannot be compared")
    if found["worse"]:                 # a weaker part decides, whatever the other parts are
        return "worse", said("worse", "unjudged", "neutral")
    if noise and noise[0] == "worse":  # and a smaller noise, even next to a part that cannot be judged
        return noise
    if found["unjudged"]:
        return "unjudged", said("unjudged", "neutral")
    if noise and noise[0] == "unjudged":
        return noise
    if found["neutral"]:
        return "neutral", said("neutral")
    if not found["changed"]:
        if b.get("value") != c.get("value"):
            return "unjudged", "written another way, the same parts: cannot be judged"
        return noise if noise and noise[0] == "stricter" else ("same", "")
    return noise or ("changed", "still protected: " + "; ".join(found["changed"][:4]))


# keys the fingerprinting rules give a direction of their own: what protects on main (hidden, refused,
# native-looking...) must stay so; becoming so is stricter; any other change cannot be judged, and no
# evidence ever accepts it. None: no protective value is known (any change cannot be judged).
def _starts(*words):
    return lambda v: isinstance(v, str) and v.startswith(words)


PROTECTIVE = (
    (re.compile(r"^natives\."), _starts("true:")),
    (re.compile(r"^navigator\.webdriver$"), lambda v: v in (False, None)),
    (re.compile(r"^navigator\.globalPrivacyControl$"), lambda v: v is True),
    (re.compile(r"^navigator\.(connection|getBattery|keyboard|gpu|bluetooth|usb|hid|serial)$"),
     lambda v: v == "undefined"),
    (re.compile(r"^media_devices$"), lambda v: isinstance(v, str) and all(
        re.fullmatch(r"[a-z]+::", x) for x in v.split("|") if x)),
    (re.compile(r"^battery$"), lambda v: v == "none" or v == [True, 1, 0, "Infinity"] or _starts("error")(v)),
    (re.compile(r"^webgpu$"), lambda v: v in ("none", "no adapter", "timeout") or _starts("error")(v)),
    (re.compile(r"^local_fonts$"), lambda v: v in ("none", "timeout") or _starts("refused")(v)),
    (re.compile(r"^keyboard$"), lambda v: v in ("none", "timeout") or _starts("refused")(v)),
    (re.compile(r"^voices$"), lambda v: v in (0, "none")),
    (re.compile(r"^third_party$"), lambda v: v != "loaded"),
    (re.compile(r"^ike_scheme$"), lambda v: v == "refused"),
    (re.compile(r"^permissions\."), lambda v: v == "denied"),
    (re.compile(r"^(storage_quota|navigator\.doNotTrack|navigator\.cookieEnabled)$"), None),
)
# marks judged as a protection that must stay on: the value differs from Off (".noised"), from the
# other start (".differs"), reads the same twice ("stable."), differs on another site ("site.")
MARKS = re.compile(r"(\.noised|\.differs)$|^(stable|site|sites|env|again)\.|^frame\.agrees\.")


def _protective(name):
    for pattern, test in PROTECTIVE:
        if pattern.search(name):
            return True, test
    return False, None


def _judge_protective(test, base, cand):
    if test is not None and test(base) and not test(cand):
        return "worse", "protected on main (%s), not here (%s)" % (_short(base, 60), _short(cand, 60))
    if test is not None and not test(base) and test(cand):
        return "stricter", "%s on main, protected here (%s)" % (_short(base, 60), _short(cand, 60))
    return "unjudged", "%s on main, %s here (a value with a protective direction: no evidence accepts it)" % (
        _short(base, 80), _short(cand, 80))


def _rule(key, b, c):
    """The rule of an observation: this copy's own for the fingerprinting values (FP_JUDGED, the
    directional ones, the marks) and the pages' scriptlets, whatever rule the snapshots carry (one of
    an older copy is judged the same way); otherwise the one main's snapshot gives."""
    parts = key.split("/", 2)
    if parts[0] == "fingerprint" and len(parts) == 3 and parts[1] != "off":
        if FP_JUDGED.match(parts[2]):
            return "fingerprint"
        if MARKS.search(parts[2]):
            return "safer-true"
        if _protective(parts[2])[0]:
            return "protective"
    if parts[0] == "page-scriptlets":
        return "protective"
    if parts[0] == "fingerprint-config" and len(parts) == 3 and parts[2] == "fonts":
        return "fonts"
    return (b or c)["rule"]


# the families every system answers to, never masked by fingerprint.js (fontcheck.py KEPT)
FONTS_KEPT = {"arial", "helvetica", "times", "times new roman", "courier", "courier new"}


def _unmasked(o):
    """The fonts a page can find that the level does not mask (lower case), or None if not measured."""
    if not isinstance(o, dict) or not isinstance(o.get("findable"), list):
        return None
    masked = o.get("masked") if isinstance(o.get("masked"), list) else o.get("listed")
    if not isinstance(masked, list):
        return None
    return sorted({str(n).lower() for n in o["findable"]} - {str(n).lower() for n in masked} - FONTS_KEPT)


def _judge_fonts(key, b, c):
    """fingerprint-config/<level>/fonts: the names fingerprint.js masks, which follow the fonts of the
    computer and when its check answered (a digest differs between two runs of the same code). Judged
    by what protects: every font a page can find (measured by the tool in the same run, FONTS_JS) is
    masked; a font left findable that main masked is worse, fewer names masked is not."""
    if c is None:
        return "unjudged", "not measured on the candidate"
    ub, uc = _unmasked(b), _unmasked(c)
    if uc is None:
        if isinstance((b or {}).get("findable"), list):
            return "unjudged", "the fonts a page can find were not measured here"
        return _judge("exact", (b or {}).get("value"), c.get("value"), key)
    new = sorted(set(uc) - set(ub or ()))
    if new:
        return "worse", "a font a page can find here is not masked: %s" % ", ".join(new[:8])
    if ub and len(uc) < len(ub):
        return "stricter", "%d fonts a page can find unmasked on main, %d here" % (len(ub), len(uc))
    if (b or {}).get("value") == c.get("value") and ub == uc:
        return "same", ""
    return "changed", "every font a page can find is masked, as on main (%d found here, %s on main)" % (
        len(c["findable"]), len(b["findable"]) if isinstance((b or {}).get("findable"), list) else "not measured")
def _short(v, n=160):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n] + "..."


def load_allowlist(path):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError) as exc:
        return [], "the allowlist could not be read (%s): nothing is accepted" % type(exc).__name__
    entries = [e for e in data.get("entries") or () if isinstance(e, dict) and e.get("key") and
               str(e.get("why") or "").strip()]
    bad = len(data.get("entries") or ()) - len(entries)
    return entries, ("%d entries without a key or a reason were ignored" % bad) if bad else ""


def _accepted(entries, key, base, cand, detail="", version=""):
    """The index of the allowlist entry a person wrote for this row, or None. Beyond the key and the
    values (main's, the candidate's), an entry may pin (N9 of the fourth review, for the rows whose
    values change with the session's key): "part", the part of a disguised value the row is about (its
    detail starts with it); "detail", a text the row's detail holds; "version", the I.K.E. version of
    the candidate it is for (another version: the entry no longer counts)."""
    for i, e in enumerate(entries):
        if not fnmatch.fnmatchcase(key, e["key"]):
            continue
        if "base" in e and e["base"] != base:
            continue
        if "candidate" in e and e["candidate"] != cand:
            continue
        if "part" in e and not str(detail).startswith(str(e["part"]) + " "):
            continue
        if "detail" in e and str(e["detail"]) not in str(detail):
            continue
        if "version" in e and str(e["version"]) != str(version):
            continue
        return i
    return None


# --- evidence: what lets a change the rules call worse pass with no person ------------------------
# Necessity (2026-11-24, the owner's principle: a change needed for I.K.E. to work and for its
# protections to keep working is approved by the chain itself), narrowed after an independent review
# ("when in doubt, worse"): a test that fails on main and passes here, both confirmed by running it
# CONFIRM_RUNS times on each side, accepts only rows of the one neutral kind (a fingerprinting value
# main left real, now disguised in both sessions), only the observations a person bound to that test
# in NECESSITY_MAP (exact test ids, keys with at most the level as "*"), only when this change touches
# the files of that entry, and at most NECESSITY_CAP rows per test. Never a weakening, a value that
# could not be read or was not measured, an Off-level row, a value with a protective direction, the
# fingerprinting configuration, a request, a host, a security setting.
NECESSITY_MAP = FIXTURES / "necessity.json"
NECESSITY_CAP = 4
CONFIRM_RUNS = 3
NECESSITY_TEST = re.compile(r"tests/test_\w+\.py::test_[\w\[\]\-.,]+")
NECESSITY_KEY = re.compile(r"fingerprint/(\*|[a-z]+)/[A-Za-z0-9_.]+")
# I.K.E.'s known external endpoints: a host contacted by itself that main does not contact passes only
# when it is declared there for that observation and this change's own code (ike/**/*.py, not a
# comment) names it. Only a person (or Claude, with the change read in full) edits it: it is under
# tests/, as the allowlist; tests.yml reads main's copy of both.
ENDPOINTS = FIXTURES / "endpoints.json"
# why a change passed, by the rule that judged it
RULE_WHY = {
    "block": "still stopped (blocked, or sent to a harmless local answer)",
    "hidden": "the element hidden here",
    "kept": "nothing lost, something more kept",
    "no-new": "nothing new, something less",
    "switches": "an added engine switch that does not read as weaker, none lost",
    "safer-true": "now the safer value", "safer-false": "now the safer value",
    "level": "a higher protection level", "permission": "a stricter permission",
    "setting": "the safer WebEngine setting",
    "protective": "now protected (hidden, refused or native-looking)",
    "fingerprint": "judged by what protects: still disguised (the fingerprinting rules)",
    "fonts": "judged by what protects: every font a page can find is masked",
}


def _junit_file(case):
    f = case.get("file")
    if f:
        return f
    parts = (case.get("classname") or "").split(".")
    for i in range(len(parts), 0, -1):
        if parts[i - 1].startswith("test_"):
            return "/".join(parts[:i]) + ".py"
    return "?"


def read_junit(paths):
    """{"tests/test_x.py::name": "failed" | "passed" | "skipped"} from pytest's junit files; a test
    failed in any of them is failed, else passed in one of them is passed. Unreadable files are left
    out (no evidence from them)."""
    import xml.etree.ElementTree as ET
    out, rank = {}, {"skipped": 0, "passed": 1, "failed": 2}
    for path in paths or ():
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for case in root.iter("testcase"):
            tid = "%s::%s" % (_junit_file(case), case.get("name") or "?")
            state = "failed" if case.find("failure") is not None or case.find("error") is not None else \
                "skipped" if case.find("skipped") is not None else "passed"
            if rank[state] > rank.get(out.get(tid), -1):
                out[tid] = state
    return out


def read_diff(text):
    """(changed files, the code lines this change adds to ike/**/*.py, comments left out) from the
    output of git's diff."""
    changed, added, path = set(), [], None
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            if m:
                changed.update(m.groups())
                path = m.group(2)
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and path and path.startswith("ike/") and path.endswith(".py"):
            code = line[1:].strip()
            if code and not code.startswith("#"):
                added.append(code)
    return sorted(changed), "\n".join(added)


def load_endpoints(path):
    """The declared endpoints [{"host", "purpose", "key" (default network/fresh-profile), ...}]; none
    when the file cannot be read. Exact hosts only."""
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [dict(e, key=e.get("key") or "network/fresh-profile") for e in data.get("endpoints") or ()
            if isinstance(e, dict) and isinstance(e.get("host"), str) and re.fullmatch(r"[a-z0-9.-]+", e["host"])
            and str(e.get("purpose") or "").strip()]


def load_necessity(path=None):
    """The tests a person bound to the observations they may prove needed (NECESSITY_MAP)."""
    try:
        data = json.loads(Path(path or NECESSITY_MAP).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return load_necessity_from(data.get("entries") if isinstance(data, dict) else None)


def load_necessity_from(entries):
    """[{"test", "keys", "files", "why"}] of the entries of the strict form (an exact test id, keys of
    fingerprinting values with at most the level as "*", exact files under ike/, a reason); any other
    entry is left out."""
    out = []
    for e in entries or ():
        if not isinstance(e, dict) or not str(e.get("why") or "").strip():
            continue
        test, keys, files = e.get("test"), e.get("keys"), e.get("files")
        if not (isinstance(test, str) and NECESSITY_TEST.fullmatch(test) and isinstance(keys, list) and keys
                and all(isinstance(k, str) and NECESSITY_KEY.fullmatch(k) for k in keys)
                and isinstance(files, list) and files and all(isinstance(f, str) and f.startswith("ike/")
                                                              and "*" not in f for f in files)):
            continue
        out.append({"test": test, "keys": keys, "files": files, "why": e["why"]})
    return out


def fixed_tests(evidence):
    """The tests that fail on main and pass here (junit), confirmed by running them again on both
    sides when the evidence carries a confirmation (evidence["confirmed"])."""
    main_t, cand_t = evidence.get("main_tests") or {}, evidence.get("candidate_tests") or {}
    fixed = sorted(t for t, st in main_t.items() if st == "failed" and cand_t.get(t) == "passed")
    confirmed = evidence.get("confirmed")
    return [t for t in fixed if confirmed is not None and t in confirmed]


def _key_matches(key, pattern):
    head, lv, name = pattern.split("/", 2)
    k = key.split("/", 2)
    return len(k) == 3 and k[0] == head and k[2] == name and (lv == "*" or lv == k[1]) and k[1] != "off"


def _by_necessity(rows, evidence):
    """{key: why} of the neutral rows a confirmed, bound test proves needed (NECESSITY_MAP)."""
    fixed = set(fixed_tests(evidence))
    changed = set(evidence.get("changed") or ())
    claims = {}
    for e in evidence.get("necessity") or ():
        if e["test"] not in fixed or not changed & set(e["files"]):
            continue
        if e["test"].split("::", 1)[0] in changed:
            continue                     # the change rewrote the test that would prove it needed
        rows_of = [r for r in rows if any(_key_matches(r["key"], p) for p in e["keys"])]
        if rows_of and len(rows_of) <= NECESSITY_CAP:
            for r in rows_of:
                claims.setdefault(r["key"], "needed: the test %s fails on main and passes here (confirmed %d times "
                                            "on each side), it is bound to this value (%s), and this change "
                                            "touches %s" % (e["test"], CONFIRM_RUNS, _short(e["why"], 120),
                                                            ", ".join(sorted(changed & set(e["files"]))[:3])))
    return claims


def _by_lists(key, b, c, base, cand):
    """Why a request newly let through passes: the filter list data that decides it changed (an
    exception in the list's new data lets it through, or the rule that blocked it is gone from it).
    Main's lists must have stopped it (not I.K.E.'s own rules), and here the lists must let it go."""
    if not key.startswith("requests/") or not b or not c or c.get("value") != "allow":
        return None
    lb, lc = b.get("lists"), c.get("lists")
    db, dc = base.get("list_data") or {}, cand.get("list_data") or {}
    if not isinstance(lb, dict) or not isinstance(lc, dict):
        return None
    if lb.get("verdict") != "block" or lc.get("verdict") != "allow":
        return None

    def changed(url):
        return bool(url) and url in db and url in dc and db[url] != dc[url]
    if lc.get("exception") and lc["exception"] != lb.get("exception") and changed(lc.get("exception_list")):
        return "the list decides: its new data has the exception `%s` (%s)" % (lc["exception"], lc["exception_list"])
    if not lc.get("rule") and changed(lb.get("rule_list")):
        return "the list decides: the rule `%s` is gone from the new data of %s" % (lb.get("rule"), lb["rule_list"])
    return None


def _by_registry(key, bv, cv, evidence):
    """Why new hosts pass: each is declared (ENDPOINTS) for this observation and named by this
    change's own code (added lines of ike/**/*.py, not comments)."""
    if not key.startswith("network/"):
        return None
    new = sorted(set(cv or []) - set(bv or []))
    known = {e["host"]: e for e in evidence.get("endpoints") or () if e.get("key") == key}
    added = evidence.get("added")

    def named(h):          # the host itself, not a longer name that ends or starts with it
        return re.search(r"(?<![\w.-])%s(?![\w-]|\.\w)" % re.escape(h), added) is not None
    if not new or added is None or any(h not in known or not named(h) for h in new):
        return None
    return "declared endpoints (tests/data/no-regression/endpoints.json), named by this change's code: %s" % (
        "; ".join("%s, %s" % (h, known[h]["purpose"]) for h in new))


def load_common(path=None):
    """{(value, part): [values]} a person counts among the common values of a fixed disguise
    (COMMON_VALUES); None when the file cannot be read (an error)."""
    try:
        data = json.loads(Path(path or COMMON_VALUES).read_text("utf-8"))
        return {(e["value"], e.get("part") or ""): list(e["common"]) for e in data["entries"]
                if isinstance(e, dict) and str(e.get("why") or "").strip() and isinstance(e.get("common"), list)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def compare(base, cand, allowlist_entries=(), evidence=None, floors=None, common=None):
    """The report: every observation of both snapshots judged; verdict "pass" or "fail". A change the
    rules call worse passes only by evidence (_by_necessity for the neutral kind only, _by_lists for
    a request, _by_registry for a host) or by a person (the allowlist). Every row that passed says
    why ("why", "passed_by"). evidence: {"changed": [files], "added": the code lines this change adds
    to ike/**/*.py, "main_tests" and "candidate_tests": read_junit(), "confirmed": the tests confirmed
    by running them again, "necessity": load_necessity(), "endpoints": load_endpoints()}; a part that
    is missing gives no evidence. floors: load_floors() (default: this copy's NOISE_FLOORS)."""
    evidence = evidence or {}
    floors = load_floors() if floors is None else floors
    common = load_common() if common is None else common
    rows = {"worse": [], "evidence": [], "accepted": [], "stricter": [], "changed": []}
    used = set()
    errors = []
    if floors is None:
        errors.append("the noise floors (tests/data/no-regression/noise-floor.json) could not be read")
    if common is None:
        errors.append("the common values (tests/data/no-regression/common-values.json) could not be read")
    for side, snap in (("main", base), ("candidate", cand)):
        if snap.get("format") != FORMAT:
            errors.append("%s: a snapshot of another format (%r)" % (side, snap.get("format")))
        for e in snap.get("errors") or ():
            last = ((e.get("error") or "").strip().splitlines() or ["?"])[-1]
            errors.append("%s, %s: %s" % (side, e.get("section"), last[:300]))
    bo, co = base.get("observations") or {}, cand.get("observations") or {}
    order = ("blocking", "fingerprinting", "network", "security")
    pending = []
    for key in sorted(set(bo) | set(co), key=lambda k: (order.index(_section(k)), k)):
        if key.startswith("request-headers/"):
            rk = "requests/%s/%s" % tuple(key.split("/")[1:3])
            if (bo.get(rk) or {}).get("value") != (co.get(rk) or {}).get("value"):
                continue          # the request itself is judged; its headers follow what it became
        b, c = bo.get(key), co.get(key)
        rule = _rule(key, b, c)
        bv, cv = (b or {}).get("value"), (c or {}).get("value")
        if b is not None and c is None:
            # N10 of the fourth review: measured on main (even as null), missing here: never "same"
            kind, detail = "unjudged", "not measured on the candidate"
        elif rule == "fingerprint" and (bv != cv or (b and c and (
                _sessions(b) != _sessions(c) or b.get("noise") != c.get("noise")))):
            kind, detail = _judge_fingerprint(key, b, c, bo, co, floors, common)
        elif rule == "fonts":
            kind, detail = _judge_fonts(key, b, c)
        elif rule == "protective":
            test = None if key.startswith("page-scriptlets/") else _protective(key.split("/", 2)[2])[1]
            kind, detail = ("same", "") if bv == cv else \
                ("unjudged", "not measured on the candidate") if c is None else _judge_protective(test, bv, cv)
        else:
            kind, detail = _judge(rule, bv, cv, key)
        if kind == "same":
            continue
        row = {"key": key, "section": _section(key), "rule": rule, "main": bv, "candidate": cv, "detail": detail}
        if kind in ("stricter", "changed"):
            row.update(why="the rule `%s`: %s" % (rule, RULE_WHY.get(rule, "not weaker")), passed_by="rule")
            rows[kind].append(row)
            continue
        row["weakening"] = kind == "worse"
        row["neutral"] = kind == "neutral"
        why = by = None
        if rule == "block" and kind == "worse":
            why, by = _by_lists(key, b, c, base, cand), "lists"
        elif rule == "no-new" and kind == "worse":
            why, by = _by_registry(key, bv, cv, evidence), "registry"
        if why:
            row.update(why=why, passed_by=by)
            rows["evidence"].append(row)
        else:
            pending.append(row)
    claims = _by_necessity([r for r in pending if r["neutral"]], evidence)
    for row in pending:
        if row["key"] in claims:
            row.update(why=claims[row["key"]], passed_by="necessity")
            rows["evidence"].append(row)
            continue
        i = _accepted(allowlist_entries, row["key"], row["main"], row["candidate"], row["detail"],
                      (cand.get("repo") or {}).get("version") or "")
        if i is not None:
            used.add(i)
            row.update(why=allowlist_entries[i].get("why"), passed_by="person")
            rows["accepted"].append(row)
            continue
        rows["worse"].append(row)
    verdict = "fail" if rows["worse"] or errors else "pass"
    sections = {}
    for kind, items in rows.items():
        for r in items:
            sections.setdefault(r["section"], dict.fromkeys(rows, 0))[kind] += 1
    counts = {}
    for k in bo:
        s = _section(k)
        counts[s] = counts.get(s, 0) + 1
    info = ("repo", "seconds", "corpus", "levels", "sections")
    # N5 of the fourth review: every fingerprinting row that is not the same or stricter (changed, passed
    # by evidence, accepted by a person, or worse): a person's change may bring them, an AI's never by
    # itself (tests.yml "Fingerprinting unchanged", tools/automerge.py)
    review = [{"key": r["key"], "detail": r["detail"], "passed_by": r.get("passed_by", "")}
              for kind in ("worse", "evidence", "accepted", "changed") for r in rows[kind]
              if r["section"] == "fingerprinting"]
    return {"verdict": verdict, "errors": errors, "main": {k: base.get(k) for k in info},
            "fingerprint_review": review, "floor_notices": stale_floors(base, floors),
            "candidate": {k: cand.get(k) for k in info}, "compared": counts,
            "sections": sections, "unused_allowlist": [e for i, e in enumerate(allowlist_entries) if i not in used],
            "evidence_read": {"changed_files": len(evidence["changed"]) if evidence.get("changed") is not None
                              else None,
                              "main_tests": len(evidence.get("main_tests") or ()),
                              "candidate_tests": len(evidence.get("candidate_tests") or ()),
                              "fixed_tests": fixed_tests(evidence),
                              "necessity": len(evidence.get("necessity") or ()),
                              "endpoints": len(evidence.get("endpoints") or ())},
            **rows}


SECTION_WORDS = {"blocking": "Ad and tracker blocking", "fingerprinting": "Fingerprinting surface",
                 "network": "Hosts contacted by itself", "security": "Security settings"}


def _plain(row):
    key = row["key"]
    parts = key.split("/")
    level = lambda lv: LEVEL_NAMES.get(lv, lv)  # noqa: E731
    if parts[0] == "requests":
        return "request `%s` at %s: %s" % (parts[2], level(parts[1]), row["detail"])
    if parts[0] == "cosmetic":
        return "element `%s` of the page `%s` at %s: %s" % (parts[3], parts[2], level(parts[1]), row["detail"])
    if parts[0] == "fingerprint":
        return "what a page reads at %s, `%s`: %s" % (level(parts[1]), "/".join(parts[2:]), row["detail"])
    if parts[0] == "network":
        return "hosts contacted by itself (%s): %s" % (parts[1], row["detail"])
    if parts[0] == "request-headers":
        return "header `%s` of request `%s` at %s: %s" % (parts[3], parts[2], level(parts[1]), row["detail"])
    return "`%s`: %s" % (key, row["detail"])


def markdown(report, limit=60):
    ok = report["verdict"] == "pass"
    m, c = report["main"].get("repo") or {}, report["candidate"].get("repo") or {}
    out = ["### Nothing gets worse", ""]
    if ok:
        k = len(report.get("evidence") or ())
        out.append("**Passed%s**: nothing that main does for its users is weaker on this commit%s." % (
            ", %d by evidence" % k if k else "",
            "; %d difference%s passed by evidence, each said below with its evidence" % (k, "" if k == 1 else "s")
            if k else ""))
    else:
        n = len(report["worse"])
        out.append("**Failed**: %s." % ("; ".join(x for x in (
            "%d thing%s worse than on main" % (n, "" if n == 1 else "s") if n else "",
            "%d part%s could not be measured" % (len(report["errors"]), "" if len(report["errors"]) == 1 else "s")
            if report["errors"] else "") if x)))
    out += ["", "Main `%s` (%s) and this commit `%s` (%s), measured the same way on the same inputs "
            "(%s requests at %d levels, %s page elements, the probe page, a fresh profile)." % (
                (m.get("commit") or "?")[:12], m.get("version", "?"), (c.get("commit") or "?")[:12],
                c.get("version", "?"), (report["main"].get("corpus") or {}).get("requests", "?"),
                len(report["main"].get("levels") or LEVELS),
                (report["main"].get("corpus") or {}).get("elements", "?")), "",
            "| What | Compared | Worse | Passed by evidence | Accepted by a person | Stricter | Changed |",
            "|---|---|---|---|---|---|---|"]
    for s in ("blocking", "fingerprinting", "network", "security"):
        n = report["sections"].get(s) or {}
        out.append("| %s | %d | %d | %d | %d | %d | %d |" % (
            SECTION_WORDS[s], report["compared"].get(s, 0), n.get("worse", 0), n.get("evidence", 0),
            n.get("accepted", 0), n.get("stricter", 0), n.get("changed", 0)))
    ev = report.get("evidence_read") or {}
    if ev:
        fixed = ev.get("fixed_tests") or []
        files = ev.get("changed_files")
        out += ["", "Evidence read: %s; the tests of main (%d) and of this commit (%d): %s; %d tests bound to "
                "values a person declared; %d declared endpoints." % (
                    "the files of this change not known" if files is None else
                    "%d file%s this change touches" % (files, "" if files == 1 else "s"),
                    ev.get("main_tests", 0), ev.get("candidate_tests", 0),
                    "fixed here and confirmed: %s" % ", ".join("`%s`" % t for t in fixed[:10]) if fixed else
                    "none fails on main and passes here, confirmed", ev.get("necessity", 0), ev.get("endpoints", 0))]
    if report["errors"]:
        out += ["", "Not measured (a check that did not run is never passed):", ""]
        out += ["- %s" % e.replace("\n", " ")[:400] for e in report["errors"][:20]]
    for kind, title in (("worse", "Worse than on main"),
                        ("evidence", "Passed by evidence, with no person (the evidence is said for each)"),
                        ("accepted", "Worse, but accepted by a person (tests/data/no-regression/allowlist.json)"),
                        ("stricter", "Stricter than on main (fine, reported)"),
                        ("changed", "Changed, neither weaker nor stricter (reported)")):
        rows = report.get(kind) or []
        if not rows:
            continue
        out += ["", "#### %s (%d)" % (title, len(rows)), ""]
        for r in rows[:limit]:
            line = "- %s" % _plain(r).replace("\n", " ")
            if kind == "worse":
                line += " (%s)" % ("weaker" if r.get("weakening", True) else
                                   "cannot be judged; a security setting: only a person accepts it"
                                   if r["section"] == "security" else
                                   "a value main left real, now disguised: a test bound to it that fails on main "
                                   "and passes here shows it is needed" if r.get("neutral") else
                                   "cannot be judged: only a person accepts it")
            elif r.get("why"):
                line += " (%s: %s)" % ("accepted" if kind == "accepted" else "passed", r["why"])
            out.append(line[:700])
        if len(rows) > limit:
            out.append("- and %d more (the JSON report has them all)" % (len(rows) - limit))
    if report["unused_allowlist"]:
        out += ["", "Allowlist entries that matched nothing (a person may remove them): %s." % ", ".join(
            "`%s`" % e["key"] for e in report["unused_allowlist"][:20])]
    if report.get("floor_notices"):
        out += ["", "**Noise floors far under main's noise** (under %d %%: a person raises them in "
                "tests/data/no-regression/noise-floor.json): %s." % (
                    FLOOR_STALE * 100, "; ".join(report["floor_notices"][:12]))]
    if report.get("runs", 1) > 1:
        out += ["", "Measured %d times, each with its own random keys: a row worse in any run is worse." % report["runs"]]
    return "\n".join(out) + "\n"


def _write(path, text):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, "utf-8")


EVIDENCE_TITLE = "Nothing gets worse: passed by evidence"


def _finish(report, args):
    _write(getattr(args, "json", None), json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
    _write(getattr(args, "markdown", None), markdown(report))
    rows = report.get("evidence") or []
    if rows and os.environ.get("GITHUB_ACTIONS") == "true":
        # one notice of the run (tools/release-notice.py reads it for the signing notice)
        text = "%d passed by evidence: %s" % (len(rows), "; ".join("%s (%s): %s" % (
            r["key"], r.get("passed_by"), r.get("why")) for r in rows))
        print("::notice title=%s::%s" % (EVIDENCE_TITLE, text[:4000].replace("%", "%25").replace("\r", "%0D")
                                         .replace("\n", "%0A")))
    print(report["verdict"])
    return 0 if report["verdict"] == "pass" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="the behaviour snapshot of one checkout")
    s.add_argument("--repo", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--levels", nargs="+", default=list(LEVELS), choices=LEVELS)
    s.add_argument("--sections", nargs="+", default=list(SECTIONS), choices=SECTIONS)
    s.add_argument("--fixtures", default=str(FIXTURES))
    s.add_argument("--keep", help="keep the profiles and logs in this folder")
    c = sub.add_parser("compare", help="main's snapshot against a candidate's")
    c.add_argument("--base", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--allowlist", default=str(ALLOWLIST))
    c.add_argument("--json")
    c.add_argument("--markdown")
    c.add_argument("--diff", help="this change as git's diff output (the files it touches, the lines it adds)")
    k = sub.add_parser("check", help="both snapshots, then the comparison")
    k.add_argument("--base-repo", required=True)
    k.add_argument("--candidate-repo", required=True)
    k.add_argument("--allowlist", default=str(ALLOWLIST))
    k.add_argument("--out-dir", default=".")
    k.add_argument("--fixtures", default=str(FIXTURES))
    k.add_argument("--json")
    k.add_argument("--markdown")
    k.add_argument("--diff", help="this change as git's diff output (default: asked of git in the candidate's "
                                  "checkout, from main's commit)")
    k.add_argument("--runs", type=int, default=1,
                   help="measure both sides this many times, each with its own random keys and shape; a row "
                        "worse in any run is worse (tests.yml: 3 for an AI's change of the fingerprinting)")
    for x in (c, k):
        x.add_argument("--main-junit", action="append", default=[],
                       help="pytest's junit file of main's tests (evidence: a test that fails there)")
        x.add_argument("--candidate-junit", action="append", default=[],
                       help="pytest's junit file of the candidate's tests (evidence: that test passes here)")
        x.add_argument("--endpoints", default=str(ENDPOINTS), help="I.K.E.'s declared external endpoints")
        x.add_argument("--necessity", default=str(NECESSITY_MAP),
                       help="the tests a person bound to the values they may prove needed")
    c.add_argument("--confirmed", action="append", default=[],
                   help="a test confirmed by running it again on both sides (check confirms them itself)")
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        snap = snapshot(args.repo, args.levels, args.sections, args.fixtures, keep=args.keep)
        _write(args.out, json.dumps(snap, indent=1, ensure_ascii=False, default=str) + "\n")
        print("%s: %d observations, %d errors, %.0f s" % (args.out, len(snap["observations"]), len(snap["errors"]),
                                                          snap["seconds"]))
        return 0
    entries, note = load_allowlist(args.allowlist)
    if note:
        print("allowlist: " + note, file=sys.stderr)
    evidence = {"main_tests": read_junit(args.main_junit), "candidate_tests": read_junit(args.candidate_junit),
                "endpoints": load_endpoints(args.endpoints), "necessity": load_necessity(args.necessity)}
    if args.cmd == "compare":
        base = json.loads(Path(args.base).read_text("utf-8"))
        cand = json.loads(Path(args.candidate).read_text("utf-8"))
        if args.diff:
            evidence["changed"], evidence["added"] = read_diff(Path(args.diff).read_text("utf-8", "replace"))
        evidence["confirmed"] = set(args.confirmed)
        return _finish(compare(base, cand, entries, evidence), args)
    out = Path(args.out_dir)
    import secrets
    reports, runs = [], max(1, int(args.runs or 1))
    # main's names of the masked fonts, tested on both sides (N4: a name taken out is still tested)
    fonts_main = masked_fonts(args.base_repo)
    for run in range(runs):
        # the same noise keys and the same shape of the probe for both sides, random: the code measured
        # cannot know them in advance
        keys = [secrets.token_hex(16) for _ in range(SESSIONS + PICK_DRAWS)]
        shape, names = random_shape(), run_names()
        where = out if run == 0 else out / ("run%d" % (run + 1))
        base = snapshot(args.base_repo, fixtures=args.fixtures, keys=keys, shape=shape, fonts_main=fonts_main,
                        names=names)
        _write(where / "main.json", json.dumps(base, indent=1, ensure_ascii=False, default=str) + "\n")
        cand = snapshot(args.candidate_repo, fixtures=args.fixtures, keys=keys, shape=shape, fonts_main=fonts_main,
                        names=names)
        _write(where / "candidate.json", json.dumps(cand, indent=1, ensure_ascii=False, default=str) + "\n")
        if run == 0:
            diff = Path(args.diff).read_text("utf-8", "replace") if args.diff else \
                _change(args.candidate_repo, (base.get("repo") or {}).get("commit"))
            if diff is not None:
                evidence["changed"], evidence["added"] = read_diff(diff)
            # only a test a person bound to values can be evidence: only those are run again, on both sides
            bound = {e["test"] for e in evidence["necessity"]}
            main_t, cand_t = evidence["main_tests"], evidence["candidate_tests"]
            asked = sorted(t for t in bound if main_t.get(t) == "failed" and cand_t.get(t) == "passed")
            evidence["confirmation"], evidence["confirmed"] = confirm(asked, args.base_repo, args.candidate_repo)
        reports.append(compare(base, cand, entries, evidence))
    report = merge_runs(reports)
    report["confirmation"] = evidence["confirmation"]
    args.json = args.json or str(out / "report.json")
    args.markdown = args.markdown or str(out / "report.md")
    return _finish(report, args)


def merge_runs(reports):
    """Several checks of the same change, each with its own keys and shape: the first run's report, with
    every row any other run found worse (or could not judge) added, every error, and the fingerprinting
    rows of all runs (a row worse in any run is worse)."""
    report = reports[0]
    report["runs"] = len(reports)
    seen = {(r["key"], r["detail"]) for r in report["worse"]}
    review = {(r["key"], r["detail"]) for r in report.get("fingerprint_review") or ()}
    for n, other in enumerate(reports[1:], 2):
        report["errors"] += ["run %d: %s" % (n, e) for e in other["errors"]]
        for r in other["worse"]:
            if (r["key"], r["detail"]) not in seen:
                seen.add((r["key"], r["detail"]))
                report["worse"].append(dict(r, detail="run %d: %s" % (n, r["detail"])))
                report["sections"].setdefault(r["section"], {}).setdefault("worse", 0)
                report["sections"][r["section"]]["worse"] += 1
        for r in other.get("fingerprint_review") or ():
            if (r["key"], r["detail"]) not in review:
                review.add((r["key"], r["detail"]))
                report.setdefault("fingerprint_review", []).append(dict(r, detail="run %d: %s" % (n, r["detail"])))
    report["verdict"] = "fail" if report["worse"] or report["errors"] else "pass"
    return report


if __name__ == "__main__":
    sys.exit(main())
