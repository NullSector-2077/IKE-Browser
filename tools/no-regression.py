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
  with a fixed noise key, and again with a second fixed key (a second session).
  What the protection disguises (FP_JUDGED: canvas, audio, WebGL, navigator,
  screen, fonts, Client Hints, time zone and language...) is judged by what
  protects, against the Off level's real value: worse when it is the real
  value again, no longer changes with the session, has a smaller noise, or
  shows more of a real list (_judge_fingerprint); a change that keeps the
  protection passes. For anything else: any value that differs from main
  cannot be judged, and is worse unless a test proves it needed (below);
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

What the rules cannot judge (a changed value with no rule of its own, a
disguised value main left real...) is "unjudged": worse, unless a test of its
area that fails on main passes here and this change touches the area's files
(the owner's principle of 2026-11-24: a change needed for I.K.E. to work and
for its protections to keep working is approved by the chain itself;
_by_necessity). No evidence accepts a weakening the rules see; only a person
does, in tests/data/no-regression/allowlist.json. The report says why each
difference passed: the rule, the evidence, or the person.

    no-regression.py snapshot --repo DIR --out FILE [--levels ...] [--sections ...]
    no-regression.py compare --base FILE --candidate FILE [--allowlist FILE] [--json OUT] [--markdown OUT]
        [--diff FILE] [--main-junit FILE ...] [--candidate-junit FILE ...] [--endpoints FILE]
    no-regression.py check --base-repo DIR --candidate-repo DIR [--out-dir DIR] [--allowlist FILE]
        [--diff FILE] [--main-junit FILE ...] [--candidate-junit FILE ...] [--endpoints FILE]

compare and check print "pass" or "fail" and exit 1 on "fail". Deterministic,
offline (local fixtures, a local server and proxy) and headless (offscreen),
like the automatic tests. tests.yml runs main's copy of this tool (the step
"Nothing gets worse"), so a candidate never judges itself with its own copy.
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
    r"^(canvas|canvas_blob|audio|frame|worker|media_queries"
    r"|webgl\.(vendor|renderer|unmasked_vendor|unmasked_renderer|max_texture|extensions|read_pixels)"
    r"|navigator\.(userAgent|appVersion|platform|vendor|product|productSub|oscpu|hardwareConcurrency|deviceMemory"
    r"|language|languages|plugins|mimeTypes|maxTouchPoints|pdfViewerEnabled)"
    r"|screen\.\w+|hints\.\w+|intl\.\w+|fonts_(measured|check|generic|computed))$")
# lists of names (comma separated): a disguised list that shows more of the real one (Off's), or comes
# closer to it, is worse; one randomised on main may change fewer names by LIST_TOLERANCE at most
FP_LISTS = {"fonts_measured", "fonts_check", "navigator.languages", "navigator.plugins", "webgl.extensions"}
LIST_TOLERANCE = 0.5
# what the probe hands over for the size of the noise only (not an observation) -> the value it belongs
# to: the canvas's noise measured by the page on a picture of known bytes, the audio samples themselves
SAMPLES = {"canvas_noise": "canvas", "audio_samples": "audio"}
# the size of the noise (the two sessions' average) may shrink by this share before it is worse
NOISE_TOLERANCE = 0.2
LEVEL_NAMES = {"off": "Off", "compatibility": "Compatibility", "balanced": "Balanced", "strict": "Strict",
               "maximum": "Maximum"}


# --- the probe page --------------------------------------------------------------------------
PROBE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="unsafe-url">
<title>nothing gets worse</title></head><body><p>probe</p>
<script>
(async function () {
  var R = {};
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
  function canvasHash(doc) {
    var c = doc.createElement('canvas'); c.width = 220; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. no regression ☺', 2, 10);
    x.strokeStyle = 'rgba(102,204,0,0.7)'; x.arc(160, 20, 15, 0, Math.PI * 2); x.stroke();
    return [hash(c.toDataURL()), hash(Array.from(x.getImageData(0, 0, 220, 40).data.slice(0, 4000)).join(',')),
            x.measureText('I.K.E. no regression').width];
  }
  function settle(p, ms, late) { return Promise.race([p, new Promise(function (ok) { setTimeout(function () { ok(late); }, ms); })]); }
  try { R.canvas = canvasHash(document); } catch (e) { R.canvas = 'error ' + e; }
  try {
    // the size of the canvas noise (SAMPLES in the tool): a picture of known varied opaque bytes read
    // back, the mean change of a byte (0 where nothing is noised)
    var nc = document.createElement('canvas'); nc.width = 128; nc.height = 128;
    var nx = nc.getContext('2d'), known = nx.createImageData(128, 128), kd = known.data, st = 12345, diff = 0;
    for (var ki = 0; ki < kd.length; ki++) {
      st = (Math.imul(st, 1103515245) + 12345) >>> 0;
      kd[ki] = ki % 4 === 3 ? 255 : st >>> 24;
    }
    nx.putImageData(known, 0, 0);
    var back = nx.getImageData(0, 0, 128, 128).data;
    for (var kj = 0; kj < kd.length; kj++) diff += Math.abs(back[kj] - kd[kj]);
    R.canvas_noise = diff / kd.length;
  } catch (e) { R.canvas_noise = 'error ' + e; }
  try {
    var bc = document.createElement('canvas'); bc.width = 64; bc.height = 16;
    var bx = bc.getContext('2d'); bx.fillStyle = '#123456'; bx.fillRect(0, 0, 64, 16); bx.fillStyle = '#fff'; bx.fillText('ike', 2, 12);
    R.canvas_blob = await settle(new Promise(function (ok) { bc.toBlob(function (b) {
      var fr = new FileReader(); fr.onload = function () { ok(hash(String(fr.result))); }; fr.readAsDataURL(b); }); }), 3000, 'timeout');
  } catch (e) { R.canvas_blob = 'error ' + e; }
  try {
    var gl = document.createElement('canvas').getContext('webgl');
    var dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
    var px = null;
    if (gl) { gl.clearColor(0.2, 0.4, 0.6, 1); gl.clear(gl.COLOR_BUFFER_BIT); var b = new Uint8Array(16); gl.readPixels(0, 0, 2, 2, gl.RGBA, gl.UNSIGNED_BYTE, b); px = Array.from(b).join(','); }
    R.webgl = gl ? {vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
      unmasked_vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      unmasked_renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      max_texture: gl.getParameter(gl.MAX_TEXTURE_SIZE), extensions: (gl.getSupportedExtensions() || []).join(','),
      read_pixels: px} : null;
  } catch (e) { R.webgl = 'error ' + e; }
  try {
    var ac = new OfflineAudioContext(1, 5000, 44100), o = ac.createOscillator(), comp = ac.createDynamicsCompressor();
    o.type = 'triangle'; o.frequency.value = 10000; o.connect(comp); comp.connect(ac.destination); o.start(0);
    var buf = await ac.startRendering(), d = buf.getChannelData(0), sum = 0;
    for (var i = 4500; i < 5000; i++) sum += Math.abs(d[i]);
    R.audio = sum.toFixed(10);
    R.audio_samples = Array.from(d.slice(4500, 5000));
  } catch (e) { R.audio = 'error ' + e; }
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
    R.worker = await new Promise(function (ok) {
      var src = "var c=null;try{var oc=new OffscreenCanvas(60,20),x=oc.getContext('2d');x.fillText('ike',2,10);" +
        "c=Array.from(x.getImageData(0,0,60,20).data).join(',').length}catch(e){c='e'}" +
        "var g=null;try{var gc=new OffscreenCanvas(4,4).getContext('webgl'),gd=gc&&gc.getExtension('WEBGL_debug_renderer_info');" +
        "g=gc?[gd?gc.getParameter(gd.UNMASKED_RENDERER_WEBGL):null,(gc.getSupportedExtensions()||[]).join(',')]:'none'}catch(e){g='e '+e}" +
        "postMessage([navigator.userAgent,navigator.platform,navigator.hardwareConcurrency,navigator.deviceMemory," +
        "(navigator.languages||[]).join(','),c,g])";
      var w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
      w.onmessage = function (e) { ok(e.data); };
      w.onerror = function () { ok('worker error'); };
      setTimeout(function () { ok('worker timeout'); }, 4000);
    });
  } catch (e) { R.worker = 'error ' + e; }
  try {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    var fw = f.contentWindow;
    R.frame = [fw.navigator.hardwareConcurrency, fw.navigator.userAgent, fw.navigator.plugins.length,
      fw.screen.width, canvasHash(fw.document)];
  } catch (e) { R.frame = 'error ' + e; }
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
    var est = await settle(navigator.storage.estimate(), 3000, null);
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
    im.src = 'http://__THIRD__/pixel.png?lv=__LV__'; document.body.appendChild(im); }), 4000, 'timeout');
  window.nrResult = JSON.stringify(R);
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

PLAN = json.load(open(os.environ["IKE_NR_PLAN"], encoding="utf-8"))
OUT = {"errors": []}
_gen = None
_FONT_WAIT = [0]


def _finish():
    try:
        net = sys.modules.get("ike_nr_net")
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
        for big in ("psl", "fonts"):
            if big in fpcfg:
                fpcfg[big] = "sha256 " + hashlib.sha256(json.dumps(fpcfg[big]).encode()).hexdigest()[:16]
    out["scripts"] = sorted(scripts)
    out["fingerprint_config"] = fpcfg
    return out


COSMETIC_JS = r"""(function(keys, probes){var out={}; keys.forEach(function(k){
 var e=document.querySelector('[data-nr="'+k+'"]'); if(!e){out[k]='removed';return;}
 var cs=getComputedStyle(e), r=e.getBoundingClientRect();
 out[k]=(cs.display==='none'||cs.visibility==='hidden'||cs.opacity==='0'||(r.width===0&&r.height===0))?'hidden':'shown';});
 var p={}; Object.keys(probes).forEach(function(k){try{p[k]=String((0,eval)(probes[k]))}catch(e){p[k]='error '+e.name}});
 return JSON.stringify({elements:out, probes:p});})(%s, %s)"""


def _keys(sh, key):
    for p in list(sh.profiles):
        sh.profile_keys[id(p)] = key


def _probe(view, tag, limit=40):
    """The probe page loaded at the level tag; (loaded, what its scripts read or None)."""
    state, box, found = {}, {}, None
    yield from _load(view, PLAN["base"] + "/fp?lv=" + tag, state, "ok")
    end = time.monotonic() + limit
    while time.monotonic() < end:
        yield from _js(view, "window.nrResult || ''", box)
        if box.get("r"):
            found = json.loads(box["r"])
            break
        yield 100
    return state.get("ok"), found


def _list_verdicts():
    """What the filter lists' own data says of each request of the corpus: an engine of this
    checkout built from the lists alone (not I.K.E.'s own rules), keeping the rules' text, gives the
    rule that blocks it, or the exception that lets it through, and the list each comes from; with
    a digest of each list's data. Only evidence ("Nothing gets worse" accepts a request newly let
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
    if "requests" in sections:
        _list_verdicts()
    try:
        _keys(sh, PLAN["key"])
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
            try:
                here["page_settings"] = _settings(view.page().settings())
                prof = view.page().profile()
                here["profile_settings"] = _settings(prof.settings())
                here["profile"] = _profile(prof)
            except Exception:
                _err("security")
        if "fingerprint" in sections and PLAN.get("key2"):
            # a second session: another noise key, as a new start of the browser has; what the
            # protection randomises must differ from the first. Its own tag ("<level>.s2"), so the
            # headers the server keeps for the level are the first session's.
            here["probe_session2"] = None
            try:
                _keys(sh, PLAN["key2"])
                sh.apply_settings()
            except Exception:
                _err("fingerprint")
            else:
                yield 50
                here["loaded_session2"], here["probe_session2"] = yield from _probe(view, lv + ".s2")
            try:
                _keys(sh, PLAN["key"])
                sh.apply_settings()
            except Exception:
                _err("fingerprint")
            yield 50
        if "cosmetic" in sections:
            pages = here["pages"] = {}
            for pg in PLAN["pages"]:
                state = {}
                yield from _load(view, "http://%s%s" % (pg["host"], pg["path"]), state, "ok")
                keys = [e["key"] for e in pg["elements"]]
                code = COSMETIC_JS % (json.dumps(keys), json.dumps(pg.get("probes") or {}))
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
    state = {}
    yield from _load(view, PLAN["base"] + "/fp?lv=network", state, "ok")
    box = {}
    end = time.monotonic() + 30
    while time.monotonic() < end:
        yield from _js(view, "window.nrResult || ''", box)
        if box.get("r"):
            break
        yield 100
    OUT["probe_loaded"] = state.get("ok")
    OUT["probe_done"] = bool(box.get("r"))
    yield 1500


def _start():
    global _gen
    # a fresh profile shows the welcome of the first start (1.1.24) before any window: it is
    # skipped as a new user skips it (the defaults kept), and the run waits for the first window.
    # This hook runs from main against the candidate, so it must know the welcome before the
    # version that brings it can pass "Nothing gets worse".
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
_mod = types.ModuleType("ike_nr_net")
_mod.hosts = _hosts
sys.modules["ike_nr_net"] = _mod


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
            raise OSError("no network while measuring (tools/no-regression.py): %s" % _name(host))
    elif event == "socket.connect":
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr and isinstance(addr[0], (str, bytes)) and not _local(addr[0]):
            _hosts.append(_name(addr[0]))
            raise OSError("no network while measuring (tools/no-regression.py): %s" % _name(addr[0]))


sys.addaudithook(_audit)
boot = sys.argv[1]
sys.argv = [boot] + sys.argv[2:]
sys.path[0] = os.path.dirname(os.path.abspath(boot))
runpy.run_path(boot, run_name="__main__")
'''


# --- the local server: probe pages, and the proxy every other address goes to ------------
class Server:
    """127.0.0.1: the probe page (direct) and, as the engine's and Qt's proxy, the pages of the corpus's
    hosts; any other host the browser asks for is recorded and refused (nothing leaves the computer)."""

    def __init__(self, corpus):
        self.pages = {p["host"]: p for p in corpus["pages"]}
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
                outer._record(host, "CONNECT")
                self.send_error(403)

            def _any(self):
                if self.path.startswith(("http://", "https://", "ws://", "wss://")):
                    u = urlsplit(self.path)
                    host = (u.hostname or "").lower()
                    if host not in outer.pages and host != THIRD:
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

    def _keep(self, which, lv, headers):
        port = str(self.port)
        kept = {}
        for k, v in headers.items():
            k = k.lower()
            if k in VOLATILE_HEADERS:
                continue
            kept[k] = re.sub(r":%s\b" % port, ":PORT", v)
        with self.lock:
            self.headers.setdefault(lv, {})[which] = kept

    def serve(self, host, path, query, headers):
        lv = (query.get("lv") or ["?"])[0]
        if host == "127.0.0.1" and path == "/fp":
            self._keep("page", lv, headers)
            return PROBE.replace("__THIRD__", THIRD).replace("__LV__", lv).encode("utf-8"), \
                "text/html; charset=utf-8"
        if host == THIRD and path == "/pixel.png":
            self._keep("third-party", lv, headers)
            return PNG, "image/png"
        page = self.pages.get(host)
        if page and path == page["path"]:
            parts = []
            for e in page["elements"]:
                html = e["html"]
                at = html.index(">")
                parts.append(html[:at] + ' data-nr="%s"' % e["key"] + html[at:])
            body = "<!doctype html><html><head><meta charset=\"utf-8\"><title>%s</title></head><body>%s</body></html>" \
                % (page["id"], "\n".join(parts))
            return body.encode("utf-8"), "text/html; charset=utf-8"
        return None, None

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


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


def run_browser(repo, mode, plan, settings, server, workdir, timeout):
    """Start the checkout's I.K.E. with a profile of its own in workdir; returns the hook's output."""
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
    hook, wrapper = workdir / "nr_hook.py", workdir / "nr_wrapper.py"
    hook.write_text(HOOK, "utf-8")
    wrapper.write_text(WRAPPER, "utf-8")
    out = workdir / "hook-out.json"
    plan = dict(plan, mode=mode, out=str(out), base=server.base)
    (workdir / "plan.json").write_text(json.dumps(plan), "utf-8")
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
        "IKE_NO_SINGLE": "1", "IKE_TEST_NOASK": "1", "IKE_TEST_HOOK": str(hook), "IKE_NR_PLAN": str(workdir / "plan.json"),
        "DBUS_SESSION_BUS_ADDRESS": "",
        "http_proxy": proxy, "https_proxy": proxy, "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy,
        "all_proxy": proxy, "ALL_PROXY": proxy, "no_proxy": "127.0.0.1,localhost", "NO_PROXY": "127.0.0.1,localhost",
    })
    cmd = [sys.executable, str(wrapper), str(Path(repo).resolve() / "ike_boot.py")]
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        code, stderr = proc.returncode, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code, stderr = "timeout", (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) \
            else (exc.stderr or "")
    if not out.exists():
        return {"errors": [{"section": mode, "error": "the browser ended without results (exit %s): %s"
                            % (code, stderr[-2000:])}]}
    data = json.loads(out.read_text("utf-8"))
    data["exit"] = code
    return data


def snapshot(repo, levels=LEVELS, sections=SECTIONS, fixtures=FIXTURES, keep=None, settle=6.0):
    """The behaviour snapshot of the checkout in `repo` (a dict, see FORMAT)."""
    repo = Path(repo).resolve()
    corpus = load_corpus(fixtures)
    t0 = time.monotonic()
    plan = {"levels": list(levels), "sections": list(sections), "lists": corpus["lists"],
            "requests": corpus["requests"], "pages": corpus["pages"], "cosmetic_urls": corpus["cosmetic_urls"],
            "scriptlet_hosts": corpus["scriptlet_hosts"], "key": FIXED_KEY, "key2": FIXED_KEY_2,
            "defaults": sorted(SAFE_DEFAULTS),
            "hostile_flags": HOSTILE_FLAGS, "hostile_env": HOSTILE_ENV, "settle": settle}
    quiet = {"lists_version": _lists_version(repo), "last_lists_update": 4102444800,
             "last_fast_update": 4102444800, "chrome_checked": 4102444800, "app_updates": "off",
             "auto_update": False, "newtab_bg": "", "newtab_bg_118": True, "app_updates_1113": True,
             "site_opts": {p["host"]: {"https": False} for p in corpus["pages"]}}
    server = Server(corpus)
    raw = {}
    tmp = tempfile.mkdtemp(prefix="ike-nr-") if keep is None else str(keep)
    try:
        measured = [s for s in sections if s != "network"]
        if measured:
            raw["measure"] = run_browser(repo, "measure", plan, quiet, server, Path(tmp) / "measure", timeout=420)
            raw["measure"]["proxy_hosts"] = server.take()
            with server.lock:
                raw["measure"]["headers"] = server.headers
                server.headers = {}
        if "network" in sections:
            # a fresh profile, every default as a new user has it: what the browser contacts by itself
            raw["network"] = run_browser(repo, "network", dict(plan, lists={}), None, server,
                                         Path(tmp) / "network", timeout=180)
            raw["network"]["proxy_hosts"] = server.take()
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
    # the digest of each filter list's data the requests were measured with (evidence for a request
    # newly let through: the list data that decides it changed)
    snap["list_data"] = (raw.get("measure") or {}).get("list_data")
    snap["raw"] = raw
    return snap


def _change(repo, since):
    """git's diff of the checkout's HEAD from the commit `since` (None when git cannot give it)."""
    if not since:
        return None
    try:
        proc = subprocess.run(["git", "-C", str(repo), "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                               since, "HEAD"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


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


def observations(raw, levels, sections, corpus):
    """(errors, {key: {"rule", "value"}}) from what the browser recorded."""
    errors, obs = [], {}
    for part in ("measure", "network"):
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
            probe, second = here.get("probe"), here.get("probe_session2")
            if probe is None:
                errors.append({"section": "fingerprint", "error": "the probe page gave no result at %s" % lv})
            else:
                if "probe_session2" in here and second is None:
                    errors.append({"section": "fingerprint", "error": "the probe page gave no result at %s in "
                                                                      "the second session" % lv})
                fp, fp2 = {}, {}
                _flat("", {k: v for k, v in probe.items() if k not in SAMPLES}, fp, "exact")
                if second is not None:
                    _flat("", {k: v for k, v in second.items() if k not in SAMPLES}, fp2, "exact")
                off = ((m.get("levels") or {}).get("off") or {}).get("probe") or {}
                for k, o in fp.items():
                    if k in fp2:
                        o["session2"] = fp2[k]["value"]
                    if lv != "off" and FP_JUDGED.match(k):
                        o["rule"] = "fingerprint"
                    if lv != "off" and k in SAMPLES.values() and off:
                        o["noise"] = _noise(k, [x for x in (probe, second) if x is not None], off)
                if lv != "off" and off:
                    for k in ("canvas", "canvas_blob", "audio"):
                        fp["%s.noised" % k] = {"rule": "safer-true", "value": probe.get(k) != off.get(k)}
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
                elif k == "fingerprint_config":
                    fc = {}
                    _flat("", v if isinstance(v, dict) else {"config": v}, fc, "exact")
                    for kk, vv in fc.items():
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
        n = raw.get("network") or {}
        hosts = set(n.get("proxy_hosts") or []) | set(n.get("python_hosts") or [])
        obs["network/fresh-profile"] = {"rule": "no-new", "value": sorted(hosts)}
        if n and not n.get("probe_done"):
            errors.append({"section": "network", "error": "the probe page did not finish in the fresh profile"})
    if m:
        hosts = set(m.get("proxy_hosts") or []) | set(m.get("python_hosts") or [])
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
    if cand is None and rule not in ("no-new",):
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
def _noise(key, probes, off):
    """The size of the noise, the sessions' average: the mean relative change of the audio samples
    from Off's (the real ones), the mean change of a byte of the canvas of known bytes (the page
    measures it: 0 at Off). None when it cannot be measured."""
    raw = next(r for r, k in SAMPLES.items() if k == key)
    real = off.get(raw)
    sizes = []
    for p in probes:
        got = p.get(raw)
        try:
            if key == "audio":
                pairs = [(float(a), float(b)) for a, b in zip(got, real) if float(b) != 0.0]
                if len(got) != len(real) or not pairs:
                    return None
                sizes.append(sum(abs(a / b - 1.0) for a, b in pairs) / len(pairs))
            elif isinstance(got, (int, float)) and not isinstance(got, bool):
                sizes.append(float(got))
            else:
                return None
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return float("%.6g" % (sum(sizes) / len(sizes))) if sizes else None


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


def _judge_part(name, path, b, c):
    """One part of a disguised value. b = (main, main's second session, Off on main, Off's second
    session on main), c = the same here; MISSING where not measured.
    (kind, why): "same", "changed" (still protected), "worse" (weaker) or "unjudged" (it cannot be
    judged: worse too, unless evidence accepts it)."""
    vb, vb2, ob, ob2 = b
    vc, vc2, oc, oc2 = c
    if vb == vc and (vb2 is MISSING or vc2 is MISSING or vb2 == vc2):
        return "same", ""
    if vc is MISSING:
        return "unjudged", "not read here"
    if isinstance(vc, str) and FAILED.match(vc):
        return "unjudged", "could not be read here (%s)" % _short(vc, 60)
    if ob is MISSING or oc is MISSING:
        return "unjudged", "cannot be judged: the Off level was not measured"
    if vb == ob:
        return "unjudged", "main gave the real value (Off's): a change of it cannot be judged"
    if vc == oc or vc2 == oc:
        return "worse", "the real value (Off's) here"
    if vb is None:
        return "worse", "hidden on main, readable here"
    if (ob2 is not MISSING and ob2 != ob) or (oc2 is not MISSING and oc2 != oc):
        return "unjudged", "cannot be judged: it changes from one session to the next at Off too"
    names = not path and name in FP_LISTS and all(isinstance(x, str) for x in (vb, vc, ob, oc))
    if names and vb2 in (MISSING, vb):
        # a fixed list on main: no name of the real list that main did not show, and no closer to it
        shown = sorted((_names(vc) | _names(vc2)) & _names(oc) - _names(vb))
        if shown:
            return "worse", "shows more of the real list: %s" % ", ".join(shown[:8])
        near = min(_far(x, oc) for x in (vc, vc2) if isinstance(x, str))
        if near < _far(vb, ob):
            return "worse", "closer to the real list: %d names differ from it on main, %d here" % (_far(vb, ob), near)
    if vb2 is MISSING:
        if vc2 is not MISSING and vc2 != vc:
            return "changed", "still not the real value, and different in each session"
        return "unjudged", "cannot be judged: main's second session was not measured"
    if vb2 != vb:
        if vc2 is MISSING:
            return "unjudged", "cannot be judged: no second session measured here"
        if vc2 == vc:
            return "worse", "the same in every session here (on main it changed with the session)"
        if names and isinstance(vb2, str) and isinstance(vc2, str):
            # a list randomised on main: as many names changed from the real list (the sessions' average)
            far_b, far_c = (_far(vb, ob) + _far(vb2, ob)) / 2.0, (_far(vc, oc) + _far(vc2, oc)) / 2.0
            if far_c < far_b * (1 - LIST_TOLERANCE):
                return "worse", "fewer names changed from the real list: %g on main, %g here" % (far_b, far_c)
        return "changed", "still noised (not the real value) and different in each session"
    return "changed", "another disguised value, still not the real one"


def _judge_fingerprint(key, b, c, bo, co):
    """A value the fingerprinting protection disguises (FP_JUDGED), judged by what protects, part by
    part (_parts), on main and here, each against the Off level of its own snapshot (the real value)
    and its own second session:
    - randomised on main (it changed with the session): still not the real value, still different
      in each session, and the size of its noise not smaller than main's: `noise` (audio, canvas)
      by NOISE_TOLERANCE at most ("stricter" when larger beyond it), the names a list changes
      (FP_LISTS) by LIST_TOLERANCE at most;
    - a fixed disguise on main: still not the real value in either session and, a list of names,
      showing no name of the real list main did not show and coming no closer to the real list;
    - the real value on main, the Off level not measured, a part that could not be read, a value
      that changes between sessions at Off too: "unjudged" (worse, unless evidence accepts it).
    bo, co: every observation of main's snapshot and of the candidate's. (kind, detail): a weaker part
    makes it "worse" whatever the other parts are."""
    if c is None:
        return "unjudged", "not measured on the candidate"
    if b is None:
        return "unjudged", "not measured on main: a new value cannot be judged"
    head, _, name = key.split("/", 2)
    offkey = "%s/off/%s" % (head, name)

    def split(o, field):
        return _parts(o[field], name) if o is not None and field in o else None

    def at(parts, path):
        return MISSING if parts is None else parts.get(path, MISSING)

    main = [split(b, "value"), split(b, "session2"), split(bo.get(offkey), "value"), split(bo.get(offkey), "session2")]
    here = [split(c, "value"), split(c, "session2"), split(co.get(offkey), "value"), split(co.get(offkey), "session2")]
    found = {"worse": [], "unjudged": [], "changed": []}
    for path in sorted(set(main[0]) | set(here[0])):
        kind, why = _judge_part(name, path, tuple(at(x, path) for x in main), tuple(at(x, path) for x in here))
        if kind != "same":
            found[kind].append(("%s %s" % (path, why)) if path else why)
    why = found["worse"] + found["unjudged"]
    why = "; ".join(why[:6]) + ("; and %d more parts" % (len(why) - 6) if len(why) > 6 else "")
    if found["worse"]:                 # a weaker part decides, whatever the other parts are
        return "worse", why
    # the size of the noise is judged even when a part cannot be: a smaller noise is a weakening
    nb, nc = b.get("noise"), c.get("noise")
    noise = None
    if isinstance(nb, (int, float)) and nb > 0:
        if not isinstance(nc, (int, float)):
            noise = "unjudged", "the size of the noise could not be measured here (%s on main)" % nb
        elif nc < nb * (1 - NOISE_TOLERANCE):
            return "worse", "the noise is smaller: %s on main, %s here" % (nb, nc)
        elif nc > nb * (1 + NOISE_TOLERANCE):
            noise = "stricter", "still protected, the noise larger: %s on main, %s here (x%.3g)" % (nb, nc, nc / nb)
        else:
            noise = "changed", "still protected, the noise as large: %s on main, %s here" % (nb, nc)
    if found["unjudged"]:
        return "unjudged", why
    if not found["changed"]:           # the same parts, written another way: nothing to judge them by
        return "unjudged", "written another way, the same parts: cannot be judged"
    return noise or ("changed", "still protected: " + "; ".join(found["changed"][:4]))


def _rule(key, b, c):
    """The rule of an observation: this copy's own for the disguised fingerprinting values
    (FP_JUDGED) and the .noised marks, whatever rule the snapshots carry (one of an older copy is
    judged the same way); otherwise the one main's snapshot gives."""
    parts = key.split("/", 2)
    if parts[0] == "fingerprint" and len(parts) == 3 and parts[1] != "off":
        if FP_JUDGED.match(parts[2]):
            return "fingerprint"
        if parts[2].endswith(".noised"):
            return "safer-true"
    return (b or c)["rule"]


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


def _accepted(entries, key, base, cand):
    for i, e in enumerate(entries):
        if not fnmatch.fnmatchcase(key, e["key"]):
            continue
        if "base" in e and e["base"] != base:
            continue
        if "candidate" in e and e["candidate"] != cand:
            continue
        return i
    return None


# --- evidence: what lets a change the rules call worse pass with no person ------------------------
# Necessity (2026-11-24, the owner's principle: a change needed for I.K.E. to work and for its
# protections to keep working is approved by the chain itself): a test that fails on main and passes
# here shows the change is needed. It accepts only what the rules cannot judge ("unjudged"), never a
# weakening, in an area whose files this change touches, with a test of that area. Never a security
# setting (no exceptions), a request or a host: those have their own evidence below, or none.
# (area, observation keys, the area's files, its tests as "file::name" globs)
NECESSITY = (
    ("fingerprinting", ("fingerprint/", "fingerprint-config/"),
     ("ike/resources/fingerprint.js", "ike/shields.py", "ike/osinfo.py", "ike/fontcheck.py"),
     ("tests/test_fingerprint*.py::*", "tests/test_client_hints.py::*", "*::*fp*", "*::*fingerprint*",
      "*::*noise*", "*::*canvas*", "*::*audio*", "*::*webgl*", "*::*font*")),
    ("the pages' scriptlets", ("page-scriptlets/",),
     ("ike/blocker.py", "ike/scriptlets.py", "ike/shields.py", "ike/resources/*"),
     ("tests/test_adblock.py::*", "*::*scriptlet*")),
)
# I.K.E.'s known external endpoints: a host contacted by itself that main does not contact passes
# only when it is declared there and this change's own code names it. Only a person (or Claude,
# with the change read in full) edits it: it is under tests/, as the allowlist
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
    "fingerprint": "judged by what protects: still disguised (the fingerprinting rules)",
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
    """(changed files, the lines this change adds outside tests/) from the output of git's diff."""
    changed, added, path = set(), [], None
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            if m:
                changed.update(m.groups())
                path = m.group(2)
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and path and not path.startswith("tests/"):
            added.append(line[1:])
    return sorted(changed), "\n".join(added)


def load_endpoints(path):
    """The declared endpoints [{"host", "purpose", ...}]; none when the file cannot be read."""
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data.get("endpoints") or () if isinstance(e, dict) and e.get("host") and
            str(e.get("purpose") or "").strip()]


def _fixed_tests(evidence):
    main_t, cand_t = evidence.get("main_tests") or {}, evidence.get("candidate_tests") or {}
    return sorted(t for t, st in main_t.items() if st == "failed" and cand_t.get(t) == "passed")


def _by_necessity(row, evidence):
    """Why a change the rules cannot judge is needed: a test of its area that fails on main passes
    here, and this change touches the area's files. Never in the security settings."""
    if row["section"] == "security":
        return None
    fixed = _fixed_tests(evidence)
    for area, keys, files, tests in NECESSITY:
        if not row["key"].startswith(keys):
            continue
        touched = sorted(f for f in evidence.get("changed") or () if any(fnmatch.fnmatchcase(f, g) for g in files))
        proof = [t for t in fixed if any(fnmatch.fnmatchcase(t, g) for g in tests)]
        if touched and proof:
            return "needed (%s): the test %s fails on main and passes here, and this change touches %s" % (
                area, proof[0], ", ".join(touched[:3]))
    return None


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
    """Why new hosts pass: each is declared (ENDPOINTS) and named by this change's own code."""
    if not key.startswith("network/"):
        return None
    new = sorted(set(cv or []) - set(bv or []))
    known = {e["host"]: e for e in evidence.get("endpoints") or ()}
    added = evidence.get("added")
    def named(h):          # the host itself, not a longer name that ends or starts with it
        return re.search(r"(?<![\w.-])%s(?![\w-]|\.\w)" % re.escape(h), added) is not None
    if not new or added is None or any(h not in known or not named(h) for h in new):
        return None
    return "declared endpoints (tests/data/no-regression/endpoints.json), named by this change's code: %s" % (
        "; ".join("%s, %s" % (h, known[h]["purpose"]) for h in new))


def compare(base, cand, allowlist_entries=(), evidence=None):
    """The report: every observation of both snapshots judged; verdict "pass" or "fail". A change the
    rules call worse passes only by evidence (_by_necessity for what they cannot judge, never for a
    weakening; _by_lists for a request; _by_registry for a host) or by a person (the allowlist).
    Every row that passed says why ("why", "passed_by"). evidence: {"changed": [files], "added": the
    lines this change adds outside tests/, "main_tests" and "candidate_tests": read_junit(),
    "endpoints": load_endpoints()}; a part that is missing gives no evidence."""
    evidence = evidence or {}
    rows = {"worse": [], "evidence": [], "accepted": [], "stricter": [], "changed": []}
    used = set()
    errors = []
    for side, snap in (("main", base), ("candidate", cand)):
        if snap.get("format") != FORMAT:
            errors.append("%s: a snapshot of another format (%r)" % (side, snap.get("format")))
        for e in snap.get("errors") or ():
            last = ((e.get("error") or "").strip().splitlines() or ["?"])[-1]
            errors.append("%s, %s: %s" % (side, e.get("section"), last[:300]))
    bo, co = base.get("observations") or {}, cand.get("observations") or {}
    order = ("blocking", "fingerprinting", "network", "security")
    for key in sorted(set(bo) | set(co), key=lambda k: (order.index(_section(k)), k)):
        if key.startswith("request-headers/"):
            rk = "requests/%s/%s" % tuple(key.split("/")[1:3])
            if (bo.get(rk) or {}).get("value") != (co.get(rk) or {}).get("value"):
                continue          # the request itself is judged; its headers follow what it became
        b, c = bo.get(key), co.get(key)
        rule = _rule(key, b, c)
        bv, cv = (b or {}).get("value"), (c or {}).get("value")
        if rule == "fingerprint" and (bv != cv or (b and c and "session2" in b and "session2" in c and
                                                   b["session2"] != c["session2"])):
            kind, detail = _judge_fingerprint(key, b, c, bo, co)
        else:
            kind, detail = _judge(rule, bv, cv, key)
        if kind == "same":
            continue
        row = {"key": key, "section": _section(key), "rule": rule, "main": bv, "candidate": cv, "detail": detail}
        if kind not in ("worse", "unjudged"):
            row.update(why="the rule `%s`: %s" % (rule, RULE_WHY.get(rule, "not weaker")), passed_by="rule")
            rows[kind].append(row)
            continue
        row["weakening"] = kind == "worse"
        if kind == "unjudged":
            why, by = _by_necessity(row, evidence), "necessity"
        elif rule == "block":
            why, by = _by_lists(key, b, c, base, cand), "lists"
        elif rule == "no-new":
            why, by = _by_registry(key, bv, cv, evidence), "registry"
        else:
            why, by = None, None
        if why:
            row.update(why=why, passed_by=by)
            rows["evidence"].append(row)
            continue
        i = _accepted(allowlist_entries, key, bv, cv)
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
    return {"verdict": verdict, "errors": errors, "main": {k: base.get(k) for k in info},
            "candidate": {k: cand.get(k) for k in info}, "compared": counts,
            "sections": sections, "unused_allowlist": [e for i, e in enumerate(allowlist_entries) if i not in used],
            "evidence_read": {"changed_files": len(evidence["changed"]) if evidence.get("changed") is not None
                              else None,
                              "main_tests": len(evidence.get("main_tests") or ()),
                              "candidate_tests": len(evidence.get("candidate_tests") or ()),
                              "fixed_tests": _fixed_tests(evidence),
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
        out.append("**Passed**: nothing that main does for its users is weaker on this commit.")
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
        out += ["", "Evidence read: %s; the tests of main (%d) and of this commit (%d): %s; %d declared "
                "endpoints." % (
                    "the files of this change not known" if files is None else
                    "%d file%s this change touches" % (files, "" if files == 1 else "s"),
                    ev.get("main_tests", 0), ev.get("candidate_tests", 0),
                    "fixed here: %s" % ", ".join("`%s`" % t for t in fixed[:10]) if fixed else
                    "none fails on main and passes here", ev.get("endpoints", 0))]
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
                                   "cannot be judged: a test of its area that fails on main and passes here, "
                                   "with this change touching the area, shows it is needed")
            elif r.get("why"):
                line += " (%s: %s)" % ("accepted" if kind == "accepted" else "passed", r["why"])
            out.append(line[:700])
        if len(rows) > limit:
            out.append("- and %d more (the JSON report has them all)" % (len(rows) - limit))
    if report["unused_allowlist"]:
        out += ["", "Allowlist entries that matched nothing (a person may remove them): %s." % ", ".join(
            "`%s`" % e["key"] for e in report["unused_allowlist"][:20])]
    return "\n".join(out) + "\n"


def _write(path, text):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, "utf-8")


def _finish(report, args):
    _write(getattr(args, "json", None), json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
    _write(getattr(args, "markdown", None), markdown(report))
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
    for x in (c, k):
        x.add_argument("--main-junit", action="append", default=[],
                       help="pytest's junit file of main's tests (evidence: a test that fails there)")
        x.add_argument("--candidate-junit", action="append", default=[],
                       help="pytest's junit file of the candidate's tests (evidence: that test passes here)")
        x.add_argument("--endpoints", default=str(ENDPOINTS), help="I.K.E.'s declared external endpoints")
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
                "endpoints": load_endpoints(args.endpoints)}
    if args.cmd == "compare":
        base = json.loads(Path(args.base).read_text("utf-8"))
        cand = json.loads(Path(args.candidate).read_text("utf-8"))
        if args.diff:
            evidence["changed"], evidence["added"] = read_diff(Path(args.diff).read_text("utf-8", "replace"))
        return _finish(compare(base, cand, entries, evidence), args)
    out = Path(args.out_dir)
    base = snapshot(args.base_repo, fixtures=args.fixtures)
    _write(out / "main.json", json.dumps(base, indent=1, ensure_ascii=False, default=str) + "\n")
    cand = snapshot(args.candidate_repo, fixtures=args.fixtures)
    _write(out / "candidate.json", json.dumps(cand, indent=1, ensure_ascii=False, default=str) + "\n")
    diff = Path(args.diff).read_text("utf-8", "replace") if args.diff else \
        _change(args.candidate_repo, (base.get("repo") or {}).get("commit"))
    if diff is not None:
        evidence["changed"], evidence["added"] = read_diff(diff)
    report = compare(base, cand, entries, evidence)
    args.json = args.json or str(out / "report.json")
    args.markdown = args.markdown or str(out / "report.md")
    return _finish(report, args)


if __name__ == "__main__":
    sys.exit(main())
