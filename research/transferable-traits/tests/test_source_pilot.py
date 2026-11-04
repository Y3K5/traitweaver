"""Synthetic software checks of the real-source preparation contract."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from traitstudy.core import canonical,digest
from traitstudy.source_pilot import IDS,prepare_cases,parse_critique,write_packet


class SourcePilotTest(unittest.TestCase):
    def setUp(self):
        self.rows=[{'ID':i,'test_data':'Synthetic test candidate; not biology'} for i in IDS]
        self.sources=[{'workbook_id':i,'human_scientific_review':'pending','retrieval_status':'abstract_available',
                       'short_quote':'Synthetic test text','source_url':'https://example.invalid/test',
                       'locator':'Synthetic fixture paragraph','coverage_gaps':['Synthetic only']} for i in IDS]
        self.packet=prepare_cases(self.rows,self.sources)[0]
        self.reply={'context_sha256':self.packet['context_sha256'],'workbook_id':IDS[0],
                    'assessment':'needs_more_evidence','findings':[{'issue':'Synthetic test gap',
                    'source_locator':'not_available_in_supplied_material','certainty':'unresolved'}],
                    'next_step':'human_source_review'}

    def test_exact_six_cases_and_hash_bound_schema(self):
        packets=prepare_cases(self.rows,self.sources)
        self.assertEqual(len(packets),6)
        for p in packets:
            self.assertEqual(digest(canonical(p['body']).encode()),p['wire_sha256'])
            schema=p['body']['text']['format']['schema']
            self.assertEqual(schema['properties']['context_sha256']['enum'],[p['context_sha256']])

    def test_missing_case_and_duplicate_case_fail(self):
        for rows in (self.rows[:5],self.rows[:5]+[self.rows[0]]):
            with self.assertRaises(ValueError):prepare_cases(rows,self.sources)

    def test_source_review_not_auto_granted(self):
        self.sources[0]['human_scientific_review']='approved'
        with self.assertRaises(ValueError):prepare_cases(self.rows,self.sources)

    def test_model_cannot_grant_approval_or_execute(self):
        self.reply['assessment']='scientifically_approved'
        with self.assertRaises(ValueError):parse_critique(canonical(self.reply),self.packet)
        self.reply['assessment']='needs_more_evidence';self.reply['next_step']='run_lab'
        with self.assertRaises(ValueError):parse_critique(canonical(self.reply),self.packet)

    def test_stale_hash_and_invented_locator_fail(self):
        self.reply['context_sha256']='stale'
        with self.assertRaises(ValueError):parse_critique(canonical(self.reply),self.packet)
        self.reply['context_sha256']=self.packet['context_sha256']
        self.reply['findings'][0]['source_locator']='Invented figure 99'
        with self.assertRaises(ValueError):parse_critique(canonical(self.reply),self.packet)

    def test_valid_unresolved_finding_preserved(self):
        self.assertEqual(parse_critique(canonical(self.reply),self.packet),self.reply)

    def test_long_quote_and_payload_rejected(self):
        source=deepcopy(self.sources);source[0]['short_quote']='word '*26
        with self.assertRaises(ValueError):prepare_cases(self.rows,source)
        rows=deepcopy(self.rows);rows[0]['test_data']='x'*16000
        with self.assertRaises(ValueError):prepare_cases(rows,self.sources)

    def test_offline_packet_keeps_budget_distinct_from_permission(self):
        with tempfile.TemporaryDirectory() as tmp, patch('socket.socket',side_effect=AssertionError('no network')), patch('os.getenv',side_effect=AssertionError('no credentials')):
            out=Path(tmp)/'packet';plan=write_packet(self.rows,self.sources,out)
            self.assertEqual(plan['study_budget_usd'],100)
            self.assertEqual(plan['pilot_allocation_usd'],1)
            self.assertFalse(plan['exact_live_payload_approved'])
            self.assertEqual(plan['funding_policy'],'existing_credits_only')
            self.assertFalse(plan['payment_method_charges_authorized'])
            self.assertFalse(plan['credit_only_enforcement_verified'])
            self.assertIsNone(plan['verified_available_credits_usd'])
            self.assertEqual(plan['provider_calls'],0)
            for name,sha in plan['request_hashes'].items():self.assertEqual(digest((out/(name+'.wire.json')).read_bytes()),sha)
            with self.assertRaises(ValueError):write_packet(self.rows,self.sources,out)
