# REST API (v1)

Base path: `/api/v1`. The OpenAPI schema and interactive docs are served at
`/openapi.json` and `/docs` while the API is running.

> **No authentication yet.** Anyone who can reach the API can create runs,
> and once real providers exist (Phase 3) runs can spend provider credits.
> Keep the API bound to `127.0.0.1`; Docker Compose already does this.

## Conventions

- JSON request and response bodies; IDs are UUIDs; timestamps are UTC ISO 8601.
- List endpoints are paginated with `limit` (1–200, default 50) and `offset`,
  and return `{"items": [...], "total": n, "limit": l, "offset": o}`.
- Unknown request fields are rejected (`422`).
- Every response carries an `X-Request-ID` header. Send your own (≤ 64 chars)
  to correlate client and server logs.
- Request bodies larger than `MAX_REQUEST_BYTES` (default 10 MB) get `413`.

### Errors

Every error uses one envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request is invalid.",
    "details": [{"field": "body.name", "message": "String should have at least 1 character"}],
    "request_id": "req_3f2c..."
  }
}
```

| Status | `code`                   | Meaning                                              |
|--------|--------------------------|------------------------------------------------------|
| 404    | `NOT_FOUND`              | The resource does not exist                          |
| 409    | `CONFLICT`               | Duplicate name, or an action invalid in this state   |
| 413    | `PAYLOAD_TOO_LARGE`      | Request body over the configured limit               |
| 422    | `VALIDATION_ERROR`       | Malformed or semantically invalid input              |
| 503    | `DEPENDENCY_UNAVAILABLE` | The run queue (Redis) could not accept the run       |
| 500    | `INTERNAL_ERROR`         | Unexpected server error; details are only in logs    |

Error messages never include secret values.

## Health

| Method | Path            | Description                                                      |
|--------|-----------------|------------------------------------------------------------------|
| GET    | `/health/live`  | The process is up.                                               |
| GET    | `/health/ready` | Database (and Redis, with Celery dispatch) reachable; else `503`. |

## Projects

| Method | Path                     | Description                                                  |
|--------|--------------------------|--------------------------------------------------------------|
| POST   | `/projects`              | Create (`name` is unique).                                   |
| GET    | `/projects`              | List; `include_archived=true` to include archived projects.  |
| GET    | `/projects/{id}`         | Get one.                                                     |
| PATCH  | `/projects/{id}`         | Update name, description, settings.                          |
| DELETE | `/projects/{id}`         | Archive (soft delete, `204`). Runs and results remain readable; new runs are refused. |

## Datasets

Datasets are versioned. Every change creates a new immutable version, and
runs pin an exact version together with its content hash.

| Method | Path                                    | Description |
|--------|-----------------------------------------|-------------|
| POST   | `/projects/{id}/datasets`               | Create with `name`, optional `description`, and `cases` (version 1). |
| GET    | `/projects/{id}/datasets`               | List datasets in a project. |
| POST   | `/datasets/import`                      | Multipart upload: `project_id`, `file` (`.json` or `.jsonl`), optional `name`. |
| GET    | `/datasets/{id}`                        | Get one, including the current version and case count. |
| PATCH  | `/datasets/{id}`                        | Rename or change the description (does not create a version). |
| POST   | `/datasets/{id}/versions`               | Add a version with a new `cases` list. |
| GET    | `/datasets/{id}/versions`               | List versions with content hashes. |
| GET    | `/datasets/{id}/versions/{n}`           | Version detail with paginated `cases`; filter with `tag` and `q` (case-key search). |
| GET    | `/datasets/{id}/export`                 | Download `format=jsonl` (default) or `json`; optional `version`. |

The case format matches the CLI (see the README's dataset example). Case
keys must be unique within a version. Datasets larger than
`MAX_CASES_PER_RUN` are rejected.

## Model configurations

| Method | Path                         | Description |
|--------|------------------------------|-------------|
| POST   | `/projects/{id}/models`      | Create: `name`, `provider`, `model_id`, `parameters`, optional `timeout_seconds`, `max_concurrency`, `secret_reference`. |
| GET    | `/projects/{id}/models`      | List. |
| GET    | `/models/{id}`               | Get one. |
| PATCH  | `/models/{id}`               | Update. Past runs are unaffected because they keep a snapshot. |
| POST   | `/models/{id}/test`          | Send one small probe request: `200` with `ok: true`, or `502` with the error category. **Billable for paid providers.** |

Provider parameters are validated against the provider's schema. Keys that
look like credentials (`api_key`, `token`, `secret`, `password`, ...) are
rejected anywhere in `parameters`. Credentials are referenced through
`secret_reference`, the *name* of an environment variable (for example
`OPENAI_API_KEY`) that the worker reads at run time. Only the `fake`
provider exists in this phase.

## Runs

| Method | Path                                | Description |
|--------|-------------------------------------|-------------|
| GET    | `/metrics`                          | Available metrics, versions, required inputs, score direction. |
| POST   | `/runs`                             | Start a run (`202`); returns `run_id` and `status_url`. |
| GET    | `/runs`                             | List; filter by `project_id` and `status`. |
| GET    | `/runs/{id}`                        | Status, progress, per-model summaries (once finished), config snapshot and hash. |
| POST   | `/runs/{id}/cancel`                 | Request cancellation (`202`); `409` if already finished. |
| GET    | `/runs/{id}/results`                | Case results; filter by `model_name`, `status` (`success`/`error`), `tag`, and `metric` with `min_score`/`max_score`. |
| GET    | `/runs/{id}/results/{result_id}`    | One case result with input, expected and actual output, metrics, and error. |
| GET    | `/runs/{id}/report`                 | `format=json` (default), `csv` or `markdown`; `409` until the run finishes. |

Start a run:

```json
POST /api/v1/runs
{
  "project_id": "…",
  "dataset_id": "…",
  "dataset_version": 2,
  "model_config_ids": ["…", "…"],
  "metrics": [{"name": "exact_match", "version": "1.0"}, {"name": "latency"}],
  "run_config": {"timeout_seconds": 30, "max_concurrency": 4, "max_retries": 1}
}
```

`dataset_version` defaults to the current version. Metric `version`, when
given, must match the implemented version. At most `MAX_MODELS_PER_RUN`
models are allowed per run.

### Run lifecycle

```text
queued ──> running ──> completed
   │          ├──────> cancelled   (cancellation observed before a case started)
   │          └──────> failed      (unrecoverable error; error_message is redacted)
   └─────> cancelled               (cancelled before a worker picked it up)
```

- The full configuration (model snapshots, metrics, run settings) is frozen at
  creation and hashed (`config_hash`). Later edits to models or datasets do
  not change existing runs.
- A worker claims a run atomically, so a duplicate queue delivery cannot
  execute it twice, and a late delivery cannot restart a cancelled run.
- Case results are committed as each one finishes, so progress is visible
  while the run is going and partial results survive failure or cancellation.
- Individual case failures (timeouts, provider errors) do not fail the run.
  They are recorded per case, excluded from quality metrics, and counted in
  `error_rate`. A run is `failed` only when the run itself cannot proceed.
- Cancellation stops before the next case. Cases already in flight finish.
- If the worker process dies mid-run, the run stays `running`. This phase does
  not detect stuck runs yet. Mark them by hand or rerun them; automatic
  recovery is planned.

### Report export

CSV has one row per (model, case) with `<metric>_score` and `<metric>_status`
columns. Cells that begin with `=`, `+`, `-`, `@`, a tab or a carriage return are prefixed with `'` so
spreadsheets do not run model output as a formula. The JSON report has the
same schema as the CLI's `llm-eval run --output` report.
