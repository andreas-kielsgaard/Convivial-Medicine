# Phase One Orientation

Phase One builds a reproducible biomedical corpus constructor. It is not a
search UI, a document reading product, or a general literature assistant.

The acceptance target for Phase One is a reproducible 50-paper
`vitamin_D_ms_seed_v1` corpus build with stable raw and derived artifacts.

## Source Order

1. PubMed defines corpus membership.
2. PMC ID Converter and PMC BioC provide the lawful full-text path when content
   is available through approved services.
3. OpenAlex singleton lookups enrich already identified works.

## Deferred Work

- Live PubMed, PMC, and OpenAlex adapters.
- Source adapter implementations beyond the schema v1 persistence boundary.
- Task orchestration behavior beyond the initial build run tables.
- Source retry, rate-limit, and provenance policies.
- Artifact persistence beyond deterministic local primitives.
- Frontend or product UI routes.
- Notebook workflows.
- Graph or vector databases.

Schema v1 now provides the initial Postgres tables for manifests, source
snapshots, works, identifiers, full-text assets, OpenAlex enrichment, build
runs, slice membership, and review conflicts.
