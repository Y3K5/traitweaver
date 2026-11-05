"""Research custody, selective context and provider-free integration."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import research_homes as m, study, workspace_server
from traitweaver.study_store import Conflict, Store
from traitweaver.completed_cycle import CompletedCycle
from test_review_handlers import MemoryServer
import test_molecular_handlers


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.s = m.Session()
        self.question()

    def question(self, text='Could GFP report the intended quantity in this receiving context?', old=None):
        self.s.act({'type':'question','question_id':old['event']['question_id'] if old else None,
                    'previous_hash':old['hash'] if old else None,'text':text,
                    'trait_id':'gfp-reporting','recipient_id':'ecoli'}, self.s.fingerprint())
        return self.s.history[-1]

    def selection(self, **kw):
        return {'claim_ids':['gfp-observation'],'include_question':True,'components':True,
                'dependencies':True,'study_plan':False,'note_hashes':[],'plan_hashes':[],**kw}

    def note(self, text='Synthetic background note: signal interpretation needs review.'):
        q=self.s.questions()[0]
        self.s.act({'type':'note','question_id':q['event']['question_id'],'question_hash':q['hash'],
                    'text':text,'provenance':'mock_pilot_note'},self.s.fingerprint())
        return self.s.history[-1]

    def packet(self, **kw):
        return self.s.packet(self.s.questions()[0]['hash'], self.selection(**kw))

    def save_packet(self):
        self.s.act({'type':'prepare','question_hash':self.s.questions()[0]['hash'],
                    'selection':self.selection()},self.s.fingerprint())
        return self.s.history[-1]

    def test_preview_is_nonmutating_and_never_reads_credentials_or_network(self):
        before=deepcopy(self.s.history)
        with patch('socket.socket',side_effect=AssertionError('No sockets')), patch('os.getenv',side_effect=AssertionError('No credentials')):
            p=self.packet()
        self.assertEqual(self.s.history,before)
        self.assertFalse(p['sending_enabled']);self.assertEqual(p['effective_limit_usd'],'0.00')
        self.assertEqual(p['actual_usage']['status'],'not_called')
        self.assertIsNone(p['actual_usage']['cost_usd'])
        self.assertEqual(study.decode(p['body']['input']),p['payload'])
        self.assertEqual(study.digest(p['body']),p['request_sha256'])

    def test_selection_has_source_closure_and_mandatory_caveats(self):
        p=self.packet(components=False,dependencies=False,study_plan=False)
        self.assertEqual([c['id'] for c in p['payload']['claims']],['gfp-observation'])
        self.assertEqual({s['id'] for s in p['payload']['sources']},{'GFP_1994','GFP_2010'})
        self.assertTrue(p['payload']['caveats'])
        self.assertEqual(p['payload']['claims'][0]['role'],'documented_observation')
        self.assertEqual(p['payload']['safety_and_limits']['transfer'],'untested')
        self.assertIn('gfp-transfer',[e['id'] for e in p['excluded']])

    def test_local_notes_are_opt_in_and_exact_provenance_survives(self):
        note=self.note('NOTE_SENTINEL local authored context')
        p=self.packet()
        self.assertNotIn('NOTE_SENTINEL',p['body']['input'])
        self.assertIn(note['hash'],[e['id'] for e in p['excluded']])
        selected=self.packet(note_hashes=[note['hash']])
        self.assertIn('NOTE_SENTINEL',selected['body']['input'])
        self.assertEqual(selected['payload']['local_notes'][0]['provenance'],'mock_pilot_note')

    def test_question_can_be_excluded_and_other_questions_never_enter(self):
        self.question('OTHER_QUESTION_SENTINEL')
        p=self.packet(include_question=False)
        self.assertIsNone(p['payload']['question']['text'])
        self.assertNotIn('OTHER_QUESTION_SENTINEL',p['body']['input'])

    def test_review_notes_never_enter_context(self):
        q=self.s.questions()[0]
        self.s.act({'type':'review','question_id':q['event']['question_id'],'target_hash':q['hash'],
                    'reviewer':'Synthetic reviewer','decision':'needs_evidence','reason':'REVIEW_NOTE_SENTINEL'},self.s.fingerprint())
        self.assertNotIn('REVIEW_NOTE_SENTINEL',study.canonical(self.packet()))

    def test_plan_amendments_are_opt_in_with_prior_context(self):
        q=self.s.questions()[0]
        e={'type':'plan_revision','question_id':q['event']['question_id'],'question_hash':q['hash'],
           'text':'PLAN_SENTINEL reconsider the baseline','reason':'Synthetic note motivates reconsideration','previous_plan_hash':None}
        self.s.act(e,self.s.fingerprint());row=self.s.history[-1]
        self.assertNotIn('PLAN_SENTINEL',self.packet()['body']['input'])
        p=self.packet(plan_hashes=[row['hash']])
        self.assertEqual(p['payload']['plan_amendments'][0]['question_revision_hash'],q['hash'])
        self.assertIn('PLAN_SENTINEL',p['body']['input'])
        with self.assertRaises(ValueError):self.s.act(e,self.s.fingerprint())

    def test_question_revision_preserves_old_packet_and_reviewer_binding(self):
        packet=self.save_packet();before=deepcopy(packet)
        old=self.s.questions()[0];new=self.question('A revised question with a narrower endpoint',old)
        self.assertEqual(packet,before)
        self.assertNotEqual(packet['event']['packet']['question_hash'],new['hash'])
        self.assertEqual(len(self.s.questions()),1)
        self.assertEqual(len(self.s.history),3)

    def test_invalid_selection_and_cross_question_notes_fail_closed(self):
        q2=self.question('Second question')
        self.s.act({'type':'note','question_id':q2['event']['question_id'],'question_hash':q2['hash'],
                    'text':'Other context','provenance':'local_note_unverified'},self.s.fingerprint())
        for changes in ({'claim_ids':[]},{'claim_ids':['gfp-observation']*2},{'claim_ids':['psr1-observation']},
                        {'components':'yes'},{'note_hashes':[self.s.history[-1]['hash']]},{'plan_hashes':['unknown']}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.packet(**changes)

    def test_private_note_is_retained_but_not_admitted_or_silently_scrubbed(self):
        note=self.note('Synthetic privacy fixture /Users/example/private.txt')
        before=deepcopy(self.s.history)
        self.packet()  # Excluding the local note is allowed.
        with self.assertRaisesRegex(ValueError,'privacy'):self.packet(note_hashes=[note['hash']])
        with self.assertRaisesRegex(ValueError,'privacy'):self.s.export(self.s.fingerprint())
        self.assertEqual(self.s.history,before)

    def test_stale_revision_and_fabricated_validation_do_not_append(self):
        old=self.s.fingerprint();self.note()
        with self.assertRaises(Conflict):self.s.act({'type':'question','question_id':None,'previous_hash':None,
            'text':'Stale question','trait_id':'gfp-reporting','recipient_id':'ecoli'},old)
        q=self.s.questions()[0]
        with self.assertRaises(ValueError):self.s.act({'type':'review','question_id':q['event']['question_id'],
            'target_hash':q['hash'],'reviewer':'Synthetic reviewer','decision':'lab_ready','reason':'Not authorized'},self.s.fingerprint())

    def test_mock_output_has_no_provider_receipt_or_charges(self):
        p=self.save_packet();self.s.act({'type':'mock','packet_hash':p['hash']},self.s.fingerprint())
        e=self.s.history[-1]['event'];self.assertEqual(e['provenance'],'authored_synthetic_example_no_model_call')
        self.assertEqual(e['packet_hash'],p['hash'])
        self.assertEqual(self.s.view()['new_provider_calls'],0)
        self.assertNotIn('provider_receipt',e)

    def test_export_reopen_and_restart_preserve_exact_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.s=m.Session(Path(tmp)/'research')
            self.question();self.note();self.save_packet()
            durable=self.s
            before=deepcopy(durable.history)
            restored=m.Session(Path(tmp)/'research')
            self.assertEqual(restored.history,before)
            package=restored.export(restored.fingerprint())
            opened=m.Session.from_package(package)
            self.assertTrue(opened.read_only);self.assertEqual(opened.history,before)
            with self.assertRaises(ValueError):opened.act({'type':'mock','packet_hash':before[-1]['hash']},opened.fingerprint())

    def test_rehashed_packet_tamper_is_rejected_against_original_sources(self):
        self.save_packet();p=self.s.export(self.s.fingerprint())
        row=p['history'][-1];row['event']['packet']['payload']['claims'][0]['text']='Fabricated result'
        row['hash']=study.digest({k:v for k,v in row.items() if k!='hash'})
        with self.assertRaises(ValueError):m.Session.from_package(p)

    def test_storage_cannot_use_application_or_symlink(self):
        with self.assertRaises(ValueError):m.Session(study.APP_ROOT/'test-research-data')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'real').mkdir();(root/'alias').symlink_to(root/'real',target_is_directory=True)
            with self.assertRaises(ValueError):m.Session(root/'alias'/'data')


class ResearchHandlers(unittest.TestCase):
    request=test_molecular_handlers.MolecularHandlerTests.request
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'study');self.addCleanup(self.store.close)
        guard=patch('socket.socket',side_effect=AssertionError('No network'));guard.start();self.addCleanup(guard.stop)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']
    def body(self,**kw):
        return {'expected_hash':self.server.workspace.active.current()['hash'],
                'research_hash':self.server.workspace.research_homes.fingerprint(),**kw}
    def action(self):
        return {'type':'question','question_id':None,'previous_hash':None,'text':'Synthetic test question',
                'trait_id':'gfp-reporting','recipient_id':'ecoli'}
    def test_question_uses_separate_durable_owner_and_preserves_original_study(self):
        before=self.store.export();old_library=self.server.workspace.trait_library.export(self.server.workspace.trait_library.fingerprint())
        self.assertEqual(self.request('/api/research/act',self.body(action=self.action()))[0],200)
        self.assertEqual(self.store.export(),before)
        self.assertEqual(self.server.workspace.trait_library.export(self.server.workspace.trait_library.fingerprint()),old_library)
        self.assertTrue((self.store.root/'research-homes-v1/000001.json').is_file())
    def test_origin_token_and_stale_binding_block_actions(self):
        body=self.body(action=self.action())
        for headers in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/research/act',body,headers)[0],403)
        body['research_hash']='stale';self.assertEqual(self.request('/api/research/act',body)[0],409)
    def test_no_provider_route_or_automatic_export(self):
        self.assertEqual(self.request('/api/research/send',self.body())[0],404)
        self.assertEqual(self.request('/api/research/export.json')[0],400)
    def test_reopen_read_only_then_return_retains_local_owner(self):
        owner=self.server.workspace.research_homes
        self.request('/api/research/act',self.body(action=self.action()))
        package=owner.export(owner.fingerprint())
        self.assertEqual(self.request('/api/research/open',self.body(package_json=study.canonical(package)))[0],200)
        self.assertTrue(self.server.workspace.research_homes.read_only)
        self.assertEqual(self.request('/api/research/local',self.body())[0],200)
        self.assertIs(self.server.workspace.research_homes,owner)
    def test_demo_remains_read_only_while_research_questions_are_editable(self):
        demo=CompletedCycle(study.APP_ROOT/'data/synthetic-cycle');before=demo.export_review()
        self.server=workspace_server.make_server(demo,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']
        self.assertEqual(self.request('/api/research/act',self.body(action=self.action()))[0],200)
        self.assertEqual(demo.export_review(),before)


if __name__=='__main__':unittest.main()
