"""Offline history-informed selection and independent proposal review.

Never translates a v2 reply into a v1 decision, executes a check, or sends a
request. Archived source packages preserve the owning v1 bytes for validation.
"""
from copy import deepcopy
import hashlib

from traitweaver import intelligence as model, intelligence_continuation as continuation
from traitweaver import intelligence_muse as v1, intelligence_store, study
from traitweaver.study_store import Conflict, MAX_BYTES, screen_export

REQUEST = 'traitweaver.intelligence_request.v2'
PACKAGE = 'traitweaver.intelligence_next_review.v2'
MAX_REQUEST_BYTES = 131072
MAX_REVIEWS = 8
LIMIT = ('Valid proposal only; no intelligence cycle accepted or check run. Local consistency does not '
         'authenticate a provider or establish scientific usefulness, adaptation or execution approval. '
         'No live transport, credential access or inherited spending approval. ' + model.LIMIT)
BASE_FIELDS = ('check', 'arguments', 'claim_codes', 'citations')
PROPOSAL_FIELDS = (*BASE_FIELDS, 'preview_sha256', 'check_input_sha256',
                   'reviewed_result_ids', 'unresolved_requirement_ids')


def prepare(source, bundle, context, reviewed_preview_sha256, acknowledged, focus='trait'):
    records = intelligence_store.validate_package(source, bundle)
    preview = continuation.prepare(records, bundle, context)
    if acknowledged is not True or reviewed_preview_sha256 != preview['preview_sha256']:
        raise ValueError('Review and acknowledge the exact current continuation before preparing v2')
    if preview['status'] != 'review_next_check':
        raise ValueError('No next selection is available: review scope, finish the current cycle, or stop with the saved gaps')
    if not any(c['result'] is not None and c['assessment'] is not None for c in preview['prior_cycles']):
        raise ValueError('A next-selection request requires a prior saved result and separate reassessment')
    state = records[-1]['state']
    legacy = v1.prepare(state, 'selection', bundle, focus)
    public = study.decode(legacy['body']['input'])
    eligible = [row['check'] for row in preview['checks'] if row['eligible']]
    requirements = [{**deepcopy(row), 'id': 'REQ_' + str(i).zfill(4)}
                    for i, row in enumerate(preview['unresolved_requirements'], 1)]
    result_ids = [c['result']['id'] for c in preview['prior_cycles'] if c['result'] is not None]
    public['eligible_checks'] = {key: model.CHECKS[key] for key in eligible}
    public['continuation_context'] = {
        'preview_sha256': preview['preview_sha256'], 'lineage': deepcopy(preview['lineage']),
        'source_digests': deepcopy(preview['source_digests']),
        'prior_cycles': deepcopy(preview['prior_cycles']), 'unresolved_requirements': requirements,
        'input_eligibility': deepcopy(preview['checks']),
        'qualification': 'Prior cycles retain original scope and synthetic/imported-unverified provenance. '
                         'Requirements are authored review gaps, not observations or proof of biological absence.'}
    schema = v1.response_schema(state, 'selection', bundle)
    schema['properties']['check']['enum'] = eligible
    schema['properties'].update({
        'preview_sha256': {'type': 'string', 'enum': [preview['preview_sha256']]},
        'check_input_sha256': {'type': 'string', 'enum': [r['input_sha256'] for r in preview['checks'] if r['eligible']]},
        'reviewed_result_ids': {'type': 'array', 'items': {'type': 'string', 'enum': result_ids}, 'minItems': 1, 'maxItems': len(result_ids)},
        'unresolved_requirement_ids': {'type': 'array', 'items': {'type': 'string', 'enum': [r['id'] for r in requirements]}, 'minItems': 1, 'maxItems': len(requirements)},
    })
    schema['required'] = list(PROPOSAL_FIELDS)
    body = {**deepcopy(legacy['body']), 'input': study.canonical(public),
            'instructions': legacy['body']['instructions'] +
            ' This is a next-selection review. Inspect the supplied prior decisions, actual results, reassessments '
            'and unresolved requirements in their original scope. Select only an eligible check. Do not repeat '
            'completed inputs or retry failed inputs. Cite at least one supplied result and an unresolved requirement '
            'from that result; preserve claim qualifications. Use the exact input identity for the selected check. '
            'A proposal does not authorize execution. References and schema compliance alone do not demonstrate adaptation.',
            'text': {'format': {'type': 'json_schema', 'name': 'traitweaver_molecular_next_selection_v2', 'strict': True, 'schema': schema}}}
    screen_export(body)
    if len(study.canonical(body).encode()) > MAX_REQUEST_BYTES:
        raise ValueError('V2 request exceeds 128 KiB; no history was truncated or sent')
    return {'schema_version': REQUEST, 'phase': 'next_selection', 'focus': focus,
            'reviewed_preview_sha256': preview['preview_sha256'], 'human_acknowledgment': 'exact_preview_for_local_preparation_only',
            'lineage': deepcopy(preview['lineage']), 'eligible_checks': eligible,
            'source_package_sha256': study.digest(source), 'destination': v1.DESTINATION,
            'body': body, 'request_sha256': study.digest(body), 'status': 'not_sent',
            'live_transport_available': False, 'limit': LIMIT}


def validate_request(request, source, bundle, context):
    if not isinstance(request, dict):
        raise ValueError('V2 request must be a structured object')
    expected = prepare(source, bundle, context, request.get('reviewed_preview_sha256'), True, request.get('focus'))
    if study.canonical(request) != study.canonical(expected):
        raise ValueError('V2 request is stale or differs from its exact reviewed source history')
    return expected


def _unique_refs(values, allowed, name):
    if not isinstance(values, list) or not values or any(not isinstance(x, str) or x not in allowed for x in values) or len(values) != len(set(values)):
        raise ValueError('Invalid, duplicate or missing ' + name)


def validate_proposal(proposal, request, source, bundle):
    study.fields(proposal, PROPOSAL_FIELDS)
    state = source['revisions'][-1]['state']
    v1.validate_proposal(state, 'selection', {k: proposal[k] for k in BASE_FIELDS}, bundle)
    if proposal['check'] not in request['eligible_checks']:
        raise ValueError('V2 proposal selects completed, failed or otherwise ineligible inputs')
    context = study.decode(request['body']['input'])['continuation_context']
    check = next(r for r in context['input_eligibility'] if r['check'] == proposal['check'])
    if proposal['preview_sha256'] != request['reviewed_preview_sha256'] or proposal['check_input_sha256'] != check['input_sha256']:
        raise ValueError('V2 proposal does not match the reviewed continuation and selected inputs')
    results = {c['result']['id'] for c in context['prior_cycles'] if c['result'] is not None}
    requirements = {r['id']: r for r in context['unresolved_requirements']}
    _unique_refs(proposal['reviewed_result_ids'], results, 'prior result references')
    _unique_refs(proposal['unresolved_requirement_ids'], requirements, 'unresolved requirement references')
    if any(requirements[key]['result_id'] not in proposal['reviewed_result_ids'] for key in proposal['unresolved_requirement_ids']):
        raise ValueError('Unresolved requirement does not belong to a referenced prior result')
    return deepcopy(proposal)


def synthetic_reply(request, check):
    if check not in request['eligible_checks']:
        raise ValueError('Select an eligible check for this synthetic fixture')
    public = study.decode(request['body']['input']); context = public['continuation_context']
    row = next(r for r in context['input_eligibility'] if r['check'] == check)
    requirement = context['unresolved_requirements'][0]
    claims = public['claims']
    citations = model.required_citations(check, {'reference': public['reference_mapping']})
    if any(c not in claims for c in citations):
        raise ValueError('Synthetic fixture lacks admitted claims')
    proposal = {'check': check, 'arguments': deepcopy(public['scope']), 'claim_codes': deepcopy(v1.CLAIMS[check]),
                'citations': citations, 'preview_sha256': request['reviewed_preview_sha256'],
                'check_input_sha256': row['input_sha256'], 'reviewed_result_ids': [requirement['result_id']],
                'unresolved_requirement_ids': [requirement['id']]}
    return {'model': v1.MODEL, 'status': 'completed', 'traitweaver_synthetic': True,
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': study.canonical(proposal)}]}]}


def _receipt(receipt):
    study.fields(receipt, ('reported_model', 'response_sha256', 'provenance', 'reported_usage', 'cost_usd', 'transport_calls'))
    if receipt['reported_model'] != v1.MODEL or receipt['provenance'] not in ('synthetic_fixture', 'owner_imported_authenticity_unverified') or receipt['cost_usd'] is not None or type(receipt['transport_calls']) is not int or receipt['transport_calls'] != 0:
        raise ValueError('Unsupported v2 response provenance or transport claim')
    fingerprint = receipt['response_sha256']
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError('Invalid v2 response fingerprint')
    usage = receipt['reported_usage']
    if usage is not None:
        study.fields(usage, ('input_tokens', 'output_tokens', 'total_tokens'))
        if any(type(v) is not int or not 0 <= v <= 10000000 for v in usage.values()) or usage['output_tokens'] > 1024 or usage['total_tokens'] != usage['input_tokens'] + usage['output_tokens']:
            raise ValueError('Invalid v2 typed usage')


def parse_reply(request, source, bundle, context, raw):
    validate_request(request, source, bundle, context)
    if not isinstance(raw, bytes) or len(raw) > v1.MAX_RESPONSE:
        raise ValueError('V2 response must be bounded JSON text')
    reply = study.decode(raw); screen_export(reply)
    if not isinstance(reply, dict) or reply.get('model') != v1.MODEL or reply.get('status') != 'completed':
        raise ValueError('Wrong model, incomplete v2 response or refusal')
    if 'traitweaver_synthetic' in reply and type(reply['traitweaver_synthetic']) is not bool:
        raise ValueError('Synthetic provenance marker must be boolean')
    if not isinstance(reply.get('output'), list):
        raise ValueError('Expected typed response output')
    texts = []
    for item in reply['output']:
        if not isinstance(item, dict): raise ValueError('Malformed response item')
        if item.get('type') == 'reasoning': continue
        if item.get('type') != 'message' or not isinstance(item.get('content'), list):
            raise ValueError('Unexpected provider action; no tool executed')
        for block in item['content']:
            if not isinstance(block, dict) or block.get('type') != 'output_text' or not isinstance(block.get('text'), str):
                raise ValueError('Refusal or unsupported response content')
            texts.append(block['text'])
    if len(texts) != 1: raise ValueError('Expected one structured v2 proposal')
    proposal = validate_proposal(study.decode(texts[0]), request, source, bundle)
    usage = reply.get('usage')
    if usage is not None and not isinstance(usage, dict): raise ValueError('Invalid v2 usage')
    receipt = {'reported_model': v1.MODEL, 'response_sha256': hashlib.sha256(raw).hexdigest(),
               'provenance': 'synthetic_fixture' if reply.get('traitweaver_synthetic') is True else 'owner_imported_authenticity_unverified',
               'reported_usage': None if usage is None else {k: usage.get(k) for k in ('input_tokens', 'output_tokens', 'total_tokens')},
               'cost_usd': None, 'transport_calls': 0}
    _receipt(receipt)
    return {'status': 'valid_proposal_only', 'request_sha256': request['request_sha256'], 'proposal': proposal, 'receipt': receipt}


def validate_package(value, bundle):
    try:
        study.fields(value, ('schema_version', 'source_package', 'request', 'proposal_review', 'limit'))
        if value['schema_version'] != PACKAGE or value['limit'] != LIMIT:
            raise ValueError('Unsupported v2 proposal-review package')
        source = value['source_package']
        records = intelligence_store.validate_package(source, bundle)
        request = validate_request(value['request'], source, bundle, records[-1]['state']['context'])
        review = value['proposal_review']
        if review is not None:
            study.fields(review, ('status', 'request_sha256', 'proposal', 'receipt'))
            if review['status'] != 'valid_proposal_only' or review['request_sha256'] != request['request_sha256']:
                raise ValueError('Invalid v2 proposal-review binding')
            validate_proposal(review['proposal'], request, source, bundle); _receipt(review['receipt'])
        screen_export(value)
        if len(study.canonical(value).encode()) > MAX_BYTES: raise ValueError('V2 review package exceeds its byte limit')
        return deepcopy(value)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('Malformed v2 proposal-review package') from exc


class Session:
    """Bounded session-only archives; never writes to the v1 journal or disk."""
    def __init__(self):
        self.reviews = []; self.active = None; self.read_only = False

    def current(self):
        return self.reviews[self.active] if self.active is not None else None

    def fingerprint(self):
        return study.digest(self.current()) if self.current() is not None else None

    def expect(self, expected):
        if expected != self.fingerprint(): raise Conflict('V2 review changed; reload before continuing')

    def _append(self, value, read_only):
        if len(self.reviews) >= MAX_REVIEWS or len(study.canonical(self.reviews + [value]).encode()) > MAX_BYTES:
            raise ValueError('V2 session archive is full; export reviews before starting a new session')
        self.reviews.append(deepcopy(value)); self.active = len(self.reviews) - 1; self.read_only = read_only

    def prepare(self, expected, journal, context, reviewed_preview_sha256, acknowledged, focus):
        self.expect(expected)
        if journal.read_only: raise ValueError('Imported intelligence history is read-only')
        source = journal.export()
        request = prepare(source, journal.bundle, context, reviewed_preview_sha256, acknowledged, focus)
        value = {'schema_version': PACKAGE, 'source_package': source, 'request': request, 'proposal_review': None, 'limit': LIMIT}
        self._append(validate_package(value, journal.bundle), False)

    def respond(self, expected, journal, context, raw=None, check=None):
        self.expect(expected); value = self.current()
        if value is None or self.read_only or value['proposal_review'] is not None:
            raise ValueError('One editable v2 request without a validated response is required')
        if journal.read_only: raise ValueError('Imported intelligence history is read-only')
        source = journal.export()
        validate_request(value['request'], source, journal.bundle, context)
        if check is not None: raw = study.canonical(synthetic_reply(value['request'], check)).encode()
        review = parse_reply(value['request'], source, journal.bundle, context, raw)
        updated = {**deepcopy(value), 'proposal_review': review}
        validate_package(updated, journal.bundle)
        proposed = deepcopy(self.reviews); proposed[self.active] = updated
        if len(study.canonical(proposed).encode()) > MAX_BYTES: raise ValueError('V2 session archive exceeds its byte limit')
        self.reviews[self.active] = updated

    def open(self, expected, value, bundle):
        self.expect(expected); self._append(validate_package(value, bundle), True)

    def select(self, expected, fingerprint):
        self.expect(expected)
        for index, value in enumerate(self.reviews):
            if study.digest(value) == fingerprint:
                self.active = index; self.read_only = True; return
        raise ValueError('Unknown archived v2 review')

    def view(self, journal, context):
        value = self.current(); request = value['request'] if value else None
        current = journal.current() if journal else None
        applicable = bool(request and current and request['lineage']['head_hash'] == current['hash'] and
                          request['lineage']['state_sha256'] == study.digest(current['state']) and
                          request['lineage']['catalog_sha256'] == study.digest(journal.bundle) and
                          request['lineage']['owning_context_sha256'] == study.digest(context))
        return {'review_hash': self.fingerprint(), 'read_only': self.read_only,
                'applicability': 'not_prepared' if value is None else 'current' if applicable else 'stale',
                'request': deepcopy(request), 'proposal_review': deepcopy(value['proposal_review']) if value else None,
                'package': deepcopy(value), 'history': [{'review_hash': study.digest(p), 'source_revision': p['request']['lineage']['revision'],
                                                       'status': 'valid_proposal_only' if p['proposal_review'] else 'not_sent'} for p in self.reviews],
                'storage': 'session_only_export_to_keep', 'limit': LIMIT}
