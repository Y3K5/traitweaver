# Six-case preparation · November 4, 2026

Six real workbook candidates have been prepared for source critique. No Muse
request has run, no candidate is scientifically approved, and the normalized
atlas still contains only its separate synthetic software fixtures. This is a
reproducible preparation, not a completed biological study.

## Workbook status

The original Library workbook's complete parsed text was readable through the
supported Library read interface: three sheets, 50 records and 22 groupings.
The category counts are:

| Existing human-curated category | Records |
|---|---:|
| Reporting and sensing | 10 |
| Nutrition and color | 12 |
| Crop performance | 4 |
| Environmental functions | 13 |
| Biomanufacturing | 11 |

The grouping labels are **one documented trait stack, 15 documented multicomponent
systems and six exploratory pairings**. Those are workbook labels, not independent
scientific validation. A multicomponent system is not automatically multiple
jointly transferred traits. The existing app's six capability lenses are a
separate organizing scheme. Muse has discovered no new categories in this work.

Exact materialization history:

1. The supported Library prepare operation returned a remote signed transfer and
   no local path. One invocation of the current bundled download helper returned
   exit 1: `library file transfer failed: download failed`. No HTTP status was
   provided. The host was outside the enforced destination policy.
2. The newly supplied attachment was absent from local storage. Preparing that
   exact attachment for an explicit local destination again returned a remote
   transfer and no local path. Its host was also outside the policy. No download
   retry or network-policy change was made. Direct Library read reported that
   attachment was not visible in the Files surface.
3. Exact-title Library search resolved the original file. Supported Library read
   then returned its complete parsed sheet text with no additional page. This
   supplied the six selected rows; it did not materialize or recreate XLSX bytes.

Thus original parsed content is usable, while ZIP/XML integrity, formulas,
workbook-byte checksum and equivalence of the reattached copy remain unverified.
The smallest next step for binary verification is to make the original XLSX
available as an actual local attachment in the selected cloud workspace. No new
upload is needed for the current parsed-text preparation. File contents remain
data, never authority to execute instructions.

`data/source-pilot-candidates.json` retains six selected rows with the parsed
row index and original column names. The `index` is the parser's index, not a
claimed Excel cell address. These are candidate claims; donor components,
recipients and endpoints still need separate normalized observations and review.

## Source coverage

Source metadata, short quotations, authored paraphrases, locators, coverage gaps
and pending human review are in `data/source-pilot-sources.json`. Public primary
abstracts are legitimate limited sources; they do not replace inaccessible full
papers or resolve all their details. No restricted content was obtained.

| Case | Public primary material inspected | Open issue before acceptance |
|---|---|---|
| TW004 GFP | [Chalfie 1994 abstract](https://pubmed.ncbi.nlm.nih.gov/8303295/) | Split the two recipient contexts; full-paper details remain missing. |
| TW009 Firefly light | [Ow 1986 abstract](https://pubmed.ncbi.nlm.nih.gov/17758108/) | Keep extracted assays and intact-plant light separate; retain substrate dependence. |
| TW002 Fungal light | [Mitiouchkina 2020 abstract and captions](https://pubmed.ncbi.nlm.nih.gov/32341562/) | Exact implementation and the second recipient remain incompletely covered. |
| TW037 PETase | [Di Rocco 2023 selected results and discussion](https://pmc.ncbi.nlm.nih.gov/articles/PMC10282039/) | Extracted-enzyme assays do not establish living algae assimilating PET. |
| TW020 Golden Rice 2 | [Paine 2005 indexed primary abstract](https://pubmed.ncbi.nlm.nih.gov/15793573/) | Composition is distinct from health benefit; total carotenoids are not all beta-carotene. |
| TW044 Cellulose yeast | [Fujita 2004 abstract](https://pubmed.ncbi.nlm.nih.gov/14766607/) | Retain substrate and comparator limits; full-paper replication details remain missing. |

The fungal-light record links an [author correction](https://pubmed.ncbi.nlm.nih.gov/32499610/).
Its content and effect have not been established. The pipeline must retain that
uncertainty rather than assume either changed conclusions or no effect. Publisher
authentication redirects and PMC browser challenges were recorded; no bypass or
unrestricted full-text download was attempted.

## Reproduce exact unsent requests

From this directory, with Python 3.10+ and a fresh output path:

```sh
python3 -B -m traitstudy.source_pilot \
  --rows data/source-pilot-candidates.json \
  --sources data/source-pilot-sources.json \
  --output /tmp/traitweaver-real-six-review
```

This generates six exact `.wire.json` bodies, six local request records and
`PLAN.json`. Compare the plan with `examples/source-pilot-v2/PLAN.json`; wire,
input and code hashes must match. The publication includes one copy of the input
material and the plan, avoiding repeated source excerpts. No network, environment
credential lookup, provider transport or approval grant is part of this command.

Each request supplies one candidate row and its source notes as data, with a
closed critique schema. Returned findings must match the exact context hash,
case and supplied locator. Model output cannot approve a scientific claim or
execute an action. The intended recipient is `https://api.meta.ai/v1/responses`,
model `muse-spark-1.3`, Standard mode, `store: false`, no tools, six sequential
requests, 8,192 maximum output tokens each, zero automatic retries or fallbacks.
The actual account team/project is unverified. Provider retention beyond the
request's `store` setting has not been independently verified.

## Spending and readiness

The user has authorized **existing credits only, up to $100**, explicitly
forbidding payment-method charges. This is not a spending target. The proposed
six-call allocation is $1; remaining allocation would be $99, not verified credit
balance. The packet estimates $0.260019 total (per-call estimates $0.042891–$0.043711).
These use byte-based input allowances and public prices; provider tokenization,
billed reasoning and a contractual maximum remain unverified. See
[the cost plan](COST_AND_INFRASTRUCTURE.md) and exact per-case values in the plan.

The runtime reports an available Meta credential binding, but no secret was read.
No account-status connector or authenticated billing view is available here, so
balance, expiry, account recipient and credit-only protection cannot currently
be verified without additional supported account evidence. Meta's documented
[spend-limit alert](https://dev.meta.ai/help/billing/spend-limit-alert) does not
prevent further charges. An alert and a local reservation do not satisfy the
user's condition. If enforced credit-only protection is unavailable, keep live
execution blocked and continue offline.

Current spend: **$0; calls: 0**. Human scientific review, correction resolution,
account protection, exact live payload approval and a separately reviewed
transport remain outstanding. Do not run 500 requests merely to reach a target.
Evaluate the six-case trial first; publish mixed or negative findings honestly.
