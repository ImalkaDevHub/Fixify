# AI provider

## Setup

```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...        # server side only
AI_MODEL=claude-opus-5-5            # default
AI_EFFORT=medium                    # low | medium | high | xhigh | max
```

**Low-cost configuration:** `AI_MODEL=claude-haiku-5-5` and `AI_EFFORT=low`. Any Claude model ID works. `AI_PROVIDER=none`, or an empty key, switches AI off: the API reports `available: false`, the UI says AI is not configured, and nothing is simulated.

Limits: `AI_TIMEOUT_SECONDS` (120), `AI_MAX_RETRIES` (2, done by the SDK for 408/409/429/5xx and connection errors), `AI_MAX_OUTPUT_TOKENS` (16,000), and `AI_JOBS_PER_USER_PER_HOUR` (30). Job-level retries (`JOB_MAX_ATTEMPTS`, with backoff) apply only to transient errors. Refusals, bad keys, and invalid requests fail immediately with a visible reason.

## Implementation

`app/ai/provider.py` defines `AIProvider.generate_json(system, user_content, schema, max_tokens)`. `AnthropicProvider` uses the official `anthropic` Python SDK (`AsyncAnthropic`):

- `client.beta.messages.create(...)` with `output_config = {"effort": AI_EFFORT, "format": {"type": "json_schema", "schema": ...}}`, so the response is schema-constrained JSON.
- For models that support it (Claude Fable 5.1, Opus 5.5, Opus 5, Sonnet 5.5), the server-side refusal fallback `fallbacks: "default"` with the `server-side-fallback-2026-07-01` beta. It is switched off with `AI_REFUSAL_FALLBACK=false`, and never sent to Haiku.
- `stop_reason` is checked before the content is read (`refusal` and `max_tokens` are reported, not parsed).
- Errors map to a public message plus a retryable flag. Keys and provider internals are never shown to users.

To add another provider, implement the same protocol and select it in `create_ai_provider`. The rest of Fixify does not change.

## What is sent

| Analysis | Fix generation |
|---|---|
| Finding type, severity, title, description, affected URL, HTTP status, sanitized evidence JSON (≤ 12 KB), scan URLs | The finding, the latest analysis summary, up to 5 allow-listed repository files (≤ 150 KB each, ≤ 200 KB total), reviewer comments and instructions when regenerating |
| Up to 40 other findings from the same scan (for grouping) | |
| Up to 300 allow-listed repository paths (when a repository is connected) | |

Everything passes through `redact_secrets` and the `<untrusted_*>` wrapper first. Cookies, headers, request bodies, and tokens are never collected by the scanner in the first place.

## Output handling

- Analysis: validated with `AnalysisOutput`. `suggested_locations` must be paths Fixify sent, and `related_finding_ids` must be IDs Fixify sent; anything else is dropped.
- Fix: validated with `FixOutput`. Each edit's path must be a provided file, and `original` must occur exactly once in it. Results are syntax-checked (JSON, Python AST, markup balance, bracket balance) and stored as `failed_validation` when invalid. If the model returns no edits, its `cannot_fix_reason` becomes the job error, and no empty proposal is created.
