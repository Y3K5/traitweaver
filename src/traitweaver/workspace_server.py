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

from traitweaver import muse_boundary, protein_card, study
from traitweaver.study_store import Conflict, MAX_BYTES, Store
from traitweaver.completed_cycle import CompletedCycle

WEB = Path(__file__).with_name('web')
CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


class WorkspaceSession:
    """Imported reviews replace only the in-memory view, never the study store."""
    def __init__(self, store):
        self.active=store
        self.mutex=threading.RLock()


def make_server(store, port=0, server_factory=ThreadingHTTPServer):
    workspace=WorkspaceSession(store)
    token = secrets.token_urlsafe(32)
    assets = {'/'+p.relative_to(WEB).as_posix(): p for p in WEB.rglob('*') if p.is_file() and not p.is_symlink()}

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
                    if path == '/api/session':
                        self.send(200, {'token': token}); return
                    if path == '/api/state':
                        with store.mutex:
                            current = store.current()
                            self.send(200, {'current': current, 'evidence': study.bundle(), 'eligible_checks': study.eligible_checks(current['state']),
                                            'history': [{'revision': r['revision'], 'saved_utc': r['saved_utc'], 'action': r['action']['type'], 'hash': r['hash']} for r in store.history],
                                            'live_enabled': False, 'baseten_live_enabled': False, 'read_only': isinstance(store, CompletedCycle), 'completed_cycle': store.summary() if isinstance(store, CompletedCycle) else None}); return
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
            if isinstance(store, CompletedCycle) and urlsplit(self.path).path!='/api/cycle-review/open':
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
                    if path == '/api/cycle-review/open':
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
    options = parser.parse_args(args)
    if not 0 <= options.port <= 65535:
        parser.error('Port must be between 0 and 65535')
    store = None; server = None
    try:
        store = (CompletedCycle(study.APP_ROOT/'data/synthetic-cycle') if options.demo else
                 CompletedCycle.from_file(options.completed_cycle_file) if options.completed_cycle_file else
                 CompletedCycle(options.completed_cycle_dir) if options.completed_cycle_dir else Store(options.data_dir))
        server = make_server(store, options.port)
        print('Open Traitweaver: http://127.0.0.1:'+str(server.server_port)+('/#muse-cycle' if isinstance(store,CompletedCycle) else ''), flush=True)
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
