"""Clearly synthetic completed-packet fixtures, local only; no provider traffic."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import muse_boundary as muse, study
from traitweaver.completed_cycle import CompletedCycle
from traitweaver.study_store import Store


def write(path,value): path.write_text(study.canonical(value))


def fixture(root, synthetic=False):
    """Synthetic transport claims solely to exercise receipt consistency checks."""
    root.mkdir()
    store=Store(root/'synthetic-study')
    previews=[];receipts=[]
    try:
        for phase in ('selection','reassessment'):
            state=store.current()['state'];preview=muse.prepare(state,phase);previews.append(preview)
            reply=muse.synthetic_reply(state,phase)
            if not synthetic:reply.pop('traitweaver_synthetic')
            raw=study.canonical(reply).encode()
            accepted=muse.parse_reply(state,phase,raw,preview['request_sha256'])
            store.apply(store.current()['hash'],{'type':'muse_accept','payload':accepted})
            if phase=='selection':store.apply(store.current()['hash'],{'type':'run','payload':{}})
            receipt={'phase':phase,'destination':muse.DESTINATION,'reported_model':muse.MODEL,
                     'request_sha256':preview['request_sha256'],
                     'accepted_response_sha256':accepted['receipt']['response_sha256'],
                     'source':'synthetic_fixture' if synthetic else 'direct_meta_transport','validation':'accepted',
                     'usage':{'input_tokens':100,'output_tokens':40,'reasoning_tokens':0},
                     'estimated_token_charge_usd':'0.000295','elapsed_seconds':0.1}
            receipts.append(receipt);write(root/('RECEIPT-'+phase+'.json'),receipt)
        write(root/'STUDY_PACKAGE.json',store.export())
    finally:store.close()
    entries=[]
    for phase,preview,branch in zip(('selection','reassessment'),previews,('selection','coverage')):
        name='01-selection.json' if phase=='selection' else '02-reassessment-coverage.json'
        raw=study.canonical(preview['body']).encode();(root/name).write_bytes(raw)
        entries.append({'branch':branch,'file':name,'sha256':preview['request_sha256'],'bytes':len(raw),'input_token_allowance':len(raw)+1024})
    plan={'destination':muse.DESTINATION,'model':muse.MODEL,'max_requests':2,'maximum_authorized_spend_usd':'0.05','requests':entries,
          'previous_attempt':{'reserved_upper_bound_usd':'0.02153825'}}
    if synthetic:
        plan['fixture_kind']='synthetic_demo';plan['previous_attempt']=None
    plan['approval_sha256']=study.digest(plan);write(root/'PUBLIC_CYCLE.json',plan)
    write(root/('SYNTHETIC_APPROVAL.json' if synthetic else 'OWNER_APPROVAL.json'),{'approved':not synthetic,'approval_sha256':plan['approval_sha256'],'destination':muse.DESTINATION,'model':muse.MODEL,'maximum_spend_usd':'0.05','max_requests':2})
    write(root/'STATUS.json',{'status':'complete','requests_started':2,'requests_completed':2,'transport':'synthetic_fixture' if synthetic else 'direct_meta_api','approval_sha256':plan['approval_sha256'],
                            'reserved_upper_bound_usd':'0','observed_token_charge_estimate_usd':'0.000590','updated_utc':'2026-10-29T00:00:00+00:00'})
    return root


class CompletedCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-synthetic-cycle-review-');self.addCleanup(self.temp.cleanup)
        self.root=fixture(Path(self.temp.name)/'packet')

    def change(self,name,mutate):
        value=json.loads((self.root/name).read_text());mutate(value);write(self.root/name,value)

    def test_readonly_reopen_reads_saved_results_without_tools_credentials_network_or_writes(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        class Forbidden:
            def get(self,*args):raise AssertionError('Credential access forbidden')
        with patch('socket.socket',side_effect=AssertionError('External network forbidden')),patch.object(muse.os,'environ',Forbidden()),patch.object(study,'coverage',side_effect=AssertionError('No check dispatch')),patch.object(study,'contrasts',side_effect=AssertionError('No check dispatch')),patch.object(muse,'send_approved',side_effect=AssertionError('No provider call')):
            record=CompletedCycle(self.root)
            self.assertEqual(record.current()['revision'],4)
            self.assertEqual(record.summary()['estimated_cost_usd'],'0.000590')
            self.assertEqual(record.summary()['total_reasoning_tokens'],0)
            self.assertIsNone(record.summary()['actual_provider_charge_usd'])
            self.assertEqual(record.current()['state']['cycles'][0]['assessment']['outcome'],'unavailable')
            record.export();record.close()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()})

    def test_unrelated_files_and_local_control_never_read(self):
        (self.root/'LOCAL_CONTROL.json').mkdir();(self.root/'raw-response.json').mkdir()
        self.assertEqual(CompletedCycle(self.root).summary()['request_count'],2)

    def test_rejects_inconsistent_usage_receipt(self):
        self.change('RECEIPT-selection.json',lambda v:v['usage'].update(input_tokens=101))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_missing_usage_is_not_silently_zero(self):
        self.change('RECEIPT-selection.json',lambda v:v['usage'].pop('input_tokens'))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_corrupt_or_altered_study_rejected(self):
        self.change('STUDY_PACKAGE.json',lambda v:v['revisions'][-1]['state']['cycles'][0]['assessment'].update(outcome='supporting'))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_receipt_does_not_match_accepted_model_reply(self):
        self.change('RECEIPT-selection.json',lambda v:v.update(accepted_response_sha256='0'*64))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_changed_request_or_manifest_rejected(self):
        self.change('01-selection.json',lambda v:v.update(model='other'))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_incomplete_cycle_not_shown_as_complete(self):
        self.change('STATUS.json',lambda v:v.update(requests_completed=1))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_model_source_or_cost_mismatch_rejected(self):
        self.change('RECEIPT-selection.json',lambda v:v.update(source='fake_transport_for_tests'))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_response_and_export_copies_cannot_mutate_record(self):
        record=CompletedCycle(self.root);value=record.summary();value['request_count']=500
        package=record.export();package['revisions'].clear()
        self.assertEqual(record.summary()['request_count'],2);self.assertEqual(len(record.export()['revisions']),4)
        self.assertIn('Estimated token cost: $0.000590',record.readable())

    def test_secret_shaped_unexpected_summary_content_is_blocked(self):
        self.change('STATUS.json',lambda v:v.update(updated_utc='/Users/private-person/file'))
        with self.assertRaises(ValueError):CompletedCycle(self.root)

    def test_qualified_synthetic_fixture_is_visibly_distinct_and_has_no_live_grant(self):
        root=fixture(Path(self.temp.name)/'synthetic-demo',synthetic=True)
        record=CompletedCycle(root)
        self.assertTrue(record.summary()['synthetic'])
        self.assertEqual(record.summary()['mode'],'Synthetic offline replay')
        self.assertIn('Synthetic usage only',record.readable())
        self.assertFalse((root/'OWNER_APPROVAL.json').exists())
        self.assertFalse(json.loads((root/'SYNTHETIC_APPROVAL.json').read_text())['approved'])

    def test_synthetic_fixture_cannot_be_relabelled_as_a_live_cycle(self):
        root=fixture(Path(self.temp.name)/'synthetic-demo',synthetic=True)
        plan=json.loads((root/'PUBLIC_CYCLE.json').read_text());plan.pop('fixture_kind');plan.pop('approval_sha256')
        plan['approval_sha256']=study.digest(plan);write(root/'PUBLIC_CYCLE.json',plan)
        with self.assertRaises(ValueError):CompletedCycle(root)

    def test_cycle_with_usage_roundtrip_is_readonly_without_execution_or_credential_access(self):
        original=CompletedCycle(self.root);exported=original.export_review()
        class Forbidden:
            def get(self,*args):raise AssertionError('No credential access')
        with patch('socket.socket',side_effect=AssertionError('No sockets')),patch.object(muse.os,'environ',Forbidden()),patch.object(study,'coverage',side_effect=AssertionError('No tool execution')),patch.object(study,'contrasts',side_effect=AssertionError('No tool execution')),patch.object(muse,'send_approved',side_effect=AssertionError('No provider call')):
            reopened=CompletedCycle.from_review(exported)
            self.assertEqual(reopened.export_review(),exported)
            self.assertEqual(reopened.current(),original.current())
            self.assertEqual(reopened.summary()['total_reasoning_tokens'],0)
            self.assertEqual(len(reopened.history),4)

    def test_synthetic_review_file_roundtrip_preserves_mode_and_usage(self):
        root=fixture(Path(self.temp.name)/'synthetic-demo',synthetic=True)
        original=CompletedCycle(root);path=Path(self.temp.name)/'review.json';write(path,original.export_review())
        before=path.read_bytes();reopened=CompletedCycle.from_file(path)
        self.assertTrue(reopened.summary()['synthetic'])
        self.assertEqual(reopened.export_review(),original.export_review())
        self.assertEqual(before,path.read_bytes())

    def test_unknown_reasoning_remains_null_on_roundtrip(self):
        exported=CompletedCycle(self.root).export_review()
        exported['summary']['requests'][0]['reasoning_tokens']=None
        exported['summary']['total_reasoning_tokens']=None
        self.assertIsNone(CompletedCycle.from_review(exported).summary()['total_reasoning_tokens'])

    def test_review_rejects_changed_totals_claims_receipt_links_and_source(self):
        exported=CompletedCycle(self.root).export_review()
        changes=[lambda v:v['summary'].update(total_input_tokens=201),
                 lambda v:v['summary'].update(estimated_cost_usd='0.04'),
                 lambda v:v['summary'].update(actual_provider_charge_usd='0.000590'),
                 lambda v:v['summary'].update(model='other'),
                 lambda v:v['summary'].update(synthetic=True),
                 lambda v:v['summary']['requests'][0].update(request_sha256='0'*64),
                 lambda v:v['summary']['requests'][0].update(accepted_response_sha256='0'*64),
                 lambda v:v['summary']['requests'][0].update(output_tokens=2048),
                 lambda v:v['summary']['requests'][0].update(input_tokens=True),
                 lambda v:v['summary']['requests'][0].update(unknown='synthetic extra'),
                 lambda v:v['summary'].update(provenance='Independently authenticated'),
                 lambda v:v['study_package'].update(source_bundle={})]
        for change in changes:
            altered=deepcopy(exported);change(altered)
            with self.assertRaises(ValueError):CompletedCycle.from_review(altered)
        self.assertEqual(CompletedCycle.from_review(exported).export_review(),exported)

    def test_review_timestamp_failure_does_not_echo_untrusted_value(self):
        exported=CompletedCycle(self.root).export_review();exported['summary']['completed_utc']='synthetic-sensitive-marker'
        with self.assertRaises(ValueError) as failure:CompletedCycle.from_review(exported)
        self.assertNotIn('synthetic-sensitive-marker',str(failure.exception))

    def test_review_file_rejects_symlink_corruption_and_oversize(self):
        valid=Path(self.temp.name)/'review.json';write(valid,CompletedCycle(self.root).export_review())
        link=Path(self.temp.name)/'link.json';link.symlink_to(valid)
        with self.assertRaises(ValueError):CompletedCycle.from_file(link)
        valid.write_text('{invalid')
        with self.assertRaises(ValueError):CompletedCycle.from_file(valid)
        valid.write_bytes(b' '*(4*1024*1024+1))
        with self.assertRaises(ValueError):CompletedCycle.from_file(valid)


if __name__=='__main__':unittest.main()
