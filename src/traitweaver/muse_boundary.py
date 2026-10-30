"""Prepared, bounded Muse requests. Live sending requires a separate exact grant.

Model output selects registered choices/citations, not uncheckable scientific prose.
The browser never sends live requests or reads a credential.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from traitweaver import study

DESTINATION = 'https://api.meta.ai/v1/responses'
MODEL = 'muse-spark-1.3'
MAX_REQUEST = 24000
MAX_RESPONSE = 256 * 1024
MAX_TOKENS = 1024


def context(state, phase):
    if phase not in ('selection', 'reassessment'):
        raise ValueError('Unknown reasoning phase')
    if phase == 'selection':
        if state['cycles'] and state['cycles'][-1]['applicability'] == 'current' and state['cycles'][-1]['assessment'] is None:
            raise ValueError('Finish the current cycle before preparing a selection')
    else:
        if not state['cycles'] or state['cycles'][-1]['applicability'] != 'current' or state['cycles'][-1]['result'] is None or state['cycles'][-1]['assessment'] is not None:
            raise ValueError('Reassessment requires a current unassessed result')
    return {'study_id': state['study_id'], 'brief': state['brief'], 'public_evidence': study.bundle(),
            'eligible_checks': study.eligible_checks(state),
            'result': state['cycles'][-1]['result'] if phase == 'reassessment' else None,
            'claim_limit': study.LIMIT}


def response_schema(state, phase):
    properties = {'citations': {'type': 'array', 'items': {'type': 'string', 'enum': [s['id'] for s in study.bundle()['sources']]}, 'minItems': 1, 'maxItems': 2}}
    if phase == 'selection':
        properties.update({'check': {'type': 'string', 'enum': list(study.CHECKS)},
                           'metric': {'type': ['string', 'null'], 'enum': [None, *study.METRICS]},
                           'rationale_code': {'type': 'string', 'enum': ['audit_target_before_comparison', 'describe_source_bound_means']}})
    else:
        expected = study.assessment(state, state['cycles'][-1]['result'])
        properties.update({'outcome': {'type': 'string', 'enum': [expected['outcome']]},
                           'next_action': {'type': 'string', 'enum': ['researcher_review_measurement_plan']},
                           'result_id': {'type': 'string', 'enum': [state['cycles'][-1]['result']['id']]}})
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def prepare(state, phase):
    view = context(state, phase)
    body = {'model': MODEL, 'store': False, 'max_output_tokens': MAX_TOKENS,
            'instructions': 'Select one registered scientific evidence check or classify the supplied result within the closed schema. Cite only supplied source IDs. No arbitrary tools, laboratory execution, statistical significance, endpoint substitution or biological winner. Return only the structured object. This is an open-evidence literature workflow, not a hidden-data evaluation.',
            'input': study.canonical(view),
            'text': {'format': {'type': 'json_schema', 'name': 'traitweaver_'+phase, 'strict': True, 'schema': response_schema(state, phase)}}}
    if len(study.canonical(body).encode()) > MAX_REQUEST:
        raise ValueError('Prepared request exceeds the allowed size; no truncation or send occurred')
    return {'schema_version': 'traitweaver.muse_request.v1', 'phase': phase,
            'destination': DESTINATION, 'request_sha256': study.digest(body), 'body': body, 'status': 'not_sent',
            'review_notice': 'Review all edited question/context text before approving the exact payload and spending limit. Preparing sends nothing.'}


def validate_proposal(state, phase, proposal):
    schema = response_schema(state, phase)
    study.fields(proposal, schema['required'])
    citations = proposal['citations']
    if not isinstance(citations, list) or not 1 <= len(citations) <= 2 or any(not isinstance(c, str) for c in citations) or len(set(citations)) != len(citations) or any(c not in ('S_PSR1_2023', 'S_OVERPLUS_2024') for c in citations):
        raise ValueError('Unknown, missing or duplicated source citations')
    if phase == 'selection':
        check = proposal['check']; metric = proposal['metric']
        if check not in study.CHECKS or (check == 'endpoint_coverage' and metric is not None) or (check == 'published_contrasts' and metric not in study.METRICS):
            raise ValueError('Unavailable action or altered arguments')
        expected = 'audit_target_before_comparison' if check == 'endpoint_coverage' else 'describe_source_bound_means'
        if proposal['rationale_code'] != expected or (check == 'published_contrasts' and 'S_PSR1_2023' not in citations):
            raise ValueError('Rationale/citation exceeds the admitted check context')
    else:
        expected = study.assessment(state, state['cycles'][-1]['result'])
        if (proposal['outcome'] != expected['outcome'] or proposal['next_action'] != expected['next_action'] or
                proposal['result_id'] != state['cycles'][-1]['result']['id']):
            raise ValueError('Reassessment exceeds the recorded result or claim ceiling')
    return deepcopy(proposal)


def parse_reply(state, phase, raw, request_hash):
    preview = prepare(state, phase)
    if request_hash != preview['request_sha256']:
        raise ValueError('Reply does not match the current prepared request')
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Saved reply exceeds the size limit')
    reply = study.decode(raw)
    if not isinstance(reply, dict) or reply.get('model') != MODEL or reply.get('status') != 'completed':
        raise ValueError('Wrong model, refusal or incomplete provider reply')
    texts = []
    output = reply.get('output')
    if not isinstance(output, list):
        raise ValueError('Expected typed provider output items')
    for item in output:
        if not isinstance(item, dict):
            raise ValueError('Malformed provider output item')
        if item.get('type') == 'message':
            content_items = item.get('content')
            if not isinstance(content_items, list):
                raise ValueError('Malformed provider message')
            for content in content_items:
                if not isinstance(content, dict):
                    raise ValueError('Malformed provider content')
                if content.get('type') == 'refusal':
                    raise ValueError('Provider refused this request')
                if content.get('type') == 'output_text':
                    if not isinstance(content.get('text'), str):
                        raise ValueError('Provider output text must be text')
                    texts.append(content['text'])
        elif item.get('type') != 'reasoning':
            raise ValueError('Unexpected provider tool/action output')
    if len(texts) != 1:
        raise ValueError('Expected one structured response')
    proposal = validate_proposal(state, phase, study.decode(texts[0]))
    return {'phase': phase, 'request_sha256': request_hash, 'proposal': proposal,
            'receipt': {'reported_model': MODEL, 'response_sha256': hashlib.sha256(raw).hexdigest(),
                        'provenance': 'synthetic_fixture' if reply.get('traitweaver_synthetic') is True else 'owner_imported_reply_authenticity_unverified'}}


def accept_action(state, payload):
    study.fields(payload, ('phase', 'request_sha256', 'proposal', 'receipt'))
    phase = payload['phase']
    if payload['request_sha256'] != prepare(state, phase)['request_sha256']:
        raise ValueError('Stale or altered prepared request')
    proposal = validate_proposal(state, phase, payload['proposal'])
    receipt = payload['receipt']
    study.fields(receipt, ('reported_model', 'response_sha256', 'provenance'))
    if receipt['reported_model'] != MODEL or receipt['provenance'] not in ('synthetic_fixture', 'owner_imported_reply_authenticity_unverified'):
        raise ValueError('Unsupported provider receipt')
    if not isinstance(receipt['response_sha256'], str) or len(receipt['response_sha256']) != 64 or any(c not in '0123456789abcdef' for c in receipt['response_sha256']):
        raise ValueError('Malformed response fingerprint')
    if phase == 'selection':
        args = {} if proposal['check'] == 'endpoint_coverage' else {'metric': proposal['metric']}
        out = study.transition(state, {'type': 'decide', 'payload': {'check': proposal['check'], 'arguments': args, 'policy': 'muse_validated'}})
        out['cycles'][-1]['decision']['provider_receipt'] = deepcopy(receipt)
        out['cycles'][-1]['decision']['provider_citations'] = proposal['citations']
    else:
        out = study.transition(state, {'type': 'reassess', 'payload': {}})
        out['cycles'][-1]['assessment']['provider_receipt'] = deepcopy(receipt)
    return out


def synthetic_reply(state, phase):
    prepare(state, phase)
    if phase == 'selection':
        proposal = {'check': 'endpoint_coverage', 'metric': None, 'rationale_code': 'audit_target_before_comparison', 'citations': ['S_PSR1_2023', 'S_OVERPLUS_2024']}
    else:
        result = study.assessment(state, state['cycles'][-1]['result'])
        proposal = {'outcome': result['outcome'], 'next_action': result['next_action'], 'result_id': state['cycles'][-1]['result']['id'], 'citations': ['S_PSR1_2023', 'S_OVERPLUS_2024']}
    return {'model': MODEL, 'status': 'completed', 'traitweaver_synthetic': True,
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': study.canonical(proposal)}]}]}


def receipt_usage(value):
    """Admit numeric billing fields only, never arbitrary provider metadata."""
    if not isinstance(value, dict):
        return None
    def number(v):
        return type(v) is int and 0 <= v <= 1_000_000_000
    out = {k: value[k] for k in ('input_tokens', 'output_tokens', 'total_tokens')
           if number(value.get(k))}
    for group, field in (('input_tokens_details', 'cached_tokens'),
                         ('output_tokens_details', 'reasoning_tokens')):
        detail = value.get(group)
        if isinstance(detail, dict) and number(detail.get(field)):
            out[group] = {field: detail[field]}
    return out


def send_approved(preview, grant, ledger_directory, allow_live=False, opener=None):
    """Owner-operated transport only. No caller in the browser invokes this.

    Reserve each request before accessing a credential or attempting the network.
    Preserve the ledger after timeout/failure; there is no automatic retry.
    """
    if not allow_live:
        raise ValueError('Live transport disabled')
    study.fields(grant, ('destination', 'request_sha256', 'spending_limit_usd', 'allow_live', 'verified_price_usd_per_million'))
    body = preview['body']; request_hash = study.digest(body)
    study.fields(body, ('model', 'store', 'max_output_tokens', 'instructions', 'input', 'text'))
    if (preview['destination'] != DESTINATION or preview['request_sha256'] != request_hash or grant['destination'] != DESTINATION or
        grant['request_sha256'] != request_hash or grant['allow_live'] is not True or body.get('model') != MODEL or body.get('store') is not False or body.get('max_output_tokens') != MAX_TOKENS):
        raise ValueError('Exact destination, request and model approval required')
    cap = grant['spending_limit_usd']
    if type(cap) not in (int, float) or not 0 < cap < float('inf'):
        raise ValueError('A finite positive owner spending limit is required')
    data = study.canonical(body).encode()
    if len(data) > MAX_REQUEST or preview['phase'] not in ('selection', 'reassessment'):
        raise ValueError('Unsupported request size or phase')
    prices = grant['verified_price_usd_per_million']
    study.fields(prices, ('input', 'output'))
    if any(type(v) not in (int, float) or not 0 <= v < float('inf') for v in prices.values()):
        raise ValueError('Owner-verified finite token prices are required')
    # Conservative byte-based token allowance plus framing overhead. Prices
    # must be verified by the owner; this is not an account-wide billing cap.
    maximum_cost = ((len(data)+1024)*prices['input']+MAX_TOKENS*prices['output'])/1_000_000
    if maximum_cost > cap:
        raise ValueError('Conservative token-cost bound exceeds the approved spending limit')
    ledger = Path(ledger_directory)
    if ledger.is_symlink() or not ledger.is_dir() or ledger.resolve() == study.APP_ROOT or study.APP_ROOT in ledger.resolve().parents:
        raise ValueError('Choose an existing external ledger directory')
    reservation = ledger / (request_hash+'.attempt.json')
    try:
        with reservation.open('x') as f:
            json.dump({'request_sha256': request_hash, 'phase': preview['phase'], 'status': 'reserved',
                       'spending_limit_usd': cap, 'conservative_token_cost_bound_usd': maximum_cost,
                       'cost_limit_note': 'Bound relies on owner-verified token prices; not an account-wide limit.'}, f)
    except FileExistsError as exc:
        raise ValueError('Request already attempted; ledger retained, no retry') from exc
    key = os.environ.get('MODEL_API_KEY')
    if not key:
        raise ValueError('Credential unavailable; reservation retained')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(DESTINATION, data=data, headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}, method='POST')
    started = time.monotonic()
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise ValueError('Provider returned a non-success status; body withheld')
            raw = response.read(MAX_RESPONSE+1)
        if len(raw) > MAX_RESPONSE or key.encode() in raw:
            raise ValueError('Unsafe provider response; body withheld')
        parsed = study.decode(raw)
        # JSON escaping must not bypass the wire-byte check. Inspect the decoded
        # canonical envelope before any response-derived value is persisted.
        if not isinstance(parsed, dict) or key in study.canonical(parsed):
            raise ValueError('Unsafe decoded provider response; body withheld')
        if parsed.get('model') != MODEL or parsed.get('status') != 'completed':
            raise ValueError('Provider reply incomplete or model mismatch')
        receipt = {'request_sha256': request_hash, 'status': 'received_unvalidated', 'elapsed_seconds': time.monotonic()-started,
                   'reported_model': MODEL, 'reported_usage': receipt_usage(parsed.get('usage')), 'actual_cost_usd': None,
                   'response_sha256': hashlib.sha256(raw).hexdigest()}
        with (ledger/(request_hash+'.receipt.json')).open('x') as f:
            json.dump(receipt, f, allow_nan=False)
        return parsed, receipt
    except (OSError, urllib.error.URLError, ValueError) as exc:
        # Do not echo server errors, request headers, credentials or raw response.
        raise ValueError('Provider attempt failed or response was rejected; billing may be unknown. Reservation retained.') from None
