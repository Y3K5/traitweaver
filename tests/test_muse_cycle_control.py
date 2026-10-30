"""Cycle approval/monitor tests with synthetic credentials and fake transport only."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import runpy
import socket
import ssl
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT
spec=importlib.util.spec_from_file_location('muse_cycle_control',ROOT/'tools/muse_cycle.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)


class Response(io.BytesIO):
    status=200


class FakeTransport:
    def __init__(self,branch='coverage',fail=None):self.calls=[];self.branch=branch;self.fail=fail
    def open(self,request,timeout):
        body=json.loads(request.data);phase=body['text']['format']['name'].removeprefix('traitweaver_');self.calls.append(phase)
        if self.fail=='timeout' or self.fail==phase+'_timeout':raise TimeoutError('Synthetic sensitive detail must not be logged')
        context=json.loads(body['input'])
        if phase=='selection':
            p={'check':'endpoint_coverage' if self.branch=='coverage' else 'published_contrasts',
               'metric':None if self.branch=='coverage' else self.branch,
               'rationale_code':'audit_target_before_comparison' if self.branch=='coverage' else 'describe_source_bound_means',
               'citations':['S_PSR1_2023','S_OVERPLUS_2024']}
        else:
            p={'outcome':body['text']['format']['schema']['properties']['outcome']['enum'][0],
               'result_id':context['result']['id'],'next_action':'researcher_review_measurement_plan',
               'citations':['S_PSR1_2023','S_OVERPLUS_2024']}
        if self.fail=='invalid_selection' and phase=='selection':p['check']='shell'
        result={'id':'resp_fake_cycle_test','model':'muse-spark-1.3','status':'completed',
                'usage':{'input_tokens':2500,'output_tokens':300,'output_tokens_details':{'reasoning_tokens':100}},
                'output':[{'type':'message','content':[{'type':'output_text','text':control.canonical(p)}]}]}
        if self.fail=='missing_usage':result.pop('usage')
        if self.fail=='over_cap':result['usage']['output_tokens']=2048
        return Response(control.canonical(result).encode())


class MuseCycleControlTests(unittest.TestCase):
    def setUp(self):
        # Fail any accidental real network use during every test in this suite.
        guard=patch('socket.socket',side_effect=AssertionError('Offline tests prohibit sockets'))
        guard.start();self.addCleanup(guard.stop)
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-cycle-control-test-');self.addCleanup(self.temp.cleanup)
        self.packet=Path(self.temp.name)/'packet'
        self.plan=control.prepare(APP,self.packet)
        self.modules=control.configure(APP)

    def approval(self,**changes):
        value=control.load(self.packet/'APPROVAL_DRAFT.json');value['approved']=True;value.update(changes)
        path=Path(self.temp.name)/'SYNTHETIC_TEST_APPROVAL.json';control.atomic(path,value);return path

    def execute(self,transport,approval=None,allow_live=True):
        with patch.object(self.modules[2].os,'environ',{'MODEL_API_KEY':'synthetic-cycle-control-token'}):
            return control.run(self.packet,approval or self.approval(),allow_live,opener=transport)

    def test_preparation_contains_four_exact_public_bodies_but_allows_only_two_requests(self):
        self.assertEqual(self.plan['max_requests'],2);self.assertEqual(len(self.plan['requests']),4)
        self.assertEqual(str(control.TOTAL_CAP),'0.05')
        self.assertEqual(self.plan['conservative_largest_pair_usd'],'0.04596025')
        for entry in self.plan['requests']:
            raw=(self.packet/entry['file']).read_bytes();self.assertEqual(control.sha(raw),entry['sha256'])
            self.assertNotIn(b'/Users/',raw);self.assertNotIn(b'GFP',raw);self.assertNotIn(b'MODEL_API_KEY',raw)
        self.assertFalse(control.load(self.packet/'APPROVAL_DRAFT.json')['approved'])
        self.assertEqual(control.status(self.packet)['requests_started'],0)

    def test_prepare_and_status_never_access_credentials(self):
        class NoCredential:
            def get(self,*args):raise AssertionError('Credential access before approval')
        with patch.object(self.modules[2].os,'environ',NoCredential()):
            other=Path(self.temp.name)/'no-credential-packet';control.prepare(APP,other)
            self.assertEqual(control.status(other)['status'],'awaiting_approval')

    def test_default_send_disabled_and_draft_approval_cannot_run(self):
        fake=FakeTransport()
        with self.assertRaises(ValueError):self.execute(fake,allow_live=False)
        with self.assertRaises(ValueError):self.execute(fake,self.packet/'APPROVAL_DRAFT.json')
        self.assertEqual(fake.calls,[]);self.assertFalse((self.packet/'CYCLE.started').exists())

    def test_wrong_bundle_or_spend_limit_rejected_before_dispatch(self):
        fake=FakeTransport()
        for changes in [{'approval_sha256':'0'*64},{'maximum_spend_usd':'0.10'},{'max_requests':3},{'model':'other'}]:
            with self.assertRaises(ValueError):self.execute(fake,self.approval(**changes))
        self.assertEqual(fake.calls,[])

    def test_modified_body_is_refused_before_dispatch(self):
        (self.packet/'01-selection.json').write_bytes(b'{}')
        fake=FakeTransport()
        with self.assertRaises(ValueError):self.execute(fake)
        self.assertEqual(fake.calls,[])

    def test_each_allowed_branch_matches_its_exact_preapproved_followup(self):
        for branch in ('coverage','phosphate_uptake','growth'):
            packet=Path(self.temp.name)/branch;control.prepare(APP,packet)
            approval=control.load(packet/'APPROVAL_DRAFT.json');approval['approved']=True
            path=Path(self.temp.name)/(branch+'-synthetic-approval.json');control.atomic(path,approval)
            fake=FakeTransport(branch)
            with patch.object(self.modules[2].os,'environ',{'MODEL_API_KEY':'synthetic-cycle-control-token'}):
                final=control.run(packet,path,True,opener=fake)
            self.assertEqual(fake.calls,['selection','reassessment']);self.assertEqual(final['status'],'complete')
            self.assertEqual(final['requests_started'],2);self.assertEqual(final['reserved_upper_bound_usd'],'0E-8')
            self.assertLess(float(final['observed_token_charge_estimate_usd']),.05)
            self.assertEqual(len(list((packet/'ledger').glob('*.attempt.json'))),2)
            self.assertTrue((packet/'STUDY_PACKAGE.json').is_file())
            self.assertEqual(final['transport'],'fake_test_only')

    def test_timeout_stops_without_retry_and_retains_uncertain_budget(self):
        fake=FakeTransport(fail='timeout')
        with self.assertRaises(ValueError):self.execute(fake)
        value=control.status(self.packet)
        self.assertEqual(fake.calls,['selection']);self.assertEqual(value['requests_started'],1)
        self.assertEqual(value['billing_state'],'uncertain_reserved_budget_retained')
        self.assertGreater(float(value['reserved_upper_bound_usd']),0)
        self.assertNotIn('Synthetic sensitive detail',(self.packet/'EVENTS.jsonl').read_text())
        with self.assertRaises(ValueError):self.execute(fake)
        self.assertEqual(fake.calls,['selection'])

    def test_missing_usage_invalid_choice_and_output_cap_violation_prevent_second_call(self):
        for failure in ['missing_usage','invalid_selection','over_cap']:
            packet=Path(self.temp.name)/failure;control.prepare(APP,packet)
            approval=control.load(packet/'APPROVAL_DRAFT.json');approval['approved']=True
            path=Path(self.temp.name)/(failure+'-test-approval.json');control.atomic(path,approval)
            fake=FakeTransport(fail=failure)
            with patch.object(self.modules[2].os,'environ',{'MODEL_API_KEY':'synthetic-cycle-control-token'}):
                with self.assertRaises(ValueError):control.run(packet,path,True,opener=fake)
            self.assertEqual(fake.calls,['selection']);self.assertEqual(control.status(packet)['status'],'stopped_requires_review')

    def test_second_phase_timeout_preserves_first_usage_and_holds_only_second_reservation(self):
        fake=FakeTransport(fail='reassessment_timeout')
        with self.assertRaises(ValueError):self.execute(fake)
        value=control.status(self.packet)
        self.assertEqual(value['requests_completed'],1);self.assertEqual(value['requests_started'],2)
        self.assertGreater(float(value['observed_token_charge_estimate_usd']),0)
        self.assertEqual(float(value['reserved_upper_bound_usd']),.02287575)
        self.assertTrue((self.packet/'RECEIPT-selection.json').exists())

    def test_monitor_records_events_and_usage_without_raw_responses_or_credentials(self):
        self.execute(FakeTransport());records=[json.loads(line) for line in (self.packet/'EVENTS.jsonl').read_text().splitlines()]
        self.assertEqual(records[0]['status'],'awaiting_approval');self.assertEqual(records[-1]['status'],'complete')
        text=(self.packet/'MONITOR.html').read_text()+(self.packet/'EVENTS.jsonl').read_text()
        self.assertNotIn('synthetic-cycle-control-token',text)
        self.assertNotIn('output_text',(self.packet/'STUDY_PACKAGE.json').read_text())
        self.assertTrue((self.packet/'study/revision-000002.json').exists())
        receipt=control.load(self.packet/'RECEIPT-selection.json')
        self.assertEqual(receipt['usage']['reasoning_tokens'],100);self.assertIsNone(receipt['actual_provider_charge_usd'])

    def test_operator_interrupt_preserves_reservation_and_stops(self):
        class Interrupt(FakeTransport):
            def open(self,*args,**kwargs):raise KeyboardInterrupt()
        with self.assertRaises(ValueError):self.execute(Interrupt())
        value=control.status(self.packet)
        self.assertEqual(value['status'],'stopped_requires_review')
        self.assertGreater(float(value['reserved_upper_bound_usd']),0)

    def test_dead_runner_is_visible_without_resuming_or_querying_provider(self):
        control.event(self.packet,'selection_in_flight',runner_pid=999999,request_started_utc='2026-10-29T00:00:00+00:00',reserved_upper_bound_usd='0.02153825')
        with patch.object(control.os,'kill',side_effect=ProcessLookupError):value=control.status(self.packet)
        self.assertEqual(value['status'],'interrupted_requires_review')
        self.assertEqual(value['billing_state'],'uncertain_reserved_budget_retained')
        self.assertFalse((self.packet/'CYCLE.started').exists())

    def failure(self,transport):
        with self.assertRaises(control.CycleStopped):self.execute(transport)
        record=control.load(self.packet/'FAILURE-selection.json')
        self.assertEqual(control.status(self.packet)['failure'],record)
        self.assertFalse((self.packet/'STUDY_PACKAGE.json').exists())
        return record

    def test_http_status_and_allowlisted_codes_retained_without_private_error_material(self):
        secret='synthetic-cycle-control-token'
        class Rejected:
            calls=0
            def open(self,request,timeout):
                self.calls+=1
                body={'error':{'code':'invalid_api_key','type':'authentication_error','param':'model',
                               'message':'private owner /Users/private '+secret}}
                raise urllib.error.HTTPError(request.full_url,401,'private '+secret,
                        {'Set-Cookie':'private-cookie','Authorization':secret},io.BytesIO(json.dumps(body).encode()))
        fake=Rejected();record=self.failure(fake)
        self.assertEqual(fake.calls,1);self.assertEqual(record['http_status'],401)
        self.assertEqual(record['code'],'http_authentication_rejected')
        self.assertEqual(record['provider_error_code'],'invalid_api_key')
        self.assertEqual(record['provider_error_parameter'],'model')
        for f in self.packet.rglob('*'):
            if f.is_file():
                text=f.read_text()
                for forbidden in (secret,'private owner','private-cookie','Authorization'):
                    self.assertNotIn(forbidden,text,f.name)

    def test_http_matrix_no_redirect_retry_or_second_request(self):
        for status,expected in [(400,'http_request_rejected'),(403,'http_permission_rejected'),
                                 (429,'http_rate_or_quota_rejected'),(500,'http_provider_error'),(302,'redirect_blocked')]:
            packet=Path(self.temp.name)/str(status);control.prepare(APP,packet)
            approval=control.load(packet/'APPROVAL_DRAFT.json');approval['approved']=True
            path=Path(self.temp.name)/(str(status)+'-test-approval.json');control.atomic(path,approval)
            class Rejected:
                calls=0
                def open(self,request,timeout):
                    self.calls+=1
                    raise urllib.error.HTTPError(request.full_url,status,'withheld',{'Location':'https://private.invalid'},io.BytesIO(b'not json'))
            fake=Rejected()
            with patch.object(self.modules[2].os,'environ',{'MODEL_API_KEY':'synthetic-cycle-control-token'}):
                with self.assertRaises(control.CycleStopped):control.run(packet,path,True,opener=fake)
            record=control.load(packet/'FAILURE-selection.json')
            self.assertEqual(record['code'],expected);self.assertEqual(record['http_status'],status)
            self.assertEqual(fake.calls,1)
            self.assertNotIn('private.invalid',(packet/'EVENTS.jsonl').read_text())

    def test_unknown_provider_fields_withheld_instead_of_echoed(self):
        class Rejected:
            def open(self,request,timeout):
                error={k:'synthetic-secret-and-owner-detail' for k in ('code','type','param','message')}
                raise urllib.error.HTTPError(request.full_url,400,'withheld',{},io.BytesIO(json.dumps({'error':error}).encode()))
        record=self.failure(Rejected())
        self.assertEqual(record['provider_error_code'],'unrecognized_value_withheld')
        self.assertNotIn('synthetic-secret',json.dumps(record))

    def test_network_types_distinguished_without_exception_strings(self):
        cases=[(TimeoutError('synthetic-secret'),'timeout'),
               (urllib.error.URLError(socket.gaierror('synthetic-secret')),'dns_resolution_failed'),
               (ssl.SSLCertVerificationError('synthetic-secret'),'tls_certificate_verification_failed'),
               (ConnectionRefusedError('synthetic-secret'),'connection_refused'),
               (ConnectionResetError('synthetic-secret'),'connection_reset')]
        for index,(error,code) in enumerate(cases):
            packet=Path(self.temp.name)/('network-'+str(index));control.prepare(APP,packet)
            approval=control.load(packet/'APPROVAL_DRAFT.json');approval['approved']=True
            path=Path(self.temp.name)/('network-'+str(index)+'.json');control.atomic(path,approval)
            class Broken:
                def open(self,*args,**kwargs):raise error
            with patch.object(self.modules[2].os,'environ',{'MODEL_API_KEY':'synthetic-cycle-control-token'}):
                with self.assertRaises(control.CycleStopped):control.run(packet,path,True,opener=Broken())
            record=control.load(packet/'FAILURE-selection.json')
            self.assertEqual(record['code'],code);self.assertEqual(record['stage'],'transport_open')
            self.assertNotIn('synthetic-secret',json.dumps(record))
            self.assertIsNone(control.status(packet)['observed_token_charge_estimate_usd'])

    def test_read_timeout_records_response_stage_and_http_status(self):
        class BrokenResponse(Response):
            def read(self,*args):raise TimeoutError('synthetic-secret')
        class Broken:
            def open(self,*args,**kwargs):return BrokenResponse()
        record=self.failure(Broken())
        self.assertEqual(record['code'],'timeout');self.assertEqual(record['stage'],'response_read')
        self.assertEqual(record['http_status'],200)

    def test_malformed_json_is_distinct_from_provider_rejection(self):
        class Broken:
            def open(self,*args,**kwargs):return Response(b'not JSON synthetic-secret')
        record=self.failure(Broken())
        self.assertEqual(record['stage'],'response_decode');self.assertEqual(record['code'],'malformed_json')
        self.assertNotIn('synthetic-secret',json.dumps(record))

    def test_incomplete_response_retains_reason_and_numeric_usage(self):
        class Broken:
            def open(self,*args,**kwargs):
                return Response(json.dumps({'model':'muse-spark-1.3','status':'incomplete',
                    'incomplete_details':{'reason':'max_output_tokens'},'usage':{'input_tokens':1000,'output_tokens':1024}}).encode())
        record=self.failure(Broken())
        self.assertEqual(record['code'],'provider_not_completed')
        self.assertEqual(record['incomplete_reason'],'max_output_tokens')
        self.assertEqual(record['reported_usage']['output_tokens'],1024)

    def test_model_mismatch_does_not_echo_untrusted_model_name(self):
        class Broken:
            def open(self,*args,**kwargs):return Response(b'{"model":"synthetic-secret","status":"completed"}')
        record=self.failure(Broken())
        self.assertEqual(record['code'],'model_mismatch');self.assertNotIn('synthetic-secret',json.dumps(record))

    def test_rejected_action_retains_usage_but_cannot_execute(self):
        record=self.failure(FakeTransport(fail='invalid_selection'))
        self.assertEqual(record['code'],'unavailable_action_or_arguments')
        self.assertEqual(record['stage'],'structured_reply_validation')
        self.assertEqual(record['reported_usage']['output_tokens'],300)
        self.assertEqual(len(list((self.packet/'study').glob('revision-*.json'))),1)

    def test_refusal_has_separate_code_and_withholds_refusal_text(self):
        class Refused:
            def open(self,*args,**kwargs):
                return Response(json.dumps({'model':'muse-spark-1.3','status':'completed',
                 'output':[{'type':'message','content':[{'type':'refusal','refusal':'synthetic-secret'}]}]}).encode())
        record=self.failure(Refused())
        self.assertEqual(record['code'],'provider_refusal');self.assertNotIn('synthetic-secret',json.dumps(record))

    def test_missing_usage_has_separate_failure_code(self):
        record=self.failure(FakeTransport(fail='missing_usage'))
        self.assertEqual(record['stage'],'usage_validation')
        self.assertEqual(record['code'],'missing_or_invalid_usage')

    def test_monitor_clears_obsolete_credential_blocker_when_run_starts(self):
        control.event(self.packet,'awaiting_credential',blocker='obsolete missing-key message')
        self.execute(FakeTransport())
        self.assertIsNone(control.status(self.packet)['blocker'])
        self.assertNotIn('obsolete missing-key message',(self.packet/'MONITOR.html').read_text())
        self.assertIn('obsolete missing-key message',(self.packet/'EVENTS.jsonl').read_text())

    def test_live_opener_disables_environment_proxies_and_redirects(self):
        # Construct only; network is prohibited by the socket guard.
        opener=control.diagnostics.CaptureOpener(self.modules[2]).opener
        redirects=[h for h in opener.handlers if isinstance(h,control.diagnostics.urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(redirects),1)
        self.assertIsNone(redirects[0].redirect_request(None,None,302,None,None,None))
        self.assertFalse(any(isinstance(h,control.diagnostics.urllib.request.ProxyHandler) and h.proxies for h in opener.handlers))

    def test_cli_prints_safe_failure_details_instead_of_generic_stop(self):
        class Rejected:
            def open(self,request,timeout):
                raise urllib.error.HTTPError(request.full_url,400,'synthetic-secret',{},io.BytesIO(b'{"error":{"code":"invalid_json_schema","param":"text.format.schema"}}'))
        args=['muse_cycle.py','run','--packet',str(self.packet),'--approval',str(self.approval()),'--send']
        original=control.diagnostics.CaptureOpener.__init__
        def init(instance,muse,opener=None):original(instance,muse,Rejected())
        output=io.StringIO()
        with patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys,'argv',args),patch.object(control.diagnostics.CaptureOpener,'__init__',init),patch.dict(control.os.environ,{'MODEL_API_KEY':'synthetic-cycle-control-token'},clear=True),redirect_stderr(output):
            with self.assertRaises(SystemExit):control.main()
        text=output.getvalue()
        self.assertIn('http_status=400',text);self.assertIn('invalid_json_schema',text)
        self.assertNotIn('synthetic-secret',text)

    def test_previous_attempt_is_locked_and_cost_uncertainty_carried_forward(self):
        with self.assertRaises(control.CycleStopped):self.execute(FakeTransport(fail='timeout'))
        old=(self.packet/'STATUS.json').read_bytes()
        new=Path(self.temp.name)/'new-packet';plan=control.prepare(APP,new,previous=self.packet)
        self.assertFalse(control.load(new/'APPROVAL_DRAFT.json')['approved'])
        self.assertFalse((new/'OWNER_APPROVAL.json').exists())
        self.assertEqual(plan['previous_attempt']['combined_prior_reservation_plus_new_ceiling_usd'],'0.07153825')
        self.assertEqual((self.packet/'STATUS.json').read_bytes(),old)
        self.assertFalse((new/'CYCLE.started').exists())

    def test_starter_rejects_unapproved_packet_before_asking_for_key(self):
        namespace=runpy.run_path(str(self.packet/'START_APPROVED_CYCLE.py'))
        class Loader:
            def exec_module(self,module):pass
        class Spec:loader=Loader()
        with patch('importlib.util.spec_from_file_location',return_value=Spec()),patch('importlib.util.module_from_spec',return_value=control),patch('getpass.getpass',side_effect=AssertionError('Must not ask for a key')):
            with self.assertRaises(FileNotFoundError):namespace['main']()

    def test_starter_prints_safe_failure_summary(self):
        approval=control.load(self.approval());control.atomic(self.packet/'OWNER_APPROVAL.json',approval)
        namespace=runpy.run_path(str(self.packet/'START_APPROVED_CYCLE.py'))
        class Loader:
            def exec_module(self,module):pass
        class Spec:loader=Loader()
        diagnostic=control.diagnostics.base('http_response','http_authentication_rejected',True,http_status=401,provider_error_code='invalid_api_key')
        output=io.StringIO()
        with patch.object(sys.stdin,'isatty',return_value=True),patch('importlib.util.spec_from_file_location',return_value=Spec()),patch('importlib.util.module_from_spec',return_value=control),patch.dict(control.os.environ,{'MODEL_API_KEY':'synthetic-cycle-control-token'},clear=True),patch.object(control,'run',side_effect=control.CycleStopped(diagnostic)),redirect_stderr(output):
            self.assertEqual(namespace['main'](),1)
        self.assertIn('http_status=401',output.getvalue());self.assertIn('invalid_api_key',output.getvalue())
        self.assertNotIn('synthetic-cycle-control-token',output.getvalue())

    def test_missing_credential_is_distinguished_from_network_dispatch(self):
        fake=FakeTransport()
        with patch.dict(control.os.environ,{},clear=True):
            with self.assertRaises(control.CycleStopped):control.run(self.packet,self.approval(),True,opener=fake)
        record=control.load(self.packet/'FAILURE-selection.json')
        self.assertEqual(record['code'],'credential_unavailable')
        self.assertFalse(record['dispatch_attempted']);self.assertEqual(fake.calls,[])

    def test_diagnostic_file_failure_still_reports_safe_original_error(self):
        original=control.atomic
        def atomic(path,value):
            if path.name.startswith('FAILURE-'):raise OSError('synthetic-private-path')
            return original(path,value)
        with patch.object(control,'atomic',atomic):
            with self.assertRaises(control.CycleStopped) as caught:self.execute(FakeTransport(fail='timeout'))
        self.assertEqual(caught.exception.diagnostic['code'],'timeout')
        self.assertTrue(caught.exception.diagnostic['diagnostic_file_write_failed'])
        self.assertNotIn('synthetic-private-path',json.dumps(caught.exception.diagnostic))

    def test_local_ledger_failure_is_reported_before_any_transport(self):
        (self.packet/'ledger').mkdir()
        fake=FakeTransport()
        record=self.failure(fake)
        self.assertEqual(record['stage'],'ledger_create');self.assertEqual(fake.calls,[])
        self.assertFalse(record['dispatch_attempted'])
        self.assertEqual(control.status(self.packet)['requests_started'],0)

    def test_changed_starter_refused_before_credential_or_transport(self):
        (self.packet/'START_APPROVED_CYCLE.py').write_text('changed')
        fake=FakeTransport()
        with self.assertRaises(ValueError):self.execute(fake)
        self.assertEqual(fake.calls,[]);self.assertFalse((self.packet/'CYCLE.started').exists())

    def test_output_cap_failure_preserves_reported_count_and_reservation(self):
        record=self.failure(FakeTransport(fail='over_cap'))
        self.assertEqual(record['code'],'usage_exceeds_allowance')
        self.assertEqual(record['reported_usage']['output_tokens'],2048)
        self.assertGreater(float(control.status(self.packet)['reserved_upper_bound_usd']),0)

    def test_copied_execution_support_tampering_is_refused_before_dispatch(self):
        for name in ('muse_cycle.py','muse_diagnostics.py','muse_cycle_start.py'):
            p=self.packet/name;original=p.read_bytes();p.write_text('changed')
            fake=FakeTransport()
            with self.assertRaises(ValueError):self.execute(fake)
            self.assertEqual(fake.calls,[]);self.assertFalse((self.packet/'CYCLE.started').exists())
            p.write_bytes(original)

    def test_copied_starter_runs_only_fake_transport_without_checkout_name_assumptions(self):
        # The socket guard prevents any real request even if injection fails.
        control.atomic(self.packet/'OWNER_APPROVAL.json',control.load(self.approval()))
        namespace=runpy.run_path(str(self.packet/'START_APPROVED_CYCLE.py'))
        fake=FakeTransport();output=io.StringIO()
        from contextlib import redirect_stdout
        with patch.object(sys.stdin,'isatty',return_value=True),patch.dict(control.os.environ,{'MODEL_API_KEY':'synthetic-cycle-control-token'},clear=True),patch('urllib.request.build_opener',return_value=fake),redirect_stdout(output):
            self.assertEqual(namespace['main'](),0)
        self.assertEqual(fake.calls,['selection','reassessment'])
        self.assertEqual(control.status(self.packet)['status'],'complete')


    def test_real_transport_noninteractive_refused_before_markers_logs_or_credentials(self):
        class ForbiddenEnvironment(dict):
            def get(self,*args):raise AssertionError('Credential must not be read')
        approval=self.approval()
        with patch.object(sys.stdin,'isatty',return_value=False),patch.object(control.os,'environ',ForbiddenEnvironment(MODEL_API_KEY='synthetic-cycle-control-token')),patch.object(control.diagnostics,'send_approved') as transport:
            with self.assertRaisesRegex(ValueError,'interactive owner terminal'):
                control.run(self.packet,approval,allow_live=True,opener=None)
            transport.assert_not_called()
        self.assertFalse((self.packet/'CYCLE.started').exists())
        self.assertFalse((self.packet/'ledger').exists())
        self.assertFalse((self.packet/'study').exists())
        self.assertEqual(control.status(self.packet)['requests_started'],0)

    def test_copied_starter_with_preset_synthetic_key_requires_terminal_before_run(self):
        control.atomic(self.packet/'OWNER_APPROVAL.json',control.load(self.approval()))
        class Loader:
            def exec_module(self,module):pass
        class Spec:loader=Loader()
        class ForbiddenEnvironment(dict):
            def get(self,*args):raise AssertionError('Credential must not be read')
        with patch.object(sys.stdin,'isatty',return_value=False),patch('importlib.util.spec_from_file_location',return_value=Spec()),patch('importlib.util.module_from_spec',return_value=control),patch.object(control.os,'environ',ForbiddenEnvironment(MODEL_API_KEY='synthetic-cycle-control-token')),patch.object(control,'run') as runner,patch('getpass.getpass',side_effect=AssertionError('Must not prompt')):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(self.packet/'START_APPROVED_CYCLE.py'),run_name='__main__')
            self.assertEqual(stopped.exception.code,'Local approval/credential/startup check failed. No implicit send or retry. Inspect the packet; do not paste credentials into chat.')
            runner.assert_not_called()
        self.assertFalse((self.packet/'CYCLE.started').exists())
        self.assertFalse((self.packet/'ledger').exists())
        self.assertEqual(control.status(self.packet)['requests_started'],0)


if __name__=='__main__':unittest.main(verbosity=2)
