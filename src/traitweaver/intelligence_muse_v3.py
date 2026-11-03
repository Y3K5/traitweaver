"""Bounded, transport-free proposals informed by reviewed execution receipts.

This independent archive never becomes an execution approval. Existing v1, v2
and execution contracts remain unchanged; historical validation never dispatches.
"""
from copy import deepcopy
from functools import wraps
import hashlib
import threading

from traitweaver import intelligence as model, intelligence_continuation as continuation
from traitweaver import intelligence_execution as execution, intelligence_muse as v1
from traitweaver import intelligence_muse_v2 as v2, intelligence_store, study
from traitweaver.study_store import Conflict, MAX_BYTES, screen_export

REQUEST = 'traitweaver.intelligence_request.v3'
PACKAGE = 'traitweaver.intelligence_followup_review.v3'
PREVIEW = 'traitweaver.intelligence_followup_preview.v3'
MAX_REQUEST_BYTES = 131072
MAX_REVIEWS = 8
BASE_FIELDS = ('check', 'arguments', 'claim_codes', 'citations')
PROPOSAL_FIELDS = (*BASE_FIELDS, 'preview_sha256', 'check_input_sha256',
                   'reviewed_receipt_refs', 'unresolved_requirement_ids')
LIMIT = ('Proposal review only. No v1 decision, execution approval, local check or retry follows from this v3 record. '
         'References and structural validation do not prove source entailment, useful adaptation or scientific validity. '
         'Human receipt acknowledgment is distinct from model output. Imported execution records are not independently authenticated. '
         'No live transport, credential access or inherited spending approval. ' + model.LIMIT)


def _locked(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with self.mutex: return method(self,*args,**kwargs)
    return call


def _record_events(chain):
    result_events={}; review_events={}; start=None
    for event in chain:
        if event['kind']=='approve': start=None
        elif event['kind']=='started': start=event['hash']
        elif event['kind']=='result': result_events[start]=event['hash']
        elif event['kind']=='reassess': review_events[start]=event['hash']
    return result_events,review_events


def project(source, execution_package, bundle, context):
    """Reconstruct a public projection from both complete validated boundaries."""
    records=intelligence_store.validate_package(source,bundle)
    checked=execution.validate_package(execution_package,bundle)
    # Never inspect claimed hashes before the complete source histories validate.
    chains=execution._dominant([checked['events'],*checked['guard_histories']])
    chains=sorted(chains,key=lambda chain:(chain[0]['hash'],chain[-1]['hash']))
    prior=continuation.prepare(records,bundle,context); state=records[-1]['state']
    owned_hashes={event['hash'] for event in checked['events']}
    bridge=[]; requirements=[]; reserved=set(); unfinished=False
    for chain in chains:
        results,reviews=_record_events(chain)
        for cycle in execution._state(chain,bundle):
            approval=cycle['approval']; identity=approval['input_sha256']
            if execution._reserved(cycle): reserved.add(identity)
            if cycle['status'] in ('approved','retry_approved','started'): unfinished=True
            for attempt in cycle['attempts']:
                result=attempt['result']; review=attempt['review']
                if result is None or review is None: unfinished=True
                result_hash=results.get(attempt['start_hash']); review_hash=reviews.get(attempt['start_hash'])
                binding={'approval_event_hash':cycle['approval_id'],'start_hash':attempt['start_hash'],
                         'result_event_hash':result_hash,'result_id':None if result is None else result['id']}
                reference=None if result is None else 'RECEIPT_'+study.digest(binding)
                owned_result=bool(result is not None and all(h in owned_hashes for h in (cycle['approval_id'],attempt['start_hash'],result_hash)))
                owned_review=bool(owned_result and review is not None and review_hash in owned_hashes)
                owned_record=owned_result or (result is None and all(h in owned_hashes for h in (cycle['approval_id'],attempt['start_hash'])))
                accepted=approval['proposal_review']; receipt=accepted['receipt']
                current=(approval['lineage']['head_hash']==records[-1]['hash'] and
                         approval['lineage']['owning_context_sha256']==study.digest(context) and
                         study.canonical(approval['scope'])==study.canonical(state['scope']))
                bridge.append({'receipt_ref':reference,'origin':'owned_execution' if owned_record else 'imported_execution_authenticity_unverified',
                    'review_origin':None if review is None else 'owned_human_acknowledgment' if owned_review else 'imported_human_acknowledgment_unverified',
                    'owned_reviewed':owned_review,'source_relation':'owned_execution_events' if owned_record else 'imported_guard_history',
                    'approval_id':cycle['approval_id'],'start_hash':attempt['start_hash'],'result_event_hash':result_hash,
                    'review_event_hash':review_hash,'raw_result_id':None if result is None else result['id'],
                    'check':approval['check'],'scope':deepcopy(approval['scope']),'lineage':deepcopy(approval['lineage']),
                    'applicability':'current' if current else 'historical',
                    'proposal_review':{'proposal':deepcopy(accepted['proposal']),'provenance':receipt['provenance'],
                        'request_sha256':accepted['request_sha256'],'response_sha256':receipt['response_sha256'],
                        'receipt':{'reported_model':receipt['reported_model'],'provenance':receipt['provenance'],
                                   'response_sha256':receipt['response_sha256']},
                        'source_package_sha256':study.digest(cycle['review_package']['source_package']),
                        'qualification':'Original v2 references remain scoped to their archived source package.'},
                    'result':deepcopy(result),'human_review':deepcopy(review)})
                if result is not None:
                    for kind,texts in [('saved_result_blocker',result['blockers']),
                                       ('authored_measurement_requirement',result['measurement_plan']['unresolved'])]:
                        for index,text in enumerate(texts):
                            requirement={'receipt_ref':reference,'kind':kind,'index':index,'text':text}
                            requirements.append({'id':'REQ_'+study.digest(requirement),'receipt_ref':reference,'kind':kind,'text':text,
                                'citations':deepcopy(result['citations']),
                                'qualification':'Original-scope review requirement. Citations locate context, not proof of biological absence.'})
    checks=[]
    for original in prior['checks']:
        row=deepcopy(original)
        if row['input_sha256'] in reserved:
            row.update(eligible=False,status='execution_guarded',
                       reason='An owned or imported execution history already reserves or records these inputs; another proposal cannot reset that guard.')
        checks.append(row)
    owned_refs=[r['receipt_ref'] for r in bridge if r['owned_reviewed']]
    status=('review_scope' if prior['context_status']!='current' else
            'finish_current_cycle' if prior['status']=='finish_current_cycle' else
            'review_execution' if unfinished else 'needs_owned_review' if not owned_refs else
            'stop_no_new_inputs' if not any(r['eligible'] for r in checks) else 'review_next_check')
    reasons={
        'review_scope':'Save the current intelligence scope and owning context before preparing another proposal.',
        'finish_current_cycle':'Finish the existing intelligence cycle before another selection.',
        'review_execution':'A retained ledger has an unstarted approval, interrupted attempt or unreviewed result. Resolve it in its owning ledger before another selection.',
        'needs_owned_review':'At least one owned execution receipt and its separate owned human acknowledgment are required.',
        'stop_no_new_inputs':'No eligible unchecked inputs remain. Review the saved gaps; changing settings is not new source evidence.',
        'review_next_check':'Review the exact combined history, then deliberately prepare a proposal for an eligible check.'}
    value={'schema_version':PREVIEW,'status':status,'reason':reasons[status],
           'lineage':{'source_package_sha256':study.digest(source),'execution_package_sha256':study.digest(checked),
                      'catalog_sha256':study.digest(bundle),'source_head_hash':records[-1]['hash'],
                      'execution_head_hash':checked['events'][-1]['hash'] if checked['events'] else None,
                      'dominant_execution_heads':[chain[-1]['hash'] for chain in chains],
                      'scope_sha256':study.digest(state['scope']),'owning_context_sha256':study.digest(context)},
           'scope':deepcopy(state['scope']),'checks':checks,'bridge_records':bridge,'unresolved_requirements':requirements,
           'intelligence_prior_cycles':deepcopy(prior['prior_cycles']),'owned_reviewed_receipt_refs':owned_refs,
           'source_digests':deepcopy(bundle['source_digests']),'limit':LIMIT}
    screen_export(value)
    if len(study.canonical(value).encode())>MAX_BYTES: raise ValueError('Combined v3 preview exceeds its bound; no history was truncated')
    return {**value,'preview_sha256':study.digest(value)}


def prepare(source, execution_package, bundle, context, reviewed_preview_sha256, acknowledged, focus='trait'):
    preview=project(source,execution_package,bundle,context)
    if acknowledged is not True or reviewed_preview_sha256!=preview['preview_sha256']:
        raise ValueError('Review and acknowledge the exact combined preview before preparing v3')
    if preview['status']!='review_next_check': raise ValueError(preview['reason'])
    state=source['revisions'][-1]['state']; legacy=v1.prepare(state,'selection',bundle,focus)
    public=study.decode(legacy['body']['input'])
    eligible=[row['check'] for row in preview['checks'] if row['eligible']]
    public['eligible_checks']={key:model.CHECKS[key] for key in eligible}
    public['followup_context']=deepcopy(preview)
    schema=v1.response_schema(state,'selection',bundle); schema['properties']['check']['enum']=eligible
    refs=[r['receipt_ref'] for r in preview['bridge_records'] if r['result'] is not None and r['human_review'] is not None]
    schema['properties'].update({
        'preview_sha256':{'type':'string','enum':[preview['preview_sha256']]},
        'check_input_sha256':{'type':'string','enum':[r['input_sha256'] for r in preview['checks'] if r['eligible']]},
        'reviewed_receipt_refs':{'type':'array','items':{'type':'string','enum':refs},'minItems':1,'maxItems':len(refs)},
        'unresolved_requirement_ids':{'type':'array','items':{'type':'string','enum':[r['id'] for r in preview['unresolved_requirements']]},
                                      'minItems':1,'maxItems':len(preview['unresolved_requirements'])}})
    schema['required']=list(PROPOSAL_FIELDS)
    body={**deepcopy(legacy['body']),'input':study.canonical(public),
          'instructions':legacy['body']['instructions']+
              ' This v3 selection includes approved local audit receipts and separate human acknowledgments. '
              'Use their original scope and provenance. Imported execution histories are unverified; human acknowledgment is not model output or biological validation. '
              'Choose only a currently eligible check and its exact input identity. Cite at least one owned reviewed receipt using its collision-safe receipt_ref, '
              'plus an unresolved requirement belonging to a cited receipt. Raw result IDs alone do not identify receipts across ledgers. '
              'Do not repeat guarded inputs or retry failures. Changed settings are questions, not new evidence. '
              'References do not prove entailment or useful adaptation. This proposal cannot authorize execution.',
          'text':{'format':{'type':'json_schema','name':'traitweaver_molecular_followup_v3','strict':True,'schema':schema}}}
    screen_export(body)
    if len(study.canonical(body).encode())>MAX_REQUEST_BYTES:
        raise ValueError('V3 request exceeds 128 KiB; no history was truncated or sent')
    return {'schema_version':REQUEST,'phase':'execution_informed_selection','focus':focus,
            'reviewed_preview_sha256':preview['preview_sha256'],'human_acknowledgment':'exact_combined_preview_for_local_preparation_only',
            'lineage':deepcopy(preview['lineage']),'eligible_checks':eligible,'destination':v1.DESTINATION,
            'body':body,'request_sha256':study.digest(body),'status':'not_sent','live_transport_available':False,'limit':LIMIT}


def validate_request(request, source, execution_package, bundle, context):
    if not isinstance(request,dict): raise ValueError('V3 request must be structured')
    expected=prepare(source,execution_package,bundle,context,request.get('reviewed_preview_sha256'),True,request.get('focus'))
    if study.canonical(request)!=study.canonical(expected): raise ValueError('V3 request differs from its exact combined source history')
    return expected


def validate_proposal(proposal, request, source, bundle):
    study.fields(proposal,PROPOSAL_FIELDS)
    v1.validate_proposal(source['revisions'][-1]['state'],'selection',{key:proposal[key] for key in BASE_FIELDS},bundle)
    if proposal['check'] not in request['eligible_checks']: raise ValueError('V3 proposal selects guarded or unavailable inputs')
    preview=study.decode(request['body']['input'])['followup_context']
    row=next(r for r in preview['checks'] if r['check']==proposal['check'])
    if proposal['preview_sha256']!=preview['preview_sha256'] or proposal['check_input_sha256']!=row['input_sha256']:
        raise ValueError('V3 proposal does not bind the reviewed preview and exact selected inputs')
    refs={r['receipt_ref'] for r in preview['bridge_records'] if r['result'] is not None and r['human_review'] is not None}
    requirements={r['id']:r for r in preview['unresolved_requirements']}
    v2._unique_refs(proposal['reviewed_receipt_refs'],refs,'reviewed execution receipt references')
    v2._unique_refs(proposal['unresolved_requirement_ids'],requirements,'execution requirement references')
    if not set(proposal['reviewed_receipt_refs']) & set(preview['owned_reviewed_receipt_refs']):
        raise ValueError('Reference at least one owned execution receipt with its owned human acknowledgment')
    if any(requirements[key]['receipt_ref'] not in proposal['reviewed_receipt_refs'] for key in proposal['unresolved_requirement_ids']):
        raise ValueError('Requirement does not belong to a cited execution receipt')
    return deepcopy(proposal)


def synthetic_reply(request, check):
    if check not in request['eligible_checks']: raise ValueError('Select an eligible v3 fixture check')
    public=study.decode(request['body']['input']); preview=public['followup_context']
    reference=preview['owned_reviewed_receipt_refs'][0]
    requirement=next(r for r in preview['unresolved_requirements'] if r['receipt_ref']==reference)
    row=next(r for r in preview['checks'] if r['check']==check)
    proposal={'check':check,'arguments':deepcopy(public['scope']),'claim_codes':deepcopy(v1.CLAIMS[check]),
              'citations':model.required_citations(check,{'reference':public['reference_mapping']}),
              'preview_sha256':preview['preview_sha256'],'check_input_sha256':row['input_sha256'],
              'reviewed_receipt_refs':[reference],'unresolved_requirement_ids':[requirement['id']]}
    return {'model':v1.MODEL,'status':'completed','traitweaver_synthetic':True,
            'output':[{'type':'message','content':[{'type':'output_text','text':study.canonical(proposal)}]}]}


def parse_reply(request, source, execution_package, bundle, context, raw):
    validate_request(request,source,execution_package,bundle,context)
    if not isinstance(raw,bytes) or len(raw)>v1.MAX_RESPONSE: raise ValueError('V3 response must be bounded JSON bytes')
    reply=study.decode(raw); screen_export(reply)
    if not isinstance(reply,dict) or reply.get('model')!=v1.MODEL or reply.get('status')!='completed':
        raise ValueError('Wrong model, incomplete v3 response or refusal')
    if 'traitweaver_synthetic' in reply and type(reply['traitweaver_synthetic']) is not bool:
        raise ValueError('Synthetic provenance marker must be boolean')
    if not isinstance(reply.get('output'),list): raise ValueError('Expected typed v3 response output')
    texts=[]
    for item in reply['output']:
        if not isinstance(item,dict): raise ValueError('Malformed v3 response item')
        if item.get('type')=='reasoning': continue
        if item.get('type')!='message' or not isinstance(item.get('content'),list): raise ValueError('Unexpected provider action; nothing executed')
        for block in item['content']:
            if not isinstance(block,dict) or block.get('type')!='output_text' or not isinstance(block.get('text'),str):
                raise ValueError('Refusal or unsupported v3 response content')
            texts.append(block['text'])
    if len(texts)!=1: raise ValueError('Expected one structured v3 proposal')
    proposal=validate_proposal(study.decode(texts[0]),request,source,bundle)
    usage=reply.get('usage')
    if usage is not None and not isinstance(usage,dict): raise ValueError('Invalid v3 usage')
    receipt={'reported_model':v1.MODEL,'response_sha256':hashlib.sha256(raw).hexdigest(),
             'provenance':'synthetic_fixture' if reply.get('traitweaver_synthetic') is True else 'owner_imported_authenticity_unverified',
             'reported_usage':None if usage is None else {key:usage.get(key) for key in ('input_tokens','output_tokens','total_tokens')},
             'cost_usd':None,'transport_calls':0}
    v2._receipt(receipt)
    return {'status':'valid_proposal_only','request_sha256':request['request_sha256'],'proposal':proposal,'receipt':receipt}


def validate_package(value, bundle):
    try:
        study.fields(value,('schema_version','source_package','execution_package','request','proposal_review','limit'))
        if value['schema_version']!=PACKAGE or value['limit']!=LIMIT: raise ValueError('Unsupported v3 proposal package')
        if len(study.canonical(value).encode())>MAX_BYTES: raise ValueError('V3 proposal package exceeds its byte limit')
        source=value['source_package']; checked=intelligence_store.validate_package(source,bundle)
        context=checked[-1]['state']['context']
        request=validate_request(value['request'],source,value['execution_package'],bundle,context)
        review=value['proposal_review']
        if review is not None:
            study.fields(review,('status','request_sha256','proposal','receipt'))
            if review['status']!='valid_proposal_only' or review['request_sha256']!=request['request_sha256']:
                raise ValueError('Invalid v3 proposal-review binding')
            validate_proposal(review['proposal'],request,source,bundle); v2._receipt(review['receipt'])
        screen_export(value); return deepcopy(value)
    except (KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
        raise ValueError('Malformed v3 proposal package; existing work retained') from None


def _blocked(status, reason):
    return {'schema_version':PREVIEW,'status':status,'preview_sha256':None,'reason':reason,'lineage':None,'scope':None,
            'checks':[],'bridge_records':[],'unresolved_requirements':[],'intelligence_prior_cycles':[],
            'owned_reviewed_receipt_refs':[],'source_digests':None,'limit':LIMIT}


class Session:
    def __init__(self):
        self.reviews=[]; self.active=None; self.read_only=False; self.mutex=threading.RLock()
        self._preview_key=None; self._preview_value=None

    @_locked
    def current(self): return deepcopy(self.reviews[self.active]) if self.active is not None else None

    @_locked
    def fingerprint(self):
        value=self.current(); return study.digest(value) if value is not None else None

    def expect(self, expected):
        if expected!=self.fingerprint(): raise Conflict('V3 review changed; reload before continuing')

    def _sources(self, journal, ledger, context, editable=False):
        if journal is None or ledger is None: raise ValueError('Valid intelligence and execution owners are required')
        with ledger.mutex:
            if ledger.storage_blocked: raise ValueError('Execution storage is uncertain; reload the durable ledger first')
            if editable and (journal.read_only or ledger.active_import is not None):
                raise ValueError('Use the editable intelligence source and local execution ledger for a new v3 review')
            if study.canonical(journal.bundle)!=study.canonical(ledger.bundle): raise ValueError('Source catalogs differ')
            source=journal.export(); archive=deepcopy(ledger._owned_package())
        return source,archive,journal.bundle

    def _preview(self, source, archive, bundle, context):
        key=study.digest({'source':source,'execution':archive,'catalog':bundle,'context':context})
        if key!=self._preview_key:
            value=project(source,archive,bundle,context)
            self._preview_key=key; self._preview_value=value
        return deepcopy(self._preview_value)

    def _append(self, value, read_only):
        if len(self.reviews)>=MAX_REVIEWS or len(study.canonical(self.reviews+[value]).encode())>MAX_BYTES:
            raise ValueError('V3 session archive is full; export reviews before starting another session')
        self.reviews.append(deepcopy(value)); self.active=len(self.reviews)-1; self.read_only=read_only

    @_locked
    def prepare(self, expected, journal, ledger, context, reviewed_preview_sha256, acknowledged, focus):
        self.expect(expected); source,archive,bundle=self._sources(journal,ledger,context,True)
        request=prepare(source,archive,bundle,context,reviewed_preview_sha256,acknowledged,focus)
        value={'schema_version':PACKAGE,'source_package':source,'execution_package':archive,
               'request':request,'proposal_review':None,'limit':LIMIT}
        self._append(validate_package(value,bundle),False)

    @_locked
    def respond(self, expected, journal, ledger, context, raw=None, check=None):
        self.expect(expected); value=self.current()
        if value is None or self.read_only or value['proposal_review'] is not None:
            raise ValueError('One editable v3 request without a validated response is required')
        source,archive,bundle=self._sources(journal,ledger,context,True)
        validate_request(value['request'],source,archive,bundle,context)
        if check is not None: raw=study.canonical(synthetic_reply(value['request'],check)).encode()
        review=parse_reply(value['request'],source,archive,bundle,context,raw)
        updated={**value,'proposal_review':review}; validate_package(updated,bundle)
        proposed=deepcopy(self.reviews); proposed[self.active]=updated
        if len(study.canonical(proposed).encode())>MAX_BYTES: raise ValueError('V3 session archive exceeds its byte limit')
        self.reviews[self.active]=updated

    @_locked
    def open(self, expected, value, bundle):
        self.expect(expected); self._append(validate_package(value,bundle),True)

    @_locked
    def select(self, expected, review_hash):
        self.expect(expected)
        for index,value in enumerate(self.reviews):
            if study.digest(value)==review_hash:
                self.active=index; self.read_only=True; return
        raise ValueError('Unknown archived v3 proposal review')

    @_locked
    def view(self, journal, ledger, context):
        value=self.current(); request=value['request'] if value else None
        applicable=False; editable=False
        try:
            if journal is not None and journal.current()['revision']==0:
                preview=_blocked('review_scope','Save the intelligence scope, complete a local check and separately acknowledge its result first.')
            else:
                source,archive,bundle=self._sources(journal,ledger,context)
                preview=self._preview(source,archive,bundle,context)
                editable=not journal.read_only and ledger.active_import is None and not ledger.storage_blocked
                applicable=bool(request and request['reviewed_preview_sha256']==preview['preview_sha256'] and
                    study.canonical(request['lineage'])==study.canonical(preview['lineage']))
        except (ValueError,Conflict,KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
            preview=_blocked('unavailable','Valid current intelligence and execution histories are required. Saved archives remain inspectable; no request can be prepared.')
        ready=editable and preview['status']=='review_next_check'
        return {'review_hash':self.fingerprint(),'read_only':self.read_only,
                'applicability':'not_prepared' if value is None else 'current' if applicable else 'stale',
                'request':deepcopy(request),'proposal_review':deepcopy(value['proposal_review']) if value else None,'package':value,
                'history':[{'review_hash':study.digest(p),'source_revision':p['source_package']['revisions'][-1]['revision'],
                            'status':'valid_proposal_only' if p['proposal_review'] else 'not_sent'} for p in self.reviews],
                'preview':preview,'can_prepare':ready,
                'can_review':bool(ready and applicable and value is not None and not self.read_only and value['proposal_review'] is None),
                'storage':'session_only_export_to_keep','limit':LIMIT}
