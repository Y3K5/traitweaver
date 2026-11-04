# Traitweaver transferable-trait research study

This is an isolated, **offline software pilot** for a literature-backed atlas
that could grow toward 500 documented transfer cases. It contains six explicitly
synthetic test records, a durable queue, evidence storage, a local review display,
tests and an unsigned Muse request contract. **It contains zero newly researched
biological cases and zero new Muse results.**

The original workbook could not be materialized in this cloud environment through
the supported Library route. Its download failed; the returned file host was not
in the enforced destination policy. The previous declined host change was not
retried or bypassed. The actual workbook rows and primary studies have therefore
not been inspected here. Six targets supplied for subsequent review are TW004
(GFP), TW009 (firefly light), TW002 (fungal glow), TW037 (PETase), TW020 (Golden
Rice) and TW044 (cellulose-to-ethanol yeast). These labels are research trails,
not a reconstructed workbook or verified observation catalog.

## Reproduce the offline trial

Python 3.10+ and its standard library suffice. No installation, GPU, key or network
access is needed. Run commands from this directory. Output is local and private
until separately reviewed for publication.

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m traitstudy.cli pilot --output /tmp/traitweaver-study-review --limit 2
python3 -B -m traitstudy.cli pilot --output /tmp/traitweaver-study-review
python3 -B -m traitstudy.cli pilot --output /tmp/traitweaver-study-review
```

Open `/tmp/traitweaver-study-review/START_HERE.html`. The three runs process
2, 4 and 0 jobs respectively. Six records remain unreviewed; six software jobs
await review. No item becomes scientifically accepted. Generated files include
`atlas.json`, `research-trails.json`, `study.sqlite`, exact `WIRE-*.json` bodies,
their request hashes and `UNSIGNED_PILOT.json`. The SQLite file remains local;
the publication contains only explicitly selected code, docs and synthetic
fixtures. The ready-to-open [synthetic display](examples/offline-pilot/START_HERE.html)
is included as a review artifact; GitHub's file view may require downloading it.

```sh
python3 -B -m traitstudy.cli search --db /tmp/traitweaver-study-review/study.sqlite enzyme
python3 -B -m traitstudy.cli retrieval-plan 'GFP expression recipient'
python3 -B -m traitstudy.estimate
```

`retrieval-plan` only prepares URLs and reports missing network authorization.
It never calls PubMed, Europe PMC, NCBI, UniProt or a model. When a workbook has
been properly materialized, `inspect-workbook PATH --output FILE.json` preserves
cell coordinates and cached formula values without executing formulas or mapping
unseen columns to biological claims. An explicit column map still requires review.

## What is implemented

- Normalized SQLite sources, entity identities, observations, component links,
  citations with exact locators, dependencies, category assignments and group
  membership. Canonical SHA-256 identities retain revisions and provenance.
- Separate assay scopes, measured zero versus missing values, negative findings,
  transfer method, stability, host context and uncertainty. Unreported fields stay
  null. Reference annotations cannot by themselves establish a transfer result.
- Different contracts for demonstrated-in-context stacks and proposed pairings.
  Structural checks require joint study, recipient, condition and citation support;
  a person still must check what the paper entails.
- Durable leases, checkpoints, capped local retries, access-denial stops and
  expired-worker protection. Model-request uncertainty never auto-retries.
- Integer-microdollar reservations, call limits and fail-closed missing usage.
  This is application accounting, **not a provider-enforced account spending cap**.
- Append-only, hash-bound reviewer decisions. Synthetic fixtures cannot receive
  `source_checked`. No model output can approve itself or broaden the pilot record.
- Search, scope filtering, ordering, evidence details and a source-bound flow in
  a standalone read-only HTML display. No external assets or script dependencies.

## Current limits

This is not an autonomous literature crawler or a deployed service. Source APIs,
model transport, real workbook mapping, real extraction quality, inter-reviewer
agreement and biological usefulness have not been tested. The fake model returns
the supplied record and a synthetic gap notice; it proves plumbing, not Muse's
reasoning ability. The proposed live pilot critiques exact supplied observations;
it does not silently rewrite evidence. Expansion to extraction requires a new
reviewed schema and evaluation.

The source record can hold a short, lawfully admitted text snapshot (up to 20,000
characters) or metadata only. Full texts and PDFs belong in a separately approved
content-addressed store with rights metadata; no unrestricted scraping is included.
Deduplication is exact/context-aware, not a universal semantic match: synonyms,
DOI↔PMID crosswalks, accessions and related studies require review. Multiple
observations may belong to one trait; 500 calls, trails, observations and unique
traits are different counts. No universal transferability score is generated.

The existing app's six capability categories and the workbook's five reported
human-curated categories are separate schemes. New Muse groupings must retain a
`muse_proposed_v1` label and reviewer history. No new categories have emerged from
Muse in this trial.

Read [study protocol](STUDY_PROTOCOL.md), [compute and cost](COST_AND_INFRASTRUCTURE.md),
[integration plan](INTEGRATION.md), [validation](VALIDATION.md) and
[publication provenance](PUBLICATION.md). Nothing here supplies sequences,
experimental procedures or laboratory readiness. Qualified scientific and biosafety
review must precede laboratory use.
