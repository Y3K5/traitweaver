"""Generate only a clearly synthetic replay from admitted public evidence.

No live grant, credential access or external traffic. Existing outputs refused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_completed_cycle import fixture
from traitweaver.completed_cycle import CompletedCycle

FILES=('01-selection.json','02-reassessment-coverage.json','PUBLIC_CYCLE.json',
       'SYNTHETIC_APPROVAL.json','STATUS.json','STUDY_PACKAGE.json',
       'RECEIPT-selection.json','RECEIPT-reassessment.json')

def build(output):
    output=Path(output)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Choose a fresh directory with an existing parent')
    with tempfile.TemporaryDirectory(prefix='traitweaver-synthetic-replay-') as temporary:
        source=fixture(Path(temporary)/'synthetic-packet',synthetic=True)
        output.mkdir()
        hashes={}
        for name in FILES:
            raw=(source/name).read_bytes();(output/name).write_bytes(raw)
            hashes[name]=hashlib.sha256(raw).hexdigest()
        raw=(json.dumps(CompletedCycle(source).export_review(),indent=2)+'\n').encode()
        (output/'REVIEW_PACKAGE.json').write_bytes(raw)
        hashes['REVIEW_PACKAGE.json']=hashlib.sha256(raw).hexdigest()
        (output/'FIXTURE_PROVENANCE.json').write_text(json.dumps({
            'schema_version':'traitweaver.synthetic_fixture_provenance.v1',
            'kind':'clearly_synthetic_offline_demo','generator':'tools/make_synthetic_cycle.py',
            'evidence':'Unmodified admitted public algae facts and source IDs',
            'synthetic_fields':['model choices','accepted synthetic reply receipts','token counts','cost estimates','execution timing'],
            'transport_calls':0,'credentials_used':False,'provider_ids_included':False,
            'approval_enabled':False,'purpose':'Portable read-only walkthrough and software verification; not proof of a live contribution',
            'files_sha256':hashes},indent=2)+'\n')
    return {'status':'synthetic_only','provider_calls':0,'files':10}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    print(json.dumps(build(parser.parse_args().output_dir)))
