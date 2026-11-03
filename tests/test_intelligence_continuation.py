"""Continuation preview and new-admission policy; old v1 bytes remain readable."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_muse as ai, intelligence_store as db, study
from traitweaver import intelligence_continuation as next_decision


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket', side_effect=AssertionError('No network'))
        guard.start(); self.addCleanup(guard.stop)
        self.bundle = m.catalog(); self.j = db.Journal(self.bundle)
        self.ctx = {'study_id': 'PUBLIC_ALGAE', 'study_revision_hash': 'a' * 64}
        self.revise()

    def revise(self, **changes):
        scope = deepcopy(self.j.current()['state']['scope']); scope.update(changes)
        self.j.apply(self.j.current()['hash'], {'type': 'revise', 'payload': {'scope': scope, 'context': self.ctx}})

    def accept(self, phase='selection', focus='trait', legacy=False):
        s = self.j.current()['state']; req = ai.prepare(s, phase, self.bundle, focus)
        reply = ai.synthetic_reply(s, phase, self.bundle, focus)
        p = ai.parse_reply(s, phase, study.canonical(reply).encode(), req['request_sha256'], self.bundle, focus)
        self.apply({'type': 'accept', 'payload': p}, legacy)

    def apply(self, action, legacy=False):
        if not legacy:
            return self.j.apply(self.j.current()['hash'], action)
        # Construct historically valid v1 history through its unchanged replay contract.
        r = {'schema_version': 'traitweaver.intelligence_revision.v1', 'catalog_sha256': study.digest(self.bundle),
             'revision': len(self.j.history) + 1, 'parent_hash': self.j.current()['hash'],
             'saved_utc': datetime.now(timezone.utc).isoformat(), 'action': deepcopy(action),
             'state': m.transition(self.j.current()['state'], action, self.bundle)}
        r['hash'] = study.digest(r); self.j.history.append(r)

    def cycle(self, focus='trait', legacy=False):
        self.accept(focus=focus, legacy=legacy)
        self.apply({'type': 'run', 'payload': {}}, legacy)
        self.accept('reassessment', focus, legacy)

    def preview(self, context=None):
        return next_decision.prepare(self.j.history, self.bundle, context or self.ctx)

    def row(self, check='trait_evidence_audit'):
        return next(x for x in self.preview()['checks'] if x['check'] == check)

    def test_v1_request_bytes_unchanged_and_preview_is_separate(self):
        req = ai.prepare(self.j.current()['state'], 'selection', self.bundle)
        self.assertEqual(req['request_sha256'], '5b2e94012dc70ee0f81cd8ab604f213632f6791676bba8a8801e2c791e4aab3b')
        p = self.preview(); self.assertEqual(p['schema_version'], 'traitweaver.intelligence_continuation.v1')
        self.assertEqual(p['kind'], 'deterministic_local_preview'); self.assertTrue(p['human_review_required'])
        self.assertFalse(p['model_request']); self.assertNotIn('PUBLIC_ALGAE', study.canonical(p))
        self.assertEqual(self.j.current()['revision'], 1)

    def test_empty_and_unfinished_histories_require_their_current_stage(self):
        p = next_decision.prepare([], self.bundle, self.ctx)
        self.assertEqual(p['status'], 'review_scope'); self.assertEqual(p['prior_cycles'], [])
        self.accept(); self.assertEqual(self.preview()['status'], 'finish_current_cycle')
        self.assertEqual(self.preview()['suggestion']['check_ids'], [])
        self.assertIsNone(self.preview()['prior_cycles'][0]['result'])
        self.apply({'type': 'run', 'payload': {}})
        self.assertEqual(self.preview()['status'], 'finish_current_cycle')
        self.assertIsNone(self.preview()['prior_cycles'][0]['assessment'])

    def test_view_cache_binds_all_owning_bytes_and_returns_independent_copies(self):
        self.cycle(); first = self.j.continuation(self.ctx)
        with patch.object(next_decision, 'prepare', side_effect=AssertionError('No repeated full replay')):
            copy = self.j.continuation(self.ctx); copy['prior_cycles'].clear()
            self.assertEqual(self.j.continuation(self.ctx), first)
        other = {**self.ctx, 'study_revision_hash': 'b' * 64}
        self.assertEqual(self.j.continuation(other)['status'], 'review_scope')
        self.j.continuation(self.ctx)
        self.j.history[-1]['state']['cycles'][0]['result']['facts']['causal_effect'] = True
        with self.assertRaises(ValueError): self.j.continuation(self.ctx)

    def test_two_cycles_preserve_prior_result_assessment_sources_and_missing_evidence(self):
        self.cycle(); first = deepcopy(self.j.current()['state']['cycles'][0])
        self.revise(target_endpoint='phosphate_uptake'); p = self.preview()
        self.assertEqual(self.row()['status'], 'eligible_changed_inputs')
        carried = p['prior_cycles'][0]
        self.assertEqual(carried['result'], first['result']); self.assertEqual(carried['assessment']['outcome'], 'unavailable')
        self.assertEqual(carried['scope']['target_endpoint'], 'recovered_product_phosphorus')
        self.assertEqual(carried['applicability'], 'needs_reassessment')
        self.assertTrue(p['unresolved_requirements']); self.assertIn('C_ENDPOINTS', p['claim_records'])
        self.assertEqual(p['claim_records']['C_COMBINATION_GAP']['role'], 'curation_gap')
        self.assertIsNone(p['claim_records']['C_COMBINATION_GAP']['source_id'])
        self.cycle(); p = self.preview(); self.assertEqual(len(p['prior_cycles']), 2)
        self.assertEqual(p['prior_cycles'][1]['result']['outcome'], 'supported')
        self.assertEqual(self.j.current()['state']['cycles'][0]['result'], first['result'])

    def test_identical_unrelated_context_only_and_reverted_inputs_block_repeat(self):
        self.cycle(); before = self.j.current()
        with self.assertRaisesRegex(ValueError, 'already checked'): self.accept()
        self.assertEqual(self.j.current(), before)
        self.ctx['study_revision_hash'] = 'b' * 64
        self.revise(recipient='study_uvm4', combination='regulation_storage')
        self.assertEqual(self.row()['status'], 'already_checked')
        with self.assertRaisesRegex(ValueError, 'already checked'): self.accept()
        self.revise(target_endpoint='phosphate_uptake'); self.cycle()
        self.revise(target_endpoint='recovered_product_phosphorus')
        with self.assertRaisesRegex(ValueError, 'already checked'): self.accept()

    def test_numeric_equivalents_cannot_bypass_but_null_and_zero_differ(self):
        self.cycle(); self.revise(minimum_growth_ratio=0); self.cycle()
        for value in (0.0, -0.0):
            self.revise(minimum_growth_ratio=value)
            with self.assertRaisesRegex(ValueError, 'already checked'): self.accept()
        self.revise(minimum_growth_ratio=1); self.cycle(); self.revise(minimum_growth_ratio=1.0)
        with self.assertRaisesRegex(ValueError, 'already checked'): self.accept()

    def test_irrelevant_endpoint_does_not_renew_combination_or_transfer(self):
        self.cycle('combinations'); self.cycle('transfer'); self.revise(target_endpoint='growth')
        for focus in ('combinations', 'transfer'):
            with self.assertRaisesRegex(ValueError, 'already checked'): self.accept(focus=focus)
        self.revise(combination='regulation_storage', recipient='study_uvm4')
        self.cycle('combinations'); self.cycle('transfer')

    def test_all_checks_exhausted_stops_without_inventing_new_evidence(self):
        for focus in m.FOCI: self.cycle(focus)
        p = self.preview(); self.assertEqual(p['status'], 'stop_no_new_inputs')
        self.assertEqual(p['suggestion']['check_ids'], [])
        self.assertTrue(p['unresolved_requirements'])

    def test_failure_stays_distinct_and_cannot_automatically_retry(self):
        self.accept()
        with patch.object(m, 'run_check', side_effect=RuntimeError('private exception')):
            self.apply({'type': 'run', 'payload': {}})
        self.accept('reassessment'); p = self.preview()
        self.assertEqual(self.row()['status'], 'failed_requires_review')
        self.assertEqual(p['prior_cycles'][0]['result']['status'], 'failed')
        self.assertNotIn('private exception', study.canonical(p))
        with self.assertRaisesRegex(ValueError, 'failed'): self.accept()

    def test_old_repeat_packages_reopen_without_dispatch_or_rewriting(self):
        self.cycle(); self.cycle(legacy=True); package = self.j.export()
        with patch.object(m, 'run_check', side_effect=AssertionError('No dispatch')), \
             patch.object(ai, 'synthetic_reply', side_effect=AssertionError('No model')):
            reopened = db.Journal.from_package(package, self.bundle)
            p = next_decision.prepare(reopened.history, self.bundle, self.ctx)
            self.assertEqual(reopened.export(), package); self.assertEqual(len(p['prior_cycles']), 2)
            self.assertTrue(reopened.read_only)

    def test_legacy_pending_duplicate_is_rejected_before_tool_dispatch(self):
        self.cycle(); self.accept(legacy=True); before = self.j.current()
        with patch.object(m, 'run_check', side_effect=AssertionError('No duplicate dispatch')) as dispatch:
            with self.assertRaisesRegex(ValueError, 'already checked'): self.apply({'type': 'run', 'payload': {}})
            dispatch.assert_not_called()
        self.assertEqual(self.j.current(), before)

    def test_preview_rejects_stale_context_altered_content_and_rehashed_bad_lineage(self):
        self.cycle(); p = self.preview()
        self.assertEqual(next_decision.validate(p, self.j.history, self.bundle, self.ctx), p)
        changed = deepcopy(p); changed['prior_cycles'][0]['result']['facts']['causal_effect'] = True
        changed['preview_sha256'] = study.digest({k: v for k, v in changed.items() if k != 'preview_sha256'})
        with self.assertRaises(ValueError): next_decision.validate(changed, self.j.history, self.bundle, self.ctx)
        other = {**self.ctx, 'study_revision_hash': 'b' * 64}
        with self.assertRaises(ValueError): next_decision.validate(p, self.j.history, self.bundle, other)
        self.assertEqual(self.preview(other)['status'], 'review_scope')
        records = deepcopy(self.j.history); records[-1]['state']['cycles'][0]['assessment']['result_id'] = '0' * 64
        records[-1]['hash'] = study.digest({k: v for k, v in records[-1].items() if k != 'hash'})
        with self.assertRaises(ValueError): next_decision.prepare(records, self.bundle, self.ctx)
        changed_catalog = deepcopy(self.bundle); changed_catalog['claims']['C_ENDPOINTS']['statement'] = 'Altered catalog'
        with self.assertRaises(ValueError): next_decision.prepare(self.j.history, changed_catalog, self.ctx)
        self.revise(target_endpoint='growth')
        with self.assertRaises(ValueError): next_decision.validate(p, self.j.history, self.bundle, self.ctx)


if __name__ == '__main__': unittest.main()
