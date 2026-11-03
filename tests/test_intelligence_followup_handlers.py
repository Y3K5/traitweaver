"""Acceptance-first routes for reviewed execution history in an offline v3 request."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_execution as execution
from traitweaver import intelligence_muse_v2 as v2, study
import test_intelligence_execution_handlers as existing


class FollowupHandlerTests(unittest.TestCase):
    setUp = existing.ExecutionHandlerTests.setUp
    request = existing.ExecutionHandlerTests.request
    body = existing.ExecutionHandlerTests.body
    save_scope = existing.ExecutionHandlerTests.save_scope
    example = existing.ExecutionHandlerTests.example
    next_body = existing.ExecutionHandlerTests.next_body
    next_prepare = existing.ExecutionHandlerTests.next_prepare
    complete_first = existing.ExecutionHandlerTests.complete_first
    prepare = existing.ExecutionHandlerTests.prepare
    action = existing.ExecutionHandlerTests.action
    approve = existing.ExecutionHandlerTests.approve
    result = existing.ExecutionHandlerTests.result

    def bridge(self, reviewed=True):
        self.prepare(); self.assertEqual(self.approve()[0], 200)
        self.assertEqual(self.action('run')[0], 200)
        if reviewed:
            self.assertEqual(self.action('reassess', result_id=self.result()['id'], acknowledged=True)[0], 200)

    def followup_body(self, **items):
        state = self.request('/api/state')[1]
        return self.body(execution_hash=state['intelligence_execution']['execution_hash'],
                         followup_review_hash=state['intelligence_followup']['review_hash'], **items)

    def followup_prepare(self, acknowledged=True):
        preview = self.request('/api/state')[1]['intelligence_followup']['preview']
        return self.request('/api/intelligence/followup/prepare', self.followup_body(
            reviewed_preview_sha256=preview['preview_sha256'], acknowledged=acknowledged, focus='transfer'))

    def synthetic(self):
        return self.request('/api/intelligence/followup/synthetic', self.followup_body(check='transfer_coverage'))

    def test_actual_reviewed_bridge_result_reaches_request_without_mutating_owners(self):
        self.bridge(); w = self.server.workspace; j = w.intelligence
        before = (j.export(), deepcopy(w.intelligence_next.current()), w.intelligence_execution.export())
        with patch.object(m, 'run_check', side_effect=AssertionError('Request preparation cannot dispatch')):
            code, value = self.followup_prepare(); self.assertEqual(code, 200)
            request = value['intelligence_followup']['request']
            self.assertEqual(request['schema_version'], 'traitweaver.intelligence_request.v3')
            self.assertEqual(request['eligible_checks'], ['transfer_coverage'])
            self.assertEqual(request['status'], 'not_sent')
            self.assertIn(self.result()['id'], request['body']['input'])
            self.assertIn('human_acknowledgment_of_fixed_local_result', request['body']['input'])
            self.assertIn('synthetic_fixture', request['body']['input'])
            self.assertNotIn('study_id', request['body']['input'])
            self.assertEqual(self.synthetic()[0], 200)
        self.assertEqual((j.export(), w.intelligence_next.current(), w.intelligence_execution.export()), before)

    def test_current_preview_boolean_ack_and_all_revision_tokens_are_required(self):
        self.bridge()
        for acknowledged in (False, 1, 'true'): self.assertEqual(self.followup_prepare(acknowledged)[0], 400)
        preview = self.request('/api/state')[1]['intelligence_followup']['preview']
        body = self.followup_body(reviewed_preview_sha256=preview['preview_sha256'], acknowledged=True, focus='transfer')
        for key in ('expected_hash', 'intelligence_hash', 'execution_hash', 'followup_review_hash'):
            self.assertEqual(self.request('/api/intelligence/followup/prepare', {**body, key: 'a' * 64})[0], 409)
        self.assertEqual(self.request('/api/intelligence/followup/prepare', {**body, 'reviewed_preview_sha256': 'a' * 64})[0], 400)
        for headers in ({'Origin': 'https://outside.invalid'}, {'X-Traitweaver-Token': ''}):
            self.assertEqual(self.request('/api/intelligence/followup/prepare', body, headers)[0], 403)
        self.assertEqual(self.request('/api/intelligence/followup/prepare', body)[0], 200)
        self.assertEqual(self.request('/api/intelligence/followup/prepare', body)[0], 409)

    def test_unreviewed_receipt_stops_preparation_until_separate_human_review(self):
        self.bridge(reviewed=False)
        value = self.request('/api/state')[1]['intelligence_followup']
        self.assertFalse(value['can_prepare']); self.assertEqual(self.followup_prepare()[0], 400)
        self.assertEqual(self.action('reassess', result_id=self.result()['id'], acknowledged=True)[0], 200)
        self.assertEqual(self.followup_prepare()[0], 200)

    def test_execution_history_change_invalidates_pending_response_validation(self):
        self.bridge(); self.assertEqual(self.followup_prepare()[0], 200)
        self.assertEqual(self.next_prepare()[0], 200)
        self.assertEqual(self.request('/api/intelligence/next/synthetic', self.next_body(check='transfer_coverage'))[0], 200)
        self.assertEqual(self.approve()[0], 200)
        with patch.object(m, 'run_check', side_effect=AssertionError('No stale reply dispatch')):
            self.assertIn(self.synthetic()[0], (400, 409))
        value = self.request('/api/state')[1]['intelligence_followup']
        self.assertEqual(value['applicability'], 'stale'); self.assertFalse(value['can_review'])

    def test_all_completed_inputs_stop_without_new_request_or_repeat(self):
        self.bridge(); self.assertEqual(self.next_prepare()[0], 200)
        self.assertEqual(self.request('/api/intelligence/next/synthetic', self.next_body(check='transfer_coverage'))[0], 200)
        self.assertEqual(self.approve()[0], 200); self.assertEqual(self.action('run')[0], 200)
        self.assertEqual(self.action('reassess', result_id=self.result()['id'], acknowledged=True)[0], 200)
        value = self.request('/api/state')[1]['intelligence_followup']
        self.assertEqual(value['preview']['status'], 'stop_no_new_inputs')
        self.assertFalse(value['can_prepare']); self.assertIsNone(value['request'])
        with patch.object(m, 'run_check', side_effect=AssertionError('No repeat dispatch')):
            self.assertEqual(self.followup_prepare()[0], 400)

    def test_reopen_is_readonly_and_stale_without_changing_any_owning_history(self):
        self.bridge(); self.assertEqual(self.followup_prepare()[0], 200); self.assertEqual(self.synthetic()[0], 200)
        package = self.request('/api/state')[1]['intelligence_followup']['package']
        self.assertEqual(self.save_scope(recipient='study_uvm4')[0], 200)
        w = self.server.workspace; before = (w.intelligence.export(), w.intelligence_execution.export())
        with patch.object(m, 'run_check', side_effect=AssertionError('No reopen dispatch')):
            code, value = self.request('/api/intelligence/followup/open', self.followup_body(package_json=study.canonical(package)))
            self.assertEqual(code, 200); view = value['intelligence_followup']
            self.assertTrue(view['read_only']); self.assertEqual(view['applicability'], 'stale')
            self.assertEqual(view['package'], package); self.assertFalse(view['can_review'])
            self.assertEqual(self.synthetic()[0], 400)
        self.assertEqual((w.intelligence.export(), w.intelligence_execution.export()), before)

    def test_imported_guard_cannot_disappear_when_returning_to_local_view(self):
        self.bridge(); w = self.server.workspace; j = w.intelligence
        context = m.context(w.active.current()); owner = v2.Session(); preview = j.continuation(context)
        owner.prepare(None, j, context, preview['preview_sha256'], True, 'transfer')
        owner.respond(owner.fingerprint(), j, context, check='transfer_coverage')
        other = execution.Session(j.bundle); other.approve(other.fingerprint(), owner.current(), j, context, True)
        other.run(other.fingerprint(), j, context)
        result = other.view(j, context)['active']['attempts'][-1]['result']
        other.reassess(other.fingerprint(), j, context, result['id'], True)
        self.assertEqual(self.action('open', package_json=study.canonical(other.export()))[0], 200)
        self.assertEqual(self.followup_prepare()[0], 400)
        self.assertEqual(self.action('local')[0], 200)
        value = self.request('/api/state')[1]['intelligence_followup']
        self.assertEqual(value['preview']['status'], 'stop_no_new_inputs')
        self.assertFalse(value['can_prepare']); self.assertEqual(self.followup_prepare()[0], 400)

    def test_no_execution_route_and_malformed_import_preserves_review(self):
        self.bridge(); self.assertEqual(self.followup_prepare()[0], 200)
        before = deepcopy(self.request('/api/state')[1]['intelligence_followup']['package'])
        self.assertEqual(self.request('/api/intelligence/followup/open', self.followup_body(package_json='{bad'))[0], 400)
        with patch.object(m, 'run_check', side_effect=AssertionError('No v3 dispatch')):
            for route in ('run', 'approve', 'send', 'retry'):
                self.assertEqual(self.request('/api/intelligence/followup/' + route, self.followup_body())[0], 404)
        self.assertEqual(self.request('/api/state')[1]['intelligence_followup']['package'], before)

    def test_readonly_owning_v1_history_blocks_fresh_v3_actions(self):
        self.bridge(); self.assertEqual(self.followup_prepare()[0], 200)
        before = deepcopy(self.request('/api/state')[1]['intelligence_followup']['package'])
        package = self.server.workspace.intelligence.export()
        self.assertEqual(self.request('/api/intelligence/open', self.body(package_json=study.canonical(package)))[0], 200)
        view = self.request('/api/state')[1]['intelligence_followup']
        self.assertFalse(view['can_prepare']); self.assertFalse(view['can_review'])
        self.assertEqual(self.followup_prepare()[0], 400); self.assertEqual(self.synthetic()[0], 400)
        self.assertEqual(self.request('/api/state')[1]['intelligence_followup']['package'], before)


if __name__ == '__main__': unittest.main()
