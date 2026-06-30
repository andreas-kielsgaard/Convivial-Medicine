from __future__ import annotations

from convivial_medicine.storage.constants import (
    BuildStatus,
    ConflictResolutionState,
    IdentifierNamespace,
    LegalFulltextStatus,
    WorkStatus,
)


def test_controlled_storage_values_are_stable_strings() -> None:
    assert BuildStatus.PENDING == "pending"
    assert BuildStatus.RUNNING == "running"
    assert WorkStatus.CANDIDATE == "candidate"
    assert WorkStatus.INCLUDED == "included"
    assert IdentifierNamespace.DOI == "doi"
    assert IdentifierNamespace.PMID == "pmid"
    assert LegalFulltextStatus.NOT_CHECKED == "not_checked"
    assert ConflictResolutionState.OPEN == "open"
