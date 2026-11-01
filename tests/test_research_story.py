"""Scientific quantities/provenance and actual local route tests; no sockets."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

from traitweaver import research_story as r, study, workspace_server
from traitweaver.study_store import Store
from test_review_handlers import MemoryServer
import test_molecular_handlers as handlers

def offline(event,args):
    if event.startswith('socket.'):raise RuntimeError('Research-story tests prohibit sockets')
sys.addaudithook(offline)


class ResearchStoryTests(unittest.TestCase):
    def test_published_means_se_n_units_and_source_controls_are_retained(self):
        d=r.content();u=d['summaries']['phosphate_uptake'];g=d['summaries']['growth']
        self.assertEqual(len(u['rows']),4);line=next(x for x in u['rows'] if x['record']['subject']=='8-27')
        self.assertEqual(line['record']['value'],.97);self.assertEqual(line['record']['uncertainty'],{'kind':'SE','value':.04,'n':3,'independent_unit':'culture replicate'})
        self.assertAlmostEqual(line['ratio_to_control'],.97/.48)
        self.assertEqual(u['unit'],'mmol P g dry_weight^-1 d^-1')
        self.assertAlmostEqual(next(x for x in g['rows'] if x['record']['subject']=='8-27')['ratio_to_control'],1.33/1.44)
        self.assertEqual(u['source_id'],'S_PSR1_2023')

    def test_reference_mapping_is_one_locus_not_a_whole_edited_genome(self):
        d=r.content();nodes=d['reference_chain']
        self.assertEqual([x.get('length') for x in nodes],[5402,None,4772,752])
        self.assertEqual(nodes[2]['exon_count'],3);self.assertEqual(nodes[2]['parent'],'REF_GENE')
        self.assertIn('Region hash only',nodes[0]['limit'])
        self.assertIn('CC-503',d['reference_limit']);self.assertIn('UVM4',d['reference_limit'])
        self.assertIsNone(d['actual_edited_material_id']);self.assertIsNone(d['actual_lab_run_id'])

    def test_planned_materials_have_no_fabricated_sample_construct_or_genotype(self):
        d=r.content()
        for row in d['planned_materials']:
            self.assertTrue(row['id'].startswith('PLAN_'))
            for key,value in row.items():
                if key not in ('id','form','parent_reference','parent_plan_id'):self.assertIsNone(value)
        self.assertIsNone(d['gfp_reference']['relevance_link_to_algae'])
        self.assertIsNone(d['gfp_reference']['reporter_construct_record'])

    def test_each_plan_has_comparison_controls_readouts_independent_units_and_gate(self):
        d=r.content();ids={s['id'] for s in d['sources']}|{e['id'] for e in d['public_observations']}|{s['id'] for s in d['scope_records']}
        for c in d['study_design']:
            for key in ('question','comparison','controls','readouts','independent_units','required_before_run','completion_check'):self.assertTrue(c[key])
            self.assertTrue(set(c['sources'])<=ids)
        self.assertIsNone(d['decision_thresholds'])

    def test_synthetic_fluorescence_arithmetic_is_not_genotype_or_performance(self):
        inputs=r.fixture()['synthetic_math']['fluorescence'];value=r.fluorescence(inputs)
        self.assertEqual(value['net_signal'],1000);self.assertEqual(value['normalized_signal'],2500)
        self.assertEqual(value['status'],'illustration_only');self.assertIsNone(value['inputs']['genotype_confirmation'])
        self.assertIn('not edit confirmation',value['interpretation'])

    def test_fluorescence_missing_zero_incompatible_and_negative_net_are_distinct(self):
        f=r.fixture()['synthetic_math']['fluorescence']
        missing=r.fluorescence(dict(f,signal=None));self.assertEqual(missing['status'],'unavailable')
        zero=r.fluorescence(dict(f,signal=0,background=0));self.assertEqual(zero['net_signal'],0);self.assertEqual(zero['normalized_signal'],0)
        denom=r.fluorescence(dict(f,normalization_mass=0));self.assertIsNone(denom['normalized_signal']);self.assertEqual(denom['status'],'inconclusive')
        self.assertEqual(r.fluorescence(dict(f,background_unit='arbitrary_other_unit'))['status'],'invalid')
        self.assertEqual(r.fluorescence(dict(f,signal=True))['status'],'invalid')
        self.assertEqual(r.fluorescence(dict(f,signal=100,background=200))['net_signal'],-100)

    def test_synthetic_p_accounting_distinguishes_concentration_mass_product_and_closure(self):
        value=r.phosphorus(r.fixture()['synthetic_math']['phosphorus'])
        self.assertEqual(value['concentration_change_percent'],60)
        self.assertEqual(value['liquid_inventory_decrease_percent'],64)
        self.assertEqual(value['collected_product_fraction_percent'],10)
        self.assertEqual(value['mass_closure_percent'],96)
        self.assertAlmostEqual(value['unaccounted_mass_mg_P'],.8)
        for key in ('microbe_effect','plant_use','chemical_transformation'):self.assertIsNone(value[key])
        self.assertEqual(value['status'],'illustration_only')

    def test_p_accounting_cannot_merge_units_overlapping_compartments_or_missing_mass(self):
        f=r.fixture()['synthetic_math']['phosphorus']
        for mutation in ({'basis':'orthophosphate_mass'},{'mass_unit':'mg PO4'},{'compartments_disjoint':False},{'initial_volume':-1},{'other_input_P':False}):
            self.assertEqual(r.phosphorus(dict(f,**mutation))['status'],'invalid')
        self.assertEqual(r.phosphorus(dict(f,collected_product_P=None))['status'],'unavailable')
        self.assertEqual(r.phosphorus(dict(f,collected_product_P=0))['collected_product_fraction_percent'],0)
        noinput=r.phosphorus(dict(f,initial_concentration=0,other_input_P=0))
        self.assertIsNone(noinput['concentration_change_percent']);self.assertIsNone(noinput['mass_closure_percent'])

    def test_content_export_and_reopen_do_not_dispatch_registered_tools(self):
        with (patch.object(study,'contrasts',side_effect=AssertionError('No registered tool')),
              patch.object(study,'coverage',side_effect=AssertionError('No registered tool'))):
            session=r.Session();value=session.export();session.open(value)
        self.assertEqual(session.export(),value)

    def test_tampered_sources_numbers_roles_and_proposed_materials_fail_even_after_rehash(self):
        value=r.Session().export()
        mutations=[lambda v:v['content']['synthetic_calculations']['phosphorus'].update(role='experimental_observation'),
                   lambda v:v['content'].update(actual_lab_run_id='invented-run'),
                   lambda v:v['content']['planned_materials'][0].update(sequence_sha256='0'*64),
                   lambda v:v['content']['summaries']['growth']['rows'][0]['record'].update(value=0),
                   lambda v:v['content']['study_design'][0].update(sources=['INVENTED']),
                   lambda v:v['content']['gfp_reference'].update(relevance_link_to_algae='invented')]
        for mutate in mutations:
            changed=deepcopy(value);mutate(changed);changed['sha256']=study.digest({k:v for k,v in changed.items() if k!='sha256'})
            with self.assertRaises(ValueError):r.validate_package(changed)

    def test_package_text_preserves_synthetic_labels_published_stats_and_all_plan_fields(self):
        s=r.Session();s.present(dict(s.settings,stage='phosphorus',examples=True,scientist=True));p=s.export();text=s.readable()
        self.assertIn('SYNTHETIC mathematical illustration, NOT experimental observations',text)
        self.assertIn(study.canonical(p),text)
        for card in p['content']['study_design']:
            self.assertIn(card['completion_check'],text);self.assertIn(card['independent_units'],text)
        t=r.Session();t.open(p);self.assertTrue(t.reopened);self.assertEqual(t.export(),p)

    def test_fixture_is_pinned_and_has_no_retrieval_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.json';path.write_text('{}')
            with patch.object(r,'FIXTURE',path),self.assertRaises(ValueError):r.fixture()


class ResearchStoryHandlerTests(unittest.TestCase):
    request=handlers.MolecularHandlerTests.request

    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        guard=patch('socket.socket',side_effect=AssertionError('No sockets'));guard.start();self.addCleanup(guard.stop)
        self.store=Store(self.folder/'study');self.addCleanup(self.store.close)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer);self.token=self.request('/api/session')[1]['token']

    def body(self,**fields):return {'expected_hash':self.store.current()['hash'],'story_hash':self.server.workspace.research_story.current()['hash'],**fields}

    def test_presentation_export_reopen_preserve_data_and_original_study(self):
        before=self.store.export();owner=self.server.workspace.research_story
        view=dict(owner.settings,stage='plan',examples=True,scientist=True)
        self.assertEqual(self.request('/api/research-story/present',self.body(view=view))[0],200)
        p=self.request('/api/research-story/export.json')[1];text=self.request('/api/research-story/export.txt')[1]
        self.assertIn('SYNTHETIC',text)
        self.assertEqual(self.request('/api/research-story/open',self.body(package_json=study.canonical(p)))[0],200)
        self.assertEqual(owner.export(),p);self.assertEqual(self.store.export(),before)

    def test_origin_stale_hashes_invalid_view_and_unknown_tool_are_refused(self):
        owner=self.server.workspace.research_story;body=self.body(view=owner.settings)
        self.assertEqual(self.request('/api/research-story/present',body,{'Origin':'https://outside.invalid'})[0],403)
        self.assertEqual(self.request('/api/research-story/present',{**body,'story_hash':'0'*64})[0],409)
        self.assertEqual(self.request('/api/research-story/present',self.body(view=dict(owner.settings,subject='unknown')))[0],400)
        self.assertEqual(self.request('/api/research-story/run',self.body())[0],404)

    def test_exports_reject_stale_view_and_bad_import_keeps_prior_view(self):
        owner=self.server.workspace.research_story;old=owner.current()['hash']
        self.request('/api/research-story/present',self.body(view=dict(owner.settings,examples=True)))
        self.assertEqual(self.request('/api/research-story/export.json',headers={'X-Traitweaver-Expected-Revision':old})[0],409)
        before=owner.current()
        for raw in ('{bad','{"x":1,"x":2}',' '*262145):
            self.assertEqual(self.request('/api/research-story/open',self.body(package_json=raw))[0],400)
            self.assertEqual(owner.current(),before)


if __name__=='__main__':unittest.main()
