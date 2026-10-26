# LLM Evaluation and Monitoring Platform

A portfolio project for evaluating LLM and RAG applications across
answer quality, retrieval quality, reliability, latency, and estimated
cost. Run repeatable experiments, compare models and prompt versions,
inspect failures, and enforce quality gates in CI.

> **Project status:** In development. Phase 1 (deterministic evaluation
> core + CLI) is implemented and tested. Everything else below is planned.
> Do not treat illustrative sample scores or costs as real benchmark
> results.

## What works today

-   `llm-eval validate | run | gate | metrics list` CLI with exit codes
    `0` pass, `1` gate failed, `2` invalid input, `3` run failure, `4`
    internal error.
-   JSON and JSONL datasets (schema 1.0), with case-level validation
    errors.
-   A deterministic **fake provider** (no network, no credentials) that
    can simulate wrong answers and provider errors.
-   Engine with bounded concurrency, timeouts, retries for transient
    errors only, and partial-failure handling.
-   Metrics: `exact_match` v1.0 and `latency` v1.0 (mean, median, p95,
    min, max). See [`docs/metrics.md`](docs/metrics.md).
-   Absolute-threshold quality gates with an explicit missing-metric
    policy.
-   JSON + Markdown reports that record the dataset content hash, the
    config hash, metric versions and the software version.

## Why this project?

LLM applications are nondeterministic and can regress when prompts,
models, retrieval settings, or application code change. This project
aims to make evaluation repeatable by storing datasets and run
configurations, calculating documented metrics, comparing results
against baselines, and failing CI when configured thresholds are
violated.

## Planned capabilities

-   Import and version JSON/JSONL evaluation datasets.
-   Evaluate multiple model providers or compatible application
    endpoints.
-   Use a deterministic fake provider for local demos and CI without
    paid API credentials.
-   Measure exact match, latency, token usage, and estimated cost.
-   Evaluate retrieval Precision@k, Recall@k, and reciprocal rank when
    relevance labels are available.
-   Support optional LLM-as-judge metrics for correctness, relevance,
    instruction adherence, and groundedness.
-   Persist run summaries and case-level results.
-   Compare baseline and candidate runs and identify regressions.
-   Apply quality gates through a CLI and GitHub Actions.
-   Provide a REST API and a dashboard for projects, datasets, runs, and
    comparisons.

These are intended capabilities; check the current implementation and
roadmap before assuming a feature is available.

## Architecture

The proposed architecture is a modular Python backend with a separate
background worker:

``` text
Dashboard / CLI / GitHub Actions
               |
               v
          FastAPI API
               |
       Application Services
               |
        Evaluation Engine
        /       |        \
 Providers    Metrics    Gates/Compare
        \       |        /
               |
          PostgreSQL
               |
           Redis Queue
               |
        Background Worker
```

The frontend is planned with React, TypeScript, and Vite. Docker Compose
will provide local infrastructure. The evaluation engine and core
metrics should remain testable without external model APIs.

See: - [`REQUIREMENTS.md`](REQUIREMENTS.md) --- product, functional,
non-functional, technical, API, security, and acceptance requirements. -
[`PROJECT_MAP.md`](PROJECT_MAP.md) --- intended file structure,
responsibilities, dependencies, and build order. - `docs/metrics.md` ---
planned metric formulas and limitations. - `docs/architecture.md` ---
planned detailed architecture.

## Proposed technology stack

  Area              Technology
  ----------------- -----------------------------
  Language          Python 3.12+
  API               FastAPI, Pydantic
  Database          PostgreSQL
  ORM/migrations    SQLAlchemy 2.x, Alembic
  Background jobs   Redis + Celery
  HTTP client       HTTPX
  Frontend          React, TypeScript, Vite
  Testing           pytest
  Quality           Ruff, optional mypy/pyright
  Containers        Docker, Docker Compose
  CI                GitHub Actions

The project should be built in phases. Do not add all infrastructure
before the deterministic evaluation core and CLI are working.

## Quick start

The commands below are the intended workflow; adjust them to the actual
files and scripts present in the current implementation.

### Prerequisites

-   Git
-   Python 3.12 or newer
-   `uv` (recommended) or another Python environment manager
-   Docker Desktop or Docker Engine for the full stack
-   Node.js LTS only when running the frontend
-   Provider API credentials only for live-provider evaluations

### 1. Clone the repository

``` bash
git clone https://github.com/YOUR_USERNAME/llm-evaluation-platform.git
cd llm-evaluation-platform
```

Replace `YOUR_USERNAME` with your GitHub username and use the actual
repository URL.

### 2. Configure environment variables

``` bash
cp .env.example .env
```

On Windows Command Prompt, use:

``` bat
copy .env.example .env
```

Review `.env.example` and fill in only the credentials for providers you
intend to use. Never commit `.env`.

### 3. Start local infrastructure

When `docker-compose.yml` and its services are implemented:

``` bash
docker compose up -d --build
```

### 4. Install backend dependencies

The project is managed with `uv` (`uv.lock` is committed):

``` bash
uv sync --all-groups
```

Phase 1 needs no `.env` and no Docker: the CLI and fake provider run
without any configuration.

### 5. Run tests

``` bash
uv run pytest
```

The core test suite should work without paid provider credentials by
using the deterministic fake provider.

### 6. Run a demo evaluation

``` bash
uv run llm-eval validate --config evals/demo_config.yaml
uv run llm-eval run --config evals/demo_config.yaml   # writes reports/demo-run.json and .md
uv run llm-eval gate --report reports/demo-run.json --rules evals/gates.example.yaml
uv run llm-eval metrics list
```

The demo evaluates 21 cases against two fake models. `fake-reference`
returns the reference answers. `fake-noisy` gives three wrong answers and
hits one simulated rate limit. Both pass the example gate (exact_match
mean ≥ 0.8, error_rate ≤ 0.05, latency p95 ≤ 2000 ms). Tighten a
threshold in `evals/gates.example.yaml` to watch the run exit with code
`1`. Paths inside a config file resolve relative to that file.

### 7. Start the API and frontend

The planned local defaults are API `http://localhost:8000` and frontend
`http://localhost:5173`. Confirm the actual ports in configuration.

``` bash
# Backend example; run from the directory/package where app is importable
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend, after its package.json is implemented
cd frontend
npm install
npm run dev
```

FastAPI's interactive documentation is expected at
`http://localhost:8000/docs` when the API is running.

## Dataset example

A minimal dataset may look like this:

``` json
{
  "schema_version": "1.0",
  "name": "basic-qa",
  "cases": [
    {
      "case_key": "capital-001",
      "input": {
        "question": "What is the capital of France?"
      },
      "expected_output": "Paris",
      "reference_context": null,
      "retrieved_contexts": [],
      "tags": ["geography"],
      "metadata": {}
    }
  ]
}
```

Each case should have a stable `case_key` so results from different runs
can be aligned. For retrieval metrics, provide relevance labels or
reference document IDs in the documented schema. Do not infer retrieval
relevance from answer text alone.

## Metrics and interpretation

  ---------------------------------------------------------------------------
  Metric                      What it tells you       Important limitation
  --------------------------- ----------------------- -----------------------
  Exact match                 Whether normalized      Too strict for many
                              output exactly matches  open-ended answers
                              the expected output     

  Text similarity             Approximate             Similarity does not
                              textual/semantic        guarantee factual
                              similarity              correctness

  LLM-as-judge                A model's rubric-based  Can be inconsistent or
                              assessment of an answer biased; keep rubric and
                                                      judge model versioned

  Precision@k                 Fraction of top-k       Requires relevance
                              retrieved items that    labels
                              are relevant            

  Recall@k                    Fraction of known       Requires a reference
                              relevant items          set of relevant items
                              retrieved in top-k      

  Reciprocal rank             Rewards the position of Requires relevance
                              the first relevant      labels
                              result                  

  Faithfulness/groundedness   Whether an answer is    Requires the actual
                              supported by supplied   context and a
                              context                 documented evaluator

  Latency                     Time taken for a        Report sample size and
                              request                 percentile limitations

  Estimated cost              Estimated model cost    Not exact;
                              from usage and          usage/pricing may be
                              configured prices       unavailable or change
  ---------------------------------------------------------------------------

No single score should be treated as a complete measure of model
quality. Keep per-metric results and error rates visible.

## Quality gates and CI

The intended workflow is:

1.  Validate the evaluation configuration.
2.  Run a small deterministic test dataset using the fake provider.
3.  Execute unit and integration tests.
4.  Compare candidate results with a baseline where configured.
5.  Fail CI if a required gate fails.
6.  Upload reports as build artifacts.

Default pull-request CI should not require a paid LLM API key. Live
provider tests should be optional, protected, and subject to spending
limits.

## Security and privacy

-   Never commit `.env`, API keys, private datasets, or customer
    conversations.
-   Do not log authorization headers or provider secrets.
-   Treat prompts, retrieved documents, and model outputs as potentially
    sensitive.
-   Use timeouts, bounded retries, concurrency limits, and run budgets.
-   Restrict custom HTTP targets to mitigate server-side request forgery
    (SSRF).
-   Do not expose a publicly reachable API that can spend provider
    credits without authentication.
-   Use only datasets you are permitted to redistribute.
-   Review dependency and license requirements before release.

## Development roadmap

-   [x] Phase 0: project skeleton, config, linting, tests, CI workflow
    (Docker Compose deferred to Phase 2, when there are services to run)
-   [x] Phase 1: deterministic fake provider, dataset validation, core
    metrics, CLI, JSON report
-   [ ] Phase 2: FastAPI, PostgreSQL persistence, migrations, background
    worker
-   [ ] Phase 3: hosted and OpenAI-compatible provider adapters, token
    usage and cost estimation
-   [ ] Phase 4: judge and retrieval metrics
-   [ ] Phase 5: run comparisons, baselines, quality gates, CI
    integration
-   [ ] Phase 6: React dashboard and report exports
-   [ ] Phase 7: security review, end-to-end tests, screenshots,
    documentation, release

Update this checklist as features are implemented and verified.

## Contributing

Contributions should include tests, documentation, and clear
reproduction steps for bugs. Keep metric definitions explicit and
versioned. See [`CONTRIBUTING.md`](CONTRIBUTING.md) when available.

## License

Choose and add a license before publishing. Do not imply that the
repository is open-source under a particular license until the `LICENSE`
file exists.

## Disclaimer

Scores and cost figures are only as reliable as the dataset, metric
definitions, judge model, usage metadata, and pricing configuration.
This platform is an evaluation aid, not a guarantee of correctness or
safety.
