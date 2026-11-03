"""Mission acceptance: honest roles, typed imports, immutable review and safe reopen."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from traitweaver import release_review as r, study
import test_review_handlers as handlers

class StudyReviewTests(unittest.TestCase):
    def setUp(self): self.s=r.Session()
    def export(self): return self.s.export(self.s.current()['hash'])
    def add(self,c=None): self.s.apply({'type':'candidate','payload':c or r.template()})
    def review(self):
        self.s.apply({'type':'review','payload':{'reviewer':'Synthetic tester','scope':'study','decision':'reviewed_with_blockers',
            'reason':'Software fixture, not a real scientific review','content_sha256':r.content_hash(self.s.state())}})
    def test_pinned_sources_graph_reference_and_four_endpoints(self):
        v=self.s.view(); ids={n['id'] for n in v['graph']['nodes']}
        self.assertTrue(all(e['from'] in ids and e['to'] in ids and e['evidence_node'] in ids for e in v['graph']['edges']))
        self.assertEqual(len(v['endpoints']),4)
        m=v['science']['reference_mapping'];self.assertEqual(m['gene']['assembly'],'GCF_000002595.2')
        self.assertEqual(m['gene']['start'],724591);self.assertIn('0-based',m['coordinate_system'])
        self.assertIsNone(v['science']['annotation_version']);self.assertTrue(v['blockers'])
    def test_default_human_review_unknown_and_no_cycle_fabricated(self):
        self.assertEqual(self.s.state()['reviews'],[]);self.assertIsNone(self.s.view()['cycle'])
    def test_typed_records_no_conversion_and_numeric_zero_preserved(self):
        for i,(kind,seq) in enumerate([('guide_rna','ACGU'),('primer_dna','ACGT'),('genomic_dna','ACGTN'),('protein_aa','MKW')]):
            c=r.template();c.update(id='SYNTHETIC_'+str(i),sequence_type=kind,sequence=seq,reported_value=0,reported_unit='dimensionless')
            self.add(c)
        p=self.export();target=r.Session();target.open(p)
        self.assertEqual(target.export(target.current()['hash']),p)
        self.assertTrue(all(c['reported_value']==0 and c['reference']['assembly'] is None for c in target.state()['candidates']))
    def test_malformed_reference_sequence_or_claim_does_not_mutate(self):
        changes=[{'sequence_type':'guide_rna','sequence':'ACGT'}, {'sequence_type':'primer_dna','sequence':'ACGU'},
                 {'reported_value':True}, {'reported_value':float('nan')}, {'reported_stage':'ready'},
                 {'reported_stage':'experimentally_evaluated'}, {'reported_stage':'computationally_assessed'}]
        before=self.s.current()
        for change in changes:
            c=r.template();c.update(change)
            with self.assertRaises(ValueError):self.add(c)
            self.assertEqual(before,self.s.current())
        c=r.template();c['reference']['interval']=[0,10]
        with self.assertRaises(ValueError):self.add(c)
    def test_source_tool_versions_assessments_preserved_as_reported(self):
        c=r.template();c['reported_stage']='computationally_assessed';c['tool']={'name':'Synthetic local tool','version':None,'settings':'Synthetic configuration'}
        c['assessments']['specificity']='Unassessed; local score is not specificity analysis';self.add(c)
        self.assertEqual(self.s.state()['candidates'][0],c);self.assertTrue(any('not independently verified' in x for x in self.s.view()['blockers']))
    def test_incompatible_reference_blocks_mapping_without_conversion(self):
        c=r.template();c['reference']['assembly']='GCF_000000000.1';c['reference']['accession']='NC_000000.1'
        self.add(c);v=self.s.view()
        self.assertEqual(v['record_checks'][0]['assembly'],'incompatible_with_pinned_reference')
        self.assertTrue(any('incompatible assembly' in b for b in v['blockers']))
        self.assertEqual(self.s.state()['candidates'][0]['reference'],c['reference'])

    def test_duplicates_and_unknown_fields_rejected(self):
        self.add();before=self.s.current()
        with self.assertRaises(ValueError):self.add()
        c=r.template();c['unexpected']='value'
        with self.assertRaises(ValueError):self.add(c)
        with self.assertRaises(ValueError):self.s.apply({'type':'candidate','payload':'{"id":"one","id":"two"}'})
        self.assertEqual(before,self.s.current())
    def test_multitrait_hypothesis_and_unassessed_pairs(self):
        self.s.apply({'type':'trait','payload':{'label':'Synthetic extra study question'}})
        v=self.s.view();self.assertEqual(v['state']['traits'][-1]['role'],'hypothesis_evidence_missing')
        self.assertEqual(len(v['interactions']),6);self.assertTrue(all(i['status']=='not_assessed' for i in v['interactions']))
    def test_review_binds_exact_content_and_changes_require_reassessment(self):
        self.review();old=deepcopy(self.s.state()['reviews'])
        self.s.apply({'type':'trait','payload':{'label':'A changed study question'}})
        self.assertEqual(old,self.s.state()['reviews']);self.assertNotEqual(old[0]['content_sha256'],r.content_hash(self.s.state()))
    def test_invalid_scope_and_duplicate_review_rejected(self):
        self.review();before=self.s.current()
        with self.assertRaises(ValueError):self.review()
        e=deepcopy(self.s.history[0]['event']);e['payload']['scope']='missing'
        with self.assertRaises(ValueError):self.s.apply(e)
        self.assertEqual(before,self.s.current())
    def test_all_history_privacy_gate_without_silent_scrub(self):
        b={k:self.s.state()[k] for k in ('question','recipient','constraints')};b['constraints']='Cookie: SYNTHETIC_TEST'
        self.s.apply({'type':'brief','payload':b});b['constraints']='Contained study';self.s.apply({'type':'brief','payload':b})
        self.assertEqual(self.s.view()['privacy']['status'],'blocked')
        with self.assertRaises(ValueError):self.export()
        self.assertIn('SYNTHETIC_TEST',study.canonical(self.s.history));self.assertNotIn('SYNTHETIC_TEST',study.canonical(self.s.view()['privacy']))
    def test_export_ack_stale_after_edit_and_plain_text_is_readable(self):
        before=self.s.current()['hash'];self.add()
        with self.assertRaises(ValueError):self.s.export(before)
        brief=self.s.readable(self.s.current()['hash']);self.assertIn('Confounders:',brief);self.assertIn('BLOCKERS',brief)
        self.assertIn('collected',brief);self.assertIn('Not reviewed',brief)
    def test_reopen_readonly_and_no_tool_model_execution(self):
        self.add();self.review();p=self.export();target=r.Session()
        with patch('traitweaver.muse_boundary.send_approved',side_effect=AssertionError('No provider')),patch('traitweaver.study.coverage',side_effect=AssertionError('No rerun')):
            target.open(p);self.assertEqual(p,target.export(target.current()['hash']))
        with self.assertRaises(ValueError):target.apply({'type':'trait','payload':{'label':'Changed'}})
    def test_invalid_reopen_retains_current_and_rehashed_forgery_rejected(self):
        self.add();p=self.export();before=self.s.current()
        for mutate in ('source','history','state','schema'):
            q=deepcopy(p)
            if mutate=='source':q['science']['annotation_version']='invented'
            elif mutate=='history':q['history'][0]['event']['payload']['id']='changed'
            elif mutate=='state':q['state']['question']='invented'
            else:q['schema_version']='unknown'
            q['sha256']=study.digest({k:v for k,v in q.items() if k!='sha256'})
            with self.assertRaises(ValueError):self.s.open(q)
            self.assertEqual(before,self.s.current())

class StudyReviewHandlerTests(unittest.TestCase):
    setUp=handlers.ReviewHandlerTests.setUp
    request=handlers.ReviewHandlerTests.request
    def test_review_routes_stale_duplicate_origin_and_atomic_import(self):
        owner=self.server.workspace.release_review;active=self.server.workspace.active.current()['hash']
        body={'expected_hash':active,'review_hash':owner.current()['hash'],'event':{'type':'candidate','payload':r.template()}}
        self.assertEqual(self.request('/api/study-review/apply',body,{'Origin':'https://outside.invalid'})[0],403)
        self.assertEqual(self.request('/api/study-review/apply',body)[0],200)
        self.assertEqual(self.request('/api/study-review/apply',body)[0],409)
        before=owner.current();body={'expected_hash':active,'review_hash':before['hash'],'package_json':'{invalid'}
        self.assertEqual(self.request('/api/study-review/open',body)[0],400);self.assertEqual(owner.current(),before)
        self.assertEqual(self.request('/api/study-review/export.json')[0],400)
        code,p=self.request('/api/study-review/export.json',headers={'X-Traitweaver-Privacy-Reviewed':before['hash']});self.assertEqual(code,200)
        body['package_json']=study.canonical(p);self.assertEqual(self.request('/api/study-review/open',body)[0],200)
        self.assertTrue(self.server.workspace.release_review.read_only)
        body={'expected_hash':active,'review_hash':self.server.workspace.release_review.current()['hash']}
        self.assertEqual(self.request('/api/study-review/local',body)[0],200);self.assertIs(self.server.workspace.release_review,owner)
