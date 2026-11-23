#!/usr/bin/env python3
"""Run the Antigravity agent for one automatic fix, model after model (no AI here).

Called by the "fix" job of .github/workflows/autofix.yml, read from main. The
agent itself runs as the user "agent" (see the workflow): no terminal and no
web by its own permission rules, outbound network only to the Gemini API by
the firewall, and only GEMINI_API_KEY, HOME and PATH in its environment.

For each model in turn (AUTOFIX_MODEL, then the free Flash models):

    quota of the day used up (429 per day)   -> the next model goes on with the
                                                same working tree
    rate limit per minute (429 per minute)   -> wait (at most WAIT_MAX seconds)
                                                and try the same model once more
    Google temporarily unavailable (5xx)     -> wait 30 s, same model once more,
                                                then the next model
    invalid key or no permission (401/403)   -> stop: the key must be fixed
    unknown model or bad request (400/404)   -> stop: the configuration must be fixed
    time limit reached                       -> stop (what was done is kept)
    anything else                            -> stop

The failure description (.autofix/failure.md) goes inside the instructions
themselves, and so does, before a model takes over, what the previous one
already changed: the agent has no terminal, and its file tools may skip
.autofix/, which git ignores (the first real trial: "logs not available").
One request less, too. The outcome goes to
--status (JSON: result, model, message in Italian, detail with the key hidden).

    autofix-agent.py --workdir DIR --prompt FILE --out DIR --status FILE
                     [--agent-cmd "sudo -u agent ..."]
"""

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path


def _registry():
    """tools/ai-providers.py next to this script (both come from main in the
    workflow): the one place for the providers' order, models and limits."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ike_ai_providers", Path(__file__).resolve().parent / "ai-providers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REGISTRY = _registry()
FREE_MODELS = tuple(REGISTRY.GEMINI_MODELS)
MODEL_TIMEOUT = REGISTRY.MODEL_TIMEOUT          # seconds for one model (wall clock)
TOTAL_TIMEOUT = REGISTRY.TOTAL_TIMEOUT          # seconds for all models together
WAIT_MAX = 90                   # longest wait for a per-minute limit
WAIT_TEMPORARY = 30

MESSAGES = {
    "ok": "L'agente ha finito.",
    "quota": "Quota gratuita di oggi esaurita su tutti i modelli: riprova domani.",
    "auth": "Chiave GEMINI_API_KEY non valida o senza permessi: va controllata.",
    "config": "Modello o configurazione non validi (AUTOFIX_MODEL): va corretta.",
    "temporary": "Google non risponde in questo momento: riprova più tardi.",
    "timeout": "Tempo massimo raggiunto: l'agente è stato fermato.",
    "error": "L'agente si è fermato per un errore imprevisto.",
    "unavailable": "Gemini non è gratuito per questa chiave o questo modello (fatturazione), oppure il "
                   "controllo settimanale l'ha segnato non disponibile: Antigravity non è partito.",
    "rotated": "Questo tentativo comincia da un altro fornitore gratuito (un tentativo precedente non è "
               "bastato): Antigravity non è partito, provano le riserve.",
    # part 2 of AUTOMAT: the budget of the free quotas (tools/ai-quota.py)
    "budget": "La quota gratuita di Gemini di oggi non basta (finita, già usata da questo candidato, oppure "
              "non resterebbe quota per far rivedere la correzione da altre AI): Antigravity non è partito.",
}
# a billing error: the model or the project is not on the free tier (WP9; the
# same words as tools/autofix-reserve.py, never a quota's advice)
BILLING = re.compile(r"payment[ _]required|insufficient[ _](?:balance|credits?|funds)|BILLING_DISABLED"
                     r"|billing (?:is )?(?:not )?(?:enabled|required)|requires? billing"
                     r"|(?:paid|billing) (?:plan|tier|account) (?:is )?required|only available (?:on|for|to) (?:the )?paid",
                     re.I)


def models(wanted):
    """AUTOFIX_MODEL (one name or several, separated by commas), then the free
    Flash models; no duplicates, no empty names."""
    out = []
    for m in [x.strip() for x in (wanted or "").split(",")] + list(FREE_MODELS):
        if m and m not in out:
            out.append(m)
    return out


def classify(status, err):
    """What a failed run means: (kind, seconds to wait).

    kind is "day" (daily quota: next model), "minute" (rate limit: wait and
    retry), "temporary", "auth", "config", "timeout" or "error"."""
    if status == 124:
        return "timeout", 0
    text = err[-20000:]
    # Google busy, even when the CLI's own retries then ran into its time limit
    # (final review of 1.1.18, run 44715968623: "Error 503 ... high demand" after
    # 326 s, finished_reason print_timeout): the next model, as for any 5xx
    if re.search(r"\bError 503\b|Status: UNAVAILABLE|experiencing high demand", text):
        return "temporary", 0
    # the CLI's own time limit ("print timeout ... turn still in progress"): the
    # agent was still working, not Google failing. Another try would end the
    # same way (the first real trial spent 25 minutes on four of them).
    if "print_timeout" in text or "print timeout" in text.lower():
        return "timeout", 0
    info = {}
    for line in text.splitlines():
        if line.startswith("AGY_ERROR:"):
            try:
                info = json.loads(line.split(":", 1)[1])
            except ValueError:
                info = {}
    if BILLING.search(text):
        return "unavailable", 0
    code = info.get("error_code")
    status_name = str(info.get("status") or "")
    if code is None:
        m = re.search(r"\bError (\d{3})\b", text)
        code = int(m.group(1)) if m else None
    lower = text.lower()
    if code == 429 or "RESOURCE_EXHAUSTED" in status_name or "RESOURCE_EXHAUSTED" in text:
        wait = 0
        m = re.search(r"retryDelay:?\s*\"?(\d+)s", text) or re.search(r"retry in (\d+(?:\.\d+)?)s", text)
        if m:
            wait = int(float(m.group(1)))
        if "perday" in lower.replace(" ", "") or "per day" in lower:
            return "day", wait
        if "perminute" in lower.replace(" ", "") or "per minute" in lower:
            return "minute", wait
        return ("minute", wait) if 0 < wait <= WAIT_MAX else ("day", wait)
    if code in (401, 403) or status_name in ("UNAUTHENTICATED", "PERMISSION_DENIED") \
            or "api_key_invalid" in lower or "api key not valid" in lower:
        return "auth", 0
    if code in (400, 404) or status_name in ("INVALID_ARGUMENT", "NOT_FOUND") \
            or "unknown model" in lower or "model not found" in lower or "available models" in lower:
        return "config", 0
    if (code and 500 <= code < 600) or status_name in ("UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED") \
            or "overloaded" in lower:
        return "temporary", 0
    return "error", 0


PROMPT_MAX = 110_000          # one argument of a command: at most 128 KiB on Linux


def with_failure(rules, failure, done="", context=""):
    """The instructions, then the failure, the code it points at (prepared by
    tools/autofix-context.py, 1.1.15) and the work a previous model did, within
    the size one command argument may have."""
    text = rules.rstrip() + "\n\n# The failure (also in .autofix/failure.md)\n\n"
    extra = ""
    if context:
        extra += "\n\n" + context[:40000].rstrip() + "\n"
    if done:
        extra += ("\n\n# Work already done by a previous model\n\nIt is already in the files: "
                 "go on from here, do not redo it.\n\n```diff\n%s\n```\n" % done[:20000])
    room = PROMPT_MAX - len(text.encode()) - len(extra.encode())
    body = failure.encode()
    if len(body) > room:
        body = b"(beginning cut)\n" + body[-max(0, room - 20):]
    return text + body.decode("utf-8", "ignore") + extra


LISTS_NOTE = """

## This run: the filter lists (an analysis of I.K.E.'s adapter)

This run is not a failed test: the failure description names real rules of
today's filter lists that I.K.E. does not read. Change only I.K.E.'s adapter
(`ike/scriptlets.py`, `ike/blocker.py`, `ike-adblock/src/`) so that it reads
them with the meaning uBlock Origin gives them. Never the filter lists,
`ike/config.py`, the bundled uBlock Origin resources, the tests or their data,
YouTube's ad blocking (`videoads.js`, `videorelay.js`, `mediahook.js`,
`Scriptlets.host_scripts`) or `Cargo.toml`/`Cargo.lock`; never drop an option
or a rule to make it parse, never remove a protection. If only the engine
itself (the adblock-rust crate) could do it, change nothing and say so.
"""


def auto_note(auto):
    """The static guard's rules (tools/fix-guard.py), for a fix that may reach main by itself."""
    if not auto:
        return ""
    return ("\n\n## This fix may reach main by itself: a program checks it\n\nNever change a test, a tool, a "
            "workflow, `ike/app.py`, `ike_boot.py`, `ike/updater.py`, `ike/__init__.py` or `ike/extensions.py`: "
            "fix I.K.E.'s code instead, or change nothing and say why. In the ad-blocking adapter, the modules "
            "that decide the user's safety and I.K.E.'s page scripts only ADD statements: every existing "
            "statement, condition, return and raise stays exactly as it is; no new return or raise before "
            "existing code unless under a new condition; no new import, address, file write or process. If "
            "`tests/test_inventory_guard.py` fails, add the missing entry to `components.json` exactly as its "
            "message says (a plain download, never a build command).\n")


def tier_b_note(on):
    """The narrow form of tier B the owner opened with AUTOMAT_TIER_B (tools/tier-b.py)."""
    if not on:
        return ""
    return ("\n\n## The owner opened a few reserved files, in their narrowest form\n\nA program checks it "
            "(tools/tier-b.py). In a workflow under `.github/` ONLY a pinned version may change (an action's full "
            "commit with its version comment, cargo-deny's version, the Python, Node.js or Rust version): never a "
            "command, a permission, a secret, a trigger, `runs-on` or a step, never an older version. In "
            "`ike/app.py`, `ike/updater.py` and `ike_boot.py` only ADD statements, never inside a function that "
            "decides the signature, the update, the sandbox or the update check (they are frozen), and never name "
            "UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, LNA_FEATURES or ENGINE_SAFETY. Everything else that the "
            "section above forbids stays forbidden.\n")


def _quota():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_ai_quota", Path(__file__).resolve().parent / "ai-quota.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine_note(allow_adblock, lists=False):
    """Whether this run may touch the ad blocker's wrapper: the same answer the
    reserves get and the checker enforces (--allow-adblock; --lists: the filter
    lists' analysis, the adapter only, WP8)."""
    if lists:
        return LISTS_NOTE
    if allow_adblock:
        return ("\n\n## This run\n\nThis run updates the ad blocker's engine: I.K.E.'s own wrapper "
                "(`ike-adblock/src/`, `vendor/adblock/__init__.py`, `ike/blocker.py`, "
                "`ike/scriptlets.py`) may change if the failure is there. Still never "
                "`ike-adblock/Cargo.toml`, `Cargo.lock` or the engine itself.\n")
    return ("\n\n## This run\n\nThis run does not update the ad blocker's engine: do not change "
            "`ike-adblock/`, `vendor/`, `ike/blocker.py` or `ike/scriptlets.py`. If the failure is "
            "there, change nothing and say so in the summary.\n")


SECURITY_RULES = (
    "\n\n## A security finding\n\nThis run fixes a security finding on an isolated branch "
    "(automation/update/security-*). Never change the engine's sandbox and isolation switches "
    "(UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, NOTICE_SWITCHES, LNA_FEATURES in `ike/app.py`), "
    "`ENGINE_SAFETY` or the functions that decide them, the security tests (the files `security.yml` "
    "runs), `ike-adblock/deny.toml`, or anything that names a RustSec advisory. The checker refuses such a "
    "fix (--security) and no other assistant is asked. If the only way out is weakening a protection, "
    "change nothing and say so in the summary.\n")


BUILDERS = {"darkreader": "tools/build-darkreader.py", "ubo-scriptlets": "tools/build-ubo-scriptlets.mjs"}


def builder_note(builder):
    """WP11: the builders' re-anchoring, the same rule the reserves get and the checker enforces
    (--builder, tools/builder-anchor.py)."""
    if builder not in BUILDERS:
        return ""
    return ("\n\n## This run: re-anchor I.K.E.'s builder\n\nA new upstream version moved the text one of "
            "I.K.E.'s patches is anchored to; the failure description shows the new upstream lines around it. "
            "Change ONLY `%s`, and in it only the anchor texts of the existing patches (Dark Reader: the second "
            "text of each `PATCHES` entry; uBlock Origin: only the path of the library it imports). Never a "
            "replacement text, never a new or removed patch, never other code, never upstream code or the "
            "generated files in `ike/resources/`. If that is not enough, change nothing and say so.\n"
            % BUILDERS[builder])


def security_note(security):
    """The rules of a fix of a security finding: the same the reserves get and the checker
    enforces (--security, WP6)."""
    return SECURITY_RULES if security else ""


def key_variants(key):
    key = key.encode()
    out = {key, key[::-1]}
    for i in range(3):
        for enc in (base64.b64encode, base64.urlsafe_b64encode):
            out.add(enc(b"\0" * i + key)[4 if i else 0:-4])
    return {v for v in out if v}


def redact(data, key):
    if key:
        for v in key_variants(key):
            data = data.replace(v, b"***")
    return data


def _checker():
    """tools/check-autofix-patch.py next to this script (both come from main in
    the workflow): its SAFE_GIT, so the two run git the same way."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ike_autofix_checker", Path(__file__).resolve().parent / "check-autofix-patch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def changes(workdir):
    """What the agent changed so far, new files included (not .autofix/).

    git runs here on a tree the agent writes (1.1.18): without system or global
    configuration, hooks, fsmonitor, attributes file or submodules, and without
    external diff or text conversion; .git itself is out of the agent's reach
    (the workflow)."""
    checker = _checker()
    git = checker.SAFE_GIT + ["-C", str(workdir)]
    env = checker.safe_git_env()
    # no pathspec: with .autofix/ in .gitignore, naming it makes "add" end with an
    # error (the diff below leaves .autofix/ out)
    subprocess.run(git + ["add", "-A", "-N"],
                   capture_output=True, check=False, env=env)
    out = subprocess.run(git + ["diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", ".", ":(exclude).autofix"],
                         capture_output=True, text=True, check=False, env=env)
    return out.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--agent-cmd", default="agy", help="how to start the agent (as the agent user)")
    ap.add_argument("--model-timeout", type=int, default=MODEL_TIMEOUT)
    ap.add_argument("--total-timeout", type=int, default=TOTAL_TIMEOUT)
    ap.add_argument("--allow-adblock", action="store_true",
                    help="this run updates the ad blocker's engine (tools/autofix-plan.py)")
    ap.add_argument("--security", action="store_true",
                    help="this run fixes a security finding (tools/autofix-plan.py): the stricter rules")
    ap.add_argument("--lists", action="store_true", help="the filter lists' analysis (tools/filter-lists.py)")
    ap.add_argument("--builder", default="", choices=["", *sorted(BUILDERS)],
                    help="the builders' re-anchoring (WP11): that builder's existing patches only")
    ap.add_argument("--first", default="", help="the provider this attempt starts with (tools/ai-providers.py)")
    ap.add_argument("--auto", action="store_true", help="a fix that may reach main by itself: the static guard")
    # part 2 of AUTOMAT
    ap.add_argument("--tier-b", action="store_true", help="the owner turned AUTOMAT_TIER_B on (tools/tier-b.py)")
    ap.add_argument("--quota-limits", help="tools/ai-quota.json (the free quotas, as data)")
    ap.add_argument("--quota-state", help="quota.json of the data branch (today's use)")
    ap.add_argument("--quota-usage", help="where this run's use is written (numbers only)")
    ap.add_argument("--candidate", default="", help="the branch being fixed (its share of the quota)")
    a = ap.parse_args(argv)
    key = os.environ.get("GEMINI_API_KEY", "")
    workdir, out = Path(a.workdir), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tier_b = bool(a.tier_b and a.auto and not getattr(a, "builder", ""))
    rules = (Path(a.prompt).read_text("utf-8") + engine_note(a.allow_adblock, a.lists) + security_note(a.security)
             + builder_note(getattr(a, "builder", "")) + auto_note(a.auto and not getattr(a, "builder", ""))
             + tier_b_note(tier_b))
    try:
        failure = (workdir / ".autofix" / "failure.md").read_text("utf-8", "replace")
    except OSError:
        failure = "(no failure description was found)\n"
    try:
        context = (workdir / ".autofix" / "context.md").read_text("utf-8", "replace")
    except OSError:
        context = ""
    result, used, detail = "error", "", ""
    deadline = time.monotonic() + a.total_timeout
    off = {n.strip() for n in (os.environ.get("AUTOFIX_UNAVAILABLE") or "").split(",") if n.strip()}
    first = a.first or os.environ.get("AUTOFIX_FIRST", "")
    if first and first not in ("Antigravity", "Gemini"):
        # a later attempt starts with another free provider (tools/ai-providers.py FIX_ATTEMPTS): a
        # fresh context, another model family; the reserves begin with that one
        Path(a.status).write_text(json.dumps({"result": "rotated", "model": "", "message": MESSAGES["rotated"],
                                              "detail": first}, ensure_ascii=False), "utf-8")
        print("Outcome: rotated (this attempt starts with %s)" % first.replace("::", ": ")[:40], flush=True)
        return 0
    if off & {"Antigravity", "Gemini"}:
        # the weekly check found Gemini not free (tools/provider-check.py): not started
        Path(a.status).write_text(json.dumps({"result": "unavailable", "model": "", "message":
                                              MESSAGES["unavailable"], "detail": ""}, ensure_ascii=False), "utf-8")
        print("Outcome: unavailable (marked by the weekly check)", flush=True)
        return 0
    # part 2 of AUTOMAT: the budget of Gemini's free quota. One session of the agent is counted as
    # session_requests requests (it reads and edits files in several requests)
    spend, session = None, 0
    if a.quota_limits or a.quota_state or a.quota_usage:
        quota = _quota()
        limits = quota.load_limits(a.quota_limits)
        named = [n.strip() for n in (os.environ.get("AUTOFIX_REVIEWERS") or "").split(",") if n.strip() in quota.NAMES]
        spend = quota.Budget(limits, quota.load_state(a.quota_state) if a.quota_state else None, a.candidate,
                             tier_b=tier_b, available=[n for n in (named or quota.NAMES) if n not in off])
        session = int(limits["providers"]["Antigravity"].get("session_requests") or 10)
        allowed, why = spend.allows("Antigravity", 0, "fix", requests=session)
        if not allowed:
            spend.skipped["Antigravity"] = why
            Path(a.status).write_text(json.dumps({"result": "budget", "model": "", "message": MESSAGES["budget"],
                                                  "detail": why}, ensure_ascii=False), "utf-8")
            if a.quota_usage:
                Path(a.quota_usage).write_text(json.dumps(spend.delta()) + "\n", "utf-8")
            print("Outcome: budget (%s)" % why.replace("::", ": ")[:200], flush=True)
            return 0
    for model in models(os.environ.get("AUTOFIX_MODEL")):
        tries = 0
        while True:
            tries += 1
            prompt = with_failure(rules, failure, changes(workdir), context)
            limit = int(min(a.model_timeout, deadline - time.monotonic()))
            if limit < 60:
                result = "timeout"
                break
            print("Agent with model: %s (at most %d s)" % (model, limit), flush=True)
            cmd = shlex.split(a.agent_cmd) + ["-p", prompt, "--model", model,
                                               "--dangerously-skip-permissions", "--output-format", "json",
                                               "--print-timeout", "%ds" % max(30, limit - 30)]
            started = time.monotonic()
            try:
                run = subprocess.run(["timeout", "-k", "10", str(limit)] + cmd, cwd=workdir,
                                     stdin=subprocess.DEVNULL, capture_output=True, timeout=limit + 60)
                status, err = run.returncode, run.stderr
            except subprocess.TimeoutExpired:
                run, status, err = None, 124, b""
            # the agent's own output is never printed: the logs of a public repository are public
            err = redact(err, key)
            said = redact(getattr(run, "stdout", b"") or b"", key) if status != 124 else b""
            (out / ("agent-%s.err" % re.sub(r"\W+", "_", model))).write_bytes(err)
            used, detail = model, "\n".join(err.decode("utf-8", "replace").splitlines()[-30:])
            if status and said.strip():
                # what the agent had produced when it stopped (its own words, no key): for the diagnosis
                detail += "\n--- the agent's last output ---\n" + said.decode("utf-8", "replace")[-1500:]
            if spend is not None:
                spend.note("Antigravity", 0, "fix", requests=session)
            if status == 0:
                result = "ok"
                break
            # the CLI writes its last error in its JSON answer on standard output
            # too (final review of 1.1.18): both are read
            kind, wait = classify(status, err.decode("utf-8", "replace") + "\n" + said.decode("utf-8", "replace"))
            print("Agent stopped (%s): %s" % (status, kind), flush=True)
            if kind == "minute" and tries == 1 and wait <= WAIT_MAX and time.monotonic() + wait < deadline:
                time.sleep(max(wait, 5))
                continue
            # Google busy: once more only after a quick failure. A slow one means
            # the CLI already retried by itself for minutes (2026-11-19: 503 after
            # 5 minutes, then 5 more): the next model, or the reserves, instead.
            if kind == "temporary" and tries == 1 and time.monotonic() - started < 60:
                time.sleep(WAIT_TEMPORARY)
                continue
            result = {"day": "quota", "minute": "quota", "temporary": "temporary"}.get(kind, kind)
            if spend is not None and kind == "day":
                spend.mark_spent("Antigravity", "429: the quota of the day")
            if spend is not None and kind == "unavailable":
                spend.mark_spent("Antigravity", "not free (billing)")
            break
        if result == "ok":
            break
        if result in ("quota", "temporary"):
            print("This model is not available now: the next model goes on", flush=True)
            continue
        break                    # auth, config, timeout, error, unavailable: switching model would not help
    Path(a.status).write_text(json.dumps({"result": result, "model": used, "message": MESSAGES[result],
                                          "detail": detail}, ensure_ascii=False), "utf-8")
    if spend is not None and a.quota_usage:
        spend.result = "answered" if result in ("ok", "timeout", "error") else ""
        Path(a.quota_usage).write_text(json.dumps(spend.delta()) + "\n", "utf-8")
    print("Outcome: %s (%s)" % (result, used), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
