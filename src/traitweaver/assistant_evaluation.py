"""Open synthetic evaluation, separate from the unchanged assistant v1 contract.

No transport, credentials, arbitrary source importer or research/tool execution.
Authored rubric agreement and human usefulness judgments remain separate.
"""
from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import hashlib
import html
import json
import re

from traitweaver import assistant, assistant_workspace, study, study_store

CATALOG=study.APP_ROOT/'data/assistant-evaluation.v1.json'
CATALOG_SHA256='b802783f882f6cd907acc4c0c636960923a299f2aebe3072f3796e526fc61ffc'
SCHEMA='traitweaver.assistant_evaluation_result.v1'
PACKAGE='traitweaver.assistant_evaluation_package.v1'
LIMIT='Open authored synthetic evaluation, not a hidden benchmark or independent scientific validation. Offline controls are not Muse responses. No action, model, tool, experiment, installation or arbitrary project is executed.'
DIMENSIONS={
 'relevance':'0: misses the question; 1: partly relevant; 2: directly addresses the decision.',
 'feasibility':'0: assumes unavailable input/approval; 1: partly actionable; 2: clearly separates now from blocked work.',
 'priority':'0: misses the first blocker; 1: defensible but weak order; 2: addresses the most useful dependency first.',
 'completion_check':'0: cannot determine completion; 1: partly specific; 2: concrete deliverable and verifiable completion.',
 'source_entailment':'0: contradicts/promotes evidence; 1: support uncertain; 2: cited records support the interpretation with limits.'}
MAX_BYTES=512*1024


def read_json(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Missing, unsafe or oversized evaluation file')
    return study.decode(path.read_bytes())


def screen(value):
    study_store.screen_export(value)
    raw=study.canonical(value)
    if re.search(r'(?i)(?:api[_ -]?key|password|client[_ -]?secret|authorization|cookie)\s*[:=]\s*\S+|\b(?:confidential|internal-only|private research)\b',raw):
        raise ValueError('Evaluation requires privacy review; no content was removed')


def catalog():
    if CATALOG.is_symlink():raise ValueError('Unsafe evaluation catalog')
    raw=CATALOG.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA256:raise ValueError('Evaluation catalog changed; no fallback or retrieval')
    value=study.decode(raw);screen(value)
    if value['schema_version']!='traitweaver.assistant_evaluation_catalog.v1' or len(value['cases'])!=12:raise ValueError('Unsupported evaluation catalog')
    return value


def get_case(case_id):
    for case in catalog()['cases']:
        if case['id']==case_id:return deepcopy(case)
    raise ValueError('Unknown evaluation case')


def ordered_actions(case,permutation):
    if type(permutation) is not int or permutation not in (0,1,2):raise ValueError('Unknown action permutation')
    actions=deepcopy(case['candidate_actions'])
    return (actions,list(reversed(actions)),actions[1:]+actions[:1])[permutation]


def response_schema(case):
    def ids(values):return {'type':'array','items':{'type':'string','enum':values},'minItems':1,'maxItems':len(values)}
    records=[r['id'] for r in case['records']]
    claim={'type':'object','properties':{'claim_id':{'type':'string','enum':[c['id'] for c in case['candidate_claims']]},'verdict':{'type':'string','enum':['supported','unknown','contradicted']},'cited_record_ids':ids(records)},'required':['claim_id','verdict','cited_record_ids'],'additionalProperties':False}
    action={'type':'object','properties':{'action_id':{'type':'string','enum':[a['id'] for a in case['candidate_actions']]},'rationale':{'type':'string','minLength':1,'maxLength':320},'cited_record_ids':ids(records)},'required':['action_id','rationale','cited_record_ids'],'additionalProperties':False}
    return {'type':'object','properties':{'judgments':{'type':'array','items':claim,'minItems':len(case['candidate_claims']),'maxItems':len(case['candidate_claims'])},'actions':{'type':'array','items':action,'minItems':3,'maxItems':3}},'required':['judgments','actions'],'additionalProperties':False}


def prepare(case_id,permutation=0):
    case=get_case(case_id)
    supplied={k:deepcopy(case[k]) for k in ('id','area','question','input_kind','records','candidate_claims','limits')}
    supplied['candidate_actions']=ordered_actions(case,permutation)
    body={'model':assistant.MODEL,'store':False,'max_output_tokens':8192,
          'instructions':'Evaluate only these explicitly synthetic records. Judge every candidate claim as supported, unknown or contradicted, citing exact record IDs. Choose exactly three distinct documentation/data-check actions in priority order; explain each briefly with citations. Resolve the most relevant evidence blocker first. Readiness and action cards are supplied; do not invent inputs, promote predictions, substitute endpoints, treat missing as zero, or claim completed science. No scripts, biological designs or laboratory protocols. Return only the structured format. This is an open evaluation; no action executes.',
          'input':study.canonical(supplied),'text':{'format':{'type':'json_schema','name':'traitweaver_evaluation_v1','strict':True,'schema':response_schema(case)}}}
    screen(body)
    return {'schema_version':'traitweaver.assistant_evaluation_request.v1','case_id':case_id,'permutation':permutation,'catalog_sha256':CATALOG_SHA256,
            'destination':assistant.DESTINATION,'body':body,'request_sha256':study.digest(body),'status':'not_sent','live_transport_available':False,'spend_authorized_usd':0,'limit':LIMIT}


def validate_answer(case,answer):
    study.fields(answer,('judgments','actions'))
    known={r['id'] for r in case['records']}
    def citations(values):
        if not isinstance(values,list) or not values or any(type(v) is not str for v in values) or len(values)!=len(set(values)) or not set(values)<=known:raise ValueError('Unknown, duplicate or absent evaluation citations')
    judgments=answer['judgments'];actions=answer['actions']
    if not isinstance(judgments,list) or len(judgments)!=len(case['candidate_claims']):raise ValueError('Every candidate claim needs one judgment')
    seen=[]
    for value in judgments:
        study.fields(value,('claim_id','verdict','cited_record_ids'))
        if value['verdict'] not in ('supported','unknown','contradicted'):raise ValueError('Invalid evaluation verdict')
        citations(value['cited_record_ids']);seen.append(value['claim_id'])
    if any(type(v) is not str for v in seen) or len(set(seen))!=len(seen) or set(seen)!={c['id'] for c in case['candidate_claims']}:raise ValueError('Missing, duplicated or unknown claim')
    if not isinstance(actions,list) or len(actions)!=3:raise ValueError('Three distinct actions required')
    seen=[]
    for action in actions:
        study.fields(action,('action_id','rationale','cited_record_ids'))
        study.text(action['rationale'],320);citations(action['cited_record_ids']);seen.append(action['action_id'])
    if any(type(v) is not str for v in seen) or len(set(seen))!=3 or not set(seen)<={a['id'] for a in case['candidate_actions']}:raise ValueError('Unavailable or duplicate action')
    screen(answer)
    return deepcopy(answer)


def grade(case_id,permutation,answer,request_sha256,provenance):
    preview=prepare(case_id,permutation)
    if request_sha256!=preview['request_sha256']:raise ValueError('Stale or changed evaluation request')
    if provenance not in ('synthetic_oracle_control','synthetic_supplied_order_control','synthetic_false_certainty_control','imported_model_response_unverified'):raise ValueError('Unqualified evaluation provenance')
    case=get_case(case_id);answer=validate_answer(case,answer);rubric=case['rubric'];actions={a['id']:a for a in case['candidate_actions']}
    judged={j['claim_id']:j for j in answer['judgments']}
    checks=[]
    for claim_id,expected in rubric['claim_judgments'].items():
        got=judged[claim_id]
        checks.append({'claim_id':claim_id,'expected':expected['verdict'],'observed':got['verdict'],
                       'verdict_agrees':got['verdict']==expected['verdict'],'required_citations_present':set(expected['required_record_ids'])<=set(got['cited_record_ids'])})
    selected=[dict(priority=n,**deepcopy(actions[a['action_id']]),model_rationale=a['rationale'],model_citations=a['cited_record_ids']) for n,a in enumerate(answer['actions'],1)]
    auto={'first_action_matches_authored_rubric':selected[0]['id']==rubric['first_action_id'],
          'first_action_ready_now':selected[0]['readiness']=='now','claim_checks':checks,
          'claim_verdict_agreement_count':sum(c['verdict_agrees'] for c in checks),'claim_count':len(checks),
          'all_required_claim_citations_present':all(c['required_citations_present'] for c in checks),
          'action_citations_match_cards':all(set(a['cited_record_ids'])==set(actions[a['action_id']]['citations']) for a in answer['actions']),
          'unsupported_success_withheld':judged[case_id.split('_')[0]+'_SUCCESS']['verdict']!='supported',
          'scientific_entailment':'not_automatically_established'}
    result={'schema_version':SCHEMA,'case_id':case_id,'permutation':permutation,'request_sha256':request_sha256,'catalog_sha256':CATALOG_SHA256,
            'provenance':provenance,'answer':answer,'expanded_actions':selected,'automated':auto,'human_review':{'status':'not_reviewed','scores':{k:None for k in DIMENSIONS},'notes':''},'limit':LIMIT}
    result['sha256']=study.digest(result);screen(result);return result


def validate_result(result):
    fields=('schema_version','case_id','permutation','request_sha256','catalog_sha256','provenance','answer','expanded_actions','automated','human_review','limit','sha256')
    study.fields(result,fields)
    if result['schema_version']!=SCHEMA:raise ValueError('Wrong evaluation version')
    expected=grade(result['case_id'],result['permutation'],result['answer'],result['request_sha256'],result['provenance'])
    if study.canonical(result)!=study.canonical(expected):raise ValueError('Altered score, actions, provenance or package hash')
    return deepcopy(result)


def control(case_id,permutation=0,kind='oracle'):
    case=get_case(case_id);expected=case['rubric']['claim_judgments']
    judgments=[{'claim_id':c['id'],'verdict':expected[c['id']]['verdict'],'cited_record_ids':expected[c['id']]['required_record_ids']} for c in case['candidate_claims']]
    actions=ordered_actions(case,permutation) if kind=='supplied_order' else sorted(case['candidate_actions'],key=lambda a:(a['id']!=case['rubric']['first_action_id'],a['id']))
    if kind=='false_certainty':
        for j in judgments:j['verdict']='supported'
    if kind not in ('oracle','supplied_order','false_certainty'):raise ValueError('Unknown synthetic control')
    answer={'judgments':judgments,'actions':[{'action_id':a['id'],'rationale':'Synthetic control only; not model reasoning or a research result.','cited_record_ids':a['citations']} for a in actions[:3]]}
    provenance={'oracle':'synthetic_oracle_control','supplied_order':'synthetic_supplied_order_control','false_certainty':'synthetic_false_certainty_control'}[kind]
    return grade(case_id,permutation,answer,prepare(case_id,permutation)['request_sha256'],provenance)


def parse_reply(case_id,permutation,raw,request_sha256):
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ValueError('Bounded reply required')
    reply=study.decode(raw)
    if not isinstance(reply,dict) or reply.get('model')!=assistant.MODEL or reply.get('status')!='completed':raise ValueError('Wrong model or incomplete/refused evaluation')
    if 'traitweaver_synthetic' in reply:raise ValueError('Use explicit synthetic-control command; never relabel a fixture as model work')
    outputs=reply.get('output');texts=[]
    if not isinstance(outputs,list):raise ValueError('Typed evaluation output required')
    for item in outputs:
        if not isinstance(item,dict):raise ValueError('Malformed output')
        if item.get('type')=='reasoning':continue
        if item.get('type')!='message' or not isinstance(item.get('content'),list):raise ValueError('Tools and unknown outputs forbidden')
        for block in item['content']:
            if not isinstance(block,dict) or block.get('type')!='output_text' or not isinstance(block.get('text'),str):raise ValueError('Refusal or unsupported content')
            texts.append(block['text'])
    if len(texts)!=1:raise ValueError('Exactly one structured answer required')
    return grade(case_id,permutation,study.decode(texts[0].encode()),request_sha256,'imported_model_response_unverified')


def summarize(results):
    values=[validate_result(r) for r in results]
    if len({r['provenance'] for r in values})>1:raise ValueError('Never pool synthetic controls or imported-model results in one metric')
    keys=[(r['case_id'],r['permutation']) for r in values]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate case/permutation results')
    lookup={k:v for k,v in zip(keys,values)};pairs=[];orders=[]
    for case in catalog()['cases']:
        if case['phase']=='before':
            for perm in range(3):
                a=lookup.get((case['id'],perm));z=lookup.get((case['family_id']+'_AFTER',perm))
                pairs.append({'family_id':case['family_id'],'permutation':perm,'expected_first_action_change':True,
                              'observed_change':None if a is None or z is None else a['answer']['actions'][0]['action_id']!=z['answer']['actions'][0]['action_id'],
                              'both_first_actions_match_rubric':None if a is None or z is None else a['automated']['first_action_matches_authored_rubric'] and z['automated']['first_action_matches_authored_rubric']})
        group=[lookup.get((case['id'],perm)) for perm in range(3)]
        orders.append({'case_id':case['id'],'first_action_consistent':None if any(v is None for v in group) else len({v['answer']['actions'][0]['action_id'] for v in group})==1})
    return {'scored_responses':len(values),'expected_requests_for_one_complete_evaluation':36,'first_action_rubric_matches':sum(r['automated']['first_action_matches_authored_rubric'] for r in values),
            'first_actions_ready_now':sum(r['automated']['first_action_ready_now'] for r in values),
            'claim_verdict_rubric_matches':sum(r['automated']['claim_verdict_agreement_count'] for r in values),
            'claim_judgments':sum(r['automated']['claim_count'] for r in values),'unsupported_successes_withheld':sum(r['automated']['unsupported_success_withheld'] for r in values),
            'evidence_change_pairs':pairs,'order_variants':orders,'human_usefulness':'not_reviewed','limits':LIMIT}


def review_template(results):
    return {'schema_version':'traitweaver.evaluation_human_review.v1','rubric':DIMENSIONS,'status':'not_reviewed','rows':[{'case_id':r['case_id'],'permutation':r['permutation'],'request_sha256':r['request_sha256'],'scores':{k:None for k in DIMENSIONS},'notes':''} for r in results],
            'limit':'Human scores are separate from automation. This local review is never part of model inputs or publishing approval.'}


def validate_human_review(value,results):
    study.fields(value,('schema_version','rubric','status','rows','limit'))
    expected=review_template(results)
    if value['schema_version']!=expected['schema_version'] or value['rubric']!=DIMENSIONS or value['limit']!=expected['limit']:raise ValueError('Unknown human rubric')
    if not isinstance(value['rows'],list) or len(value['rows'])!=len(expected['rows']):raise ValueError('Missing human review rows')
    any_score=False
    for row,identity in zip(value['rows'],expected['rows']):
        study.fields(row,('case_id','permutation','request_sha256','scores','notes'))
        if any(row[k]!=identity[k] for k in ('case_id','permutation','request_sha256')):raise ValueError('Stale or reordered human review')
        study.fields(row['scores'],tuple(DIMENSIONS))
        for score in row['scores'].values():
            if score is not None and (type(score) is not int or not 0<=score<=2):raise ValueError('Human score must be null, zero, one or two')
            any_score|=score is not None
        if type(row['notes']) is not str or len(row['notes'])>1000:raise ValueError('Bounded reviewer notes required')
    if value['status']!=('partially_or_fully_scored' if any_score else 'not_reviewed'):raise ValueError('Human review status disagrees with scores')
    screen(value);return deepcopy(value)


def package(results,human_review=None):
    results=[validate_result(r) for r in results]
    human=validate_human_review(human_review or review_template(results),results)
    summary=summarize(results);summary['human_usefulness']=human['status']
    value={'schema_version':PACKAGE,'catalog_sha256':CATALOG_SHA256,'catalog':catalog(),'results':results,'summary':summary,
           'human_review':human,'limit':LIMIT}
    value['sha256']=study.digest(value);screen(value);return value


def reopen(value):
    study.fields(value,('schema_version','catalog_sha256','catalog','results','summary','human_review','limit','sha256'))
    if value['schema_version']!=PACKAGE:raise ValueError('Unsupported evaluation package')
    expected=package(value['results'],value['human_review'])
    if study.canonical(value)!=study.canonical(expected):raise ValueError('Changed evaluation evidence, score or receipt')
    return deepcopy(value)


def historical_batch(folder):
    """Only known accepted exports/receipts are read; no controls or raw replies."""
    folder=Path(folder);rows=[];batch_identity=None
    if folder.is_symlink() or not folder.is_dir():raise ValueError('Unsafe batch directory')
    for case in assistant.catalog()['cases']:
        cid=case['case_id'];directory=folder/cid
        if directory.is_symlink():raise ValueError('Unsafe case directory')
        record=assistant.validate_package(read_json(directory/'assistant-review.json'))
        receipt=read_json(directory/'BATCH_RECEIPT.json')
        required=('schema_version','case_id','approval_sha256','request_sha256','response_sha256','transport','core_request_sha256','wire_override','reported_model','reported_usage','estimated_cost_usd','actual_provider_charge_usd','local_checks','core_provenance_limit','qualification')
        study.fields(receipt,required);screen(receipt)
        if type(receipt['approval_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',receipt['approval_sha256']):raise ValueError('Invalid batch identity')
        if batch_identity is None:batch_identity=receipt['approval_sha256']
        elif receipt['approval_sha256']!=batch_identity:raise ValueError('Mixed historical batches')
        if receipt['schema_version']!='traitweaver.assistant_batch_receipt.v2' or receipt['case_id']!=cid or receipt['reported_model']!=assistant.MODEL or receipt['actual_provider_charge_usd'] is not None:raise ValueError('Unsupported receipt')
        if receipt['transport']!='direct_meta_transport' or record['receipt']['provenance']!='owner_imported_reply_authenticity_unverified':raise ValueError('Not a saved direct-transport review')
        if receipt['response_sha256']!=record['receipt']['response_sha256'] or receipt['core_request_sha256']!=record['request_sha256']:raise ValueError('Receipt mismatch')
        usage=receipt['reported_usage']
        study.fields(usage,('input_tokens','output_tokens','total_tokens','reasoning_tokens','cached_tokens'))
        for key in ('input_tokens','output_tokens','total_tokens'):
            if type(usage[key]) is not int or not 0<=usage[key]<=1_000_000_000 or usage[key]!=record['receipt']['reported_usage'][key]:raise ValueError('Invalid historical usage')
        if usage['total_tokens']!=usage['input_tokens']+usage['output_tokens'] or usage['output_tokens']>8192:raise ValueError('Invalid usage total')
        for key,parent in [('reasoning_tokens','output_tokens'),('cached_tokens','input_tokens')]:
            if usage[key] is not None and (type(usage[key]) is not int or not 0<=usage[key]<=usage[parent]):raise ValueError('Invalid nested usage')
        cost=receipt['estimated_cost_usd']
        if type(cost) is not str or not re.fullmatch(r'\d+(?:\.\d+)?',cost) or Decimal(cost)!=(Decimal(usage['input_tokens'])*Decimal('1.25')+Decimal(usage['output_tokens'])*Decimal('4.25'))/1_000_000:raise ValueError('Historical cost differs from approved rate estimate')
        if receipt['wire_override']!={'max_output_tokens':8192}:raise ValueError('Unqualified wire budget')
        body=assistant.prepare(cid)['body'];body['max_output_tokens']=8192
        if receipt['request_sha256']!=study.digest(body):raise ValueError('Changed historical wire payload')
        text=directory/'assistant-review.txt'
        if text.is_symlink() or text.stat().st_size>MAX_BYTES or text.read_text()!=assistant.readable(record):raise ValueError('Readable export differs')
        checks=assistant_workspace.validate_checks(cid,receipt['local_checks'])
        rows.append({'case_id':cid,'input_kind':case['input_kind'],'saved_model_reply':'local_direct_transport_receipt; independently_unverified',
                     'claim_and_action_contract':'exact_v1_catalog_preserved','local_audits':len(checks),
                     'action_order_unchanged':[a['id'] for a in record['actions']]==[a['id'] for a in case['actions']],
                     'reported_usage':deepcopy(usage),'estimated_cost_usd':cost,'actual_provider_charge_usd':None,
                     'position_bias':'not_tested_in_saved_batch','response_usefulness':'requires_human_review','biological_validation':False})
    return {'schema_version':'traitweaver.historical_batch_evaluation.v1','cases':rows,'new_model_or_tool_calls':0,
            'limit':'Saved four-case responses checked read-only. Valid fixed IDs and unchanged priorities do not establish useful reasoning, order robustness, independent provider authenticity or repeated-run reliability.'}


def report_html(value):
    value=reopen(value);summary=value['summary']
    page='<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Traitweaver evaluation</title><style>body{max-width:1100px;margin:32px auto;padding:20px;background:#02070a;color:#edf4f8;font:16px/1.6 system-ui}a,h1,h2{color:#0297de}strong{color:#fc734d}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #28404d}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}</style>'
    page+='<h1>Does the plan respond to the evidence?</h1><p><strong>'+html.escape(', '.join(sorted({r['provenance'] for r in value['results']})))+'</strong></p><p>'+html.escape(LIMIT)+'</p><p>Scored responses: '+str(summary['scored_responses'])+' · first actions matching authored rubric: '+str(summary['first_action_rubric_matches'])+' · claim labels matching authored rubric: '+str(summary['claim_verdict_rubric_matches'])+' / '+str(summary['claim_judgments'])+'. Human usefulness: '+html.escape(summary['human_usefulness'])+'.</p><p>Comparisons use before/after evidence pairs and three supplied-action orders. Expected judgments are excluded from requests; criteria remain openly inspectable. Automated agreement is not scientific entailment.</p><table><tr><th>Case</th><th>Order variant</th><th>First proposed action</th><th>Rubric match</th></tr>'
    for r in value['results']:
        page+='<tr><td>'+html.escape(r['case_id'])+'</td><td>'+str(r['permutation'])+'</td><td>'+html.escape(r['expanded_actions'][0]['task'])+'</td><td>'+str(r['automated']['first_action_matches_authored_rubric'])+'</td></tr>'
    page+='</table><h2>Inspect judgments, actions, limits and receipts</h2>'
    for r in value['results']:
        page+='<details><summary>'+html.escape(r['case_id'])+' / '+str(r['permutation'])+'</summary><pre>'+html.escape(json.dumps(r,indent=2))+'</pre></details>'
    page+='<h2>Exact synthetic inputs and open authored criteria</h2><details><summary>Inspect all scenario records, missing values and rubric</summary><pre>'+html.escape(json.dumps(value['catalog'],indent=2))+'</pre></details>'
    page+='<h2>Human review stays separate</h2><p>Score relevance, feasibility, priority, completion check and source entailment from 0 to 2 or leave unknown. No scores are filled automatically. A fluent explanation or correct source ID is not proof that the evidence supports the conclusion.</p><p><a href="evaluation.json">Versioned JSON package</a> · <a href="human-review.json">Human scoring template</a></p>'
    return page
