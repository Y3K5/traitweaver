"""Unsent public batches: provider identity, accounting unknowns and fail-closed cap."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trait_research_planner',ROOT/'tools/prepare_trait_research.py')
planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)


class BatchTests(unittest.TestCase):
    def test_three_bounded_batches_have_no_execution_and_no_invented_cost(self):
        with tempfile.TemporaryDirectory() as tmp, patch('socket.socket',side_effect=AssertionError('No network')), patch('os.getenv',side_effect=AssertionError('No secrets')):
            folder=Path(tmp)/'plan';plan=planner.prepare(folder)
            self.assertEqual(plan['new_provider_calls'],0)
            self.assertEqual(plan['execution_limit_usd'],'0.00')
            self.assertFalse(plan['approved']);self.assertEqual(len(plan['batches']),3)
            for batch in plan['batches']:
                self.assertEqual(len(batch['request_ids']),2)
                self.assertIsNone(batch['actual_invoiced_cost_usd'])
            for row in plan['requests']:
                self.assertEqual(row['provider'],'meta_direct')
                for key in ('input_tokens','output_tokens','actual_invoiced_cost_usd','provider_receipt'):
                    self.assertIsNone(row[key])
                packet=json.loads((folder/(row['id']+'.json')).read_text())
                raw=(folder/(row['id']+'-body.json')).read_bytes()
                self.assertEqual(len(raw),row['request_bytes'])
                self.assertEqual(packet['request_sha256'],planner.study.digest(json.loads(raw)))
            with self.assertRaises(ValueError):planner.prepare(folder)

    def test_generated_packets_cannot_be_written_into_source_tree(self):
        with self.assertRaises(ValueError):planner.prepare(ROOT/'outputs/test')
