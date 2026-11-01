"""Actual local dispatch in memory; no API or network requests are sent."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import public_algae, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
from test_completed_cycle import fixture
import test_molecular_handlers as molecular_handlers
from test_review_handlers import MemoryServer


class PublicAlgaeHandlerTests(unittest.TestCase):
    request=molecular_handlers.MolecularHandlerTests.request

    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.folder=Path(t.name)
        g=patch('socket.socket',side_effect=AssertionError('No sockets'));g.start();self.addCleanup(g.stop)
        self.store=Store(self.folder/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def body(self,**changes):
        s=public_algae.initial_selection();s['transcript_id']=public_algae.TRANSCRIPT
        b={'expected_hash':self.server.workspace.active.current()['hash'],'molecular_hash':self.server.workspace.public_algae.current()['hash'],'selection':s,'stage':'identity','note':'Public reference checkpoint'}
        b.update(changes);return b

    def test_public_source_file_allowlist_and_exact_bytes(self):
        code,text=self.request('/public-algae-source/refseq_XM_001700501.2.gb')
        self.assertEqual(code,200);self.assertEqual(text.encode(),public_algae.source_file('refseq_XM_001700501.2.gb'))
        for path in ('../SOURCE_MANIFEST.json','%2e%2e%2fSOURCE_MANIFEST.json','SOURCE_MANIFEST.json','evidence-needed/REQUIREMENTS.json'):
            self.assertEqual(self.request('/public-algae-source/'+path)[0],400)

    def test_public_checkpoint_does_not_modify_legacy_synthetic_or_study(self):
        before=self.store.export();legacy=self.server.workspace.molecular.current()
        self.assertEqual(self.request('/api/public-algae/save',self.body())[0],200)
        self.assertEqual(self.store.export(),before);self.assertEqual(self.server.workspace.molecular.current(),legacy)
        self.assertTrue((self.store.root/'public-algae-review-v2/review-000001.json').is_file())
        self.assertEqual(self.request('/api/state')[1]['public_algae']['current']['revision'],1)

    def test_public_save_requires_origin_session_and_current_both_revisions(self):
        for h in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/public-algae/save',self.body(),h)[0],403)
        b=self.body();self.assertEqual(self.request('/api/public-algae/save',b)[0],200)
        self.assertEqual(self.request('/api/public-algae/save',b)[0],409)
        self.assertEqual(self.request('/api/public-algae/save',self.body(expected_hash='f'*64))[0],409)

    def test_export_reopen_and_corrupt_input_preserve_saved_disk(self):
        self.request('/api/public-algae/save',self.body());j=self.server.workspace.public_algae
        p=self.request('/api/public-algae/export.json')[1];self.assertEqual(p['schema_version'],'traitweaver.molecular_review.v2')
        self.assertIn('SOURCE FILES AND CLAIM TRACE',self.request('/api/public-algae/export.txt')[1])
        def request(text):return {'expected_hash':self.store.current()['hash'],'molecular_hash':j.current()['hash'],'package_json':text}
        self.assertEqual(self.request('/api/public-algae/open',request('{bad'))[0],400);self.assertIs(self.server.workspace.public_algae,j)
        self.assertEqual(self.request('/api/public-algae/open',request(study.canonical(p)))[0],200)
        self.assertTrue(self.server.workspace.public_algae.read_only)
        self.assertEqual(self.request('/api/public-algae/save',self.body())[0],400)
        self.assertEqual(study.decode((self.store.root/'public-algae-review-v2/review-000001.json').read_bytes()),j.current())

    def test_changed_study_context_marks_reassessment_without_erasing_public_review(self):
        self.request('/api/public-algae/save',self.body());old=self.server.workspace.public_algae.current()
        brief=self.store.current()['state']['brief'];brief['minimum_growth_ratio']=0
        self.store.apply(self.store.current()['hash'],{'type':'edit','payload':brief})
        v=self.request('/api/state')[1]['public_algae'];self.assertEqual(v['context_status'],'needs_review');self.assertEqual(v['current'],old)

    def test_failed_public_sources_block_only_public_case_without_synthetic_substitution(self):
        with patch.object(public_algae,'catalog',side_effect=ValueError('Do not leak internal detail')):
            self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        v=self.request('/api/state')[1];self.assertIsNone(v['public_algae']);self.assertIsNotNone(v['molecular'])
        self.assertNotIn('internal detail',v['public_algae_error']);self.assertEqual(v['current'],self.store.current())
        self.assertEqual(self.request('/public-algae-source/refseq_XM_001700501.2.gb')[0],400)

    def test_completed_muse_cycle_remains_immutable_and_public_review_session_only(self):
        c=CompletedCycle(fixture(self.folder/'cycle',synthetic=True));before=c.export_review()
        self.server=workspace_server.make_server(c,server_factory=MemoryServer);self.token=self.request('/api/session')[1]['token']
        self.assertEqual(self.request('/api/public-algae/save',self.body())[0],200)
        self.assertEqual(self.server.workspace.public_algae.view(c.current())['storage'],'session_only_export_to_keep')
        self.assertEqual(c.export_review(),before);self.assertEqual(self.request('/api/check/run',{'expected_hash':c.current()['hash']})[0],403)


if __name__=='__main__':unittest.main()
