# 0001: Modular monolith plus a separate worker

**Date:** 2026-10-26

## Context

The platform needs an API, long-running evaluations, a CLI and a dashboard. It
has to be easy to run on one computer and easy to read.

## Decision

Keep one Python codebase with clear modules (`api`, `services`, `evaluation`,
`providers`, `db`, `workers`, `cli`) and deploy it as two processes: the API and
a Celery worker. The CLI and worker call the same evaluation engine.

## Alternatives

-   **Microservices:** independent scaling, but far more to run and demonstrate,
    with no need for it at this size.
-   **Everything in the API process:** simplest, but long runs would tie up the
    API and die with it.

## Consequences

Scores are calculated the same way from the CLI and the API because there is only
one engine. The engine has no dependency on HTTP or the database, so it is tested
directly. Everything shares one release and one database.
