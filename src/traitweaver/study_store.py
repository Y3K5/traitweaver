"""Immutable, hash-linked local study revisions and self-contained package replay."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import threading
import uuid

from traitweaver import study

MAX_BYTES = 4 * 1024 * 1024
MAX_REVISIONS = 256


def screen_export(value):
    """Report excluded-looking content; never silently redact a study."""
    raw = study.canonical(value)
    checks = {
        'personal filesystem path': r'/Users/|/home/|\$HOME',
        'credential-shaped content': r'(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)',
        'response cookie': r'(?i)set-cookie\s*:',
    }
    findings = [name for name, pattern in checks.items() if re.search(pattern, raw)]
    if findings:
        raise ValueError('Export requires owner privacy review: '+', '.join(findings)+'. No content was removed.')


class Conflict(ValueError):
    pass








def package(revisions):
    return {'schema_version': 'traitweaver.study_package.v1', 'source_bundle': study.bundle(),
            'revisions': deepcopy(revisions), 'limits': study.LIMIT}

def validate_package(value, depth=0):
    if depth > 3:
        raise ValueError('Restore nesting limit exceeded')
    study.fields(value, ('schema_version', 'source_bundle', 'revisions', 'limits'))
    if (value['schema_version'] != 'traitweaver.study_package.v1' or
        study.canonical(value['source_bundle']) != study.canonical(study.bundle()) or value['limits'] != study.LIMIT):
        raise ValueError('Package source identity or schema is unsupported')
    revisions = value['revisions']
    if not isinstance(revisions, list) or not 1 <= len(revisions) <= MAX_REVISIONS:
        raise ValueError('Unsupported revision count')
    prior = None; state = None
    for number, r in enumerate(revisions, 1):
        study.fields(r, ('schema_version', 'revision', 'parent_hash', 'saved_utc', 'action', 'state', 'hash'))
        if r['schema_version'] != 'traitweaver.study_revision.v1' or type(r['revision']) is not int or r['revision'] != number or r['parent_hash'] != prior:
            raise ValueError('Broken revision chain')
        try:
            parsed = datetime.fromisoformat(r['saved_utc'])
            if parsed.tzinfo is None:
                raise ValueError('Timestamp lacks timezone')
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid revision timestamp') from exc
        study.fields(r['action'], ('type', 'payload'))
        if not isinstance(r['state'], dict):
            raise ValueError('Recorded state must be an object')
        if number == 1:
            if r['action'] != {'type': 'initialize', 'payload': {}}:
                raise ValueError('Missing initialization')
            state = study.initial_state()
        elif r['action']['type'] == 'restore':
            restored = validate_package(r['action']['payload'], depth+1)['state']
            if restored['study_id'] != state['study_id']:
                raise ValueError('Restore cannot change the owning study identity')
            state = restored
        elif r['action']['type'] == 'muse_accept':
            from traitweaver.muse_boundary import accept_action
            state = accept_action(state, r['action']['payload'])
        else:
            recorded = None
            if r['action']['type'] == 'run':
                cycles = r['state'].get('cycles')
                if not isinstance(cycles, list) or not cycles or not isinstance(cycles[-1], dict):
                    raise ValueError('Result revision lacks its cycle')
                recorded = cycles[-1].get('result')
                if not isinstance(recorded, dict):
                    raise ValueError('Result revision lacks its receipt')
            state = study.transition(state, r['action'], recorded_result=recorded)
        if study.canonical(state) != study.canonical(r['state']):
            raise ValueError('Recorded state does not replay from its actions')
        unsigned = {k: v for k, v in r.items() if k != 'hash'}
        if r['hash'] != study.digest(unsigned):
            raise ValueError('Revision checksum mismatch')
        prior = r['hash']
    if value['schema_version'] != package(revisions)['schema_version']:
        raise ValueError('Package version does not match its recorded state contract')
    return deepcopy(revisions[-1])


class Store:
    def __init__(self, directory):
        path = Path(directory)
        resolved = path.resolve()
        if path.is_symlink() or study.APP_ROOT == resolved or study.APP_ROOT in resolved.parents:
            raise ValueError('Choose a regular data directory outside the application')
        # Refuse symlink components even if their resolved destination looks safe.
        aliases = {Path('/var'): Path('/private/var'), Path('/tmp'): Path('/private/tmp')}
        if any(p.is_symlink() and not (p in aliases and p.resolve() == aliases[p]) for p in (path.absolute(), *path.absolute().parents)):
            raise ValueError('Data directory must not use symlinks')
        if not path.parent.is_dir():
            raise ValueError('Data directory parent must already exist')
        path.mkdir(exist_ok=True)
        self.root = resolved
        self.lock_path = resolved / '.workspace-owner.lock'
        try:
            self.lock_fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(self.lock_fd, str(os.getpid()).encode())
        except FileExistsError as exc:
            raise ValueError('Data directory is already owned or has a retained lock; do not start a second writer. After an interrupted process, verify it is stopped before removing only .workspace-owner.lock.') from exc
        self.mutex = threading.RLock()
        try:
            self.history = self._read()
            if not self.history:
                self._append({'type': 'initialize', 'payload': {}}, study.initial_state())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
            self.lock_path.unlink()

    def _read(self):
        records = []
        for path in sorted(self.root.glob('revision-*.json')):
            if path.is_symlink() or path.stat().st_size > MAX_BYTES:
                raise ValueError('Unsafe or oversized revision file')
            r = study.decode(path.read_bytes())
            if path.name != 'revision-'+str(len(records)+1).zfill(6)+'.json':
                raise ValueError('Missing or unexpected revision filename')
            records.append(r)
        if records:
            validate_package(package(records))
        return records

    def current(self):
        with self.mutex:
            return deepcopy(self.history[-1])

    def export(self):
        with self.mutex:
            result = package(self.history)
            if len(study.canonical(result).encode()) > MAX_BYTES:
                raise ValueError('Package exceeds the supported size')
            screen_export(result)
            return result

    def _append(self, action, state):
        if len(self.history) >= MAX_REVISIONS:
            raise ValueError('Revision limit reached; export for review')
        r = {'schema_version': 'traitweaver.study_revision.v1', 'revision': len(self.history)+1,
             'parent_hash': self.history[-1]['hash'] if self.history else None,
             'saved_utc': datetime.now(timezone.utc).isoformat(), 'action': deepcopy(action), 'state': state}
        r['hash'] = study.digest(r)
        payload = (study.canonical(r)+'\n').encode()
        if len(payload) > MAX_BYTES or len(study.canonical(package(self.history+[r])).encode()) > MAX_BYTES:
            raise ValueError('Study size limit reached')
        dest = self.root / ('revision-'+str(r['revision']).zfill(6)+'.json')
        pending = self.root / ('.pending-'+uuid.uuid4().hex)
        try:
            with pending.open('xb') as f:
                os.chmod(pending, 0o600)
                f.write(payload); f.flush(); os.fsync(f.fileno())
            # Atomic publication without replacing an earlier revision.
            os.link(pending, dest)
            self.history.append(r)
            fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            pending.unlink(missing_ok=True)
        return deepcopy(r)

    def apply(self, expected_hash, action):
        with self.mutex:
            current = self.history[-1]
            if expected_hash != current['hash']:
                raise Conflict('Study changed; reload before applying this action')
            if action['type'] == 'restore':
                state = validate_package(action['payload'])['state']
                if state['study_id'] != current['state']['study_id']:
                    raise ValueError('Saved package belongs to another study; open that study before restoring')
            elif action['type'] == 'muse_accept':
                from traitweaver.muse_boundary import accept_action
                state = accept_action(current['state'], action['payload'])
            else:
                state = study.transition(current['state'], action)
            return self._append(action, state)


