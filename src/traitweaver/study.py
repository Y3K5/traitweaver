"""Guided study state machine. Pure transitions; no files, network or model calls."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = APP_ROOT / 'data/algae-public.v1.json'
BUNDLE_HASH = '08329fe8052a3d4cf708a20da55e295721fa5c56c61a4dc1f6be0c0d9fc87347'
ENDPOINTS = ('recovered_product_phosphorus', 'phosphate_uptake', 'growth', 'cellular_phosphorus')
CHECKS = ('endpoint_coverage', 'published_contrasts')
METRICS = ('phosphate_uptake', 'growth')
LIMIT = 'Descriptive source-bound evidence only. No cross-study ranking, significance, equivalence, field performance or biological winner is established.'
BRANCHES = {
    'supporting': 'Retain the narrow descriptive statement; the wider recovery claim remains unqualified.',
    'contradictory': 'Replan the stated point-mean constraint; do not infer statistical or biological failure.',
    'inconclusive': 'Specify the missing decision margin or obtain evidence for the target endpoint.',
    'unavailable': 'Request the missing endpoint/context measurements; do not substitute another endpoint.',
    'invalid': 'Correct the input identity, unit or measurement basis before interpreting it.',
    'failed': 'Inspect the software failure; no biological interpretation is permitted.',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decode(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('Duplicate JSON key')
            out[k] = v
        return out
    def nonfinite(_):
        raise ValueError('Nonfinite JSON is not supported')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid JSON document') from exc


def fields(obj, keys):
    if type(obj) is not dict or set(obj) != set(keys):
        raise ValueError('Unexpected or missing fields')


def text(value, maximum=3000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError('A nonempty, bounded text value is required')


def bundle():
    if BUNDLE.is_symlink():
        raise ValueError('Public evidence must not be a symlink')
    raw = BUNDLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BUNDLE_HASH:
        raise ValueError('Public evidence changed; separate admission is required')
    return decode(raw)


def validate_brief(brief):
    fields(brief, ('question', 'target_endpoint', 'context_notes', 'minimum_growth_ratio'))
    text(brief['question'])
    if brief['target_endpoint'] not in ENDPOINTS:
        raise ValueError('Unsupported target endpoint')
    if not isinstance(brief['context_notes'], str) or len(brief['context_notes']) > 3000 or '\x00' in brief['context_notes']:
        raise ValueError('Context notes must be bounded text')
    value = brief['minimum_growth_ratio']
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
        raise ValueError('Growth constraint must be null or a finite nonnegative ratio')


def initial_state():
    bundle()
    return {'schema_version': 'traitweaver.guided_study.v1', 'study_id': 'ALGAE_001',
            'source_bundle_sha256': BUNDLE_HASH,
            'brief': {'question': 'What evidence and next measurements would support phosphorus recovery using algae while considering growth?',
                      'target_endpoint': ENDPOINTS[0], 'context_notes': '', 'minimum_growth_ratio': None},
            'cycles': [], 'recovery_winner': None}


def eligible_checks(state):
    return [
        {'id': 'endpoint_coverage', 'label': 'Audit endpoint and context coverage', 'arguments': {}},
        *[{'id': 'published_contrasts', 'label': 'Describe published '+m+' contrasts', 'arguments': {'metric': m}} for m in METRICS]]


def decision(state, check, arguments, policy='deterministic_offline'):
    if not any(c['id'] == check and c['arguments'] == arguments for c in eligible_checks(state)):
        raise ValueError('Unavailable check or altered arguments')
    if policy not in ('deterministic_offline', 'user_selected', 'muse_validated'):
        raise ValueError('Unsupported decision policy')
    choice = {'check': check, 'arguments': deepcopy(arguments), 'policy': policy,
              'purpose': ('Establish what the admitted endpoints can support before comparing paths.' if check == 'endpoint_coverage'
                          else 'Describe a within-study contrast without converting it into recovery or equivalence evidence.'),
              'source_ids': [s['id'] for s in bundle()['sources']],
              'deferred': [c for c in eligible_checks(state) if not (c['id'] == check and c['arguments'] == arguments)],
              'branches': deepcopy(BRANCHES), 'brief_hash': digest(state['brief'])}
    return choice


def _coverage_value(state):
    b = bundle(); target = state['brief']['target_endpoint']
    rows = []
    for path in b['paths'][1:]:
        matching = [e for e in b['evidence'] if e['path_id'] == path['id'] and e['endpoint'] == target]
        rows.append({'path_id': path['id'], 'target_endpoint': target,
                     'state': 'reported_summary' if any(e['value'] is not None for e in matching) else ('qualitative_only' if matching else 'unavailable'),
                     'evidence_ids': [e['id'] for e in matching]})
    blockers = [{'code': 'different_source_contexts', 'meaning': 'The research paths have different strain/condition controls and measurement bases; no common baseline or cross-study ranking is admitted.'}]
    for row in rows:
        if row['state'] != 'reported_summary':
            blockers.append({'code': 'target_not_quantified', 'path_id': row['path_id'], 'meaning': 'The requested endpoint is not quantitatively admitted for this path.'})
    if state['brief']['minimum_growth_ratio'] is None:
        blockers.append({'code': 'growth_margin_unknown', 'meaning': 'No growth decision margin was specified.'})
    if state['brief']['context_notes'].strip():
        blockers.append({'code': 'context_transfer_unqualified', 'meaning': 'Edited context notes do not qualify transfer from the published source conditions.'})
    return {'status': 'completed', 'kind': 'actual_computation', 'tool': 'endpoint_coverage',
            'rows': rows, 'blockers': blockers, 'limit': LIMIT}


def coverage(state):
    return _coverage_value(state)


def _contrast_value(state, metric):
    if metric not in METRICS:
        raise ValueError('Unsupported contrast metric')
    records = [e for e in bundle()['evidence'] if e['source_id'] == 'S_PSR1_2023' and e['metric'] == metric]
    control = next((e for e in records if e['subject'] == 'UVM4'), None)
    if not control or len(records) != 4:
        return {'status': 'unavailable', 'tool': 'published_contrasts', 'reason': 'Required source summaries are missing.', 'limit': LIMIT}
    for record in records:
        value = record['value']
        if (type(value) not in (int, float) or not math.isfinite(value) or
            any(record[k] != control[k] for k in ('source_id', 'metric', 'unit', 'measurement_basis', 'organism'))):
            return {'status': 'invalid', 'tool': 'published_contrasts', 'reason': 'Input identity, units, basis or numeric values are incompatible.', 'limit': LIMIT}
    rows = [{'subject': r['subject'], 'evidence_id': r['id'], 'reported_mean': r['value'], 'reported_uncertainty': r['uncertainty'],
             'difference_from_control': r['value'] - control['value'],
             'ratio_to_control': r['value'] / control['value'] if control['value'] != 0 else None} for r in records[1:]]
    return {'status': 'completed', 'kind': 'actual_computation', 'tool': 'published_contrasts', 'metric': metric,
            'source_id': control['source_id'], 'unit': control['unit'], 'measurement_basis': control['measurement_basis'],
            'control': control, 'rows': rows, 'formula': 'difference = published mean - control mean; ratio = published mean / control mean',
            'uncertainty_limit': 'Original SE and n retained; uncertainty of differences/ratios is not estimated. No p-values or equivalence test.', 'limit': LIMIT}


def contrasts(state, metric):
    return _contrast_value(state, metric)


def measurement_plan(state):
    return {'mode': 'proposed_measurement_study_for_review', 'question': state['brief']['question'],
            'target_endpoint': state['brief']['target_endpoint'],
            'comparison': 'Each proposed research path versus an explicitly qualified, matched reference; establish a common context before comparing paths.',
            'controls': ['Matched source/strain and nutrient-context reference', 'Process/material accounting control', 'Growth reference measured alongside the target endpoint'],
            'readouts': ['Phosphorus in recovered product and its accounting boundary', 'Medium phosphate and biomass phosphorus as separate compartments', 'Growth with explicit units and time basis'],
            'independent_units': 'Independent culture/process units; technical readings are not independent replication.',
            'unresolved': ['Actual material/stock and target context', 'Recovery compartment, denominator and assay qualification', 'Growth margin and recovery decision threshold', 'Independent sample count and justified analysis design'],
            'execution': 'Not executed. Researcher review required; no laboratory instructions or organism design.'}


def assessment(state, result):
    status = result['status']; brief = state['brief']; outcome = 'inconclusive'
    if status in ('failed', 'invalid', 'unavailable'):
        outcome = status
    elif result['tool'] == 'endpoint_coverage':
        outcome = 'unavailable' if any(r['state'] == 'unavailable' for r in result['rows']) else 'inconclusive'
    elif result.get('metric') == 'growth' and brief['minimum_growth_ratio'] is not None:
        ratios = [r['ratio_to_control'] for r in result['rows']]
        if None in ratios:
            outcome = 'invalid'
        elif max(ratios) < brief['minimum_growth_ratio']:
            outcome = 'contradictory'
        elif brief['target_endpoint'] == 'growth' and not brief['context_notes'].strip():
            outcome = 'supporting' if min(ratios) >= brief['minimum_growth_ratio'] else 'inconclusive'
    return {'outcome': outcome, 'interpretation': BRANCHES[outcome], 'source_ids': [s['id'] for s in bundle()['sources']],
            'next_action': 'researcher_review_measurement_plan', 'measurement_plan': measurement_plan(state),
            'constraint_limit': 'Any growth-bound comparison concerns published point means only; it does not establish equivalence or performance in a new context.',
            'recovery_winner': None, 'limit': LIMIT}


def transition(state, action, recorded_result=None):
    fields(action, ('type', 'payload')); kind, payload = action['type'], action['payload']; out = deepcopy(state)
    if kind == 'edit':
        validate_brief(payload)
        if payload == state['brief']:
            raise ValueError('No study fields changed')
        out['brief'] = deepcopy(payload)
        for c in out['cycles']:
            c['applicability'] = 'current' if c['decision']['brief_hash'] == digest(payload) else 'needs_reassessment'
    elif kind == 'decide':
        fields(payload, ('check', 'arguments', 'policy'))
        if out['cycles'] and out['cycles'][-1]['applicability'] == 'current' and out['cycles'][-1]['assessment'] is None:
            raise ValueError('Finish the current cycle before starting another')
        if len(out['cycles']) >= 32:
            raise ValueError('Study cycle limit reached; export and review the study')
        out['cycles'].append({'id': 'C'+str(len(out['cycles'])+1), 'decision': decision(state, **payload),
                              'result': None, 'assessment': None, 'applicability': 'current'})
    elif kind in ('run', 'reassess'):
        fields(payload, ())
        if not out['cycles'] or out['cycles'][-1]['applicability'] != 'current':
            raise ValueError('No current decision; prepare a new cycle')
        c = out['cycles'][-1]
        if kind == 'run':
            if c['result'] is not None:
                raise ValueError('This cycle already has a result')
            d = c['decision']
            failure = {'status': 'failed', 'kind': 'actual_computation', 'tool': d['check'],
                       'reason': 'Local check failed; no biological interpretation is permitted.', 'limit': LIMIT, 'id': c['id']+'_RESULT'}
            if recorded_result is not None:
                # Validate saved values without dispatching a registered tool or
                # generating a new execution/result receipt during reopen.
                expected = failure if recorded_result.get('status') == 'failed' else (
                    _coverage_value(state) if d['check'] == 'endpoint_coverage' else _contrast_value(state, d['arguments']['metric']))
                expected['id'] = c['id']+'_RESULT'
                if canonical(recorded_result) != canonical(expected):
                    raise ValueError('Saved result does not match its admitted inputs and formula')
                c['result'] = deepcopy(recorded_result)
            else:
                try:
                    c['result'] = coverage(state) if d['check'] == 'endpoint_coverage' else contrasts(state, d['arguments']['metric'])
                except (OSError, ArithmeticError):
                    c['result'] = failure
            c['result']['id'] = c['id']+'_RESULT'
        else:
            if c['result'] is None or c['assessment'] is not None:
                raise ValueError('Reassessment needs one unassessed result')
            c['assessment'] = assessment(state, c['result'])
    else:
        raise ValueError('Unsupported study action')
    return out


def readable(state):
    lines = ['# Traitweaver — research study brief', '', 'Study: '+state['study_id'],
             'Question: '+state['brief']['question'], 'Target endpoint: '+state['brief']['target_endpoint'],
             'Context notes: '+(state['brief']['context_notes'] or 'Source contexts only'),
             'Minimum growth ratio: '+str(state['brief']['minimum_growth_ratio']), '', LIMIT, '', '## Source evidence', '']
    for s in bundle()['sources']:
        lines += [s['id']+' — '+s['authors']+' ('+str(s['year'])+')', s['title'], s['url'], s['license'], s['admission'], '']
    for e in bundle()['evidence']:
        lines += [e['id']+' ['+e['role']+'] — '+e['source_id']+' — '+e['locator'],
                  canonical(e), '']
    for cycle in state['cycles']:
        lines += ['## Cycle '+cycle['id']+' — '+cycle['applicability'],
                  'Decision (saved before result): '+canonical(cycle['decision']),
                  'Actual result: '+canonical(cycle['result']), 'Reassessment: '+canonical(cycle['assessment']), '']
    lines += ['## Proposed measurement plan', canonical(measurement_plan(state)), '', 'Recovery winner: none (null)',
              'Software: Codex; guided local workspace. Provider contribution is present only when a validated receipt exists.']
    return '\n'.join(lines)+'\n'
