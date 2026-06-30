from __future__ import annotations

from enum import StrEnum


class BuildStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkStatus(StrEnum):
    CANDIDATE = "candidate"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    MERGED = "merged"


class IdentifierNamespace(StrEnum):
    DOI = "doi"
    PMID = "pmid"
    PMCID = "pmcid"
    OPENALEX = "openalex"


class LegalFulltextStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    AVAILABLE = "available"
    RESTRICTED = "restricted"
    NOT_FOUND = "not_found"


class ConflictResolutionState(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
