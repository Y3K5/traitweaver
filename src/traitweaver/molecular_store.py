"""Separate versioned planning journal; never changes an algae/Muse revision."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import uuid

from traitweaver import molecular, study
from traitweaver.study_store import Conflict, MAX_BYTES, screen_export

LIMIT=128


def version(bundle):
    if bundle['schema_version']=='traitweaver.molecular_catalog.v2':return 'v2'
    if bundle['schema_version']=='traitweaver.molecular_catalog.v1':return 'v1'
    raise ValueError('Unsupported molecular catalog')


def initial(bundle=None):
    if bundle is not None and version(bundle)=='v2':
        from traitweaver import public_algae
        selection=public_algae.initial_selection()
    else:selection=molecular.initial_selection()
    return {'selection':selection,'reviewed_stages':[],'note':'','context':None,'planning_assessment':None}


def transition(previous, action, bundle):
    study.fields(action, ('selection','stage','note','context'))
    selection=molecular.validate_selection(action['selection'],bundle)
    if action['stage'] not in molecular.STAGES:raise ValueError('Unknown molecular review stage')
    study.text(action['note'],1000)
    ctx=action['context'];study.fields(ctx, ('study_id','study_revision_hash','target_endpoint'))
    study.text(ctx['study_id'],100)
    if not isinstance(ctx['study_revision_hash'],str) or not re.fullmatch('[a-f0-9]{64}',ctx['study_revision_hash']) or ctx['target_endpoint'] not in study.ENDPOINTS:
        raise ValueError('Invalid owning study context')
    same=previous['selection']==selection and previous['context']==ctx
    stages=previous['reviewed_stages'] if same else []
    stages=[s for s in molecular.STAGES if s in stages or s==action['stage']]
    return {'selection':selection,'reviewed_stages':stages,'note':action['note'],'context':deepcopy(ctx),'planning_assessment':deepcopy(molecular.assess(selection,bundle))}


def package(records, bundle):
    return {'schema_version':'traitweaver.molecular_review.'+version(bundle),'catalog':deepcopy(bundle),
            'revisions':deepcopy(records),'limit':bundle['limit']}


def validate_package(value, bundle):
    try:
        study.fields(value, ('schema_version','catalog','revisions','limit'))
        if value['schema_version']!='traitweaver.molecular_review.'+version(bundle) or value['limit']!=bundle['limit'] or study.canonical(value['catalog'])!=study.canonical(bundle):
            raise ValueError('Unsupported molecular sources or review version')
        records=value['revisions']
        if not isinstance(records,list) or not 1<=len(records)<=LIMIT:raise ValueError('Unsupported molecular revision count')
        if len(study.canonical(value).encode())>MAX_BYTES:raise ValueError('Molecular review too large')
        prior=None;state=initial(bundle)
        for number,r in enumerate(records,1):
            study.fields(r, ('schema_version','catalog_sha256','revision','parent_hash','saved_utc','action','state','hash'))
            if r['schema_version']!='traitweaver.molecular_revision.'+version(bundle) or r['catalog_sha256']!=study.digest(bundle) or type(r['revision']) is not int or r['revision']!=number or r['parent_hash']!=prior:
                raise ValueError('Broken molecular revision chain')
            try:timestamp=datetime.fromisoformat(r['saved_utc'])
            except (TypeError,ValueError):raise ValueError('Invalid molecular revision timestamp') from None
            if timestamp.tzinfo is None:raise ValueError('Molecular timestamp requires a timezone')
            state=transition(state,r['action'],bundle)
            if state!=r['state'] or r['hash']!=study.digest({k:v for k,v in r.items() if k!='hash'}):
                raise ValueError('Molecular history does not replay')
            prior=r['hash']
        screen_export(value)
        return deepcopy(records)
    except (KeyError,TypeError,AttributeError,IndexError,RecursionError):
        raise ValueError('Malformed molecular review; nothing was changed') from None


class Journal:
    """Uses the enclosing workspace's owner lock and request mutex for writes."""
    def __init__(self, bundle, directory=None):
        self.bundle=deepcopy(bundle);self.root=Path(directory) if directory is not None else None
        self.history=[];self.read_only=False
        if self.root is not None and self.root.is_symlink():raise ValueError('Unsafe molecular review directory')
        if self.root is not None and self.root.exists():
            if self.root.is_symlink() or not self.root.is_dir():raise ValueError('Unsafe molecular review directory')
            total_bytes=0
            for path in sorted(self.root.glob('review-*.json')):
                total_bytes+=path.stat().st_size if not path.is_symlink() else 0
                if len(self.history)>=LIMIT or total_bytes>MAX_BYTES or path.is_symlink() or path.stat().st_size>MAX_BYTES or path.name!='review-'+str(len(self.history)+1).zfill(6)+'.json':
                    raise ValueError('Unsafe or missing molecular revision')
                self.history.append(study.decode(path.read_bytes()))
            if self.history:validate_package(self.export(),self.bundle)

    @classmethod
    def from_package(cls,value,bundle):
        records=validate_package(value,bundle);self=cls(bundle);self.history=records;self.read_only=True
        return self

    def current(self):
        return deepcopy(self.history[-1]) if self.history else {'revision':0,'hash':None,'state':initial(self.bundle)}

    def view(self, current):
        ctx=molecular.context(current);saved=self.current()
        return {'catalog':deepcopy(self.bundle),'current':saved,
                'history':[{'revision':r['revision'],'hash':r['hash'],'saved_utc':r['saved_utc'],'stage':r['action']['stage']} for r in self.history],
                'context_status':'not_saved' if not self.history else ('current' if saved['state']['context']==ctx else 'needs_review'),
                'storage':'imported_read_only' if self.read_only else ('external_data_directory' if self.root is not None else 'session_only_export_to_keep'),
                'read_only':self.read_only,'owning_context':ctx}

    def export(self):
        if not self.history:raise ValueError('Save a molecular review before exporting')
        value=package(self.history,self.bundle);screen_export(value)
        return value

    def readable(self):
        self.export()  # Apply the same privacy gate to readable output.
        r=self.current();state=r['state'];a=state['planning_assessment']
        lines=['TRAITWEAVER — MOLECULAR PLANNING REVIEW', '',
               'Source role: '+('Public algae reference annotation; frozen primary records' if version(self.bundle)=='v2' else ('Synthetic coordinate software fixture' if a['synthetic'] else 'Qualified public reference metadata; exact mapping unavailable')),
               'Original algae/Muse records are unchanged.',
               'Molecular revision: '+str(r['revision']),
               'Catalog SHA-256: '+r['catalog_sha256'],
               'Selected protein: '+state['selection']['protein_id'],
               'Explicit transcript: '+(state['selection']['transcript_id'] or 'Not selected'),
               'Comparison transcript: '+(state['selection']['comparison_id'] or 'Not selected'),
               'Planning concept: '+a['concept']['label'],
               'Biological target ready: No', '', 'STUDY CONTEXT POINTER',study.canonical(state['context']),
               '', 'RECORDED PLANNING CHECKPOINTS',', '.join(state['reviewed_stages']),
               '', 'REVIEW NOTE',state['note'] or 'No note supplied', '', 'MAPPING / COMPARISON',
               *(self._mapping_lines(a)),
               '', 'UNRESOLVED BLOCKERS',*['- '+item for item in a['blockers']],
               '', 'MEASUREMENT QUESTIONS',study.canonical(a['measurement_plan']),
               '', 'HISTORY',*['Revision '+str(v['revision'])+' · '+v['saved_utc']+' · '+v['action']['stage'] for v in self.history],
               '',self.bundle['limit']]
        if version(self.bundle)=='v2':
            lines+=['','REFERENCE ANNOTATION QUALIFICATION',self.bundle['record_status'],
                    'Reference organism: '+self.bundle['organism'],'Reference strain: '+self.bundle['strain'],
                    '', 'SOURCE FILES AND CLAIM TRACE',study.canonical(self.bundle['sources']),study.canonical(self.bundle['claims']),
                    '', 'OFFLINE SEQUENCE CHECKS',study.canonical(self.bundle['checks'])]
        return '\n'.join(lines)+'\n'

    def _mapping_lines(self, assessment):
        mapping=assessment['mapping'];comparison=assessment['comparison'];lines=[]
        if mapping is None:lines.append('No exact transcript/gene/assembly mapping is established for this selection.')
        else:
            g=mapping['gene']
            lines += ['Gene model: '+g['id']+'; '+g['assembly']+'; '+g['chromosome']+'; strand '+g['strand'],
                      'Transcript length: '+str(mapping['transcript_length_nt'])+' nt',
                      'Coding model length: '+str(mapping['coding_length_nt'])+' nt',
                      'Protein model length: '+str(mapping['protein_length_aa'])+(' aa; matched to pinned reference sequence offline' if version(self.bundle)=='v2' else ' aa; not sequence-verified')]
            for row in mapping['rows']:
                lines.append('Exon '+row['exon_id']+': genomic '+str(row['genomic_interval'])+'; transcript '+str(row['transcript_interval'])+' nt; coding '+str(row['coding_interval'])+' nt; protein model '+str(row['protein_interval'])+' aa (null/None means unavailable or noncoding).')
        if comparison is not None:
            lines += ['Comparison: '+comparison['comparison'],
                      'Transcript length difference: '+str(comparison['transcript_delta_nt'])+' nt',
                      'Coding length difference: '+str(comparison['coding_delta_nt'])+' nt',
                      'Protein length-model difference: '+str(comparison['protein_length_difference_aa'])+' aa; unknown remains None']
        return lines

    def save(self, expected, action):
        if self.read_only:raise ValueError('Imported molecular review is read-only; original saved work is preserved')
        if expected!=self.current()['hash']:raise Conflict('Molecular review changed; reload before saving')
        if len(self.history)>=LIMIT:raise ValueError('Molecular revision limit reached')
        state=transition(self.current()['state'],action,self.bundle)
        r={'schema_version':'traitweaver.molecular_revision.'+version(self.bundle),'catalog_sha256':study.digest(self.bundle),'revision':len(self.history)+1,
           'parent_hash':expected,'saved_utc':datetime.now(timezone.utc).isoformat(),'action':deepcopy(action),'state':state}
        r['hash']=study.digest(r)
        validate_package(package(self.history+[r],self.bundle),self.bundle)
        if self.root is not None:
            if self.root.is_symlink():raise ValueError('Unsafe molecular review directory')
            self.root.mkdir(mode=0o700,exist_ok=True)
            pending=self.root/('.pending-'+uuid.uuid4().hex)
            dest=self.root/('review-'+str(r['revision']).zfill(6)+'.json')
            try:
                with pending.open('xb') as f:
                    os.chmod(pending,0o600);f.write((study.canonical(r)+'\n').encode());f.flush();os.fsync(f.fileno())
                os.link(pending,dest)
                descriptor=os.open(self.root,os.O_RDONLY)
                try:os.fsync(descriptor)
                finally:os.close(descriptor)
            finally:pending.unlink(missing_ok=True)
        self.history.append(r)
        return self.current()
