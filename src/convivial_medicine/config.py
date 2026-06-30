from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://convivial:convivial@localhost:5432/convivial_medicine",
        validation_alias="DATABASE_URL",
    )
    object_store_endpoint: str = Field(
        default="http://localhost:9000",
        validation_alias="OBJECT_STORE_ENDPOINT",
    )
    object_store_bucket: str = Field(
        default="convivial-medicine",
        validation_alias="OBJECT_STORE_BUCKET",
    )
    object_store_access_key: str | None = Field(
        default=None,
        validation_alias="OBJECT_STORE_ACCESS_KEY",
    )
    object_store_secret_key: str | None = Field(
        default=None,
        validation_alias="OBJECT_STORE_SECRET_KEY",
    )
    object_store_region: str = Field(
        default="us-east-1",
        validation_alias="OBJECT_STORE_REGION",
    )
    ncbi_tool: str | None = Field(default=None, validation_alias="NCBI_TOOL")
    ncbi_email: str | None = Field(default=None, validation_alias="NCBI_EMAIL")
    ncbi_api_key: str | None = Field(default=None, validation_alias="NCBI_API_KEY")
    openalex_api_key: str | None = Field(default=None, validation_alias="OPENALEX_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
