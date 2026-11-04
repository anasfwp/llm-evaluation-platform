# Operations

How to run and look after the Docker Compose stack. It is meant for one
computer: there is no login, so don't expose it to a network. See the
[threat model](threat-model.md) before deploying it anywhere else.

## Configuration

Copy `.env.example` to `.env`. Settings are validated when the API and worker
start, and a bad value stops startup with an error. Set `POSTGRES_PASSWORD`
before the database is first created. Provider API keys are read from the
environment and are never stored in the database.

## Upgrading

Back up first (see below), then:

``` bash
git pull
docker compose up -d --build
```

Your data lives in the `pgdata` volume and is kept. The `migrate` service
applies database migrations before the API and worker start. To check the
result:

``` bash
docker compose ps -a                          # migrate should show Exited (0)
docker compose exec api alembic current       # should end in (head)
```

## Backup and restore

The database holds everything worth keeping. Redis only holds the queue.

``` bash
# Back up
docker compose exec -T postgres pg_dump -U eval_user --clean --if-exists llm_eval > backup.sql

# Restore, replacing what is there
docker compose exec -T postgres psql -q -U eval_user -d llm_eval < backup.sql
```

Backups contain your prompts and model outputs, so store them as carefully as
the database. `docker compose down -v` deletes the database volume.

## Logs

The API and worker write one JSON object per line, apart from Celery's startup
banner. Lines carry `request_id`, `run_id` and `case_key` where they apply.
Secrets are redacted, and prompts and model outputs are not logged.

``` bash
docker compose logs -f worker
docker compose logs worker --no-log-prefix | grep '"run_id": "<run id>"'
```

Every API error response includes the `request_id` to search for.

## When a run gets stuck

| What you see | Why | What to do |
|---|---|---|
| Stays `queued` | The worker is down | Start it with `docker compose up -d worker`. Waiting runs then execute. |
| Stays `queued` after the worker is back | Redis lost the job, for example because its container was recreated | Cancel the run and start a new one. |
| Stays `running` with no progress | The worker died mid-run; nothing detects this yet | Mark it as failed (below) and start a new one. Results already saved are kept. |

To mark runs as failed when they have been running for over an hour and you
know no worker is processing them:

``` bash
docker compose exec postgres psql -U eval_user -d llm_eval -c "
  UPDATE evaluation_runs
  SET status = 'failed', error_message = 'worker died; marked by hand', finished_at = now()
  WHERE status = 'running' AND started_at < now() - interval '1 hour';"
```

Runs marked this way have no summary, so the run page shows only their case
results.

## Keeping and deleting data

Questions and answers are stored with results, with no retention window yet.

-   `DELETE /api/v1/projects/{id}` archives a project. Its data stays.
-   `DELETE /api/v1/datasets/{id}` works only if no run has used the dataset.
-   There is no API to delete runs.
-   To remove everything, run `docker compose down -v`.
