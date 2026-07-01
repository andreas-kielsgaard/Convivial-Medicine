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
the same as full-text retrieval or legal reuse permission. PMC BioC/full-text
retrieval remains deferred, and PMC HTML must not be scraped.

OpenAlex is singleton enrichment only. Later branches may look up one known work
at a time to enrich already selected corpus records. OpenAlex must not define
membership for the Phase One seed corpus.

Later OpenAlex adapter work must store raw singleton lookup bytes before parsing
enrichment fields.

Crossref, Unpaywall, PubTator, and Semantic Scholar are outside Phase One branch
work unless a later prompt explicitly changes that boundary.
