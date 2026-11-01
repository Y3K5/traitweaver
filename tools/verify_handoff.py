"""Verify exact candidate bytes and reject unexpected/secret-named files.

No network or Git mutation. The separate human/privacy screen remains required.
"""
import hashlib
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def verify():
    manifest_path=ROOT/'HANDOFF_MANIFEST.json'
    if manifest_path.is_symlink():raise ValueError('Unsafe manifest')
    manifest=json.loads(manifest_path.read_text())
    expected={entry['path']:entry for entry in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate manifest entry')
    # Only root Git metadata is omitted. Never traverse or open its contents.
    actual=set()
    for folder,directories,names in os.walk(ROOT,followlinks=False):
        base=Path(folder)
        if base==ROOT:directories[:]=[name for name in directories if name!='.git']
        for name in directories+names:
            path=base/name;relative=path.relative_to(ROOT).as_posix()
            if relative=='.git':continue
            if path.is_symlink():raise ValueError('Symlinks are not permitted')
            if '.git' in path.relative_to(ROOT).parts:raise ValueError('Embedded Git metadata is excluded')
            if re.search(r'(^|/)(\.env(?:\..*)?|credentials[^/]*|secrets[^/]*)(?:/|$)|\.(pem|key|p12|pfx)$',relative,re.I):
                raise ValueError('Secret-named path found; no content read')
            if path.is_file():actual.add(relative)
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
            'publication_approved':False,'git_metadata':'Root .git ignored without inspection; never part of the candidate file list','note':'Checksum/membership verification is not independent privacy, scientific or rights approval.'}

if __name__=='__main__':
    print(json.dumps(verify(),indent=2))
