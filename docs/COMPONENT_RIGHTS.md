# Component rights inventory — owner decisions pending

Current publication status reconciled November 2, 2026 against public main
`febe18b0b16e53a49aee71d3f8f4142b4a828618`. The original November 1 rights review
used `0987c1b`; its scoped MIT/license documentation was subsequently published
in `5e14721`. This update does not independently re-audit upstream terms or grant
new clearance. Existing notices, qualifications and unanswered rights questions
remain in force. The current documentation-only edits are uncommitted.

## Original application code, tests and documentation

Yuvraj Patel confirmed he is the sole human contributor on November 1 UTC
(October 31 Eastern). Project records describe Codex-assisted application
implementation; Meta runtime contributions are separately described in
[META_CONTRIBUTION.md](META_CONTRIBUTION.md). Sole-human status does not itself
establish employer, university or client rights, or copyrightability of AI output.
The earlier `0987c1b` base had no root LICENSE. The recorded November 1 owner decision expressly
approved MIT for original application code, with fonts, datasets and branding
kept under their own terms. Published commit `5e14721` added [LICENSE](../LICENSE), copyright
(c) 2026 Yuvraj Patel, using the [official MIT text](https://opensource.org/license/mit).
It permits commercial reuse and requires retention of the copyright and
permission notice. This records a license choice, not independent ownership
clearance or a guarantee against intellectual-property or patent claims.

**Scope:** original application code and associated original documentation only,
to the extent the owner can grant rights. The grant excludes `data/`,
`src/traitweaver/web/assets/`, archive-derived `src/traitweaver/web/base.css`,
fonts, datasets/source records, branding/logos/trademarks and any other separately
identified third-party material. Their own applicable terms and notices remain;
no new license for unresolved branding/design material is supplied by this MIT
grant. Preserve THIRD_PARTY_NOTICES.md and the source qualifications below.

## Bundled fonts

- **Manrope:** `src/traitweaver/web/assets/fonts/Manrope-Variable.ttf` and
  `Manrope-OFL.txt`; inspected notice identifies copyright 2018 Manrope Project
  Authors, [upstream project](https://github.com/googlefonts/manrope).
- **Newsreader:** `src/traitweaver/web/assets/fonts/Newsreader-Variable.ttf` and
  `Newsreader-OFL.txt`; inspected notice identifies copyright 2020 Newsreader
  Project Authors, [upstream project](https://github.com/productiontype/Newsreader).

Both retain bundled SIL OFL 1.1 notices. Preserve the copyright and license with
redistributed fonts; the fonts remain under OFL, cannot be sold by themselves,
and applicable reserved-name restrictions matter if modified. Font use does not
force application code under OFL. See the
[official OFL text](https://openfontlicense.org/open-font-license-official-text/).
Exact equivalence to upstream font binaries was not independently checked.

## Brand artwork and design stylesheets

`src/traitweaver/web/ASSET_PROVENANCE.json` records selected `base.css`,
`assets/brand.css`, logo/favicon SVGs and fonts from the owner's design archive,
SHA256 `c1723841b8b03292c09d0c8e5db69b42bbd7c18d24e786a183ccb2480d549d4e`.
The SVG describes custom hand-drawn lettering and a woven W, not a font.
Descriptions and hashes establish provenance claims, not rights by themselves.

Earlier baseline design-distribution confirmation is recorded in project history;
this review does not erase it. **Pending:** confirm that its scope covers the
exact current CSS, logo/favicon and newer adaptations, and disclose any external
templates, icons or snippets beyond named components. No clearance of untracked
video, music or other submission assets is established here.

## November 2 release additions and final media

`docs/CONTRIBUTION_LEDGER.txt` attributes the study-review presentation and trait/
landfill-water teaching visuals to Codex-assisted work at the owner's request.
They are included in `febe18b0`, including `src/traitweaver/web/study-review-ui.js`, its stylesheet
and `docs/INTEGRATION.svg`. That attribution is not independent rights clearance.
Confirm the scope of design permissions and any external reference adaptations;
background/scientific citations do not establish ownership of every visual asset.
Existing font/data notices and outstanding branding/mixed-GFP questions remain
in force.
No final video or accessible video link has been supplied and checked in this
reconciliation. Video, narration, music and other media need their own review;
no new media license or publication authorization is inferred.

## Public algae evidence

`data/algae-public.v1.json` contains manually curated facts and paraphrases from:

- Slocombe et al. (2023), DOI `10.3389/fpls.2023.1208168`,
  [publisher article](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2023.1208168/full).
- Zuniga-Burgos et al. (2024), DOI `10.1016/j.algal.2024.103589`,
  [institutional published-version record](https://eprints.whiterose.ac.uk/id/eprint/213933/)
  and [published PDF](https://discovery.ucl.ac.uk/id/eprint/10198202/1/1-s2.0-S2211926424002017-main.pdf).

The source publications state [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Retain authors/title/source/DOI/license and indicate paraphrase or adaptation;
do not imply endorsement. No full papers, figures, raw replicate data or
protocols are claimed as redistributed. Source metadata was inspected, but
this was not a line-by-line attribution audit of every downstream view.

## Qualified GFP / Biohub record — mixed scope unresolved

`data/gfp/QUALIFICATION.json` and `atlas-record.json` retain snapshot identity
UPI0000002FB4 / UniProt P42212 and source-level qualification. There is no
individual-record license field. The
[Biohub-managed registry](https://registry.opendata.aws/biohub-esm-atlas/)
distinguishes Atlas-generated data (CC BY 4.0), Sequences/All Data collections
(CC BY-SA 4.0), and upstream UniRef/UniParc (CC BY 4.0).

Do not label the combined sequence/activation record unqualified CC BY.
Preserve source/record identity, access date and the existing license
classification. **Pending:** confirm exact component scope, or conservatively
preserve applicable [BY-SA conditions](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en)
for adapted covered data. This component is not fully rights-cleared.
Merely bundling or reading ShareAlike data does not automatically license
independent application code as ShareAlike; adaptation and database-rights scope
can be case-specific. See the [Creative Commons collection guidance](https://creativecommons.org/faq/#if-i-create-a-collection-that-includes-a-work-offered-under-a-cc-license-which-licenses-may-i-choose-for-the-collection).

## Public PSR1 reference bundle

`data/public-algae/psr1-reference/SOURCE_MANIFEST.json` records source URLs and
hashes for RefSeq XP_001700553.1, XM_001700501.2, the NC_057015.1 region,
GCF_000002595.2 assembly report, and UniProt Q9S807 FASTA.

UniProt states CC BY 4.0: [canonical license page](https://www.uniprot.org/help/license)
(JavaScript fallback during this review) and
[consortium-partner confirmation](https://www.expasy.org/resources/uniprotkb).
The [NCBI policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)
places no restriction on molecular-database use but warns that submitter
copyrights, patents or other rights may exist; NCBI cannot grant blanket
unrestricted rights. Retain accessions, versions, sources and notices.
Do not label everything public domain or infer a JGI license solely from an
assembly submitter's name. Original cached retrieval and submitter rights were
not independently established by this review.

## Synthetic fixtures and local dependencies

Project-authored synthetic choices, receipts, timing and RNA/evaluation fixtures
remain labeled synthetic. Public algae material embedded in synthetic cycles
retains its third-party attribution and terms: synthetic labeling does not erase
underlying source rights. Real provider packets and credentials are not granted
publication permission by this inventory.

Tracked-path review and focused HTML/JS/CSS inspection found local assets,
no CDN scripts, package-lock/node_modules/vendor trees, or identified GPL
component. This is not proof that every snippet is original and not a full
line-by-line dependency/license or history audit. **Pending:** owner confirmation
that no copied templates, icons or snippets are omitted from notices.
Hosted sites and video assets outside this tracked repository are out of scope.

## Remaining owner decisions

1. **Completed:** owner selected MIT for original code. Retain component
   exceptions and required notices; this selection is not component clearance.
2. Confirm employer/university/client rights and disclose any other rights holder.
3. Confirm the earlier design grant covers the exact current assets/adaptations,
   and identify any unlisted third-party templates, icons or snippets.
4. Resolve the mixed GFP component's precise distribution/adaptation scope.
5. Separately clear final video/narration/music/assets and submission terms. No
   final video has been supplied and checked here; no final accessible URL is cleared.

These pending decisions do not negate the confirmed sole-human roster. They
also must not be converted into an all-rights warranty or eligibility certificate.
