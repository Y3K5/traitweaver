"""Prepare public-only Muse research batches locally; this tool cannot send."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from traitweaver import trait_library as library, study

PRICES = {'input_usd_per_million': '1.25', 'output_usd_per_million': '4.25',
          'cached_input_usd_per_million': '0.15', 'checked': '2026-11-04',
          'source': 'https://dev.meta.ai/docs/pricing-rate-limits'}
HARD_CAP_SOURCE = 'https://dev.meta.ai/help/billing/spend-limit-alert'


def prepare(destination):
    destination = Path(destination).expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError('Generated review packets must be outside the source repository')
    if destination.exists():
        raise ValueError('Use a fresh directory; no existing packet will be overwritten')
    bundle = library.catalog()
    packets = [library.prepare_request(bundle, t['id'], 'alga') for t in bundle['traits']]
    requests = []
    for number, packet in enumerate(packets, 1):
        size = len(study.canonical(packet['body']).encode())
        # Estimates only. Neither heuristic is a verified tokenizer/billing bound.
        estimate = (Decimal(size)/4*Decimal('1.25')+8192*Decimal('4.25'))/1000000
        reserve = (Decimal(size+1024)*Decimal('1.25')+8192*Decimal('4.25'))/1000000
        requests.append({'id': f'request-{number:02d}', 'batch': (number-1)//2+1,
                         'provider': 'meta_direct', 'model': library.MODEL,
                         'request_sha256': packet['request_sha256'], 'request_bytes': size,
                         'estimated_input_tokens': size/4, 'max_output_tokens': 8192,
                         'estimated_cost_at_output_cap_usd': str(estimate),
                         'conservative_planning_reservation_usd': str(reserve),
                         'status': 'prepared_not_sent', 'input_tokens': None, 'cached_input_tokens': None,
                         'output_tokens': None, 'estimated_cost_from_actual_usage_usd': None,
                         'actual_invoiced_cost_usd': None, 'provider_receipt': None,
                         'primary_source_verification': 'pending_after_any_model_output',
                         'reviewer_decision': None})
    batches = [{'batch': n, 'request_ids': [r['id'] for r in requests if r['batch']==n],
                'proposed_application_limit_usd': '0.20',
                'estimated_cost_at_output_cap_usd': str(sum(Decimal(r['estimated_cost_at_output_cap_usd']) for r in requests if r['batch']==n)),
                'actual_invoiced_cost_usd': None, 'status': 'blocked_not_sent'} for n in (1,2,3)]
    manifest = {'schema_version': 'traitweaver.trait_research_batch_plan.v1',
                'provider': 'meta_direct', 'model': library.MODEL, 'mode': 'Standard',
                'destination': library.DESTINATION, 'pricing': PRICES, 'batches': batches,
                'requests': requests, 'new_provider_calls': 0, 'approved': False,
                'account_credit_balance': None, 'credit_expiration': None,
                'hard_cap_status': 'provider_documentation_says_no_hard_cap',
                'hard_cap_source': HARD_CAP_SOURCE,
                'execution_limit_usd': '0.00',
                'execution_guard': 'NO_TRANSPORT_IMPLEMENTED_AND_NO_CREDIT_ONLY_GUARANTEE',
                'no_overage_guarantee': 'Only zero execution is currently enforced; application budgets are not provider billing caps.',
                'limits': ['Two requests per proposed batch; six total; no retries or fallback',
                           'Only curated public sources, dossier, comparison and instructions are proposed for sending',
                           'No reviewer notes, private study files, credentials or saved historical model packets included',
                           'Actual invoice cost stays unknown until provider billing evidence is reconciled',
                           'Any later live implementation requires exact approval and verified credit protection',
                           'Model suggestions must be checked against primary sources and reviewed before use']}
    destination.mkdir(parents=True)
    for row, packet in zip(requests, packets):
        (destination/(row['id']+'.json')).write_text(json.dumps(packet, ensure_ascii=False, indent=2)+'\n')
        (destination/(row['id']+'-body.json')).write_text(study.canonical(packet['body']))
    (destination/'BATCH_PLAN.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    options=parser.parse_args()
    plan=prepare(options.output)
    print(json.dumps({'status':plan['execution_guard'],'batches':plan['batches'],'new_provider_calls':0},indent=2))


if __name__ == '__main__': main()
