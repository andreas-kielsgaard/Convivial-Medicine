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
- Full Postgres schema and task orchestration state.
- Source retry, rate-limit, and provenance policies.
- Artifact persistence beyond deterministic local primitives.
- Frontend or product UI routes.
- Notebook workflows.
- Graph or vector databases.
