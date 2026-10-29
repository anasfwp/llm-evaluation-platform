import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadUrl } from "../api/client";
import type { CaseResult, GateResult, MetricInfo, ModelSummary, Run } from "../api/types";
import { BarChart } from "../components/charts";
import {
  AsyncBlock,
  Badge,
  ErrorMessage,
  Pager,
  PassBadge,
  RunStatusBadge,
  Stat,
} from "../components/common";
import {
  directionLabel,
  formatDate,
  formatDuration,
  formatMetric,
  formatNumber,
  formatPercent,
  shortId,
} from "../format";
import { useAsync, useInterval } from "../hooks";

export function RunPage() {
  const { runId = "" } = useParams();
  const run = useAsync(() => api.getRun(runId), [runId]);
  const metrics = useAsync(() => api.listMetrics(), []);
  const active = run.data?.status === "queued" || run.data?.status === "running";
  useInterval(run.reload, 2000, active);

  return (
    <AsyncBlock state={run}>
      {(r) => <RunView run={r} metricInfo={metrics.data ?? []} onChange={run.reload} />}
    </AsyncBlock>
  );
}

function RunView({ run, metricInfo, onChange }: { run: Run; metricInfo: MetricInfo[]; onChange: () => void }) {
  const [error, setError] = useState<unknown>();
  const active = run.status === "queued" || run.status === "running";
  const done = run.progress.completed_cases;
  const models = run.models ?? [];

  const cancel = async () => {
    try {
      await api.cancelRun(run.id);
      onChange();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <>
      <div className="breadcrumbs">
        <Link to="/">Projects</Link> / <Link to={`/projects/${run.project_id}`}>Project</Link> /
      </div>
      <h1>
        Run <span className="mono">{shortId(run.id)}</span>
      </h1>
      <p className="subtitle">
        <RunStatusBadge status={run.status} /> · dataset{" "}
        <Link to={`/datasets/${run.dataset.id}`}>{run.dataset.name}</Link> v{run.dataset.version} · created{" "}
        {formatDate(run.created_at)}
      </p>

      <div className="toolbar">
        {active && (
          <button onClick={cancel} disabled={run.cancel_requested}>
            {run.cancel_requested ? "Cancelling…" : "Cancel run"}
          </button>
        )}
        {run.status === "completed" && (
          <>
            <a className="button" href={downloadUrl(`/runs/${run.id}/report`, { format: "markdown" })}>
              Download Markdown report
            </a>
            <a className="button" href={downloadUrl(`/runs/${run.id}/report`, { format: "json" })}>
              JSON
            </a>
            <a className="button" href={downloadUrl(`/runs/${run.id}/report`, { format: "csv" })}>
              CSV
            </a>
            <Link className="button" to={`/projects/${run.project_id}/compare?candidate=${run.id}`}>
              Compare with…
            </Link>
          </>
        )}
      </div>
      <ErrorMessage error={error} />
      {run.error_message && (
        <div className="alert" role="alert">
          <strong>Run failed:</strong> {run.error_message}
        </div>
      )}

      <div className="stats">
        <Stat
          label="Progress"
          value={`${done} / ${run.progress.total_cases}`}
          hint={active ? "Updating every 2 s" : undefined}
        />
        <Stat label="Failed cases" value={run.progress.failed_cases} />
        <Stat label="Duration" value={formatDuration(run.started_at, run.finished_at)} />
        <Stat label="Software" value={<span className="mono">{run.software_version}</span>} />
      </div>
      {active && (
        <progress
          max={run.progress.total_cases || 1}
          value={done}
          aria-label="Run progress"
          style={{ width: "100%" }}
        />
      )}

      {models.length > 0 && (
        <>
          <h2>Summary</h2>
          <SummaryCharts models={models} metricInfo={metricInfo} />
          <SummaryTable models={models} metricInfo={metricInfo} />
        </>
      )}

      {run.status === "completed" && <RunActions run={run} />}

      {run.status !== "queued" && (
        <>
          <h2>Case results</h2>
          <ResultsTable run={run} metricNames={metricNames(models)} />
        </>
      )}
    </>
  );
}

function metricNames(models: ModelSummary[]): string[] {
  return [...new Set(models.flatMap((m) => Object.keys(m.metrics)))];
}

function SummaryCharts({ models, metricInfo }: { models: ModelSummary[]; metricInfo: MetricInfo[] }) {
  const series = [{ name: "mean", color: "var(--series-1)" }];
  const charts = metricNames(models).filter((name) => models.some((m) => m.metrics[name]?.mean != null));
  return (
    <div className="chart-grid">
      {charts.map((metric) => {
        const info = metricInfo.find((i) => i.name === metric);
        const upper = info?.score_range[1] ?? undefined;
        const isLatency = metric === "latency";
        return (
          <div className="card" key={metric}>
            <BarChart
              title={`${metric} — ${isLatency ? "p95" : "mean"}`}
              rows={models.map((m) => ({
                label: m.model_name,
                values: [isLatency ? (m.metrics[metric]?.p95 ?? null) : (m.metrics[metric]?.mean ?? null)],
              }))}
              series={series.map((s) => ({ ...s, name: isLatency ? "p95" : s.name }))}
              format={(v) => formatMetric(metric, v)}
              maxValue={upper ?? undefined}
            />
            {info && <div className="muted">{directionLabel(info.direction)}</div>}
          </div>
        );
      })}
      <div className="card">
        <BarChart
          title="error rate"
          rows={models.map((m) => ({ label: m.model_name, values: [m.error_rate] }))}
          series={[{ name: "error rate", color: "var(--series-1)" }]}
          format={(v) => formatPercent(v)}
          maxValue={0.1}
        />
        <div className="muted">lower is better</div>
      </div>
    </div>
  );
}

function SummaryTable({ models, metricInfo }: { models: ModelSummary[]; metricInfo: MetricInfo[] }) {
  const names = metricNames(models);
  return (
    <details>
      <summary>Table view (all statistics)</summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Metric</th>
              <th className="num">Scored</th>
              <th className="num">Mean</th>
              <th className="num">Median</th>
              <th className="num">p95</th>
              <th className="num">Min</th>
              <th className="num">Max</th>
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {models.flatMap((m) => [
              <tr key={`${m.model_name}:errors`}>
                <td>
                  {m.model_name} <span className="muted">({m.provider}/{m.model_id})</span>
                </td>
                <td>error_rate</td>
                <td className="num">{m.case_count}</td>
                <td className="num">{formatPercent(m.error_rate)}</td>
                <td colSpan={5} className="muted">
                  {Object.entries(m.error_codes)
                    .map(([code, n]) => `${code}: ${n}`)
                    .join(", ") || "no errors"}
                </td>
              </tr>,
              ...names.map((name) => {
                const s = m.metrics[name];
                const f = (v: number | null | undefined) => formatMetric(name, v);
                const info = metricInfo.find((i) => i.name === name);
                return (
                  <tr key={`${m.model_name}:${name}`}>
                    <td>{m.model_name}</td>
                    <td title={info?.description}>
                      {name}
                      {s?.small_sample && (
                        <Badge tone="neutral" icon="!">
                          small sample
                        </Badge>
                      )}
                    </td>
                    <td className="num">{s?.scored_count ?? 0}</td>
                    <td className="num">{f(s?.mean)}</td>
                    <td className="num">{f(s?.median)}</td>
                    <td className="num">{f(s?.p95)}</td>
                    <td className="num">{f(s?.min)}</td>
                    <td className="num">{f(s?.max)}</td>
                    <td className="num">{f(s?.total)}</td>
                  </tr>
                );
              }),
            ])}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function RunActions({ run }: { run: Run }) {
  const gates = useAsync(() => api.listGates(run.project_id), [run.project_id]);
  const baselines = useAsync(() => api.listBaselines(run.project_id), [run.project_id]);
  const [name, setName] = useState("");
  const [gateId, setGateId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [result, setResult] = useState<GateResult>();
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState<string>();

  const saveBaseline = async (event: FormEvent) => {
    event.preventDefault();
    setError(undefined);
    try {
      const baseline = await api.createBaseline(run.project_id, { name, run_id: run.id });
      setSaved(baseline.name);
      setName("");
      baselines.reload();
    } catch (err) {
      setError(err);
    }
  };

  const evaluate = async (event: FormEvent) => {
    event.preventDefault();
    setError(undefined);
    try {
      setResult(
        await api.evaluateGate({ run_id: run.id, gate_id: gateId, baseline_id: baselineId || undefined }),
      );
    } catch (err) {
      setError(err);
    }
  };

  const gateList = gates.data ?? [];
  const needsBaseline = gateList.find((g) => g.id === gateId)?.rules.some((r) => r.kind === "relative");

  return (
    <>
      <h2>Baseline & gates</h2>
      <div className="grid">
        <form className="card form" onSubmit={saveBaseline}>
          <h3>Save as baseline</h3>
          <label>
            Baseline name
            <input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div>
            <button type="submit" disabled={!name.trim()}>
              Save baseline
            </button>
          </div>
          {saved && (
            <p role="status">
              <Badge tone="good" icon="✓">
                Saved “{saved}”
              </Badge>
            </p>
          )}
        </form>
        <form className="card form" onSubmit={evaluate}>
          <h3>Evaluate a saved gate</h3>
          {gateList.length === 0 ? (
            <p className="muted">This project has no saved gates.</p>
          ) : (
            <>
              <label>
                Gate
                <select required value={gateId} onChange={(e) => setGateId(e.target.value)}>
                  <option value="">Choose…</option>
                  {gateList.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Baseline {needsBaseline ? "(needed by relative rules)" : "(optional)"}
                <select value={baselineId} onChange={(e) => setBaselineId(e.target.value)}>
                  <option value="">None</option>
                  {(baselines.data ?? []).map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
              <div>
                <button type="submit" disabled={!gateId}>
                  Evaluate
                </button>
              </div>
            </>
          )}
        </form>
      </div>
      <ErrorMessage error={error} />
      {result && <GateResultView result={result} />}
    </>
  );
}

function GateResultView({ result }: { result: GateResult }) {
  return (
    <section aria-live="polite">
      <h3 style={{ marginTop: 16 }}>
        Gate “{result.gate_name}”:{" "}
        <PassBadge passed={result.passed} passText="Passed" failText="Failed" />
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Model</th>
              <th>Rule</th>
              <th className="num">Actual</th>
              <th className="num">Baseline</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {result.results.map((o, i) => (
              <tr key={i}>
                <td>
                  {o.status === "passed" ? (
                    <Badge tone="good" icon="✓">
                      passed
                    </Badge>
                  ) : o.status === "failed" ? (
                    <Badge tone="bad" icon="✕">
                      failed
                    </Badge>
                  ) : (
                    <Badge tone="neutral" icon="–">
                      {o.status}
                    </Badge>
                  )}
                </td>
                <td>{o.model}</td>
                <td className="mono">{o.rule}</td>
                <td className="num">{formatNumber(o.actual)}</td>
                <td className="num">{formatNumber(o.baseline)}</td>
                <td>{o.reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const PAGE = 25;

function ResultsTable({ run, metricNames: names }: { run: Run; metricNames: string[] }) {
  const modelNames = (run.config_snapshot.models ?? []).map((m) => m.name);
  const [model, setModel] = useState("");
  const [status, setStatus] = useState("");
  const [tag, setTag] = useState("");
  const [metric, setMetric] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useMemo(
    () => ({
      model_name: model,
      status,
      tag,
      metric,
      max_score: metric && maxScore !== "" ? Number(maxScore) : undefined,
      limit: PAGE,
      offset,
    }),
    [model, status, tag, metric, maxScore, offset],
  );
  const results = useAsync(() => api.listResults(run.id, query), [run.id, query, run.progress.completed_cases]);
  const reset = () => setOffset(0);

  return (
    <>
      <div className="toolbar" role="search" aria-label="Filter case results">
        <label>
          Model
          <select value={model} onChange={(e) => (setModel(e.target.value), reset())}>
            <option value="">All</option>
            {modelNames.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => (setStatus(e.target.value), reset())}>
            <option value="">All</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </select>
        </label>
        <label>
          Tag
          <input value={tag} maxLength={100} onChange={(e) => (setTag(e.target.value), reset())} />
        </label>
        <label>
          Scored on metric
          <select value={metric} onChange={(e) => (setMetric(e.target.value), reset())}>
            <option value="">Any</option>
            {names.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label>
          Max score
          <input
            type="number"
            step="any"
            disabled={!metric}
            value={maxScore}
            onChange={(e) => (setMaxScore(e.target.value), reset())}
            style={{ width: 100 }}
          />
        </label>
      </div>
      <AsyncBlock state={results}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="muted">No case results match these filters.</p>
          ) : (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Model</th>
                      <th>Status</th>
                      <th>Output vs expected</th>
                      <th>Scores</th>
                      <th className="num">Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((r) => (
                      <ResultRow key={r.id} result={r} />
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager total={page.total} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )
        }
      </AsyncBlock>
    </>
  );
}

function ResultRow({ result: r }: { result: CaseResult }) {
  return (
    <tr>
      <td>
        <span className="mono">{r.case_key}</span>
        {r.tags.length > 0 && <div className="muted">{r.tags.join(", ")}</div>}
      </td>
      <td>{r.model_name}</td>
      <td>
        {r.status === "success" ? (
          <Badge tone="good" icon="✓">
            success
          </Badge>
        ) : (
          <Badge tone="bad" icon="✕">
            {r.error_code ?? "error"}
          </Badge>
        )}
        {r.attempts > 1 && <div className="muted">{r.attempts} attempts</div>}
      </td>
      <td style={{ minWidth: 220 }}>
        {r.status === "error" ? (
          <span className="muted">{r.error_message}</span>
        ) : (
          <>
            <pre className="output">{r.actual_output}</pre>
            {r.expected_output !== null && (
              <div className="muted">
                expected: <span className="mono">{r.expected_output}</span>
              </div>
            )}
          </>
        )}
        <details>
          <summary className="muted">Input</summary>
          <pre className="output">{JSON.stringify(r.input, null, 2)}</pre>
        </details>
      </td>
      <td>
        {r.metrics.map((m) => (
          <div key={m.metric_name} title={metricTitle(m.details)}>
            <span className="muted">{m.metric_name}:</span>{" "}
            {m.status === "scored" ? (
              <strong>{formatMetric(m.metric_name, m.score)}</strong>
            ) : (
              <span className="muted">{m.status.replace("_", " ")}</span>
            )}
          </div>
        ))}
      </td>
      <td className="num">{r.latency_ms === null ? "—" : `${formatNumber(r.latency_ms)} ms`}</td>
    </tr>
  );
}

function metricTitle(details: Record<string, unknown>): string | undefined {
  const reason = details.reason ?? details.message ?? details.explanation;
  return typeof reason === "string" ? reason : undefined;
}

