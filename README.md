# Convivial Medicine

Phase One is a reproducible biomedical corpus constructor. It is not a search
application, a notebook project, or a product UI.

The first acceptance target is a reproducible 50-paper
`vitamin_D_ms_seed_v1` corpus build. Later branches will use PubMed for corpus
membership, PMC-approved services for lawful full text, OpenAlex singleton
lookups for enrichment, content-addressed artifacts, and Postgres for normalized
build state.

This branch establishes the local deterministic substrate for Phase One
artifacts. Raw source bytes are addressed by `sha256:<hex>` payload hashes and
written under a content-addressed filesystem layout for tests and local
development. Manifest hashes are computed from a project-level deterministic
JSON subset: UTF-8 bytes, sorted object keys, and no insignificant whitespace.

Later source adapter branches must store raw source bytes before parsing them,
then record manifests and snapshots from those immutable bytes.

PubMed ESearch is the first adapter boundary: it defines corpus membership.
PubMed ESummary retrieves PubMed-side metadata for known PMIDs. PubMed EFetch
retrieves known-PMID PubMed record snapshots. Raw ESearch JSON, ESummary JSON,
and EFetch XML bytes are stored before parsing. Live non-2xx PubMed HTTP
responses are also stored as raw artifacts and represented by source snapshot
manifests before the adapter reports the HTTP failure.

PMC ID Converter is the PMC-side identifier and availability gate for known
PMIDs. It can report PMID-to-PMCID/DOI/MID mappings, missing/not-in-PMC PMIDs,
and availability fields such as `live` or `release-date` when PMC provides
them. Raw ID Converter JSON bytes are stored before parsing. A PMCID is not, by
itself, legal reuse permission, and this branch does not fetch PMC full text.

PMC BioC retrieves approved BioC JSON source payloads for known PMID or PMCID
values where PMC exposes them through the BioC API. Not all PMC articles are
available through that API. Raw BioC JSON bytes are stored before parsing, and
BioC availability is not treated as unrestricted legal reuse permission.

OpenAlex singleton work lookup enriches already-known records by DOI, PMID, or
OpenAlex work ID. It does not search, bulk enrich, or define corpus membership.
Raw OpenAlex JSON bytes are stored before parsing.

ESearch can optionally persist query manifest, source snapshot, and snapshot
manifest records to Postgres with `corpus query pubmed --persist-db`. Database
persistence is explicit and off by default; fixture and live ESearch runs still
write local content-addressed artifacts without requiring a database unless that
flag is passed.

ESummary can optionally persist source snapshot and snapshot manifest records
with `corpus fetch pubmed-summary --persist-db`; it does not create normalized
works yet.

EFetch can optionally persist source snapshot and snapshot manifest records with
`corpus fetch pubmed-records --persist-db`; it also does not create normalized
works yet.

PMC ID Converter can optionally persist source snapshot and snapshot manifest
records with `corpus enrich pmc-idconv --persist-db`; it does not create works
or full-text assets.

PMC BioC can optionally persist source snapshot and snapshot manifest records
with `corpus fetch pmc-bioc --persist-db`; it also does not create works or
full-text assets.

OpenAlex can optionally persist source snapshot and snapshot manifest records
with `corpus enrich openalex --persist-db`; it does not create normalized works
or corpus membership.

## Development

Install dependencies:

```powershell
uv sync
```

Run checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Inspect the CLI:

```powershell
uv run corpus --help
uv run corpus doctor
uv run corpus query pubmed --fixture tests/fixtures/pubmed/esearch_vitamin_d_ms_seed.json
uv run corpus fetch pubmed-summary --pmids 11111111,22222222,33333333 --fixture tests/fixtures/pubmed/esummary_vitamin_d_ms_seed.json
uv run corpus fetch pubmed-records --pmids 11111111,22222222,33333333 --fixture tests/fixtures/pubmed/efetch_vitamin_d_ms_seed.xml
uv run corpus enrich pmc-idconv --pmids 11111111,22222222,33333333 --fixture tests/fixtures/pmc/idconv_vitamin_d_ms_seed.json
uv run corpus fetch pmc-bioc --id PMC1111111 --fixture tests/fixtures/pmc/bioc_vitamin_d_ms_seed.json
uv run corpus enrich openalex --pmid 11111111 --fixture tests/fixtures/openalex/work_vitamin_d_ms_seed.json
```

Run the API locally:

```powershell
uv run uvicorn convivial_medicine.api.main:app --reload
```

The health endpoint is available at `GET /health`.

## Local Services

Start Postgres and MinIO:

```powershell
docker compose up -d
```

Default local database URL:

```text
postgresql+psycopg://convivial:convivial@localhost:5432/convivial_medicine
```

Apply database migrations:

```powershell
uv run alembic upgrade head
```

MinIO API is exposed on `http://localhost:9000`.

MinIO console is exposed on `http://localhost:9001`.

Stop services:

```powershell
docker compose down
```

Remove local service data as well:

```powershell
docker compose down -v
```

Copy `.env.example` to `.env` for local development and replace placeholder
values only when a later adapter branch needs live credentials.
