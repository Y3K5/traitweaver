"""Exact manifest checks in a clone without reading Git metadata or secrets."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('handoff_check',ROOT/'tools/verify_handoff.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class HandoffVerifierTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='traitweaver-manifest-test-');self.addCleanup(t.cleanup);self.root=Path(t.name)
        p=self.root/'README.md';p.write_text('Synthetic verifier input\n')
        manifest={'files':[{'path':'README.md','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}]}
        (self.root/'HANDOFF_MANIFEST.json').write_text(json.dumps(manifest))
        p=patch.object(checker,'ROOT',self.root);p.start();self.addCleanup(p.stop)

    def test_root_git_directory_is_never_traversed_or_opened(self):
        g=self.root/'.git';g.mkdir();(g/'config').write_text('Synthetic unread metadata')
        original=Path.read_bytes
        def read(p):
            if g in p.parents:raise AssertionError('Git metadata was read')
            return original(p)
        with patch.object(Path,'read_bytes',read):self.assertEqual(checker.verify()['files'],2)

    def test_root_worktree_git_pointer_is_not_read(self):
        p=self.root/'.git';p.write_text('Synthetic unread pointer')
        original=Path.read_bytes
        def read(path):
            if path==p:raise AssertionError('Git pointer was read')
            return original(path)
        with patch.object(Path,'read_bytes',read):self.assertEqual(checker.verify()['files'],2)

    def test_changed_bytes_and_unknown_files_still_fail(self):
        (self.root/'README.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'checksum'):checker.verify()
        (self.root/'unexpected').write_text('Synthetic extra')
        with self.assertRaisesRegex(ValueError,'membership'):checker.verify()

    def test_secret_named_directory_is_refused_before_content_read(self):
        p=self.root/'secrets';p.mkdir();(p/'not-read').write_text('Synthetic unread fixture')
        with self.assertRaisesRegex(ValueError,'Secret-named'):checker.verify()

    def test_embedded_git_and_symlinks_are_not_silently_ignored(self):
        p=self.root/'nested';p.mkdir();(p/'.git').mkdir()
        with self.assertRaisesRegex(ValueError,'Embedded Git'):checker.verify()
        (p/'.git').rmdir();(p/'alias').symlink_to(self.root/'README.md')
        with self.assertRaisesRegex(ValueError,'Symlinks'):checker.verify()


if __name__=='__main__':unittest.main()
