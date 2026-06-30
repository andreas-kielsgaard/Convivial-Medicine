from __future__ import annotations

from fastapi.testclient import TestClient

from convivial_medicine.api.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "convivial-medicine", "status": "ok"}


def test_import_storage_modules() -> None:
    from convivial_medicine.storage.db import make_engine
    from convivial_medicine.storage.object_store import object_store_config

    assert callable(make_engine)
    assert callable(object_store_config)
