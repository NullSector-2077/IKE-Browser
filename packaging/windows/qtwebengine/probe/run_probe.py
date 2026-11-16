#!/usr/bin/env python3
"""Builds mft_probe.cpp and runs it on streams made with FFmpeg.

Workflow helper (``windows-mft-probe.yml``); nothing here is shipped. FFmpeg
only makes the test streams on the runner. The probe asks the H.264 and AAC
decoders of Windows the same questions, in the same order, as the engine
patches do, so this run says in minutes what a build of the engine would only
show after many hours: whether Windows decodes these streams when driven that
way.

    python run_probe.py --work DIR --report FILE
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build  # noqa: E402  (msvc_env: the compiler's environment)

# name: (width, height, x264 options, low delay)
VIDEO = {
    "baseline_320x240": (320, 240, ["-profile:v", "baseline"], False),
    "high_bframes_854x480": (854, 480, ["-profile:v", "high", "-bf", "2"], False),
    "main_1920x1080": (1920, 1080, ["-profile:v", "main"], False),
    "high_1280x720": (1280, 720, ["-profile:v", "high"], False),
    "high_bframes_854x480_low_delay": (854, 480, ["-profile:v", "high", "-bf", "2"], True),
    "baseline_322x242_odd": (322, 242, ["-profile:v", "baseline"], False),
}
# name: ffmpeg audio options
AUDIO = {
    "aac_lc_stereo_44100": ["-ar", "44100", "-ac", "2", "-b:a", "96k"],
    "aac_lc_mono_48000": ["-ar", "48000", "-ac", "1", "-b:a", "64k"],
}


def log(text):
    print(f"[probe] {text}", flush=True)


def quarters(width, height):
    w, h = width // 2, height // 2
    return (f"color=c=red:s={w}x{h}:r=25[a];color=c=lime:s={w}x{h}:r=25[b];"
            f"color=c=blue:s={w}x{h}:r=25[c];color=c=white:s={w}x{h}:r=25[d];"
            f"[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack[v]")


def tool(name):
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} is not on PATH")
    return found


def checked(cmd, **kwargs):
    done = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kwargs)
    if done.returncode != 0:
        raise SystemExit(f"failed: {' '.join(str(c) for c in cmd)}\n{done.stdout[-800:]}\n"
                         f"{done.stderr[-800:]}")
    return done.stdout


def make_video(work, name, width, height, options):
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    mp4, stream, times = work / f"{name}.mp4", work / f"{name}.h264", work / f"{name}.pts"
    # aud=1: every picture starts with an access unit delimiter, which is how
    # the probe finds where one picture ends.
    checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-filter_complex", quarters(width, height), "-map", "[v]", "-t", "2",
             "-c:v", "libx264", *options, "-pix_fmt", "yuv420p", "-g", "25",
             "-preset", "veryfast", "-x264-params", "aud=1", mp4])
    checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", mp4, "-c:v", "copy",
             "-bsf:v", "h264_mp4toannexb", "-f", "h264", stream])
    listed = checked([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                      "packet=pts_time", "-of", "csv=p=0", mp4])
    times.write_text("\n".join(line.strip().strip(",") for line in listed.splitlines()
                               if line.strip()) + "\n", encoding="ascii")
    return stream, times


def make_audio(work, name, options):
    target = work / f"{name}.aac"
    checked([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "sine=frequency=440:sample_rate=48000", "-t", "2", "-c:a", "aac", *options,
             "-f", "adts", target])
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    env = build.msvc_env()
    exe = work / "mft_probe.exe"
    log(f"compiling with MSVC {env.get('VCTOOLSVERSION')}")
    # Windows looks a program up in this process's PATH, not in |env|'s.
    compiler = shutil.which("cl", path=env["PATH"])
    if not compiler:
        raise SystemExit("cl.exe not found in the compiler's environment")
    done = subprocess.run(
        [compiler, "/nologo", "/std:c++17", "/EHsc", "/O2", "/W3", f"/Fe{exe}", f"/Fo{work}\\",
         str(HERE / "mft_probe.cpp"), "/link", "mfplat.lib", "mfuuid.lib", "ole32.lib"],
        env=env, capture_output=True, text=True)
    print(done.stdout[-4000:], done.stderr[-2000:], flush=True)
    if done.returncode != 0 or not exe.exists():
        raise SystemExit("mft_probe.cpp does not compile")

    runs = []
    for name, (width, height, options, low_delay) in VIDEO.items():
        stream, times = make_video(work, name, width, height, options)
        runs.append((f"H.264 {name}", [exe, "h264", stream, times, width, height]
                     + (["low-delay"] if low_delay else [])))
    for name, options in AUDIO.items():
        sound = make_audio(work, name, options)
        runs.append((f"AAC {name}, bare frames (as from an MP4 file)", [exe, "aac", sound, "raw"]))
        runs.append((f"AAC {name}, ADTS frames (as from Media Source)", [exe, "aac", sound, "adts"]))

    lines = [f"## Windows decoders driven as the engine patches drive them{args.name}", "",
             "| Stream | Result |", "|---|---|"]
    details = []
    failed = 0
    for title, cmd in runs:
        done = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=300)
        text = (done.stdout + done.stderr).strip()
        print(f"--- {title}\n{text}", flush=True)
        ok = done.returncode == 0 and "RESULT: ok" in text
        failed += 0 if ok else 1
        lines.append(f"| {title} | {'decoded' if ok else '**FAILED**'} |")
        details += [f"### {title}", "", "```", text, "```", ""]
    lines += ["", f"{len(runs) - failed} of {len(runs)} passed.", ""] + details
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    if failed:
        raise SystemExit(f"{failed} of {len(runs)} probe runs failed")
    log(f"all {len(runs)} probe runs passed")


if __name__ == "__main__":
    main()
