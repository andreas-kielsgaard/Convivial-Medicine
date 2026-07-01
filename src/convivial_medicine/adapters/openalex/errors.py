from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpenAlexHTTPStatusError(RuntimeError):
    operation: str
    endpoint: str
    http_status: int
    content_type: str
    raw_payload_hash: str
    raw_artifact_uri: str
    source_snapshot_manifest_hash: str
    request_fingerprint: str
    request_metadata: dict[str, Any]
    original_http_message: str | None = None

    def __str__(self) -> str:
        message = (
            f"OpenAlex {self.operation} HTTP {self.http_status} from {self.endpoint}; "
            f"raw_payload_hash={self.raw_payload_hash}; "
            f"manifest_hash={self.source_snapshot_manifest_hash}"
        )
        if self.original_http_message:
            return f"{message}; http_message={self.original_http_message}"
        return message
