"""Public guided-study lifecycle, integrity and failure checks; no network."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import study
from traitweaver.study_store import Conflict, Store, package, validate_package


class StudyMVPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='traitweaver-mvp-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'study'
        self.store = Store(self.path)
        self.addCleanup(self.store.close)

    def apply(self, kind, payload=None):
        return self.store.apply(self.store.current()['hash'], {'type': kind, 'payload': payload or {}})

    def choose(self, check='endpoint_coverage', metric=None):
        return self.apply('decide', {'check': check, 'arguments': {} if metric is None else {'metric': metric}, 'policy': 'user_selected'})

    def complete(self, check='endpoint_coverage', metric=None):
        self.choose(check, metric);self.apply('run');return self.apply('reassess')

    def test_public_admission_is_exact_and_internal_case_is_not_loaded(self):
        b = study.bundle()
        self.assertEqual(len(b['evidence']), 10)
        self.assertEqual({r['subject'] for r in b['evidence'][:8]}, {'UVM4','8-27','8-42','8-2'})
        self.assertEqual([e['value'] for e in b['evidence'][8:]], [None,None])
        self.assertTrue(all(e['role']=='published_observation' for e in b['evidence']))
        with patch.object(study, 'BUNDLE', self.path/'missing'):
            with self.assertRaises(OSError):study.bundle()

    def test_changed_public_bytes_are_refused(self):
        path=self.path/'changed.json';path.write_text('{}')
        with patch.object(study,'BUNDLE',path),self.assertRaisesRegex(ValueError,'changed'):study.bundle()

    def test_source_contrasts_keep_all_lines_control_units_se_n(self):
        out=study.contrasts(self.store.current()['state'],'phosphate_uptake')
        self.assertEqual([r['subject'] for r in out['rows']], ['8-27','8-42','8-2'])
        self.assertAlmostEqual(out['rows'][0]['ratio_to_control'],.97/.48)
        self.assertAlmostEqual(out['rows'][0]['difference_from_control'],.49)
        self.assertEqual(out['control']['value'],.48)
        self.assertEqual(out['rows'][0]['reported_uncertainty'],{'kind':'SE','value':.04,'n':3,'independent_unit':'culture replicate'})
        self.assertNotIn('p_value',out)

    def test_zero_control_yields_null_ratio_not_infinity(self):
        b=study.bundle();b['evidence'][4]['value']=0
        with patch.object(study,'bundle',return_value=b):
            out=study.contrasts(self.store.current()['state'],'phosphate_uptake')
        self.assertTrue(all(r['ratio_to_control'] is None for r in out['rows']))

    def test_missing_and_mismatched_units_cannot_combine(self):
        for mutate,status in [(lambda b:b['evidence'].pop(7),'unavailable'),
                              (lambda b:b['evidence'][5].update(unit='different'),'invalid'),
                              (lambda b:b['evidence'][5].update(value=None),'invalid')]:
            b=study.bundle();mutate(b)
            with patch.object(study,'bundle',return_value=b):
                self.assertEqual(study.contrasts(self.store.current()['state'],'phosphate_uptake')['status'],status)

    def test_coverage_keeps_endpoints_context_and_unknown_margin_separate(self):
        r=study.coverage(self.store.current()['state'])
        self.assertTrue(all(row['state']=='unavailable' for row in r['rows']))
        self.assertIn('growth_margin_unknown',[b['code'] for b in r['blockers']])
        self.assertIn('different_source_contexts',[b['code'] for b in r['blockers']])

    def test_decision_must_precede_result_and_assessment(self):
        for kind in ['run','reassess']:
            with self.assertRaises(ValueError):self.apply(kind)
        decision=self.choose()
        self.assertIsNone(decision['state']['cycles'][-1]['result'])
        self.assertEqual(set(decision['state']['cycles'][-1]['decision']['branches']),set(study.BRANCHES))
        with self.assertRaises(ValueError):self.choose()
        self.apply('run')
        with self.assertRaises(ValueError):self.apply('run')
        done=self.apply('reassess')
        self.assertEqual(done['state']['cycles'][-1]['assessment']['outcome'],'unavailable')
        self.assertIsNone(done['state']['recovery_winner'])
        with self.assertRaises(ValueError):self.apply('reassess')
        self.choose()  # A new cycle is deliberate, never auto-executed.

    def test_altered_tool_arguments_are_refused(self):
        with self.assertRaises(ValueError):self.choose('published_contrasts','recovered_product_phosphorus')
        with self.assertRaises(ValueError):self.choose('shell')

    def test_context_edit_preserves_result_but_invalidates_assessment(self):
        original=self.complete('published_contrasts','growth')
        old=deepcopy(original['state']['cycles'][0])
        brief=deepcopy(original['state']['brief']);brief['context_notes']='A different proposed material context'
        changed=self.apply('edit',brief)
        self.assertEqual(changed['state']['cycles'][0]['result'],old['result'])
        self.assertEqual(changed['state']['cycles'][0]['applicability'],'needs_reassessment')
        self.assertEqual(self.store.history[-2],original)
        with self.assertRaises(ValueError):self.apply('run')
        self.assertIn('context_transfer_unqualified',[b['code'] for b in study.coverage(changed['state'])['blockers']])
        self.choose()

    def test_stale_revision_and_bad_brief_leave_history_unchanged(self):
        old=self.store.current();brief=deepcopy(old['state']['brief']);brief['minimum_growth_ratio']=0
        self.apply('edit',brief)
        with self.assertRaises(Conflict):self.store.apply(old['hash'],{'type':'edit','payload':brief})
        for bad in [False,-1,float('inf'),'0']:
            brief['minimum_growth_ratio']=bad
            with self.assertRaises(ValueError):self.apply('edit',brief)
        self.assertEqual(len(self.store.history),2)

    def test_growth_constraint_has_descriptive_support_and_contradiction_not_equivalence(self):
        b=deepcopy(self.store.current()['state']['brief']);b.update(target_endpoint='growth',minimum_growth_ratio=0)
        self.apply('edit',b);r=self.complete('published_contrasts','growth')
        self.assertEqual(r['state']['cycles'][-1]['assessment']['outcome'],'supporting')
        b['minimum_growth_ratio']=2;self.apply('edit',b);r=self.complete('published_contrasts','growth')
        self.assertEqual(r['state']['cycles'][-1]['assessment']['outcome'],'contradictory')
        self.assertIsNone(r['state']['cycles'][-1]['assessment']['recovery_winner'])

    def test_software_failure_is_saved_without_exposing_exception_and_replays(self):
        self.choose('published_contrasts','growth')
        with patch.object(study,'contrasts',side_effect=OSError('private error detail')):r=self.apply('run')
        self.assertEqual(r['state']['cycles'][-1]['result']['status'],'failed')
        self.assertNotIn('private error detail',study.canonical(r))
        self.assertEqual(self.apply('reassess')['state']['cycles'][-1]['assessment']['outcome'],'failed')
        self.assertEqual(validate_package(self.store.export())['state'],self.store.current()['state'])

    def test_export_reopen_restores_state_without_execution_and_preserves_local_history(self):
        self.complete('published_contrasts','phosphate_uptake');saved=self.store.export()
        before=self.store.current()['state'];brief=deepcopy(before['brief']);brief['question']='A changed question'
        self.apply('edit',brief)
        with patch.object(study,'contrasts',side_effect=AssertionError('No tool dispatch on reopen')):
            restored=self.apply('restore',saved)
        # Replay checks saved arithmetic, but never dispatches a check or model.
        self.assertEqual(restored['state'],before)
        self.assertEqual(restored['action']['type'],'restore')
        self.assertEqual(validate_package(self.store.export())['state'],before)
        self.assertGreater(len(self.store.history),len(saved['revisions']))

    def test_corrupt_package_and_forged_but_rehashed_result_are_refused(self):
        self.complete();p=self.store.export();count=len(self.store.history)
        variants=[]
        q=deepcopy(p);q['revisions'][-1]['parent_hash']='0'*64;variants.append(q)
        q=deepcopy(p);q['source_bundle']['evidence'][0]['value']=999;variants.append(q)
        q=deepcopy(p);q['revisions'][2]['state']['cycles']=[];variants.append(q)
        q=deepcopy(p);q['revisions'][0]['state']=None;variants.append(q)
        q=deepcopy(p);r=q['revisions'][-1];r['state']['recovery_winner']='PATH_PSR1';r['hash']=study.digest({k:v for k,v in r.items() if k!='hash'});variants.append(q)
        for q in variants:
            with self.assertRaises(ValueError):self.apply('restore',q)
        self.assertEqual(len(self.store.history),count)

    def test_restart_loads_same_revision_and_refuses_corrupted_disk(self):
        self.complete();current=self.store.current();self.store.close()
        other=Store(self.path)
        self.assertEqual(other.current(),current);other.close()
        path=self.path/'revision-000002.json';path.write_text('{}')
        with self.assertRaises(ValueError):Store(self.path)
        self.assertFalse((self.path/'.workspace-owner.lock').exists())

    def test_interrupted_write_preserves_last_revision_and_removes_pending_file(self):
        old=self.store.current()
        with patch('traitweaver.study_store.os.link',side_effect=OSError('synthetic disk error')):
            with self.assertRaises(OSError):self.choose()
        self.assertEqual(self.store.current(),old)
        self.assertEqual(list(self.path.glob('.pending-*')),[])
        self.assertEqual(len(list(self.path.glob('revision-*.json'))),1)

    def test_second_writer_and_symlink_data_directory_are_refused(self):
        with self.assertRaises(ValueError):Store(self.path)
        link=Path(self.temp.name)/'link';link.symlink_to(self.path,target_is_directory=True)
        with self.assertRaises(ValueError):Store(link)

    def test_export_reports_private_path_without_silently_scrubbing(self):
        b=deepcopy(self.store.current()['state']['brief']);b['context_notes']='/Users/synthetic-owner/private'
        self.apply('edit',b)
        with self.assertRaisesRegex(ValueError,'privacy review'):self.store.export()
        self.assertEqual(self.store.current()['state']['brief']['context_notes'],b['context_notes'])

    def test_strict_json_rejects_duplicate_nonfinite_and_invalid_utf8(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'{bad']:
            with self.assertRaises(ValueError):study.decode(raw)

    def test_readable_handoff_preserves_roles_sources_and_measurement_gaps(self):
        self.complete();text=study.readable(self.store.current()['state'])
        for value in ['published_observation','S_PSR1_2023','S_OVERPLUS_2024','SE','independent','Not executed','Recovery winner: none']:
            self.assertIn(value,text)
        self.assertNotIn(str(self.path),text)


if __name__=='__main__':unittest.main(verbosity=2)
