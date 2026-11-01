"""Separate, transport-free four-case assistant contract.

Muse may prioritize reviewed proposals, never author unchecked scientific claims
or execute an action. Accepted records expand IDs into exact attributed claims
and three complete action cards. No keys, network, shell or provider transport.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from traitweaver import study, study_store, protein_card

CATALOG = study.APP_ROOT / 'data' / 'assistant-cases.v1.json'
CATALOG_SHA256 = 'df752862c5afd728d7cb288830123380c9305833734d28ec53e5e0fcecd759f7'
MODEL = 'muse-spark-1.3'
DESTINATION = 'https://api.meta.ai/v1/responses'
SCHEMA = 'traitweaver.assistant_review.v1'
PACKAGE = 'traitweaver.assistant_package.v1'
GROUPS = ('supports', 'unknown_or_contradictory', 'withheld')
MAX_BYTES = 256 * 1024
MAX_REQUEST = 48 * 1024
MAX_TOKENS = 1024


def catalog():
    if CATALOG.is_symlink():
        raise ValueError('Assistant catalog must not be a symlink')
    raw = CATALOG.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('Assistant catalog bytes changed; no fallback or retrieval')
    value = study.decode(raw)
    # Do not let a separately refreshed source silently change the admitted case.
    algae = value['cases'][0]
    if algae['sources'] != study.bundle()['sources'] or algae['records'][:-2] != study.bundle()['evidence']:
        raise ValueError('Assistant algae snapshot differs from the admitted source bundle')
    gfp = value['cases'][1]; card = protein_card.build_card()
    if (gfp['sources'] != card['sources'] or gfp['attribution'] != card['attribution'] or
        gfp['records'][1:-2] != card['database_annotations'] + card['model_predictions'] or
        gfp['records'][-2]['value'] != card['unavailable'] or
        gfp['records'][-1]['value'] != card['experimental_evidence'] or
        gfp['records'][0]['value'] != {k:v for k,v in card['identity'].items() if k != 'sequence'}):
        raise ValueError('Assistant GFP snapshot differs from the qualified card')
    study_store.screen_export(value)
    return value


def get_case(case_id):
    if not isinstance(case_id, str):
        raise ValueError('Case ID must be a registered string')
    for case in catalog()['cases']:
        if case['case_id'] == case_id:
            return deepcopy(case)
    raise ValueError('Unknown assistant case; no importer or retrieval is enabled')


def response_schema(case):
    properties = {}
    for group in GROUPS:
        ids = [c['id'] for c in case['claims'] if c['category'] == group]
        properties[group] = {'type':'array', 'items':{'type':'string','enum':ids},
                             'minItems':len(ids), 'maxItems':len(ids)}
    properties['prioritized_action_ids'] = {'type':'array','items':{
        'type':'string','enum':[a['id'] for a in case['actions']]},'minItems':3,'maxItems':3}
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def prepare(case_id):
    """Prepare a screened candidate only. No live sending entry point exists."""
    case = get_case(case_id)
    body = {'model':MODEL, 'store':False, 'max_output_tokens':MAX_TOKENS,
        'instructions': 'Review only this supplied public/synthetic case. Return all required claim IDs in their original categories and exactly three unique action IDs in priority order. Each action expands locally to the supplied task, why, required input, expected deliverable, completion check, readiness and citations. You may prioritize but cannot rewrite claims, roles, limits, actions or readiness, omit unknowns/withheld conclusions, infer a winner, invent measurements/structures/analyses, or execute tools. Use only the structured format. This is a visible open-evidence software evaluation, not a hidden benchmark.',
        'input':study.canonical(case), 'text':{'format':{'type':'json_schema',
        'name':'traitweaver_assistant_v1','strict':True,'schema':response_schema(case)}}}
    study_store.screen_export(body)
    if len(study.canonical(body).encode()) > MAX_REQUEST:
        raise ValueError('Assistant request exceeds byte limit; nothing truncated or sent')
    return {'schema_version':'traitweaver.assistant_request.v1','case_id':case_id,
        'case_sha256':study.digest(case),'destination':DESTINATION,'body':body,
        'request_sha256':study.digest(body),'status':'not_sent','live_transport_available':False,
        'approval':'No current or historical approval is inherited by this request.'}


def validate_proposal(case_id, proposal):
    case = get_case(case_id)
    study.fields(proposal, (*GROUPS, 'prioritized_action_ids'))
    for group in (*GROUPS, 'prioritized_action_ids'):
        ids = proposal[group]
        expected = ([a['id'] for a in case['actions']] if group == 'prioritized_action_ids' else
                    [c['id'] for c in case['claims'] if c['category'] == group])
        if (not isinstance(ids, list) or any(not isinstance(i,str) for i in ids) or
            len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected)):
            raise ValueError('Missing, duplicate, unknown or wrongly categorized assistant IDs')
    return deepcopy(proposal)


def synthetic_reply(case_id):
    case = get_case(case_id)
    proposal = {g:[c['id'] for c in case['claims'] if c['category'] == g] for g in GROUPS}
    proposal['prioritized_action_ids'] = [a['id'] for a in case['actions']]
    return {'model':MODEL,'status':'completed','traitweaver_synthetic':True,
        'output':[{'type':'message','content':[{'type':'output_text','text':study.canonical(proposal)}]}]}


def _usage(value):
    if value is None:
        return None
    if not isinstance(value,dict) or not value or set(value) - {'input_tokens','output_tokens','total_tokens'}:
        raise ValueError('Unsupported assistant usage fields')
    if any(type(v) is not int or not 0 <= v <= 1_000_000_000 for v in value.values()):
        raise ValueError('Assistant usage must be bounded nonnegative integer counts')
    if set(value) == {'input_tokens','output_tokens','total_tokens'} and value['total_tokens'] != value['input_tokens']+value['output_tokens']:
        raise ValueError('Inconsistent assistant usage totals')
    return deepcopy(value)


def _expanded(case, proposal, receipt):
    claims = {c['id']:c for c in case['claims']}; actions = {a['id']:a for a in case['actions']}
    return {'schema_version':SCHEMA,'case_id':case['case_id'],'case_sha256':study.digest(case),
        'request_sha256':prepare(case['case_id'])['request_sha256'],'proposal':deepcopy(proposal),
        'claims':{g:[deepcopy(claims[i]) for i in proposal[g]] for g in GROUPS},
        'actions':[dict(priority=n,**deepcopy(actions[i])) for n,i in enumerate(proposal['prioritized_action_ids'],1)],
        'limits':deepcopy(case['limits']), 'receipt':deepcopy(receipt),
        'execution':'Read-only proposal review. No action, tool or provider request was executed by this contract.'}


def parse_reply(case_id, raw, request_sha256):
    preview = prepare(case_id)
    if request_sha256 != preview['request_sha256']:
        raise ValueError('Stale or altered assistant request identity')
    if not isinstance(raw,bytes) or len(raw) > MAX_BYTES:
        raise ValueError('Expected bounded provider reply bytes')
    reply = study.decode(raw)
    if not isinstance(reply,dict) or reply.get('model') != MODEL or reply.get('status') != 'completed':
        raise ValueError('Wrong model, refusal or incomplete assistant reply')
    if 'traitweaver_synthetic' in reply and type(reply['traitweaver_synthetic']) is not bool:
        raise ValueError('Invalid synthetic marker')
    outputs = reply.get('output')
    if not isinstance(outputs,list):
        raise ValueError('Expected typed assistant output')
    texts = []
    for item in outputs:
        if not isinstance(item,dict):
            raise ValueError('Malformed assistant output')
        if item.get('type') == 'reasoning':
            continue  # Never retain provider reasoning or summaries.
        if item.get('type') != 'message' or not isinstance(item.get('content'),list):
            raise ValueError('Assistant tool calls and unknown output items are forbidden')
        for block in item['content']:
            if not isinstance(block,dict) or block.get('type') != 'output_text' or not isinstance(block.get('text'),str):
                raise ValueError('Refusal or unsupported assistant content')
            texts.append(block['text'])
    if len(texts) != 1:
        raise ValueError('Expected exactly one structured assistant response')
    proposal = validate_proposal(case_id,study.decode(texts[0].encode()))
    synthetic = reply.get('traitweaver_synthetic',False)
    receipt = {'reported_model':MODEL,'response_sha256':hashlib.sha256(raw).hexdigest(),
        'provenance':'synthetic_fixture' if synthetic else 'owner_imported_reply_authenticity_unverified',
        'reported_usage':_usage(reply.get('usage')), 'billing_verified':False}
    record = _expanded(get_case(case_id),proposal,receipt)
    validate_record(record)
    return record


def validate_record(record):
    if not isinstance(record,dict):
        raise ValueError('Assistant record must be an object')
    case = get_case(record.get('case_id'))
    proposal = validate_proposal(case['case_id'],record.get('proposal'))
    receipt = record.get('receipt')
    study.fields(receipt,('reported_model','response_sha256','provenance','reported_usage','billing_verified'))
    fingerprint = receipt['response_sha256']
    if (receipt['reported_model'] != MODEL or receipt['billing_verified'] is not False or
        receipt['provenance'] not in ('synthetic_fixture','owner_imported_reply_authenticity_unverified') or
        not isinstance(fingerprint,str) or len(fingerprint) != 64 or
        any(c not in '0123456789abcdef' for c in fingerprint)):
        raise ValueError('Unsupported assistant receipt')
    _usage(receipt['reported_usage'])
    if study.canonical(record) != study.canonical(_expanded(case,proposal,receipt)):
        raise ValueError('Assistant claims/actions/roles/arguments differ from the admitted contract')
    study_store.screen_export(record)
    return deepcopy(record)


def package(record):
    record = validate_record(record)
    value = {'schema_version':PACKAGE,'catalog_sha256':CATALOG_SHA256,
        'case':get_case(record['case_id']),'accepted_review':record,
        'limits':'Public/synthetic bounded proposals; not biological validation, an execution receipt or independent provider authentication.'}
    value['sha256'] = study.digest(value)
    study_store.screen_export(value)
    return value


def validate_package(value):
    if not isinstance(value,dict) or not isinstance(value.get('accepted_review'),dict):
        raise ValueError('Malformed assistant package')
    record = validate_record(value['accepted_review'])
    if study.canonical(value) != study.canonical(package(record)):
        raise ValueError('Corrupt or altered assistant package')
    return deepcopy(record)


def reopen(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Assistant package must not be a symlink')
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Assistant package exceeds byte limit')
    return validate_package(study.decode(raw))


def readable(record):
    record = validate_record(record)
    case = get_case(record['case_id'])
    lines = ['Traitweaver — three-action assistant review', 'Schema: '+SCHEMA,
        'Case: '+case['case_id'], 'Input: '+case['input_kind'],
        'PROVENANCE: '+record['receipt']['provenance'], record['execution'],
        'Claims and actions are authored bounded records; Muse can prioritize the eligible actions.',
        'Reported usage: '+study.canonical(record['receipt']['reported_usage']),
        'Provider billing/authenticity not independently verified.', '']
    for group in GROUPS:
        lines.append(group)
        for claim in record['claims'][group]:
            lines += [study.canonical(claim)]
    lines += ['', 'Three prioritized proposals']
    for action in record['actions']:
        lines += [study.canonical(action)]
    lines += ['', 'Limitations', *record['limits'], '', 'Case/source records (zero and null preserved)',
        study.canonical(case), '', 'Accepted identity and receipt',
        'Case SHA-256: '+record['case_sha256'], 'Request SHA-256: '+record['request_sha256'],
        study.canonical(record['receipt'])]
    return '\n'.join(lines)+'\n'


def export_bundle(record, destination):
    """Publish a complete directory atomically; never overwrite saved work."""
    import os
    import tempfile
    import shutil
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise ValueError('Choose a fresh assistant export directory')
    resolved = target.resolve()
    if resolved == study.APP_ROOT or study.APP_ROOT in resolved.parents:
        raise ValueError('Assistant exports must be outside the application')
    aliases = {Path('/tmp'):Path('/private/tmp'),Path('/var'):Path('/private/var')}
    if any(p.is_symlink() and not (p in aliases and p.resolve()==aliases[p]) for p in (target.absolute(),*target.absolute().parents)):
        raise ValueError('Assistant export path must not use symlinks')
    payloads = {'assistant-review.json':study.canonical(package(record))+'\n',
                'assistant-review.txt':readable(record)}
    pending = Path(tempfile.mkdtemp(prefix='.assistant-pending-',dir=target.parent))
    try:
        for name,text in payloads.items():
            with (pending/name).open('x',encoding='utf-8') as handle:
                handle.write(text); handle.flush(); os.fsync(handle.fileno())
        # Recheck before rename; existing nonempty exports cannot be replaced.
        if target.exists() or target.is_symlink():
            raise ValueError('Assistant export destination appeared during save')
        os.rename(pending,target)
    finally:
        if pending.exists():
            shutil.rmtree(pending)
    return target
