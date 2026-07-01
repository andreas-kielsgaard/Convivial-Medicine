# Phase One Orientation

Phase One builds a reproducible biomedical corpus constructor. It is not a
search UI, a document reading product, or a general literature assistant.

The acceptance target for Phase One is a reproducible 50-paper
`vitamin_D_ms_seed_v1` corpus build with stable raw and derived artifacts.

Artifact payloads use canonical `sha256:<64 lowercase hex>` hashes. Manifest
hashes are computed from deterministic JSON bytes with sorted keys and no
insignificant whitespace. The current implementation is a project-level
deterministic JSON subset, not a full RFC 8785/JCS implementation.

Adapters must write raw source response bytes to content-addressed storage
before parsing. Parsed snapshots and derived artifacts can then refer back to
the stored payload hash and parent manifest hashes.

PubMed ESearch defines membership for the seed corpus. PubMed ESummary retrieves
PubMed-side metadata for known PMIDs. PubMed EFetch retrieves known-PMID PubMed
record snapshots. All three adapters preserve raw response bytes before parsing.

PMC ID Converter is the next PMC-side gate for those known PubMed records. It
records whether PMC returns identifier mappings or availability fields for a
PMID batch, preserves the raw JSON response before parsing, and treats
not-returned PMIDs as normal missing/not-in-PMC results. A returned PMCID does
not imply legal reuse permission or fetch full text.

PMC BioC retrieves approved BioC JSON source payloads for a single known PMID or
PMCID where available. It preserves raw response bytes before parsing and only
records minimal document/passages detection in this branch. BioC availability
does not imply unrestricted legal reuse, and PMC HTML scraping remains outside
the boundary.

`corpus query pubmed` remains database-free by default. Passing `--persist-db`
explicitly attempts a Postgres connection and stores the query manifest, raw
source snapshot metadata, and source snapshot manifest rows for fixture or live
ESearch runs.

`corpus fetch pubmed-summary` is also database-free by default. Passing
`--persist-db` stores source snapshot metadata and the source snapshot manifest
for fixture or live ESummary runs, but does not create normalized works yet.

`corpus fetch pubmed-records` follows the same pattern for EFetch XML record
snapshots. It persists source snapshot metadata and manifests only when
`--persist-db` is passed.

`corpus enrich pmc-idconv` follows that same explicit persistence boundary. It
stores source snapshot metadata and manifests only when `--persist-db` is
passed, and it does not create normalized works or full-text assets.

`corpus fetch pmc-bioc` follows the same boundary for BioC source snapshots. It
persists source snapshot metadata and manifests only when `--persist-db` is
passed, and it does not create works, embeddings, or full-text assets.

`corpus enrich openalex` performs one singleton work lookup for a known DOI,
PMID, or OpenAlex work ID. It preserves raw response bytes before parsing a
minimal enrichment model, persists source snapshot metadata and manifests only
when `--persist-db` is passed, and does not define corpus membership.

The completed fixture build workflow is documented in
[`phase1-fixture-workflow.md`](phase1-fixture-workflow.md). It runs
`corpus build seed`, `corpus validate build`, and `corpus export slice` for the
deterministic `vitamin_D_ms_seed_v1` fixture corpus.

## Source Order

1. PubMed defines corpus membership and PubMed-side record snapshots.
2. PMC ID Converter determines PMC identifier and availability eligibility for
   known PMIDs.
3. PMC BioC retrieves approved BioC source payloads for known IDs where
   available through the API.
4. OpenAlex singleton lookups enrich already identified works.

## Deferred Work

- Broader PMC full-text ingestion and legal reuse interpretation.
- Source adapters outside the current PubMed, PMC, and OpenAlex singleton
  persistence boundary.
- OpenAlex search, bulk enrichment, and work normalization.
- Task orchestration behavior beyond the initial build run tables.
- Source retry, rate-limit, and provenance policies.
- External artifact persistence beyond deterministic local primitives.
- Frontend or product UI routes.
- Notebook workflows.
- Graph or vector databases.

Schema v1 now provides the initial Postgres tables for manifests, source
snapshots, works, identifiers, full-text assets, OpenAlex enrichment, build
runs, slice membership, and review conflicts.
