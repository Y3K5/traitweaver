"""Versioned v3 approvals preserve pinned snapshots and bounded pure replay."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import intelligence as model, intelligence_execution as execution
from traitweaver import intelligence_muse_v3 as v3, study
import test_intelligence_muse_v3 as fixtures


class FollowupExecutionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FollowupTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.j=self.f.j; self.e=self.f.e; self.ctx=self.f.ctx; self.bundle=self.f.bundle
        self.f.prepare(); self.f.s.respond(self.f.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
        self.review=deepcopy(self.f.s.current()); self.base=self.e.export()

    def approve(self): self.e.approve_followup(self.e.fingerprint(),self.review,self.j,self.ctx,True)
    def run_check(self): self.e.run(self.e.fingerprint(),self.j,self.ctx)
    def result(self): return self.e.view(self.j,self.ctx)['active']['attempts'][-1]['result']
    def acknowledge(self): self.e.reassess(self.e.fingerprint(),self.j,self.ctx,self.result()['id'],True)

    def test_exact_v3_approval_and_explicit_run_preserve_old_bytes(self):
        source=self.j.export(); review=deepcopy(self.review)
        with patch.object(model,'run_check',wraps=model.run_check) as dispatch:
            self.approve(); dispatch.assert_not_called()
            view=self.e.view(self.j,self.ctx)
            self.assertEqual(view['active']['approval']['proposal_version'],'v3')
            self.assertTrue(view['availability']['can_run'])
            self.run_check(); self.acknowledge(); self.assertEqual(dispatch.call_count,1)
        package=self.e.export(); self.assertEqual(package['schema_version'],execution.SCHEMA_V2)
        self.assertEqual(package['events'][:len(self.base['events'])],self.base['events'])
        self.assertEqual(self.j.export(),source); self.assertEqual(self.review,review)
        self.assertEqual(execution.validate_package(self.base,self.bundle),self.base)
        self.assertEqual(v3.validate_package(review,self.bundle),review)
        self.assertEqual(self.f.s.view(self.j,self.e,self.ctx)['preview']['status'],'stop_no_new_inputs')
        with self.assertRaises(ValueError): self.e.guard('transfer_coverage',self.j.current()['state']['scope'])

    def test_import_change_or_current_context_change_blocks_run_before_dispatch(self):
        self.approve(); other=self.f.alternate()
        self.e.open(self.e.fingerprint(),other.export()); self.e.local(self.e.fingerprint())
        with patch.object(model,'run_check') as dispatch:
            with self.assertRaises(ValueError): self.run_check()
            dispatch.assert_not_called()
        self.e.cancel(self.e.fingerprint(),True)
        self.f.prepare(); self.f.s.respond(self.f.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
        self.review=deepcopy(self.f.s.current()); self.approve()
        self.ctx['study_revision_hash']='b'*64
        with patch.object(model,'run_check') as dispatch:
            with self.assertRaises(ValueError): self.run_check()
            dispatch.assert_not_called()

    def test_own_failure_review_and_retry_suffix_is_allowed_without_new_model_call(self):
        self.approve()
        with patch.object(model,'run_check',side_effect=OSError('private failure')): self.run_check()
        self.acknowledge(); failed=self.result()['id']
        self.e.retry(self.e.fingerprint(),self.j,self.ctx,failed,'reviewed_local_failure',True)
        self.run_check(); self.acknowledge()
        self.assertEqual([a['ordinal'] for a in self.e.view(self.j,self.ctx)['active']['attempts']],[1,2])
        self.assertNotIn('private failure',study.canonical(self.e.export()))
        with self.assertRaises(ValueError): self.e.retry(self.e.fingerprint(),self.j,self.ctx,self.result()['id'],'reviewed_local_failure',True)

    def test_reopen_v2_execution_is_pure_and_guarded(self):
        self.approve(); self.run_check(); self.acknowledge(); package=self.e.export()
        with patch.object(model,'run_check',side_effect=AssertionError('No reopen dispatch')) as dispatch:
            restored=execution.Session(self.bundle); restored.open(restored.fingerprint(),package)
            self.assertEqual(restored.export(),package); dispatch.assert_not_called()
        restored.local(restored.fingerprint())
        with self.assertRaises(ValueError): restored.guard('transfer_coverage',self.j.current()['state']['scope'])

    def test_exact_preapproval_prefix_and_retained_guards_are_validated(self):
        other=self.f.alternate(); self.f.import_guard(other.export())
        self.f.prepare(); self.f.s.respond(self.f.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
        self.review=deepcopy(self.f.s.current()); self.approve(); package=self.e.export()
        changed=deepcopy(package); changed['guard_histories']=[]
        with self.assertRaises(ValueError): execution.validate_package(changed,self.bundle)
        changed=deepcopy(package); event=changed['events'][-1]
        event['payload']['review_package']['execution_package']['events']=[]
        event['hash']=study.digest({k:v for k,v in event.items() if k!='hash'})
        with self.assertRaises(ValueError): execution.validate_package(changed,self.bundle)

    def test_depth_and_work_limits_reject_before_recursive_review_validation(self):
        self.approve(); package=self.e.export()
        with patch.object(execution,'MAX_FOLLOWUP_DEPTH',0),patch.object(v3,'validate_package') as validate:
            with self.assertRaises(ValueError): execution.validate_package(package,self.bundle)
            validate.assert_not_called()
        with patch.object(execution,'MAX_VALIDATION_WORK_BYTES',1),self.assertRaises(ValueError):
            execution.validate_package(package,self.bundle)

    def test_cancelled_first_v3_approval_allows_bounded_fresh_v3_approval(self):
        self.approve(); self.e.cancel(self.e.fingerprint(),True)
        self.f.prepare(); self.f.s.respond(self.f.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
        self.review=deepcopy(self.f.s.current()); self.approve(); self.run_check(); self.acknowledge()
        self.assertEqual(self.f.s.view(self.j,self.e,self.ctx)['preview']['status'],'stop_no_new_inputs')

    def test_four_nested_approvals_are_bounded_and_fifth_draft_is_rejected(self):
        with patch.object(model,'run_check') as dispatch:
            for index in range(4):
                self.approve(); self.e.cancel(self.e.fingerprint(),True)
                if index<3:
                    self.f.prepare(); self.f.s.respond(self.f.s.fingerprint(),self.j,self.e,self.ctx,check='transfer_coverage')
                    self.review=deepcopy(self.f.s.current())
            before=deepcopy(self.f.s.current()); ledger=self.e.export()
            with self.assertRaisesRegex(ValueError,'depth'): self.f.prepare()
            self.assertEqual(self.f.s.current(),before); self.assertEqual(self.e.export(),ledger)
            dispatch.assert_not_called()

    def test_malformed_disk_events_and_python_values_fail_closed_as_value_error(self):
        for bad in (None,7,[],{},'invalid'):
            with self.subTest(value=bad),tempfile.TemporaryDirectory() as directory:
                (Path(directory)/'event-000001.json').write_text(study.canonical(bad))
                with self.assertRaises(ValueError): execution.Session(self.bundle,directory)
        for bad in ({'not_json':set()}, {'events':object()}):
            with self.assertRaises(ValueError): execution.validate_package(bad,self.bundle)

    def test_full_content_memo_is_per_call_and_work_steps_are_bounded(self):
        self.approve(); original=self.e.export()
        first=execution.validate_package(original,self.bundle)
        first['events'].clear()
        self.assertEqual(execution.validate_package(original,self.bundle),original)
        with patch.object(execution,'MAX_VALIDATION_STEPS',0),self.assertRaisesRegex(ValueError,'step budget'):
            execution.validate_package(original,self.bundle)
        altered=deepcopy(original); altered['events'][-1]['payload']['acknowledged']=False
        with self.assertRaises(ValueError): execution.validate_package(altered,self.bundle)


if __name__=='__main__': unittest.main()
