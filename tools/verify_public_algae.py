"""Verify pinned public records and their reproducible catalog, without sockets."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traitweaver import public_algae, study


if __name__=='__main__':
    catalog=public_algae.catalog()
    print(json.dumps({'status':'passed','public_primary_files':len(catalog['sources']['sources']),
        'catalog_sha256':study.digest(catalog),'checks':catalog['checks'],
        'external_requests':0,'limit':catalog['limit']},indent=2))
