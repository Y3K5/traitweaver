"""Explicit human approval and local audit receipts; never model/laboratory execution.

The new ledger wraps unchanged v2 reviews. Replay uses pure result validation,
never the dispatcher. Imported histories add conservative guards without replacing
owned history. A started attempt without a result is deliberately not retryable.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import hashlib
from pathlib import Path
import os
import threading
import uuid

from traitweaver import intelligence as model, intelligence_continuation as continuation
from traitweaver import intelligence_muse_v2 as v2, study
from traitweaver.study_store import Conflict, MAX_BYTES, screen_export

SCHEMA = 'traitweaver.intelligence_execution_package.v1'
EVENT = 'traitweaver.intelligence_execution_event.v1'
SCHEMA_V2 = 'traitweaver.intelligence_execution_package.v2'
EVENT_V2 = 'traitweaver.intelligence_execution_event.v2'
MAX_EVENTS = 96
MAX_IMPORTS = 8
MAX_FOLLOWUP_DEPTH = 4
MAX_VALIDATION_NODES = 200000
MAX_VALIDATION_STEPS = 512
MAX_VALIDATION_WORK_BYTES = 128 * 1024 * 1024
_VALIDATION = ContextVar('traitweaver_execution_validation',default=None)
LIMIT = ('Completion means one registered local evidence audit, not biological validation. '
         'Human approval and acknowledgment are separate from model proposals. No live model call, '
         'credential access, arbitrary code, laboratory execution or automatic retry. ' + model.LIMIT)


def _ack(value):
    if value is not True: raise ValueError('An explicit affirmative human acknowledgment is required')


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.mutex: return method(self, *args, **kwargs)
    return call


@contextmanager
def _validation_scope():
    if _VALIDATION.get() is not None:
        yield; return
    token=_VALIDATION.set({'memo':{},'active':set(),'steps':0,'bytes':0})
    try: yield
    finally: _VALIDATION.reset(token)


def _validation_operation(method):
    @wraps(method)
    def call(*args,**kwargs):
        with _validation_scope(): return method(*args,**kwargs)
    return call


def _preflight(value):
    # Iterative inspection precedes canonicalization and recursive validators.
    pending=[(value,0,0)]; nodes=0
    while pending:
        item,depth,followups=pending.pop(); nodes+=1
        if nodes>MAX_VALIDATION_NODES or depth>128: raise ValueError('Execution validation structure exceeds its bound')
        if isinstance(item,dict):
            if item.get('schema_version')=='traitweaver.intelligence_followup_review.v3': followups+=1
            if followups>MAX_FOLLOWUP_DEPTH: raise ValueError('Nested v3 review depth exceeds its bound; no history was truncated')
            pending.extend((child,depth+1,followups) for child in item.values())
        elif isinstance(item,list): pending.extend((child,depth+1,followups) for child in item)


def _memo(kind, value, compute):
    with _validation_scope():
        try: _preflight(value); raw=study.canonical(value).encode()
        except (KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
            raise ValueError('Malformed bounded execution validation input') from None
        context=_VALIDATION.get()
        context['bytes']+=len(raw)
        if context['bytes']>MAX_VALIDATION_WORK_BYTES: raise ValueError('Execution validation work exceeds its byte budget')
        key=(kind,hashlib.sha256(raw).hexdigest())
        if key in context['memo']: return deepcopy(context['memo'][key])
        if key in context['active']: raise ValueError('Cyclic execution validation dependency')
        context['steps']+=1
        if context['steps']>MAX_VALIDATION_STEPS: raise ValueError('Execution validation work exceeds its step budget')
        context['active'].add(key)
        try:
            try: result=compute()
            except (KeyError,TypeError,AttributeError,IndexError,RecursionError,OverflowError):
                raise ValueError('Malformed execution validation dependency') from None
            context['memo'][key]=deepcopy(result); return result
        finally: context['active'].remove(key)


def _key(check, scope, bundle):
    if not isinstance(check, str) or check not in model.CHECKS: raise ValueError('Unregistered local check')
    return continuation.input_identity(check, scope, study.digest(bundle))['input_sha256']


def _human(result):
    return {'result_id': result['id'], 'outcome': result['outcome'],
            'next_action': 'researcher_review_measurement_plan',
            'interpretation': result['interpretation'], 'measurement_plan': deepcopy(result['measurement_plan']),
            'provenance': 'human_acknowledgment_of_fixed_local_result', 'acknowledged': True, 'limit': LIMIT}


def _reserved(cycle):
    return bool(cycle['attempts']) or cycle['status'] in ('approved', 'started', 'retry_approved')


def _replay(events, bundle):
    """Validate and replay an event chain without dispatching a registered check."""
    if not isinstance(events, list) or len(events) > MAX_EVENTS: raise ValueError('Execution event bounds exceeded')
    cycles = []; previous = None; version_two=False
    for number, event in enumerate(events, 1):
        study.fields(event, ('schema_version', 'revision', 'parent_hash', 'saved_utc', 'kind', 'payload', 'hash'))
        if (event['schema_version'] not in (EVENT,EVENT_V2) or type(event['revision']) is not int or
                event['revision'] != number or event['parent_hash'] != previous or
                event['hash'] != study.digest({k:v for k,v in event.items() if k != 'hash'})):
            raise ValueError('Broken execution event lineage')
        if version_two and event['schema_version']!=EVENT_V2: raise ValueError('Execution event version cannot regress')
        version_two=version_two or event['schema_version']==EVENT_V2
        if datetime.fromisoformat(event['saved_utc']).tzinfo is None: raise ValueError('Execution timestamp requires timezone')
        kind, payload = event['kind'], event['payload']; active = cycles[-1] if cycles else None
        if kind in ('approve','approve_v3'):
            study.fields(payload, ('review_package', 'acknowledged')); _ack(payload['acknowledged'])
            if kind=='approve_v3':
                if event['schema_version']!=EVENT_V2: raise ValueError('V3 approval requires execution event v2')
                from traitweaver import intelligence_muse_v3 as v3
                review=v3.validate_package(payload['review_package'],bundle)
                if study.canonical(review['execution_package']['events'])!=study.canonical(events[:number-1]):
                    raise ValueError('V3 approval does not bind the exact preapproval owned event prefix')
            else:
                review=_memo('v2_review',{'review':payload['review_package'],'catalog_sha256':study.digest(bundle)},
                             lambda:v2.validate_package(payload['review_package'],bundle))
            if review['proposal_review'] is None: raise ValueError('A validated model proposal is required')
            if active and active['status'] not in ('reviewed', 'cancelled'):
                raise ValueError('Finish, review or cancel the current approval first')
            proposal = review['proposal_review']['proposal']; scope = proposal['arguments']
            identity = _key(proposal['check'], scope, bundle)
            if any(c['approval']['input_sha256'] == identity and _reserved(c) for c in cycles):
                raise ValueError('These local check inputs already have an approval or attempt')
            cycles.append({'approval_id': event['hash'], 'approval_revision': number,
                           'review_package': deepcopy(review), 'status': 'approved', 'attempts': [], 'reassessment': None,
                           'approval': {'review_hash': study.digest(review), 'check': proposal['check'],
                                        'input_sha256': identity, 'scope': deepcopy(scope),
                                        'proposal_review': deepcopy(review['proposal_review']),
                                        'lineage': deepcopy(review['request']['lineage'])}})
            if kind=='approve_v3': cycles[-1]['approval']['proposal_version']='v3'
        elif kind == 'started':
            study.fields(payload, ('attempt_id',))
            if active is None or active['status'] not in ('approved', 'retry_approved'):
                raise ValueError('One unstarted human approval is required')
            ordinal = len(active['attempts']) + 1
            attempt_id = 'E' + str(active['approval_revision']) + 'A' + str(ordinal)
            if ordinal > 2 or payload['attempt_id'] != attempt_id: raise ValueError('Invalid attempt identity or retry count')
            active['attempts'].append({'id': attempt_id, 'ordinal': ordinal, 'start_hash': event['hash'], 'result': None, 'review': None})
            active['status'] = 'started'; active['reassessment'] = None
        elif kind == 'result':
            study.fields(payload, ('result',))
            if active is None or active['status'] != 'started': raise ValueError('A saved start is required before its result')
            attempt = active['attempts'][-1]; result = payload['result']
            if not isinstance(result, dict): raise ValueError('A typed saved local result is required')
            factory = model.failure_result if result.get('status') == 'failed' else model.result
            expected = factory(active['approval']['check'], active['approval']['scope'], bundle, attempt['id'])
            if study.canonical(result) != study.canonical(expected): raise ValueError('Local result differs from its source-bound check')
            attempt['result'] = deepcopy(result); active['status'] = result['status']
        elif kind == 'reassess':
            study.fields(payload, ('result_id', 'acknowledged')); _ack(payload['acknowledged'])
            if active is None or active['status'] not in ('completed', 'failed'): raise ValueError('One unreviewed local result is required')
            attempt = active['attempts'][-1]
            if payload['result_id'] != attempt['result']['id']: raise ValueError('Human review must bind the exact saved result')
            attempt['review'] = _human(attempt['result']); active['reassessment'] = deepcopy(attempt['review']); active['status'] = 'reviewed'
        elif kind == 'retry':
            study.fields(payload, ('result_id', 'reason', 'acknowledged')); _ack(payload['acknowledged'])
            if (active is None or active['status'] != 'reviewed' or len(active['attempts']) != 1 or
                    active['attempts'][0]['result']['status'] != 'failed' or
                    payload['result_id'] != active['attempts'][0]['result']['id'] or payload['reason'] != 'reviewed_local_failure'):
                raise ValueError('One reviewed known failure permits at most one explicitly approved retry')
            active['status'] = 'retry_approved'
        elif kind == 'cancel':
            study.fields(payload, ('acknowledged',)); _ack(payload['acknowledged'])
            if active is None or active['status'] not in ('approved', 'retry_approved'):
                raise ValueError('Only an unstarted initial approval or retry approval may be cancelled')
            # Cancelling a retry withdraws only the unstarted permission. Its
            # earlier failed attempt and review still reserve these inputs.
            active['status'] = 'cancelled'
        else: raise ValueError('Unknown execution event')
        previous = event['hash']
    return cycles


def _state(events,bundle):
    return _memo('execution_state',{'events':events,'catalog_sha256':study.digest(bundle)},lambda:_replay(events,bundle))


def _prefix(left, right):
    return len(left) <= len(right) and all(a['hash'] == b['hash'] for a,b in zip(left,right))


def _dominant(chains):
    """A known later snapshot supersedes its own prefixes, never other ledgers."""
    result = []
    for chain in chains:
        if not chain or any(_prefix(chain, other) for other in result): continue
        for other in result:
            if other[0]['hash'] == chain[0]['hash'] and not _prefix(other, chain):
                raise ValueError('Conflicting execution history fork; existing guard retained')
        result = [other for other in result if not _prefix(other, chain)] + [chain]
    return result


def _package(events, guards, bundle):
    version=SCHEMA_V2 if any(isinstance(event,dict) and event.get('schema_version')==EVENT_V2 for chain in [events,*guards] for event in chain) else SCHEMA
    return {'schema_version': version, 'catalog_sha256': study.digest(bundle), 'events': deepcopy(events),
            'guard_histories': deepcopy(guards), 'limit': LIMIT}


def _validate_package(value, bundle):
    try:
        study.fields(value, ('schema_version', 'catalog_sha256', 'events', 'guard_histories', 'limit'))
        if value['schema_version'] not in (SCHEMA,SCHEMA_V2) or value['catalog_sha256'] != study.digest(bundle) or value['limit'] != LIMIT:
            raise ValueError('Execution catalog or package version changed')
        guards = value['guard_histories']
        if not isinstance(guards,list) or len(guards) > MAX_IMPORTS: raise ValueError('Too many execution guard histories')
        if len(study.canonical(value).encode()) > MAX_BYTES: raise ValueError('Execution package exceeds its byte limit')
        chains=[value['events'],*guards]; states=[_state(chain,bundle) for chain in chains]
        dominant=_dominant(chains)
        expected_version=SCHEMA_V2 if any(e['schema_version']==EVENT_V2 for chain in chains for e in chain) else SCHEMA
        if value['schema_version']!=expected_version: raise ValueError('Execution envelope does not match its event versions')
        for cycles in states:
            for cycle in cycles:
                if cycle['approval'].get('proposal_version')=='v3':
                    for guard in cycle['review_package']['execution_package']['guard_histories']:
                        if guard and not any(_prefix(guard,known) for known in dominant):
                            raise ValueError('Execution package omits a guard committed by a v3 approval')
        screen_export(value)
        return deepcopy(value)
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError, OverflowError):
        raise ValueError('Malformed execution package; saved work unchanged') from None


def validate_package(value,bundle):
    return _memo('execution_package',{'package':value,'catalog_sha256':study.digest(bundle)},lambda:_validate_package(value,bundle))


class Session:
    def __init__(self, bundle, directory=None):
        self.mutex = threading.RLock()
        self.bundle = deepcopy(bundle); self.root = Path(directory) if directory is not None else None
        self.events = []; self.imports = []; self.active_import = None; self.storage_blocked = False
        if self.root is not None:
            if self.root.is_symlink() or self.root.resolve() == study.APP_ROOT or study.APP_ROOT in self.root.resolve().parents:
                raise ValueError('Explicit external execution storage required')
            if self.root.exists():
                if not self.root.is_dir(): raise ValueError('Unsafe execution storage')
                total = 0
                for prefix, destination, limit in [('event',self.events,MAX_EVENTS),('import',self.imports,MAX_IMPORTS)]:
                    for path in sorted(self.root.glob(prefix+'-*.json')):
                        if path.is_symlink() or not path.is_file() or path.name != prefix+'-'+str(len(destination)+1).zfill(6)+'.json':
                            raise ValueError('Unsafe or missing execution record')
                        total += path.stat().st_size
                        if total > MAX_BYTES or len(destination) >= limit: raise ValueError('Execution storage exceeds its bounds')
                        destination.append(study.decode(path.read_bytes()))
                for value in self.imports: validate_package(value,self.bundle)
                # Raw disk events must validate before prefix/union helpers
                # inspect their hashes. Corrupt storage fails closed as ValueError.
                validate_package(_package(self.events,[],self.bundle),self.bundle)
                validate_package(self._owned_package(),self.bundle)

    @_locked
    def fingerprint(self):
        return study.digest({'events':self.events,'imports':self.imports,'active_import':self.active_import,'storage_blocked':self.storage_blocked})

    def _expect(self, expected):
        if expected != self.fingerprint(): raise Conflict('Execution review changed; reload before continuing')

    def _local(self):
        if self.storage_blocked: raise ValueError('Execution storage outcome is uncertain; reload the durable ledger before continuing')
        if self.active_import is not None: raise ValueError('Imported execution history is read-only; return to the local ledger')

    def _chains(self, extra=None):
        chains = [self.events]
        for value in [*self.imports, *([] if extra is None else [extra])]:
            chains += [value['events'], *value['guard_histories']]
        return _dominant(chains)

    def _owned_package(self):
        guards = [chain for chain in self._chains() if not _prefix(chain,self.events)]
        return _package(self.events,guards,self.bundle)

    @_locked
    def export(self):
        if self.storage_blocked: raise ValueError('Reload uncertain durable execution storage before exporting')
        value = self.imports[self.active_import] if self.active_import is not None else self._owned_package()
        return validate_package(value,self.bundle)

    def _active(self):
        cycles = _state(self.events,self.bundle)
        return cycles[-1] if cycles else None

    def _matching(self, identity):
        return [c for chain in self._chains() for c in _state(chain,self.bundle) if c['approval']['input_sha256']==identity]

    @_locked
    def guard(self, check, scope):
        if self.storage_blocked: raise ValueError('Execution storage is uncertain; reload before another check')
        identity = _key(check,scope,self.bundle)
        if any(_reserved(c) for c in self._matching(identity)):
            raise ValueError('These check inputs have a saved approval or attempt; review the execution ledger instead of repeating them')

    def _run_guard(self, active, retry=False):
        matches = self._matching(active['approval']['input_sha256'])
        if any(c['approval_id'] != active['approval_id'] and _reserved(c) for c in matches):
            raise ValueError('Another owned or imported record already reserves these inputs')
        attempts = {a['start_hash']:a for c in matches for a in c['attempts']}
        if retry:
            own = active['attempts']
            if len(own)!=1 or set(attempts)!={own[0]['start_hash']} or own[0]['result'] is None or own[0]['result']['status']!='failed' or own[0]['review'] is None:
                raise ValueError('Retry requires exactly one owned, reviewed known failure across all recorded histories')
        elif attempts: raise ValueError('These inputs already have a started attempt; no duplicate dispatch')

    def _editable_source(self, journal):
        if journal is None or journal.read_only: raise ValueError('An editable current intelligence source is required')
        if study.canonical(journal.bundle)!=study.canonical(self.bundle): raise ValueError('Execution source catalog changed')

    def _current(self, review, journal, context):
        self._editable_source(journal)
        if review.get('schema_version')=='traitweaver.intelligence_followup_review.v3':
            from traitweaver import intelligence_muse_v3 as v3
            checked=v3.validate_package(review,self.bundle)
            if (study.canonical(journal.export())!=study.canonical(checked['source_package']) or
                    study.digest(context)!=checked['request']['lineage']['owning_context_sha256']):
                raise ValueError('The v3 approval source or owning context changed')
            snapshot=checked['execution_package']; prefix=snapshot['events']; index=len(prefix)
            if (study.canonical(self.events[:index])!=study.canonical(prefix) or len(self.events)<=index or
                    self.events[index]['kind']!='approve_v3' or
                    study.canonical(self.events[index]['payload']['review_package'])!=study.canonical(checked)):
                raise ValueError('The v3 approval does not extend its exact saved execution snapshot')
            if any(e['kind'] not in ('started','result','reassess','retry','cancel') for e in self.events[index+1:]):
                raise ValueError('Another approval superseded this v3 lifecycle')
            if study.canonical(self._owned_package()['guard_histories'])!=study.canonical(snapshot['guard_histories']):
                raise ValueError('Execution guard histories changed after v3 approval')
            return
        v2.validate_request(review['request'],journal.export(),self.bundle,context)

    def _approval_check(self, review, journal, context, acknowledged):
        _ack(acknowledged); self._local(); checked=v2.validate_package(review,self.bundle)
        if checked['proposal_review'] is None: raise ValueError('A validated v2 proposal is required')
        self._current(checked,journal,context)
        active=self._active()
        if active and active['status'] not in ('reviewed','cancelled'): raise ValueError('Finish, review or cancel the current approval first')
        p=checked['proposal_review']['proposal']; self.guard(p['check'],p['arguments'])
        return checked

    def _followup_approval_check(self, review, journal, context, acknowledged):
        from traitweaver import intelligence_muse_v3 as v3
        _ack(acknowledged); self._local(); self._editable_source(journal)
        checked=v3.validate_package(review,self.bundle)
        if checked['proposal_review'] is None: raise ValueError('A validated v3 proposal is required')
        snapshot=self._owned_package()
        v3.validate_request(checked['request'],journal.export(),snapshot,self.bundle,context)
        if study.canonical(checked['execution_package'])!=study.canonical(snapshot):
            raise ValueError('V3 approval requires the exact current owned execution snapshot')
        active=self._active()
        if active and active['status'] not in ('reviewed','cancelled'):
            raise ValueError('Finish, review or cancel the current approval first')
        proposal=checked['proposal_review']['proposal']; self.guard(proposal['check'],proposal['arguments'])
        return checked

    def _event(self, kind, payload, events=None):
        events=self.events if events is None else events
        version=EVENT_V2 if kind=='approve_v3' or any(e['schema_version']==EVENT_V2 for e in events) else EVENT
        event={'schema_version':version,'revision':len(events)+1,'parent_hash':events[-1]['hash'] if events else None,
               'saved_utc':datetime.now(timezone.utc).isoformat(timespec='microseconds'),'kind':kind,'payload':deepcopy(payload)}
        event['hash']=study.digest(event); return event

    def _write(self, name, value):
        if self.root is None: return
        if self.root.is_symlink(): raise ValueError('Unsafe execution storage')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        pending=self.root/('.pending-'+uuid.uuid4().hex); target=self.root/name
        try:
            with pending.open('xb') as handle:
                os.chmod(pending,0o600); handle.write((study.canonical(value)+'\n').encode()); handle.flush(); os.fsync(handle.fileno())
            os.link(pending,target)
            fd=os.open(self.root,os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        except BaseException:
            if target.exists(): self.storage_blocked=True
            raise
        finally:
            # A leftover private temporary file is not a failed commit. Do not
            # report disk-new/memory-old merely because best-effort cleanup failed.
            try: pending.unlink(missing_ok=True)
            except OSError: pass
            except BaseException:
                if target.exists(): self.storage_blocked=True
                raise

    def _persist(self, event):
        self._write('event-'+str(event['revision']).zfill(6)+'.json',event)

    def _append(self, kind, payload):
        event=self._event(kind,payload)
        guards=self._owned_package()['guard_histories']
        validate_package(_package(self.events+[event],guards,self.bundle),self.bundle)
        if len(study.canonical({'events':self.events+[event],'imports':self.imports}).encode())>MAX_BYTES:
            raise ValueError('Execution storage exceeds its byte limit')
        self._persist(event); self.events.append(event)

    @_locked
    @_validation_operation
    def approve(self, expected, review_package, journal, context, acknowledged):
        self._expect(expected); checked=self._approval_check(review_package,journal,context,acknowledged)
        self._append('approve',{'review_package':checked,'acknowledged':True})

    @_locked
    @_validation_operation
    def approve_followup(self, expected, review_package, journal, context, acknowledged):
        self._expect(expected); checked=self._followup_approval_check(review_package,journal,context,acknowledged)
        self._append('approve_v3',{'review_package':checked,'acknowledged':True})

    @_locked
    @_validation_operation
    def run(self, expected, journal, context):
        self._expect(expected); self._local(); active=self._active()
        if active is None or active['status'] not in ('approved','retry_approved'): raise ValueError('One unstarted human approval is required')
        self._current(active['review_package'],journal,context)
        self._run_guard(active,active['status']=='retry_approved')
        if len(self.events)+2>MAX_EVENTS: raise ValueError('Reserve room for both execution start and result before dispatch')
        attempt_id='E'+str(active['approval_revision'])+'A'+str(len(active['attempts'])+1)
        start=self._event('started',{'attempt_id':attempt_id}); future=self.events+[start]
        check,scope=active['approval']['check'],active['approval']['scope']
        # Both possible terminal records must fit before the dispatch reservation.
        for factory in (model.result,model.failure_result):
            terminal=self._event('result',{'result':factory(check,scope,self.bundle,attempt_id)},future)
            if len(study.canonical({'events':future+[terminal],'imports':self.imports}).encode())+1024>MAX_BYTES:
                raise ValueError('Reserve result capacity before starting a local check')
            validate_package(_package(future+[terminal],self._owned_package()['guard_histories'],self.bundle),self.bundle)
        self._append('started',{'attempt_id':attempt_id})
        try:
            result=model.run_check(check,deepcopy(scope),deepcopy(self.bundle),attempt_id)
        except Exception:
            result=model.failure_result(check,scope,self.bundle,attempt_id)
        else:
            # A malformed return or validation interruption is indeterminate,
            # not a known invocation failure that may authorize a retry.
            if study.canonical(result)!=study.canonical(model.result(check,scope,self.bundle,attempt_id)):
                raise ValueError('Invalid dispatcher result; recorded start remains blocked')
        # Persistence errors are NOT check failures and cannot authorize a retry.
        self._append('result',{'result':result})

    @_locked
    @_validation_operation
    def reassess(self, expected, journal, context, result_id, acknowledged):
        self._expect(expected); self._local(); _ack(acknowledged); active=self._active()
        if active is None: raise ValueError('No local result to review')
        # A human may acknowledge a validated historical receipt in its original
        # scope. This does not make it current or relax execution/retry lineage.
        self._editable_source(journal)
        self._append('reassess',{'result_id':result_id,'acknowledged':True})

    @_locked
    @_validation_operation
    def retry(self, expected, journal, context, result_id, reason, acknowledged):
        self._expect(expected); self._local(); _ack(acknowledged); active=self._active()
        if active is None or active['status']!='reviewed': raise ValueError('Review a known local failure before approving a retry')
        self._current(active['review_package'],journal,context); self._run_guard(active,True)
        self._append('retry',{'result_id':result_id,'reason':reason,'acknowledged':True})

    @_locked
    @_validation_operation
    def cancel(self, expected, acknowledged):
        self._expect(expected); self._local(); _ack(acknowledged)
        self._append('cancel',{'acknowledged':True})

    @_locked
    @_validation_operation
    def open(self, expected, value):
        self._expect(expected)
        if self.storage_blocked: raise ValueError('Reload uncertain durable execution storage first')
        checked=validate_package(value,self.bundle)
        chains=self._chains(checked)
        guards=[chain for chain in chains if not _prefix(chain,self.events)]
        validate_package(_package(self.events,guards,self.bundle),self.bundle)
        for index,item in enumerate(self.imports):
            if study.canonical(item)==study.canonical(checked): self.active_import=index; return
        if len(self.imports)>=MAX_IMPORTS or len(study.canonical({'events':self.events,'imports':self.imports+[checked]}).encode())>MAX_BYTES:
            raise ValueError('Execution import archive is full; existing history retained')
        self._write('import-'+str(len(self.imports)+1).zfill(6)+'.json',checked)
        self.imports.append(checked); self.active_import=len(self.imports)-1

    @_locked
    def local(self, expected):
        self._expect(expected)
        if self.storage_blocked: raise ValueError('Reload uncertain durable execution storage first')
        self.active_import=None

    @_locked
    @_validation_operation
    def view(self, journal, context, next_package=None, next_read_only=False, followup_package=None, followup_read_only=False):
        value=deepcopy(self.imports[self.active_import]) if self.active_import is not None else self._owned_package()
        cycles=_state(value['events'],self.bundle); active=cycles[-1] if cycles else None
        readonly=self.active_import is not None; applicable=False; reason='Review a validated v2 proposal before approving a local check.'
        if active:
            try: self._current(active['review_package'],journal,context); applicable=True
            except (ValueError,Conflict): reason='The approval source or owning context changed; execution is withheld.'
        available={k:False for k in ('can_approve','can_run','can_review','can_retry','can_cancel','can_approve_followup')}
        followup_reason='Review a current validated v3 proposal before approving its local check.'
        if not readonly and not self.storage_blocked:
            available['can_cancel']=bool(active and active['status'] in ('approved','retry_approved'))
            if active and active['status'] in ('completed','failed'):
                try: self._editable_source(journal); available['can_review']=True
                except ValueError: pass
            if applicable:
                if active['status'] in ('approved','retry_approved'):
                    try: self._run_guard(active,active['status']=='retry_approved'); available['can_run']=True
                    except ValueError as error: reason=str(error)
                if active['status']=='reviewed' and len(active['attempts'])==1 and active['attempts'][-1]['result']['status']=='failed':
                    try: self._run_guard(active,True); available['can_retry']=True
                    except ValueError as error: reason=str(error)
            if next_package is not None and not next_read_only:
                try: self._approval_check(next_package,journal,context,True); available['can_approve']=True
                except (ValueError,Conflict) as error: reason=str(error)
            if followup_package is not None and not followup_read_only:
                try:
                    self._followup_approval_check(followup_package,journal,context,True)
                    available['can_approve_followup']=True
                    followup_reason='The exact current v3 proposal is available for separate human approval; no check has run.'
                except (ValueError,Conflict) as error: followup_reason=str(error)
        if readonly: reason='Imported execution history is read-only. Local and imported duplicate guards remain retained.'
        elif self.storage_blocked: reason='Storage outcome is uncertain. Reload the durable ledger; no further checks are allowed.'
        elif active and active['status']=='started': reason='A start has no recorded result. Its outcome is uncertain; no automatic or manual retry is allowed.'
        available['reason']=reason
        available['followup_reason']=followup_reason
        checks={}
        if journal is not None:
            scope=journal.current()['state']['scope']
            try: rows={r['check']:r for r in journal.continuation(context)['checks']}
            except ValueError: rows={}
            for check in model.CHECKS:
                message='No execution-ledger reservation for these check inputs.'; allowed=True
                try: self.guard(check,scope)
                except ValueError as error: allowed=False; message=str(error)
                if check not in rows or not rows[check]['eligible']:
                    allowed=False; message=rows[check]['reason'] if check in rows else 'Intelligence source validation failed.'
                checks[check]={'allowed':allowed,'reason':message,'input_sha256':_key(check,scope,self.bundle)}
        public_active=None if active is None else {k:deepcopy(active[k]) for k in ('approval','attempts','reassessment','status')}
        return {'execution_hash':self.fingerprint(),'read_only':readonly,'storage':'imported_read_only' if readonly else 'external_data_directory' if self.root else 'session_only_export_to_keep',
                'package':value,'status':active['status'] if active else 'empty','applicability':'not_approved' if active is None else 'current' if applicable else 'stale',
                'active':public_active,'history':[{'revision':e['revision'],'hash':e['hash'],'action':e['kind'],'saved_utc':e['saved_utc']} for e in value['events']],
                'availability':available,'check_availability':checks,
                'persistence_notice':'External execution records and imported guards survive process restart; incomplete starts stay blocked.' if self.root else
                    'Session memory only. Duplicate guards do not survive process exit unless the exported histories are retained and reopened. No automatic execution or retry occurs on reopen.',
                'limit':LIMIT}
