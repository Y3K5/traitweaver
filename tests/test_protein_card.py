"""Focused offline GFP card and real launcher checks; no generated science."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import protein_card as card

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'run_protein_card.py'


def no_network(event, args):
    if event.startswith('socket.'):
        raise RuntimeError('Protein-card tests prohibit socket operations')


sys.addaudithook(no_network)


class ProteinCardTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='traitweaver-card-test-')
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        self.report = card.build_card()

    def cli(self, *args):
        guard = '''import runpy,sys
def offline(event,args):
 if event.startswith('socket.'): raise RuntimeError('No sockets in card CLI tests')
sys.addaudithook(offline)
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        return subprocess.run([sys.executable, '-B', '-c', guard, str(LAUNCHER), *map(str,args)],
                              cwd=self.folder, env={'PATH':'/usr/bin:/bin'},
                              capture_output=True, text=True, timeout=15)

    def test_pinned_sources_identity_roles_and_original_feature_values_are_preserved(self):
        inputs = card._load_inputs()
        raw = inputs['atlas-record.json']
        identity = self.report['identity']
        self.assertEqual(identity['sequence'], inputs['accession.json']['sequence'])
        self.assertEqual(identity['sequence_length'], 238)
        self.assertEqual(identity['atlas_accession'], 'UPI0000002FB4')
        self.assertEqual(hashlib.md5(identity['sequence'].encode()).hexdigest(), identity['atlas_protein_hash_md5'])
        self.assertEqual(hashlib.sha256(identity['sequence'].encode()).hexdigest(), identity['sequence_sha256'])
        self.assertEqual(len(self.report['model_predictions']), 3)
        for got, original in zip(self.report['model_predictions'], raw['sae_features']):
            self.assertEqual({k:got[k] for k in original}, original)
            self.assertEqual(got['role'], 'model_prediction')
            self.assertEqual(got['value_state'], 'reported')
            self.assertEqual(got['source_id'], 'S_ATLAS_GFP')
        self.assertEqual(self.report['database_annotations'][0]['value'], inputs['accession.json']['function'])
        self.assertEqual(self.report['database_annotations'][0]['role'], 'database_annotation')
        self.assertEqual(self.report['experimental_evidence'], [])

    def test_nulls_original_zero_coordinate_and_component_licenses_are_preserved(self):
        self.assertTrue(all(value is None for value in self.report['unavailable'].values()))
        self.assertEqual(self.report['model_predictions'][2]['residue_regions'][0]['start'], 0)
        self.assertIs(type(self.report['model_predictions'][2]['residue_regions'][0]['start']), int)
        self.assertEqual(self.report['attribution'], card._load_inputs()['QUALIFICATION.json']['license_provenance'])
        self.assertEqual(self.report['attribution']['sequences_and_all_data_collections'], 'CC BY-SA 4.0')

    def test_loader_reads_only_three_pinned_files_and_changed_bytes_have_no_fallback(self):
        original = Path.read_bytes
        reads = []
        def tracked(path):
            reads.append(path)
            return original(path)
        with patch.object(Path,'read_bytes',tracked):
            card._load_inputs()
        self.assertEqual(reads,[card.FIXTURE_ROOT/name for name in card.PINS])
        for name in card.PINS:
            (self.folder/name).write_bytes((card.FIXTURE_ROOT/name).read_bytes())
        (self.folder/'atlas-record.json').write_text('{}')
        with patch.object(card,'FIXTURE_ROOT',self.folder), self.assertRaisesRegex(ValueError,'bytes changed'):
            card.build_card()

    def test_missing_or_symlink_fixture_is_refused_without_lookup(self):
        with patch.object(card,'FIXTURE_ROOT',self.folder), self.assertRaises(OSError):
            card.build_card()
        (self.folder/'accession.json').symlink_to(card.FIXTURE_ROOT/'accession.json')
        with patch.object(card,'FIXTURE_ROOT',self.folder), self.assertRaisesRegex(ValueError,'symlink'):
            card.build_card()

    def test_closed_versioned_schema_rejects_roles_values_null_changes_and_extra_fields(self):
        mutations=[lambda r:r.update(schema_version='traitweaver.file_only_case.v1'),
                   lambda r:r['model_predictions'][0].update(role='published_observation'),
                   lambda r:r['model_predictions'][0].update(value=0),
                   lambda r:r['unavailable'].update(ptm=0),
                   lambda r:r['unavailable'].update(model_version='invented'),
                   lambda r:r['model_predictions'][2]['residue_regions'][0].update(start=False),
                   lambda r:r['sources'][0].update(id='UNRESOLVED'),
                   lambda r:r.update(extra='unsupported'),
                   lambda r:r['attribution'].update(sequences_and_all_data_collections='CC BY 4.0')]
        for index,mutate in enumerate(mutations):
            variant=deepcopy(self.report);mutate(variant)
            with self.subTest(index=index), self.assertRaises(ValueError):
                card.validate_card(variant)

    def test_saved_report_reopens_without_access_to_source_fixture(self):
        path=self.folder/'saved.json';path.write_text(json.dumps(self.report))
        with patch.object(card,'_load_inputs',side_effect=AssertionError('Fixture must not be read')):
            self.assertEqual(card.open_report(path),self.report)
        link=self.folder/'link.json';link.symlink_to(path)
        with self.assertRaisesRegex(ValueError,'symlink'):card.open_report(link)

    def test_saved_report_rejects_malformed_duplicate_nonfinite_and_oversize_json(self):
        path=self.folder/'saved.json'
        for raw in [b'{bad', b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b' '* (card.MAX_REPORT_BYTES+1)]:
            path.write_bytes(raw)
            with self.subTest(raw_size=len(raw)),self.assertRaises(ValueError):card.open_report(path)

    def test_export_round_trip_readable_precision_and_static_html_integrity(self):
        before=deepcopy(self.report)
        output=card.export_bundle(self.report,self.folder/'export')
        self.assertEqual({p.name for p in output.iterdir()},{'index.html','protein-card.json','protein-card.txt'})
        self.assertEqual(card.open_report(output/'protein-card.json'),self.report)
        readable=(output/'protein-card.txt').read_text()
        for text in ['0.3951131478760761','start 0; end 237','pdb: Unavailable (null)','model_prediction','database_annotation','CC BY-SA 4.0','S_ATLAS_GFP']:
            self.assertIn(text,readable)
        html=(output/'index.html').read_text()
        script=html.split('<script>',1)[1].split('</script>',1)[0]
        self.assertIn("'sha256-"+base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()+"'",html)
        self.assertIn("connect-src 'none'",html)
        self.assertNotIn('/*CARD_DATA*/',html)
        self.assertNotIn('/Users/',html)
        self.assertNotIn('fetch(',html)
        self.assertEqual(self.report,before)

    def test_export_refuses_overwrite_symlink_app_destination_and_missing_parent(self):
        output=self.folder/'existing';output.mkdir()
        (output/'keep').write_text('unchanged')
        link=self.folder/'linked';link.symlink_to(output,target_is_directory=True)
        for target in [output,link,ROOT/'outputs/not-created']:
            with self.assertRaises(ValueError):card.export_bundle(self.report,target)
        self.assertEqual((output/'keep').read_text(),'unchanged')
        with self.assertRaises(OSError):card.export_bundle(self.report,self.folder/'missing/child')
        self.assertFalse((self.folder/'missing').exists())

    def test_failed_export_removes_only_new_files(self):
        output=self.folder/'failed'
        original=Path.open
        def fail(path,*args,**kwargs):
            if path==output/'index.html':raise OSError('Synthetic write failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',fail),self.assertRaises(OSError):card.export_bundle(self.report,output)
        self.assertFalse(output.exists())

    def test_real_launcher_creates_page_and_views_exported_saved_report(self):
        output=self.folder/'first'
        result=self.cli('--output-dir',output)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn((output/'index.html').resolve().as_uri(),result.stdout)
        self.assertEqual(card.open_report(output/'protein-card.json'),self.report)
        saved=self.folder/'reopened'
        result=self.cli('--report',output/'protein-card.json','--output-dir',saved)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('no study restored',result.stdout)
        self.assertEqual(card.open_report(saved/'protein-card.json'),self.report)
        self.assertIn('const savedMode = true;',(saved/'index.html').read_text())
        result=self.cli('--output-dir',output)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('Traceback',result.stderr)

    def test_invalid_saved_report_and_unapproved_input_option_do_not_export(self):
        path=self.folder/'wrong.json';path.write_text('{}')
        output=self.folder/'never'
        for args in [('--report',path,'--output-dir',output),('--fixture','other','--output-dir',output)]:
            result=self.cli(*args)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(output.exists())
            self.assertNotIn('Traceback',result.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
