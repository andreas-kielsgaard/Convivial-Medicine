from __future__ import annotations

import pytest

from convivial_medicine.config import Settings
from convivial_medicine.storage.db import (
    check_database_connection,
    make_engine,
    make_session_factory,
)


def test_make_engine_uses_configured_database_url() -> None:
    settings = Settings(_env_file=None)

    engine = make_engine(settings, database_url="sqlite+pysqlite:///:memory:")

    assert engine.url.drivername == "sqlite+pysqlite"
    engine.dispose()


def test_make_session_factory_returns_sessionmaker() -> None:
    engine = make_engine(database_url="sqlite+pysqlite:///:memory:")
    session_factory = make_session_factory(engine=engine)

    assert session_factory.kw["expire_on_commit"] is False
    engine.dispose()


def test_check_database_connection_returns_typed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    settings = Settings(_env_file=None)

    result = check_database_connection(settings=settings)

    assert result.database_url_configured is True
    assert result.dialect == "sqlite"
