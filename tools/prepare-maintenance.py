#!/usr/bin/env python3
"""Prepare a versioned IKE maintenance candidate from check-components.json."""
import argparse
import json
import re
from pathlib import Path


def replace_one(path, pattern, replacement, flags=0):
    text = path.read_text("utf-8")
    changed, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit("expected exactly one match in %s: %s" % (path, pattern))
    path.write_text(changed, "utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--base-version",
                    help="version from main; daily updates reuse the same candidate version")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    report = json.loads(Path(args.report).read_text("utf-8"))
    if report.get("errors"):
        raise SystemExit("refusing to prepare a candidate: component checks contain errors")
    changed = [c for c in report["components"] if c.get("update") or c.get("also")]
    if not changed:
        print("No component changes; no candidate version needed.")
        return 0

    init = root / "ike" / "__init__.py"
    text = init.read_text("utf-8")
    current = re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', text, re.M)
    if not current:
        raise SystemExit("IKE version is not a stable three-part release")
    base = args.base_version or ".".join(current.groups())
    parsed = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", base)
    if not parsed:
        raise SystemExit("base version is not a stable three-part release")
    major, minor, patch = map(int, parsed.groups())
    version = "%d.%d.%d" % (major, minor, patch + 1)
    replace_one(init, r'^__version__ = "[^"]+"$', '__version__ = "%s"' % version, re.M)

    adblock_changed = any(c["name"].startswith("adblock-rust") and c.get("update") for c in changed)
    if adblock_changed:
        replace_one(init, r'^__min_system__ = "[^"]+"$',
                    '__min_system__ = "%s"' % version, re.M)

    replace_one(root / "PKGBUILD", r'^pkgver=.*$', "pkgver=%s" % version, re.M)
    replace_one(root / "PKGBUILD", r'^pkgrel=.*$', "pkgrel=1", re.M)
    # the DEB and RPM recipes carry the same version (tests/test_packaging.py)
    deb = root / "packaging" / "debian" / "changelog"
    if deb.exists():
        import email.utils
        old_deb = deb.read_text("utf-8")
        entry = ("ike-browser (%s-1) unstable; urgency=medium\n\n"
                 "  * Component maintenance; see CHANGELOG.md in /usr/share/doc/ike-browser.\n\n"
                 " -- The I.K.E. project <noreply@github.com>  %s\n\n"
                 % (version, email.utils.formatdate(usegmt=False)))
        if not old_deb.startswith("ike-browser (%s-1)" % version):
            deb.write_text(entry + old_deb, "utf-8")
    spec = root / "packaging" / "rpm" / "ike-browser.spec"
    if spec.exists():
        replace_one(spec, r'^Version:(\s+).*$', r"Version:\g<1>%s" % version, re.M)
        replace_one(spec, r'^Release:(\s+).*$', r"Release:\g<1>1%{?dist}", re.M)
    replace_one(root / "README.md", r'^\*\*Version [^\n]+',
                "**Version %s** - see [CHANGELOG.md](CHANGELOG.md)." % version, re.M)
    replace_one(root / "README.md", r'ike-browser-[0-9]+\.[0-9]+\.[0-9]+-1-x86_64\.pkg\.tar\.zst',
                "ike-browser-%s-1-x86_64.pkg.tar.zst" % version)

    bullets = []
    for component in changed:
        bullets.append("- %s: %s -> %s%s" % (
            component["name"], component.get("current") or "current",
            component.get("latest") or "updated",
            (" (" + component["note"] + ")") if component.get("note") else ""))
    if adblock_changed:
        bullets.append("- AdBlock engine system component updated; minimum compatible system package is now %s." % version)

    changelog = root / "CHANGELOG.md"
    old_log = changelog.read_text("utf-8")
    if not old_log.startswith("# Changelog\n"):
        raise SystemExit("unexpected CHANGELOG.md header")
    rest = old_log[len("# Changelog\n"):].lstrip("\n")
    heading = "## %s\n" % version
    if rest.startswith(heading):
        tail = rest[len(heading):]
        next_heading = re.search(r'^## ', tail, re.M)
        end = next_heading.start() if next_heading else len(tail)
        section = tail[:end].rstrip()
        rest = heading + section + "\n" + "\n".join(bullets) + "\n\n" + tail[end:].lstrip("\n")
    else:
        rest = heading + "\n" + "\n".join(bullets) + "\n\n" + rest
    changelog.write_text("# Changelog\n\n" + rest, "utf-8")

    print("Prepared I.K.E. %s from component changes:" % version)
    for bullet in bullets:
        print(bullet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
