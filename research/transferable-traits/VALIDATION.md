# Offline validation · November 4, 2026

The reproducible software trial uses synthetic fixtures and fake provider
transport. A separate preparation now uses six real workbook candidate rows and
limited primary-source material. Neither is a completed live Muse experiment.

## Checks

`python3 -B -m unittest discover -s tests -v`: **49 tests passed**, including the
original 41 pipeline checks and eight source-pilot contract checks. Coverage
includes exact deduplication, immutable revisions, recipient/assay separation,
null versus zero, citation integrity, source hashes, unsafe URLs, dependencies,
stale review, combination constraints, scope escalation, invented source IDs,
model-authored approval, ambiguous JSON, HTML escaping, leases, resume, access
stops, retry limits, atomic budget reservations, uncertain usage, rounding and
XLSX archive/XML handling.

The eight additional checks cover exactly six distinct cases, source-coverage
matching, exact context/wire hashes, pending human review, model execution and
approval rejection, invented locators, preserved unresolved findings, bounded
payload/quotation size and offline preparation with credit-only funding recorded
separately from permission. Socket creation and environment-value lookup are
blocked in the integration tests. These are software tests, not scientific review.

`node tests/ui_offline.cjs examples/offline-pilot/START_HERE.html`: **12 offline UI
assertions passed** with a minimal DOM. They cover counts, scope/search filters,
empty results, reset, ordering, recipient search and proposed-group styling. This
is not a native-browser layout or accessibility audit.

The synthetic trial processed 2 jobs, resumed with 4 and then processed 0. Six
records and jobs remain review-pending, with all scientific states unreviewed.
The published historical fixture and its request bodies are unchanged. A separate
500-record synthetic storage/queue check took 0.889 seconds and 2,568,192 SQLite
bytes on this executor; it did not retrieve or research 500 biological traits.

The real-source v2 preparation produces six hash-bound request bodies locally.
The published plan is reproduced from the selected input rows and source notes;
all hashes match. No record is imported as an approved scientific observation.
New provider calls: **0**. Model spend: **$0**.

## Access and scientific limits

The original Library parsed sheets are now readable. Counts are verified:
50 records, five existing human-curated categories, 22 groupings (one stack,
15 multicomponent systems, six exploratory pairings). Binary XLSX materialization
remains unavailable; the newly attached copy's equivalence is unverified. Exact
supported attempts and outcomes are in [pilot preparation](REAL_PILOT_PREPARATION.md).

Public web research inspected five primary abstracts and selected PETase result
passages. This is manual source preparation, not a tested automated scientific-API
client. Fungal-light correction content is unresolved. Full-paper coverage,
normalized observation import, extraction accuracy, scientific usefulness and
independent reviewer agreement remain incomplete.

The runtime's configured Meta credential binding is not verified spending
permission. Actual account, credit balance, expiry and provider-enforced credit-only
stopping remain unknown. The user explicitly prohibits payment-method charges.
There is no live transport in this package and no permission to bypass that rule.
Native atlas integration, deployment and multi-user operations remain a documented
implementation plan. No Muse-discovered category count is claimed.
