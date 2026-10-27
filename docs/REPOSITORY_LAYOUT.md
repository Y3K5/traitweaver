# Repository layout

This repository holds reviewed entry code and public-approved documentation.

```text
docs/                    Mission, scientific requirements, attribution
tasks/                   Bounded coding task specifications
src/traitweaver/          Future Python application source
tests/fixtures/          Labeled synthetic software fixtures
examples/                Individually reviewed public examples
```

No application or UI is implemented by these folder markers. Scientific records
are not automatically public because their underlying papers are published.
Private support, credentials, source curation, transcripts and real study runs
belong outside this repository. Raw outputs and generated artifacts require
their own privacy review before publication.

Use main for reviewed milestones. After an owner-requested initial commit,
develop one product slice on a local feature branch. No automatic staging,
committing, pushing, pull requests, workflows or deployments. The owner performs
every push. Inspect the exact outgoing files and history before publication.
