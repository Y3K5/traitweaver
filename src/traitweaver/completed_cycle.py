"""Read a completed local Muse cycle without rerunning checks or providers.

Only named public-study/receipt files are read. Credentials, local controls,
provider raw responses and unrelated packet files are never opened.
"""
from copy import deepcopy
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import threading
import re

from traitweaver import muse_boundary, study
from traitweaver.study_store import MAX_BYTES, screen_export, validate_package


def read(directory, name):
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Completed cycle file is missing, unsafe or oversized')
    return study.decode(path.read_bytes())


def count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ValueError('Invalid saved token count')
    return value


def money(value):
    if not isinstance(value, str): raise ValueError('Invalid saved cost')
    result = Decimal(value)
    if not result.is_finite() or result < 0: raise ValueError('Invalid saved cost')
    return result


def completed_package(package):
    validate_package(package); screen_export(package)
    revisions = package['revisions']
    if [r['action']['type'] for r in revisions] != ['initialize', 'muse_accept', 'run', 'muse_accept']:
        raise ValueError('Review requires exactly one recorded Muse cycle')
    cycles = revisions[-1]['state']['cycles']
    if len(cycles) != 1 or cycles[0]['result']['status'] != 'completed' or not cycles[0]['assessment']:
        raise ValueError('Expected one completed cycle')
    return revisions, cycles[0]


def validate_review(value):
    """Validate an exported v1 review without a grant, transport or tool dispatch.

    Receipt consistency is preserved. Imported local records are not independent
    provider authentication and never authorize another request.
    """
    study.fields(value, ('schema_version', 'study_package', 'summary'))
    if value['schema_version'] != 'traitweaver.completed_cycle_review.v1':
        raise ValueError('Unsupported completed-cycle review version')
    if len(study.canonical(value).encode()) > MAX_BYTES:
        raise ValueError('Completed-cycle review exceeds the supported size')
    screen_export(value)
    revisions, cycle = completed_package(value['study_package'])
    summary = value['summary']
    study.fields(summary, ('schema_version','status','synthetic','model','mode','completed_utc','approval_sha256',
                          'request_count','maximum_spend_usd','requests','total_input_tokens','total_output_tokens',
                          'total_reasoning_tokens','estimated_cost_usd','actual_provider_charge_usd',
                          'previous_attempt_unresolved_reservation_usd','provenance','reopen_behavior','scientific_limit'))
    if type(summary['synthetic']) is not bool:
        raise ValueError('Explicit synthetic/live marker required')
    synthetic = summary['synthetic']
    provenance = ('Synthetic fixture only; no provider request or charge.' if synthetic else
                  'Recorded live transport; local request/receipt/revision consistency checked. No independent provider authentication.')
    if (summary['schema_version'] != 'traitweaver.completed_cycle_summary.v1' or summary['status'] != 'complete' or
            summary['model'] != muse_boundary.MODEL or summary['mode'] != ('Synthetic offline replay' if synthetic else 'Standard') or
            type(summary['request_count']) is not int or summary['request_count'] != 2 or
            summary['maximum_spend_usd'] != '0.05' or summary['actual_provider_charge_usd'] is not None or
            summary['provenance'] != provenance or summary['scientific_limit'] != study.LIMIT or
            summary['reopen_behavior'] != 'Saved records only. No tool execution, model request, credential read or new revision.'):
        raise ValueError('Review claims or source limits are inconsistent')
    if not isinstance(summary['approval_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}',summary['approval_sha256']):
        raise ValueError('Invalid original approval identity')
    try:
        timestamp=datetime.fromisoformat(summary['completed_utc']) if isinstance(summary['completed_utc'],str) else None
    except ValueError:
        raise ValueError('Invalid completed-cycle timestamp') from None
    if timestamp is None or timestamp.tzinfo is None:
        raise ValueError('Timezone-qualified completion timestamp required')
    rows = summary['requests']
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError('Two phase usage receipts required')
    for row, phase, before, accepted in zip(rows, ('selection','reassessment'),
            (revisions[0]['state'],revisions[2]['state']), (cycle['decision'],cycle['assessment'])):
        study.fields(row, ('phase','input_tokens','output_tokens','reasoning_tokens','estimated_cost_usd',
                           'elapsed_seconds','request_sha256','accepted_response_sha256'))
        preview = muse_boundary.prepare(before,phase)
        if (row['phase'] != phase or row['request_sha256'] != preview['request_sha256'] or
                row['accepted_response_sha256'] != accepted['provider_receipt']['response_sha256'] or
                (accepted['provider_receipt']['provenance']=='synthetic_fixture') != synthetic):
            raise ValueError('Review receipt does not match its saved study revision')
        inputs=count(row['input_tokens']); outputs=count(row['output_tokens']); reasoning=row['reasoning_tokens']
        if inputs > len(study.canonical(preview['body']).encode())+1024 or outputs > 1024:
            raise ValueError('Review usage exceeded the approved allowance')
        if reasoning is not None and count(reasoning)>outputs:
            raise ValueError('Reasoning exceeds output count')
        if money(row['estimated_cost_usd']) != (Decimal(inputs)*Decimal('1.25')+Decimal(outputs)*Decimal('4.25'))/1_000_000:
            raise ValueError('Review usage cost mismatch')
        elapsed=row['elapsed_seconds']
        if type(elapsed) not in (int,float) or not 0 <= elapsed < 86400:
            raise ValueError('Invalid receipt duration')
    for total, field in (('total_input_tokens','input_tokens'),('total_output_tokens','output_tokens')):
        if count(summary[total]) != sum(row[field] for row in rows):
            raise ValueError('Review token total mismatch')
    reasoning_total=sum(row['reasoning_tokens'] for row in rows) if all(row['reasoning_tokens'] is not None for row in rows) else None
    if (summary['total_reasoning_tokens'] is not None and type(summary['total_reasoning_tokens']) is not int) or summary['total_reasoning_tokens'] != reasoning_total:
        raise ValueError('Review reasoning total mismatch')
    total=sum((money(row['estimated_cost_usd']) for row in rows),Decimal('0'))
    if total>Decimal('0.05') or money(summary['estimated_cost_usd']) != total:
        raise ValueError('Review total cost or ceiling mismatch')
    prior=summary['previous_attempt_unresolved_reservation_usd']
    if prior is not None and (synthetic or money(prior)>Decimal('0.05')):
        raise ValueError('Invalid prior-attempt reservation')
    return deepcopy(value)


class CompletedCycle:
    read_only = True

    @classmethod
    def from_review(cls, value):
        try:
            review=validate_review(value)
        except (KeyError, TypeError, IndexError, ArithmeticError, AttributeError) as exc:
            raise ValueError('Malformed completed-cycle review; nothing was executed or changed') from None
        self=cls.__new__(cls)
        self._package=review['study_package'];self._summary=review['summary']
        self.history=deepcopy(self._package['revisions']);self.mutex=threading.RLock()
        return self

    @classmethod
    def from_file(cls, filename):
        path=Path(filename)
        if path.suffix.lower()!='.json' or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
            raise ValueError('Choose a regular bounded completed-cycle JSON file')
        return cls.from_review(study.decode(path.read_bytes()))

    def __init__(self, directory):
        try:
            self._load(directory)
        except (KeyError, TypeError, IndexError, ArithmeticError, AttributeError) as exc:
            raise ValueError('Malformed completed-cycle records; nothing was executed or changed') from None

    def _load(self, directory):
        directory = Path(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Choose a regular completed-cycle directory')
        plan = read(directory, 'PUBLIC_CYCLE.json')
        if plan['approval_sha256'] != study.digest({k:v for k,v in plan.items() if k!='approval_sha256'}):
            raise ValueError('Completed cycle manifest checksum mismatch')
        synthetic = plan.get('fixture_kind') == 'synthetic_demo'
        expected = {'approved': not synthetic, 'approval_sha256': plan['approval_sha256'],
                    'destination': muse_boundary.DESTINATION, 'model': muse_boundary.MODEL,
                    'maximum_spend_usd': '0.05', 'max_requests': 2}
        if (read(directory, 'SYNTHETIC_APPROVAL.json' if synthetic else 'OWNER_APPROVAL.json') != expected or plan['destination'] != muse_boundary.DESTINATION or
                plan['model'] != muse_boundary.MODEL or plan['max_requests'] != 2 or
                plan['maximum_authorized_spend_usd'] != '0.05'):
            raise ValueError('Completed cycle does not match its owner approval')
        package = read(directory, 'STUDY_PACKAGE.json')
        # Uses recorded_result during validation; no tool dispatch or new receipt.
        revisions, cycle = completed_package(package)
        status = read(directory, 'STATUS.json')
        if (status['status'] != 'complete' or status['requests_started'] != 2 or status['requests_completed'] != 2 or
                status['transport'] != ('synthetic_fixture' if synthetic else 'direct_meta_api') or status['approval_sha256'] != plan['approval_sha256']):
            raise ValueError('Live completion record is missing or inconsistent')
        if money(status['reserved_upper_bound_usd']) != 0:
            raise ValueError('Completed cycle still has an unresolved reservation')
        branch = 'coverage' if cycle['decision']['check']=='endpoint_coverage' else cycle['decision']['arguments']['metric']
        costs = []; rows = []
        for phase, before, receipt_part, request_branch in (
                ('selection', revisions[0]['state'], cycle['decision'], 'selection'),
                ('reassessment', revisions[2]['state'], cycle['assessment'], branch)):
            receipt = read(directory, 'RECEIPT-'+phase+'.json')
            entries = [e for e in plan['requests'] if e['branch']==request_branch]
            if len(entries) != 1: raise ValueError('Ambiguous approved request')
            entry = entries[0]
            filename = '01-selection.json' if phase=='selection' else '02-reassessment-'+branch+'.json'
            if entry['file'] != filename: raise ValueError('Unexpected approved file name')
            prepared = muse_boundary.prepare(before, phase)
            body = read(directory, filename)
            if (study.digest(body) != entry['sha256'] or study.digest(body) != prepared['request_sha256'] or
                    body != prepared['body'] or len(study.canonical(body).encode()) != entry['bytes']):
                raise ValueError('Saved request differs from its approved study revision')
            if (receipt['phase'] != phase or receipt['request_sha256'] != entry['sha256'] or
                    receipt['destination'] != muse_boundary.DESTINATION or receipt['reported_model'] != muse_boundary.MODEL or
                    receipt['source'] != ('synthetic_fixture' if synthetic else 'direct_meta_transport') or receipt['validation'] != 'accepted' or
                    receipt['accepted_response_sha256'] != receipt_part['provider_receipt']['response_sha256']):
                raise ValueError('Saved provider receipt differs from its accepted revision')
            if (receipt_part['provider_receipt']['provenance'] == 'synthetic_fixture') != synthetic:
                raise ValueError('A synthetic fixture cannot be displayed as a live cycle')
            usage = receipt['usage']
            inputs = count(usage['input_tokens']); outputs = count(usage['output_tokens'])
            reasoning = usage['reasoning_tokens']
            if reasoning is not None and count(reasoning) > outputs: raise ValueError('Reasoning exceeds output count')
            if outputs > 1024 or inputs > entry['input_token_allowance']:
                raise ValueError('Usage exceeded approved allowance')
            cost = (Decimal(inputs)*Decimal('1.25')+Decimal(outputs)*Decimal('4.25'))/1_000_000
            if money(receipt['estimated_token_charge_usd']) != cost:
                raise ValueError('Saved token-cost estimate differs from usage')
            elapsed = receipt['elapsed_seconds']
            if type(elapsed) not in (int,float) or not 0 <= elapsed < 86400:
                raise ValueError('Invalid receipt duration')
            rows.append({'phase':phase, 'input_tokens':inputs, 'output_tokens':outputs,
                         'reasoning_tokens':reasoning, 'estimated_cost_usd':str(cost),
                         'elapsed_seconds':elapsed, 'request_sha256':entry['sha256'],
                         'accepted_response_sha256':receipt['accepted_response_sha256']})
            costs.append(cost)
        total = sum(costs, Decimal('0'))
        if total > Decimal('0.05') or money(status['observed_token_charge_estimate_usd']) != total:
            raise ValueError('Completion usage or ceiling mismatch')
        prior = plan.get('previous_attempt')
        prior_reservation = str(money(prior['reserved_upper_bound_usd'])) if prior else None
        self._package = package
        self.history = deepcopy(revisions)
        self.mutex = threading.RLock()
        self._summary = {'schema_version':'traitweaver.completed_cycle_summary.v1',
                         'status':'complete', 'synthetic':synthetic, 'model':muse_boundary.MODEL, 'mode':'Synthetic offline replay' if synthetic else 'Standard',
                         'completed_utc':status['updated_utc'], 'approval_sha256':plan['approval_sha256'],
                         'request_count':2, 'maximum_spend_usd':'0.05', 'requests':rows,
                         'total_input_tokens':sum(r['input_tokens'] for r in rows),
                         'total_output_tokens':sum(r['output_tokens'] for r in rows),
                         'total_reasoning_tokens':sum(r['reasoning_tokens'] for r in rows) if all(r['reasoning_tokens'] is not None for r in rows) else None,
                         'estimated_cost_usd':str(total), 'actual_provider_charge_usd':None,
                         'previous_attempt_unresolved_reservation_usd':prior_reservation,
                         'provenance':('Synthetic fixture only; no provider request or charge.' if synthetic else 'Recorded live transport; local request/receipt/revision consistency checked. No independent provider authentication.'),
                         'reopen_behavior':'Saved records only. No tool execution, model request, credential read or new revision.',
                         'scientific_limit':study.LIMIT}
        screen_export(self._summary)
        validate_review(self.export_review())

    def current(self): return deepcopy(self.history[-1])
    def export(self): return deepcopy(self._package)
    def summary(self): return deepcopy(self._summary)
    def export_review(self):
        return {'schema_version':'traitweaver.completed_cycle_review.v1','study_package':self.export(),'summary':self.summary()}
    def close(self): pass

    def readable(self):
        s=self._summary
        billing=('Synthetic usage only. No provider request or charge.\n' if s['synthetic'] else
                 'Actual provider charge: unverified. Previous attempt billing remains separate.\n')
        return (study.readable(self.current()['state'])+'\n## Recorded Muse usage\n\n'
                +f"Model: {s['model']}\nMode: {s['mode']}\nRequests: {s['request_count']}\n"
                +f"Input tokens: {s['total_input_tokens']}\nOutput tokens (including reasoning): {s['total_output_tokens']}\n"
                +f"Estimated token cost: ${s['estimated_cost_usd']}\n"+billing
                +'Reopened from saved records. No new execution.\n')
