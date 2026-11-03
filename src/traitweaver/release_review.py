"""Local study review: imported records and human judgments never become evidence.

Independent v1 contract. No model transport, sequence design or tool dispatch.
"""
from copy import deepcopy
from datetime import datetime, timezone
from itertools import combinations
import math
import re

from traitweaver import study, public_algae, research_story, workbench
from traitweaver.completed_cycle import validate_review

SCHEMA = 'traitweaver.study_review.v1'
MAX_BYTES = 2 * 1024 * 1024
LIMIT = ('Research review only. Imported assessments and reviewer identities are self-reported, '
         'not independently authenticated. Checksums establish consistency, not scientific truth. '
         'No sequence design, laboratory execution, organism containment guarantee or publication approval.')
REVIEW_LIMIT = 'Human decision for the exact saved content; not biological validation or execution approval.'


def pinned():
    story = research_story.content()
    ref = public_algae.catalog()
    return {'observations': story['public_observations'], 'sources': story['sources'],
            'reference_chain': story['reference_chain'], 'reference_limit': story['reference_limit'],
            'reference_mapping': ref['transcript_maps'][public_algae.TRANSCRIPT],
            'reference_organism': ref['organism'], 'reference_strain': ref['strain'],
            'annotation_version': None, 'record_status': ref['record_status'],
            'study_design': story['study_design'], 'source_identity': story['source_identity']}


def initial():
    return {'question': 'What evidence would establish collected phosphorus from a contained algae study?',
            'recipient': 'Chlamydomonas reinhardtii; receiving strain not yet qualified',
            'constraints': 'Contained research only. Material identity, containment and disposal require human review.',
            'traits': [
                {'id': 'T1', 'label': 'Phosphorus uptake', 'role': 'published_association', 'citations': ['S_PSR1_2023']},
                {'id': 'T2', 'label': 'Growth during phosphorus accumulation', 'role': 'published_observation', 'citations': ['S_PSR1_2023']},
                {'id': 'T3', 'label': 'Recoverable phosphorus in collected material', 'role': 'hypothesis_evidence_missing', 'citations': []}],
            'candidates': [], 'reviews': []}


def text(value, maximum=2000, nullable=False):
    if nullable and value is None:
        return
    study.text(value, maximum)


def candidate(value):
    study.fields(value, ('id', 'sequence_type', 'sequence', 'source', 'reference', 'tool',
                         'reported_stage', 'assessments', 'reported_value', 'reported_unit', 'limitations'))
    text(value['id'], 80)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value['id']):
        raise ValueError('Record ID must contain letters, numbers, underscores or hyphens')
    alphabets = {'guide_rna': 'ACGUN', 'primer_dna': 'ACGTRYSWKMBDHVN',
                 'genomic_dna': 'ACGTRYSWKMBDHVN', 'protein_aa': 'ACDEFGHIKLMNPQRSTVWYBXZJUO*'}
    kind = value['sequence_type']
    if not isinstance(kind, str) or kind not in alphabets:
        raise ValueError('Choose a distinct guide RNA, primer DNA, genomic DNA or protein type')
    if value['sequence'] is not None:
        text(value['sequence'], 10000)
        if set(value['sequence']) - set(alphabets[kind]):
            raise ValueError('Sequence alphabet does not match its declared type; nothing was converted')
    study.fields(value['source'], ('citation', 'locator', 'record_kind'))
    text(value['source']['citation']); text(value['source']['locator'])
    if value['source']['record_kind'] not in ('imported_report', 'synthetic_fixture'):
        raise ValueError('Imported reports and synthetic fixtures must remain distinct')
    study.fields(value['reference'], ('organism', 'strain', 'assembly', 'annotation_version', 'accession', 'coordinate_convention', 'interval'))
    for k, v in value['reference'].items():
        if k != 'interval': text(v, 300, nullable=True)
    interval = value['reference']['interval']
    if interval is not None:
        convention = value['reference']['coordinate_convention']
        if (not isinstance(interval, list) or len(interval) != 2 or
                not all(type(v) is int for v in interval) or
                convention not in ('0-based half-open', '1-based inclusive') or
                interval[0] < (0 if convention == '0-based half-open' else 1) or
                (interval[1] <= interval[0] if convention == '0-based half-open' else interval[1] < interval[0])):
            raise ValueError('Coordinates need a valid explicit convention; no guessed conversion')
        if not value['reference']['assembly'] or not value['reference']['accession']:
            raise ValueError('Coordinates require assembly and accession context')
    study.fields(value['tool'], ('name', 'version', 'settings'))
    for v in value['tool'].values(): text(v, nullable=True)
    if value['reported_stage'] not in ('imported_candidate', 'computationally_assessed', 'human_reviewed', 'experimentally_evaluated'):
        raise ValueError('Unsupported reported record stage')
    study.fields(value['assessments'], ('identity', 'host_compatibility', 'specificity', 'empirical_evidence'))
    for v in value['assessments'].values(): text(v, nullable=True)
    if value['reported_stage'] == 'computationally_assessed' and (not value['tool']['name'] or not any(value['assessments'].values())):
        raise ValueError('Reported computation requires tool provenance and an assessment')
    if value['reported_stage'] == 'experimentally_evaluated' and not value['assessments']['empirical_evidence']:
        raise ValueError('Reported experimental evaluation requires an evidence locator')
    number = value['reported_value']
    if number is not None and (type(number) not in (int, float) or not math.isfinite(number)):
        raise ValueError('Reported measurement must be finite or null')
    text(value['reported_unit'], 100, nullable=True)
    if number is not None and value['reported_unit'] is None:
        raise ValueError('A reported number requires its unit or an explicit dimensionless label')
    text(value['limitations'])
    return deepcopy(value)


def template():
    return {'id': 'EXAMPLE_METADATA_ONLY', 'sequence_type': 'primer_dna', 'sequence': None,
            'source': {'citation': 'Authored software fixture; no biological candidate',
                       'locator': 'Traitweaver import interface example', 'record_kind': 'synthetic_fixture'},
            'reference': dict.fromkeys(('organism', 'strain', 'assembly', 'annotation_version', 'accession', 'coordinate_convention', 'interval')),
            'tool': {'name': None, 'version': None, 'settings': None}, 'reported_stage': 'imported_candidate',
            'assessments': dict.fromkeys(('identity', 'host_compatibility', 'specificity', 'empirical_evidence')),
            'reported_value': None, 'reported_unit': None,
            'limitations': 'Metadata-only synthetic example. No sequence, target, tool run or empirical result.'}


def content_hash(state):
    return study.digest({k: v for k, v in state.items() if k != 'reviews'})


def transition(state, event):
    study.fields(event, ('type', 'payload'))
    state = deepcopy(state); p = event['payload']
    if event['type'] == 'brief':
        study.fields(p, ('question', 'recipient', 'constraints'))
        for v in p.values(): text(v)
        if all(state[k] == v for k, v in p.items()): raise ValueError('No brief changes to save')
        state.update(p)
    elif event['type'] == 'trait':
        study.fields(p, ('label',)); text(p['label'], 200)
        if len(state['traits']) >= 8: raise ValueError('Eight proposed traits maximum')
        if p['label'].casefold() in {t['label'].casefold() for t in state['traits']}:
            raise ValueError('That proposed trait is already present')
        state['traits'].append({'id': 'T'+str(len(state['traits'])+1), 'label': p['label'],
                                'role': 'hypothesis_evidence_missing', 'citations': []})
    elif event['type'] == 'candidate':
        c = candidate(study.decode(p) if isinstance(p, str) else p)
        if len(state['candidates']) >= 20: raise ValueError('Twenty imported records maximum')
        if c['id'] in {r['id'] for r in state['candidates']}: raise ValueError('Duplicate record ID; original retained')
        state['candidates'].append(c)
    elif event['type'] == 'review':
        study.fields(p, ('reviewer', 'scope', 'decision', 'reason', 'content_sha256'))
        text(p['reviewer'], 160); text(p['reason'])
        scopes = {'study'} | {c['id'] for c in state['candidates']}
        if not isinstance(p['scope'], str) or p['scope'] not in scopes: raise ValueError('Unknown review scope')
        if p['decision'] not in ('needs_evidence', 'reviewed_with_blockers', 'declined'):
            raise ValueError('Review cannot certify biological readiness')
        if p['content_sha256'] != content_hash(state): raise ValueError('Review must bind the exact current content')
        if p in state['reviews']: raise ValueError('This exact review is already saved')
        state['reviews'].append(deepcopy(p))
    else:
        raise ValueError('Unregistered review action; execution is unavailable')
    return state


def graph(science):
    def node(i, label, role, record): return {'id': i, 'label': label, 'role': role, 'record': record}
    nodes = [node('trait', 'Phosphorus uptake', 'published_association', science['observations']),
             node('source', 'Observed organism & conditions', 'published_observation', science['sources'][:2]),
             node('mechanism', 'PSR1-associated regulation', 'association_not_sufficiency', {'sources': ['S_PSR1_2023'], 'limit': 'Not a one-gene / one-trait transfer rule.'})]
    nodes += [node(r['id'], r['form']+' · '+r['identifier'], r['role'], r) for r in science['reference_chain']]
    nodes += [node('host', 'Receiving-host context', 'evidence_missing', {'limit': science['reference_limit'], 'annotation_version': None}),
              node('location', 'Reference location', 'database_annotation', science['reference_mapping']),
              node('review', 'Study questions & decisions', 'human_review_required', {'next': 'Qualify recipient identity; measure collected product separately.'})]
    pairs = [('trait','source','observed in source conditions'), ('source','mechanism','source-associated interpretation'),
             ('mechanism','REF_GENE','reference association; not proof of causation'), ('REF_GENOME','REF_GENE','annotated locus'),
             ('REF_GENE','REF_RNA','reference transcript'), ('REF_RNA','REF_PROTEIN','sequence reconciliation'),
             ('REF_PROTEIN','host','unqualified recipient link'), ('REF_GENE','location','reference coordinates only'),
             ('host','review','blocking question'), ('location','review','reference review required')]
    return {'nodes': nodes, 'edges': [{'from': a, 'to': b, 'relationship': c,
              'evidence_node': b, 'role': 'evidence_missing' if b in ('host','review') else 'source_linked_relationship'} for a,b,c in pairs]}


def record_checks(c):
    reference = c['reference']
    expected_accession = public_algae.PROTEIN if c['sequence_type'] == 'protein_aa' else 'NC_057015.1'
    return {'record_id': c['id'], 'role': 'local_metadata_check_not_scientific_validation',
            'assembly': 'missing' if reference['assembly'] is None else ('matches_pinned_reference' if reference['assembly']=='GCF_000002595.2' else 'incompatible_with_pinned_reference'),
            'accession': 'missing' if reference['accession'] is None else ('matches_pinned_reference' if reference['accession']==expected_accession else 'different_or_unresolved_reference'),
            'receiving_host_compatibility': 'not_qualified', 'annotation_compatibility': 'unknown_pinned_annotation_version',
            'sequence_identity': 'not_assessed', 'specificity': 'not_assessed', 'empirical_evidence': 'not_independently_verified'}


def blockers(state):
    out = ['Collected-product phosphorus is not quantified in the admitted evidence.',
           'Later plant use is unassessed; water removal, cellular uptake and collection are distinct endpoints.',
           'Receiving strain/reference compatibility and annotation version remain unqualified.',
           'Containment and disposal need human review; no dependency guarantees survival restriction.',
           'Combined traits, resource demands and environmental interactions remain unassessed.',
           'Primer3 / Primer-BLAST is reference documentation and a plan, not a verified installed integration.',
           'New guide/primer design is blocked pending a separately reviewed organism, reference and purpose.']
    for c in state['candidates']:
        checks = record_checks(c)
        if checks['assembly']=='incompatible_with_pinned_reference': out.append(c['id']+': incompatible assembly; cannot attach to the pinned reference map.')
        if checks['accession']=='different_or_unresolved_reference': out.append(c['id']+': different or unresolved accession; no coordinate mapping inferred.')
        missing = [k for k,v in c['reference'].items() if v is None]
        if missing: out.append(c['id']+': missing reference fields: '+', '.join(missing))
        out.append(c['id']+': imported identity, compatibility, specificity and empirical claims are not independently verified.')
    return out


def privacy(value):
    encoded = study.canonical(value)
    findings = [k for k,p in workbench.PATTERNS.items() if re.search(p, encoded)]
    return {'status': 'blocked' if findings else 'requires_owner_review', 'categories': findings,
            'limit': 'All included history is scanned. Pattern screening cannot detect every private detail; nothing is silently removed.'}


class Session:
    def __init__(self, cycle=None):
        self.science = pinned(); self.cycle = deepcopy(cycle); self.history = []; self.read_only = False
        if cycle is not None: validate_review(cycle)

    def state(self):
        state = initial()
        for row in self.history: state = transition(state, row['event'])
        return state

    def current(self):
        return {'hash': study.digest({'science': self.science, 'cycle': self.cycle, 'history': self.history}),
                'revision': len(self.history), 'read_only': self.read_only}

    def apply(self, event):
        if self.read_only: raise ValueError('Reopened review is read-only; the original local review is preserved')
        if len(self.history) >= 64: raise ValueError('Review history limit reached; export before continuing')
        transition(self.state(), event)
        row = {'revision': len(self.history)+1, 'parent_hash': self.history[-1]['hash'] if self.history else None,
               'saved_utc': datetime.now(timezone.utc).isoformat(), 'event': deepcopy(event)}
        row['hash'] = study.digest(row)
        proposed = self._package(self.history+[row])
        if len(study.canonical(proposed).encode()) > MAX_BYTES: raise ValueError('Review size limit exceeded; current state retained')
        self.history.append(row)

    def _package(self, history=None):
        rows = self.history if history is None else history
        state = initial()
        for row in rows: state = transition(state, row['event'])
        value = {'schema_version': SCHEMA, 'science': self.science, 'cycle': self.cycle,
                 'history': rows, 'state': state, 'blockers': blockers(state), 'review_limit': REVIEW_LIMIT, 'limit': LIMIT}
        value['sha256'] = study.digest(value)
        return deepcopy(value)

    def view(self):
        state = self.state()
        return {'current': self.current(), 'state': state, 'content_sha256': content_hash(state),
                'science': deepcopy(self.science), 'graph': graph(self.science), 'blockers': blockers(state),
                'record_checks': [record_checks(c) for c in state['candidates']],
                'interactions': [{'traits': [a['id'],b['id']], 'status': 'not_assessed',
                    'question': 'Do these proposals share resource requirements or change each other under the same conditions?',
                    'role': 'authored_review_question_evidence_missing'} for a,b in combinations(state['traits'],2)],
                'endpoints': ['Removal from water', 'Uptake into cells', 'Physically collected phosphorus', 'Later plant use'],
                'cycle': deepcopy(self.cycle), 'privacy': privacy(self._package()),
                'template': template(), 'history': deepcopy(self.history), 'limit': LIMIT,
                'storage': 'Session memory; export before shutdown. Imported packages reopen read-only.'}

    def export(self, acknowledgment):
        p = self._package()
        if privacy(p)['categories']: raise ValueError('Privacy findings block export; inspect local history. No content was removed.')
        if acknowledgment != self.current()['hash']: raise ValueError('Review all included records and acknowledge this exact local export first')
        return p

    def readable(self, acknowledgment):
        p = self.export(acknowledgment); s = self.state()
        lines = ['TRAITWEAVER — STUDY REVIEW', LIMIT, '', s['question'], 'Recipient: '+s['recipient'], 'Constraints: '+s['constraints'],
                 '', 'Four separate endpoints: removal from water; uptake into cells; physically collected phosphorus; later plant use.',
                 'Phosphorus is an element. Changes in form or location do not establish collection or later use.',
                 '', 'Hypothesis: a source-associated uptake route may support a contained recovery study; collected-product performance remains unknown.',
                 'Comparisons: source-matched control and proposed material; physical-removal controls; separately reviewed later plant-use comparison.',
                 'Confounders: strain, starting phosphorus, growth, sampling, biomass carryover, abiotic removal and compartment overlap.',
                 'Success/failure criteria: define quantitative thresholds and independent units before experiments; no thresholds are invented here.',
                 'Decision now: seek missing recovery and recipient evidence before choosing an engineering route.', '', 'BLOCKERS', *blockers(s),
                 '', 'MULTI-TRAIT PROPOSALS', study.canonical(s['traits']), 'Interactions: not assessed. No combined score.',
                 '', 'HUMAN REVIEW', REVIEW_LIMIT, study.canonical(s['reviews']) if s['reviews'] else 'Not reviewed',
                 'A review applies only when its content_sha256 matches '+content_hash(s)+'.',
                 '', 'SOURCE-LINKED MEASUREMENT OUTLINE', study.canonical(self.science['study_design']),
                 '', 'IMPORTED CANDIDATE RECORDS', study.canonical(s['candidates']),
                 '', 'MUSE', 'No cycle loaded.' if self.cycle is None else study.canonical(self.cycle['summary']),
                 '', 'COMPLETE REOPENABLE RECORD — includes source identities, settings, limits and full history', study.canonical(p)]
        return '\n'.join(lines)+'\n'

    def open(self, value):
        # Build and validate a replacement before changing any current field.
        study.fields(value, ('schema_version','science','cycle','history','state','blockers','review_limit','limit','sha256'))
        if len(study.canonical(value).encode()) > MAX_BYTES: raise ValueError('Review package too large')
        if value['schema_version'] != SCHEMA or value['limit'] != LIMIT: raise ValueError('Incompatible review package')
        if value['sha256'] != study.digest({k:v for k,v in value.items() if k!='sha256'}): raise ValueError('Review checksum mismatch')
        if study.canonical(value['science']) != study.canonical(pinned()): raise ValueError('Changed or incompatible evidence/reference snapshot')
        if privacy(value)['categories']: raise ValueError('Import has privacy findings; current study retained')
        other = Session(value['cycle'])
        if not isinstance(value['history'], list) or len(value['history']) > 64: raise ValueError('Invalid review history')
        for i,row in enumerate(value['history'],1):
            study.fields(row, ('revision','parent_hash','saved_utc','event','hash'))
            if type(row['revision']) is not int or row['revision'] != i or row['parent_hash'] != (other.history[-1]['hash'] if other.history else None):
                raise ValueError('Broken review history')
            try:
                if datetime.fromisoformat(row['saved_utc']).tzinfo is None: raise ValueError('Timestamp needs timezone')
            except (TypeError, ValueError): raise ValueError('Invalid review timestamp') from None
            if row['hash'] != study.digest({k:v for k,v in row.items() if k!='hash'}): raise ValueError('Changed history record')
            transition(other.state(), row['event']); other.history.append(deepcopy(row))
        if study.canonical(other._package()) != study.canonical(value): raise ValueError('Changed derived state or review limits')
        self.science=other.science; self.cycle=other.cycle; self.history=other.history; self.read_only=True
