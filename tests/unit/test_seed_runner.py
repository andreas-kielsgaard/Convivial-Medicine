from __future__ import annotations

from pathlib import Path

from convivial_medicine.config import Settings
from convivial_medicine.domain.manifests import load_query_manifest
from convivial_medicine.orchestration.seed import SeedFixturePaths, run_seed_build
from convivial_medicine.storage.artifacts import LocalArtifactStore

SEED_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
FIXTURE_ROOT = Path("tests/fixtures")


def test_fixture_seed_runner_executes_existing_source_steps(tmp_path: Path) -> None:
    manifest = load_query_manifest(SEED_MANIFEST_PATH)

    summary = run_seed_build(
        query_manifest=manifest,
        artifact_store=LocalArtifactStore(tmp_path),
        settings=Settings(),
        live=False,
        fixture_paths=SeedFixturePaths.from_root(FIXTURE_ROOT),
    )

    assert summary.manifest_name == "vitamin_D_ms_seed_v1"
    assert summary.mode == "fixture"
    assert summary.results.pubmed_esearch.parsed.pmids == (
        "11111111",
        "22222222",
        "33333333",
    )
    assert summary.results.pubmed_esummary.parsed.summaries_returned == 3
    assert summary.results.pubmed_efetch.parsed.records_returned == 3
    assert summary.results.pmc_idconv.parsed.records_returned == 2
    assert tuple(result.parsed.requested_id for result in summary.results.pmc_bioc) == (
        "PMC1111111",
    )
    assert summary.results.openalex_work.parsed.requested_id_type == "pmid"
    assert summary.results.openalex_work.parsed.requested_id == "11111111"
    assert summary.source_snapshot_count == 6
    assert len(summary.raw_artifact_hashes) == 6
    assert summary.db_persisted is False
    assert any((tmp_path / "sha256").glob("*/*"))
