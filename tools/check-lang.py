#!/usr/bin/env python3
"""Check the language packs in ike/resources/lang/ against the source strings.

For each pack: missing and unknown strings, and translations that changed a
placeholder (%s, %d, %%, {url}, {lang}, {q}), the number of "&" accelerators,
or a final "…" / ":". Run from the repository root:

    python3 tools/check-lang.py [code ...]
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ike.i18n import template  # noqa: E402

PLACEHOLDER = re.compile(r"%[sd%]|\{[a-z]+\}")


def problems(src, dst):
    out = []
    if sorted(PLACEHOLDER.findall(src)) != sorted(PLACEHOLDER.findall(dst)):
        out.append("placeholders")
    if src.count("&") != dst.count("&"):
        out.append("accelerator &")
    for end in ("…", ":"):
        if src.endswith(end) and not dst.endswith(end):
            out.append("final " + end)
    return out


def main(codes):
    if hasattr(sys.stdout, "reconfigure"):       # Windows consoles: names such as Español
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    strings = set(template())
    folder = ROOT / "ike" / "resources" / "lang"
    files = [folder / (c + ".json") for c in codes] if codes else sorted(folder.glob("*.json"))
    bad = 0
    for f in files:
        pack = json.loads(f.read_text("utf-8"))
        tr = pack["strings"]
        missing = sorted(strings - set(tr))
        unknown = sorted(set(tr) - strings)
        wrong = [(k, p) for k, v in tr.items() if k in strings for p in [problems(k, v)] if p]
        print("%s (%s): %d/%d translated, %d missing, %d unknown, %d with errors"
              % (pack.get("code"), pack.get("name"), len(set(tr) & strings), len(strings),
                 len(missing), len(unknown), len(wrong)))
        for k, p in wrong:
            print("   error (%s): %r" % (", ".join(p), k))
        for k in unknown:
            print("   unknown: %r" % k)
        bad += len(wrong)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
