"""Read-only pilot admission must not invent, mix or silently drop results."""
import json
from pathlib import Path
import tempfile
import unittest
from traitweaver import showcase, evaluation_pilot as ep, completion_pilot as cp, assistant_evaluation as ae, study

class ShowcaseTests(unittest.TestCase):
    def record(self, module, slot):
        item=module.slot(slot)
        answer=ae.control(item['case_id'],item['permutation'])['answer']
        if module is cp:
            cards={a['id']:a for a in ae.get_case(item['case_id'])['candidate_actions']}
            answer['actions']=[{'action_id':aid,'rationale':'Synthetic repeated-task fixture','cited_record_ids':cards[aid]['citations']} for aid in ['RNA_RECONCILE','RNA_DESIGN_CHECK','RNA_LEDGER']]
        raw=study.canonical({'model':'muse-spark-1.3','status':'completed','traitweaver_synthetic':True,
            'output':[{'type':'message','content':[{'type':'output_text','text':study.canonical(answer)}]}]}).encode()
        return module.parse_reply(slot,raw,module.prepare(slot)['request_sha256'],offline=True)
    def save(self, root, module, slot):
        p=root/slot/'pilot-result.json';p.parent.mkdir();p.write_text(json.dumps(self.record(module,slot)));return p
    def test_missing_does_not_substitute(self):
        self.assertEqual(showcase.load_pilot(None,'rna')['status'],'not_loaded')
        with tempfile.TemporaryDirectory() as d:self.assertEqual(showcase.load_pilot(Path(d).resolve(),'rna')['status'],'not_loaded')
    def test_partial_is_explicit_and_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=self.save(root,ep,'RNA_BEFORE_O0');before=p.read_bytes()
            result=showcase.load_pilot(root,'rna')
            self.assertEqual(result['summary']['scored_slots'],1);self.assertTrue(result['synthetic'])
            self.assertIsNone(result['summary']['evidence_comparisons'][0]['first_action_changed'])
            self.assertEqual(p.read_bytes(),before)
    def test_corrupt_record_invalidates_projection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();self.save(root,ep,'RNA_BEFORE_O0');p=self.save(root,ep,'RNA_AFTER_O0');p.write_text('{}')
            self.assertEqual(showcase.load_pilot(root,'rna')['status'],'invalid')
    def test_misplaced_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=self.save(root,ep,'RNA_BEFORE_O0');p.write_text(json.dumps(self.record(ep,'RNA_AFTER_O0')))
            self.assertEqual(showcase.load_pilot(root,'rna')['status'],'invalid')
            p.unlink();p.symlink_to(root/'absent')
            self.assertEqual(showcase.load_pilot(root,'rna')['status'],'invalid')
    def test_completed_repetition_preserved_as_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();self.save(root,cp,'COMPLETED_O0')
            result=showcase.load_pilot(root,'completion')
            self.assertEqual(result['status'],'loaded')
            self.assertFalse(result['summary']['metrics'][0]['avoids_repeating_completed_work'])
