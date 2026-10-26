from __future__ import annotations

import asyncio
import csv
import io
from collections.abc import Callable

from app.domain.datasets import Dataset, EvaluationCase
from app.domain.runs import EvalConfig
from app.evaluation.engine import RunPlan, run_evaluation
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.reporting import render_csv, render_markdown
from app.providers.fake import FakeProvider


def test_csv_has_one_row_per_result_and_neutralizes_formulas(
    make_case: Callable[..., EvaluationCase],
    make_dataset: Callable[..., Dataset],
    make_config: Callable[..., EvalConfig],
) -> None:
    dataset = make_dataset(make_case("c1", "=1+1"), make_case("c2", "plain"))
    config = make_config(metrics=["exact_match"])
    plan = RunPlan(
        config=config,
        dataset=dataset,
        dataset_source="dataset.json",
        metrics=[ExactMatch()],
        adapters={"m1": FakeProvider.from_config(config.models[0], dataset=dataset)},
    )
    report = asyncio.run(run_evaluation(plan))

    rows = list(csv.DictReader(io.StringIO(render_csv(report))))
    assert [row["case_key"] for row in rows] == ["c1", "c2"]
    assert rows[0]["actual_output"] == "'=1+1"
    assert rows[0]["expected_output"] == "'=1+1"
    assert rows[1]["actual_output"] == "plain"
    assert rows[1]["exact_match_score"] == "1.0"
    assert rows[1]["exact_match_status"] == "scored"
    assert "m1" in render_markdown(report)
