# Project Map --- LLM Evaluation and Monitoring Platform

**Purpose:** Repository layout, module responsibilities, dependencies,
and implementation order.\
**Companion document:** `REQUIREMENTS.md`\
**Status:** Proposed structure; adjust when implementation reveals a
concrete need.

------------------------------------------------------------------------

## 1. Repository structure

``` text
llm-evaluation-platform/
├── README.md
├── REQUIREMENTS.md
├── PROJECT_MAP.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
├── .gitignore
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── uv.lock
├── alembic.ini
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── health.py
│   │   │           ├── projects.py
│   │   │           ├── datasets.py
│   │   │           ├── models.py
│   │   │           ├── runs.py
│   │   │           ├── results.py
│   │   │           ├── metrics.py
│   │   │           ├── comparisons.py
│   │   │           └── gates.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── errors.py
│   │   │   ├── security.py
│   │   │   └── constants.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── datasets.py
│   │   │   ├── models.py
│   │   │   ├── runs.py
│   │   │   ├── metrics.py
│   │   │   └── gates.py
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   ├── project.py
│   │   │   ├── dataset.py
│   │   │   ├── model_config.py
│   │   │   ├── run.py
│   │   │   ├── result.py
│   │   │   ├── metric.py
│   │   │   ├── comparison.py
│   │   │   └── gate.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── base.py
│   │   │   ├── models/
│   │   │   │   ├── project.py
│   │   │   │   ├── dataset.py
│   │   │   │   ├── model_config.py
│   │   │   │   ├── evaluation_run.py
│   │   │   │   ├── case_result.py
│   │   │   │   ├── metric_result.py
│   │   │   │   ├── comparison.py
│   │   │   │   └── gate.py
│   │   │   └── repositories/
│   │   │       ├── projects.py
│   │   │       ├── datasets.py
│   │   │       ├── model_configs.py
│   │   │       ├── runs.py
│   │   │       ├── results.py
│   │   │       └── gates.py
│   │   ├── services/
│   │   │   ├── project_service.py
│   │   │   ├── dataset_service.py
│   │   │   ├── model_config_service.py
│   │   │   ├── run_service.py
│   │   │   ├── result_service.py
│   │   │   ├── comparison_service.py
│   │   │   ├── gate_service.py
│   │   │   └── report_service.py
│   │   ├── evaluation/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── runner.py
│   │   │   ├── context.py
│   │   │   ├── registry.py
│   │   │   ├── aggregation.py
│   │   │   ├── normalization.py
│   │   │   ├── cost.py
│   │   │   ├── comparison.py
│   │   │   ├── gates.py
│   │   │   └── metrics/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── exact_match.py
│   │   │       ├── text_similarity.py
│   │   │       ├── latency.py
│   │   │       ├── token_usage.py
│   │   │       ├── estimated_cost.py
│   │   │       ├── retrieval_precision.py
│   │   │       ├── retrieval_recall.py
│   │   │       ├── reciprocal_rank.py
│   │   │       ├── llm_judge.py
│   │   │       └── rag_faithfulness.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── fake.py
│   │   │   ├── openai_compatible.py
│   │   │   ├── hosted_provider.py
│   │   │   └── custom_http_target.py
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   └── tasks.py
│   │   ├── cli/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── validate.py
│   │   │   ├── run.py
│   │   │   ├── compare.py
│   │   │   └── gate.py
│   │   └── utils/
│   │       ├── ids.py
│   │       ├── time.py
│   │       ├── redaction.py
│   │       └── jsonl.py
│   │
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_exact_match.py
│       │   ├── test_retrieval_metrics.py
│       │   ├── test_cost.py
│       │   ├── test_gates.py
│       │   ├── test_comparison.py
│       │   ├── test_normalization.py
│       │   └── test_redaction.py
│       ├── integration/
│       │   ├── test_dataset_api.py
│       │   ├── test_run_worker.py
│       │   ├── test_results_api.py
│       │   └── test_gate_api.py
│       └── e2e/
│           └── test_demo_workflow.py
│
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   ├── client.ts
│       │   ├── projects.ts
│       │   ├── datasets.ts
│       │   ├── runs.ts
│       │   └── comparisons.ts
│       ├── components/
│       │   ├── layout/
│       │   ├── common/
│       │   ├── charts/
│       │   └── tables/
│       ├── pages/
│       │   ├── DashboardPage.tsx
│       │   ├── ProjectsPage.tsx
│       │   ├── ProjectDetailPage.tsx
│       │   ├── DatasetsPage.tsx
│       │   ├── DatasetDetailPage.tsx
│       │   ├── RunsPage.tsx
│       │   ├── RunDetailPage.tsx
│       │   ├── CompareRunsPage.tsx
│       │   └── SettingsPage.tsx
│       ├── hooks/
│       ├── types/
│       └── styles/
│
├── datasets/
│   ├── README.md
│   ├── demo_qa.json
│   └── demo_rag.json
│
├── evals/
│   ├── README.md
│   ├── demo_config.yaml
│   └── gates.example.yaml
│
├── reports/
│   └── .gitkeep
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── metrics.md
│   ├── security.md
│   ├── development.md
│   ├── deployment.md
│   ├── decisions/
│   │   ├── 0001-modular-monolith.md
│   │   ├── 0002-metric-result-statuses.md
│   │   └── 0003-cost-estimation.md
│   └── images/
│       └── .gitkeep
│
└── .github/
    ├── workflows/
    │   ├── ci.yml
    │   ├── evaluation-gate.yml
    │   └── dependency-review.yml
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md
```

**Important:** This is the intended full structure, not a requirement to
create every file on day one. Build in vertical slices and create files
when their phase begins. The early deterministic MVP can start with a
much smaller structure.

------------------------------------------------------------------------

## 2. Module responsibilities

### Backend API (`backend/app/api/`)

HTTP routing, request validation, response schemas, dependency
injection, and HTTP status codes. Keep business logic out of endpoint
functions.

### Core (`core/`)

Application settings, structured logging, error mapping,
redaction/security helpers, and shared constants.

### Domain (`domain/`)

Typed concepts and rules independent of FastAPI, SQLAlchemy, provider
SDKs, and the frontend.

### Schemas (`schemas/`)

Pydantic request/response models. These define the external API contract
and must not expose secrets or internal-only fields.

### Database (`db/`)

SQLAlchemy models, database sessions, migrations, and repository
queries. Repositories should own persistence operations, not evaluation
policy.

### Services (`services/`)

Application use cases such as creating datasets, starting runs,
cancelling runs, preparing reports, and saving comparisons.

### Evaluation engine (`evaluation/`)

Core value of the product. Owns the evaluation lifecycle, metric
registry, metric implementations, aggregation, cost calculations,
comparison logic, and gates. It should be unit-testable without starting
FastAPI or PostgreSQL.

### Providers (`providers/`)

Provider-specific calls hidden behind a common interface. Normalize
responses and errors. The fake provider must work without network access
or credentials.

### Workers (`workers/`)

Background tasks for evaluation runs. Tasks must be idempotent where
possible, use bounded retries, and persist state so interrupted work can
be diagnosed.

### CLI (`cli/`)

Command-line interface for dataset validation, running evaluations,
exporting reports, comparing runs, and applying gates. Reuse the
evaluation engine rather than reimplementing its logic.

### Frontend (`frontend/`)

Dashboard and user interactions. The frontend should consume the
versioned REST API and should not contain provider keys or evaluate
metrics independently.

### Datasets and evaluations

Small, redistributable demo fixtures and example configuration. Never
commit private customer data, real prompts containing secrets, or large
unlicensed datasets.

### Docs (`docs/`)

Architecture, metric definitions, API details, security, local
development, deployment, and architecture decision records.

------------------------------------------------------------------------

## 3. Dependency direction

Keep dependencies flowing inward:

``` text
API / CLI / Worker
        |
        v
Application Services
        |
        v
Domain + Evaluation Engine
        |
        +----> Provider interfaces
        |
        v
Repository interfaces
        |
        v
Database implementations
```

Practical rules: - Metric implementations must not import FastAPI
routers. - Provider adapters must not write directly to database
tables. - API endpoints call services; they do not run whole evaluations
in request handlers. - The CLI calls the same application/evaluation
services as the API. - Frontend code communicates through the API. -
Shared schemas should not import database sessions or provider SDK
objects.

------------------------------------------------------------------------

## 4. Core data flow

``` text
Dataset + Run Configuration
            |
            v
       Run Validator
            |
            v
     Create Run Snapshot
            |
            v
      Background Queue
            |
            v
      Evaluation Runner
            |
      +-----+------+
      |            |
      v            v
 Model Adapter  Metric Registry
      |            |
      v            v
 Normalized     Metric Results
 Model Output       |
      +------|------+
             v
      Persist Case Result
             |
             v
      Aggregate Run Metrics
             |
             v
       Evaluate Gates
             |
             v
   JSON / CSV / Markdown Report
             |
             v
     Dashboard / CLI / CI
```

------------------------------------------------------------------------

## 5. Minimal first-phase structure

Do not ask Claude Code to generate the entire tree at once. Begin with
this smaller vertical slice:

``` text
llm-evaluation-platform/
├── README.md
├── REQUIREMENTS.md
├── PROJECT_MAP.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── datasets/
│   └── demo_qa.json
├── evals/
│   └── demo_config.yaml
├── reports/
│   └── .gitkeep
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── evaluation/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── normalization.py
│   │   │   ├── aggregation.py
│   │   │   └── metrics/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── exact_match.py
│   │   │       └── latency.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── fake.py
│   │   └── cli/
│   │       ├── __init__.py
│   │       └── main.py
│   └── tests/
│       ├── unit/
│       │   ├── test_exact_match.py
│       │   └── test_engine.py
│       └── e2e/
│           └── test_demo_workflow.py
└── .github/
    └── workflows/
        └── ci.yml
```

Only add FastAPI, PostgreSQL, Redis, Celery, React, and hosted-provider
integrations after the deterministic evaluation engine and CLI tests
pass.

------------------------------------------------------------------------

## 6. File creation order

1.  `REQUIREMENTS.md`, `PROJECT_MAP.md`, `README.md`
2.  `pyproject.toml`, `.gitignore`, `.env.example`
3.  dataset schema and `datasets/demo_qa.json`
4.  provider contract and deterministic fake provider
5.  metric contract, exact match, normalization, latency
6.  evaluation engine and JSON report output
7.  unit tests and demo end-to-end test
8.  CLI commands and exit-code behavior
9.  GitHub Actions CI
10. FastAPI app, schemas, health endpoint
11. PostgreSQL models and Alembic migrations
12. dataset/project/model/run API
13. Redis queue and worker
14. hosted and OpenAI-compatible adapters
15. usage/cost calculations and judge/retrieval metrics
16. comparisons and gates
17. frontend dashboard
18. security hardening, docs, demo screenshots, release

------------------------------------------------------------------------

## 7. File ownership and contracts

  ---------------------------------------------------------------------------------
  Area                    Owns                              Must not own
  ----------------------- --------------------------------- -----------------------
  API endpoint            HTTP                              Metric formulas or
                          validation/status/serialization   provider SDK logic

  Service                 Use-case orchestration            Frontend state or raw
                                                            HTTP handling

  Evaluation engine       Evaluation order and result       Database connection
                          composition                       setup

  Metric                  One documented scoring rule       Network calls unless
                                                            explicitly a
                                                            judge/embedding metric

  Provider adapter        Model/target request and response Run aggregation or gate
                          normalization                     policy

  Repository              Database queries and persistence  LLM prompt construction
                                                            or scoring policy

  Worker                  Background task lifecycle         Duplicated evaluation
                                                            logic

  CLI                     Argument parsing, config loading, Separate metric
                          exit codes                        implementation

  Frontend                Visualization and user input      Secret management or
                                                            trusted scoring

  CI workflow             Repeatable quality checks         Required paid model
                                                            calls for every pull
                                                            request
  ---------------------------------------------------------------------------------

------------------------------------------------------------------------

## 8. Naming and coding conventions

-   Use `snake_case` for Python files, functions, and variables.
-   Use `PascalCase` for Python classes and TypeScript components.
-   Keep API route prefixes under `/api/v1`.
-   Use UUIDs for persisted resource IDs and stable string `case_key`
    values for test-case matching.
-   Use UTC timestamps internally and in API responses.
-   Use typed functions and explicit return types for public
    service/metric/provider interfaces.
-   Prefer small functions and clear names over deep inheritance trees.
-   Keep metric names stable; introduce a new metric version when
    scoring semantics change.
-   Keep database migrations committed and reviewed.
-   Keep test fixtures deterministic and small.
-   Do not commit generated reports by default unless they are curated
    demo artifacts.

------------------------------------------------------------------------

## 9. Configuration and secret handling

-   `.env` is local-only and must be ignored by Git.
-   `.env.example` documents keys with blank values or harmless
    placeholders.
-   Provider adapters read credentials from environment/configuration;
    they never return secrets through API responses.
-   Redact `Authorization`, API-key headers, and credential-like values
    from logs.
-   Store a secret reference or provider configuration identifier rather
    than copying raw credentials into run snapshots.
-   Do not place real API keys in Claude Code prompts, screenshots,
    issues, or commits.
-   The deterministic fake provider is the default for tests and public
    demos.

------------------------------------------------------------------------

## 10. Test strategy by layer

  -----------------------------------------------------------------------
  Layer                   Test approach           Network required?
  ----------------------- ----------------------- -----------------------
  Metrics                 pytest unit tests with  No
                          fixed inputs            

  Provider normalization  Fake SDK/HTTP responses No

  Evaluation engine       Deterministic fake      No
                          adapter                 

  CLI                     Temporary files and     No
                          exit-code assertions    

  API                     FastAPI                 No, unless a specific
                          TestClient/HTTPX with   integration test
                          test dependencies       

  Database                Isolated test           Local test service
                          PostgreSQL or test      
                          database                

  Worker                  Fake provider and test  Local test service
                          queue                   

  Live provider smoke     Protected/manual        Yes, optional
  test                    workflow                

  Frontend                Component and API-mock  No
                          tests                   

  End-to-end              Docker Compose demo     Local containers
                          workflow                
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 11. Architecture decision records to write

Create short records in `docs/decisions/` when these choices are
made: 1. Modular monolith plus separate worker versus microservices. 2.
Celery versus another background queue. 3. Normalized case/result tables
versus JSON-heavy storage. 4. Which metrics are native versus delegated
to RAGAS/DeepEval. 5. Pricing data source, versioning, and update
process. 6. LLM judge rubric format and versioning. 7. Authentication
approach before any public deployment. 8. Custom HTTP target
restrictions and SSRF mitigation.

Each record should include context, decision, alternatives,
consequences, and date.

------------------------------------------------------------------------

## 12. Claude Code implementation guardrails

Use Claude Code as an implementation assistant, but require it to: -
read `REQUIREMENTS.md` and `PROJECT_MAP.md` before changing
architecture; - implement one milestone at a time; - list files it plans
to create or modify before broad changes; - avoid generating every
planned file as empty boilerplate; - run tests and report actual command
results; - never claim a provider integration works without a verified
test; - preserve deterministic no-credential CI; - update docs and
`.env.example` when configuration changes; - never write secrets or
private datasets to the repository; - ask before adding expensive hosted
services or unnecessary infrastructure; - summarize the changes, test
evidence, limitations, and next step after each milestone.

------------------------------------------------------------------------

## 13. Definition of done for repository structure

The project map is implemented progressively when: - the first-phase
tree exists and its demo test passes; - modules follow the dependency
direction above; - API, worker, CLI, and UI reuse the same
evaluation/domain logic; - migrations and configuration are
version-controlled; - every active top-level directory has a documented
purpose; - no unexplained empty modules or unused abstractions remain; -
the README matches the actual repository and verified commands.
