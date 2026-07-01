# Phase One Orientation

Phase One builds a reproducible biomedical corpus constructor. It is not a
search UI, a document reading product, or a general literature assistant.

The acceptance target for Phase One is a reproducible 50-paper
`vitamin_D_ms_seed_v1` corpus build with stable raw and derived artifacts.

Artifact payloads use canonical `sha256:<64 lowercase hex>` hashes. Manifest
hashes are computed from deterministic JSON bytes with sorted keys and no
insignificant whitespace. The current implementation is a project-level
deterministic JSON subset, not a full RFC 8785/JCS implementation.

Later adapters must write raw source response bytes to content-addressed storage
before parsing. Parsed snapshots and derived artifacts can then refer back to
the stored payload hash and parent manifest hashes.

PubMed ESearch defines membership for the seed corpus. PubMed ESummary retrieves
PubMed-side metadata for known PMIDs. Both adapters preserve raw response bytes
before parsing. PubMed EFetch remains deferred.

`corpus query pubmed` remains database-free by default. Passing `--persist-db`
explicitly attempts a Postgres connection and stores the query manifest, raw
source snapshot metadata, and source snapshot manifest rows for fixture or live
ESearch runs.

`corpus fetch pubmed-summary` is also database-free by default. Passing
`--persist-db` stores source snapshot metadata and the source snapshot manifest
for fixture or live ESummary runs, but does not create normalized works yet.

## Source Order

1. PubMed defines corpus membership.
2. PMC ID Converter and PMC BioC provide the lawful full-text path when content
   is available through approved services.
3. OpenAlex singleton lookups enrich already identified works.

## Deferred Work

- PubMed EFetch adapter.
- Live PMC and OpenAlex adapters.
- Source adapter implementations beyond PubMed ESearch/ESummary and the schema v1
  persistence boundary.
- Task orchestration behavior beyond the initial build run tables.
- Source retry, rate-limit, and provenance policies.
- External artifact persistence beyond deterministic local primitives.
- Frontend or product UI routes.
- Notebook workflows.
- Graph or vector databases.

Schema v1 now provides the initial Postgres tables for manifests, source
snapshots, works, identifiers, full-text assets, OpenAlex enrichment, build
runs, slice membership, and review conflicts.
