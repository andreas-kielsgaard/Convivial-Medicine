from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from convivial_medicine.config import Settings, get_settings


def make_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    return create_engine(resolved_settings.database_url, pool_pre_ping=True)
