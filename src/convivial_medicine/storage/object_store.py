from __future__ import annotations

from dataclasses import dataclass

from convivial_medicine.config import Settings, get_settings


@dataclass(frozen=True)
class ObjectStoreConfig:
    endpoint: str
    bucket: str
    region: str
    access_key: str | None
    secret_key: str | None


def object_store_config(settings: Settings | None = None) -> ObjectStoreConfig:
    resolved_settings = settings or get_settings()
    return ObjectStoreConfig(
        endpoint=resolved_settings.object_store_endpoint,
        bucket=resolved_settings.object_store_bucket,
        region=resolved_settings.object_store_region,
        access_key=resolved_settings.object_store_access_key,
        secret_key=resolved_settings.object_store_secret_key,
    )
