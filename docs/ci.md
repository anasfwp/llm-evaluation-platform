# CI integration

The CLI is designed for CI: it reads a config, calls models, writes JSON and
Markdown reports, and signals the outcome through its exit code.

| Exit code | Meaning |
|---|---|
| 0 | Run succeeded and every gate rule passed (or no gate configured) |
| 1 | A gate rule failed, or `compare --fail-on-regression` found a regression |
| 2 | Invalid configuration, dataset, gate file, or report |
| 3 | Run failure: every case errored for at least one model |
| 4 | Unexpected internal error |

## Typical pipeline

1. `llm-eval validate` — fail fast on config mistakes, without model calls.
2. `llm-eval run --baseline <report>` — evaluate, apply absolute and
   baseline-relative gate rules, and add a regression section to the reports.
3. Upload `reports/` as a build artifact for reviewers.

Keep a baseline report in the repository (or download the one from the
last release) and refresh it deliberately when you accept a change:
`llm-eval run --config … --output evals/baselines/<name>.json`.

## GitHub Actions example

Ordinary pull requests should not need paid credentials. This workflow uses
the deterministic fake provider; for a live evaluation, add a separate job
that runs only on `workflow_dispatch` or a schedule and reads the API key
from repository secrets.

```yaml
name: LLM evaluation

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  evaluate:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --locked --python 3.12

      - name: Validate
        run: uv run llm-eval validate --config evals/demo_config.yaml

      - name: Evaluate and gate against the baseline
        run: >-
          uv run llm-eval run --config evals/demo_config.yaml
          --gates evals/gates.regression.yaml
          --baseline evals/baselines/demo-baseline.json
          --output reports/run.json --markdown reports/run.md

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-reports
          path: reports/

  # Optional live run against a real provider: manual trigger only.
  live:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --locked --python 3.12
      - run: uv run llm-eval run --config evals/your_live_config.yaml --output reports/live.json
```

`.github/workflows/ci.yml` in this repository runs the same steps on every
push and pull request.

## Gate files

- `evals/gates.example.yaml` — absolute thresholds (quality, error rate,
  p95 latency, cost budget).
- `evals/gates.regression.yaml` — relative rules against a baseline (no
  quality drop, no new errors, bounded latency growth) and a per-tag rule.

Rules that need data the run does not have (a metric that was not
computed, a relative rule without `--baseline`, a tag with no cases) follow
`missing_metric_policy`: `fail` (default), `warn`, or `skip`. They never
pass silently.
