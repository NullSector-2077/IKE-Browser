#!/usr/bin/env python3
"""Keep docs/THIRD-PARTY.md in step with the AdBlock engine (1.1.14).

Rewrites the adblock-rust version in the components table and the list of the
Rust libraries linked into ``ike_adblock`` (name, version, licence), from
``ike-adblock/Cargo.lock`` and ``cargo metadata``. The daily maintenance runs
it whenever it moves adblock-rust to a new version (tools/check-components.py),
and the tests check that the file matches Cargo.lock. Run from anywhere:

    python3 tools/third-party.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "THIRD-PARTY.md"
MANIFEST = ROOT / "ike-adblock" / "Cargo.toml"
LOCK = ROOT / "ike-adblock" / "Cargo.lock"


def locked_packages(lock_text):
    """[(name, version)] of Cargo.lock, sorted as cargo lists them."""
    return re.findall(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', lock_text)


def licences():
    """{(name, version): licence} from cargo metadata (downloads the crate manifests if needed)."""
    out = subprocess.run(["cargo", "metadata", "--format-version", "1", "--locked",
                          "--manifest-path", str(MANIFEST)],
                         check=True, capture_output=True, text=True).stdout
    return {(p["name"], p["version"]): (p.get("license") or "see the crate")
            for p in json.loads(out)["packages"]}


def render(text, packages, lic):
    adblock = dict(packages).get("adblock")
    if adblock:
        text = re.sub(r"adblock-rust [0-9][^ ]* \(filter engine, by Brave\)",
                      "adblock-rust %s (filter engine, by Brave)" % adblock, text)
    lines = ["%s v%s — %s" % (n, v, lic.get((n, v), "see the crate")) for n, v in packages]
    block = "## Rust libraries linked into `ike_adblock`\n\n```\n%s\n```\n" % "\n".join(lines)
    return re.sub(r"## Rust libraries linked into `ike_adblock`\n\n```\n.*?\n```\n", lambda m: block,
                  text, flags=re.S)


def main():
    packages = locked_packages(LOCK.read_text("utf-8"))
    new = render(DOC.read_text("utf-8"), packages, licences())
    if new != DOC.read_text("utf-8"):
        DOC.write_text(new, "utf-8")
        print("docs/THIRD-PARTY.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
