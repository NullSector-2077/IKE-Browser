# Free-tier usage of AI providers from an automated CI job (AUTOMAT)

Research date: 2026-11-25 (all "read" dates below are 2026-11-25 unless stated).

## UPDATE 2026-11-25 (second pass): primary pages read directly

The hosts were allowed later the same day and every primary page below was
downloaded with `curl -sL` into `providers/pages/` and read. **Section 0
supersedes sections 1-4 wherever they differ**; sections 1-4 are kept as the
first-pass record. In `limits.json`, `"verified": true` now means "read on the
primary page today", with the URL.

## How this was researched (first pass), and how much to trust it

- **WebFetch could not reach any provider host** in this session: `ai.google.dev`
  and `console.groq.com` both failed with `getaddrinfo ENOTFOUND` (the session's
  network allow-list). Following the tool's instruction, no further hosts were
  tried with WebFetch. To read the pages directly, these hosts must be allowed in
  the session's network settings: `ai.google.dev`, `aistudio.google.com`,
  `antigravity.google`, `console.groq.com`, `docs.z.ai`, `api.z.ai`,
  `open.bigmodel.cn`, `openrouter.ai`.
- **WebSearch worked.** It returns the official page URL plus a search-engine
  summary of fragments of that page. Facts marked **[official, via search
  excerpt]** come from that: the URL is the provider's own page, but the page
  text was not read in full by me and the summary could be imprecise. Treat
  numbers marked this way as "probably right, confirm on the page".
- **`git clone` of public GitHub repositories worked.** Facts marked
  **[official code]** were read directly in the provider's own open-source code
  (exact commit given). These are the strongest facts in this report.
- **[not verified]** = only third-party sources, forum posts, or the search
  summary hedged/conflicted.

---

## 0. Verified from primary pages (2026-11-25, second pass)

Saved copies: `/tmp/claude-0/-home-user-ike-browser/b1a7534b-02d9-5057-a876-15a2180bd86a/scratchpad/providers/pages/`.

### 0.1 Gemini API

Pages: https://ai.google.dev/gemini-api/docs/rate-limits (`.md.txt`),
https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/models/<id>,
https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations,
https://ai.google.dev/gemini-api/docs/changelog, https://ai.google.dev/gemini-api/docs/troubleshooting,
https://aistudio.google.com/docs/api-errors.md?generate-content=true,
https://ai.google.dev/gemini-api/docs/api-errors (Interactions API), https://ai.google.dev/gemini-api/terms.

**Free-tier text models** (pricing page, "Free Tier" column says "Free of charge"
for input and output; limits from each model page):

| API model code | Free tier | Input / output tokens | Status (deprecations page) |
|---|---|---|---|
| `gemini-4-hydrogen` | yes (GA 2026-11-12, "Available on the free tier", changelog) | unified 1,048,576 context; max output 65,536 sync (up to 1,048,576 with long decode) | no shutdown date announced |
| `gemini-3.8-flash` | yes | 1,048,576 / 65,536 | released 2026-09-02, no shutdown date announced |
| `gemini-3.6-flash` | yes | 1,048,576 / 65,536 | no shutdown date announced |
| `gemini-3.5-flash-lite` | yes | 1,048,576 / 65,536 | no shutdown date announced |
| `gemini-3.1-flash-lite` | yes | 1,048,576 / 65,536 | **earliest shutdown 2027-05-07**, replacement `gemini-3.5-flash-lite` |
| `gemini-3-flash-preview` | yes (preview) | 1,048,576 / 65,536 | preview; no shutdown date announced, replacement `gemini-3.6-flash` |
| `gemini-2.5-flash-lite` | yes | 1,048,576 / 65,536 | not deprecated, but **API access limited to users who used it before** |
| `gemini-2.5-flash`, `gemini-2.5-pro` | listed free, but **deprecated**; existing users only; **from 2026-12-01 auto-routed** to `gemini-3.5-flash-lite` / `gemini-3.8-flash` | | |
| `gemini-4-carbon`, `gemini-4-argon`, `gemini-4-neon`, `gemini-3.1-pro-preview` | **Not available** on the Free tier | | |
| `gemini-3.7-flash`, `gemini-3.5-flash` | endpoints route automatically to `gemini-3.8-flash` / `gemini-3.6-flash` | | |

Note: the AI Studio docs index (https://aistudio.google.com/llms.txt) now calls
`generateContent` a **legacy API** ("still supported for existing
integrations"); the Interactions API (`/v1beta/interactions`) is the default.

**Limits (rate-limits page, verbatim):**
- Dimensions RPM, TPM (input), RPD; "exceeding any of them will trigger a rate
  limit error". "**Rate limits are applied per project, not per API key.
  Requests per day (RPD) quotas reset at midnight Pacific time.**"
- "Other models might have a token per day limit (TPD)." "Rate limits are more
  restricted for experimental and preview models."
- **No per-model free-tier RPM/RPD/TPM numbers are published** for the text
  models: "Rate limits depend on a variety of factors (such as your usage tier)
  and can be viewed in Google AI Studio" (https://aistudio.google.com/rate-limit).
  "Specified rate limits are not guaranteed and actual capacity may vary."
  (The page publishes tables only for Omni Flash, Genie 4 - both "Not
  supported" on Free - and Gemini Decision 1.)
- Spend-based limits (rolling 10 minutes): Free tier "N/A".
- Free tier qualification: "Active project or free trial; some projects need
  verification". Troubleshooting: "Not all Google Cloud projects or accounts
  are eligible for the Gemini API free tier ... **Creating a new API key in the
  same project won't resolve the error**" (eligibility is per project).

**Errors (generateContent, https://aistudio.google.com/docs/api-errors.md?generate-content=true):**
- 429 `RESOURCE_EXHAUSTED`: "You've exceeded one of the API's rate limits
  (RPM, TPM, RPD, spend, etc.)" -> "Wait and retry after a short period."
- 400 `FAILED_PRECONDITION`: "Gemini API free tier is not available in your
  country" (terminal).
- 402 `RESOURCE_EXHAUSTED`: Prepay credits depleted - "Don't retry".
- 403 `PERMISSION_DENIED`: wrong/blocked/leaked key, project restricted or
  ineligible for free tier (terminal).
- 500 `INTERNAL`: "Your input context is too long" -> reduce input or switch model.
- 503 `UNAVAILABLE`: "temporarily running out of capacity" -> switch model or wait.
- 504 `DEADLINE_EXCEEDED`: prompt too large to finish -> larger client timeout.
- Body: `{"error": {"code", "message", "status", "details": [...]}}` (gRPC details).
- **The docs do not list the `QuotaFailure.quotaId` strings.** They remain
  verified only from Google's own gemini-cli code and test fixture
  (`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`; rule "`PerDay` /
  `Daily` in quotaId = daily"). The daily string
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier` is **still not verified**
  from Google text.
- **Interactions API** (new, https://ai.google.dev/gemini-api/docs/api-errors)
  distinguishes the two cases with string codes: `rate_limit_exceeded` (429,
  "per-minute or per-second request or token limit" -> backoff),
  `quota_exceeded` (429, "exceeded your daily quota" -> "Wait until the quota
  resets"), `too_many_requests` (429, short burst), `service_unavailable` (503),
  `payment_required` (402, don't retry). If AUTOMAT moves to the Interactions
  API, branch on `error.code`.

**Retry (troubleshooting page):** exponential backoff ("1 second, then 2s, 4s,
8s"), jitter, retry only 429/408/5xx, never 400/402/403, cap attempts. "The
Python SDK automatically retries transient errors up to four times with an
initial delay of approximately 1 second and a maximum delay of 60 seconds."

**Deprecation policy (deprecations page):** "Deprecation announcements are made
on the Release notes page"; table dates are "the earliest possible dates";
"We will communicate the exact shutdown date to users with advance notice". No
fixed notice period.

**Terms (https://ai.google.dev/gemini-api/terms, read today):**
- Unpaid Services: prompts/responses used to improve products; "human reviewers
  may read, annotate, and process your API input and output"; "Do not submit
  sensitive, confidential, or personal information to the Unpaid Services."
  Pricing page per model: "Used to improve our products: Yes" on Free Tier.
- "If you're in the European Economic Area, Switzerland, or the United Kingdom,
  the terms under 'How Google uses Your Data' in 'Paid Services' apply to all
  Services, including Google AI Studio and unpaid quota in the Gemini API".
- "**You may use only Paid Services when making API Clients available to users
  in the European Economic Area, Switzerland, or the United Kingdom.**" (AUTOMAT
  is an internal CI tool, not an API client offered to users; flag for the
  owner, not a blocker.)
- Use is "for professional or business purposes, not for consumer use"; 18+;
  only from an available region.

### 0.2 Antigravity

Pages: https://antigravity.google/pricing/, https://antigravity.google/docs/plans/,
https://antigravity.google/docs/models/, https://antigravity.google/docs/cli/commands/usage/.

- **Free plan ("For Individuals", $0/month): "Baseline agent quota refreshed
  weekly"**; plans page: "A meaningful quota, refreshed weekly", "A weekly rate
  limit", "Access to Gemini 4 Hydrogen (and Gemini 3.8 Flash until November 30,
  2026)". **No numbers published**: "rate limits correlate with the amount of
  work done by the agent"; "Usage limits for this service are subject to
  modification." Free trials "may receive lower quota entitlements".
- **Leaving on 2026-11-30** (pricing footnote 4 and models page: "Gemini 4
  Argon, Gemini 3.8 Flash, GPT-OSS-120b, and Claude 4.6 models are leaving on
  November 30, 2026"). On the Free plan that removes **Gemini 3.8 Flash,
  Claude Sonnet 4.6 (thinking), Claude Opus 4.6 (thinking), GPT-OSS-120b**
  (Argon is not on Free).
- **Replacement**: no per-model replacement is named; what remains on Free is
  **Gemini 4 Hydrogen**, which "is available on all plans and is the default
  model for Free, Google AI Plus, and standard Google AI Pro trial accounts".
  Claude Sonnet/Opus 5.5 and Gemini 4 Neon/Carbon are **not** on Free.
- `/usage` (CLI): "Your remaining quota for each model group ... The models in a
  group share a weekly limit and a five-hour limit."
- No BYOK for extra Antigravity rate limits ("There is currently no support
  for ... Bring-your-own-key").
- Antigravity quota is the Google-account plan quota, separate from the
  `GEMINI_API_KEY` project quota (the plans page describes plan quotas only;
  the API key is not mentioned) [inference].

### 0.3 Groq

Pages: https://console.groq.com/docs/rate-limits (.md), https://console.groq.com/docs/models,
https://console.groq.com/docs/errors, https://console.groq.com/docs/deprecations.

- **Per-model table** (rate-limits page; verbatim columns MODEL ID / RPM / RPD / TPM / TPD):

| Model ID | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 30 | 1K | 8K | 200K |
| `openai/gpt-oss-20b` | 30 | 1K | 8K | 200K |
| `qwen/qwen3.8-27b` | 30 | 1K | 8K | 200K |
| `openai/gpt-oss-safeguard-20b` | 3 | 1K | 2K | 200K |
| `meta-llama/llama-prompt-guard-2-22m` / `-86m` | 30 | 14.4K | 15K | 500K |

  **Caveat:** the sentence above the table says "the limits shown below are the
  base limits for the Developer plan", but the models page lists Developer-plan
  limits of **1K RPM / 250K TPM** for these same models, so this table is the
  free-plan level (page wording is inconsistent). The org's exact values are on
  https://console.groq.com/settings/limits.
- New: some organisations also have **ITPM / OTPM** (input / output tokens per
  minute) caps, visible as "X in / Y out" on the Limits page.
- "Cached tokens do not count towards your rate limits." "Rate limits apply at
  the organization level, not individual users."
- **Headers (verbatim):** `x-ratelimit-limit-requests`,
  `x-ratelimit-remaining-requests`, `x-ratelimit-reset-requests` "Always refers
  to Requests Per Day (RPD)"; `x-ratelimit-limit-tokens`,
  `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-tokens` "Always refers to
  Tokens Per Minute (TPM)"; `retry-after` "In seconds", "only set if you hit
  the rate limit and status code 429 is returned. The other headers are always
  included." There is **no header for RPM or TPD** - those appear only in the
  429 message text (format not shown on the official pages; still not verified).
- Models (models page): Production: `openai/gpt-oss-120b` (131,072 ctx, 65,536
  max completion), `openai/gpt-oss-20b` (131,072 / 65,536);
  `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` are now **Enterprise only**
  ("ContactSales"). Preview: `qwen/qwen3.8-27b` (131,072 / 16,384; "may be
  discontinued at short notice"), `openai/gpt-oss-safeguard-20b`. List:
  `GET https://api.groq.com/openai/v1/models` "return[s] a JSON list of all
  active models".
- Errors page: 429 "Implement request throttling and respect rate limits"; 498
  flex capacity exceeded; 500 / 502 (retry may resolve) / 503 ("Wait before
  retrying"); "**You will not be charged for requests that return server error
  codes.**" 413 request body too large; error body
  `{"error": {"message", "type"}}`.
- Deprecation process (verbatim): announcement by **email to affected users**
  plus the deprecations page; transition period; possible automatic upgrade;
  after the date "Requests to deprecated model IDs will return errors". Preview
  models "may be discontinued at short notice with limited advance warning".
  Observed notice: 2 months for Llama (emailed 2026-06-17, shutdown 2026-08-16),
  4 weeks for compound. Deprecations "apply to free and developer-tier usage".

### 0.4 Z.AI

Pages: https://docs.z.ai/api-reference/api-code, https://docs.z.ai/guides/overview/pricing,
https://docs.z.ai/guides/llm/glm-4.7, https://docs.z.ai/guides/overview/concept-param,
https://docs.z.ai/api-reference/introduction, https://docs.z.ai/api-reference/llm/chat-completion,
https://docs.z.ai/devpack/notice/api-key-management, https://docs.z.ai/help/faq, https://docs.z.ai/llms.txt.

- **Free models (pricing page, "Other Pricing"):** `GLM-4.7-Flash` and
  `GLM-4.5-Flash`: Input / Cached Input / Storage / Output all "Free". GLM-4.7-Flash
  page: "Lightweight, Completely Free", text in/out, **context 200K, maximum
  output 128K**. `GLM-4.6V-Flash` is **no longer listed** (first-pass claim
  removed). `GLM-5.3-Flash` is paid ($0.15 / $0.50 per 1M).
- **Endpoint:** "general API endpoint ... `https://api.z.ai/api/paas/v4`"
  (`POST /paas/v4/chat/completions`). Coding Plan uses a dedicated endpoint.
  Since 2026-10-16 the **key type decides billing** ("Changing the endpoint does
  not change the key's billing type"); a Standard API Key uses balance/bundles.
- **Concurrency (concept-param page, verbatim):** "Concurrency refers to the
  number of API requests you can initiate simultaneously ... Different users or
  subscription plans may have different concurrency quotas ... If you exceed
  the concurrency limit, new requests may fail or need to wait in queue." No
  number published. The docs' "Rate Limits" link (`docs.z.ai/api-reference/rate-limit`)
  **redirects (307) to the console** `https://z.ai/manage-apikey/rate-limits`
  (login; not reachable here). "1 concurrent request" for free Flash remains
  **not verified**.
- **Model list endpoint:** none documented (the docs index lists no models API;
  `api.z.ai` itself was not reachable to probe). Not verified.
- **Error codes (verbatim, api-code page; HTTP status / message):**

| Code | HTTP | Official message |
|---|---|---|
| 1113 | 429 | "Insufficient balance or no resource package. Please recharge." |
| 1211 | 400 | "Unknown Model, please check the model code." |
| 1221 | 400 | "API `${API_name}` has been taken offline" |
| 1234 | 500 | "Network error, error id: ..., please try again later" |
| 1261 | 400 | "Prompt too long" |
| 1301 | 400 | unsafe/sensitive content detected |
| **1302** | 429 | "Rate limit reached for requests" |
| **1303** | - | **not listed on the official page** (no official meaning) |
| **1305** | 429 | "The service may be temporarily overloaded, please try again later" |
| 1308 | 429 | "Usage limit reached for {number} {unit}. Your limit will reset at {next_flush_time}" |
| 1309 | 429 | "Your GLM Coding Plan package has expired and is temporarily unavailable..." |
| 1310 | 429 | "Weekly/Monthly Limit Exhausted. Your limit will reset at {next_flush_time}" |
| 1311 | 429 | "Your current subscription plan does not yet include access to ${model_name}" |
| 1313 | 429 | "Your account's current usage pattern does not comply with the Fair Usage Policy, and your request frequency has been limited ... To restore access, please submit a request." |
| 1314-1321 | 429 | enterprise package expired / key limited to enterprise coding / 5-hour or 7-day usage limit with no extra-usage balance or monthly spend limit, "Resets at {next_flush_time}" |

  Shape: `{"error": {"code": "1214", "message": "..."}}` (code is a **string**).
  Streaming: "if the API terminates abnormally during inference, the above error
  codes will not be returned. Instead, the reason ... in the `finish_reason`".
  The timezone of `{next_flush_time}` is not stated (UTC+8 claim not verified).

### 0.5 OpenRouter

Pages: https://openrouter.ai/docs/api-reference/limits (.md),
https://openrouter.ai/docs/api_reference/errors-and-debugging (.md),
https://openrouter.ai/docs/faq, https://openrouter.ai/docs/guides/routing/model-variants/free,
https://openrouter.ai/docs/guides/routing/routers/free-router, https://openrouter.ai/api/v1/models,
OpenRouter's blog https://openrouter.ai/blog/tutorials/llm-api-rate-limits/ (dated 2026-11-11).

- **Free limits (limits page table, verbatim):** credits purchased all-time
  "Less than 10": **20 RPM, 50 RPD**; "At least 10": **20 RPM, 1000 RPD**.
  The higher ceiling is granted "starting one credit below the table's
  threshold". FAQ: "For free models, rate limits are determined by the credits
  that you have purchased."
- "Making additional accounts or API keys will not affect your rate limits, as
  we govern capacity globally. We do however have different rate limits for
  different models, so you can share the load that way". The blog (measured)
  says "OpenRouter applies **one per-minute limiter to all free models** on an
  account". Treat RPM as shared (safe side).
- **Negative balance**: "If your account has a negative credit balance, you may
  see errors, including for free models."
- **`GET /api/v1/key`** (limits page): `free_model_daily_requests {used, limit,
  remaining}` "the daily counter and ceiling that gate your free-model requests
  ... **The per-minute limit is not reported there**"; counters are per "current
  UTC day". `is_free_tier`: "Whether the user has paid for credits before".
  `limit`/`limit_remaining`/`usage*` are credits (USD). `rate_limit`: "A
  deprecated object in the response, safe to ignore". `/api/v1/key` itself has
  a per-IP burst limit (no `X-RateLimit-*` headers; wait a few seconds, backoff).
- **429 handling (limits page):** body `{"error": {"code": 429, "message":
  "Rate limit exceeded", "metadata": {"error_type": "rate_limit_exceeded"}}}`.
  A 429 comes from OpenRouter (free per-minute/per-day, key-management,
  per-IP, DDoS) or from the upstream provider (`error.metadata.provider_code`
  = provider's code; fallback routing retries other providers first). "When
  OpenRouter itself returns a 429 error for a free-model ... limit, the error
  response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
  `X-RateLimit-Reset`"; "Successful inference responses do not include
  `X-RateLimit-*` headers"; `Retry-After` only "when every attempted provider
  returned a retry hint". Errors page: `Retry-After` may appear on 429 and 503.
- **`limit_source` on 429** is **not in the reference docs** (they document
  it only for 402/403: `openrouter_in_flight_budget`, `openrouter_credits`,
  `openrouter_key_limit`, `openrouter_guardrail_budget`,
  `openrouter_workspace_budget`). OpenRouter's own blog (2026-11-11) shows real
  429 bodies:
  ```json
  {"message": "Rate limit exceeded: free-models-per-min. ", "code": 429,
   "metadata": {"headers": {"X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1792448640000"},
                "limit_source": "openrouter_free_tier_per_minute",
                "remedy_hint": "Slow down requests to free models, or retry after the per-minute window resets.",
                "provider_name": null}}
  ```
  and `upstream_provider_shared_pool` (upstream capacity, e.g. message
  "google/gemma-4-31b-it:free is temporarily rate-limited upstream. Please retry
  shortly, or add your own key ..."; no reset header); its sample code checks
  `openrouter_free_tier_daily` ("resets at UTC midnight"). Note the
  `X-RateLimit-*` values are also **inside `error.metadata.headers`** (Reset in
  Unix ms). Status of these names: official blog, not reference docs.
- Typed `error.metadata.error_type` (errors page): `rate_limit_exceeded` (429),
  `provider_overloaded` (503), `provider_unavailable` (502),
  `context_length_exceeded` (400), `payment_required` (402), `not_found` (404),
  `payload_too_large` (413); 500s are masked (`error_type: "server"`).
  Status meanings: 502 "model is down or we received an invalid response",
  503 "no available model provider that meets your routing requirements".
- **Fallback trap (free-variant page):** "If you list a `:free` model in a
  `models` fallback array ... a fallback to a paid model incurs charges ... To
  keep a request free, list only `:free` models in `models`, or use the Free
  Models Router (`openrouter/free`) on its own, which falls back only to other
  free models."
- **`openrouter/free`**: "automatically selects a free model at random from the
  available free models", filtering for needed features (tools, structured
  outputs). Ctx 200,000 in `/models`. Random choice = non-reproducible fixes.
- Privacy (FAQ): providers that log/train "will not be routed to unless the
  model training toggle is switched on in the privacy settings"; otherwise "you
  will get an error and your request will not complete".
- **Current free models from `GET /api/v1/models` (read 2026-11-25; 472 text
  models; 14 with prompt = completion = 0; sorted by context):**

| id | context | max output (top provider) | tools |
|---|---|---|---|
| `inclusionai/ling-3.2-flash:free` | 1,048,576 | 262,144 | yes |
| `particle-ai/particle-1:free` (agentic coding, post-trained on DeepSeek V4.1 Flash) | 1,048,576 | 131,072 | yes |
| `baidu/ernie-5.5-flash-preview:free` | 1,024,000 | 921,600 | yes |
| `nvidia/nemotron-3.5-super-vl:free` | 1,000,000 | 131,072 | yes |
| `nvidia/nemotron-3.5-lightning:free` | 1,000,000 | 65,536 | yes |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,000,000 | 65,536 | yes |
| `recursive/flint-v1.0:free` (for coding agents, 2.5B active) | 262,144 | 235,929 | yes |
| `google/gemma-4-31b-it:free` | 262,144 | 32,768 | yes |
| `google/gemma-4-26b-a4b-it:free` | 262,144 | 32,768 | yes |
| `liquid/lfm-3-1.7b:free` (1.7B, too small; "Prompts and outputs may be retained and used") | 262,144 | 8,192 | yes |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256,000 | 65,536 | yes |
| `openrouter/free` (router) | 200,000 | - | yes |

  (The other two zero-price entries are Google Lyria music models.) **Gone:**
  `openai/gpt-oss-120b:free`, `qwen/qwen3-coder:free`,
  `deepseek/deepseek-r1-0528:free` are **not** in the list (only paid variants
  exist). No free model has an `expiration_date` set today.

### 0.6 Recommended default model lists for AUTOMAT (code fixing, free only)

Order = try first to last; always re-check availability at run time.

- **Gemini (`GEMINI_API_KEY`)**: `gemini-4-hydrogen` -> `gemini-3.8-flash` ->
  `gemini-3.6-flash` -> `gemini-3.5-flash-lite`. Do not use `gemini-2.5-*`
  (existing-users only; 2.5 Flash/Pro auto-route from 2026-12-01) or Argon /
  Carbon / Neon / `gemini-3.1-pro-preview` (no free tier). Quota is per model,
  so on a daily 429 move down the list.
- **Antigravity**: after 2026-11-30 only `Gemini 4 Hydrogen` on the Free plan;
  drop 3.8 Flash, GPT-OSS-120b, Claude 4.6 from AUTOMAT's Antigravity config.
- **Groq (`GROQ_API_KEY`)**: `openai/gpt-oss-120b` -> `qwen/qwen3.8-27b`
  (preview) -> `openai/gpt-oss-20b`. Keep `max_completion_tokens` modest: the
  free TPM is 8K.
- **Z.AI (`ZAI_API_KEY`, `https://api.z.ai/api/paas/v4`, Standard API key)**:
  `glm-4.7-flash` -> `glm-4.5-flash`. One request at a time.
- **OpenRouter (`OPENROUTER_API_KEY`, only `:free`, never a paid fallback)**:
  `particle-ai/particle-1:free` -> `nvidia/nemotron-3-ultra-550b-a55b:free` ->
  `inclusionai/ling-3.2-flash:free` -> `google/gemma-4-31b-it:free` ->
  `baidu/ernie-5.5-flash-preview:free` (preview). Suitability for code is from
  OpenRouter's descriptions, not tested. Build the list from `/api/v1/models`
  each run (`:free` + zero pricing + `tools` if needed); use `openrouter/free`
  only as a last resort.

---

## 1. Google Gemini API (AI Studio key, `GEMINI_API_KEY`)

### 1.1 Free models suitable for code fixing (Nov 2026)

The model line-up has moved on a lot from 2025 (Gemini 4 "Argon"/"Hydrogen"/"Neon",
3.8 Flash, 3.6 Flash, 3.5 Flash-Lite). From the pricing page
(https://ai.google.dev/gemini-api/docs/pricing) [official, via search excerpt]:

| Model | Free tier? | Notes |
|---|---|---|
| Gemini 3.8 Flash | Yes ("Free of charge" input on Free tier) | newest Flash; exact model code and limits not seen [not verified] |
| Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) | listed with free tier in "what's new 3.6" page | input 1,048,576 tokens, output 65,536 tokens (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) [official, via search excerpt] |
| Gemini 3.6 Flash | 1M context, 64k output; free-tier token rows not visible [not verified] | |
| Gemini 2.5 Flash-Lite | "Free of charge" input/output on Free tier [official, via search excerpt] | 2.5 models: "not deprecated", served "until further notice", but **only to users who used them before**; new projects told to use 3.5 Flash-Lite or 3.8 Flash (changelog) |
| Gemini 4 Argon | **Not available on the Free tier** (https://ai.google.dev/gemini-api/docs/latest-model) | |
| `gemini-3.1-pro-preview` | **no free tier** (https://ai.google.dev/gemini-api/docs/gemini-3) | |

- Context caveat [official, via search excerpt]: input + `max_output_tokens`
  share the 1M window; synchronous requests cap `max_output_tokens` at 65,536.
- **List models programmatically:** `GET https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY`
  returns `name`, `inputTokenLimit`, `outputTokenLimit`, `supportedGenerationMethods`
  (standard Gemini API `models.list`; this does **not** say whether a model is in
  the free tier or what your quota is). [Endpoint is standard API surface; page
  not re-read today -> not verified today.]
- A forum report: Gemini 3.8 Flash shows "Leaving Soon (Nov 30)" in Antigravity
  (https://discuss.ai.google.dev/t/.../204690) [not verified for the API].

### 1.2 Limits on the free tier

From https://ai.google.dev/gemini-api/docs/rate-limits [official, via search excerpt]:

- Dimensions: **RPM, TPM (input tokens), RPD**; plus spend caps on paid tiers
  ($10/$50/$200 per 10 minutes, rolling, for Tier 1/2/3 - not relevant to free).
- "**Rate limits are applied per project, not per API key.**" A second key in
  the same Google Cloud project gives **no** extra quota. Limits are also
  **per model** (the quota IDs below say `PerProjectPerModel`).
- **The page no longer publishes a per-model free-tier table.** It points to
  the **rate-limit view in Google AI Studio** (https://aistudio.google.com ->
  usage / rate limit) which shows the live limits for *your* project.
  So: **no official numbers for RPM/RPD exist in the docs as of today.**
- Free tier eligibility: "tied to an active project or free trial"; Google may
  exclude projects "flagged by automated systems" (forum, Google-affiliated
  responder) [not verified].
- Numbers circulating on third-party sites (e.g. 5 RPM / 20 RPD for Gemini 3.8
  Flash, 1,500 RPD for Flash-Lite) are **[not verified]** and conflict.
- What counts: per-model RPM/RPD count requests; TPM counts input tokens
  (older official wording; not re-read today) [not verified today]. Forum users
  report that **503-failed requests are still counted against RPM/RPD** (not
  confirmed by Google) [not verified].

### 1.3 Reset

- **RPD resets at midnight Pacific time** (America/Los_Angeles; 08:00 UTC in
  winter/PST, 07:00 UTC in summer/PDT). Quote: "Requests per day (RPD) quotas
  reset at midnight Pacific time." [official, via search excerpt]
- Per-minute windows: not documented as rolling or fixed. Google's own CLI
  treats any `PerMinute` violation as "retry after 60 s" [official code].
- Forum reports of RPD counters not resetting at midnight PT (stuck at 21/20)
  exist [not verified].

### 1.4 How to tell per-minute from per-day on a 429 (the key point)

The 429 body is a `google.rpc` error with `status: "RESOURCE_EXHAUSTED"` and
`details[]`. Google's own Gemini CLI
(`google-gemini/gemini-cli`, `packages/core/src/utils/googleQuotaErrors.ts`,
commit `08e9a20f749aefcbda38622ac757899c3d6216e0`, 2026-11-24) classifies it
like this [official code]:

1. Message contains `limit: 0` -> **terminal** (the project/tier has no quota
   for this model at all; waiting will not help -> switch model/provider).
2. Message matches `spend cap` / `spending cap` -> terminal.
3. `QuotaFailure.violations[].quotaId` contains **`PerDay` or `Daily`** ->
   **terminal**: "You have exhausted your daily quota on this model."
   **This check runs before RetryInfo**, because the `retryDelay` on a per-day
   429 can be short (e.g. "34s") and misleading.
4. `ErrorInfo.reason` `MODEL_CAPACITY_EXHAUSTED` / `MODEL_CAPACITY_EXCEEDED`
   -> terminal (switch model at once).
5. `RetryInfo.retryDelay` present (e.g. `"56s"`, `"34.07s"`, `"900ms"`) ->
   retryable after that delay; **if > 300 s treat as terminal**.
6. `quotaId` contains **`PerMinute`** (or `ErrorInfo.metadata.quota_limit`
   contains `PerMinute`) -> retryable after **60 s**.
7. No details but message has `Please retry in X[s|ms]` -> retryable (terminal
   if > 300 s).
8. Message matches `exhausted your capacity|capacity exceeded|MODEL_CAPACITY_EXHAUSTED`
   -> terminal.
9. Otherwise 429/499/503 -> generic retryable.

Exact free-tier per-minute example from Google's test file
(`googleQuotaErrors.test.ts`) [official code]:

```json
{
  "code": 429,
  "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits.\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 2\nPlease retry in 56.185908122s.",
  "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{
       "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
       "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
       "quotaDimensions": {"location": "global", "model": "gemini-2.5-pro"},
       "quotaValue": "2"}]},
    {"@type": "type.googleapis.com/google.rpc.Help", "links": [{"description": "Learn more about Gemini API quotas", "url": "https://ai.google.dev/gemini-api/docs/rate-limits"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "56s"}
  ]
}
```

The daily one has `quotaId: "GenerateRequestsPerDayPerProjectPerModel-FreeTier"`
(same metric `generate_content_free_tier_requests`); there is also a TPM one
(`GenerateContentInputTokensPerModelPerMinute-FreeTier`, metric
`generate_content_free_tier_input_token_count`) [names of the daily/TPM ids:
seen in third-party issue reports, e.g.
https://github.com/UKGovernmentBEIS/inspect_ai/issues/5526 -> not verified from
Google's own text; the *rule* "contains PerDay" is official code].

- The `quotaDimensions.model` field tells **which model** is exhausted; the
  daily quota is per model, so another free model in the same project may
  still work.
- Some 429s (and many 503s) on new models carry **no QuotaFailure / RetryInfo**
  at all (capacity, not quota) [forum, not verified] -> Google's CLI treats
  these as a generic retryable error.

### 1.5 503 / 500 / overloaded

From https://ai.google.dev/gemini-api/docs/troubleshooting [official, via search excerpt]:
- **503 UNAVAILABLE**: "The service may be temporarily overloaded or down."
  Fix: check status page, wait and retry, or **temporarily switch model**.
  Google staff (forum): a 503 is unrelated to your quota.
- **500 INTERNAL**: unexpected error on Google's side; **an overly long input
  context can cause it** -> reduce input or switch model.
- **504 DEADLINE_EXCEEDED**: prompt/context too large to finish in time -> set a
  larger client timeout [general troubleshooting table; not re-read today].
- Retry: exponential backoff "1 s, then 2 s, 4 s, 8 s", with jitter; **retry
  only transient errors (429, 408, 5xx)**; never 400/403; cap the attempts.
- The official SDKs already retry. Python `google-genai` [official code,
  `googleapis/python-genai` `google/genai/_api_client.py`, commit
  `36e29707`, 2026-11-24]: 5 attempts including the first, initial 1 s, max
  60 s, exp base 2, jitter 1, on HTTP 408/429/500/502/503/504. **If AUTOMAT
  wraps its own retry loop around the SDK, calls are multiplied** (up to 5x per
  outer attempt, and each counts against RPM/RPD).
- Gemini CLI default retry [official code, `retry.ts`]: 10 attempts, initial
  5 s, max 30 s, doubling, ±30 % jitter; 429/499/5xx retryable.
- Status page: https://aistudio.google.com/status (not reachable from here).

### 1.6 Deprecation policy

- https://ai.google.dev/gemini-api/docs/deprecations [official, via search excerpt]:
  the table's shutdown dates are "the earliest possible dates on which a model
  might be retired"; "exact dates will be communicated with advance notice".
  No fixed notice period is stated. Announcements: the deprecations page and the
  changelog https://ai.google.dev/gemini-api/docs/changelog.
- Preview models can be shut down at short notice (several preview TTS/live
  models: earliest shutdown 2026-11-17).
- Gemini 2.5: "will continue to be served until further notice", **only for
  users who used them before** (new keys may get "no longer available to new
  users").

### 1.7 Data use / automated use (brief)

- https://ai.google.dev/gemini-api/terms [official, via search excerpt]: free
  ("Unpaid Services") prompts and responses **may be used to improve Google's
  products and reviewed by humans** (disconnected from account/key first); do
  not send sensitive/personal data.
- **Exception: users in the EEA, Switzerland or the UK** - the "Paid Services"
  data terms apply to all services, **including the unpaid Gemini API quota**
  (so no training use). Relevant if the project's Google account is in Italy.
- No rule found that forbids CI/automated use of the free tier [not verified].
- Region: the Gemini API is only available in supported countries (list in
  "available regions" page) - GitHub Actions runners are in the US, which is
  supported [not re-read today].

### 1.8 Antigravity (CLI/IDE) free usage

- https://antigravity.google/pricing/ and https://antigravity.google/docs/plans/
  [official, via search excerpt]: **Individuals $0/month: "baseline agent quota
  that refreshes weekly"** plus a weekly rate limit. **No numbers are
  published.** Pro: refresh every 5 h + higher weekly limits.
- Free models: Gemini 4 Hydrogen, Gemini 3.8 Flash, Claude Sonnet 4.6, Claude
  Opus 4.6, GPT-OSS-120b; **Gemini 4 Argon, Gemini 3.8 Flash, GPT-OSS-120b and
  the Claude 4.6 models "leaving on November 30" (2026)** (https://antigravity.google/docs/models/).
  Gemini 4 Neon not on Free.
- `/usage` in the Antigravity CLI (https://antigravity.google/docs/cli/commands/usage/)
  shows remaining quota per **model group**; models in a group share a weekly
  limit and a 5-hour limit.
- Antigravity quota is the **Google-account (subscription) quota, not the
  `GEMINI_API_KEY` project quota**, unless the CLI is configured to use an API
  key [inference; not verified].
- 403 `VALIDATION_REQUIRED` from `cloudcode-pa.googleapis.com` means the account
  needs a manual verification in a browser -> CI cannot fix it, it is terminal
  for the bot [official code, gemini-cli].

---

## 2. Groq (`GROQ_API_KEY`, OpenAI-compatible, base `https://api.groq.com/openai/v1`)

### 2.1 Free models suitable for code fixing (Nov 2026)

Groq retired the Llama/Kimi/Qwen3-32B line in 2026 (https://console.groq.com/docs/deprecations
[official, via search excerpt]):

| Retired model | Shutdown | Groq's recommended replacement |
|---|---|---|
| `groq/compound`, `groq/compound-mini` | 2026-09-21 (announced 2026-08-24) | none given |
| `qwen/qwen3.6-27b` | 2026-09-14 | `qwen/qwen3.8-27b` |
| `llama-3.1-8b-instant` | 2026-08-16 | `openai/gpt-oss-20b` |
| `llama-3.3-70b-versatile` | 2026-08-16 | `openai/gpt-oss-120b` (or qwen 27b) |
| `qwen/qwen3-32b`, `meta-llama/llama-4-scout-17b-16e-instruct` | 2026-07-17 | `openai/gpt-oss-120b` |
| `moonshotai/kimi-k2-instruct-0905` | 2026-04-15 | `openai/gpt-oss-120b` |
| `meta-llama/llama-4-maverick-17b-128e-instruct` | 2026-03-09 | `openai/gpt-oss-120b` |

Current candidates for code fixing [official model pages, via search excerpt]:

| Model ID | Context | Max output |
|---|---|---|
| `openai/gpt-oss-120b` | 131,072 | 65,536 (https://console.groq.com/docs/model/openai/gpt-oss-120b) |
| `qwen/qwen3.8-27b` | 131,072 | 16,384 (https://console.groq.com/docs/model/qwen/qwen3.8-27b) |
| `openai/gpt-oss-20b` | 131,072 (assumed same family) | [not verified] |

- **List programmatically:** `GET https://api.groq.com/openai/v1/models`
  (Bearer `GROQ_API_KEY`) returns `id`, `owned_by`, `active`, `context_window`,
  `created` (https://console.groq.com/docs/api-reference [official, via search
  excerpt]). Max completion tokens is **not** in that response; it is only in
  the models table on https://console.groq.com/docs/models. Filter on
  `active: true`.

### 2.2 Limits on the free plan

From https://console.groq.com/docs/rate-limits [official, via search excerpt]:
- Dimensions: **RPM, RPD, TPM, TPD** (plus ASH/ASD audio-seconds for audio
  models). "You can hit any limit type depending on which threshold you reach
  first."
- **Limits apply at the organization level, not per user / per key**, and
  per model. A second key in the same organisation adds nothing.
- Cached tokens do not count toward rate limits (prompt-caching page).
- The per-model Free-plan table did not render in the search excerpt. Values
  copied by several third-party sites for **`openai/gpt-oss-120b` on the Free
  plan: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD** [not verified - consistent
  across several third-party copies, and a user-reported 429 shows "requests
  per day (RPD): Limit 1000" for this model]. The exact live values for the
  org are on the console's **Settings -> Limits** page.
- Tokens: TPM/TPD count prompt + completion tokens; requests are counted with
  their `max_completion_tokens` reservation [not verified - not in the excerpt].
  Practical consequence: a large `max_completion_tokens` can trip TPM on the
  8k-TPM free plan even when the actual output is short.

### 2.3 Reset

- Headers (official, illustrative values): `x-ratelimit-reset-requests: 2m59.56s`
  ("always refers to RPD"), `x-ratelimit-reset-tokens: 7.66s` ("always refers to
  TPM"). Values are **Go-style durations** (`2m59.56s`, `14h12m`, `7.66s`,
  `120ms`), not timestamps.
- Because the RPD reset header counts down minutes, not to a fixed clock time,
  **Groq's daily limits replenish continuously (rolling / token-bucket), not at
  a fixed midnight** [inference from the official header example and from user
  429s with RPD "Limit 1000, Used 1000 ... Please try again in 1m8.977s";
  no official sentence states the window type -> not verified]. A third-party
  guide claims a "UTC calendar day" for TPD [not verified, contradicts the above].

### 2.4 How to tell per-minute from per-day on a 429

Official headers (https://console.groq.com/docs/rate-limits [official, via search excerpt]):

| Header | Meaning |
|---|---|
| `retry-after` | seconds; **only on 429** (example `2`) |
| `x-ratelimit-limit-requests` | **RPD** limit (example 14400) |
| `x-ratelimit-limit-tokens` | **TPM** limit (example 18000) |
| `x-ratelimit-remaining-requests` | remaining **RPD** |
| `x-ratelimit-remaining-tokens` | remaining **TPM** |
| `x-ratelimit-reset-requests` | time until RPD replenishes (`2m59.56s`) |
| `x-ratelimit-reset-tokens` | time until TPM replenishes (`7.66s`) |

Note: the headers expose **RPD and TPM only** - there is no header for RPM or
TPD. To identify those, parse the error body.

429 body (format from user-reported logs, matches Groq's OpenAI-style errors
[not verified from an official example]):

```json
{"error": {"message": "Rate limit reached for model `openai/gpt-oss-120b` in organization `org_...` service tier `on_demand` on requests per day (RPD): Limit 1000, Used 1000, Requested 1. Please try again in 1m8.977s. ...",
           "type": "requests", "code": "rate_limit_exceeded"}}
```

Classification rule for AUTOMAT:
- message contains `per minute (RPM)` or `per minute (TPM)` -> short wait
  (`retry-after`), retry the same model.
- message contains `per day (RPD)` or `per day (TPD)` -> daily quota; the
  "try again in" is real (rolling) but usually only frees a few requests/tokens
  -> **switch model/provider instead of hammering**; re-try Groq later.
- `x-ratelimit-remaining-requests: 0` on any response = RPD exhausted.
- A single request larger than the TPM limit fails with **413** /
  `request_too_large` style errors and never succeeds by waiting [not verified].

### 2.5 503 / 500 / 498

From https://console.groq.com/docs/errors [official, via search excerpt]:
- **503 Service Unavailable**: maintenance or overload -> wait, then retry.
- **500 Internal Server Error**: retry with backoff.
- **498** (Groq-specific): **flex tier** capacity exceeded (`capacity_exceeded`)
  -> jittered backoff. Free plan does not use flex unless `service_tier=flex`
  or `auto` is requested (https://console.groq.com/docs/flex-processing).
- 429: "add throttling and respect limits".
- Official Python SDK [official code, `groq/groq-python`
  `src/groq/_constants.py` + `_base_client.py`, commit `55066d94`, 2026-09-04]:
  `DEFAULT_MAX_RETRIES = 2`, backoff 0.5 s doubling to max 8 s with jitter;
  retries 408, 409, 429, >=500; honours `x-should-retry`, `retry-after-ms`,
  then `retry-after`, **but only if 0 < retry-after <= 60 s** (longer waits
  are ignored and normal backoff is used). Timeout 60 s.

### 2.6 Deprecation policy

- Groq Services Agreement (https://console.groq.com/docs/legal/services-agreement):
  Groq "may deprecate the AI Model Services at any time and will use
  commercially reasonable efforts to provide Customer with reasonable prior
  notice". **No fixed notice period.** Observed notice in 2026: ~4 weeks
  (compound: 2026-08-24 -> 2026-09-21).
- Announcements: https://console.groq.com/docs/deprecations and
  https://console.groq.com/docs/changelog (plus email to org owners [not verified]).
- Once a model is decommissioned, calls fail with 404/`model_decommissioned`
  style errors [not verified] -> AUTOMAT must re-read `/models` and not
  hard-code IDs.

### 2.7 Data use / automated use (brief)

- https://console.groq.com/docs/your-data [official, via search excerpt]:
  inference inputs/outputs **not retained by default**; kept up to 30 days only
  for reliability/abuse monitoring; Zero Data Retention can be enabled in Data
  Controls. Groq "will never access Customer Data for training purposes"
  (Terms of Sale / services agreement). Data stored in GCP, US. No
  free-tier-specific exception found.
- No clause found forbidding automated/CI use [not verified].
---

## 3. Z.AI / Zhipu GLM (`ZAI_API_KEY`)

### 3.1 Endpoints and keys

- **General API (what the free Flash models use): `https://api.z.ai/api/paas/v4/`**
  (`/chat/completions`, OpenAI-style). China mirror: `https://open.bigmodel.cn/api/paas/v4/`
  (separate account/key, `ZhipuAiClient`). [official, via search excerpt;
  https://docs.z.ai/api-reference/introduction, PyPI `zai-sdk` page]
- **Coding endpoint `https://api.z.ai/api/coding/paas/v4`** is only for the paid
  GLM Coding Plan. **Since 2026-10-16 standard-API keys and Coding-Plan keys
  are managed separately**; the base URL decides billing: the general endpoint
  bills account balance / bundles, the coding endpoint draws plan quota
  (https://docs.z.ai/devpack/notice/api-key-management [official, via search
  excerpt]). For a no-billing setup: **use the general endpoint and only the
  free Flash models**; any paid model on a zero-balance account returns 1113.
- Official SDK: `pip install zai-sdk` (`ZaiClient`, env `ZAI_BASE_URL`);
  source `zai-org/z-ai-sdk-python` (could not be cloned here - SDK retry
  defaults **not verified**).

### 3.2 Free models

From https://docs.z.ai/guides/overview/pricing [official, via search excerpt;
the page metadata said "last updated ~161 days ago"]:

| Model ID | Price | Context / max output |
|---|---|---|
| `glm-4.7-flash` | Free (input, cached input, storage, output) | 200K / up to 128K for the GLM-4.7 family (https://docs.z.ai/guides/llm/glm-4.7; Flash-specific values **not verified**). Chat API: `max_tokens` 1..131072, default 65536 for glm-4.7 (https://docs.z.ai/guides/overview/concept-param) |
| `glm-4.5-flash` | Free | 128K [not verified]. **Status unclear**: third-party sites say "retirement announced" / "offline since Jan 2026, routed to 4.7-Flash"; no official notice found [not verified] |
| `glm-4.6v-flash` | Free (vision) | not suitable/needed for code |
| `glm-5.3-flash` | **paid** ($0.15 in / $0.50 out per 1M) - not free | |

- **Best free code model: `glm-4.7-flash`.**
- List programmatically: no public, documented `GET /models` endpoint was found
  for `api.z.ai` [not verified]; the model list is the pricing/overview page.
  AUTOMAT should keep a small allow-list and treat 400/404 "model not found"
  as "retired".

### 3.3 Limits

- **No published RPM/RPD/TPM/TPD for the free Flash models.** The docs
  describe **concurrency** limits: "the number of API requests that can be
  initiated at the same time"; "different users or subscription plans may have
  different concurrency quotas"; when exceeded "new requests may fail or need
  to wait in queue" (https://docs.z.ai/guides/overview/concept-param
  [official, via search excerpt]).
- Your actual limits: **https://z.ai/manage-apikey/rate-limits** (console,
  login) per the FAQ (https://docs.z.ai/help/faq).
- Third-party (several sources): **free `glm-4.7-flash` = 1 concurrent
  request** [not verified]. Practical rule: **never send parallel requests to
  Z.AI free models**; serialise them.
- 5-hour / weekly usage limits and peak hours (Mon-Fri 14:00-18:00 UTC+8)
  apply to the **Coding Plan**, not to the free general-API models
  (https://docs.z.ai/devpack/usage-policy).

### 3.4 Reset

- Free Flash models: no daily quota documented, so no daily reset (concurrency
  frees as soon as the running request ends) [not verified].
- Coding-Plan codes 1308/1310 carry "Your limit will reset at
  {next_flush_time}"; a third-party bug report says that timestamp has **no
  zone and is Asia/Shanghai (UTC+8)**, not UTC
  (https://github.com/diegosouzapw/OmniRoute/issues/14479) [not verified].

### 3.5 Error codes (HTTP status outside, business code inside the body)

From https://docs.z.ai/api-reference/api-code [official, via search excerpt]:

| Business code | HTTP | Meaning | What AUTOMAT should do |
|---|---|---|---|
| **1302** | 429 | "Rate limit reached for requests" (too fast / too many concurrent) | short backoff, retry same model, lower concurrency to 1 |
| **1303** | 429 | not in the excerpt. Commonly "request frequency too high" (rate limit variant) [not verified] | treat like 1302 |
| **1305** | 429 | "service may be temporarily overloaded, please try again later" (provider-side capacity, **not your quota**) | backoff and retry; slowing down does not help; switch provider after a few tries |
| **1113** | 429 | "Insufficient balance or no resource package. Please recharge." Also when a Coding-Plan key is used outside supported tools / wrong base URL | **terminal**: wrong model (not free) or wrong key/endpoint; never retry |
| 1308 | 429 | Coding Plan: "Usage limit reached for {n} {unit}. Your limit will reset at {next_flush_time}" | terminal until that time |
| 1309 | 429 | Coding Plan expired | terminal |
| 1310 | 429 | "Weekly/Monthly Limit Exhausted. Your limit will reset at {next_flush_time}" | terminal until that time |
| 1313 | 429 | fair-use restriction (third-party: must appeal) [not verified] | terminal |
| 1301 | 400 | content filter flagged input/output | do not retry same prompt |

- **Key point: on Z.AI, HTTP 429 alone means nothing - always read
  `error.code`.** Body shape: `{"error": {"code": "1302", "message": "..."}}`
  [shape not verified from an official example].
- Streaming: if inference stops abnormally, error codes may not be returned;
  the reason is in `finish_reason` (official errors page).
- No `Retry-After` / `x-ratelimit-*` headers are documented [not verified].

### 3.6 Retry / backoff

- Docs give no numbers. Use exponential backoff with jitter for 1302/1303/1305
  and 5xx; never retry 1113/1308/1309/1310/1313/1301.

### 3.7 Deprecation

- No formal deprecation policy or notice period found. Announcements:
  https://docs.z.ai/release-notes/new-released (and `.md`). [not verified]

### 3.8 Data use (brief)

- Consumer privacy policy does not apply to API data; API data is covered by a
  "Data Processing Addendum for API Services" which was **not found / not read**.
  Terms of use contain a bracketed (draft-looking) sentence that Z.ai will not
  use End User Content to improve services (https://docs.z.ai/legal-agreement/terms-of-use)
  [not verified]. Company: Zhipu AI (China); international endpoint
  `api.z.ai`. Since the repository is public, sending its code is low risk.
---

## 4. OpenRouter (`OPENROUTER_API_KEY`, `:free` models, base `https://openrouter.ai/api/v1`)

Primary code source used: OpenRouter's official OpenAPI spec shipped in its
SDKs (`OpenRouterTeam/python-sdk/.speakeasy/in.openapi.yaml`, commit
`faf973f9`, 2026-11-25; same spec in `typescript-sdk` `ffb8aa6a` and `go-sdk`
`c09aa673`) - marked **[official spec]**.

### 4.1 Free models and how to list them

- `GET https://openrouter.ai/api/v1/models` (no key needed) [official spec]:
  query params `category`, `supported_parameters` (comma-separated, e.g.
  `tools`), `input_modalities`, `output_modalities` (default `text`), `q`
  (search by name/slug), `sort` (e.g. `context-high-to-low`, `newest`),
  `offset`/`limit` (max 1000). Each model has `id`, `context_length`,
  `pricing` (strings, `"0"` for free), `top_provider.context_length`,
  `top_provider.max_completion_tokens`, `supported_parameters`,
  **`expiration_date`** ("The date after which the model may be removed",
  YYYY-MM-DD or null), `knowledge_cutoff`.
- **Free = `id` ends in `:free`** (and `pricing.prompt == "0"` and
  `pricing.completion == "0"`). Filter client-side; also drop models whose
  `expiration_date` is past or near.
- Code-capable free models seen on official pages (Nov 2026)
  [official, via search excerpt]: `openai/gpt-oss-120b:free` (131K context),
  `qwen/qwen3-coder:free` (free context may be smaller than the paid 262K;
  "context windows on free endpoints are sometimes smaller"). The free list
  changes often - **always build it from `/models` at run time.**
  `openrouter/auto-code` exists (router for coding agents) but whether it is
  free is **not verified**.

### 4.2 Limits for `:free` models

https://openrouter.ai/pricing, https://openrouter.ai/collections/free-models,
https://openrouter.ai/docs/api_reference/limits [official, via search excerpt]:

- **20 requests per minute** for `:free` variants, **one limiter shared by all
  free models of the account** (switching to another `:free` model does not
  escape an RPM 429).
- **50 `:free` requests per day** if the account has bought < $10 of credits
  ever; **1,000 per day** after $10 (collections page says the threshold is
  $9 to absorb fees). "**Failed attempts count toward the daily cap.**"
- Limits are **per account**, not per key: extra keys do not add quota.
- No TPM/TPD for free models from OpenRouter itself; the upstream provider may
  enforce its own limits (shows up as upstream 429s).
- **Negative credit balance -> errors (402) even for free models.**
- Other $0 models without `:free` are not under these caps but can be limited
  by OpenRouter/provider.

### 4.3 Reset

- Daily free-model counter **resets at UTC midnight** [official spec,
  `FreeModelDailyRequests`: "the counter resets at UTC midnight"].
- Per-minute window: the 429 carries `X-RateLimit-Reset` (Unix ms) =
  earliest time a retry can succeed (OpenRouter blog tutorial
  https://openrouter.ai/blog/tutorials/llm-api-rate-limits/ [official, via
  search excerpt]); rolling vs fixed not stated [not verified].

### 4.4 Key status endpoint `GET /api/v1/key` [official spec]

Relevant fields of `data`:
- **`free_model_daily_requests: {used, limit, remaining}`** - "Free-model
  (`:free` variant) daily request quota for the account that owns the key.
  Reports the same counter and tier limit that free-model enforcement reads
  ... the counter resets at UTC midnight." `limit` "depends on total credits
  purchased and is independent of `is_free_tier`". Example
  `{"limit": 50, "remaining": 38, "used": 12}`.
  **-> AUTOMAT should call this before a run and skip OpenRouter when
  `remaining == 0`.** (Exempt accounts/BYOK: `remaining` is policy only.)
- `is_free_tier` - "Whether this is a free tier API key" (search excerpt: means
  the account never paid). Not the right field for quota decisions.
- `limit`, `limit_remaining`, `limit_reset` - the key's **USD spending cap**,
  not request limits. `usage`, `usage_daily`/`weekly`/`monthly` - **USD credits**
  used (UTC day; UTC week Mon-Sun; UTC month). For a free-only bot these stay 0.
- `rate_limit` - **deprecated**, "Legacy ... Will always return -1" (example
  still shows `{"requests": 1000, "interval": "1h"}`) - **ignore it**.

### 4.5 429 handling: who limited you, per minute or per day

Error body [official spec]: `{"error": {"code": 429, "message": "...",
"metadata": {...}}, "user_id": ..., "openrouter_metadata": ...}`.

From https://openrouter.ai/docs/api_reference/errors-and-debugging and
https://openrouter.ai/docs/api_reference/limits [official, via search excerpt]:

| `error.metadata.limit_source` | HTTP | Meaning | Action |
|---|---|---|---|
| `openrouter_free_tier_per_minute` | 429 | OpenRouter's 20 RPM free cap | wait until `X-RateLimit-Reset` (ms) / `Retry-After`; do **not** switch to another `:free` model (same limiter) |
| `openrouter_free_tier_daily` | 429 | daily 50/1000 cap used up; resets UTC midnight | **stop using OpenRouter free models until 00:00 UTC** (seen in the tutorial's code comment; not in the official table -> name [not verified]) |
| `upstream_provider_shared_pool` | 429 | the upstream provider serving that free model is out of capacity / rate-limiting the shared free pool | try another `:free` model or later; **no reset header**; it still consumes a daily request |
| `openrouter_in_flight_budget` | 402 | in-flight spending budget full | wait `Retry-After`, retry |
| `openrouter_key_limit` / `openrouter_credits` | 402 | key USD cap / balance | terminal for a free bot (negative balance) |

- For upstream errors: `metadata.provider_name`, `metadata.provider_code`
  (original upstream code; omitted on 500s), `metadata.raw` (verbatim upstream
  payload).
- **Branch on `limit_source`, not on the message text.**
- Headers on 429: `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset` (Unix **milliseconds**); `Retry-After` may be absent
  (tutorial's logs).
- Fallback: OpenRouter already retries other providers of the same model
  before returning an upstream 429/502 (`provider.allow_fallbacks`, default
  true) [official spec]; a `models: [...]` list in the request gives
  model-level fallback.

### 4.6 5xx

[official spec + errors page via search excerpt]:
- **502** Bad Gateway: provider error (OpenRouter may already have retried
  another provider).
- **503** Service Unavailable: "no available providers" (or provider
  overloaded - pages disagree). For `:free` this often means no provider
  meets your **data policy** (see 4.8).
- **529** Provider Overloaded ("Provider returned error").
- Mid-stream errors arrive as an SSE event with `finish_reason: "error"`
  (HTTP status already 200).
- Spec default retry strategy for its SDKs: exponential, initial 500 ms,
  max 60 s, max 3 attempts (`x-retry-strategy`); speakeasy config retries
  only **5XX** and connection errors (not 429), exponent 1.5, max elapsed 1 h.

### 4.7 Deprecation

- Model availability is independent of API versioning: "models are added and
  removed by providers independently" (https://openrouter.ai/docs/api_reference/versioning).
- `expiration_date` in `/models` ("date after which the model may be
  removed"); providers can set a `deprecation_date`, past which models may be
  auto-hidden (https://openrouter.ai/docs/guides/community/for-providers).
- An account alert "model deprecation" is sent to users who recently used a
  model scheduled for retirement, with date and replacement
  (https://openrouter.ai/docs/guides/features/notifications).
- Free variants are removed without fixed notice (history: "some less popular
  models will soon transition away from the free tier",
  https://openrouter.ai/blog/announcements/updates-to-our-free-tier-sustaining-accessible-ai-for-everyone/).
  No fixed notice period [not verified].

### 4.8 Data policy / required settings / headers

- **Free routes are served by providers "whose data policy may allow training
  on your prompts".** The account's privacy settings have a **separate switch
  for free models**; if it is off (or a guardrail / `provider.data_collection:
  "deny"` excludes them), the request fails with **404 "No endpoints found
  matching your data policy"-style error** that names the free-model training
  setting (https://openrouter.ai/docs/guides/privacy/provider-logging,
  https://openrouter.ai/docs/guides/routing/provider-selection [official, via
  search excerpt]). OpenRouter itself does not train on inputs/outputs
  (https://openrouter.ai/privacy). The repository is public, so training
  exposure is acceptable for code; never send secrets.
- Attribution headers (https://openrouter.ai/docs/app-attribution):
  `HTTP-Referer` (optional for the call; required only for app rankings),
  `X-OpenRouter-Title` (display name; `X-Title` still accepted). **Not
  required for the API to work.** Avoid putting personal data in them.
- Auth: `Authorization: Bearer $OPENROUTER_API_KEY`.

---

## 5. Cross-provider rules for AUTOMAT (derived from the above)

1. **Classify every 429 before retrying**; never treat all 429s alike:
   - Gemini: `quotaId` contains `PerDay`/`Daily` or message `limit: 0` ->
     daily/zero quota -> stop this model until 00:00 America/Los_Angeles;
     `PerMinute` -> wait `retryDelay` (or 60 s) and retry; 503 -> backoff, then
     another model.
   - Groq: message `per day (RPD|TPD)` or `x-ratelimit-remaining-requests: 0`
     -> daily (rolling) -> switch provider; `per minute (RPM|TPM)` -> wait
     `retry-after`.
   - Z.AI: read `error.code`: 1302/1303 -> slow down (concurrency 1);
     1305 -> provider overloaded, backoff; 1113/1308/1309/1310/1313 -> terminal.
   - OpenRouter: read `error.metadata.limit_source`; daily -> stop until
     00:00 UTC; per-minute -> wait `X-RateLimit-Reset`; upstream -> other free
     model. Check `GET /api/v1/key` `free_model_daily_requests.remaining` first.
2. **Daily resets differ**: Gemini 00:00 Pacific (08:00 UTC in winter); OpenRouter
   00:00 UTC; Groq rolling (no fixed time) [not verified]; Z.AI free: no daily
   cap documented.
3. **Quotas are per project/organisation/account, never per key** (Gemini
   project, Groq organisation, OpenRouter account). Rotating keys of the same
   account does not help and may breach terms.
4. **Do not stack retries**: the official SDKs already retry (google-genai 5
   attempts; groq 2 retries; OpenRouter SDK 5xx only). Every retry consumes RPD
   (OpenRouter: failed attempts count; Gemini: reported).
5. **Never hard-code model IDs**: Groq retired 8 models in 2026; Gemini 2.5
   restricted to existing users; OpenRouter free list changes. List models at
   run time (Gemini `models.list`, Groq `/models` `active`, OpenRouter
   `/models` `:free` + `expiration_date`); Z.AI has no documented list endpoint.
