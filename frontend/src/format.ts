import type { MetricDirection } from "./api/types";

/** Series colours in fixed slot order; colour follows the entity, never its rank. */
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];
export const MAX_SERIES = SERIES.length;

/** A stable colour per name, assigned by first appearance in `names`. */
export function seriesColor(names: readonly string[], name: string): string {
  const index = names.indexOf(name);
  return SERIES[index >= 0 ? index % SERIES.length : 0] ?? SERIES[0]!;
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (!Number.isFinite(value)) return value > 0 ? "∞" : "-∞";
  if (Number.isInteger(value)) return value.toLocaleString();
  const abs = Math.abs(value);
  if (abs >= 1000) return Math.round(value).toLocaleString();
  return Number(value.toPrecision(digits)).toString();
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const text = formatNumber(value);
  return value > 0 ? `+${text}` : text;
}

export function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0 || Math.abs(value) >= 0.01) return `$${value.toFixed(2)}`;
  // Sub-cent amounts keep two significant digits: $0.000012, not $0.00001.
  const digits = Math.min(10, 1 - Math.floor(Math.log10(Math.abs(value))));
  return `$${value.toFixed(digits)}`;
}

/** A metric value in its natural unit. */
export function formatMetric(metric: string, value: number | null | undefined): string {
  if (metric === "latency") return value == null ? "—" : `${formatNumber(value)} ms`;
  if (metric === "estimated_cost") return formatCost(value);
  return formatNumber(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function directionLabel(direction: MetricDirection): string {
  return direction === "higher_is_better" ? "higher is better" : "lower is better";
}

/** "Nice" axis maximum and ticks for a value domain starting at zero. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? rough;
  const ticks: number[] = [];
  for (let v = 0; v <= max + step * 0.5 && ticks.length < 12; v += step) {
    ticks.push(Number(v.toPrecision(10)));
  }
  if (ticks[ticks.length - 1]! < max) ticks.push(Number((ticks.length * step).toPrecision(10)));
  return ticks;
}
