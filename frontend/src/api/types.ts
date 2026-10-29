// Types mirroring the backend's API schemas (backend/app/schemas, backend/app/domain).

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  current_version: number;
  case_count: number;
  created_at: string;
  updated_at: string;
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  schema_version: string;
  content_hash: string;
  case_count: number;
  created_at: string;
}

export interface RetrievedContext {
  document_id: string;
  text: string;
  score?: number | null;
}

export interface EvaluationCase {
  case_key: string;
  input: Record<string, unknown>;
  expected_output: string | null;
  reference_context: string | null;
  retrieved_contexts: RetrievedContext[];
  relevant_document_ids: string[] | null;
  tags: string[];
  metadata: Record<string, unknown>;
}

export interface DatasetVersionDetail extends DatasetVersion {
  cases: EvaluationCase[];
  matching_cases: number;
  limit: number;
  offset: number;
}

export interface ModelConfig {
  id: string;
  project_id: string;
  name: string;
  provider: string;
  model_id: string;
  parameters: Record<string, unknown>;
  timeout_seconds: number | null;
  max_concurrency: number | null;
  secret_reference: string | null;
  created_at: string;
  updated_at: string;
}

export type MetricCategory = "answer_quality" | "retrieval_quality" | "performance" | "cost";
export type MetricDirection = "higher_is_better" | "lower_is_better";

export interface MetricInfo {
  name: string;
  version: string;
  category: MetricCategory;
  direction: MetricDirection;
  unit: string | null;
  score_range: [number | null, number | null];
  required_inputs: string[];
  description: string;
  config: Record<string, unknown>;
}

export interface MetricSummary {
  metric_version: string;
  scored_count: number;
  not_applicable_count: number;
  error_count: number;
  mean: number | null;
  median: number | null;
  p95: number | null;
  min: number | null;
  max: number | null;
  total: number | null;
  small_sample: boolean;
}

export interface ModelSummary {
  model_name: string;
  provider: string;
  model_id: string;
  case_count: number;
  success_count: number;
  error_count: number;
  error_rate: number;
  error_codes: Record<string, number>;
  usage: { cases_with_usage: number; input_tokens_total: number; output_tokens_total: number };
  metrics: Record<string, MetricSummary>;
}

export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface Run {
  id: string;
  project_id: string;
  status: RunStatus;
  dataset: { id: string; name: string; version: number; content_hash: string };
  progress: { total_cases: number; completed_cases: number; failed_cases: number };
  cancel_requested: boolean;
  models: ModelSummary[] | null;
  config_hash: string;
  config_snapshot: {
    metrics?: { name: string; version?: string | null; config?: Record<string, unknown> }[];
    models?: { name: string; provider: string; model_id: string }[];
    [key: string]: unknown;
  };
  software_version: string;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export type MetricStatus = "scored" | "not_applicable" | "error";

export interface MetricResult {
  metric_name: string;
  metric_version: string;
  score: number | null;
  status: MetricStatus;
  details: Record<string, unknown>;
}

export interface CaseResult {
  id: string;
  run_id: string;
  case_key: string;
  model_name: string;
  provider: string;
  model_id: string;
  status: "success" | "error";
  tags: string[];
  input: Record<string, unknown>;
  expected_output: string | null;
  actual_output: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string;
  metrics: MetricResult[];
}

export interface MetricSelection {
  name: string;
  version?: string;
  config?: Record<string, unknown>;
}

export interface RunCreate {
  project_id: string;
  dataset_id: string;
  dataset_version?: number;
  model_config_ids: string[];
  metrics: MetricSelection[];
  run_config?: Partial<{
    timeout_seconds: number;
    max_concurrency: number;
    max_retries: number;
    retry_backoff_seconds: number;
  }>;
}

export type Verdict = "improved" | "regressed" | "unchanged" | "not_comparable";

export interface MetricDelta {
  metric: string;
  aggregation: string;
  category: MetricCategory | null;
  direction: MetricDirection;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
  relative_delta: number | null;
  verdict: Verdict;
  reason: string | null;
}

export interface CaseChange {
  case_key: string;
  baseline_state: string;
  candidate_state: string;
  baseline_reasons: string[];
  candidate_reasons: string[];
}

export interface ScoreChange {
  case_key: string;
  metric: string;
  baseline: number;
  candidate: number;
  delta: number;
  verdict: "improved" | "regressed";
}

export interface ModelComparison {
  baseline_model: string;
  candidate_model: string;
  cases_compared: number;
  cases_only_in_baseline: string[];
  cases_only_in_candidate: string[];
  error_rate: MetricDelta;
  metrics: MetricDelta[];
  newly_failing: CaseChange[];
  recovered: CaseChange[];
  score_changes: ScoreChange[];
  regressed: boolean;
}

export interface RunComparison {
  baseline: { run_id: string; dataset_name: string; finished_at: string };
  candidate: { run_id: string; dataset_name: string; finished_at: string };
  same_dataset: boolean;
  excluded_metrics: Record<string, string>;
  warnings: string[];
  models: ModelComparison[];
  newly_failing_count: number;
  recovered_count: number;
  regressed: boolean;
}

export interface Comparison {
  id: string;
  project_id: string;
  baseline_run_id: string;
  candidate_run_id: string;
  created_at: string;
  result: RunComparison;
}

export interface ComparisonListItem {
  id: string;
  project_id: string;
  baseline_run_id: string;
  candidate_run_id: string;
  created_at: string;
  regressed: boolean;
  newly_failing_count: number;
  recovered_count: number;
}

export interface Baseline {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  run_id: string;
  created_at: string;
  updated_at: string;
}

export interface GateRule {
  metric: string;
  aggregation: string;
  kind?: "absolute" | "relative";
  operator?: string;
  threshold?: number;
  max_regression?: number;
  regression_unit?: "absolute" | "percent";
  model?: string;
  tag?: string;
}

export interface Gate {
  id: string;
  project_id: string;
  name: string;
  missing_metric_policy: "fail" | "skip" | "warn";
  rules: GateRule[];
  created_at: string;
  updated_at: string;
}

export interface RuleOutcome {
  rule: string;
  kind: "absolute" | "relative";
  metric: string;
  model: string;
  tag: string | null;
  actual: number | null;
  baseline: number | null;
  regression: number | null;
  threshold: number;
  status: "passed" | "failed" | "skipped" | "warned";
  reason: string | null;
}

export interface GateResult {
  gate_name: string;
  passed: boolean;
  baseline_run_id: string | null;
  results: RuleOutcome[];
}
