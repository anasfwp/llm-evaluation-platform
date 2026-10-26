# Metrics

Every metric has a stable name and a version. If a metric's scoring
semantics change (including the normalization it uses), its version is
bumped. A config that pins an old version then fails validation instead
of silently getting reinterpreted scores.

Per-case metric results have one of three statuses:

| Status           | Meaning                                                        |
|------------------|----------------------------------------------------------------|
| `scored`         | A score was computed.                                          |
| `not_applicable` | Required inputs are missing. **Never** counted as a zero.      |
| `error`          | The metric itself failed to compute; the case result is kept.  |

**Errored model calls.** When a model call fails (timeout, rate limit,
auth failure, …) after the allowed retries, the case is recorded with
`status: error` and an `error_code`. Its metrics are marked
`not_applicable`. The failure shows up in the model's `error_rate`, not
as a 0 score in quality metrics. A quality mean therefore describes the
cases that got an answer, so gate on `error_rate` as well (see
`evals/gates.example.yaml`).

## Implemented metrics (Phase 1)

### `exact_match` v1.0 — answer quality, higher is better, range [0, 1]

- **Requires:** `expected_output` on the case and a model output.
- **Score:** `1.0` if `normalize(expected) == normalize(actual)`, else `0.0`.
- **Normalization (`normalize: true`, the default):** Unicode NFKC, casefold,
  collapse runs of whitespace to one space, then strip leading/trailing
  whitespace and Unicode punctuation (category `P*`). Internal
  punctuation and symbols such as `$` are kept.
- **Config:** `normalize: false` compares raw strings.
- **Not applicable** when the case has no `expected_output`.
- **Limitation:** too strict for open-ended answers. "The square root of
  144 is 12." does not match "12". Use it for short factual or structured
  outputs.

### `latency` v1.0 — performance, lower is better, unit ms

- **Score:** wall-clock time of the successful model call, measured by the
  engine around the adapter call. Only the final attempt is timed; time
  spent on retries and backoff is not included.
- **Not applicable** for errored calls.
- **Limitation:** includes local scheduling overhead. The fake provider's
  simulated latency is affected by OS timer resolution (≈15 ms on Windows).

## Aggregation

For each model and metric, over `scored` results only:

- `mean`, `median`, `min`, `max`
- `p95`: **nearest-rank** percentile, the smallest observed value with at
  least 95% of observations ≤ it (`sorted[ceil(0.95·n) − 1]`).
- `small_sample: true` when fewer than 20 scored observations exist.
  Percentiles from small samples are indicative only.

Run-level values per model: `case_count`, `success_count`, `error_count`,
`error_rate = error_count / case_count`, `error_codes`, and token usage
totals (summed only over cases where the provider reported usage).

The fake provider's token counts are a whitespace approximation and are
labelled `usage_method: whitespace_approximation` in `raw_metadata`.

## Gates

A gate rule is `metric` + `aggregation` + `operator` + `threshold`,
optionally scoped to one `model`. It is evaluated per model.

- Aggregations: `mean`, `median`, `p95`, `min`, `max`, `count` (scored
  count). `error_rate` only supports `overall`.
- Operators: `gte`, `gt`, `lte`, `lt`, `eq`.
- **Missing metrics never pass silently.** If a metric was not computed,
  or has no scored cases, `missing_metric_policy` decides: `fail`
  (default), `skip`, or `warn`. The policy can be overridden per rule.

Baseline-relative regression thresholds arrive with run comparisons in
Phase 5.

## Planned metrics

Text similarity, estimated cost (versioned pricing), LLM-as-judge
(versioned rubric), retrieval Precision@k / Recall@k / reciprocal rank
(explicit relevance labels required), and RAG faithfulness. See the
roadmap in `README.md`.
