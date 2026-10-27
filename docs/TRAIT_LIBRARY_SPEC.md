# Trait and intervention library

Purpose: connect a known reported trait to its biological context, intervention class, gene/protein identities, source organisms, studied hosts and primary evidence. This is a research map, not an edit recipe or prevalence ranking.

Each record needs stable ID, trait label, gene/protein labels, intervention class, source species as reported, host(s) as studied, donor relationship, primary citation/location, brief reported observation, applicability limits, exact-identity gaps, and the next research question. Preserve null/unknown fields. A gene's source species is not its ultimate evolutionary origin.

Classes: endogenous_edit, heterologous_expression, expression_change, natural_function_reference. Natural-function records must not be returned as completed edits. Endogenous edits have no foreign donor. Expression changes are not automatically CRISPR edits. An ortholog, engineered variant or differently named gene requires its own source/version; do not combine them silently.

Initial research-support examples to qualify: GFP fluorescence; firefly luciferase reporter; soybean FAD2 oil-composition studies; tomato GAD GABA-composition studies; algal PSR1 phosphorus-uptake study; native PET enzyme-function reference. No source record from private support is automatically approved for model context or publication.

No sequences, guide RNAs, mutation coordinates, constructs, laboratory conditions or protocols in this catalogue. Do not invent precise gene/reference accessions, common-use frequencies, safety, transfer success or commercial/regulatory status. The first source-backed metadata curation is preliminary; exact accession/taxonomy reconciliation and full-text qualification remain explicit gaps.
