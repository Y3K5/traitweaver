"""Single-owner loopback workspace. No external network is used by this server."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit

from traitweaver import molecular, molecular_store, muse_boundary, protein_card, study, public_algae
from traitweaver import intelligence, intelligence_muse, intelligence_store, intelligence_muse_v2, intelligence_execution
from traitweaver import assistant_workspace
from traitweaver import research_story
from traitweaver import workbench, step_tracking, showcase, release_review
from traitweaver.study_store import Conflict, MAX_BYTES, Store
from traitweaver.completed_cycle import CompletedCycle

WEB = Path(__file__).with_name('web')
CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


class WorkspaceSession:
    """Imported reviews replace only the in-memory view, never the study store."""
    def __init__(self, store):
        self.active=store
        self.mutex=threading.RLock()
        self.molecular=None
        self.molecular_error=None
        try:
            bundle=molecular.catalog()
            self.molecular=molecular_store.Journal(bundle,store.root/'molecular-review' if isinstance(store,Store) else None)
        except (ValueError,OSError):
            self.molecular_error='Molecular sources or saved review failed validation. The original study remains available.'
        self.public_algae=None
        self.public_algae_error=None
        try:
            self.public_algae=molecular_store.Journal(public_algae.catalog(),store.root/'public-algae-review-v2' if isinstance(store,Store) else None)
        except (ValueError,OSError):
            self.public_algae_error='Public algae sources or saved review failed validation. No substitute data or retrieval was used.'
        self.intelligence_next=intelligence_muse_v2.Session()
        self.intelligence=None
        self.intelligence_error=None
        try:
            self.intelligence=intelligence_store.Journal(intelligence.catalog(),store.root/'intelligence-review-v1' if isinstance(store,Store) else None)
        except (ValueError,OSError):
            self.intelligence_error='Intelligence sources or saved records failed validation. Original study and reference reviews remain available.'
        self.intelligence_execution=None
        self.intelligence_execution_error=None
        try:
            if self.intelligence is None:raise ValueError('Intelligence catalog unavailable')
            self.intelligence_execution=intelligence_execution.Session(self.intelligence.bundle,store.root/'intelligence-execution-v1' if isinstance(store,Store) else None)
        except (ValueError,OSError):
            self.intelligence_execution_error='Execution history failed validation. New intelligence checks are blocked; existing records remain available.'
        self.assistant=None
        self.assistant_error=None
        try:
            self.assistant=assistant_workspace.Session()
        except (ValueError,OSError):
            self.assistant_error='Assistant public/synthetic catalog failed validation. Other study views remain available.'
        self.research_story=None
        self.research_story_error=None
        try:
            self.research_story=research_story.Session()
        except (ValueError,OSError):
            self.research_story_error='Research story source qualification failed. Other study views remain available; no substitute data used.'
        self.workbench=None
        self.workbench_error=None
        try:
            self.workbench=workbench.Session(self.assistant,self.research_story)
        except (ValueError,OSError):
            self.workbench_error='Workbench requires qualified assistant records. Original study and other views remain available.'

        self.release_review=None;self.release_review_error=None
        try:
            self.release_review_local=release_review.Session(store.export_review() if isinstance(store,CompletedCycle) else None)
            self.release_review=self.release_review_local
        except (ValueError,OSError):
            self.release_review_error='Study review source validation failed; no substitute evidence used.'

        self.steps=None;self.steps_error=None
        try:
            self.steps_local=step_tracking.Journal(store.root/'completed-steps-v1' if isinstance(store,Store) else None)
            self.steps=self.steps_local
        except (ValueError,OSError):
            self.steps_error='Completed-step history/source failed validation. Other workspace records remain available.'


class LoopbackHTTPServer(ThreadingHTTPServer):
    # The workspace loads multiple local controllers/styles in parallel. Keep
    # their initial connections from overflowing the standard five-slot queue.
    request_queue_size = 64


def make_server(store, port=0, server_factory=LoopbackHTTPServer, rna_pilot_dir=None, completion_pilot_dir=None):
    workspace=WorkspaceSession(store)
    workspace.showcase_pilots={"rna":showcase.load_pilot(rna_pilot_dir,"rna"),"completion":showcase.load_pilot(completion_pilot_dir,"completion")}
    token = secrets.token_urlsafe(32)
    assets = {'/'+p.relative_to(WEB).as_posix(): p for p in WEB.rglob('*') if p.is_file() and not p.is_symlink()}

    def execution_view(current):
        owner=workspace.intelligence_execution
        return owner.view(workspace.intelligence,intelligence.context(current),workspace.intelligence_next.current(),workspace.intelligence_next.read_only) if owner else None

    def intelligence_views(current):
        j=workspace.intelligence
        return {'intelligence':j.view(current) if j else None,
                'intelligence_next':workspace.intelligence_next.view(j,intelligence.context(current)),
                'intelligence_execution':execution_view(current),
                'intelligence_execution_error':workspace.intelligence_execution_error}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *args):
            pass

        def send(self, status, payload, content_type='application/json; charset=utf-8', filename=None, csp=CSP):
            raw = payload if isinstance(payload, bytes) else (json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if content_type.startswith('application/json') else payload.encode())
            self.send_response(status)
            for name, value in [('Content-Type', content_type), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                                ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY')]:
                self.send_header(name, value)
            if csp:
                self.send_header('Content-Security-Policy', csp)
            if filename:
                self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def safe_host(self):
            origin = 'http://127.0.0.1:'+str(self.server.server_port)
            return (self.headers.get('Host') == origin[7:] and self.headers.get('Origin', origin) == origin and
                    self.headers.get('Sec-Fetch-Site', 'same-origin') != 'cross-site')

        def do_GET(self):
            with workspace.mutex:
                self.read_get()

        def read_get(self):
            store=workspace.active
            if not self.safe_host():
                self.send(403, {'error': 'Local same-origin requests only'}); return
            path = urlsplit(self.path).path
            try:
                if path.startswith('/api/'):
                    if self.headers.get('X-Traitweaver-Client') != 'workspace':
                        self.send(403, {'error': 'Workspace client header required'}); return
                    # Optional read identity used by Data flow. Keep the shown
                    # revision and the exported bytes in the same mutex scope.
                    exports={'/api/export.json':store,'/api/export.md':store,
                             '/api/intelligence/export.json':workspace.intelligence,'/api/intelligence/export.txt':workspace.intelligence,
                             '/api/public-algae/export.json':workspace.public_algae,'/api/public-algae/export.txt':workspace.public_algae,
                             '/api/molecular/export.json':workspace.molecular,'/api/molecular/export.txt':workspace.molecular}
                    exports.update({'/api/steps/export.json':workspace.steps,'/api/steps/export.txt':workspace.steps})
                    exports.update({'/api/assistant/export.json':workspace.assistant,'/api/assistant/export.txt':workspace.assistant})
                    exports.update({'/api/research-story/export.json':workspace.research_story,'/api/research-story/export.txt':workspace.research_story})
                    exports.update({'/api/workbench/export.json':workspace.workbench,'/api/workbench/export.md':workspace.workbench})
                    if isinstance(store,CompletedCycle):exports['/api/cycle-review.json']=store
                    expected=self.headers.get('X-Traitweaver-Expected-Revision')
                    if path in exports and expected is not None:
                        owner=exports[path]
                        if owner is None:raise ValueError('Selected export is unavailable')
                        if expected!=owner.current()['hash']:
                            self.send(409,{'error':'Saved state changed. Refresh Data flow before exporting; nothing was downloaded.'});return
                    if path == '/api/session':
                        self.send(200, {'token': token}); return
                    if path == '/api/state':
                        with store.mutex:
                            current = store.current()
                            self.send(200, {'current': current, 'evidence': study.bundle(), 'eligible_checks': study.eligible_checks(current['state']),
                                            'history': [{'revision': r['revision'], 'saved_utc': r['saved_utc'], 'action': r['action']['type'], 'hash': r['hash']} for r in store.history],
                                            'live_enabled': False, 'baseten_live_enabled': False, 'read_only': isinstance(store, CompletedCycle), 'completed_cycle': store.summary() if isinstance(store, CompletedCycle) else None,
                                            'molecular':workspace.molecular.view(current) if workspace.molecular else None,'molecular_error':workspace.molecular_error,
                                            'public_algae':workspace.public_algae.view(current) if workspace.public_algae else None,'public_algae_error':workspace.public_algae_error,
                                            'intelligence':workspace.intelligence.view(current) if workspace.intelligence else None,'intelligence_error':workspace.intelligence_error,
                                            'intelligence_next':workspace.intelligence_next.view(workspace.intelligence,intelligence.context(current)),
                                            'intelligence_execution':execution_view(current),'intelligence_execution_error':workspace.intelligence_execution_error,
                                            'assistant':workspace.assistant.view() if workspace.assistant else None,'assistant_error':workspace.assistant_error,
                                            'research_story':workspace.research_story.view() if workspace.research_story else None,'research_story_error':workspace.research_story_error,
                                            'workbench':workspace.workbench.view() if workspace.workbench else None,'workbench_error':workspace.workbench_error,
                                            'showcase_pilots':workspace.showcase_pilots,
                                            'release_review':workspace.release_review.view() if workspace.release_review else None,'release_review_error':workspace.release_review_error,
                                            'steps':workspace.steps.view() if workspace.steps else None,'steps_error':workspace.steps_error}); return
                    if path in ('/api/study-review/export.json','/api/study-review/export.txt'):
                        owner=workspace.release_review
                        if owner is None:raise ValueError('Study review unavailable')
                        acknowledgment=self.headers.get('X-Traitweaver-Privacy-Reviewed')
                        if path.endswith('.json'):self.send(200,owner.export(acknowledgment),filename='traitweaver-study-review.json')
                        else:self.send(200,owner.readable(acknowledgment),'text/plain; charset=utf-8',filename='traitweaver-study-review.txt')
                        return
                    if path in ('/api/workbench/export.json','/api/workbench/export.md'):
                        owner=workspace.workbench
                        if owner is None:raise ValueError('Workbench unavailable')
                        reviewed=self.headers.get('X-Traitweaver-Privacy-Reviewed')
                        if path.endswith('.json'):self.send(200,owner.export(reviewed),filename='traitweaver-workbench.json')
                        else:self.send(200,owner.readable(reviewed),'text/markdown; charset=utf-8',filename='traitweaver-workbench.md')
                        return
                    if path in ('/api/research-story/export.json','/api/research-story/export.txt'):
                        owner=workspace.research_story
                        if owner is None:raise ValueError('Research story unavailable')
                        if path.endswith('.json'):self.send(200,owner.export(),filename='traitweaver-research-story.json')
                        else:self.send(200,owner.readable(),'text/plain; charset=utf-8',filename='traitweaver-research-story.txt')
                        return
                    if path in ('/api/steps/export.json','/api/steps/export.txt'):
                        owner=workspace.steps
                        if owner is None:raise ValueError('Completed-step review unavailable')
                        if path.endswith('.json'):self.send(200,owner.export(),filename='traitweaver-completed-steps.json')
                        else:self.send(200,owner.readable(),'text/plain; charset=utf-8',filename='traitweaver-completed-steps.txt')
                        return
                    if path in ('/api/assistant/export.json','/api/assistant/export.txt'):
                        owner=workspace.assistant
                        if owner is None:raise ValueError('Assistant review unavailable')
                        if path.endswith('.json'):self.send(200,owner.export(),filename='traitweaver-assistant-review.json')
                        else:self.send(200,owner.readable(),'text/plain; charset=utf-8',filename='traitweaver-assistant-review.txt')
                        return
                    if path in ('/api/intelligence/export.json','/api/intelligence/export.txt'):
                        journal=workspace.intelligence
                        if journal is None:raise ValueError('Intelligence review unavailable')
                        if path.endswith('.json'):self.send(200,journal.export(),filename='traitweaver-intelligence-review.json')
                        else:self.send(200,journal.readable(),'text/plain; charset=utf-8',filename='traitweaver-intelligence-review.txt')
                        return
                    if path in ('/api/public-algae/export.json','/api/public-algae/export.txt'):
                        journal=workspace.public_algae
                        if journal is None:raise ValueError('Public algae review unavailable')
                        if path.endswith('.json'):self.send(200,journal.export(),filename='traitweaver-public-algae-review.json')
                        else:self.send(200,journal.readable(),'text/plain; charset=utf-8',filename='traitweaver-public-algae-review.txt')
                        return
                    if path == '/api/molecular/export.json':
                        if workspace.molecular is None:raise ValueError('Molecular review unavailable')
                        self.send(200,workspace.molecular.export(),filename='traitweaver-molecular-review.json');return
                    if path == '/api/molecular/export.txt':
                        if workspace.molecular is None:raise ValueError('Molecular review unavailable')
                        self.send(200,workspace.molecular.readable(),'text/plain; charset=utf-8',filename='traitweaver-molecular-review.txt');return
                    if path == '/api/cycle-review.json' and isinstance(store, CompletedCycle):
                        self.send(200, store.export_review(), filename='traitweaver-completed-cycle.json'); return
                    if path == '/api/export.json':
                        self.send(200, store.export(), filename='traitweaver-study.json'); return
                    if path == '/api/export.md':
                        store.export()  # Same privacy and size gate as the JSON package.
                        state = store.current()['state']
                        self.send(200, store.readable() if isinstance(store, CompletedCycle) else study.readable(state), 'text/markdown; charset=utf-8', filename='traitweaver-study.md'); return
                    self.send(404, {'error': 'Unknown endpoint'}); return
                if path == '/gfp':
                    self.send(200, protein_card.render_html(protein_card.build_card()), 'text/html; charset=utf-8', csp=None); return
                if path.startswith('/public-algae-source/'):
                    if workspace.public_algae is None:raise ValueError('Public algae source validation failed')
                    name=path.removeprefix('/public-algae-source/')
                    self.send(200,public_algae.source_file(name),'text/plain; charset=utf-8');return
                path = '/index.html' if path == '/' else path
                if path not in assets:
                    self.send(404, {'error': 'Unknown resource'}); return
                mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                self.send(200, assets[path].read_bytes(), mime)
            except (ValueError, OSError):
                self.send(400, {'error': 'Selected local data is unavailable or failed validation'})

        def do_POST(self):
            with workspace.mutex:
                self.read_post()

        def read_post(self):
            store=workspace.active
            if not self.safe_host() or not hmac.compare_digest(self.headers.get('X-Traitweaver-Token', ''), token):
                self.send(403, {'error': 'Same-origin session authorization required'}); return
            if isinstance(store, CompletedCycle) and urlsplit(self.path).path not in ('/api/study-review/apply','/api/study-review/open','/api/study-review/local','/api/steps/source','/api/steps/check','/api/steps/open','/api/steps/local','/api/cycle-review/open','/api/molecular/save','/api/molecular/open','/api/public-algae/save','/api/public-algae/open','/api/intelligence/execution/approve','/api/intelligence/execution/run','/api/intelligence/execution/reassess','/api/intelligence/execution/retry','/api/intelligence/execution/cancel','/api/intelligence/execution/open','/api/intelligence/execution/local','/api/intelligence/next/prepare','/api/intelligence/next/synthetic','/api/intelligence/next/validate','/api/intelligence/next/open','/api/intelligence/next/select','/api/intelligence/revise','/api/intelligence/prepare','/api/intelligence/synthetic','/api/intelligence/accept','/api/intelligence/run','/api/intelligence/open','/api/assistant/select','/api/assistant/synthetic','/api/assistant/check','/api/assistant/open','/api/research-story/present','/api/research-story/open','/api/workbench/prepare','/api/workbench/select','/api/workbench/present','/api/workbench/save','/api/workbench/history','/api/workbench/check','/api/workbench/synthetic','/api/workbench/open'):
                self.send(403, {'error':'Completed-cycle review is read-only. No edits, reruns or model calls are available.'}); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.send(415, {'error': 'JSON required'}); return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 < length <= MAX_BYTES:
                    self.send(413, {'error': 'Request size unsupported'}); return
                data = study.decode(self.rfile.read(length))
                if not isinstance(data, dict) or 'expected_hash' not in data:
                    raise ValueError('Current revision identity required')
                path = urlsplit(self.path).path
                # Serialize reads, validation, provider admission and commit together.
                with store.mutex:
                    current = store.current()
                    if data['expected_hash'] != current['hash']:
                        raise Conflict('Study changed; reload before applying this action')
                    state = current['state']
                    if path.startswith('/api/study-review/'):
                        owner=workspace.release_review
                        if owner is None:raise ValueError('Study review unavailable')
                        if data.get('review_hash')!=owner.current()['hash']:raise Conflict('Study review changed; refresh before acting')
                        prefix=('expected_hash','review_hash')
                        if path=='/api/study-review/apply':
                            study.fields(data,(*prefix,'event'));owner.apply(data['event'])
                        elif path=='/api/study-review/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str) or len(data['package_json'].encode())>release_review.MAX_BYTES:raise ValueError('Review package too large')
                            replacement=release_review.Session();replacement.open(study.decode(data['package_json']))
                            workspace.release_review=replacement
                        elif path=='/api/study-review/local':
                            study.fields(data,prefix);workspace.release_review=workspace.release_review_local
                        else:self.send(404,{'error':'Unknown study review action'});return
                        self.send(200,{'release_review':workspace.release_review.view()});return
                    elif path.startswith('/api/steps/'):

                        owner=workspace.steps
                        if owner is None:raise ValueError('Completed-step review unavailable')
                        if data.get('steps_hash')!=owner.current()['hash']:raise Conflict('Completed-step revision changed; refresh before acting')
                        prefix=('expected_hash','steps_hash')
                        if path=='/api/steps/source':
                            study.fields(data,(*prefix,'case_id'));owner.apply(data['steps_hash'],{'type':'source','payload':{'case_id':data['case_id']}})
                        elif path=='/api/steps/check':
                            study.fields(data,prefix);owner.apply(data['steps_hash'],{'type':'check','payload':{}})
                        elif path=='/api/steps/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str) or len(data['package_json'].encode())>step_tracking.MAX_BYTES:raise ValueError('Completed-step package too large')
                            workspace.steps=step_tracking.Journal.from_package(study.decode(data['package_json']))
                        elif path=='/api/steps/local':
                            study.fields(data,prefix);workspace.steps=workspace.steps_local
                        else:self.send(404,{'error':'No registered completion action or model transport'});return
                        self.send(200,{'showcase_pilots':workspace.showcase_pilots,
                                            'steps':workspace.steps.view()});return
                    elif path.startswith('/api/workbench/'):

                        owner=workspace.workbench
                        if owner is None:raise ValueError('Workbench unavailable')
                        if data.get('workbench_hash')!=owner.current()['hash']:raise Conflict('Workbench changed. Refresh before changing annotations, running a check or importing.')
                        prefix=('expected_hash','workbench_hash')
                        if path=='/api/workbench/prepare':
                            study.fields(data,prefix)
                            self.send(200,{'prepared':owner.prepare_muse(),'workbench_hash':owner.current()['hash']});return
                        elif path=='/api/workbench/select':
                            study.fields(data,(*prefix,'case_id'));owner.select(data['case_id'])
                        elif path=='/api/workbench/present':
                            study.fields(data,(*prefix,'checkpoint'));owner.present(data['checkpoint'])
                        elif path=='/api/workbench/save':
                            study.fields(data,(*prefix,'question','notes'));owner.save(data['question'],data['notes'])
                        elif path=='/api/workbench/history':
                            study.fields(data,(*prefix,'annotation_hash'));owner.history(data['annotation_hash'])
                        elif path in ('/api/workbench/check','/api/workbench/synthetic'):
                            study.fields(data,prefix);owner.act(path.rsplit('/',1)[-1])
                        elif path=='/api/workbench/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str) or len(data['package_json'].encode())>workbench.MAX_BYTES:raise ValueError('Workbench JSON exceeds supported size')
                            owner.open(study.decode(data['package_json']))
                        else:self.send(404,{'error':'No registered workbench action or provider transport'});return
                        self.send(200,{'workbench':owner.view(),'assistant':workspace.assistant.view(),
                            'research_story':workspace.research_story.view() if workspace.research_story else None});return
                    elif path.startswith('/api/research-story/'):
                        owner=workspace.research_story
                        if owner is None:raise ValueError('Research story unavailable')
                        if data.get('story_hash')!=owner.current()['hash']:raise Conflict('Research story changed. Refresh before changing or importing a presentation.')
                        prefix=('expected_hash','story_hash')
                        if path=='/api/research-story/present':
                            study.fields(data,(*prefix,'view'));owner.present(data['view'])
                        elif path=='/api/research-story/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str) or len(data['package_json'].encode())>256*1024:raise ValueError('Research story package exceeds the supported size')
                            owner.open(study.decode(data['package_json']))
                        else:self.send(404,{'error':'No research-story tool, provider or laboratory endpoint exists'});return
                        self.send(200,{'research_story':owner.view()});return
                    elif path.startswith('/api/assistant/'):
                        owner=workspace.assistant
                        if owner is None:raise ValueError('Assistant review unavailable')
                        if data.get('assistant_hash')!=owner.current()['hash']:raise Conflict('Assistant view changed. Refresh before changing or reopening a case.')
                        prefix=('expected_hash','assistant_hash')
                        if path=='/api/assistant/select':
                            study.fields(data,(*prefix,'case_id'));owner.select(data['case_id'])
                        elif path in ('/api/assistant/synthetic','/api/assistant/check'):
                            study.fields(data,prefix)
                            if path.endswith('/synthetic'):owner.synthetic()
                            else:owner.check()
                        elif path=='/api/assistant/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str) or len(data['package_json'].encode())>256*1024:raise ValueError('Assistant package must be bounded JSON text')
                            owner.open(study.decode(data['package_json']))
                        else:self.send(404,{'error':'No registered assistant endpoint or live transport'});return
                        self.send(200,{'assistant':owner.view()});return
                    elif path.startswith('/api/intelligence/'):
                        j=workspace.intelligence
                        if j is None:raise ValueError('Intelligence review unavailable')
                        if data.get('intelligence_hash')!=j.current()['hash'] or 'intelligence_hash' not in data:raise Conflict('Current intelligence revision identity required')
                        prefix=('expected_hash','intelligence_hash')
                        if path.startswith('/api/intelligence/execution/'):
                            owner=workspace.intelligence_execution;context=intelligence.context(current)
                            if owner is None:raise ValueError('Execution history unavailable; checks are blocked')
                            fields=(*prefix,'execution_hash')
                            if 'execution_hash' not in data:raise Conflict('Current execution identity required')
                            expected=data['execution_hash']
                            if path=='/api/intelligence/execution/approve':
                                study.fields(data,(*fields,'next_review_hash','acknowledged'))
                                workspace.intelligence_next.expect(data['next_review_hash'])
                                if workspace.intelligence_next.read_only:raise ValueError('Imported or archived v2 proposal is read-only')
                                owner.approve(expected,workspace.intelligence_next.current(),j,context,data['acknowledged'])
                            elif path=='/api/intelligence/execution/run':
                                study.fields(data,fields);owner.run(expected,j,context)
                            elif path=='/api/intelligence/execution/reassess':
                                study.fields(data,(*fields,'result_id','acknowledged'))
                                owner.reassess(expected,j,context,data['result_id'],data['acknowledged'])
                            elif path=='/api/intelligence/execution/retry':
                                study.fields(data,(*fields,'result_id','reason','acknowledged'))
                                owner.retry(expected,j,context,data['result_id'],data['reason'],data['acknowledged'])
                            elif path=='/api/intelligence/execution/cancel':
                                study.fields(data,(*fields,'acknowledged'));owner.cancel(expected,data['acknowledged'])
                            elif path=='/api/intelligence/execution/open':
                                study.fields(data,(*fields,'package_json'))
                                if not isinstance(data['package_json'],str):raise ValueError('Execution package must be JSON text')
                                owner.open(expected,study.decode(data['package_json']))
                            elif path=='/api/intelligence/execution/local':
                                study.fields(data,fields);owner.local(expected)
                            else:self.send(404,{'error':'No registered execution operation or live transport'});return
                            self.send(200,intelligence_views(current));return
                        if path.startswith('/api/intelligence/next/'):
                            owner=workspace.intelligence_next;context=intelligence.context(current)
                            fields=(*prefix,'next_review_hash')
                            if 'next_review_hash' not in data:raise Conflict('Current v2 review identity required')
                            expected=data['next_review_hash']
                            if path=='/api/intelligence/next/prepare':
                                study.fields(data,(*fields,'reviewed_preview_sha256','acknowledged','focus'))
                                owner.prepare(expected,j,context,data['reviewed_preview_sha256'],data['acknowledged'],data['focus'])
                            elif path=='/api/intelligence/next/synthetic':
                                study.fields(data,(*fields,'check'));owner.respond(expected,j,context,check=data['check'])
                            elif path=='/api/intelligence/next/validate':
                                study.fields(data,(*fields,'reply'))
                                if not isinstance(data['reply'],str):raise ValueError('V2 response must be JSON text')
                                owner.respond(expected,j,context,raw=data['reply'].encode())
                            elif path=='/api/intelligence/next/open':
                                study.fields(data,(*fields,'package_json'))
                                if not isinstance(data['package_json'],str):raise ValueError('V2 review package must be JSON text')
                                owner.open(expected,study.decode(data['package_json']),j.bundle)
                            elif path=='/api/intelligence/next/select':
                                study.fields(data,(*fields,'review_hash'));owner.select(expected,data['review_hash'])
                            else:self.send(404,{'error':'No registered v2 review operation or live transport'});return
                            self.send(200,intelligence_views(current));return
                        if path=='/api/intelligence/open':
                            study.fields(data,(*prefix,'package_json'))
                            if not isinstance(data['package_json'],str):raise ValueError('Intelligence package must be JSON text')
                            workspace.intelligence=intelligence_store.Journal.from_package(study.decode(data['package_json']),j.bundle)
                            self.send(200,intelligence_views(current));return
                        if j.read_only:raise ValueError('Imported intelligence review is read-only')
                        if path=='/api/intelligence/revise':
                            study.fields(data,(*prefix,'scope'));action={'type':'revise','payload':{'scope':data['scope'],'context':intelligence.context(current)}}
                        else:
                            if j.current()['state']['context']!=intelligence.context(current):raise Conflict('Save intelligence scope for the current owning study revision first')
                            if path=='/api/intelligence/prepare':
                                study.fields(data,(*prefix,'phase','focus'))
                                self.send(200,{'prepared':intelligence_muse.prepare(j.current()['state'],data['phase'],j.bundle,data['focus'])});return
                            if path in ('/api/intelligence/synthetic','/api/intelligence/accept'):
                                if path.endswith('/synthetic'):
                                    study.fields(data,(*prefix,'phase','focus'));raw=study.canonical(intelligence_muse.synthetic_reply(j.current()['state'],data['phase'],j.bundle,data['focus'])).encode()
                                    fingerprint=intelligence_muse.prepare(j.current()['state'],data['phase'],j.bundle,data['focus'])['request_sha256']
                                else:
                                    study.fields(data,(*prefix,'phase','focus','request_sha256','reply'))
                                    if not isinstance(data['reply'],str):raise ValueError('Saved intelligence reply must be text')
                                    raw=data['reply'].encode();fingerprint=data['request_sha256']
                                accepted=intelligence_muse.parse_reply(j.current()['state'],data['phase'],raw,fingerprint,j.bundle,data['focus'])
                                action={'type':'accept','payload':accepted}
                            elif path=='/api/intelligence/run':
                                study.fields(data,prefix);action={'type':'run','payload':{}}
                            else:self.send(404,{'error':'Unregistered intelligence endpoint; no transport available'});return
                        # Share semantic reservations with the separate bridge for new
                        # v1 decisions/runs. Historical replay remains byte-compatible.
                        check=None
                        if action['type']=='accept' and action['payload']['phase']=='selection':
                            check=action['payload']['proposal']['check']
                        elif action['type']=='run':
                            cycle=intelligence.active(j.current()['state'])
                            if cycle and cycle['result'] is None:check=cycle['decision']['check']
                        if check:
                            if workspace.intelligence_execution is None:raise ValueError('Execution history unavailable; checks are blocked')
                            workspace.intelligence_execution.guard(check,j.current()['state']['scope'])
                        j.apply(data['intelligence_hash'],action);self.send(200,intelligence_views(current));return
                    elif path in ('/api/public-algae/save','/api/public-algae/open'):
                        journal=workspace.public_algae
                        if journal is None:raise ValueError('Public algae review unavailable')
                        if path.endswith('/save'):
                            study.fields(data,('expected_hash','molecular_hash','selection','stage','note'))
                            journal.save(data['molecular_hash'],{'selection':data['selection'],'stage':data['stage'],'note':data['note'],'context':molecular.context(current)})
                        else:
                            study.fields(data,('expected_hash','molecular_hash','package_json'))
                            if data['molecular_hash']!=journal.current()['hash']:raise Conflict('Public algae review changed; reload before opening')
                            if not isinstance(data['package_json'],str):raise ValueError('Public algae review must be JSON text')
                            journal=molecular_store.Journal.from_package(study.decode(data['package_json']),journal.bundle)
                            workspace.public_algae=journal
                        self.send(200,{'public_algae':journal.view(current)});return
                    elif path == '/api/molecular/save':
                        study.fields(data, ('expected_hash','molecular_hash','selection','stage','note'))
                        journal=workspace.molecular
                        if journal is None:raise ValueError('Molecular review unavailable')
                        journal.save(data['molecular_hash'],{'selection':data['selection'],'stage':data['stage'],'note':data['note'],'context':molecular.context(current)})
                        self.send(200,{'molecular':journal.view(current)});return
                    elif path == '/api/molecular/open':
                        study.fields(data, ('expected_hash','molecular_hash','package_json'))
                        journal=workspace.molecular
                        if journal is None:raise ValueError('Molecular review unavailable')
                        if data['molecular_hash']!=journal.current()['hash']:raise Conflict('Molecular review changed; reload before opening')
                        if not isinstance(data['package_json'],str):raise ValueError('Molecular review must be JSON text')
                        imported=molecular_store.Journal.from_package(study.decode(data['package_json']),journal.bundle)
                        workspace.molecular=imported
                        self.send(200,{'molecular':imported.view(current)});return
                    elif path == '/api/cycle-review/open':
                        study.fields(data, ('expected_hash','review_json'))
                        if not isinstance(data['review_json'],str):
                            raise ValueError('Completed review must be JSON text')
                        review=CompletedCycle.from_review(study.decode(data['review_json']))
                        workspace.active=review
                        self.send(200, {'current':review.current(),'read_only':True}); return
                    elif path == '/api/study/revise':
                        study.fields(data, ('expected_hash', 'brief')); action = {'type': 'edit', 'payload': data['brief']}
                    elif path == '/api/decision/prepare':
                        study.fields(data, ('expected_hash', 'check', 'arguments'))
                        action = {'type': 'decide', 'payload': {'check': data['check'], 'arguments': data['arguments'], 'policy': 'user_selected'}}
                    elif path in ('/api/check/run', '/api/reassess'):
                        study.fields(data, ('expected_hash',))
                        action = {'type': 'run' if path.endswith('/run') else 'reassess', 'payload': {}}
                    elif path == '/api/restore':
                        study.fields(data, ('expected_hash', 'package_json'))
                        if not isinstance(data['package_json'], str):
                            raise ValueError('Saved package must be JSON text')
                        action = {'type': 'restore', 'payload': study.decode(data['package_json'])}
                    elif path == '/api/muse/prepare':
                        study.fields(data, ('expected_hash', 'phase'))
                        self.send(200, muse_boundary.prepare(state, data['phase'])); return
                    elif path in ('/api/muse/accept', '/api/muse/synthetic'):
                        if path.endswith('/synthetic'):
                            study.fields(data, ('expected_hash', 'phase'))
                            raw = study.canonical(muse_boundary.synthetic_reply(state, data['phase'])).encode()
                            fingerprint = muse_boundary.prepare(state, data['phase'])['request_sha256']
                        else:
                            study.fields(data, ('expected_hash', 'phase', 'reply', 'request_sha256'))
                            if not isinstance(data['reply'], str):
                                raise ValueError('Saved provider reply must be text')
                            raw = data['reply'].encode(); fingerprint = data['request_sha256']
                        payload = muse_boundary.parse_reply(state, data['phase'], raw, fingerprint)
                        action = {'type': 'muse_accept', 'payload': payload}
                    else:
                        self.send(404, {'error': 'Unknown endpoint'}); return
                    self.send(200, {'current': store.apply(current['hash'], action)})
            except Conflict as exc:
                self.send(409, {'error': str(exc)})
            except (ValueError, KeyError, TypeError, RecursionError) as exc:
                self.send(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Malformed request; study unchanged'})
            except OSError:
                self.send(500, {'error': 'Local write failed. Reload to inspect the last committed revision; previous revisions were not overwritten.'})

    server = server_factory(('127.0.0.1', port), Handler)
    server.workspace=workspace
    server.daemon_threads = True
    return server


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description='Traitweaver guided local research workspace. No live APIs.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--data-dir', type=Path, help='External directory for durable study revisions')
    source.add_argument('--completed-cycle-dir', type=Path, help='Read-only completed local packet')
    source.add_argument('--completed-cycle-file', type=Path, help='Reopen exported cycle-with-usage JSON read-only')
    source.add_argument('--demo', action='store_true', help='Clearly synthetic offline replay; no provider calls')
    parser.add_argument('--port', type=int, default=0, help='Loopback port; default chooses an available port')
    parser.add_argument('--rna-pilot-dir', type=Path, help='Explicit saved RNA comparison directory; read-only')
    parser.add_argument('--completion-pilot-dir', type=Path, help='Explicit saved completion comparison directory; read-only')
    options = parser.parse_args(args)
    if not 0 <= options.port <= 65535:
        parser.error('Port must be between 0 and 65535')
    store = None; server = None
    try:
        store = (CompletedCycle(study.APP_ROOT/'data/synthetic-cycle') if options.demo else
                 CompletedCycle.from_file(options.completed_cycle_file) if options.completed_cycle_file else
                 CompletedCycle(options.completed_cycle_dir) if options.completed_cycle_dir else Store(options.data_dir))
        pilot_options={}
        if options.rna_pilot_dir is not None:pilot_options['rna_pilot_dir']=options.rna_pilot_dir
        if options.completion_pilot_dir is not None:pilot_options['completion_pilot_dir']=options.completion_pilot_dir
        server = make_server(store, options.port, **pilot_options)
        print('Open Traitweaver: http://127.0.0.1:'+str(server.server_port)+'/#journey', flush=True)
        print('Read-only recorded cycle. No execution.' if isinstance(store,CompletedCycle) else 'Local study storage. Browser transport disabled.', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError) as exc:
        parser.exit(1, 'Workspace stopped: '+(str(exc) if isinstance(exc, ValueError) else 'Local server or storage unavailable')+'\n')
    finally:
        if server:
            server.server_close()
        if store:
            store.close()
    return 0
