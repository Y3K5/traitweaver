"""Source-bound completed documentation checks; no model or biological execution."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import os
import hashlib
import threading
import uuid

from traitweaver import assistant_evaluation as evidence,study
from traitweaver.study_store import Conflict,screen_export

SCHEMA='traitweaver.completed_steps_package.v1'
REVISION='traitweaver.completed_steps_revision.v1'
LIMIT='Completion means a local metadata check on explicitly synthetic records. It does not establish replication, analysis readiness, expression results, gene editing or experimental success. No model decides completion.'
CASES=('RNA_BEFORE','RNA_AFTER')
ACTION='RNA_RECONCILE'
CHECK='rna_manifest_integrity'
MAX_REVISIONS=96
MAX_BYTES=512*1024
_SOURCE_CACHE=None


def source(case_id):
    global _SOURCE_CACHE
    if case_id not in CASES:raise ValueError('Unregistered completed-step source')
    if evidence.CATALOG.is_symlink() or hashlib.sha256(evidence.CATALOG.read_bytes()).hexdigest()!=evidence.CATALOG_SHA256:raise ValueError('Completion source snapshot changed')
    if _SOURCE_CACHE is None:
        checked=evidence.catalog()
        _SOURCE_CACHE={c['id']:{'case_id':c['id'],'input_kind':'clearly_synthetic','records':c['records'],'catalog_sha256':evidence.CATALOG_SHA256} for c in checked['cases'] if c['id'] in CASES}
    return deepcopy(_SOURCE_CACHE[case_id])


def context_hash(case_id):return study.digest(source(case_id))


def manifest_result(case_id):
    records={r['id']:r['value'] for r in source(case_id)['records']};sheet=records['RNA_SAMPLES']
    labels=sheet['labels'];layouts=sheet['library_layouts']
    duplicates=sorted({v for v in labels if labels.count(v)>1})
    conflicts=sorted({label for label in labels if len({layout for label2,layout in zip(labels,layouts) if label2==label})>1})
    valid=bool(labels) and len(labels)==len(layouts) and not duplicates and not conflicts and all(v in ('paired','single') for v in layouts)
    return {'check':CHECK,'status':'passed' if valid else 'blocked','unique_labels':not duplicates,'duplicates':duplicates,'layout_conflicts':conflicts,
            'source_context_sha256':context_hash(case_id),'record_ids':['RNA_SAMPLES'],
            'qualification':'Actual deterministic metadata validation of synthetic input only; no independent-unit, read, analysis or biological validation.'}


def run_check(case_id):return manifest_result(case_id)


def initial():return {'source_case_id':'RNA_AFTER','attempts':[]}


def transition(state,action,recorded_result=None):
    state=deepcopy(state);study.fields(action,('type','payload'));kind=action['type'];data=action['payload']
    if kind=='source':
        study.fields(data,('case_id',));source(data['case_id'])
        if data['case_id']==state['source_case_id']:raise ValueError('Source already selected')
        state['source_case_id']=data['case_id']
    elif kind=='decide':
        study.fields(data,('action_id',))
        if data['action_id']!=ACTION:raise ValueError('Only the registered metadata check may be executed')
        ctx=context_hash(state['source_case_id'])
        if any(a['source_context_sha256']==ctx for a in state['attempts']):raise ValueError('This source revision already has a decision/receipt; no duplicate check')
        state['attempts'].append({'action_id':ACTION,'check':CHECK,'source_case_id':state['source_case_id'],'source_context_sha256':ctx,
           'purpose':'Check supplied sample-label uniqueness and per-label library-layout consistency before marking reconciliation complete.','result':None})
    elif kind=='result':
        study.fields(data,())
        if not state['attempts'] or state['attempts'][-1]['result'] is not None:raise ValueError('Missing pre-result decision')
        a=state['attempts'][-1]
        if a['source_context_sha256']!=context_hash(state['source_case_id']):raise ValueError('Source changed before check result')
        expected=manifest_result(state['source_case_id'])
        failure={'check':CHECK,'status':'failed','source_context_sha256':context_hash(state['source_case_id']),'record_ids':['RNA_SAMPLES'],'qualification':'Local check failed; no completion claim.'}
        if recorded_result!=expected and recorded_result!=failure:raise ValueError('Unbound or altered completion receipt')
        a['result']=deepcopy(recorded_result)
    else:raise ValueError('Unknown tracking action; no arbitrary tool or model completion')
    return state


def status(state):
    ctx=context_hash(state['source_case_id']);current=[a for a in state['attempts'] if a['source_context_sha256']==ctx]
    if current:
        last=current[-1]
        if last['result'] is None:return 'in_progress'
        return {'passed':'completed','blocked':'blocked','failed':'failed'}[last['result']['status']]
    return 'needs_reassessment' if state['attempts'] else 'not_started'


def project(state):
    ctx=context_hash(state['source_case_id']);current=[a for a in state['attempts'] if a['source_context_sha256']==ctx]
    last=current[-1] if current else None
    return {'source_context_sha256':ctx,'input_kind':'clearly_synthetic','steps':[
       {'action_id':ACTION,'status':status(state),'check':CHECK,'scope':'Sample labels and per-label layout consistency only',
        'completion_receipt':deepcopy(last['result']) if last and last['result'] else None},
       {'action_id':'RNA_DESIGN_CHECK','status':'unresolved','scope':'Independent unit, contrast and batch require researcher decisions; no completion receipt.'},
       {'action_id':'RNA_LEDGER','status':'unresolved','scope':'Document remaining metadata gaps; no completion receipt.'},
       {'action_id':'RNA_CHECKLIST','status':'unresolved','scope':'Future software/documentation validation checklist; not executed.'}],
       'limit':LIMIT}


def package(history):return {'schema_version':SCHEMA,'catalog_sha256':evidence.CATALOG_SHA256,'sources':[source(c) for c in CASES],'revisions':deepcopy(history),'limit':LIMIT}


def _validate_package(value):
    study.fields(value,('schema_version','catalog_sha256','sources','revisions','limit'))
    if value['schema_version']!=SCHEMA or value['catalog_sha256']!=evidence.CATALOG_SHA256 or value['sources']!=[source(c) for c in CASES] or value['limit']!=LIMIT:raise ValueError('Changed completion source or version')
    revisions=value['revisions']
    if not isinstance(revisions,list) or not 1<=len(revisions)<=MAX_REVISIONS or len(study.canonical(value).encode())>MAX_BYTES:raise ValueError('Completion history bounds exceeded')
    state=initial();previous=None
    for number,r in enumerate(revisions,1):
        study.fields(r,('schema_version','revision','parent_hash','saved_utc','action','state','hash'))
        if r['schema_version']!=REVISION or type(r['revision']) is not int or r['revision']!=number or r['parent_hash']!=previous:raise ValueError('Broken completion history chain')
        if datetime.fromisoformat(r['saved_utc']).tzinfo is None:raise ValueError('Completion timestamp needs timezone')
        if number==1:
            if r['action']!={'type':'create','payload':{}}:raise ValueError('History needs creation record')
        else:
            receipt=r['state']['attempts'][-1]['result'] if r['action']['type']=='result' else None
            state=transition(state,r['action'],receipt)
        if r['state']!=state or r['hash']!=study.digest({k:v for k,v in r.items() if k!='hash'}):raise ValueError('Completion history/receipt changed')
        previous=r['hash']
    screen_export(value);evidence.screen(value);return deepcopy(revisions)


def validate_package(value):
    try:return _validate_package(value)
    except (ValueError,KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
        raise ValueError('Malformed completion history; existing work preserved') from None


class Journal:
    def __init__(self,directory=None):
        self.root=Path(directory) if directory is not None else None;self.history=[];self.read_only=False;self.mutex=threading.RLock()
        if self.root is not None:
            if self.root.is_symlink() or study.APP_ROOT==self.root.resolve() or study.APP_ROOT in self.root.resolve().parents:raise ValueError('Explicit external completion storage required')
            if self.root.exists():
                revisions=sorted(self.root.glob('revision-*.json'))
                if len(revisions)>MAX_REVISIONS:raise ValueError('Completion history too large')
                for p in revisions:
                    if p.is_symlink() or p.name!='revision-'+str(len(self.history)+1).zfill(6)+'.json' or p.stat().st_size>MAX_BYTES:raise ValueError('Unsafe completion revision')
                    self.history.append(study.decode(p.read_bytes()))
                if self.history:validate_package(package(self.history))
        if not self.history:
            root=self.root;self.root=None
            self._append({'type':'create','payload':{}},initial());self.root=root

    def current(self):return deepcopy(self.history[-1])

    def _append(self,action,state):
        r={'schema_version':REVISION,'revision':len(self.history)+1,'parent_hash':self.history[-1]['hash'] if self.history else None,
           'saved_utc':datetime.now(timezone.utc).isoformat(),'action':deepcopy(action),'state':deepcopy(state)}
        r['hash']=study.digest(r);validate_package(package(self.history+[r]))
        if self.root is not None:
            if self.root.is_symlink():raise ValueError('Unsafe completion storage')
            self.root.mkdir(mode=0o700,exist_ok=True)
            # Initial state stays memory-only until the first deliberate edit.
            pending_records=[self.history[0],r] if len(self.history)==1 and not any(self.root.glob('revision-*.json')) else [r]
            for record in pending_records:
                pending=self.root/('.pending-'+uuid.uuid4().hex);dest=self.root/('revision-'+str(record['revision']).zfill(6)+'.json')
                try:
                    with pending.open('xb') as f:
                        os.chmod(pending,0o600);f.write((study.canonical(record)+'\n').encode());f.flush();os.fsync(f.fileno())
                    os.link(pending,dest)
                    fd=os.open(self.root,os.O_RDONLY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                finally:pending.unlink(missing_ok=True)
        self.history.append(r);return self.current()

    def apply(self,expected,action):
        with self.mutex:
            if self.read_only:raise ValueError('Imported completion review is read-only')
            if expected!=self.current()['hash']:raise Conflict('Completion revision changed; refresh before editing')
            if len(self.history)>=MAX_REVISIONS:raise ValueError('Completion revision limit reached')
            if action['type']=='check':
                study.fields(action,('type','payload'));study.fields(action['payload'],())
                if len(self.history)>MAX_REVISIONS-2:raise ValueError('Need room for decision and result')
                state=transition(self.current()['state'],{'type':'decide','payload':{'action_id':ACTION}})
                self._append({'type':'decide','payload':{'action_id':ACTION}},state)
                try:result=run_check(state['source_case_id'])
                except Exception:result={'check':CHECK,'status':'failed','source_context_sha256':context_hash(state['source_case_id']),'record_ids':['RNA_SAMPLES'],'qualification':'Local check failed; no completion claim.'}
                return self._append({'type':'result','payload':{}},transition(state,{'type':'result','payload':{}},result))
            return self._append(action,transition(self.current()['state'],action))

    def export(self):
        value=package(self.history);validate_package(value);return value

    @classmethod
    def from_package(cls,value):
        history=validate_package(value);j=cls.__new__(cls);j.root=None;j.history=history;j.read_only=True;j.mutex=threading.RLock();return j

    def view(self):
        current=self.current()
        return {'current':current,'source':source(current['state']['source_case_id']),'projection':project(current['state']),
                'history':[{'revision':r['revision'],'hash':r['hash'],'action':r['action']['type']} for r in self.history],
                'read_only':self.read_only,'storage':'imported_read_only' if self.read_only else 'external_data_directory' if self.root else 'session_only_export_to_preserve',
                'cases':[{'id':'RNA_AFTER','label':'Synthetic reconciled manifest'},{'id':'RNA_BEFORE','label':'Synthetic conflicting manifest'}],'live_enabled':False,'limit':LIMIT}

    def readable(self):return 'Completed-step tracking\n'+LIMIT+'\n'+study.canonical(self.view())+'\n'
