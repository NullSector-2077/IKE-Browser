#!/usr/bin/env python3
"""Known vulnerabilities in the dependencies I.K.E. builds and tests with.

    python3 tools/audit-deps.py [--json FILE] [--markdown FILE]

- Rust: ike-adblock/Cargo.lock with `cargo audit` (the RustSec advisory
  database);
- Python: the pinned requirement files (tools/test-requirements.txt and,
  when present, packaging/windows/requirements*.txt) with `pip-audit`
  (the PyPI / OSV advisory data).

On Linux the browser runs on the distribution's own Qt and Python packages,
which their security teams follow; those are not audited here. Both tools are
installed by the daily workflow; when one is missing or fails, that is
counted as an error, never as "no vulnerabilities". Nothing is changed: the
report goes to the daily "components" issue, and the owner decides.
With GITHUB_OUTPUT set, writes ``vulnerabilities=N`` and ``audit_errors=N``.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def requirement_files(root):
    files = [root / "tools/test-requirements.txt"]
    files += sorted((root / "packaging/windows").glob("requirements*.txt"))
    return [f for f in files if f.is_file()]


def cargo_audit(root):
    """[(crate, version, advisory id, title)], error text or None."""
    if not shutil.which("cargo-audit") and not shutil.which("cargo"):
        return [], "cargo-audit is not installed"
    r = subprocess.run(["cargo", "audit", "--json", "--file", str(root / "ike-adblock/Cargo.lock")],
                       capture_output=True, text=True, timeout=600)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return [], "cargo audit failed: " + (r.stderr.strip().splitlines() or ["no output"])[-1]
    found = []
    for v in data.get("vulnerabilities", {}).get("list", []):
        adv, pkg = v.get("advisory", {}), v.get("package", {})
        found.append((pkg.get("name", "?"), pkg.get("version", "?"), adv.get("id", "?"), adv.get("title", "")))
    return found, None


def pip_audit(path):
    """[(package, version, advisory id, fix versions)], error text or None."""
    if not shutil.which("pip-audit"):
        return [], "pip-audit is not installed"
    r = subprocess.run(["pip-audit", "--requirement", str(path), "--format", "json", "--progress-spinner", "off",
                        "--disable-pip", "--no-deps"],
                       capture_output=True, text=True, timeout=900)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return [], "pip-audit failed on %s: %s" % (path.name, (r.stderr.strip().splitlines() or ["no output"])[-1])
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    found = []
    for d in deps:
        for v in d.get("vulns", []):
            found.append((d.get("name", "?"), d.get("version", "?"), v.get("id", "?"),
                          ", ".join(v.get("fix_versions", [])) or "no fix yet"))
    return found, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    root = Path(args.root)

    report = {"rust": [], "python": [], "errors": []}
    found, err = cargo_audit(root)
    report["rust"] = [dict(zip(("crate", "version", "id", "title"), f)) for f in found]
    if err:
        report["errors"].append(err)
    for path in requirement_files(root):
        found, err = pip_audit(path)
        report["python"] += [dict(zip(("package", "version", "id", "fix"), f), file=path.name) for f in found]
        if err:
            report["errors"].append(err)
    vulns = len(report["rust"]) + len(report["python"])

    lines = ["## Known vulnerabilities", ""]
    if not vulns and not report["errors"]:
        lines.append("None known in the Rust engine module and the pinned Python packages.")
    for v in report["rust"]:
        lines.append("- Rust `%s` %s: **%s** %s" % (v["crate"], v["version"], v["id"], v["title"]))
    for v in report["python"]:
        lines.append("- Python `%s` %s (%s): **%s**, fixed in %s"
                     % (v["package"], v["version"], v["file"], v["id"], v["fix"]))
    for e in report["errors"]:
        lines.append("- Could not check: %s" % e)
    md = "\n".join(lines) + "\n"
    print(md)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    if args.markdown:
        Path(args.markdown).write_text(md, "utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("vulnerabilities=%d\naudit_errors=%d\n" % (vulns, len(report["errors"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
