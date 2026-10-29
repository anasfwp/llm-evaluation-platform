import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import type { Comparison, Run } from "../api/types";

type Routes = Record<string, unknown>;

/** Serve canned JSON by request path (query string ignored); unknown paths are 404s. */
function mockApi(routes: Routes) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input).split("?")[0]!;
    const key = `${init?.method ?? "GET"} ${url}`;
    if (key in routes) return new Response(JSON.stringify(routes[key]), { status: 200 });
    return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: `no route ${key}` } }), {
      status: 404,
    });
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

afterEach(() => vi.restoreAllMocks());

const delta = (metric: string, baseline: number, candidate: number, verdict: string) => ({
  metric,
  aggregation: "mean",
  category: "answer_quality",
  direction: "higher_is_better",
  baseline,
  candidate,
  delta: candidate - baseline,
  relative_delta: null,
  verdict,
  reason: null,
});

const comparison: Comparison = {
  id: "c0ffee00-0000-0000-0000-000000000000",
  project_id: "p1",
  baseline_run_id: "b0000000-0000",
  candidate_run_id: "d0000000-0000",
  created_at: "2026-10-28T10:00:00Z",
  result: {
    baseline: { run_id: "b0000000-0000", dataset_name: "demo", finished_at: "2026-10-27T10:00:00Z" },
    candidate: { run_id: "d0000000-0000", dataset_name: "demo", finished_at: "2026-10-28T10:00:00Z" },
    same_dataset: true,
    excluded_metrics: { token_f1: "not computed in the baseline run" },
    warnings: [],
    newly_failing_count: 1,
    recovered_count: 0,
    regressed: true,
    models: [
      {
        baseline_model: "model-a",
        candidate_model: "model-a",
        cases_compared: 4,
        cases_only_in_baseline: [],
        cases_only_in_candidate: [],
        error_rate: { ...delta("error_rate", 0, 0, "unchanged"), aggregation: "overall" },
        metrics: [delta("exact_match", 1, 0.75, "regressed")] as never,
        newly_failing: [
          {
            case_key: "case-1",
            baseline_state: "pass",
            candidate_state: "fail",
            baseline_reasons: [],
            candidate_reasons: ["exact_match=0"],
          },
        ],
        recovered: [],
        score_changes: [],
        regressed: true,
      },
    ] as never,
  },
};

describe("pages", () => {
  it("shows an empty projects list with a create form", async () => {
    mockApi({ "GET /api/v1/projects": { items: [], total: 0, limit: 100, offset: 0 } });
    renderAt("/");
    expect(await screen.findByText(/No projects yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create project" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Name"), "demo");
    expect(screen.getByRole("button", { name: "Create project" })).toBeEnabled();
  });

  it("renders a comparison with verdicts, failing cases and excluded metrics", async () => {
    mockApi({ [`GET /api/v1/comparisons/${comparison.id}`]: comparison });
    renderAt(`/comparisons/${comparison.id}`);
    expect(await screen.findByRole("heading", { name: /Comparison c0ffee00/ })).toBeInTheDocument();
    expect(screen.getAllByText("Regressed").length).toBeGreaterThan(0);
    const failing = screen.getByRole("heading", { name: "Newly failing cases (1)" });
    expect(failing).toBeInTheDocument();
    expect(screen.getByText("case-1")).toBeInTheDocument();
    expect(screen.getByText("exact_match=0")).toBeInTheDocument();
    expect(screen.getByText(/Metrics not compared \(1\)/)).toBeInTheDocument();
    const table = screen.getAllByRole("table")[0]!;
    expect(within(table).getByText("-0.25")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download regression report" })).toHaveAttribute(
      "href",
      `/api/v1/comparisons/${comparison.id}/report?format=markdown`,
    );
  });

  it("shows API errors with their details", async () => {
    mockApi({});
    renderAt("/runs/missing");
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found");
  });

  it("renders a completed run's summary and report links", async () => {
    const run: Run = {
      id: "a1b2c3d4-0000",
      project_id: "p1",
      status: "completed",
      dataset: { id: "d1", name: "demo", version: 1, content_hash: "sha256:x" },
      progress: { total_cases: 2, completed_cases: 2, failed_cases: 0 },
      cancel_requested: false,
      models: [
        {
          model_name: "model-a",
          provider: "fake",
          model_id: "fake-1",
          case_count: 2,
          success_count: 2,
          error_count: 0,
          error_rate: 0,
          error_codes: {},
          usage: { cases_with_usage: 0, input_tokens_total: 0, output_tokens_total: 0 },
          metrics: {
            exact_match: {
              metric_version: "1.0",
              scored_count: 2,
              not_applicable_count: 0,
              error_count: 0,
              mean: 0.5,
              median: 0.5,
              p95: 1,
              min: 0,
              max: 1,
              total: null,
              small_sample: true,
            },
          },
        },
      ],
      config_hash: "h",
      config_snapshot: { models: [{ name: "model-a", provider: "fake", model_id: "fake-1" }] },
      software_version: "0.1.0",
      error_message: null,
      created_at: "2026-10-28T10:00:00Z",
      started_at: "2026-10-28T10:00:00Z",
      finished_at: "2026-10-28T10:00:02Z",
    };
    mockApi({
      [`GET /api/v1/runs/${run.id}`]: run,
      "GET /api/v1/metrics": [],
      [`GET /api/v1/runs/${run.id}/results`]: { items: [], total: 0, limit: 25, offset: 0 },
      "GET /api/v1/projects/p1/gates": [],
      "GET /api/v1/projects/p1/baselines": [],
    });
    renderAt(`/runs/${run.id}`);
    expect(await screen.findByRole("img", { name: /exact_match — mean/ })).toBeInTheDocument();
    expect(screen.getByLabelText("model-a, mean: 0.5")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Markdown report" })).toHaveAttribute(
      "href",
      `/api/v1/runs/${run.id}/report?format=markdown`,
    );
    expect(await screen.findByText("No case results match these filters.")).toBeInTheDocument();
    expect(screen.getByText("This project has no saved gates.")).toBeInTheDocument();
  });
});
