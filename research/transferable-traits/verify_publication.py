"""Check exact study membership/hashes plus obvious sensitive payload patterns.

This local screen is not a complete privacy/rights audit or publication approval.
It never reads outside the explicitly supplied study directory.
"""
import hashlib
import json
from pathlib import Path
import re
import sys


def verify(root):
    root=Path(root)
    manifest=json.loads((root/'PUBLICATION_MANIFEST.json').read_text())
    expected={x['path']:x for x in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate manifest members')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected)|{'PUBLICATION_MANIFEST.json'}:raise ValueError('Unexpected or missing study file')
    findings=[]
    patterns={
        'private_key':r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
        'token':r'\b(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}',
        'signed_transfer':r'https://[^\s"\']*oaiusercontent\.com|[?&]sig=[^\s"\']+',
        'private_library_identity':r'\blibfile_[a-f0-9]{24,}',
        'private_user_path':r'/(?:Users|home)/[A-Za-z0-9_.-]+/',
    }
    for name,entry in expected.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe manifest path')
        p=root/relative
        if p.is_symlink():raise ValueError('Symlink publication forbidden')
        raw=p.read_bytes()
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Checksum mismatch: '+name)
        content=raw.decode('utf-8')
        for category,pattern in patterns.items():
            if re.search(pattern,content):findings.append({'path':name,'category':category})
    if findings:raise ValueError(json.dumps({'findings':findings}))
    return {'status':'exact_study_verified','files':len(actual),'sensitive_pattern_findings':0,
            'note':'Exact membership and limited pattern screen only; source rights/science are separate.'}


if __name__=='__main__':print(json.dumps(verify(sys.argv[1] if len(sys.argv)>1 else Path(__file__).parent),indent=2))
