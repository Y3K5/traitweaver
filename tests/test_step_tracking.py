"""Source-bound completed checks and actual local handler integration, offline."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import step_tracking as s,study,workspace_server
from traitweaver.study_store import Store,Conflict
from test_review_handlers import MemoryServer
import test_molecular_handlers as mh


class StepTests(unittest.TestCase):
    def test_read_does_not_run_check_or_write_to_explicit_storage(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'tracking'
            with patch.object(s,'run_check',side_effect=AssertionError('No dispatch')):
                j=s.Journal(root);self.assertEqual(j.view()['projection']['steps'][0]['status'],'not_started');j.export()
            self.assertFalse(root.exists())

    def test_pre_result_decision_saved_before_actual_check_and_completion_scoped(self):
        with tempfile.TemporaryDirectory() as t:
            j=s.Journal(Path(t)/'tracking');original=s.run_check
            def checked(cid):
                self.assertEqual(j.current()['action']['type'],'decide');self.assertIsNone(j.current()['state']['attempts'][-1]['result'])
                self.assertTrue((j.root/'revision-000002.json').exists());return original(cid)
            with patch.object(s,'run_check',side_effect=checked):j.apply(j.current()['hash'],{'type':'check','payload':{}})
            p=j.view()['projection'];self.assertEqual(p['steps'][0]['status'],'completed');self.assertEqual(p['steps'][1]['status'],'unresolved')
            self.assertEqual(p['steps'][0]['completion_receipt']['record_ids'],['RNA_SAMPLES'])
            self.assertIn('synthetic',p['limit']);self.assertEqual(j.current()['revision'],3)

    def test_restart_and_read_only_reopen_preserve_receipt_without_dispatch(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'tracking';j=s.Journal(root);j.apply(j.current()['hash'],{'type':'check','payload':{}});before=j.export()
            with patch.object(s,'run_check',side_effect=AssertionError('No rerun')):
                reloaded=s.Journal(root);opened=s.Journal.from_package(before)
                self.assertEqual(reloaded.export(),before);self.assertEqual(opened.export(),before)
            with self.assertRaises(ValueError):opened.apply(opened.current()['hash'],{'type':'check','payload':{}})
            with self.assertRaises(ValueError):reloaded.apply(reloaded.current()['hash'],{'type':'check','payload':{}})

    def test_changed_source_needs_reassessment_and_bad_metadata_is_blocked(self):
        j=s.Journal();j.apply(j.current()['hash'],{'type':'check','payload':{}});first=j.current()['hash']
        j.apply(j.current()['hash'],{'type':'source','payload':{'case_id':'RNA_BEFORE'}})
        self.assertEqual(j.view()['projection']['steps'][0]['status'],'needs_reassessment')
        self.assertIsNone(j.view()['projection']['steps'][0]['completion_receipt'])
        j.apply(j.current()['hash'],{'type':'check','payload':{}});step=j.view()['projection']['steps'][0]
        self.assertEqual(step['status'],'blocked');self.assertEqual(step['completion_receipt']['duplicates'],['SYN-B'])
        self.assertTrue(any(r['hash']==first for r in j.history))
        j.apply(j.current()['hash'],{'type':'source','payload':{'case_id':'RNA_AFTER'}})
        self.assertEqual(j.view()['projection']['steps'][0]['status'],'completed')

    def test_stale_edit_and_model_requested_completion_cannot_mark_done(self):
        j=s.Journal();head=j.current()['hash']
        with self.assertRaises(Conflict):j.apply('0'*64,{'type':'check','payload':{}})
        for action in ({'type':'complete','payload':{'action_id':'RNA_RECONCILE'}},{'type':'result','payload':{}},{'type':'source','payload':{'case_id':'PRIVATE_CASE'}},{'type':'decide','payload':{'action_id':'RUN_SHELL'}}):
            with self.assertRaises(ValueError):j.apply(j.current()['hash'],action)
        self.assertEqual(j.current()['hash'],head)

    def test_forged_or_stale_receipt_and_tampered_sources_fail_even_if_rehashed(self):
        j=s.Journal();j.apply(j.current()['hash'],{'type':'source','payload':{'case_id':'RNA_BEFORE'}});j.apply(j.current()['hash'],{'type':'check','payload':{}})
        p=j.export();bad=deepcopy(p);r=bad['revisions'][-1];r['state']['attempts'][-1]['result']['status']='passed';r['hash']=study.digest({k:v for k,v in r.items() if k!='hash'})
        with self.assertRaises(ValueError):s.validate_package(bad)
        bad=deepcopy(p);bad['sources'][0]['records'][-1]['value']['read_count']=0
        with self.assertRaises(ValueError):s.validate_package(bad)
        bad=deepcopy(p);bad['revisions'][-1]['parent_hash']='0'*64
        with self.assertRaises(ValueError):s.validate_package(bad)

    def test_local_failure_is_recorded_without_secret_text_or_completion(self):
        j=s.Journal()
        with patch.object(s,'run_check',side_effect=RuntimeError('SYNTHETIC_PRIVATE_ERROR_CANARY')):j.apply(j.current()['hash'],{'type':'check','payload':{}})
        self.assertEqual(j.view()['projection']['steps'][0]['status'],'failed');self.assertNotIn('SYNTHETIC_PRIVATE_ERROR_CANARY',study.canonical(j.export()))

    def test_interrupted_result_save_preserves_valid_prior_work_and_no_false_completion(self):
        with tempfile.TemporaryDirectory() as t:
            j=s.Journal(Path(t)/'tracking');original=s.os.link
            def link(a,b):
                if Path(b).name=='revision-000003.json':raise OSError('Synthetic interrupted result save')
                return original(a,b)
            with patch.object(s.os,'link',side_effect=link),self.assertRaises(OSError):j.apply(j.current()['hash'],{'type':'check','payload':{}})
            loaded=s.Journal(j.root);self.assertEqual(loaded.view()['projection']['steps'][0]['status'],'in_progress')
            self.assertFalse((j.root/'revision-000003.json').exists());self.assertFalse(list(j.root.glob('.pending-*')))

    def test_malformed_package_fails_safely_with_no_private_value_echo(self):
        j=s.Journal();p=j.export();p['revisions'][0]['saved_utc']='SYNTHETIC_PRIVATE_TIMESTAMP_CANARY'
        with self.assertRaises(ValueError) as e:s.validate_package(p)
        self.assertNotIn('SYNTHETIC_PRIVATE_TIMESTAMP_CANARY',str(e.exception))
        for v in (None,{},[],{'revisions':[{}]}):
            with self.assertRaises(ValueError):s.validate_package(v)


class StepHandlerTests(unittest.TestCase):
    request=mh.MolecularHandlerTests.request
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);self.store=Store(self.root/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer);self.token=self.request('/api/session')[1]['token']
    def body(self,**values):return {'expected_hash':self.server.workspace.active.current()['hash'],'steps_hash':self.server.workspace.steps.current()['hash'],**values}
    def post(self,name,**values):return self.request('/api/steps/'+name,self.body(**values))

    def test_check_export_reopen_and_return_local_do_not_mutate_original_study(self):
        before=self.store.export();self.assertEqual(self.post('check')[0],200)
        value=self.request('/api/steps/export.json')[1];self.assertEqual(self.post('open',package_json=study.canonical(value))[0],200)
        self.assertTrue(self.server.workspace.steps.read_only);self.assertEqual(self.post('check')[0],400)
        self.assertEqual(self.post('local')[0],200);self.assertFalse(self.server.workspace.steps.read_only)
        self.assertEqual(self.server.workspace.steps.view()['projection']['steps'][0]['status'],'completed');self.assertEqual(self.store.export(),before)

    def test_stale_hash_session_origin_and_extra_arguments_cannot_dispatch(self):
        b=self.body()
        for values,headers,expected in ((dict(b,steps_hash='0'*64),None,409),(b,{'Origin':'https://outside.invalid'},403),(b,{'X-Traitweaver-Token':''},403),(dict(b,script='unknown'),None,400)):
            with patch.object(s,'run_check',side_effect=AssertionError('No dispatch')):self.assertEqual(self.request('/api/steps/check',values,headers)[0],expected)
        self.assertEqual(self.post('source',case_id='RNA_BEFORE')[0],200)
        self.assertEqual(self.request('/api/steps/check',b)[0],409)

    def test_changed_export_revision_and_bad_import_leave_current_records(self):
        h=self.server.workspace.steps.current()['hash'];self.post('check');before=self.server.workspace.steps.export()
        self.assertEqual(self.request('/api/steps/export.json',None,{'X-Traitweaver-Expected-Revision':h})[0],409)
        self.assertEqual(self.post('open',package_json='{}')[0],400);self.assertEqual(self.server.workspace.steps.export(),before)
        self.assertEqual(self.post('run-model')[0],404)


if __name__=='__main__':unittest.main()
