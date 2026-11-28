#!/usr/bin/env python3
"""The reserve assistants of the automatic fix (no AI here: this calls them).

When the Antigravity agent could not fix a failure (quota used up, Google not
answering, an error of the agent, or simply no fix), .github/workflows/autofix.yml
asks the reserves, one after the other, never together:

    1. Groq        (GROQ_API_KEY,       models in AUTOFIX_GROQ_MODELS)
    2. Z.AI        (ZAI_API_KEY,        models in AUTOFIX_ZAI_MODELS; its free GLM
                    Flash models, another family than the others: 1.1.19)
    3. OpenRouter  (OPENROUTER_API_KEY, models in AUTOFIX_OPENROUTER_MODELS)

A provider without its key is skipped. Groq's free plan takes about 8,000
tokens a minute, so it gets a short message (the failure and the code around
it); OpenRouter's free models also get the whole files involved. Unlike Antigravity they cannot open
files: they get the failure, the code it points at (.autofix/context.md, from
tools/autofix-context.py) and the full text of the files involved, and answer
with a JSON object of edits, each one an exact piece of text to replace in one
file. This script applies the edits to the working tree; nothing a model writes
is ever run. Then the usual checks decide (tools/check-autofix-patch.py,
--related included) and GitHub runs all the tests.

For each model in turn:

    quota or rate limit (429)            -> the next model
    key refused (401/403)                -> the next provider (the key must be fixed)
    unknown model, bad request (400/404) -> the next model (the variable must be fixed);
      an OpenRouter model that is gone -> also the free models OpenRouter offers now (1.1.18)
    server error, no answer              -> once more, then the next model
    request too large (413)              -> the next provider
    an answer that cannot be applied     -> once more, told what was wrong, then the next model
    a fix the checks refuse (--checker)  -> undone; the next model is told why
    a fix refused for safety (exit 3)    -> undone; stop: no other model is asked
    "no fix possible in the code"        -> the next model; stop when models of two
                                            providers say so (1.1.19: two of one provider
                                            stopped the chain before the last one)
    any other malformed answer or error  -> undone; the next model

What a model writes reaches the log only through for_log(): one line, and no
"::" that could start a GitHub workflow command.

--refused FILE: why the checks refused Antigravity's fix (the reserves are told,
so they do not repeat it).

Part 2 of AUTOMAT (each only with its option; without them nothing above changes):

--inner            the inner loop (tools/autofix-inner.py): the answer must be exactly the
                   patch format; the cheap checks run at once (Python compiled, never run;
                   node --check; cargo check through --cargo-cmd only; then the checker with
                   the static guard, then ruff) and what they find goes back to the SAME
                   model, at most INNER_TRIES answers per model; a refusal for safety still
                   stops everything.
--quota-limits, --quota-state, --quota-usage, --candidate
                   the budget of the free quotas (tools/ai-quota.py): a provider spent today
                   is never asked, the reviewers' reserve and the candidate's share are kept,
                   a limit per minute is waited out; every call's headers and 429s correct
                   the budget; the run's use is written as numbers to --quota-usage.
                   No deadlock (2026-11-25, PR #111: three days and nobody asked):
                   - a request larger than a provider's limit of tokens per minute is fitted
                     to it (fitted: the rules, the failure with the refusal reasons, the files
                     to change; the code around the failure as far as it fits) and asked;
                     only when even that cannot fit is the provider skipped, with the reason;
                   - a 429 of a minute or of concurrency (tools/ai-quota.py rate_limit_scope)
                     is waited out and asked again (at most MINUTE_RETRIES times), never taken
                     for the day's quota; a 503 is asked again after BACKOFF;
                   - when the reviewers' reserve alone left every provider unasked, a second
                     pass asks the one whose fix leaves the most reviewers (Budget.way_forward):
                     the fix is written now and its two reviews come on a later day; it never
                     reaches main without them (status "reviews_deferred");
                   - the watchdog: a branch that asked nobody for UNASKED_DAYS days in a row is
                     said in the message (tools/ai-quota.py stuck_text).
--order A,B,C, --task KIND
                   the order of the providers for this kind of task (tools/automat-route.py),
                   and the cap of the answer; --tried FILE: the fingerprints of the patches
                   that already failed for this error: the same patch twice stops the attempt
                   (result "loop").
--tier-b           the owner turned AUTOMAT_TIER_B on: the narrow form of tools/tier-b.py.

The outcome goes to --status (JSON: result, model, message in Italian) and the
Italian summary to .autofix/summary.md. Keys never reach a file or the log.

    autofix-reserve.py --workdir DIR --prompt FILE --status FILE
                       [--checker FILE [--related FILE] [--allow-adblock]] [--refused FILE]
"""

import argparse
import functools
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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
# name, endpoint, key variable, models variable, default models, characters of
# failure + code sent, tokens of the answer (tools/ai-providers.py, RESERVES)
PROVIDERS = tuple(tuple(p) for p in REGISTRY.RESERVES)
ROOTS = ("ike/", "tests/", "tools/", "docs/")
# I.K.E.'s own wrapper of the ad blocker: only when the workflow says this run
# updates the engine (--allow-adblock, from tools/autofix-plan.py). The checker
# (tools/check-autofix-patch.py) stays the authority either way.
WRAPPER = ("ike-adblock/src/", "vendor/adblock/__init__.py")
SHOWN_ROOTS = ROOTS + WRAPPER          # may be shown, as context, even when not editable


# the filter lists' analysis (--lists, WP8): I.K.E.'s adapter only
LISTS_EDITABLE = ("ike/scriptlets.py", "ike/blocker.py", "ike-adblock/src/")


# --auto (2026-11-22): a fix of the automation, which may reach main by itself. Never the tests or the
# tools; the component manifest may get a missing entry (tools/fix-guard.py)
AUTO = {"on": False}
MANIFEST = "components.json"
AUTO_RULES = (
    "\n\nThis fix may reach main by itself, so a program checks it (tools/fix-guard.py). Never change a test, "
    "a tool, a workflow, ike/app.py, ike_boot.py, ike/updater.py, ike/__init__.py or ike/extensions.py: fix "
    "I.K.E.'s code instead, or answer \"fixable\": false. In the ad-blocking adapter, the modules that decide "
    "the user's safety and I.K.E.'s page scripts only ADD statements: every existing statement, condition, "
    "return and raise stays exactly as it is, no new return or raise before existing code unless under a new "
    "condition, no new import, address, file write or process. If tests/test_inventory_guard.py fails, add "
    "the missing entry to components.json exactly as its message says (a plain download, never a build).\n")


# --tier-b (the owner's switch AUTOMAT_TIER_B): the few tier-B files of tools/tier-b.py
TIER_B = {"on": False}
TIER_B_FILES = ("ike/app.py", "ike/updater.py", "ike_boot.py")
TIER_B_ROOTS = (".github/workflows/", ".github/actions/")
TIER_B_RULES = (
    "\n\nThe owner opened a few reserved files in their narrowest form (a program checks it, tools/tier-b.py): "
    "in a workflow under .github/ ONLY a pinned version may change (an action's full commit with its version "
    "comment, cargo-deny's version, the Python, Node.js or Rust version), never a command, a permission, a "
    "secret, a trigger, runs-on or a step, and never to an older version; in ike/app.py, ike/updater.py and "
    "ike_boot.py only ADD statements, never inside a function that decides the signature, the update, the "
    "sandbox or the update check (they are frozen), never naming UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, "
    "LNA_FEATURES or ENGINE_SAFETY. If the fix needs more than that, answer \"fixable\": false.\n")


def tier_b_path(path):
    return TIER_B["on"] and (path in TIER_B_FILES or path.startswith(TIER_B_ROOTS))


def editable(path, allow_adblock, lists=False):
    if lists:
        return path.startswith(LISTS_EDITABLE)
    if tier_b_path(path):
        return True
    if AUTO["on"]:
        if path == MANIFEST:
            return True
        if path.startswith(("tests/", "tools/")):
            return False
    return path.startswith(ROOTS + WRAPPER if allow_adblock else ROOTS)


@functools.lru_cache(maxsize=1)
def _checker():
    """The checker next to this script (both come from main in the workflow), or
    None."""
    path = Path(__file__).resolve().parent / "check-autofix-patch.py"
    if not path.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_autofix_checker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _checker_rule():
    """allowed_path() of the checker: the reserves never edit what the checker
    would refuse, so the two lists of forbidden files cannot drift apart."""
    mod = _checker()
    return mod.allowed_path if mod else None


@functools.lru_cache(maxsize=None)
def _tool(name):
    """A tool next to this script (all come from main in the workflow)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_" + name.replace("-", "_"),
                                                  Path(__file__).resolve().parent / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(workdir, *args, text=True):
    """git on the work tree, as the checker runs it (SAFE_GIT, 1.1.18): no system
    or global configuration, hooks, fsmonitor, attributes file or submodules."""
    mod = _checker()
    if mod is None:
        raise OSError("tools/check-autofix-patch.py is missing next to this script")
    return subprocess.run([*mod.SAFE_GIT, "-C", str(workdir), *args], capture_output=True, text=text,
                          check=False, env=mod.safe_git_env())
MAX_FILES = 5
TOTAL_TIMEOUT = REGISTRY.RESERVES_TIMEOUT
REQUEST_TIMEOUT = 150
GEMINI_TIMEOUT = 300           # seconds for one request to Gemini (whole large files)
FILES_BUDGET = 400_000         # characters of whole files at most (each provider gets those that fit its own budget)
MAX_TOKENS = 6000
# fitting a request to a provider's limit of tokens per minute (fitted, 2026-11-25)
FIT_SHARE = 0.9                # of the limit a fitted request may take (the estimate is careful already)
MIN_USER = 1500                # characters: the smallest request worth sending (the failure and the files' names)
MIN_ANSWER = 1500              # tokens: the smallest answer a fix fits in
# a busy service (503) is asked again after these seconds; a limit per minute (429) is waited out this many times,
# each wait at most MINUTE_WAIT seconds
BACKOFF = (5, 15, 45)
MINUTE_RETRIES = 2
MINUTE_WAIT = 75

MESSAGES = {
    "ok": "Una riserva (%s) ha preparato una correzione.",
    "none": "La riserva (%s) dice che il problema non si corregge nel codice, e nessun'altra l'ha corretto.",
    "quota": "Le riserve hanno esaurito la quota o non rispondono: riprova più tardi.",
    "nokey": "Nessuna riserva configurata: mancano le chiavi GROQ_API_KEY, ZAI_API_KEY e OPENROUTER_API_KEY.",
    "error": "Le riserve non sono riuscite a preparare una correzione applicabile.",
    "refused": "La correzione della riserva (%s) è stata respinta dai controlli di sicurezza: "
               "nessun'altra riserva è stata interpellata.",
    "unavailable": "Nessuna riserva gratuita disponibile (a pagamento, senza credito o segnata non "
                   "disponibile dal controllo settimanale): il lavoro riprova più tardi.",
    # part 2 of AUTOMAT
    "budget": "La quota gratuita di oggi non basta per scrivere una correzione e farla anche rivedere da "
              "altre AI, oppure è lavoro di fondo che aspetta (prima gli aggiornamenti veri): la correzione "
              "aspetta, nessuna quota è stata sprecata. Riprova da sola.",
    "loop": "La riserva (%s) ha proposto due volte la stessa modifica: il tentativo si ferma qui e viene "
            "registrato, il prossimo parte da un altro assistente.",
}
# the way forward of the reviewers' reserve (2026-11-25): the fix is written now, its reviews come later
DEFERRED = (" Oggi nessun'altra AI aveva quota per rivederla: la correzione è stata scritta lo stesso e aspetta le "
            "revisioni indipendenti nei prossimi giorni; non entra in main senza di esse.")

INSTRUCTIONS = """
# How to answer (reserve assistant)

You cannot open files or run anything. Everything you can see is below: the
failure, the code it points at, and the full text of the files involved.
Answer with ONE JSON object and nothing else:

{"summary": "in Italian, plain and short (at most 10 lines), for an owner who
  is not a programmer: what failed, why, what you changed",
 "fixable": true,
 "edits": [{"file": "ike/example.py",
            "find": "exact text copied from the file (several whole lines, enough to be unique)",
            "replace": "the new text"}]}

- "find" must be copied exactly from the file text (without the line numbers
  shown on the left of the excerpts) and appear exactly once in that file.
- Comments can be wrong (the tests and docs decide); a comment next to your fix
  that says the opposite of it is corrected too.
- At most 5 files, the smallest correct change. Only files that are shown
  below, in full or in an excerpt of the code at the failure (then "find" is
  copied from that excerpt), and only under ike/, tests/, tools/ or docs/
  (%(wrapper)s).
- Never ike-adblock/Cargo.toml or Cargo.lock, the adblock-rust engine itself, Dark
  Reader's files, uBlock Origin's scriptlets, the icon sets, docs/THIRD-PARTY.md
  or any file that comes from others or is generated.
- If the failure cannot be fixed in the code, answer {"summary": "...",
  "fixable": false, "edits": []}.
"""


# WP6: the rules of a fix of a security finding (--security), the same Antigravity gets
# (tools/autofix-agent.py) and the checker enforces
SECURITY_RULES = (
    "\n\nThis run fixes a security finding on an isolated branch (automation/update/security-*). Never "
    "change the engine's sandbox and isolation switches (UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, "
    "NOTICE_SWITCHES, LNA_FEATURES in ike/app.py), ENGINE_SAFETY or the functions that decide them, the "
    "security tests, ike-adblock/deny.toml, or anything that names a RustSec advisory: such a fix is "
    "refused and no other model is asked. If only weakening a protection would make it pass, answer "
    "\"fixable\": false.\n")


# WP11 (--builder ID): only the refused builder's existing patches, re-anchored
BUILDERS = {"ubo-scriptlets": "tools/build-ubo-scriptlets.mjs"}
BUILDER_RULES = (
    "\n\nThis run re-anchors I.K.E.'s builder %(file)s on an isolated branch: a new upstream version moved "
    "the text one of I.K.E.'s patches is anchored to (the failure description shows the new upstream lines "
    "around it). Change ONLY %(file)s, and in it only the path of the library it imports (uBlock "
    "Origin): never a replacement text, never a new or removed patch, never other code, never the "
    "upstream code or the generated files. If the patch cannot be re-anchored that way, answer "
    "\"fixable\": false.\n")


def builder_rules(builder):
    return BUILDER_RULES % {"file": BUILDERS[builder]} if builder in BUILDERS else ""


def instructions(allow_adblock, lists=False, builder=""):
    if builder in BUILDERS:
        return INSTRUCTIONS % {"wrapper": "this run re-anchors ONLY %s (its existing patches' anchors)"
                               % BUILDERS[builder]} + builder_rules(builder)
    if lists:
        return INSTRUCTIONS % {"wrapper": "this run is the filter lists' analysis: ONLY ike/scriptlets.py, "
                               "ike/blocker.py or ike-adblock/src/, never a test"} + _agent_lists_note()
    return INSTRUCTIONS % {"wrapper": (
        "this run updates the ad blocker's engine, so I.K.E.'s own wrapper may change "
        "too: ike-adblock/src/ and vendor/adblock/__init__.py" if allow_adblock else
        "not the ad blocker: ike-adblock/, vendor/, ike/blocker.py and ike/scriptlets.py "
        "may change only when the engine is being updated, and this run does not update it")}


class Stop(Exception):
    pass


def unavailable(env=os.environ):
    """The providers the weekly check marked unavailable (AUTOFIX_UNAVAILABLE,
    names separated by commas: tools/provider-check.py, read by the plan)."""
    return {n.strip() for n in (env.get("AUTOFIX_UNAVAILABLE") or "").split(",") if n.strip()}


def chain(env=os.environ):
    """[(provider, endpoint, key, model, budget, max_tokens)] in order; providers
    without a key, or marked unavailable, left out, and so is a model the
    provider would charge for (OpenRouter: only ":free" models, also from the
    variable; tools/ai-providers.py)."""
    out = []
    off = unavailable(env)
    gemini = env.get(REGISTRY.GEMINI_KEY, "").strip()
    if gemini and not off & {"Antigravity", "Gemini"}:
        # Gemini through its own API, under Antigravity's name and quota (2026-11-28: the CLI never ran)
        named = [m.strip() for m in (env.get(REGISTRY.GEMINI_MODELS_VAR) or "").split(",") if m.strip()]
        ids = []
        for m in named + list(REGISTRY.GEMINI_MODELS):
            mid = REGISTRY.gemini_api_id(m)
            if mid and mid not in ids:
                ids.append(mid)
        ids += [m for m in REGISTRY.discovered(env, "Antigravity") if m not in ids]
        out += [("Antigravity", REGISTRY.GEMINI_OPENAI, gemini, m, REGISTRY.GEMINI_BUDGET, REGISTRY.GEMINI_TOKENS)
                for m in ids]
    for name, url, key_var, models_var, default, budget, tokens in PROVIDERS:
        key = env.get(key_var, "").strip()
        if not key:
            continue
        if name in off:
            print("%s: marked unavailable by the weekly check (not free, or billing): skipped" % name, flush=True)
            continue
        models = [m.strip() for m in (env.get(models_var) or "").split(",") if m.strip()] or list(default)
        # the provider's new free models the weekly check found (AUTOFIX_DISCOVERED), after the configured ones
        models += [m for m in REGISTRY.discovered(env, name) if m not in models]
        for m in models:
            if not REGISTRY.is_free_model(name, m):
                print("%s: %s is not a free model (%s only): refused" % (
                    name, for_log(m), REGISTRY.FREE_SUFFIX.get(name)), flush=True)
                continue
            out.append((name, url, key, m, budget, tokens))
    return out


def rotated(plan, first):
    """The chain starting with the provider `first` (an attempt after a failed fix starts with
    another free provider: tools/ai-providers.py FIX_ATTEMPTS), the others after it in their order;
    the chain as it is when first is not one of its providers."""
    names = [p[0] for p in plan]
    if not first or first not in names:
        return plan
    i = names.index(first)
    return plan[i:] + plan[:i]


def ordered(plan, order):
    """The chain in the order of the providers tools/automat-route.py gives for this kind of task
    (names it does not list keep their place after them); the chain as it is for an empty order."""
    order = [n for n in order if n]
    if not order:
        return plan
    rank = {n: i for i, n in enumerate(order)}
    return sorted(plan, key=lambda p: rank.get(p[0], len(rank)))


OPENROUTER_MODELS = REGISTRY.OPENROUTER_MODELS
DISCOVERED = 2          # free models taken from OpenRouter's list when a listed one is gone
MODEL_ID = re.compile(r"^[A-Za-z0-9._/:-]{3,100}:free$")


def free_catalog(key, opener=urllib.request.urlopen):
    """OpenRouter's free models at this moment, from its own list (GET /api/v1/models): [(id, context)], the
    largest context first, only ids of the usual shape and only at zero price in OpenRouter's own price list (the
    Free Models Router too, FREE_ROUTER); None when the list cannot be read."""
    req = urllib.request.Request(OPENROUTER_MODELS, headers={
        "Authorization": "Bearer " + key, "User-Agent": "IKE-autofix"})
    try:
        with opener(req, timeout=30) as r:
            data = json.loads(r.read(8_000_000).decode("utf-8", "replace"))
        models = data.get("data") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return None
        found = []
        for m in models:
            mid = m.get("id") if isinstance(m, dict) else None
            ctx = m.get("context_length") if isinstance(m, dict) else None
            if isinstance(mid, str) and isinstance(ctx, int) and priced_free(m) and (MODEL_ID.match(mid) or (
                    mid == REGISTRY.FREE_ROUTER and isinstance(m.get("pricing"), dict))):
                found.append((ctx, mid))
        found.sort(key=lambda t: (-t[0], t[1]))
        return [(mid, ctx) for ctx, mid in found]
    except Exception:                       # no list: the chain simply goes on without it
        return None


def free_models(key, opener=urllib.request.urlopen, exclude=(), count=DISCOVERED):
    """OpenRouter's free models at this moment, the largest context first (1.1.18).
    Free models come and go: when one of the list answers 404 (it no longer
    exists), the chain asks OpenRouter which ones there are instead of failing
    until someone edits the list. Only ids of the usual shape are taken."""
    found = free_catalog(key, opener) or []
    return [mid for mid, ctx in found if mid != REGISTRY.FREE_ROUTER and mid not in exclude
            and ctx >= 32_000][:count]


def refreshed(plan, opener=urllib.request.urlopen, listed=None):
    """The chain with OpenRouter's models rebuilt from its own list of this run (2026-11-25: the free models of
    the list were gone, and a paid fallback would cost money): the listed ones that are still free, in their
    order; then the free ones OpenRouter offers now (DISCOVERED, the largest context first); then the Free Models
    Router, the last resort. Nothing changes when the list cannot be read."""
    mine = [p for p in plan if p[0] == "OpenRouter"]
    if not mine:
        return plan
    name, url, key, _model, budget, tokens = mine[0]
    found = free_catalog(key, opener)
    if found is None:
        return plan
    if listed is not None:
        listed["read"] = True               # the list of this moment is in the chain: not asked for again
    free = {mid for mid, _ctx in found}
    keep = [p for p in mine if p[3] in free]
    for p in mine:
        if p[3] not in free:
            print("OpenRouter: %s is not a free model any more (its own list): not asked" % for_log(p[3]), flush=True)
    have = {p[3] for p in keep}
    more = [mid for mid, ctx in found if mid not in have and mid != REGISTRY.FREE_ROUTER and ctx >= 32_000]
    keep += [(name, url, key, mid, budget, tokens) for mid in more[:DISCOVERED]]
    if REGISTRY.FREE_ROUTER in free and REGISTRY.FREE_ROUTER not in have:
        keep.append((name, url, key, REGISTRY.FREE_ROUTER, budget, tokens))
    at = plan.index(mine[0])
    rest = [p for p in plan if p[0] != "OpenRouter"]
    return rest[:at] + keep + rest[at:]


def priced_free(model):
    """True unless OpenRouter's own price list gives the model a price above
    zero (WP9: a ":free" name alone proves nothing). Prices are strings of
    dollars per token; a model without prices is taken as its name says."""
    pricing = model.get("pricing") if isinstance(model, dict) else None
    if not isinstance(pricing, dict):
        return True
    for value in pricing.values():
        try:
            if float(value) > 0:
                return False
        except (TypeError, ValueError):
            continue
    return True


# an answer or an error that says money is asked: payment required, no credit,
# billing not enabled, a model of a paid tier (Z.AI's code 1113: "insufficient
# balance or no resource package"). Only these exact words: a rate limit's
# advice ("upgrade to Dev Tier", "check your plan and billing details") is a
# quota, never this. The provider is not free for this model: it is skipped.
BILLING = re.compile(r"payment[ _]required|insufficient[ _](?:balance|credits?|funds)|余额不足|resource package"
                     r"|\"code\"\s*:\s*\"?1113\b|BILLING_DISABLED|billing (?:is )?(?:not )?(?:enabled|required)"
                     r"|requires? billing|(?:paid|billing) (?:plan|tier|account) (?:is )?required"
                     r"|only available (?:on|for|to) (?:the )?paid", re.I)


# OpenRouter: the privacy settings of the account allow no free endpoint (2026-11-25, openrouter.ai/docs)
DATA_POLICY = re.compile(r"no endpoints found matching your data policy", re.I)
POLICY = (" OpenRouter non può usare i modelli gratuiti: nelle impostazioni di privacy dell'account va permesso "
          "l'uso degli endpoint gratuiti (\"No endpoints found matching your data policy\").")


# the provider's own words of an error, for the log (2026-11-25: "stopped: quota (HTTP 429)" alone did not say
# whether the account, the model's pool upstream or the minute was spent)
def error_words(said):
    """error.message (and OpenRouter's error.metadata.limit_source or raw) of an error body, one short line."""
    try:
        err = (json.loads(said or "{}") or {}).get("error")
    except (ValueError, AttributeError, TypeError):
        err = None
    parts = []
    if isinstance(err, dict):
        meta = err.get("metadata") if isinstance(err.get("metadata"), dict) else {}
        for value in (err.get("message"), meta.get("limit_source"), meta.get("raw")):
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    elif isinstance(err, str):
        parts.append(err)
    text = " / ".join(parts)
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"[^\w .,:;'()/@+=-]+", " ", text).strip()[:160]


def billing_in(text):
    return bool(BILLING.search(text or ""))


def cost_of(data):
    """The cost an answer reports (OpenRouter's usage.cost, or a total_cost),
    or 0."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return 0
    for name in ("cost", "total_cost"):
        try:
            value = float(usage.get(name) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def classify(status):
    if status == 402:
        return "unavailable"          # payment required: no free use of this model
    if status == 413:
        return "toolarge"
    if status == 429:
        return "quota"
    if status in (401, 403):
        return "auth"
    if status in (400, 404, 422):
        return "config"
    return "temporary"


# How much a model reasons before it answers (2026-11-27, run 45983654916: Z.AI, OpenRouter and Groq models alike
# spent the whole answer on their reasoning and gave no text, "cutoff"). "less": the request asks for little
# reasoning; "off": none, the same model asked again after a cutoff. Each provider's own parameter, read on
# 2026-11-27: docs.z.ai/guides/capabilities/thinking-mode ("thinking": {"type": "disabled"}, GLM-4.7 thinks by
# default); console.groq.com/docs/reasoning (reasoning_effort: low|medium|high for gpt-oss, none|default for
# Qwen 3.8 27B); openrouter.ai/docs/use-cases/reasoning-tokens (reasoning.effort minimal ... none; a model whose
# reasoning is mandatory refuses "none": then the next model). An unknown host gets nothing.
def reasoning_params(url, model, level):
    """The provider's own parameters for reasoning "less" or "off" ({} for "" or an unknown provider)."""
    model = str(model or "").lower()
    if level not in ("less", "off"):
        return {}
    if "openrouter.ai/" in url:
        return {"reasoning": {"effort": "minimal" if level == "less" else "none", "exclude": True}}
    if "api.z.ai/" in url:
        return {"thinking": {"type": "disabled"}} if level == "off" else {}
    if "generativelanguage.googleapis.com/" in url:
        # Gemini's thinking models through the OpenAI-compatible endpoint (2026-11-28): little thinking, so that
        # the answer keeps its room; "low" is accepted by every thinking model of the free tier
        return {"reasoning_effort": "low"}
    if "api.groq.com/" in url:
        if "gpt-oss" in model:
            return {"reasoning_effort": "low"}
        if "qwen3.8" in model:
            return {"reasoning_effort": "none"} if level == "off" else {}
    return {}


def ask(url, key, model, messages, timeout=REQUEST_TIMEOUT, opener=urllib.request.urlopen,
        max_tokens=MAX_TOKENS, temperature=0.1, meter=None, reasoning="less"):
    """The model's answer text, or raises (kind, detail). meter(status, headers, usage, body): what
    the answer says about the quota (tools/ai-quota.py), also for an error."""
    request = {"model": model, "messages": messages, "temperature": 0.1, "max_tokens": max_tokens}
    # 2026-11-25/27: free reasoning models spent the whole answer on their reasoning and gave no text
    request.update(reasoning_params(url, model, reasoning))
    if temperature != 0.1:
        request["temperature"] = min(0.3, max(0.0, float(temperature)))      # always low: never above 0.3
    body = json.dumps(request).encode()
    if "generativelanguage.googleapis.com/" in url:
        # a request with whole large files takes Gemini longer than the others' 150 s (run 46178015817: TimeoutError)
        timeout = max(timeout, GEMINI_TIMEOUT)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "User-Agent": "IKE-autofix", "X-Title": "I.K.E. automatic fix"})
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read(4_000_000).decode("utf-8", "replace"))
            headers = getattr(r, "headers", None)
        if meter:
            meter(200, headers, data.get("usage") if isinstance(data, dict) else None, "")
    except urllib.error.HTTPError as e:
        wait = 0
        try:
            wait = int(float((e.headers or {}).get("Retry-After") or 0))
        except (TypeError, ValueError):
            wait = 0
        try:
            said = e.read(20_000).decode("utf-8", "replace") if e.fp is not None else ""
        except Exception:
            said = ""
        if meter:
            meter(402 if billing_in(said) else e.code, e.headers, None, said[:2000])
        if billing_in(said):                # never a quota to wait for: money is asked
            raise Stop("unavailable", "HTTP %d, billing" % e.code, 0)
        if e.code == 404 and DATA_POLICY.search(said):
            # OpenRouter's account setting blocks the free endpoints (openrouter.ai/docs: "No endpoints found
            # matching your data policy"): an owner's setting, never a quota and never a model that is gone
            raise Stop("policy", "HTTP 404, the account's privacy setting", 0, 404)
        words = redact(error_words(said), [key])
        if e.code == 429 and "openrouter.ai/" in url and model_busy(said):
            # one free model's own pool, busy upstream: the next model at once, nothing waited
            raise Stop("quota", "HTTP 429, this model is busy upstream" + (": " + words if words else ""), 0, 429,
                       "model")
        raise Stop(classify(e.code), "HTTP %d" % e.code + (": " + words if words else ""), wait, e.code)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as e:
        # http.client's IncompleteRead (an answer cut off) is no OSError: until the
        # final review of 1.1.18 it skipped the retry of a server error
        raise Stop("temporary", type(e).__name__)
    if cost_of(data) > 0:
        # WP9: the answer itself says it cost money; the provider is not free here
        raise Stop("unavailable", "the answer reports a cost")
    try:
        # Gemini's answer cut off by its thinking has a message with no "content" at all (2026-11-28): read as
        # empty, so that it is the cutoff it is (and asked again with less reasoning), not "no answer"
        content = (data["choices"][0].get("message") or {}).get("content") or ""
        finish = data["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise Stop("temporary", "no answer")
    if not content and finish == "length":
        # the room for the answer went to the model's reasoning: no text at all (the next model)
        raise Stop("cutoff", "the answer was cut off before its text (its reasoning took all the room)")
    if isinstance(content, list):          # content given in parts: their text
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict) and
                          isinstance(p.get("text"), str))
    return content if isinstance(content, str) else ""


def model_busy(said):
    """A 429 of one free model's pool upstream (tools/ai-quota.json, OpenRouter's model_words)."""
    try:
        quota = _tool("ai-quota")
        conf = quota.load_limits()["providers"].get("OpenRouter") or {}
    except Exception:
        return False
    return quota.per_model(conf, said)


def parse(text):
    """The JSON object of an answer (code fences and reasoning around it tolerated)."""
    if not isinstance(text, str):
        raise ValueError("the answer is not text")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict) or not isinstance(obj.get("edits", []), list):
        raise ValueError("the JSON object has no list of edits")
    return obj


_NUMBERED = re.compile(r"^ {0,6}\d{1,6}  ")       # "  740  " in front of the excerpts' lines


def _unnumbered(text):
    """The text without the line numbers of the excerpts, when every line has one
    (2026-11-19: a model copied them along, and nothing matched)."""
    lines = text.split("\n")
    body = [ln for ln in lines if ln.strip()]
    if body and all(_NUMBERED.match(ln) for ln in body):
        return "\n".join(_NUMBERED.sub("", ln, count=1) for ln in lines)
    return text


def _locate(current, find):
    """(start, end) of find in current: exact, or line by line ignoring the
    spaces at the end of lines. None when absent or not unique."""
    if current.count(find) == 1:
        start = current.index(find)
        return start, start + len(find)
    if current.count(find) > 1:
        return None
    want = [ln.rstrip() for ln in find.strip("\n").split("\n")]
    if not want or not any(want):
        return None
    lines = current.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    hits = [i for i in range(len(lines) - len(want) + 1)
            if all(lines[i + k].rstrip() == want[k] for k in range(len(want)))]
    if len(hits) != 1:
        return None
    i = hits[0]
    end_line = i + len(want) - 1
    return offsets[i], offsets[end_line] + len(lines[end_line])


def apply_edits(workdir, edits, shown, allow_adblock=False, security=False, lists=False, builder=""):
    """Apply the edits (all or none). Returns the changed files; raises ValueError."""
    if not isinstance(edits, list):
        raise ValueError("the edits are not a list")
    if len({e.get("file") for e in edits if isinstance(e, dict) and isinstance(e.get("file"), str)}) > MAX_FILES:
        raise ValueError("more than %d files" % MAX_FILES)
    new = {}
    for e in edits:
        if not isinstance(e, dict):
            raise ValueError("an edit is not an object")
        path, find, repl = e.get("file"), e.get("find"), e.get("replace")
        if not all(isinstance(x, str) for x in (path, find, repl)) or not find:
            raise ValueError("an edit lacks file, find or replace")
        path = path.strip()
        if path.startswith("./"):
            path = path[2:]
        if ".." in Path(path).parts or path not in shown:
            raise ValueError("%s is not one of the files shown" % path)
        if builder:
            # WP11: the one builder, nothing else; the checker then judges the re-anchoring itself
            if path != BUILDERS.get(builder):
                raise ValueError("%s may not be changed when the builder is re-anchored: only %s"
                                 % (path, BUILDERS.get(builder, "?")))
        elif lists and not editable(path, True, lists=True):
            raise ValueError("%s may not be changed in the filter lists' analysis: only I.K.E.'s adapter "
                             "(ike/scriptlets.py, ike/blocker.py, ike-adblock/src/)" % path)
        if not builder and not tier_b_path(path) and (not editable(path, allow_adblock) or (
                not allow_adblock and path in ("ike/blocker.py", "ike/scriptlets.py"))):
            raise ValueError("%s may not be changed in this run (the ad blocker only with an "
                             "update of its engine)" % path)
        rule = None if builder or (AUTO["on"] and path == MANIFEST) or tier_b_path(path) else _checker_rule()
        why = rule(path, allow_adblock, security) if rule else ""
        if why:
            raise ValueError("%s may not be changed: %s" % (path, why))
        current = new.get(path)
        if current is None:
            if (workdir / path).is_symlink():
                raise ValueError("%s is a link" % path)
            current = (workdir / path).read_text("utf-8")
        find, repl = _unnumbered(find), _unnumbered(repl)
        span = _locate(current, find)
        if span is None:
            raise ValueError("the text to replace appears %d times in %s (must be exactly once, "
                             "copied without the line numbers)" % (current.count(find), path))
        start, end = span
        if current[start:end] != find and find.endswith("\n") and not repl.endswith("\n"):
            repl += "\n"
        if current[start:end] != find and not find.endswith("\n") and repl.endswith("\n"):
            repl = repl[:-1]
        new[path] = current[:start] + repl + current[end:]
    for path, text in new.items():
        (workdir / path).write_text(text, "utf-8")
    return sorted(new)


def files_shown(workdir, related):
    """The full text of the files involved, within the budget: {path: text}."""
    out, used = {}, 0
    for path in related:
        p = workdir / path
        if not (path.startswith(SHOWN_ROOTS) or (AUTO["on"] and path == MANIFEST) or tier_b_path(path)) \
                or not p.is_file() \
                or p.is_symlink():                                                    # a link: never followed
            continue
        text = p.read_text("utf-8", errors="replace")
        if used + len(text) > FILES_BUDGET:
            continue
        out[path] = text
        used += len(text)
    return out


EXCERPT = re.compile(r"^### `([\w./-]+)`, lines \d+-\d+ \(the failure points at line \d+\)$", re.M)


def editable_files(shown, context, related):
    """The files an edit may change: the ones shown in full and the ones whose code at the failure is shown in an
    excerpt (tools/autofix-context.py). A large file (ike/window.py, 175 KB) never fits whole, and its fix was
    refused as "not one of the files shown" (the drill, 2026-11-28); the text to replace must still be copied
    exactly and appear once in the file, and the checks after it are the same."""
    out = dict(shown)
    for path in EXCERPT.findall(context or ""):
        if path in related and path not in out:
            out[path] = ""
    return out


NOTES = re.compile(r"\n(?=## (?:One problem per attempt|AUTOMAT's memory of this error|What changed upstream"
                   r"|The fix of this attempt's last round"
                   r"|Why earlier fixes were refused|Previous automatic fix))")


def failure_within(failure, room):
    """The failure description within `room` characters: the end of the error itself (its last lines
    say what failed), then the notes the plan added after it (one problem per attempt, AUTOMAT's
    memory, what changed upstream, earlier refusals), each cut to its share from its start. Without
    such notes: the end of the text, as before."""
    parts = NOTES.split(failure)
    if len(parts) == 1:
        return failure[-room:]
    error, notes = parts[0], parts[1:]
    share = max(600, (room // 2) // len(notes))
    kept = [n if len(n) <= share else n[:share].rstrip() + "\n(... cut)\n" for n in notes]
    left = max(room // 2, room - sum(len(k) + 1 for k in kept))
    return error[-left:].rstrip() + "\n\n" + "\n".join(kept)


def message_for(failure, context, shown, budget, refused=""):
    """The user message within the provider's budget (characters): the failure,
    the code at it, then whole files while they fit."""
    head = "# The failure\n\n%s\n\n" % failure_within(failure, max(2000, budget // 3))
    if refused:
        head += ("# A fix already refused\n\nThe automatic checks refused an earlier fix for this "
                 "failure:\n\n%s\nDo not repeat it.\n\n" % refused[:2000])
    room = budget - len(head)
    body = context[:max(0, room)]
    room -= len(body)
    files = ""
    for path, text in shown.items():
        part = "\n## File `%s`\n\n```text\n%s\n```\n" % (path, text)
        if len(part) <= room:
            files += part
            room -= len(part)
    return head + body + "\n\n# Files involved (full text)\n" + (files or "\n(not sent: see the code above)\n")


def compact_message(failure, context, shown, room, refused="", to_change=()):
    """The user message within `room` characters, for a provider whose limit per minute is small (fitted): what
    must stay, deterministically: the failure (the end of the error and the plan's notes, the refusal reasons among
    them, each cut to its share from its start), why an earlier fix was refused, the names of the files to change;
    then whole files to change while they fit (the smallest first); the code around the failure takes the rest."""
    room = max(MIN_USER, int(room))
    names = [p for p in shown if p in to_change] or list(shown)
    listing = "# Files to change\n\n" + "".join("- %s\n" % p for p in names) + "\n" if names else ""
    refusal = ("# A fix already refused\n\nThe automatic checks refused an earlier fix for this failure:\n\n%s\n"
               "Do not repeat it.\n\n" % refused[:max(300, room // 6)]) if refused else ""
    head_room = max(400, room // 2 - len(refusal) - len(listing))
    parts = NOTES.split(failure)
    error, notes = parts[0], parts[1:]
    if notes:
        share = max(150, (head_room * 2 // 3) // len(notes))
        kept = [n if len(n) <= share else n[:share].rstrip() + "\n(... cut)\n" for n in notes]
        tail = error[-max(200, head_room - sum(len(k) + 1 for k in kept)):]
        text_failure = tail.rstrip() + "\n\n" + "\n".join(kept)
    else:
        text_failure = failure[-head_room:]
    text = "# The failure\n\n%s\n\n" % text_failure + refusal + listing
    left = room - len(text) - 120
    files = ""
    for path in sorted(names, key=lambda n: (len(shown[n]), n)):
        part = "\n## File `%s`\n\n```text\n%s\n```\n" % (path, shown[path])
        if len(part) <= left:
            files += part
            left -= len(part)
    text += "# Files involved (full text)\n" + (files or "\n(not sent, too large for this provider: see the code "
                                                          "below)\n")
    text += "\n# Code at the failure\n\n" + context[:max(0, room - len(text) - 40)]
    return text[:room]


def fitted(spend, provider, system, user, tokens, compact):
    """(user, answer tokens, note) of a request that fits the provider's limit of tokens per minute (2026-11-25:
    Groq's request of 7,678 tokens against its 6,000 a minute was skipped every day, so it could never help).
    Unchanged when it fits; else compact(room) builds a smaller one, with a smaller answer when needed (never
    below MIN_ANSWER). (None, tokens, why) only when even the smallest request cannot fit."""
    quota = _tool("ai-quota")
    limit = spend.minute_limit(provider, "tokens")

    def size(text, answer):
        return quota.estimate_tokens(len(system) + len(text), answer, spend.limits)
    if not limit or size(user, tokens) <= limit:
        return user, tokens, ""
    per = spend.limits.get("chars_per_token") or 3
    cap = int(limit * FIT_SHARE)
    answer = tokens
    room = int((cap - answer) * per) - len(system)
    if room < MIN_USER and answer > MIN_ANSWER:
        answer = max(MIN_ANSWER, cap - int((len(system) + MIN_USER) / float(per)) - 1)
        room = int((cap - answer) * per) - len(system)
    if room < MIN_USER:
        return None, tokens, ("even the smallest request (the rules, the failure and the files to change: %d tokens) "
                              "is larger than its limit per minute (%d tokens): not asked" % (
                                  size("x" * MIN_USER, min(answer, MIN_ANSWER)), limit))
    small = compact(room)
    if size(small, answer) > limit:
        return None, tokens, ("the request could not be made smaller than its limit per minute (%d tokens, %d a "
                              "minute): not asked" % (size(small, answer), limit))
    return small, answer, ("the request was fitted to its limit per minute: %d tokens instead of %d (%d a minute)"
                           % (size(small, answer), size(user, tokens), limit))


def fit_followup(messages, base, tokens, budget, provider):
    """An answer told what the checks found (the inner loop) within the provider's limit per minute: the model's
    earlier answer is cut first, then dropped, then the feedback is cut. The base request was fitted already."""
    quota = _tool("ai-quota")
    limit = budget.minute_limit(provider, "tokens")
    if not limit or len(messages) <= len(base):
        return messages

    def size(ms):
        return quota.estimate_tokens(sum(len(m.get("content") or "") for m in ms), tokens, budget.limits)
    if size(messages) <= limit:
        return messages
    per = budget.limits.get("chars_per_token") or 3
    free = int((int(limit * FIT_SHARE) - tokens) * per) - sum(len(m.get("content") or "") for m in base)
    extra = [dict(m) for m in messages[len(base):]]
    feedback = extra[-1]
    others = extra[:-1]
    keep = free - len(feedback.get("content") or "")
    for m in others:
        m["content"] = (m.get("content") or "")[:max(0, keep)]
        keep -= len(m["content"])
    others = [m for m in others if m["content"]]
    if free < len(feedback.get("content") or ""):
        feedback["content"] = (feedback.get("content") or "")[:max(200, free)]
    return list(base) + others + [feedback]


def diff_of(workdir):
    return _git(workdir, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--", ".",
                ":(exclude).autofix").stdout


def undo(workdir, files):
    _git(workdir, "checkout", "-q", "--", *files)


def _agent_lists_note():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ike_autofix_agent", Path(__file__).resolve().parent /
                                                      "autofix-agent.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.LISTS_NOTE
    except Exception:
        return ""


def checked(workdir, checker, related, allow_adblock, security=False, lists=False, builder=""):
    """(exit status, reasons) of the trusted checks on the work tree's changes."""
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(diff_of(workdir))
        patch = f.name
    cmd = [sys.executable, "-I", checker, "--repo", str(workdir), "--patch", patch, "--check-only"]
    if related:
        cmd += ["--related", related]
    if allow_adblock:
        cmd.append("--allow-adblock")
    if security:
        cmd.append("--security")          # WP6: a fix of a security finding, the stricter rules
    if lists:
        cmd.append("--lists")
    if builder:
        cmd += ["--builder", builder]       # WP11: the builders' re-anchoring rule
    if AUTO["on"]:
        cmd.append("--auto")                # the static guard of a fix that may reach main by itself
    if TIER_B["on"]:
        cmd.append("--tier-b")              # the owner's switch: the narrow form of tools/tier-b.py
    run = subprocess.run(cmd, capture_output=True, text=True, check=False)
    os.unlink(patch)
    return run.returncode, run.stdout.strip()[-2000:]


def linted(workdir, files):
    """(ok, output) of ruff on the changed Python files, after its own safe fixes
    (an unused import, the order of imports: no AI needed). 2026-11-19: a right
    fix left an unused import and the guard's lint refused it. No ruff: ok."""
    py = [f for f in files if f.endswith(".py")]
    if not py:
        return True, ""
    base = ["ruff", "check", "--no-cache", "--force-exclude"]
    try:
        subprocess.run(base + ["--fix", "--quiet", *py], cwd=workdir, capture_output=True, text=True,
                       check=False, timeout=120)
        run = subprocess.run(base + py, cwd=workdir, capture_output=True, text=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return True, ""
    return run.returncode == 0, (run.stdout + run.stderr).strip()[-2000:]


def redact(text, keys):
    for k in keys:
        if k:
            text = text.replace(k, "***")
    return text


def for_log(text, limit=300):
    """Text a model wrote (or chose, like a file name), safe to print in the job's
    log: one line, no control characters, and no "::" that could start a GitHub
    workflow command (1.1.18)."""
    text = re.sub(r"[\x00-\x1f\x7f\x85  ]+", " ", str(text))
    return re.sub(r":(?=:)", ": ", text)[:limit]


class Feedback(ValueError):
    """What a check found wrong with a fix, to tell the same model (the inner loop)."""


def one_model(url, key, model, base, tokens, deadline, opener, workdir, shown, a, refused, applied, run=None):
    """Ask one model, at most twice (with --inner: INNER_TRIES answers, each told what the checks
    found). Returns (outcome, text, refused): outcome is ok | none | refused | error | quota | auth |
    toolarge | budget | loop, text its summary (or the checker's reasons for "refused"), refused why
    the checks refused its fix (for the next model). The files it changed stay listed in `applied`
    until they are undone, so the caller can undo them after any error. run: what part 2 of AUTOMAT
    adds to a run ({"provider", "budget", "loop", "inner", "limits", "temperature"}), or None."""
    run = run or {}
    inner = _tool("autofix-inner") if getattr(a, "inner", False) else None
    budget, provider, loop = run.get("budget"), run.get("provider", ""), run.get("loop")
    messages, tries, waited = list(base), 0, False
    most = inner.INNER_TRIES if inner else 2
    answers, stops = 0, 0
    busy, minute_waits = 0, 0
    reasoning = "less"
    while tries < most:
        tries += 1
        size = 0
        if budget is not None:
            messages = fit_followup(messages, base, tokens, budget, provider)
            size = _tool("ai-quota").estimate_tokens(sum(len(m.get("content") or "") for m in messages), tokens,
                                                     budget.limits)
            ok, why = budget.allows(provider, size, "fix")
            if not ok:
                print("  not asked: %s" % for_log(why), flush=True)
                budget.skipped[provider] = why
                return "budget", "", refused
            pause = budget.wait_seconds(provider, size)
            if pause:
                if pause > 75 or time.monotonic() + pause > deadline:
                    print("  its limit per minute is used up for %d s: the next one" % pause, flush=True)
                    return "quota", "", refused
                time.sleep(pause)
        seen = {}

        def meter(status, headers, usage, body, seen=seen):
            seen.update(done=True)
            if budget is not None:
                budget.note(provider, size, "fix", usage=usage, headers=headers, status=status, body=body)
        try:
            answer = ask(url, key, model, messages, opener=opener, max_tokens=tokens,
                         temperature=run.get("temperature", 0.1), meter=meter, reasoning=reasoning)
        except Stop as s:
            if budget is not None and not seen:
                budget.note(provider, 0, "fix", requests=1)        # asked, no answer read: one request all the same
            kind = s.args[0]
            wait = s.args[2] if len(s.args) > 2 else 0
            code = s.args[3] if len(s.args) > 3 else 0
            print("  stopped: %s (%s)" % (kind, for_log(s.args[1])), flush=True)
            if len(s.args) > 4 and s.args[4] == "model":
                return "quota", "", refused             # this model's pool upstream: the next model, no wait
            if kind == "cutoff" and reasoning != "off" and reasoning_params(url, model, "off") \
                    and time.monotonic() < deadline:
                # its reasoning took all the room: the same model once more, with its reasoning off
                reasoning = "off"
                print("  asked again with its reasoning off", flush=True)
                tries -= 1
                continue
            # a busy service (503): asked again after a growing pause (BACKOFF, or its own short Retry-After)
            if kind == "temporary" and code == 503 and busy < len(BACKOFF):
                pause = wait if 0 < wait <= 60 else BACKOFF[busy]
                if time.monotonic() + pause < deadline:
                    busy += 1
                    print("  busy: asked again in %d s" % pause, flush=True)
                    time.sleep(pause)
                    tries -= 1
                    continue
            # a 429 the budget read as a limit per minute or of concurrency (tools/ai-quota.py rate_limit_scope),
            # never the day's quota: waited out and asked again, a few times within the run's time
            if kind == "quota" and budget is not None and not budget.spent(provider) and minute_waits < MINUTE_RETRIES:
                pause = max(int(wait or 0), budget.wait_seconds(provider, size))
                if pause <= MINUTE_WAIT and time.monotonic() + pause < deadline:
                    minute_waits += 1
                    waited = True
                    print("  a limit per minute: asked again in %d s" % (pause + 1), flush=True)
                    time.sleep(pause + 1)
                    tries -= 1
                    continue
            # too large for its limit per minute, which its answer just told (the budget learned it): the request is
            # fitted to it and asked again (the caller), never the provider skipped for its size
            if kind == "toolarge" and budget is not None and (budget.minute_limit(provider, "tokens") or 0) < size \
                    and not run.get("refitted"):
                return "refit", "", refused
            stops += 1
            if inner and stops > 2:
                return "quota", "", refused
            if kind == "temporary" and tries < 2:
                time.sleep(10)
                continue
            # a limit per minute (Groq: about 8,000 tokens): wait it out once,
            # when the server says it is short, and ask the same model again
            if kind == "quota" and 0 < wait <= 60 and not waited and time.monotonic() + wait < deadline:
                waited = True
                time.sleep(wait + 1)
                tries -= 1                  # the wait does not use up a try
                continue
            if kind in ("auth", "toolarge", "config", "unavailable", "policy"):
                return kind, "", refused
            return ("quota" if kind in ("quota", "temporary") else "error"), "", refused
        answers += 1
        try:
            obj = parse(answer)
            if inner:
                obj = inner.strict(obj)             # exactly the patch format, small edits
            if obj.get("fixable") is False:
                return "none", str(obj.get("summary") or ""), refused
            if not obj.get("edits"):
                # 2026-11-19: a model named the cause and gave no edit; only an
                # explicit "fixable": false counts as "cannot be fixed"
                raise ValueError("the answer has no edits: give the exact edits of the fix, "
                                 "or \"fixable\": false if it cannot be fixed in the code")
            applied[:] = apply_edits(workdir, obj["edits"], shown, a.allow_adblock, getattr(a, "security", False),
                                     getattr(a, "lists", False), getattr(a, "builder", ""))
            summary = str(obj.get("summary") or "")
            print("  edits applied: %s" % for_log(", ".join(applied)), flush=True)
            if loop is not None:
                # going in circles: the same patch twice stops the attempt (tools/automat-route.py)
                seen_before = loop.check(_tool("automat-memory").patch_hash(diff_of(workdir)))
                if seen_before == "twice":
                    undo(workdir, applied)
                    applied.clear()
                    print("  the same patch twice: the attempt stops here", flush=True)
                    return "loop", summary, refused
                if seen_before == "tried":
                    raise Feedback("this exact change was already tried for this error and its tests failed "
                                   "(AUTOMAT's memory): find another way, do not send it again")
            if inner:
                why, ran = inner.cheap(workdir, applied, getattr(a, "cargo_cmd", "") or "")
                print("  cheap checks: %s" % for_log(", ".join("%s %s" % r for r in ran)), flush=True)
                if why:
                    raise Feedback(why)
            if a.checker:
                status, reasons = checked(workdir, a.checker, a.related, a.allow_adblock,
                                          getattr(a, "security", False), getattr(a, "lists", False),
                                          getattr(a, "builder", ""))
                if status == 3:
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused for safety: no other model is asked", flush=True)
                    return "refused", reasons, refused
                if status in (1, 2):         # refused, or the edits changed nothing
                    if inner and tries < most:
                        refused = reasons
                        raise Feedback("The automatic checks refused the fix:\n\n%s" % reasons)
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused by the checks: the next model is told why", flush=True)
                    return "error", summary, reasons
            if a.lint:
                clean, said = linted(workdir, applied)
                if not clean:
                    if inner and tries < most:
                        refused = "The lint (ruff) refused the fix:\n\n" + said
                        raise Feedback(refused)
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused by the lint: the next model is told why", flush=True)
                    return "error", summary, "The lint (ruff) refused the fix:\n\n" + said
            return "ok", summary, refused
        except Feedback as e:
            # the inner loop: undone, and the same model is told what the checks found
            if applied:
                undo(workdir, applied)
                applied.clear()
            print("  refused by a check: the same model is told why (answer %d of %d)" % (answers, most), flush=True)
            messages = base + [{"role": "assistant", "content": str(answer)[:20000]},
                               {"role": "user", "content": "That fix was undone. %s\n\nAnswer again with one "
                                "JSON object as described: a fix that passes this check." % str(e)[:3000]}]
        except (ValueError, OSError) as e:
            if applied:
                undo(workdir, applied)
                applied.clear()
            print("  answer not usable: %s" % for_log(e), flush=True)
            messages = base + [{"role": "assistant", "content": str(answer)[:20000]},
                               {"role": "user", "content": "That answer could not be applied: %s. "
                                "Answer again with one JSON object as described." % e}]
    return "error", "", refused


def _ping_one(url, key, model, opener):
    try:
        ask(url, key, model, [{"role": "user", "content": "Answer with the word OK."}],
            timeout=60, opener=opener, max_tokens=16)
        return "ok"
    except Stop as e:
        if e.args and e.args[0] == "cutoff":
            return "ok"                 # it answered: 16 tokens are too few for a reasoning model's text
        return e.args[0] if e.args else "temporary"


def ping(env=os.environ, opener=urllib.request.urlopen):
    """1.1.19, for the weekly check: one tiny question to the first model of
    each reserve that has a key, so a refused key or a model that is gone is
    found before a real failure needs it. [(provider, model, result)], result
    "ok" or a kind of classify(); keys never leave this function."""
    out, done = [], set()
    for name, url, key, model, _budget, _tokens in chain(env):
        if name in done:
            continue
        done.add(name)
        result = _ping_one(url, key, model, opener)
        if result == "config" and name == "OpenRouter":
            # as in a real run: a listed free model that is gone gives way to
            # the free models OpenRouter offers now
            try:
                for m in free_models(key, opener=opener)[:1]:
                    model, result = m, _ping_one(url, key, m, opener)
            except Exception:
                pass
        out.append((name, model, result))
    return out


def main(argv=None, env=os.environ, opener=urllib.request.urlopen):
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["ping"]:            # autofix-reserve.py ping OUT.json (health.yml)
        Path(argv[1]).write_text(json.dumps(ping(env, opener)) + "\n", "utf-8")
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--prompt", required=True, help="the agent's instructions (rules)")
    ap.add_argument("--status", required=True)
    ap.add_argument("--total-timeout", type=int, default=TOTAL_TIMEOUT)
    ap.add_argument("--checker", help="tools/check-autofix-patch.py from main: each fix is checked")
    ap.add_argument("--related", help="the files involved (for the checker)")
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--security", action="store_true", help="a fix of a security finding: the stricter rules")
    ap.add_argument("--lists", action="store_true", help="the filter lists' analysis: the adapter only (WP8)")
    ap.add_argument("--builder", default="", choices=["", *sorted(BUILDERS)],
                    help="the builders' re-anchoring (WP11): that builder's existing patches only")
    ap.add_argument("--first", default="", help="the provider this attempt starts with (FIX_ATTEMPTS rotation)")
    ap.add_argument("--refused", help="why the checks refused Antigravity's fix")
    ap.add_argument("--lint", action="store_true", help="ruff on each fix (its safe fixes first)")
    ap.add_argument("--auto", action="store_true", help="a fix that may reach main by itself: the static guard")
    # part 2 of AUTOMAT
    ap.add_argument("--inner", action="store_true", help="the inner loop: strict format, cheap checks, the errors "
                                                         "back to the same model (tools/autofix-inner.py)")
    ap.add_argument("--cargo-cmd", default="", help="how cargo is run for `cargo check` (a user with no keys)")
    ap.add_argument("--quota-limits", help="tools/ai-quota.json (the free quotas, as data)")
    ap.add_argument("--quota-state", help="quota.json of the data branch (today's use)")
    ap.add_argument("--quota-usage", help="where this run's use is written (numbers only)")
    ap.add_argument("--candidate", default="", help="the branch being fixed (its share of the quota)")
    ap.add_argument("--quota-memory", help="AUTOMAT's memory.json: the real updates still pending (background "
                                           "work waits for them, tools/ai-quota.py)")
    ap.add_argument("--quota-pending", help="the plan's list of the real updates still pending (open pull requests "
                                            "whose checks are not green, and the memory's rows)")
    ap.add_argument("--order", default="", help="the providers in the order of this kind of task")
    ap.add_argument("--task", default="", help="the kind of task (tools/automat-route.py)")
    ap.add_argument("--tried", help="the fingerprints of the patches that already failed for this error")
    ap.add_argument("--tier-b", action="store_true", help="the owner turned AUTOMAT_TIER_B on (tools/tier-b.py)")
    a = ap.parse_args(argv)
    AUTO["on"] = bool(a.auto)
    TIER_B["on"] = bool(a.tier_b and a.auto)
    workdir = Path(a.workdir)
    auto = workdir / ".autofix"

    def read(name):
        try:
            return "" if (auto / name).is_symlink() else (auto / name).read_text("utf-8", "replace")
        except OSError:
            return ""
    failure, context = read("failure.md"), read("context.md")
    related = [line.strip() for line in read("related.txt").splitlines() if line.strip()]
    shown = files_shown(workdir, related)
    editable = editable_files(shown, context, related)
    rules = Path(a.prompt).read_text("utf-8") + (SECURITY_RULES if a.security else "") + builder_rules(a.builder) \
        + (AUTO_RULES if a.auto and not a.builder else "") + (TIER_B_RULES if TIER_B["on"] and not a.builder else "")
    keys = [env.get(p[2], "") for p in PROVIDERS]
    refused = ""
    if a.refused:
        try:
            refused = Path(a.refused).read_text("utf-8", "replace")
        except OSError:
            refused = ""
    result, used, summary = "nokey", "", ""
    said_none, none_summary = [], ""          # the models that answered "fixable": false
    skip, deadline = set(), time.monotonic() + a.total_timeout
    plan = rotated(chain(env), a.first or env.get("AUTOFIX_FIRST", ""))
    if a.order:
        plan = ordered(plan, a.order.split(","))
    # part 2 of AUTOMAT: the budget of the free quotas, the cap of the answer for this kind of task, and
    # the patches that already failed for this error
    spend, limits, route = None, None, None
    if a.quota_limits or a.quota_state or a.quota_usage:
        quota = _tool("ai-quota")
        limits = quota.load_limits(a.quota_limits)
        # (the weekly check names Gemini, the provider behind Antigravity)
        gone = unavailable(env) | ({"Antigravity"} if "Gemini" in unavailable(env) else set())
        has_key = [n for n in quota.NAMES if n not in gone and (
            env.get(REGISTRY.GEMINI_KEY, "").strip() if n == "Antigravity" else
            env.get(next(p[2] for p in PROVIDERS if p[0] == n), "").strip())]
        # the reviewers may also be providers whose key this step does not hold (Gemini): the workflow says
        # which ones have a key at all (AUTOFIX_REVIEWERS), else those this step can see
        named = [n.strip() for n in (env.get("AUTOFIX_REVIEWERS") or "").split(",") if n.strip() in quota.NAMES]
        spend = quota.Budget(limits, quota.load_state(a.quota_state) if a.quota_state else None, a.candidate,
                              tier_b=TIER_B["on"], available=[n for n in (named or has_key) if n not in gone],
                              pending=quota.pending_for_run(a.quota_memory, a.quota_pending, limits))
        # OpenRouter's free models share one cap of requests a day for the whole account: read it from the
        # account itself (GET /api/v1/key, no model asked), else the documented default stays
        key = env.get(next(p[2] for p in PROVIDERS if p[0] == "OpenRouter"), "").strip()
        if key and "OpenRouter" not in gone and spend.account(
                "OpenRouter", quota.read_account(limits["providers"]["OpenRouter"], key, opener,
                                                 REGISTRY.OPENROUTER_KEY_INFO)):
            print("OpenRouter: %s free requests a day for all its free models together (read from the account)"
                  % spend.day_limit("OpenRouter", "requests"), flush=True)
    # OpenRouter's free models of this moment, from its own list (refreshed), when it may be asked at all today
    listed = {}
    if spend is None or not (spend.spent("OpenRouter") or spend.priority_why("OpenRouter")):
        plan = refreshed(plan, opener, listed)
    if a.task:
        route = _tool("automat-route")
        limits = limits or _tool("ai-quota").load_limits(a.quota_limits)
    tried = []
    if a.tried:
        try:
            tried = [x.strip() for x in Path(a.tried).read_text("utf-8").split() if x.strip()]
        except OSError:
            tried = []
    loop = _tool("automat-route").Loop(tried) if (a.inner or a.tried) else None
    looped = ""
    discovered, refused_keys = bool(listed.get("read")), []
    # WP9: whether any model really answered; a chain where each model was busy,
    # out of quota or not free ends "no provider available" (the work waits:
    # tools/ai-work.py), not a question for the owner
    outcomes, not_free = [], []
    deferred, second, policy_blocked = "", False, []
    system = rules + "\n" + instructions(a.allow_adblock, a.lists, a.builder)
    while True:
        for provider, url, key, model, budget, tokens in plan:      # the list may grow (free_models)
            if provider in skip:
                continue
            if time.monotonic() > deadline:
                result = result if result != "nokey" else "quota"
                break
            used = "%s / %s" % (provider, model)
            print("Reserve: %s" % for_log(used), flush=True)
            applied = []
            if route is not None:
                tokens = route.answer_tokens(a.task, tokens, limits)
            extra = {"provider": provider, "budget": spend, "loop": loop,
                     "temperature": route.temperature(limits) if route is not None else 0.1}
            outcome = "refit"
            while outcome == "refit":
                user = message_for(failure, context, shown, budget, refused)
                if spend is not None:
                    # 2026-11-25: a request larger than the provider's limit per minute is fitted to it, never skipped
                    # for its size (fitted)
                    user, tokens, note = fitted(spend, provider, system, user, tokens, functools.partial(
                        compact_message, failure, context, shown, refused=refused, to_change=related))
                    if user is None:
                        print("  not asked: %s" % for_log(note), flush=True)
                        spend.skipped[provider] = note
                        outcome = "budget"
                        break
                    if note:
                        print("  %s" % for_log(note), flush=True)
                base = [{"role": "system", "content": system}, {"role": "user", "content": user}]
                try:
                    outcome, said, refused = one_model(url, key, model, base, tokens, deadline, opener,
                                                       workdir, editable, a, refused, applied, extra)
                except Exception as e:                    # 1.1.18: a malformed answer never ends the chain
                    if applied:
                        undo(workdir, applied)
                    print("  answer not usable (%s): the next model goes on" % type(e).__name__, flush=True)
                    outcome, said = "error", ""
                if outcome == "refit":
                    if extra.get("refitted"):
                        outcome = "toolarge"
                    else:
                        extra["refitted"] = True
                        print("  too large for the limit per minute it just told: fitted and asked again", flush=True)
            outcomes.append(outcome)
            if outcome in ("ok", "refused"):
                result, summary = outcome, said
                break
            if outcome == "unavailable":
                # a billing error, a paid tier or a cost in the answer: this provider is
                # not free here; none of its models is asked again in this run
                not_free.append(provider)
                skip.add(provider)
                if spend is not None:
                    spend.mark_spent(provider, "not free (billing, or a cost in the answer)")
            if outcome == "policy":
                # an owner's setting of the account, said plainly; the other providers go on
                policy_blocked.append(provider)
                skip.add(provider)
                outcome = "unavailable"
            if outcome == "budget":
                # the budget of the free quotas says no (spent today, the reviewers' reserve, this candidate's
                # share): none of this provider's models is asked in this run
                skip.add(provider)
            if outcome == "loop":
                # the same patch twice: the attempt stops and is recorded (tools/automat-route.py)
                looped = used
                result = "loop"
                break
            if outcome == "none":
                # 1.1.18: one model's word is not enough (a weak free model gives up on
                # a plain fix); the chain stops when two different models agree
                said_none.append(used)
                none_summary = said
                # 1.1.19 (autofix trial 4): two models of one provider (Z.AI's two
                # Flash models) stopped the chain before OpenRouter was asked
                if len({u.split(" / ")[0] for u in said_none}) >= 2:
                    print("  two providers say it cannot be fixed in the code: no other model is asked", flush=True)
                    result = "none"
                    break
                print("  says it cannot be fixed in the code: the next model is asked too", flush=True)
            if outcome == "auth":
                # final review of 1.1.18: a refused key read as "no fix found"; the
                # message now says which key to check
                refused_keys.append("%s (%s)" % (provider, next(p[2] for p in PROVIDERS if p[0] == provider)))
            if outcome in ("auth", "toolarge"):
                skip.add(provider)
                outcome = "error"
            if outcome == "config" and provider == "OpenRouter" and not discovered:
                # a listed free model is gone: try the free ones OpenRouter has now
                discovered = True
                tried = {m for _p, _u, _k, m, _b, _t in plan}
                for m in free_models(key, opener, exclude=tried):
                    print("  OpenRouter now offers %s: it is asked too" % for_log(m), flush=True)
                    plan.append((provider, url, key, m, budget, tokens))
            if outcome == "config":
                outcome = "error"
            result = outcome or "error"
        # the way forward (2026-11-25, PR #111): when no fix was kept and the reviewers' reserve alone kept
        # providers from being asked, the one whose fix leaves the most reviewers with room today is asked now
        # (tools/ai-quota.py way_forward); its two independent reviews come on a later day, and the fix never
        # reaches main without them. Only once, only for security fixes and real updates, only with time left.
        if spend is None or second or result in ("ok", "refused", "loop") or (result == "none" and len(
                {u.split(" / ")[0] for u in said_none}) >= 2) or time.monotonic() > deadline:
            break
        held = [n for n, why in spend.skipped.items() if str(why).startswith(_tool("ai-quota").RESERVE_WHY)]
        names = [n for n in dict.fromkeys(p[0] for p in plan) if n in held]
        choice, mode = spend.way_forward(names) if names else (None, "")
        if choice is None:
            break
        second = True
        # ("now" only when the day changed meanwhile: then the reserve holds as usual)
        spend.defer_reviews = mode == "reviews-later"
        deferred = choice if spend.defer_reviews else ""
        ranked = sorted(names, key=lambda n: (n != choice, -len(spend.reviewers_left(n)), names.index(n)))
        print("Nobody could be asked with the reviewers' reserve: %s writes the fix now, its reviews come on a "
              "later day (it never reaches main without them)" % choice, flush=True)
        for n in names:
            skip.discard(n)
            spend.skipped.pop(n, None)
        skip.update(n for n in dict.fromkeys(p[0] for p in plan) if n not in names)
        plan = sorted((p for p in plan if p[0] in names), key=lambda p: ranked.index(p[0]))
    no_provider = bool(outcomes) and all(o in ("quota", "unavailable", "budget", "policy") for o in outcomes)
    if no_provider and not_free and result != "quota":
        result = "unavailable"
    if no_provider and outcomes and all(o == "budget" for o in outcomes):
        result = "budget"
    if looped:
        result, used = "loop", looped
    if result != "ok" and result != "refused" and said_none:
        # nobody fixed it, and at least one model said it cannot be fixed in the code
        result, used, summary = "none", said_none[-1], none_summary
    message = MESSAGES[result] % used if "%s" in MESSAGES[result] else MESSAGES[result]
    if refused_keys:
        message += " Chiave rifiutata (401/403), va controllata: %s." % ", ".join(refused_keys)
    if result in ("ok", "none", "refused"):
        text = redact(summary.strip()[:3000], keys) or "La riserva non ha scritto un riassunto."
        (auto / "summary.md").write_text("%s\n\n_(%s)_\n" % (text, message), "utf-8")
    if policy_blocked:
        message += POLICY
    if not_free:
        message += " Non gratuite in questo run (fatturazione o costo nella risposta): %s." % ", ".join(
            sorted(set(not_free)))
    if deferred and result == "ok":
        message += DEFERRED
        if (auto / "summary.md").is_file():
            (auto / "summary.md").write_text((auto / "summary.md").read_text("utf-8") + "\n_(%s)_\n" % DEFERRED.strip(),
                                             "utf-8")
    status = {"result": result, "model": used, "message": message,
              "no_provider": no_provider and result not in ("ok", "refused", "none", "loop"),
              "not_free": sorted(set(not_free))}
    if deferred and result == "ok":
        status["reviews_deferred"] = True
    if spend is not None:
        # the run's use of the free quotas, as numbers, for the job that writes the data branch
        spend.result = "no-provider" if status["no_provider"] else ("answered" if outcomes else "")
        status["budget"] = {n: for_log(w, 200) for n, w in sorted(spend.skipped.items())}
        if spend.skipped:
            message += " Non interpellati per la quota gratuita: %s." % "; ".join(
                "%s (%s)" % (n, for_log(w, 160)) for n, w in sorted(spend.skipped.items()))
            status["message"] = message
        if status["no_provider"] and a.candidate:
            # the watchdog (2026-11-25): this run asked nobody either; said plainly when it is the second day or more
            quota = _tool("ai-quota")
            seen = json.loads(json.dumps(spend.state))
            quota.ran(seen, "no-provider", now=spend.now, component=a.candidate if a.candidate.startswith(
                "automation/") else "automation/update/" + a.candidate)
            warn = quota.stuck_text(seen, spend.now)
            if warn:
                status["watchdog"] = warn
                status["message"] = message = message + " " + warn
                print("::warning title=AUTOMAT watchdog::%s" % for_log(warn, 400), flush=True)
        if a.quota_usage:
            Path(a.quota_usage).write_text(json.dumps(spend.delta()) + "\n", "utf-8")
    if loop is not None and loop.stopped:
        status["loop"] = loop.stopped
    Path(a.status).write_text(json.dumps(status, ensure_ascii=False), "utf-8")
    print("Reserves: %s (%s)" % (result, for_log(used or "none")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
