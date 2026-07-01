from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from convivial_medicine.config import Settings, get_settings


@dataclass(frozen=True)
class DatabaseConnectionCheck:
    database_url_configured: bool
    dialect: str


class DatabaseConnectionError(RuntimeError):
    """Raised when a configured database URL cannot be reached."""


def make_engine(settings: Settings | None = None, *, database_url: str | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    resolved_database_url = database_url or resolved_settings.database_url
    connect_args: dict[str, object] = {}
    if make_url(resolved_database_url).get_backend_name() == "postgresql":
        connect_args["connect_timeout"] = 5
    return create_engine(
        resolved_database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def make_session_factory(
    engine: Engine | None = None, settings: Settings | None = None
) -> sessionmaker[Session]:
    resolved_engine = engine or make_engine(settings)
    return sessionmaker(bind=resolved_engine, class_=Session, expire_on_commit=False)


def check_database_connection(settings: Settings | None = None) -> DatabaseConnectionCheck:
    resolved_settings = settings or get_settings()
    if not resolved_settings.database_url:
        msg = "Database URL is not configured."
        raise DatabaseConnectionError(msg)

    engine = make_engine(resolved_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseConnectionCheck(
            database_url_configured=True,
            dialect=engine.dialect.name,
        )
    except SQLAlchemyError as exc:
        msg = f"Database connection failed for configured URL: {exc}"
        raise DatabaseConnectionError(msg) from exc
    finally:
        engine.dispose()
