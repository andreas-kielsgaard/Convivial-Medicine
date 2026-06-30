from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class QueryManifest(BaseModel):
    manifest_version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    db: str = Field(min_length=1)
    term: str = Field(min_length=1)
    usehistory: bool
    retmax: int = Field(gt=0)
    retmode: str = Field(default="json", min_length=1)
    notes: str | None = None


def load_manifest(path: Path) -> QueryManifest:
    return QueryManifest.model_validate_json(path.read_text(encoding="utf-8"))
