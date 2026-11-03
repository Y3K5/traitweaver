"""Versioned local decision preview. No model payload, transport or check dispatch.

Historical v1 packages and request hashes are unchanged. This projection explains
which existing receipts cover the current check inputs; it does not make old
assessments current or claim that a different question supplies new evidence.
"""
from copy import deepcopy

from traitweaver import intelligence, study
from traitweaver.study_store import MAX_BYTES, screen_export

SCHEMA = 'traitweaver.intelligence_continuation.v1'
INPUT_FIELDS = {
    'trait_evidence_audit': ('target_endpoint', 'minimum_growth_ratio'),
    'combination_coverage': ('combination',),
    'transfer_coverage': ('recipient',),
}


def input_identity(check, scope, catalog_hash):
    """Only scientific check inputs count, not authored plan wording or notes."""
    intelligence.validate_scope(scope)
    values = {key: scope[key] for key in INPUT_FIELDS[check]}
    if 'minimum_growth_ratio' in values and values['minimum_growth_ratio'] is not None:
        # v1 accepts int/float and signed zero; their audit semantics are identical.
        number = float(values['minimum_growth_ratio'])
        values['minimum_growth_ratio'] = 0.0 if number == 0 else number
    body = {'check': check, 'catalog_sha256': catalog_hash, 'inputs': values}
    return {**body, 'input_sha256': study.digest(body)}


def _accepted(record):
    if record is None:
        return None
    accepted = record['accepted_reply']
    return {'proposal': deepcopy(accepted['proposal']),
            'provenance': accepted['receipt']['provenance'],
            'request_sha256': accepted['request_sha256'],
            'response_sha256': accepted['receipt']['response_sha256']}


def prepare(records, bundle, owning_context):
    # Import lazily: Journal.view owns this projection, not the saved v1 schema.
    from traitweaver.intelligence_store import package, validate_package
    if records:
        records = validate_package(package(records, bundle), bundle)
        head = records[-1]; state = head['state']
    else:
        head = {'revision': 0, 'hash': None}; state = intelligence.initial()
    catalog_hash = study.digest(bundle)
    checks = []
    for check in intelligence.CHECKS:
        identity = input_identity(check, state['scope'], catalog_hash)
        history = [c for c in state['cycles'] if c['decision']['check'] == check]
        matches = [c for c in history if c['result'] is not None and
                   input_identity(check, c['scope'], catalog_hash)['input_sha256'] == identity['input_sha256']]
        completed = [c for c in matches if c['result']['status'] == 'completed']
        status = ('already_checked' if completed else 'failed_requires_review' if matches else
                  'eligible_changed_inputs' if any(c['result'] is not None for c in history) else 'eligible_unchecked')
        reason = {
            'already_checked': 'These check inputs were already checked. Missing evidence is not a reason to rerun identical inputs.',
            'failed_requires_review': 'A local check failed on these inputs. Inspect the failure; this preview does not authorize a retry.',
            'eligible_changed_inputs': 'Relevant check inputs changed. This is a new question or constraint, not new source evidence.',
            'eligible_unchecked': 'No saved result covers these check inputs. Review whether this audit helps the study.',
        }[status]
        checks.append({**identity, 'label': intelligence.CHECKS[check], 'status': status,
                       'eligible': not matches, 'reason': reason,
                       'matching_results': [{'cycle_id': c['id'], 'result_id': c['result']['id'],
                                             'status': c['result']['status'], 'applicability': c['applicability']} for c in matches]})
    context_status = ('not_saved' if state['context'] is None else
                      'current' if state['context'] == owning_context else 'needs_review')
    current = intelligence.active(state)
    status = ('review_scope' if context_status != 'current' else
              'finish_current_cycle' if current and current['assessment'] is None else
              'review_next_check' if any(row['eligible'] for row in checks) else 'stop_no_new_inputs')
    prior, unresolved = [], []
    for c in state['cycles']:
        result, assessment = c['result'], c['assessment']
        prior.append({'cycle_id': c['id'], 'scope': deepcopy(c['scope']), 'applicability': c['applicability'],
                      'decision': {'check': c['decision']['check'], 'authored_purpose': c['decision']['purpose'],
                                   **_accepted(c['decision'])},
                      'result': deepcopy(result),
                      'assessment': None if assessment is None else {
                          'result_id': assessment['result_id'], 'outcome': assessment['outcome'],
                          'next_action': assessment['next_action'], 'authored_interpretation': assessment['interpretation'],
                          **_accepted(assessment)}})
        if result is not None:
            for kind, texts in [('saved_result_blocker', result['blockers']),
                                ('authored_measurement_requirement', result['measurement_plan']['unresolved'])]:
                unresolved.extend({'cycle_id': c['id'], 'result_id': result['id'], 'kind': kind, 'text': text,
                                   'citations': deepcopy(result['citations']),
                                   'qualification': 'Review requirement in its original scope; citations locate context, not proof of biological absence.'}
                                  for text in texts)
    value = {
        'schema_version': SCHEMA, 'kind': 'deterministic_local_preview', 'model_request': False,
        'human_review_required': True, 'transport_calls': 0, 'status': status,
        'lineage': {'revision': head['revision'], 'head_hash': head['hash'], 'state_sha256': study.digest(state),
                    'catalog_sha256': catalog_hash, 'scope_sha256': study.digest(state['scope']),
                    'saved_context_sha256': study.digest(state['context']),
                    'owning_context_sha256': study.digest(owning_context)},
        'context_status': context_status, 'scope': deepcopy(state['scope']),
        'source_digests': deepcopy(bundle['source_digests']), 'claim_records': deepcopy(bundle['claims']),
        'public_sources': deepcopy(bundle['literature']['sources']),
        'prior_cycles': prior, 'unresolved_requirements': unresolved, 'checks': checks,
        'suggestion': {'kind': 'deterministic_local_rule',
                       'action': status,
                       'check_ids': [row['check'] for row in checks if row['eligible']] if status == 'review_next_check' else []},
        'limit': 'Local review only. No model selected these options. Existing v1 Muse requests do not include this preview. '
                 'Changed settings are not new evidence. Prior records retain their original scope and provenance. '
                 'Human review and an explicit action are required; no automatic selection, execution or retry. ' + intelligence.LIMIT,
    }
    screen_export(value)
    if len(study.canonical(value).encode()) > MAX_BYTES:
        raise ValueError('Continuation preview exceeds its bound; no history was truncated')
    return {**value, 'preview_sha256': study.digest(value)}


def validate(value, records, bundle, owning_context):
    expected = prepare(records, bundle, owning_context)
    if study.canonical(value) != study.canonical(expected):
        raise ValueError('Continuation preview is stale or differs from its validated source history')
    return expected


def require_available(records, bundle, check):
    """New-admission gate only; never apply to historical v1 replay validation."""
    context = records[-1]['state']['context'] if records else None
    preview = prepare(records, bundle, context)
    row = next(row for row in preview['checks'] if row['check'] == check)
    if row['status'] == 'already_checked':
        raise ValueError('These intelligence inputs were already checked; review the saved result or change relevant inputs')
    if row['status'] == 'failed_requires_review':
        raise ValueError('The local check failed on these inputs; review is required before any separately implemented retry')
