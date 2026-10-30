"""Prepare, approve separately, run once, and monitor one bounded public cycle.

Preparation/status are local only. `run` requires both --send and an exact
owner-approved manifest hash; no credential is read during preparation/status.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

TOOL_ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('muse_safe_diagnostics', TOOL_ROOT/'muse_diagnostics.py')
diagnostics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnostics)


class CycleStopped(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Cycle stopped; safe failure record available; no retry permitted')

TOTAL_CAP = Decimal('0.05')
INPUT_PRICE = Decimal('1.25')
OUTPUT_PRICE = Decimal('4.25')
PRICE_SOURCE = 'https://dev.meta.ai/docs/pricing-rate-limits'
PRICE_CHECKED = '2026-10-29'
CODE_FILES = ('src/traitweaver/study.py', 'src/traitweaver/study_store.py', 'src/traitweaver/muse_boundary.py', 'data/algae-public.v1.json')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return sha(canonical(value).encode())


def load(path):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError('Duplicate JSON field')
            out[key] = value
        return out
    def invalid(_):
        raise ValueError('Nonfinite JSON')
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 4*1024*1024:
        raise ValueError('Unsafe or oversized local control file')
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid local JSON') from exc


def atomic(path, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n').encode()
    pending = path.with_name('.'+path.name+'.pending')
    try:
        with pending.open('xb') as f:
            os.chmod(pending, 0o600); f.write(raw); f.flush(); os.fsync(f.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def configure(app):
    app = Path(app).resolve()
    for name in CODE_FILES:
        if not (app/name).is_file() or (app/name).is_symlink():
            raise ValueError('Selected application source is unavailable or unsafe')
    for name in ('study', 'study_store', 'muse_boundary'):
        existing = sys.modules.get('traitweaver.'+name)
        if existing and Path(existing.__file__).resolve() != app/'src/traitweaver'/ (name+'.py'):
            raise ValueError('Another Traitweaver checkout is already loaded; use a fresh process')
    sys.path.insert(0, str(app/'src'))
    return tuple(importlib.import_module('traitweaver.'+name) for name in ('study', 'study_store', 'muse_boundary'))


def bound(size):
    return ((Decimal(size)+1024)*INPUT_PRICE+1024*OUTPUT_PRICE)/1_000_000


def screen(raw):
    # Inspect only the intended public payloads; never scan credential stores.
    patterns = (r'/Users/|/home/|\$HOME',
                r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}',
                r'(?i)set-cookie\s*:|authorization\s*:',
                r'study_case\.json|raw_chat|response_cookies')
    if any(re.search(pattern, raw.decode()) for pattern in patterns):
        raise ValueError('Public-payload privacy screen requires owner review; no content was removed')


def event(packet, status, **values):
    state = load(packet/'STATUS.json') if (packet/'STATUS.json').exists() else {}
    now = datetime.now(timezone.utc).isoformat()
    if status == 'starting':
        state['blocker'] = None
        state['failure'] = None
    state.update(values); state.update(status=status, updated_utc=now)
    record = {'time_utc': now, 'status': status, **values}
    with (packet/'EVENTS.jsonl').open('a', encoding='utf-8') as f:
        os.chmod(packet/'EVENTS.jsonl', 0o600)
        f.write(canonical(record)+'\n'); f.flush(); os.fsync(f.fileno())
    atomic(packet/'STATUS.json', state)
    contents = '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
    contents += '<title>Traitweaver cycle monitor</title><style>body{font:16px/1.6 system-ui;max-width:950px;margin:40px auto;padding:0 24px;color:#243d47}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2ef;padding:24px}h1{font-size:28px}</style>'
    contents += '<h1>Traitweaver · '+html.escape(status.replace('_',' '))+'</h1><p>Local monitor snapshot. Refresh to see the latest state. This page makes no network requests.</p><pre>'+html.escape(json.dumps(state, indent=2))+'</pre>'
    (packet/'MONITOR.html').write_text(contents)
    return state


def prepare(app, directory, previous=None):
    study, store_module, muse = configure(app)
    target = Path(directory)
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError('Choose a fresh approval-packet directory with an existing parent')
    initial = study.initial_state()  # Never read the owner's edited/saved study.
    previews = {'selection': muse.prepare(initial, 'selection')}
    branch_states = {}
    for choice in study.eligible_checks(initial):
        branch = 'coverage' if choice['id']=='endpoint_coverage' else choice['arguments']['metric']
        decision = study.transition(initial, {'type': 'decide', 'payload': {'check': choice['id'], 'arguments': choice['arguments'], 'policy': 'muse_validated'}})
        after_result = study.transition(decision, {'type': 'run', 'payload': {}})
        previews[branch] = muse.prepare(after_result, 'reassessment')
        branch_states[branch] = after_result
    entries = []
    for branch, preview in previews.items():
        raw = canonical(preview['body']).encode(); screen(raw)
        entries.append({'branch': branch, 'phase': preview['phase'], 'file': '01-selection.json' if branch=='selection' else '02-reassessment-'+branch+'.json',
                        'sha256': sha(raw), 'bytes': len(raw), 'input_token_allowance': len(raw)+1024,
                        'max_output_tokens': 1024, 'conservative_token_cost_usd': str(bound(len(raw)))})
    maximum = bound(entries[0]['bytes'])+max(bound(e['bytes']) for e in entries[1:])
    if maximum > TOTAL_CAP:
        raise ValueError('Prepared cycle exceeds the proposed total ceiling')
    prior = None
    if previous is not None:
        old = load(Path(previous)/'PUBLIC_CYCLE.json'); status_record = load(Path(previous)/'STATUS.json')
        if not (Path(previous)/'CYCLE.started').is_file() or status_record['status'] != 'stopped_requires_review':
            raise ValueError('Prior attempt must remain stopped and locked')
        held = Decimal(status_record['reserved_upper_bound_usd'])
        if not held.is_finite() or held < 0 or held > TOTAL_CAP:
            raise ValueError('Invalid prior reservation')
        prior = {'approval_sha256': old['approval_sha256'], 'requests_started': status_record['requests_started'],
                 'requests_completed': status_record['requests_completed'], 'reserved_upper_bound_usd': str(held),
                 'actual_charge_usd': None, 'usage_unverified': True,
                 'note': 'Prior attempt stays locked. New approval is a separate attempt, not a retry within that cycle.',
                 'combined_prior_reservation_plus_new_ceiling_usd': str(held+TOTAL_CAP)}
    plan = {'schema_version': 'traitweaver.one_muse_cycle.v2', 'cycle_id': 'public-algae-cycle-002' if prior else 'public-algae-cycle-001',
            'method': 'POST', 'destination': muse.DESTINATION, 'model': muse.MODEL, 'mode': 'Standard', 'store': False,
            'source_bundle_sha256': study.BUNDLE_HASH, 'initial_state_sha256': fingerprint(initial),
            'max_requests': 2, 'max_output_tokens_per_request': 1024, 'maximum_authorized_spend_usd': str(TOTAL_CAP),
            'conservative_largest_pair_usd': str(maximum),
            'pricing': {'source': PRICE_SOURCE, 'checked_date': PRICE_CHECKED, 'input_usd_per_million': str(INPUT_PRICE), 'output_usd_per_million': str(OUTPUT_PRICE),
                        'note': 'Uncached input price used throughout. Output cap includes reasoning and visible tokens. No search/tools surcharge is enabled.'},
            'requests': entries, 'flow': 'Selection request; validate choice; save pre-result decision; execute one local check; send exactly the matching preapproved reassessment body; validate and stop.',
            'dry_run_note': 'Follow-up bodies enumerate all three possible allowed checks using local public-data arithmetic only. No provider response or live research receipt exists yet.',
            'stop_rules': ['No automatic retries, redirects, provider/model fallback or additional requests', 'Stop before reassessment on selection rejection, refusal, timeout, missing usage or mismatched body hash',
                           'Reserve the full per-request bound before dispatch; uncertain charges stay reserved', 'Stop if observed token counts exceed the conservative allowance or remaining budget',
                           'No third request, even if the response is incomplete or the cycle fails'],
            'billing_limit': 'Application authorization ceiling based on documented token prices and conservative input allowance. Not a provider-enforced account-wide cap; actual invoice/credit balance is not verified.'}
    plan['previous_attempt'] = prior
    plan['diagnostics_policy'] = 'Retain failure stage, HTTP status, exact allowlisted provider code/parameter, numeric usage and bounded timing. Never retain provider messages, arbitrary headers, raw bodies, exception strings or credentials. No redirects, inherited proxies, retries or fallback.'
    code_hashes = {name: sha((Path(app)/name).read_bytes()) for name in CODE_FILES}
    execution = {'code_sha256': code_hashes, 'runner_sha256': sha(Path(__file__).read_bytes()),
                 'diagnostics_sha256': sha((TOOL_ROOT/'muse_diagnostics.py').read_bytes()),
                 'starter_sha256': sha((TOOL_ROOT/'muse_cycle_start.py').read_bytes())}
    plan['execution_sha256'] = fingerprint(execution)
    plan['approval_sha256'] = fingerprint(plan)
    target.mkdir(); os.chmod(target, 0o700)
    for entry in entries:
        (target/entry['file']).write_bytes(canonical(previews[entry['branch']]['body']).encode())
    atomic(target/'PUBLIC_CYCLE.json', plan)
    atomic(target/'PUBLIC_INITIAL_STATE.json', initial)
    for branch, state in branch_states.items():
        atomic(target/('DRY_RUN-'+branch+'.json'), {'status': 'dry_run_only_not_a_provider_run', 'state': state})
    atomic(target/'LOCAL_CONTROL.json', {'app_dir': str(Path(app).resolve()), **execution, 'not_sent': True})
    (target/'START_APPROVED_CYCLE.py').write_bytes((TOOL_ROOT/'muse_cycle_start.py').read_bytes())
    for name in ('muse_cycle.py','muse_diagnostics.py','muse_cycle_start.py'):
        (target/name).write_bytes((TOOL_ROOT/name).read_bytes())
    atomic(target/'APPROVAL_DRAFT.json', {'approved': False, 'approval_sha256': plan['approval_sha256'],
                                         'destination': muse.DESTINATION, 'model': muse.MODEL,
                                         'maximum_spend_usd': str(TOTAL_CAP), 'max_requests': 2})
    pieces = ['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
              '<title>Approve one Traitweaver Muse cycle</title><style>body{font:16px/1.6 system-ui;color:#243d47;max-width:1080px;margin:40px auto;padding:0 24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2ef;padding:20px}summary{cursor:pointer;padding:12px 0}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #d8e2df}code{overflow-wrap:anywhere}</style>',
              '<h1>One public algae research cycle · awaiting approval</h1><p>Nothing has been sent. Credentials have not been read.</p>',
              '<p><b>Destination:</b> POST '+html.escape(muse.DESTINATION)+'<br><b>Model:</b> '+muse.MODEL+' · Standard<br><b>Maximum approval:</b> $0.05 total · at most two requests · no retries.</p>',
              '<p><b>Question:</b> '+html.escape(initial['brief']['question'])+'</p>',
              '<p>Public inputs: eight growth/uptake summary records and two qualitative observations from the two cited algae papers; source controls, uncertainty and claim limits. No saved owner notes, private example, GFP, repository code, raw chat, credential or local path is sent.</p>',
              '<p>Request one selects an allowed check. Exactly one of the three possible request-two bodies can follow. The independent requests carry public evidence/result context; no hidden model reasoning or conversation history is forwarded.</p>',
              '<p>The reassessment is constrained to result-compatible interpretation codes. This is a bounded evidence-use/control-flow exercise, not independent scientific validation or discovery.</p>',
              '<p><b>Bundle approval SHA-256:</b> <code>'+plan['approval_sha256']+'</code></p>', '<h2>Every permitted request</h2>']
    if prior:
        pieces += ['<p><b>Previous attempt:</b> one stopped selection attempt; no accepted response or usage. Its $'+prior['reserved_upper_bound_usd']+' reservation remains unresolved. This new $0.05 ceiling is additional: combined prior reservation plus new ceiling $'+prior['combined_prior_reservation_plus_new_ceiling_usd']+'. This packet is not yet approved.</p>']
    for entry in entries:
        body = previews[entry['branch']]['body']; decoded_body = dict(body); decoded_body['input'] = json.loads(body['input'])
        pieces += ['<h3>'+html.escape(entry['file'])+'</h3><p>'+str(entry['bytes'])+' exact UTF-8 body bytes · conservative bound $'+entry['conservative_token_cost_usd']+'<br>SHA-256: <code>'+entry['sha256']+'</code></p>',
                   '<details><summary>Read the entire payload with input decoded for readability</summary><pre>'+html.escape(json.dumps(decoded_body, indent=2, ensure_ascii=False))+'</pre></details>',
                   '<details><summary>Exact canonical HTTP body bytes (also in the named JSON file)</summary><pre>'+html.escape(canonical(body))+'</pre></details>']
    pieces += ['<h2>Monitoring and stopping</h2><p>STATUS.json and MONITOR.html show stage, elapsed time, request count, selected branch, reserved budget, returned usage and conservative token-charge estimate. EVENTS.jsonl is append-only. Successful completion preserves a study package and typed accepted replies; raw responses, cookies and auth headers are excluded.</p>',
               '<p>Failures write FAILURE-selection.json or FAILURE-reassessment.json and show stage, HTTP status, allowlisted provider code/parameter and numeric usage when available. Raw error messages, response bodies, cookies, auth headers and exception strings are not retained. The terminal starter prints the safe failure summary.</p>',
               '<p>Timeouts, interrupted processes and missing usage mean billing uncertainty, not zero spend. No retry or follow-up is permitted after those states. Account balance and the provider invoice require an owner dashboard check; the local monitor does not query them.</p>']
    (target/'APPROVAL.html').write_text('\n'.join(pieces))
    event(target, 'awaiting_approval', requests_started=0, requests_completed=0, maximum_spend_usd='0.05',
          reserved_upper_bound_usd='0', observed_token_charge_estimate_usd='0', actual_provider_charge_usd=None,
          billing_state='no_requests_sent', approval_sha256=plan['approval_sha256'])
    return plan


def verify_packet(packet):
    plan = load(packet/'PUBLIC_CYCLE.json'); control = load(packet/'LOCAL_CONTROL.json')
    unsigned = {k:v for k,v in plan.items() if k!='approval_sha256'}
    if plan['approval_sha256'] != fingerprint(unsigned):
        raise ValueError('Approval bundle changed')
    if plan['execution_sha256'] != fingerprint({k:control[k] for k in ('code_sha256','runner_sha256','diagnostics_sha256','starter_sha256')}):
        raise ValueError('Execution pins differ from the approved bundle')
    if sha(Path(__file__).read_bytes()) != control['runner_sha256']:
        raise ValueError('Runner changed after preparation; prepare and review a new bundle')
    if sha((TOOL_ROOT/'muse_diagnostics.py').read_bytes()) != control['diagnostics_sha256']:
        raise ValueError('Diagnostics changed after preparation; review a new bundle')
    if sha((TOOL_ROOT/'muse_cycle_start.py').read_bytes()) != control['starter_sha256'] or sha((packet/'START_APPROVED_CYCLE.py').read_bytes()) != control['starter_sha256']:
        raise ValueError('Local starter changed after preparation; review a new bundle')
    for name,key in (('muse_cycle.py','runner_sha256'),('muse_diagnostics.py','diagnostics_sha256'),('muse_cycle_start.py','starter_sha256')):
        if sha((packet/name).read_bytes()) != control[key]:
            raise ValueError('Copied execution support changed; review a new packet')
    app = Path(control['app_dir'])
    for name, expected in control['code_sha256'].items():
        if sha((app/name).read_bytes()) != expected:
            raise ValueError('Application source or public evidence changed after preparation')
    study, store_module, muse = configure(app)
    if plan['destination'] != muse.DESTINATION or plan['model'] != muse.MODEL or plan['max_requests'] != 2 or Decimal(plan['maximum_authorized_spend_usd']) != TOTAL_CAP:
        raise ValueError('Unsupported cycle authorization')
    initial = load(packet/'PUBLIC_INITIAL_STATE.json')
    if fingerprint(initial) != plan['initial_state_sha256'] or initial != study.initial_state():
        raise ValueError('Initial public study changed')
    for entry in plan['requests']:
        if Path(entry['file']).name != entry['file']:
            raise ValueError('Unsafe payload path')
        raw = (packet/entry['file']).read_bytes(); screen(raw)
        if sha(raw) != entry['sha256'] or len(raw) != entry['bytes'] or raw != canonical(load(packet/entry['file'])).encode():
            raise ValueError('Exact request body changed')
    return plan, (study, store_module, muse)


def usage_estimate(usage, entry):
    if not isinstance(usage, dict):
        raise ValueError('Reported token usage unavailable')
    values = {k:usage.get(k) for k in ('input_tokens','output_tokens')}
    if any(type(v) is not int or v < 0 for v in values.values()):
        raise ValueError('Reported token usage unavailable')
    if values['input_tokens'] > entry['input_token_allowance'] or values['output_tokens'] > 1024:
        raise ValueError('Reported tokens exceed the approved conservative allowance')
    amount = (values['input_tokens']*INPUT_PRICE+values['output_tokens']*OUTPUT_PRICE)/1_000_000
    details = usage.get('output_tokens_details', {})
    reasoning = details.get('reasoning_tokens') if isinstance(details, dict) else None
    return amount, {**values, 'reasoning_tokens': reasoning if type(reasoning) is int and 0 <= reasoning <= values['output_tokens'] else None}


def run(packet, approval_path, allow_live=False, opener=None):
    if not allow_live:
        raise ValueError('Sending disabled: both explicit --send and an exact owner approval are required')
    if opener is None and not sys.stdin.isatty():
        raise ValueError('Live sending requires an interactive owner terminal')
    packet = Path(packet); plan, modules = verify_packet(packet); study, stores, muse = modules
    approval = load(approval_path)
    expected = {'approved': True, 'approval_sha256': plan['approval_sha256'], 'destination': plan['destination'],
                'model': plan['model'], 'maximum_spend_usd': '0.05', 'max_requests': 2}
    if approval != expected:
        raise ValueError('Owner approval must match the exact bundle, destination, model and total ceiling')
    try:
        with (packet/'CYCLE.started').open('x') as f:
            os.chmod(packet/'CYCLE.started',0o600); f.write(plan['approval_sha256']+'\n');f.flush();os.fsync(f.fileno())
    except FileExistsError:
        raise ValueError('This cycle was already started; no retry or automatic resume is permitted') from None
    ledger = packet/'ledger'
    store = None; amount=Decimal('0'); reserved=Decimal('0'); completed=0; started=0
    phase='selection';stage='ledger_create';receipt=None
    try:
        ledger.mkdir()
        stage='monitor_start'
        event(packet,'starting',runner_pid=os.getpid(),transport='fake_test_only' if opener else 'direct_meta_api',billing_state='no_dispatch_yet')
        stage='study_open'
        store=stores.Store(packet/'study')
        for phase in ('selection','reassessment'):
            stage='request_preparation';receipt=None
            verify_packet(packet)
            state=store.current()['state']
            branch='selection' if phase=='selection' else ('coverage' if state['cycles'][-1]['decision']['check']=='endpoint_coverage' else state['cycles'][-1]['decision']['arguments']['metric'])
            entry=next(e for e in plan['requests'] if e['branch']==branch)
            preview=muse.prepare(state,phase)
            if preview['request_sha256']!=entry['sha256'] or canonical(preview['body']).encode()!=(packet/entry['file']).read_bytes():
                raise ValueError('Runtime request differs from the exact preapproved branch')
            request_bound=Decimal(entry['conservative_token_cost_usd'])
            if amount+reserved+request_bound>TOTAL_CAP:
                raise ValueError('Remaining approved budget is insufficient')
            started+=1;reserved+=request_bound
            event(packet,phase+'_in_flight',phase=phase,selected_branch=branch,requests_started=started,requests_completed=completed,
                  request_sha256=entry['sha256'],request_started_utc=datetime.now(timezone.utc).isoformat(),
                  reserved_upper_bound_usd=str(reserved),observed_token_charge_estimate_usd=str(amount),billing_state='charge_pending',request_timeout_seconds=30)
            grant={'destination':plan['destination'],'request_sha256':entry['sha256'],'spending_limit_usd':float(request_bound),
                   'allow_live':True,'verified_price_usd_per_million':{'input':float(INPUT_PRICE),'output':float(OUTPUT_PRICE)}}
            stage='transport'
            response, receipt=diagnostics.send_approved(muse,preview,grant,ledger,allow_live=True,opener=opener)
            raw=canonical(response).encode()
            # Validate before accepting any model choice or executing a local check.
            stage='structured_reply_validation'
            accepted=muse.parse_reply(state,phase,raw,entry['sha256'])
            stage='usage_validation'
            charge,usage=usage_estimate(receipt['reported_usage'],entry)
            response_id=response.get('id')
            if not isinstance(response_id,str) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,160}',response_id):response_id=None
            stage='receipt_save'
            atomic(packet/('RECEIPT-'+phase+'.json'),{'destination':plan['destination'],'phase':phase,'request_sha256':entry['sha256'],
                    'reported_model':response['model'],'provider_response_id':response_id,'http_response_sha256':receipt['response_sha256'],
                    'accepted_response_sha256':accepted['receipt']['response_sha256'],'usage':usage,'elapsed_seconds':receipt['elapsed_seconds'],
                    'estimated_token_charge_usd':str(charge),'actual_provider_charge_usd':None,
                    'source':'fake_transport_for_tests' if opener else 'direct_meta_transport','validation':'accepted'})
            stage='accepted_reply_save'
            store.apply(store.current()['hash'],{'type':'muse_accept','payload':accepted})
            amount+=charge;reserved-=request_bound;completed+=1
            event(packet,phase+'_accepted',requests_completed=completed,reserved_upper_bound_usd=str(reserved),observed_token_charge_estimate_usd=str(amount),
                  usage=usage,provider_response_id=response_id,billing_state='usage_reported_actual_invoice_unverified')
            if phase=='selection':
                stage='local_check'
                store.apply(store.current()['hash'],{'type':'run','payload':{}})
                if store.current()['state']['cycles'][-1]['result']['status']!='completed':
                    raise ValueError('Local check did not complete; no reassessment dispatch permitted')
                event(packet,'local_check_completed',selected_check=store.current()['state']['cycles'][-1]['decision']['check'])
        stage='export'
        atomic(packet/'STUDY_PACKAGE.json',store.export())
        (packet/'STUDY_BRIEF.md').write_text(study.readable(store.current()['state']))
        return event(packet,'complete',requests_started=started,requests_completed=completed,reserved_upper_bound_usd=str(reserved),
                     observed_token_charge_estimate_usd=str(amount),billing_state='usage_reported_actual_invoice_unverified')
    except (Exception, KeyboardInterrupt) as exc:
        # Never include exception text, raw error bodies, auth headers or cookies.
        failure=diagnostics.exception_diagnostic(exc,stage)
        if receipt is not None:
            failure.update(receipt.get('safe_transport',{}))
            failure['elapsed_seconds']=receipt['elapsed_seconds']
        failure.update(phase=phase,request_sha256=entry['sha256'] if 'entry' in locals() else None)
        try:
            atomic(packet/('FAILURE-'+phase+'.json'),failure)
        except OSError:
            failure['diagnostic_file_write_failed']=True
        try:
            event(packet,'stopped_requires_review',requests_started=started,requests_completed=completed,
                  reserved_upper_bound_usd=str(reserved),observed_token_charge_estimate_usd=str(amount) if completed else None,
                  billing_state='uncertain_reserved_budget_retained' if reserved else 'no_pending_dispatch_known',
                  failure=failure,blocker=diagnostics.describe(failure),
                  stop_reason='Safe failure details recorded where writable. No retry/follow-up is permitted; review failure record and provider dashboard before any new approval.')
        except OSError:
            failure['monitor_write_failed']=True
        raise CycleStopped(failure) from None
    finally:
        if store:store.close()


def status(packet):
    value=load(Path(packet)/'STATUS.json')
    if value.get('status','').endswith('_in_flight'):
        value['elapsed_since_dispatch_seconds']=round((datetime.now(timezone.utc)-datetime.fromisoformat(value['request_started_utc'])).total_seconds(),1)
        value['monitor_note']='A stale in-flight state after interruption means unknown execution/billing; never retry automatically.'
        try:
            if type(value.get('runner_pid')) is int:
                os.kill(value['runner_pid'], 0)  # Read-only process-existence probe.
        except ProcessLookupError:
            value['status']='interrupted_requires_review'
            value['billing_state']='uncertain_reserved_budget_retained'
        except PermissionError:
            value['monitor_note']='Runner existence cannot be checked. Reservation remains held; do not retry.'
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--app-dir',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--previous-packet',type=Path)
    p=sub.add_parser('status');p.add_argument('--packet',required=True,type=Path);p.add_argument('--watch',action='store_true')
    p=sub.add_parser('run');p.add_argument('--packet',required=True,type=Path);p.add_argument('--approval',required=True,type=Path);p.add_argument('--send',action='store_true')
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            p=prepare(args.app_dir,args.output_dir,args.previous_packet);print(json.dumps({'status':'awaiting_approval','approval_sha256':p['approval_sha256'],'maximum_spend_usd':'0.05','requests_sent':0},indent=2))
        elif args.command=='run':
            print(json.dumps(run(args.packet,args.approval,args.send),indent=2))
        else:
            while True:
                value=status(args.packet);print(json.dumps(value,indent=2),flush=True)
                if not args.watch or value['status'] in ('complete','stopped_requires_review','interrupted_requires_review'):break
                time.sleep(2)
    except CycleStopped as exc:
        parser.exit(1,'Stopped: '+diagnostics.describe(exc.diagnostic)+'. See FAILURE-*.json and MONITOR.html. No retry.\n')
    except (ValueError,OSError,KeyError,StopIteration):
        parser.exit(1,'Local preparation/control failed. No implicit approval, credential lookup, retry or fallback is allowed. Inspect the selected packet and monitor.\n')


if __name__=='__main__':main()
