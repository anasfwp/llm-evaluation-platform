import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { MetricInfo } from "../api/types";
import { AsyncBlock, ErrorMessage } from "../components/common";
import { useAsync } from "../hooks";

const DEFAULT_METRICS = ["exact_match", "token_f1", "latency", "estimated_cost"];

/** Metrics that need extra configuration (a judge model, an embedding model) are set up via the API. */
function needsConfig(metric: MetricInfo): boolean {
  return metric.name.startsWith("llm_judge_") || metric.name === "semantic_similarity";
}

export function NewRunPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const datasets = useAsync(() => api.listDatasets(projectId), [projectId]);
  const models = useAsync(() => api.listModels(projectId), [projectId]);
  const metrics = useAsync(() => api.listMetrics(), []);
  const [datasetId, setDatasetId] = useState("");
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [metricNames, setMetricNames] = useState<string[]>(DEFAULT_METRICS);
  const [maxConcurrency, setMaxConcurrency] = useState(4);
  const [maxRetries, setMaxRetries] = useState(1);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const available = new Set((metrics.data ?? []).map((m) => m.name));
      const started = await api.startRun({
        project_id: projectId,
        dataset_id: datasetId,
        model_config_ids: modelIds,
        metrics: metricNames.filter((n) => available.has(n)).map((name) => ({ name })),
        run_config: { max_concurrency: maxConcurrency, max_retries: maxRetries },
      });
      navigate(`/runs/${started.run_id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <>
      <div className="breadcrumbs">
        <Link to="/">Projects</Link> / <Link to={`/projects/${projectId}`}>Project</Link> /
      </div>
      <h1>New evaluation run</h1>
      <p className="subtitle">
        Runs execute in the background worker. Hosted providers read their API key from the
        server's environment; keys are never entered here.
      </p>
      <form className="form" onSubmit={submit}>
        <AsyncBlock state={datasets}>
          {(page) => (
            <label>
              Dataset (latest version)
              <select required value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
                <option value="">Choose a dataset…</option>
                {page.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} (v{d.current_version}, {d.case_count} cases)
                  </option>
                ))}
              </select>
            </label>
          )}
        </AsyncBlock>

        <fieldset>
          <legend>Models</legend>
          <AsyncBlock state={models}>
            {(page) =>
              page.items.length === 0 ? (
                <p className="muted">This project has no model configurations yet.</p>
              ) : (
                page.items.map((m) => (
                  <label key={m.id} className="check">
                    <input
                      type="checkbox"
                      checked={modelIds.includes(m.id)}
                      onChange={() => setModelIds(toggle(modelIds, m.id))}
                    />
                    {m.name} <span className="muted">({m.provider} / {m.model_id})</span>
                  </label>
                ))
              )
            }
          </AsyncBlock>
        </fieldset>

        <fieldset>
          <legend>Metrics</legend>
          <AsyncBlock state={metrics}>
            {(items) =>
              items.map((m) => (
                <label key={m.name} className="check" title={m.description}>
                  <input
                    type="checkbox"
                    disabled={needsConfig(m)}
                    checked={metricNames.includes(m.name)}
                    onChange={() => setMetricNames(toggle(metricNames, m.name))}
                  />
                  {m.name}
                  <span className="muted">
                    {needsConfig(m) ? "needs configuration: start via the API or CLI" : m.category.replace("_", " ")}
                  </span>
                </label>
              ))
            }
          </AsyncBlock>
        </fieldset>

        <fieldset>
          <legend>Execution</legend>
          <div className="toolbar" style={{ margin: 0 }}>
            <label>
              Max concurrency
              <input
                type="number"
                min={1}
                max={64}
                value={maxConcurrency}
                onChange={(e) => setMaxConcurrency(Number(e.target.value))}
              />
            </label>
            <label>
              Max retries
              <input
                type="number"
                min={0}
                max={5}
                value={maxRetries}
                onChange={(e) => setMaxRetries(Number(e.target.value))}
              />
            </label>
          </div>
        </fieldset>

        <ErrorMessage error={error} />
        <div>
          <button
            className="primary"
            type="submit"
            disabled={busy || !datasetId || modelIds.length === 0 || metricNames.length === 0}
          >
            {busy ? "Starting…" : "Start run"}
          </button>
        </div>
      </form>
    </>
  );
}
