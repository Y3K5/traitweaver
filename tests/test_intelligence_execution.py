"""Human-gated local checks, durable reservations and read-only receipt imports."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from traitweaver import intelligence as model, intelligence_execution as execution
from traitweaver import intelligence_store, study
from traitweaver.study_store import Conflict
import test_intelligence_muse_v2 as fixtures


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NextSelectionTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.j = self.fixture.j; self.bundle = self.fixture.bundle; self.ctx = self.fixture.ctx
        self.fixture.prepare()
        owner = self.fixture.session
        owner.respond(owner.fingerprint(), self.j, self.ctx, check='combination_coverage')
        self.proposal = deepcopy(owner.current()); self.s = execution.Session(self.bundle)

    def approve(self):
        self.s.approve(self.s.fingerprint(), self.proposal, self.j, self.ctx, True)

    def run_check(self):
        self.s.run(self.s.fingerprint(), self.j, self.ctx)

    def result(self):
        return self.s.view(self.j, self.ctx)['active']['attempts'][-1]['result']

    def review(self):
        self.s.reassess(self.s.fingerprint(), self.j, self.ctx, self.result()['id'], True)

    def fail(self):
        self.approve()
        with patch.object(model, 'run_check', side_effect=OSError('private failure detail')):
            self.run_check()

    def test_approval_run_and_human_review_are_separate_and_preserve_old_bytes(self):
        before = study.canonical(self.j.export()); proposal = deepcopy(self.proposal)
        with patch.object(model, 'run_check', wraps=model.run_check) as dispatch:
            self.approve(); dispatch.assert_not_called()
            self.assertEqual(self.s.view(self.j, self.ctx)['status'], 'approved')
            self.run_check(); self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(self.result()['outcome'], 'unavailable')
            self.review(); self.assertEqual(dispatch.call_count, 1)
        active = self.s.view(self.j, self.ctx)['active']
        self.assertEqual(active['reassessment']['provenance'], 'human_acknowledgment_of_fixed_local_result')
        self.assertEqual(active['reassessment']['result_id'], self.result()['id'])
        self.assertEqual(study.canonical(self.j.export()), before); self.assertEqual(self.proposal, proposal)

    def test_exact_ack_stale_hash_and_imported_source_reject_without_dispatch(self):
        for ack in (False, 1, None, 'true'):
            with self.assertRaises(ValueError): self.s.approve(self.s.fingerprint(), self.proposal, self.j, self.ctx, ack)
        readonly = intelligence_store.Journal.from_package(self.j.export(), self.bundle)
        with self.assertRaises(ValueError): self.s.approve(self.s.fingerprint(), self.proposal, readonly, self.ctx, True)
        old = self.s.fingerprint(); self.approve()
        with patch.object(model, 'run_check') as dispatch:
            with self.assertRaises(Conflict): self.s.run(old, self.j, self.ctx)
            self.fixture.revise(recipient='study_uvm4')
            with self.assertRaises(ValueError): self.run_check()
            dispatch.assert_not_called()

    def test_cancel_releases_only_an_unstarted_reservation(self):
        self.approve()
        with self.assertRaises(ValueError): self.s.guard('combination_coverage', self.j.current()['state']['scope'])
        self.s.cancel(self.s.fingerprint(), True)
        self.s.guard('combination_coverage', self.j.current()['state']['scope'])
        self.approve(); self.run_check()
        with self.assertRaises(ValueError): self.s.cancel(self.s.fingerprint(), True)

    def test_duplicate_guard_covers_other_reviews_and_irrelevant_scope_changes(self):
        self.approve(); self.run_check(); self.review()
        with self.assertRaises(ValueError): self.approve()
        scope = deepcopy(self.j.current()['state']['scope']); scope.update(recipient='study_uvm4', minimum_growth_ratio=0)
        with self.assertRaises(ValueError): self.s.guard('combination_coverage', scope)
        scope['combination'] = 'regulation_storage'; self.s.guard('combination_coverage', scope)

    def test_failure_requires_separate_review_and_one_explicit_retry(self):
        self.fail(); failed = self.result()['id']
        self.assertNotIn('private failure detail', study.canonical(self.s.export()))
        with self.assertRaises(ValueError): self.s.retry(self.s.fingerprint(), self.j, self.ctx, failed, 'reviewed_local_failure', True)
        self.review()
        for result_id, reason in ((failed, 'automatic'), ('0'*64, 'reviewed_local_failure')):
            with self.assertRaises(ValueError): self.s.retry(self.s.fingerprint(), self.j, self.ctx, result_id, reason, True)
        with patch.object(model, 'run_check', side_effect=OSError('private second failure')) as dispatch:
            self.s.retry(self.s.fingerprint(), self.j, self.ctx, failed, 'reviewed_local_failure', True)
            dispatch.assert_not_called(); self.run_check(); self.assertEqual(dispatch.call_count, 1)
        self.review()
        with self.assertRaises(ValueError): self.s.retry(self.s.fingerprint(), self.j, self.ctx, self.result()['id'], 'reviewed_local_failure', True)
        self.assertEqual([a['ordinal'] for a in self.s.view(self.j,self.ctx)['active']['attempts']], [1,2])

    def test_started_interruption_cannot_cancel_retry_or_dispatch_again(self):
        self.approve()
        with patch.object(model, 'run_check', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt): self.run_check()
        self.assertEqual(self.s.view(self.j,self.ctx)['status'], 'started')
        with patch.object(model, 'run_check') as dispatch:
            with self.assertRaises(ValueError): self.run_check()
            with self.assertRaises(ValueError): self.s.cancel(self.s.fingerprint(), True)
            with self.assertRaises(ValueError): self.s.retry(self.s.fingerprint(), self.j, self.ctx, 'missing', 'reviewed_local_failure', True)
            dispatch.assert_not_called()

    def test_malformed_dispatch_return_stays_indeterminate_not_retryable_failure(self):
        self.approve()
        with patch.object(model,'run_check',return_value={'unexpected':'not a result'}), self.assertRaises(ValueError):
            self.run_check()
        self.assertEqual(self.s.view(self.j,self.ctx)['status'],'started')
        self.assertIsNone(self.result())
        with self.assertRaises(ValueError): self.run_check()

    def test_completed_unavailable_result_never_permits_retry(self):
        self.approve(); self.run_check(); self.review()
        self.assertEqual(self.result()['outcome'],'unavailable')
        with self.assertRaises(ValueError):
            self.s.retry(self.s.fingerprint(),self.j,self.ctx,self.result()['id'],'reviewed_local_failure',True)

    def test_durable_start_and_result_survive_reload_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            self.s = execution.Session(self.bundle, directory); self.approve(); self.run_check(); self.review()
            package = self.s.export()
            with patch.object(model, 'run_check', side_effect=AssertionError('No replay dispatch')) as dispatch:
                restored = execution.Session(self.bundle, directory)
                self.assertEqual(restored.export(), package)
                self.assertEqual(execution.validate_package(package, self.bundle), package)
                dispatch.assert_not_called()

    def test_start_write_failure_never_dispatches(self):
        self.approve(); before = self.s.export()
        with patch.object(self.s, '_persist', side_effect=OSError('start write failed')), patch.object(model, 'run_check') as dispatch:
            with self.assertRaises(OSError): self.run_check()
            dispatch.assert_not_called()
        self.assertEqual(self.s.export(), before)

    def test_result_write_failure_remains_started_on_disk_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            self.s = execution.Session(self.bundle, directory); self.approve(); persist = self.s._persist
            def write(event):
                if event['kind'] == 'result': raise OSError('result write failed')
                return persist(event)
            with patch.object(self.s, '_persist', side_effect=write), patch.object(model, 'run_check', wraps=model.run_check) as dispatch:
                with self.assertRaises(OSError): self.run_check()
                self.assertEqual(dispatch.call_count, 1)
            restored = execution.Session(self.bundle, directory)
            self.assertEqual(restored.view(self.j,self.ctx)['status'], 'started')
            with self.assertRaises(ValueError): restored.run(restored.fingerprint(), self.j, self.ctx)

    def test_imports_are_readonly_and_do_not_reset_owned_guards(self):
        empty = self.s.export(); self.approve(); self.run_check(); self.review(); owned = self.s.export()
        self.s.open(self.s.fingerprint(), empty)
        self.assertTrue(self.s.view(self.j,self.ctx)['read_only'])
        with self.assertRaises(ValueError): self.s.cancel(self.s.fingerprint(), True)
        self.s.local(self.s.fingerprint()); self.assertEqual(self.s.export()['events'], owned['events'])
        with self.assertRaises(ValueError): self.s.guard('combination_coverage', self.j.current()['state']['scope'])

    def test_imported_guard_survives_external_reload_and_cannot_authorize_retry(self):
        self.fail(); self.review(); imported = self.s.export()
        with tempfile.TemporaryDirectory() as directory:
            other = execution.Session(self.bundle, directory); other.open(other.fingerprint(), imported)
            other.local(other.fingerprint()); restored = execution.Session(self.bundle, directory)
            with self.assertRaises(ValueError): restored.guard('combination_coverage', self.j.current()['state']['scope'])
            with self.assertRaises(ValueError): restored.approve(restored.fingerprint(), self.proposal, self.j, self.ctx, True)
            with self.assertRaises(ValueError): restored.retry(restored.fingerprint(), self.j, self.ctx, self.result()['id'], 'reviewed_local_failure', True)

    def test_old_prefix_import_does_not_resurrect_cancelled_reservation(self):
        self.approve(); old = self.s.export(); self.s.cancel(self.s.fingerprint(), True)
        self.s.open(self.s.fingerprint(), old); self.s.local(self.s.fingerprint())
        self.s.guard('combination_coverage', self.j.current()['state']['scope']); self.approve()

    def test_combined_import_guard_bounds_are_checked_before_persistence(self):
        self.approve(); template=self.s.export(); chains=[]
        for number in range(3):
            chain=deepcopy(template['events']); event=chain[0]
            event['saved_utc']='2026-11-03T00:00:0'+str(number)+'+00:00'
            event['hash']=study.digest({k:v for k,v in event.items() if k!='hash'}); chains.append(chain)
        first={**deepcopy(template),'events':[],'guard_histories':chains[:2]}
        second={**deepcopy(template),'events':chains[2],'guard_histories':[]}
        other=execution.Session(self.bundle)
        with patch.object(execution,'MAX_IMPORTS',2):
            other.open(other.fingerprint(),first); before=other.fingerprint()
            with patch.object(other,'_write') as write, self.assertRaises(ValueError):
                other.open(other.fingerprint(),second)
            write.assert_not_called(); self.assertEqual(other.fingerprint(),before)

    def test_cleanup_error_after_publication_does_not_lose_committed_event(self):
        with tempfile.TemporaryDirectory() as directory:
            self.s=execution.Session(self.bundle,directory); original=Path.unlink
            def cleanup(path,*args,**kwargs):
                if path.name.startswith('.pending-'): raise OSError('cleanup unavailable')
                return original(path,*args,**kwargs)
            with patch.object(Path,'unlink',cleanup): self.approve()
            self.assertEqual(self.s.view(self.j,self.ctx)['status'],'approved')
            self.assertEqual(execution.Session(self.bundle,directory).export(),self.s.export())

    def test_visible_event_sync_failure_blocks_memory_until_durable_reload(self):
        for failure_call, expected_status, calls in ((2,'started',0),(4,'completed',1)):
            with self.subTest(stage=expected_status), tempfile.TemporaryDirectory() as directory:
                self.s=execution.Session(self.bundle,directory); self.approve(); original=execution.os.fsync; count=0
                def sync(fd):
                    nonlocal count
                    count+=1
                    if count==failure_call: raise OSError('directory sync interrupted')
                    return original(fd)
                with patch.object(execution.os,'fsync',side_effect=sync), patch.object(model,'run_check',wraps=model.run_check) as dispatch:
                    with self.assertRaises(OSError): self.run_check()
                    self.assertEqual(dispatch.call_count,calls)
                self.assertTrue(self.s.storage_blocked)
                with self.assertRaises(ValueError): self.s.guard('transfer_coverage',self.j.current()['state']['scope'])
                with self.assertRaises(ValueError): self.s.export()
                restored=execution.Session(self.bundle,directory)
                self.assertEqual(restored.view(self.j,self.ctx)['status'],expected_status)

    def test_conflicting_fork_import_is_rejected_before_write(self):
        self.approve(); self.run_check(); fork=self.s.export(); before=self.s.fingerprint()
        fork['events'][1]['saved_utc']='2026-11-03T00:00:00+00:00'
        for index,event in enumerate(fork['events']):
            event['parent_hash']=fork['events'][index-1]['hash'] if index else None
            event['hash']=study.digest({k:v for k,v in event.items() if k!='hash'})
        execution.validate_package(fork,self.bundle)
        with patch.object(self.s,'_write') as write, self.assertRaisesRegex(ValueError,'fork'):
            self.s.open(self.s.fingerprint(),fork)
        write.assert_not_called(); self.assertEqual(self.s.fingerprint(),before)

    def test_concurrent_run_requests_dispatch_once(self):
        self.approve(); expected=self.s.fingerprint(); barrier=threading.Barrier(2)
        def run():
            barrier.wait()
            try: self.s.run(expected,self.j,self.ctx); return 'completed'
            except Conflict: return 'stale'
        with patch.object(model,'run_check',wraps=model.run_check) as dispatch, ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:run(),range(2)))
            self.assertEqual(sorted(results),['completed','stale']); self.assertEqual(dispatch.call_count,1)

    def test_stale_result_can_be_human_reviewed_without_becoming_current(self):
        self.approve(); self.run_check(); saved=deepcopy(self.result())
        self.fixture.revise(combination='regulation_storage')
        self.assertTrue(self.s.view(self.j,self.ctx)['availability']['can_review'])
        self.review(); self.assertEqual(self.s.view(self.j,self.ctx)['applicability'],'stale')
        self.assertEqual(self.result(),saved)
        self.fixture.prepare(); owner=self.fixture.session
        owner.respond(owner.fingerprint(),self.j,self.ctx,check='combination_coverage')
        self.proposal=deepcopy(owner.current()); self.approve()
        self.assertEqual(self.s.view(self.j,self.ctx)['status'],'approved')

    def test_stale_failure_can_be_reviewed_but_cannot_authorize_a_retry(self):
        self.fail(); self.fixture.revise(recipient='study_uvm4'); self.review()
        self.assertFalse(self.s.view(self.j,self.ctx)['availability']['can_retry'])
        with self.assertRaises(ValueError):
            self.s.retry(self.s.fingerprint(),self.j,self.ctx,self.result()['id'],'reviewed_local_failure',True)

    def test_cancel_stale_unstarted_retry_preserves_failure_guard_and_allows_other_inputs(self):
        self.fail(); self.review(); failed=deepcopy(self.result())
        self.s.retry(self.s.fingerprint(),self.j,self.ctx,failed['id'],'reviewed_local_failure',True)
        attempts=deepcopy(self.s.view(self.j,self.ctx)['active']['attempts'])
        self.fixture.revise(recipient='study_uvm4')
        view=self.s.view(self.j,self.ctx)
        self.assertEqual(view['applicability'],'stale'); self.assertTrue(view['availability']['can_cancel'])
        for ack in (False,1,None,'true'):
            with self.assertRaises(ValueError): self.s.cancel(self.s.fingerprint(),ack)
        with patch.object(model,'run_check') as dispatch:
            self.s.cancel(self.s.fingerprint(),True); dispatch.assert_not_called()
        view=self.s.view(self.j,self.ctx)
        self.assertEqual(view['status'],'cancelled'); self.assertEqual(view['active']['attempts'],attempts)
        self.assertEqual(view['active']['reassessment']['result_id'],failed['id'])
        with self.assertRaises(ValueError): self.s.guard('combination_coverage',self.j.current()['state']['scope'])
        self.fixture.prepare(); owner=self.fixture.session
        owner.respond(owner.fingerprint(),self.j,self.ctx,check='combination_coverage')
        with self.assertRaises(ValueError):
            self.s.approve(self.s.fingerprint(),owner.current(),self.j,self.ctx,True)
        self.fixture.prepare()
        owner.respond(owner.fingerprint(),self.j,self.ctx,check='transfer_coverage')
        self.s.approve(self.s.fingerprint(),owner.current(),self.j,self.ctx,True)
        self.assertEqual(self.s.view(self.j,self.ctx)['active']['approval']['check'],'transfer_coverage')

    def test_tampered_rehashed_receipt_and_malformed_import_preserve_owned_work(self):
        self.approve(); self.run_check(); package = self.s.export(); changed = deepcopy(package)
        event = changed['events'][-1]; event['payload']['result']['facts']['combination_effect'] = 1
        event['hash'] = study.digest({k:v for k,v in event.items() if k!='hash'})
        for bad in (changed, {}, None, {**package,'extra':True}):
            with patch.object(model,'run_check') as dispatch:
                with self.assertRaises(ValueError): self.s.open(self.s.fingerprint(), bad)
                dispatch.assert_not_called()
        self.assertEqual(self.s.export(), package)

    def test_capacity_is_reserved_before_dispatch_and_views_are_copies(self):
        self.approve(); before = self.s.export()
        with patch.object(execution,'MAX_EVENTS',len(before['events'])+1), patch.object(model,'run_check') as dispatch:
            with self.assertRaises(ValueError): self.run_check()
            dispatch.assert_not_called()
        view = self.s.view(self.j,self.ctx); view['active']['approval']['scope']['recipient']='study_uvm4'
        self.assertEqual(self.s.export(),before)
        self.assertIn('process', self.s.view(self.j,self.ctx)['persistence_notice'])


if __name__ == '__main__': unittest.main()
