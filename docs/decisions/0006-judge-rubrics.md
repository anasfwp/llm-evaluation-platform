# 0006: Versioned rubrics in code for LLM judges

**Date:** 2026-10-28

## Context

A judge's score depends on the exact wording of its instructions. Comparing
scores from different wording would be misleading, and judged text can try to
influence the judge.

## Decision

Keep rubrics in `backend/app/evaluation/rubrics.py`. Any change in wording must
bump the rubric and metric versions. All rubrics use a 1-5 scale and a JSON
answer. Judged text is fenced in tags, and the judge is told to treat it as data.
Unparseable answers are recorded as errors. `max_calls` limits calls per run.

## Alternatives

-   **Rubrics editable by users:** flexible, but each edit would need its own
    version tracking to keep comparisons honest.
-   **A framework's prompts:** see [0004](0004-native-metrics.md).

## Consequences

Comparisons refuse to mix metric versions. Custom rubrics need a code change.
Fencing reduces prompt injection but can't eliminate it, so judge scores are
labelled as estimates.
