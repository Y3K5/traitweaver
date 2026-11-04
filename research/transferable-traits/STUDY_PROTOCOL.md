# Research question and admission rules

Which documented donor components produce which measured outcomes in which
recipient contexts, and what limitations or dependencies prevent extrapolation?
The unit of admission is a **donor–component–recipient–study–condition–endpoint
observation**. Multiple observations can describe one trait; unsuccessful or
inconclusive observations remain useful evidence. Trail completion may mean a
documented gap, not a successful transfer.

## Six target trails

| Workbook ID confirmed in parsed sheet text | Target topic | Main distinction to review |
|---|---|---|
| TW004 | GFP | Reference protein identity versus observed reporter expression |
| TW009 | Firefly light | Substrate availability and host dependencies |
| TW002 | Fungal glow | Multi-component pathway and recipient context |
| TW037 | PETase | Recipient-produced enzyme assay versus intact-organism function |
| TW020 | Golden Rice | Tissue pathway endpoint versus nutritional/health extrapolation |
| TW044 | Cellulose-to-ethanol yeast | Jointly measured capabilities versus an untested combination |

These identifiers are confirmed against the original Library workbook's parsed
sheet text. The selected candidate rows and public primary-source notes are in
`data/source-pilot-*.json`. They are not approved normalized observations. Binary
XLSX verification and full-paper coverage remain incomplete. The optional supplied
protocol document was not retrieved; this document is newly authored guidance.

## Evidence workflow

1. Materialize the authorized workbook, verify bytes and sheet readability,
   retain version/hash, and review an explicit header-to-field map. Preserve raw
   cells, sheet and row locators in quarantine. Import 50 existing rows and 22
   groupings only after the actual counts and contents are checked. Parsed counts
   are now verified; binary fidelity and normalized import remain pending.
2. Resolve each citation to its DOI/PMID/PMCID and actual primary study. Keep
   retractions, corrections and study variants separate. PubMed/Europe PMC index
   metadata is discovery evidence, not proof of a specific claim.
3. Admit only accessible metadata and permitted text. Record source URL, license,
   access date, version, snapshot hash and exact table/figure/paragraph/assay
   locator. Access denied means blocked; do not replace inaccessible full text
   with a guessed claim or use a different service to evade restrictions.
4. Cross-reference NCBI taxonomy/gene/protein and UniProt when needed for identity.
   Retain species, strain, accession/version and unresolved alternatives. A
   database annotation or similar sequence does not establish a transfer outcome.
5. Record observed endpoint, assay compartment, material, units, control,
   timepoint, n and uncertainty where reported. Distinguish a null result field
   from a measured zero and an unsearched negative-result field from no effect.
6. Record host dependencies as reported, unknown or hypotheses, each with its
   own citation. Preserve transfer-method and stability gaps. Do not generate
   implementation recipes, sequences, intervention sites or performance promises.
7. Review component stacks only in their exact common recipient, study and
   condition. Two independently successful transfers are not a demonstrated
   combination. Proposed pairings carry no measured joint endpoint.
8. Require human source checking before promoting a candidate into the atlas.
   Record the precise record hash, reviewer, decision and note as a new event.
   Corrections create a new observation revision, retaining earlier judgments.

## Trial before scale

The current offline trial has six synthetic fixtures and a fake provider. It
exercises source linkage, separation of assay scopes, null/zero, unreviewed states,
group constraints, interrupted queues and budgets. It does **not** establish
biological accuracy, real workbook readability or model usefulness.

A separate v2 packet now prepares one exact Muse critique per real target (six
calls, sequential, at most 8,192 output tokens each, no tools or retries). The
source coverage and correction gaps remain in every affected request. Code,
source and wire hashes are pinned in `examples/source-pilot-v2/PLAN.json`.
Reproduction is local; nothing sends. The older synthetic packet is retained only
as software history.

The owner permits existing credits only, up to $100, and explicitly prohibits
payment-method charges. Proposed application allocation: $1 for the six-call
critique; its byte-based planning estimate is $0.260019, not a verified billing
maximum. Actual recipient/team, available credits, expiry, provider-enforced
credit-only stopping and exact live approval are still required. A spend alert
and the local ledger cannot meet that condition. Do not call if protection is
unavailable. Any later extraction-plus-verification pilot is a separate stage.

Before calling Muse, a qualified reviewer creates a held-out checklist of source
locators, required caveats and intentionally unresolved fields. Do not put that
answer key in model input. Two people independently check the six resulting
cards when feasible. Record disagreements and time, not only a pass percentage.

Proposed progression criteria (authored criteria, not achieved results):

- Every output parses, remains source/context-bound and retains all required
  uncertainty. Zero fabricated source identifiers or unsupported scope upgrades.
- The reviewer confirms all material claim-to-source links, or leaves the case
  blocked. No automatic scientific promotion.
- At least five of six critiques identify a reviewer-confirmed useful gap or
  correction; explicitly report cases where Muse adds no value.
- Median reviewer time improves over the same manual task without reducing source
  accuracy. Six cases provide only a feasibility signal, not a reliable accuracy
  estimate; report counts and case details, never a universal success rate.
- Account usage is complete and reconciled; no uncertain spend, policy failure
  or unintended disclosure. Stop at any provider/access/evidence failure.

Next stage: 50 candidate cases in batches of 10; audit every material claim and
all proposed combinations. Then target 500 in batches of 25 only after the trial succeeds, with a
reviewed batch scope under the same $100 credit-only ceiling. Do not spend to
reach the ceiling or exceed it to reach a case count. If evidence or usefulness criteria fail, retain and
publish the failure report; improve the workflow before spending on more cases.

## Categorization and display

Keep the five workbook shelves as `workbook_human_v1`, the existing app's six
capability lenses as `app_capabilities_v1`, and model clusters as
`muse_proposed_v1`. Allow many-to-many membership and explicit unassigned records.
Compare candidate groupings by shared endpoint, component function and dependency;
do not imply that visual proximity means biological compatibility. Display a
solid demonstrated-context link only with joint evidence and review status;
display unvalidated suggestions as dashed links. Show source passages and gaps
before any ranking. Transferability is a scoped evidence description, not a score.
