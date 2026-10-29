import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Run, RunStatus } from "../api/types";
import { LineChart } from "../components/charts";
import {
  AsyncBlock,
  Badge,
  ErrorMessage,
  Pager,
  PassBadge,
  RunStatusBadge,
  TabPanel,
  Tabs,
} from "../components/common";
import { MAX_SERIES, formatDate, formatMetric, formatPercent, seriesColor, shortId } from "../format";
import { useAsync, useInterval } from "../hooks";

const TABS = [
  { id: "runs", label: "Runs" },
  { id: "datasets", label: "Datasets" },
  { id: "models", label: "Models" },
  { id: "comparisons", label: "Comparisons" },
  { id: "baselines", label: "Baselines & gates" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "runs") as TabId;
  const project = useAsync(() => api.getProject(projectId), [projectId]);

  return (
    <>
      <div className="breadcrumbs">
        <Link to="/">Projects</Link> /
      </div>
      <AsyncBlock state={project}>
        {(p) => (
          <>
            <h1>{p.name}</h1>
            {p.description && <p className="subtitle">{p.description}</p>}
          </>
        )}
      </AsyncBlock>
      <div className="toolbar">
        <Link className="button primary" to={`/projects/${projectId}/runs/new`}>
          New run
        </Link>
        <Link className="button" to={`/projects/${projectId}/compare`}>
          Compare runs
        </Link>
      </div>
      <Tabs
        label="Project sections"
        tabs={TABS}
        active={tab}
        onChange={(id) => setParams(id === "runs" ? {} : { tab: id }, { replace: true })}
      />
      <TabPanel id={tab}>
        {tab === "runs" && <RunsTab projectId={projectId} />}
        {tab === "datasets" && <DatasetsTab projectId={projectId} />}
        {tab === "models" && <ModelsTab projectId={projectId} />}
        {tab === "comparisons" && <ComparisonsTab projectId={projectId} />}
        {tab === "baselines" && <BaselinesTab projectId={projectId} />}
      </TabPanel>
    </>
  );
}

const STATUSES: RunStatus[] = ["queued", "running", "completed", "failed", "cancelled"];
const PAGE = 25;

function RunsTab({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<RunStatus | "">("");
  const [offset, setOffset] = useState(0);
  const runs = useAsync(
    () => api.listRuns({ project_id: projectId, status, limit: PAGE, offset }),
    [projectId, status, offset],
  );
  const active = runs.data?.items.some((r) => r.status === "queued" || r.status === "running") ?? false;
  useInterval(runs.reload, 3000, active);

  return (
    <>
      <QualityTrend projectId={projectId} />
      <div className="toolbar">
        <label>
          Status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as RunStatus | "");
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>
      <AsyncBlock state={runs}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="muted">No runs{status ? ` with status "${status}"` : ""} yet.</p>
          ) : (
            <>
              <RunsTable runs={page.items} />
              <Pager total={page.total} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )
        }
      </AsyncBlock>
    </>
  );
}

function RunsTable({ runs }: { runs: Run[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Dataset</th>
            <th>Models</th>
            <th className="num">Progress</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link to={`/runs/${run.id}`} className="mono">
                  {shortId(run.id)}
                </Link>
              </td>
              <td>
                <RunStatusBadge status={run.status} />
              </td>
              <td>
                {run.dataset.name} <span className="muted">v{run.dataset.version}</span>
              </td>
              <td>{(run.config_snapshot.models ?? []).map((m) => m.name).join(", ") || "—"}</td>
              <td className="num">
                {run.progress.completed_cases}/{run.progress.total_cases}
              </td>
              <td>{formatDate(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Mean of a chosen metric per model across the project's recent completed runs. */
function QualityTrend({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const runs = useAsync(
    () => api.listRuns({ project_id: projectId, status: "completed", limit: 50 }),
    [projectId],
  );
  const completed = useMemo(
    () => [...(runs.data?.items ?? [])].filter((r) => r.models).reverse(),
    [runs.data],
  );
  const metricNames = useMemo(() => {
    const names = new Set<string>(["error_rate"]);
    completed.forEach((r) => r.models?.forEach((m) => Object.keys(m.metrics).forEach((k) => names.add(k))));
    return [...names];
  }, [completed]);
  const [metric, setMetric] = useState("exact_match");
  const chosen = metricNames.includes(metric) ? metric : (metricNames[0] ?? "error_rate");

  if (completed.length < 2) return null;
  const allModels = [...new Set(completed.flatMap((r) => r.models!.map((m) => m.model_name)))];
  const models = allModels.slice(0, MAX_SERIES);
  const series = models.map((name) => ({ name, color: seriesColor(allModels, name) }));
  const value = (run: Run, model: string): number | null => {
    const summary = run.models!.find((m) => m.model_name === model);
    if (!summary) return null;
    if (chosen === "error_rate") return summary.error_rate;
    return summary.metrics[chosen]?.mean ?? null;
  };
  const points = completed.map((run) => ({
    label: formatDate(run.finished_at),
    values: models.map((m) => value(run, m)),
  }));
  const format = (v: number | null) => (chosen === "error_rate" ? formatPercent(v) : formatMetric(chosen, v));

  return (
    <section className="card" aria-label="Quality trend">
      <div className="toolbar" style={{ marginTop: 0 }}>
        <label>
          Metric (mean per run)
          <select value={chosen} onChange={(e) => setMetric(e.target.value)}>
            {metricNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {allModels.length > MAX_SERIES && (
          <span className="muted">Showing the first {MAX_SERIES} of {allModels.length} models.</span>
        )}
      </div>
      <LineChart
        title={`${chosen} over the last ${completed.length} completed runs`}
        points={points}
        series={series}
        format={format}
        onSelect={(i) => navigate(`/runs/${completed[i]!.id}`)}
      />
      <details>
        <summary>Table view</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run finished</th>
                {models.map((m) => (
                  <th key={m} className="num">
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {completed.map((run, i) => (
                <tr key={run.id}>
                  <td>
                    <Link to={`/runs/${run.id}`}>{points[i]!.label}</Link>
                  </td>
                  {models.map((m) => (
                    <td key={m} className="num">
                      {format(value(run, m))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function DatasetsTab({ projectId }: { projectId: string }) {
  const datasets = useAsync(() => api.listDatasets(projectId), [projectId]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.importDataset(projectId, file);
      setFile(null);
      (event.target as HTMLFormElement).reset();
      datasets.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AsyncBlock state={datasets}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="muted">No datasets yet. Import a JSON or JSONL file below.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th className="num">Version</th>
                    <th className="num">Cases</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link to={`/datasets/${d.id}`}>{d.name}</Link>
                      </td>
                      <td className="num">v{d.current_version}</td>
                      <td className="num">{d.case_count}</td>
                      <td>{formatDate(d.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </AsyncBlock>
      <h2>Import a dataset</h2>
      <form className="form card" onSubmit={upload}>
        <label>
          Dataset file (.json or .jsonl)
          <input
            type="file"
            accept=".json,.jsonl,application/json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <p className="muted" style={{ margin: 0 }}>
          The whole file is validated first; invalid files are rejected with every problem listed.
        </p>
        <ErrorMessage error={error} />
        <div>
          <button className="primary" type="submit" disabled={!file || busy}>
            {busy ? "Importing…" : "Import"}
          </button>
        </div>
      </form>
    </>
  );
}

function ModelsTab({ projectId }: { projectId: string }) {
  const models = useAsync(() => api.listModels(projectId), [projectId]);
  return (
    <AsyncBlock state={models}>
      {(page) =>
        page.items.length === 0 ? (
          <p className="muted">
            No model configurations yet. Create them with <code>POST /api/v1/projects/{"{id}"}/models</code>.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Provider</th>
                  <th>Model ID</th>
                  <th>Credential</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((m) => (
                  <tr key={m.id}>
                    <td>{m.name}</td>
                    <td>{m.provider}</td>
                    <td className="mono">{m.model_id}</td>
                    <td>
                      {m.secret_reference ? (
                        <span className="mono" title="Environment variable name; the value is never shown">
                          ${m.secret_reference}
                        </span>
                      ) : (
                        <span className="muted">none</span>
                      )}
                    </td>
                    <td>{formatDate(m.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </AsyncBlock>
  );
}

function ComparisonsTab({ projectId }: { projectId: string }) {
  const comparisons = useAsync(() => api.listComparisons(projectId), [projectId]);
  return (
    <AsyncBlock state={comparisons}>
      {(page) =>
        page.items.length === 0 ? (
          <p className="muted">
            No comparisons yet. <Link to={`/projects/${projectId}/compare`}>Compare two runs</Link>.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Comparison</th>
                  <th>Result</th>
                  <th>Baseline run</th>
                  <th>Candidate run</th>
                  <th className="num">Newly failing</th>
                  <th className="num">Recovered</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/comparisons/${c.id}`} className="mono">
                        {shortId(c.id)}
                      </Link>
                    </td>
                    <td>
                      <PassBadge passed={!c.regressed} />
                    </td>
                    <td>
                      <Link to={`/runs/${c.baseline_run_id}`} className="mono">
                        {shortId(c.baseline_run_id)}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/runs/${c.candidate_run_id}`} className="mono">
                        {shortId(c.candidate_run_id)}
                      </Link>
                    </td>
                    <td className="num">{c.newly_failing_count}</td>
                    <td className="num">{c.recovered_count}</td>
                    <td>{formatDate(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </AsyncBlock>
  );
}

function BaselinesTab({ projectId }: { projectId: string }) {
  const baselines = useAsync(() => api.listBaselines(projectId), [projectId]);
  const gates = useAsync(() => api.listGates(projectId), [projectId]);
  return (
    <>
      <h2>Baselines</h2>
      <p className="muted">Named runs to compare against. Save one from a completed run's page.</p>
      <AsyncBlock state={baselines}>
        {(items) =>
          items.length === 0 ? (
            <p className="muted">No baselines yet.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Run</th>
                    <th>Description</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((b) => (
                    <tr key={b.id}>
                      <td>{b.name}</td>
                      <td>
                        <Link to={`/runs/${b.run_id}`} className="mono">
                          {shortId(b.run_id)}
                        </Link>
                      </td>
                      <td>{b.description ?? <span className="muted">—</span>}</td>
                      <td>{formatDate(b.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </AsyncBlock>
      <h2>Saved gates</h2>
      <AsyncBlock state={gates}>
        {(items) =>
          items.length === 0 ? (
            <p className="muted">
              No saved gates. Create them with <code>POST /api/v1/projects/{"{id}"}/gates</code>; gate
              files for the CLI live in <code>evals/</code>.
            </p>
          ) : (
            <div className="grid">
              {items.map((g) => (
                <div className="card" key={g.id}>
                  <h3>{g.name}</h3>
                  <div className="muted">Missing data: {g.missing_metric_policy}</div>
                  <ul>
                    {g.rules.map((r, i) => (
                      <li key={i} className="mono">
                        {describeRule(r)}
                      </li>
                    ))}
                  </ul>
                  {g.rules.some((r) => r.kind === "relative") && (
                    <Badge tone="neutral" icon="↔">
                      needs a baseline
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          )
        }
      </AsyncBlock>
    </>
  );
}

const OPS: Record<string, string> = { gte: "≥", gt: ">", lte: "≤", lt: "<", eq: "=" };

export function describeRule(rule: {
  metric: string;
  aggregation: string;
  kind?: string;
  operator?: string;
  threshold?: number;
  max_regression?: number;
  regression_unit?: string;
  model?: string;
  tag?: string;
}): string {
  const target = `${rule.metric}.${rule.aggregation}`;
  const body =
    rule.kind === "relative"
      ? `${target} regression ≤ ${rule.max_regression}${rule.regression_unit === "percent" ? "%" : ""}`
      : `${target} ${OPS[rule.operator ?? ""] ?? rule.operator} ${rule.threshold}`;
  const scope = [rule.model && `model=${rule.model}`, rule.tag && `tag=${rule.tag}`].filter(Boolean);
  return scope.length ? `${body} [${scope.join(", ")}]` : body;
}
