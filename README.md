# LLM Evaluation and Monitoring Platform

Test your AI app before you ship it.

You give it a list of questions with the answers you expect. It sends the
questions to one or more AI models, scores every answer, and shows you
which model did better, which answers got worse, and whether the results
are good enough to release.

> **v0.1.1, portfolio project.** There is no login yet, so run it on your
> own computer only. The demo uses fake models, so its scores are
> examples, not benchmarks.

![Comparison page showing which metrics got worse and which questions started failing](docs/screenshots/comparison.png)

## What you can do with it

-   **Score answers**: exact match, word overlap, meaning similarity,
    speed, and estimated cost.
-   **Score RAG apps**: check whether the right documents were found and
    whether the answer sticks to them.
-   **Use an AI as a judge**: let a model rate answers from 1 to 5
    (treat these as estimates).
-   **Compare runs**: see what got better or worse against a saved
    baseline.
-   **Block bad releases**: set rules such as "accuracy must stay above
    80%" and fail the CI build when a rule breaks.
-   **Work the way you like**: a command-line tool, a REST API, or a web
    dashboard.

It works with Anthropic, OpenAI, and any OpenAI-compatible server. A
built-in **fake model** lets you try everything with no API key and no
internet.

## Try it in 2 minutes (no API key needed)

You need Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

``` bash
git clone <this repository's URL>
cd llm-evaluation-platform
uv sync --all-groups

uv run llm-eval run --config evals/demo_config.yaml
```

This scores two fake models on 21 questions and writes a report to
`reports/demo-run.md`. Open it to see the results.

More things to try:

``` bash
# Check for regressions against a saved baseline
uv run llm-eval compare --baseline evals/baselines/demo-baseline.json \
  --candidate reports/demo-run.json --fail-on-regression

# RAG demo: a model that sticks to the documents vs. one that makes things up
uv run llm-eval run --config evals/demo_rag_config.yaml --gates evals/gates.rag.yaml
```

Each command exits with `0` when everything passes and `1` when a rule
fails, so you can use it directly in CI.

## Run the dashboard

You also need Docker and Node.js 20+.

``` bash
cp .env.example .env              # Windows: copy .env.example .env
docker compose up -d --build      # starts the database, API and worker

cd frontend
npm ci
npm run dev                       # open http://127.0.0.1:5173
```

To fill it with demo data, run `uv run python scripts/seed_demo.py` from
the project folder.

![Starting a run, filtering results, and comparing against an earlier run](docs/screenshots/demo.gif)

| Project page | Run results |
|---|---|
| ![Project page with a quality trend chart and a list of runs](docs/screenshots/project-runs.png) | ![Run page with a chart for each metric and report downloads](docs/screenshots/run-summary.png) |

## Use your own data

Write your questions in a JSON file:

``` json
{
  "schema_version": "1.0",
  "name": "my-questions",
  "cases": [
    {
      "case_key": "capital-france",
      "input": {"question": "What is the capital of France?"},
      "expected_output": "Paris"
    }
  ]
}
```

Then copy `evals/demo_config.yaml`, point it at your file, and pick your
models and metrics. To use a real model, put its API key in `.env` (never
commit this file). See [`datasets/`](datasets/) for more examples and
[`docs/providers.md`](docs/providers.md) for model setup.

## How it works

```mermaid
flowchart LR
    UI["Dashboard"] --> API["API"]
    CLI["Command line"] --> ENG
    API --> ENG["Evaluation engine<br/>(scoring, comparing, rules)"]
    ENG --> M["AI models"]
    API --> DB[("Database")]
```

The command line and the API use the same engine, so results are the
same everywhere.

Built with Python (FastAPI, SQLAlchemy, Celery), PostgreSQL, Redis,
React, and TypeScript.

## Good to know

-   **No login yet.** Anyone who can reach the API can see results and
    start runs that cost money. Keep it on `127.0.0.1`.
-   **Scores are a guide, not proof.** No single number tells you an
    answer is correct. Check important results yourself.
-   **API keys stay private.** They are read from environment variables
    and are never saved, shown, or logged.
-   **Your data is stored.** Questions and answers are saved with the
    results, so don't use confidential data.

## Roadmap

These aren't built yet:

-   **Login and per-project access**, needed before running this anywhere
    but your own computer.
-   **Data controls**: a retention window and an option not to store raw
    questions and answers.
-   **Rate limits**: API rate limits and a server-wide spend limit.
-   **Testing your own app**: send questions to any HTTP endpoint, with
    protection against calls to internal addresses.
-   **Stuck run recovery**: detect runs left behind when a worker dies.
-   **More evaluation options**: scheduled runs, repeat runs to measure
    variance, weighted overall scores, and reusable run settings.
-   **Operations**: track queue depth, worker failures, and provider error
    rates, and load test at 1,000 cases per run.
-   **Dashboard**: create model configurations and write datasets without
    uploading a file.

## Learn more

| Document | What's inside |
|---|---|
| [`docs/metrics.md`](docs/metrics.md) | What each score means, and how rules work |
| [`docs/providers.md`](docs/providers.md) | Connecting real models and API keys |
| [`docs/ci.md`](docs/ci.md) | Adding checks to your CI pipeline |
| [`docs/api.md`](docs/api.md) | REST API reference |
| [`docs/architecture.md`](docs/architecture.md) | How the system is built |
| [`docs/threat-model.md`](docs/threat-model.md) | Security risks and protections |
| [`docs/operations.md`](docs/operations.md) | Upgrades, backups, logs, and stuck runs |
| [`docs/decisions/`](docs/decisions/) | Why it's built this way |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed in each version |

## License

[MIT](LICENSE) © 2026 hasseb01 and anasfwp.
