"""``llm-eval`` command-line interface.

Exit codes: 0 success/pass, 1 gate failure, 2 invalid configuration/input,
3 provider/run failure, 4 unexpected internal error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app import __version__
from app.core.errors import InputValidationError
from app.domain.gates import GateResult
from app.domain.runs import RunReport
from app.evaluation.engine import run_evaluation
from app.evaluation.gates import evaluate_gate
from app.evaluation.loader import load_config, load_gate_config, load_report
from app.evaluation.registry import METRICS
from app.evaluation.reporting import write_json_report, write_markdown_report

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_INVALID_INPUT = 2
EXIT_RUN_FAILED = 3
EXIT_INTERNAL_ERROR = 4


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-eval",
        description="Run repeatable LLM evaluations and enforce quality gates.",
        epilog=(
            "Exit codes: 0 pass, 1 gate failed, 2 invalid input, 3 run failure, 4 internal error."
        ),
    )
    parser.add_argument("--version", action="version", version=f"llm-eval {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    validate = commands.add_parser(
        "validate", help="Validate a config, its dataset, and gate rules without model calls."
    )
    validate.add_argument("--config", required=True, type=Path, help="Evaluation config YAML.")
    validate.add_argument("--gates", type=Path, help="Gate rules YAML (overrides config 'gates').")

    run = commands.add_parser("run", help="Run an evaluation and write reports.")
    run.add_argument("--config", required=True, type=Path, help="Evaluation config YAML.")
    run.add_argument("--output", type=Path, help="JSON report path (overrides config).")
    run.add_argument("--markdown", type=Path, help="Markdown report path (overrides config).")
    run.add_argument("--gates", type=Path, help="Gate rules YAML (overrides config 'gates').")
    run.add_argument("--json", action="store_true", help="Print a machine-readable summary.")

    gate = commands.add_parser("gate", help="Evaluate gate rules against an existing JSON report.")
    gate.add_argument("--report", required=True, type=Path, help="JSON report from 'run'.")
    gate.add_argument("--rules", required=True, type=Path, help="Gate rules YAML.")
    gate.add_argument("--json", action="store_true", help="Print a machine-readable result.")

    metrics = commands.add_parser("metrics", help="Inspect available metrics.")
    metrics_commands = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_list = metrics_commands.add_parser("list", help="List metrics and their inputs.")
    metrics_list.add_argument("--json", action="store_true", help="Print JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "gate":
            return _cmd_gate(args)
        return _cmd_metrics_list(args)
    except InputValidationError as exc:
        print(f"error: invalid input\n{exc.format()}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    except Exception as exc:
        print(f"error: unexpected internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def _cmd_validate(args: argparse.Namespace) -> int:
    loaded = load_config(args.config, gate_override=args.gates)
    print(f"OK  config   {loaded.path}")
    print(f"OK  dataset  {loaded.dataset_path} ({len(loaded.dataset.cases)} cases)")
    print(f"OK  models   {', '.join(m.name for m in loaded.config.models)}")
    print(f"OK  metrics  {', '.join(f'{m.name} v{m.version}' for m in loaded.metrics)}")
    if loaded.gate is not None:
        print(f"OK  gates    {loaded.gate_path} ({len(loaded.gate.rules)} rules)")
    return EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    loaded = load_config(args.config, gate_override=args.gates)
    report = asyncio.run(run_evaluation(loaded.build_plan()))
    if loaded.gate is not None:
        report = report.model_copy(update={"gate": evaluate_gate(loaded.gate, report.summaries)})

    report_settings = loaded.config.report
    json_path = args.output or (
        loaded.resolve(report_settings.json_path) if report_settings.json_path else None
    )
    markdown_path = args.markdown or (
        loaded.resolve(report_settings.markdown_path) if report_settings.markdown_path else None
    )
    if json_path is not None:
        write_json_report(report, json_path)
    if markdown_path is not None:
        write_markdown_report(report, markdown_path)

    failed_models = [s.model_name for s in report.summaries if s.all_failed]
    if failed_models:
        exit_code = EXIT_RUN_FAILED
    elif report.gate is not None and not report.gate.passed:
        exit_code = EXIT_GATE_FAILED
    else:
        exit_code = EXIT_OK

    if args.json:
        payload = {
            "exit_code": exit_code,
            "run_id": report.run_id,
            "status": report.status,
            "report_json": str(json_path) if json_path else None,
            "report_markdown": str(markdown_path) if markdown_path else None,
            "summaries": [s.model_dump(mode="json") for s in report.summaries],
            "gate": report.gate.model_dump(mode="json") if report.gate else None,
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_run_summary(report)
        for path in (json_path, markdown_path):
            if path is not None:
                print(f"Report written: {path}")
        if failed_models:
            names = ", ".join(failed_models)
            print(f"Run failure: every case errored for {names}", file=sys.stderr)
    return exit_code


def _cmd_gate(args: argparse.Namespace) -> int:
    report = load_report(args.report)
    gate = load_gate_config(args.rules)
    result = evaluate_gate(gate, report.summaries)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        _print_gate(result)
    return EXIT_OK if result.passed else EXIT_GATE_FAILED


def _cmd_metrics_list(args: argparse.Namespace) -> int:
    infos = [cls.describe() for cls in METRICS.values()]
    if args.json:
        print(json.dumps([info.model_dump(mode="json") for info in infos], indent=2))
        return EXIT_OK
    for info in infos:
        unit = f" [{info.unit}]" if info.unit else ""
        print(f"{info.name} v{info.version} ({info.category}, {info.direction}){unit}")
        print(f"    requires: {', '.join(info.required_inputs)}")
        print(f"    {info.description}")
    return EXIT_OK


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _print_run_summary(report: RunReport) -> None:
    print(f"Run {report.run_id}  project={report.project}  status={report.status}")
    print(f"Dataset {report.dataset.name}: {report.dataset.case_count} cases")
    for summary in report.summaries:
        print(
            f"\n  {summary.model_name} ({summary.provider}/{summary.model_id}): "
            f"{summary.success_count}/{summary.case_count} succeeded, "
            f"error_rate={_fmt(summary.error_rate)}"
        )
        for name, stats in summary.metrics.items():
            note = "  (small sample)" if stats.small_sample and name == "latency" else ""
            print(
                f"    {name:<12} mean={_fmt(stats.mean)} median={_fmt(stats.median)} "
                f"p95={_fmt(stats.p95)} scored={stats.scored_count} "
                f"n/a={stats.not_applicable_count}{note}"
            )
        if summary.error_codes:
            codes = ", ".join(f"{code}={count}" for code, count in summary.error_codes.items())
            print(f"    errors: {codes}")
    if report.gate is not None:
        print()
        _print_gate(report.gate)


def _print_gate(result: GateResult) -> None:
    print(f"Gate '{result.gate_name}': {'PASSED' if result.passed else 'FAILED'}")
    for outcome in result.results:
        reason = f"  - {outcome.reason}" if outcome.reason else ""
        print(
            f"  [{outcome.status.upper():<7}] {outcome.model}: {outcome.rule} "
            f"(actual={_fmt(outcome.actual)}){reason}"
        )


if __name__ == "__main__":
    sys.exit(main())
