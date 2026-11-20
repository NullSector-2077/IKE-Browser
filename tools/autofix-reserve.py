#!/usr/bin/env python3
"""The reserve assistants of the automatic fix (no AI here: this calls them).

When the Antigravity agent could not fix a failure (quota used up, Google not
answering, an error of the agent, or simply no fix), .github/workflows/autofix.yml
asks the reserves, one after the other, never together:

    1. Groq        (GROQ_API_KEY,       models in AUTOFIX_GROQ_MODELS)
    2. OpenRouter  (OPENROUTER_API_KEY, models in AUTOFIX_OPENROUTER_MODELS)

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
    unknown model, bad request (400/404) -> the next model (the variable must be fixed)
    server error, no answer              -> once more, then the next model
    request too large (413)              -> the next provider
    an answer that cannot be applied     -> once more, told what was wrong, then the next model
    a fix the checks refuse (--checker)  -> undone; the next model is told why
    a fix refused for safety (exit 3)    -> undone; stop: no other model is asked
    "no fix possible in the code"        -> the next model; stop when two models say so
    any other malformed answer or error  -> undone; the next model

What a model writes reaches the log only through for_log(): one line, and no
"::" that could start a GitHub workflow command.

--refused FILE: why the checks refused Antigravity's fix (the reserves are told,
so they do not repeat it).

The outcome goes to --status (JSON: result, model, message in Italian) and the
Italian summary to .autofix/summary.md. Keys never reach a file or the log.

    autofix-reserve.py --workdir DIR --prompt FILE --status FILE
                       [--checker FILE [--related FILE] [--allow-adblock]] [--refused FILE]
"""

import argparse
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

PROVIDERS = (
    # name, endpoint, key variable, models variable, default models (checked 2026-11-19),
    # characters of failure + code sent, tokens of the answer
    ("Groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
     "AUTOFIX_GROQ_MODELS", ("qwen/qwen3.8-27b", "openai/gpt-oss-120b"), 14_000, 2_000),
    ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY",
     "AUTOFIX_OPENROUTER_MODELS", ("cohere/north-mini-code:free", "particle-ai/particle-1:free"),
     120_000, 6_000),
)
ROOTS = ("ike/", "tests/", "tools/", "docs/")
# I.K.E.'s own wrapper of the ad blocker: only when the workflow says this run
# updates the engine (--allow-adblock, from tools/autofix-plan.py). The checker
# (tools/check-autofix-patch.py) stays the authority either way.
WRAPPER = ("ike-adblock/src/", "vendor/adblock/__init__.py")
SHOWN_ROOTS = ROOTS + WRAPPER          # may be shown, as context, even when not editable


def editable(path, allow_adblock):
    return path.startswith(ROOTS + WRAPPER if allow_adblock else ROOTS)


def _checker_rule():
    """allowed_path() of the checker next to this script (both come from main in
    the workflow): the reserves never edit what the checker would refuse, so
    the two lists of forbidden files cannot drift apart."""
    path = Path(__file__).resolve().parent / "check-autofix-patch.py"
    if not path.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_autofix_checker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.allowed_path
MAX_FILES = 5
TOTAL_TIMEOUT = 12 * 60
REQUEST_TIMEOUT = 150
FILES_BUDGET = 60_000          # characters of whole files sent along
MAX_TOKENS = 6000

MESSAGES = {
    "ok": "Una riserva (%s) ha preparato una correzione.",
    "none": "La riserva (%s) dice che il problema non si corregge nel codice, e nessun'altra l'ha corretto.",
    "quota": "Le riserve hanno esaurito la quota o non rispondono: riprova più tardi.",
    "nokey": "Nessuna riserva configurata: mancano le chiavi GROQ_API_KEY e OPENROUTER_API_KEY.",
    "error": "Le riserve non sono riuscite a preparare una correzione applicabile.",
    "refused": "La correzione della riserva (%s) è stata respinta dai controlli di sicurezza: "
               "nessun'altra riserva è stata interpellata.",
}

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
- At most 5 files, the smallest correct change. Only files that are shown
  below, and only under ike/, tests/, tools/ or docs/ (%(wrapper)s).
- Never ike-adblock/Cargo.toml or Cargo.lock, Brave's engine itself, Dark
  Reader's files, uBlock Origin's scriptlets, the icon sets, docs/THIRD-PARTY.md
  or any file that comes from others or is generated.
- If the failure cannot be fixed in the code, answer {"summary": "...",
  "fixable": false, "edits": []}.
"""


def instructions(allow_adblock):
    return INSTRUCTIONS % {"wrapper": (
        "this run updates the ad blocker's engine, so I.K.E.'s own wrapper may change "
        "too: ike-adblock/src/ and vendor/adblock/__init__.py" if allow_adblock else
        "not the ad blocker: ike-adblock/, vendor/, ike/blocker.py and ike/scriptlets.py "
        "may change only when the engine is being updated, and this run does not update it")}


class Stop(Exception):
    pass


def chain(env=os.environ):
    """[(provider, endpoint, key, model, budget, max_tokens)] in order; providers
    without a key left out."""
    out = []
    for name, url, key_var, models_var, default, budget, tokens in PROVIDERS:
        key = env.get(key_var, "").strip()
        if not key:
            continue
        models = [m.strip() for m in (env.get(models_var) or "").split(",") if m.strip()] or list(default)
        for m in models:
            out.append((name, url, key, m, budget, tokens))
    return out


def classify(status):
    if status == 413:
        return "toolarge"
    if status == 429:
        return "quota"
    if status in (401, 403):
        return "auth"
    if status in (400, 404, 422):
        return "config"
    return "temporary"


def ask(url, key, model, messages, timeout=REQUEST_TIMEOUT, opener=urllib.request.urlopen,
        max_tokens=MAX_TOKENS):
    """The model's answer text, or raises (kind, detail)."""
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.1,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "User-Agent": "IKE-autofix", "X-Title": "I.K.E. automatic fix"})
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read(4_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        wait = 0
        try:
            wait = int(float((e.headers or {}).get("Retry-After") or 0))
        except (TypeError, ValueError):
            wait = 0
        raise Stop(classify(e.code), "HTTP %d" % e.code, wait)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise Stop("temporary", type(e).__name__)
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise Stop("temporary", "no answer")
    if isinstance(content, list):          # content given in parts: their text
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict) and
                          isinstance(p.get("text"), str))
    return content if isinstance(content, str) else ""


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


def apply_edits(workdir, edits, shown, allow_adblock=False):
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
        if not editable(path, allow_adblock) or (not allow_adblock and path in ("ike/blocker.py",
                                                                              "ike/scriptlets.py")):
            raise ValueError("%s may not be changed in this run (the ad blocker only with an "
                             "update of its engine)" % path)
        rule = _checker_rule()
        why = rule(path, allow_adblock) if rule else ""
        if why:
            raise ValueError("%s may not be changed: %s" % (path, why))
        current = new.get(path)
        if current is None:
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
        if not path.startswith(SHOWN_ROOTS) or not p.is_file():
            continue
        text = p.read_text("utf-8", errors="replace")
        if used + len(text) > FILES_BUDGET:
            continue
        out[path] = text
        used += len(text)
    return out


def message_for(failure, context, shown, budget, refused=""):
    """The user message within the provider's budget (characters): the failure,
    the code at it, then whole files while they fit."""
    head = "# The failure\n\n%s\n\n" % failure[-max(2000, budget // 3):]
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


def diff_of(workdir):
    out = subprocess.run(["git", "-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null",
                          "-C", str(workdir), "diff", "--binary", "--", ".", ":(exclude).autofix"],
                         capture_output=True, text=True, check=False)
    return out.stdout


def undo(workdir, files):
    subprocess.run(["git", "-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null",
                    "-C", str(workdir), "checkout", "-q", "--", *files], check=False)


def checked(workdir, checker, related, allow_adblock):
    """(exit status, reasons) of the trusted checks on the work tree's changes."""
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(diff_of(workdir))
        patch = f.name
    cmd = [sys.executable, "-I", checker, "--repo", str(workdir), "--patch", patch, "--check-only"]
    if related:
        cmd += ["--related", related]
    if allow_adblock:
        cmd.append("--allow-adblock")
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


def one_model(url, key, model, base, tokens, deadline, opener, workdir, shown, a, refused, applied):
    """Ask one model, at most twice. Returns (outcome, text, refused): outcome is
    ok | none | refused | error | quota | auth | toolarge, text its summary (or
    the checker's reasons for "refused"), refused why the checks refused its
    fix (for the next model). The files it changed stay listed in `applied`
    until they are undone, so the caller can undo them after any error."""
    messages, tries, waited = list(base), 0, False
    while tries < 2:
        tries += 1
        try:
            answer = ask(url, key, model, messages, opener=opener, max_tokens=tokens)
        except Stop as s:
            kind = s.args[0]
            wait = s.args[2] if len(s.args) > 2 else 0
            print("  stopped: %s (%s)" % (kind, for_log(s.args[1])), flush=True)
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
            if kind in ("auth", "toolarge"):
                return kind, "", refused
            return ("quota" if kind in ("quota", "temporary") else "error"), "", refused
        try:
            obj = parse(answer)
            if obj.get("fixable") is False:
                return "none", str(obj.get("summary") or ""), refused
            if not obj.get("edits"):
                # 2026-11-19: a model named the cause and gave no edit; only an
                # explicit "fixable": false counts as "cannot be fixed"
                raise ValueError("the answer has no edits: give the exact edits of the fix, "
                                 "or \"fixable\": false if it cannot be fixed in the code")
            applied[:] = apply_edits(workdir, obj["edits"], shown, a.allow_adblock)
            summary = str(obj.get("summary") or "")
            print("  edits applied: %s" % for_log(", ".join(applied)), flush=True)
            if a.checker:
                status, reasons = checked(workdir, a.checker, a.related, a.allow_adblock)
                if status == 3:
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused for safety: no other model is asked", flush=True)
                    return "refused", reasons, refused
                if status in (1, 2):         # refused, or the edits changed nothing
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused by the checks: the next model is told why", flush=True)
                    return "error", summary, reasons
            if a.lint:
                clean, said = linted(workdir, applied)
                if not clean:
                    undo(workdir, applied)
                    applied.clear()
                    print("  refused by the lint: the next model is told why", flush=True)
                    return "error", summary, "The lint (ruff) refused the fix:\n\n" + said
            return "ok", summary, refused
        except (ValueError, OSError) as e:
            if applied:
                undo(workdir, applied)
                applied.clear()
            print("  answer not usable: %s" % for_log(e), flush=True)
            messages = base + [{"role": "assistant", "content": str(answer)[:20000]},
                               {"role": "user", "content": "That answer could not be applied: %s. "
                                "Answer again with one JSON object as described." % e}]
    return "error", "", refused


def main(argv=None, env=os.environ, opener=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--prompt", required=True, help="the agent's instructions (rules)")
    ap.add_argument("--status", required=True)
    ap.add_argument("--total-timeout", type=int, default=TOTAL_TIMEOUT)
    ap.add_argument("--checker", help="tools/check-autofix-patch.py from main: each fix is checked")
    ap.add_argument("--related", help="the files involved (for the checker)")
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--refused", help="why the checks refused Antigravity's fix")
    ap.add_argument("--lint", action="store_true", help="ruff on each fix (its safe fixes first)")
    a = ap.parse_args(argv)
    workdir = Path(a.workdir)
    auto = workdir / ".autofix"

    def read(name):
        try:
            return (auto / name).read_text("utf-8", "replace")
        except OSError:
            return ""
    failure, context = read("failure.md"), read("context.md")
    related = [line.strip() for line in read("related.txt").splitlines() if line.strip()]
    shown = files_shown(workdir, related)
    rules = Path(a.prompt).read_text("utf-8")
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
    plan = chain(env)
    for provider, url, key, model, budget, tokens in plan:
        if provider in skip:
            continue
        base = [{"role": "system", "content": rules + "\n" + instructions(a.allow_adblock)},
                {"role": "user", "content": message_for(failure, context, shown, budget, refused)}]
        if time.monotonic() > deadline:
            result = result if result != "nokey" else "quota"
            break
        used = "%s / %s" % (provider, model)
        print("Reserve: %s" % for_log(used), flush=True)
        applied = []
        try:
            outcome, said, refused = one_model(url, key, model, base, tokens, deadline, opener,
                                               workdir, shown, a, refused, applied)
        except Exception as e:                    # 1.1.18: a malformed answer never ends the chain
            if applied:
                undo(workdir, applied)
            print("  answer not usable (%s): the next model goes on" % type(e).__name__, flush=True)
            outcome, said = "error", ""
        if outcome in ("ok", "refused"):
            result, summary = outcome, said
            break
        if outcome == "none":
            # 1.1.18: one model's word is not enough (a weak free model gives up on
            # a plain fix); the chain stops when two different models agree
            said_none.append(used)
            none_summary = said
            if len(set(said_none)) >= 2:
                print("  two models say it cannot be fixed in the code: no other model is asked", flush=True)
                result = "none"
                break
            print("  says it cannot be fixed in the code: the next model is asked too", flush=True)
        if outcome in ("auth", "toolarge"):
            skip.add(provider)
            outcome = "error"
        result = outcome or "error"
    if result != "ok" and result != "refused" and said_none:
        # nobody fixed it, and at least one model said it cannot be fixed in the code
        result, used, summary = "none", said_none[-1], none_summary
    message = MESSAGES[result] % used if "%s" in MESSAGES[result] else MESSAGES[result]
    if result in ("ok", "none", "refused"):
        text = redact(summary.strip()[:3000], keys) or "La riserva non ha scritto un riassunto."
        (auto / "summary.md").write_text("%s\n\n_(%s)_\n" % (text, message), "utf-8")
    Path(a.status).write_text(json.dumps({"result": result, "model": used, "message": message},
                                         ensure_ascii=False), "utf-8")
    print("Reserves: %s (%s)" % (result, for_log(used or "none")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
