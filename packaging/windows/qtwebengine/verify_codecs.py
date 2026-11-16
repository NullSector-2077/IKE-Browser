#!/usr/bin/env python3
"""Checks what an installed PyQt6 + Qt WebEngine really plays.

Used by the workflow ``windows-engine.yml`` after the engine is built: small
clips are made with FFmpeg on the runner (FFmpeg only makes the test clips; it
is not part of I.K.E.), served from this computer, and played in a real
QWebEngineView. A clip counts as played only when the engine decoded it:
pictures counted, their colours read back, audio bytes counted. The names of
the decoders the engine chose are read from its media log through the remote
debugging port.

    python verify_codecs.py clips   --out DIR
    python verify_codecs.py overlay --package DIR      (copies the built engine
                                                        over the installed one)
    python verify_codecs.py run     --clips DIR --expect patched|stock
                                    --name NAME --report DIR [--flags "..."]

``--expect stock`` is the control: with the engine from PyPI the H.264 / AAC
clips must NOT play. If they did, this check would prove nothing.
"""

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

# name, tags, how it is made. Every picture is four coloured quarters (red,
# green / blue, white), so a wrong plane order or row length shows in the
# colours read back.
VIDEO_SIZES = {"320": (320, 240), "854": (854, 480), "1280": (1280, 720), "1920": (1920, 1080)}

AAC = ["-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2"]
FRAGMENTED = ["-movflags", "frag_keyframe+empty_moov+default_base_moof"]


def x264(profile, extra=()):
    return ["-c:v", "libx264", "-profile:v", profile, "-pix_fmt", "yuv420p", "-g", "25",
            "-preset", "veryfast", *extra]


# file name: (video size or None, with audio, ffmpeg output options)
CLIPS = {
    "h264_baseline_aac_320.mp4": ("320", True, x264("baseline") + AAC + ["-movflags", "+faststart"]),
    "h264_high_aac_854.mp4": ("854", True, x264("high", ["-bf", "2"]) + AAC + ["-movflags", "+faststart"]),
    "h264_main_aac_1920.mp4": ("1920", True, x264("main") + AAC + ["-movflags", "+faststart"]),
    "h264_high_1280_noaudio.mp4": ("1280", False, x264("high") + ["-movflags", "+faststart"]),
    "aac_lc.m4a": (None, True, AAC + ["-movflags", "+faststart"]),
    "aac_lc_mono_48k.m4a": (None, True, ["-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "1",
                                         "-movflags", "+faststart"]),
    "mse_h264_high_854.mp4": ("854", False, x264("high", ["-bf", "2"]) + FRAGMENTED),
    "mse_h264_main_1280.mp4": ("1280", False, x264("main") + FRAGMENTED),
    "mse_aac_lc.mp4": (None, True, AAC + FRAGMENTED),
    "vp9_opus_320.webm": ("320", True, ["-c:v", "libvpx-vp9", "-b:v", "300k", "-deadline", "realtime",
                                        "-cpu-used", "8", "-pix_fmt", "yuv420p",
                                        "-c:a", "libopus", "-b:a", "64k"]),
    "mp3.mp3": (None, True, ["-c:a", "libmp3lame", "-b:a", "96k"]),
}
# Optional: only made when this FFmpeg has the encoder.
OPTIONAL_CLIPS = {
    "h264_high_heaac_320.mp4": ("libfdk_aac", "320", True,
                                x264("high") + ["-c:a", "libfdk_aac", "-profile:a", "aac_he",
                                                "-b:a", "48k", "-ar", "44100", "-ac", "2",
                                                "-movflags", "+faststart"]),
    "av1_opus_320.webm": ("libsvtav1", "320", True,
                          ["-c:v", "libsvtav1", "-preset", "12", "-pix_fmt", "yuv420p",
                           "-c:a", "libopus", "-b:a", "64k"]),
}

H264 = 'video/mp4; codecs="avc1.640028"'
H264_MAIN = 'video/mp4; codecs="avc1.4D401F"'
AAC_TYPE = 'audio/mp4; codecs="mp4a.40.2"'

# name, what must decode ("h264", "aac": the formats under test; "free": the
# controls), element, source
CASES = [
    {"name": "file H.264 Baseline + AAC-LC 320x240", "tags": ["h264", "aac"],
     "url": "h264_baseline_aac_320.mp4", "video": "320", "audio": True},
    {"name": "file H.264 High (B-frames) + AAC-LC 854x480", "tags": ["h264", "aac"],
     "url": "h264_high_aac_854.mp4", "video": "854", "audio": True},
    {"name": "file H.264 Main + AAC-LC 1920x1080", "tags": ["h264", "aac"],
     "url": "h264_main_aac_1920.mp4", "video": "1920", "audio": True},
    {"name": "file H.264 High 1280x720, no audio", "tags": ["h264"],
     "url": "h264_high_1280_noaudio.mp4", "video": "1280", "audio": False},
    {"name": "file AAC-LC stereo 44.1 kHz (m4a)", "tags": ["aac"],
     "url": "aac_lc.m4a", "video": None, "audio": True},
    {"name": "file AAC-LC mono 48 kHz (m4a)", "tags": ["aac"],
     "url": "aac_lc_mono_48k.m4a", "video": None, "audio": True},
    {"name": "Media Source H.264 High 854x480 + AAC-LC (two buffers)", "tags": ["h264", "aac"],
     "mse": [{"url": "mse_h264_high_854.mp4", "type": H264},
             {"url": "mse_aac_lc.mp4", "type": AAC_TYPE}], "video": "854", "audio": True},
    {"name": "Media Source H.264 Main 1280x720, video only", "tags": ["h264"],
     "mse": [{"url": "mse_h264_main_1280.mp4", "type": H264_MAIN}], "video": "1280", "audio": False},
    {"name": "Media Source AAC-LC, audio only", "tags": ["aac"],
     "mse": [{"url": "mse_aac_lc.mp4", "type": AAC_TYPE}], "video": None, "audio": True},
    {"name": "control: file VP9 + Opus 320x240 (WebM)", "tags": ["free"],
     "url": "vp9_opus_320.webm", "video": "320", "audio": True},
    {"name": "control: file MP3", "tags": ["free"],
     "url": "mp3.mp3", "video": None, "audio": True},
]
OPTIONAL_CASES = {
    "h264_high_heaac_320.mp4": {"name": "file H.264 High + HE-AAC 320x240", "tags": ["h264", "aac"],
                                "url": "h264_high_heaac_320.mp4", "video": "320", "audio": True},
    "av1_opus_320.webm": {"name": "control: file AV1 + Opus 320x240 (WebM)", "tags": ["free"],
                          "url": "av1_opus_320.webm", "video": "320", "audio": True},
}

# What the engine declares. True: must be playable with the patched engine.
PROBES = [
    ("H.264 Baseline", 'video/mp4; codecs="avc1.42E01E"', True),
    ("H.264 Main", 'video/mp4; codecs="avc1.4D401F"', True),
    ("H.264 High", 'video/mp4; codecs="avc1.640028"', True),
    ("H.264 High 10 (10 bit)", 'video/mp4; codecs="avc1.6E0028"', False),
    ("AAC-LC", 'audio/mp4; codecs="mp4a.40.2"', True),
    ("HE-AAC", 'audio/mp4; codecs="mp4a.40.5"', True),
    ("H.264 + AAC", 'video/mp4; codecs="avc1.640028, mp4a.40.2"', True),
    ("HEVC", 'video/mp4; codecs="hvc1.1.6.L93.B0"', False),
    ("VP9", 'video/webm; codecs="vp9"', None),
    ("AV1", 'video/mp4; codecs="av01.0.05M.08"', None),
    ("Opus", 'audio/webm; codecs="opus"', None),
    ("MP3", "audio/mpeg", None),
]

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>I.K.E. codec check</title></head>
<body style="background:#222;color:#ddd;font:14px sans-serif">
<p id="status">waiting</p>
<canvas id="canvas" width="128" height="96"></canvas>
<script>
"use strict";
const CASES = __CASES__;
const PROBES = __PROBES__;
function report(tag, value) { console.log("IKE:" + tag + ":" + JSON.stringify(value)); }
function sleep(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

function probe() {
  const video = document.createElement("video"), out = [];
  PROBES.forEach(function (entry) {
    let mse = false;
    try { mse = !!(window.MediaSource && MediaSource.isTypeSupported(entry[1])); } catch (e) {}
    out.push({name: entry[0], type: entry[1], canPlayType: video.canPlayType(entry[1]), mediaSource: mse});
  });
  return out;
}

// Mean colour of five points around the middle of each quarter of the picture.
function quarters(element) {
  const canvas = document.getElementById("canvas"), context = canvas.getContext("2d", {willReadFrequently: true});
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(element, 0, 0, canvas.width, canvas.height);
  const out = [];
  [[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]].forEach(function (centre) {
    const sum = [0, 0, 0];
    [[0, 0], [-0.12, -0.12], [0.12, -0.12], [-0.12, 0.12], [0.12, 0.12]].forEach(function (offset) {
      const x = Math.round((centre[0] + offset[0]) * canvas.width);
      const y = Math.round((centre[1] + offset[1]) * canvas.height);
      const pixel = context.getImageData(x, y, 1, 1).data;
      sum[0] += pixel[0]; sum[1] += pixel[1]; sum[2] += pixel[2];
    });
    out.push([Math.round(sum[0] / 5), Math.round(sum[1] / 5), Math.round(sum[2] / 5)]);
  });
  return out;
}

async function appendAll(mediaSource, parts) {
  for (const part of parts) {
    if (!MediaSource.isTypeSupported(part.type)) {
      throw new Error("MediaSource.isTypeSupported is false for " + part.type);
    }
    const buffer = mediaSource.addSourceBuffer(part.type);
    const data = await (await fetch(part.url)).arrayBuffer();
    await new Promise(function (resolve, reject) {
      buffer.addEventListener("updateend", resolve, {once: true});
      buffer.addEventListener("error", function () { reject(new Error("SourceBuffer error for " + part.url)); }, {once: true});
      buffer.appendBuffer(data);
    });
  }
  mediaSource.endOfStream();
}

async function runCase(test) {
  document.title = "case:" + test.name;
  document.getElementById("status").textContent = test.name;
  const result = {name: test.name};
  const element = document.createElement(test.video ? "video" : "audio");
  element.volume = 0.05;
  element.preload = "auto";
  if (test.video) { element.width = 320; element.playsInline = true; }
  document.body.appendChild(element);

  let finish;
  const finished = new Promise(function (resolve) { finish = resolve; });
  const timer = setTimeout(function () { finish("timeout"); }, 20000);
  element.addEventListener("error", function () { finish("error"); });
  element.addEventListener("ended", function () { finish("ended"); });
  element.addEventListener("timeupdate", function () { if (element.currentTime >= 1.0) { finish("played"); } });
  try {
    if (test.mse) {
      const mediaSource = new MediaSource();
      element.src = URL.createObjectURL(mediaSource);
      await new Promise(function (resolve) { mediaSource.addEventListener("sourceopen", resolve, {once: true}); });
      await appendAll(mediaSource, test.mse);
    } else {
      element.src = test.url;
    }
    await element.play();
  } catch (error) {
    result.exception = String(error);
    finish("exception");
  }
  result.outcome = await finished;
  clearTimeout(timer);
  // Let a picture reach the screen before reading it back.
  await sleep(150);
  result.currentTime = element.currentTime;
  result.duration = isFinite(element.duration) ? element.duration : null;
  result.readyState = element.readyState;
  result.error = element.error ? {code: element.error.code, message: element.error.message} : null;
  result.audioBytes = element.webkitAudioDecodedByteCount || 0;
  result.videoBytes = element.webkitVideoDecodedByteCount || 0;
  if (test.video) {
    result.width = element.videoWidth;
    result.height = element.videoHeight;
    result.frames = element.webkitDecodedFrameCount || 0;
    const quality = element.getVideoPlaybackQuality ? element.getVideoPlaybackQuality() : null;
    result.totalFrames = quality ? quality.totalVideoFrames : null;
    result.droppedFrames = quality ? quality.droppedVideoFrames : null;
    try { result.quarters = element.videoWidth ? quarters(element) : null; } catch (error) { result.quartersError = String(error); }
  }
  element.pause();
  element.removeAttribute("src");
  element.load();
  element.remove();
  return result;
}

window.ikeStart = async function () {
  report("probe", probe());
  for (const test of CASES) {
    let result;
    try { result = await runCase(test); } catch (error) { result = {name: test.name, outcome: "exception", exception: String(error)}; }
    report("case", result);
    await sleep(500);
  }
  document.title = "done";
  report("done", {});
};
report("ready", {});
</script></body></html>
"""


# chrome://gpu keeps its text inside shadow trees, which innerText does not see.
GPU_TEXT_JS = """(function () {
  function text(node) {
    var out = "";
    if (node.shadowRoot) { out += text(node.shadowRoot) + "\\n"; }
    node.childNodes.forEach(function (child) {
      if (child.nodeType === 3) { out += child.textContent; }
      else if (child.nodeType === 1 && child.tagName !== "SCRIPT" && child.tagName !== "STYLE") {
        out += text(child);
        if (/^(DIV|LI|TR|P|H1|H2|H3|H4|UL|TABLE)$/.test(child.tagName)) { out += "\\n"; }
        else if (child.tagName === "TD" || child.tagName === "TH") { out += " | "; }
      }
    });
    return out;
  }
  return text(document.documentElement);
})()"""


def log(message):
    print(f"[codec-check] {message}", flush=True)


# --- clips ------------------------------------------------------------------

def quarters_filter(size):
    width, height = VIDEO_SIZES[size]
    w, h = width // 2, height // 2
    return (f"color=c=red:s={w}x{h}:r=25[a];color=c=lime:s={w}x{h}:r=25[b];"
            f"color=c=blue:s={w}x{h}:r=25[c];color=c=white:s={w}x{h}:r=25[d];"
            f"[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack[v]")


def make_clip(ffmpeg, target, size, audio, options):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    if size:
        cmd += ["-filter_complex", quarters_filter(size), "-map", "[v]"]
    if audio:
        cmd += ["-map", "0:a"]
    cmd += ["-t", "3", *options, str(target)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0 or not target.exists() or target.stat().st_size < 500:
        log(f"FFmpeg could not make {target.name}: {done.stderr.strip()[-400:]}")
        return False
    return True


def cmd_clips(args):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is not on PATH")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    log(version)
    made = []
    for name, (size, audio, options) in CLIPS.items():
        if not make_clip(ffmpeg, out / name, size, audio, options):
            raise SystemExit(f"could not make the test clip {name}")
        made.append(name)
    skipped = []
    for name, (encoder, size, audio, options) in OPTIONAL_CLIPS.items():
        if f" {encoder} " in encoders and make_clip(ffmpeg, out / name, size, audio, options):
            made.append(name)
        else:
            skipped.append(f"{name} (this FFmpeg has no {encoder})")
    for name in made:
        log(f"  {name}  {(out / name).stat().st_size:,} bytes")
    for name in skipped:
        log(f"  not made: {name}")
    (out / "clips.json").write_text(json.dumps({"ffmpeg": version, "made": made, "skipped": skipped},
                                               indent=1), encoding="utf-8")


# --- overlay ----------------------------------------------------------------

def site_qt_dir():
    import PyQt6
    return Path(PyQt6.__file__).resolve().parent


def cmd_overlay(args):
    package = Path(args.package)
    sums = {}
    for line in (package / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if "  " in line:
            digest, name = line.split("  ", 1)
            sums[name] = digest
    target_root = site_qt_dir().parent
    replaced, added = [], []
    for source in sorted(p for p in (package / "PyQt6").rglob("*") if p.is_file()):
        relative = source.relative_to(package).as_posix()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if sums.get(relative) != digest:
            raise SystemExit(f"{relative} does not match SHA256SUMS.txt")
        destination = target_root / relative
        (replaced if destination.exists() else added).append(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    log(f"{len(replaced)} files replaced, {len(added)} added under {target_root}")
    for name in added:
        log(f"  added (not in the PyPI wheel): {name}")
    kept = []
    wheel_qt = target_root / "PyQt6" / "Qt6"
    for folder in ("bin", "resources"):
        for path in sorted((wheel_qt / folder).glob("*")):
            relative = path.relative_to(target_root).as_posix()
            if path.is_file() and ("WebEngine" in path.name or folder == "resources") \
                    and relative not in replaced and relative not in added:
                kept.append(relative)
    for name in kept:
        log(f"  kept from the PyPI wheel: {name}")


# --- run --------------------------------------------------------------------

class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with byte ranges, which a media element asks for."""
    page = b""

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/check.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(self.page)))
            self.end_headers()
            self.wfile.write(self.page)
            return
        requested = self.headers.get("Range")
        path = Path(self.translate_path(self.path))
        if not requested or not path.is_file():
            super().do_GET()
            return
        size = path.stat().st_size
        try:
            first, _, last = requested.split("=", 1)[1].partition("-")
            start = int(first) if first else max(0, size - int(last))
            end = min(int(last), size - 1) if first and last else size - 1
        except ValueError:
            super().do_GET()
            return
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as handle:
            handle.seek(start)
            try:
                self.wfile.write(handle.read(end - start + 1))
            except OSError:
                pass


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class MediaLogReader(threading.Thread):
    """Listens to the engine's media log over the remote debugging port."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.connected = threading.Event()
        self.stop = threading.Event()
        self.error = None
        self.players = {}       # player id -> {"properties": {}, "messages": [], "errors": []}

    def player(self, identifier):
        return self.players.setdefault(identifier, {"properties": {}, "messages": [], "errors": []})

    def run(self):
        try:
            import websocket
        except ImportError as error:
            self.error = f"websocket-client is not installed ({error})"
            return
        try:
            target = None
            for _attempt in range(40):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=2) as reply:
                        pages = json.load(reply)
                    target = next((p for p in pages if "check.html" in p.get("url", "")
                                   and p.get("webSocketDebuggerUrl")), None)
                    if target:
                        break
                except OSError:
                    pass
                time.sleep(0.25)
            if not target:
                self.error = "the remote debugging port did not list the check page"
                return
            connection = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=5,
                                                     suppress_origin=True)
            connection.send(json.dumps({"id": 1, "method": "Media.enable"}))
            connection.settimeout(0.5)
            self.connected.set()
            while not self.stop.is_set():
                try:
                    message = json.loads(connection.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                except (OSError, ValueError, websocket.WebSocketException):
                    break
                self.handle(message)
            connection.close()
        except Exception as error:      # never let the listener break the check itself
            self.error = f"{type(error).__name__}: {error}"

    def handle(self, message):
        method, params = message.get("method"), message.get("params", {})
        if method == "Media.playersCreated":
            for identifier in params.get("players", []):
                self.player(identifier)
        elif method == "Media.playerPropertiesChanged":
            for entry in params.get("properties", []):
                self.player(params.get("playerId"))["properties"][entry.get("name")] = entry.get("value")
        elif method == "Media.playerMessagesLogged":
            for entry in params.get("messages", []):
                self.player(params.get("playerId"))["messages"].append(
                    f"{entry.get('level')}: {entry.get('message')}")
        elif method == "Media.playerErrorsRaised":
            for entry in params.get("errors", []):
                self.player(params.get("playerId"))["errors"].append(json.dumps(entry)[:600])


def colour_ok(name, rgb):
    r, g, b = rgb
    if name == "red":
        return r > 150 and g < 115 and b < 115
    if name == "green":
        return g > 150 and r < 125 and b < 125
    if name == "blue":
        return b > 150 and r < 115 and g < 115
    return r > 180 and g > 180 and b > 180          # white


def judge(case, result):
    """(decoded, list of reasons why not)."""
    reasons = []
    if result.get("outcome") not in ("played", "ended"):
        reasons.append(f"outcome {result.get('outcome')}")
    if result.get("error"):
        reasons.append(f"media error {result['error'].get('code')}: {result['error'].get('message')}")
    if result.get("exception"):
        reasons.append(result["exception"])
    if case["video"]:
        width, height = VIDEO_SIZES[case["video"]]
        if (result.get("width"), result.get("height")) != (width, height):
            reasons.append(f"size {result.get('width')}x{result.get('height')}, wanted {width}x{height}")
        if not (result.get("frames") or result.get("totalFrames")):
            reasons.append("no picture decoded")
        quarters = result.get("quarters")
        if not quarters:
            reasons.append("the picture could not be read back")
        else:
            for name, rgb in zip(("red", "green", "blue", "white"), quarters):
                if not colour_ok(name, rgb):
                    reasons.append(f"the {name} quarter reads {rgb}")
    if case["audio"] and not result.get("audioBytes"):
        reasons.append("no audio decoded")
    return (not reasons), reasons


def engine_processes():
    """Command lines of the running engine processes."""
    try:
        listed = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='QtWebEngineProcess.exe'\" | "
             "ForEach-Object { $_.CommandLine }"],
            capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in listed.splitlines() if line.strip()]


def cmd_run(args):
    clips = Path(args.clips).resolve()
    report_dir = Path(args.report)
    report_dir.mkdir(parents=True, exist_ok=True)
    made = json.loads((clips / "clips.json").read_text(encoding="utf-8"))
    cases = list(CASES) + [case for clip, case in OPTIONAL_CASES.items() if clip in made["made"]]
    page = PAGE.replace("__CASES__", json.dumps(cases)).replace(
        "__PROBES__", json.dumps([[p[0], p[1]] for p in PROBES]))

    RangeHandler.page = page.encode("utf-8")
    web_port, debug_port = free_port(), free_port()

    def handler(*handler_args, **handler_kwargs):
        return RangeHandler(*handler_args, directory=str(clips), **handler_kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", web_port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    flags = ["--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required"]
    flags += args.flags.split() if args.flags else []
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = str(debug_port)

    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QTimer, QUrl
    from PyQt6.QtWebEngineCore import (
        PYQT_WEBENGINE_VERSION_STR,
        QWebEnginePage,
        QWebEngineSettings,
        qWebEngineChromiumVersion,
        qWebEngineVersion,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    state = {"probe": None, "results": [], "done": False, "ready": False, "console": [],
             "processes": [], "gpu": ""}

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, _level, message, _line, _source):
            if not message.startswith("IKE:"):
                state["console"].append(message[:300])
                return
            _prefix, tag, payload = message.split(":", 2)
            value = json.loads(payload)
            if tag == "ready":
                state["ready"] = True
            elif tag == "probe":
                state["probe"] = value
            elif tag == "case":
                state["results"].append(value)
                log(f"  {value.get('name')}: {value.get('outcome')}")
                if len(state["results"]) == 1:
                    state["processes"] = engine_processes()
            elif tag == "done":
                state["done"] = True

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    web_page = Page(view)
    view.setPage(web_page)
    web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    view.resize(900, 700)
    view.show()

    versions = {"python": sys.version.split()[0], "PyQt6": PYQT_VERSION_STR, "Qt": QT_VERSION_STR,
                "PyQt6-WebEngine": PYQT_WEBENGINE_VERSION_STR, "Qt WebEngine": qWebEngineVersion(),
                "Chromium": qWebEngineChromiumVersion(),
                "engine file": str(site_qt_dir() / "Qt6" / "bin" / "Qt6WebEngineCore.dll")}
    core = Path(versions["engine file"])
    if core.exists():
        versions["engine file sha256"] = hashlib.sha256(core.read_bytes()).hexdigest()
        versions["engine file bytes"] = core.stat().st_size
    for key, value in versions.items():
        log(f"{key}: {value}")

    reader = MediaLogReader(debug_port)
    started = time.time()
    phase = {"name": "loading"}

    def tick():
        elapsed = time.time() - started
        if phase["name"] == "loading" and state["ready"]:
            reader.start()
            phase["name"] = "attaching"
            phase["since"] = time.time()
        elif phase["name"] == "attaching":
            if reader.connected.is_set() or reader.error or time.time() - phase["since"] > 15:
                log("media log: " + ("attached" if reader.connected.is_set()
                                     else f"NOT attached ({reader.error or 'no answer'})"))
                web_page.runJavaScript("window.ikeStart()")
                phase["name"] = "running"
        elif phase["name"] == "running" and state["done"]:
            phase["name"] = "gpu"
            phase["since"] = time.time()
            web_page.load(QUrl("chrome://gpu"))
        elif phase["name"] == "gpu" and time.time() - phase.get("asked", 0) > 3:
            # chrome://gpu fills in after it loads: ask until it has its table.
            phase["asked"] = time.time()

            def keep(text):
                state["gpu"] = text if isinstance(text, str) else ""
                if "Video Decode" in state["gpu"] or time.time() - phase["since"] > 25:
                    phase["name"] = "finished"
            web_page.runJavaScript(GPU_TEXT_JS, keep)
        if phase["name"] == "finished" or elapsed > args.timeout:
            if phase["name"] != "finished":
                log(f"gave up after {elapsed:.0f} s in phase '{phase['name']}'")
            timer.stop()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(200)
    web_page.load(QUrl(f"http://127.0.0.1:{web_port}/check.html"))
    app.exec()
    reader.stop.set()
    server.shutdown()

    # --- judge -------------------------------------------------------------
    patched = args.expect == "patched"
    problems = []
    lines = [f"## Codec check: {args.name}", "",
             f"Expectation: **{'patched engine: H.264 and AAC decode' if patched else 'engine from PyPI: H.264 and AAC must not decode (control)'}**",
             "", f"Engine flags: `{' '.join(flags)}`", ""]
    lines += [f"- {key}: {value}" for key, value in versions.items()]

    renderers = [p for p in state["processes"] if "--type=renderer" in p]
    sandbox = "unknown"
    if renderers:
        sandbox = "off (--no-sandbox)" if any("--no-sandbox" in p for p in renderers) else "on"
    lines.append(f"- renderer sandbox: {sandbox} ({len(renderers)} renderer processes seen)")
    gpu_lines = []
    for line in state["gpu"].splitlines():
        line = " ".join(line.split())
        if line and line not in gpu_lines and any(key in line for key in (
                "Video Decode", "Video Encode", "GL_RENDERER", "Display type", "GPU0",
                "Rasterization", "Compositing:", "Canvas:", "WebGL:", "Decode h264", "Decode vp9",
                "Decode av1", "Skia Backend", "Direct Rendering")):
            gpu_lines.append(line)
    lines += ["", "chrome://gpu:", ""] + [f"    {line[:200]}" for line in gpu_lines[:24]]

    if not state["probe"]:
        problems.append("the page never answered")
    lines += ["", "| Format | type | canPlayType | Media Source |", "|---|---|---|---|"]
    for name, mime, expected in PROBES:
        answer = next((p for p in state["probe"] or [] if p["type"] == mime), None)
        if not answer:
            continue
        lines.append(f"| {name} | `{mime}` | {answer['canPlayType'] or '(no)'} | "
                     f"{'yes' if answer['mediaSource'] else 'no'} |")
        declared = bool(answer["canPlayType"])
        if expected is not None:
            wanted = expected if patched else False
            if declared != wanted:
                problems.append(f"{name}: canPlayType says {'yes' if declared else 'no'}, "
                                f"expected {'yes' if wanted else 'no'}")

    by_title = {}
    for player in reader.players.values():
        title = str(player["properties"].get("kFrameTitle", ""))
        if title.startswith("case:"):
            by_title[title[5:]] = player
    lines += ["", "| Clip | result | video decoder | audio decoder | details |", "|---|---|---|---|---|"]
    results = {r.get("name"): r for r in state["results"]}
    decoders = []
    for case in cases:
        result = results.get(case["name"])
        if result is None:
            problems.append(f"{case['name']}: not run")
            continue
        decoded, reasons = judge(case, result)
        player = by_title.get(case["name"], {"properties": {}, "messages": [], "errors": []})
        video_decoder = player["properties"].get("kVideoDecoderName", "")
        audio_decoder = player["properties"].get("kAudioDecoderName", "")
        decoders.append((case, video_decoder, audio_decoder))
        details = "; ".join(reasons) if reasons else (
            f"{result.get('frames') or result.get('totalFrames') or 0} pictures, "
            f"{result.get('audioBytes', 0)} audio bytes")
        lines.append(f"| {case['name']} | {'decoded' if decoded else 'NOT decoded'} | "
                     f"{video_decoder or '-'} | {audio_decoder or '-'} | {details[:300]} |")
        under_test = "free" not in case["tags"]
        if under_test and patched and not decoded:
            problems.append(f"{case['name']}: {'; '.join(reasons)}")
        if under_test and not patched and decoded:
            problems.append(f"{case['name']}: decoded with the engine from PyPI; the control is void")
        if not under_test and not decoded:
            problems.append(f"control failed, {case['name']}: {'; '.join(reasons)}")
        # Whatever the build, FFmpeg must never be the one decoding H.264 / AAC.
        if "h264" in case["tags"] and "FFmpeg" in str(video_decoder):
            problems.append(f"{case['name']}: decoded by {video_decoder}")
        if "aac" in case["tags"] and "FFmpeg" in str(audio_decoder):
            problems.append(f"{case['name']}: decoded by {audio_decoder}")
        if patched and decoded and video_decoder and args.video_decoder \
                and "h264" in case["tags"] and case["video"] and video_decoder != args.video_decoder:
            problems.append(f"{case['name']}: video decoded by {video_decoder}, "
                            f"expected {args.video_decoder}")
        if patched and decoded and audio_decoder and args.audio_decoder \
                and "aac" in case["tags"] and audio_decoder != args.audio_decoder:
            problems.append(f"{case['name']}: audio decoded by {audio_decoder}, "
                            f"expected {args.audio_decoder}")

    if reader.connected.is_set() and by_title:
        lines += ["", "Decoder names come from the engine's media log (remote debugging, `Media` domain)."]
    else:
        lines += ["", f"**Decoder names were not observed** ({reader.error or 'no media log received'})."]
        if patched and args.require_decoder_names:
            problems.append("the media log gave no decoder names")
    media_messages = []
    for title, player in by_title.items():
        for message in player["messages"]:
            if "MediaFoundation" in message or "Selected" in message or "error" in message.lower():
                media_messages.append(f"{title}: {message[:260]}")
    if media_messages:
        lines += ["", "Media log:", ""] + [f"    {m}" for m in media_messages[:60]]

    lines += ["", "### Result: " + ("as expected" if not problems else "NOT as expected"), ""]
    lines += [f"- {problem}" for problem in problems]
    text = "\n".join(lines) + "\n"
    slug = "".join(c if c.isalnum() else "-" for c in args.name.lower()).strip("-")
    (report_dir / f"codec-check-{slug}.md").write_text(text, encoding="utf-8")
    (report_dir / f"codec-check-{slug}.json").write_text(json.dumps({
        "name": args.name, "expect": args.expect, "flags": flags, "versions": versions,
        "probe": state["probe"], "results": state["results"], "problems": problems,
        "players": list(reader.players.values()), "media_log_error": reader.error,
        "processes": state["processes"], "gpu": state["gpu"][:20000],
        "console": state["console"][:100]}, indent=1), encoding="utf-8")
    print(text, flush=True)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text)
    if problems:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    clips = commands.add_parser("clips")
    clips.add_argument("--out", required=True)
    clips.set_defaults(function=cmd_clips)
    overlay = commands.add_parser("overlay")
    overlay.add_argument("--package", required=True)
    overlay.set_defaults(function=cmd_overlay)
    run = commands.add_parser("run")
    run.add_argument("--clips", required=True)
    run.add_argument("--expect", choices=("patched", "stock"), required=True)
    run.add_argument("--name", required=True)
    run.add_argument("--report", required=True)
    run.add_argument("--flags", default="")
    run.add_argument("--timeout", type=int, default=420)
    run.add_argument("--require-decoder-names", action="store_true")
    run.add_argument("--video-decoder", default="",
                     help="the decoder the H.264 clips must have been decoded by")
    run.add_argument("--audio-decoder", default="",
                     help="the decoder the AAC clips must have been decoded by")
    run.set_defaults(function=cmd_run)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
