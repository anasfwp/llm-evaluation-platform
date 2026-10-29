"""End-to-end RAG demo: retrieval metrics, a fake groundedness judge, gates and comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.cli.main import EXIT_GATE_FAILED, EXIT_OK, main

REPO_ROOT = Path(__file__).resolve().parents[3]
RAG_CONFIG = REPO_ROOT / "evals" / "demo_rag_config.yaml"
RAG_GATES = REPO_ROOT / "evals" / "gates.rag.yaml"


def _metric(report: dict[str, Any], model: str, case: str, metric: str) -> dict[str, Any]:
    result = next(
        r for r in report["results"] if r["model_name"] == model and r["case_key"] == case
    )
    found: dict[str, Any] = next(m for m in result["metrics"] if m["metric_name"] == metric)
    return found


@pytest.fixture(scope="module")
def rag_report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    path = tmp_path_factory.mktemp("rag") / "run.json"
    code = main(["run", "--config", str(RAG_CONFIG), "--gates", str(RAG_GATES),
                 "--output", str(path)])  # fmt: skip
    assert code == EXIT_OK
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    report["_path"] = str(path)
    return report


def test_retrieval_metrics_follow_the_labels(rag_report: dict[str, Any]) -> None:
    assert rag_report["gate"]["passed"] is True
    model = "fake-grounded"
    # Relevant document ranked second of three: precision 1/3, recall 1, reciprocal rank 1/2.
    assert _metric(rag_report, model, "support-hours", "retrieval_precision_at_k")["score"] == (
        pytest.approx(1 / 3)
    )
    assert _metric(rag_report, model, "support-hours", "retrieval_recall_at_k")["score"] == 1.0
    assert _metric(rag_report, model, "support-hours", "reciprocal_rank")["score"] == 0.5
    # The retriever missed the only relevant document.
    for metric in ("retrieval_precision_at_k", "retrieval_recall_at_k", "reciprocal_rank"):
        assert _metric(rag_report, model, "battery-replacement", metric)["score"] == 0.0
    # No relevance labels: not applicable rather than zero.
    unlabelled = _metric(rag_report, model, "unlabelled-summary", "retrieval_recall_at_k")
    assert unlabelled["status"] == "not_applicable"
    assert _metric(rag_report, model, "unlabelled-summary", "token_f1")["status"] == (
        "not_applicable"
    )
    summaries = {s["model_name"]: s["metrics"] for s in rag_report["summaries"]}
    # Retrieval scores describe the recorded rankings, so both models get the same values.
    assert (
        summaries["fake-grounded"]["retrieval_recall_at_k"]
        == summaries["fake-hallucinating"]["retrieval_recall_at_k"]
    )


def test_groundedness_judge_separates_the_models(rag_report: dict[str, Any]) -> None:
    summaries = {s["model_name"]: s["metrics"] for s in rag_report["summaries"]}
    grounded = summaries["fake-grounded"]["llm_judge_groundedness"]["mean"]
    hallucinating = summaries["fake-hallucinating"]["llm_judge_groundedness"]["mean"]
    assert grounded >= 4 > hallucinating
    details = _metric(rag_report, "fake-hallucinating", "returns-window", "llm_judge_groundedness")
    assert details["score"] <= 2
    assert details["details"]["rubric_version"] == "1.0"
    assert details["details"]["judge_provider"] == "fake"
    # Groundedness only needs context, so it applies to the unlabelled open-ended case too.
    open_ended = _metric(
        rag_report, "fake-grounded", "unlabelled-summary", "llm_judge_groundedness"
    )
    assert open_ended["status"] == "scored"


def test_unscoped_groundedness_gate_fails(rag_report: dict[str, Any], tmp_path: Path) -> None:
    strict = tmp_path / "strict.yaml"
    rule = {"metric": "llm_judge_groundedness", "aggregation": "mean", "operator": "gte",
            "threshold": 4}  # fmt: skip
    strict.write_text(yaml.safe_dump({"rules": [rule]}), encoding="utf-8")
    assert main(["gate", "--report", rag_report["_path"], "--rules", str(strict)]) == (
        EXIT_GATE_FAILED
    )


def test_swapping_in_the_hallucinating_model_is_a_regression(
    rag_report: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    path = rag_report["_path"]
    args = ["compare", "--baseline", path, "--candidate", path,
            "--pair", "fake-grounded=fake-hallucinating",
            "--fail-on-regression", "--json"]  # fmt: skip
    assert main(args) == EXIT_GATE_FAILED
    printed = json.loads(capsys.readouterr().out)
    assert printed["regressed"] is True
    assert printed["newly_failing_count"] >= 1
