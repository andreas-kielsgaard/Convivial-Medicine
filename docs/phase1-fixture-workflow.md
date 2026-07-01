# Phase One Fixture Workflow

Phase One now has a deterministic fixture workflow for the
`vitamin_D_ms_seed_v1` seed corpus. The workflow replays committed fixtures,
preserves raw source bytes before parsing, writes a build report, validates the
artifact root, and exports a deterministic JSON slice.

The fixture workflow is local and database-free by default. Optional database
persistence and live network mode are explicit flags.

## Build -> Validate -> Export

Run the fixture path from a clean checkout:

```powershell
uv run corpus build seed
uv run corpus validate build
uv run corpus export slice --output .artifacts/exports/vitamin_D_ms_seed_v1.fixture-slice.json
```

The commands use these defaults unless overridden:

- Manifest: `manifests/vitamin_D_ms_seed_v1.json`
- Fixture root: `tests/fixtures`
- Artifact root: `.artifacts`
- Slice export output: `fixture-slice.json`, or the explicit `--output` path

## Expected Key Output

`uv run corpus build seed` should include:

```text
manifest_name: vitamin_D_ms_seed_v1
manifest_hash: sha256:f68c8218203459e1d549ab64f656b4272a71796161a13dc2515fd1f1d3450e8b
mode: fixture
step_order: pubmed_esearch,pubmed_esummary,pubmed_efetch,pmc_idconv,pmc_bioc,openalex_work
pubmed_esearch.count: 123
pubmed_esearch.pmids_returned: 3
pubmed_esummary.summaries_returned: 3
pubmed_efetch.records_returned: 3
pmc_idconv.records_returned: 2
pmc_idconv.pmcids_returned: 2
pmc_bioc.requests: 1
pmc_bioc.pmcids: PMC1111111
pmc_bioc.document_count: 1
pmc_bioc.passage_count: 3
openalex.requested_id_type: pmid
openalex.requested_id: 11111111
openalex.openalex_id: https://openalex.org/W1111111111
raw_artifacts: 6
source_snapshots: 6
db_persisted: False
build_report: .artifacts/build-reports/vitamin_D_ms_seed_v1.json
```

The build also prints raw payload hashes for each source response. Those hashes
are expected to be stable for the committed fixtures.

`uv run corpus validate build` should include:

```text
status: ok
manifest_name: vitamin_D_ms_seed_v1
mode: fixture
build_report_present: True
steps: 6/6
source_snapshots: 6/6
raw_artifacts: 6/6
db_persisted: False
missing_raw_artifacts: none
errors: none
```

If the build used `--persist-db`, validation can still pass, but the
`db_persisted` line will be `True` because that value comes from the build
report.

`uv run corpus export slice --output .artifacts/exports/vitamin_D_ms_seed_v1.fixture-slice.json`
should include:

```text
status: ok
manifest_name: vitamin_D_ms_seed_v1
mode: fixture
source_steps: 6
raw_artifacts: 6
source_snapshots: 6
output: .artifacts/exports/vitamin_D_ms_seed_v1.fixture-slice.json
```

## Output Locations

Raw artifacts are content-addressed under the artifact root:

```text
.artifacts/sha256/<first-two-hex>/<hex>
```

They are also referenced by logical artifact URIs:

```text
artifact://sha256/<first-two-hex>/<hex>
```

The fixture build report is written under the artifact root:

```text
.artifacts/build-reports/vitamin_D_ms_seed_v1.json
```

Slice exports are written exactly where `--output` points. The CLI default is
`fixture-slice.json` in the current working directory. For local workflow runs,
prefer an explicit path under `.artifacts/exports/`:

```powershell
uv run corpus export slice --output .artifacts/exports/vitamin_D_ms_seed_v1.fixture-slice.json
```

## Optional Database Persistence

Database persistence is explicit and off by default. It records source snapshot
metadata and snapshot manifests; it does not create normalized works yet.

Start local Postgres, apply migrations, and check the connection:

```powershell
docker compose up -d postgres
uv run alembic upgrade head
uv run corpus doctor --check-db
```

Then run the fixture build with persistence:

```powershell
uv run corpus build seed --persist-db
```

The default database URL is:

```text
postgresql+psycopg://convivial:convivial@localhost:5432/convivial_medicine
```

Override it with `DATABASE_URL` when needed. With `--persist-db`, the build
summary should end with `db_persisted: True`; without it, the expected fixture
summary is `db_persisted: False`.

Individual source adapter commands also accept `--persist-db`, but the fixture
workflow should normally use `corpus build seed --persist-db` so the persisted
rows match the same source order as the build report.

## Live Mode

Live mode makes network calls instead of replaying fixtures:

```powershell
uv run corpus build seed --live --artifact-root .artifacts-live
```

Required environment variables for a live seed build:

- `NCBI_EMAIL`: required for PubMed ESearch, PubMed ESummary, PubMed EFetch,
  and PMC ID Converter calls.
- `OPENALEX_API_KEY`: required for the OpenAlex singleton work lookup.

Optional live-mode variables:

- `NCBI_TOOL`: sent to NCBI and useful for identifying the local tool.
- `NCBI_API_KEY`: sent to NCBI when available.
- `DATABASE_URL`: required only when also passing `--persist-db`.

The current `corpus validate build` and `corpus export slice` commands validate
and export fixture builds. Keep live runs in a separate artifact root such as
`.artifacts-live` so they do not overwrite the deterministic fixture build
report.

## Current Boundaries

The Phase One fixture workflow captures source responses and writes source
snapshot manifests. It does not normalize works yet.

Current non-goals:

- Work normalization and conflict resolution.
- OpenAlex search or bulk enrichment.
- PMC HTML scraping or unrestricted full-text reuse interpretation.
- Embeddings, vector databases, graph databases, notebooks, or product UI.
