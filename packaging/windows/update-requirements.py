#!/usr/bin/env python3
"""Write packaging/windows/requirements.txt again with the SHA-256 hashes
PyPI publishes for the wheels of 64-bit Windows.

    python3 packaging/windows/update-requirements.py                 same versions, hashes read again
    python3 packaging/windows/update-requirements.py PyQt6-WebEngine-Qt6==6.140.1 cryptography==50.0.3
    python3 packaging/windows/update-requirements.py --from-tests    the versions of tools/test-requirements.txt

For each package it asks https://pypi.org/pypi/<name>/<version>/json (no
account, nothing sent but the request) and picks the one wheel pip would
install on Windows x64 with CPython 3.13: "cp313-cp313-win_amd64", else the
newest "abi3" wheel, else "py3-none-win_amd64" or "py3-none-any"; of two
builds of the same wheel the one with the higher build number. A package
without such a wheel stops the script: nothing is ever compiled on the way
into the installer. Review the difference before committing it, and let the
Windows workflow build and test with it.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TARGET = HERE / "requirements.txt"
PYTHON = (3, 13)
PLATFORM = "win_amd64"


def pins(text):
    """{name: version} of the "name==version" lines, in order."""
    found = {}
    for line in text.replace("\\\n", " ").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.-]+)==([0-9][0-9A-Za-z.]*)", line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def wheel_rank(filename):
    """How well a wheel suits CPython 3.13 on 64-bit Windows: a tuple to
    compare (higher is better), or None when it cannot be installed there."""
    m = re.fullmatch(r"(?P<name>[^-]+)-(?P<version>[^-]+)(?:-(?P<build>\d[^-]*))?-(?P<py>[^-]+)-(?P<abi>[^-]+)"
                     r"-(?P<plat>[^-]+)\.whl", filename)
    if not m:
        return None
    py, abi, plat = m.group("py").split("."), m.group("abi").split("."), m.group("plat").split(".")
    build = int(re.match(r"\d+", m.group("build")).group()) if m.group("build") else 0
    tag = "cp%d%d" % PYTHON
    if PLATFORM in plat:
        if tag in py and tag in abi:
            return (3, 0, build)
        if "abi3" in abi:
            minors = [int(p[3:]) for p in py if re.fullmatch(r"cp3\d+", p) and int(p[3:]) <= PYTHON[1]]
            if minors:
                return (2, max(minors), build)
        if "none" in abi and ("py3" in py or tag in py):
            return (1, 0, build)
    if "any" in plat and "none" in abi and "py3" in py:
        return (0, 0, build)
    return None


def choose(files):
    """The wheel to pin among a release's files: (filename, sha256)."""
    ranked = sorted(((wheel_rank(f["filename"]), f) for f in files if wheel_rank(f["filename"]) is not None),
                    key=lambda pair: pair[0])
    if not ranked:
        return None
    best = ranked[-1][1]
    return best["filename"], best["digests"]["sha256"]


def fetch(name, version):
    url = "https://pypi.org/pypi/%s/%s/json" % (name, version)
    req = urllib.request.Request(url, headers={"User-Agent": "IKE-Browser-requirements"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read(8 * 1024 * 1024).decode("utf-8"))["urls"]


def render(header, chosen):
    lines = [header.rstrip("\n")]
    for name, (version, _filename, digest) in chosen.items():
        lines.append("%s==%s \\\n    --hash=sha256:%s" % (name, version, digest))
    return "\n".join(lines) + "\n"


def main(argv=None, fetch=fetch):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pins", nargs="*", help="name==version to change")
    ap.add_argument("--from-tests", action="store_true",
                    help="take the versions of tools/test-requirements.txt (for the packages listed here)")
    ap.add_argument("--file", default=str(TARGET))
    args = ap.parse_args(argv)
    target = Path(args.file)
    text = target.read_text("utf-8")
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    current = pins(text)
    if args.from_tests:
        tests = pins((ROOT / "tools" / "test-requirements.txt").read_text("utf-8"))
        current.update({name: tests[name] for name in current if name in tests})
    for pin in args.pins:
        wanted = pins(pin)
        if not wanted or not set(wanted) <= set(current):
            raise SystemExit("update-requirements: %r is not name==version of a package listed in %s"
                             % (pin, target.name))
        current.update(wanted)
    chosen = {}
    for name, version in current.items():
        picked = choose(fetch(name, version))
        if picked is None:
            raise SystemExit("update-requirements: %s %s has no wheel for CPython %d.%d on %s"
                             % (name, version, PYTHON[0], PYTHON[1], PLATFORM))
        chosen[name] = (version, picked[0], picked[1])
        print("%s==%s  %s" % (name, version, picked[0]))
    new = render(header, chosen)
    if new == text:
        print("update-requirements: nothing to change")
    else:
        target.write_text(new, "utf-8")
        print("update-requirements: %s written - review the difference" % target.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
