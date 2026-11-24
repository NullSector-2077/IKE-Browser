#!/usr/bin/env python3
"""The signing notice: what the owner's signature covers, in plain Italian (no AI here).

Since 2026-11-22 the only human step of the maintenance is the owner's signature
(``python3 tools/publish.py`` on the owner's computer), so the notice release-ready.yml opens (GitHub
mails it) must let the owner judge before signing. For the version in main that is not published
yet it lists every change merged since the last published version:

0. before everything else (part 2 of AUTOMAT), each **change an AI wrote on a reserved file** (tier B
   in the narrow form the owner opened with the repository variable AUTOMAT_TIER_B, tools/tier-b.py:
   a pinned version of a workflow, statements added to ike/app.py, ike/updater.py or ike_boot.py):
   its files, the three independent reviewers with their verdicts, "Nothing gets worse", its diff link;
1. first, clearly marked, the changes merged by themselves that touch **reserved files** (tier B of
   tools/fix-guard.py: the workflows, the tools, the sandbox and start, the signing and update
   channel, the package): today only the automation's own deterministic tools change them (a pin of
   the workflows, a builder re-anchored under tools/builder-anchor.py), each with its diff link;
2. each **change an AI wrote on protected code** (tier A): its files, a one-line summary, the two
   independent reviewers with their verdicts, and the result of "Nothing gets worse" (no-regression)
   on the merged commit;
3. the other changes merged by themselves (updates, fixes of ordinary code) and the pull requests
   merged by a person's order, one line each;
4. the updates that are **still being retried** (the maintenance ledger's "retrying" and "blocked"
   entries, the open pull requests of the automation): nothing the owner must do, but what this
   version does not contain yet;
5. the **free quota of each AI provider** (part 2 of AUTOMAT, tools/ai-quota.py): what was used today
   and in the last days, the limit, what is left, and whether the limit was verified or is a careful
   guess.

GET calls only. What cannot be read is said as "non letto", never left out or guessed. An AUTOMAT drill
(tools/automat-drill.py) is never listed: it never merges, and it is no update being retried.

    release-notice.py --repo OWNER/NAME --version X.Y.Z --owner LOGIN --out FILE
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SELF = "(merged by itself"
MERGE = re.compile(r"^Merge pull request #(\d+)")
# the clone when it is not there, main up to date, then the one command that signs and publishes
# (docs/UPDATES.md). In bash -c, so it is the same in fish (CachyOS's shell) as in bash.
STEPS = ("[ -d ~/IKE-Browser/.git ] || git clone https://github.com/NullSector-2077/IKE-Browser.git ~/IKE-Browser; "
         "cd ~/IKE-Browser && git checkout main && git pull --ff-only && python3 tools/publish.py")
COMMAND = "bash -c '%s'" % STEPS
READY = "LA RELEASE E' PRONTA DA FIRMARE"          # the owner's words: the notice's title and first line
VERSION_FILES = ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md")
MAX_LISTED = 40


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).resolve().parent /
                                                  (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gh_api(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:200]))
    return json.loads(out.stdout or "null")


def plain(text, limit=200):
    """One line of someone's words, safe in the notice: no mention, no link syntax, no code."""
    text = re.sub(r"\s+", " ", str(text or "")).replace("`", "'").replace("@", "@​")
    return re.sub(r"[\[\]<>]", "", text)[:limit].strip()


def change_of(repo, number, api, tools):
    """What one merged pull request was: {"n", "title", "self", "ai", "tier_a", "tier_b", "files",
    "reviews", "no_regression", "summary"}; unread parts are None."""
    fg, rv, am = tools
    out = {"n": number, "title": "", "ai": False, "tier_a": [], "tier_b": [], "files": None, "reviews": None,
           "no_regression": None, "summary": "", "author": "", "tier_b_ai": []}
    try:
        pr = api("repos/%s/pulls/%d" % (repo, number))
        commits = api("repos/%s/pulls/%d/commits?per_page=100" % (repo, number))
        files = api("repos/%s/pulls/%d/files?per_page=100" % (repo, number))
    except (RuntimeError, ValueError):
        return out
    sha = (pr.get("head") or {}).get("sha", "")
    out["title"] = plain(pr.get("title"))
    out["drill"] = _tool("automat-drill").is_drill_pr(pr, files)
    names = [f.get("filename", "") for f in files if f.get("filename") not in VERSION_FILES]
    out["files"] = names
    ai = [c for c in commits if rv.AUTOFIX_COMMIT.match((c.get("commit") or {}).get("message") or "")]
    out["ai"] = bool(ai)
    out["tier_b"] = sorted(n for n in names if fg.tier(n) == "B" and not n.startswith(("licenses/", "tests/data/"))
                           and n not in ("docs/THIRD-PARTY.md",) and not n.startswith("ike/resources/")
                           and not n.startswith(("ike-adblock/", "vendor/")))
    out["tier_a"] = sorted(n for n in names if fg.tier(n) == "A") if ai else []
    # a reserved file an AI commit itself changed (only possible with the owner's switch AUTOMAT_TIER_B)
    if ai and any(fg.tier_b_open(n) for n in names):
        touched = set()
        for c in ai:
            try:
                data = api("repos/%s/commits/%s" % (repo, c.get("sha")))
                touched.update(x.get("filename", "") for x in data.get("files") or [])
            except (RuntimeError, ValueError, AttributeError):
                touched.update(names)                  # not read: said as an AI's, never left out
        out["tier_b_ai"] = sorted(n for n in names if fg.tier_b_open(n) and n in touched)
    out["author"] = rv.authors(commits)[0]
    for line in "\n".join(f.get("patch") or "" for f in files if f.get("filename") == "CHANGELOG.md").split("\n"):
        if line.startswith("+- "):
            out["summary"] = plain(line[3:], 240)
            break
    if ai:
        try:
            out["reviews"] = rv.result_in(api("repos/%s/issues/%d/comments?per_page=100" % (repo, number)), sha)
        except (RuntimeError, ValueError):
            out["reviews"] = None
        try:
            led = _tool("maintenance-ledger")
            runs = {"tests.yml": led.run_info(repo, "tests.yml", led.gh_api, sha=sha)}
            out["no_regression"] = am.no_regression({"runs": runs})[0]
        except Exception:
            out["no_regression"] = None
    return out


def gather(repo, api=gh_api):
    """{"last": the last published tag, "changes": [change], "pending": [text], "unread": [what]}."""
    tools = (_tool("fix-guard"), _tool("ai-review"), _tool("automerge"))
    drill = _tool("automat-drill")
    info = {"last": "", "changes": [], "pending": [], "unread": [], "quota": None}
    try:
        info["last"] = (api("repos/%s/releases/latest" % repo) or {}).get("tag_name", "")
        commits = api("repos/%s/compare/%s...main" % (repo, info["last"])).get("commits", []) if info["last"] else []
    except (RuntimeError, ValueError, AttributeError):
        commits = []
        info["unread"].append("le modifiche dall'ultima versione pubblicata")
    for c in commits:
        first = ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0]
        m = MERGE.match(first)
        if not m or len(c.get("parents") or []) < 2:
            continue
        change = change_of(repo, int(m.group(1)), api, tools)
        if change.get("drill") or drill.is_drill_title(first.split(":", 1)[-1]):
            continue                         # an AUTOMAT drill is never part of a version (it never merges)
        change["self"] = SELF in first
        change["title"] = change["title"] or plain(first.split(":", 1)[-1])
        info["changes"].append(change)
    try:
        led = _tool("maintenance-ledger")
        _number, ledger = led.read_ledger(repo, led.gh_api)
        for e in sorted(((ledger or {}).get("entries") or {}).values(), key=lambda e: e.get("key", "")):
            if drill.is_drill_branch(e.get("via")) or str(e.get("component", "")).startswith("drill-") or \
                    e.get("drill"):
                continue                     # nor is it an update still being retried
            if e.get("state") in ("retrying", "blocked"):
                info["pending"].append("%s%s: %s" % (
                    "**BLOCCATO** " if e["state"] == "blocked" else "", plain(e.get("name"), 80),
                    plain(e.get("reason"), 220)))
    except Exception:
        info["unread"].append("il registro della manutenzione")
    try:
        # the use of the free quotas, from the data branch (tools/ai-quota.py); the limits from this checkout
        import base64
        quota = _tool("ai-quota")
        data = api("repos/%s/contents/%s?ref=%s" % (repo, quota.FILE, quota.BRANCH))
        state = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("days"), dict):
            raise ValueError("not the quota's record")
        info["quota"] = quota.summary(quota.load_limits(), state)
    except Exception:
        info["unread"].append("l'uso della quota gratuita degli assistenti AI")
    return info


def _verdicts(change):
    reviews = change.get("reviews")
    if not isinstance(reviews, dict):
        return "revisione delle due AI: **non letta**"
    said = ", ".join("%s %s" % (plain(r.get("provider"), 20), "approva" if r.get("verdict") == "approve"
                                else "respinge") for r in reviews.get("reviews") or []) or "nessuna risposta"
    how_many = "tre" if len(reviews.get("reviews") or []) >= 3 else "due"
    return "revisione di %s AI indipendenti (scritta da %s): %s" % (how_many, plain(change.get("author") or "?", 20),
                                                                   said)


def quota_lines(rows):
    """The free quota of each provider, one line each."""
    def of(used, limit):
        return "%s su %s" % (used, limit) if limit is not None else "%s (nessun limite al giorno noto)" % used
    out = []
    for r in rows or []:
        left = []
        if r.get("requests_left") is not None:
            left.append("%d richieste" % r["requests_left"])
        if r.get("tokens_left") is not None:
            left.append("%d token" % r["tokens_left"])
        note = "" if r.get("verified") else (" Limite **non verificato** (stima prudente%s)." % (
            ", corretta oggi dalle risposte del fornitore" if r.get("live") else ""))
        spent = " **Finita per oggi** (%s)." % plain(r.get("spent"), 80) if r.get("spent") else ""
        # real updates first (2026-11-24): real updates may use all of it; what they leave goes to the background
        keep = (" Oggi a sicurezza e aggiornamenti veri %d richieste, al lavoro di fondo (quello che avanzava) %d." % (
            r.get("real_requests") or 0, r.get("background_requests") or 0)) \
            if isinstance(r.get("real_requests"), int) else ""
        if r.get("account") == "not-free":
            # what GET /api/v1/key said of OpenRouter's account (tools/ai-quota.py account_tier)
            keep += (" **OpenRouter account is not free tier**: l'account non risulta nel livello gratuito; AUTOMAT "
                     "resta al limite documentato delle richieste gratuite e il controllo settimanale lo segnala.")
        out.append("- **%s**: oggi %s richieste, %s token; restano %s. Ultimi giorni: %d richieste, %d token.%s%s%s" % (
            plain(r.get("provider"), 20), of(r.get("requests", 0), r.get("requests_limit")),
            of(r.get("tokens", 0), r.get("tokens_limit")), " e ".join(left) or "non noto",
            r.get("week_requests", 0), r.get("week_tokens", 0), keep, spent, note))
    return out


def _regression(change):
    return {"passed": "superato", "failed": "**fallito**", "not verified": "**non verificato**"}.get(
        change.get("no_regression"), "**non letto**")


def body(version, repo, owner, info):
    """The notice's text."""
    link = "https://github.com/%s/pull/%%d/files" % repo
    out = ["**%s: I.K.E. %s**" % (READY, version), "",
           "```bash", COMMAND, "```", "",
           "@%s: **I.K.E. %s** è in `main`, con tutti i test verdi, e non è ancora pubblicata. Per firmarla e "
           "pubblicarla, apri un terminale sul tuo PC e incolla il comando qui sopra (una riga sola; va bene anche in "
           "fish)." % (owner, version), "",
           "La tua firma è l'unico passo fatto da una persona: tutto il resto lo fa AUTOMAT, la manutenzione "
           "automatica. Qui sotto c'è tutto quello che la firma copre, cioè ogni "
           "modifica entrata in `main` dall'ultima versione pubblicata%s." % (
               " (%s)" % info["last"] if info.get("last") else ""), ""]
    changes = info.get("changes") or []
    by_ai = [c for c in changes if c.get("self") and c.get("tier_b_ai")]
    reserved = [c for c in changes if c.get("self") and c.get("tier_b") and c not in by_ai]
    protected = [c for c in changes if c.get("self") and c.get("tier_a") and c not in by_ai]
    rest = [c for c in changes if c not in reserved and c not in protected and c not in by_ai]
    if by_ai:
        out += ["### ⚠⚠ Modifiche scritte da un'AI a file riservati: guardale per prime", "",
                "Sono possibili solo perché hai acceso tu l'interruttore `AUTOMAT_TIER_B`, e solo nella forma più "
                "stretta: in un workflow può cambiare soltanto una versione fissata; in `ike/app.py`, `ike/updater.py` "
                "e `ike_boot.py` solo righe aggiunte, mai nelle funzioni che decidono firma, aggiornamenti e sandbox. "
                "Ognuna è passata da tre AI revisori indipendenti invece di due.", ""]
        for c in by_ai[:MAX_LISTED]:
            out.append("- **#%d** %s" % (c["n"], c.get("summary") or c["title"]))
            out.append("  - File riservati: %s" % ", ".join("`%s`" % x for x in c["tier_b_ai"][:8]))
            out.append("  - %s" % _verdicts(c))
            out.append("  - \"Niente peggiora\" (no-regression): %s. [Vedi le differenze](%s)" % (
                _regression(c), link % c["n"]))
        out.append("")
    if reserved:
        out += ["### ⚠ Modifiche a file riservati (workflow, strumenti, sandbox, firma e aggiornamenti)", "",
                "Guardale per prime. Nessuna AI può cambiare questi file: qui arrivano solo dagli strumenti "
                "automatici senza AI (i pin dei workflow) o dal riancoraggio controllato di un costruttore.", ""]
        for c in reserved[:MAX_LISTED]:
            out.append("- **#%d** %s. File riservati: %s. [Vedi le differenze](%s)" % (
                c["n"], c["title"], ", ".join("`%s`" % f for f in c["tier_b"][:8]), link % c["n"]))
        out.append("")
    if protected:
        out += ["### Correzioni scritte da un'AI su codice protetto", "",
                "Blocco pubblicità, privacy, impronta digitale e script delle pagine. Ognuna è passata da: tutti i "
                "test, il controllo automatico delle regole (solo aggiunte, niente tolto), due AI revisori "
                "indipendenti e il confronto \"niente peggiora\" con la versione di prima.", ""]
        for c in protected[:MAX_LISTED]:
            out.append("- **#%d** %s" % (c["n"], c.get("summary") or c["title"]))
            out.append("  - File: %s" % ", ".join("`%s`" % f for f in c["tier_a"][:8]))
            out.append("  - %s" % _verdicts(c))
            out.append("  - \"Niente peggiora\" (no-regression): %s. [Vedi le differenze](%s)" % (
                _regression(c), link % c["n"]))
        out.append("")
    if rest:
        out += ["### Le altre modifiche", ""]
        for c in rest[:MAX_LISTED]:
            how = "entrata da sola, verificata in tutto" if c.get("self") else "unita su tuo ordine"
            ai = "; correzione di un'AI su codice normale, %s" % _verdicts(c) if c.get("ai") and c.get("self") else ""
            out.append("- **#%d** %s (%s%s)" % (c["n"], c.get("summary") or c["title"], how, ai))
        if len(rest) > MAX_LISTED:
            out.append("- ... e altre %d" % (len(rest) - MAX_LISTED))
        out.append("")
    if not changes:
        out += ["Nessuna modifica entrata con una pull request dall'ultima versione pubblicata (o non è stato "
                "possibile leggerle).", ""]
    pending = info.get("pending") or []
    out += ["### Aggiornamenti ancora in corso", ""]
    if pending:
        out.append("Non sono in questa versione. Non devi fare niente: AUTOMAT (la manutenzione automatica) li riprova ogni "
                   "giorno "
                   "(quelli **bloccati** sono avvisi di sicurezza senza una correzione sicura).")
        out.append("")
        out += ["- %s" % p for p in pending[:MAX_LISTED]]
        if len(pending) > MAX_LISTED:
            out.append("- ... e altri %d (nel registro della manutenzione)" % (len(pending) - MAX_LISTED))
    else:
        out.append("Nessuno: tutto quello che è stato trovato è in questa versione.")
    out.append("")
    if info.get("quota"):
        out += ["### Quota gratuita degli assistenti AI", "",
                "Solo fornitori gratuiti. Quanto è stato usato e quanto resta oggi (AUTOMAT tiene sempre da parte la "
                "quota per far rivedere ogni correzione da altre AI):", ""]
        out += quota_lines(info["quota"])
        out.append("")
    if info.get("unread"):
        out += ["**Non letto** (GitHub non ha risposto): %s." % ", ".join(info["unread"]), ""]
    out += ["Ti chiederà la password della tua chiave di firma. Se si ferma, dice perché e non cambia niente su "
            "GitHub.",
            "Per una prova a vuoto (tutto tranne la pubblicazione), cambia la fine in `python3 tools/publish.py "
            "--dry-run'` (con l'apice finale).", "",
            "Le novità: [CHANGELOG.md](https://github.com/%s/blob/main/CHANGELOG.md). Quando è pubblicata, questo "
            "avviso si chiude da solo." % repo, "", "<!-- release-ready: %s -->" % version]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\d+\.\d+\.\d+", a.version):
        print("::error::not a version")
        return 1
    text = body(a.version, a.repo, a.owner, gather(a.repo))
    if len(text) > 60000:                      # GitHub's limit is 65536
        text = text[:58000] + "\n\n(... il resto è nel registro della manutenzione)\n\n<!-- release-ready: %s -->\n" \
            % a.version
    Path(a.out).write_text(text, "utf-8")
    print("the signing notice: %d characters" % len(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
