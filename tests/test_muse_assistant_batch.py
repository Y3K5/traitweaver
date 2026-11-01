"""Four-case approval/spend/monitor runner: fake transport, never sockets or keys."""
from copy import deepcopy
from decimal import Decimal
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('muse_assistant_batch_test',ROOT/'tools/muse_assistant_batch.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


class Fake:
    def __init__(self,mutate=None,after=None):self.calls=[];self.mutate=mutate;self.after=after;self.raw=[]
    def __call__(self,core,raw,key):
        if key is not None:raise AssertionError('Offline fake must receive no credential')
        body=json.loads(raw);cid=json.loads(body['input'])['case_id'];self.calls.append(cid)
        reply=core.synthetic_reply(cid)
        # Real-shaped nested usage, identifiers and reasoning are deliberately fake.
        reply.update(id='SYNTHETIC_PRIVATE_PROVIDER_IDENTIFIER',usage={'input_tokens':120,'output_tokens':60,'total_tokens':180,
                     'input_tokens_details':{'cached_tokens':10},'output_tokens_details':{'reasoning_tokens':20}})
        reply['output'].insert(0,{'type':'reasoning','summary':[{'text':'SYNTHETIC_RAW_REASONING_CANARY'}]})
        if self.mutate:self.mutate(reply,cid)
        out=b.canonical(reply).encode();self.raw.append(out)
        if self.after:self.after(cid)
        return out


class EnvelopeFake:
    """Exercise the actual rejecting HTTP reader with synthetic response bytes."""
    def __init__(self,usage=None,*,missing=False,status='incomplete',fail_case=0):
        self.calls=[];self.usage=usage;self.missing=missing;self.status=status;self.fail_case=fail_case

    def __call__(self,core,raw,key):
        if key is not None:raise AssertionError('Offline fake must receive no credential')
        cid=json.loads(json.loads(raw)['input'])['case_id'];self.calls.append(cid)
        if len(self.calls)-1!=self.fail_case:return Fake()(core,raw,key)
        reply={'model':b.MODEL,'status':self.status,'incomplete_details':{'reason':'max_output_tokens'},
               'id':'SYNTHETIC_PROVIDER_ID_NOT_FOR_LOGS','output':[{'type':'reasoning','summary':[{'text':'SYNTHETIC_PRIVATE_REASONING'}]}]}
        if not self.missing:reply['usage']=self.usage
        class Response(io.BytesIO):
            status=200
        opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b.canonical(reply).encode())})()
        spec=type('Spec',(),{'DESTINATION':b.DESTINATION,'MODEL':b.MODEL,'MAX_RESPONSE':core.MAX_BYTES,'study':core.study})()
        reader=b.diagnostics.CaptureOpener(spec,opener)
        request=b.urllib.request.Request(b.DESTINATION,data=raw,method='POST')
        with reader.open(request,timeout=1) as response:return response.read(core.MAX_BYTES+1)


class AssistantBatchTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket',side_effect=AssertionError('Tests prohibit sockets'));guard.start();self.addCleanup(guard.stop)
        tmp=tempfile.TemporaryDirectory(prefix='traitweaver-four-case-offline-');self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name);self.packet=self.folder/'packet';self.plan=b.prepare(ROOT,self.packet);self.core,self.helper=b.configure(ROOT)

    def approve(self,**changes):
        value=b.approval_for(self.plan,True);value.update(changes);b.atomic(self.packet/'OWNER_APPROVAL.json',value)

    def execute(self,fake=None):
        self.approve();return b.run(self.packet,fake_transport=fake or Fake())

    def fingerprints(self):return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.packet.iterdir() if p.is_file()}

    def rehash(self,plan):
        plan['approval_sha256']=b.digest({k:v for k,v in plan.items() if k!='approval_sha256'})
        control=b.read(self.packet/'LOCAL_CONTROL.json');control['approval_sha256']=plan['approval_sha256']
        b.atomic(self.packet/'PUBLIC_BATCH.json',plan);b.atomic(self.packet/'LOCAL_CONTROL.json',control)
        b.atomic(self.packet/'UNSIGNED_APPROVAL.json',b.approval_for(plan));self.plan=plan

    def test_prepare_exact_four_bodies_and_explicit_zero_authorization(self):
        self.assertEqual(self.plan['max_requests'],4);self.assertEqual(self.plan['maximum_spend_usd'],'0.20')
        self.assertEqual(self.plan['conservative_batch_reservation_usd'],'0.19129400')
        self.assertEqual(self.plan['planning_estimate_usd'],'0.1509915000')
        for entry,cid in zip(self.plan['requests'],b.CASES):
            raw=(self.packet/entry['file']).read_bytes();self.assertEqual(raw,b.canonical(b.request_for(self.core,cid)[0]).encode())
            original=self.core.prepare(cid)['body'];wire=json.loads(raw)
            self.assertEqual(wire,dict(original,max_output_tokens=8192));self.assertEqual(original['max_output_tokens'],1024)
            self.assertEqual(entry['core_request_sha256'],self.core.prepare(cid)['request_sha256'])
            self.assertEqual(entry['sha256'],b.sha(raw));self.assertEqual(entry['input_token_allowance'],len(raw)+1024)
            self.assertNotIn(b'/Users/',raw);self.assertNotIn(b'MODEL_API_KEY',raw);self.assertNotIn(b'authorization',raw.lower())
            self.assertFalse(json.loads(raw)['store']);self.assertNotIn('tools',json.loads(raw))
        self.assertFalse(b.read(self.packet/'UNSIGNED_APPROVAL.json')['approved'])
        self.assertFalse((self.packet/'OWNER_APPROVAL.json').exists());self.assertFalse((self.packet/'BATCH.started').exists())
        status=b.status(self.packet);self.assertEqual(status['requests_started'],0);self.assertEqual(status['maximum_spend_authorized_usd'],'0')

    def test_prepare_status_and_monitor_never_read_credentials_or_call_transport(self):
        with patch.object(b,'credential',side_effect=AssertionError('No key read')),patch.object(b,'real_transport',side_effect=AssertionError('No network')):
            b.status(self.packet);self.assertEqual(b.main(['status','--packet',str(self.packet)]),0)
            self.assertEqual(b.main(['monitor','--once','--packet',str(self.packet)]),0)

    def test_default_live_disabled_draft_or_wrong_approval_stop_before_markers(self):
        self.approve();before=self.fingerprints()
        with self.assertRaises(ValueError):b.run(self.packet)
        self.assertEqual(self.fingerprints(),before)
        for changes in ({'approved':False},{'approval_sha256':'0'*64},{'maximum_spend_usd':'0.11'},
                        {'max_requests':5},{'model':'other'},{'retries':1},{'fallback':True},{'extra':'unreviewed'}):
            self.approve(**changes)
            with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
            self.assertFalse((self.packet/'BATCH.started').exists())

    def test_both_live_entries_require_terminal_even_with_preset_fake_key(self):
        self.approve();before=self.fingerprints()
        with patch.object(b.sys.stdin,'isatty',return_value=False),patch.object(b,'credential',side_effect=AssertionError('Must not read key')):
            with self.assertRaises(ValueError):b.run(self.packet,allow_live=True)
        result=subprocess.run([sys.executable,'-B',str(self.packet/'START_REVIEWED_BATCH.py')],input='',capture_output=True,text=True,
                              env={'PATH':'/usr/local/bin:/usr/bin:/bin','MODEL_API_KEY':'SYNTHETIC_PRESET_KEY_CANARY'},cwd=self.folder)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('SYNTHETIC_PRESET_KEY_CANARY',result.stdout+result.stderr)
        self.assertEqual(self.fingerprints(),before);self.assertFalse((self.packet/'BATCH.started').exists())

    def test_cli_unknown_secret_argument_is_not_echoed(self):
        r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/muse_assistant_batch.py'),'run','--packet',str(self.packet),'--key','SYNTHETIC_ARG_CANARY'],capture_output=True,text=True,env={'PATH':'/usr/local/bin:/usr/bin:/bin'})
        self.assertNotEqual(r.returncode,0);self.assertNotIn('SYNTHETIC_ARG_CANARY',r.stdout+r.stderr)

    def test_fake_transport_cannot_be_labelled_live(self):
        self.approve()
        with self.assertRaises(ValueError):b.run(self.packet,allow_live=True,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_whitespace_body_tamper_code_and_pricing_tamper_rejected(self):
        self.approve();entry=self.plan['requests'][0];p=self.packet/entry['file'];raw=p.read_bytes();p.write_bytes(raw+b'\n')
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        p.write_bytes(raw)
        p=self.packet/'muse_diagnostics.py';raw=p.read_bytes();p.write_bytes(raw+b'\n')
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        p.write_bytes(raw);price=b.read(self.packet/'PRICING.json');price['input_usd_per_million']='0';b.atomic(self.packet/'PRICING.json',price)
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_copied_packet_cannot_reuse_same_approval(self):
        self.approve();copy=self.folder/'copy';shutil.copytree(self.packet,copy)
        with self.assertRaises(ValueError):b.run(copy,fake_transport=Fake())
        self.assertFalse((copy/'BATCH.started').exists())

    def test_expired_review_and_rehashed_scope_change_are_refused(self):
        plan=deepcopy(self.plan);old=datetime.now(timezone.utc)-timedelta(days=2)
        plan['prepared_utc']=old.isoformat();plan['expires_utc']=(old+timedelta(hours=24)).isoformat();self.rehash(plan);self.approve()
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        plan['max_requests']=5;self.rehash(plan);self.approve()
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_preexisting_stop_blocks_before_any_key_or_attempt(self):
        self.approve();(self.packet/'STOP.requested').touch()
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_four_successes_keep_original_response_hash_usage_and_distinct_fake_labels(self):
        fake=Fake();result=self.execute(fake)
        self.assertEqual(result['status'],'completed');self.assertEqual(fake.calls,list(b.CASES))
        self.assertEqual(result['responses_accepted'],4);self.assertEqual(result['cases_completed'],4)
        self.assertEqual(result['transport'],'offline_fake_transport');self.assertEqual(Decimal(result['reserved_upper_bound_usd']),0)
        self.assertIsNone(result['actual_provider_charge_usd'])
        for cid,raw in zip(b.CASES,fake.raw):
            p=b.read(self.packet/cid/'assistant-review.json');record=self.core.validate_package(p)
            self.assertEqual(record['receipt']['response_sha256'],b.sha(raw));self.assertEqual(record['receipt']['provenance'],'synthetic_fixture')
            self.assertEqual(record['receipt']['reported_usage'],{'input_tokens':120,'output_tokens':60,'total_tokens':180})
            receipt=b.read(self.packet/cid/'BATCH_RECEIPT.json');self.assertEqual(receipt['reported_usage']['reasoning_tokens'],20)
            self.assertEqual(receipt['reported_usage']['cached_tokens'],10);self.assertEqual(len(record['actions']),3)
            self.assertEqual(b.read(self.packet/cid/'LOCAL_CHECK_RESULT.json')[0]['decision'],b.read(self.packet/cid/'LOCAL_CHECK_DECISION.json'))
        # Provider IDs, raw reasoning and headers must never survive, even in errors/monitoring.
        all_text='\n'.join(p.read_text() for p in self.packet.rglob('*') if p.is_file())
        for canary in ('SYNTHETIC_PRIVATE_PROVIDER_IDENTIFIER','SYNTHETIC_RAW_REASONING_CANARY'):self.assertNotIn(canary,all_text)

    def test_decision_is_durable_before_registered_local_check_runs(self):
        original=self.helper.run_local_check;seen=[]
        def check(cid):
            self.assertTrue((self.packet/cid/'LOCAL_CHECK_DECISION.json').is_file());seen.append(cid);return original(cid)
        with patch.object(self.helper,'run_local_check',side_effect=check):self.execute()
        self.assertEqual(seen,list(b.CASES))

    def test_duplicate_attempt_is_permanently_refused_without_more_fake_calls(self):
        fake=Fake();self.execute(fake)
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=fake)
        self.assertEqual(len(fake.calls),4)

    def test_simultaneous_starts_dispatch_one_batch_only(self):
        self.approve();fake=Fake();results=[]
        def runner():
            try:results.append(b.run(self.packet,fake_transport=fake)['status'])
            except (ValueError,OSError):results.append('refused')
        first=threading.Thread(target=runner);second=threading.Thread(target=runner);first.start();second.start();first.join();second.join()
        self.assertEqual(sorted(results),['completed','refused']);self.assertEqual(len(fake.calls),4)

    def test_source_or_payload_drift_after_first_case_stops_remaining_sends(self):
        def alter(cid):
            if cid==b.CASES[0]:(self.packet/self.plan['requests'][1]['file']).write_text('{}')
        fake=Fake(after=alter)
        with self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        self.assertEqual(fake.calls,[b.CASES[0]]);self.assertEqual(exc.exception.state['cases_completed'],1)
        self.assertEqual(exc.exception.state['failure']['code'],'source_or_payload_changed')
        self.assertTrue((self.packet/b.CASES[0]/'assistant-review.json').exists())

    def test_timeout_or_sensitive_transport_exception_stops_with_unknown_charge_and_no_leak(self):
        self.approve()
        def failure(*args):raise TimeoutError('SYNTHETIC_EXCEPTION_SECRET Cookie: do-not-log')
        with self.assertRaises(b.BatchStopped) as exc:b.run(self.packet,fake_transport=failure)
        self.assertEqual(exc.exception.state['requests_started'],1);self.assertEqual(exc.exception.state['responses_received'],0)
        self.assertGreater(Decimal(exc.exception.state['reserved_upper_bound_usd']),0)
        self.assertIsNone(exc.exception.state['actual_provider_charge_usd'])
        for p in (self.packet/'FAILURE.json',self.packet/'STATUS.json',self.packet/'EVENTS.jsonl',self.packet/'MONITOR.html'):
            self.assertNotIn('SYNTHETIC_EXCEPTION_SECRET',p.read_text());self.assertNotIn('do-not-log',p.read_text())

    def test_missing_usage_is_not_zero_and_no_later_case_runs(self):
        fake=Fake(mutate=lambda r,c:r.pop('usage'))
        with self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        state=exc.exception.state;self.assertEqual(len(fake.calls),1);self.assertIsNone(state['cases'][0]['reported_usage'])
        self.assertGreater(Decimal(state['reserved_upper_bound_usd']),0);self.assertEqual(state['failure']['code'],'usage_missing_or_invalid')

    def test_zero_usage_and_missing_optional_counts_remain_distinct(self):
        def zero(r,c):r['usage']={'input_tokens':0,'output_tokens':0}
        result=self.execute(Fake(mutate=zero));u=result['cases'][0]['reported_usage']
        self.assertEqual(u['input_tokens'],0);self.assertIsNone(u['reasoning_tokens']);self.assertIsNone(u['cached_tokens'])
        self.assertNotIn('total_tokens',u);self.assertEqual(Decimal(result['observed_token_charge_estimate_usd']),0)

    def test_usage_bool_negative_total_and_reasoning_inconsistency_are_rejected(self):
        variants=[{'input_tokens':True,'output_tokens':1},{'input_tokens':-1,'output_tokens':1},
                  {'input_tokens':1,'output_tokens':1,'total_tokens':3},
                  {'input_tokens':1,'output_tokens':1,'output_tokens_details':{'reasoning_tokens':2}},
                  {'input_tokens':1,'output_tokens':1,'input_tokens_details':{'cached_tokens':2}}]
        for u in variants:
            with self.assertRaises(ValueError):b.usage_from({'usage':u})

    def test_over_allowance_usage_is_reported_then_stops_before_another_request(self):
        def exceed(r,c):r['usage']={'input_tokens':120,'output_tokens':b.OUTPUT_CAP+1,'total_tokens':120+b.OUTPUT_CAP+1}
        fake=Fake(mutate=exceed)
        with self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        self.assertEqual(fake.calls,[b.CASES[0]]);state=exc.exception.state
        self.assertEqual(state['failure']['code'],'usage_exceeds_allowance');self.assertEqual(state['cases'][0]['reported_usage']['output_tokens'],b.OUTPUT_CAP+1)
        self.assertGreater(Decimal(state['observed_token_charge_estimate_usd']),0)

    def test_invalid_claim_or_action_cannot_execute_a_check(self):
        def invalid(r,c):
            p=json.loads(r['output'][1]['content'][0]['text']);p['prioritized_action_ids'][0]='UNAVAILABLE_ACTION';r['output'][1]['content'][0]['text']=b.canonical(p)
        fake=Fake(mutate=invalid)
        with patch.object(self.helper,'run_local_check',side_effect=AssertionError('Rejected model must not execute')),self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        self.assertEqual(exc.exception.state['responses_accepted'],0);self.assertEqual(len(fake.calls),1)
        self.assertEqual(exc.exception.state['failure']['code'],'response_validation_failed')

    def test_refusal_wrong_model_incomplete_and_tool_calls_are_distinct_safe_failures(self):
        raw=Fake()(self.core,b.canonical(self.core.prepare(b.CASES[0])['body']).encode(),None)
        variants=[(lambda r:r.update(model='other'),'model_mismatch'),(lambda r:r.update(status='incomplete'),'provider_not_completed'),
                  (lambda r:r.update(output=[{'type':'function_call','name':'unavailable'}]),'unsupported_output_or_tool_call'),
                  (lambda r:r.update(output=[{'type':'message','content':[{'type':'refusal','refusal':'SYNTHETIC_REFUSAL_PRIVATE'}]}]),'provider_refusal')]
        for mutate,code in variants:
            reply=json.loads(raw);mutate(reply)
            with self.assertRaisesRegex(ValueError,code):b.adapt_reply(self.core,b.CASES[0],b.canonical(reply).encode(),self.plan['requests'][0]['sha256'],offline=True)

    def test_live_adapter_rejects_synthetic_marker_and_does_not_relabel_core_authenticity(self):
        raw=Fake()(self.core,b.canonical(self.core.prepare(b.CASES[0])['body']).encode(),None)
        with self.assertRaisesRegex(ValueError,'synthetic_marker_on_live_reply'):b.adapt_reply(self.core,b.CASES[0],raw,self.plan['requests'][0]['sha256'])
        value=json.loads(raw);value.pop('traitweaver_synthetic');raw=b.canonical(value).encode()
        record,u=b.adapt_reply(self.core,b.CASES[0],raw,self.plan['requests'][0]['sha256'])
        self.assertEqual(record['receipt']['provenance'],'owner_imported_reply_authenticity_unverified');self.assertEqual(record['receipt']['response_sha256'],b.sha(raw))

    def test_hard_deadline_and_stop_marker_do_not_submit_another_request(self):
        self.approve();state=b.fresh_status(self.plan);state.update(status='in_flight',transport='offline_fake_transport',requests_started=1,active_case=b.CASES[0])
        release=threading.Event()
        def slow(*args):release.wait(2);return b'{}'
        try:
            with self.assertRaises(b.diagnostics.SafeFailure) as exc:b.wait_transport(self.packet,state,slow,self.core,b'{}',None,time.monotonic(),deadline=.02)
            self.assertEqual(exc.exception.diagnostic['code'],'deadline_exceeded')
        finally:release.set()
        (self.packet/'STOP.requested').touch()
        sent=[]
        with self.assertRaises(b.diagnostics.SafeFailure) as exc:b.wait_transport(self.packet,state,lambda *a:sent.append(1),self.core,b'{}',None,time.monotonic())
        self.assertEqual(exc.exception.diagnostic['code'],'operator_stop')
        self.assertEqual(sent,[])

    def test_partial_export_failure_preserves_prior_valid_case_and_lock(self):
        self.approve();real=self.core.export_bundle
        def save(record,destination):
            if record['case_id']==b.CASES[1]:raise OSError('SYNTHETIC_FILESYSTEM_PRIVATE_DETAIL')
            return real(record,destination)
        fake=Fake()
        with patch.object(self.core,'export_bundle',side_effect=save),self.assertRaises(b.BatchStopped) as exc:b.run(self.packet,fake_transport=fake)
        self.assertEqual(len(fake.calls),2);self.assertEqual(exc.exception.state['cases_completed'],1)
        self.core.validate_package(b.read(self.packet/b.CASES[0]/'assistant-review.json'))
        self.assertTrue((self.packet/'BATCH.started').exists());self.assertNotIn('SYNTHETIC_FILESYSTEM_PRIVATE_DETAIL',(self.packet/'FAILURE.json').read_text())

    def test_interrupted_atomic_save_preserves_earlier_valid_file(self):
        path=self.packet/'test-state.json';b.atomic(path,{'version':1})
        with patch.object(b.os,'replace',side_effect=OSError('Synthetic interrupted save')),self.assertRaises(OSError):b.atomic(path,{'version':2})
        self.assertEqual(b.read(path),{'version':1});self.assertFalse(any(self.packet.glob('.*.pending')))

    def test_existing_pending_file_and_symlink_outputs_are_not_removed_or_followed(self):
        path=self.packet/'test-state.json';pending=path.with_name('.'+path.name+'.'+str(os.getpid())+'.pending')
        pending.write_text('Synthetic earlier pending record')
        with self.assertRaises(FileExistsError):b.atomic(path,{'version':2})
        self.assertEqual(pending.read_text(),'Synthetic earlier pending record')
        other=self.folder/'other.txt';other.write_text('Synthetic original record');link=self.packet/'linked.txt';link.symlink_to(other)
        with self.assertRaises(ValueError):b.private_text(link,'New text')
        self.assertEqual(other.read_text(),'Synthetic original record')

    def test_heartbeat_is_written_while_one_slow_request_is_in_flight(self):
        state=b.fresh_status(self.plan);state.update(status='in_flight',transport='offline_fake_transport',requests_started=1,active_case=b.CASES[0])
        def slow(*args):time.sleep(1.3);return b'{}'
        raw=b.wait_transport(self.packet,state,slow,self.core,b'{}',None,time.monotonic(),deadline=2)
        self.assertEqual(raw,b'{}');self.assertGreater(b.read(self.packet/'STATUS.json')['request_elapsed_seconds'],.9)

    def test_noninteractive_send_cli_has_no_marker_logs_or_credential_access(self):
        self.approve();before=self.fingerprints()
        result=subprocess.run([sys.executable,'-B',str(self.packet/'muse_assistant_batch.py'),'run','--send','--packet',str(self.packet)],
                              input='',capture_output=True,text=True,env={'PATH':'/usr/local/bin:/usr/bin:/bin','MODEL_API_KEY':'SYNTHETIC_KEY_MUST_NOT_READ'})
        self.assertNotEqual(result.returncode,0);self.assertNotIn('SYNTHETIC_KEY_MUST_NOT_READ',result.stdout+result.stderr)
        self.assertEqual(self.fingerprints(),before);self.assertFalse((self.packet/'BATCH.started').exists())

    def test_monitor_rejects_unknown_private_fields_and_detects_stale_heartbeat(self):
        value=b.read(self.packet/'STATUS.json');value['private_note']='SYNTHETIC_PRIVATE_MONITOR_CANARY';b.atomic(self.packet/'STATUS.json',value)
        with self.assertRaises(ValueError):b.status(self.packet)
        value=b.fresh_status(self.plan);value.update(status='in_flight',transport='offline_fake_transport',updated_utc=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
        b.atomic(self.packet/'STATUS.json',value);view=b.status(self.packet)
        self.assertTrue(view['monitor_observation']['possibly_interrupted']);self.assertFalse(view['monitor_observation']['retry_permitted'])

    def test_private_outputs_have_restrictive_parent_and_control_permissions(self):
        self.assertEqual(self.packet.stat().st_mode&0o777,0o700)
        for name in ('PUBLIC_BATCH.json','LOCAL_CONTROL.json','STATUS.json','START_REVIEWED_BATCH.py'):
            self.assertEqual((self.packet/name).stat().st_mode&0o777,0o600)


    def test_original_incomplete_http200_accounts_usage_before_rejection(self):
        fake=EnvelopeFake({'input_tokens':3378,'output_tokens':1024})
        with patch.object(self.helper,'run_local_check',side_effect=AssertionError('No rejected answer executes')),self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        state=exc.exception.state;row=state['cases'][0]
        self.assertEqual(state['responses_received'],1);self.assertEqual(state['responses_accepted'],0)
        self.assertEqual(state['observed_token_charge_estimate_usd'],'0.0085745')
        self.assertEqual(row['estimated_cost_usd'],'0.0085745');self.assertEqual(row['reported_usage']['output_tokens'],1024)
        self.assertEqual(row['usage_state'],'complete_counts');self.assertTrue(row['reservation_released'])
        self.assertEqual(Decimal(state['reserved_upper_bound_usd']),0);self.assertIsNone(state['actual_provider_charge_usd'])
        self.assertEqual(state['failure']['code'],'provider_not_completed')
        self.assertEqual(fake.calls,[b.CASES[0]]);self.assertEqual([r['status'] for r in state['cases']],['failed','skipped','skipped','skipped'])
        self.assertEqual(b.read(self.packet/'STATUS.json'),state)
        self.assertIn('$0.0085745',(self.packet/'MONITOR.html').read_text())
        self.assertFalse((self.packet/b.CASES[0]).exists())
        for name in ('MONITOR.html','STATUS.json','EVENTS.jsonl','FAILURE.json'):
            text=(self.packet/name).read_text()
            self.assertNotIn('SYNTHETIC_PROVIDER_ID_NOT_FOR_LOGS',text);self.assertNotIn('SYNTHETIC_PRIVATE_REASONING',text)
        before=self.fingerprints()
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=fake)
        self.assertEqual(self.fingerprints(),before);self.assertEqual(len(fake.calls),1)

    def test_new_output_cap_exhaustion_is_accounted_and_still_not_accepted(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake({'input_tokens':3378,'output_tokens':8192}))
        s=exc.exception.state
        self.assertEqual(s['responses_received'],1);self.assertEqual(s['cases_completed'],0)
        self.assertEqual(s['observed_token_charge_estimate_usd'],'0.0390385')
        self.assertEqual(s['failure']['incomplete_reason'],'max_output_tokens')

    def test_incomplete_without_usage_keeps_reservation_and_unknown_cost(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake(missing=True))
        s=exc.exception.state;r=s['cases'][0]
        self.assertEqual(s['responses_received'],1);self.assertIsNone(r['reported_usage']);self.assertIsNone(r['estimated_cost_usd'])
        self.assertEqual(r['usage_state'],'unavailable');self.assertFalse(r['reservation_released'])
        self.assertEqual(s['reserved_upper_bound_usd'],self.plan['requests'][0]['reserved_upper_bound_usd'])
        self.assertIn('cost unknown',(self.packet/'MONITOR.html').read_text())

    def test_incomplete_partial_usage_keeps_zero_distinct_from_missing(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake({'input_tokens':0}))
        s=exc.exception.state;r=s['cases'][0]
        self.assertEqual(r['reported_usage'],{'input_tokens':0});self.assertIsNone(r['estimated_cost_usd'])
        self.assertEqual(r['usage_state'],'partial_or_invalid');self.assertFalse(r['reservation_released'])
        self.assertGreater(Decimal(s['reserved_upper_bound_usd']),0)
        self.assertIn('0 input / unknown output',(self.packet/'MONITOR.html').read_text())

    def test_incomplete_zero_pair_is_known_zero_not_unknown(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake({'input_tokens':0,'output_tokens':0}))
        r=exc.exception.state['cases'][0]
        self.assertEqual(Decimal(r['estimated_cost_usd']),0);self.assertEqual(r['usage_state'],'complete_counts')
        self.assertTrue(r['reservation_released']);self.assertEqual(exc.exception.state['responses_accepted'],0)

    def test_incomplete_bool_count_is_not_silently_zero(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake({'input_tokens':True,'output_tokens':1024}))
        r=exc.exception.state['cases'][0]
        self.assertEqual(r['reported_usage'],{'output_tokens':1024});self.assertIsNone(r['estimated_cost_usd'])
        self.assertFalse(r['reservation_released'])

    def test_second_case_incomplete_keeps_first_package_and_sums_usage_once(self):
        fake=EnvelopeFake({'input_tokens':3378,'output_tokens':1024},fail_case=1)
        with self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        s=exc.exception.state
        self.assertEqual(s['responses_received'],2);self.assertEqual(s['responses_accepted'],1);self.assertEqual(s['cases_completed'],1)
        expected=b.charge({'input_tokens':120,'output_tokens':60})+Decimal('0.0085745')
        self.assertEqual(Decimal(s['observed_token_charge_estimate_usd']),expected)
        self.assertEqual(len(fake.calls),2);self.core.validate_package(b.read(self.packet/b.CASES[0]/'assistant-review.json'))
        self.assertFalse((self.packet/b.CASES[1]).exists());self.assertEqual(Decimal(s['reserved_upper_bound_usd']),0)

    def test_accounting_is_idempotent_and_monitor_refuses_inconsistent_totals(self):
        s=b.fresh_status(self.plan);r=s['cases'][0];reserve=self.plan['requests'][0]['reserved_upper_bound_usd']
        s['reserved_upper_bound_usd']=reserve
        for _ in range(2):b.account_usage(s,r,{'input_tokens':3378,'output_tokens':1024},reserve,settled=True)
        self.assertEqual(s['observed_token_charge_estimate_usd'],'0.0085745');self.assertEqual(Decimal(s['reserved_upper_bound_usd']),0)
        b.valid_status(s)
        s['observed_token_charge_estimate_usd']='0'
        with self.assertRaises(ValueError):b.valid_status(s)

    def test_invalid_total_preserves_safe_counts_but_does_not_release_reservation(self):
        fake=Fake(mutate=lambda r,c:r.update(usage={'input_tokens':120,'output_tokens':60,'total_tokens':0}))
        with self.assertRaises(b.BatchStopped) as exc:self.execute(fake)
        s=exc.exception.state;r=s['cases'][0]
        self.assertEqual(r['reported_usage'],{'input_tokens':120,'output_tokens':60})
        self.assertEqual(r['usage_state'],'partial_or_invalid');self.assertFalse(r['reservation_released'])
        self.assertGreater(Decimal(s['reserved_upper_bound_usd']),0);self.assertGreater(Decimal(s['observed_token_charge_estimate_usd']),0)
        self.assertEqual(s['failure']['code'],'usage_missing_or_invalid')

    def test_wire_budget_hash_and_original_core_hash_are_separate_and_bound(self):
        fake=Fake();s=self.execute(fake)
        for row in self.plan['requests']:
            cid=row['case_id'];record=self.core.validate_package(b.read(self.packet/cid/'assistant-review.json'))
            receipt=b.read(self.packet/cid/'BATCH_RECEIPT.json')
            self.assertEqual(record['request_sha256'],row['core_request_sha256'])
            self.assertNotEqual(row['sha256'],row['core_request_sha256'])
            self.assertEqual(receipt['request_sha256'],row['sha256']);self.assertEqual(receipt['wire_override'],{'max_output_tokens':8192})
        with self.assertRaises(ValueError):b.adapt_reply(self.core,b.CASES[0],fake.raw[0],self.plan['requests'][0]['core_request_sha256'],offline=True)

    def test_incomplete_other_provider_status_is_still_accounted_and_stops(self):
        with self.assertRaises(b.BatchStopped) as exc:self.execute(EnvelopeFake({'input_tokens':2,'output_tokens':3},status='failed'))
        s=exc.exception.state
        self.assertEqual(s['failure']['provider_status'],'failed');self.assertEqual(s['responses_received'],1)
        self.assertEqual(Decimal(s['observed_token_charge_estimate_usd']),b.charge({'input_tokens':2,'output_tokens':3}))


class NetworkBoundaryTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket',side_effect=AssertionError('No sockets'));guard.start();self.addCleanup(guard.stop)
        tmp=tempfile.TemporaryDirectory(prefix='traitweaver-http-fake-only-');self.addCleanup(tmp.cleanup);self.packet=Path(tmp.name)/'packet'
        self.plan=b.prepare(ROOT,self.packet);b.atomic(self.packet/'OWNER_APPROVAL.json',b.approval_for(self.plan,True))
        (self.packet/'BATCH.started').write_text(self.plan['approval_sha256']+'\n')
        state=b.fresh_status(self.plan);state.update(status='in_flight',transport='direct_meta_transport',active_case=b.CASES[0],requests_started=1,
              maximum_spend_authorized_usd='0.10',reserved_upper_bound_usd=self.plan['requests'][0]['reserved_upper_bound_usd'])
        b.event(self.packet,state);self.raw=(self.packet/self.plan['requests'][0]['file']).read_bytes()
        for stream in (b.sys.stdin,b.sys.stderr):
            p=patch.object(stream,'isatty',return_value=True);p.start();self.addCleanup(p.stop)

    def test_real_transport_uses_one_post_no_proxy_or_redirect_and_ignores_headers(self):
        class Response(io.BytesIO):
            status=200
        spec=SimpleCore()
        reply={'model':b.MODEL,'status':'completed','usage':{'input_tokens':1,'output_tokens':1},'output':[]}
        opener=type('Opener',(),{'open':lambda self,request,timeout:Response(b.canonical(reply).encode())})()
        captured={}
        def opened(request,timeout):
            captured['request']=request;return Response(b.canonical(reply).encode())
        opener.open=opened
        def factory(*handlers):
            captured['handlers']=handlers;return opener
        with patch('socket.socket',side_effect=AssertionError('No sockets')),patch.object(b.urllib.request,'build_opener',side_effect=factory):
            raw=b.real_transport(spec,self.raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)
        self.assertEqual(json.loads(raw)['model'],b.MODEL)
        self.assertEqual(captured['handlers'][0].proxies,{})
        self.assertIsNone(captured['handlers'][1].redirect_request(None,None,None,None,None,None))
        self.assertEqual(captured['request'].full_url,b.DESTINATION);self.assertEqual(captured['request'].get_method(),'POST')
        self.assertEqual(captured['request'].data,self.raw)
        with self.assertRaises(b.diagnostics.SafeFailure) as duplicate:b.real_transport(spec,self.raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)
        self.assertEqual(duplicate.exception.diagnostic['code'],'duplicate_attempt_blocked')

    def test_http_error_diagnostics_withhold_body_headers_and_unknown_fields(self):
        value={'error':{'code':'invalid_api_key','param':'SYNTHETIC_SECRET_PARAMETER','message':'SYNTHETIC_ERROR_BODY_PRIVATE'}}
        exc=urllib.error.HTTPError(b.DESTINATION,401,'SYNTHETIC_ERROR_REASON',{'Set-Cookie':'SYNTHETIC_COOKIE'},io.BytesIO(b.canonical(value).encode()))
        opener=type('Opener',(),{'open':lambda *args,**kwargs:(_ for _ in ()).throw(exc)})()
        with patch('socket.socket',side_effect=AssertionError('No sockets')),patch.object(b.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(b.diagnostics.SafeFailure) as result:b.real_transport(SimpleCore(),self.raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)
        d=result.exception.diagnostic;self.assertEqual(d['http_status'],401);self.assertEqual(d['provider_error_code'],'invalid_api_key')
        self.assertEqual(d['provider_error_parameter'],'unrecognized_value_withheld')
        for value in ('SYNTHETIC_SECRET_PARAMETER','SYNTHETIC_ERROR_BODY_PRIVATE','SYNTHETIC_COOKIE','SYNTHETIC_KEY_CANARY'):self.assertNotIn(value,b.canonical(d))

    def test_lowest_send_entry_rejects_missing_approval_changed_body_and_stop(self):
        with self.assertRaises(ValueError):b.real_transport(SimpleCore(),self.raw,'SYNTHETIC_KEY_CANARY')
        with self.assertRaises(ValueError):b.real_transport(SimpleCore(),b'{}','SYNTHETIC_KEY_CANARY',packet=self.packet)
        (self.packet/'OWNER_APPROVAL.json').unlink()
        with self.assertRaises((ValueError,OSError)):b.real_transport(SimpleCore(),self.raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)


def SimpleCore():
    from types import SimpleNamespace
    return SimpleNamespace(MAX_BYTES=256*1024,study=SimpleNamespace(decode=lambda raw:json.loads(raw)))


if __name__=='__main__':unittest.main()
