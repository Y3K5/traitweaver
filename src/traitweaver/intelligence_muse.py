"""Typed offline Muse boundary for molecular reasoning. Intentionally no transport."""
from copy import deepcopy
import hashlib
import itertools

from traitweaver import intelligence as model, study
from traitweaver.study_store import screen_export

MODEL='muse-spark-1.3'
DESTINATION='https://api.meta.ai/v1/responses'
MAX_RESPONSE=262144
RATIONALES={'trait_evidence_audit':'Audit the trait association, exact identities and endpoint gaps without claiming necessity or sufficiency.',
            'combination_coverage':'Audit candidate roles and admitted pair evidence before interpreting a protein combination.',
            'transfer_coverage':'Audit recipient identity and context compatibility before interpreting function transfer.'}
CLAIMS={'trait_evidence_audit':['publication_association_only','necessity_unknown','sufficiency_unknown'],
        'combination_coverage':['additional_identities_unavailable','combination_effect_unknown'],
        'transfer_coverage':['recipient_function_unqualified','transfer_success_unknown']}


def validate_phase(state,phase):
    c=model.active(state)
    if state['context'] is None:raise ValueError('Save the intelligence scope and owning context first')
    if phase=='selection':
        if c and c['assessment'] is None:raise ValueError('Finish or deliberately supersede the current intelligence cycle')
    elif phase=='reassessment':
        if c is None or c['result'] is None or c['assessment'] is not None:raise ValueError('Reassessment requires one current unassessed result')
    else:raise ValueError('Unknown intelligence reasoning phase')


def response_schema(state,phase,bundle):
    p={'citations':{'type':'array','items':{'type':'string','enum':sorted(bundle['claims'])},'minItems':1,'maxItems':len(bundle['claims'])}}
    if phase=='selection':
        p.update({'check':{'type':'string','enum':list(model.CHECKS)},'arguments':{'type':'object','properties':{
            k:{'type':'null' if v is None else ('number' if type(v) in (int,float) else 'string'),'enum':[v]} for k,v in state['scope'].items()},'required':sorted(state['scope']),'additionalProperties':False},
            'claim_codes':{'type':'array','items':{'type':'string','enum':sorted({x for values in CLAIMS.values() for x in values})},'minItems':2,'maxItems':3}})
    else:
        c=model.active(state)
        p.update({'result_id':{'type':'string','enum':[c['result']['id']]},'outcome':{'type':'string','enum':[c['result']['outcome']]},
                  'next_action':{'type':'string','enum':['researcher_review_measurement_plan']}})
    return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}


def prepare(state,phase,bundle,focus='trait'):
    validate_phase(state,phase)
    if not isinstance(focus,str) or focus not in model.FOCI:raise ValueError('Unknown intelligence review focus')
    c=model.active(state)
    public={'review_state_sha256':study.digest(state),'catalog_sha256':study.digest(bundle),'scope':deepcopy(state['scope']),'preferred_focus':focus,'candidate_catalog':deepcopy(bundle['candidates']),
            'claims':deepcopy(bundle['claims']),'public_literature':deepcopy(bundle['literature']),
            'reference_mapping':None if bundle['reference'] is None else {'maps':deepcopy(bundle['reference']['transcript_maps']),'source_manifest':deepcopy(bundle['reference']['sources']),'record_status':bundle['reference']['record_status']},
            'recipients':deepcopy(bundle['recipients']),'combination_templates':deepcopy(bundle['combination_templates']),
            'eligible_checks':deepcopy(model.CHECKS),'result':deepcopy(c['result']) if phase=='reassessment' else None,'limit':model.LIMIT}
    body={'model':MODEL,'store':False,'max_output_tokens':1024,
          'instructions':'Review only the supplied public evidence and choose one registered check, or reassess its supplied result. Use only the exact registered identities, citations, arguments and claim codes in the structured schema. Publication association does not establish necessary/sufficient proteins. Do not invent additional proteins, combination effects, species compatibility, success probabilities, rankings or experimental results. Return one structured object. No executable biological design or arbitrary tool calls.',
          'input':study.canonical(public),'text':{'format':{'type':'json_schema','name':'traitweaver_molecular_'+phase,'strict':True,'schema':response_schema(state,phase,bundle)}}}
    screen_export(body)
    if len(study.canonical(body).encode())>49152:raise ValueError('Prepared intelligence payload exceeds its bound; nothing truncated or sent')
    return {'schema_version':'traitweaver.intelligence_request.v1','phase':phase,'focus':focus,'state_sha256':study.digest(state),'catalog_sha256':study.digest(bundle),
            'destination':DESTINATION,'body':body,'request_sha256':study.digest(body),'status':'not_sent','live_transport_available':False,
            'review_notice':'Public evidence and controlled scope only; no study notes, raw model history or machine paths. No credential access or transport exists in this boundary. Live use requires separate review.'}


def validate_proposal(state,phase,p,bundle):
    validate_phase(state,phase);study.fields(p,response_schema(state,phase,bundle)['required'])
    citations=p['citations']
    if not isinstance(citations,list) or not citations or any(not isinstance(x,str) or x not in bundle['claims'] for x in citations) or len(set(citations))!=len(citations):raise ValueError('Unknown, missing or duplicate intelligence citations')
    if phase=='selection':
        check=p['check']
        model.validate_scope(p['arguments'])
        if not isinstance(check,str) or check not in model.CHECKS or study.canonical(p['arguments'])!=study.canonical(state['scope']):raise ValueError('Unavailable intelligence action or altered scope arguments')
        if p['claim_codes']!=CLAIMS[check]:raise ValueError('Claim exceeds the admitted molecular evidence')
    else:
        c=model.active(state);check=c['decision']['check']
        if p['result_id']!=c['result']['id'] or p['outcome']!=c['result']['outcome'] or p['next_action']!='researcher_review_measurement_plan':raise ValueError('Reassessment exceeds the actual intelligence result')
    if not set(model.required_citations(check,bundle))<=set(citations):raise ValueError('Decision lacks the required source/qualification citations')
    return deepcopy(p)


def synthetic_reply(state,phase,bundle,focus):
    prepare(state,phase,bundle,focus)
    if phase=='selection':
        check=model.FOCI[focus];proposal={'check':check,'arguments':deepcopy(state['scope']),'claim_codes':deepcopy(CLAIMS[check]),'citations':model.required_citations(check,bundle)}
    else:
        c=model.active(state);proposal={'result_id':c['result']['id'],'outcome':c['result']['outcome'],'next_action':'researcher_review_measurement_plan','citations':model.required_citations(c['decision']['check'],bundle)}
    return {'model':MODEL,'status':'completed','traitweaver_synthetic':True,'output':[{'type':'message','content':[{'type':'output_text','text':study.canonical(proposal)}]}]}


def parse_reply(state,phase,raw,request_hash,bundle,focus):
    prepared=prepare(state,phase,bundle,focus)
    if request_hash!=prepared['request_sha256']:raise ValueError('Reply does not match the prepared public intelligence request')
    if not isinstance(raw,bytes) or len(raw)>MAX_RESPONSE:raise ValueError('Saved intelligence reply is oversized or unsupported')
    reply=study.decode(raw);screen_export(reply)
    if not isinstance(reply,dict) or reply.get('model')!=MODEL or reply.get('status')!='completed':raise ValueError('Wrong model, incomplete reply or refusal')
    if not isinstance(reply.get('output'),list):raise ValueError('Expected typed response output')
    texts=[]
    for item in reply['output']:
        if not isinstance(item,dict):raise ValueError('Malformed response item')
        if item.get('type')=='reasoning':continue
        if item.get('type')!='message' or not isinstance(item.get('content'),list):raise ValueError('Unexpected provider action; no tool executed')
        for block in item['content']:
            if not isinstance(block,dict) or block.get('type')!='output_text' or not isinstance(block.get('text'),str):raise ValueError('Refusal or unsupported response content')
            texts.append(block['text'])
    if len(texts)!=1:raise ValueError('Expected one structured intelligence proposal')
    proposal=validate_proposal(state,phase,study.decode(texts[0]),bundle)
    usage=reply.get('usage');typed=None
    if usage is not None:
        if not isinstance(usage,dict):raise ValueError('Malformed usage')
        typed={k:usage.get(k) for k in ('input_tokens','output_tokens','total_tokens')}
        if any(type(x) is not int or not 0<=x<=10000000 for x in typed.values()) or typed['output_tokens']>1024 or typed['total_tokens']!=typed['input_tokens']+typed['output_tokens']:raise ValueError('Unsupported usage or output-token ceiling exceeded')
    receipt={'reported_model':MODEL,'response_sha256':hashlib.sha256(raw).hexdigest(),'provenance':'synthetic_fixture' if reply.get('traitweaver_synthetic') is True else 'owner_imported_authenticity_unverified','reported_usage':typed,'cost_usd':None,'transport_calls':0}
    return {'phase':phase,'focus':focus,'request_sha256':request_hash,'proposal':proposal,'receipt':receipt}


def historical_request_matches(state,p,bundle):
    """Early local records used insertion order in schema arrays; never rewrite them.

    Only array order varies. Public body, source/state hashes, arguments, claim
    ceilings and typed proposals must still match. New response admission uses
    the deterministic current request exclusively.
    """
    body=prepare(state,p['phase'],bundle,p['focus'])['body']
    schema=body['text']['format']['schema']
    order=['C_PSR1_PATH','C_ENDPOINTS','C_COMBINATION_GAP','C_RECIPIENT_GAP','C_STRAIN_CONTEXT','C_REFERENCE_IDENTITY','C_REFERENCE_SEQUENCE']
    schema['properties']['citations']['items']['enum']=[x for x in order if x in bundle['claims']]
    if p['phase']=='reassessment':return study.digest(body)==p['request_sha256']
    for keys in itertools.permutations(sorted(state['scope'])):
        schema['properties']['arguments']['required']=list(keys)
        if study.digest(body)==p['request_sha256']:return True
    return False


def validate_accept(state,p,bundle,allow_historical_order=False):
    study.fields(p,('phase','focus','request_sha256','proposal','receipt'))
    if p['request_sha256']!=prepare(state,p['phase'],bundle,p['focus'])['request_sha256']:
        if not allow_historical_order or not historical_request_matches(state,p,bundle):raise ValueError('Stale intelligence request')
    validate_proposal(state,p['phase'],p['proposal'],bundle)
    r=p['receipt'];study.fields(r,('reported_model','response_sha256','provenance','reported_usage','cost_usd','transport_calls'))
    if r['reported_model']!=MODEL or r['provenance'] not in ('synthetic_fixture','owner_imported_authenticity_unverified') or r['cost_usd'] is not None or type(r['transport_calls']) is not int or r['transport_calls']!=0:raise ValueError('Unsupported intelligence receipt')
    if not isinstance(r['response_sha256'],str) or len(r['response_sha256'])!=64 or any(c not in 'abcdef0123456789' for c in r['response_sha256']):raise ValueError('Invalid response fingerprint')
    u=r['reported_usage']
    if u is not None:
        study.fields(u,('input_tokens','output_tokens','total_tokens'))
        if any(type(x) is not int or not 0<=x<=10000000 for x in u.values()) or u['output_tokens']>1024 or u['total_tokens']!=u['input_tokens']+u['output_tokens']:raise ValueError('Invalid typed usage')
    screen_export(p)
