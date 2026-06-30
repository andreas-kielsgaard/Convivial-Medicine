# Source Boundaries

Phase One has intentionally narrow source boundaries.

PubMed defines corpus membership. Query execution and result set membership
belong to PubMed branches, not to this bootstrap branch.

PMC is the full-text gate. Full text must come through PMC-approved services
such as PMC ID Converter and PMC BioC when available. Do not scrape PMC HTML.

OpenAlex is singleton enrichment only. Later branches may look up one known work
at a time to enrich already selected corpus records. OpenAlex must not define
membership for the Phase One seed corpus.

Crossref, Unpaywall, PubTator, and Semantic Scholar are outside Phase One branch
work unless a later prompt explicitly changes that boundary.
