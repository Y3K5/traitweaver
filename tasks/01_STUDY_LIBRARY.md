# Initial product-task proposal for Muse

This file is retained as planning history, not the current coding assignment. Subsequent bounded tasks require separate review and are not included in this initial scaffold.

Only begin in the eligible implementation window after the initial coding context and token allowance are approved. This file is a task specification, not authorization to spend or publish.

Implement the first headless product slice: a typed local trait/intervention library and study brief, with source inspection and filtering. Use only explicitly supplied public fixture records. No existing Traitweaver application source is available for reuse.

A user should be able to list examples, filter by trait/species/intervention class, inspect source and limits for one record, and attach that record as a source-bound precedent to a study question. An endogenous edit must show no foreign donor. A native-function reference is not an edit. Records without exact gene/reference identity remain incomplete rather than receiving invented IDs.

Use Python standard library and JSON/text output. Keep private inputs and run outputs in an explicit external data directory, never automatically in this public tree. Do not crawl the filesystem, retrieve omitted records, read credentials, or call a model/service. No UI or generic coding-agent framework.

Verify valid/unknown record IDs, class/species/donor consistency, ambiguous identities, duplicate IDs, absent sources, case-insensitive filters, incomplete records and unchanged source fixtures. Label synthetic inputs as software checks. Report what actually ran and do not claim scientific validation.

Return useful source changes with actual verification and remaining scientific gaps. No commit, push, deployment or API activation.
