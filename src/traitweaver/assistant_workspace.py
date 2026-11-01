"""Session-only UI owner for the independent four-case assistant.

Public inputs, bounded local audits and synthetic proposals. Saved packages are
read-only reviews, not original study revisions or an organism design contract.
"""
from copy import deepcopy
from datetime import datetime, timezone

from traitweaver import assistant as core, protein_card, study, study_store

SCHEMA = 'traitweaver.assistant_workspace_package.v1'
TITLES = {'ENV_ALGAE':'Algae · phosphorus recovery','PROTEIN_GFP':'Protein · qualified GFP',
          'RNA_SYNTHETIC':'RNA-seq · synthetic study planning','REPRO_SYNTHETIC':'Reproducibility · synthetic project'}
TOOLS = {'ENV_ALGAE':('algae_endpoint_audit','Audit admitted phosphorus endpoints without substituting uptake for collected product or plant use.'),
         'PROTEIN_GFP':('gfp_record_audit','Check qualified identity, evidence roles and unavailable fields without inferring structural or experimental validation.'),
         'RNA_SYNTHETIC':('rna_metadata_audit','Locate duplicates, layout conflicts and missing design/input metadata without expression analysis.'),
         'REPRO_SYNTHETIC':('repro_record_audit','Check version/source/run-record completeness without installing or executing a project.')}
LIMIT = 'Local source/metadata audit and proposed next actions only. No biological winner, organism design, cassette sequence, edit site, laboratory protocol or experimental validation.'


def _check_value(case_id):
    """Pure replay formula. The registered tool calls this only on execution."""
    case=core.get_case(case_id)
    if case_id=='ENV_ALGAE':
        return {'status':'completed','tool':TOOLS[case_id][0], 'findings':[
            {'code':'endpoint_gaps','text':'Removal, assimilation, collection and plant use require distinct evidence. Collected-product and plant-use data remain unavailable.','citations':['ENV_SCOPE','ENV_GAPS']},
            {'code':'different_contexts','text':'No common baseline or cross-study recovery ranking is admitted.','citations':['ENV_GAPS']}],
            'coverage':study._coverage_value(study.initial_state()),'limit':LIMIT}
    if case_id=='PROTEIN_GFP':
        card=protein_card.build_card()
        return {'status':'completed','tool':TOOLS[case_id][0], 'findings':[
            {'code':'roles_preserved','text':'Qualified identity, database annotation and model features remain separate.','citations':[card['card_id'],'DB_GFP_FUNCTION','SAE_11271','SAE_4790','SAE_11579']},
            {'code':'structure_assay_gaps','text':'Unavailable structure/confidence/version fields remain null. No experimental evidence is admitted in this snapshot.','citations':['GFP_MISSING','GFP_ASSAYS']}],
            'sequence_length':card['identity']['sequence_length'], 'unavailable':deepcopy(card['unavailable']), 'limit':LIMIT}
    records={r['id']:r['value'] for r in case['records']}
    if case_id=='RNA_SYNTHETIC':
        rows=records['RNA_SHEET']['rows'];manifest=records['RNA_MANIFEST'];design=records['RNA_DESIGN']
        duplicates=sorted({r['sample_id'] for r in rows if sum(x['sample_id']==r['sample_id'] for x in rows)>1})
        conflicts=[r['sample_id'] for r in rows if r['sample_id']+'_layout' in manifest and r['layout']!=manifest[r['sample_id']+'_layout']]
        missing=sorted(['design.'+k for k,v in design.items() if v is None]+['manifest.'+k for k,v in manifest.items() if v is None])
        return {'status':'completed','tool':TOOLS[case_id][0], 'duplicates':duplicates,'layout_conflicts':conflicts,
            'missing_fields':missing,'fastq_files_supplied':manifest['fastq_files_supplied'],'read_count':manifest['read_count'],
            'analysis_ready':False,'findings':[
                {'code':'metadata_blocked','text':'Duplicate IDs, conflicting layouts and missing design/reference/QC metadata block an analysis-ready claim.','citations':['RNA_DESIGN','RNA_SHEET','RNA_MANIFEST']}], 'limit':LIMIT}
    missing=sorted(record+'.'+k for record,value in records.items() for k,v in value.items() if v is None)
    return {'status':'completed','tool':TOOLS[case_id][0], 'missing_fields':missing,
        'exit_code':records['REP_RUN']['exit_code'],'run_records_count':records['REP_RUN']['run_records_count'],
        'reproducibility_verified':False, 'findings':[
            {'code':'unverified_completion','text':'README completion claims lack version/source/run evidence. Exit code zero alone is not a verified run.','citations':['REP_README','REP_ENV','REP_INPUTS','REP_RUN']}], 'limit':LIMIT}


def run_local_check(case_id):
    return _check_value(case_id)


def validate_checks(case_id, checks):
    if not isinstance(checks,list) or len(checks)>1:
        raise ValueError('At most one local audit receipt per assistant review')
    for receipt in checks:
        study.fields(receipt,('decision','result','saved_utc'))
        decision={'check':TOOLS[case_id][0],'purpose':TOOLS[case_id][1],
                  'case_sha256':study.digest(core.get_case(case_id)),'policy':'explicit_user_selected_local_check'}
        if receipt['decision'] != decision:
            raise ValueError('Altered assistant check decision')
        try:
            stamp=datetime.fromisoformat(receipt['saved_utc'])
            if stamp.tzinfo is None:raise ValueError('No timezone')
        except (ValueError,TypeError) as exc:
            raise ValueError('Invalid assistant audit timestamp') from exc
        failure={'status':'failed','tool':TOOLS[case_id][0], 'findings':[],
                 'reason':'Local audit failed; no interpretation is permitted.','limit':LIMIT}
        expected=failure if isinstance(receipt['result'],dict) and receipt['result'].get('status')=='failed' else _check_value(case_id)
        if study.canonical(receipt['result'])!=study.canonical(expected):
            raise ValueError('Assistant audit receipt differs from its admitted inputs')
    return deepcopy(checks)


class Session:
    def __init__(self):
        core.catalog()
        self.selected='ENV_ALGAE';self.slots={};self.imported=None;self.revision=0

    def _active(self):
        return self.imported if self.imported is not None else self.slots.get(self.selected,{'case_id':self.selected,'review':None,'checks':[]})

    def current(self):
        value={'revision':self.revision,'state':deepcopy(self._active()),'read_only':self.imported is not None}
        value['hash']=study.digest(value)
        return value

    def view(self):
        active=self._active();case=core.get_case(active['case_id'])
        return {'current':self.current(),'case':case,'review':deepcopy(active['review']),
            'checks':deepcopy(active['checks']),'read_only':self.imported is not None,
            'cases':[{'id':c['case_id'],'title':TITLES[c['case_id']],'input_kind':c['input_kind']} for c in core.catalog()['cases']],
            'tool':{'id':TOOLS[case['case_id']][0],'purpose':TOOLS[case['case_id']][1]},
            'storage':'session_only_export_to_preserve','live_enabled':False,'transport_calls':0,'limit':LIMIT}

    def select(self,case_id):
        core.get_case(case_id)
        self.selected=case_id;self.imported=None;self.revision+=1

    def _editable(self):
        if self.imported is not None:raise ValueError('Reopened assistant package is read-only. Return to a local case to start a separate review.')
        return deepcopy(self._active())

    def synthetic(self):
        active=self._editable()
        if active['review'] is not None:raise ValueError('This local case already has a review; no duplicate synthetic acceptance')
        request=core.prepare(self.selected)
        active['review']=core.parse_reply(self.selected,study.canonical(core.synthetic_reply(self.selected)).encode(),request['request_sha256'])
        self.slots[self.selected]=active;self.revision+=1

    def check(self):
        active=self._editable()
        if active['checks']:raise ValueError('This case already has a local audit receipt; no automatic rerun')
        # Save a pre-result decision in the session before registered dispatch.
        receipt={'decision':{'check':TOOLS[self.selected][0],'purpose':TOOLS[self.selected][1],
            'case_sha256':study.digest(core.get_case(self.selected)),'policy':'explicit_user_selected_local_check'},
            'result':None,'saved_utc':datetime.now(timezone.utc).isoformat()}
        active['checks'].append(receipt);self.slots[self.selected]=active;self.revision+=1
        try:
            receipt['result']=run_local_check(self.selected)
        except Exception:
            receipt['result']={'status':'failed','tool':TOOLS[self.selected][0], 'findings':[],
                'reason':'Local audit failed; no interpretation is permitted.','limit':LIMIT}

    def export(self):
        active=self._active()
        if active['review'] is None:raise ValueError('Create a labelled synthetic plan or reopen an accepted review before exporting')
        checks=validate_checks(active['case_id'],active['checks'])
        value={'schema_version':SCHEMA,'assistant_package':core.package(active['review']),
               'local_checks':checks,'limit':LIMIT}
        value['sha256']=study.digest(value)
        study_store.screen_export(value)
        return value

    def readable(self):
        self.export()
        active=self._active()
        return core.readable(active['review'])+'\nLocal audit receipts (separate from model claims)\n'+study.canonical(active['checks'])+'\n'+LIMIT+'\n'

    def open(self,value):
        if isinstance(value,dict) and value.get('schema_version')==core.PACKAGE:
            record=core.validate_package(value);checks=[]
        else:
            study.fields(value,('schema_version','assistant_package','local_checks','limit','sha256'))
            if value['schema_version']!=SCHEMA or value['limit']!=LIMIT:raise ValueError('Unsupported assistant workspace package')
            record=core.validate_package(value['assistant_package'])
            checks=validate_checks(record['case_id'],value['local_checks'])
            if value['sha256']!=study.digest({k:v for k,v in value.items() if k!='sha256'}):raise ValueError('Assistant workspace checksum mismatch')
            study_store.screen_export(value)
        # Commit the new view only after every record has passed. Local slots stay.
        self.imported={'case_id':record['case_id'],'review':record,'checks':checks};self.revision+=1
