"""Offline scientific claim boundaries, pre-result decisions and durable records."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import intelligence as m, intelligence_muse as ai, intelligence_store as db, public_algae, study
from traitweaver.study_store import Conflict


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        g=patch('socket.socket',side_effect=AssertionError('No sockets'));g.start();self.addCleanup(g.stop)
        self.b=m.catalog();self.j=db.Journal(self.b);self.ctx={'study_id':'PUBLIC_ALGAE','study_revision_hash':'a'*64};self.revise()

    def revise(self,**changes):
        scope=m.initial_scope();scope.update(changes);return self.j.apply(self.j.current()['hash'],{'type':'revise','payload':{'scope':scope,'context':self.ctx}})

    def accepted(self,phase='selection',focus='trait',change=None):
        s=self.j.current()['state'];req=ai.prepare(s,phase,self.b,focus);reply=ai.synthetic_reply(s,phase,self.b,focus)
        if change:change(reply)
        return ai.parse_reply(s,phase,study.canonical(reply).encode(),req['request_sha256'],self.b,focus)

    def accept(self,phase='selection',focus='trait'):
        p=self.accepted(phase,focus);return self.j.apply(self.j.current()['hash'],{'type':'accept','payload':p})

    def run_cycle(self,focus='trait'):
        self.accept(focus=focus);self.j.apply(self.j.current()['hash'],{'type':'run','payload':{}});self.accept('reassessment',focus)
        return self.j.current()['state']['cycles'][-1]

    def test_catalog_is_public_source_bound_and_keeps_one_candidate(self):
        self.assertEqual(len(self.b['candidates']),1);c=self.b['candidates'][0]
        self.assertEqual(c['protein_id'],'XP_001700553.1');self.assertIsNone(c['necessity']);self.assertIsNone(c['sufficiency'])
        self.assertEqual(self.b['source_digests']['reference'],study.digest(public_algae.catalog()))
        self.assertEqual(self.b['source_digests']['literature'],study.digest(study.bundle()))

    def test_trait_supported_association_preserves_summary_stats_and_context(self):
        self.revise(target_endpoint='phosphate_uptake');r=self.run_cycle()['result']
        self.assertEqual(r['outcome'],'supported');self.assertEqual(len(r['facts']['matching_records']),4)
        for e in r['facts']['matching_records']:
            self.assertEqual(e['uncertainty']['kind'],'SE');self.assertEqual(e['uncertainty']['n'],3)
            self.assertEqual(e['uncertainty']['independent_unit'],'culture replicate');self.assertIn('unit',e)
        self.assertIn('UVM4',' '.join(r['blockers']));self.assertIsNone(r['facts']['necessity'])

    def test_recovery_endpoint_stays_unavailable_without_erasing_identity(self):
        r=self.run_cycle()['result'];self.assertEqual(r['outcome'],'unavailable')
        self.assertEqual(r['facts']['numeric_record_count'],0);self.assertEqual(r['facts']['matching_records'],[])
        self.assertEqual(r['facts']['mapping']['length_aa'],752);self.assertIsNone(r['facts']['causal_effect'])

    def test_growth_ratios_are_descriptive_and_zero_differs_from_unknown(self):
        for margin in (None,0,.99):
            self.revise(target_endpoint='phosphate_uptake',minimum_growth_ratio=margin)
            r=self.run_cycle()['result'];self.assertEqual(r['facts']['growth_constraint']['margin'],margin)
            flags=[x['meets_point_mean_margin'] for x in r['facts']['growth_constraint']['point_mean_comparisons']]
            self.assertEqual(flags,[None]*3 if margin is None else [margin==0]*3)
            self.assertEqual(r['outcome'],'contradictory' if margin==.99 else 'supported')

    def test_combinations_are_role_hypotheses_with_unknown_effects(self):
        r=self.run_cycle('combinations')['result'];f=r['facts']
        self.assertEqual(f['qualified_pair_count'],0);self.assertIsNone(f['combination_effect']);self.assertIsNone(f['synergy'])
        self.assertEqual(f['roles'][1]['candidate_ids'],[]);self.assertIsNone(f['roles'][1]['required_for_trait'])
        self.assertIn('not a qualified protein combination',r['interpretation'])

    def test_recipient_reference_identity_is_not_transfer_function(self):
        for recipient,expected in [('unselected','unavailable'),('study_uvm4','unavailable'),('reference_cc503','inconclusive')]:
            self.revise(recipient=recipient);r=self.run_cycle('transfer')['result']
            self.assertEqual(r['outcome'],expected);self.assertIsNone(r['facts']['transfer_success_probability'])
            self.assertIsNone(r['facts']['phenotype_transfer'])

    def test_missing_reference_blocks_identity_but_retains_public_trait_records(self):
        with patch.object(public_algae,'catalog',side_effect=ValueError('Do not expose path')):b=m.catalog()
        self.assertIsNone(b['reference']);self.assertIsNone(b['candidates'][0]['protein_id'])
        scope=m.initial_scope();scope['target_endpoint']='phosphate_uptake';r=m.audit('trait_evidence_audit',scope,b)
        self.assertEqual(r['facts']['numeric_record_count'],4);self.assertIsNone(r['facts']['mapping'])
        self.assertNotIn('Do not expose path',study.canonical(b))

    def test_request_contains_public_inputs_not_owning_notes_or_identifiers(self):
        req=ai.prepare(self.j.current()['state'],'selection',self.b)
        body=study.decode(req['body']['input']);self.assertNotIn('context',body);self.assertNotIn('PUBLIC_ALGAE',req['body']['input'])
        self.assertFalse(req['live_transport_available']);self.assertEqual(req['status'],'not_sent');self.assertEqual(req['body']['max_output_tokens'],1024)
        self.assertIn('public_literature',body);self.assertIn('reference_mapping',body)

    def test_scope_validation_rejects_boolean_nonfinite_and_unregistered_inputs(self):
        for changes in ({'minimum_growth_ratio':False},{'minimum_growth_ratio':float('inf')},{'minimum_growth_ratio':-1},{'recipient':'unqualified-species-name'},{'combination':[]},{'target_endpoint':'recovery_winner'}):
            with self.assertRaises(ValueError):m.validate_scope({**m.initial_scope(),**changes})

    def test_altered_arguments_unknown_citations_and_success_claims_are_rejected(self):
        def alter(fn):
            def change(reply):
                p=study.decode(reply['output'][0]['content'][0]['text']);fn(p);reply['output'][0]['content'][0]['text']=study.canonical(p)
            return change
        mutations=[lambda p:p['citations'].append('UNKNOWN'),lambda p:p['arguments'].update(recipient='reference_cc503'),
                   lambda p:p.update(protein_necessary=True),lambda p:p.update(claim_codes=['transfer_success_proven']),lambda p:p.update(check='execute_script')]
        for mutate in mutations:
            with self.assertRaises(ValueError):self.accepted(change=alter(mutate))
        self.assertEqual(self.j.current()['revision'],1)

    def test_false_cannot_substitute_for_a_zero_growth_argument(self):
        self.revise(minimum_growth_ratio=0)
        p=deepcopy(self.accepted()['proposal']);p['arguments']['minimum_growth_ratio']=False
        with self.assertRaises(ValueError):ai.validate_proposal(self.j.current()['state'],'selection',p,self.b)

    def test_refusal_wrong_model_incomplete_and_unrestricted_tool_output_rejected(self):
        changes=[lambda r:r.update(status='incomplete'),lambda r:r.update(model='other-model'),lambda r:r.update(output=[{'type':'function_call','name':'shell'}]),
                 lambda r:r.update(output=[{'type':'message','content':[{'type':'refusal','refusal':'No'}]}])]
        for fn in changes:
            with self.assertRaises(ValueError):self.accepted(change=fn)

    def test_saved_usage_is_typed_bounded_and_not_claimed_as_actual_spend(self):
        p=self.accepted(change=lambda r:r.update(usage={'input_tokens':0,'output_tokens':0,'total_tokens':0}));self.assertEqual(p['receipt']['reported_usage']['output_tokens'],0)
        self.assertIsNone(p['receipt']['cost_usd']);self.assertEqual(p['receipt']['transport_calls'],0)
        for u in ({'input_tokens':1,'output_tokens':1025,'total_tokens':1026},{'input_tokens':True,'output_tokens':0,'total_tokens':1},{'input_tokens':1,'output_tokens':2,'total_tokens':0}):
            with self.assertRaises(ValueError):self.accepted(change=lambda r:r.update(usage=u))

    def test_credential_echo_is_rejected_before_any_record_is_saved(self):
        with self.assertRaises(ValueError):self.accepted(change=lambda r:r.update(extra='sk-'+'x'*24))
        self.assertEqual(self.j.current()['revision'],1)

    def test_one_decision_execution_and_reassessment_per_cycle(self):
        with self.assertRaises(ValueError):self.j.apply(self.j.current()['hash'],{'type':'run','payload':{}})
        self.accept()
        with self.assertRaises(ValueError):self.accept()
        with self.assertRaises(ValueError):self.accept('reassessment')
        self.j.apply(self.j.current()['hash'],{'type':'run','payload':{}})
        with self.assertRaises(ValueError):self.j.apply(self.j.current()['hash'],{'type':'run','payload':{}})
        self.accept('reassessment')
        with self.assertRaises(ValueError):self.accept('reassessment')
        self.assertEqual(len(self.j.current()['state']['cycles']),1)

    def test_stale_request_or_record_cannot_advance_the_cycle(self):
        old=self.accepted();oldhash=self.j.current()['hash'];self.revise(target_endpoint='growth')
        with self.assertRaises(ValueError):self.j.apply(self.j.current()['hash'],{'type':'accept','payload':old})
        with self.assertRaises(Conflict):self.j.apply(oldhash,{'type':'revise','payload':{'scope':m.initial_scope(),'context':self.ctx}})

    def test_prior_selection_cannot_be_replayed_as_a_new_cycle(self):
        old=self.accepted();self.run_cycle()
        with self.assertRaises(ValueError):self.j.apply(self.j.current()['hash'],{'type':'accept','payload':old})

    def test_changed_scope_preserves_old_decision_result_and_assessment(self):
        before=self.run_cycle();self.revise(target_endpoint='phosphate_uptake')
        old=self.j.current()['state']['cycles'][0];self.assertEqual(old['applicability'],'needs_reassessment')
        for k in ('decision','result','assessment'):self.assertEqual(old[k],before[k])
        self.assertEqual(self.j.history[0]['state']['scope']['target_endpoint'],'recovered_product_phosphorus')

    def test_local_software_failure_is_saved_and_reassessed_without_exception_text(self):
        self.accept()
        with patch.object(m,'run_check',side_effect=OSError('private debug detail')):self.j.apply(self.j.current()['hash'],{'type':'run','payload':{}})
        self.accept('reassessment');c=m.active(self.j.current()['state'])
        self.assertEqual(c['result']['outcome'],'failed');self.assertEqual(c['assessment']['outcome'],'failed')
        self.assertNotIn('private debug detail',study.canonical(self.j.export()))

    def test_export_reopen_and_validation_never_dispatch_a_tool_or_model(self):
        self.run_cycle('transfer');p=self.j.export()
        with patch.object(m,'run_check',side_effect=AssertionError('No dispatch on reopen')),patch.object(ai,'synthetic_reply',side_effect=AssertionError('No model on reopen')):
            restored=db.Journal.from_package(p,self.b);self.assertEqual(restored.export(),p);self.assertTrue(restored.read_only)
        with self.assertRaises(ValueError):restored.apply(restored.current()['hash'],{'type':'run','payload':{}})

    def test_missing_result_or_forged_but_rehashed_receipt_is_rejected(self):
        self.run_cycle();p=self.j.export();run=next(r for r in p['revisions'] if r['action']['type']=='run')
        for change in (None,{'fake':'result'}):
            x=deepcopy(p);r=next(v for v in x['revisions'] if v['action']['type']=='run');r['state']['cycles'][-1]['result']=change;r['hash']=study.digest({k:v for k,v in r.items() if k!='hash'})
            with patch.object(m,'run_check',side_effect=AssertionError('Import cannot dispatch')),self.assertRaises(ValueError):db.validate_package(x,self.b)
        changed=deepcopy(p);changed['catalog']['candidates'].append({'id':'invented'})
        with self.assertRaises(ValueError):db.validate_package(changed,self.b)

    def test_disk_restart_interrupted_publication_and_context_review(self):
        with tempfile.TemporaryDirectory() as folder:
            j=db.Journal(self.b,folder);r=j.apply(None,{'type':'revise','payload':{'scope':m.initial_scope(),'context':self.ctx}})
            with patch('traitweaver.intelligence_store.os.link',side_effect=OSError('Interrupted')),self.assertRaises(OSError):j.apply(r['hash'],{'type':'revise','payload':{'scope':m.initial_scope(),'context':self.ctx}})
            self.assertEqual(db.Journal(self.b,folder).current(),r);self.assertEqual(list(Path(folder).glob('.pending-*')),[])
            self.assertIn('PROVISIONAL',j.readable());self.assertIn('CC-503',j.readable())

    def test_complete_cycles_survive_canonical_json_and_disk_restart(self):
        self.run_cycle();p=study.decode(study.canonical(self.j.export()).encode())
        with patch.object(m,'run_check',side_effect=AssertionError('No dispatch on restart')):
            self.assertEqual(db.Journal.from_package(p,self.b).export(),p)
            with tempfile.TemporaryDirectory() as folder:
                for r in p['revisions']:(Path(folder)/('revision-'+str(r['revision']).zfill(6)+'.json')).write_text(study.canonical(r)+'\n')
                self.assertEqual(db.Journal(self.b,folder).export(),p)

    def test_early_schema_array_order_records_remain_valid_without_rewriting(self):
        original=ai.response_schema
        def early_schema(state,phase,bundle):
            schema=original(state,phase,bundle)
            schema['properties']['citations']['items']['enum']=list(bundle['claims'])
            if phase=='selection':schema['properties']['arguments']['required']=list(reversed(sorted(state['scope'])))
            return schema
        with patch.object(ai,'response_schema',side_effect=early_schema):self.run_cycle()
        p=study.decode(study.canonical(self.j.export()).encode());before=deepcopy(p)
        self.assertEqual(db.Journal.from_package(p,self.b).export(),before)
        # Historical validation cannot admit an old selection as a new cycle.
        old=p['revisions'][1]['action']['payload']
        with self.assertRaises(ValueError):self.j.apply(self.j.current()['hash'],{'type':'accept','payload':old})


if __name__=='__main__':unittest.main()
