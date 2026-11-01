"""Public-reference gaps and synthetic coordinate/journal checks; zero sockets."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import molecular as m, molecular_store as ms, study
from traitweaver.study_store import Conflict


class MolecularTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('socket.socket',side_effect=AssertionError('No sockets'));self.guard.start();self.addCleanup(self.guard.stop)
        self.bundle=m.catalog();self.model=self.bundle['synthetic_models']
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-molecular-test-');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def selection(self,**changes):
        s=m.initial_selection();s.update(transcript_id='DEMO-TX-A.1');s.update(changes);return s

    def action(self,**changes):
        a={'selection':self.selection(),'stage':'identity','note':'Synthetic reviewer checkpoint',
           'context':{'study_id':'ALGAE_001','study_revision_hash':'a'*64,'target_endpoint':study.ENDPOINTS[0]}}
        a.update(changes);return a

    def test_public_gene_label_is_not_promoted_to_exact_gene_or_transcript(self):
        s=self.selection(protein_id='P42212',transcript_id=None)
        a=m.assess(s,self.bundle)
        self.assertEqual(a['mapping_status'],'unavailable');self.assertIsNone(a['mapping'])
        self.assertEqual(self.bundle['public_reference']['gene_label'],'GFP')
        self.assertIsNone(self.bundle['public_reference']['gene_id']);self.assertFalse(a['synthetic'])
        self.assertFalse(a['biological_target_ready'])

    def test_shared_protein_requires_explicit_transcript_choice(self):
        a=m.assess(m.initial_selection(),self.bundle)
        self.assertEqual(a['mapping_status'],'selection_required');self.assertEqual(len(a['candidate_transcripts']),2)
        self.assertIsNone(a['mapping'])
        for t in a['candidate_transcripts']:
            self.assertEqual(m.assess(self.selection(transcript_id=t),self.bundle)['mapping']['gene']['id'],'DEMO-GENE-1.1')

    def test_forward_coordinates_preserve_zero_phase_and_half_open_boundaries(self):
        a=m.transcript_map(self.model,'DEMO-TX-A.1')
        self.assertEqual((a['transcript_length_nt'],a['coding_length_nt'],a['protein_length_aa']),(340,270,90))
        self.assertEqual(a['rows'][0]['transcript_coding_interval'],[40,130])
        self.assertEqual(a['rows'][0]['coding_interval'],[0,90]);self.assertEqual(a['rows'][0]['protein_interval'],[0,30])
        self.assertEqual(a['rows'][0]['phase_at_coding_start'],0)

    def test_reverse_strand_uses_transcript_order_not_increasing_genomic_order(self):
        a=m.transcript_map(self.model,'DEMO-TX-MINUS.1')
        self.assertEqual(a['gene']['strand'],'-')
        self.assertEqual([r['exon_id'] for r in a['rows']],['M1','M2','M3'])
        self.assertEqual(a['rows'][0]['transcript_coding_interval'],[80,200])
        self.assertEqual(a['rows'][1]['transcript_coding_interval'],[200,260])
        self.assertEqual(a['protein_length_aa'],80)

    def test_noncoding_exon_changes_transcript_but_not_coding_or_protein_model(self):
        a=m.assess(self.selection(comparison_id='DEMO-TX-UTR.1'),self.bundle)['comparison']
        self.assertEqual((a['transcript_delta_nt'],a['coding_delta_nt'],a['protein_length_difference_aa']),(100,0,0))
        row=self.bundle['transcript_maps']['DEMO-TX-UTR.1']['rows'][-1]
        self.assertIsNone(row['coding_interval']);self.assertIsNone(row['protein_interval']);self.assertIsNone(row['phase_at_coding_start'])

    def test_alternative_membership_is_not_an_observed_splice_event(self):
        a=m.assess(self.selection(comparison_id='DEMO-TX-SKIP.1'),self.bundle)
        self.assertEqual(a['comparison']['primary_only'],['E2'])
        self.assertEqual((a['comparison']['coding_delta_nt'],a['comparison']['protein_length_difference_aa']),(-60,-20))
        self.assertIn('no splice event',a['comparison']['interpretation'])
        self.assertFalse(a['biological_target_ready'])

    def test_incomplete_coding_length_never_becomes_a_protein_length(self):
        a=m.assess(self.selection(comparison_id='DEMO-TX-PARTIAL.1'),self.bundle)['comparison']
        self.assertEqual(a['comparison_coding_remainder'],1);self.assertIsNone(a['protein_length_difference_aa'])
        self.assertTrue(all(r['protein_interval'] is None for r in self.bundle['transcript_maps']['DEMO-TX-PARTIAL.1']['rows']))

    def test_mismatched_unknown_and_cross_gene_selections_are_refused(self):
        for s in [self.selection(protein_id='unknown'),self.selection(transcript_id='DEMO-TX-SKIP.1'),
                  self.selection(comparison_id='DEMO-TX-MINUS.1'),self.selection(comparison_id='DEMO-TX-A.1'),
                  self.selection(goal='arbitrary_script'),self.selection(goal=[]),self.selection(transcript_id='')]:
            with self.subTest(s=s),self.assertRaises(ValueError):m.validate_selection(s,self.bundle)

    def test_model_context_strand_lengths_and_roles_are_validated(self):
        cases=[]
        x=deepcopy(self.model);x['source']['role']='published_observation';cases.append(x)
        x=deepcopy(self.model);x['genes'][0]['start']=True;cases.append(x)
        x=deepcopy(self.model);x['transcripts'][-1]['exon_ids'].reverse();cases.append(x)
        x=deepcopy(self.model);x['transcripts'][0]['exon_ids'].append('M1');cases.append(x)
        x=deepcopy(self.model);x['proteins'][0]['length_aa']=91;cases.append(x)
        x=deepcopy(self.model);x['exons'][0]['cds']=[0,20];cases.append(x)
        x=deepcopy(self.model);x['genes'].append(x['genes'][0]);cases.append(x)
        x=deepcopy(self.model);x['exons'][0]['cds']=[120,210];cases.append(x)
        for x in cases:
            with self.subTest(x=x['schema_version']),self.assertRaises(ValueError):m.validate_models(x)

    def test_modified_fixture_is_rejected_without_any_lookup_fallback(self):
        p=self.folder/'changed.json';p.write_text(json.dumps(self.model)+' ')
        with patch.object(m,'FIXTURE',p),self.assertRaisesRegex(ValueError,'changed'):m.catalog()
        p.write_bytes(b' '*131073)
        with patch.object(m,'FIXTURE',p),self.assertRaisesRegex(ValueError,'oversized'):m.catalog()

    def test_bounded_concepts_have_no_execution_or_new_provider_evidence(self):
        for goal in m.GOALS:
            a=m.assess(self.selection(goal=goal),self.bundle)
            self.assertTrue(a['planning_only']);self.assertFalse(a['biological_target_ready'])
            self.assertIn('guide sequences',a['concept']['not_generated'])
            self.assertIn('independent biological units',a['measurement_plan']['independent_units'])

    def test_journal_restart_export_import_preserves_revisions_and_original_state(self):
        j=ms.Journal(self.bundle,self.folder/'reviews');a=j.save(None,self.action())
        b=j.save(a['hash'],self.action(stage='transcripts'))
        self.assertEqual(b['parent_hash'],a['hash'])
        reopened=ms.Journal(self.bundle,self.folder/'reviews');self.assertEqual(reopened.current(),b)
        imported=ms.Journal.from_package(j.export(),self.bundle);self.assertTrue(imported.read_only)
        self.assertEqual(imported.export(),j.export())
        with self.assertRaises(ValueError):imported.save(b['hash'],self.action())
        self.assertEqual(reopened.current(),b)

    def test_goal_and_context_changes_preserve_old_history_but_reset_acknowledgments(self):
        j=ms.Journal(self.bundle);first=j.save(None,self.action())
        changed=self.action(selection=self.selection(goal='decrease_expression'),stage='concept')
        second=j.save(first['hash'],changed)
        self.assertEqual(second['state']['reviewed_stages'],['concept'])
        self.assertEqual(j.history[0],first)
        self.assertNotEqual(first['state']['planning_assessment']['concept'],second['state']['planning_assessment']['concept'])
        self.assertFalse(first['state']['planning_assessment']['biological_target_ready'])
        fake={'hash':'b'*64,'state':{'study_id':'ALGAE_001','brief':{'target_endpoint':study.ENDPOINTS[0]}}}
        self.assertEqual(j.view(fake)['context_status'],'needs_review')

    def test_stale_write_and_interrupted_publication_preserve_last_valid_revision(self):
        j=ms.Journal(self.bundle,self.folder/'reviews');r=j.save(None,self.action())
        with self.assertRaises(Conflict):j.save(None,self.action())
        with patch.object(ms.os,'link',side_effect=OSError('Synthetic failure')),self.assertRaises(OSError):j.save(r['hash'],self.action(stage='review'))
        self.assertEqual(j.current(),r);self.assertEqual(ms.Journal(self.bundle,j.root).current(),r)
        self.assertEqual(list(j.root.glob('.pending-*')),[])

    def test_rehashed_tampering_extra_fields_and_false_readiness_are_rejected(self):
        j=ms.Journal(self.bundle,self.folder/'source-linked');j.save(None,self.action())
        for key,value in [('note','Changed after save'),('biological_target_ready',True)]:
            p=j.export();r=p['revisions'][0];r['state'][key]=value;r['hash']=study.digest({k:v for k,v in r.items() if k!='hash'})
            with self.assertRaises(ValueError):ms.validate_package(p,self.bundle)
        p=j.export();p['catalog']['public_reference']['gene_id']='fabricated'
        with self.assertRaises(ValueError):ms.validate_package(p,self.bundle)
        changed=deepcopy(self.bundle);changed['public_reference']['organism']='Changed metadata'
        with self.assertRaises(ValueError):ms.Journal(changed,j.root)

    def test_privacy_rejection_and_corrupt_saved_record_do_not_erase_valid_work(self):
        j=ms.Journal(self.bundle,self.folder/'reviews');r=j.save(None,self.action())
        with self.assertRaisesRegex(ValueError,'privacy review'):j.save(r['hash'],self.action(note='/'+'home'+'/synthetic/input'))
        self.assertEqual(j.current(),r)
        (j.root/'review-000002.json').write_text('{bad')
        with self.assertRaises(ValueError):ms.Journal(self.bundle,j.root)
        self.assertEqual(study.decode((j.root/'review-000001.json').read_bytes()),r)

    def test_symlinked_and_oversized_records_are_refused(self):
        link=self.folder/'link';link.symlink_to(self.folder/'missing',target_is_directory=True)
        with self.assertRaises(ValueError):ms.Journal(self.bundle,link)
        j=ms.Journal(self.bundle,self.folder/'reviews');j.save(None,self.action())
        p=j.root/'review-000001.json';p.unlink();p.symlink_to(self.folder/'not-read')
        with self.assertRaises(ValueError):ms.Journal(self.bundle,j.root)
        p.unlink();p.write_bytes(b' '*(ms.MAX_BYTES+1))
        with self.assertRaises(ValueError):ms.Journal(self.bundle,j.root)


if __name__=='__main__':unittest.main()
