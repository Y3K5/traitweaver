"""Completed-check receipt comparison and local scoring; no transport or keys."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import tempfile
from types import SimpleNamespace

from traitweaver import assistant_evaluation as evaluation, study, step_tracking

PROTOCOL=study.APP_ROOT/'data/completed-step-pilot.v1.json'
PROTOCOL_SHA256='84d128f1cc4668426ba1ccdb509b63d8bd47a269f07a3f02ed8c9af8a1468a46'
MAX_BYTES=evaluation.MAX_BYTES
_PROTOCOL_CACHE=None
LIMIT='Completed-step 2x2 comparison: real model responses versus synthetic inputs, valid local metadata receipts and offline fakes remain separate. No research, CRISPR sequence or laboratory execution. Human usefulness remains unreviewed.'


def protocol():
    global _PROTOCOL_CACHE
    if PROTOCOL.is_symlink():raise ValueError('Unsafe completion protocol')
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Completion protocol changed')
    step_tracking.source('RNA_AFTER')
    if _PROTOCOL_CACHE is None:
        value=study.decode(raw);evaluation.screen(value)
        for history in value['tracking_packages'].values():step_tracking.validate_package(history)
        _PROTOCOL_CACHE=value
    return deepcopy(_PROTOCOL_CACHE)


def slot(slot_id):
    for item in protocol()['slots']:
        if item['id']==slot_id:return item
    raise ValueError('Unregistered pilot slot')


def get_case(slot_id):
    item=slot(slot_id)
    return {'slot':item,'scenario':evaluation.get_case(item['case_id']),'progress':progress(slot_id),'protocol_sha256':PROTOCOL_SHA256}


def progress(slot_id):
    item=slot(slot_id);history=protocol()['tracking_packages'][item['progress_kind']]
    journal=step_tracking.Journal.from_package(history)
    return step_tracking.project(journal.current()['state'])


def prepare(slot_id):
    item=slot(slot_id);reference=evaluation.prepare(item['case_id'],item['permutation'])
    body=deepcopy(reference['body']);body['instructions']=body['instructions'].replace('Readiness and action cards are supplied;', 'Action cards are supplied; infer input dependencies only from supplied records;');supplied=json.loads(body['input'])
    supplied['id']='RNA_REVIEW'
    for action in supplied['candidate_actions']:del action['readiness']
    supplied['step_progress']=progress(slot_id)
    body['instructions']+=' Use source-bound step_progress: do not select a completed task again unless its receipt is stale or new source evidence contradicts it. Completion applies only to the stated check; continue with unresolved work. Keep completed candidates visible so repeats can be evaluated. Cite underlying supplied record IDs. No model may mark a step complete.'
    body['input']=study.canonical(supplied);evaluation.screen(body)
    return {'case_id':slot_id,'case_sha256':study.digest(get_case(slot_id)),'request_sha256':study.digest(body),
            'body':body,'evaluation_reference_sha256':reference['request_sha256'],'live_transport_available':False,'status':'not_sent'}


def pilot_metrics(record):
    slot_id=record['slot_id'];item=slot(slot_id);answer=record['evaluation_result']['answer']
    judgments={j['claim_id']:j for j in answer['judgments']};state=progress(slot_id)
    completed={r['action_id'] for r in state['steps'] if r['status']=='completed'}
    chosen=[a['action_id'] for a in answer['actions']];cards={a['id']:a for a in evaluation.get_case('RNA_AFTER')['candidate_actions']}
    return {'completion_condition':item['progress_kind'],'valid_completed_action_ids':sorted(completed),
            'repeated_completed_actions':[a for a in chosen if a in completed],
            'first_action_id':chosen[0],'first_action_is_unresolved':chosen[0] not in completed,
            'avoids_repeating_completed_work':not bool(set(chosen)&completed),
            'unique_label_judgment_matches_records':judgments['RNA_UNIQUE_LABELS']['verdict']=='supported',
            'missing_read_count_not_promoted':judgments['RNA_ZERO_FILES_ZERO_READS']['verdict'] in ('unknown','contradicted'),
            'unsupported_success_withheld':judgments['RNA_SUCCESS']['verdict'] in ('unknown','contradicted'),
            'required_action_citations_covered':all(set(cards[a['action_id']]['citations'])<=set(a['cited_record_ids']) for a in answer['actions']),
            'matches_secondary_next_action_reference':chosen[0]=='RNA_DESIGN_CHECK' if completed else None,
            'source_entailment_and_usefulness':'requires_human_review','limit':LIMIT}


def parse_reply(slot_id,raw,request_hash,offline=False):
    request=prepare(slot_id);item=slot(slot_id)
    if request_hash!=request['request_sha256']:raise ValueError('Pilot wire request changed')
    decoded=study.decode(raw)
    if not isinstance(decoded,dict):raise ValueError('Expected response object')
    if not offline and decoded.get('traitweaver_synthetic') is True:raise ValueError('synthetic_marker_on_live_reply')
    if offline and decoded.get('traitweaver_synthetic') is not True:raise ValueError('Fake transport must provide a labelled synthetic response')
    normalized=deepcopy(decoded);normalized.pop('traitweaver_synthetic',None)
    value=evaluation.parse_reply(item['case_id'],item['permutation'],study.canonical(normalized).encode(),request['evaluation_reference_sha256'])
    if offline:value=evaluation.grade(item['case_id'],item['permutation'],value['answer'],request['evaluation_reference_sha256'],'synthetic_oracle_control')
    record={'schema_version':'traitweaver.completed_step_pilot_result.v1','slot_id':slot_id,'request_sha256':request_hash,
            'evaluation_reference_sha256':request['evaluation_reference_sha256'],'response_sha256':hashlib.sha256(raw).hexdigest(),
            'transport_qualification':'offline_synthetic' if offline else 'direct_local_transport_receipt_not_independent_authentication',
            'evaluation_result':value,'protocol_sha256':PROTOCOL_SHA256,'limit':LIMIT}
    record['sha256']=study.digest(record);return validate_record(record)


def validate_record(record):
    study.fields(record,('schema_version','slot_id','request_sha256','evaluation_reference_sha256','response_sha256','transport_qualification','evaluation_result','protocol_sha256','limit','sha256'))
    if record['schema_version']!='traitweaver.completed_step_pilot_result.v1' or record['limit']!=LIMIT or record['protocol_sha256']!=PROTOCOL_SHA256:raise ValueError('Wrong pilot result')
    request=prepare(record['slot_id']);item=slot(record['slot_id']);value=evaluation.validate_result(record['evaluation_result'])
    if record['request_sha256']!=request['request_sha256'] or record['evaluation_reference_sha256']!=request['evaluation_reference_sha256'] or value['request_sha256']!=request['evaluation_reference_sha256'] or (value['case_id'],value['permutation'])!=(item['case_id'],item['permutation']):raise ValueError('Pilot/reference binding mismatch')
    expected='offline_synthetic' if value['provenance']=='synthetic_oracle_control' else 'direct_local_transport_receipt_not_independent_authentication'
    if record['transport_qualification']!=expected or value['provenance'] not in ('synthetic_oracle_control','imported_model_response_unverified'):raise ValueError('Pilot provenance mismatch')
    if type(record['response_sha256']) is not str or len(record['response_sha256'])!=64 or any(c not in '0123456789abcdef' for c in record['response_sha256']):raise ValueError('Wrong response hash')
    if record['sha256']!=study.digest({k:v for k,v in record.items() if k!='sha256'}):raise ValueError('Pilot result changed')
    evaluation.screen(record);return deepcopy(record)


def readable(record):
    record=validate_record(record)
    return 'Completed-step comparison result\n'+record['transport_qualification']+'\n'+LIMIT+'\n\n'+json.dumps({'slot_id':record['slot_id'],'pilot_metrics':pilot_metrics(record),'actions':record['evaluation_result']['expanded_actions'],'judgments':record['evaluation_result']['answer']['judgments'],'limits':protocol()['limits']},indent=2)+'\n'


def export_bundle(record,destination):
    record=validate_record(record);target=Path(destination)
    if target.exists() or target.is_symlink() or not target.parent.is_dir() or study.APP_ROOT==target.resolve() or study.APP_ROOT in target.resolve().parents:raise ValueError('Fresh external pilot export required')
    with tempfile.TemporaryDirectory(prefix='.pilot-export-',dir=target.parent) as tmp:
        stage=Path(tmp)/'result';stage.mkdir(mode=0o700)
        value=evaluation.package([record['evaluation_result']])
        files={'pilot-result.json':json.dumps(record,indent=2)+'\n','pilot-brief.txt':readable(record),'evaluation.json':json.dumps(value,indent=2)+'\n','REPORT.html':evaluation.report_html(value),'human-review.json':json.dumps(value['human_review'],indent=2)+'\n'}
        for name,text in files.items():
            path=stage/name
            with path.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
            path.chmod(0o600)
        if target.exists():raise ValueError('Export appeared concurrently')
        # The live batch lock owns this destination. Refuse prior result folders.
        target.mkdir(mode=0o700)
        for path in stage.iterdir():path.rename(target/path.name)


class AuditSession:
    def select(self,slot_id):self.slot_id=slot_id;slot(slot_id)
    def check(self):
        request=prepare(self.slot_id)
        self.checks=[{'decision':{'check':'pilot_source_binding_audit','purpose':'Revalidate fixed synthetic source/protocol and neutral wire bindings; never execute proposed research actions.',
                       'case_sha256':study.digest(get_case(self.slot_id)),'policy':'explicit_user_selected_local_check'},
                      'result':{'status':'completed','tool':'pilot_source_binding_audit','protocol_sha256':PROTOCOL_SHA256,'request_sha256':request['request_sha256'],'qualification':'Local consistency check only; not model usefulness or experimental validation.'}}]
    def view(self):return {'checks':deepcopy(self.checks)}


def helper():
    tools={s['id']:('pilot_source_binding_audit','Revalidate fixed synthetic source/protocol and neutral wire bindings; never execute proposed research actions.') for s in protocol()['slots']}
    return SimpleNamespace(Session=AuditSession,TOOLS=tools)


def summary(records):
    records=[validate_record(r) for r in records]
    if len({r['slot_id'] for r in records})!=len(records) or len({r['transport_qualification'] for r in records})>1:raise ValueError('Duplicate or mixed comparison results')
    lookup={r['slot_id']:r for r in records};orders=[];comparisons=[]
    def actions(r):return [a['action_id'] for a in r['evaluation_result']['answer']['actions']]
    for condition in ('UNVERIFIED','COMPLETED'):
        a=lookup.get(condition+'_O0');b=lookup.get(condition+'_O1')
        orders.append({'completion_condition':condition,'first_action_same':None if a is None or b is None else actions(a)[0]==actions(b)[0],
                       'full_action_order_same':None if a is None or b is None else actions(a)==actions(b)})
    for order in (0,1):
        a=lookup.get('UNVERIFIED_O'+str(order));b=lookup.get('COMPLETED_O'+str(order))
        comparisons.append({'presentation_order':order,'first_action_changed':None if a is None or b is None else actions(a)[0]!=actions(b)[0],
                            'completed_step_not_repeated':None if b is None else 'RNA_RECONCILE' not in actions(b),
                            'next_unresolved_step_first':None if b is None else actions(b)[0]!='RNA_RECONCILE'})
    return {'scored_slots':len(records),'expected_slots':4,'order_comparisons':orders,'completion_comparisons':comparisons,
            'metrics':[dict(slot_id=r['slot_id'],**pilot_metrics(r)) for r in records],'human_usefulness':'not_reviewed','criteria':protocol()['criteria'],'limits':protocol()['limits']}
