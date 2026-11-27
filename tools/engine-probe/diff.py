#!/usr/bin/env python3
"""Compare engine-probe results (run.py): what differs between two browsers,
grouped by surface.

    python3 tools/engine-probe/diff.py A.json B.json [--full] [--json OUT]

Every result is flattened into "path = value" facts (a list of names
becomes one fact per name), so a difference is a fact one side has and the
other has not, or has with another value. Volatile facts (times, the
probe's own durations) are left out.
"""

import json
import re
import sys
from collections import OrderedDict

VOLATILE = re.compile(r"(^|\.)(t0|ms|seconds|log|cmd|target|name|timer\.minStep|histLen|hasFocus|sx|sy)$")
# facts that come from the computer, the screen or the user's settings, not from the engine
ENVIRONMENT = re.compile(r"webgl|webgpu|wgsl|gpuPreferred|\.screen\.|canvasNoise|emoji|voices|quota|hardwareConcurrency|deviceMemory|"
                         r"\.mq\.|scrollbar|ech_len|viewport-(width|height)|defaults\.font|mcap|audio\.base")


def flatten(obj, prefix="", out=None):
    out = OrderedDict() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, prefix + "." + str(k) if prefix else str(k), out)
    elif isinstance(obj, list) and obj and all(isinstance(x, str) for x in obj):
        for x in obj:
            out["%s[%s]" % (prefix, x)] = True
        out[prefix + ".#"] = len(obj)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            flatten(x, "%s.%d" % (prefix, i), out)
        out[prefix + ".#"] = len(obj)
    else:
        out[prefix] = obj
    return out


def facts(path):
    d = json.load(open(path, encoding="utf-8"))
    r = d.get("result") or {}
    f = OrderedDict()
    for realm in ("page", "iframe", "dedicated", "shared", "service"):
        v = r.get(realm)
        if isinstance(v, dict):
            flatten(v, realm, f)
        else:
            f[realm] = v
    for k in ("css", "chrome", "doc", "wasm", "network"):
        flatten(r.get(k), k, f)
    # request headers: the names in their order, and the values, per kind of request
    seen = {}
    for h in d.get("headers", []):
        key = h["method"] + " " + h["path"]
        if key in seen:
            continue
        seen[key] = 1
        names = [n.lower() for n, _ in h["headers"] if n.lower() not in ("host", "content-length")]
        f["headers.%s.order" % key] = ",".join(names)
        for n, v in h["headers"]:
            n = n.lower()
            if n in ("host", "content-length", "referer", "origin"):
                continue
            f["headers.%s.%s" % (key, n)] = re.sub(r"127\.0\.0\.1:\d+", "HOST", v)
    for i, t in enumerate(d.get("tls", [])[:1]):
        h = dict(t.get("hello") or {})
        h.pop("extensions", None)                  # shuffled by Chrome on every connection
        h.pop("padding_len", None)
        flatten(h, "tls.hello", f)
        f["tls.alpn"] = t.get("alpn")
        if t.get("h2"):
            flatten({k: v for k, v in t["h2"].items() if k != "error"}, "tls.h2", f)
    return {k: v for k, v in f.items() if not VOLATILE.search(k)}


def category(key):
    if ENVIRONMENT.search(key):
        return "environment"
    head = key.split(".")[0]
    if head in ("page", "iframe", "dedicated", "shared", "service"):
        sub = key.split(".")[1] if "." in key else ""
        return "%s:%s" % (head, sub)
    return head


def compare(a, b):
    out = OrderedDict()
    for k in list(a) + [k for k in b if k not in a]:
        va, vb = a.get(k, "<absent>"), b.get(k, "<absent>")
        if va != vb:
            out.setdefault(category(k), []).append((k, va, vb))
    return out


def short(v, n=90):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n] + "..."


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    full = "--full" in sys.argv
    jout = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if jout in args:
        args.remove(jout)
    a, b = facts(args[0]), facts(args[1])
    diff = compare(a, b)
    total = sum(len(v) for v in diff.values())
    print("# %s vs %s: %d differing facts (of %d / %d)\n" % (args[0], args[1], total, len(a), len(b)))
    for cat, items in diff.items():
        print("## %s (%d)" % (cat, len(items)))
        for k, va, vb in (items if full else items[:25]):
            print("  %-70s %s  |  %s" % (short(k, 70), short(va, 45), short(vb, 45)))
        if not full and len(items) > 25:
            print("  ... %d more" % (len(items) - 25))
    if jout:
        json.dump({c: [[k, va, vb] for k, va, vb in v] for c, v in diff.items()}, open(jout, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
