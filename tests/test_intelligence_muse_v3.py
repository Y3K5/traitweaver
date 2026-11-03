"""Execution-informed proposals remain separate, bounded and non-executable."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import intelligence as model, intelligence_execution as execution
from traitweaver import intelligence_muse as v1, intelligence_muse_v3 as v3, study
from traitweaver.study_store import Conflict
import test_intelligence_execution as fixtures


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExecutionTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.fixture.approve(); self.fixture.run_check(); self.fixture.review()
        self.j=self.fixture.j; self.e=self.fixture.s; self.bundle=self.fixture.bundle; self.ctx=self.fixture.ctx
        self.s=v3.Session()

    def view(self): return self.s.view(self.j,self.e,self.ctx)

    def prepare(self):
        p=self.view()['preview']
        self.s.prepare(self.s.fingerprint(),self.j,self.e,self.ctx,p['preview_sha256'],True,'transfer')
        return self.s.current()['request']

    def raw(self, request, change=None):
        reply=v3.synthetic_reply(request,request['eligible_checks'][0])
        if change: change(reply)
        return study.canonical(reply).encode()

    def alternate(self, check='combination_coverage', complete=True, review=True):
        owner=self.fixture.fixture.session
        if check=='combination_coverage': proposal=self.fixture.proposal
        else:
            self.fixture.fixture.prepare()
            owner.respond(owner.fingerprint(),self.j,self.ctx,check=check); proposal=deepcopy(owner.current())
        other=execution.Session(self.bundle)
        other.approve(other.fingerprint(),proposal,self.j,self.ctx,True)
        if complete:
            other.run(other.fingerprint(),self.j,self.ctx)
            if review:
                rid=other.view(self.j,self.ctx)['active']['attempts'][-1]['result']['id']
                other.reassess(other.fingerprint(),self.j,self.ctx,rid,True)
        return other

    def import_guard(self, package):
        self.e.open(self.e.fingerprint(),package); self.e.local(self.e.fingerprint())

    def test_initial_missing_owners_and_unsaved_views_are_blocked_without_crashing(self):
        for journal,ledger in ((None,None),(self.j,None)):
            view=self.s.view(journal,ledger,self.ctx)
            self.assertFalse(view['can_prepare']); self.assertFalse(view['can_review'])
            self.assertIsNone(view['preview']['preview_sha256'])
        from traitweaver.intelligence_store import Journal
        view=self.s.view(Journal(self.bundle),execution.Session(self.bundle),self.ctx)
        self.assertEqual(view['preview']['status'],'review_scope'); self.assertFalse(view['can_prepare'])

    def test_payload_contains_owned_receipt_human_review_and_qualified_original_scope(self):
        request=self.prepare(); public=study.decode(request['body']['input']); p=public['followup_context']
        self.assertEqual(request['schema_version'],v3.REQUEST)
        self.assertEqual(request['eligible_checks'],['transfer_coverage'])
        record=p['bridge_records'][0]; saved=self.fixture.result()
        self.assertEqual(record['result'],saved); self.assertEqual(record['raw_result_id'],saved['id'])
        self.assertTrue(record['owned_reviewed']); self.assertEqual(record['origin'],'owned_execution')
        self.assertEqual(record['human_review']['provenance'],'human_acknowledgment_of_fixed_local_result')
        self.assertEqual(record['scope'],self.fixture.proposal['proposal_review']['proposal']['arguments'])
        for excluded in ('PUBLIC_ALGAE','study_id','saved_utc','context_notes'):
            self.assertNotIn(excluded,request['body']['input'])
        self.assertTrue(p['unresolved_requirements']); self.assertEqual(request['status'],'not_sent')

    def test_exact_ack_and_current_combined_preview_required(self):
        preview=self.view()['preview']
        for ack in (False,1,None,'true'):
            with self.assertRaises(ValueError): self.s.prepare(None,self.j,self.e,self.ctx,preview['preview_sha256'],ack,'transfer')
        self.fixture.fixture.revise(recipient='study_uvm4')
        with self.assertRaises(ValueError): self.s.prepare(None,self.j,self.e,self.ctx,preview['preview_sha256'],True,'transfer')
        self.assertIsNone(self.s.current())

    def test_synthetic_acceptance_export_and_reopen_never_dispatch_or_mutate_old_contracts(self):
        original_source=self.j.export(); original_execution=self.e.export(); original_v2=deepcopy(self.fixture.proposal)
        with patch.object(model,'run_check',side_effect=AssertionError('No v3 dispatch')) as dispatch:
            request=self.prepare()
            self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
            package=deepcopy(self.s.current()); self.assertEqual(v3.validate_package(package,self.bundle),package)
            restored=v3.Session(); restored.open(None,package,self.bundle)
            dispatch.assert_not_called()
        self.assertTrue(restored.view(self.j,self.e,self.ctx)['read_only'])
        self.assertEqual(self.j.export(),original_source); self.assertEqual(self.e.export(),original_execution)
        self.assertEqual(self.fixture.proposal,original_v2)
        review=package['proposal_review']; self.assertEqual(review['receipt']['provenance'],'synthetic_fixture')
        self.assertEqual(review['receipt']['transport_calls'],0)
        self.assertIn(review['proposal']['reviewed_receipt_refs'][0],request['body']['input'])

    def test_colliding_raw_ids_have_distinct_receipt_references_and_requirement_bindings(self):
        other=self.alternate(); self.import_guard(other.export()); request=self.prepare()
        p=study.decode(request['body']['input'])['followup_context']; records=p['bridge_records']
        self.assertEqual(len(records),2); self.assertEqual(records[0]['raw_result_id'],records[1]['raw_result_id'])
        self.assertEqual(len({r['receipt_ref'] for r in records}),2)
        imported=next(r for r in records if not r['owned_reviewed'])
        self.assertEqual(imported['origin'],'imported_execution_authenticity_unverified')
        requirement=next(r for r in p['unresolved_requirements'] if r['receipt_ref']==imported['receipt_ref'])
        def alter(reply):
            proposal=study.decode(reply['output'][0]['content'][0]['text'])
            proposal['unresolved_requirement_ids']=[requirement['id']]
            reply['output'][0]['content'][0]['text']=study.canonical(proposal)
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request,alter))
        def only_imported(reply):
            alter(reply); proposal=study.decode(reply['output'][0]['content'][0]['text'])
            proposal['reviewed_receipt_refs']=[imported['receipt_ref']]
            reply['output'][0]['content'][0]['text']=study.canonical(proposal)
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request,only_imported))

    def test_imported_pending_unreviewed_and_interrupted_histories_block_globally(self):
        for mode in ('approved','completed','started','retry_approved'):
            with self.subTest(mode=mode):
                other=self.alternate(complete=False)
                if mode=='started':
                    with patch.object(model,'run_check',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
                        other.run(other.fingerprint(),self.j,self.ctx)
                elif mode in ('completed','retry_approved'):
                    if mode=='completed': other.run(other.fingerprint(),self.j,self.ctx)
                    else:
                        with patch.object(model,'run_check',side_effect=RuntimeError('private failure')): other.run(other.fingerprint(),self.j,self.ctx)
                        rid=other.view(self.j,self.ctx)['active']['attempts'][-1]['result']['id']
                        other.reassess(other.fingerprint(),self.j,self.ctx,rid,True)
                        other.retry(other.fingerprint(),self.j,self.ctx,rid,'reviewed_local_failure',True)
                owned=execution.Session(self.bundle); owned.events=deepcopy(self.e.events)
                owned.open(owned.fingerprint(),other.export()); owned.local(owned.fingerprint())
                view=self.s.view(self.j,owned,self.ctx)
                self.assertEqual(view['preview']['status'],'review_execution'); self.assertFalse(view['can_prepare'])

    def test_prefix_import_deduplicates_and_does_not_revive_unreviewed_state(self):
        old=self.e.export(); old['events']=old['events'][:-1]
        self.import_guard(old); preview=self.view()['preview']
        self.assertEqual(preview['status'],'review_next_check'); self.assertEqual(len(preview['bridge_records']),1)
        self.assertEqual(len(preview['owned_reviewed_receipt_refs']),1)

    def test_imported_only_review_cannot_substitute_for_owned_human_review(self):
        other=execution.Session(self.bundle); other.open(other.fingerprint(),self.e.export()); other.local(other.fingerprint())
        view=self.s.view(self.j,other,self.ctx)
        self.assertEqual(view['preview']['status'],'needs_owned_review'); self.assertFalse(view['can_prepare'])

    def test_retained_imported_completion_exhausts_inputs_even_after_return_to_local(self):
        other=self.alternate('transfer_coverage'); self.import_guard(other.export())
        view=self.view(); self.assertEqual(view['preview']['status'],'stop_no_new_inputs')
        self.assertFalse(view['can_prepare']); self.assertTrue(all(not r['eligible'] for r in view['preview']['checks']))
        with self.assertRaises(ValueError): self.prepare()

    def test_reviewed_failure_is_preserved_and_its_input_excluded(self):
        other=self.alternate(complete=False)
        with patch.object(model,'run_check',side_effect=OSError('private local exception')): other.run(other.fingerprint(),self.j,self.ctx)
        rid=other.view(self.j,self.ctx)['active']['attempts'][-1]['result']['id']
        other.reassess(other.fingerprint(),self.j,self.ctx,rid,True)
        self.import_guard(other.export()); request=self.prepare()
        records=study.decode(request['body']['input'])['followup_context']['bridge_records']
        self.assertTrue(any(r['result']['status']=='failed' for r in records))
        self.assertEqual(request['eligible_checks'],['transfer_coverage']); self.assertNotIn('private local exception',study.canonical(request))

    def test_stale_context_and_changed_guard_history_reject_pending_reply(self):
        request=self.prepare(); before=deepcopy(self.s.current())
        changed={**self.ctx,'study_revision_hash':'b'*64}
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,changed,raw=self.raw(request))
        other=self.alternate('transfer_coverage'); self.import_guard(other.export())
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request))
        self.assertEqual(self.s.current(),before); self.assertEqual(self.view()['applicability'],'stale')

    def test_historical_package_reopens_stale_and_readonly_without_dispatch(self):
        self.prepare(); self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
        package=deepcopy(self.s.current()); self.fixture.fixture.revise(recipient='study_uvm4')
        with patch.object(model,'run_check') as dispatch:
            self.s.open(self.s.fingerprint(),package,self.bundle); view=self.view(); dispatch.assert_not_called()
        self.assertTrue(view['read_only']); self.assertEqual(view['applicability'],'stale')
        self.assertEqual(view['package'],package); self.assertFalse(view['can_review'])
        self.assertTrue(view['can_prepare'])

    def test_unverified_provenance_zero_usage_and_duplicate_response(self):
        request=self.prepare(); before=self.s.fingerprint()
        def imported(reply):
            reply.pop('traitweaver_synthetic'); reply['usage']={'input_tokens':0,'output_tokens':0,'total_tokens':0}
        self.s.respond(before,self.j,self.e,self.ctx,raw=self.raw(request,imported))
        receipt=self.s.current()['proposal_review']['receipt']
        self.assertEqual(receipt['provenance'],'owner_imported_authenticity_unverified')
        self.assertEqual(receipt['reported_usage']['total_tokens'],0); self.assertIsNone(receipt['cost_usd'])
        with self.assertRaises(Conflict): self.s.respond(before,self.j,self.e,self.ctx,check='transfer_coverage')
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')

    def test_provider_shapes_and_actual_proposal_fields_are_closed(self):
        request=self.prepare(); before=deepcopy(self.s.current())
        def proposal_change(key,value):
            def mutate(reply):
                p=study.decode(reply['output'][0]['content'][0]['text']); p[key]=value
                reply['output'][0]['content'][0]['text']=study.canonical(p)
            return mutate
        mutations=[lambda r:r.update(traitweaver_synthetic=1),lambda r:r.update(model='other'),lambda r:r.update(status='incomplete'),
                   lambda r:r.update(output=[{'type':'function_call','name':'shell'}]),lambda r:r.update(extra='sk-'+'x'*24),
                   proposal_change('reviewed_receipt_refs',['unknown']),proposal_change('check_input_sha256','0'*64),
                   proposal_change('preview_sha256','0'*64),proposal_change('claim_codes',['transfer_success_proven']),
                   proposal_change('unresolved_requirement_ids',[])]
        for mutate in mutations:
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):
                self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request,mutate))
        self.assertEqual(self.s.current(),before)

    def test_tampered_source_execution_and_rehashed_request_are_rejected(self):
        self.prepare(); package=deepcopy(self.s.current())
        for part in ('wire','result','source','extra'):
            changed=deepcopy(package)
            if part=='wire':
                changed['request']['body']['instructions']+=' altered'; changed['request']['request_sha256']=study.digest(changed['request']['body'])
            elif part=='result':
                events=changed['execution_package']['events']
                next(e for e in events if e['kind']=='result')['payload']['result']['facts']['combination_effect']=1
                for index,event in enumerate(events):
                    event['parent_hash']=events[index-1]['hash'] if index else None
                    event['hash']=study.digest({k:v for k,v in event.items() if k!='hash'})
            elif part=='source': changed['source_package']['revisions'][-1]['state']['scope']['recipient']='study_uvm4'
            else: changed['extra']=True
            with self.subTest(part=part),patch.object(model,'run_check') as dispatch,self.assertRaises(ValueError):
                self.s.open(self.s.fingerprint(),changed,self.bundle)
            dispatch.assert_not_called()
        self.assertEqual(self.s.current(),package)

    def test_bounds_and_old_request_contracts_preserve_work(self):
        self.assertEqual(v1.prepare(self.j.history[0]['state'],'selection',self.bundle)['request_sha256'],'5b2e94012dc70ee0f81cd8ab604f213632f6791676bba8a8801e2c791e4aab3b')
        old=deepcopy(self.fixture.proposal)
        with patch.object(v3,'MAX_REQUEST_BYTES',100),self.assertRaisesRegex(ValueError,'truncated'): self.prepare()
        self.assertIsNone(self.s.current()); self.prepare(); before=deepcopy(self.s.current())
        with patch.object(v3,'MAX_REVIEWS',1),self.assertRaises(ValueError): self.prepare()
        with patch.object(v3,'MAX_BYTES',100),self.assertRaises(ValueError): self.s.open(self.s.fingerprint(),before,self.bundle)
        self.assertEqual(self.s.current(),before); self.assertEqual(self.fixture.proposal,old)

    def test_readonly_sources_import_view_and_uncertain_storage_preserve_draft(self):
        from traitweaver.intelligence_store import Journal
        request=self.prepare(); before=deepcopy(self.s.current()); preview_hash=self.view()['preview']['preview_sha256']
        readonly=Journal.from_package(self.j.export(),self.bundle)
        for method in ('prepare','respond'):
            with self.subTest(owner='readonly_source',method=method),self.assertRaises(ValueError):
                if method=='prepare': self.s.prepare(self.s.fingerprint(),readonly,self.e,self.ctx,preview_hash,True,'transfer')
                else: self.s.respond(self.s.fingerprint(),readonly,self.e,self.ctx,raw=self.raw(request))
        self.e.open(self.e.fingerprint(),execution.Session(self.bundle).export())
        self.assertFalse(self.view()['can_prepare']); self.assertEqual(len(self.view()['preview']['bridge_records']),1)
        with self.assertRaises(ValueError): self.prepare()
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request))
        self.e.local(self.e.fingerprint()); self.e.storage_blocked=True
        self.assertFalse(self.view()['can_prepare']); self.assertFalse(self.view()['can_review'])
        with self.assertRaises(ValueError): self.prepare()
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request))
        self.assertEqual(self.s.current(),before)

    def test_cache_rechecks_owned_bytes_and_owned_pending_attempt_keeps_its_origin(self):
        request=self.prepare(); before=deepcopy(self.s.current()); events=deepcopy(self.e.events)
        changed=self.view(); changed['preview']['bridge_records'][0]['result']['facts']['combination_effect']=1
        self.assertIsNone(self.view()['preview']['bridge_records'][0]['result']['facts']['combination_effect'])
        self.e.events[-1]['payload']['acknowledged']=False
        self.assertEqual(self.view()['preview']['status'],'unavailable')
        with self.assertRaises(ValueError): self.s.respond(self.s.fingerprint(),self.j,self.e,self.ctx,raw=self.raw(request))
        self.assertEqual(self.s.current(),before); self.e.events=events
        self.alternate('transfer_coverage',complete=False)
        proposal=deepcopy(self.fixture.fixture.session.current())
        self.e.approve(self.e.fingerprint(),proposal,self.j,self.ctx,True)
        with patch.object(model,'run_check',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            self.e.run(self.e.fingerprint(),self.j,self.ctx)
        preview=self.view()['preview']; self.assertEqual(preview['status'],'review_execution')
        pending=next(r for r in preview['bridge_records'] if r['result'] is None)
        self.assertEqual(pending['origin'],'owned_execution'); self.assertIsNone(pending['receipt_ref'])
        self.assertFalse(pending['owned_reviewed']); self.assertFalse(self.view()['can_prepare'])

    def test_cancelled_retry_numeric_equivalents_and_context_changes_do_not_reset_guards(self):
        self.fixture.fixture.revise(minimum_growth_ratio=0); self.fixture.fixture.cycle()
        self.alternate('transfer_coverage',complete=False)
        proposal=deepcopy(self.fixture.fixture.session.current())
        self.e.approve(self.e.fingerprint(),proposal,self.j,self.ctx,True)
        with patch.object(model,'run_check',side_effect=OSError('safe local failure')):
            self.e.run(self.e.fingerprint(),self.j,self.ctx)
        rid=self.e.view(self.j,self.ctx)['active']['attempts'][-1]['result']['id']
        self.e.reassess(self.e.fingerprint(),self.j,self.ctx,rid,True)
        self.e.retry(self.e.fingerprint(),self.j,self.ctx,rid,'reviewed_local_failure',True)
        self.assertEqual(self.view()['preview']['status'],'review_execution')
        self.e.cancel(self.e.fingerprint(),True)
        for value in (0,0.0,-0.0):
            self.fixture.fixture.revise(minimum_growth_ratio=value)
            self.assertEqual(self.view()['preview']['status'],'stop_no_new_inputs')
        self.ctx['study_revision_hash']='b'*64; self.fixture.fixture.revise()
        view=self.view(); self.assertEqual(view['preview']['status'],'stop_no_new_inputs')
        self.assertFalse(view['can_prepare'])
        self.assertTrue(any(r['result']['status']=='failed' for r in view['preview']['bridge_records']))


if __name__=='__main__': unittest.main()
