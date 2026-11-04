# 0005: Bundled, versioned pricing table

**Date:** 2026-10-27

## Context

Cost has to be an estimate that stays stable for past runs, even though provider
prices change.

## Decision

Keep list prices in `backend/app/evaluation/default_pricing.yaml`, with a
`pricing_version` and a source for each entry. Each run freezes the table into
its configuration snapshot. A model with no entry reports `not_applicable`,
never zero.

## Alternatives

-   **Fetching prices live:** there is no common source, and runs would stop being
    reproducible.
-   **A pricing table in the database:** editable at runtime, but needs management
    screens that a single-user tool doesn't need yet.

## Consequences

Past costs never change. Prices go out of date until someone updates the file,
and discounts such as caching or batch pricing aren't modelled, so costs are
always labelled as estimates.
