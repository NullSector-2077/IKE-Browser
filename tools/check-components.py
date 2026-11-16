#!/usr/bin/env python3
"""Check and optionally update the Arch-relevant bundled browser components.

    python3 tools/check-components.py [--json FILE] [--markdown FILE]
                                      [--apply] [--ubo-src DIR]

Only the native Rust AdBlock engine and uBlock Origin scriptlets are checked.
Python, PyQt6, Qt and Qt WebEngine are supplied and updated by Arch Linux.
Windows and AppImage dependencies are deliberately out of scope.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRATES_INDEX = "https://index.crates.io/ad/bl/adblock"
UBO_GIT = "https://github.com/gorhill/uBlock"


def fetch(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "ike-browser-component-check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def vkey(version):
    return tuple(int(number) for number in re.findall(r"\d+", version))


def is_stable(version):
    return re.fullmatch(r"[0-9]+(\.[0-9]+)*(\.post[0-9]+)?", version) is not None


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs).stdout


def current_adblock(root):
    manifest = (root / "ike-adblock" / "Cargo.toml").read_text("utf-8")
    library = (root / "ike-adblock" / "src" / "lib.rs").read_text("utf-8")
    lockfile = (root / "ike-adblock" / "Cargo.lock").read_text("utf-8")
    version = re.search(r'^adblock = \{ version = "=([^"]+)"', manifest, re.M)
    engine = re.search(r'const ENGINE_VERSION: &str = "([^"]+)"', library)
    locked = re.search(r'\[\[package\]\]\nname = "adblock"\nversion = "([^"]+)"', lockfile)
    if not version or not engine or not locked:
        raise RuntimeError("cannot read the AdBlock version from Cargo.toml, lib.rs and Cargo.lock")
    values = {version.group(1), engine.group(1), locked.group(1)}
    if len(values) != 1:
        raise RuntimeError("AdBlock version mismatch between Cargo.toml, lib.rs and Cargo.lock")
    return version.group(1)


def latest_adblock():
    versions = []
    for line in fetch(CRATES_INDEX).decode("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if not entry.get("yanked") and is_stable(entry["vers"]):
                versions.append(entry["vers"])
    if not versions:
        raise RuntimeError("crates.io returned no stable AdBlock versions")
    return max(versions, key=vkey)


def check_adblock(root):
    current, latest = current_adblock(root), latest_adblock()
    update = vkey(latest) > vkey(current)
    return {
        "current": current,
        "latest": latest,
        "update": update,
        "note": (
            "review API changes, raise __min_system__ if required, and review docs/arch/THIRD-PARTY.md when Cargo.lock changes"
            if update else ""
        ),
    }


def apply_adblock(root, info):
    version = info["latest"]
    manifest = root / "ike-adblock" / "Cargo.toml"
    library = root / "ike-adblock" / "src" / "lib.rs"
    manifest_text, count_manifest = re.subn(
        r'^(adblock = \{ version = "=)[^"]+"',
        lambda match: match.group(1) + version + '"',
        manifest.read_text("utf-8"),
        count=1,
        flags=re.M,
    )
    library_text, count_library = re.subn(
        r'(const ENGINE_VERSION: &str = ")[^"]+"',
        lambda match: match.group(1) + version + '"',
        library.read_text("utf-8"),
        count=1,
    )
    if count_manifest != 1 or count_library != 1:
        raise RuntimeError("could not update both AdBlock version declarations")
    if not shutil.which("cargo"):
        raise RuntimeError("cargo is required to update the locked AdBlock dependency")
    manifest.write_text(manifest_text, "utf-8")
    library.write_text(library_text, "utf-8")
    run([
        "cargo", "update", "-p", "adblock", "--precise", version,
        "--manifest-path", str(manifest),
    ])


def scriptlets_hash(data):
    payload = json.dumps(data["scriptlets"], sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_scriptlets(root, work, ubo_src=None):
    source = work / "src"
    if ubo_src:
        os.symlink(Path(ubo_src).resolve(), source)
    else:
        run(["git", "clone", "--quiet", "--depth", "1", UBO_GIT, str(source)])
    run(["node", str(root / "tools" / "build-ubo-scriptlets.mjs")], cwd=work)
    return work / "ubo-scriptlets.json"


def check_scriptlets(root, work, ubo_src=None):
    current = json.loads((root / "ike" / "resources" / "ubo-scriptlets.json").read_text("utf-8"))
    built = build_scriptlets(root, work, ubo_src)
    latest = json.loads(built.read_text("utf-8"))
    changed = scriptlets_hash(current) != scriptlets_hash(latest)
    current_names, latest_names = set(current["scriptlets"]), set(latest["scriptlets"])
    note = ""
    if changed:
        modified = sum(
            current[name] != latest[name]
            for name in current_names & latest_names
        )
        note = "%d changed, %d new, %d removed" % (
            modified, len(latest_names - current_names), len(current_names - latest_names)
        )
    return {
        "current": "%s (%s)" % (current["commit"][:10], current["date"]),
        "latest": "%s (%s)" % (latest["commit"][:10], latest["date"]),
        "update": changed,
        "note": note,
        "_file": str(built),
    }


def apply_scriptlets(root, info):
    shutil.copyfile(info["_file"], root / "ike" / "resources" / "ubo-scriptlets.json")


def check_all(root, ubo_src=None, work=None):
    work = Path(work or tempfile.mkdtemp(prefix="ike-check-"))
    work.mkdir(parents=True, exist_ok=True)
    checks = [
        ("adblock-rust (AdBlock engine)", check_adblock, apply_adblock, ()),
        ("uBlock Origin scriptlets", check_scriptlets, apply_scriptlets, (work, ubo_src)),
    ]
    results = []
    for name, check, apply, args in checks:
        try:
            info = check(root, *args)
            info.setdefault("also", "")
            info["error"] = ""
        except Exception as error:
            info = {
                "current": "",
                "latest": "",
                "update": False,
                "note": "",
                "also": "",
                "error": "%s: %s" % (
                    type(error).__name__,
                    (getattr(error, "stderr", "") or str(error)).strip()[:300],
                ),
            }
        info["name"] = name
        info["_apply"] = apply
        results.append(info)
    return results


def public(results):
    return [{key: value for key, value in result.items() if not key.startswith("_")}
            for result in results]


def to_markdown(results):
    updates = sum(result["update"] for result in results)
    errors = sum(bool(result["error"]) for result in results)
    lines = [
        "Arch / CachyOS component check: **%d updates**, **%d errors**. Checked %s UTC.\n"
        % (updates, errors, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")),
        "| Component | In use | Newest | Update | Notes |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        notes = "; ".join(
            value for value in (
                result["note"],
                ("**check failed**: " + result["error"]) if result["error"] else "",
            ) if value
        )
        lines.append("| %s | %s | %s | %s | %s |" % (
            result["name"], result["current"], result["latest"],
            "**yes**" if result["update"] else "no", notes.replace("|", "\\|"),
        ))
    lines.extend([
        "",
        "Only the Rust AdBlock engine and uBlock Origin scriptlets are checked. "
        "Python, PyQt6, Qt and Qt WebEngine remain system-managed by Arch Linux.",
    ])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", help="write the result as JSON")
    parser.add_argument("--markdown", help="write a Markdown report")
    parser.add_argument("--apply", action="store_true", help="apply every newer component version")
    parser.add_argument("--ubo-src", help="use this uBlock Origin checkout instead of cloning")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)

    with tempfile.TemporaryDirectory(prefix="ike-check-") as temporary:
        results = check_all(root, args.ubo_src, Path(temporary))
        updates = sum(result["update"] for result in results)
        errors = sum(bool(result["error"]) for result in results)
        for result in results:
            state = "ERROR" if result["error"] else ("NEW" if result["update"] else "ok")
            detail = result["error"] or result["note"]
            print("%-30s %-5s %s -> %s %s" % (
                result["name"], state, result["current"], result["latest"], detail
            ))
        print("updates: %d, errors: %d" % (updates, errors))

        if args.json:
            Path(args.json).write_text(json.dumps({
                "updates": updates, "errors": errors, "components": public(results),
            }, indent=1) + "\n", "utf-8")
        if args.markdown:
            Path(args.markdown).write_text(to_markdown(results), "utf-8")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("updates=%d\nerrors=%d\n" % (updates, errors))

        if args.apply:
            if errors:
                print("not applying updates: at least one component source could not be checked")
                return 1
            for result in results:
                if result["update"]:
                    result["_apply"](root, result)
                    print("applied:", result["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
