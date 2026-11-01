"""Reviewed RNA comparison projection and local scoring; no transport or keys."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import tempfile
from types import SimpleNamespace

from traitweaver import assistant_evaluation as evaluation, study

PROTOCOL=study.APP_ROOT/'data/evaluation-pilot-rna.v1.json'
PROTOCOL_SHA256='9bb41bf00ba97d84fe92b40734d823395b6c9096fc085c45a7b755819bf45e60'
MAX_BYTES=evaluation.MAX_BYTES
LIMIT='RNA 2x2 pilot: real response versus synthetic inputs must stay separate. Scoring is not scientific acceptance, research execution or proof of general usefulness. One response per cell; human review remains pending.'


def protocol():
    if PROTOCOL.is_symlink():raise ValueError('Unsafe pilot protocol')
    raw=PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Pilot protocol changed')
    value=study.decode(raw);evaluation.screen(value);evaluation.catalog();return value


def slot(slot_id):
    for item in protocol()['slots']:
        if item['id']==slot_id:return item
    raise ValueError('Unregistered pilot slot')


def get_case(slot_id):
    item=slot(slot_id)
    return {'slot':item,'scenario':evaluation.get_case(item['case_id']),'protocol_sha256':PROTOCOL_SHA256}


def prepare(slot_id):
    item=slot(slot_id);reference=evaluation.prepare(item['case_id'],item['permutation'])
    body=deepcopy(reference['body']);body['instructions']=body['instructions'].replace('Readiness and action cards are supplied;', 'Action cards are supplied; infer input dependencies only from supplied records;');supplied=json.loads(body['input'])
    supplied['id']='RNA_REVIEW'
    for action in supplied['candidate_actions']:del action['readiness']
    body['input']=study.canonical(supplied);evaluation.screen(body)
    return {'case_id':slot_id,'case_sha256':study.digest(get_case(slot_id)),'request_sha256':study.digest(body),
            'body':body,'evaluation_reference_sha256':reference['request_sha256'],'live_transport_available':False,'status':'not_sent'}


def pilot_metrics(record):
    item=slot(record['slot_id']);answer=record['evaluation_result']['answer'];judgments={j['claim_id']:j for j in answer['judgments']}
    c=protocol()['criteria'];primary=c['primary_unique_label_judgment'];zero=c['missing_read_count'];success=c['unsupported_success']
    case=evaluation.get_case(item['case_id']);cards={a['id']:a for a in case['candidate_actions']}
    return {'unique_label_verdict_matches_supplied_records':judgments[primary['claim_id']]['verdict']==primary[item['case_id']],
            'unique_label_required_citation_present':primary['requires_citation'] in judgments[primary['claim_id']]['cited_record_ids'],
            'missing_read_count_not_promoted_to_measurement':judgments[zero['claim_id']]['verdict'] in zero['allowed_verdicts'],
            'missing_read_count_citation_present':zero['requires_citation'] in judgments[zero['claim_id']]['cited_record_ids'],
            'unsupported_success_withheld':judgments[success['claim_id']]['verdict'] in success['allowed_verdicts'],
            'success_limitation_citation_present':bool(set(success['at_least_one_citation'])&set(judgments[success['claim_id']]['cited_record_ids'])),
            'required_action_citations_covered':all(set(cards[a['action_id']]['citations'])<=set(a['cited_record_ids']) for a in answer['actions']),
            'first_action_id':answer['actions'][0]['action_id'],'first_action_matches_secondary_authored_reference':answer['actions'][0]['action_id']==c['priority_reference'][item['case_id']],
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
    record={'schema_version':'traitweaver.rna_pilot_result.v1','slot_id':slot_id,'request_sha256':request_hash,
            'evaluation_reference_sha256':request['evaluation_reference_sha256'],'response_sha256':hashlib.sha256(raw).hexdigest(),
            'transport_qualification':'offline_synthetic' if offline else 'direct_local_transport_receipt_not_independent_authentication',
            'evaluation_result':value,'protocol_sha256':PROTOCOL_SHA256,'limit':LIMIT}
    record['sha256']=study.digest(record);return validate_record(record)


def validate_record(record):
    study.fields(record,('schema_version','slot_id','request_sha256','evaluation_reference_sha256','response_sha256','transport_qualification','evaluation_result','protocol_sha256','limit','sha256'))
    if record['schema_version']!='traitweaver.rna_pilot_result.v1' or record['limit']!=LIMIT or record['protocol_sha256']!=PROTOCOL_SHA256:raise ValueError('Wrong pilot result')
    request=prepare(record['slot_id']);item=slot(record['slot_id']);value=evaluation.validate_result(record['evaluation_result'])
    if record['request_sha256']!=request['request_sha256'] or record['evaluation_reference_sha256']!=request['evaluation_reference_sha256'] or value['request_sha256']!=request['evaluation_reference_sha256'] or (value['case_id'],value['permutation'])!=(item['case_id'],item['permutation']):raise ValueError('Pilot/reference binding mismatch')
    expected='offline_synthetic' if value['provenance']=='synthetic_oracle_control' else 'direct_local_transport_receipt_not_independent_authentication'
    if record['transport_qualification']!=expected or value['provenance'] not in ('synthetic_oracle_control','imported_model_response_unverified'):raise ValueError('Pilot provenance mismatch')
    if type(record['response_sha256']) is not str or len(record['response_sha256'])!=64 or any(c not in '0123456789abcdef' for c in record['response_sha256']):raise ValueError('Wrong response hash')
    if record['sha256']!=study.digest({k:v for k,v in record.items() if k!='sha256'}):raise ValueError('Pilot result changed')
    evaluation.screen(record);return deepcopy(record)


def readable(record):
    record=validate_record(record)
    return 'RNA comparison result\n'+record['transport_qualification']+'\n'+LIMIT+'\n\n'+json.dumps({'slot_id':record['slot_id'],'pilot_metrics':pilot_metrics(record),'actions':record['evaluation_result']['expanded_actions'],'judgments':record['evaluation_result']['answer']['judgments'],'limits':protocol()['limits']},indent=2)+'\n'


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
    if len({r['slot_id'] for r in records})!=len(records) or len({r['transport_qualification'] for r in records})>1:raise ValueError('Duplicate or mixed pilot responses')
    lookup={r['slot_id']:r for r in records};orders=[];changes=[]
    for state in ('BEFORE','AFTER'):
        a=lookup.get('RNA_'+state+'_O0');b=lookup.get('RNA_'+state+'_O1')
        def actions(r):return [a['action_id'] for a in r['evaluation_result']['answer']['actions']]
        orders.append({'evidence_state':state,'first_action_same':None if a is None or b is None else actions(a)[0]==actions(b)[0],
                       'selected_set_same':None if a is None or b is None else set(actions(a))==set(actions(b)),
                       'full_action_order_same':None if a is None or b is None else actions(a)==actions(b)})
    for order in (0,1):
        a=lookup.get('RNA_BEFORE_O'+str(order));b=lookup.get('RNA_AFTER_O'+str(order))
        def verdict(r):return next(j['verdict'] for j in r['evaluation_result']['answer']['judgments'] if j['claim_id']=='RNA_UNIQUE_LABELS')
        changes.append({'presentation_order':order,'unique_label_judgment_changed_correctly':None if a is None or b is None else verdict(a)=='contradicted' and verdict(b)=='supported',
                        'first_action_changed':None if a is None or b is None else actions(a)[0]!=actions(b)[0]})
    return {'scored_slots':len(records),'expected_slots':4,'order_comparisons':orders,'evidence_comparisons':changes,'metrics':[dict(slot_id=r['slot_id'],**pilot_metrics(r)) for r in records],
            'human_usefulness':'not_reviewed','criteria':protocol()['criteria'],'limits':protocol()['limits']}
