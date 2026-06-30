from __future__ import annotations

import httpx

from convivial_medicine.adapters.pubmed.esearch import (
    DEFAULT_TIMEOUT_SECONDS,
    PUBMED_ESEARCH_ENDPOINT,
    PubMedESearchAdapterResult,
    run_esearch,
)
from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import QueryManifest
from convivial_medicine.storage.artifacts import LocalArtifactStore


class PubMedClient:
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.Client | None = None,
        endpoint: str = PUBMED_ESEARCH_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.settings = settings
        self.http_client = http_client
        self.endpoint = endpoint
        self.timeout = timeout

    def esearch(
        self,
        *,
        manifest: QueryManifest,
        artifact_store: LocalArtifactStore,
    ) -> PubMedESearchAdapterResult:
        return run_esearch(
            manifest=manifest,
            artifact_store=artifact_store,
            settings=self.settings,
            client=self.http_client,
            endpoint=self.endpoint,
            timeout=self.timeout,
        )
