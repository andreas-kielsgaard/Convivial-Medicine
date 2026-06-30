# Source Boundaries

Phase One has intentionally narrow source boundaries.

PubMed defines corpus membership. PubMed ESearch is the membership adapter and
stores raw response bytes by content hash before parsing. PubMed ESummary and
EFetch remain deferred.

PMC is the full-text gate. Full text must come through PMC-approved services
such as PMC ID Converter and PMC BioC when available. Do not scrape PMC HTML.

Later PMC adapter work must store approved raw source bytes before extracting or
normalizing full-text artifacts.

OpenAlex is singleton enrichment only. Later branches may look up one known work
at a time to enrich already selected corpus records. OpenAlex must not define
membership for the Phase One seed corpus.

Later OpenAlex adapter work must store raw singleton lookup bytes before parsing
enrichment fields.

Crossref, Unpaywall, PubTator, and Semantic Scholar are outside Phase One branch
work unless a later prompt explicitly changes that boundary.
