import { Link, useParams } from "react-router-dom";
import { api, downloadUrl } from "../api/client";
import type { CaseChange, MetricDelta, ModelComparison, Verdict } from "../api/types";
import { BarChart } from "../components/charts";
import { AsyncBlock, Badge, PassBadge, Stat } from "../components/common";
import { directionLabel, formatDate, formatMetric, formatPercent, formatSigned, shortId } from "../format";
import { useAsync } from "../hooks";

const BASELINE = { name: "baseline", color: "var(--series-1)" };
const CANDIDATE = { name: "candidate", color: "var(--series-2)" };

export function ComparisonPage() {
  const { comparisonId = "" } = useParams();
  const comparison = useAsync(() => api.getComparison(comparisonId), [comparisonId]);

  return (
    <AsyncBlock state={comparison}>
      {(c) => {
        const r = c.result;
        return (
          <>
            <div className="breadcrumbs">
              <Link to="/">Projects</Link> /{" "}
              <Link to={`/projects/${c.project_id}?tab=comparisons`}>Project</Link> /
            </div>
            <h1>
              Comparison <span className="mono">{shortId(c.id)}</span>
            </h1>
            <p className="subtitle">
              <PassBadge passed={!r.regressed} /> · baseline{" "}
              <Link to={`/runs/${c.baseline_run_id}`} className="mono">
                {shortId(c.baseline_run_id)}
              </Link>{" "}
              ({formatDate(r.baseline.finished_at)}) → candidate{" "}
              <Link to={`/runs/${c.candidate_run_id}`} className="mono">
                {shortId(c.candidate_run_id)}
              </Link>{" "}
              ({formatDate(r.candidate.finished_at)})
            </p>
            <div className="toolbar">
              <a className="button" href={downloadUrl(`/comparisons/${c.id}/report`, { format: "markdown" })}>
                Download regression report
              </a>
              <a className="button" href={downloadUrl(`/comparisons/${c.id}/report`, { format: "json" })}>
                JSON
              </a>
            </div>
            {r.warnings.length > 0 && (
              <div className="alert info">
                <strong>Read with care</strong>
                <ul>
                  {r.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="stats">
              <Stat label="Newly failing cases" value={r.newly_failing_count} />
              <Stat label="Recovered cases" value={r.recovered_count} />
              <Stat label="Same dataset" value={r.same_dataset ? "yes" : "no"} />
              <Stat label="Model pairs" value={r.models.length} />
            </div>
            {Object.keys(r.excluded_metrics).length > 0 && (
              <details>
                <summary>Metrics not compared ({Object.keys(r.excluded_metrics).length})</summary>
                <ul>
                  {Object.entries(r.excluded_metrics).map(([name, reason]) => (
                    <li key={name}>
                      <code>{name}</code>: {reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {r.models.map((m) => (
              <ModelSection key={`${m.baseline_model}->${m.candidate_model}`} model={m} />
            ))}
          </>
        );
      }}
    </AsyncBlock>
  );
}

const VERDICT: Record<Verdict, [string, "good" | "bad" | "neutral", string]> = {
  improved: ["improved", "good", "▲"],
  regressed: ["regressed", "bad", "▼"],
  unchanged: ["unchanged", "neutral", "="],
  not_comparable: ["n/a", "neutral", "–"],
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const [label, tone, icon] = VERDICT[verdict];
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}

function format(delta: MetricDelta, value: number | null): string {
  return delta.metric === "error_rate" ? formatPercent(value) : formatMetric(delta.metric, value);
}

function ModelSection({ model: m }: { model: ModelComparison }) {
  const label =
    m.baseline_model === m.candidate_model ? m.candidate_model : `${m.baseline_model} → ${m.candidate_model}`;
  const deltas = [m.error_rate, ...m.metrics];
  const charted = m.metrics.filter((d) => d.baseline !== null || d.candidate !== null);

  return (
    <section aria-labelledby={`model-${label}`}>
      <h2 id={`model-${label}`}>
        {label} <PassBadge passed={!m.regressed} />
      </h2>
      <p className="muted">
        {m.cases_compared} cases compared
        {m.cases_only_in_baseline.length > 0 && `, ${m.cases_only_in_baseline.length} only in baseline`}
        {m.cases_only_in_candidate.length > 0 && `, ${m.cases_only_in_candidate.length} only in candidate`}
      </p>

      {charted.length > 0 && (
        <div className="chart-grid">
          {charted.map((d) => (
            <div className="card" key={d.metric}>
              <BarChart
                title={`${d.metric} — ${d.aggregation}`}
                rows={[{ label, values: [d.baseline, d.candidate] }]}
                series={[BASELINE, CANDIDATE]}
                format={(v) => format(d, v)}
              />
              <div className="muted">
                {directionLabel(d.direction)} · <VerdictBadge verdict={d.verdict} />
              </div>
            </div>
          ))}
        </div>
      )}

      <h3 style={{ marginTop: 16 }}>Metric changes</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th className="num">Baseline</th>
              <th className="num">Candidate</th>
              <th className="num">Delta</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {deltas.map((d) => (
              <tr key={`${d.metric}:${d.aggregation}`}>
                <td>
                  {d.metric} <span className="muted">{d.aggregation}</span>
                </td>
                <td className="num">{format(d, d.baseline)}</td>
                <td className="num">{format(d, d.candidate)}</td>
                <td className="num">
                  {d.metric === "error_rate"
                    ? d.delta === null
                      ? "—"
                      : `${d.delta > 0 ? "+" : ""}${formatPercent(d.delta)}`
                    : formatSigned(d.delta)}
                </td>
                <td>
                  <VerdictBadge verdict={d.verdict} />
                  {d.reason && <div className="muted">{d.reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CaseList title="Newly failing cases" cases={m.newly_failing} empty="No newly failing cases." />
      <CaseList title="Recovered cases" cases={m.recovered} empty="No recovered cases." />

      {m.score_changes.length > 0 && (
        <details>
          <summary>Per-case score changes ({m.score_changes.length})</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Metric</th>
                  <th className="num">Baseline</th>
                  <th className="num">Candidate</th>
                  <th className="num">Delta</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {m.score_changes.map((s) => (
                  <tr key={`${s.case_key}:${s.metric}`}>
                    <td className="mono">{s.case_key}</td>
                    <td>{s.metric}</td>
                    <td className="num">{formatMetric(s.metric, s.baseline)}</td>
                    <td className="num">{formatMetric(s.metric, s.candidate)}</td>
                    <td className="num">{formatSigned(s.delta)}</td>
                    <td>
                      <VerdictBadge verdict={s.verdict} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

function CaseList({ title, cases, empty }: { title: string; cases: CaseChange[]; empty: string }) {
  return (
    <>
      <h3 style={{ marginTop: 16 }}>
        {title} ({cases.length})
      </h3>
      {cases.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Case</th>
                <th>Baseline</th>
                <th>Candidate</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.case_key}>
                  <td className="mono">{c.case_key}</td>
                  <td>
                    {c.baseline_state}
                    {c.baseline_reasons.length > 0 && (
                      <div className="muted">{c.baseline_reasons.join("; ")}</div>
                    )}
                  </td>
                  <td>
                    {c.candidate_state}
                    {c.candidate_reasons.length > 0 && (
                      <div className="muted">{c.candidate_reasons.join("; ")}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
