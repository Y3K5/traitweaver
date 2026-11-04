"""Synthetic saved-reply custody and accounting tests. No provider calls."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import research_homes, research_runs as runs, study
from test_research_homes import ResearchHandlers


def prepare(session):
    session.act({'type':'question','question_id':None,'previous_hash':None,
                 'text':'Synthetic question about phosphorus evidence, not an actual study.',
                 'trait_id':'psr1-uptake','recipient_id':'alga'}, session.fingerprint())
    q=session.history[-1]
    session.act({'type':'prepare','question_hash':q['hash'], 'selection':{
        'claim_ids':['psr1-observation','psr1-inference'],'include_question':True,
        'components':True,'dependencies':True,'study_plan':True,'note_hashes':[],'plan_hashes':[]}}, session.fingerprint())
    return session.history[-1]


def fixture(packet_row, failed=False):
    packet=packet_row['event']['packet']; request=study.canonical(packet['body'])
    suggestions=[{'claim_ids':['psr1-observation'],'source_ids':['PSR1_2023'],
                  'gap':'Synthetic gap for a software test.', 'proposed_check':'Synthetic review only.'}]
    usage={'input_tokens':100,'output_tokens':20,'total_tokens':120,
           'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':5}}
    reply={'error':{'code':'invalid_api_key','message':'Synthetic authentication failure'}} if failed else {
        'status':'completed','model':'muse-spark-1.3','usage':usage,
        'output':[{'type':'message','content':[{'type':'output_text','text':study.canonical({'suggestions':suggestions})}]}]}
    response=study.canonical(reply)
    ledger={'request_sha256':runs.fingerprint(request),'response_sha256':runs.fingerprint(response),
            'provider':'Meta direct','model':'muse-spark-1.3','attempt_number':1,'retry_allowed':False,
            'synthetic':True,'provenance':'synthetic_transport_test',
            'started_utc':'2026-01-01T00:00:00+00:00','finished_utc':'2026-01-01T00:00:01+00:00',
            'http_status':401 if failed else 200,'scientific_review':'pending','reviewer_decision':None,
            'reported_usage':None if failed else usage,'token_derived_cost_usd':None if failed else '0.00021000',
            'provider_settled_charge_usd':None,'local_budget_usd':'0.05',
            'unsettled_reservation_usd':'0.045396' if failed else '0.00'}
    validation={'scientific_review':'pending','laboratory_ready':False,'suggestions':None if failed else suggestions,
                'status':'needs_review' if failed else 'structure_checked_human_review_pending'}
    values={'EXACT_REQUEST_BODY.json':request,'RESPONSE_BODY.json':response,
            'USAGE_LEDGER.json':study.canonical(ledger),'LOCAL_VALIDATION.json':study.canonical(validation)}
    package={'schema_version':runs.SCHEMA,'run_id':'reply-'+study.digest({'request':ledger['request_sha256'],
        'response':ledger['response_sha256'],'started':ledger['started_utc']})[:20],
        'artifacts':{n:{'text':t,'sha256':runs.fingerprint(t)} for n,t in values.items()}}
    return {'type':'provider_attempt','question_id':packet_row['event']['question_id'],
            'packet_hash':packet_row['hash'],'run':package}


class RunTests(unittest.TestCase):
    def setUp(self):
        self.s=research_homes.Session(); self.packet=prepare(self.s)
        self.e=fixture(self.packet)
        guard=patch('socket.socket',side_effect=AssertionError('No network'));guard.start();self.addCleanup(guard.stop)

    def mutate_file(self,name,fn):
        artifact=self.e['run']['artifacts'][name];value=study.decode(artifact['text']);fn(value)
        artifact['text']=study.canonical(value);artifact['sha256']=runs.fingerprint(artifact['text'])

    def test_success_and_failure_remain_separate_without_changing_packet(self):
        old=deepcopy(self.s.history)
        for event in [fixture(self.packet,True),self.e]:self.s.act(event,self.s.fingerprint())
        self.assertEqual(self.s.history[:2],old)
        failed,success=self.s.view()['saved_runs']
        self.assertIsNone(failed['cost_usd']);self.assertIsNone(failed['usage'])
        self.assertEqual(failed['unsettled_reservation_usd'],'0.045396')
        self.assertEqual(success['cost_usd'],'0.00021');self.assertTrue(success['synthetic'])
        self.assertEqual(self.s.view()['new_provider_calls'],0);self.assertFalse(self.s.view()['live_enabled'])

    def test_exact_bytes_tamper_rejected(self):
        self.e['run']['artifacts']['EXACT_REQUEST_BODY.json']['text']+=' '
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_different_packet_cannot_take_reply(self):
        other=research_homes.Session();other_packet=prepare(other)
        other_packet=deepcopy(other_packet);other_packet['event']['packet']['request_sha256']='0'*64
        with self.assertRaises(ValueError):runs.validate(self.e['run'],other_packet['event']['packet'])

    def test_duplicate_attempt_blocked(self):
        self.s.act(self.e,self.s.fingerprint())
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_unknown_usage_cannot_be_zero_cost(self):
        self.e=fixture(self.packet,True)
        self.mutate_file('USAGE_LEDGER.json',lambda x:x.update(token_derived_cost_usd='0.00'))
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_edited_cost_rejected(self):
        self.mutate_file('USAGE_LEDGER.json',lambda x:x.update(token_derived_cost_usd='0.01'))
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_provider_and_synthetic_role_cannot_be_silently_changed(self):
        self.mutate_file('USAGE_LEDGER.json',lambda x:x.update(provenance='actual_direct_meta_attempt'))
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_scientific_promotion_rejected(self):
        self.mutate_file('LOCAL_VALIDATION.json',lambda x:x.update(laboratory_ready=True))
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_extra_artifacts_and_private_paths_blocked(self):
        self.e['run']['artifacts']['extra.json']={'text':'{}','sha256':runs.fingerprint('{}')}
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())
        self.e=fixture(self.packet)
        self.mutate_file('LOCAL_VALIDATION.json',lambda x:x.update(note='/Users/synthetic/private-note'))
        with self.assertRaises(ValueError):self.s.act(self.e,self.s.fingerprint())

    def test_import_reader_ignores_unrelated_files_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for n,a in self.e['run']['artifacts'].items():(root/n).write_text(a['text'])
            (root/'do-not-read.txt').write_text('unrelated synthetic context')
            p=runs.from_directory(root);self.assertEqual(p,self.e['run'])
            f=root/'RESPONSE_BODY.json';f.rename(root/'moved');f.symlink_to(root/'moved')
            with self.assertRaises(ValueError):runs.from_directory(root)

    def test_run_and_human_review_survive_restart_and_read_only_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=research_homes.Session(Path(tmp)/'records');packet=prepare(s)
            s.act(fixture(packet),s.fingerprint());target=s.history[-1]
            s.act({'type':'review','question_id':target['event']['question_id'],'target_hash':target['hash'],
                   'reviewer':'Synthetic reviewer','decision':'needs_evidence','reason':'Synthetic planning review only.'},s.fingerprint())
            restored=research_homes.Session(Path(tmp)/'records');self.assertEqual(s.history,restored.history)
            reopened=research_homes.Session.from_package(s.export(s.fingerprint()))
            self.assertTrue(reopened.read_only);self.assertEqual(reopened.view()['saved_runs'],s.view()['saved_runs'])
            with self.assertRaises(ValueError):reopened.act(fixture(packet,True),reopened.fingerprint())

    def test_replies_and_reviews_never_enter_a_future_context(self):
        self.s.act(self.e,self.s.fingerprint())
        p=self.s.packet(self.packet['event']['packet']['question_hash'],self.packet['event']['packet']['selection'])
        self.assertEqual(p,self.packet['event']['packet'])


class RunHandlers(ResearchHandlers):
    def test_import_via_existing_action_is_local_only_and_bound(self):
        owner=self.server.workspace.research_homes;packet=prepare(owner);before=self.store.export()
        code,payload=self.request('/api/research/act',self.body(action=fixture(packet)))
        self.assertEqual(code,200);self.assertEqual(len(payload['research_homes']['saved_runs']),1)
        self.assertEqual(self.store.export(),before)
        self.assertEqual(self.request('/api/research/send',self.body())[0],404)


if __name__=='__main__':unittest.main()
