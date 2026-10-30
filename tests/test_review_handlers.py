"""Actual HTTP handler parsing against in-memory sockets; no server or API call."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import muse_boundary, study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store
from test_completed_cycle import fixture, write


class MemoryServer:
    def __init__(self,address,handler):
        self.server_port=8765;self.RequestHandlerClass=handler
    def serve_forever(self):raise KeyboardInterrupt()
    def server_close(self):pass


class MemoryConnection:
    def __init__(self,raw):self.raw=raw;self.response=bytearray()
    def makefile(self,*args):return io.BytesIO(self.raw)
    def sendall(self,value):self.response.extend(value)


class ReviewHandlerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-offline-review-route-');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.review=CompletedCycle(fixture(self.folder/'packet',synthetic=True)).export_review()
        self.store=Store(self.folder/'editable');self.addCleanup(self.store.close)
        guard=patch('socket.socket',side_effect=AssertionError('No sockets allowed'));guard.start();self.addCleanup(guard.stop)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def request(self,path,body=None,headers=None):
        head={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','X-Traitweaver-Client':'workspace'}
        if body is not None:head.update({'Content-Type':'application/json','X-Traitweaver-Token':self.token})
        head.update(headers or {})
        raw=b'' if body is None else study.canonical(body).encode()
        head['Content-Length']=str(len(raw))
        wire=(('GET' if body is None else 'POST')+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in head.items())+'\r\n').encode()+raw
        connection=MemoryConnection(wire)
        self.server.RequestHandlerClass(connection,('127.0.0.1',1000),self.server)
        response=bytes(connection.response);header,payload=response.split(b'\r\n\r\n',1)
        return int(header.split(b' ',2)[1]),json.loads(payload)

    def open_review(self,**changes):
        body={'expected_hash':self.server.workspace.active.current()['hash'],'review_json':study.canonical(self.review)}
        body.update(changes);return self.request('/api/cycle-review/open',body)

    def test_open_and_reexport_preserve_usage_without_mutating_original_study(self):
        before=self.store.current()
        with patch.object(muse_boundary,'send_approved',side_effect=AssertionError('No model')),patch.object(study,'coverage',side_effect=AssertionError('No tool')):
            code,_=self.open_review();self.assertEqual(code,200)
            code,snapshot=self.request('/api/state')
            self.assertEqual(code,200);self.assertTrue(snapshot['read_only'])
            self.assertTrue(snapshot['completed_cycle']['synthetic'])
            self.assertEqual(snapshot['completed_cycle']['estimated_cost_usd'],'0.000590')
            self.assertEqual(snapshot['current']['revision'],4)
            self.assertEqual(self.request('/api/cycle-review.json')[1],self.review)
        self.assertEqual(self.store.current(),before);self.assertEqual(len(self.store.history),1)

    def test_reopened_view_blocks_edits_reruns_and_provider_routes(self):
        self.open_review();current=self.server.workspace.active.current()
        for path in ('/api/study/revise','/api/check/run','/api/reassess','/api/muse/send','/api/muse/synthetic','/api/restore'):
            self.assertEqual(self.request(path,{'expected_hash':current['hash']})[0],403)
        self.assertEqual(self.server.workspace.active.current(),current)

    def test_invalid_or_stale_review_leaves_current_view_unchanged(self):
        before=self.store.current()
        self.assertEqual(self.open_review(review_json='{bad')[0],400)
        self.assertEqual(self.open_review(expected_hash='0'*64)[0],409)
        self.assertIs(self.server.workspace.active,self.store);self.assertEqual(before,self.store.current())

    def test_open_requires_current_origin_and_session(self):
        body={'expected_hash':self.store.current()['hash'],'review_json':study.canonical(self.review)}
        self.assertEqual(self.request('/api/cycle-review/open',body,{'X-Traitweaver-Token':''})[0],403)
        self.assertEqual(self.request('/api/cycle-review/open',body,{'Origin':'https://outside.invalid'})[0],403)
        self.assertEqual(self.request('/api/cycle-review/open',body,{'Host':'outside.invalid'})[0],403)

    def test_reopened_review_can_reopen_again_without_extra_revision(self):
        self.open_review();before=self.server.workspace.active.current()
        self.assertEqual(self.open_review()[0],200)
        self.assertEqual(self.server.workspace.active.current(),before)
        self.assertEqual(len(self.server.workspace.active.history),4)

    def test_new_file_launcher_reads_export_without_a_real_server(self):
        filename=self.folder/'review.json';write(filename,self.review);before=filename.read_bytes()
        output=io.StringIO()
        def factory(store,port):
            self.assertIsInstance(store,CompletedCycle)
            self.assertEqual(store.export_review(),self.review)
            return MemoryServer(None,None)
        with patch.object(workspace_server,'make_server',factory),redirect_stdout(output):
            self.assertEqual(workspace_server.main(['--completed-cycle-file',str(filename)]),0)
        self.assertIn('/#muse-cycle',output.getvalue());self.assertEqual(filename.read_bytes(),before)


if __name__=='__main__':unittest.main()
