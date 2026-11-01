"""Read-only projections of explicitly selected saved pilot results. No transport."""
from pathlib import Path
from traitweaver import study, evaluation_pilot, completion_pilot


def load_pilot(directory, kind):
    if directory is None:
        return {'status': 'not_loaded'}
    module = {'rna': evaluation_pilot, 'completion': completion_pilot}[kind]
    try:
        root = Path(directory)
        if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('Unsafe directory')
        records = []
        for slot in module.protocol()['slots']:
            folder = root / slot['id']
            path = folder / 'pilot-result.json'
            if folder.is_symlink() or path.is_symlink():
                raise ValueError('Unsafe result')
            if not path.exists():
                continue
            if path.stat().st_size > module.MAX_BYTES:
                raise ValueError('Oversized result')
            record = module.validate_record(study.decode(path.read_bytes()))
            if record['slot_id'] != slot['id']:
                raise ValueError('Misplaced result')
            records.append(record)
        if not records:
            return {'status': 'not_loaded'}
        summary = module.summary(records)
        return {'status': 'loaded', 'synthetic': records[0]['transport_qualification'] == 'offline_synthetic',
                'summary': summary,
                'verdicts': [{'slot_id':r['slot_id'], 'unique_labels':next(j['verdict'] for j in r['evaluation_result']['answer']['judgments'] if j['claim_id']=='RNA_UNIQUE_LABELS')} for r in records],
                'record_hashes': [r['sha256'] for r in records],
                'qualification': 'Local record consistency only; not independent provider authentication. Synthetic scientific inputs. Human usefulness not reviewed.'}
    except (ValueError, OSError, KeyError, TypeError):
        return {'status': 'invalid', 'error': 'Selected saved pilot failed validation. No results substituted.'}
