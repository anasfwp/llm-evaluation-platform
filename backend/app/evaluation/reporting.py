"""Report rendering: JSON (machine-readable, the source of truth) and Markdown (human)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.domain.comparison import RunComparison, Verdict
from app.domain.runs import RunReport, UsageSummary
from app.evaluation.comparison import case_state, is_quality

MAX_FAILURES_LISTED = 20
MAX_CHANGES_LISTED = 20
# Same default as comparisons: a quality score must reach half of its range to pass.
DEFAULT_PASS_THRESHOLD = 0.5
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
    if value is None:
        return "n/a"
    if 0 < abs(value) < 10**-digits:  # e.g. per-case costs in USD
        return f"{value:.3g}"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


# Statistics shown next to the mean for specific metrics.
_EXTRA_COLUMNS: dict[str, tuple[str, ...]] = {"latency": ("p95",), "estimated_cost": ("total",)}


def _tokens(usage: UsageSummary) -> str:
    if usage.cases_with_usage == 0:
        return "n/a"
    return f"{usage.input_tokens_total} / {usage.output_tokens_total}"


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
    header = ["Model", "Cases", "Errors", "Error rate", "Tokens in / out"]
    for name in metric_names:
        header += [f"{name} mean", *(f"{name} {extra}" for extra in _EXTRA_COLUMNS.get(name, ()))]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for summary in report.summaries:
        row = [
            f"{summary.model_name} ({summary.provider}/{summary.model_id})",
            str(summary.case_count),
            str(summary.error_count),
            _fmt(summary.error_rate),
            _tokens(summary.usage),
        ]
        for name in metric_names:
            stats = summary.metrics.get(name)
            row.append(_fmt(stats.mean if stats else None))
            for extra in _EXTRA_COLUMNS.get(name, ()):
                row.append(_fmt(getattr(stats, extra) if stats else None))
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

    if "estimated_cost" in metric_names:
        lines += [
            "",
            "> estimated_cost is in USD, from provider-reported tokens and the pricing table "
            "frozen into this run's config. It is an estimate, not billing data.",
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

    quality = {m.name: m for m in report.metrics if is_quality(m)}
    failures = [
        (result, reasons)
        for result in report.results
        for state, reasons in [case_state(result, quality, DEFAULT_PASS_THRESHOLD)]
        if state == "fail"
    ]
    lines += ["", f"## Failed cases ({len(failures)})", ""]
    lines.append(
        "A case fails when the model call errored or a quality metric scored below half of "
        "its range."
    )
    lines.append("")
    if not failures:
        lines.append("None.")
    else:
        lines.append("| Model | Case | Expected | Actual | Why |")
        lines.append("|---|---|---|---|---|")
        for result, reasons in failures[:MAX_FAILURES_LISTED]:
            lines.append(
                f"| {result.model_name} | `{result.case_key}` | {_cell(result.expected_output)} | "
                f"{_cell(result.actual_output)} | {_cell('; '.join(reasons))} |"
            )
        if len(failures) > MAX_FAILURES_LISTED:
            lines.append(f"\n…and {len(failures) - MAX_FAILURES_LISTED} more in the JSON report.")

    if report.comparison is not None:
        lines += ["", *render_comparison_sections(report.comparison, heading_level=2)]

    lines += [
        "",
        "---",
        "Scores are only as reliable as the dataset and metric definitions. "
        "Errored cases are excluded from quality metrics and counted in the error rate.",
        "",
    ]
    return "\n".join(lines)


def _signed(value: float | None) -> str:
    if value is None:
        return "n/a"
    return ("+" if value > 0 else "") + _fmt(value)


def render_comparison_sections(comparison: RunComparison, *, heading_level: int = 2) -> list[str]:
    """Markdown sections describing regressions and improvements against a baseline."""
    h = "#" * heading_level
    verdict = "REGRESSED" if comparison.regressed else "no regressions"
    lines = [
        f"{h} Comparison with baseline: {verdict}",
        "",
        f"- Baseline run: `{comparison.baseline.run_id}` ({comparison.baseline.dataset_name})",
        f"- Candidate run: `{comparison.candidate.run_id}` ({comparison.candidate.dataset_name})",
        f"- Same dataset content: {'yes' if comparison.same_dataset else 'no'}",
        f"- Newly failing cases: {comparison.newly_failing_count} · "
        f"recovered: {comparison.recovered_count}",
    ]
    for warning in comparison.warnings:
        lines.append(f"- Warning: {warning}")
    for name, reason in comparison.excluded_metrics.items():
        lines.append(f"- Not compared: `{name}` ({reason})")

    for model in comparison.models:
        pair = (
            model.candidate_model
            if model.baseline_model == model.candidate_model
            else f"{model.baseline_model} → {model.candidate_model}"
        )
        lines += [
            "",
            f"{h}# {pair} ({model.cases_compared} aligned cases)",
            "",
            "| Metric | Baseline | Candidate | Delta | Verdict |",
            "|---|---|---|---|---|",
        ]
        for delta in [model.error_rate, *model.metrics]:
            mark = " ⚠" if delta.verdict == Verdict.REGRESSED else ""
            lines.append(
                f"| {delta.metric} {delta.aggregation} | {_fmt(delta.baseline)} | "
                f"{_fmt(delta.candidate)} | {_signed(delta.delta)} | {delta.verdict}{mark} |"
            )
        if model.newly_failing:
            lines += ["", f"Newly failing ({len(model.newly_failing)}):", ""]
            for change in model.newly_failing[:MAX_CHANGES_LISTED]:
                why = "; ".join(change.candidate_reasons)
                lines.append(f"- `{change.case_key}`: {_cell(why, 120)}")
        if model.recovered:
            lines += ["", f"Recovered ({len(model.recovered)}):", ""]
            for change in model.recovered[:MAX_CHANGES_LISTED]:
                lines.append(f"- `{change.case_key}`")
        regressions = [c for c in model.score_changes if c.verdict == "regressed"]
        if regressions:
            lines += ["", "Largest score drops:", ""]
            for drop in regressions[:MAX_CHANGES_LISTED]:
                lines.append(
                    f"- `{drop.case_key}` {drop.metric}: {_fmt(drop.baseline)} → "
                    f"{_fmt(drop.candidate)}"
                )
    return lines


def render_comparison_markdown(comparison: RunComparison) -> str:
    lines = [
        f"# Run comparison: {comparison.candidate.project}",
        "",
        *render_comparison_sections(comparison, heading_level=2),
        "",
        "---",
        "Cases are aligned by case_key; only metrics with the same version and configuration "
        "in both runs are compared. Latency and cost deltas are informational; gate on them "
        "with relative rules.",
        "",
    ]
    return "\n".join(lines)
