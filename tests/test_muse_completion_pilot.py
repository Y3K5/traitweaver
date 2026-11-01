"""Completed-step pilot: strict approval/transport/accounting and neutral 2x2 comparison offline."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from traitweaver import completion_pilot as core,assistant_evaluation as e,study

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rna_pilot_test',ROOT/'tools/muse_completion_pilot.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


def offline(event,args):
    if event.startswith('socket.'):raise RuntimeError('Completed-step pilot tests forbid sockets')
sys.addaudithook(offline)


class Fake:
    def __init__(self,mutate=None,incomplete=False):self.calls=[];self.raw=[];self.mutate=mutate;self.incomplete=incomplete
    def __call__(self,c,raw,key):
        assert key is None
        slot=next(cid for cid in b.CASES if b.sha(raw)==core.prepare(cid)['request_sha256']);self.calls.append(slot)
        item=core.slot(slot);answer=e.control(item['case_id'],item['permutation'])['answer']
        case=e.get_case('RNA_AFTER');cards={a['id']:a for a in case['candidate_actions']}
        ids=['RNA_DESIGN_CHECK','RNA_LEDGER','RNA_CHECKLIST'] if item['progress_kind']=='completed' else ['RNA_RECONCILE','RNA_DESIGN_CHECK','RNA_LEDGER']
        answer['actions']=[{'action_id':aid,'rationale':'Synthetic completion-aware fixture, not model reasoning.','cited_record_ids':cards[aid]['citations']} for aid in ids]
        reply={'model':b.MODEL,'status':'completed','traitweaver_synthetic':True,'id':'SYNTHETIC_RAW_ID_CANARY',
               'usage':{'input_tokens':1000,'output_tokens':1000,'total_tokens':2000,'output_tokens_details':{'reasoning_tokens':700},'input_tokens_details':{'cached_tokens':0}},
               'output':[{'type':'reasoning','summary':'SYNTHETIC_RAW_REASONING_CANARY'},{'type':'message','content':[{'type':'output_text','text':study.canonical(answer)}]}]}
        if self.mutate:self.mutate(reply,slot)
        if self.incomplete:
            reply.update(status='incomplete',incomplete_details={'reason':'max_output_tokens'})
            reply['usage']={'input_tokens':3378,'output_tokens':1024}
            class Response(io.BytesIO):status=200
            opener=type('Opener',(),{'open':lambda *a,**kw:Response(study.canonical(reply).encode())})()
            model=type('Spec',(),{'DESTINATION':b.DESTINATION,'MODEL':b.MODEL,'MAX_RESPONSE':core.MAX_BYTES,'study':study})()
            capture=b.diagnostics.CaptureOpener(model,opener)
            request=b.urllib.request.Request(b.DESTINATION,data=raw,method='POST')
            with capture.open(request,timeout=1) as response:return response.read(core.MAX_BYTES+1)
        result=study.canonical(reply).encode();self.raw.append(result);return result


class PilotTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='rna-pilot-offline-');self.addCleanup(t.cleanup);self.root=Path(t.name).resolve();self.packet=self.root/'packet';self.plan=b.prepare(ROOT,self.packet)
    def approve(self,**changes):
        grant=b.approval_for(self.plan,True);grant.update(changes);b.atomic(self.packet/'OWNER_APPROVAL.json',grant)
    def run_fake(self,fake=None):self.approve();return b.run(self.packet,fake_transport=fake or Fake())

    def test_unsigned_prepare_exact_four_neutral_bodies_no_keys_or_calls(self):
        self.assertEqual(self.plan['max_requests'],4);self.assertEqual(self.plan['max_output_tokens_each'],8192);self.assertEqual(self.plan['maximum_spend_usd'],'0.20')
        self.assertLess(Decimal(self.plan['conservative_batch_reservation_usd']),Decimal('.20'))
        self.assertFalse((self.packet/'OWNER_APPROVAL.json').exists());self.assertFalse((self.packet/'BATCH.started').exists())
        b.verify_packet(self.packet)
        for cid,row in zip(b.CASES,self.plan['requests']):
            raw=(self.packet/row['file']).read_bytes();self.assertEqual(b.sha(raw),row['sha256'])
            body=json.loads(raw);supplied=json.loads(body['input'])
            self.assertEqual(supplied['id'],'RNA_REVIEW');self.assertTrue(all('readiness' not in a for a in supplied['candidate_actions']))
            for phrase in ('rubric','human_review','first_action_id','RNA_BEFORE','RNA_AFTER','Readiness and action cards are supplied'):
                self.assertNotIn(phrase,raw.decode())
            self.assertEqual(body['max_output_tokens'],8192);self.assertFalse(body['store']);self.assertNotIn('tools',body)
            self.assertEqual(row['evaluation_reference_sha256'],core.prepare(cid)['evaluation_reference_sha256'])

    def test_factorial_differences_are_only_completion_receipt_or_candidate_order(self):
        def body(cid):return deepcopy(core.prepare(cid)['body'])
        before=body('UNVERIFIED_O0');after=body('COMPLETED_O0')
        a=json.loads(before.pop('input'));z=json.loads(after.pop('input'));self.assertEqual(before,after)
        ap=a.pop('step_progress');zp=z.pop('step_progress');self.assertEqual(a,z)
        self.assertEqual(ap['steps'][0]['status'],'not_started');self.assertIsNone(ap['steps'][0]['completion_receipt'])
        self.assertEqual(zp['steps'][0]['status'],'completed');self.assertEqual(zp['steps'][0]['completion_receipt']['status'],'passed')
        rev=body('UNVERIFIED_O1');normal=body('UNVERIFIED_O0');a=json.loads(normal.pop('input'));z=json.loads(rev.pop('input'))
        self.assertEqual(normal,rev);actions=a.pop('candidate_actions');reversed_actions=z.pop('candidate_actions');self.assertEqual(actions,list(reversed(reversed_actions)));self.assertEqual(a,z)
        self.assertIn('RNA_RECONCILE',[v['id'] for v in actions])

    def test_prior_grants_or_changed_caps_scope_and_extra_fields_refused(self):
        for changes in ({'approved':False},{'approval_sha256':'0'*64},{'max_requests':5},{'max_output_tokens_each':1024},{'maximum_spend_usd':'0.10'},{'retries':1},{'fallback':True},{'extra':'unreviewed'}):
            self.approve(**changes)
            with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
            self.assertFalse((self.packet/'BATCH.started').exists())
        self.approve()
        with self.assertRaises(ValueError):b.run(self.packet)

    def test_real_terminal_required_before_key_or_markers_even_with_preset_fake_key(self):
        self.approve();before=(self.packet/'EVENTS.jsonl').read_bytes()
        with patch.object(b.sys.stdin,'isatty',return_value=False),patch.object(b,'credential',side_effect=AssertionError('No key')):
            with self.assertRaises(ValueError):b.run(self.packet,allow_live=True)
        r=subprocess.run([sys.executable,'-B',str(self.packet/'START_REVIEWED_BATCH.py')],capture_output=True,input='',text=True,env={'PATH':'/usr/bin:/bin','MODEL_API_KEY':'SYNTHETIC_KEY_CANARY'})
        self.assertNotEqual(r.returncode,0);self.assertNotIn('SYNTHETIC_KEY_CANARY',r.stdout+r.stderr)
        self.assertFalse((self.packet/'BATCH.started').exists());self.assertEqual((self.packet/'EVENTS.jsonl').read_bytes(),before)

    def test_expired_review_and_copied_location_refuse_without_dispatch(self):
        self.approve();copied=self.root/'copied';shutil.copytree(self.packet,copied)
        with self.assertRaises(ValueError):b.run(copied,fake_transport=Fake())
        plan=deepcopy(self.plan);old=datetime.now(timezone.utc)-timedelta(days=2);plan['prepared_utc']=old.isoformat();plan['expires_utc']=(old+timedelta(hours=24)).isoformat()
        plan['approval_sha256']=b.digest({k:v for k,v in plan.items() if k!='approval_sha256'})
        control=b.read(self.packet/'LOCAL_CONTROL.json');control['approval_sha256']=plan['approval_sha256']
        b.atomic(self.packet/'PUBLIC_BATCH.json',plan);b.atomic(self.packet/'LOCAL_CONTROL.json',control);b.atomic(self.packet/'UNSIGNED_APPROVAL.json',b.approval_for(plan));b.atomic(self.packet/'OWNER_APPROVAL.json',b.approval_for(plan,True))
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_protocol_code_price_and_payload_tamper_fail(self):
        self.approve()
        for name in ('COMPLETION_PROTOCOL.json',self.plan['requests'][0]['file'],'muse_completion_pilot.py','PRICING.json'):
            path=self.packet/name;raw=path.read_bytes();path.write_bytes(raw+b' ' if name.endswith('.py') else b'{}')
            with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
            path.write_bytes(raw)
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_four_scored_synthetic_replies_preserve_bindings_and_compare_factors(self):
        fake=Fake();state=self.run_fake(fake)
        self.assertEqual(fake.calls,list(b.CASES));self.assertEqual(state['cases_completed'],4)
        summary=b.read(self.packet/'COMPARISON.json');self.assertEqual(summary['scored_slots'],4)
        self.assertTrue(all(v['first_action_same'] for v in summary['order_comparisons']))
        self.assertTrue(all(v['completed_step_not_repeated'] for v in summary['completion_comparisons']))
        for cid,raw in zip(b.CASES,fake.raw):
            record=core.validate_record(b.read(self.packet/cid/'pilot-result.json'));receipt=b.read(self.packet/cid/'BATCH_RECEIPT.json')
            self.assertEqual(record['response_sha256'],b.sha(raw));self.assertEqual(receipt['response_sha256'],b.sha(raw))
            self.assertEqual(record['request_sha256'],core.prepare(cid)['request_sha256'])
            self.assertNotEqual(record['request_sha256'],record['evaluation_reference_sha256'])
            self.assertEqual(record['evaluation_result']['provenance'],'synthetic_oracle_control')
            e.reopen(b.read(self.packet/cid/'evaluation.json'))
        for file in self.packet.rglob('*'):
            if file.is_file():
                text=file.read_text();self.assertNotIn('SYNTHETIC_RAW_ID_CANARY',text);self.assertNotIn('SYNTHETIC_RAW_REASONING_CANARY',text)
        with self.assertRaises(ValueError):b.run(self.packet,fake_transport=fake)
        self.assertEqual(len(fake.calls),4)

    def test_repeating_a_completed_step_is_scored_as_failure_not_hidden(self):
        def repeat(reply,cid):
            answer=json.loads(reply['output'][1]['content'][0]['text'])
            case=e.get_case('RNA_AFTER');cards={a['id']:a for a in case['candidate_actions']}
            answer['actions']=[{'action_id':aid,'rationale':'Synthetic repetition baseline, not model output.','cited_record_ids':cards[aid]['citations']} for aid in ['RNA_RECONCILE','RNA_DESIGN_CHECK','RNA_LEDGER']]
            reply['output'][1]['content'][0]['text']=study.canonical(answer)
        state=self.run_fake(Fake(mutate=repeat));self.assertEqual(state['cases_completed'],4)
        summary=b.read(self.packet/'COMPARISON.json')
        for m in summary['metrics']:
            if m['completion_condition']=='completed':
                self.assertEqual(m['repeated_completed_actions'],['RNA_RECONCILE']);self.assertFalse(m['avoids_repeating_completed_work'])
        self.assertTrue(all(not c['completed_step_not_repeated'] for c in summary['completion_comparisons']))

    def test_well_formed_wrong_answers_are_scored_and_do_not_stop_comparison(self):
        def wrong(reply,cid):
            answer=json.loads(reply['output'][1]['content'][0]['text'])
            for j in answer['judgments']:j['verdict']='supported'
            reply['output'][1]['content'][0]['text']=study.canonical(answer)
        state=self.run_fake(Fake(mutate=wrong));self.assertEqual(state['cases_completed'],4)
        summary=b.read(self.packet/'COMPARISON.json');self.assertTrue(all(not m['unsupported_success_withheld'] for m in summary['metrics']))
        self.assertEqual(summary['human_usefulness'],'not_reviewed')

    def test_reviewed_uncertainty_and_extra_relevant_citations_not_false_quality_failures(self):
        def alternatives(reply,cid):
            answer=json.loads(reply['output'][1]['content'][0]['text'])
            for j in answer['judgments']:
                if j['claim_id']=='RNA_ZERO_FILES_ZERO_READS':j['verdict']='unknown'
                if j['claim_id']=='RNA_SUCCESS':j.update(verdict='contradicted',cited_record_ids=['RNA_DESIGN'])
            for a in answer['actions']:a['cited_record_ids']=sorted(set(a['cited_record_ids'])|{'RNA_FILES'})
            reply['output'][1]['content'][0]['text']=study.canonical(answer)
        self.run_fake(Fake(mutate=alternatives));metrics=b.read(self.packet/'COMPARISON.json')['metrics']
        self.assertTrue(all(m['missing_read_count_not_promoted'] and m['unsupported_success_withheld'] and m['required_action_citations_covered'] for m in metrics))

    def test_incomplete_usage_counts_response_cost_and_stops_no_retry(self):
        fake=Fake(incomplete=True)
        with self.assertRaises(b.BatchStopped) as exc:self.run_fake(fake)
        s=exc.exception.state;self.assertEqual(s['responses_received'],1);self.assertEqual(s['responses_accepted'],0)
        self.assertEqual(s['observed_token_charge_estimate_usd'],'0.0085745');self.assertEqual(Decimal(s['reserved_upper_bound_usd']),0)
        self.assertEqual(len(fake.calls),1);self.assertTrue(all(r['status']=='skipped' for r in s['cases'][1:]))
        self.assertFalse((self.packet/b.CASES[0]).exists())

    def test_missing_usage_and_zero_counts_stay_distinct(self):
        fake=Fake(mutate=lambda r,c:r.update(usage={'input_tokens':0}))
        with self.assertRaises(b.BatchStopped) as exc:self.run_fake(fake)
        row=exc.exception.state['cases'][0];self.assertEqual(row['reported_usage'],{'input_tokens':0});self.assertIsNone(row['estimated_cost_usd'])
        self.assertGreater(Decimal(exc.exception.state['reserved_upper_bound_usd']),0)

    def test_rejected_unknown_citations_do_not_execute_source_audit(self):
        def invalid(reply,cid):
            answer=json.loads(reply['output'][1]['content'][0]['text']);answer['actions'][0]['cited_record_ids']=['UNKNOWN']
            reply['output'][1]['content'][0]['text']=study.canonical(answer)
        with patch.object(core.AuditSession,'check',side_effect=AssertionError('No audit dispatch')),self.assertRaises(b.BatchStopped) as exc:self.run_fake(Fake(mutate=invalid))
        self.assertEqual(exc.exception.state['responses_accepted'],0);self.assertEqual(exc.exception.state['requests_started'],1)

    def test_refusal_and_tool_outputs_stop_with_safe_codes(self):
        def refusal(reply,cid):reply['output']=[{'type':'message','content':[{'type':'refusal','refusal':'SYNTHETIC_RAW_REFUSAL_CANARY'}]}]
        with self.assertRaises(b.BatchStopped) as exc:self.run_fake(Fake(mutate=refusal))
        self.assertEqual(exc.exception.state['failure']['code'],'provider_refusal')
        self.assertNotIn('SYNTHETIC_RAW_REFUSAL_CANARY',(self.packet/'FAILURE.json').read_text())

    def test_live_provenance_rejects_synthetic_and_offline_cannot_be_labelled_live(self):
        fake=Fake();raw=fake(core,study.canonical(core.prepare(b.CASES[0])['body']).encode(),None)
        with self.assertRaises(ValueError):core.parse_reply(b.CASES[0],raw,core.prepare(b.CASES[0])['request_sha256'])
        decoded=json.loads(raw);decoded.pop('traitweaver_synthetic');live=core.parse_reply(b.CASES[0],study.canonical(decoded).encode(),core.prepare(b.CASES[0])['request_sha256'])
        self.assertEqual(live['evaluation_result']['provenance'],'imported_model_response_unverified')
        self.approve()
        with self.assertRaises(ValueError):b.run(self.packet,allow_live=True,fake_transport=Fake())

    def test_partial_comparison_has_unknown_pairs_and_result_tampering_fails(self):
        fake=Fake();raw=fake(core,study.canonical(core.prepare(b.CASES[0])['body']).encode(),None)
        record=core.parse_reply(b.CASES[0],raw,core.prepare(b.CASES[0])['request_sha256'],offline=True)
        summary=core.summary([record]);self.assertTrue(all(p['first_action_same'] is None for p in summary['order_comparisons']))
        self.assertTrue(all(p['completed_step_not_repeated'] is None for p in summary['completion_comparisons']))
        changed=deepcopy(record);changed['request_sha256']=changed['evaluation_reference_sha256'];changed['sha256']=study.digest({k:v for k,v in changed.items() if k!='sha256'})
        with self.assertRaises(ValueError):core.validate_record(changed)

    def test_prior_valid_export_survives_later_save_failure(self):
        original=core.export_bundle
        def save(record,destination):
            if record['slot_id']==b.CASES[1]:raise OSError('SYNTHETIC_PRIVATE_LOCAL_ERROR')
            original(record,destination)
        with patch.object(core,'export_bundle',side_effect=save),self.assertRaises(b.BatchStopped) as exc:self.run_fake()
        self.assertEqual(exc.exception.state['cases_completed'],1);core.validate_record(b.read(self.packet/b.CASES[0]/'pilot-result.json'))
        self.assertNotIn('SYNTHETIC_PRIVATE_LOCAL_ERROR',(self.packet/'FAILURE.json').read_text())

    def test_stop_before_dispatch_no_marker_and_monitor_has_no_key_access(self):
        self.approve();(self.packet/'STOP.requested').touch()
        with patch.object(b,'credential',side_effect=AssertionError('No key')):
            b.status(self.packet)
            with self.assertRaises(ValueError):b.run(self.packet,fake_transport=Fake())
        self.assertFalse((self.packet/'BATCH.started').exists())

    def test_concurrent_starts_create_one_batch_only(self):
        self.approve();fake=Fake();results=[]
        def run():
            try:results.append(b.run(self.packet,fake_transport=fake)['status'])
            except (ValueError,OSError):results.append('refused')
        first=threading.Thread(target=run);second=threading.Thread(target=run)
        first.start();second.start();first.join();second.join()
        self.assertEqual(sorted(results),['completed','refused']);self.assertEqual(len(fake.calls),4)

    def test_deadline_heartbeat_and_stop_have_no_retry_or_second_dispatch(self):
        state=b.fresh_status(self.plan);state.update(status='in_flight',transport='offline_fake_transport',requests_started=1,active_case=b.CASES[0])
        release=threading.Event()
        def slow(*args):release.wait(2);return b'{}'
        try:
            with self.assertRaises(b.diagnostics.SafeFailure) as exc:b.wait_transport(self.packet,state,slow,core,b'{}',None,time.monotonic(),deadline=.02)
            self.assertEqual(exc.exception.diagnostic['code'],'deadline_exceeded')
        finally:release.set()
        def heartbeat(*args):time.sleep(1.1);return b'{}'
        b.wait_transport(self.packet,state,heartbeat,core,b'{}',None,time.monotonic(),deadline=2)
        self.assertGreater(b.read(self.packet/'STATUS.json')['request_elapsed_seconds'],.9)
        (self.packet/'STOP.requested').touch();calls=[]
        with self.assertRaises(b.diagnostics.SafeFailure):b.wait_transport(self.packet,state,lambda *a:calls.append(1),core,b'{}',None,time.monotonic())
        self.assertEqual(calls,[])

    def test_reported_usage_over_output_allowance_stops_before_next_call(self):
        fake=Fake(mutate=lambda r,c:r.update(usage={'input_tokens':1000,'output_tokens':8193,'total_tokens':9193}))
        with self.assertRaises(b.BatchStopped) as exc:self.run_fake(fake)
        self.assertEqual(exc.exception.state['failure']['code'],'usage_exceeds_allowance');self.assertEqual(len(fake.calls),1)
        self.assertEqual(exc.exception.state['cases'][0]['reported_usage']['output_tokens'],8193)
        self.assertGreater(Decimal(exc.exception.state['observed_token_charge_estimate_usd']),0)

    def test_actual_send_boundary_uses_one_post_no_proxy_redirect_and_duplicate_refusal(self):
        self.approve();(self.packet/'BATCH.started').write_text(self.plan['approval_sha256']+'\n')
        state=b.fresh_status(self.plan);state.update(status='in_flight',transport='direct_meta_transport',active_case=b.CASES[0],requests_started=1,maximum_spend_authorized_usd='0.20',reserved_upper_bound_usd=self.plan['requests'][0]['reserved_upper_bound_usd'])
        b.event(self.packet,state);raw=(self.packet/self.plan['requests'][0]['file']).read_bytes();seen={}
        class Response(io.BytesIO):status=200
        def opened(request,timeout):
            seen['request']=request;return Response(study.canonical({'model':b.MODEL,'status':'completed','usage':{'input_tokens':0,'output_tokens':0},'output':[]}).encode())
        opener=type('Opener',(),{})();opener.open=opened
        def factory(*handlers):seen['handlers']=handlers;return opener
        with patch.object(b.sys.stdin,'isatty',return_value=True),patch.object(b.sys.stderr,'isatty',return_value=True),patch.object(b.urllib.request,'build_opener',side_effect=factory):
            b.real_transport(core,raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)
            with self.assertRaises(b.diagnostics.SafeFailure) as exc:b.real_transport(core,raw,'SYNTHETIC_KEY_CANARY',packet=self.packet)
        self.assertEqual(exc.exception.diagnostic['code'],'duplicate_attempt_blocked')
        self.assertEqual(seen['request'].data,raw);self.assertEqual(seen['request'].full_url,b.DESTINATION)
        self.assertEqual(seen['handlers'][0].proxies,{})
        self.assertIsNone(seen['handlers'][1].redirect_request(None,None,None,None,None,None))

    def test_lowest_transport_requires_packet_approval_and_exact_body(self):
        raw=(self.packet/self.plan['requests'][0]['file']).read_bytes()
        with patch.object(b.sys.stdin,'isatty',return_value=True),patch.object(b.sys.stderr,'isatty',return_value=True):
            with self.assertRaises(ValueError):b.real_transport(core,raw,'SYNTHETIC_KEY')
            with self.assertRaises((ValueError,OSError)):b.real_transport(core,raw,'SYNTHETIC_KEY',packet=self.packet)
        self.assertFalse(any(self.packet.glob('POST-*.started')))


if __name__=='__main__':unittest.main()
