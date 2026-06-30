from __future__ import annotations

from convivial_medicine.config import Settings


def test_settings_defaults_are_local_safe_values() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.object_store_endpoint == "http://localhost:9000"
    assert settings.object_store_bucket == "convivial-medicine"
    assert settings.openalex_api_key is None


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/app")
    monkeypatch.setenv("OBJECT_STORE_ENDPOINT", "http://object-store:9000")
    monkeypatch.setenv("OBJECT_STORE_BUCKET", "test-bucket")
    monkeypatch.setenv("OBJECT_STORE_ACCESS_KEY", "access")
    monkeypatch.setenv("OBJECT_STORE_SECRET_KEY", "secret")
    monkeypatch.setenv("OBJECT_STORE_REGION", "eu-north-1")
    monkeypatch.setenv("NCBI_TOOL", "test-tool")
    monkeypatch.setenv("NCBI_EMAIL", "placeholder@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", "ncbi-placeholder")
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-placeholder")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/app"
    assert settings.object_store_endpoint == "http://object-store:9000"
    assert settings.object_store_bucket == "test-bucket"
    assert settings.object_store_access_key == "access"
    assert settings.object_store_secret_key == "secret"
    assert settings.object_store_region == "eu-north-1"
    assert settings.ncbi_tool == "test-tool"
    assert settings.ncbi_email == "placeholder@example.invalid"
    assert settings.ncbi_api_key == "ncbi-placeholder"
    assert settings.openalex_api_key == "openalex-placeholder"
