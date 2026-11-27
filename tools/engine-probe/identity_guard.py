#!/usr/bin/env python3
"""The weekly check of I.K.E.'s engine identity (1.1.29; engine-identity.yml).

After every update of Qt WebEngine (and of I.K.E.'s own protection) sites
must still see an ordinary Chromium of the engine's own version. This reads
the probe's results (run.py) of I.K.E. at Balanced and Strict and of Arch's
Chromium of the engine's version (the workflow takes it from the Arch Linux
Archive by the installed engine's version: nothing is written here by hand),
and writes, in Italian, the lines the signing notice shows
(release-ready.yml), and the same findings as JSON. It never fails a run
for a finding: the owner reads it before signing; no AI changes what it
checks (tier B).

    identity_guard.py DIR BASELINE.json NOTICE.md RESULT.json [RUN_URL]

DIR holds ike-balanced.json, ike-strict.json, chromium.json (probe.html)
and ike-balanced-extra.json, chromium-extra.json (extra.html).

Checks, each against the Chromium of the run, never against fixed values
where the reference can give them:
  1. the layer works: window.chrome has Chromium's keys, permissions.query
     answers as Chromium, the network is the common one, the advertising
     APIs are gone and the profile kept no attribution source;
  2. one identity in the page, the frame and the workers (User-Agent,
     versions, platform, first language, Intl's language);
  3. the network identity is Chromium's of that version (JA4);
  4. engine-only gaps: interfaces Chromium has and I.K.E. lacks, compared
     with BASELINE: a new one is a new way to recognise the engine, one that
     is gone is good news (record it).
"""

import json
import sys
from pathlib import Path

REALMS = ("page", "iframe", "dedicated", "shared", "service")
PERMS_SHOWN = ("midi", "background-fetch", "background-sync", "persistent-storage", "accelerometer", "gyroscope",
               "magnetometer", "clipboard-write", "payment-handler", "idle-detection", "screen-wake-lock",
               "storage-access", "window-management", "captured-surface-control", "keyboard-lock",
               "pointer-lock", "local-network-access")
NETWORK = [50, 10]
ADS = ("HTMLImageElement.attributionSrc", "Document.browsingTopics")


def load(d, name):
    p = Path(d) / (name + ".json")
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8"))


def has(globals_, name):
    if "." in name:
        iface, member = name.split(".", 1)
        return member in globals_.get(iface, {}).get("p", [])
    return name in globals_


def identity(realm):
    n = realm.get("nav") or {}
    u = n.get("uaHigh") if isinstance(n.get("uaHigh"), dict) else {}
    intl = realm.get("intl") or {}
    loc = (intl.get("resolved") or {}).get("locale") if isinstance(intl.get("resolved"), dict) else None
    return {"userAgent": n.get("userAgent"), "versions": json.dumps(u.get("fullVersionList")),
            "platform": n.get("platform"), "platformVersion": u.get("platformVersion"),
            "language": n.get("language"), "intl": loc}


def ja4(raw):
    for t in (raw or {}).get("tls", []):
        if t.get("hello"):
            return t["hello"].get("ja4")
    return None


def check_level(name, raw, ref, findings):
    """Checks 1 and 2 for one I.K.E. result; findings: (ok, text)."""
    r = (raw or {}).get("result")
    if not r:
        findings.append((False, "%s: la prova non ha dato risultati" % name))
        return
    page, cpage = r["page"], ref["page"]
    want = ref["chrome"].get("keys") if isinstance(ref.get("chrome"), dict) else None
    got = r["chrome"].get("keys") if isinstance(r.get("chrome"), dict) else None
    findings.append((got == want, "%s: window.chrome %s" % (name, "come Chromium" if got == want
                                                            else "diverso da Chromium (%s / %s)" % (got, want))))
    bad = [p for p in PERMS_SHOWN if page["perms"].get(p) != cpage["perms"].get(p)]
    findings.append((not bad, "%s: permessi %s" % (name, "come Chromium" if not bad else "diversi: " + ", ".join(bad))))
    c = page["nav"].get("connection") or {}
    net = [c.get("rtt"), c.get("downlink")]
    findings.append((net == NETWORK, "%s: rete comune %s" % (name, "sì" if net == NETWORK else "no (%s)" % net)))
    left = [a for a in ADS if has(page["surface"]["globals"], a)]
    findings.append((not left, "%s: API pubblicitarie %s" % (name, "spente" if not left else "presenti: " + ", ".join(left))))
    # one identity everywhere (the workers a level refuses are left out, and named)
    base = identity(page)
    odd, refused = [], []
    for k in REALMS[1:]:
        v = r.get(k)
        if not isinstance(v, dict):
            refused.append(k)
            continue
        diff = [f for f, x in identity(v).items() if x != base[f]]
        if diff:
            odd.append("%s (%s)" % (k, ", ".join(diff)))
    text = "%s: stessa identità in pagina, frame e worker" % name
    if refused:
        text += " (worker non disponibili a questo livello: %s)" % ", ".join(refused)
    findings.append((not odd, text if not odd else "%s: identità diversa in %s" % (name, "; ".join(odd))))


def main():
    d, baseline_path, notice_path, result_path = sys.argv[1:5]
    url = sys.argv[5] if len(sys.argv) > 5 else ""
    baseline = json.loads(Path(baseline_path).read_text("utf-8"))
    ref_raw = load(d, "chromium")
    ref = (ref_raw or {}).get("result")
    findings, info = [], []
    if not ref:
        lines = ["**Identità del motore** (controllo settimanale): non eseguito, il Chromium di riferimento "
                 "non ha dato risultati%s." % (" ([dettagli](%s))" % url if url else "")]
        Path(notice_path).write_text("\n".join(lines) + "\n", "utf-8")
        Path(result_path).write_text(json.dumps({"ok": None, "findings": []}), "utf-8")
        return
    for level in ("balanced", "strict"):
        check_level("Balanced" if level == "balanced" else "Strict", load(d, "ike-" + level), ref, findings)
    extra = (load(d, "ike-balanced-extra") or {})
    if extra:
        kept = extra.get("conversions_sources")
        findings.append((not kept, "Balanced: fonti pubblicitarie salvate nel profilo: %s" % (kept or "nessuna")))
    # the reference must be the engine's own version: another one differs in
    # everything that changed between the two, which is no finding
    def major(raw):
        ua = (((raw or {}).get("result") or {}).get("page", {}).get("nav", {}) or {}).get("userAgent") or ""
        return ua.split("Chrome/")[1].split(".")[0] if "Chrome/" in ua else None
    same = major(load(d, "ike-balanced")) == major(ref_raw)
    if not same:
        info.append("Il Chromium di riferimento è di un'altra versione (%s, il motore %s): connessione e interfacce "
                    "non confrontate." % (major(ref_raw), major(load(d, "ike-balanced"))))
    a, b = ja4(load(d, "ike-balanced")), ja4(ref_raw)
    if not same:
        a = b
    findings.append((a == b, "connessione cifrata (JA4) %s" % ("uguale a Chromium" if a == b else "diversa: %s / %s" % (a, b))))
    ike = ((load(d, "ike-balanced") or {}).get("result") or {}).get("page", {}).get("surface", {}).get("globals", {})
    gaps = sorted(k for k in ref["page"]["surface"]["globals"] if k not in ike) if ike else []
    new = sorted(set(gaps) - set(baseline.get("gaps", [])))
    gone = sorted(set(baseline.get("gaps", [])) - set(gaps))
    if ike and same:
        findings.append((not new, "interfacce che Chromium ha e il motore no: %d%s" % (
            len(gaps), "" if not new else "; **nuove**: " + ", ".join(new))))
    if gone and same:
        info.append("Il motore ora ha anche: %s (da togliere dall'elenco di riferimento)." % ", ".join(gone))
    engine = (ref_raw.get("engine") or {})
    bad = [t for ok, t in findings if not ok]
    head = "**Identità del motore** (controllo settimanale%s): " % (", [dettagli](%s)" % url if url else "")
    if engine:
        head += "Qt WebEngine %s confrontato con Chromium %s. " % (engine.get("qt", "?"), engine.get("ref", "?"))
    head += "Tutto come previsto." if not bad else "Da guardare:"
    lines = [head] + ["- %s" % t for t in bad] + info
    Path(notice_path).write_text("\n".join(lines) + "\n", "utf-8")
    Path(result_path).write_text(json.dumps({"ok": not bad, "findings": findings, "gaps": gaps, "new": new,
                                             "gone": gone}, indent=1, ensure_ascii=False), "utf-8")
    print("\n".join(lines))
    for ok, t in findings:
        print(("ok   " if ok else "NO   ") + t)


if __name__ == "__main__":
    main()
