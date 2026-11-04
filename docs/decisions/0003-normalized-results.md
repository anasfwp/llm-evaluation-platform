# 0003: Normalized result tables, JSON for snapshots

**Date:** 2026-10-26

## Context

Users filter results by model, status, tag, metric and score. Runs must also
stay reproducible when datasets or model configurations change later.

## Decision

Store cases, case results and metric results as ordinary rows, with indexes on
fields used for filtering. Use JSON columns for things that are read whole: run
configuration snapshots, per-model summaries, case inputs and metric details.

## Alternatives

-   **One JSON document per run:** simple to write, but filtering and paging would
    mean loading and scanning whole runs.
-   **Rows for everything:** the run snapshot has a flexible shape, and it is never
    queried by field.

## Consequences

Results are saved as each case finishes, so progress is visible and partial
results survive a failure. Case input and expected output are copied into each
result, which uses more storage but keeps old results readable.
