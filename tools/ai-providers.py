#!/usr/bin/env python3
"""The AI providers of the automatic maintenance: their order and limits, in one place.

Only free providers (the owner's decision of 2026-11-22: no billing on Gemini,
Groq, Z.AI, OpenRouter or Antigravity), no local inference. This file is read,
never run, by:

- tools/autofix-agent.py      the Antigravity agent (Gemini), always first: it
                              runs in its own closed room (autofix.yml);
- tools/autofix-reserve.py    the reserves, asked one after the other in the
                              order of RESERVES below;
- tools/provider-check.py     the weekly check (health.yml): every configured
                              provider answers a tiny question, and is free;
- tools/ai-work.py            work that found no free provider waits
                              (retry-later) and is tried again by the daily
                              check, at most RETRY_CAP times.

To change the order of the reserves, a default model, a time limit or the
retry cap, change it here (a person's change: the automatic fix's guard
refuses this file, tools/check-autofix-patch.py). The models can also be set
without a change of code, in the repository variables named below
(AUTOFIX_MODEL, AUTOFIX_GROQ_MODELS, AUTOFIX_ZAI_MODELS,
AUTOFIX_OPENROUTER_MODELS; names separated by commas, in order).
"""

# Antigravity (the `agy` CLI with GEMINI_API_KEY): the first to work on a fix.
# AUTOFIX_MODEL comes first, then these free models. The same names serve the Gemini
# API (the reviewers, the weekly check: "Gemini 4 Hydrogen (High)" is gemini-4-hydrogen).
# Read on 2026-11-25 on the providers' own pages: Gemini 4 Hydrogen is the free default
# of Antigravity and the only Gemini that stays on its free plan after 2026-11-30
# (antigravity.google/docs/plans: "Gemini 3.8 Flash until November 30, 2026"); on the
# Gemini API all four are on the free tier (ai.google.dev/gemini-api/docs/pricing; 3.7
# Flash now routes to 3.8 Flash). A model that is no longer offered gives way to the
# next one (tools/autofix-agent.py MODEL_GONE).
GEMINI_MODELS = ("Gemini 4 Hydrogen (High)", "Gemini 3.8 Flash (High)", "Gemini 3.6 Flash (High)",
                 "Gemini 3.5 Flash Lite (High)")
GEMINI_KEY = "GEMINI_API_KEY"
GEMINI_MODELS_VAR = "AUTOFIX_MODEL"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
MODEL_TIMEOUT = 8 * 60          # seconds for one Gemini model (wall clock)
TOTAL_TIMEOUT = 25 * 60         # seconds for all Gemini models together

# The reserves, in the order they are asked (never together). Each: name,
# endpoint (OpenAI-compatible), key secret, models variable, default models
# (checked 2026-11-19), characters of failure + code sent, tokens of the answer.
RESERVES = (
    # Groq's free plan: 30 requests and 8,000 tokens a minute, 1,000 requests and 200,000
    # tokens a day for each of these models (console.groq.com/docs/rate-limits, read on
    # 2026-11-25): a short message and a modest answer. gpt-oss-120b and -20b are
    # production models; qwen3.8-27b is a preview that "may be discontinued at short
    # notice" (console.groq.com/docs/models)
    ("Groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
     "AUTOFIX_GROQ_MODELS", ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"), 14_000, 2_000),
    # 1.1.19, the owner's choice: Z.AI's free GLM Flash models (docs.z.ai/guides/overview/
    # pricing, read on 2026-11-25: GLM-4.7-Flash and GLM-4.5-Flash "Free"; the general endpoint)
    ("Z.AI", "https://api.z.ai/api/paas/v4/chat/completions", "ZAI_API_KEY",
     "AUTOFIX_ZAI_MODELS", ("glm-4.7-flash", "glm-4.5-flash"), 60_000, 6_000),
    # OpenRouter's free models come and go (cohere/north-mini-code:free, openai/gpt-oss-120b:free
    # and qwen/qwen3-coder:free are gone): these were in GET /api/v1/models at zero price on
    # 2026-11-25, and each run rebuilds the list from it (tools/autofix-reserve.py refreshed)
    ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY",
     "AUTOFIX_OPENROUTER_MODELS", ("particle-ai/particle-1:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
                                   "inclusionai/ling-3.2-flash:free", "google/gemma-4-31b-it:free"),
     120_000, 6_000),
)
RESERVES_TIMEOUT = 12 * 60      # seconds for all reserves together

# OpenRouter sells most models: only its ":free" variants may be used. A model
# without the suffix, also one set in AUTOFIX_OPENROUTER_MODELS, is refused
# (tools/autofix-reserve.py chain(), tools/provider-check.py), and the weekly
# check also asks OpenRouter's own price list and key (a name alone proves
# nothing).
FREE_SUFFIX = {"OpenRouter": ":free"}
# OpenRouter's Free Models Router "falls back only to other free models"
# (openrouter.ai/docs/guides/routing/model-variants/free). It picks a free model at random,
# so a fix is not reproducible: only the last resort, and only when the run's own listing of
# OpenRouter's models shows it at zero price (tools/autofix-reserve.py refreshed)
FREE_ROUTER = "openrouter/free"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEY_INFO = "https://openrouter.ai/api/v1/key"

# Work that found no free provider at all (every one busy, out of quota, or
# unavailable): it stays in the maintenance ledger as "retry-later", with its
# branch and its attempts, and the daily check starts it again after
# RETRY_HOURS. After RETRY_CAP such tries it waits for the owner, who is told
# once (tools/ai-work.py).
RETRY_HOURS = 24
RETRY_CAP = 5

# Fixes of one failure (the owner's decision of 2026-11-22: "more attempts and other free
# providers if needed"). Each attempt is a new run of the automatic fix with a fresh context:
# only the earlier fix, the new test logs and its summary go in, as data; the tests run again
# after each (Tests, Security, Arch Linux on the branch). On the isolated candidates of the full
# chain (automation/update/<id>, automation/builder/<id>, automation/update/arch-testing-<date>)
# attempt n starts with the n-th provider of all_names(), round robin, so after a fix that did
# not pass another free provider and model family tries first; at FIX_ATTEMPTS the branch is
# kept, the maintenance ledger says needs-person and the owner is told once. On main, the
# automatic fix's branch, the daily candidate and the security branches FIX_ATTEMPTS_MAIN
# (tools/autofix-plan.py MAX_ATTEMPTS), Antigravity first each time.
FIX_ATTEMPTS = 4
FIX_ATTEMPTS_MAIN = 2


def first_provider(attempt):
    """The provider attempt n (1, 2, ...) of an isolated candidate starts with."""
    names = all_names()
    return names[(max(1, int(attempt)) - 1) % len(names)]


def reserve_names():
    return tuple(r[0] for r in RESERVES)


def all_names():
    """Every provider, in the order a fix asks them."""
    return ("Antigravity",) + reserve_names()


def is_free_model(provider, model):
    """False for a model the provider would charge for, by the rule above
    (a name: the weekly check verifies the price too)."""
    suffix = FREE_SUFFIX.get(provider)
    if provider == "OpenRouter" and model == FREE_ROUTER:
        return True
    return bool(model) and (not suffix or model.endswith(suffix))


# The providers' new free models, found each week by tools/provider-check.py (discover) and passed to the automatic
# fix as AUTOFIX_DISCOVERED ("Provider:model|model;Provider:model"): asked after the configured models, so a model
# a provider adds (a new Gemini, a new Groq model) is used without a change here, and one it retires costs one
# failed request. AUTOMAT block 2, 2026-11-27.
DISCOVERED_VAR = "AUTOFIX_DISCOVERED"
_SAFE_ID = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,80}$")


def discovered(env=None, provider=None):
    """{provider: [model ids]} of AUTOFIX_DISCOVERED (or one provider's list); anything else ignored."""
    import os
    text = (env if env is not None else os.environ).get(DISCOVERED_VAR) or ""
    out = {}
    for part in str(text).split(";"):
        name, _, models = part.partition(":")
        if name in all_names() and name not in FREE_SUFFIX:
            ok = [m for m in models.split("|") if _SAFE_ID.match(m)][:4]
            if ok:
                out[name] = ok
    return out.get(provider, []) if provider else out


def gemini_cli_name(model_id):
    """The Antigravity CLI's name of a Gemini API id: "gemini-4-neon" -> "Gemini 4 Neon (High)"."""
    words = str(model_id).split("-")
    return " ".join(w if w[:1].isdigit() else w.capitalize() for w in words) + " (High)"
