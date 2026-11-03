"""Acceptance-first checks for separate approval of an offline v3 proposal."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import intelligence as model, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from test_completed_cycle import fixture
from test_review_handlers import MemoryServer
import test_intelligence_followup_handlers as existing


class ExecutionFollowupHandlerTests(unittest.TestCase):
    for name in ('setUp', 'request', 'body', 'save_scope', 'example', 'next_body',
                 'next_prepare', 'complete_first', 'prepare', 'action', 'approve',
                 'result', 'bridge', 'followup_body', 'followup_prepare', 'synthetic'):
        locals()[name] = getattr(existing.FollowupHandlerTests, name)

    def prepared(self):
        self.bridge()
        self.assertEqual(self.followup_prepare()[0], 200)
        self.assertEqual(self.synthetic()[0], 200)

    def approve_followup(self, acknowledged=True):
        return self.request('/api/intelligence/execution/approve-followup',
                            self.followup_body(acknowledged=acknowledged))

    def test_explicit_approval_run_review_and_exhaustion_are_separate(self):
        self.prepared(); w = self.server.workspace
        original = (w.intelligence.export(), deepcopy(w.intelligence_next.current()),
                    deepcopy(w.intelligence_followup.current()))
        with patch.object(model, 'run_check', wraps=model.run_check) as dispatch:
            self.assertTrue(self.request('/api/state')[1]['intelligence_execution']['availability']['can_approve_followup'])
            for ack in (False, 1, 'true'): self.assertEqual(self.approve_followup(ack)[0], 400)
            self.assertEqual(self.approve_followup()[0], 200); dispatch.assert_not_called()
            self.assertEqual(self.action('run')[0], 200); self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(self.action('run')[0], 400)
            self.assertEqual(self.action('reassess', result_id=self.result()['id'], acknowledged=True)[0], 200)
            self.assertEqual(dispatch.call_count, 1)
        state = self.request('/api/state')[1]
        self.assertEqual(state['intelligence_followup']['preview']['status'], 'stop_no_new_inputs')
        self.assertFalse(state['intelligence_followup']['can_prepare'])
        active = state['intelligence_execution']['active']
        self.assertEqual(active['approval']['proposal_review']['receipt']['provenance'], 'synthetic_fixture')
        self.assertEqual(active['reassessment']['provenance'], 'human_acknowledgment_of_fixed_local_result')
        self.assertEqual(original, (w.intelligence.export(), w.intelligence_next.current(), w.intelligence_followup.current()))

    def test_current_hashes_origin_and_boolean_ack_bind_approval(self):
        self.prepared(); body = self.followup_body(acknowledged=True)
        with patch.object(model, 'run_check') as dispatch:
            for key in ('expected_hash', 'intelligence_hash', 'execution_hash', 'followup_review_hash'):
                self.assertEqual(self.request('/api/intelligence/execution/approve-followup', {**body, key: 'f'*64})[0], 409)
            for headers in ({'Origin': 'https://outside.invalid'}, {'X-Traitweaver-Token': ''}):
                self.assertEqual(self.request('/api/intelligence/execution/approve-followup', body, headers)[0], 403)
            self.assertEqual(self.request('/api/intelligence/execution/approve-followup', body)[0], 200)
            self.assertEqual(self.request('/api/intelligence/execution/approve-followup', body)[0], 409)
            dispatch.assert_not_called()

    def test_changed_scope_blocks_run_but_allows_cancelling_unstarted_approval(self):
        self.prepared(); self.assertEqual(self.approve_followup()[0], 200)
        self.assertEqual(self.save_scope(recipient='study_uvm4')[0], 200)
        with patch.object(model, 'run_check') as dispatch:
            self.assertIn(self.action('run')[0], (400, 409)); dispatch.assert_not_called()
        self.assertEqual(self.action('cancel', acknowledged=True)[0], 200)

    def test_imported_review_and_execution_reopen_never_authorize_dispatch(self):
        self.prepared(); proposal = self.server.workspace.intelligence_followup.current()
        with patch.object(model, 'run_check') as dispatch:
            self.assertEqual(self.request('/api/intelligence/followup/open', self.followup_body(package_json=study.canonical(proposal)))[0], 200)
            self.assertEqual(self.approve_followup()[0], 400); dispatch.assert_not_called()
        self.assertEqual(self.followup_prepare()[0], 200); self.assertEqual(self.synthetic()[0], 200)
        self.assertEqual(self.approve_followup()[0], 200); self.assertEqual(self.action('run')[0], 200)
        package = self.request('/api/state')[1]['intelligence_execution']['package']
        with patch.object(model, 'run_check') as dispatch:
            self.assertEqual(self.action('open', package_json=study.canonical(package))[0], 200)
            self.assertEqual(self.action('run')[0], 400)
            self.assertEqual(self.action('local')[0], 200)
            self.assertEqual(self.example(focus='transfer')[0], 400); dispatch.assert_not_called()

    def test_known_failure_requires_review_and_only_one_retry(self):
        self.prepared(); self.assertEqual(self.approve_followup()[0], 200)
        with patch.object(model, 'run_check', side_effect=OSError('synthetic software failure')) as dispatch:
            self.assertEqual(self.action('run')[0], 200)
            for attempt in range(2):
                result = self.result(); args = dict(result_id=result['id'], reason='reviewed_local_failure', acknowledged=True)
                if attempt == 0: self.assertEqual(self.action('retry', **args)[0], 400)
                self.assertEqual(self.action('reassess', result_id=result['id'], acknowledged=True)[0], 200)
                self.assertEqual(self.action('retry', **args)[0], 200 if attempt == 0 else 400)
                if attempt == 0: self.assertEqual(self.action('run')[0], 200)
            self.assertEqual(dispatch.call_count, 2)

    def test_readonly_intelligence_and_tampered_review_fail_closed(self):
        self.prepared(); w = self.server.workspace
        package = w.intelligence_followup.reviews[w.intelligence_followup.active]
        original = deepcopy(package)
        package['proposal_review']['proposal']['check_input_sha256'] = 'f'*64
        with patch.object(model, 'run_check') as dispatch:
            self.assertEqual(self.approve_followup()[0], 400); dispatch.assert_not_called()
        w.intelligence_followup.reviews[w.intelligence_followup.active] = original
        self.assertEqual(self.request('/api/intelligence/open', self.body(package_json=study.canonical(w.intelligence.export())))[0], 200)
        self.assertEqual(self.approve_followup()[0], 400)

    def test_offline_completed_study_supports_bridge_without_changing_original(self):
        cycle = CompletedCycle(fixture(self.folder / 'v3-bridge-cycle', synthetic=True)); before = cycle.export_review()
        self.server = workspace_server.make_server(cycle, server_factory=MemoryServer)
        self.token = self.request('/api/session')[1]['token']
        self.prepared(); self.assertEqual(self.approve_followup()[0], 200)
        self.assertEqual(self.action('run')[0], 200)
        self.assertEqual(cycle.export_review(), before)


if __name__ == '__main__': unittest.main()
