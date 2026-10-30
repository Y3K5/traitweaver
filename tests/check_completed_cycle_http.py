"""Loopback-only integration for the saved cycle view; synthetic fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traitweaver import muse_boundary as muse, study
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.workspace_server import make_server
from test_completed_cycle import fixture


def local_only(event,args):
    if event in ('socket.connect','socket.bind') and args[1][0]!='127.0.0.1':
        raise AssertionError('External network forbidden')
sys.addaudithook(local_only)
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='traitweaver-synthetic-cycle-http-') as folder:
    root=fixture(Path(folder)/'packet')
    before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    with patch.object(muse,'send_approved',side_effect=AssertionError('Provider call forbidden')),patch.object(study,'coverage',side_effect=AssertionError('Tool dispatch forbidden')),patch.object(study,'contrasts',side_effect=AssertionError('Tool dispatch forbidden')):
        record=CompletedCycle(root);server=make_server(record)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None,headers=None):
            h={'X-Traitweaver-Client':'workspace',**(headers or {})}
            if body is not None:h.update({'Content-Type':'application/json','Origin':base,'X-Traitweaver-Token':token})
            req=urllib.request.Request(base+path,data=None if body is None else study.canonical(body).encode(),headers=h)
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,response.read(),response.headers
            except urllib.error.HTTPError as error:return error.code,error.read(),error.headers
        try:
            code,raw,headers=request('/api/session');token=json.loads(raw)['token']
            check('session is local and cookie-free',code==200 and 'Set-Cookie' not in headers)
            code,raw,headers=request('/api/state');state=json.loads(raw)
            check('saved revision and read-only usage are joined',code==200 and state['read_only'] and state['current']['revision']==4 and state['completed_cycle']['estimated_cost_usd']=='0.000590')
            check('provider transport disabled',not state['live_enabled'] and not state['baseten_live_enabled'])
            for path in ('/api/check/run','/api/reassess','/api/study/revise','/api/restore','/api/muse/send','/api/muse/synthetic'):
                check('review refuses mutation '+path,request(path,{'expected_hash':state['current']['hash']})[0]==403)
            code,raw,headers=request('/api/cycle-review.json');package=json.loads(raw)
            check('local download preserves package and usage',code==200 and package['summary']['total_reasoning_tokens']==0 and len(package['study_package']['revisions'])==4 and 'attachment' in headers['Content-Disposition'])
            code,raw,headers=request('/api/export.md')
            check('readable export includes saved usage',code==200 and b'Estimated token cost: $0.000590' in raw)
            check('study export still works',request('/api/export.json')[0]==200)
            for path in ('/','/workspace.js','/completed-cycle-ui.js','/workspace.css'):
                check('existing shell serves '+path,request(path)[0]==200)
            check('browser CSP permits only local connections',"connect-src 'self'" in headers['Content-Security-Policy'])
            check('cross-origin access refused',request('/api/state',headers={'Origin':'https://outside.invalid'})[0]==403)
            check('local control file inaccessible',request('/LOCAL_CONTROL.json')[0]==404)
        finally:
            server.shutdown();server.server_close();thread.join(5);record.close()
        check('all source files remain unchanged',before=={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()})
        check('reopen keeps same saved revision and cost',CompletedCycle(root).current()==record.current())
print(json.dumps({'status':'passed','checks':len(checks),'scenarios':checks,'external_connections':0},indent=2))
