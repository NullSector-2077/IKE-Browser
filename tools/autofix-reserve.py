#!/usr/bin/env python3
"""The reserve assistants of the automatic fix (no AI here: this calls them).

When the Antigravity agent could not fix a failure (quota used up, Google not
answering, an error of the agent, or simply no fix), .github/workflows/autofix.yml
asks the reserves, one after the other, never together:

    1. Groq        (GROQ_API_KEY,       models in AUTOFIX_GROQ_MODELS)
    2. OpenRouter  (OPENROUTER_API_KEY, models in AUTOFIX_OPENROUTER_MODELS)

A provider without its key is skipped. Unlike Antigravity they cannot open
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
    an answer that cannot be applied     -> once more, told what was wrong, then the next model
    "no fix possible in the code"        -> stop: asking another model would not help

The outcome goes to --status (JSON: result, model, message in Italian) and the
Italian summary to .autofix/summary.md. Keys never reach a file or the log.

    autofix-reserve.py --workdir DIR --prompt FILE --status FILE
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVIDERS = (
    # name, endpoint, key variable, models variable, default models
    ("Groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
     "AUTOFIX_GROQ_MODELS", ("qwen/qwen3-32b",)),
    ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY",
     "AUTOFIX_OPENROUTER_MODELS", ("qwen/qwen3-coder:free",)),
)
ROOTS = ("ike/", "tests/", "tools/", "docs/")
MAX_FILES = 5
TOTAL_TIMEOUT = 12 * 60
REQUEST_TIMEOUT = 150
FILES_BUDGET = 60_000          # characters of whole files sent along
MAX_TOKENS = 6000

MESSAGES = {
    "ok": "Una riserva (%s) ha preparato una correzione.",
    "none": "La riserva (%s) dice che il problema non si corregge nel codice.",
    "quota": "Le riserve hanno esaurito la quota o non rispondono: riprova più tardi.",
    "nokey": "Nessuna riserva configurata: mancano le chiavi GROQ_API_KEY e OPENROUTER_API_KEY.",
    "error": "Le riserve non sono riuscite a preparare una correzione applicabile.",
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
- At most 5 files, the smallest correct change. Only files under ike/, tests/,
  tools/ or docs/ that are shown below.
- If the failure cannot be fixed in the code, answer {"summary": "...",
  "fixable": false, "edits": []}.
"""


class Stop(Exception):
    pass


def chain(env=os.environ):
    """[(provider, endpoint, key, model)] in order; providers without a key left out."""
    out = []
    for name, url, key_var, models_var, default in PROVIDERS:
        key = env.get(key_var, "").strip()
        if not key:
            continue
        models = [m.strip() for m in (env.get(models_var) or "").split(",") if m.strip()] or list(default)
        for m in models:
            out.append((name, url, key, m))
    return out


def classify(status):
    if status == 429:
        return "quota"
    if status in (401, 403):
        return "auth"
    if status in (400, 404, 422):
        return "config"
    return "temporary"


def ask(url, key, model, messages, timeout=REQUEST_TIMEOUT, opener=urllib.request.urlopen):
    """The model's answer text, or raises (kind, detail)."""
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.1,
                       "max_tokens": MAX_TOKENS}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "User-Agent": "IKE-autofix", "X-Title": "I.K.E. automatic fix"})
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read(4_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise Stop(classify(e.code), "HTTP %d" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise Stop("temporary", type(e).__name__)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise Stop("temporary", "no answer")


def parse(text):
    """The JSON object of an answer (code fences and reasoning around it tolerated)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict) or not isinstance(obj.get("edits", []), list):
        raise ValueError("the JSON object has no list of edits")
    return obj


def apply_edits(workdir, edits, shown):
    """Apply the edits (all or none). Returns the changed files; raises ValueError."""
    if len({e.get("file") for e in edits if isinstance(e, dict)}) > MAX_FILES:
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
        if ".." in Path(path).parts or not path.startswith(ROOTS) or path not in shown:
            raise ValueError("%s is not one of the files shown" % path)
        current = new.get(path)
        if current is None:
            current = (workdir / path).read_text("utf-8")
        count = current.count(find)
        if count != 1:
            raise ValueError("the text to replace appears %d times in %s (must be exactly once)"
                             % (count, path))
        new[path] = current.replace(find, repl, 1)
    for path, text in new.items():
        (workdir / path).write_text(text, "utf-8")
    return sorted(new)


def files_shown(workdir, related):
    """The full text of the files involved, within the budget: {path: text}."""
    out, used = {}, 0
    for path in related:
        p = workdir / path
        if not path.startswith(ROOTS) or not p.is_file():
            continue
        text = p.read_text("utf-8", errors="replace")
        if used + len(text) > FILES_BUDGET:
            continue
        out[path] = text
        used += len(text)
    return out


def redact(text, keys):
    for k in keys:
        if k:
            text = text.replace(k, "***")
    return text


def main(argv=None, env=os.environ, opener=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--prompt", required=True, help="the agent's instructions (rules)")
    ap.add_argument("--status", required=True)
    ap.add_argument("--total-timeout", type=int, default=TOTAL_TIMEOUT)
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
    files_text = "".join("\n## File `%s`\n\n```text\n%s\n```\n" % (p, t) for p, t in shown.items())
    user = ("# The failure\n\n%s\n\n%s\n\n# Files involved (full text)\n%s"
            % (failure[-30000:], context[:40000], files_text or "\n(none could be sent)\n"))
    base = [{"role": "system", "content": rules + "\n" + INSTRUCTIONS},
            {"role": "user", "content": user}]
    result, used, summary = "nokey", "", ""
    skip, deadline = set(), time.monotonic() + a.total_timeout
    plan = chain(env)
    for provider, url, key, model in plan:
        if provider in skip:
            continue
        if time.monotonic() > deadline:
            result = result if result != "nokey" else "quota"
            break
        used = "%s / %s" % (provider, model)
        print("Reserve: %s" % used, flush=True)
        messages, tries, outcome = list(base), 0, None
        while tries < 2 and outcome is None:
            tries += 1
            try:
                answer = ask(url, key, model, messages, opener=opener)
            except Stop as s:
                kind = s.args[0]
                print("  stopped: %s (%s)" % (kind, s.args[1]), flush=True)
                if kind == "temporary" and tries < 2:
                    time.sleep(10)
                    continue
                if kind == "auth":
                    skip.add(provider)
                outcome = "quota" if kind in ("quota", "temporary") else "error"
                break
            try:
                obj = parse(answer)
                if obj.get("fixable") is False or not obj.get("edits"):
                    summary = str(obj.get("summary") or "")
                    outcome = "none"
                    break
                changed = apply_edits(workdir, obj["edits"], shown)
                summary = str(obj.get("summary") or "")
                print("  edits applied: %s" % ", ".join(changed), flush=True)
                outcome = "ok"
            except (ValueError, OSError) as e:
                print("  answer not usable: %s" % e, flush=True)
                messages = base + [{"role": "assistant", "content": answer[:20000]},
                                   {"role": "user", "content": "That answer could not be applied: %s. "
                                    "Answer again with one JSON object as described." % e}]
        if outcome in ("ok", "none"):
            result = outcome
            break
        result = outcome or "error"
    message = MESSAGES[result] % used if "%s" in MESSAGES[result] else MESSAGES[result]
    if result in ("ok", "none"):
        text = redact(summary.strip()[:3000], keys) or "La riserva non ha scritto un riassunto."
        (auto / "summary.md").write_text("%s\n\n_(%s)_\n" % (text, message), "utf-8")
    Path(a.status).write_text(json.dumps({"result": result, "model": used, "message": message},
                                         ensure_ascii=False), "utf-8")
    print("Reserves: %s (%s)" % (result, used or "none"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
