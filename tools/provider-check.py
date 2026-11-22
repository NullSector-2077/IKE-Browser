#!/usr/bin/env python3
"""Every configured AI provider answers, and is free (WP9; no AI here).

Run weekly by .github/workflows/health.yml, with the providers' keys in that
one step only. For each provider that has a key (tools/ai-providers.py: the
Gemini API of Antigravity, then the reserves Groq, Z.AI and OpenRouter):

- the endpoint and the first configured model answer one tiny request
  ("Answer with the word OK.", at most 16 tokens);
- OpenRouter: every configured model must be a ":free" variant (a model
  without the suffix is refused and never asked, also one set in
  AUTOFIX_OPENROUTER_MODELS); its own price list (/api/v1/models) must give
  each one a price of zero, and its key (/api/v1/key) must be on the free tier
  with nothing spent. A name alone proves nothing;
- any answer that reports a cost, a paid tier or a billing error (HTTP 402,
  "payment required", "insufficient balance", Z.AI's code 1113, Gemini's
  BILLING_DISABLED...) marks the provider **unavailable**: the automatic fix
  does not ask it (autofix.yml passes AUTOFIX_UNAVAILABLE to the agent and the
  reserves) and the owner is told (the "Automation health" issue).

Groq, Z.AI and Gemini do not say by API whether an account could be charged:
for them "free" rests on the owner's word (no billing on those accounts,
2026-11-22) and is shown as "not provable by API", never as proven.

Keys never leave this file: the output holds provider, model, state and a
reason chosen here (never the text of an answer).

    provider-check.py check OUT.json [--markdown FILE]
    provider-check.py unavailable --repo OWNER/NAME     (the plan of autofix.yml:
        the providers the last weekly check marked unavailable, from its
        artifact "ai-providers", GET calls only; prints "a,b" or nothing)
"""

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ARTIFACT = "ai-providers"
HEALTH = "health.yml"
STATES = ("available", "unavailable", "failing", "busy", "unverified")
FREE_NOT_PROVABLE = "not provable by API: rests on the owner's account without billing"


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                  Path(__file__).resolve().parent / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REGISTRY = _tool("ai-providers")
RESERVE = _tool("autofix-reserve")      # the same request, the same reading of answers and errors


def _request(url, key, opener, data=None, header="Authorization", timeout=60):
    """(status, parsed JSON or None, body text). Never raises for an HTTP error."""
    headers = {"User-Agent": "IKE-provider-check", "Content-Type": "application/json"}
    headers[header] = ("Bearer " + key) if header == "Authorization" else key
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 method="POST" if data is not None else "GET", headers=headers)
    try:
        with opener(req, timeout=timeout) as r:
            text = r.read(8_000_000).decode("utf-8", "replace")
            status = getattr(r, "status", 200) or 200
    except urllib.error.HTTPError as e:
        try:
            text = e.read(20_000).decode("utf-8", "replace") if e.fp is not None else ""
        except Exception:
            text = ""
        status = e.code
    except Exception as e:                  # no answer at all
        return 0, None, type(e).__name__
    try:
        return status, json.loads(text), text
    except ValueError:
        return status, None, text


def _verdict(status, data, text):
    """(state, reason) of one tiny request's answer."""
    if status == 402 or RESERVE.billing_in(text):
        return "unavailable", "a billing error or a paid tier in the answer (HTTP %s)" % status
    if status == 200 and RESERVE.cost_of(data) > 0:
        return "unavailable", "the answer reports a cost"
    if status == 200:
        return "available", "answered"
    if status in (401, 403):
        return "failing", "the key was refused (HTTP %d): make a new one and put it in the secret" % status
    if status in (400, 404, 422):
        return "failing", "the model is unknown there (HTTP %d): set the variable of its models" % status
    if status == 429:
        return "busy", "rate limit or quota of today (HTTP 429): not a fault"
    return "busy", "no answer now (%s): not a fault" % (status or text)


def tiny(url, key, model, opener):
    body = {"model": model, "messages": [{"role": "user", "content": "Answer with the word OK."}],
            "temperature": 0, "max_tokens": 16}
    return _verdict(*_request(url, key, opener, body))


def gemini_id(model):
    """The Gemini API's id of a model the CLI names "Gemini 3.8 Flash (High)":
    "gemini-3.8-flash" (the effort in brackets is the CLI's)."""
    name = model.split("(")[0].strip().lower()
    return "-".join(name.split())


def check_gemini(key, env, opener):
    configured = [m.strip() for m in (env.get(REGISTRY.GEMINI_MODELS_VAR) or "").split(",") if m.strip()]
    model = (configured or list(REGISTRY.GEMINI_MODELS))[0]
    row = {"provider": "Antigravity", "model": model, "free": FREE_NOT_PROVABLE}
    status, data, text = _request(REGISTRY.GEMINI_API + "/models?pageSize=1000", key, opener,
                                  header="x-goog-api-key")
    if status != 200:
        state, reason = _verdict(status, data, text)
        return [dict(row, state=state, reason="the Gemini API's list of models: " + reason)]
    listed = {str(m.get("name", "")).split("/", 1)[-1] for m in (data or {}).get("models", []) if isinstance(m, dict)}
    api = gemini_id(model)
    if api not in listed:
        flash = sorted(m for m in listed if "flash" in m)
        if not flash:
            return [dict(row, state="unverified", reason="the key works, but no Flash model is listed")]
        api = flash[-1]
        row["reason_model"] = "the CLI's name has no id of the same form in the list: %s asked instead" % api
    status, data, text = _request("%s/models/%s:generateContent" % (REGISTRY.GEMINI_API, api), key, opener,
                                  {"contents": [{"parts": [{"text": "Answer with the word OK."}]}],
                                   "generationConfig": {"maxOutputTokens": 16}}, header="x-goog-api-key")
    state, reason = _verdict(status, data, text)
    if status == 429 and "FreeTier" in text:
        row["free"] = "proven: the quota that ran out is the free tier's"
    return [dict(row, state=state, reason=reason)]


def check_openrouter(name, url, key, models, opener):
    rows, free = [], []
    for m in models:
        if REGISTRY.is_free_model(name, m):
            free.append(m)
        else:
            rows.append({"provider": name, "model": m, "state": "unavailable", "free": "no",
                         "reason": "not a :free model: refused, never asked (a variant without :free is paid)"})
    if not free:
        return rows
    status, data, text = _request(REGISTRY.OPENROUTER_MODELS, key, opener)
    prices = {}
    if status == 200 and isinstance(data, dict) and isinstance(data.get("data"), list):
        prices = {m.get("id"): m for m in data["data"] if isinstance(m, dict)}
    usable = []
    for m in free:
        if prices and m not in prices:
            rows.append({"provider": name, "model": m, "state": "failing", "free": "unknown",
                         "reason": "no longer listed by OpenRouter (the chain asks other :free models)"})
        elif prices and not RESERVE.priced_free(prices[m]):
            rows.append({"provider": name, "model": m, "state": "unavailable", "free": "no",
                         "reason": "OpenRouter's price list gives it a price above zero"})
        else:
            usable.append(m)
    account = "not read"
    status, data, text = _request(REGISTRY.OPENROUTER_KEY_INFO, key, opener)
    info = data.get("data") if isinstance(data, dict) else None
    paid = ""
    if status == 200 and isinstance(info, dict):
        if info.get("is_free_tier") is False:
            paid = "the key's account has bought credits (not the free tier)"
        elif _number(info.get("usage")) > 0:
            paid = "the key reports money spent (usage above zero)"
        elif info.get("is_free_tier") is True:
            account = "free tier, nothing spent"
    elif status in (401, 403):
        return rows + [{"provider": name, "model": usable[0] if usable else free[0], "state": "failing",
                        "free": "unknown", "reason": "the key was refused (HTTP %d)" % status}]
    if paid:
        return rows + [{"provider": name, "model": m, "state": "unavailable", "free": "no", "reason": paid}
                       for m in usable]
    if not usable:
        return rows
    state, reason = tiny(url, key, usable[0], opener)
    proof = "proven: :free, priced 0 by OpenRouter, account %s" % account if prices else \
        "by name only (:free): OpenRouter's price list could not be read"
    rows.append({"provider": name, "model": usable[0], "state": state, "reason": reason,
                 "free": proof if state != "unavailable" else "no"})
    return rows


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def check(env=os.environ, opener=urllib.request.urlopen):
    """[{provider, model, state, reason, free}] for each provider with a key."""
    rows = []
    key = (env.get(REGISTRY.GEMINI_KEY) or "").strip()
    if key:
        rows += check_gemini(key, env, opener)
    for name, url, key_var, models_var, default, _budget, _tokens in REGISTRY.RESERVES:
        key = (env.get(key_var) or "").strip()
        if not key:
            continue
        models = [m.strip() for m in (env.get(models_var) or "").split(",") if m.strip()] or list(default)
        if name in REGISTRY.FREE_SUFFIX:
            rows += check_openrouter(name, url, key, models, opener)
            continue
        state, reason = tiny(url, key, models[0], opener)
        rows.append({"provider": name, "model": models[0], "state": state, "reason": reason,
                     "free": FREE_NOT_PROVABLE if state != "unavailable" else "no"})
    keys = [(env.get(k) or "").strip() for k in [REGISTRY.GEMINI_KEY] + [r[2] for r in REGISTRY.RESERVES]]
    for row in rows:                        # nothing of a key, ever
        for k in keys:
            if k:
                for field in ("reason", "model", "free"):
                    row[field] = str(row.get(field, "")).replace(k, "***")
    return rows


def unavailable_of(rows):
    """Providers to skip: one whose every checked model is unavailable (a
    provider with one paid model in the variable and one free model that
    answered stays: the paid one is refused by name anyway)."""
    out = []
    for name in REGISTRY.all_names():
        mine = [r for r in rows if r["provider"] == name]
        if mine and all(r["state"] == "unavailable" for r in mine):
            out.append(name)
    return out


def summary(rows, when=None):
    return {"checked": (when or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "providers": rows, "unavailable": unavailable_of(rows)}


def markdown(info):
    out = ["### The AI providers (weekly check, tools/provider-check.py)", ""]
    if not info["providers"]:
        out.append("No provider has a key: the automatic fix cannot ask anyone.")
        return "\n".join(out) + "\n"
    out += ["| Provider | Model | State | Free | Why |", "|---|---|---|---|---|"]
    for r in info["providers"]:
        out.append("| %s | `%s` | %s | %s | %s |" % (r["provider"], r["model"], r["state"], r.get("free", ""),
                                                   r["reason"]))
    if info["unavailable"]:
        out += ["", "**Not used by the automatic fix until the next weekly check:** %s." % ", ".join(
            info["unavailable"])]
    return "\n".join(out) + "\n"


# --- for the plan of autofix.yml -------------------------------------------------------------

def gh_api(path, raw=False):
    out = subprocess.run(["gh", "api", path], capture_output=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.decode("utf-8", "replace").strip()[:200]))
    return out.stdout if raw else json.loads(out.stdout)


def last_unavailable(repo, api=gh_api):
    """The providers the newest weekly check (with its artifact) marked
    unavailable. Nothing when it cannot be read: the runtime checks of each
    answer (a billing error, a cost) still skip a provider that is not free."""
    runs = api("repos/%s/actions/workflows/%s/runs?per_page=10&status=completed" % (repo, HEALTH))
    for run in runs.get("workflow_runs", []):
        arts = api("repos/%s/actions/runs/%s/artifacts?name=%s" % (repo, run["id"], ARTIFACT)).get("artifacts", [])
        for art in arts:
            if art.get("expired"):
                continue
            data = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                info = json.loads(z.read("ai-providers.json").decode("utf-8"))
            names = [n for n in info.get("unavailable", []) if n in REGISTRY.all_names()]
            return names
    return []


def main(argv=None, env=os.environ, opener=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("out")
    c.add_argument("--markdown")
    u = sub.add_parser("unavailable")
    u.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    a = ap.parse_args(argv)
    if a.cmd == "unavailable":
        try:
            names = last_unavailable(a.repo)
        except Exception as e:
            print("::warning::the last weekly check of the providers could not be read: %s"
                  % str(e)[:200].replace("::", ": "), file=sys.stderr)
            names = []
        print(",".join(names))
        return 0
    info = summary(check(env, opener))
    Path(a.out).write_text(json.dumps(info, indent=1) + "\n", "utf-8")
    md = markdown(info)
    if a.markdown:
        Path(a.markdown).write_text(md, "utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
