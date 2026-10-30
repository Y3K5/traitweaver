"""Verify exact candidate bytes and reject unexpected/secret-named files.

No network or Git mutation. The separate human/privacy screen remains required.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def verify():
    manifest_path=ROOT/'HANDOFF_MANIFEST.json'
    if manifest_path.is_symlink():raise ValueError('Unsafe manifest')
    manifest=json.loads(manifest_path.read_text())
    expected={entry['path']:entry for entry in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate manifest entry')
    actual=set()
    for path in ROOT.rglob('*'):
        if path.is_symlink():raise ValueError('Symlinks are not permitted')
        relative=path.relative_to(ROOT).as_posix()
        if relative=='.git' or relative.startswith('.git/'):
            raise ValueError('Git metadata is excluded')
        if not path.is_file():continue
        if re.search(r'(^|/)(\.env(?:\..*)?|credentials[^/]*|secrets[^/]*)$|\.(pem|key|p12|pfx)$',relative,re.I):
            raise ValueError('Secret-named file found; no content read')
        actual.add(relative)
    if actual != set(expected)|{'HANDOFF_MANIFEST.json'}:
        raise ValueError('Candidate membership changed; review the exact file list again')
    for name,entry in expected.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe manifest path')
        raw=(ROOT/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256'] or len(raw)!=entry['bytes']:
            raise ValueError('Candidate checksum mismatch')
    return {'status':'exact_candidate_verified','files':len(actual),
            'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'publication_approved':False,'note':'Checksum/membership verification is not independent privacy, scientific or rights approval.'}

if __name__=='__main__':
    print(json.dumps(verify(),indent=2))
