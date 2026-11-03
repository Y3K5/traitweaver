"""Evidence projection acceptance: provenance, missingness and read-only replay."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from traitweaver import evidence_map, intelligence, intelligence_muse, intelligence_store, public_algae, study


class EvidenceMapTests(unittest.TestCase):
    def setUp(self):
        self.socket_guard = patch('socket.socket', side_effect=AssertionError('No network'))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.bundle = intelligence.catalog()

    def graph(self, bundle=None, endpoint='recovered_product_phosphorus'):
        return evidence_map.project(self.bundle if bundle is None else bundle, endpoint)

    def test_every_connection_resolves_and_has_typed_provenance(self):
        graph = self.graph()
        ids = [n['id'] for n in graph['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        for edge in graph['edges']:
            self.assertIn(edge['from'], ids)
            self.assertIn(edge['to'], ids)
            self.assertTrue(edge['relation'])
            self.assertTrue(edge['role'])
            self.assertTrue(edge['provenance']['locator'] if 'locator' in edge['provenance']
                            else edge['provenance']['claim']['locator'])

    def test_original_observations_and_statistics_are_exact(self):
        observations = {n['id']: n['record'] for n in self.graph()['nodes'] if n['kind'] == 'observation'}
        self.assertEqual(observations, {e['id']: e for e in self.bundle['literature']['evidence']})
        for e in observations.values():
            if e['value'] is not None:
                self.assertEqual(e['uncertainty']['kind'], 'SE')
                self.assertEqual(e['uncertainty']['n'], 3)
                self.assertTrue(e['measurement_basis'])

    def test_missing_recovery_and_cellular_evidence_is_not_uptake_or_zero_effect(self):
        graph = self.graph()
        nodes = {n['id']: n for n in graph['nodes']}
        for endpoint in ['recovered_product_phosphorus', 'cellular_phosphorus']:
            gap = nodes['gap:' + endpoint]['record']
            self.assertIsNone(gap['value'])
            self.assertEqual(gap['admitted_record_count'], 0)
            connections = [e for e in graph['edges'] if e['from'] == 'endpoint:' + endpoint]
            self.assertEqual([e['relation'] for e in connections], ['missing_admitted_evidence'])
        self.assertNotEqual(nodes['endpoint:medium_phosphate_removal']['id'], nodes['endpoint:phosphate_uptake']['id'])

    def test_numeric_zero_is_preserved_and_not_replaced_by_missing(self):
        # Exercise formatting input without admitting a new public source.
        bundle = deepcopy(self.bundle)
        bundle['literature']['evidence'][0]['value'] = 0
        graph = self.graph(bundle)
        observation = next(n for n in graph['nodes'] if n['id'] == 'E_GROWTH_UVM4')
        self.assertEqual(observation['record']['value'], 0)
        growth = next(n for n in graph['nodes'] if n['id'] == 'endpoint:growth')
        self.assertEqual(growth['record']['numeric_record_count'], 4)

    def test_reference_and_study_contexts_stay_separate_and_noncausal(self):
        graph = self.graph()
        nodes = {n['id']: n for n in graph['nodes']}
        gene = nodes['reference:GeneID:5726104']['record']
        self.assertIn('CC-503', gene['strain'])
        self.assertIn('UVM4', nodes['E_PHOSPHATE_UPTAKE_8_27']['record']['background'])
        self.assertIn('PROVISIONAL', gene['record_status'])
        candidate_edges = [e for e in graph['edges'] if e['from'] == 'P_PSR1_REFERENCE']
        self.assertFalse(any(e['to'] == 'S_OVERPLUS_2024' or e['to'].startswith('endpoint:') for e in candidate_edges))
        identity = next(e for e in candidate_edges if e['relation'] == 'gene_level_identity_association')
        self.assertIn('not proof', identity['provenance']['basis'])
        self.assertEqual(identity['to'], 'reference:GeneID:5726104')

    def test_missing_reference_has_no_inferred_identity_or_dangling_edge(self):
        with patch.object(public_algae, 'catalog', side_effect=ValueError('Unsafe source detail')):
            bundle = intelligence.catalog()
        graph = self.graph(bundle)
        self.assertFalse(any(n['kind'] in ('gene', 'protein', 'transcript', 'reference_source') for n in graph['nodes']))
        self.assertEqual(sum(n['kind'] == 'observation' for n in graph['nodes']), 10)
        self.assertNotIn('Unsafe source detail', study.canonical(graph))

    def test_missing_source_fails_closed(self):
        bundle = deepcopy(self.bundle)
        bundle['literature']['sources'] = []
        with self.assertRaisesRegex(ValueError, 'Observation source'):
            self.graph(bundle)
        bundle = deepcopy(self.bundle)
        bundle['reference']['sources']['sources'] = []
        with self.assertRaises((ValueError, KeyError)):
            self.graph(bundle)

    def test_projection_preserves_catalog_payload_and_journal_bytes(self):
        before = study.canonical(self.bundle)
        j = intelligence_store.Journal(self.bundle)
        j.apply(None, {'type': 'revise', 'payload': {
            'scope': intelligence.initial_scope(),
            'context': {'study_id': 'PUBLIC_ALGAE', 'study_revision_hash': 'a' * 64}}})
        package = j.export()
        request = intelligence_muse.prepare(j.current()['state'], 'selection', self.bundle)
        with patch.object(intelligence, 'run_check', side_effect=AssertionError('No dispatch')):
            restored = intelligence_store.Journal.from_package(package, self.bundle)
            current = {'hash': 'a' * 64, 'state': {'study_id': 'PUBLIC_ALGAE'}}
            graph = restored.view(current)['evidence_map']
            self.assertEqual(graph, j.view(current)['evidence_map'])
            self.assertEqual(restored.export(), package)
        self.assertNotIn('evidence_map', package)
        self.assertEqual(request, intelligence_muse.prepare(j.current()['state'], 'selection', self.bundle))
        self.assertEqual(before, study.canonical(self.bundle))
        graph['nodes'][0]['record']['title'] = 'Changed returned projection'
        self.assertEqual(before, study.canonical(self.bundle))


if __name__ == '__main__':
    unittest.main()
