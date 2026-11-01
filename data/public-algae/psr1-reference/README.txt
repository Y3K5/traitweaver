PUBLIC ALGAE REFERENCE — PSR1-ASSOCIATED LOCUS

WHAT GOES IN
Five primary public source records, copied byte-for-byte from existing public
source snapshots and checked against their recorded hashes. No new download or
API request was made. SOURCE_MANIFEST.json lists exact bytes, hashes, public
origin links, human-readable links, roles, locators and freshness limits.

WHAT HAPPENS
src/traitweaver/public_algae.py derives reference.v2.json directly from these
files, checks exact versioned identity qualifiers and joins the annotated
forward-strand exons. It checks genomic-to-transcript sequence equality, standard
code translation to the RefSeq protein, and sequence equality to unreviewed
UniProt Q9S807. Startup rechecks source pins and reproduces the catalog.

Run from the repository root:
PYTHONPATH=src python3 -B tools/verify_public_algae.py

WHAT COMES OUT
XP_001700553.1, 752 aa ↔ XM_001700501.2, 4772 nt ↔ GeneID:5726104.
Locus tag CHLRE_12g495100v5, gene-level cross-reference Cre12.g495100.
Assembly GCF_000002595.2 (v5.5), NC_057015.1, CC-503 cw92 mt+ strain.
Three annotated exons; ONE admitted transcript. No alternative isoforms are
invented. Unknown is different from an observed absence of other isoforms.

COORDINATE TRACE
GenBank's extracted region is 724592..729993, 1-based inclusive. Its exon/CDS
locations are relative to that region. Add 724591 to normalized 0-based offsets.
Exons on chromosome NC_057015.1, 0-based half-open:
[724591,725902), [726139,726807), [727200,729993).
Annotated joined CDS: 2259 nt INCLUDING terminal TAG stop. Peptide-coding spans
exclude those final 3 nt and total 2256 nt, encoding 752 aa. The original CDS
joins and stop intervals are retained separately in reference.v2.json/checks.
CDS offset modulo 3 is not a GFF phase. A codon can cross an exon junction;
adjacent protein projections may overlap by one amino acid for that reason.

CLAIMS AND LIMITS
reference.v2.json/claims links each claim to exact source files and sections.
The paper's Cre12.g495100.t1.1 identifier shares a gene-level identifier with
the RefSeq cross-reference. Its title/DOI/section locator and reviewed public
full-text snapshot hash are in SOURCE_MANIFEST.json/publication_identity.
Only the identity association was admitted: no full methods, construct sequence
or authored private planning example was copied. The full-text source snapshot
is not bundled; the public source link allows independent review.

RefSeq is PROVISIONAL and calls the product uncharacterized protein; its
conceptual translation is not experimental protein identification. UniProt is
unreviewed. Database file agreement does not establish function, observed splice
usage, present-day database status or equivalence to the publication's UVM4
lines/construct. Frozen source dates are not retrieval times.

evidence-needed/REQUIREMENTS.json records the missing experimental evidence and
required trace fields. It contains no measurements and no laboratory protocol.
Keep future observations in an explicitly chosen external data directory. They
are not automatically imported or promoted into this catalog.

LOCAL RECORDS
The app's CRISPR workflow, Protein ↔ gene and Splicing maps default to this real
reference case. The synthetic isoform example remains a separate explicit mode.
Public checkpoints use a v2 contract and public-algae-review-v2 journal; earlier
v1 synthetic records and original algae/Muse records are preserved unchanged.
Review JSON includes catalog, claim/source trace, immutable checkpoints and
saved assessments. Raw provider responses and machine paths are excluded.

This folder is a local review candidate, not new publication approval.
