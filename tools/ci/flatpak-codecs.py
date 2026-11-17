#!/usr/bin/env python3
"""Does an installed Flatpak contain H.264 / AAC / HEVC decoders of its own?

    flatpak-codecs.py APP_FILES [CONTROL_FILES]

Looks through every ELF file under APP_FILES (an installed application's
``files`` folder) for the names FFmpeg gives its H.264, AAC and HEVC decoders
(``CODEC_LONG_NAME``, present in every FFmpeg built without CONFIG_SMALL, such
as Chromium's own). CONTROL_FILES, if given, is searched the same way and
must contain them (the Qt WebEngine base application, whose Chromium has its
own FFmpeg): proof that the search finds such decoders where they are.

Prints a Markdown report; exit status 0 when APP_FILES has none, 1 when it
has some, 2 when the control has none (the search proves nothing then).
Used by .github/workflows/flatpak.yml (packaging/flatpak/README.md, "Codecs").
"""
import os
import subprocess
import sys

DECODERS = {
    "H.264": b"H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
    "AAC": b"AAC (Advanced Audio Coding)",
    "HEVC": b"H.265 / HEVC (High Efficiency Video Coding)",
}
# Cisco's OpenH264 compiled in (WebRTC's H.264 encoder); with the run time's
# library the name is only an imported symbol and the library is NEEDED
OPENH264 = b"WelsCreateSVCEncoder"


def elf_files(root):
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as f:
                    if f.read(4) == b"\x7fELF":
                        yield path
            except OSError:
                continue


def scan(root):
    found = {}
    for path in elf_files(root):
        with open(path, "rb") as f:
            data = f.read()
        for codec, name in DECODERS.items():
            if name in data:
                found.setdefault(codec, []).append(os.path.relpath(path, root))
    return found


def needed(path):
    try:
        out = subprocess.run(["readelf", "-d", path], capture_output=True, text=True).stdout
    except OSError:
        return []
    return [line.split("[", 1)[1].rstrip("]") for line in out.splitlines() if "(NEEDED)" in line]


def main():
    app = sys.argv[1]
    control = sys.argv[2] if len(sys.argv) > 2 else None
    print("### Codecs of the bundle itself\n")
    core = [p for p in elf_files(app) if os.path.basename(p).startswith("libQt6WebEngineCore.so")]
    for path in core:
        libs = [lib for lib in needed(path) if lib.startswith(("libav", "libopenh264"))]
        print("- `%s` uses from the run time: %s" % (os.path.relpath(path, app),
                                                     ", ".join("`%s`" % x for x in libs) or "nothing (own FFmpeg)"))
        with open(path, "rb") as f:
            data = f.read()
        if OPENH264 in data and not any(lib.startswith("libopenh264") for lib in libs):
            print("  - **OpenH264 compiled in** (WebRTC's H.264 encoder)")
    found = scan(app)
    status = 0
    if found:
        status = 1
        for codec, paths in sorted(found.items()):
            print("- **%s decoder in the bundle**: %s" % (codec, ", ".join("`%s`" % p for p in paths)))
    else:
        print("- No H.264, AAC or HEVC decoder in any program or library of the bundle.")
    if control:
        seen = scan(control)
        print("- Control, the same search in `%s`: %s" % (
            control, ", ".join("%s in %s" % (c, ", ".join(p)) for c, p in sorted(seen.items())) or "nothing found"))
        if not seen.get("H.264") and status == 0:
            print("\n**The control has no decoder either: this search proves nothing.**")
            status = 2
    print()
    return status


if __name__ == "__main__":
    sys.exit(main())
