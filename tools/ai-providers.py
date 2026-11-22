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
# AUTOFIX_MODEL comes first, then these free Flash models.
GEMINI_MODELS = ("Gemini 3.8 Flash (High)", "Gemini 3.7 Flash (High)", "Gemini 3.6 Flash (High)")
GEMINI_KEY = "GEMINI_API_KEY"
GEMINI_MODELS_VAR = "AUTOFIX_MODEL"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
MODEL_TIMEOUT = 8 * 60          # seconds for one Gemini model (wall clock)
TOTAL_TIMEOUT = 25 * 60         # seconds for all Gemini models together

# The reserves, in the order they are asked (never together). Each: name,
# endpoint (OpenAI-compatible), key secret, models variable, default models
# (checked 2026-11-19), characters of failure + code sent, tokens of the answer.
RESERVES = (
    # Groq's free plan takes about 8,000 tokens a minute: a short message
    ("Groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
     "AUTOFIX_GROQ_MODELS", ("qwen/qwen3.8-27b", "openai/gpt-oss-120b"), 14_000, 2_000),
    # 1.1.19, the owner's choice: Z.AI's free GLM Flash models
    ("Z.AI", "https://api.z.ai/api/paas/v4/chat/completions", "ZAI_API_KEY",
     "AUTOFIX_ZAI_MODELS", ("glm-4.7-flash", "glm-4.5-flash"), 60_000, 6_000),
    ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY",
     "AUTOFIX_OPENROUTER_MODELS", ("cohere/north-mini-code:free", "particle-ai/particle-1:free"),
     120_000, 6_000),
)
RESERVES_TIMEOUT = 12 * 60      # seconds for all reserves together

# OpenRouter sells most models: only its ":free" variants may be used. A model
# without the suffix, also one set in AUTOFIX_OPENROUTER_MODELS, is refused
# (tools/autofix-reserve.py chain(), tools/provider-check.py), and the weekly
# check also asks OpenRouter's own price list and key (a name alone proves
# nothing).
FREE_SUFFIX = {"OpenRouter": ":free"}
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
OPENROUTER_KEY_INFO = "https://openrouter.ai/api/v1/key"

# Work that found no free provider at all (every one busy, out of quota, or
# unavailable): it stays in the maintenance ledger as "retry-later", with its
# branch and its attempts, and the daily check starts it again after
# RETRY_HOURS. After RETRY_CAP such tries it waits for the owner, who is told
# once (tools/ai-work.py).
RETRY_HOURS = 24
RETRY_CAP = 5


def reserve_names():
    return tuple(r[0] for r in RESERVES)


def all_names():
    """Every provider, in the order a fix asks them."""
    return ("Antigravity",) + reserve_names()


def is_free_model(provider, model):
    """False for a model the provider would charge for, by the rule above
    (a name: the weekly check verifies the price too)."""
    suffix = FREE_SUFFIX.get(provider)
    return bool(model) and (not suffix or model.endswith(suffix))
