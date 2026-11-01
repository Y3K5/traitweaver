"""Three-column review owner over existing assistant/story services.

Annotations are not model instructions or scientific evidence. No provider,
arbitrary tool, new source admission or original-study mutation is implemented.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re

from traitweaver import assistant, assistant_workspace, research_story, study, study_store

SCHEMA='traitweaver.workbench_package.v1'
REVISION='traitweaver.workbench_annotation.v1'
MAX_BYTES=512*1024
STAGES=('evidence','identity','check','actions','plan','export')
LIMIT='Public/synthetic fixed-case review. Free text is an uninterpreted annotation; human scientific review remains NOT REVIEWED. Privacy review and integrity checks are not scientific approval or publication permission.'
PATTERNS={
    'personal filesystem reference':r'/Users/|/home/|\$HOME|(?i:([A-Z]:\\Users\\|file://|smb://))',
    'credential-shaped content':r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'credential assignment/header':r'(?i)(?:api[_ -]?key|password|access[_ -]?token|client[_ -]?secret|authorization)\s*[:=]\s*\S+',
    'response/session cookie':r'(?i)(?:set-cookie|\bcookie)\s*:',
    'active embedded content':r'(?i)<\s*(?:script|img|iframe|object|svg)\b|!\[[^\]]*\]\(\s*(?:https?://|data:)',
    'sensitive URL parameter':r'(?i)https?://\S*[?&](?:token|key|sig|signature|auth|credential)=',
    'private-content marking':r'(?i)\b(?:confidential|internal[- ]only|do not share|private research)\b',
}


def validate_text(question,notes):
    study.text(question,1200)
    if type(notes) is not str or len(notes)>2000 or '\x00' in notes:
        raise ValueError('Notes must be text of at most 2000 characters, without null characters')


def privacy(history):
    findings=[]
    for row in history:
        for field in ('question','notes'):
            for category,pattern in PATTERNS.items():
                if re.search(pattern,row[field]):
                    findings.append({'revision':row['revision'],'field':field,'category':category})
    return {'status':'blocked' if findings else 'requires_owner_review','findings':findings,
        'scope':'All saved annotation revisions for this case are included. No content was removed.',
        'limit':'Pattern checks cannot recognize every private project, research claim or personal detail. Review all annotations before local export. This does not authorize sharing.'}


def validate_history(history,case):
    if not isinstance(history,list) or not 1<=len(history)<=32:raise ValueError('Unsupported annotation history length')
    prior=None;seen=set()
    for number,row in enumerate(history,1):
        study.fields(row,('schema_version','revision','parent_hash','based_on_hash','saved_utc','case_sha256','question','notes','hash'))
        if row['schema_version']!=REVISION or type(row['revision']) is not int or row['revision']!=number or row['parent_hash']!=prior or row['case_sha256']!=study.digest(case):
            raise ValueError('Broken annotation history/source identity')
        if (number==1 and row['based_on_hash'] is not None) or (number>1 and (type(row['based_on_hash']) is not str or row['based_on_hash'] not in seen)):
            raise ValueError('Unknown annotation base revision')
        try:
            if datetime.fromisoformat(row['saved_utc']).tzinfo is None:raise ValueError('Missing timezone')
        except (ValueError,TypeError) as exc:raise ValueError('Invalid annotation timestamp') from exc
        validate_text(row['question'],row['notes'])
        if row['hash']!=study.digest({k:v for k,v in row.items() if k!='hash'}):raise ValueError('Annotation checksum mismatch')
        seen.add(row['hash']);prior=row['hash']
    return deepcopy(history)


def validate_science(value):
    study.fields(value,('case','accepted_review','local_checks','story_package'))
    if not isinstance(value['case'],dict):raise ValueError('Scientific case must be an object')
    case=assistant.get_case(value['case'].get('case_id'))
    if study.canonical(value['case'])!=study.canonical(case):raise ValueError('Changed scientific case')
    review=value['accepted_review']
    if review is not None:
        assistant.validate_record(review)
        if review['case_id']!=case['case_id']:raise ValueError('Cross-case assistant review')
    assistant_workspace.validate_checks(case['case_id'],value['local_checks'])
    if value['story_package'] is not None:
        if case['case_id']!='ENV_ALGAE':raise ValueError('Public algae mapping cannot attach to another case')
        research_story.validate_package(value['story_package'])
    return deepcopy(value)


def validate_package(value):
    study.fields(value,('schema_version','science','annotations','selected_hash','checkpoint','human_review','limit','sha256'))
    if value['schema_version']!=SCHEMA or value['human_review']!='not_reviewed' or value['limit']!=LIMIT or value['checkpoint'] not in STAGES:
        raise ValueError('Unsupported workbench package/review status')
    science=validate_science(value['science']);history=validate_history(value['annotations'],science['case'])
    if type(value['selected_hash']) is not str or value['selected_hash'] not in {r['hash'] for r in history}:raise ValueError('Missing selected annotation revision')
    if value['sha256']!=study.digest({k:v for k,v in value.items() if k!='sha256'}):raise ValueError('Workbench package checksum mismatch')
    if privacy(history)['findings']:raise ValueError('Workbench import requires privacy review. Suspected private content was not admitted or removed.')
    study_store.screen_export(value)
    return deepcopy(value)


def markdown_literal(value):
    # Encoding is presentation, not redaction. Exact original strings remain JSON.
    value=value.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|])',r'\\\1',value)


class Session:
    def __init__(self,assistant_owner,story_owner):
        if assistant_owner is None:raise ValueError('Qualified assistant cases required')
        self.assistant=assistant_owner;self.story=story_owner
        self.slots={};self.selected={};self.checkpoint='evidence';self.imported=None;self.version=0

    def science(self):
        if self.imported is not None:return deepcopy(self.imported['science'])
        v=self.assistant.view()
        return {'case':v['case'],'accepted_review':v['review'],'local_checks':v['checks'],
                'story_package':self.story.export() if self.story and v['case']['case_id']=='ENV_ALGAE' else None}

    def _history(self,case):
        if self.imported is not None:return self.imported['annotations']
        cid=case['case_id']
        if cid not in self.slots:
            self.slots[cid]=[];self._append(case,case['objective'],'',None)
        return self.slots[cid]

    def _append(self,case,question,notes,based):
        validate_text(question,notes);history=self.slots[case['case_id']]
        if len(history)>=32:raise ValueError('Annotation history limit reached; no revision changed')
        row={'schema_version':REVISION,'revision':len(history)+1,'parent_hash':history[-1]['hash'] if history else None,
             'based_on_hash':based,'saved_utc':datetime.now(timezone.utc).isoformat(),'case_sha256':study.digest(case),'question':question,'notes':notes}
        row['hash']=study.digest(row);history.append(row);self.selected[case['case_id']]=row['hash']

    def _parts(self):
        science=self.science();case=science['case'];history=self._history(case)
        selected=self.imported['selected_hash'] if self.imported else self.selected[case['case_id']]
        return science,history,selected

    def current(self):
        science,history,selected=self._parts()
        value={'case_id':science['case']['case_id'],'annotation_hash':selected,'history_sha256':study.digest(history),
               'science_sha256':study.digest(science),'checkpoint':self.checkpoint,'read_only':self.imported is not None,'version':self.version}
        value['hash']=study.digest(value);return value

    def view(self):
        science,history,selected=self._parts()
        return {'current':self.current(),'science':science,'annotations':deepcopy(history),
            'annotation':deepcopy(next(r for r in history if r['hash']==selected)),
            'cases':self.assistant.view()['cases'],'privacy':privacy(history),'human_review':'not_reviewed',
            'assistant_read_only':self.assistant.view()['read_only'] if self.imported is None else True,
            'storage':'server_memory_only_export_to_preserve','live_enabled':False,'limit':LIMIT}

    def present(self,checkpoint):
        if checkpoint not in STAGES:raise ValueError('Unknown workbench checkpoint')
        self.checkpoint=checkpoint;self.version+=1

    def prepare_muse(self):
        """Exact public/synthetic case only; annotations never enter a request."""
        return assistant.prepare(self.science()['case']['case_id'])

    def select(self,case_id):
        self.assistant.select(case_id);self.imported=None;self.checkpoint='evidence';self.version+=1

    def save(self,question,notes):
        if self.imported:raise ValueError('Imported workbench is read-only. Return to a local case for a separate review.')
        science,history,selected=self._parts();current=next(r for r in history if r['hash']==selected)
        if (question,notes)==(current['question'],current['notes']):raise ValueError('No annotations changed')
        self._append(science['case'],question,notes,selected);self.version+=1

    def history(self,fingerprint):
        if self.imported:raise ValueError('Imported workbench is read-only')
        science,rows,_=self._parts()
        if fingerprint not in {r['hash'] for r in rows}:raise ValueError('Unknown annotation revision')
        self.selected[science['case']['case_id']]=fingerprint;self.version+=1

    def act(self,action):
        if self.imported:raise ValueError('Imported workbench is read-only; no tool or synthetic acceptance')
        if action=='check':self.assistant.check()
        elif action=='synthetic':self.assistant.synthetic()
        else:raise ValueError('Unregistered workbench action')
        self.version+=1

    def export(self,privacy_reviewed_hash=None):
        science,history,selected=self._parts();findings=privacy(history)
        if findings['findings']:
            locations=', '.join('revision '+str(f['revision'])+' / '+f['field']+' / '+f['category'] for f in findings['findings'])
            raise ValueError('Export blocked for privacy review: '+locations+'. No content was removed; no file was created.')
        if privacy_reviewed_hash!=self.current()['hash']:
            raise ValueError('Review all saved annotations and confirm this exact local export. This is not scientific approval or permission to publish.')
        value={'schema_version':SCHEMA,'science':validate_science(science),'annotations':validate_history(history,science['case']),
               'selected_hash':selected,'checkpoint':self.checkpoint,'human_review':'not_reviewed','limit':LIMIT}
        value['sha256']=study.digest(value)
        study_store.screen_export(value)
        if len(study.canonical(value).encode())>MAX_BYTES:raise ValueError('Workbench package exceeds byte limit; nothing truncated')
        return value

    def readable(self,privacy_reviewed_hash=None):
        p=self.export(privacy_reviewed_hash);science=p['science'];case=science['case']
        lines=['# Traitweaver — study workbench','',LIMIT,'','Human scientific review: NOT REVIEWED',
               'Export privacy acknowledgment is not publication or biological approval.',
               'Fixed case: '+case['case_id'],'Checkpoint: '+p['checkpoint'],
               'All saved annotation revisions for this case follow. These are uninterpreted annotations.']
        for row in p['annotations']:
            lines += ['', '## Annotation revision '+str(row['revision']),
                      'Question: '+markdown_literal(row['question']),'Notes: '+markdown_literal(row['notes']),
                      'Revision hash: '+row['hash'],'Parent hash: '+str(row['parent_hash'])]
        lines+=['','## Qualified evidence, next actions and actual local audit receipts',markdown_literal(study.canonical(science)),
                '', '## Exact accepted records (escaped Markdown; JSON retains original text)',markdown_literal(study.canonical(p))]
        # The scientific snapshot contains no free text. Do not append a raw
        # annotation JSON block to Markdown (it could activate embedded markup).
        return '\n'.join(lines)+'\n'

    def open(self,value):
        valid=validate_package(value)
        self.imported=valid;self.checkpoint=valid['checkpoint'];self.version+=1
