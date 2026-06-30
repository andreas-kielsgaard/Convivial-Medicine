from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from convivial_medicine.config import get_settings
from convivial_medicine.storage.models import Base

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="set RUN_DB_TESTS=1 to run Postgres schema integration tests",
)


def test_alembic_upgrade_head_creates_schema_v1_tables() -> None:
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        assert set(Base.metadata.tables).issubset(set(inspector.get_table_names()))
    finally:
        engine.dispose()
