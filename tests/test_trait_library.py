"""Evidence roles, unknowns, immutable review custody and offline boundaries."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import trait_library as m, study, workspace_server
from traitweaver.study_store import Conflict, Store
from traitweaver.completed_cycle import CompletedCycle
import test_molecular_handlers
from test_review_handlers import MemoryServer


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.s = m.Session()

    def action(self, kind='source_check'):
        return {'type': kind, 'trait_id': 'psr1-uptake', 'recipient_id': 'yeast'}

    def act(self, kind='source_check'):
        self.s.act(self.action(kind), self.s.fingerprint())

    def review(self):
        return {**self.s.event_base('review', 'psr1-uptake', 'yeast'),
                'decision': 'needs_evidence', 'reviewer': 'Synthetic test reviewer',
                'reason': 'Synthetic review: stock and regulatory compatibility remain unresolved.',
                'claim_ids': ['psr1-observation'], 'safety_acknowledged': True}

    def test_catalog_has_six_contextualized_systems_with_three_separate_roles(self):
        b = self.s.bundle
        self.assertEqual(len(b['traits']), 6)
        for t in b['traits']:
            self.assertEqual({c['role'] for c in t['claims']}, m.ROLES)
            self.assertTrue(t['context'] and t['safety'] and t['open_questions'])
            self.assertTrue(all(c['reference_accession'] is None for c in t['components']))
        self.assertEqual(next(t for t in b['traits'] if t['id']=='community-phosphorus')['system_level'], 'community_process')

    def test_missing_source_and_role_promotion_fail(self):
        b = deepcopy(self.s.bundle); b['sources'].pop(0)
        with self.assertRaises(ValueError): m.validate_catalog(b)
        b = deepcopy(self.s.bundle); b['traits'][0]['claims'][1]['role'] = 'documented_observation'
        with self.assertRaises(ValueError): m.validate_catalog(b)

    def test_catalog_byte_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'changed.json'; path.write_bytes(m.DATA.read_bytes()+b' ')
            with patch.object(m, 'DATA', path), self.assertRaises(ValueError): m.catalog()

    def test_all_18_comparisons_leave_stock_evidence_unknown(self):
        for c in self.s.view()['comparisons']:
            self.assertEqual(c['transfer_status'], 'untested')
            self.assertEqual(c['sufficiency'], 'unknown')
            self.assertTrue(all(r['recipient_status']=='unknown' for r in c['rows']))
            self.assertIsNone(c['recipient']['strain'])
        self.assertIn('same_species', m.compare(self.s.bundle, 'vtc-storage', 'yeast')['relationship'])
        with self.assertRaises(ValueError): m.compare(self.s.bundle, 'vtc-storage', 'made-up')

    def test_source_check_retains_limit_and_does_not_change_evidence(self):
        before = deepcopy(self.s.bundle)
        self.act()
        result = self.s.history[0]['event']['result']
        self.assertEqual(result['scientific_entailment'], 'not_checked')
        self.assertEqual(result['recipient_validation'], 'not_performed')
        self.assertEqual(self.s.bundle, before)

    def test_stale_action_and_false_receipt_do_not_append(self):
        old = self.s.fingerprint(); self.act()
        with self.assertRaises(Conflict): self.s.act(self.action(), old)
        event = deepcopy(self.s.history[0]['event']); event['result']['recipient_validation']='passed'
        with self.assertRaises(ValueError): self.s.append(event, self.s.fingerprint())
        self.assertEqual(len(self.s.history), 1)

    def test_human_review_requires_reason_claims_safety_and_current_comparison(self):
        for key, value in [('reason', ''), ('reviewer', ''), ('safety_acknowledged', False), ('safety_acknowledged', 1), ('claim_ids', []), ('claim_ids', ['gfp-observation']), ('comparison_sha256', 'wrong'), ('decision', 'transfer_proven')]:
            event=self.review();event[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): self.s.act(event,self.s.fingerprint())
        self.s.act(self.review(),self.s.fingerprint())
        self.assertEqual(self.s.view()['scientific_review'],'pending')

    def test_prepare_is_public_only_and_never_reads_environment_or_sends(self):
        review=self.review();review['reason']='LOCAL_ONLY_SENTINEL';self.s.act(review,self.s.fingerprint())
        with patch('socket.socket',side_effect=AssertionError('No network')), patch('os.getenv',side_effect=AssertionError('No environment')):
            p=m.prepare_request(self.s.bundle,'psr1-uptake','yeast')
        self.assertNotIn('LOCAL_ONLY_SENTINEL',study.canonical(p))
        self.assertFalse(p['approved']);self.assertFalse(p['body']['store'])
        self.assertEqual(p['request_sha256'],m.digest(p['body']))
        self.assertEqual(p['max_requests'],1)

    def test_synthetic_and_imported_output_have_distinct_untrusted_provenance(self):
        self.act('synthetic_suggestions')
        event=self.s.history[-1]['event'];self.assertEqual(event['provenance'],'synthetic_replay_no_call')
        wrapper={'request_sha256':event['request']['request_sha256'],'model':m.MODEL,'output':event['output']}
        self.s.act({**self.action('import_suggestions'),'reply':study.canonical(wrapper)},self.s.fingerprint())
        self.assertEqual(self.s.history[-1]['event']['provenance'],'imported_output_authenticity_unverified')
        self.assertEqual(self.s.view()['new_provider_calls'],0)

    def test_wrong_model_hash_claim_and_arbitrary_command_are_not_admitted(self):
        self.act('synthetic_suggestions');e=self.s.history[-1]['event']
        base={'request_sha256':e['request']['request_sha256'],'model':m.MODEL,'output':e['output']}
        variants=[deepcopy(base) for _ in range(4)]
        variants[0]['model']='other';variants[1]['request_sha256']='wrong'
        variants[2]['output']['suggestions'][0]['claim_ids']=['invented']
        variants[3]['output']['suggestions'][0]['execute']='shell command'
        for v in variants:
            self.s.act({**self.action('import_suggestions'),'reply':study.canonical(v)},self.s.fingerprint())
            self.assertEqual(self.s.history[-1]['event']['type'],'rejected_import')
            self.assertNotIn('reply',self.s.history[-1]['event'])

    def test_export_requires_current_acknowledgment_and_screens_all_history(self):
        old=self.s.fingerprint();self.act()
        with self.assertRaises(ValueError):self.s.export(old)
        e=self.review();e['reason']='Synthetic private research marker';self.s.act(e,self.s.fingerprint())
        self.s.act(self.review(),self.s.fingerprint())
        with self.assertRaises(ValueError):self.s.export(self.s.fingerprint())
        self.assertEqual(len(self.s.history),3)
        self.assertTrue(self.s.view()['privacy']['findings'])

    def test_roundtrip_preserves_source_output_check_and_human_decision_readonly(self):
        self.act('synthetic_suggestions');self.act();self.s.act(self.review(),self.s.fingerprint())
        p=self.s.export(self.s.fingerprint());restored=m.Session.from_package(p)
        self.assertEqual(restored.export(restored.fingerprint()),p)
        with self.assertRaises(ValueError):restored.act(self.action(),restored.fingerprint())
        for field,value in [('new_provider_calls',1),('scientific_review','approved')]:
            changed=deepcopy(p);changed[field]=value
            with self.assertRaises(ValueError):m.Session.from_package(changed)

    def test_tampered_chain_and_forged_authenticity_are_rejected(self):
        self.act('synthetic_suggestions');p=self.s.export(self.s.fingerprint())
        p['history'][0]['event']['provenance']='real_muse_call'
        row=p['history'][0];row['hash']=m.digest({k:v for k,v in row.items() if k!='hash'})
        with self.assertRaises(ValueError):m.Session.from_package(p)

    def test_durable_restart_retains_exact_history_and_rejects_competing_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'library';self.s=m.Session(root);other=m.Session(root)
            self.act();first=(root/'000001.json').read_bytes()
            with self.assertRaises(Conflict):other.act(self.action(),other.fingerprint())
            self.s.act(self.review(),self.s.fingerprint())
            restored=m.Session(root)
            self.assertEqual(restored.history,self.s.history)
            self.assertEqual((root/'000001.json').read_bytes(),first)

    def test_browsing_repeated_views_does_not_create_history_or_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'library';s=m.Session(root)
            before=s.fingerprint()
            for _ in range(3):s.view()
            self.assertEqual(s.fingerprint(),before);self.assertFalse(root.exists())

    def test_all_dossiers_include_scoped_conflicts_methods_controls_and_pending_signoff(self):
        for t in self.s.bundle['traits']:
            d=t['dossier'];p=d['study_plan']
            self.assertEqual(p['status'],'draft_not_lab_ready')
            self.assertIsNone(p['signoff']['qualified_reviewer'])
            self.assertTrue(d['conflicts_and_caveats'] and d['missing_information'])
            self.assertTrue(p['candidate_methods'] and p['controls'] and p['measurements'])
            self.assertEqual(d['crispr_future']['status'],'future_not_connected')
            request=m.prepare_request(self.s.bundle,t['id'],'alga')
            data=study.decode(request['body']['input'])
            self.assertEqual({s['id'] for s in data['sources']},m.source_ids_for_trait(t))

    def test_scoped_signoff_preserves_plan_and_never_claims_lab_readiness(self):
        plan=m.study_plan(self.s.bundle,'psr1-uptake','yeast')
        e={**self.s.event_base('plan_signoff','psr1-uptake','yeast'),
           'plan_sha256':plan['plan_sha256'],'decision':'changes_required',
           'reviewer':'Synthetic test reviewer','qualification':'Synthetic role; not an actual reviewer',
           'organism_stock':'Synthetic stock scope','methods_conditions':'Synthetic measurement scope',
           'reason':'Synthetic rehearsal; real qualified review remains pending.','reviewer_attestation':True}
        for field,value in [('plan_sha256','wrong'),('qualification',''),('organism_stock',''),('methods_conditions',''),('decision','lab_ready'),('reviewer_attestation',False)]:
            bad=deepcopy(e);bad[field]=value
            with self.assertRaises(ValueError):self.s.act(bad,self.s.fingerprint())
        self.s.act(e,self.s.fingerprint())
        self.assertEqual(m.study_plan(self.s.bundle,'psr1-uptake','yeast'),plan)
        self.assertEqual(self.s.view()['scientific_review'],'pending')

    def test_malformed_action_is_rejected_without_mutation(self):
        for bad in (None,[],True,'send'):
            with self.assertRaises(ValueError):self.s.act(bad,self.s.fingerprint())
        self.assertFalse(self.s.history)


class LibraryHandlerTests(unittest.TestCase):
    request=test_molecular_handlers.MolecularHandlerTests.request

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'study');self.addCleanup(self.store.close)
        guard=patch('socket.socket',side_effect=AssertionError('No sockets'));guard.start();self.addCleanup(guard.stop)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']

    def body(self,**kw):
        return {'expected_hash':self.server.workspace.active.current()['hash'],'library_hash':self.server.workspace.trait_library.fingerprint(),**kw}

    def test_actions_preserve_original_study_and_use_separate_namespace(self):
        before=self.store.export();code,_=self.request('/api/trait-library/act',self.body(action={'type':'source_check','trait_id':'psr1-uptake','recipient_id':'yeast'}))
        self.assertEqual(code,200);self.assertEqual(self.store.export(),before)
        self.assertTrue((self.store.root/'trait-library-review-v1/000001.json').exists())

    def test_origin_token_and_stale_identity_block_writes(self):
        body=self.body(action={'type':'source_check','trait_id':'psr1-uptake','recipient_id':'yeast'})
        for headers in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/trait-library/act',body,headers)[0],403)
        body['library_hash']='stale';self.assertEqual(self.request('/api/trait-library/act',body)[0],409)
        self.assertFalse(self.server.workspace.trait_library.history)

    def test_no_send_route_and_prepare_is_nonmutating(self):
        before=self.server.workspace.trait_library.fingerprint()
        self.assertEqual(self.request('/api/trait-library/send',self.body())[0],404)
        code,p=self.request('/api/trait-library/prepare',self.body(trait_id='gfp-reporting',recipient_id='ecoli'))
        self.assertEqual(code,200);self.assertEqual(p['status'],'prepared_not_sent')
        self.assertEqual(self.server.workspace.trait_library.fingerprint(),before)

    def test_invalid_import_preserves_local_and_valid_import_can_return(self):
        owner=self.server.workspace.trait_library
        self.assertEqual(self.request('/api/trait-library/open',self.body(package_json='{}'))[0],400)
        self.assertIs(self.server.workspace.trait_library,owner)
        p=owner.export(owner.fingerprint())
        self.assertEqual(self.request('/api/trait-library/open',self.body(package_json=study.canonical(p)))[0],200)
        self.assertTrue(self.server.workspace.trait_library.read_only)
        self.assertEqual(self.request('/api/trait-library/local',self.body())[0],200)
        self.assertIs(self.server.workspace.trait_library,owner)

    def test_export_requires_header_bound_to_current_library(self):
        self.assertEqual(self.request('/api/trait-library/export.json')[0],400)
        self.assertEqual(self.request('/api/trait-library/export.json',headers={'X-Traitweaver-Privacy-Reviewed':self.server.workspace.trait_library.fingerprint()})[0],200)

    def test_completed_phosphorus_demo_remains_unchanged_when_library_used(self):
        completed=CompletedCycle(study.APP_ROOT/'data/synthetic-cycle')
        before=completed.export_review()
        self.server=workspace_server.make_server(completed,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token']
        self.assertEqual(self.request('/api/trait-library/act',self.body(action={'type':'synthetic_suggestions','trait_id':'gfp-reporting','recipient_id':'ecoli'}))[0],200)
        self.assertEqual(completed.export_review(),before)
