# 0008: No custom HTTP targets yet

**Date:** 2026-10-27

## Context

Evaluating a user's own app needs requests to a user-chosen URL. Combined with
no login, that would let any caller make the worker reach internal addresses
(SSRF).

## Decision

Don't build the custom HTTP target yet. Provider base URLs can come only from
environment variables named in `PROVIDER_ENV_ALLOWLIST`, which the operator
sets. API requests can't supply a URL. An app can still be evaluated if it
exposes an OpenAI-compatible endpoint.

## Alternatives

-   **Build it now with address filtering:** covers more of the requirements, but
    needs careful checks of DNS results and redirects, and is safer after login
    exists.

## Consequences

FR-025 and FR-026 are open and listed on the roadmap. When built, the feature
must block private, loopback, link-local and metadata addresses by default, check
DNS results and redirects, filter sensitive headers, and not retry non-idempotent
requests unless configured to.
