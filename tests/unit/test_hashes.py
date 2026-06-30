from __future__ import annotations

from pathlib import Path

from convivial_medicine.domain.hashes import sha256_hex
from convivial_medicine.domain.identifiers import normalize_doi
from convivial_medicine.domain.manifests import load_manifest


def test_sha256_hex_is_deterministic() -> None:
    assert sha256_hex(b"convivial") == (
        "1a27e7bf2aca65b749bfa313e4a9b774377a96b548f2539bebe3a2be99b883c2"
    )


def test_normalize_doi_strips_url_prefix_and_lowercases() -> None:
    assert normalize_doi(" https://doi.org/10.1000/ABC.Def ") == "10.1000/abc.def"


def test_normalize_doi_returns_none_for_blank_values() -> None:
    assert normalize_doi("   ") is None
    assert normalize_doi(None) is None


def test_load_seed_manifest() -> None:
    manifest = load_manifest(Path("manifests/vitamin_D_ms_seed_v1.json"))

    assert manifest.manifest_version == "1"
    assert manifest.name == "vitamin_D_ms_seed_v1"
    assert manifest.db == "pubmed"
    assert manifest.retmax == 50
