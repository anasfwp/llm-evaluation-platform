"""Importing this package registers every table on ``Base.metadata`` (used by Alembic)."""

from app.db.models.case_result import CaseResult, MetricResult
from app.db.models.dataset import Dataset, DatasetVersion, EvaluationCase
from app.db.models.evaluation_run import EvaluationRun
from app.db.models.model_config import ModelConfig
from app.db.models.project import Project

__all__ = [
    "CaseResult",
    "Dataset",
    "DatasetVersion",
    "EvaluationCase",
    "EvaluationRun",
    "MetricResult",
    "ModelConfig",
    "Project",
]
