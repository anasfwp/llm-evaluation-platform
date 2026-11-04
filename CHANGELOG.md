# Changelog

## 0.1.1 (2026-11-04)

### Added

-   `DELETE /api/v1/datasets/{id}`. It returns `409` once a run has used the
    dataset.
-   Case IDs in logs, and a "case finished" log line with no prompt or output
    content.
-   CI test of the full Docker stack, including the worker.
-   Demo GIF, roadmap, operations guide, and decision records.

### Fixed

-   Worker logs lost their JSON format and run IDs because Celery replaced the
    logging handlers at startup.
-   Duplicate React keys on the comparison page, for metrics charted with two
    aggregations.
-   Running migrations in-process disabled the application's loggers.
-   Missing favicon on the dashboard.

## 0.1.0 (2026-10-29)

First release: evaluation engine and CLI, REST API and worker, Anthropic and
OpenAI-compatible providers, cost estimates, LLM judges, retrieval metrics,
comparisons, baselines, quality gates, and the React dashboard.
