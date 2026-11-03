"""Immutable, separate molecular intelligence revisions; enclosing workspace lock."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import uuid

from traitweaver import evidence_map, intelligence, study
from traitweaver.study_store import Conflict, MAX_BYTES, screen_export

MAX_REVISIONS=128


def package(records,bundle):
    return {'schema_version':'traitweaver.intelligence_package.v1','catalog':deepcopy(bundle),'revisions':deepcopy(records),'limit':intelligence.LIMIT}


def validate_package(value,bundle):
    try:
        study.fields(value,('schema_version','catalog','revisions','limit'))
        if value['schema_version']!='traitweaver.intelligence_package.v1' or study.canonical(value['catalog'])!=study.canonical(bundle) or value['limit']!=intelligence.LIMIT:raise ValueError('Intelligence source identity or version changed')
        records=value['revisions']
        if not isinstance(records,list) or not 1<=len(records)<=MAX_REVISIONS or len(study.canonical(value).encode())>MAX_BYTES:raise ValueError('Intelligence package exceeds its bounds')
        previous=None;state=intelligence.initial()
        for i,r in enumerate(records,1):
            study.fields(r,('schema_version','catalog_sha256','revision','parent_hash','saved_utc','action','state','hash'))
            if r['schema_version']!='traitweaver.intelligence_revision.v1' or r['catalog_sha256']!=study.digest(bundle) or type(r['revision']) is not int or r['revision']!=i or r['parent_hash']!=previous:raise ValueError('Broken intelligence revision chain')
            stamp=datetime.fromisoformat(r['saved_utc'])
            if stamp.tzinfo is None:raise ValueError('Intelligence timestamp needs timezone')
            result=None
            if r['action']['type']=='run':
                result=r['state']['cycles'][-1]['result']
                if not isinstance(result,dict):raise ValueError('Result revision requires its saved receipt; import cannot execute a check')
            state=intelligence.transition(state,r['action'],bundle,recorded_result=result,validating_history=True)
            if study.canonical(state)!=study.canonical(r['state']) or r['hash']!=study.digest({k:v for k,v in r.items() if k!='hash'}):raise ValueError('Intelligence revision does not validate from accepted records')
            previous=r['hash']
        screen_export(value);return deepcopy(records)
    except (KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
        raise ValueError('Malformed intelligence package; saved work unchanged') from None


class Journal:
    def __init__(self,bundle,directory=None):
        self.bundle=deepcopy(bundle);self.root=Path(directory) if directory is not None else None;self.history=[];self.read_only=False
        self._continuation_key=None;self._continuation_value=None
        if self.root is not None and self.root.exists():
            if self.root.is_symlink() or not self.root.is_dir():raise ValueError('Unsafe intelligence directory')
            total=0
            for p in sorted(self.root.glob('revision-*.json')):
                if p.is_symlink() or p.name!='revision-'+str(len(self.history)+1).zfill(6)+'.json':raise ValueError('Unsafe or missing intelligence revision')
                total+=p.stat().st_size
                if total>MAX_BYTES or len(self.history)>=MAX_REVISIONS:raise ValueError('Intelligence history too large')
                self.history.append(study.decode(p.read_bytes()))
            if self.history:validate_package(self.export(),self.bundle)

    def current(self):
        return deepcopy(self.history[-1]) if self.history else {'revision':0,'hash':None,'state':intelligence.initial()}

    def view(self,current):
        r=self.current();ctx=intelligence.context(current)
        return {'catalog':deepcopy(self.bundle),'current':r,'history':[{'revision':v['revision'],'hash':v['hash'],'saved_utc':v['saved_utc'],'action':v['action']['type']} for v in self.history],
          'context_status':'not_saved' if r['state']['context'] is None else ('current' if r['state']['context']==ctx else 'needs_review'),
          'owning_context':ctx,'storage':'imported_read_only' if self.read_only else ('external_data_directory' if self.root else 'session_only_export_to_keep'),
          'read_only':self.read_only,'live_enabled':False,'transport_calls':0,
          'evidence_map':evidence_map.project(self.bundle,r['state']['scope']['target_endpoint']),
          'continuation':self.continuation(ctx)}

    def continuation(self,context):
        from traitweaver import intelligence_continuation
        # Hash all owning bytes, not only the claimed head hash: an in-memory
        # mutation must invalidate the cache and pass full validation again.
        key=study.digest({'history':self.history,'catalog':self.bundle,'context':context})
        if key!=self._continuation_key:
            value=intelligence_continuation.prepare(self.history,self.bundle,context)
            self._continuation_key=key;self._continuation_value=value
        return deepcopy(self._continuation_value)

    @classmethod
    def from_package(cls,value,bundle):
        records=validate_package(value,bundle);j=cls(bundle);j.history=records;j.read_only=True;return j

    def export(self):
        if not self.history:raise ValueError('Save the intelligence scope before exporting')
        value=package(self.history,self.bundle);screen_export(value);return value

    def readable(self):
        self.export();r=self.current();s=r['state'];ref=self.bundle['reference']
        lines=['TRAITWEAVER — MOLECULAR INTELLIGENCE REVIEW','Offline transport disabled; synthetic replies are software fixtures.','Revision: '+str(r['revision']),
          'Catalog SHA-256: '+r['catalog_sha256'],'SCOPE',study.canonical(s['scope']),'SOURCE QUALIFICATION',
          ref['record_status'] if ref else 'Exact reference mapping unavailable; source validation failed.',
          'Reference strain: '+ref['strain'] if ref else 'Reference strain mapping unavailable.',
          'SOURCE DIGESTS',study.canonical(self.bundle['source_digests']),'CANDIDATES AND CLAIMS',study.canonical(self.bundle['candidates']),study.canonical(self.bundle['claims'])]
        for c in s['cycles']:
            lines+=['','CYCLE '+c['id']+' · '+c['applicability'],'PRE-RESULT DECISION',study.canonical(c['decision']),
                    'ACTUAL LOCAL RESULT',study.canonical(c['result']),'SEPARATE REASSESSMENT',study.canonical(c['assessment'])]
        lines+=['',intelligence.LIMIT];return '\n'.join(lines)+'\n'

    def apply(self,expected,action):
        if self.read_only:raise ValueError('Imported intelligence review is read-only')
        if expected!=self.current()['hash']:raise Conflict('Intelligence revision changed; reload before saving')
        if len(self.history)>=MAX_REVISIONS:raise ValueError('Intelligence revision limit reached')
        from traitweaver import intelligence_continuation
        if isinstance(action,dict) and action.get('type')=='run':
            current=intelligence.active(self.current()['state'])
            if current and current['result'] is None:
                intelligence_continuation.require_available(self.history,self.bundle,current['decision']['check'])
        state=intelligence.transition(self.current()['state'],action,self.bundle)
        if action['type']=='accept' and action['payload']['phase']=='selection':
            intelligence_continuation.require_available(self.history,self.bundle,state['cycles'][-1]['decision']['check'])
        r={'schema_version':'traitweaver.intelligence_revision.v1','catalog_sha256':study.digest(self.bundle),'revision':len(self.history)+1,
           'parent_hash':expected,'saved_utc':datetime.now(timezone.utc).isoformat(),'action':deepcopy(action),'state':state}
        r['hash']=study.digest(r);validate_package(package(self.history+[r],self.bundle),self.bundle)
        if self.root is not None:
            if self.root.is_symlink():raise ValueError('Unsafe intelligence directory')
            self.root.mkdir(mode=0o700,exist_ok=True);pending=self.root/('.pending-'+uuid.uuid4().hex);dest=self.root/('revision-'+str(r['revision']).zfill(6)+'.json')
            try:
                with pending.open('xb') as f:
                    os.chmod(pending,0o600);f.write((study.canonical(r)+'\n').encode());f.flush();os.fsync(f.fileno())
                os.link(pending,dest);fd=os.open(self.root,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            finally:pending.unlink(missing_ok=True)
        self.history.append(r);return self.current()
