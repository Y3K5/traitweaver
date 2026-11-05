"""Read-only research replies from explicit local receipts. No provider transport.

Only named evidence artifacts are admitted. Keys, launchers and control files
are never read. The exact request and response remain inspectable, while the
workspace independently checks their bindings and accounting.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

from traitweaver import study, trait_library as library

SCHEMA = 'traitweaver.saved_research_reply.v1'
REQUIRED = {'EXACT_REQUEST_BODY.json', 'RESPONSE_BODY.json', 'USAGE_LEDGER.json', 'LOCAL_VALIDATION.json'}
OPTIONAL = {'SOURCE_CHECKS.json'}
LIMIT = 512 * 1024


def fingerprint(text):
    return sha256(text.encode('utf-8')).hexdigest()


def output_text(reply):
    texts = []
    for item in reply.get('output', []):
        if type(item) is dict and item.get('type') == 'message':
            for part in item.get('content', []):
                if type(part) is dict and part.get('type') == 'output_text' and type(part.get('text')) is str:
                    texts.append(part['text'])
    return '\n'.join(texts)


def amount(value):
    try:
        if type(value) is not str:
            raise ValueError('Amount must be a decimal string')
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise ValueError('Invalid amount')
        return result
    except InvalidOperation:
        raise ValueError('Invalid amount') from None


def validate(package, packet=None):
    library.fields(package, ('schema_version', 'run_id', 'artifacts'))
    if package['schema_version'] != SCHEMA or type(package['artifacts']) is not dict:
        raise ValueError('Unknown saved research reply')
    files = package['artifacts']
    if not REQUIRED <= set(files) or not set(files) <= REQUIRED | OPTIONAL:
        raise ValueError('Only named request, response, usage and review evidence is admitted')
    decoded = {}
    for name, artifact in files.items():
        library.fields(artifact, ('text', 'sha256'))
        if type(artifact['text']) is not str or len(artifact['text'].encode()) > LIMIT or fingerprint(artifact['text']) != artifact['sha256']:
            raise ValueError('Saved artifact fingerprint changed')
        decoded[name] = study.decode(artifact['text'])
    if len(study.canonical(package).encode()) > library.MAX_BYTES // 3:
        raise ValueError('Saved research reply too large')
    if library.privacy([{'event': package}])['findings']:
        raise ValueError('Saved reply has privacy findings; nothing was removed or imported')
    body, reply, ledger, local = (decoded[n] for n in ('EXACT_REQUEST_BODY.json', 'RESPONSE_BODY.json', 'USAGE_LEDGER.json', 'LOCAL_VALIDATION.json'))
    if not all(type(x) is dict for x in (body, reply, ledger, local)):
        raise ValueError('Invalid saved reply shape')
    req_hash = files['EXACT_REQUEST_BODY.json']['sha256']
    response_hash = files['RESPONSE_BODY.json']['sha256']
    if ledger.get('request_sha256') != req_hash or ledger.get('response_sha256') != response_hash:
        raise ValueError('Request/response receipt binding changed')
    if packet is not None and (body != packet['body'] or req_hash != packet['request_sha256']):
        raise ValueError('This reply does not belong to the saved evidence pack')
    if body.get('model') != library.MODEL or body.get('store') is not False or body.get('max_output_tokens') != 8192 or set(body) != {'model', 'store', 'max_output_tokens', 'instructions', 'input'}:
        raise ValueError('Unrecognized request contract')
    context = study.decode(body['input'])
    if ledger.get('provider') != 'Meta direct' or ledger.get('model') != body['model'] or ledger.get('attempt_number') != 1 or ledger.get('retry_allowed') is not False:
        raise ValueError('Provider identity or attempt boundary changed')
    synthetic = ledger.get('synthetic')
    if type(synthetic) is not bool or ledger.get('provenance') != ('synthetic_transport_test' if synthetic else 'actual_direct_meta_attempt'):
        raise ValueError('Synthetic and actual receipts must stay distinct')
    started = datetime.fromisoformat(ledger['started_utc'])
    finished = datetime.fromisoformat(ledger['finished_utc'])
    if started.tzinfo is None or finished.tzinfo is None or finished < started:
        raise ValueError('Invalid attempt timestamps')
    run_id = 'reply-' + study.digest({'request': req_hash, 'response': response_hash, 'started': ledger['started_utc']})[:20]
    if package['run_id'] != run_id:
        raise ValueError('Saved reply identity changed')
    status = ledger.get('http_status')
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError('HTTP receipt required for this import contract')
    if ledger.get('scientific_review') != 'pending' or ledger.get('reviewer_decision') is not None or local.get('scientific_review') != 'pending' or local.get('laboratory_ready') is not False:
        raise ValueError('A saved reply cannot grant scientific approval')
    usage = reply.get('usage')
    if usage != ledger.get('reported_usage'):
        raise ValueError('Usage differs from the original response')
    cost = None
    if usage is not None:
        if type(usage) is not dict or any(type(usage.get(k)) is not int or not 0 <= usage[k] <= 1000000000 for k in ('input_tokens', 'output_tokens')):
            raise ValueError('Invalid reported usage')
        if usage.get('total_tokens', usage['input_tokens'] + usage['output_tokens']) != usage['input_tokens'] + usage['output_tokens']:
            raise ValueError('Inconsistent usage total')
        cached = usage.get('input_tokens_details', {}).get('cached_tokens', 0)
        reasoning = usage.get('output_tokens_details', {}).get('reasoning_tokens', 0)
        if type(cached) is not int or not 0 <= cached <= usage['input_tokens'] or type(reasoning) is not int or not 0 <= reasoning <= usage['output_tokens']:
            raise ValueError('Inconsistent cached/reasoning usage')
        cost = ((Decimal(usage['input_tokens'] - cached) * Decimal('1.25')) + Decimal(cached) * Decimal('0.15') + Decimal(usage['output_tokens']) * Decimal('4.25')) / 1000000
        if ledger.get('token_derived_cost_usd') is None or amount(ledger['token_derived_cost_usd']) != cost:
            raise ValueError('Token cost differs from reported usage and pinned prices')
    elif ledger.get('token_derived_cost_usd') is not None:
        raise ValueError('Missing usage cannot become a known cost')
    if ledger.get('provider_settled_charge_usd') is not None:
        raise ValueError('This contract has no independent billing settlement evidence')
    budget = amount(ledger['local_budget_usd'])
    reservation = amount(ledger['unsettled_reservation_usd'])
    if usage is None and reservation <= 0:
        raise ValueError('Missing usage must retain its unsettled reservation')
    text = output_text(reply)
    answer = None
    suggestions = []
    success = status == 200 and reply.get('status') == 'completed'
    if success:
        if reply.get('model') != body['model'] or not text:
            raise ValueError('Completed response must identify its model and output')
        cleaned = text.strip()
        if cleaned.startswith('```') and cleaned.endswith('```'):
            cleaned = '\n'.join(cleaned.splitlines()[1:-1])
        answer = study.decode(cleaned)
        suggestions = answer if type(answer) is list else answer.get('suggestions', [answer]) if type(answer) is dict else None
        if type(suggestions) is not list or not 1 <= len(suggestions) <= 40:
            raise ValueError('No inspectable suggestion list')
        claims, sources = {c['id'] for c in context['claims']}, {s['id'] for s in context['sources']}
        for row in suggestions:
            if type(row) is not dict or not {'claim_ids', 'gap', 'proposed_check'} <= set(row):
                raise ValueError('Suggestion fields missing')
            for field, allowed in (('claim_ids', claims), ('source_ids', sources)):
                ids = row.get(field, [])
                if type(ids) is not list or any(type(i) is not str or i not in allowed for i in ids) or (field == 'claim_ids' and not ids):
                    raise ValueError('Unknown suggestion citation')
            for field in ('gap', 'proposed_check'):
                library.text(row[field], 8000)
        if local.get('suggestions') != suggestions or local.get('status') != 'structure_checked_human_review_pending':
            raise ValueError('Saved local result disagrees with the original response')
    elif suggestions or local.get('suggestions') not in (None, []):
        raise ValueError('A failed attempt cannot acquire model suggestions')
    source_checks = decoded.get('SOURCE_CHECKS.json')
    if 'SOURCE_CHECKS.json' in decoded:
        if type(source_checks) is not dict:
            raise ValueError('Invalid source review shape')
        if source_checks.get('request_sha256') != req_hash or source_checks.get('response_sha256') != response_hash or source_checks.get('scientific_review') != 'pending' or source_checks.get('laboratory_ready') is not False:
            raise ValueError('Source review binding or role changed')
        library.text(source_checks.get('authorship'))
        findings = source_checks.get('findings')
        if type(findings) is not list:
            raise ValueError('Source review findings must be a list')
        sources = {s['id'] for s in context['sources']}
        for finding in findings:
            if type(finding) is not dict:
                raise ValueError('Invalid source review finding')
            library.text(finding.get('status'))
            library.text(finding.get('finding'), 8000)
            ids = finding.get('source_ids', [])
            if type(ids) is not list or any(type(i) is not str or i not in sources for i in ids):
                raise ValueError('Unknown source review citation')
    error = reply.get('error') if type(reply.get('error')) is dict else {}
    return {'run_id': run_id, 'provider': 'Meta direct', 'model': body['model'], 'synthetic': synthetic,
            'outcome': 'completed' if success else 'failed', 'http_status': status,
            'error_code': error.get('code'), 'started_utc': ledger['started_utc'], 'finished_utc': ledger['finished_utc'],
            'request_sha256': req_hash, 'response_sha256': response_hash,
            'context': context, 'body': body, 'output_text': text, 'answer': answer,
            'suggestions': suggestions, 'source_checks': source_checks, 'usage': usage,
            'cost_usd': str(cost) if cost is not None else None, 'budget_usd': str(budget),
            'unsettled_reservation_usd': str(reservation), 'settled_charge_usd': None,
            'cost_basis': 'Pinned Standard prices: $1.25/M input, $0.15/M cached input, $4.25/M output. Reasoning is already inside output.',
            'authenticity_basis': 'Imported local request, response and usage receipts; not a provider-signed attestation.',
            'scientific_review': 'pending', 'laboratory_ready': False}


def from_directory(directory):
    """Prepare an import from an explicitly chosen external directory only."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir() or root.resolve() == study.APP_ROOT or study.APP_ROOT in root.resolve().parents:
        raise ValueError('Select an external saved run directory')
    artifacts = {}
    for name in sorted(REQUIRED | OPTIONAL):
        p = root / name
        if not p.exists() and name in OPTIONAL:
            continue
        if p.is_symlink() or not p.is_file() or p.stat().st_size > LIMIT:
            raise ValueError('Missing or unsafe evidence artifact')
        text = p.read_bytes().decode('utf-8')
        artifacts[name] = {'text': text, 'sha256': fingerprint(text)}
    ledger = study.decode(artifacts['USAGE_LEDGER.json']['text'])
    identity = {'request': artifacts['EXACT_REQUEST_BODY.json']['sha256'],
                'response': artifacts['RESPONSE_BODY.json']['sha256'], 'started': ledger['started_utc']}
    package = {'schema_version': SCHEMA, 'run_id': 'reply-' + study.digest(identity)[:20], 'artifacts': artifacts}
    validate(package)
    return deepcopy(package)
