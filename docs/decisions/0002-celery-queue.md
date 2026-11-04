# 0002: Celery with Redis for background runs

**Date:** 2026-10-26

## Context

Runs can take minutes and must not block API requests. The queue only has to
carry a run ID, because the worker reloads the run from the database.

## Decision

Use Celery with Redis as the broker. Runs are claimed atomically by moving them
from `queued` to `running`, so a duplicate delivery does nothing. Celery-level
retries are off, because the engine already retries each case and re-running a
whole evaluation could double provider spend.

## Alternatives

-   **RQ or Dramatiq:** smaller, and either would fit.
-   **A PostgreSQL-backed queue:** one less service, but more code to own.

## Consequences

Redis is one more service to run. If a worker dies mid-run, the run stays
`running` until someone marks it (see [operations](../operations.md)); automatic
recovery is on the roadmap. Celery replaces logging handlers at startup unless
told otherwise, so `celery_app.py` keeps the JSON logging explicitly.
