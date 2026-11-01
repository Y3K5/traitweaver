"""Primary-file reconciliation, scientific limits and versioned review isolation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import molecular, molecular_store, public_algae, study
from traitweaver.study_store import Conflict


class PublicAlgaeTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket',side_effect=AssertionError('No network'));guard.start();self.addCleanup(guard.stop)
        self.bundle=public_algae.catalog()

    def action(self,**selection):
        s=public_algae.initial_selection();s.update(transcript_id=public_algae.TRANSCRIPT);s.update(selection)
        return {'selection':s,'stage':'identity','note':'Public reference review','context':{'study_id':'public-algae-demo','study_revision_hash':'a'*64,'target_endpoint':'recovered_product_phosphorus'}}

    def test_source_bytes_are_pinned_and_derivation_is_reproducible(self):
        self.assertEqual(public_algae.derive(),self.bundle)
        for s in self.bundle['sources']['sources']:
            raw=public_algae.source_file(s['file']);self.assertEqual(len(raw),s['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),s['sha256'])

    def test_exact_real_chain_and_one_transcript_without_synthetic_promotion(self):
        b=self.bundle;m=b['transcript_maps'][public_algae.TRANSCRIPT]
        self.assertEqual(m['transcript']['protein_id'],'XP_001700553.1');self.assertEqual(m['gene']['id'],'GeneID:5726104')
        self.assertEqual(m['gene']['assembly'],'GCF_000002595.2');self.assertEqual(len(b['models']['transcripts']),1)
        self.assertEqual((m['transcript_length_nt'],m['coding_length_nt'],m['protein_length_aa']),(4772,2256,752))
        self.assertEqual([r['genomic_interval'] for r in m['rows']],[[724591,725902],[726139,726807],[727200,729993]])
        self.assertNotIn('synthetic_models',b);self.assertEqual(b['role'],'public_reference_annotation')

    def test_terminal_stop_is_preserved_separately_and_codon_can_span_junction(self):
        m=self.bundle['transcript_maps'][public_algae.TRANSCRIPT];c=self.bundle['checks']
        self.assertEqual(c['annotated_cds_length_nt']-c['peptide_coding_length_nt'],3)
        self.assertEqual(c['terminal_stop_codon'],'TAG');self.assertEqual(c['stop_genomic_interval'],[728244,728247])
        self.assertEqual(c['stop_transcript_interval'],[3023,3026]);self.assertEqual(m['rows'][1]['phase_at_coding_start'],1)
        self.assertEqual(m['rows'][0]['protein_interval'],[0,182]);self.assertEqual(m['rows'][1]['protein_interval'],[181,404])

    def test_refseq_annotation_status_and_strain_limits_are_retained(self):
        self.assertIn('PROVISIONAL',self.bundle['record_status']);self.assertIn('unreviewed',self.bundle['record_status'])
        self.assertEqual(self.bundle['strain'],'CC-503 cw92 mt+')
        self.assertIn('UVM4',' '.join(self.bundle['unknowns']))
        self.assertIn('gene-level',self.bundle['sources']['publication_identity']['basis'])

    def test_unknown_isoforms_cannot_become_a_comparison_or_biological_result(self):
        s=public_algae.initial_selection();a=molecular.assess(s,self.bundle)
        self.assertEqual(a['mapping_status'],'selection_required');self.assertIsNone(a['mapping'])
        s['transcript_id']=public_algae.TRANSCRIPT;s['goal']='isoform_comparison';a=molecular.assess(s,self.bundle)
        self.assertFalse(a['biological_target_ready']);self.assertFalse(a['synthetic']);self.assertIsNone(a['comparison'])
        for change in ({'comparison_id':public_algae.TRANSCRIPT},{'transcript_id':'unadmitted-transcript'},{'protein_id':'Q9S807'},{'goal':'run-script'}):
            with self.assertRaises(ValueError):molecular.validate_selection({**s,**change},self.bundle)

    def test_changed_source_blocks_even_when_derived_json_remains_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            # Resolve the OS temporary-directory alias; this test targets changed
            # source bytes, rather than deliberately testing a symlink parent.
            root=Path(folder).resolve();(root/'evidence-needed').mkdir()
            for name in ['SOURCE_MANIFEST.json','reference.v2.json','evidence-needed/REQUIREMENTS.json']+[s['file'] for s in self.bundle['sources']['sources']]:
                (root/name).write_bytes((public_algae.ROOT/name).read_bytes())
            p=root/'refseq_XM_001700501.2.gb';p.write_bytes(p.read_bytes()+b'\n')
            with patch.object(public_algae,'ROOT',root),self.assertRaisesRegex(ValueError,'Pinned public source changed'):public_algae.catalog()

    def test_incompatible_source_feature_cannot_be_silently_normalized(self):
        original=public_algae.source_file
        def changed(name):
            raw=original(name)
            return raw.replace(b'join(1..1311,1549..2216,2610..5402)',b'join(1..1310,1549..2216,2610..5402)') if name=='reference_gene_region.gb' else raw
        with patch.object(public_algae,'source_file',changed),self.assertRaisesRegex(ValueError,'sequence disagreement'):public_algae.derive()
        for expression in ['complement(1..30)','<1..30','join(1..20,15..30)','REMOTE:1..3']:
            with self.assertRaises(ValueError):public_algae._intervals(expression)

    def test_translation_rejects_ambiguity_internal_stop_and_missing_stop(self):
        self.assertEqual(public_algae._translate('ATGTAG'),'M')
        for dna in ('ATG','ATNTAG','ATGTAGTAG','ATGTA','ATGTGG'):
            with self.assertRaises(ValueError):public_algae._translate(dna)

    def test_requirements_are_explicitly_empty_and_traceable_to_real_sources(self):
        needs=json.loads((public_algae.ROOT/'evidence-needed/REQUIREMENTS.json').read_text())
        self.assertEqual(needs['observations'],[]);self.assertEqual(len(needs['requirements']),4)
        names={s['file'] for s in self.bundle['sources']['sources']}
        for c in self.bundle['claims']:self.assertTrue(set(c['files'])<=names)
        plan=public_algae.measurement_plan(public_algae.initial_selection())
        self.assertIn('recovered-product phosphorus',' '.join(plan['readouts']))
        self.assertIn('independent',plan['independent_units'])

    def test_v2_checkpoint_restart_and_readonly_reopen_preserve_source_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            j=molecular_store.Journal(self.bundle,folder);r=j.save(None,self.action());p=j.export()
            self.assertEqual(p['schema_version'],'traitweaver.molecular_review.v2');self.assertEqual(r['schema_version'],'traitweaver.molecular_revision.v2')
            self.assertEqual(molecular_store.Journal(self.bundle,folder).export(),p)
            imported=molecular_store.Journal.from_package(p,self.bundle);self.assertTrue(imported.read_only)
            with self.assertRaises(ValueError):imported.save(r['hash'],self.action())
            self.assertIn('refseq_XM_001700501.2.gb',j.readable());self.assertIn('PROVISIONAL',study.canonical(p))
            self.assertIn(self.bundle['record_status'],j.readable());self.assertIn('Reference strain: CC-503 cw92 mt+',j.readable())
            with self.assertRaises(ValueError):molecular_store.Journal.from_package(p,molecular.catalog())

    def test_goal_change_stale_edit_and_interrupted_save_preserve_prior_assessment(self):
        with tempfile.TemporaryDirectory() as folder:
            j=molecular_store.Journal(self.bundle,folder);r=j.save(None,self.action());old=deepcopy(r)
            with self.assertRaises(Conflict):j.save(None,self.action())
            with patch('traitweaver.molecular_store.os.link',side_effect=OSError('Interrupted local save')),self.assertRaises(OSError):j.save(r['hash'],self.action(goal='decrease_expression'))
            self.assertEqual(molecular_store.Journal(self.bundle,folder).current(),old)
            new=j.save(r['hash'],self.action(goal='decrease_expression'))
            self.assertEqual(j.history[0],old);self.assertNotEqual(new['state']['planning_assessment']['concept'],old['state']['planning_assessment']['concept'])

    def test_legacy_v1_contract_still_exports_and_replays_without_public_case(self):
        bundle=molecular.catalog();j=molecular_store.Journal(bundle);s=molecular.initial_selection();s['transcript_id']='DEMO-TX-A.1'
        a=self.action();a['selection']=s;j.save(None,a);p=j.export()
        self.assertEqual(p['schema_version'],'traitweaver.molecular_review.v1');self.assertEqual(p['limit'],molecular.LIMIT)
        self.assertNotIn('public_algae',p);self.assertEqual(molecular_store.Journal.from_package(p,bundle).export(),p)


if __name__=='__main__':unittest.main()
