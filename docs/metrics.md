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

## Implemented metrics

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

### `estimated_cost` v1.0 — cost, lower is better, unit USD

- **Requires:** provider-reported `input_tokens` and `output_tokens`, and a
  price for the response's `provider` + `model_id` in the pricing table.
- **Score:** `input_tokens × input_price + output_tokens × output_price`,
  prices per million tokens. Entries can define a long-context tier: when
  the prompt exceeds `long_context_threshold_tokens`, the whole call uses
  the long-context rates.
- **Pricing table:** `backend/app/evaluation/default_pricing.yaml`
  (`pricing_version`, one entry per provider/model with `effective_from`,
  optional `effective_to`, and a `source`). `model_id: "*"` matches any
  model of a provider; an exact match always wins. A run **freezes** the
  table into its config snapshot, so the config hash covers the prices and
  editing the file never changes a past run. To use your own prices, pass
  a full table as the metric's `pricing` config.
- **Details per case:** `input_cost`, `output_cost`, `currency`,
  `pricing_version`, `price_effective_from`, `long_context_rate`,
  `is_estimate: true`.
- **Not applicable** when usage is not reported or the model has no
  price. A missing price is never reported as zero cost.
- **Limitations:** list prices only. Prompt caching, batch discounts,
  priority tiers and regional pricing are not modelled. Thinking tokens are
  billed as output and are included in `output_tokens`. Not billing data.
  The fake provider's rates are illustrative.

### `token_f1` v1.0 — answer quality, higher is better, range [0, 1]

- **Requires:** `expected_output` and a model output.
- **Score:** F1 of token precision and recall over the multisets of word
  tokens (`\w+`) of the normalized texts (same normalization as
  `exact_match`; punctuation always separates tokens). Both empty → 1.0,
  one empty → 0.0. No English article removal.
- **Details:** `precision`, `recall`.
- **Limitation:** lexical only. Paraphrases score low; a wrong answer that
  reuses the question's words can score high.

### Retrieval metrics — retrieval quality, higher is better, range [0, 1]

They need the case's ranked `retrieved_contexts` (by `document_id`) **and**
explicit relevance labels in `relevant_document_ids`. Without labels they
are `not_applicable`; text is never used to guess relevance. Duplicate IDs
in the ranking count once, at their best rank.

- **`retrieval_precision_at_k` v1.0** (config `k`, default 5):
  `|relevant ∩ top_k| / |top_k|` with `|top_k| = min(k, retrieved)`.
  Not applicable when nothing was retrieved.
- **`retrieval_recall_at_k` v1.0** (config `k`, default 5):
  `|relevant ∩ top_k| / |relevant|`; 0.0 when nothing was retrieved.
  Not applicable when the label list is empty (undefined).
- **`reciprocal_rank` v1.0** (optional `k`): `1 / rank` of the first
  relevant document, 0.0 if none; the mean over cases is the MRR.

`relevant_document_ids: []` means "labelled, nothing is relevant";
omitting the field means "not labelled". Datasets that do not use the field
keep the content hash they had before it existed.

### LLM-as-judge — `llm_judge_*` v1.0, higher is better, range [1, 5]

A judge model grades one criterion on a versioned 1–5 rubric
(`backend/app/evaluation/rubrics.py`) and must answer with
`{"score": <1-5>, "rationale": "..."}`.

| Metric | Rubric | Needs | Category |
|---|---|---|---|
| `llm_judge_correctness` | correctness v1.0 | `expected_output` | answer quality |
| `llm_judge_relevance` | relevance v1.0 | input | answer quality |
| `llm_judge_instruction_adherence` | instruction_adherence v1.0 | input | answer quality |
| `llm_judge_groundedness` (RAG faithfulness) | groundedness v1.0 | `reference_context` or `retrieved_contexts` text | answer quality |
| `llm_judge_context_relevance` | context_relevance v1.0 | context text | retrieval quality |

Config (every judge metric):

```yaml
- name: llm_judge_correctness
  config:
    judge:
      provider: anthropic          # any registered provider
      model_id: claude-haiku-5-5
      parameters: {max_tokens: 1000}   # system_prompt/prompt_template are reserved
      secret_reference: ANTHROPIC_API_KEY   # optional; must be allowlisted in the API
      timeout_seconds: 60
      max_concurrency: 2
      max_retries: 1               # transient errors only
      max_calls: 500               # optional spend guard per run, retries included
```

- **Details per case:** `rationale`, `criterion`, `rubric_version`,
  `judge_provider`, `judge_model_id`, `judge_input_tokens`,
  `judge_output_tokens`, `judge_attempts`, `scale: "1-5"`.
- **Errors, never guessed scores:** provider failures (`error_code` =
  the provider error category), output that is not a JSON object with an
  integer score 1–5 (`unparseable_judge_output`, with a redacted excerpt),
  and an exhausted call budget (`budget_exhausted`) are `error` results.
- **Deterministic judge for tests/CI:** `provider: fake` with
  `parameters: {mode: judge}` scores by a crude lexical heuristic (share
  of the judged text's words found in the evidence). It demonstrates the
  pipeline; it is not a quality signal.
- **Limitations:** judge scores are estimates. Judges can favour long or
  confident answers or their own model family, and vary between calls.
  Answers are fenced in tags and the judge is told to ignore instructions
  inside them, which reduces but does not remove prompt injection. Judge
  calls cost money and are not included in `estimated_cost`. Spot-check
  judge results by hand.

## Aggregation

For each model and metric, over `scored` results only:

- `mean`, `median`, `min`, `max`
- `p95`: **nearest-rank** percentile, the smallest observed value with at
  least 95% of observations ≤ it (`sorted[ceil(0.95·n) − 1]`).
- `total`: sum of scores, only for additive metrics (`estimated_cost`);
  `null` for the others.
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

- Aggregations: `mean`, `median`, `p95`, `min`, `max`, `total`
  (additive metrics only, e.g. a run cost budget), `count` (scored count). `error_rate` only supports `overall`.
- Operators: `gte`, `gt`, `lte`, `lt`, `eq`.
- **Missing metrics never pass silently.** If a metric was not computed,
  or has no scored cases, `missing_metric_policy` decides: `fail`
  (default), `skip`, or `warn`. The policy can be overridden per rule.

Baseline-relative regression thresholds arrive with run comparisons in
Phase 5.

## Planned metrics

Embedding-based semantic similarity (FR-060) and composite weighted scores
(FR-061). See the roadmap in `README.md`.
