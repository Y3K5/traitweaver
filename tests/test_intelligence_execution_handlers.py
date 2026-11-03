"""Acceptance boundaries for the explicit, offline v2 execution bridge."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_execution, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from test_completed_cycle import fixture
from test_review_handlers import MemoryServer
import test_intelligence_handlers as existing


class ExecutionHandlerTests(unittest.TestCase):
    setUp = existing.IntelligenceHandlerTests.setUp
    request = existing.IntelligenceHandlerTests.request
    body = existing.IntelligenceHandlerTests.body
    save_scope = existing.IntelligenceHandlerTests.save_scope
    example = existing.IntelligenceHandlerTests.example
    next_body = existing.IntelligenceHandlerTests.next_body
    next_prepare = existing.IntelligenceHandlerTests.next_prepare
    complete_first = existing.IntelligenceHandlerTests.complete_first

    def prepare(self):
        self.complete_first(); self.assertEqual(self.next_prepare()[0], 200)
        self.assertEqual(self.request('/api/intelligence/next/synthetic', self.next_body(check='combination_coverage'))[0], 200)

    def action(self, name, **items):
        view = self.request('/api/state')[1]['intelligence_execution']
        return self.request('/api/intelligence/execution/' + name,
                            self.body(execution_hash=view['execution_hash'], **items))

    def approve(self, ack=True):
        return self.action('approve', next_review_hash=self.server.workspace.intelligence_next.fingerprint(), acknowledged=ack)

    def result(self):
        value = self.request('/api/state')[1]['intelligence_execution']['active']
        return value['attempts'][-1]['result']

    def test_approval_run_and_review_are_distinct_and_preserve_old_contracts(self):
        self.prepare(); j = self.server.workspace.intelligence
        before = j.export(); proposal = deepcopy(self.server.workspace.intelligence_next.current())
        with patch.object(m, 'run_check', wraps=m.run_check) as dispatch:
            for ack in (False, 1, 'true'): self.assertEqual(self.approve(ack)[0], 400)
            self.assertEqual(self.approve()[0], 200); self.assertEqual(dispatch.call_count, 0)
            self.assertEqual(self.action('run')[0], 200); self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(self.action('run')[0], 400); self.assertEqual(dispatch.call_count, 1)
            result = self.result(); self.assertEqual(result['outcome'], 'unavailable')
            self.assertEqual(self.action('reassess', result_id=result['id'], acknowledged=True)[0], 200)
            self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(j.export(), before)
        self.assertEqual(self.server.workspace.intelligence_next.current(), proposal)

    def test_current_hash_origin_and_allowlist_gate_before_dispatch(self):
        self.prepare(); view = self.request('/api/state')[1]['intelligence_execution']
        body = self.body(execution_hash=view['execution_hash'], next_review_hash=self.server.workspace.intelligence_next.fingerprint(), acknowledged=True)
        with patch.object(m, 'run_check', side_effect=AssertionError('No dispatch')):
            for headers in ({'Origin': 'https://outside.invalid'}, {'X-Traitweaver-Token': ''}):
                self.assertEqual(self.request('/api/intelligence/execution/approve', body, headers)[0], 403)
            for key in ('execution_hash', 'next_review_hash', 'intelligence_hash', 'expected_hash'):
                self.assertEqual(self.request('/api/intelligence/execution/approve', {**body, key: 'a' * 64})[0], 409)
            self.assertEqual(self.action('send')[0], 404)
            self.assertEqual(self.action('run')[0], 400)
            self.assertEqual(self.request('/api/intelligence/execution/approve', body)[0], 200)
            self.assertEqual(self.request('/api/intelligence/execution/approve', body)[0], 409)

    def test_scope_and_context_changes_block_approved_execution(self):
        self.prepare(); self.assertEqual(self.approve()[0], 200)
        self.assertEqual(self.save_scope(target_endpoint='growth')[0], 200)
        with patch.object(m, 'run_check', side_effect=AssertionError('No stale dispatch')):
            self.assertIn(self.action('run')[0], (400, 409))
        self.assertEqual(self.action('cancel', acknowledged=True)[0], 200)

    def test_bridge_guard_blocks_new_v1_decision_and_cannot_reset_through_new_review(self):
        self.prepare(); self.assertEqual(self.approve()[0], 200)
        self.assertEqual(self.example(focus='combinations')[0], 400)
        self.assertEqual(self.action('run')[0], 200)
        result = self.result(); self.assertEqual(self.action('reassess', result_id=result['id'], acknowledged=True)[0], 200)
        self.assertEqual(self.example(focus='combinations')[0], 400)
        self.assertEqual(self.next_prepare()[0], 200)
        self.assertEqual(self.request('/api/intelligence/next/synthetic', self.next_body(check='combination_coverage'))[0], 200)
        self.assertEqual(self.approve()[0], 400)

    def test_imported_proposal_cannot_approve_and_execution_reopen_never_dispatches(self):
        self.prepare(); proposal = self.server.workspace.intelligence_next.current()
        self.assertEqual(self.approve()[0], 200); self.assertEqual(self.action('run')[0], 200)
        package = self.request('/api/state')[1]['intelligence_execution']['package']
        with patch.object(m, 'run_check', side_effect=AssertionError('No reopen dispatch')):
            code, value = self.action('open', package_json=study.canonical(package)); self.assertEqual(code, 200)
            self.assertTrue(value['intelligence_execution']['read_only'])
            self.assertEqual(value['intelligence_execution']['package'], package)
            self.assertEqual(self.action('run')[0], 400)
            self.assertEqual(self.action('local')[0], 200)
            self.assertEqual(self.request('/api/intelligence/next/open', self.next_body(package_json=study.canonical(proposal)))[0], 200)
            self.assertEqual(self.approve()[0], 400)
        self.assertEqual(self.example(focus='combinations')[0], 400)

    def test_known_software_failure_needs_review_and_one_separate_retry(self):
        self.prepare(); self.assertEqual(self.approve()[0], 200)
        with patch.object(m, 'run_check', side_effect=RuntimeError('Synthetic software failure')) as dispatch:
            self.assertEqual(self.action('run')[0], 200); failed = self.result()
            self.assertEqual(failed['status'], 'failed')
            args = dict(result_id=failed['id'], reason='reviewed_local_failure', acknowledged=True)
            self.assertEqual(self.action('retry', **args)[0], 400)
            self.assertEqual(self.action('reassess', result_id=failed['id'], acknowledged=True)[0], 200)
            self.assertEqual(self.action('retry', **{**args, 'reason': 'biological_gap'})[0], 400)
            self.assertEqual(self.action('retry', **args)[0], 200); self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(self.action('run')[0], 200); self.assertEqual(dispatch.call_count, 2)
            second = self.result(); self.assertEqual(self.action('reassess', result_id=second['id'], acknowledged=True)[0], 200)
            self.assertEqual(self.action('retry', **{**args, 'result_id': second['id']})[0], 400)
            self.assertEqual(dispatch.call_count, 2)

    def test_readonly_v1_blocks_execution_but_keeps_export_visible(self):
        self.prepare(); self.assertEqual(self.approve()[0], 200)
        package = self.server.workspace.intelligence.export()
        self.assertEqual(self.request('/api/intelligence/open', self.body(package_json=study.canonical(package)))[0], 200)
        with patch.object(m, 'run_check', side_effect=AssertionError('No readonly dispatch')):
            self.assertEqual(self.action('run')[0], 400)
        self.assertIsNotNone(self.request('/api/state')[1]['intelligence_execution']['package'])

    def test_bridge_is_separate_from_completed_original_study(self):
        cycle = CompletedCycle(fixture(self.folder / 'bridge-cycle', synthetic=True)); before = cycle.export_review()
        self.server = workspace_server.make_server(cycle, server_factory=MemoryServer)
        self.token = self.request('/api/session')[1]['token']
        self.prepare(); self.assertEqual(self.approve()[0], 200); self.assertEqual(self.action('run')[0], 200)
        self.assertEqual(cycle.export_review(), before)

    def test_imported_receipt_blocks_an_already_pending_v1_run(self):
        self.prepare(); j = self.server.workspace.intelligence
        other = intelligence_execution.Session(j.bundle)
        context = m.context(self.server.workspace.active.current())
        other.approve(other.fingerprint(), self.server.workspace.intelligence_next.current(), j, context, True)
        other.run(other.fingerprint(), j, context); package = other.export()
        self.assertEqual(self.example(focus='combinations')[0], 200)
        before = j.export()
        self.assertEqual(self.action('open', package_json=study.canonical(package))[0], 200)
        with patch.object(m, 'run_check', side_effect=AssertionError('No repeated v1 dispatch')):
            self.assertEqual(self.request('/api/intelligence/run', self.body())[0], 400)
        self.assertEqual(j.export(), before)

    def test_invalid_saved_execution_history_fails_closed_without_hiding_v1(self):
        self.complete_first(); before = self.server.workspace.intelligence.export()
        directory = self.store.root / 'intelligence-execution-v1'; directory.mkdir()
        (directory / 'event-000001.json').write_text('{}')
        self.server = workspace_server.make_server(self.store, server_factory=MemoryServer)
        self.token = self.request('/api/session')[1]['token']
        code, value = self.request('/api/state'); self.assertEqual(code, 200)
        self.assertIsNone(value['intelligence_execution']); self.assertTrue(value['intelligence_execution_error'])
        with patch.object(m, 'run_check', side_effect=AssertionError('No dispatch with invalid ledger')):
            self.assertEqual(self.example(focus='combinations')[0], 400)
        self.assertEqual(self.server.workspace.intelligence.export(), before)

    def test_historical_result_can_be_reviewed_without_making_it_current(self):
        self.prepare(); self.assertEqual(self.approve()[0], 200); self.assertEqual(self.action('run')[0], 200)
        original = self.result()
        self.assertEqual(self.save_scope(recipient='study_uvm4')[0], 200)
        with patch.object(m, 'run_check', side_effect=AssertionError('Historical review cannot dispatch')):
            code, value = self.action('reassess', result_id=original['id'], acknowledged=True)
            self.assertEqual(code, 200); execution = value['intelligence_execution']
            self.assertEqual(execution['applicability'], 'stale')
            self.assertEqual(execution['active']['attempts'][-1]['result'], original)
            self.assertFalse(execution['availability']['can_run']); self.assertFalse(execution['availability']['can_retry'])
        self.assertEqual(self.next_prepare()[0], 200)
        self.assertEqual(self.request('/api/intelligence/next/synthetic', self.next_body(check='transfer_coverage'))[0], 200)
        self.assertEqual(self.approve()[0], 200)


if __name__ == '__main__': unittest.main()
