"""The Alembic history must build the same schema as the ORM models, and be reversible."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import build_engine

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    bool(os.environ.get("TEST_DATABASE_URL")),
    reason="migration round trip runs on its own throwaway SQLite file",
)


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_matches_models_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    config = _config(url)

    command.upgrade(config, "head")
    engine = build_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert set(Base.metadata.tables) <= tables

        with engine.connect() as connection:
            drift = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert drift == [], f"models and migrations differ: {drift}"

        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
