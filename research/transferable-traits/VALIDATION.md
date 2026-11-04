# Offline validation · November 4, 2026

The reproducible trial uses synthetic fixtures and fake provider transport only.
It measures software behavior, not biological validity or Muse usefulness.

## Completed checks

`python3 -B -m unittest discover -s tests -v`: **41 tests passed**. Coverage includes
exact deduplication, immutable revisions, recipient/assay separation, null versus
zero, citation integrity, source snapshot hashes, unsafe URLs, provenance, dependency
citations, stale reviews, combination constraints, scope escalation, fabricated
source IDs, model-authored approval, ambiguous JSON, HTML escaping, durable leases,
restart/resume, access-denial stops, retry limits, concurrent budget reservations,
uncertain/partial usage, cost rounding and workbook archive/XML handling.

The integration test blocks socket creation and environment-value lookup while
running the six-case pilot. It processes 2 jobs, resumes with 4, then processes 0
on a third run. This checks that already completed work is not duplicated.
Six synthetic records and six review-pending jobs remain; all scientific review
statuses are `unreviewed`. Every prepared wire file matches its recorded SHA-256.

`node tests/ui_offline.cjs runs/offline-pilot/START_HERE.html`: **12 offline UI
assertions passed** using a minimal DOM. Actual generated script checks cover
initial counts, scope/search filters, empty results, reset, ordering, recipient
search and dashed proposed-group display. This is not a native-browser layout,
accessibility audit or visual-regression test.

An independent command-line trial also ran 2 → 4 → 0 jobs and produced
`START_HERE.html`, normalized JSON, a local SQLite database, six unsigned request
packets and six exact wire bodies. New provider calls: 0. Model spend: $0.

A separate synthetic storage/queue capacity check admitted 500 fictional records
and completed 500 local queue items in 0.889 seconds on this executor; the resulting
SQLite file was 2,568,192 bytes. This is only a small local storage/queue check,
not source retrieval, model latency, production throughput or 500 researched traits.
Its summary is included in `examples/SYNTHETIC_SCALE_500.json`.

## Blocked or untested

- Actual workbook materialization/readability and six real-row pilot: blocked.
  Supported Library transfer returned `library file transfer failed: download
  failed`; the signed file host was absent from the enforced policy. No host
  change, alternate download or reconstructed workbook was attempted.
- Real source retrieval and access permissions: not exercised. The runtime's
  permitted destinations do not include the planned scientific APIs.
- Actual Meta account balance, recipient/team, expiry and credit-only enforcement:
  unavailable through the tools supplied to this task. Credential contents were
  not read. Configured API access is not verified account/spending permission.
- Source entailment, extraction precision/recall, scientific usefulness and reviewer
  agreement: not established by synthetic tests.
- Native atlas adapter, deployment, provider transport and multi-user operations:
  implementation plan only.

The five workbook categories and 50/22 record/grouping counts are parent-reported,
not verified by this executor. The six capability categories in the current app
were inspected in source. No new Muse-discovered category count is reported.

## Continue safely

Obtain the workbook through an approved local transfer, inspect it, map columns
explicitly and admit primary-source evidence. Prepare new real-source packets,
verify account protection and exact costs, then obtain the required exact-payload
live authorization. Run the six-case trial and evaluate it before scaling. Retain
negative and inconclusive results in the eventual published study.
