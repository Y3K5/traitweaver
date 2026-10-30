# Traitweaver — bounded research-workspace MVP

Question → source-bound paths → evidence gaps → pre-result decision → one local
check → separate reassessment → saved study package.

This is a **local review candidate**, not an approved publication or submission.
It contains one curated public algae study, required interface assets, qualified
GFP reference data, code/tests and a clearly synthetic portable replay. It has
no Git metadata, credentials, private study example or real provider-run packet.

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
python3 -B tools/verify_handoff.py
```

The 110 unit tests and 14 optional JavaScript controller scenarios were rerun
offline. Six unit tests exercise actual HTTP handlers using memory buffers,
without sockets or API requests. The two HTTP scripts are separate optional
loopback checks; they were not rerun during this no-API refresh. No provider, install, upload or Git mutation is needed.
See docs/VALIDATION.txt for the results and limits of this exact candidate.

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
