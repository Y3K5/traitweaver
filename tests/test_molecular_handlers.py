"""Actual handler dispatch using memory buffers; no HTTP/API or socket calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import molecular, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
from test_completed_cycle import fixture
from test_review_handlers import MemoryServer, MemoryConnection


class MolecularHandlerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-molecular-handler-');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.guard=patch('socket.socket',side_effect=AssertionError('No sockets'));self.guard.start();self.addCleanup(self.guard.stop)
        self.store=Store(self.folder/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def request(self,path,body=None,headers=None):
        h={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','X-Traitweaver-Client':'workspace'}
        if body is not None:h.update({'Content-Type':'application/json','X-Traitweaver-Token':self.token})
        h.update(headers or {});raw=b'' if body is None else study.canonical(body).encode();h['Content-Length']=str(len(raw))
        wire=(('GET' if body is None else 'POST')+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in h.items())+'\r\n').encode()+raw
        conn=MemoryConnection(wire);self.server.RequestHandlerClass(conn,('127.0.0.1',1000),self.server)
        head,payload=bytes(conn.response).split(b'\r\n\r\n',1)
        return int(head.split(b' ')[1]),(payload.decode() if b'text/plain' in head else json.loads(payload))

    def body(self,**changes):
        j=self.server.workspace.molecular
        s=molecular.initial_selection();s['transcript_id']='DEMO-TX-A.1'
        body={'expected_hash':self.server.workspace.active.current()['hash'],'molecular_hash':j.current()['hash'],'selection':s,'stage':'identity','note':'Synthetic checkpoint'}
        body.update(changes);return body

    def test_save_is_a_separate_durable_journal_and_never_an_algae_revision(self):
        before=self.store.export();self.assertEqual(self.request('/api/molecular/save',self.body())[0],200)
        self.assertEqual(self.store.export(),before);self.assertEqual(len(self.store.history),1)
        self.assertEqual(self.request('/api/state')[1]['molecular']['current']['revision'],1)
        self.assertEqual(self.request('/api/state')[1]['molecular']['storage'],'external_data_directory')
        self.assertTrue((self.store.root/'molecular-review/review-000001.json').is_file())

    def test_both_study_and_molecular_revision_identity_are_required(self):
        old=self.body();self.request('/api/molecular/save',old)
        self.assertEqual(self.request('/api/molecular/save',old)[0],409)
        self.assertEqual(self.request('/api/molecular/save',self.body(expected_hash='f'*64))[0],409)
        self.assertEqual(len(self.server.workspace.molecular.history),1)

    def test_origin_host_session_and_input_schema_are_enforced(self):
        for h in [{'Origin':'https://outside.invalid'},{'Host':'outside.invalid'},{'X-Traitweaver-Token':''}]:
            self.assertEqual(self.request('/api/molecular/save',self.body(),h)[0],403)
        b=self.body();b['arbitrary_script']='not executable';self.assertEqual(self.request('/api/molecular/save',b)[0],400)
        self.assertEqual(self.server.workspace.molecular.current()['revision'],0)

    def test_context_edit_marks_review_without_removing_either_history(self):
        self.request('/api/molecular/save',self.body());old=self.server.workspace.molecular.current()
        brief=self.store.current()['state']['brief'];brief['minimum_growth_ratio']=0
        self.store.apply(self.store.current()['hash'],{'type':'edit','payload':brief})
        data=self.request('/api/state')[1]
        self.assertEqual(data['molecular']['context_status'],'needs_review')
        self.assertEqual(data['molecular']['current'],old);self.assertEqual(data['current']['state']['brief']['minimum_growth_ratio'],0)

    def test_export_reopen_is_readonly_and_preserves_original_molecular_disk(self):
        self.request('/api/molecular/save',self.body());saved=self.server.workspace.molecular.current()
        p=self.request('/api/molecular/export.json')[1]
        code,brief=self.request('/api/molecular/export.txt');self.assertEqual(code,200);self.assertIn('Biological target ready: No',brief);self.assertIn('DEMO-TX-A.1',brief)
        request={'expected_hash':self.store.current()['hash'],'molecular_hash':saved['hash'],'package_json':study.canonical(p)}
        self.assertEqual(self.request('/api/molecular/open',request)[0],200)
        self.assertEqual(self.request('/api/molecular/export.json')[1],p)
        self.assertTrue(self.request('/api/state')[1]['molecular']['read_only'])
        self.assertEqual(self.request('/api/molecular/save',self.body())[0],400)
        self.assertEqual(study.decode((self.store.root/'molecular-review/review-000001.json').read_bytes()),saved)

    def test_corrupt_or_cross_source_import_leaves_current_review_intact(self):
        self.request('/api/molecular/save',self.body());j=self.server.workspace.molecular
        for text in ['{bad',study.canonical({'schema_version':'unknown'})]:
            b={'expected_hash':self.store.current()['hash'],'molecular_hash':j.current()['hash'],'package_json':text}
            self.assertEqual(self.request('/api/molecular/open',b)[0],400)
            self.assertIs(self.server.workspace.molecular,j)

    def test_completed_muse_cycle_is_immutable_while_sandbox_is_session_only(self):
        cycle=CompletedCycle(fixture(self.folder/'cycle',synthetic=True));before=cycle.export_review()
        self.server=workspace_server.make_server(cycle,server_factory=MemoryServer);self.token=self.request('/api/session')[1]['token']
        self.assertEqual(self.request('/api/molecular/save',self.body())[0],200)
        self.assertEqual(self.request('/api/state')[1]['molecular']['storage'],'session_only_export_to_keep')
        self.assertEqual(cycle.export_review(),before)
        self.assertEqual(self.request('/api/check/run',{'expected_hash':cycle.current()['hash']})[0],403)
        self.assertEqual(len(cycle.history),4)

    def test_bad_molecular_fixture_blocks_only_molecular_views(self):
        with patch.object(molecular,'catalog',side_effect=ValueError('Unsafe synthetic detail')):
            self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        code,data=self.request('/api/state');self.assertEqual(code,200)
        self.assertIsNone(data['molecular']);self.assertNotIn('Unsafe synthetic detail',data['molecular_error'])
        self.assertEqual(data['current'],self.store.current())
        self.assertEqual(self.request('/api/molecular/export.json')[0],400)

    def test_empty_export_and_unknown_molecular_action_do_not_create_a_record(self):
        self.assertEqual(self.request('/api/molecular/export.json')[0],400)
        self.assertEqual(self.request('/api/molecular/execute',self.body())[0],404)
        self.assertEqual(self.server.workspace.molecular.current()['revision'],0)


if __name__=='__main__':unittest.main()
