"""Offline v2 request/review boundaries; no provider or scientific execution."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_muse as v1, intelligence_muse_v2 as v2
from traitweaver import intelligence_continuation, intelligence_store, study
from traitweaver.study_store import Conflict


class NextSelectionTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket', side_effect=AssertionError('No sockets'))
        guard.start(); self.addCleanup(guard.stop)
        self.bundle = m.catalog(); self.j = intelligence_store.Journal(self.bundle)
        self.ctx = {'study_id': 'PUBLIC_ALGAE', 'study_revision_hash': 'a' * 64}
        self.session = v2.Session(); self.revise(); self.cycle()

    def revise(self, **changes):
        scope = deepcopy(self.j.current()['state']['scope']); scope.update(changes)
        self.j.apply(self.j.current()['hash'], {'type': 'revise', 'payload': {'scope': scope, 'context': self.ctx}})

    def accept(self, phase='selection', focus='trait'):
        state = self.j.current()['state']; request = v1.prepare(state, phase, self.bundle, focus)
        raw = study.canonical(v1.synthetic_reply(state, phase, self.bundle, focus)).encode()
        value = v1.parse_reply(state, phase, raw, request['request_sha256'], self.bundle, focus)
        self.j.apply(self.j.current()['hash'], {'type': 'accept', 'payload': value})

    def cycle(self, focus='trait'):
        self.accept(focus=focus); self.j.apply(self.j.current()['hash'], {'type': 'run', 'payload': {}})
        self.accept('reassessment', focus)

    def preview_hash(self):
        return intelligence_continuation.prepare(self.j.history, self.bundle, self.ctx)['preview_sha256']

    def prepare(self):
        self.session.prepare(self.session.fingerprint(), self.j, self.ctx, self.preview_hash(), True, 'combinations')
        return self.session.current()['request']

    def raw(self, request, check='combination_coverage', mutate=None):
        reply = v2.synthetic_reply(request, check)
        if mutate: mutate(reply)
        return study.canonical(reply).encode()

    def test_request_carries_exact_prior_records_and_references_without_owner_identifiers(self):
        request = self.prepare(); public = study.decode(request['body']['input'])
        prior = self.j.current()['state']['cycles'][0]
        self.assertEqual(request['schema_version'], v2.REQUEST); self.assertEqual(request['status'], 'not_sent')
        self.assertEqual(public['continuation_context']['prior_cycles'][0]['result'], prior['result'])
        self.assertEqual(public['continuation_context']['prior_cycles'][0]['assessment']['proposal'], prior['assessment']['accepted_reply']['proposal'])
        self.assertTrue(public['continuation_context']['unresolved_requirements'])
        self.assertEqual(public['claims']['C_COMBINATION_GAP']['role'], 'curation_gap')
        self.assertIsNone(public['claims']['C_COMBINATION_GAP']['source_id'])
        for excluded in ('PUBLIC_ALGAE', 'study_id', 'saved_utc', 'context_notes'):
            self.assertNotIn(excluded, request['body']['input'])
        self.assertEqual(request['eligible_checks'], ['combination_coverage', 'transfer_coverage'])
        self.assertEqual(request['body']['text']['format']['schema']['properties']['check']['enum'], request['eligible_checks'])

    def test_exact_human_acknowledgment_required_and_stale_preview_rejected(self):
        for ack in (False, None, 1, 'true'):
            with self.assertRaises(ValueError):
                self.session.prepare(None, self.j, self.ctx, self.preview_hash(), ack, 'trait')
        old = self.preview_hash(); self.revise(recipient='study_uvm4')
        with self.assertRaises(ValueError): self.session.prepare(None, self.j, self.ctx, old, True, 'trait')
        self.assertIsNone(self.session.current())

    def test_initial_unfinished_stale_and_exhausted_states_cannot_prepare(self):
        initial = self.j.history[:1]
        with self.assertRaisesRegex(ValueError, 'prior saved result'):
            p = intelligence_continuation.prepare(initial, self.bundle, self.ctx)
            v2.prepare(intelligence_store.package(initial, self.bundle), self.bundle, self.ctx, p['preview_sha256'], True)
        self.accept(focus='combinations')
        with self.assertRaises(ValueError): self.prepare()
        self.j.apply(self.j.current()['hash'], {'type': 'run', 'payload': {}})
        with self.assertRaises(ValueError): self.prepare()
        self.accept('reassessment', 'combinations'); self.cycle('transfer')
        with self.assertRaises(ValueError): self.prepare()
        changed = {**self.ctx, 'study_revision_hash': 'b' * 64}
        p = intelligence_continuation.prepare(self.j.history, self.bundle, changed)
        with self.assertRaises(ValueError): v2.prepare(self.j.export(), self.bundle, changed, p['preview_sha256'], True)

    def test_two_source_cycles_and_single_option_remain_explicit(self):
        self.cycle('combinations'); request = self.prepare()
        self.assertEqual(request['eligible_checks'], ['transfer_coverage'])
        public = study.decode(request['body']['input'])
        self.assertEqual(len(public['continuation_context']['prior_cycles']), 2)
        self.session.respond(self.session.fingerprint(), self.j, self.ctx, check='transfer_coverage')
        review = self.session.current()['proposal_review']
        self.assertEqual(review['status'], 'valid_proposal_only')
        self.assertEqual(len(self.j.current()['state']['cycles']), 2)

    def test_synthetic_review_has_exact_citations_and_no_v1_mutation_or_dispatch(self):
        original = study.canonical(self.j.export())
        with patch.object(m, 'run_check', side_effect=AssertionError('No dispatch')), patch.object(v1, 'synthetic_reply', side_effect=AssertionError('No v1 fixture bridge')):
            request = self.prepare(); self.session.respond(self.session.fingerprint(), self.j, self.ctx, check='combination_coverage')
            package = deepcopy(self.session.current()); restored = v2.validate_package(package, self.bundle)
        self.assertEqual(study.canonical(self.j.export()), original); self.assertEqual(package, restored)
        review = package['proposal_review']; self.assertEqual(review['receipt']['provenance'], 'synthetic_fixture')
        self.assertEqual(review['proposal']['reviewed_result_ids'], [self.j.current()['state']['cycles'][0]['result']['id']])
        self.assertEqual(review['proposal']['unresolved_requirement_ids'], ['REQ_0001'])
        self.assertNotIn('output_text', study.canonical(package)); self.assertEqual(review['receipt']['transport_calls'], 0)

    def test_actual_choice_claims_and_prior_references_are_validated(self):
        request = self.prepare()
        def altered(change):
            def mutate(reply):
                p = study.decode(reply['output'][0]['content'][0]['text']); change(p)
                reply['output'][0]['content'][0]['text'] = study.canonical(p)
            return self.raw(request, mutate=mutate)
        mutations = [lambda p: p.update(check='trait_evidence_audit', claim_codes=v1.CLAIMS['trait_evidence_audit'], citations=m.required_citations('trait_evidence_audit', self.bundle)),
                     lambda p: p.update(claim_codes=['transfer_success_proven']),
                     lambda p: p.update(check_input_sha256='0' * 64), lambda p: p.update(preview_sha256='0' * 64),
                     lambda p: p.update(reviewed_result_ids=['UNKNOWN']),
                     lambda p: p.update(unresolved_requirement_ids=['UNKNOWN']),
                     lambda p: p['reviewed_result_ids'].append(p['reviewed_result_ids'][0]),
                     lambda p: p['arguments'].update(recipient='study_uvm4')]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=altered(mutate))
        self.assertIsNone(self.session.current()['proposal_review'])

    def test_requirement_must_belong_to_a_referenced_result(self):
        self.cycle('combinations'); request = self.prepare()
        def mutate(reply):
            p = study.decode(reply['output'][0]['content'][0]['text'])
            p['reviewed_result_ids'] = [self.j.current()['state']['cycles'][1]['result']['id']]
            reply['output'][0]['content'][0]['text'] = study.canonical(p)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=self.raw(request, 'transfer_coverage', mutate))

    def test_invalid_provider_shapes_and_markers_cannot_replace_a_draft(self):
        request = self.prepare(); before = deepcopy(self.session.current())
        mutations = [lambda r: r.update(model='other'), lambda r: r.update(status='incomplete'),
                     lambda r: r.update(output=[{'type': 'function_call', 'name': 'shell'}]),
                     lambda r: r.update(output=[{'type': 'message', 'content': [{'type': 'refusal'}]}]),
                     lambda r: r['output'].append(deepcopy(r['output'][0])),
                     lambda r: r.update(traitweaver_synthetic='true'), lambda r: r.update(traitweaver_synthetic=1),
                     lambda r: r.update(usage={'input_tokens': 0, 'output_tokens': 1025, 'total_tokens': 1025}),
                     lambda r: r.update(extra='sk-' + 'x' * 24)]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=self.raw(request, mutate=mutate))
        self.assertEqual(self.session.current(), before)

    def test_imported_response_remains_unverified_and_zero_usage_is_not_unknown(self):
        request = self.prepare()
        def mutate(r):
            r.pop('traitweaver_synthetic'); r['usage'] = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
        self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=self.raw(request, mutate=mutate))
        receipt = self.session.current()['proposal_review']['receipt']
        self.assertEqual(receipt['provenance'], 'owner_imported_authenticity_unverified')
        self.assertEqual(receipt['reported_usage']['total_tokens'], 0); self.assertIsNone(receipt['cost_usd'])

    def test_changed_current_lineage_and_duplicate_response_do_not_overwrite(self):
        request = self.prepare(); old = self.session.fingerprint()
        self.session.respond(old, self.j, self.ctx, raw=self.raw(request)); saved = deepcopy(self.session.current())
        with self.assertRaises(Conflict): self.session.respond(old, self.j, self.ctx, raw=self.raw(request))
        with self.assertRaises(ValueError): self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=self.raw(request))
        self.revise(target_endpoint='growth'); self.prepare(); request2 = self.session.current()['request']
        self.ctx['study_revision_hash'] = 'b' * 64
        with self.assertRaises(ValueError): self.session.respond(self.session.fingerprint(), self.j, self.ctx, raw=self.raw(request2))
        self.assertEqual(self.session.reviews[0], saved)

    def test_historical_v2_review_reopens_readonly_as_stale_without_dispatch(self):
        self.prepare(); self.session.respond(self.session.fingerprint(), self.j, self.ctx, check='combination_coverage')
        archived = deepcopy(self.session.current()); self.revise(target_endpoint='growth')
        with patch.object(m, 'run_check', side_effect=AssertionError('No reopen dispatch')):
            self.session.open(self.session.fingerprint(), archived, self.bundle)
            view = self.session.view(self.j, self.ctx)
        self.assertTrue(view['read_only']); self.assertEqual(view['applicability'], 'stale')
        self.assertEqual(view['package'], archived)
        with self.assertRaises(ValueError): self.session.respond(view['review_hash'], self.j, self.ctx, check='combination_coverage')

    def test_readonly_owning_v1_package_cannot_prepare_or_validate_new_proposals(self):
        self.prepare(); before = deepcopy(self.session.current())
        self.j = intelligence_store.Journal.from_package(self.j.export(), self.bundle)
        with self.assertRaisesRegex(ValueError, 'read-only'): self.prepare()
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.session.respond(self.session.fingerprint(), self.j, self.ctx, check='combination_coverage')
        self.assertEqual(self.session.current(), before)

    def test_rehashed_request_history_and_eligibility_tampering_rejected(self):
        self.prepare(); package = deepcopy(self.session.current())
        for part in ('request', 'source', 'eligibility'):
            value = deepcopy(package)
            if part == 'request':
                value['request']['body']['instructions'] += ' Changed'
                value['request']['request_sha256'] = study.digest(value['request']['body'])
            elif part == 'source':
                last = value['source_package']['revisions'][-1]
                last['state']['cycles'][0]['result']['facts']['causal_effect'] = True
                last['hash'] = study.digest({k: v for k, v in last.items() if k != 'hash'})
            else: value['request']['eligible_checks'].append('trait_evidence_audit')
            with self.subTest(part=part), self.assertRaises(ValueError): v2.validate_package(value, self.bundle)

    def test_bounded_request_and_archive_failure_preserve_existing_work(self):
        with patch.object(v2, 'MAX_REQUEST_BYTES', 100), self.assertRaisesRegex(ValueError, 'no history was truncated'):
            self.prepare()
        self.assertIsNone(self.session.current()); self.prepare(); saved = deepcopy(self.session.current())
        with patch.object(v2, 'MAX_REVIEWS', 1), self.assertRaises(ValueError): self.prepare()
        self.assertEqual(self.session.current(), saved)

    def test_failed_inputs_stay_excluded_from_the_new_schema(self):
        self.accept(focus='combinations')
        with patch.object(m, 'run_check', side_effect=RuntimeError('private failure')):
            self.j.apply(self.j.current()['hash'], {'type': 'run', 'payload': {}})
        self.accept('reassessment', 'combinations'); request = self.prepare()
        self.assertEqual(request['eligible_checks'], ['transfer_coverage'])
        self.assertEqual(study.decode(request['body']['input'])['continuation_context']['prior_cycles'][1]['result']['status'], 'failed')
        self.assertNotIn('private failure', study.canonical(request))

    def test_a_reassessed_failed_first_result_can_inform_other_eligible_checks(self):
        self.j = intelligence_store.Journal(self.bundle); self.revise(); self.accept()
        with patch.object(m, 'run_check', side_effect=RuntimeError('private failure')):
            self.j.apply(self.j.current()['hash'], {'type': 'run', 'payload': {}})
        self.accept('reassessment'); request = self.prepare()
        self.assertEqual(request['eligible_checks'], ['combination_coverage', 'transfer_coverage'])
        prior = study.decode(request['body']['input'])['continuation_context']['prior_cycles'][0]
        self.assertEqual(prior['result']['status'], 'failed'); self.assertEqual(prior['assessment']['outcome'], 'failed')

    def test_v1_request_fingerprint_and_historical_package_stay_unchanged(self):
        initial = self.j.history[0]['state']
        self.assertEqual(v1.prepare(initial, 'selection', self.bundle)['request_sha256'], '5b2e94012dc70ee0f81cd8ab604f213632f6791676bba8a8801e2c791e4aab3b')
        before = self.j.export(); self.prepare()
        self.assertEqual(intelligence_store.Journal.from_package(before, self.bundle).export(), before)
        self.assertEqual(self.j.export(), before)


if __name__ == '__main__': unittest.main()
