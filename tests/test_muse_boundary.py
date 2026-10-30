"""Synthetic provider and fake transport checks. No actual credentials or API."""
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import muse_boundary as muse, study
from traitweaver.study_store import Store,validate_package


class FakeResponse(io.BytesIO):
    status=200


class FakeOpener:
    def __init__(self,raw):self.raw=raw;self.calls=0
    def open(self,request,timeout):self.calls+=1;return FakeResponse(self.raw)


class MuseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='traitweaver-muse-test-');self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'study');self.addCleanup(self.store.close)

    def state(self):return self.store.current()['state']
    def accept(self,phase,reply=None):
        s=self.state();raw=study.canonical(reply or muse.synthetic_reply(s,phase)).encode();p=muse.prepare(s,phase)
        payload=muse.parse_reply(s,phase,raw,p['request_sha256'])
        return self.store.apply(self.store.current()['hash'],{'type':'muse_accept','payload':payload})

    def test_prepare_is_bounded_public_only_and_not_sent(self):
        p=muse.prepare(self.state(),'selection')
        self.assertEqual(p['status'],'not_sent');self.assertEqual(p['body']['max_output_tokens'],1024)
        self.assertFalse(p['body']['store']);self.assertEqual(p['request_sha256'],study.digest(p['body']))
        self.assertLess(len(study.canonical(p['body']).encode()),24000)
        self.assertNotIn('GFP',p['body']['input']);self.assertNotIn('MODEL_API_KEY',study.canonical(p))

    def test_synthetic_cycle_is_labeled_and_never_misrepresented_as_live(self):
        self.accept('selection')
        self.store.apply(self.store.current()['hash'],{'type':'run','payload':{}})
        r=self.accept('reassessment')
        c=r['state']['cycles'][-1]
        self.assertEqual(c['decision']['provider_receipt']['provenance'],'synthetic_fixture')
        self.assertEqual(c['assessment']['provider_receipt']['provenance'],'synthetic_fixture')
        self.assertEqual(validate_package(self.store.export())['state'],r['state'])
        self.assertNotIn('output_text',study.canonical(self.store.export()))

    def test_imported_reply_authenticity_remains_unverified(self):
        reply=muse.synthetic_reply(self.state(),'selection');reply.pop('traitweaver_synthetic')
        r=self.accept('selection',reply)
        self.assertEqual(r['state']['cycles'][-1]['decision']['provider_receipt']['provenance'],'owner_imported_reply_authenticity_unverified')

    def test_unknown_citation_altered_arguments_and_unbounded_claim_are_refused(self):
        base=muse.synthetic_reply(self.state(),'selection')
        for changes in [{'citations':['UNKNOWN']},{'citations':[{}]},{'check':'shell'},{'metric':'growth'},{'rationale_code':'biological_success'},{'extra':'unsupported claim'}]:
            reply=deepcopy(base);p=study.decode(reply['output'][0]['content'][0]['text']);p.update(changes)
            reply['output'][0]['content'][0]['text']=study.canonical(p)
            with self.assertRaises(ValueError):self.accept('selection',reply)
        self.assertEqual(len(self.store.history),1)

    def test_refusal_wrong_model_incomplete_malformed_duplicate_and_oversize_reply(self):
        state=self.state();p=muse.prepare(state,'selection');base=muse.synthetic_reply(state,'selection')
        variants=[]
        for change in [{'model':'other'},{'status':'incomplete'},{'output':False},{'output':[None]},{'output':[{'type':'message','content':False}]},{'output':[{'type':'message','content':[None]}]},{'output':[{'type':'message','content':[{'type':'refusal'}]}]},{'output':[{'type':'function_call'}]}]:
            r=deepcopy(base);r.update(change);variants.append(study.canonical(r).encode())
        variants += [b'{bad',b'{"x":1,"x":2}',b' '*(muse.MAX_RESPONSE+1)]
        for raw in variants:
            with self.assertRaises(ValueError):muse.parse_reply(state,'selection',raw,p['request_sha256'])

    def test_result_identity_and_outcome_cannot_be_promoted(self):
        self.accept('selection');self.store.apply(self.store.current()['hash'],{'type':'run','payload':{}})
        for key,value in [('outcome','supporting'),('result_id','invented'),('next_action','execute_lab')]:
            r=muse.synthetic_reply(self.state(),'reassessment');proposal=study.decode(r['output'][0]['content'][0]['text']);proposal[key]=value;r['output'][0]['content'][0]['text']=study.canonical(proposal)
            with self.assertRaises(ValueError):self.accept('reassessment',r)

    def test_stale_request_and_second_selection_rejected(self):
        s=self.state();p=muse.prepare(s,'selection');reply=study.canonical(muse.synthetic_reply(s,'selection')).encode()
        b=deepcopy(s['brief']);b['question']='Changed public question'
        self.store.apply(self.store.current()['hash'],{'type':'edit','payload':b})
        with self.assertRaises(ValueError):muse.parse_reply(self.state(),'selection',reply,p['request_sha256'])
        self.accept('selection')
        with self.assertRaises(ValueError):muse.prepare(self.state(),'selection')

    def test_live_default_and_bad_grant_never_read_a_credential(self):
        class ForbiddenEnvironment:
            def get(self,*args):raise AssertionError('Credential must not be accessed')
        p=muse.prepare(self.state(),'selection')
        with patch.object(muse.os,'environ',ForbiddenEnvironment()):
            with self.assertRaisesRegex(ValueError,'disabled'):muse.send_approved(p,{},self.temp.name)
            with self.assertRaises(ValueError):muse.send_approved(p,{'allow_live':True},self.temp.name,allow_live=True)

    def grant(self,p):return {'destination':muse.DESTINATION,'request_sha256':p['request_sha256'],'spending_limit_usd':.10,'allow_live':True,'verified_price_usd_per_million':{'input':1.25,'output':4.25}}

    def test_spending_bound_is_checked_before_credentials(self):
        p=muse.prepare(self.state(),'selection');g=self.grant(p);g['spending_limit_usd']=.000001
        with patch.object(muse.os,'environ',{}) as env:
            with self.assertRaisesRegex(ValueError,'cost bound'):muse.send_approved(p,g,self.temp.name,allow_live=True)
        self.assertEqual(list(Path(self.temp.name).glob('*.attempt.json')),[])

    def test_fake_transport_records_usage_and_prevents_duplicate_attempt(self):
        p=muse.prepare(self.state(),'selection');reply=muse.synthetic_reply(self.state(),'selection');reply['usage']={'input_tokens':12,'output_tokens':10}
        opener=FakeOpener(study.canonical(reply).encode())
        with patch.object(muse.os,'environ',{'MODEL_API_KEY':'synthetic-transport-token'}):
            result,receipt=muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=opener)
            with self.assertRaisesRegex(ValueError,'already attempted'):muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=opener)
        self.assertEqual(opener.calls,1);self.assertEqual(receipt['reported_usage'],reply['usage']);self.assertIsNone(receipt['actual_cost_usd'])

    def test_fake_timeout_retains_reservation_without_raw_error_or_retry(self):
        class Timeout:
            def open(self,*args,**kwargs):raise TimeoutError('synthetic private transport detail')
        p=muse.prepare(self.state(),'selection')
        with patch.object(muse.os,'environ',{'MODEL_API_KEY':'synthetic-transport-token'}):
            with self.assertRaisesRegex(ValueError,'billing may be unknown') as c:muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=Timeout())
            self.assertNotIn('private transport detail',str(c.exception))
            with self.assertRaisesRegex(ValueError,'already attempted'):muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=Timeout())

    def test_secret_echo_fails_closed(self):
        p=muse.prepare(self.state(),'selection')
        with patch.object(muse.os,'environ',{'MODEL_API_KEY':'synthetic-transport-token'}):
            with self.assertRaises(ValueError):muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=FakeOpener(b'{"echo":"synthetic-transport-token"}'))

    def test_json_escaped_credential_echo_rejected_before_any_response_receipt(self):
        p=muse.prepare(self.state(),'selection');key='synthetic-transport-token'
        escaped=''.join('\\u%04x'%ord(c) for c in key).encode()
        for field in ('id','usage_value','usage_key','output'):
            with self.subTest(field=field):
                directory=Path(self.temp.name)/field;directory.mkdir()
                reply=muse.synthetic_reply(self.state(),'selection')
                reply['usage']={'input_tokens':12,'output_tokens':10}
                if field=='id':reply['id']=key
                elif field=='usage_value':reply['usage']['foreign_metadata']=key
                elif field=='usage_key':reply['usage'][key]='synthetic marker'
                else:reply['output'][0]['content'][0]['text']=key
                raw=study.canonical(reply).encode().replace(key.encode(),escaped)
                self.assertNotIn(key.encode(),raw)
                with patch.object(muse.os,'environ',{'MODEL_API_KEY':key}):
                    with self.assertRaises(ValueError):muse.send_approved(p,self.grant(p),directory,allow_live=True,opener=FakeOpener(raw))
                self.assertEqual(len(list(directory.glob('*.receipt.json'))),0)
                for file in directory.iterdir():
                    self.assertNotIn(key,file.read_text())

    def test_usage_persistence_is_numeric_allowlist_only(self):
        p=muse.prepare(self.state(),'selection');reply=muse.synthetic_reply(self.state(),'selection')
        reply['usage']={'input_tokens':12,'output_tokens':10,'total_tokens':22,
                        'private_note':'synthetic-nonbilling-marker',
                        'input_tokens_details':{'cached_tokens':0,'unknown':'synthetic-nonbilling-marker'},
                        'output_tokens_details':{'reasoning_tokens':0,'unknown':'synthetic-nonbilling-marker'}}
        with patch.object(muse.os,'environ',{'MODEL_API_KEY':'synthetic-transport-token'}):
            _,receipt=muse.send_approved(p,self.grant(p),self.temp.name,allow_live=True,opener=FakeOpener(study.canonical(reply).encode()))
        self.assertEqual(receipt['reported_usage'],{'input_tokens':12,'output_tokens':10,'total_tokens':22,
            'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}})
        for file in Path(self.temp.name).glob('*.receipt.json'):
            self.assertNotIn('synthetic-nonbilling-marker',file.read_text())

    def test_usage_null_zero_and_invalid_counts_are_not_coerced(self):
        self.assertIsNone(muse.receipt_usage(None))
        self.assertEqual(muse.receipt_usage({'input_tokens':0,'output_tokens':0}),{'input_tokens':0,'output_tokens':0})
        self.assertEqual(muse.receipt_usage({'input_tokens':True,'output_tokens':-1,'total_tokens':2.5}),{})


if __name__=='__main__':unittest.main(verbosity=2)
