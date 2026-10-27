# Providers

A model configuration names a `provider`, a `model_id`, provider
`parameters`, and optionally a `secret_reference`. Parameters are validated
against the provider's schema; unknown keys are rejected.

| Provider            | Talks to                                                    | Credential (default variable)          |
|---------------------|-------------------------------------------------------------|----------------------------------------|
| `fake`              | Nothing: deterministic, offline                             | None                                   |
| `anthropic`         | Claude Messages API, via the official SDK                   | `ANTHROPIC_API_KEY` (required)         |
| `openai`            | `https://api.openai.com/v1/chat/completions`                | `OPENAI_API_KEY` (required)            |
| `openai_compatible` | Any Chat Completions server (vLLM, llama.cpp, LiteLLM, ...) | `OPENAI_COMPATIBLE_API_KEY` (optional) |

Hosted providers spend real credits, including `POST /models/{id}/test`.

## Credentials and the environment allowlist

Secrets are never stored. A model configuration refers to an environment
variable **by name** (`secret_reference`), and the worker reads its value
when the run executes. Without `secret_reference` the provider's default
variable is used.

Every variable a configuration can make the worker read must be listed in
`PROVIDER_ENV_ALLOWLIST` (comma-separated). The default is
`ANTHROPIC_API_KEY,OPENAI_API_KEY,OPENAI_COMPATIBLE_API_KEY,OPENAI_COMPATIBLE_BASE_URL`.
This stops an API caller from pointing a model at, say, `DATABASE_URL` and
having it sent in an outgoing request. Configurations are checked when they
are created or updated and again when a run starts. To use per-team keys,
add their names (for example `TEAM_A_ANTHROPIC_KEY`) to the allowlist.

A missing key is reported as `authentication_failed` and is not retried.
Error messages name the variable, never its value.

## Prompts

All hosted providers send one user message built from the case `input`:

- With `prompt_template`, `{{field}}` placeholders are replaced by the input
  field (strings as-is, other values as JSON). Only plain names are
  placeholders; there is no expression evaluation. A missing field fails the
  case with `invalid_request`.
- Without a template, the first of `prompt`, `question`, `input`, `query`
  is used; else the only string value; else the whole input as sorted JSON.

`system_prompt` sets a system prompt.

## `anthropic`

```yaml
- name: claude
  provider: anthropic
  model_id: claude-opus-5-5
  parameters:
    max_tokens: 16000        # 1..128000, default 16000
    effort: medium           # optional: low | medium | high | xhigh | max
    stop_sequences: []       # optional, at most 8
    system_prompt: "Answer with the final answer only."
```

- Sampling parameters (`temperature`, `top_p`, `top_k`) are not accepted:
  current Claude models reject them, so `effort` is the control for
  thoroughness and cost.
- `output_text` is the concatenated text blocks; thinking is not part of
  the answer. `raw_metadata` records `message_id`, `served_model`,
  `thinking_tokens`, and `refusal_category` when the model declines.
- A refusal (`finish_reason: refusal`) is a successful call with empty or
  partial output and is scored as such. Server-side fallback to a
  different model is deliberately not enabled: it would mix another
  model's answers into the results of the configured one.
- SDK retries are disabled; the engine owns retries.

## `openai` and `openai_compatible`

```yaml
- name: local-llama
  provider: openai_compatible
  model_id: llama-3.1-8b-instruct
  parameters:
    base_url_env: OPENAI_COMPATIBLE_BASE_URL  # variable holding e.g. http://localhost:8000/v1
    temperature: 0           # optional, 0..2
    max_tokens: 512          # optional
    top_p: 1                 # optional
    seed: 7                  # optional
    stop: ["\n\n"]           # optional, at most 4
```

- `openai` takes the same parameters except `base_url_env`; its URL is fixed.
- The base URL comes from an (allowlisted) environment variable, never from
  the API request, which limits server-side request forgery. It must be
  `http(s)`, have a host, and contain no credentials. Redirects are not
  followed (`invalid_request`).
- An API key is sent as `Authorization: Bearer ...` only when configured.
- Usage is read from `usage.prompt_tokens` / `usage.completion_tokens`;
  servers that omit it get `null` token counts (and no cost estimate).

## Timeouts, retries, and errors

Each call uses the model's `timeout_seconds` (or the run's). Errors are
normalized:

| `error_code`            | From                                  | Retried |
|-------------------------|---------------------------------------|---------|
| `timeout`               | Client timeout, HTTP 408/504          | Yes     |
| `rate_limited`          | HTTP 429                              | Yes     |
| `provider_unavailable`  | Connection errors, HTTP 409, 5xx, 529 | Yes     |
| `authentication_failed` | Missing key, HTTP 401/403             | No      |
| `invalid_request`       | HTTP 400/404/413/422, bad config/URL  | No      |
| `unknown_error`         | Malformed responses, anything else    | No      |

Retries use exponential backoff from `retry_backoff_seconds`, bounded by
`max_retries`. When a provider sends `Retry-After` (seconds or HTTP date),
the engine waits at least that long, capped at 60 seconds.

## Cost

Token usage feeds the `estimated_cost` metric; see
[`metrics.md`](metrics.md). Add prices for OpenAI or self-hosted models to
the pricing table (or a run's `pricing` config) to get estimates for them.

## Testing

The test suite never calls a hosted API. Adapters are tested offline
against mock HTTP transports that reproduce each API's request and
response shapes, including errors and `Retry-After`.
