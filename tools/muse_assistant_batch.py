"""Prepare/review one four-case Muse batch. Live execution needs separate approval.

No credentials or provider requests in prepare/status/monitor. Core scientific
contracts remain transport-free. Raw responses, reasoning and headers are never
written; this separate adapter validates numeric usage and core claim/action IDs.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import getpass
import hashlib
import html
import importlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
from types import SimpleNamespace
import urllib.request
import warnings

HERE=Path(__file__).resolve().parent
_spec=importlib.util.spec_from_file_location('assistant_safe_diagnostics',HERE/'muse_diagnostics.py')
diagnostics=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(diagnostics)
CASES=('ENV_ALGAE','PROTEIN_GFP','RNA_SYNTHETIC','REPRO_SYNTHETIC')
CAP=Decimal('0.20');OUTPUT_CAP=8192;DEADLINE=120
PRICING={'source':'https://dev.meta.ai/docs/pricing-rate-limits','checked_date':'2026-10-31',
         'input_usd_per_million':'1.25','output_usd_per_million':'4.25','cached_input_usd_per_million':'0.15',
         'cost_basis':'Uncached input throughout; no cache discount or search/tool surcharge assumed.'}
APP_FILES=('src/traitweaver/__init__.py','src/traitweaver/assistant.py','src/traitweaver/assistant_workspace.py',
           'src/traitweaver/study.py','src/traitweaver/study_store.py','src/traitweaver/protein_card.py',
           'data/assistant-cases.v1.json','data/algae-public.v1.json','data/gfp/MANIFEST.json',
           'data/gfp/QUALIFICATION.json','data/gfp/accession.json','data/gfp/atlas-record.json')
RUNNER_FILES=('muse_assistant_batch.py','muse_assistant_start.py','muse_diagnostics.py')
DESTINATION='https://api.meta.ai/v1/responses';MODEL='muse-spark-1.3'
FLOW='One independent priority review per case, fixed order. Validate reply/usage, save accepted records and one local audit, then continue. Stop the entire batch on any failure; no retry, resume or fallback.'
LIMIT='Prioritization of authored public/synthetic proposals, not novel claim generation, biological validation, arbitrary tool execution or a laboratory protocol. Local receipt consistency is not independent provider authentication or billing verification.'


def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(v):return sha(canonical(v).encode())
def utc():return datetime.now(timezone.utc).isoformat()
def usd(v):return format(Decimal(v),'f')


def read(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024:raise ValueError('Unsafe/missing/oversized packet file')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate JSON field')
            out[k]=v
        return out
    def invalid(_):raise ValueError('Nonfinite JSON')
    try:return json.loads(path.read_bytes(),object_pairs_hook=pairs,parse_constant=invalid)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('Invalid local JSON') from None


def write_raw(path,raw):
    path=Path(path)
    if path.is_symlink():raise ValueError('Refuse symlink output')
    pending=path.with_name('.'+path.name+'.'+str(os.getpid())+'.pending')
    created=False
    try:
        fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        created=True
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(pending,path)
    finally:
        if created:pending.unlink(missing_ok=True)


def atomic(path,value):
    write_raw(path,(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def private_text(path,text):
    write_raw(path,text.encode())


def safe_path(path):
    path=Path(path).absolute()
    aliases={Path('/tmp'):Path('/private/tmp'),Path('/var'):Path('/private/var')}
    if any(p.is_symlink() and not (p in aliases and p.resolve()==aliases[p]) for p in (path,*path.parents)):
        raise ValueError('Packet/app path must not traverse symlinks')
    return path.resolve()


def configure(app):
    app=safe_path(app).resolve()
    for name in APP_FILES:
        p=app/name
        if p.is_symlink() or not p.is_file():raise ValueError('Required public application file unavailable')
    for name in ('assistant','assistant_workspace','study','study_store','protein_card'):
        module=sys.modules.get('traitweaver.'+name)
        if module and Path(module.__file__).resolve()!=app/'src/traitweaver'/(name+'.py'):
            raise ValueError('Different application already loaded; use a fresh process')
    sys.path.insert(0,str(app/'src'))
    return tuple(importlib.import_module('traitweaver.'+name) for name in ('assistant','assistant_workspace'))


def screen(raw):
    text=raw.decode()
    patterns=(r'/Users/|/home/|\$HOME',r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}',
              r'(?i)set-cookie\s*:|authorization\s*:|(?:api[_ -]?key|password|client[_ -]?secret)\s*[:=]\s*\S+',
              r'study_case\.json|raw_chat|response_cookies')
    if any(re.search(p,text) for p in patterns):raise ValueError('Public packet requires privacy review; no matched value displayed or removed')


def reserve(size):return ((Decimal(size)+1024)*Decimal(PRICING['input_usd_per_million'])+OUTPUT_CAP*Decimal(PRICING['output_usd_per_million']))/1_000_000
def estimate(size):return ((Decimal(size)/4)*Decimal(PRICING['input_usd_per_million'])+OUTPUT_CAP*Decimal(PRICING['output_usd_per_million']))/1_000_000


def request_for(core,cid):
    """Separate wire budget; preserve the original transport-free v1 request."""
    preview=core.prepare(cid)
    body=deepcopy(preview['body']);body['max_output_tokens']=OUTPUT_CAP
    return body,preview['request_sha256']


def approval_for(plan,approved=False):
    return {'approved':approved,'approval_sha256':plan['approval_sha256'],'destination':DESTINATION,'model':MODEL,
            'maximum_spend_usd':usd(CAP),'max_requests':4,'max_output_tokens_each':OUTPUT_CAP,'retries':0,'fallback':False}


def fresh_status(plan):
    return {'schema_version':'traitweaver.assistant_batch_status.v2','approval_sha256':plan['approval_sha256'],
            'transport':'not_started','status':'awaiting_approval','updated_utc':utc(),'elapsed_seconds':0,
            'active_case':None,'request_elapsed_seconds':0,'requests_started':0,'responses_received':0,
            'responses_accepted':0,'cases_completed':0,'maximum_spend_authorized_usd':'0',
            'reserved_upper_bound_usd':'0','observed_token_charge_estimate_usd':'0','actual_provider_charge_usd':None,
            'billing_state':'no_requests_sent','failure':None,
            'cases':[{'case_id':cid,'status':'pending','reported_usage':None,'estimated_cost_usd':None,
                      'usage_state':'unavailable','reservation_released':False,
                      'response_sha256':None,'failure':None} for cid in CASES]}


def clean_failure(value):
    # New failures are application literals; imported diagnostics use exact enums.
    codes={'deadline_exceeded','operator_stop','operator_interrupted','usage_missing_or_invalid','usage_exceeds_allowance',
           'response_validation_failed','provider_refusal','unsupported_output_or_tool_call','source_or_payload_changed','local_save_failed','local_check_failed',
           'synthetic_marker_on_live_reply','malformed_json','response_not_object','missing_http_status',
           'redirect_blocked','http_authentication_rejected','http_permission_rejected','http_rate_or_quota_rejected',
           'http_request_rejected','http_provider_error','unexpected_http_status','tls_certificate_verification_failed',
           'tls_error','dns_resolution_failed','timeout','connection_refused','connection_reset','network_error',
           'transport_error','response_too_large','model_mismatch','provider_not_completed','transport_failure','duplicate_attempt_blocked'}
    stages={'transport_open','response_read','response_decode','provider_envelope_validation','http_response',
            'request_preparation','response_validation','usage_validation','packet_validation','local_check','export','operator','transport'}
    out={'code':value.get('code') if value.get('code') in codes else 'transport_failure',
         'stage':value.get('stage') if value.get('stage') in stages else 'transport',
         'dispatch_attempted':bool(value.get('dispatch_attempted'))}
    if type(value.get('http_status')) is int and 100<=value['http_status']<=599:out['http_status']=value['http_status']
    for k in ('provider_error_code','provider_error_type'):
        if k in value:out[k]=value[k] if value[k] in diagnostics.PROVIDER_CODES else 'unrecognized_value_withheld'
    if 'provider_error_parameter' in value:out['provider_error_parameter']=value['provider_error_parameter'] if value['provider_error_parameter'] in diagnostics.PARAMETERS else 'unrecognized_value_withheld'
    if value.get('provider_status') in diagnostics.STATUSES:out['provider_status']=value['provider_status']
    if value.get('incomplete_reason') in ('max_output_tokens','content_filter'):out['incomplete_reason']=value['incomplete_reason']
    usage=diagnostics.numeric_usage(value.get('reported_usage'))
    if usage:out['reported_usage']=usage
    return out


def valid_status(value):
    template=fresh_status({'approval_sha256':'0'*64})
    if type(value) is not dict or set(value)!=set(template):raise ValueError('Malformed monitor state')
    if value['schema_version']!=template['schema_version'] or not re.fullmatch('[a-f0-9]{64}',value['approval_sha256']):raise ValueError('Invalid monitor identity')
    if value['status'] not in ('awaiting_approval','running','in_flight','validating','exporting','completed','stopped_requires_review'):raise ValueError('Invalid monitor stage')
    if value['transport'] not in ('not_started','direct_meta_transport','offline_fake_transport'):raise ValueError('Invalid transport label')
    if value['billing_state'] not in ('no_requests_sent','usage_estimates_only','possible_charge_usage_unknown','offline_fixture_only'):raise ValueError('Invalid billing label')
    if value['active_case'] not in (None,*CASES) or value['actual_provider_charge_usd'] is not None:raise ValueError('Invalid monitor value')
    stamp=datetime.fromisoformat(value['updated_utc'])
    if stamp.tzinfo is None:raise ValueError('Invalid monitor timestamp')
    for k in ('requests_started','responses_received','responses_accepted','cases_completed'):
        if type(value[k]) is not int or not 0<=value[k]<=4:raise ValueError('Invalid request count')
    if not value['cases_completed']<=value['responses_accepted']<=value['responses_received']<=value['requests_started']:raise ValueError('Inconsistent monitor counts')
    for k in ('elapsed_seconds','request_elapsed_seconds'):
        if type(value[k]) not in (int,float) or not 0<=value[k]<=86400:raise ValueError('Invalid elapsed time')
    for k in ('maximum_spend_authorized_usd','reserved_upper_bound_usd','observed_token_charge_estimate_usd'):
        if type(value[k]) is not str or len(value[k])>30 or not re.fullmatch(r'\d+(?:\.\d+)?',value[k]) or Decimal(value[k])>1_000_000:raise ValueError('Invalid monitor budget')
    if value['failure'] is not None and clean_failure(value['failure'])!=value['failure']:raise ValueError('Unsafe failure record')
    if not isinstance(value['cases'],list) or len(value['cases'])!=4:raise ValueError('Invalid case roster')
    for row,cid in zip(value['cases'],CASES):
        if type(row) is not dict or set(row)!=set(template['cases'][0]) or row['case_id']!=cid:raise ValueError('Invalid case status')
        if row['status'] not in ('pending','in_flight','received','accepted','completed','failed','skipped'):raise ValueError('Invalid case stage')
        if row['response_sha256'] is not None and not re.fullmatch('[a-f0-9]{64}',row['response_sha256']):raise ValueError('Invalid response fingerprint')
        if row['failure'] is not None and clean_failure(row['failure'])!=row['failure']:raise ValueError('Unsafe case failure')
        if row['estimated_cost_usd'] is not None and (type(row['estimated_cost_usd']) is not str or not re.fullmatch(r'\d+(?:\.\d+)?',row['estimated_cost_usd'])):raise ValueError('Invalid cost')
        if row['usage_state'] not in ('unavailable','partial_or_invalid','complete_counts') or type(row['reservation_released']) is not bool:raise ValueError('Invalid accounting state')
        if row['reservation_released'] and row['usage_state']!='complete_counts':raise ValueError('Unsettled reservation released')
        u=row['reported_usage']
        if row['usage_state']=='unavailable':
            if u is not None or row['estimated_cost_usd'] is not None:raise ValueError('Unavailable usage is not zero')
        elif row['usage_state']=='complete_counts':usage_from({'usage':u})
        elif not u or diagnostics.numeric_usage(u)!=u:raise ValueError('Unsafe partial usage')
        known=diagnostics.numeric_usage(u) or {}
        expected=usd(charge(known)) if set(known)=={'input_tokens','output_tokens'} else None
        if row['estimated_cost_usd']!=expected:raise ValueError('Case cost disagrees with usage')
    costs=sum((Decimal(r['estimated_cost_usd']) for r in value['cases'] if r['estimated_cost_usd'] is not None),Decimal(0))
    if Decimal(value['observed_token_charge_estimate_usd'])!=costs:raise ValueError('Batch cost disagrees with cases')
    return deepcopy(value)


def event(packet,state):
    state['updated_utc']=utc();valid_status(state)
    raw=(canonical(state)+'\n').encode()
    fd=os.open(packet/'EVENTS.jsonl',os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'ab') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    atomic(packet/'STATUS.json',state)
    page='<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
    page+='<title>Traitweaver four-case monitor</title><style>body{background:#02070A;color:#e8f4fa;max-width:980px;margin:35px auto;padding:0 24px;font:16px/1.65 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0a1c28;padding:20px}h1{color:#83d2fa}</style>'
    page+='<h1>Four-case Muse review · '+html.escape(state['status'].replace('_',' '))+'</h1><p>Local snapshot. Refresh this file or use the local monitor command. No network polling. A stale heartbeat may mean the process stopped; never rerun an attempted packet.</p>'
    page+='<p><b>'+('OFFLINE REHEARSAL — no provider requests or charges' if state['transport']=='offline_fake_transport' else 'Direct Meta transport — local receipts, billing unverified' if state['transport']=='direct_meta_transport' else 'NOT STARTED — awaiting exact owner approval')+'</b></p>'
    page+='<p><b>'+str(state['requests_started'])+' / 4 requests started · '+str(state['responses_received'])+' HTTP/returned responses observed (including rejected responses) · '+str(state['responses_accepted'])+' accepted · '+str(state['cases_completed'])+' case packages saved</b></p>'
    page+='<p>Active study: '+html.escape(state['active_case'] or 'None')+' · elapsed '+str(state['elapsed_seconds'])+' seconds · latest heartbeat '+html.escape(state['updated_utc'])+'</p>'
    page+='<p>Estimate from reported input/output pairs: $'+state['observed_token_charge_estimate_usd']+' · unsettled reservation: $'+state['reserved_upper_bound_usd']+' · approved application ceiling: $'+state['maximum_spend_authorized_usd']+'</p><p>Missing or partial usage is not zero cost. Unsettled reservations remain conservative and may overlap a known estimate when usage validation fails. Provider billing remains unverified.</p>'
    page+='<ul>'+''.join('<li>'+r['case_id']+' — '+r['status'].replace('_',' ')+(' · usage unavailable' if r['reported_usage'] is None else ' · '+str(r['reported_usage'].get('input_tokens','unknown'))+' input / '+str(r['reported_usage'].get('output_tokens','unknown'))+' output tokens · '+r['usage_state'].replace('_',' '))+(' · estimated $'+r['estimated_cost_usd'] if r['estimated_cost_usd'] is not None else ' · cost unknown')+'</li>' for r in state['cases'])+'</ul>'
    if state['failure']:page+='<h2>Stopped — no retry</h2><pre>'+html.escape(json.dumps(state['failure'],indent=2))+'</pre>'
    page+='<details><summary>Exact safe status record</summary><pre>'+html.escape(json.dumps(state,indent=2))+'</pre></details><p>Raw provider responses, credentials, cookies and exception text are never stored. Local cost estimates are not an independently verified invoice.</p>'
    private_text(packet/'MONITOR.html',page)


def prepare(app,destination):
    app=safe_path(app).resolve();core,_=configure(app);target=safe_path(destination)
    if target.exists() or not target.parent.is_dir() or target==app or app in target.parents:raise ValueError('Choose a fresh external packet folder with an existing parent')
    entries=[];bodies=[]
    for n,cid in enumerate(CASES,1):
        body,core_hash=request_for(core,cid);raw=canonical(body).encode();screen(raw);bodies.append(raw)
        entries.append({'case_id':cid,'file':str(n).zfill(2)+'-'+cid+'.json','sha256':sha(raw),'bytes':len(raw),
                        'case_sha256':core.prepare(cid)['case_sha256'],'core_request_sha256':core_hash,'input_token_allowance':len(raw)+1024,'max_output_tokens':OUTPUT_CAP,
                        'reserved_upper_bound_usd':usd(reserve(len(raw))),'planning_estimate_usd':usd(estimate(len(raw)))})
    maximum=sum((reserve(len(b)) for b in bodies),Decimal(0))
    if maximum>CAP:raise ValueError('Payload reservations exceed proposed batch ceiling')
    now=datetime.now(timezone.utc)
    execution={'app_files':{name:sha((app/name).read_bytes()) for name in APP_FILES},
               'runner_files':{name:sha((app/'tools'/name).read_bytes()) for name in RUNNER_FILES}}
    plan={'schema_version':'traitweaver.four_case_muse_batch.v2','prepared_utc':now.isoformat(),'expires_utc':(now+timedelta(hours=24)).isoformat(),
          'packet_location_sha256':sha(str(target.resolve()).encode()),
          'destination':DESTINATION,'method':'POST','model':MODEL,'mode':'Standard','store':False,
          'max_requests':4,'max_output_tokens_each':OUTPUT_CAP,'max_seconds_per_request':DEADLINE,'retries':0,'fallback':False,
          'maximum_spend_usd':usd(CAP),'pricing':PRICING,'requests':entries,'execution':execution,'flow':FLOW,'limit':LIMIT,
          'conservative_batch_reservation_usd':usd(maximum),'planning_estimate_usd':usd(sum((estimate(len(b)) for b in bodies),Decimal(0))),
          'cost_limit':'Application guard at pinned prices and conservative input allowances, not a provider/account-wide billing cap. Missing usage retains reservation and stops all further sends. Input bound is UTF-8 body bytes plus 1024; no tokenizer or billing API call was made.'}
    plan['approval_sha256']=digest(plan)
    target.mkdir(mode=0o700)
    for entry,raw in zip(entries,bodies):
        fd=os.open(target/entry['file'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    for name in RUNNER_FILES:private_text(target/name,(app/'tools'/name).read_text())
    private_text(target/'START_REVIEWED_BATCH.py',(app/'tools/muse_assistant_start.py').read_text())
    atomic(target/'PUBLIC_BATCH.json',plan);atomic(target/'PRICING.json',PRICING)
    atomic(target/'LOCAL_CONTROL.json',{'app_dir':str(app),'packet_dir':str(target.resolve()),'approval_sha256':plan['approval_sha256']})
    atomic(target/'UNSIGNED_APPROVAL.json',approval_for(plan))
    event(target,fresh_status(plan));write_approval(target,plan,bodies)
    return plan


def verify_packet(packet):
    packet=safe_path(packet);plan=read(packet/'PUBLIC_BATCH.json');control=read(packet/'LOCAL_CONTROL.json')
    if plan.get('approval_sha256')!=digest({k:v for k,v in plan.items() if k!='approval_sha256'}):raise ValueError('Approval manifest changed')
    if set(control)!= {'app_dir','packet_dir','approval_sha256'} or control['approval_sha256']!=plan['approval_sha256']:raise ValueError('Local control identity changed')
    if packet.resolve()!=Path(control['packet_dir']).resolve() or plan['packet_location_sha256']!=sha(str(packet.resolve()).encode()):raise ValueError('Packet moved/copied; prepare a fresh location-bound review')
    fixed={'schema_version':'traitweaver.four_case_muse_batch.v2','destination':DESTINATION,'method':'POST','model':MODEL,'mode':'Standard','store':False,
           'max_requests':4,'max_output_tokens_each':OUTPUT_CAP,'max_seconds_per_request':DEADLINE,'retries':0,'fallback':False,'maximum_spend_usd':usd(CAP),'pricing':PRICING,'flow':FLOW,'limit':LIMIT}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in fixed.items()):raise ValueError('Unsupported batch scope or price')
    app=safe_path(control['app_dir']).resolve();ex=plan['execution']
    if set(ex)!= {'app_files','runner_files'} or set(ex['app_files'])!=set(APP_FILES) or set(ex['runner_files'])!=set(RUNNER_FILES):raise ValueError('Execution roster changed')
    for name,expected in ex['app_files'].items():
        if (app/name).is_symlink() or sha((app/name).read_bytes())!=expected:raise ValueError('Public source or application changed')
    for name,expected in ex['runner_files'].items():
        for p in (app/'tools'/name,packet/name):
            if p.is_symlink() or sha(p.read_bytes())!=expected:raise ValueError('Reviewed runner changed')
    if sha(Path(__file__).read_bytes())!=ex['runner_files']['muse_assistant_batch.py'] or sha((packet/'START_REVIEWED_BATCH.py').read_bytes())!=ex['runner_files']['muse_assistant_start.py']:
        raise ValueError('Loaded runner or starter changed')
    if read(packet/'PRICING.json')!=PRICING or read(packet/'UNSIGNED_APPROVAL.json')!=approval_for(plan):raise ValueError('Pricing/draft changed')
    core,helper=configure(app)
    if type(plan['requests']) is not list or len(plan['requests'])!=4:raise ValueError('Four case requests required')
    maximum=Decimal(0);planning=Decimal(0)
    for n,(entry,cid) in enumerate(zip(plan['requests'],CASES),1):
        body,core_hash=request_for(core,cid);raw=canonical(body).encode();screen(raw)
        expected={'case_id':cid,'file':str(n).zfill(2)+'-'+cid+'.json','sha256':sha(raw),'bytes':len(raw),'case_sha256':core.prepare(cid)['case_sha256'],'core_request_sha256':core_hash,
                  'input_token_allowance':len(raw)+1024,'max_output_tokens':OUTPUT_CAP,'reserved_upper_bound_usd':usd(reserve(len(raw))),'planning_estimate_usd':usd(estimate(len(raw)))}
        if entry!=expected or (packet/expected['file']).is_symlink() or (packet/expected['file']).read_bytes()!=raw:raise ValueError('Exact public payload changed')
        maximum+=reserve(len(raw));planning+=estimate(len(raw))
    if maximum>CAP or plan['conservative_batch_reservation_usd']!=usd(maximum) or plan['planning_estimate_usd']!=usd(planning):raise ValueError('Budget reservation changed')
    made=datetime.fromisoformat(plan['prepared_utc']);expires=datetime.fromisoformat(plan['expires_utc'])
    if made.tzinfo is None or expires-made!=timedelta(hours=24):raise ValueError('Invalid review validity window')
    return plan,core,helper


def status(packet):
    packet=safe_path(packet);value=valid_status(read(packet/'STATUS.json'))
    age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(value['updated_utc'])).total_seconds())
    return {**value,'monitor_observation':{'heartbeat_age_seconds':round(age,1),'possibly_interrupted':age>15 and value['status'] in ('running','in_flight','validating','exporting'),
            'retry_permitted':False}}


def usage_from(reply):
    u=reply.get('usage')
    if not isinstance(u,dict) or any(type(u.get(k)) is not int or not 0<=u[k]<=1_000_000_000 for k in ('input_tokens','output_tokens')):raise ValueError('usage_missing_or_invalid')
    total=u.get('total_tokens')
    if total is not None and (type(total) is not int or total!=u['input_tokens']+u['output_tokens']):raise ValueError('usage_missing_or_invalid')
    out={'input_tokens':u['input_tokens'],'output_tokens':u['output_tokens']}
    if total is not None:out['total_tokens']=total
    for field,name,parent in (('reasoning_tokens','output_tokens_details','output_tokens'),('cached_tokens','input_tokens_details','input_tokens')):
        if name in u and u[name] is not None and not isinstance(u[name],dict):raise ValueError('usage_missing_or_invalid')
        count=(u.get(name) or {}).get(field)
        # Safe status receipts store these same numeric fields in flat form.
        if field in u:count=u[field]
        if count is not None and (type(count) is not int or not 0<=count<=u[parent]):raise ValueError('usage_missing_or_invalid')
        out[field]=count
    return out


def charge(usage):return (Decimal(usage['input_tokens'])*Decimal(PRICING['input_usd_per_million'])+Decimal(usage['output_tokens'])*Decimal(PRICING['output_usd_per_million']))/1_000_000


def account_usage(state,row,reported,reservation,*,settled=False):
    """Account independently of answer acceptance, without charging twice."""
    known=diagnostics.numeric_usage(reported)
    if known is None:return
    row['reported_usage']=usage_from({'usage':reported}) if settled else known
    row['usage_state']='complete_counts' if settled else 'partial_or_invalid'
    row['estimated_cost_usd']=usd(charge(known)) if set(known)=={'input_tokens','output_tokens'} else None
    if settled and not row['reservation_released']:
        state['reserved_upper_bound_usd']=usd(max(Decimal(0),Decimal(state['reserved_upper_bound_usd'])-Decimal(reservation)))
        row['reservation_released']=True
    state['observed_token_charge_estimate_usd']=usd(sum((Decimal(r['estimated_cost_usd']) for r in state['cases'] if r['estimated_cost_usd'] is not None),Decimal(0)))


def adapt_reply(core,cid,raw,request_hash,offline=False):
    body,core_hash=request_for(core,cid)
    if request_hash!=sha(canonical(body).encode()):raise ValueError('response_validation_failed')
    if not isinstance(raw,bytes) or len(raw)>core.MAX_BYTES:raise ValueError('response_validation_failed')
    reply=core.study.decode(raw)
    if not isinstance(reply,dict):raise ValueError('response_validation_failed')
    if reply.get('model')!=MODEL:raise ValueError('model_mismatch')
    if reply.get('status')!='completed':raise ValueError('provider_not_completed')
    if isinstance(reply.get('output'),list):
        for item in reply['output']:
            if isinstance(item,dict) and item.get('type') not in ('reasoning','message'):raise ValueError('unsupported_output_or_tool_call')
            if isinstance(item,dict) and isinstance(item.get('content'),list) and any(isinstance(b,dict) and b.get('type')=='refusal' for b in item['content']):raise ValueError('provider_refusal')
    if not offline and reply.get('traitweaver_synthetic') is True:raise ValueError('synthetic_marker_on_live_reply')
    usage=usage_from(reply);normalized=deepcopy(reply)
    normalized['usage']={k:usage[k] for k in ('input_tokens','output_tokens','total_tokens') if k in usage}
    if offline:normalized['traitweaver_synthetic']=True
    # The unchanged v1 record binds its original scientific request. The v2
    # batch receipt separately binds exact wire bytes and the output-only override.
    record=core.parse_reply(cid,canonical(normalized).encode(),core_hash)
    record['receipt']['response_sha256']=sha(raw)
    return core.validate_record(record),usage


def credential():
    key=os.environ.get('MODEL_API_KEY')
    if not key:
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            key=getpass.getpass('Meta MODEL_API_KEY (hidden; never saved): ')
    if type(key) is not str or not key.strip() or any(c in key for c in ('\r','\n','\x00')):raise ValueError('Credential unavailable or malformed')
    return key.strip()


def real_transport(core,raw,key,*,packet=None):
    # Guard the lowest exposed send entry as well as run and the terminal starter.
    if packet is None or not (sys.stdin.isatty() and sys.stderr.isatty()):raise ValueError('Approved packet and real terminal required')
    packet=safe_path(packet);plan,_,_=verify_packet(packet)
    if read(packet/'OWNER_APPROVAL.json')!=approval_for(plan,True):raise ValueError('Exact batch approval required')
    if datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_utc']):raise ValueError('Review expired')
    marker=packet/'BATCH.started'
    if marker.is_symlink() or not marker.is_file() or marker.read_text()!=plan['approval_sha256']+'\n':raise ValueError('Missing exact attempt marker')
    current=valid_status(read(packet/'STATUS.json'))
    if current['transport']!='direct_meta_transport' or current['status']!='in_flight':raise ValueError('No authorized in-flight slot')
    entry=next((e for e in plan['requests'] if e['case_id']==current['active_case']),None)
    if entry is None or sha(raw)!=entry['sha256'] or len(raw)!=entry['bytes'] or Decimal(current['reserved_upper_bound_usd'])<Decimal(entry['reserved_upper_bound_usd']):raise ValueError('Unreviewed body or missing reservation')
    if Decimal(current['reserved_upper_bound_usd'])+Decimal(current['observed_token_charge_estimate_usd'])>CAP:raise ValueError('Budget exceeded')
    if (packet/'STOP.requested').exists():raise diagnostics.SafeFailure({'code':'operator_stop','stage':'operator','dispatch_attempted':False})
    try:fd=os.open(packet/('POST-'+entry['case_id']+'.started'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:raise diagnostics.SafeFailure({'code':'duplicate_attempt_blocked','stage':'request_preparation','dispatch_attempted':False}) from None
    with os.fdopen(fd,'w') as f:f.write(plan['approval_sha256']+'\n'+entry['sha256']+'\n');f.flush();os.fsync(f.fileno())
    request=urllib.request.Request(DESTINATION,data=raw,headers={'Content-Type':'application/json','Accept':'application/json','Authorization':'Bearer '+key},method='POST')
    capture=diagnostics.CaptureOpener(SimpleNamespace(DESTINATION=DESTINATION,MODEL=MODEL,MAX_RESPONSE=core.MAX_BYTES,study=core.study))
    with capture.open(request,timeout=DEADLINE) as response:return response.read(core.MAX_BYTES+1)


class BatchStopped(ValueError):
    def __init__(self,state):self.state=deepcopy(state);super().__init__('Batch stopped; safe monitor details saved. No retry or resume.')


def wait_transport(packet,state,transport,core,raw,key,start,deadline=DEADLINE):
    if (packet/'STOP.requested').exists():raise diagnostics.SafeFailure({'code':'operator_stop','stage':'operator','dispatch_attempted':False})
    result=queue.Queue(maxsize=1)
    def worker():
        if (packet/'STOP.requested').exists():
            result.put(('failure',{'code':'operator_stop','stage':'operator','dispatch_attempted':False}));return
        try:result.put(('ok',transport(core,raw,key)))
        except diagnostics.SafeFailure as exc:result.put(('failure',clean_failure(exc.diagnostic)))
        except Exception as exc:result.put(('failure',clean_failure({'code':diagnostics.network_code(exc),'stage':'transport','dispatch_attempted':True})))
    thread=threading.Thread(target=worker,daemon=True);thread.start();began=time.monotonic();last=began
    while True:
        now=time.monotonic();state['elapsed_seconds']=round(now-start,3);state['request_elapsed_seconds']=round(now-began,3)
        if (packet/'STOP.requested').exists():raise diagnostics.SafeFailure({'code':'operator_stop','stage':'operator','dispatch_attempted':True})
        if now-began>=deadline:raise diagnostics.SafeFailure({'code':'deadline_exceeded','stage':'transport','dispatch_attempted':True})
        try:
            kind,value=result.get(timeout=min(.2,max(.001,deadline-(now-began))))
            if kind=='failure':raise diagnostics.SafeFailure(value)
            return value
        except queue.Empty:pass
        if now-last>=1:event(packet,state);last=now


def run(packet,*,allow_live=False,fake_transport=None):
    packet=safe_path(packet);plan,core,helper=verify_packet(packet)
    offline=fake_transport is not None
    if offline and allow_live:raise ValueError('Fake transport cannot be labelled live')
    if not offline and not allow_live:raise ValueError('Live sending is disabled')
    if not offline and not (sys.stdin.isatty() and sys.stderr.isatty()):raise ValueError('A real interactive terminal is required before live sending')
    if read(packet/'OWNER_APPROVAL.json')!=approval_for(plan,True):raise ValueError('Exact batch approval is missing')
    if datetime.now(timezone.utc)>datetime.fromisoformat(plan['expires_utc']):raise ValueError('Review expired; prepare and approve a fresh packet')
    if (packet/'BATCH.started').exists() or (packet/'BATCH.started').is_symlink() or (packet/'STOP.requested').exists():raise ValueError('Packet already attempted or stopped; no retry/resume')
    prior=valid_status(read(packet/'STATUS.json'))
    if prior['status']!='awaiting_approval' or prior['requests_started']!=0:raise ValueError('Packet has prior activity')
    key=None if offline else credential()
    # Repeat pins after any hidden prompt, before the irreversible attempt marker.
    verify_packet(packet)
    fd=os.open(packet/'BATCH.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(plan['approval_sha256']+'\n');f.flush();os.fsync(f.fileno())
    state=fresh_status(plan);state.update(status='running',transport='offline_fake_transport' if offline else 'direct_meta_transport',maximum_spend_authorized_usd=usd(CAP),billing_state='offline_fixture_only' if offline else 'usage_estimates_only')
    start=time.monotonic();active=None;stage='packet_validation'
    try:
        event(packet,state)
        for entry,row in zip(plan['requests'],state['cases']):
            active=row;state['active_case']=row['case_id'];state['request_elapsed_seconds']=0
            stage='packet_validation';verify_packet(packet)
            if (packet/'STOP.requested').exists():raise diagnostics.SafeFailure({'code':'operator_stop','stage':'operator','dispatch_attempted':False})
            reserved=Decimal(entry['reserved_upper_bound_usd']);spent=Decimal(state['observed_token_charge_estimate_usd']);held=Decimal(state['reserved_upper_bound_usd'])
            remaining=sum((Decimal(e['reserved_upper_bound_usd']) for e in plan['requests'][state['requests_started']:]),Decimal(0))
            if spent+held+remaining>CAP:raise ValueError('Budget cap would be exceeded')
            state['reserved_upper_bound_usd']=usd(held+reserved);state['requests_started']+=1
            state['status']='in_flight';row['status']='in_flight';event(packet,state)
            # Regenerate the pinned public body in memory. Never re-read mutable
            # packet bytes after validation and send them without a hash check.
            stage='packet_validation';raw=canonical(request_for(core,row['case_id'])[0]).encode()
            if sha(raw)!=entry['sha256'] or len(raw)!=entry['bytes']:raise ValueError('Pinned request changed')
            stage='transport';transport=fake_transport or (lambda core,raw,key:real_transport(core,raw,key,packet=packet))
            response=wait_transport(packet,state,transport,core,raw,key,start)
            state['responses_received']+=1;row['status']='received';row['response_sha256']=sha(response) if isinstance(response,bytes) else None
            state['status']='validating';stage='response_validation'
            try:decoded=core.study.decode(response)
            except (ValueError,UnicodeError):raise ValueError('malformed_json') from None
            stage='usage_validation';account_usage(state,row,diagnostics.numeric_usage(decoded.get('usage')),reserved)
            usage=usage_from(decoded);cost=charge(usage)
            account_usage(state,row,usage,reserved,settled=True)
            event(packet,state)
            if usage['input_tokens']>entry['input_token_allowance'] or usage['output_tokens']>OUTPUT_CAP or spent+cost>CAP:raise ValueError('usage_exceeds_allowance')
            stage='response_validation';record,_=adapt_reply(core,row['case_id'],response,entry['sha256'],offline)
            row['status']='accepted';state['responses_accepted']+=1;event(packet,state)
            stage='export';state['status']='exporting';event(packet,state)
            folder=packet/row['case_id'];core.export_bundle(record,folder)
            # Actual local record audit, with a pre-result purpose, never model-selected code.
            stage='local_check';local=helper.Session();local.select(row['case_id'])
            decision={'check':helper.TOOLS[row['case_id']][0],'purpose':helper.TOOLS[row['case_id']][1],
                      'case_sha256':core.study.digest(core.get_case(row['case_id'])),'policy':'explicit_user_selected_local_check'}
            atomic(folder/'LOCAL_CHECK_DECISION.json',decision)
            local.check();checks=local.view()['checks']
            if checks[0]['decision']!=decision:raise ValueError('local_check_failed')
            atomic(folder/'LOCAL_CHECK_RESULT.json',checks)
            if checks[0]['result']['status']=='failed':raise ValueError('local_check_failed')
            stage='export';state['status']='exporting';event(packet,state)
            receipt={'schema_version':'traitweaver.assistant_batch_receipt.v2','case_id':row['case_id'],'approval_sha256':plan['approval_sha256'],
                     'request_sha256':entry['sha256'],'response_sha256':sha(response),'transport':state['transport'],
                     'core_request_sha256':entry['core_request_sha256'],'wire_override':{'max_output_tokens':OUTPUT_CAP},
                     'reported_model':MODEL,'reported_usage':usage,'estimated_cost_usd':usd(cost),'actual_provider_charge_usd':None,
                     'local_checks':checks,'core_provenance_limit':'Core keeps its unchanged synthetic/import-unverified schema. Direct transport is a local execution record, not independent provider authentication.',
                     'qualification':'Accepted fixed claims and three proposals, not executed research tasks or biological validation.'}
            atomic(folder/'BATCH_RECEIPT.json',receipt)
            row['status']='completed';state['cases_completed']+=1;state['elapsed_seconds']=round(time.monotonic()-start,3);event(packet,state)
            del response,decoded,record
        state.update(status='completed',active_case=None,request_elapsed_seconds=0);event(packet,state);return deepcopy(state)
    except (Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,diagnostics.SafeFailure):failure=clean_failure(exc.diagnostic)
        elif isinstance(exc,KeyboardInterrupt):failure=clean_failure({'code':'operator_interrupted','stage':'operator','dispatch_attempted':bool(active and active['status']!='pending')})
        else:
            code={'packet_validation':'source_or_payload_changed','transport':'transport_failure','usage_validation':'usage_missing_or_invalid',
                  'response_validation':'response_validation_failed','local_check':'local_check_failed','export':'local_save_failed'}[stage]
            if isinstance(exc,ValueError) and exc.args and exc.args[0] in ('usage_exceeds_allowance','synthetic_marker_on_live_reply','model_mismatch','provider_not_completed','provider_refusal','unsupported_output_or_tool_call','malformed_json'):code=exc.args[0]
            failure=clean_failure({'code':code,'stage':stage,'dispatch_attempted':bool(active and active['status']!='pending')})
        # CaptureOpener may reject a returned envelope before returning its bytes.
        # Its safe status/usage must still reach the monitor; no raw reply is saved.
        if active and active['status']=='in_flight' and 'http_status' in failure:state['responses_received']+=1
        if active and 'reported_usage' in failure:
            reported=failure['reported_usage']
            try:usage=usage_from({'usage':reported})
            except ValueError:usage=None
            account_usage(state,active,usage or reported,entry['reserved_upper_bound_usd'],settled=usage is not None)
        state.update(status='stopped_requires_review',failure=failure,elapsed_seconds=round(time.monotonic()-start,3))
        if active and active['status']!='completed':active.update(status='failed',failure=failure)
        for row in state['cases']:
            if row['status']=='pending':row['status']='skipped'
        if Decimal(state['reserved_upper_bound_usd'])>0 and not offline:state['billing_state']='possible_charge_usage_unknown'
        try:atomic(packet/'FAILURE.json',failure);event(packet,state)
        except (OSError,ValueError):pass  # Attempt lock and earlier valid state remain; never send again.
        raise BatchStopped(state) from None
    finally:key=None


def write_approval(packet,plan,bodies):
    lines=['# Four-case Muse batch — awaiting owner approval','',
           'No model request has been made and no credential has been read. The unsigned template cannot authorize a run.','',
           'POST '+DESTINATION+' · '+MODEL+' · Standard · store:false',
           'Maximum 4 independent requests, one per case; 8,192 output tokens each including reasoning. No retries, fallback, search, provider tools, polling or extra reassessment call.',
           'Proposed maximum application spend: **$'+usd(CAP)+' total**. Current authorization: **$0 / 0 calls**.',
           'Verified '+PRICING['checked_date']+': $1.25/M input, $4.25/M output ($0.15/M cached input not assumed). '+PRICING['source'],
           'Planning estimate $'+plan['planning_estimate_usd']+' uses body bytes/4 plus the full output cap; it is not an exact token quote.',
           'Conservative four-request reservation $'+plan['conservative_batch_reservation_usd']+' uses each exact UTF-8 body byte + 1,024 as an input allowance and the full output cap.',
           plan['cost_limit'],'', 'Approval SHA-256: `'+plan['approval_sha256']+'`',
           'Review expires: '+plan['expires_utc']+' (24 hours after preparation).','',
           '## Budget extension and scientific contract','',
           'The v2 adapter changes only max_output_tokens from 1,024 to 8,192. Public input, instructions and structured schema stay unchanged. This gives eightfold reasoning/output headroom, not a completion guarantee. Truncation still stops the entire batch without retry.',
           'Each entry and separate batch receipt bind the exact wire hash AND core_request_sha256. The unchanged inner assistant v1 record keeps its original scientific-request hash; it does not claim those were the larger-budget wire bytes.',
           'This new USD 0.20 proposal is additional to past attempts. The previous attempted packet remains locked and unchanged; its charge is not assumed zero. No owner grant or attempt markers exist in this fresh packet.',
           '## Exact public/synthetic payloads','',
           'Only the four fixed screened cases enter these bodies. No notes, owner studies, private research, personal data, credentials, local paths, raw provider replies or real packets. Model IDs expand locally into all required claims/limits and three complete authored next actions. This is bounded prioritization, not unrestricted discovery.','']
    for entry in plan['requests']:
        lines+=['- ['+entry['case_id']+']('+entry['file']+') — '+str(entry['bytes'])+' exact bytes; SHA-256 `'+entry['sha256']+'`; reserved $'+entry['reserved_upper_bound_usd']+'.']
    lines+=['','## Monitoring and stopping','',
            '`STATUS.json` and `MONITOR.html` show stage, heartbeat, active case, elapsed time, started/received/accepted/completed counts, known token usage/cost estimates, reserved uncertain charges and safe failures. `EVENTS.jsonl` is append-only. No raw reply, reasoning text, provider ID, cookie/header, exception string or key is retained.',
            'Second terminal: `python3 -B muse_assistant_batch.py monitor --packet .` from this packet. It reads local files every two seconds and makes no provider requests. One snapshot: `... status --packet .`.',
            'Stop: Ctrl-C in the run terminal, or `python3 -B muse_assistant_batch.py stop --packet .`. Stop prevents further sends; it cannot revoke an already submitted request or guarantee no charge. Deadline: 120 seconds per request. Unknown usage retains the reservation. A stale heartbeat flags possible interruption, never safe resumption.',
            'Returned-but-rejected HTTP envelopes still increment responses observed and retain reported numeric usage/cost. Complete valid input/output counts release that request reservation even when the answer is rejected; missing/partial/invalid usage keeps it. No accepted claims or local checks follow from accounting.',
            'Every attempted packet is permanently locked against rerun/resume, with one atomic POST marker per case. Approval also binds this exact local packet location; moving/copying it cannot authorize another run. Partial valid results remain. Any failure stops all subsequent cases. A new attempt requires a fresh reviewed packet and separate approval.',
            'Accepted per-case outputs: unchanged assistant JSON/text plus a separate direct-transport/local-audit receipt. Claims and proposals are validated locally; reviewer judgment and actual provider billing remain unverified.',
            '', '## How authorization will work','',
            'Only after chat approval of this exact batch hash and $0.20 ceiling may OWNER_APPROVAL.json be written with approved:true and the exact fields in UNSIGNED_APPROVAL.json. No such approval is created during preparation. This is a new ceiling, additional to past runs; unresolved historical billing is not silently counted as zero.',
            'Then the owner runs START_REVIEWED_BATCH.py in a real terminal. Both starter and runner refuse non-interactive live sending before credential access, attempt markers or execution logs, even if a key is preset. Only then can a hidden prompt read MODEL_API_KEY; it is never saved.',
            'Standard mode is not Contributor mode. store:false controls response storage, not a blanket zero-retention guarantee. No account balance, billing or token-count API is queried. No provider compatibility or scientific-reliability claim follows from offline tests.','']
    private_text(packet/'APPROVAL.md','\n'.join(lines))
    page='<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Review four-case Muse batch</title><style>body{max-width:1000px;margin:40px auto;padding:0 24px;background:#02070a;color:#ecf5fb;font:16px/1.7 system-ui}h1,h2,a{color:#83d2fa}pre{background:#0b1c28;padding:20px;overflow-wrap:anywhere;white-space:pre-wrap}code{overflow-wrap:anywhere}summary{cursor:pointer;color:#fcad93}</style>'
    page+='<h1>Four research reviews · awaiting approval</h1><p>No model call or credential access. Four requests, '+MODEL+', Standard, 8,192 output tokens each; no retry/fallback. Proposed total ceiling $0.20. No sending authorization exists.</p>'
    page+='<p>POST '+DESTINATION+' · <code>store:false</code>. Current pricing: $1.25/M input and $4.25/M output, verified '+PRICING['checked_date']+' at <a href="'+PRICING['source']+'">Meta pricing</a>.</p>'
    page+='<p>Planning estimate $'+plan['planning_estimate_usd']+'; conservative reservation $'+plan['conservative_batch_reservation_usd']+'. <b>Application guard, not a provider/account-wide hard billing cap.</b> Unknown usage stops the batch and retains reserved cost.</p><p>Approval hash: <code>'+plan['approval_sha256']+'</code></p>'
    page+='<p><a href="APPROVAL.md">Full approval and monitoring plan</a> · <a href="PUBLIC_BATCH.json">Pinned manifest</a> · <a href="MONITOR.html">Local monitor</a></p>'
    for entry,raw in zip(plan['requests'],bodies):
        body=json.loads(raw);decoded=dict(body,input=json.loads(body['input']))
        page+='<h2>'+entry['case_id']+'</h2><p><a href="'+entry['file']+'">Exact HTTP body</a> · '+str(entry['bytes'])+' bytes · SHA-256 <code>'+entry['sha256']+'</code></p>'
        page+='<details><summary>Read public input and complete schema</summary><pre>'+html.escape(json.dumps(decoded,indent=2,ensure_ascii=False))+'</pre></details>'
        page+='<details><summary>Exact canonical body bytes</summary><pre>'+html.escape(raw.decode())+'</pre></details>'
    page+='<h2>Budget extension</h2><p>Only max_output_tokens changes, from 1,024 to 8,192. The admitted evidence, instructions and structured schema remain unchanged. Eightfold headroom is not a completion guarantee. The v2 batch receipt binds the exact wire hash and original core request hash separately. The $0.20 proposal is additional to historical attempts; their billing is not assumed zero.</p>'
    page+='<h2>What will be retained</h2><p>Accepted source-linked review JSON/text, safe numeric usage, immutable request/response fingerprints and local audit receipts. No raw provider messages, reasoning, credentials, response cookies or arbitrary headers. Model proposals cannot execute research actions.</p><h2>Monitor and stop</h2><p>Local heartbeat and stage snapshots, separate-terminal monitor, 120-second deadline per request, stop marker/Ctrl-C and permanent no-retry lock. Stop cannot revoke an in-flight request or eliminate possible charges. Four pending cases are not four completed live reviews.</p>'
    private_text(packet/'APPROVAL.html',page)


class SafeParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,'Invalid arguments. Use --help; never pass a credential as an argument. No send authorized.\n')


def main(argv=None):
    parser=SafeParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--app',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    for name in ('status','monitor','stop','run'):
        p=sub.add_parser(name);p.add_argument('--packet',required=True,type=Path)
        if name=='run':p.add_argument('--send',action='store_true')
        if name=='monitor':p.add_argument('--once',action='store_true',help='One local snapshot rather than following')
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare':
            p=prepare(args.app,args.output);print(canonical({'status':'awaiting_approval','approval_sha256':p['approval_sha256'],'maximum_spend_proposed_usd':usd(CAP),'new_live_requests':0}));return 0
        if args.command=='stop':
            packet=safe_path(args.packet);status(packet)
            try:
                fd=os.open(packet/'STOP.requested',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
            except FileExistsError:pass
            print('Local stop requested. No provider cancellation call; possible in-flight usage remains uncertain.');return 0
        if args.command in ('status','monitor'):
            while True:
                view=status(args.packet)
                if args.command=='status':print(json.dumps(view,indent=2),flush=True);return 0
                print(view['updated_utc']+' | '+view['transport']+' | '+view['status']+' | '+str(view['active_case'] or 'no active case')+' | '+str(view['requests_started'])+'/4 started, '+str(view['responses_accepted'])+' accepted, '+str(view['responses_received'])+' HTTP/returned observed | elapsed '+str(view['elapsed_seconds'])+'s | estimated $'+view['observed_token_charge_estimate_usd']+' | unsettled $'+view['reserved_upper_bound_usd']+' (missing usage is not zero)',flush=True)
                if view['failure']:print(canonical(view['failure']),flush=True)
                if args.once or view['status'] in ('completed','stopped_requires_review') or view['monitor_observation']['possibly_interrupted']:return 0
                time.sleep(2)
        result=run(args.packet,allow_live=args.send);print(canonical(result));return 0
    except BatchStopped as exc:
        print('Stopped: '+canonical(exc.state['failure'])+'. Inspect STATUS.json/MONITOR.html. No retries.',file=sys.stderr);return 1
    except KeyboardInterrupt:
        if args.command=='monitor':print('Monitor closed. The running batch is unaffected; use the stop command to prevent further requests.');return 0
        print('Interrupted. Inspect STATUS.json; no implicit retry.',file=sys.stderr);return 2
    except Exception:
        print('Local approval, terminal, credential or packet check failed. No implicit send/retry. Inspect the local packet; never paste a key.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
