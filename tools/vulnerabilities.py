#!/usr/bin/env python3
"""Known vulnerabilities of the inventory's components (WP7 of the maintenance plan).

Called by tools/inventory.py in GitHub Actions only (the daily check's ledger
job): the browser never asks these services. Sources, GET or POST of public
data, no account, no key, nothing about I.K.E.'s users:

- the OSV database (https://api.osv.dev): ``POST /v1/querybatch`` with the
  name and version of each component, in batches of OSV_BATCH, then ``GET
  /v1/vulns/<id>`` once per advisory found for its summary and fixed
  versions. Ecosystems: PyPI (the test and CI packages of the workflows,
  pinned in tools/test-requirements.txt), npm (Dark Reader's engine, and the
  modules of tools/*.mjs when a version is known) and GitHub Actions (each
  ``uses:`` pinned to a commit, by the release its comment names);
- the Arch Linux security tracker (https://security.archlinux.org,
  ``/issues/all.json``: every advisory group, AVG, with its packages, status,
  affected and fixed versions, the JSON that arch-audit reads) for the Arch
  packages I.K.E. depends on, at the versions the last green arch.yml run on
  main tested;
- the crates keep cargo-deny and RustSec (security.yml), as before.

A source that does not answer leaves its components **not checked**, never
"none known": a clean result needs a check that ran. Each advisory is recorded
once per component (by its id), in the record's ``advisories`` and in its
``vulnerabilities`` text; tools/maintenance-ledger.py turns each into one
ledger entry. No AI; the automatic fix may never change this file.
"""

import json
import re
import urllib.parse
import urllib.request

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/%s"
OSV_PAGE = "https://osv.dev/vulnerability/%s"
ARCH_TRACKER_URL = "https://security.archlinux.org/issues/all.json"
ARCH_GROUP_PAGE = "https://security.archlinux.org/%s"
OSV_BATCH = 500                 # OSV takes up to 1000 queries a request
OSV_PAGES = 5                   # a query with more advisories than one page: at most this many pages
OSV_DETAILS = 200               # advisories read in detail in one run
SOURCES = ("api.osv.dev", "security.archlinux.org")
NOT_CHECKED = "not checked"
ARCH_KINDS = ("arch-package", "arch-optional", "arch-build")
# the tracker's statuses: Vulnerable (no fix in the repositories), Testing (a fix in [testing]),
# Fixed (in the repositories from "fixed" on), Not affected, Unknown
ARCH_OPEN = ("Vulnerable", "Testing")


def post_json(url, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "User-Agent": "ike-browser-component-check", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _version(text):
    m = re.match(r"^v?(\d+(?:\.\d+)*(?:[-.+]?[A-Za-z0-9.]+)?)$", str(text or "").strip())
    return m.group(1) if m else ""


def osv_targets(records):
    """[(record, ecosystem, package name, version)] and {record id: why it is not asked}."""
    asked, skipped = [], {}
    for rec in records.values():
        kind = rec["kind"]
        if kind in ("pypi-test", "pypi-ci"):
            ver = _version(rec.get("installed"))
            if ver and re.match(r"^\d", ver):
                asked.append((rec, "PyPI", rec["name"], ver))
            else:
                skipped[rec["id"]] = "no pinned version to ask about"
        elif kind == "npm":
            ver = _version(rec.get("installed"))
            if ver and re.match(r"^\d", ver):
                asked.append((rec, "npm", rec["name"], ver))
            else:
                skipped[rec["id"]] = "no pinned version: no lockfile pins it"
        elif kind == "integrated" and rec.get("npm_version"):
            asked.append((rec, "npm", "darkreader", _version(rec["npm_version"]) or rec["npm_version"]))
        elif kind == "github-action":
            ver = _version(rec.get("release"))
            if rec.get("pinned_sha") and ver and re.match(r"^\d", ver):
                asked.append((rec, "GitHub Actions", rec["name"], ver))
            else:
                skipped[rec["id"]] = "no release named next to the pinned commit"
    return asked, skipped


def _norm(ecosystem, name):
    name = str(name or "")
    return re.sub(r"[-_.]+", "-", name).lower() if ecosystem == "PyPI" else name.lower()


def _fixed_in(vuln, ecosystem, name):
    """The versions the advisory says are fixed, for this package."""
    out = []
    for aff in vuln.get("affected") or []:
        pkg = aff.get("package") or {}
        if pkg.get("ecosystem") != ecosystem or _norm(ecosystem, pkg.get("name")) != _norm(ecosystem, name):
            continue
        for rng in aff.get("ranges") or []:
            for ev in rng.get("events") or []:
                if ev.get("fixed") and ev["fixed"] not in out:
                    out.append(ev["fixed"])
    return out


def check_osv(records, post, get):
    """Ask OSV about every PyPI, npm and GitHub Actions component; fill their advisories.
    Returns the source's state: "ok" or "unreachable: ..."."""
    asked, skipped = osv_targets(records)
    for rid, why in skipped.items():
        _not_checked(records[rid], why)
    if not asked:
        return "ok"
    found = {}                                  # record id -> [vuln ids]
    try:
        for start in range(0, len(asked), OSV_BATCH):
            chunk = asked[start:start + OSV_BATCH]
            queries = [{"package": {"name": name, "ecosystem": eco}, "version": ver} for _, eco, name, ver in chunk]
            pending = list(range(len(chunk)))
            for _ in range(OSV_PAGES):
                answer = json.loads(post(OSV_BATCH_URL, {"queries": [queries[i] for i in pending]}).decode("utf-8"))
                results = answer.get("results")
                if not isinstance(results, list) or len(results) != len(pending):
                    raise ValueError("OSV answered %s results for %d queries" % (
                        len(results) if isinstance(results, list) else "no", len(pending)))
                more = []
                for i, res in zip(pending, results):
                    rec = chunk[i][0]
                    ids = found.setdefault(rec["id"], [])
                    for v in (res or {}).get("vulns") or []:
                        if v.get("id") and v["id"] not in ids:
                            ids.append(v["id"])
                    if (res or {}).get("next_page_token"):
                        queries[i] = dict(queries[i], page_token=res["next_page_token"])
                        more.append(i)
                pending = more
                if not pending:
                    break
        details, read = {}, 0
        for rec, eco, name, ver in asked:
            advisories = []
            for vid in found.get(rec["id"], []):
                if vid not in details and read < OSV_DETAILS:
                    details[vid] = json.loads(get(OSV_VULN_URL % urllib.parse.quote(vid)).decode("utf-8"))
                    read += 1
                vuln = details.get(vid) or {}
                advisories.append({"id": vid, "source": "OSV", "summary": (vuln.get("summary") or "")[:200],
                                   "aliases": (vuln.get("aliases") or [])[:6], "fixed": _fixed_in(vuln, eco, name),
                                   "url": OSV_PAGE % vid, "package": "%s %s (%s)" % (name, ver, eco)})
            _record(rec, advisories, "OSV, %s %s" % (eco, ver))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        why = "unreachable: %s" % ("%s: %s" % (type(e).__name__, e))[:160]
        for rec, *_ in asked:
            _not_checked(rec, "api.osv.dev " + why)
            rec.pop("advisories", None)
        return why
    return "ok"


def _not_checked(rec, why):
    """A component no source could judge: "not checked" (never "none known"), and why."""
    rec["vulnerabilities"] = NOT_CHECKED
    rec["vulnerability_note"] = why[:200]


def _record(rec, advisories, where):
    rec.pop("vulnerability_note", None)
    seen, unique = set(), []
    for a in advisories:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    rec["advisories"] = unique
    if unique:
        rec["vulnerabilities"] = "%d known (%s): %s" % (len(unique), where, ", ".join(
            "%s%s" % (a["id"], " fixed in %s" % "/".join(a["fixed"][:3]) if a["fixed"] else " no fix upstream")
            for a in unique[:6]))
    else:
        rec["vulnerabilities"] = "none known (%s)" % where


# --- Arch Linux's security tracker -------------------------------------------------------------------

def _split(version):
    """(epoch, pkgver, pkgrel) of an Arch version "1:2.3-4"."""
    v = str(version or "")
    epoch, _, rest = v.rpartition(":") if ":" in v else ("0", "", v)
    ver, _, rel = rest.rpartition("-") if "-" in rest else (rest, "", "")
    return int(epoch or 0) if str(epoch).isdigit() else 0, ver, rel


def _segments(text):
    return [int(s) if s.isdigit() else s for s in re.findall(r"\d+|[A-Za-z]+", text or "")]


def _cmp_part(a, b):
    sa, sb = _segments(a), _segments(b)
    for x, y in zip(sa, sb):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return -1 if x < y else 1
        if isinstance(x, int):
            return 1                    # a number is newer than letters (rpmvercmp)
        if isinstance(y, int):
            return -1
        return -1 if x < y else 1
    if len(sa) == len(sb):
        return 0
    longer, rest = (sa, sb) if len(sa) > len(sb) else (sb, sa)
    extra = longer[len(rest)]
    newer = isinstance(extra, int)      # 1.0.1 > 1.0; 1.0rc1 < 1.0
    return (1 if newer else -1) * (1 if longer is sa else -1)


def vercmp(a, b):
    """pacman's vercmp, close enough for the tracker's versions: -1, 0 or 1."""
    ea, va, ra = _split(a)
    eb, vb, rb = _split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    c = _cmp_part(va, vb)
    if c or not ra or not rb:
        return c
    return _cmp_part(ra, rb)


def arch_version(rec):
    """The version an Arch record stands for: the one the last green arch.yml run on main
    tested, else the one in the repositories today; "" when neither is a version."""
    for v in (rec.get("installed"), rec.get("available")):
        if v and re.match(r"^(\d+:)?\d", str(v)):
            return str(v)
    return ""


def check_arch(records, get):
    """The tracker's advisory groups for every Arch package of the inventory. Returns the
    source's state: "ok" or "unreachable: ..."."""
    targets = [r for r in records.values() if r["kind"] in ARCH_KINDS]
    if not targets:
        return "ok"
    try:
        groups = json.loads(get(ARCH_TRACKER_URL).decode("utf-8"))
        if not isinstance(groups, list):
            raise ValueError("the tracker's answer is not a list")
        by_package = {}
        for g in groups:
            if isinstance(g, dict):
                for p in g.get("packages") or []:
                    by_package.setdefault(p, []).append(g)
    except (OSError, ValueError, AttributeError) as e:
        why = "unreachable: %s" % ("%s: %s" % (type(e).__name__, e))[:160]
        for rec in targets:
            _not_checked(rec, "security.archlinux.org " + why)
        return why
    for rec in targets:
        ver = arch_version(rec)
        if not ver:
            _not_checked(rec, "no version of %s known to compare" % rec["name"])
            continue
        advisories = []
        for g in by_package.get(rec["name"], []):
            status, fixed = g.get("status"), g.get("fixed") or ""
            if status in ARCH_OPEN:
                hit = not fixed or vercmp(ver, fixed) < 0
                fix = [fixed] if fixed and status == "Testing" else []
            elif status == "Fixed" and fixed:
                hit, fix = vercmp(ver, fixed) < 0, [fixed]
            else:
                continue                # Not affected, Unknown
            if hit:
                advisories.append({"id": g.get("name") or "AVG-?", "source": "Arch security tracker",
                                   "summary": "%s, %s (%s)" % (g.get("type") or "vulnerability",
                                                               g.get("severity") or "?", status),
                                   "aliases": list(g.get("issues") or [])[:6], "fixed": fix,
                                   "url": ARCH_GROUP_PAGE % (g.get("name") or ""),
                                   "package": "%s %s (Arch)" % (rec["name"], ver)})
        _record(rec, advisories, "Arch security tracker, %s %s" % (rec["name"], ver))
    # the records that only point to an Arch package say where to look
    for rec in records.values():
        pkg = rec.get("provided_by")
        if rec["kind"] in ("python-module", "runtime-tool", "build-tool") and isinstance(pkg, str):
            src = records.get("arch-package:" + pkg) or records.get("arch-build:" + pkg) or \
                records.get("arch-optional:" + pkg)
            if src and src.get("vulnerabilities") != NOT_CHECKED:
                rec["vulnerabilities"] = "see its Arch package %s: %s" % (pkg, src["vulnerabilities"][:120])
    return "ok"


def check(records, post=None, get=None):
    """Every source, each on its own: {host: "ok" | "unreachable: ..."}. post(url, payload) and
    get(url) return bytes; both raise OSError when the host does not answer."""
    post = post or post_json
    get = get or (lambda url: _get(url))
    return {"api.osv.dev": check_osv(records, post, get), "security.archlinux.org": check_arch(records, get)}


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "ike-browser-component-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
