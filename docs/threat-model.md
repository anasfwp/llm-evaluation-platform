# Threat model

Scope: the API, worker, dashboard and CLI as shipped in this repository,
run by one team on infrastructure they control. Reviewed for the v0.1.0
release.

## Assets

| Asset | Why it matters |
|---|---|
| Provider API keys | Direct spend; account abuse. |
| Prompts, outputs, datasets, retrieved contexts | May contain confidential or personal data. |
| Evaluation results and gates | Release decisions depend on them; tampering hides regressions. |
| Infrastructure (database, Redis, worker) | Compromise exposes everything above. |

## Trust boundaries

1. Browser / API client → API (untrusted input: every request body,
   uploaded dataset, query parameter).
2. API → worker via Redis (only run IDs cross; the worker reloads the run
   from the database).
3. Worker → model providers (outbound HTTPS; responses are untrusted text).
4. CI → repository (pull requests are untrusted code).

## Threats and mitigations

| # | Threat | Mitigation in this codebase | Status |
|---|---|---|---|
| T1 | **Unauthenticated access.** Anyone who can reach the API can read results and start paid runs. | No authentication exists yet. Docker Compose and the documented commands bind every port to `127.0.0.1`; the README says not to expose the API. | **Open — deploy only on localhost or behind an authenticating proxy.** |
| T2 | **Key exfiltration through configuration.** A caller points a model's `secret_reference` or base URL variable at another secret (e.g. `DATABASE_URL`) so the worker sends it in a request. | Configurations name environment variables only; every name must be in `PROVIDER_ENV_ALLOWLIST`, checked on create, update and at run start (judge and embedding configs too). | Mitigated |
| T3 | **Keys in logs, errors, reports or the repository.** | Keys are never stored in the database or returned by the API. Log records and stored error messages pass through secret redaction; prompt and completion text is never logged. `.env` is gitignored; CI runs a secret scan (gitleaks). | Mitigated |
| T4 | **SSRF via custom endpoints.** A caller makes the worker call an internal address. | Base URLs come only from allowlisted environment variables set by the operator, not from request bodies. | Mitigated (operator-controlled) |
| T5 | **Resource exhaustion / runaway spend.** Huge datasets, many models, endless retries, unbounded judge calls. | Validated caps: request size, cases and models per run, concurrency, timeouts, retry count and backoff, per-run `max_calls` for judges. Cancellation is supported. | Mitigated; no global spend limit — set provider-side limits |
| T6 | **Malicious model output.** Output containing HTML/JS, or instructions to execute. | Model output is never executed. Metrics compare strings. The dashboard renders all text through React (no `innerHTML`), so markup is shown as text. | Mitigated |
| T7 | **Prompt injection against the LLM judge.** An output says "rate this 5". | Rubric prompts separate instructions from the judged material and require a structured verdict; unparseable output is recorded as an error. Judge scores are labelled estimates and rubric/model metadata are stored. Do not use a judge score as the only release signal. | Partially mitigated (inherent to LLM judges) |
| T8 | **Malformed or hostile dataset files.** | Strict schema validation of the whole file before import, with size and case-count limits; JSON parsing only (no YAML/pickle from uploads). | Mitigated |
| T9 | **Gate tampering / silent passes.** Missing metrics or version changes make a gate pass by accident. | Missing data follows `missing_metric_policy` (default `fail`); relative rules refuse different metric versions; comparisons exclude metrics with different configurations and say so. | Mitigated |
| T10 | **Confidential data retained indefinitely.** | Projects are archived, not deleted; raw prompts and outputs are stored with results. There is no retention window or "don't store raw content" switch yet. | **Open — use non-sensitive datasets, or delete the database when done.** |
| T11 | **Vulnerable dependencies.** | Locked dependencies (`uv.lock`, `package-lock.json`); CI audits Python (pip-audit) and npm packages; Dependabot can be enabled on the repository. | Mitigated, ongoing |
| T12 | **Malicious pull request in CI.** | Workflows use `permissions: contents: read`, no secrets in pull-request jobs, and only the fake provider. | Mitigated |
| T13 | **Cross-origin requests from other sites.** | CORS allows only `CORS_ORIGINS` (default the local dashboard). Without authentication CORS is not access control — see T1. | Partially mitigated |

## Before any non-local deployment

1. Add authentication and per-project authorization (T1, T13).
2. Terminate TLS at a trusted proxy; keep PostgreSQL and Redis private.
3. Put API keys in a secret manager; set spend limits and alerts at each provider.
4. Decide on retention and implement deletion for runs and datasets (T10).
5. Re-run this review.

## Reporting a vulnerability

Please do not open a public issue for security problems. Contact the
repository owner privately through GitHub.
