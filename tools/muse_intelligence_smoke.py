"""One separately approved Meta request over a fixed public/synthetic v2 history.

Prepare and verify are offline. No browser endpoint, automatic approval, retry,
model fallback or local-check execution follows a response. Historical contracts
and transports are unchanged. Generated packets belong outside the repository.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import io
import os
from pathlib import Path
import re
import ssl
import sys
from types import SimpleNamespace
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('smoke_safe_helpers', ROOT/'tools/muse_completion_pilot.py')
helper = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(helper)
sys.path.insert(0, str(ROOT/'src'))
from traitweaver import intelligence as model, intelligence_continuation as continuation
from traitweaver import intelligence_muse as v1, intelligence_muse_v2 as v2, intelligence_store, study

CAP = Decimal('0.10')
OUTPUT_CAP = 1024
SCHEMA = 'traitweaver.intelligence_smoke.v1'
PRICING = {**helper.PRICING, 'checked_date': '2026-11-03'}
FIXTURE_STAMP = '2026-11-03T00:00:00+00:00'
LIMIT = ('Single integration smoke test, not a usefulness/adaptivity evaluation. Prior selection and '
         'reassessment are synthetic; the prior evidence audit is a local software result. The model '
         'may propose one of two eligible checks, but cannot execute either. The 1024-output-token '
         'historical contract may yield an incomplete response; stop without retry. Token estimates '
         'are not a provider/account billing cap. Credits, access, taxes and actual charges are unknown.')
TOOLS = ('tools/muse_intelligence_smoke.py', 'tools/muse_completion_pilot.py', 'tools/muse_diagnostics.py')
NETWORK_POLICY = Path('/etc/codex/network-policy.json')
TRANSPORT_POLICY = 'managed_runtime_https_proxy_required_no_direct_fallback'


def now(): return datetime.now(timezone.utc)


def dependencies():
    # Read admitted code/data only, never environment variables or secret stores.
    admitted = (ROOT/'PUBLIC_FILES.txt').read_text().splitlines()
    names = sorted({*(name for name in admitted if name.startswith('src/traitweaver/') and name.endswith('.py')),
                    *(name for name in admitted if name.startswith('data/')), *TOOLS})
    out = {}
    for name in names:
        if ('..' in Path(name).parts or re.search(r'(^|/)(\.env|credentials|secrets)|\.(key|pem|p12|pfx)$', name, re.I)):
            raise ValueError('Unapproved dependency name; contents not read')
        path = ROOT/name
        if helper.safe_path(path) != path or path.is_symlink(): raise ValueError('Unsafe dependency')
        out[name] = helper.sha(path.read_bytes())
    return out


_LOADED_CODE = {k: v for k, v in dependencies().items() if k.endswith('.py')}


def fixture(recorded_result=None):
    """A reproducible authored fixture, never an owner's study or approval."""
    bundle = model.catalog()
    if bundle['reference_status'] != 'available': raise ValueError('Pinned public reference unavailable')
    context = {'study_id': 'SYNTHETIC_SMOKE', 'study_revision_hash': study.digest('synthetic-smoke-v1')}
    state = model.initial(); records = []

    def append(action, result=None):
        nonlocal state
        state = model.transition(state, action, bundle, recorded_result=result)
        row = {'schema_version': 'traitweaver.intelligence_revision.v1', 'catalog_sha256': study.digest(bundle),
               'revision': len(records)+1, 'parent_hash': records[-1]['hash'] if records else None,
               'saved_utc': FIXTURE_STAMP, 'action': deepcopy(action), 'state': deepcopy(state)}
        row['hash'] = study.digest(row); records.append(row)

    def accept(phase):
        request = v1.prepare(state, phase, bundle, 'trait')
        raw = study.canonical(v1.synthetic_reply(state, phase, bundle, 'trait')).encode()
        reply = v1.parse_reply(state, phase, raw, request['request_sha256'], bundle, 'trait')
        append({'type': 'accept', 'payload': reply})

    append({'type': 'revise', 'payload': {'scope': state['scope'], 'context': context}})
    accept('selection'); append({'type': 'run', 'payload': {}}, recorded_result); accept('reassessment')
    source = intelligence_store.package(records, bundle)
    preview = continuation.prepare(records, bundle, context)
    # This is an authored synthetic fixture acknowledgment, not a human grant.
    request = v2.prepare(source, bundle, context, preview['preview_sha256'], True, 'combinations')
    return source, request, bundle


def estimate(size, conservative=False):
    tokens = Decimal(size)+1024 if conservative else Decimal(size)/4
    return helper.usd((tokens*Decimal(PRICING['input_usd_per_million'])+
                       OUTPUT_CAP*Decimal(PRICING['output_usd_per_million']))/1_000_000)


def approval_for(plan, approved=False, offline=False):
    return {'schema_version': 'traitweaver.intelligence_smoke_approval.v1', 'approved': approved,
            'mode': 'offline_test_only' if offline else 'owner_live_approval',
            'approval_sha256': plan['approval_sha256'], 'request_sha256': plan['request_sha256'],
            'destination': v1.DESTINATION, 'model': v1.MODEL, 'maximum_spend_usd': helper.usd(CAP),
            'max_requests': 1, 'max_output_tokens': OUTPUT_CAP, 'retries': 0, 'fallback': False}


def prepare(destination):
    packet = helper.safe_path(destination)
    if packet.exists() or not packet.parent.is_dir() or packet == ROOT or ROOT in packet.parents:
        raise ValueError('Choose a fresh external packet directory with an existing parent')
    source, request, _ = fixture(); raw = study.canonical(request['body']).encode(); helper.screen(raw)
    reservation = estimate(len(raw), True)
    if Decimal(reservation) > CAP: raise ValueError('Conservative reservation exceeds proposed budget')
    stamp = now()
    price_date = datetime.fromisoformat(PRICING['checked_date']).replace(tzinfo=timezone.utc)
    if not price_date <= stamp < price_date+timedelta(days=7):
        raise ValueError('Refresh the reviewed public price before preparing a new request')
    plan = {'schema_version': SCHEMA, 'prepared_utc': stamp.isoformat(),
            'expires_utc': (stamp+timedelta(hours=24)).isoformat(),
            'app_location_sha256': helper.sha(str(ROOT).encode()),
            'packet_location_sha256': helper.sha(str(packet).encode()),
            'destination': v1.DESTINATION, 'method': 'POST', 'model': v1.MODEL, 'mode': 'Standard',
            'store': False, 'max_requests': 1, 'max_output_tokens': OUTPUT_CAP,
            'socket_timeout_seconds': 60, 'retries': 0, 'fallback': False,
            'transport_policy': TRANSPORT_POLICY,
            'maximum_spend_usd': helper.usd(CAP), 'pricing': PRICING,
            'request_sha256': helper.sha(raw), 'request_bytes': len(raw),
            'source_sha256': study.digest(source), 'request_record_sha256': study.digest(request),
            'input_token_allowance': len(raw)+1024, 'reserved_estimate_usd': reservation,
            'planning_estimate_usd': estimate(len(raw)), 'dependencies': dependencies(),
            'fixture_provenance': 'authored_synthetic_history_with_actual_local_audit', 'limit': LIMIT}
    plan['approval_sha256'] = study.digest(plan)
    packet.mkdir(mode=0o700)
    helper.write_raw(packet/'REQUEST.json', raw)
    for name, value in (('SOURCE.json', source), ('REQUEST_RECORD.json', request), ('PLAN.json', plan),
                        ('UNSIGNED_APPROVAL.json', approval_for(plan))): helper.atomic(packet/name, value)
    helper.private_text(packet/'REVIEW.txt', '\n'.join([
        'UNSIGNED — no send or spend authorized. No credentials read.',
        'One Meta Standard request: '+v1.DESTINATION+' / '+v1.MODEL,
        'Exact outgoing bytes: REQUEST.json; source history stays local in SOURCE.json.',
        'Approval SHA-256: '+plan['approval_sha256'], 'Request SHA-256: '+plan['request_sha256'],
        'Maximum output: 1024 tokens; proposed application ceiling USD0.10; one attempt; no retry.',
        'Planning estimate USD'+plan['planning_estimate_usd']+'; conservative reservation USD'+reservation+'.',
        'Input allowance is full UTF-8 body bytes plus 1024, not a verified tokenizer bound.',
        'Pricing checked 2026-11-03: '+PRICING['source'],
        'Account, billing, credits and permitted network access must be resolved before live execution.',
        'Transport requires the inherited HTTPS proxy to match managed runtime metadata; no direct fallback, redirects or TLS bypass.',
        'Network permission is separately enforced by the runtime. A denied destination stops the attempt; this packet changes no policy.',
        'Only a separate explicit owner approval may authorize OWNER_APPROVAL.json matching the unsigned draft with approved=true.',
        'Run also requires --allow-live, this exact approval hash and a real interactive terminal.',
        'Do not place a credential in any packet, command argument or chat. No grant is generated by this tool.',
        'A completed proposal reopens read-only; the separate transport receipt does not relabel synthetic ancestors.', LIMIT, '']))
    return plan


def verify_packet(destination):
    packet = helper.safe_path(destination); plan = helper.read(packet/'PLAN.json')
    if plan.get('approval_sha256') != study.digest({k: v for k, v in plan.items() if k != 'approval_sha256'}):
        raise ValueError('Plan hash changed')
    fixed = {'schema_version': SCHEMA, 'destination': v1.DESTINATION, 'method': 'POST', 'model': v1.MODEL,
             'mode': 'Standard', 'store': False, 'max_requests': 1, 'max_output_tokens': OUTPUT_CAP,
             'socket_timeout_seconds': 60, 'retries': 0, 'fallback': False, 'maximum_spend_usd': helper.usd(CAP),
             'transport_policy': TRANSPORT_POLICY,
             'pricing': PRICING, 'fixture_provenance': 'authored_synthetic_history_with_actual_local_audit', 'limit': LIMIT,
             'app_location_sha256': helper.sha(str(ROOT).encode()),
             'packet_location_sha256': helper.sha(str(packet).encode())}
    if any(study.canonical(plan.get(k)) != study.canonical(v) for k, v in fixed.items()):
        raise ValueError('Fixed request policy or location changed')
    pins = dependencies()
    if plan['dependencies'] != pins or _LOADED_CODE != {k: v for k, v in pins.items() if k.endswith('.py')}:
        raise ValueError('Code/data pins changed; restart and prepare a fresh review')
    for name, module in tuple(sys.modules.items()):
        if name.startswith('traitweaver.') and getattr(module, '__file__', None):
            if Path(module.__file__).resolve().parent != ROOT/'src/traitweaver': raise ValueError('Different application loaded')
    source = helper.read(packet/'SOURCE.json'); request = helper.read(packet/'REQUEST_RECORD.json')
    bundle = model.catalog(); intelligence_store.validate_package(source, bundle)
    # Validation reconstructs from saved receipts; it cannot dispatch a local check.
    expected_source, expected_request, _ = fixture(source['revisions'][2]['state']['cycles'][0]['result'])
    if study.canonical(source) != study.canonical(expected_source) or study.canonical(request) != study.canonical(expected_request):
        raise ValueError('Not the fixed synthetic smoke history')
    if study.digest(source) != plan['source_sha256'] or study.digest(request) != plan['request_record_sha256']:
        raise ValueError('Source/request binding changed')
    raw = study.canonical(request['body']).encode(); helper.screen(raw)
    request_path = packet/'REQUEST.json'
    if request_path.is_symlink() or request_path.stat().st_size != len(raw) or request_path.read_bytes() != raw:
        raise ValueError('Exact outgoing bytes changed')
    if (plan['request_sha256'] != helper.sha(raw) or plan['request_bytes'] != len(raw) or
            plan['input_token_allowance'] != len(raw)+1024 or plan['reserved_estimate_usd'] != estimate(len(raw), True) or
            plan['planning_estimate_usd'] != estimate(len(raw)) or Decimal(plan['reserved_estimate_usd']) > CAP):
        raise ValueError('Payload or budget changed')
    prepared = datetime.fromisoformat(plan['prepared_utc']); expires = datetime.fromisoformat(plan['expires_utc'])
    if prepared.tzinfo is None or expires-prepared != timedelta(hours=24): raise ValueError('Invalid expiry')
    if study.canonical(helper.read(packet/'UNSIGNED_APPROVAL.json')) != study.canonical(approval_for(plan)):
        raise ValueError('Unsigned draft changed')
    return plan, request, source, bundle


def gate(packet, plan, approval_sha256, offline):
    if approval_sha256 != plan['approval_sha256']: raise ValueError('Exact approval hash required at execution')
    name = 'OFFLINE_APPROVAL.json' if offline else 'OWNER_APPROVAL.json'
    if study.canonical(helper.read(packet/name)) != study.canonical(approval_for(plan, True, offline)):
        raise ValueError('Exact payload/budget approval missing')
    if now() < datetime.fromisoformat(plan['prepared_utc']) or now() > datetime.fromisoformat(plan['expires_utc']):
        raise ValueError('Review expired or from the future')
    if now() >= datetime.fromisoformat(PRICING['checked_date']).replace(tzinfo=timezone.utc)+timedelta(days=7):
        raise ValueError('Reviewed public price expired')
    if (packet/'STOP.requested').exists() or (packet/'STOP.requested').is_symlink(): raise ValueError('Stopped by operator')


def marker(path, text):
    try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError: raise ValueError('Duplicate attempt blocked; no retry') from None
    with os.fdopen(fd, 'w') as handle: handle.write(text); handle.flush(); os.fsync(handle.fileno())
    folder = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(folder)
    finally: os.close(folder)


def runtime_proxy():
    """Read non-secret routing metadata only; never change runtime policy/settings."""
    policy = helper.read(NETWORK_POLICY)
    if type(policy.get('version')) is not int or policy['version'] != 1:
        raise ValueError('Supported managed runtime proxy metadata required')
    proxy = policy.get('http_proxy')
    if not isinstance(proxy, str) or not re.fullmatch(r'http://[A-Za-z0-9.-]+:[0-9]{1,5}', proxy):
        raise ValueError('Unsupported managed runtime proxy; no alternate route')
    address = urllib.parse.urlsplit(proxy)
    if not address.hostname or not address.port or address.port > 65535:
        raise ValueError('Invalid managed runtime proxy')
    # Read only named proxy selectors, never enumerate environment/credential values.
    inherited = os.environ.get('https_proxy', os.environ.get('HTTPS_PROXY'))
    if inherited != proxy: raise ValueError('Inherited HTTPS proxy differs from runtime; no direct fallback')
    bypass = os.environ.get('no_proxy', os.environ.get('NO_PROXY', ''))
    if urllib.request.proxy_bypass_environment('api.meta.ai', {'no': bypass}):
        raise ValueError('Inherited proxy bypass includes Meta; runtime configuration review required')
    return proxy


class RequiredProxy(urllib.request.ProxyHandler):
    def __init__(self, proxy):
        # Empty mapping avoids implicit machine proxy discovery. https_open below
        # always uses the already verified inherited runtime proxy.
        super().__init__({}); self.runtime_proxy = proxy

    def https_open(self, request):
        if request.full_url != v1.DESTINATION or request.get_method() != 'POST':
            raise ValueError('Only the exact approved Meta destination is supported')
        if runtime_proxy() != self.runtime_proxy: raise ValueError('Runtime proxy changed before dispatch')
        request.set_proxy(urllib.parse.urlsplit(self.runtime_proxy).netloc, 'http')
        return None  # HTTPSHandler performs CONNECT and verified TLS through this proxy.


def runtime_proxy_opener():
    proxy = runtime_proxy()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    return urllib.request.build_opener(RequiredProxy(proxy), NoRedirect(),
                                      urllib.request.HTTPSHandler(context=ssl.create_default_context()))


class Capture(helper.diagnostics.CaptureOpener):
    def __init__(self, muse, opener=None):
        super().__init__(muse, runtime_proxy_opener() if opener is None else opener)

    def http_failure(self, status, response):
        # Preserve known numeric counts on rejected HTTP responses too. Raw
        # provider bodies and arbitrary error text still never leave memory.
        raw = b''; usage = None
        try:
            raw = response.read(8193)
            if len(raw) <= 8192:
                value = study.decode(raw)
                usage = helper.diagnostics.numeric_usage(value.get('usage')) if isinstance(value, dict) else None
        except Exception: pass
        try: super().http_failure(status, io.BytesIO(raw))
        except helper.diagnostics.SafeFailure as exc:
            if usage is not None: exc.diagnostic['reported_usage'] = usage
            raise


def send(packet, raw, key):
    """Lowest network entry repeats the exact grant, reservation and single-send gate."""
    if not (sys.stdin.isatty() and sys.stderr.isatty()): raise ValueError('Real interactive terminal required')
    packet = helper.safe_path(packet); plan, request, _, _ = verify_packet(packet)
    gate(packet, plan, plan['approval_sha256'], False)
    attempt = packet/'ATTEMPT.started'
    if attempt.is_symlink() or attempt.read_text() != plan['approval_sha256']+'\n': raise ValueError('No exact attempt')
    receipt = helper.read(packet/'RECEIPT.json')
    if (study.canonical(receipt) != study.canonical(initial_receipt(plan, False)) or raw != study.canonical(request['body']).encode()):
        raise ValueError('No exact in-flight reservation/body')
    capture = Capture(SimpleNamespace(DESTINATION=v1.DESTINATION, MODEL=v1.MODEL,
                                      MAX_RESPONSE=v1.MAX_RESPONSE, study=study))
    marker(packet/'POST.started', plan['approval_sha256']+'\n'+plan['request_sha256']+'\n')
    http = urllib.request.Request(v1.DESTINATION, data=raw, method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer '+key})
    with capture.open(http, timeout=60) as response: return response.read(v1.MAX_RESPONSE+1)


def initial_receipt(plan, offline):
    return {'schema_version': 'traitweaver.intelligence_smoke_receipt.v1', 'approval_sha256': plan['approval_sha256'],
            'request_sha256': plan['request_sha256'], 'status': 'in_flight', 'requests_started': 1,
            'transport': 'offline_fake_transport' if offline else 'direct_meta_transport',
            'live_transport_calls': 0, 'response_sha256': None, 'reported_usage': None,
            'estimated_token_cost_usd': None, 'reserved_estimate_usd': plan['reserved_estimate_usd'],
            'billing_state': 'offline_fixture_only' if offline else 'unverified_provider_charge',
            'failure_code': None, 'limit': LIMIT}


def account(receipt, usage, complete=False):
    known = helper.diagnostics.numeric_usage(usage)
    if known is None: return
    receipt['reported_usage'] = known
    if set(known) == {'input_tokens', 'output_tokens'}:
        receipt['estimated_token_cost_usd'] = helper.usd(helper.charge(known))
    if complete: receipt['reserved_estimate_usd'] = '0'


def run(destination, *, approval_sha256, allow_live=False, fake_transport=None):
    packet = helper.safe_path(destination); plan, request, source, bundle = verify_packet(packet)
    offline = fake_transport is not None
    if offline and allow_live: raise ValueError('Fake transport cannot be labelled live')
    if not offline and not allow_live: raise ValueError('Live sending is disabled')
    if not offline and not (sys.stdin.isatty() and sys.stderr.isatty()): raise ValueError('Real interactive terminal required before key access')
    gate(packet, plan, approval_sha256, offline)
    if any((packet/name).exists() or (packet/name).is_symlink() for name in ('ATTEMPT.started', 'POST.started', 'RECEIPT.json', 'PROPOSAL_REVIEW.json')):
        raise ValueError('Packet already attempted; no retry or resume')
    if not offline: runtime_proxy_opener()  # No socket or key access; fail closed before credentials.
    key = None if offline else helper.credential()
    verify_packet(packet); gate(packet, plan, approval_sha256, offline)
    marker(packet/'ATTEMPT.started', plan['approval_sha256']+'\n')
    receipt = initial_receipt(plan, offline); helper.atomic(packet/'RECEIPT.json', receipt)
    try:
        raw = study.canonical(request['body']).encode()
        response = fake_transport(raw) if offline else send(packet, raw, key)
        receipt['live_transport_calls'] = 0 if offline else 1
        if not isinstance(response, bytes) or len(response) > v1.MAX_RESPONSE: raise ValueError('Bounded response required')
        receipt['response_sha256'] = helper.sha(response)
        reply = study.decode(response)
        if not isinstance(reply, dict): raise ValueError('Invalid envelope')
        account(receipt, reply.get('usage'))
        usage = helper.usage_from(reply)
        # Historical v2 receipt additionally requires a consistent total count.
        if usage.get('total_tokens') != usage['input_tokens']+usage['output_tokens']: raise ValueError('Missing total usage')
        account(receipt, usage, True)
        if (usage['input_tokens'] > plan['input_token_allowance'] or usage['output_tokens'] > OUTPUT_CAP or
                Decimal(receipt['estimated_token_cost_usd']) > CAP): raise ValueError('Usage exceeds allowance')
        if (reply.get('traitweaver_synthetic') is True) != offline: raise ValueError('Transport/provenance mismatch')
        review = v2.parse_reply(request, source, bundle, source['revisions'][-1]['state']['context'], response)
        package = {'schema_version': v2.PACKAGE, 'source_package': source, 'request': request,
                   'proposal_review': review, 'limit': v2.LIMIT}
        v2.validate_package(package, bundle)
        helper.atomic(packet/'PROPOSAL_REVIEW.json', package)
        receipt['status'] = 'valid_proposal_only'
    except (Exception, KeyboardInterrupt) as exc:
        receipt['status'] = 'stopped'
        receipt['failure_code'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'transport_or_response_rejected'
        if isinstance(exc, helper.diagnostics.SafeFailure):
            account(receipt, exc.diagnostic.get('reported_usage'))
        # A marker is evidence of an attempted POST, not of a completed request.
        receipt['live_transport_calls'] = int(not offline and (packet/'POST.started').exists())
    finally:
        key = None
        helper.atomic(packet/'RECEIPT.json', receipt)
    return receipt


class Parser(argparse.ArgumentParser):
    def error(self, message): self.exit(2, 'Invalid arguments. Use --help; never pass credentials as arguments.\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify', 'run'))
    parser.add_argument('packet', type=Path)
    parser.add_argument('--allow-live', action='store_true')
    parser.add_argument('--approval-sha256')
    args = parser.parse_args(argv)
    try:
        if args.action == 'prepare': result = prepare(args.packet)
        elif args.action == 'verify': result = verify_packet(args.packet)[0]
        else: result = run(args.packet, allow_live=args.allow_live, approval_sha256=args.approval_sha256)
        print(study.canonical(result)); return 1 if result.get('status') == 'stopped' else 0
    except (Exception, KeyboardInterrupt):
        print('Smoke request blocked or stopped. No retry/resume. Review the packet and static instructions; private error text withheld.', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
