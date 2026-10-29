import type {
  Baseline,
  CaseResult,
  Comparison,
  ComparisonListItem,
  Dataset,
  DatasetVersion,
  DatasetVersionDetail,
  Gate,
  GateResult,
  MetricInfo,
  ModelConfig,
  Page,
  Project,
  Run,
  RunCreate,
} from "./types";

export interface ErrorDetail {
  field: string | null;
  message: string;
}

/** An error response from the API, unpacked from its `{error: {...}}` envelope. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ErrorDetail[] = [],
    readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  static async from(response: Response): Promise<ApiError> {
    try {
      const body = (await response.json()) as {
        error?: { code?: string; message?: string; details?: ErrorDetail[]; request_id?: string };
      };
      const error = body.error ?? {};
      return new ApiError(
        response.status,
        error.code ?? "HTTP_ERROR",
        error.message ?? `Request failed with status ${response.status}`,
        error.details ?? [],
        error.request_id ?? response.headers.get("X-Request-ID"),
      );
    } catch {
      return new ApiError(
        response.status,
        "HTTP_ERROR",
        `Request failed with status ${response.status}`,
      );
    }
  }
}

const BASE = "/api/v1";

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: "application/json" } };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await fetch(withQuery(`${BASE}${path}`, query), init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the API. Is the backend running?");
  }
  if (!response.ok) throw await ApiError.from(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** URL for a download link (reports, exports); the browser handles the file. */
export function downloadUrl(path: string, query?: Query): string {
  return withQuery(`${BASE}${path}`, query);
}

export const api = {
  listProjects: (query?: Query) => request<Page<Project>>("GET", "/projects", undefined, query),
  getProject: (id: string) => request<Project>("GET", `/projects/${id}`),
  createProject: (data: { name: string; description?: string }) =>
    request<Project>("POST", "/projects", data),

  listDatasets: (projectId: string) =>
    request<Page<Dataset>>("GET", `/projects/${projectId}/datasets`, undefined, { limit: 200 }),
  getDataset: (id: string) => request<Dataset>("GET", `/datasets/${id}`),
  listVersions: (id: string) => request<DatasetVersion[]>("GET", `/datasets/${id}/versions`),
  getVersion: (id: string, version: number, query?: Query) =>
    request<DatasetVersionDetail>("GET", `/datasets/${id}/versions/${version}`, undefined, query),
  importDataset: (projectId: string, file: File, name?: string) => {
    const form = new FormData();
    form.set("project_id", projectId);
    form.set("file", file);
    if (name) form.set("name", name);
    return request<Dataset>("POST", "/datasets/import", form);
  },

  listModels: (projectId: string) =>
    request<Page<ModelConfig>>("GET", `/projects/${projectId}/models`, undefined, { limit: 200 }),
  createModel: (projectId: string, data: Partial<ModelConfig>) =>
    request<ModelConfig>("POST", `/projects/${projectId}/models`, data),

  listMetrics: () => request<MetricInfo[]>("GET", "/metrics"),

  listRuns: (query?: Query) => request<Page<Run>>("GET", "/runs", undefined, query),
  getRun: (id: string) => request<Run>("GET", `/runs/${id}`),
  startRun: (data: RunCreate) =>
    request<{ run_id: string; status: string; status_url: string }>("POST", "/runs", data),
  cancelRun: (id: string) => request<Run>("POST", `/runs/${id}/cancel`),
  listResults: (id: string, query?: Query) =>
    request<Page<CaseResult>>("GET", `/runs/${id}/results`, undefined, query),

  createComparison: (data: {
    baseline_run_id?: string;
    baseline_id?: string;
    candidate_run_id: string;
  }) => request<Comparison>("POST", "/comparisons", data),
  getComparison: (id: string) => request<Comparison>("GET", `/comparisons/${id}`),
  listComparisons: (projectId: string) =>
    request<Page<ComparisonListItem>>("GET", "/comparisons", undefined, {
      project_id: projectId,
      limit: 50,
    }),

  listBaselines: (projectId: string) =>
    request<Baseline[]>("GET", `/projects/${projectId}/baselines`),
  createBaseline: (projectId: string, data: { name: string; run_id: string }) =>
    request<Baseline>("POST", `/projects/${projectId}/baselines`, data),

  listGates: (projectId: string) => request<Gate[]>("GET", `/projects/${projectId}/gates`),
  evaluateGate: (data: { run_id: string; gate_id: string; baseline_id?: string }) =>
    request<GateResult>("POST", "/gates/evaluate", data),
};
