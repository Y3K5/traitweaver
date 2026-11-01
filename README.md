**Cinematic Meta showcase (October 31):** the default entry now opens five scenes,
Question → Evidence → Muse decision → Tool result → Next study, in full width.
Inspect the science opens existing evidence, reference and measurement panels.
Optional `--rna-pilot-dir` and `--completion-pilot-dir` load explicitly selected
saved pilot results read-only; nothing is copied into the repository or sent.
Missing results remain missing. See [showcase usage](docs/CINEMATIC_SHOWCASE.txt).

# Traitweaver — local research workspace

**Focused MVP entry:** open **Research journey**, then choose **Presentation view**.
The illustration now has source-linked evidence, reference and measurement cards,
plus a provenance-aware Muse decision → check → reassessment panel. **Show supporting
records** and **How Muse helped** jump directly to them. Four primary menu entries
lead to the journey, working study, loaded cycle and handoff; all other tools stay
under **Evidence, mapping & tools**. See [the focused MVP and finish line](docs/MVP_FOCUS.txt).
No new model calls or generated-video dependency are introduced.

**Animated research journey:** choose **Research journey** or append `#journey`
to the printed local URL. Play, pause or inspect eight stages from trait and
public reference mapping to a recipient proposal and measurement requirements.
Playback is explicitly illustrative, with no model or tool execution. Export a
source-labelled SVG. CRISPR sequences and laboratory methods remain pending
qualified inputs. See [the journey guide](docs/RESEARCH_JOURNEY.txt).

**Completed checks:** a separate synthetic RNA example now saves pre-result
decisions and actual source-bound local metadata receipts; changed inputs require
reassessment. Export/reopen retains history without reruns. A new unsigned 2x2
Muse comparison tests whether a valid receipt helps the model move on. Older
approvals do not cover it. See [tracking and comparison](docs/COMPLETED_STEPS.txt).

**The research idea comes first:** choose Algae & phosphorus, Understand GFP,
Plan an RNA study or Make it repeatable. Follow six plain-language steps; open
“Why this step?” for the reasoning and “Show evidence” for sources. Exact records
stay expandable. The new view shows a loaded saved real Muse algae cycle without
attributing it to the other cases. Their first real model reviews remain pending.
“Review public inputs for Muse” prepares an exact request and sends nothing.
See [the research experience](docs/RESEARCH_EXPERIENCE.txt).

**Small Muse comparison proposal:** a separate four-request RNA pilot crosses
changed synthetic sample metadata with original/reversed action order. It removes
phase/readiness hints, keeps factual checks separate from authored priorities,
and requires a fresh exact payload/budget approval. Preparation never sends.
See [the reviewed pilot criteria and monitoring boundary](docs/MUSE_RNA_PILOT.txt).

**Evaluate plan quality:** a separate offline harness now tests 12 explicitly
synthetic scenarios across six areas, paired before/after an evidence change and
shown in three action orders. Authored reference, order-copying and false-certainty
controls test the scorer; human usefulness scores stay unfilled. No new live call.
Run `python3 -B tools/evaluate_assistant.py offline --output /private/tmp/traitweaver-evaluation-review`
with a fresh output folder, then open its `START_HERE.html`. See
[the evaluation contract and limits](docs/ASSISTANT_EVALUATION.txt).

**Four-case Muse preparation:** a separate terminal runner now prepares exact
public/synthetic payloads, pins source/code and pricing, validates provider usage
and monitors one explicitly approved batch. It remains unsigned and sends
nothing during preparation or browser use. Read [the runner/approval guide](docs/FOUR_CASE_MUSE.txt).

**Study workbench:** the existing science now has a three-column question /
checkpoint / audit view in our midnight, blue and orange palette. Choose **Study
workbench** in the menu or open the printed local URL with `#workbench`. Review
source records, save annotation revisions, use the existing four-case audits and
three-action contract, then privacy-check JSON/Markdown and reopen read-only.
All included annotation revisions are screened; a clean screen still requires
owner review. Notes do not change the pinned scientific case or model inputs.
See [the workbench guide](docs/WORKBENCH.txt). Export before server shutdown.

**Scientific story:** a connected visual showcase now follows source evidence →
genome/protein identity → proposed material lineage → fluorescence → phosphorus
accounting → reactor comparison → measurement design. It pairs published mean/SE/n
and reference quantities with expandable scientist detail. Synthetic arithmetic
is opt-in and visibly labelled. Export a scientist brief, JSON or a standalone
stage SVG. See [the scientific walkthrough and limits](docs/SCIENTIFIC_STORY.txt).
Click **Scientific story** in the existing sidebar; no provider call is enabled.

**Research assistant is now in the app:** choose public algae, qualified GFP,
synthetic RNA-seq planning or synthetic reproducibility. Follow Evidence → Local
checks → Next actions → Export & reopen. Each case has one bounded local audit
and three source-linked action cards with inputs, deliverables, readiness and
completion checks. Model priorities are labelled synthetic; no live call.
Start the demo below and click **Research assistant** in the sidebar.
See [the browser walkthrough](docs/ASSISTANT_WORKSPACE.txt),
[the independent contract/CLI](docs/ASSISTANT_CONTRACT.txt) and
[the refreshed three-minute demo](docs/DEMO_SCRIPT_3_MIN.txt).
The algae trait-development map connects the existing reference, combination/
recipient and CRISPR views. Cassette composition and cross-species effects remain
unqualified. Export before shutdown: assistant sessions are held in memory.

**Unpublished local extension:** offline Muse intelligence for trait candidates,
combination coverage and species/context-transfer review, plus real public algae protein-to-gene/transcript
mapping, reference exon maps and bounded CRISPR planning. The published 69-file baseline remains at the
published commit cd3b1a9. These changes have not been committed or pushed.

Open the app with the commands below, then use **CRISPR workflow**,
**Protein ↔ gene** and **Splicing maps** in the sidebar.
The default molecular example now uses five pinned public records for the
PSR1-associated CC-503 reference locus. The synthetic isoform model is a
separate explicit mode. See [the public reference folder](data/public-algae/psr1-reference/README.txt)
and [the walkthrough](docs/PUBLIC_ALGAE_WORKSPACE.txt).

**Muse intelligence** in the sidebar adds a separate source-bound decision/check/
reassessment workflow. It can prepare exact public requests and accept labelled
synthetic replies; it has no live transport or credential access. Read
[the intelligence contract and walkthrough](docs/INTELLIGENCE_LAYER.txt).

**Data flow** adds a clickable Acquire → Map & qualify → Use → Export view.
It shows admitted source files, independent saved records and available packages.
See [the data-flow walkthrough](docs/DATA_FLOW.txt). It performs no live retrieval.

Question → source-bound paths → evidence gaps → pre-result decision → one local
check → separate reassessment → saved study package.

This is a **local review candidate**, not an approved publication or submission.
It contains one curated public algae study, required interface assets, qualified
GFP reference data, code/tests and a clearly synthetic portable replay. It contains no credentials, private study example or real provider-run packet.
Root Git metadata is excluded from manifest checks without being inspected.

## Open the portable demo

Python 3.10+ and its standard library are sufficient. No installation or key.

```sh
python3 -B run_workspace.py --demo
```

Open the printed `127.0.0.1` URL. Walk through **Decision, Result, Reassessment,
Usage**, then Handoff. The banner says **Synthetic offline replay**. Simulated
responses and usage are software fixtures, not a live model or biological result.
All edits/reruns are blocked in this review mode. Ctrl-C stops the server.

On Handoff, **Export cycle with usage** saves the study plus its usage summary.
Use the separate completed-cycle file picker to reopen that JSON read-only.
The four revisions, synthetic label and usage survive; nothing is rerun.
For a saved cycle export, the launcher also accepts:

```sh
python3 -B run_workspace.py --completed-cycle-file /path/to/traitweaver-completed-cycle.json
```

## Use the editable workspace

```sh
python3 -B run_workspace.py --data-dir ../traitweaver-saved-study
```

The data directory must be outside this repository and its parent must exist.
Question, Paths, Evidence, Next check, Results and Handoff share one study revision.
Changed goals/constraints preserve earlier results and require reassessment.
Export/reopen and restart preserve history without new model or tool dispatch.
GFP opens as a separate local reference; it is not attached to algae evidence.

The browser never sends live requests. It can prepare a request locally and use
visibly synthetic replies. Explicitly gated command-line Muse transport is
included for review; both entry points require an interactive terminal before
credential access or attempt creation. This is an additional guard, not spending
authorization. **Do not run live transport or provide a key during this handoff**.
Preparing, reviewing and publishing are separate decisions.

## Review an owner's saved live cycle

```sh
python3 -B run_workspace.py --completed-cycle-dir /path/to/explicit-owner-selected-packet
```

That packet is deliberately not included. The viewer checks the saved package,
approval/request hashes, accepted receipt links and usage totals. Local receipts
establish consistency, not independent provider authentication. No calls occur.
The already completed real contribution is described in docs/LIVE_RUN_SUMMARY.txt.

## Verify locally

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_*.py' -q
PYTHONPATH=src python3 -B tests/check_workspace_http.py
PYTHONPATH=src python3 -B tests/check_completed_cycle_http.py
node tests/completed_cycle_ui_offline.cjs  # optional installed Node; no install
node tests/molecular_ui_offline.cjs
node tests/public_algae_ui_offline.cjs
node tests/intelligence_ui_offline.cjs
node tests/data_flow_ui_offline.cjs
node tests/assistant_ui_offline.cjs
node tests/research_story_ui_offline.cjs
node tests/workbench_ui_offline.cjs
node tests/journey_ui_offline.cjs
# Optional: 24 additional offline software journeys, fresh external output only
python3 -B tools/exercise_workbench.py --output ../traitweaver-workflow-review
PYTHONPATH=src python3 -B tools/verify_public_algae.py
python3 -B tools/verify_handoff.py
```

The 395 Python tests (390 preceding checks plus five showcase-adapter tests)
pass offline with sockets prohibited. Controller checks pass separately: 14 completed-cycle,
22 synthetic molecular, 25 public-reference, 26 intelligence and 26 Data flow
scenarios, plus 28 assistant, 25 scientific-story and 43 workbench and 42 journey scenarios (251 total). New controllers execute actual Python handlers/core over memory I/O,
with sockets blocked. Data flow layout/navigation were checked at 1440px and
390px widths; download contents and stale/unsaved rejection were tested offline.
Actual intelligence JSON browser download/file-picker reopen and refresh now
pass for r18. Long automation stalls leave manual demo timing unqualified; other
package families were not rerun natively. The two HTTP scripts now pass separately
with 28 workspace and 21 completed-cycle loopback-only checks; initial sandbox
bind denial was retained before a permitted local rerun. No provider or install is needed.
Workbench desktop/narrow layout, annotation editing, actual local audit and
synthetic priorities, privacy blocking, native JSON download and read-only picker
reopen also pass. Native transfer automation took about 59/150 seconds; prepare
exports before a timed demo. See docs/VALIDATION.txt for results and limits.

## Start the human review

- docs/WHAT_WE_BUILT.txt — exactly what was implemented and what was not.
- docs/DEMO_SCRIPT_3_MIN.txt — timed narration, including real/synthetic distinctions.
- docs/CLAUDE_REVIEW_BRIEF.txt — read-only review request; no Claude call was made.
- docs/SCOPE_AND_PROVENANCE.txt — source selection and explicit transformations.
- docs/RELEASE_BLOCKERS.txt — owner decisions still required before distribution.
- PUBLIC_FILES.txt and HANDOFF_MANIFEST.json — exact candidate inventory/checksums.

No biological winner, significance test, cross-study ranking, recovery yield or
laboratory protocol is produced. Missing recovery evidence is a useful finding.
No blanket software license has been chosen. Retain THIRD_PARTY_NOTICES.md,
font OFL notices and the component-specific GFP attribution.
