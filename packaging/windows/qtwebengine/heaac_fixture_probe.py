#!/usr/bin/env python3
"""Download and identify the public Fraunhofer HE-AAC reference clips.

This is a fixture-discovery check only. The files are not redistributed with I.K.E.
Their SHA-256 values are printed so the engine test can pin the exact bytes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path("heaac-fixtures")
SAMPLES = {
    "heaac_v1_aot5.mp4": (
        "https://www2.iis.fraunhofer.de/AAC/SBRtestStereoAot5Sig1.mp4",
        "HE-AAC v1 (AOT 5)",
    ),
    "heaac_v2_aot29.mp4": (
        "https://www2.iis.fraunhofer.de/AAC/SBRtestStereoAot29Sig1.mp4",
        "HE-AAC v2 (AOT 29)",
    ),
}


def download(url: str, target: Path) -> tuple[int, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "IKE-Windows-Codec-Fixture-Check/1.0"}
    )
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        content_type = response.headers.get("Content-Type", "").lower()
        if "video/mp4" not in content_type and "application/octet-stream" not in content_type:
            raise RuntimeError(f"unexpected Content-Type {content_type!r} for {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > 32 * 1024 * 1024:
                    raise RuntimeError(f"fixture exceeds 32 MiB: {url}")
                digest.update(block)
                output.write(block)
    if total < 1024:
        raise RuntimeError(f"fixture is unexpectedly small ({total} bytes): {url}")
    with target.open("rb") as source:
        header = source.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise RuntimeError(f"download is not an ISO BMFF/MP4 file: {url}")
    return total, digest.hexdigest()


def probe(ffprobe: str, target: Path) -> dict:
    command = [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,profile,sample_rate,channels,channel_layout,extradata_size",
        "-show_entries", "format=format_name,duration",
        "-of", "json", str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"ffprobe failed for {target.name}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams or streams[0].get("codec_name") != "aac":
        raise RuntimeError(f"{target.name} does not contain an AAC audio stream: {data}")
    stream = streams[0]
    if stream.get("channels") != 2:
        raise RuntimeError(f"{target.name} is not stereo: {stream}")
    if not stream.get("extradata_size"):
        raise RuntimeError(f"{target.name} has no AudioSpecificConfig: {stream}")
    return {"stream": stream, "format": data.get("format", {})}


def main() -> int:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise SystemExit("ffprobe is not available on PATH")
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for filename, (url, label) in SAMPLES.items():
        target = ROOT / filename
        size, digest = download(url, target)
        metadata = probe(ffprobe, target)
        manifest[filename] = {
            "label": label,
            "url": url,
            "size_bytes": size,
            "sha256": digest,
            **metadata,
        }
        print(f"FIXTURE: {label}")
        print(f"  URL: {url}")
        print(f"  bytes: {size}")
        print(f"  SHA256: {digest}")
        print(f"  ffprobe: {json.dumps(metadata, sort_keys=True)}")
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {ROOT / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
