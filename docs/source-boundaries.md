# Source Boundaries

Phase One has intentionally narrow source boundaries.

PubMed defines corpus membership. PubMed ESearch is the membership adapter.
PubMed ESummary and EFetch retrieve known-PMID PubMed-side snapshots. All three
store raw response bytes by content hash before parsing.

Failed PubMed HTTP responses are also provenance artifacts: live non-2xx
ESearch, ESummary, and EFetch responses are written to the artifact store and
represented by source snapshot manifests before the adapter raises.

PMC ID Converter is the PMC-side eligibility and identifier gate for known
PubMed records. It may report PMCID, DOI, MID, and availability metadata such
as `live` or `release-date`, and it may simply omit PMIDs that are not in PMC.
Those omissions are normal eligibility results, not transport failures.

Raw PMC ID Converter responses are stored before parsing. PMCID presence is not
the same as full-text retrieval or legal reuse permission.

PMC BioC is now the approved PMC retrieval path for known IDs when PMC exposes a
BioC payload through the API. Not all PMC articles are available through BioC,
and BioC availability still does not imply unrestricted legal reuse. Raw BioC
responses are stored before parsing. PMC HTML must not be scraped.

OpenAlex is singleton enrichment only. It may look up one known work at a time
by DOI, PMID, or OpenAlex work ID to enrich already selected corpus records.
OpenAlex must not define membership for the Phase One seed corpus.

OpenAlex raw singleton lookup bytes are stored before parsing enrichment fields.
OpenAlex does not search, bulk enrich, or normalize works in this phase.

Crossref, Unpaywall, PubTator, and Semantic Scholar are outside Phase One branch
work unless a later prompt explicitly changes that boundary.
