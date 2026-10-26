"""Report rendering: JSON (machine-readable, the source of truth) and Markdown (human)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.domain.runs import CaseStatus, RunReport

MAX_FAILURES_LISTED = 20
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    """Neutralize spreadsheet formula injection: model output is untrusted text."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def render_csv(report: RunReport) -> str:
    """One row per (model, case) with a score and status column per metric."""
    metric_names = [m.name for m in report.metrics]
    header = [
        "run_id", "model_name", "provider", "model_id", "case_key", "status", "tags",
        "expected_output", "actual_output", "latency_ms", "input_tokens", "output_tokens",
        "attempts", "error_code", "error_message",
    ]  # fmt: skip
    for name in metric_names:
        header += [f"{name}_score", f"{name}_status"]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for result in report.results:
        by_name = {m.metric_name: m for m in result.metrics}
        row: list[object] = [
            report.run_id, result.model_name, result.provider, result.model_id,
            result.case_key, result.status, ";".join(result.tags), result.expected_output,
            result.actual_output, result.latency_ms, result.input_tokens, result.output_tokens,
            result.attempts, result.error_code, result.error_message,
        ]  # fmt: skip
        for name in metric_names:
            metric = by_name.get(name)
            row += [metric.score if metric else None, metric.status if metric else None]
        writer.writerow([_csv_safe(value) for value in row])
    return buffer.getvalue()


def write_json_report(report: RunReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: RunReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _cell(text: str | None, limit: int = 80) -> str:
    if text is None:
        return ""
    flat = " ".join(text.split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# Evaluation report: {report.project}",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: {report.status}",
        f"- Started: {report.started_at.isoformat()} · Finished: {report.finished_at.isoformat()}",
        f"- Dataset: {report.dataset.name} ({report.dataset.case_count} cases, "
        f"`{report.dataset.content_hash[:19]}…`)",
        f"- Config hash: `{report.config_hash[:19]}…` · Software: {report.software_version}",
        "- Metrics: " + ", ".join(f"{m.name} v{m.version}" for m in report.metrics),
        "",
        "## Summary by model",
        "",
    ]

    metric_names = [m.name for m in report.metrics]
    header = ["Model", "Cases", "Errors", "Error rate"]
    for name in metric_names:
        header += [f"{name} mean", f"{name} p95"] if name == "latency" else [f"{name} mean"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for summary in report.summaries:
        row = [
            f"{summary.model_name} ({summary.provider}/{summary.model_id})",
            str(summary.case_count),
            str(summary.error_count),
            _fmt(summary.error_rate),
        ]
        for name in metric_names:
            stats = summary.metrics.get(name)
            mean = _fmt(stats.mean if stats else None)
            row += [mean, _fmt(stats.p95 if stats else None)] if name == "latency" else [mean]
        lines.append("| " + " | ".join(row) + " |")

    small = [
        s.model_name for s in report.summaries if any(m.small_sample for m in s.metrics.values())
    ]
    if small:
        lines += [
            "",
            f"> Small sample (< 20 scored cases) for: {', '.join(small)}. "
            "Treat p95 and other percentiles as indicative only.",
        ]

    if report.gate is not None:
        verdict = "PASSED" if report.gate.passed else "FAILED"
        lines += ["", f"## Gate `{report.gate.gate_name}`: {verdict}", ""]
        lines.append("| Model | Rule | Actual | Status | Reason |")
        lines.append("|---|---|---|---|---|")
        for outcome in report.gate.results:
            lines.append(
                f"| {outcome.model} | `{outcome.rule}` | {_fmt(outcome.actual)} | "
                f"{outcome.status} | {_cell(outcome.reason)} |"
            )

    failures = [
        r
        for r in report.results
        if r.status == CaseStatus.ERROR
        or any(m.metric_name == "exact_match" and m.score == 0.0 for m in r.metrics)
    ]
    lines += ["", f"## Failed cases ({len(failures)})", ""]
    if not failures:
        lines.append("None.")
    else:
        lines.append("| Model | Case | Expected | Actual | Error |")
        lines.append("|---|---|---|---|---|")
        for result in failures[:MAX_FAILURES_LISTED]:
            lines.append(
                f"| {result.model_name} | `{result.case_key}` | {_cell(result.expected_output)} | "
                f"{_cell(result.actual_output)} | {_cell(result.error_code)} |"
            )
        if len(failures) > MAX_FAILURES_LISTED:
            lines.append(f"\n…and {len(failures) - MAX_FAILURES_LISTED} more in the JSON report.")

    lines += [
        "",
        "---",
        "Scores are only as reliable as the dataset and metric definitions. "
        "Errored cases are excluded from quality metrics and counted in the error rate.",
        "",
    ]
    return "\n".join(lines)
