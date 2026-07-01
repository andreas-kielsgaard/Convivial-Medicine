from __future__ import annotations

from convivial_medicine.adapters.pubmed.client import PubMedClient
from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    PubMedESearchAdapterResult,
    build_esearch_params,
    process_esearch_response_bytes,
    run_esearch,
)
from convivial_medicine.adapters.pubmed.esummary import (
    PUBMED_ESUMMARY_ENDPOINT,
    PubMedESummaryAdapterResult,
    build_esummary_params,
    process_esummary_response_bytes,
    run_esummary,
)
from convivial_medicine.adapters.pubmed.models import PubMedESearchResult, PubMedESummaryResult

__all__ = [
    "PUBMED_ESEARCH_ENDPOINT",
    "PUBMED_ESUMMARY_ENDPOINT",
    "PubMedClient",
    "PubMedESearchAdapterResult",
    "PubMedESearchResult",
    "PubMedESummaryAdapterResult",
    "PubMedESummaryResult",
    "build_esearch_params",
    "build_esummary_params",
    "process_esearch_response_bytes",
    "process_esummary_response_bytes",
    "run_esearch",
    "run_esummary",
]
