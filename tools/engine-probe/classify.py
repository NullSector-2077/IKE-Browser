#!/usr/bin/env python3
"""Where each difference between I.K.E. and Chromium of the same generation
comes from (study "Engine Privacy Layer", round 2: Chromium as the target).

    python3 tools/engine-probe/classify.py DIR TARGET QT [IKE...] [--again SUFFIX] [--json OUT]

DIR holds run.py results: TARGET (Arch's Chromium of the engine's version)
and TARGET+SUFFIX (a second run of it), QT and QT+SUFFIX (bare Qt WebEngine),
and each IKE result (I.K.E. at a level, or with switches). Facts that depend
on the computer are left out (diff.py). Every differing fact of an IKE
result falls in one bucket:

  noise     differs between two runs of the same browser, or is only the
            engine's own patch number (Qt has later security fixes)
  engine    I.K.E. has bare Qt WebEngine's value: comes from the engine
  ike       I.K.E. has neither Qt's nor Chromium's value: I.K.E.'s own choice
  tls-test  the probe's HTTPS test could not complete with this browser

and "signals" count each thing once (a header in every request, a member of
one interface, one CSS property).
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diff as D  # noqa: E402

PATCH = re.compile(r"140\.0\.7339\.\d+|\d+\.0\.\d{4}\.\d+")
REALMS = ("iframe", "dedicated", "shared", "service")


def signal(key):
    k = key
    m = re.match(r"(page|iframe|dedicated|shared|service)\.surface\.globals\.([^.\[]+)", k)
    if m:
        return "api:" + m.group(2)
    m = re.match(r"headers\.\S+ \S+\.([a-z0-9-]+)$", k)
    if m:
        return "header:" + m.group(1)
    if re.match(r"headers\.\S+ \S+\.order$", k):
        return "header-order"
    m = re.match(r"css\.(computed|supports|atrules)\W(.*)", k)
    if m:
        return "css:" + re.split(r"[:(\]{ ]", m.group(2).strip())[0]
    m = re.match(r"(page|iframe|dedicated|shared|service)\.(\w+)\.([^.\[]+)", k)
    if m:
        return "%s:%s" % (m.group(2), m.group(3))
    m = re.match(r"(\w+)\.([^.\[]+)", k)
    return "%s:%s" % (m.group(1), m.group(2)) if m else k


def load(d, name):
    p = Path(d) / (name + ".json")
    return D.facts(str(p)) if p.exists() else None


def unwrap(v):
    return PATCH.sub("V", str(v))


def classify(dirname, target, qt, ike, again):
    T, T2, Q, Q2, I = (load(dirname, n) for n in (target, target + again, qt, qt + again, ike))
    raw = json.load(open(Path(dirname) / (ike + ".json")))
    tls_failed = not any(t.get("alpn") for t in raw.get("tls", []))
    buckets, sig = Counter(), defaultdict(set)
    detail = defaultdict(list)
    for k in set(I) | set(T):
        if D.category(k) == "environment" or k.endswith(".#"):
            continue
        iv, tv = I.get(k, "<absent>"), T.get(k, "<absent>")
        if iv == tv:
            continue
        realm = k.split(".")[0] in REALMS
        if (T2 and T2.get(k, "<absent>") != tv) or (Q and Q2 and Q.get(k, "<absent>") != Q2.get(k, "<absent>")) \
                or unwrap(iv) == unwrap(tv):
            b = "noise"
        elif k.startswith("tls.") and tls_failed:
            b = "tls-test"
        elif Q is not None and Q.get(k, "<absent>") == iv:
            b = "engine"
        else:
            b = "ike"
        if realm:
            b += " (frame/workers)"
        buckets[b] += 1
        sig[b].add(signal(k))
        detail[b].append([k, iv, tv])
    return buckets, sig, detail


def main():
    args = [a for a in sys.argv[1:]]
    again = "-again"
    out = None
    if "--again" in args:
        i = args.index("--again"); again = args[i + 1]; del args[i:i + 2]
    if "--json" in args:
        i = args.index("--json"); out = args[i + 1]; del args[i:i + 2]
    dirname, target, qt, ikes = args[0], args[1], args[2], args[3:]
    report = {}
    for ike in [qt] + ikes:
        b, s, det = classify(dirname, target, qt, ike, again)
        report[ike] = {"facts": dict(b), "signals": {k: sorted(v) for k, v in s.items()}, "detail": det}
        page = {k: v for k, v in b.items() if "frame" not in k}
        print("%-28s facts %-60s signals %s" % (ike, json.dumps(page), json.dumps({k: len(v) for k, v in s.items() if "frame" not in k})))
    if out:
        json.dump(report, open(out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
