"""Standalone loopback integration checks, separate from socket-prohibited suites."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traitweaver import study
from traitweaver.study_store import Store
from traitweaver.workspace_server import make_server


def local_only(event,args):
    if event == 'socket.connect' and args[1][0] != '127.0.0.1':
        raise RuntimeError('Integration test refuses external connections')
    if event == 'socket.bind' and args[1][0] != '127.0.0.1':
        raise RuntimeError('Integration test refuses external binding')


sys.addaudithook(local_only)
checks=[]
with tempfile.TemporaryDirectory(prefix='traitweaver-http-test-') as folder:
    store=Store(Path(folder)/'data');server=make_server(store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def request(path,body=None,headers=None):
        h={'X-Traitweaver-Client':'workspace',**(headers or {})}
        if body is not None:
            h={'Content-Type':'application/json','Origin':base,'X-Traitweaver-Token':token,**h}
        req=urllib.request.Request(base+path,data=None if body is None else study.canonical(body).encode(),headers=h)
        try:
            with urllib.request.urlopen(req,timeout=5) as response:return response.status,response.read(),response.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def check(name,condition):
        assert condition,name
        checks.append(name)
    try:
        code,raw,headers=request('/api/session');token=json.loads(raw)['token']
        check('session acquired without cookie or external service',code==200 and 'Set-Cookie' not in headers)
        check('wrong host refused',request('/api/state',headers={'Host':'evil.invalid'})[0]==403)
        check('cross-origin read refused',request('/api/state',headers={'Origin':'https://evil.invalid'})[0]==403)
        check('missing client header refused',request('/api/state',headers={'X-Traitweaver-Client':''})[0]==403)
        current=json.loads(request('/api/state')[1])['current']
        action={'expected_hash':current['hash'],'check':'endpoint_coverage','arguments':{}}
        check('missing session token refused',request('/api/decision/prepare',action,{'X-Traitweaver-Token':''})[0]==403)
        check('cross-origin mutation refused',request('/api/decision/prepare',action,{'Origin':'https://evil.invalid'})[0]==403)
        check('valid decision committed before execution',request('/api/decision/prepare',action)[0]==200 and store.current()['state']['cycles'][0]['result'] is None)
        check('stale mutation refused',request('/api/decision/prepare',action)[0]==409)
        check('registered local check executed',request('/api/check/run',{'expected_hash':store.current()['hash']})[0]==200)
        check('separate reassessment saved',request('/api/reassess',{'expected_hash':store.current()['hash']})[0]==200)
        saved_state=store.current()['state'];code,raw,headers=request('/api/export.json');saved=raw.decode()
        check('JSON download is a valid package',code==200 and 'attachment' in headers['Content-Disposition'] and json.loads(saved)['revisions'][-1]['state']==saved_state)
        check('readable download retains source roles',b'published_observation' in request('/api/export.md')[1])
        brief=deepcopy(saved_state['brief']);brief['context_notes']='Changed proposed context'
        check('guided edit creates successor revision',request('/api/study/revise',{'expected_hash':store.current()['hash'],'brief':brief})[0]==200)
        check('context invalidates prior assessment',store.current()['state']['cycles'][0]['applicability']=='needs_reassessment')
        check('reopen restores without overwriting earlier history',request('/api/restore',{'expected_hash':store.current()['hash'],'package_json':saved})[0]==200 and store.current()['state']==saved_state)
        bad=json.loads(saved);bad['revisions'][-1]['state']['recovery_winner']='invented'
        check('corrupt package rejected',request('/api/restore',{'expected_hash':store.current()['hash'],'package_json':study.canonical(bad)})[0]==400)
        check('malformed and duplicate-key packages rejected',request('/api/restore',{'expected_hash':store.current()['hash'],'package_json':'{"x":1,"x":2}'})[0]==400)
        for path in ['/','/workspace.js','/workspace.css','/assets/brand.css','/assets/fonts/Manrope-Variable.ttf','/gfp']:
            check('portable resource '+path,request(path)[0]==200)
        check('traversal cannot read repository files',request('/../examples/study_case.json')[0]==404)
        check('unknown actions rejected',request('/api/shell',{'expected_hash':store.current()['hash']})[0]==404)
        check('prepared Muse request sends nothing',json.loads(request('/api/muse/prepare',{'expected_hash':store.current()['hash'],'phase':'selection'})[1])['status']=='not_sent')
        check('synthetic Muse selection explicitly accepted',request('/api/muse/synthetic',{'expected_hash':store.current()['hash'],'phase':'selection'})[0]==200 and store.current()['state']['cycles'][-1]['decision']['provider_receipt']['provenance']=='synthetic_fixture')
        check('live-send route absent',request('/api/muse/send',{'expected_hash':store.current()['hash']})[0]==404)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5);store.close()
print(json.dumps({'status':'passed','checks':len(checks),'scenarios':checks,'external_connections':0},indent=2))
