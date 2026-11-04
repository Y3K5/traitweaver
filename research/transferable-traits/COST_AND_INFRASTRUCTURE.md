# Compute, time and spending plan

**500 candidate cases is reasonable for a small hosted-model workflow.** The
main work is obtaining evidence and reviewing it, not training a model or buying
GPUs. Five hundred validated unique traits may require substantially more than
500 candidate cases, and some trails should end in an explicit evidence gap.

## Transparent model estimate

Checked November 4, 2026: Muse Spark 1.3 Standard is listed at $1.25 per million
input tokens and $4.25 per million output tokens. Optional built-in web search is
$2.50 per 1,000 queries. Cached-input savings are not assumed. These figures are
public list prices, not a verified quote for this account.
[Meta pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits).

Planning assumption per candidate case: **two model calls**, each with 20,000
input and 8,000 billed output tokens (including any billed reasoning), plus two
optional paid web queries. `python3 -B -m traitstudy.estimate` reproduces the table.

| Candidate cases | Model calls | Input / output tokens | Model | Optional search | Subtotal | With 30% correction/retry allowance |
|---:|---:|---:|---:|---:|---:|---:|
| 6 | 12 | 0.24M / 0.096M | $0.708 | $0.03 | $0.738 | $0.9594 |
| 50 | 100 | 2M / 0.8M | $5.90 | $0.25 | $6.15 | $8.00 rounded |
| 500 | 1,000 | 20M / 8M | $59.00 | $2.50 | $61.50 | $79.95 |
| 750 | 1,500 | 30M / 12M | $88.50 | $3.75 | $92.25 | $119.93 rounded |
| 1,000 | 2,000 | 40M / 16M | $118.00 | $5.00 | $123.00 | $159.90 |

The allowance is planning arithmetic, **not permission to retry**. The first live
pilot stops on a failed or uncertain request and has no automatic retries. A
later correction batch needs its own remaining-budget check and approval scope.
Source API requests are not Muse web-search calls; do not charge both unless both
are actually used. A curated-source pilot can disable paid search entirely.

At an assumed 70% candidate-to-admitted-case yield, reaching 500 admitted cases
requires about 715 candidates, before counting multiple observations per trait.
That yield is hypothetical and must be measured. Using 750 candidates as a
planning buffer gives about $120 in model/search cost with the allowance above;
any unverified credit amount is therefore not a promise of completing 500 reviewed
traits. Taxes, hosting, storage, paid access and review labor are excluded.

The immediate six-call critique pilot is smaller than the two-pass table: one
call per real case, sequential, 8,192 output-token limit, no tools. At 20,000 input
tokens each, its model estimate is $0.358896. Proposed application ceiling: $1,
only after all billing and exact-payload gates are satisfied. The generated six
**synthetic** packets have a byte-based reservation estimate of $0.248206 total;
it is not a verified tokenizer maximum or a live authorization.

## Minimum infrastructure

| Component | Initial provision | Why |
|---|---|---|
| Worker | 2 vCPU, 4 GB RAM, Python 3.10+ | Parsing, queue and API orchestration; no local model |
| Accelerator | None | Muse inference is hosted by Meta |
| Database | SQLite WAL on persistent local volume, one worker | Sufficient for a 500-case pilot, transactional reservations/checkpoints |
| Source store | 20 GB working disk; 2–5 GB initial evidence allowance | Metadata, rights-permitted passages/PDFs, checksums, backups and logs |
| Model concurrency | 1 for pilot; start with 2 for later batches | Bound in-flight spend and simplify failure reconciliation |
| Source retrieval | Shared per-host limiter and bounded response sizes | Cache DOI/PMID records; prevent duplicate downloads and 429 storms |
| UI | Static HTML review first; existing app adapter later | No separate GPU/server required for inspection |
| Deployment | One private worker/container, scheduler optional | Start on demand; do not keep a costly fleet idle |

These are engineering planning choices, not measured minimums or a cloud-provider
quote. No machine or paid service was provisioned. If multiple independent writers
or reviewers are needed, move the store to PostgreSQL and objects to approved
object storage; retain immutable hashes and transaction semantics. Kubernetes,
vector databases, local GPU inference and Baseten are unnecessary for this pilot.
Meta credits must not be assumed to pay Baseten or hosting charges.

For scale planning, budget about 1,000–3,000 unique source records and 3,000–8,000
discovery/metadata/full-text requests, with 10–25% access or transient failures.
These are assumptions to replace with pilot measurements. Cache canonical IDs,
store metadata for blocked full text, honor licenses and preserve a blocked state.
Do not script NCBI web pages. Use official APIs; NCBI documents a 3 requests/second
default without an API key, so the design starts at 2/s across all workers.
[NCBI bulk-access guidance](https://support.nlm.nih.gov/kbArticle/?pn=KA-05510).
Europe PMC supports programmatic literature access and an open-access subset;
use permitted text only. [Europe PMC developer resources](https://europepmc.org/developers).
UniProt is for qualified reference identity, not evidence of recipient function.
[UniProt API source](https://github.com/ebi-uniprot/uniprot-rest-api).

## Time and non-model costs

For 1,000 calls at an assumed 15–60 seconds/call, concurrency 2 gives about
2.1–8.3 hours of model wall time before retrieval, throttling and review. Budget
1–3 working days for machine processing and exception triage. These are not
measured Muse latency figures; the six-call pilot must measure them.

At 10–20 minutes of primary review per admitted case, 500 cases take **83–167
reviewer hours**. A second reviewer checking 20% at 5–10 minutes adds 8–17 hours:
roughly 92–184 hours combined, or 2.3–4.6 person-weeks at 40 hours/week. Difficult
papers or identity mapping can take longer. Qualified review is the largest
likely bottleneck. Cost labor as `review hours × actual reviewer rate`.

Hosting cost is `worker hours × selected provider hourly rate`, plus persistent
disk/object storage and egress. For a purely illustrative $0.02–$0.08/hour CPU
worker and 24–72 active hours, compute would be about $0.48–$5.76; running it
continuously for 30 days would be $14.40–$57.60. These are **scenario inputs,
not researched provider prices**, and the managed workspace billing is unknown.
Ask the actual platform for a quote before deployment. Keep storage/retrieval
charges separate from the model credit ledger.

## Actual account status and hard stops

Observed in the selected environment: the restricted HTTP policy permits the
Meta API, and the runtime reports a configured Meta credential binding as ready.
No credential contents were inspected. No account/billing inspection connector
or authenticated billing UI is available to this task. Therefore **actual team,
balance, expiry, payment method, auto-top-up, overage behavior and provider-enforced
credit-only stop are unverified**. No user-reported credit amount is treated as a
measured available balance or published here. Model calls made by this study: **0**.

Before live work, obtain a supported account-view confirmation of those exact
fields. Do not infer billing protection from an alert, API-key presence or local
budget counter. If the provider cannot enforce credit-only stopping, do not launch
under a credit-only instruction. Confirm exact recipient, model mode, source
payloads, retention settings, current token accounting and spend ceiling.

Reserve the maximum approved cost before each request under one transaction.
Hold uncertain reservations, count failed attempts, stop on missing/partial usage,
and reconcile actual provider usage before continuing. The local ledger prevents
this worker from intentionally overscheduling; it cannot cap other keys, account
charges, changed prices or provider billing. No live transport exists in this
version, and no account approval is manufactured in the generated files.
