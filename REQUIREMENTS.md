# LLM Evaluation and Monitoring Platform --- Requirements Specification

**Document status:** Initial product and engineering specification\
**Version:** 1.0\
**Last updated:** 2026-10-26\
**Project type:** Portfolio-grade, local-first AI engineering platform\
**Primary users:** AI engineers, backend developers, ML engineers, QA
engineers, and teams maintaining LLM/RAG applications

------------------------------------------------------------------------

## 1. Product overview

### 1.1 Purpose

The LLM Evaluation and Monitoring Platform helps developers measure and
compare the quality, reliability, latency, and estimated cost of LLM
applications. Users define evaluation datasets, run them against one or
more models or application endpoints, inspect individual results,
compare experiment versions, and prevent quality regressions through
automated checks in CI.

The first release should be a useful, reproducible evaluation tool---not
a claim that subjective AI quality can be reduced to one perfect score.
Every metric must document what it measures, how it is calculated, and
where it is only an estimate.

### 1.2 Problem statement

LLM applications can appear to work in manual testing while producing
inconsistent, unsupported, slow, or expensive answers at scale. Teams
need a repeatable process to: - test multiple models against the same
cases; - compare generated outputs with expected answers and retrieved
context; - find regressions after prompt, model, retrieval, or code
changes; - inspect failures at the individual test-case level; - enforce
quality thresholds before merging or deploying changes.

### 1.3 Goals

1.  Create and version evaluation datasets.
2.  Run evaluations against multiple supported providers and compatible
    application endpoints.
3.  measure answer quality, retrieval quality, latency, token usage, and
    estimated cost.
4.  Store experiment runs and provide comparisons between runs.
5.  support deterministic checks in a command-line interface and GitHub
    Actions.
6.  Provide an API and a simple web dashboard for datasets, runs,
    results, and comparisons.
7.  Be runnable locally with Docker Compose and documented setup steps.
8.  Keep provider credentials secure and avoid exposing secrets in logs
    or API responses.

### 1.4 Non-goals for the first release

-   Training or fine-tuning foundation models.
-   Guaranteeing that an automated judge is objectively correct.
-   Replacing production observability/APM platforms.
-   A full multi-tenant enterprise SaaS billing system.
-   Real-time tracing of every token from arbitrary providers.
-   Automatically deploying models to production.
-   Executing arbitrary user-provided code or shell commands.
-   Claiming exact cost when a provider does not expose usage or current
    pricing.

### 1.5 Success criteria

The initial release is successful when a developer can: - start the
system using documented local instructions; - create/import a dataset
with at least 20 cases; - run one dataset against two configured
models; - see case-level input, expected answer, actual answer, metric
scores, latency, token usage when available, and errors; - compare two
completed runs; - configure minimum score and maximum regression
thresholds; - run an evaluation from the CLI and receive a non-zero exit
code when a required gate fails; - run automated tests in GitHub
Actions; - reproduce a run using its recorded dataset version,
prompt/config version, model identifier, and metric configuration.

------------------------------------------------------------------------

## 2. Users and primary workflows

### 2.1 Personas

**AI/ML engineer:** evaluates prompts, models, and RAG pipelines before
changing them.

**Backend developer:** validates an LLM-powered API and watches latency,
errors, and usage.

**QA engineer:** maintains a regression dataset and blocks releases when
quality drops below agreed thresholds.

**Portfolio reviewer/recruiter:** wants clear architecture, tests, setup
instructions, screenshots, and evidence that the project runs.

### 2.2 Core workflow

1.  Create a project.
2.  Add or import a dataset.
3.  Configure model providers or an application endpoint.
4.  Choose metrics, concurrency, and run settings.
5.  Start an evaluation run.
6.  Track progress and inspect failed cases.
7.  Review aggregate and per-case metrics.
8.  Compare the run with a baseline.
9.  apply pass/fail thresholds.
10. Run the same gate from CI using a CLI command.

------------------------------------------------------------------------

## 3. Functional requirements

Priority levels: **P0 = required for MVP**, **P1 = important next**,
**P2 = later enhancement**.

### 3.1 Projects and configuration

-   **FR-001 (P0):** The system shall allow users to create, list,
    retrieve, update, and archive projects.
-   **FR-002 (P0):** A project shall have a unique ID, name,
    description, creation timestamp, and settings.
-   **FR-003 (P0):** Provider settings shall reference environment
    variable names or secret-store references; raw API keys shall not be
    returned by read APIs.
-   **FR-004 (P1):** Users shall be able to configure project-level
    default metrics, thresholds, and run settings.
-   **FR-005 (P1):** The system shall support named evaluation
    configurations that can be reused.

### 3.2 Datasets and cases

-   **FR-010 (P0):** Users shall create, list, retrieve, update, and
    delete datasets.
-   **FR-011 (P0):** A dataset shall contain a name, description, schema
    version, and ordered test cases.
-   **FR-012 (P0):** A test case shall support a unique case ID,
    input/prompt, optional expected answer, optional reference context,
    optional retrieved contexts, optional metadata, and optional tags.
-   **FR-013 (P0):** Users shall import datasets from JSON and JSONL
    files.
-   **FR-014 (P0):** Imports shall validate required fields and report
    row/case-level validation errors.
-   **FR-015 (P0):** The system shall preserve dataset versions or
    immutable snapshots used by completed runs.
-   **FR-016 (P1):** Users shall filter cases by tag and search case
    IDs.
-   **FR-017 (P1):** Users shall export datasets as JSON or JSONL.
-   **FR-018 (P1):** The system shall support datasets that evaluate
    either a plain LLM prompt or a RAG/application endpoint.

### 3.3 Providers and target adapters

-   **FR-020 (P0):** The system shall define a provider adapter
    interface for model calls.
-   **FR-021 (P0):** The initial provider adapter shall support at least
    one hosted provider and one OpenAI-compatible endpoint; a
    deterministic mock provider shall be available for tests and demos.
-   **FR-022 (P0):** Users shall select one or more model configurations
    for an evaluation.
-   **FR-023 (P0):** A model configuration shall include provider, model
    ID, generation parameters, timeout, and optional concurrency limit.
-   **FR-024 (P0):** The system shall record provider errors, timeouts,
    and rate-limit responses per case without silently treating them as
    successful answers.
-   **FR-025 (P1):** The system shall support a custom HTTP target
    adapter for evaluating a user's own application endpoint.
-   **FR-026 (P1):** The target adapter shall allow safe configuration
    of method, URL, headers, request template, response JSON path, and
    timeout.
-   **FR-027 (P1):** The system shall support a local model adapter
    where feasible, without making a local model mandatory.
-   **FR-028 (P0):** Provider adapters shall normalize model output,
    usage information, and errors into a common internal result shape.

### 3.4 Evaluation runs and orchestration

-   **FR-030 (P0):** Users shall start a run using a dataset version,
    one or more model configurations, metrics, and run settings.
-   **FR-031 (P0):** Every run shall have a unique ID and statuses
    `queued`, `running`, `completed`, `failed`, or `cancelled`.
-   **FR-032 (P0):** The system shall persist run configuration and
    immutable references to dataset and metric versions.
-   **FR-033 (P0):** The system shall process cases with configurable
    bounded concurrency.
-   **FR-034 (P0):** The system shall apply request timeouts and bounded
    retries for transient failures only.
-   **FR-035 (P0):** The system shall support cancellation of a run
    where execution has not irreversibly completed.
-   **FR-036 (P0):** The system shall record per-case start/end times,
    latency, response, error, and usage when available.
-   **FR-037 (P0):** The system shall not retry non-idempotent custom
    target requests unless explicitly configured.
-   **FR-038 (P1):** Long-running runs shall execute in a background
    worker rather than blocking an HTTP request.
-   **FR-039 (P1):** The UI/API shall expose run progress and
    completed/total case counts.
-   **FR-040 (P1):** The system shall support scheduled evaluations.
-   **FR-041 (P2):** The system may support streaming run events over
    Server-Sent Events or WebSockets.

### 3.5 Metrics and scoring

-   **FR-050 (P0):** The platform shall support exact-match and
    normalized text comparison metrics.
-   **FR-051 (P0):** The platform shall calculate latency statistics,
    including mean, median, p95, and maximum, when enough observations
    exist.
-   **FR-052 (P0):** The platform shall capture input/output token
    counts when returned by the provider.
-   **FR-053 (P0):** The platform shall estimate model-call cost using a
    versioned pricing configuration and available token usage.
-   **FR-054 (P0):** The platform shall clearly label estimated costs
    and report when usage or pricing data is unavailable.
-   **FR-055 (P0):** The platform shall support an LLM-as-judge metric
    for criteria such as relevance, correctness,
    groundedness/faithfulness, and instruction adherence.
-   **FR-056 (P0):** Judge outputs shall include a score, a short
    rationale, judge model ID, rubric version, and error status.
-   **FR-057 (P0):** The platform shall support retrieval metrics when
    reference/relevant documents are supplied, including Precision@k,
    Recall@k, and reciprocal rank where applicable.
-   **FR-058 (P0):** The platform shall distinguish answer-quality
    metrics from retrieval-quality metrics.
-   **FR-059 (P0):** Metrics that require missing inputs shall return
    `not_applicable` or an explicit error rather than inventing a score.
-   **FR-060 (P1):** The platform shall support semantic similarity
    using a configured embedding model.
-   **FR-061 (P1):** The platform shall support configurable metric
    weights for a composite score, while displaying component scores
    separately.
-   **FR-062 (P1):** The platform shall support RAG metrics such as
    context relevance and answer faithfulness using a documented
    implementation or evaluator.
-   **FR-063 (P1):** The platform shall support repeat runs to estimate
    variance for nondeterministic models.
-   **FR-064 (P2):** The platform may support user-defined metric
    plugins behind a documented, safe interface.

**Metric interpretation rules** - Exact match is useful for structured
outputs but is not a universal measure of answer quality. - LLM-as-judge
results are estimates and may be biased or inconsistent. Store the
rubric and judge model, and allow human review. - Faithfulness requires
the answer and the context used to produce it. If context is missing,
the metric must be not applicable. - Retrieval precision/recall require
a definition of relevant retrieved/reference items. Do not calculate
them from arbitrary text alone. - p95 is meaningful only with a
sufficient number of observations; label small-sample statistics. - Cost
is estimated, not guaranteed, and depends on pricing configuration and
provider usage reporting.

### 3.6 Results and reporting

-   **FR-070 (P0):** Users shall view run-level summary metrics by
    model.
-   **FR-071 (P0):** Users shall inspect each case's input, expected
    answer, model output, metric results, latency, usage, cost estimate,
    and error.
-   **FR-072 (P0):** Users shall filter results by model, metric,
    status, score threshold, and tag where available.
-   **FR-073 (P0):** Users shall export run results as JSON and CSV.
-   **FR-074 (P1):** Users shall export a human-readable Markdown
    report.
-   **FR-075 (P1):** Reports shall include run ID, dataset version,
    model/provider IDs, metric versions, timestamp, and configuration
    summary.
-   **FR-076 (P1):** The system shall identify top failures and
    regressions in reports.

### 3.7 Comparisons and regression detection

-   **FR-080 (P0):** Users shall compare two completed runs.
-   **FR-081 (P0):** Comparisons shall align cases by stable case ID and
    compare only compatible metrics/configurations.
-   **FR-082 (P0):** The comparison shall show score deltas, latency
    deltas, cost deltas, newly failing cases, and recovered cases.
-   **FR-083 (P0):** Users shall define gates such as minimum average
    judge score, minimum retrieval recall, maximum error rate, maximum
    p95 latency, and maximum estimated cost.
-   **FR-084 (P0):** A gate shall return pass/fail plus machine-readable
    reasons for every failed condition.
-   **FR-085 (P0):** The system shall support absolute thresholds and
    baseline-relative regression thresholds.
-   **FR-086 (P0):** Missing metrics shall not silently pass a gate;
    policy shall explicitly choose `fail`, `skip`, or `warn`.
-   **FR-087 (P1):** Users shall save named baselines for repeated
    comparisons.
-   **FR-088 (P1):** The platform shall allow per-tag or per-case gates.

### 3.8 CLI and CI integration

-   **FR-090 (P0):** The CLI shall validate a dataset/configuration
    without making model calls.
-   **FR-091 (P0):** The CLI shall run an evaluation from a
    configuration file.
-   **FR-092 (P0):** The CLI shall print a concise summary and
    optionally write JSON/Markdown reports.
-   **FR-093 (P0):** The CLI shall return exit code `0` when gates pass
    and a non-zero code when gates fail or execution errors occur.
-   **FR-094 (P0):** Documentation shall include a GitHub Actions
    workflow example.
-   **FR-095 (P1):** The CLI shall optionally send results to a running
    platform API.
-   **FR-096 (P1):** The CLI shall support comparing against a baseline
    run or saved baseline.

### 3.9 Dashboard and user experience

-   **FR-100 (P0):** The UI shall show projects, datasets, runs, and run
    detail pages.
-   **FR-101 (P0):** The UI shall show clear loading, empty, validation,
    error, and success states.
-   **FR-102 (P0):** The UI shall present model comparisons using
    readable tables and charts.
-   **FR-103 (P1):** The UI shall support creating datasets and run
    configurations without manually editing JSON.
-   **FR-104 (P1):** The UI shall provide accessible labels, keyboard
    navigation, and responsive layouts.

### 3.10 Auditability and observability

-   **FR-110 (P0):** The system shall use structured application logs
    with request/run/case correlation IDs.
-   **FR-111 (P0):** Each run shall preserve enough metadata to explain
    how scores were generated.
-   **FR-112 (P0):** Secrets, authorization headers, and sensitive
    prompt content shall not be logged by default.
-   **FR-113 (P1):** The platform shall expose health and readiness
    endpoints.
-   **FR-114 (P1):** The platform shall track its own worker failures,
    queue depth, provider error rates, and run durations.

------------------------------------------------------------------------

## 4. Non-functional requirements

-   **NFR-001 Reliability:** A single case failure must not erase
    successful results from other cases. Partial runs must be clearly
    marked.
-   **NFR-002 Reproducibility:** Store dataset snapshot/version,
    target/model ID, prompt/config hash, generation parameters,
    metric/rubric versions, pricing version, and software version.
-   **NFR-003 Performance:** For local development, ordinary list/detail
    API requests should generally respond within 500 ms at modest
    dataset sizes, excluding external model calls. This is a target to
    measure, not a guarantee.
-   **NFR-004 Scalability:** Background workers and bounded concurrency
    shall allow case processing without blocking the API. Initial
    target: 1,000 cases per run with configurable limits; validate with
    load tests.
-   **NFR-005 Security:** Validate all inputs; keep credentials in
    environment variables or secret storage; redact secrets; restrict
    custom target URLs to reduce SSRF risk.
-   **NFR-006 Privacy:** Treat prompts, completions, retrieved context,
    and uploaded datasets as potentially sensitive. Document storage and
    retention behavior.
-   **NFR-007 Maintainability:** Separate API, domain logic, provider
    adapters, metric implementations, persistence, workers, and UI.
-   **NFR-008 Testability:** Business logic and metrics shall be
    testable without external network calls using fake providers and
    deterministic fixtures.
-   **NFR-009 Portability:** The MVP shall run on Windows, macOS, and
    Linux using Python and Docker-compatible services.
-   **NFR-010 Observability:** Errors shall include actionable messages
    and correlation identifiers without exposing secrets.
-   **NFR-011 Usability:** A new developer shall be able to start the
    app and run a demo evaluation by following the README.
-   **NFR-012 Accessibility:** Core UI flows should support keyboard
    operation, clear contrast, and semantic controls.
-   **NFR-013 Cost control:** Set request timeouts, concurrency caps,
    maximum dataset size, optional per-run spend limits, and judge-call
    limits.
-   **NFR-014 Data integrity:** Use database transactions for run state
    transitions and unique constraints for identifiers.
-   **NFR-015 Compatibility:** Version public API routes and
    dataset/config schemas.
-   **NFR-016 Graceful degradation:** If pricing, token usage, judge
    scoring, or embeddings are unavailable, report the missing data
    explicitly and continue where possible.
-   **NFR-017 Resource efficiency:** Avoid loading entire large datasets
    into memory when streaming or chunked processing is practical.
-   **NFR-018 Documentation:** Document metric formulas, known
    limitations, environment configuration, migrations, backups, and
    deployment assumptions.

------------------------------------------------------------------------

## 5. Technical requirements and proposed stack

### 5.1 Recommended architecture

Use a modular monolith initially, with a separate background worker.
This is simpler to run and demonstrate than microservices while
retaining clear boundaries.

``` text
Browser UI / CLI / GitHub Actions
             |
             v
        FastAPI REST API
             |
   Application / Domain Services
   |        |         |        |
Datasets  Runs     Metrics  Comparisons/Gates
   |        |         |        |
   +--------+---------+--------+
                    |
             PostgreSQL
                    |
             Redis Queue
                    |
             Background Worker
                    |
        Provider / Target Adapters
        |          |          |
    Hosted LLM  Compatible API  Custom App API
```

### 5.2 Stack

**Backend** - Python 3.12+ - FastAPI - Pydantic v2 for request/config
validation - SQLAlchemy 2.x - Alembic migrations - PostgreSQL 16+ -
Redis for queueing and optional cache - Celery worker for background
runs (or a similarly mature queue worker; choose one and standardize) -
HTTPX for async HTTP calls - Tenacity or equivalent for bounded retry
policies

**Evaluation** - A project-owned metric interface and implementations
for core metrics - Optional integration with RAGAS/DeepEval for selected
advanced metrics, behind adapters - Provider SDKs behind a common
adapter interface - Token/cost estimation from provider usage and a
versioned pricing table - pytest for unit/integration tests

**Frontend** - React + TypeScript + Vite - A consistent component
library or simple reusable components - Recharts or an equivalent
charting library - OpenAPI-generated or manually typed API client

**Developer tooling and deployment** - Docker and Docker Compose - Ruff
for linting/formatting - mypy or pyright for type checks - pytest +
coverage - GitHub Actions - Structured JSON logging - `.env.example`;
never commit `.env`

### 5.3 Architecture principles

-   Keep metric functions independent from FastAPI and database code.
-   Keep provider SDK details inside adapters.
-   Use typed domain objects for cases, outputs, metrics, and run
    states.
-   Store run snapshots rather than relying on mutable current dataset
    definitions.
-   Make external model calls asynchronous where practical and bound
    concurrency.
-   Keep user-supplied model output as untrusted data.
-   Never execute generated text as code.
-   Use explicit timeouts and cancellation handling.
-   Store raw prompts/completions only as required and make retention
    configurable.
-   Prefer clear, testable code over premature abstraction.

### 5.4 Initial database entities

**Project** - `id` UUID primary key - `name`, `description` -
`settings_json` - `created_at`, `updated_at`, `archived_at`

**Dataset** - `id` UUID - `project_id` foreign key - `name`,
`description` - `current_version` - `created_at`, `updated_at`

**DatasetVersion** - `id` UUID - `dataset_id` foreign key -
`version_number` - `schema_version` - `cases_json` or normalized child
rows - `content_hash` - `created_at`

**EvaluationCase** (use normalized rows if filtering/querying individual
cases is important) - `id` UUID - `dataset_version_id` foreign key -
`case_key` stable string - `input_json` - `expected_output` -
`reference_context` - `retrieved_contexts_json` - `tags_json`,
`metadata_json`

**ModelConfig** - `id` UUID - `project_id` foreign key - `name`,
`provider`, `model_id` - `parameters_json` - `secret_reference` (not the
secret value) - `created_at`, `updated_at`

**EvaluationRun** - `id` UUID - `project_id`, `dataset_version_id` -
`status` - `config_snapshot_json` - `started_at`, `finished_at` -
`total_cases`, `completed_cases`, `failed_cases` - `created_at`,
`created_by` (optional for single-user MVP)

**CaseResult** - `id` UUID - `run_id` foreign key - `case_key` -
`model_config_snapshot_json` - `status` - `input_snapshot_json` -
`expected_output_snapshot` - `actual_output` - `latency_ms` -
`input_tokens`, `output_tokens` - `estimated_cost` - `error_code`,
`error_message_redacted` - `created_at`

**MetricResult** - `id` UUID - `case_result_id` foreign key -
`metric_name`, `metric_version` - `score` nullable numeric - `status`
(`scored`, `not_applicable`, `error`) - `details_json` - `created_at`

**Comparison** - `id` UUID - `baseline_run_id`, `candidate_run_id` -
`summary_json` - `created_at`

**EvaluationGate** - `id` UUID - `project_id` - `name` - `rules_json` -
`missing_metric_policy` - `created_at`, `updated_at`

**PricingVersion** - `id` UUID - `provider`, `model_id` -
`input_price_per_million_tokens` - `output_price_per_million_tokens` -
`currency` - `effective_from`, `effective_to` - `source_note` -
`created_at`

**Design note:** Use normalized rows for cases/results when filtering
and pagination matter. JSON columns are appropriate for snapshots and
flexible provider/metric details. Add indexes for project IDs,
dataset/run IDs, statuses, case keys, and timestamps.

### 5.5 Provider adapter contract

Each adapter should implement an interface conceptually equivalent to:

``` python
class ModelAdapter(Protocol):
    async def generate(
        self,
        *,
        input_data: dict,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse: ...
```

`NormalizedModelResponse` should contain: - `output_text` - `provider` -
`model_id` - `input_tokens` (nullable) - `output_tokens` (nullable) -
`provider_request_id` (nullable) - `finish_reason` (nullable) -
`raw_metadata` with sensitive fields removed

Provider-specific exceptions must be translated to stable internal error
categories such as `rate_limited`, `timeout`, `authentication_failed`,
`provider_unavailable`, and `invalid_request`.

### 5.6 Metric interface

A metric implementation should declare: - stable name and version; -
required inputs; - score range and direction (higher/lower is better); -
configuration schema; - result status and explanatory details.

Conceptual result:

``` json
{
  "metric_name": "exact_match",
  "metric_version": "1.0",
  "score": 1.0,
  "status": "scored",
  "details": {
    "normalized_expected": "paris",
    "normalized_actual": "paris"
  }
}
```

Do not let a metric silently interpret absent data as a zero score. Use
`not_applicable` when inputs are insufficient and `error` when
computation fails.

### 5.7 Run lifecycle

1.  Validate request and referenced dataset/model/metric configurations.
2.  Create immutable run configuration snapshot.
3.  Enqueue background work.
4.  Load dataset cases in bounded batches.
5.  Call each selected model/target with timeouts and concurrency
    limits.
6.  Persist output, usage, latency, and errors.
7.  Calculate deterministic metrics.
8.  Run configured judge/embedding metrics under separate limits.
9.  Aggregate summaries and apply gates.
10. Mark run completed or failed, preserving partial results.
11. Emit structured logs and expose final report.

### 5.8 Configuration and environment

Create `.env.example` with documented placeholders such as:

``` dotenv
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=postgresql+psycopg://eval_user:change_me@localhost:5432/llm_eval
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=replace_with_a_long_random_value
LOG_LEVEL=INFO

# Optional provider credentials; configure only providers you use.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_API_KEY=

DEFAULT_REQUEST_TIMEOUT_SECONDS=60
MAX_RUN_CONCURRENCY=5
MAX_CASES_PER_RUN=1000
MAX_RETRIES=2
STORE_RAW_CONTENT=true
RAW_CONTENT_RETENTION_DAYS=30
```

The application must validate required settings at startup and provide
safe, actionable configuration errors. Do not include real keys in
examples, screenshots, test fixtures, or Git history.

------------------------------------------------------------------------

## 6. API requirements

### 6.1 API conventions

-   Base path: `/api/v1`
-   Format: JSON over HTTPS in deployed environments; HTTP is acceptable
    for local development.
-   IDs: UUID strings.
-   Timestamps: ISO 8601 UTC.
-   Pagination: `limit` and `offset` initially; enforce a maximum limit.
-   Errors: consistent JSON error envelope with stable `code`, safe
    `message`, optional `details`, and `request_id`.
-   Long-running operations return `202 Accepted` with a resource ID.
-   API docs: FastAPI-generated OpenAPI at `/docs` and `/openapi.json`.
-   Versioning: breaking changes require a new API version.
-   Authentication: local single-user development may begin without
    accounts, but any remotely deployed instance must require
    authentication. Never expose an unauthenticated public endpoint that
    can spend provider credits.

### 6.2 Error response format

``` json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The dataset contains invalid cases.",
    "details": [
      {"field": "cases[2].input", "message": "Field is required"}
    ],
    "request_id": "req_example"
  }
}
```

### 6.3 Endpoint inventory

#### Health

  Method   Path              Purpose                    Success
  -------- ----------------- -------------------------- ----------------
  GET      `/health/live`    Process liveness           `200`
  GET      `/health/ready`   Database/queue readiness   `200` or `503`

#### Projects

  ---------------------------------------------------------------------------------------
  Method            Path                              Purpose           Success
  ----------------- --------------------------------- ----------------- -----------------
  POST              `/api/v1/projects`                Create project    `201`

  GET               `/api/v1/projects`                List projects     `200`

  GET               `/api/v1/projects/{project_id}`   Get project       `200`

  PATCH             `/api/v1/projects/{project_id}`   Update project    `200`

  DELETE            `/api/v1/projects/{project_id}`   Archive/delete    `204`
                                                      project according 
                                                      to policy         
  ---------------------------------------------------------------------------------------

#### Datasets

  -----------------------------------------------------------------------------------------------------------
  Method            Path                                                  Purpose           Success
  ----------------- ----------------------------------------------------- ----------------- -----------------
  POST              `/api/v1/projects/{project_id}/datasets`              Create dataset    `201`

  GET               `/api/v1/projects/{project_id}/datasets`              List datasets     `200`

  GET               `/api/v1/datasets/{dataset_id}`                       Get dataset       `200`
                                                                          metadata          

  PATCH             `/api/v1/datasets/{dataset_id}`                       Update metadata   `200`

  POST              `/api/v1/datasets/{dataset_id}/versions`              Create immutable  `201`
                                                                          version           

  GET               `/api/v1/datasets/{dataset_id}/versions`              List versions     `200`

  GET               `/api/v1/datasets/{dataset_id}/versions/{version}`    Get version/cases `200`

  POST              `/api/v1/datasets/import`                             Import JSON/JSONL `201`

  GET               `/api/v1/datasets/{dataset_id}/export?format=jsonl`   Export dataset    `200`
  -----------------------------------------------------------------------------------------------------------

#### Model configurations

  -----------------------------------------------------------------------------------------------
  Method            Path                                      Purpose           Success
  ----------------- ----------------------------------------- ----------------- -----------------
  POST              `/api/v1/projects/{project_id}/models`    Create model      `201`
                                                              configuration     

  GET               `/api/v1/projects/{project_id}/models`    List model        `200`
                                                              configurations    
                                                              (redacted)        

  GET               `/api/v1/models/{model_config_id}`        Get model         `200`
                                                              configuration     
                                                              (redacted)        

  PATCH             `/api/v1/models/{model_config_id}`        Update            `200`
                                                              configuration     

  POST              `/api/v1/models/{model_config_id}/test`   Test provider     `200` or `502`
                                                              connectivity      
  -----------------------------------------------------------------------------------------------

#### Runs and results

  ------------------------------------------------------------------------------------------------------
  Method            Path                                             Purpose           Success
  ----------------- ------------------------------------------------ ----------------- -----------------
  POST              `/api/v1/runs`                                   Start run         `202`

  GET               `/api/v1/runs`                                   List/filter runs  `200`

  GET               `/api/v1/runs/{run_id}`                          Run summary and   `200`
                                                                     status            

  POST              `/api/v1/runs/{run_id}/cancel`                   Request           `202`
                                                                     cancellation      

  GET               `/api/v1/runs/{run_id}/results`                  Paginated case    `200`
                                                                     results           

  GET               `/api/v1/runs/{run_id}/results/{result_id}`      Result detail     `200`

  GET               `/api/v1/runs/{run_id}/report?format=json`       Export report     `200`

  GET               `/api/v1/runs/{run_id}/report?format=csv`        Export CSV        `200`

  GET               `/api/v1/runs/{run_id}/report?format=markdown`   Export Markdown   `200`
  ------------------------------------------------------------------------------------------------------

#### Metrics, comparisons, and gates

  ---------------------------------------------------------------------------------------------
  Method            Path                                    Purpose           Success
  ----------------- --------------------------------------- ----------------- -----------------
  GET               `/api/v1/metrics`                       List metrics and  `200`
                                                            requirements      

  POST              `/api/v1/comparisons`                   Compare two runs  `201`

  GET               `/api/v1/comparisons/{comparison_id}`   Get comparison    `200`

  POST              `/api/v1/gates/evaluate`                Evaluate gate     `200`
                                                            rules against a   
                                                            run               

  POST              `/api/v1/projects/{project_id}/gates`   Save gate         `201`

  GET               `/api/v1/projects/{project_id}/gates`   List gates        `200`

  PATCH             `/api/v1/gates/{gate_id}`               Update gate       `200`
  ---------------------------------------------------------------------------------------------

### 6.4 Example: create dataset

`POST /api/v1/projects/{project_id}/datasets`

``` json
{
  "name": "support-faq-regression",
  "description": "Regression cases for a support assistant",
  "cases": [
    {
      "case_key": "faq-001",
      "input": {"question": "How do I reset my password?"},
      "expected_output": "Use the password reset link on the sign-in page.",
      "reference_context": "Users can reset their password from the sign-in page.",
      "retrieved_contexts": [
        {"document_id": "account-help", "text": "Password reset instructions..."}
      ],
      "tags": ["support", "account"]
    }
  ]
}
```

Response `201 Created`:

``` json
{
  "id": "uuid",
  "name": "support-faq-regression",
  "current_version": 1,
  "case_count": 1,
  "created_at": "2026-10-26T12:00:00Z"
}
```

### 6.5 Example: start an evaluation run

`POST /api/v1/runs`

``` json
{
  "project_id": "project-uuid",
  "dataset_id": "dataset-uuid",
  "dataset_version": 1,
  "model_config_ids": ["model-config-a", "model-config-b"],
  "metrics": [
    {"name": "exact_match", "version": "1.0"},
    {"name": "llm_judge_correctness", "version": "1.0", "config": {"scale": 5}},
    {"name": "latency", "version": "1.0"},
    {"name": "estimated_cost", "version": "1.0"}
  ],
  "run_config": {
    "max_concurrency": 4,
    "timeout_seconds": 60,
    "max_retries": 2,
    "judge_model_config_id": "judge-model-uuid"
  },
  "gate_id": "optional-gate-uuid"
}
```

Response `202 Accepted`:

``` json
{
  "run_id": "run-uuid",
  "status": "queued",
  "status_url": "/api/v1/runs/run-uuid"
}
```

### 6.6 Example: run summary

`GET /api/v1/runs/{run_id}`

``` json
{
  "id": "run-uuid",
  "status": "completed",
  "dataset": {"id": "dataset-uuid", "version": 1},
  "models": [
    {
      "provider": "example-provider",
      "model_id": "example-model",
      "case_count": 20,
      "success_count": 19,
      "error_count": 1,
      "metrics": {
        "llm_judge_correctness": {"mean": 4.2, "count": 19},
        "latency_ms": {"mean": 820, "median": 760, "p95": 1400},
        "estimated_cost_usd": {"total": 0.04, "is_estimate": true}
      }
    }
  ],
  "started_at": "2026-10-26T12:00:00Z",
  "finished_at": "2026-10-26T12:01:20Z"
}
```

The values above are illustrative schema examples only, not performance
claims.

### 6.7 Example: evaluate a gate

`POST /api/v1/gates/evaluate`

``` json
{
  "run_id": "run-uuid",
  "rules": [
    {"metric": "llm_judge_correctness", "aggregation": "mean", "operator": "gte", "threshold": 4.0},
    {"metric": "error_rate", "aggregation": "overall", "operator": "lte", "threshold": 0.02},
    {"metric": "latency_ms", "aggregation": "p95", "operator": "lte", "threshold": 2500}
  ],
  "missing_metric_policy": "fail"
}
```

Response `200 OK`:

``` json
{
  "passed": false,
  "results": [
    {"rule": "llm_judge_correctness", "passed": true, "actual": 4.2, "threshold": 4.0},
    {"rule": "error_rate", "passed": false, "actual": 0.05, "threshold": 0.02, "reason": "Error rate exceeds threshold"},
    {"rule": "latency_ms", "passed": true, "actual": 1400, "threshold": 2500}
  ]
}
```

### 6.8 Validation and API security

-   Validate all path, query, and body inputs with Pydantic.
-   Set maximum request body and upload sizes.
-   Restrict dataset case count and text length.
-   Apply timeouts and rate limits to expensive operations.
-   Do not return provider API keys in responses.
-   If a custom URL target is enabled, block loopback, link-local,
    private-network, metadata-service, and unsupported schemes by
    default; validate DNS/IP resolution and redirects to mitigate SSRF.
    Allow an explicit safe development mode only for local testing.
-   Avoid accepting arbitrary HTTP headers without filtering
    authorization-sensitive values.
-   For deployed use, implement authentication and project-level
    authorization before public access.
-   Do not render model output as trusted HTML.
-   Keep CORS origins explicit in deployment configuration.

------------------------------------------------------------------------

## 7. CLI requirements

Proposed command interface:

``` bash
# Validate dataset/config without making provider calls
llm-eval validate --config evals/config.yaml

# Run evaluation and save report
llm-eval run --config evals/config.yaml --output reports/latest.json

# Compare two reports/runs
llm-eval compare --baseline reports/baseline.json --candidate reports/latest.json

# Evaluate release gates
llm-eval gate --report reports/latest.json --rules evals/gates.yaml

# Print version and available metrics
llm-eval --version
llm-eval metrics list
```

Requirements: - Commands must have helpful `--help` output. - Config
errors must identify the file and field. - The CLI must not print
secrets. - Exit codes: `0` success/pass; `1` gate failure; `2` invalid
configuration/input; `3` provider/run failure; `4` unexpected internal
error. - Provide machine-readable JSON output for CI. - Keep CLI
behavior consistent between local runs and CI.

------------------------------------------------------------------------

## 8. Dataset and configuration formats

### 8.1 Dataset JSON example

``` json
{
  "schema_version": "1.0",
  "name": "basic-qa",
  "cases": [
    {
      "case_key": "capital-001",
      "input": {"question": "What is the capital of France?"},
      "expected_output": "Paris",
      "reference_context": null,
      "retrieved_contexts": [],
      "tags": ["geography"],
      "metadata": {}
    }
  ]
}
```

### 8.2 Evaluation configuration YAML example

``` yaml
project: demo-project
dataset: ./datasets/basic-qa.json
models:
  - name: provider-a
    provider: openai_compatible
    model_id: example-model
    base_url_env: OPENAI_COMPATIBLE_BASE_URL
    api_key_env: OPENAI_COMPATIBLE_API_KEY
    parameters:
      temperature: 0
      max_tokens: 300
metrics:
  - name: exact_match
  - name: latency
  - name: estimated_cost
run:
  timeout_seconds: 60
  max_concurrency: 3
  max_retries: 1
report:
  json: ./reports/run.json
  markdown: ./reports/run.md
```

Configuration validation must reject unknown or unsupported options
unless explicitly allowed by a schema version.

------------------------------------------------------------------------

## 9. Testing requirements

### 9.1 Unit tests

-   Metric formulas and edge cases.
-   Input normalization.
-   Cost calculations for known pricing fixtures.
-   Run state transitions.
-   Gate comparisons, missing metric policies, and regression deltas.
-   Provider error normalization.
-   Dataset import validation.
-   Redaction of credentials and sensitive headers.

### 9.2 Integration tests

-   API CRUD flows against a test database.
-   Dataset import/export round trips.
-   Worker processes a run using a deterministic fake provider.
-   Partial failure preserves successful case results.
-   Comparison and gate endpoints produce expected output.
-   Cancellation and timeout behavior.
-   Migration up/down checks where practical.

### 9.3 End-to-end tests

-   Start the stack with Docker Compose.
-   Create/import a dataset.
-   Run the demo model.
-   View results and compare two runs.
-   Confirm CI exit code fails when a deliberate gate is violated.

### 9.4 Evaluation test fixtures

-   Known-answer factual questions.
-   Exact-match structured outputs.
-   Supported and unsupported answers for groundedness checks.
-   Retrieval cases with known relevant document IDs.
-   Empty output, malformed output, timeout, rate limit, and provider
    error cases.
-   Long and multilingual inputs.
-   Cases where judge scoring is not applicable.

### 9.5 CI checks

On pull requests and pushes: 1. install locked dependencies; 2. run
formatting/lint checks; 3. run static type checks where configured; 4.
run unit tests; 5. run integration tests with service containers or
Docker Compose; 6. build backend and frontend; 7. run a small
deterministic evaluation gate using a fake provider; 8. upload test and
evaluation reports as artifacts.

Do not require paid LLM credentials for ordinary pull-request CI. Live
provider smoke tests should be optional and manually triggered or run in
a protected scheduled workflow.

------------------------------------------------------------------------

## 10. Security, privacy, and responsible evaluation

-   Treat prompts, completions, documents, and retrieved contexts as
    confidential by default.
-   Never commit `.env`, credentials, production datasets, or customer
    transcripts.
-   Include a `.gitignore` and secret-scanning workflow.
-   Redact API keys, authorization headers, and known sensitive fields
    from logs.
-   Limit access to stored prompts and outputs if authentication is
    enabled.
-   Document data retention and deletion behavior.
-   Allow raw content storage to be disabled or retention to be
    shortened.
-   Never execute model-generated code or commands.
-   Restrict custom endpoint targets to mitigate SSRF.
-   Use bounded concurrency, timeouts, retries, and per-run cost limits.
-   Label LLM-as-judge outputs as estimates; preserve judge rubric and
    model metadata.
-   Avoid using a single composite score as the sole release decision.
-   For high-impact decisions, require human review and domain-specific
    validation.
-   Include license notices for datasets, dependencies, and any copied
    examples.

------------------------------------------------------------------------

## 11. Deployment and operations

### Local development

-   Docker Compose for PostgreSQL and Redis.
-   Backend API and worker started by documented commands or Compose
    services.
-   Frontend started through its package manager.
-   Demo evaluation works with a fake provider without external
    credentials.
-   Optional hosted model providers are configured using environment
    variables.

### Portfolio deployment (optional)

-   Deploy API and UI only after authentication is implemented.
-   Use managed PostgreSQL/Redis or appropriately secured instances.
-   Terminate TLS at a trusted reverse proxy/platform.
-   Store secrets in deployment environment/secret manager.
-   Configure allowed origins, request limits, log retention, and
    backups.
-   Disable unrestricted custom target URLs by default.
-   Set spend limits and alerting for provider usage.
-   Never expose database or Redis ports publicly.

### Operational health

-   `/health/live` verifies process liveness.
-   `/health/ready` verifies critical dependencies.
-   Logs include timestamp, severity, request ID, run ID, and case key
    where applicable.
-   Worker failure and stuck-run handling are documented.
-   Database migrations run as a deliberate deployment step.

------------------------------------------------------------------------

## 12. Acceptance criteria

The MVP is ready for a public portfolio release when all P0 criteria
below pass:

-   [ ] A clean clone can be installed using the README.
-   [ ] `.env.example` contains all required settings and no real
    secrets.
-   [ ] Docker Compose starts required infrastructure.
-   [ ] A demo evaluation runs without paid provider credentials.
-   [ ] JSON/JSONL dataset validation and import work.
-   [ ] Two model configurations can be evaluated on the same dataset.
-   [ ] Per-case outputs, errors, latency, and available usage are
    persisted.
-   [ ] Exact match, latency statistics, estimated cost, and at least
    one judge metric work.
-   [ ] Retrieval precision/recall work for cases with explicit
    relevance labels.
-   [ ] Missing metric inputs are clearly marked not applicable.
-   [ ] Run comparison identifies score changes and case regressions.
-   [ ] Gate failure returns a non-zero CLI exit code.
-   [ ] API and UI show run status, summary, and case details.
-   [ ] Tests cover core metrics, run orchestration, comparisons, and
    gates.
-   [ ] GitHub Actions passes on a clean pull request without paid model
    API keys.
-   [ ] README includes architecture, screenshots/demo instructions,
    limitations, and roadmap.
-   [ ] No credentials, sensitive data, or unlicensed datasets are
    committed.

------------------------------------------------------------------------

## 13. Implementation roadmap

### Phase 0 --- Repository foundation

-   Project skeleton, dependency management, linting, testing,
    `.env.example`, Docker Compose, CI.
-   Define schemas and architecture decision records.

### Phase 1 --- Deterministic evaluation core

-   Dataset schema and validation.
-   Fake provider and adapter interface.
-   Exact match, normalization, latency capture.
-   CLI validation and run commands.
-   JSON report export.

### Phase 2 --- API, persistence, and worker

-   PostgreSQL models and migrations.
-   Project/dataset/model/run endpoints.
-   Redis queue and background worker.
-   Case-level results and run status.

### Phase 3 --- Model providers and cost

-   One hosted provider adapter.
-   OpenAI-compatible adapter.
-   Usage capture, versioned pricing, estimated cost.
-   Timeouts, bounded retries, error normalization.

### Phase 4 --- Advanced metrics

-   LLM-as-judge with a versioned rubric.
-   Retrieval Precision@k, Recall@k, reciprocal rank.
-   Optional semantic similarity and RAG faithfulness adapters.
-   Metric-level not-applicable/error handling.

### Phase 5 --- Comparisons and quality gates

-   Run comparison and baseline.
-   Absolute and relative thresholds.
-   CLI gate command and CI workflow.
-   Regression report.

### Phase 6 --- Dashboard and polish

-   React/TypeScript dashboard.
-   Project, dataset, run, result, and comparison pages.
-   Charts, filters, report export.
-   Accessibility and responsive layout.

### Phase 7 --- Portfolio release

-   End-to-end tests, demo dataset, screenshots, architecture diagram.
-   Threat-model review, secret scan, dependency scan.
-   Complete README and short demo video/GIF.
-   Tag a release and pin the repository on GitHub.

------------------------------------------------------------------------

## 14. Risks and mitigations

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  LLM judge is inconsistent           Version rubrics, store judge
                                      metadata, use deterministic tests
                                      and human spot checks

  Provider price changes              Use versioned pricing entries, mark
                                      costs as estimates, expose pricing
                                      source/effective date

  API quotas/rate limits              Bounded concurrency, backoff for
                                      transient errors, per-provider
                                      limits

  A run consumes too much money       Case limits, spend budgets,
                                      judge-call budgets, cancellation

  Prompt or dataset changes           Immutable dataset snapshots and
  invalidate comparison               configuration hashes

  Custom endpoint creates SSRF risk   Disable by default or validate
                                      target addresses/redirects strictly

  Metrics are misinterpreted          Document formulas, required inputs,
                                      direction, limitations, and sample
                                      size

  CI depends on paid APIs             Use deterministic fake provider for
                                      default CI; live tests are optional

  Scope becomes too large             Complete P0 vertical slice before
                                      adding advanced metrics or
                                      scheduling
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 15. Definition of done for every feature

A feature is complete only when: 1. implementation follows the agreed
architecture; 2. input validation and error handling are present; 3.
unit tests cover success and failure paths; 4. integration tests exist
where persistence or external boundaries are involved; 5. logs do not
leak secrets; 6. API/CLI behavior is documented; 7. migrations and
configuration examples are updated; 8. relevant CI checks pass; 9.
README or developer docs explain how to use it; 10. the feature has been
run and verified rather than merely generated.

------------------------------------------------------------------------

## 16. Recommended first milestone

Start with a vertical slice that does not require a paid LLM account:

1.  Create a small JSON dataset.
2.  Implement a `ModelAdapter` protocol and deterministic fake adapter.
3.  Implement exact-match and latency metrics.
4.  Run all cases and produce a JSON report.
5.  Add a gate that fails if exact match is below a configured
    threshold.
6.  Add pytest coverage and GitHub Actions.
7.  Only then add the database, background worker, provider APIs, judge
    metrics, and UI.

This proves the core evaluation contract before adding infrastructure
and reduces the risk of building a visually polished dashboard around an
untested engine.
