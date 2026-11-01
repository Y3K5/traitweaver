"""Revision-bound exports through actual memory handlers, with sockets blocked."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import intelligence, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
import test_molecular_handlers as handlers
from test_review_handlers import MemoryServer


class DataFlowExportTests(unittest.TestCase):
    request = handlers.MolecularHandlerTests.request

    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        guard = patch('socket.socket', side_effect=AssertionError('No sockets'))
        guard.start(); self.addCleanup(guard.stop)
        self.store = Store(Path(t.name)/'study'); self.addCleanup(self.store.close)
        self.server = workspace_server.make_server(self.store, server_factory=MemoryServer)
        self.token = self.request('/api/session')[1]['token']

    def header(self, value):
        return {'X-Traitweaver-Expected-Revision': value}

    def test_saved_study_json_is_pinned_without_mutation(self):
        before = self.store.export()
        code, package = self.request('/api/export.json', headers=self.header(self.store.current()['hash']))
        self.assertEqual(code, 200); self.assertEqual(package, before)
        self.assertEqual(self.store.export(), before)

    def test_stale_identity_blocks_all_export_formats(self):
        paths = ['/api/export.json', '/api/export.md']
        for kind in ('intelligence', 'public-algae', 'molecular'):
            paths.extend('/api/'+kind+'/export.'+ext for ext in ('json', 'txt'))
        for path in paths:
            with self.subTest(path=path):
                code, error = self.request(path, headers=self.header('f'*64))
                self.assertEqual(code, 409); self.assertIn('Refresh Data flow', error['error'])
                self.assertNotIn('revisions', error)

    def test_no_checkpoint_does_not_create_export_or_history(self):
        for kind in ('intelligence', 'public_algae', 'molecular'):
            journal = getattr(self.server.workspace, kind)
            self.assertEqual(journal.current()['revision'], 0)
            code, _ = self.request('/api/'+kind.replace('_','-')+'/export.json')
            self.assertEqual(code, 400); self.assertEqual(journal.current()['revision'], 0)

    def test_saved_intelligence_uses_its_own_identity_and_readable_format(self):
        j = self.server.workspace.intelligence
        body = {'expected_hash': self.store.current()['hash'], 'intelligence_hash': j.current()['hash'], 'scope': intelligence.initial_scope()}
        self.assertEqual(self.request('/api/intelligence/revise', body)[0], 200)
        for ext in ('json', 'txt'):
            path = '/api/intelligence/export.'+ext
            self.assertEqual(self.request(path, headers=self.header(j.current()['hash']))[0], 200)
            self.assertEqual(self.request(path, headers=self.header(self.store.current()['hash']))[0], 409)
        self.assertEqual(len(j.history), 1); self.assertEqual(len(self.store.history), 1)

    def test_header_remains_optional_for_existing_export_clients(self):
        self.assertEqual(self.request('/api/export.json')[0], 200)
        self.assertEqual(self.request('/api/state', headers=self.header('stale'))[0], 200)

    def test_completed_usage_package_has_same_revision_guard(self):
        cycle = CompletedCycle.from_file('data/synthetic-cycle/REVIEW_PACKAGE.json')
        self.server = workspace_server.make_server(cycle, server_factory=MemoryServer)
        before = cycle.export_review()
        code, package = self.request('/api/cycle-review.json', headers=self.header(cycle.current()['hash']))
        self.assertEqual(code, 200); self.assertEqual(package, before)
        self.assertEqual(self.request('/api/cycle-review.json', headers=self.header('stale'))[0], 409)
        self.assertEqual(cycle.export_review(), before)

    def test_unavailable_review_fails_safely(self):
        self.server.workspace.intelligence = None
        code, error = self.request('/api/intelligence/export.json', headers=self.header('stale'))
        self.assertEqual(code, 400); self.assertNotIn(str(self.store.root), str(error))


if __name__ == '__main__': unittest.main()
