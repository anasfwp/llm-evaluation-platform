import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Run } from "../api/types";
import { AsyncBlock, ErrorMessage } from "../components/common";
import { formatDate, shortId } from "../format";
import { useAsync } from "../hooks";

function runLabel(run: Run): string {
  const models = (run.config_snapshot.models ?? []).map((m) => m.name).join(", ");
  return `${shortId(run.id)} · ${run.dataset.name} v${run.dataset.version} · ${models} · ${formatDate(run.finished_at)}`;
}

export function NewComparisonPage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const runs = useAsync(
    () => api.listRuns({ project_id: projectId, status: "completed", limit: 100 }),
    [projectId],
  );
  const baselines = useAsync(() => api.listBaselines(projectId), [projectId]);
  const [mode, setMode] = useState<"run" | "saved">("run");
  const [baselineRun, setBaselineRun] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [candidate, setCandidate] = useState(params.get("candidate") ?? "");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const comparison = await api.createComparison(
        mode === "run"
          ? { baseline_run_id: baselineRun, candidate_run_id: candidate }
          : { baseline_id: baselineId, candidate_run_id: candidate },
      );
      navigate(`/comparisons/${comparison.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  const ready = candidate && (mode === "run" ? baselineRun : baselineId);

  return (
    <>
      <div className="breadcrumbs">
        <Link to="/">Projects</Link> / <Link to={`/projects/${projectId}`}>Project</Link> /
      </div>
      <h1>Compare runs</h1>
      <p className="subtitle">
        Cases are matched by case key and models by name. Only metrics with the same version and
        configuration in both runs are compared.
      </p>
      <AsyncBlock state={runs}>
        {(page) =>
          page.items.length < 1 ? (
            <div className="alert info">This project has no completed runs to compare yet.</div>
          ) : (
            <form className="form" onSubmit={submit}>
              <fieldset>
                <legend>Baseline</legend>
                <label className="check">
                  <input type="radio" name="mode" checked={mode === "run"} onChange={() => setMode("run")} />
                  A completed run
                </label>
                <label className="check">
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === "saved"}
                    onChange={() => setMode("saved")}
                  />
                  A saved baseline
                </label>
                {mode === "run" ? (
                  <label>
                    Baseline run
                    <select required value={baselineRun} onChange={(e) => setBaselineRun(e.target.value)}>
                      <option value="">Choose…</option>
                      {page.items.map((r) => (
                        <option key={r.id} value={r.id}>
                          {runLabel(r)}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label>
                    Saved baseline
                    <select required value={baselineId} onChange={(e) => setBaselineId(e.target.value)}>
                      <option value="">Choose…</option>
                      {(baselines.data ?? []).map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} ({shortId(b.run_id)})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </fieldset>
              <label>
                Candidate run
                <select required value={candidate} onChange={(e) => setCandidate(e.target.value)}>
                  <option value="">Choose…</option>
                  {page.items.map((r) => (
                    <option key={r.id} value={r.id}>
                      {runLabel(r)}
                    </option>
                  ))}
                </select>
              </label>
              <ErrorMessage error={error} />
              <div>
                <button className="primary" type="submit" disabled={busy || !ready}>
                  {busy ? "Comparing…" : "Compare"}
                </button>
              </div>
            </form>
          )
        }
      </AsyncBlock>
    </>
  );
}
