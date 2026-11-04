# 0004: Native metrics, no evaluation framework

**Date:** 2026-10-28

## Context

Every score has to document what it measures, return `not_applicable` rather
than invent a value, and keep a version so that comparisons are valid.

## Decision

Implement all metrics in this repository behind one `Metric` interface: exact
match, token F1, semantic similarity, latency, estimated cost, retrieval metrics
and the LLM judges. Groundedness and context relevance are judge rubrics.

## Alternatives

-   **RAGAS or DeepEval:** more metrics out of the box, but a large dependency, and
    it would still need wrapping to fit the version and `not_applicable` rules. An
    adapter can be added later.

## Consequences

Formulas are small, readable and tested without network calls. There are fewer
metrics than a framework offers, and they haven't been benchmarked against one.
