# 0007: No login in the first release

**Date:** 2026-10-26

## Context

The first release is a local, single-user tool. Accounts would add a lot of work
that a local user doesn't benefit from.

## Decision

Ship without authentication. Docker Compose binds every port to `127.0.0.1`, and
the README says to keep the API off networks.

## Alternatives

-   **A shared API key:** small, but it could suggest the app is safe to expose
    without the rest of a deployment's protections.
-   **Accounts with per-project access:** the right end state, and too large for
    the first release.

## Consequences

Anyone who can reach the API can read results and start runs that cost money.
This is the main open risk in the [threat model](../threat-model.md). Login and
per-project access must be added before any shared or public deployment.
