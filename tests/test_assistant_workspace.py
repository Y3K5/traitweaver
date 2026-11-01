"""Actual local assistant sessions and handler dispatch, all sockets prohibited."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import assistant, assistant_workspace as model, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
from test_review_handlers import MemoryServer
import test_molecular_handlers as molecular_handlers


class AssistantWorkspaceTests(unittest.TestCase):
    request=molecular_handlers.MolecularHandlerTests.request

    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        p=patch('socket.socket',side_effect=AssertionError('No sockets'));p.start();self.addCleanup(p.stop)
        self.store=Store(self.folder/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def body(self,**values):
        return {'expected_hash':self.server.workspace.active.current()['hash'],
                'assistant_hash':self.server.workspace.assistant.current()['hash'],**values}

    def post(self,name,**values):return self.request('/api/assistant/'+name,self.body(**values))

    def test_four_cases_available_without_accepting_a_response_or_running_a_tool(self):
        with patch.object(model,'run_local_check',side_effect=AssertionError('No tool on state read')):
            code,value=self.request('/api/state')
        self.assertEqual(code,200);v=value['assistant']
        self.assertEqual(len(v['cases']),4);self.assertIsNone(v['review']);self.assertEqual(v['checks'],[])
        self.assertFalse(v['live_enabled']);self.assertEqual(v['transport_calls'],0)

    def test_all_cases_actual_checks_actions_and_json_text_reopen_preserve_records(self):
        before=self.store.export()
        for case_id in model.TITLES:
            with self.subTest(case=case_id):
                self.assertEqual(self.post('select',case_id=case_id)[0],200)
                self.assertEqual(self.post('check')[0],200);self.assertEqual(self.post('synthetic')[0],200)
                code,package=self.request('/api/assistant/export.json');self.assertEqual(code,200)
                v=self.request('/api/state')[1]['assistant'];hash_before=v['current']['hash']
                self.assertEqual(len(v['review']['actions']),3);self.assertEqual(len(v['checks']),1)
                code,text=self.request('/api/assistant/export.txt');self.assertEqual(code,200)
                for action in v['review']['actions']:self.assertIn(study.canonical(action),text)
                self.assertIn('synthetic_fixture',text);self.assertIn(study.canonical(v['checks']),text)
                with patch.object(model,'run_local_check',side_effect=AssertionError('No rerun on open')):
                    self.assertEqual(self.post('open',package_json=study.canonical(package))[0],200)
                reopened=self.request('/api/state')[1]['assistant']
                self.assertTrue(reopened['read_only']);self.assertEqual(reopened['review'],v['review'])
                self.assertEqual(reopened['checks'],v['checks']);self.assertNotEqual(reopened['current']['hash'],hash_before)
                self.assertEqual(self.request('/api/assistant/export.json')[1],package)
                self.assertEqual(self.post('check')[0],400);self.assertEqual(self.post('synthetic')[0],400)
        self.assertEqual(self.store.export(),before)

    def test_pre_result_decision_is_present_before_dispatch_and_failures_are_preserved(self):
        owner=self.server.workspace.assistant
        def broken(case_id):
            receipt=owner.current()['state']['checks'][0]
            self.assertEqual(receipt['decision']['policy'],'explicit_user_selected_local_check')
            self.assertIsNone(receipt['result'])
            raise RuntimeError('SYNTHETIC_PRIVATE_EXCEPTION_DETAIL')
        with patch.object(model,'run_local_check',side_effect=broken):self.assertEqual(self.post('check')[0],200)
        v=self.request('/api/state')[1]['assistant'];self.assertEqual(v['checks'][0]['result']['status'],'failed')
        self.assertNotIn('SYNTHETIC_PRIVATE_EXCEPTION_DETAIL',study.canonical(v))
        self.assertEqual(self.post('check')[0],400)

    def test_rna_and_repro_audits_preserve_zero_null_conflicts_and_withhold_analysis(self):
        self.post('select',case_id='RNA_SYNTHETIC');v=self.post('check')[1]['assistant']['checks'][0]['result']
        self.assertEqual(v['duplicates'],['SYN-T2']);self.assertEqual(v['layout_conflicts'],['SYN-T1'])
        self.assertEqual(v['fastq_files_supplied'],0);self.assertIsNone(v['read_count']);self.assertFalse(v['analysis_ready'])
        self.post('select',case_id='REPRO_SYNTHETIC');v=self.post('check')[1]['assistant']['checks'][0]['result']
        self.assertEqual(v['exit_code'],0);self.assertIn('REP_RUN.command',v['missing_fields'])
        self.assertFalse(v['reproducibility_verified'])

    def test_native_cli_assistant_package_reopens_in_browser_contract(self):
        cid='PROTEIN_GFP';preview=assistant.prepare(cid)
        record=assistant.parse_reply(cid,study.canonical(assistant.synthetic_reply(cid)).encode(),preview['request_sha256'])
        self.assertEqual(self.post('open',package_json=study.canonical(assistant.package(record)))[0],200)
        v=self.request('/api/state')[1]['assistant'];self.assertEqual(v['case']['case_id'],cid)
        self.assertEqual(v['review'],record);self.assertEqual(v['checks'],[]);self.assertTrue(v['read_only'])

    def test_case_slots_survive_switching_and_read_only_open_without_disk_writes(self):
        self.post('check');self.post('synthetic');local=deepcopy(self.server.workspace.assistant.current()['state'])
        package=self.request('/api/assistant/export.json')[1]
        self.post('select',case_id='RNA_SYNTHETIC');self.post('synthetic')
        self.post('open',package_json=study.canonical(package))
        self.post('select',case_id='ENV_ALGAE')
        self.assertEqual(self.server.workspace.assistant.current()['state'],local)
        self.assertFalse(self.server.workspace.assistant.view()['read_only'])
        self.assertEqual(sorted(p.name for p in self.store.root.iterdir()),['.workspace-owner.lock','revision-000001.json'])

    def test_expected_study_and_assistant_hashes_origin_and_session_required(self):
        b=self.body(case_id='RNA_SYNTHETIC')
        for headers in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/assistant/select',b,headers)[0],403)
        self.assertEqual(self.request('/api/assistant/select',{**b,'expected_hash':'0'*64})[0],409)
        self.assertEqual(self.request('/api/assistant/select',{**b,'assistant_hash':'0'*64})[0],409)
        self.assertEqual(self.request('/api/assistant/select',b)[0],200)
        self.assertEqual(self.request('/api/assistant/select',b)[0],409)

    def test_invalid_unknown_or_extra_action_arguments_cannot_dispatch(self):
        before=self.server.workspace.assistant.current()
        with patch.object(model,'run_local_check',side_effect=AssertionError('No dispatch')):
            self.assertEqual(self.post('select',case_id='invented')[0],400)
            self.assertEqual(self.post('check',script='unavailable')[0],400)
            self.assertEqual(self.post('send')[0],404)
        self.assertEqual(self.server.workspace.assistant.current(),before)

    def test_export_requires_review_and_is_bound_to_displayed_case_identity(self):
        self.assertEqual(self.request('/api/assistant/export.json')[0],400)
        self.post('synthetic');old=self.server.workspace.assistant.current()['hash']
        headers={'X-Traitweaver-Expected-Revision':old}
        self.assertEqual(self.request('/api/assistant/export.json',headers=headers)[0],200)
        self.post('select',case_id='PROTEIN_GFP')
        self.assertEqual(self.request('/api/assistant/export.json',headers=headers)[0],409)

    def test_corrupt_package_and_changed_check_result_leave_selected_review_intact(self):
        self.post('check');self.post('synthetic');pkg=self.request('/api/assistant/export.json')[1]
        before=self.server.workspace.assistant.current()
        changed=deepcopy(pkg);changed['local_checks'][0]['result']['coverage']['rows'][0]['state']='reported_summary'
        changed['sha256']=study.digest({k:v for k,v in changed.items() if k!='sha256'})
        for raw in ('{bad',study.canonical(changed),study.canonical({'schema_version':'unknown'}),' '*262145):
            self.assertEqual(self.post('open',package_json=raw)[0],400)
            self.assertEqual(self.server.workspace.assistant.current(),before)

    def test_independent_assistant_can_be_used_next_to_completed_cycle_without_changing_it(self):
        cycle=CompletedCycle.from_file('data/synthetic-cycle/REVIEW_PACKAGE.json')
        self.server=workspace_server.make_server(cycle,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token'];before=cycle.export_review()
        self.assertEqual(self.post('check')[0],200);self.assertEqual(self.post('synthetic')[0],200)
        self.assertEqual(cycle.export_review(),before)

    def test_unavailable_catalog_does_not_disable_original_study(self):
        with patch.object(model,'Session',side_effect=ValueError('Synthetic source failure')):
            server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.server=server;self.token=self.request('/api/session')[1]['token']
        value=self.request('/api/state')[1];self.assertIsNone(value['assistant'])
        self.assertEqual(value['current'],self.store.current());self.assertIn('failed validation',value['assistant_error'])


if __name__=='__main__':unittest.main()
