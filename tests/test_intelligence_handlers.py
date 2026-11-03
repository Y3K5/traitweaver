"""Actual dispatch in memory: no HTTP/API requests or socket binding."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_muse as ai, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
from test_completed_cycle import fixture
import test_molecular_handlers as molecular_handlers
from test_review_handlers import MemoryServer


class IntelligenceHandlerTests(unittest.TestCase):
    request=molecular_handlers.MolecularHandlerTests.request

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name)
        guard=patch('socket.socket',side_effect=AssertionError('No sockets'));guard.start();self.addCleanup(guard.stop)
        self.store=Store(self.folder/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def body(self,**items):
        return {'expected_hash':self.server.workspace.active.current()['hash'],'intelligence_hash':self.server.workspace.intelligence.current()['hash'],**items}

    def save_scope(self,**changes):
        scope=m.initial_scope();scope.update(changes)
        return self.request('/api/intelligence/revise',self.body(scope=scope))

    def example(self,phase='selection',focus='trait'):
        return self.request('/api/intelligence/synthetic',self.body(phase=phase,focus=focus))

    def test_state_adds_public_intelligence_and_never_enables_transport(self):
        code,value=self.request('/api/state');self.assertEqual(code,200)
        self.assertFalse(value['intelligence']['live_enabled']);self.assertEqual(value['intelligence']['transport_calls'],0)
        self.assertEqual(value['intelligence']['catalog']['candidates'][0]['protein_id'],'XP_001700553.1')

    def test_scope_writes_only_new_journal_and_persists_next_to_other_reviews(self):
        before=self.store.export();legacy=self.server.workspace.molecular.current();public=self.server.workspace.public_algae.current()
        self.assertEqual(self.save_scope()[0],200)
        self.assertEqual(self.store.export(),before);self.assertEqual(self.server.workspace.molecular.current(),legacy);self.assertEqual(self.server.workspace.public_algae.current(),public)
        self.assertTrue((self.store.root/'intelligence-review-v1/revision-000001.json').is_file())

    def test_three_foci_record_decisions_actual_checks_and_separate_reassessments(self):
        self.save_scope(target_endpoint='phosphate_uptake')
        for focus in m.FOCI:
            self.assertEqual(self.example(focus=focus)[0],200)
            self.assertEqual(self.request('/api/intelligence/run',self.body())[0],200)
            self.assertEqual(self.example('reassessment',focus)[0],200)
        c=self.request('/api/state')[1]['intelligence']['current']['state']['cycles']
        self.assertEqual([x['result']['outcome'] for x in c],['supported','unavailable','unavailable'])
        for x in c:self.assertEqual(x['assessment']['result_id'],x['result']['id'])

    def test_continuation_view_and_rejected_repeat_do_not_dispatch_or_save(self):
        self.save_scope();self.example();self.request('/api/intelligence/run',self.body());self.example('reassessment')
        j=self.server.workspace.intelligence;before=j.export()
        with patch.object(m,'run_check',side_effect=AssertionError('No repeat dispatch')):
            code,value=self.request('/api/state');self.assertEqual(code,200)
            preview=value['intelligence']['continuation']
            self.assertEqual(preview['kind'],'deterministic_local_preview')
            self.assertEqual(preview['checks'][0]['status'],'already_checked')
            self.assertEqual(self.example()[0],400)
        self.assertEqual(j.export(),before)

    def test_actual_proposal_check_is_gated_even_when_focus_is_different(self):
        self.save_scope();self.example();self.request('/api/intelligence/run',self.body());self.example('reassessment')
        j=self.server.workspace.intelligence;s=j.current()['state'];before=j.export()
        req=ai.prepare(s,'selection',j.bundle,'combinations')
        # Focus is a preference in v1. A structurally valid reply may choose another check.
        reply=ai.synthetic_reply(s,'selection',j.bundle,'trait')
        with patch.object(m,'run_check',side_effect=AssertionError('No rejected dispatch')):
            code,_=self.request('/api/intelligence/accept',self.body(phase='selection',focus='combinations',request_sha256=req['request_sha256'],reply=study.canonical(reply)))
        self.assertEqual(code,400);self.assertEqual(j.export(),before)

    def test_continuation_reopen_reconstructs_exact_preview_without_dispatch(self):
        self.save_scope();self.example();self.request('/api/intelligence/run',self.body());self.example('reassessment')
        p=self.request('/api/intelligence/export.json')[1]
        before=self.request('/api/state')[1]['intelligence']['continuation']
        with patch.object(m,'run_check',side_effect=AssertionError('No reopen dispatch')):
            code,value=self.request('/api/intelligence/open',self.body(package_json=study.canonical(p)))
            self.assertEqual(code,200);self.assertTrue(value['intelligence']['read_only'])
            self.assertEqual(value['intelligence']['continuation'],before)
        self.assertEqual(self.request('/api/intelligence/export.json')[1],p)

    def test_origin_token_and_both_revision_identities_are_required(self):
        for h in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):self.assertEqual(self.request('/api/intelligence/revise',self.body(scope=m.initial_scope()),h)[0],403)
        old=self.body(scope=m.initial_scope());self.assertEqual(self.request('/api/intelligence/revise',old)[0],200)
        self.assertEqual(self.request('/api/intelligence/revise',old)[0],409)
        self.assertEqual(self.request('/api/intelligence/revise',{**self.body(scope=m.initial_scope()),'expected_hash':'b'*64})[0],409)

    def test_preparation_is_readonly_and_excludes_study_free_text(self):
        self.save_scope();before=self.server.workspace.intelligence.current()
        code,r=self.request('/api/intelligence/prepare',self.body(phase='selection',focus='trait'));self.assertEqual(code,200)
        self.assertEqual(r['prepared']['status'],'not_sent');self.assertNotIn('context_notes',r['prepared']['body']['input'])
        self.assertEqual(self.server.workspace.intelligence.current(),before)

    def test_rejected_saved_response_cannot_execute_a_tool_or_create_a_revision(self):
        self.save_scope();j=self.server.workspace.intelligence;s=j.current()['state'];req=ai.prepare(s,'selection',j.bundle)
        reply=ai.synthetic_reply(s,'selection',j.bundle,'trait');p=study.decode(reply['output'][0]['content'][0]['text']);p['claim_codes']=['successful_transfer'];reply['output'][0]['content'][0]['text']=study.canonical(p)
        with patch.object(m,'run_check',side_effect=AssertionError('Rejected output cannot dispatch')):
            code,_=self.request('/api/intelligence/accept',self.body(phase='selection',focus='trait',request_sha256=req['request_sha256'],reply=study.canonical(reply)))
        self.assertEqual(code,400);self.assertEqual(j.current()['revision'],1)

    def test_context_change_blocks_stale_execution_and_retains_earlier_decision(self):
        self.save_scope();self.example();old=self.server.workspace.intelligence.current()
        brief=self.store.current()['state']['brief'];brief['minimum_growth_ratio']=0
        self.store.apply(self.store.current()['hash'],{'type':'edit','payload':brief})
        self.assertEqual(self.request('/api/state')[1]['intelligence']['context_status'],'needs_review')
        self.assertEqual(self.request('/api/intelligence/run',self.body())[0],409)
        self.assertEqual(self.server.workspace.intelligence.current(),old)
        self.save_scope();self.assertEqual(self.server.workspace.intelligence.current()['state']['cycles'][0]['applicability'],'needs_reassessment')

    def test_export_readable_reopen_and_corrupt_input_preserve_disk_records(self):
        self.save_scope();self.example();self.request('/api/intelligence/run',self.body());self.example('reassessment')
        p=self.request('/api/intelligence/export.json')[1];j=self.server.workspace.intelligence
        self.assertEqual(p['schema_version'],'traitweaver.intelligence_package.v1')
        brief=self.request('/api/intelligence/export.txt')[1];self.assertIn('PROVISIONAL',brief);self.assertIn('CC-503',brief);self.assertIn('SEPARATE REASSESSMENT',brief)
        self.assertEqual(self.request('/api/intelligence/open',self.body(package_json='{bad'))[0],400)
        self.assertIs(self.server.workspace.intelligence,j)
        self.assertEqual(self.request('/api/intelligence/open',self.body(package_json=study.canonical(p)))[0],200)
        self.assertTrue(self.server.workspace.intelligence.read_only);self.assertEqual(self.example()[0],400)
        self.assertEqual(study.decode((self.store.root/'intelligence-review-v1/revision-000004.json').read_bytes()),j.current())

    def test_completed_muse_cycle_is_preserved_and_new_intelligence_is_session_only(self):
        c=CompletedCycle(fixture(self.folder/'cycle',synthetic=True));before=c.export_review()
        self.server=workspace_server.make_server(c,server_factory=MemoryServer);self.token=self.request('/api/session')[1]['token']
        self.assertEqual(self.save_scope()[0],200);self.assertEqual(self.example()[0],200)
        self.assertEqual(self.request('/api/state')[1]['intelligence']['storage'],'session_only_export_to_keep')
        self.assertEqual(c.export_review(),before);self.assertEqual(self.request('/api/check/run',{'expected_hash':c.current()['hash']})[0],403)

    def test_no_live_send_or_arbitrary_script_route_exists(self):
        self.save_scope();before=self.server.workspace.intelligence.current()
        for route in ('send','execute_script','retrieve','enable_live'):
            self.assertEqual(self.request('/api/intelligence/'+route,self.body())[0],404)
        self.assertEqual(self.server.workspace.intelligence.current(),before)

    def test_intelligence_failure_does_not_disable_original_study_or_reference(self):
        with patch.object(m,'catalog',side_effect=ValueError('Private exception text')):
            self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        code,v=self.request('/api/state');self.assertEqual(code,200);self.assertIsNone(v['intelligence'])
        self.assertIsNotNone(v['public_algae']);self.assertEqual(v['current'],self.store.current());self.assertNotIn('Private exception text',v['intelligence_error'])


if __name__=='__main__':unittest.main()
