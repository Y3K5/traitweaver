"""Four-case closed assistant contract: actual core/CLI, synthetic replies only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import assistant as a, study, protein_card

ROOT=Path(__file__).resolve().parents[1]
CASES=('ENV_ALGAE','PROTEIN_GFP','RNA_SYNTHETIC','REPRO_SYNTHETIC')

def offline(event,args):
    if event.startswith('socket.'):
        raise RuntimeError('Assistant tests prohibit all socket operations')
sys.addaudithook(offline)


class AssistantTests(unittest.TestCase):
    def record(self,case_id):
        preview=a.prepare(case_id)
        return a.parse_reply(case_id,study.canonical(a.synthetic_reply(case_id)).encode(),preview['request_sha256'])

    def proposal(self,case_id):
        return json.loads(a.synthetic_reply(case_id)['output'][0]['content'][0]['text'])

    def test_four_cases_are_public_or_synthetic_with_source_linked_action_cards(self):
        self.assertEqual([c['case_id'] for c in a.catalog()['cases']],list(CASES))
        for case_id in CASES:
            with self.subTest(case=case_id):
                case=a.get_case(case_id);record=self.record(case_id)
                ids={r['id'] for r in case['records']}|{s['id'] for s in case['sources']}
                self.assertEqual(len(record['actions']),3)
                self.assertEqual([x['priority'] for x in record['actions']],[1,2,3])
                for action in record['actions']:
                    for field in ('task','why','required_input','expected_deliverable','completion_check'):
                        self.assertTrue(action[field].strip())
                    self.assertEqual(action['kind'],'proposal')
                    self.assertIn(action['readiness'],('now','needs_evidence','needs_human_approval'))
                    self.assertTrue(set(action['citations'])<=ids)
                roles={r['id']:r['role'] for r in case['records']}
                roles.update({s['id']:'source_reference' for s in case['sources']})
                for claims in record['claims'].values():
                    for claim in claims:
                        self.assertTrue(set(claim['citations'])<=ids)
                        self.assertEqual(claim['source_roles'],sorted({roles[i] for i in claim['citations']}))
                self.assertTrue(record['claims']['withheld'])
                self.assertFalse(record['receipt']['billing_verified'])
                self.assertIsNone(record['receipt']['reported_usage'])

    def test_public_snapshots_and_component_attribution_match_existing_qualified_data(self):
        case=a.get_case('PROTEIN_GFP');card=protein_card.build_card()
        self.assertEqual(case['attribution'],card['attribution'])
        self.assertEqual(case['records'][1:-2],card['database_annotations']+card['model_predictions'])
        self.assertEqual(a.get_case('ENV_ALGAE')['records'][:-2],study.bundle()['evidence'])
        changed=deepcopy(card);changed['unavailable']['pdb']='invented'
        with patch.object(protein_card,'build_card',return_value=changed),self.assertRaises(ValueError):a.catalog()

    def test_changed_or_missing_catalog_never_falls_back_to_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'catalog.json';file.write_text('{}')
            with patch.object(a,'CATALOG',file),self.assertRaisesRegex(ValueError,'bytes changed'):a.catalog()
            file.unlink()
            with patch.object(a,'CATALOG',file),self.assertRaises(OSError):a.catalog()

    def test_unknown_case_free_text_and_private_notes_cannot_enter_prepared_request(self):
        for value in ('unknown',{'case_id':'ENV_ALGAE','notes':'SYNTHETIC_PRIVATE_CANARY'},None):
            with self.subTest(value=value),self.assertRaises(ValueError):a.prepare(value)
        for case_id in CASES:
            request=a.prepare(case_id)
            self.assertNotIn('SYNTHETIC_PRIVATE_CANARY',request['body']['input'])
            self.assertEqual(json.loads(request['body']['input']),a.get_case(case_id))
            self.assertEqual(request['status'],'not_sent')
            self.assertFalse(request['live_transport_available'])

    def test_prepared_body_identity_limits_and_schema_are_bound_to_case(self):
        for case_id in CASES:
            p=a.prepare(case_id);body=p['body']
            self.assertEqual(body['model'],'muse-spark-1.3')
            self.assertEqual(body['max_output_tokens'],1024)
            self.assertIs(body['store'],False)
            self.assertEqual(p['request_sha256'],study.digest(body))
            self.assertLessEqual(len(study.canonical(body).encode()),a.MAX_REQUEST)
            self.assertNotIn('tools',body)
            self.assertFalse(body['text']['format']['schema']['additionalProperties'])

    def test_three_unique_actions_can_be_reordered_but_not_replaced_or_executed(self):
        for case_id in CASES:
            p=self.proposal(case_id);p['prioritized_action_ids'].reverse()
            self.assertEqual(a.validate_proposal(case_id,p),p)
            for ids in (p['prioritized_action_ids'][:2],p['prioritized_action_ids']+[p['prioritized_action_ids'][0]],
                        [p['prioritized_action_ids'][0]]*3,['shell_command','lab_protocol','invented']):
                with self.subTest(case=case_id,ids=ids),self.assertRaises(ValueError):
                    a.validate_proposal(case_id,dict(p,prioritized_action_ids=ids))
            with self.assertRaises(ValueError):a.validate_proposal(case_id,dict(p,execute=True))

    def test_unknown_cross_case_and_wrong_category_claim_ids_are_rejected(self):
        p=self.proposal('PROTEIN_GFP')
        for ids in (['INVENTED'],['ENV_SUPPORTED'],p['withheld'],[True],{}):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                a.validate_proposal('PROTEIN_GFP',dict(p,supports=ids))

    def test_unknowns_conflicts_and_withheld_conclusions_cannot_be_omitted(self):
        for case_id in CASES:
            p=self.proposal(case_id)
            for group in a.GROUPS:
                with self.subTest(case=case_id,group=group),self.assertRaises(ValueError):
                    a.validate_proposal(case_id,dict(p,**{group:[]}))
            with self.assertRaises(ValueError):a.validate_proposal(case_id,dict(p,winner='invented'))

    def test_promoted_prediction_altered_citations_action_arguments_or_readiness_fail(self):
        baseline=self.record('PROTEIN_GFP')
        mutations=[lambda r:r['claims']['supports'][2].update(source_roles=['published_observation']),
                   lambda r:r['claims']['supports'][0].update(citations=['INVENTED']),
                   lambda r:r['actions'][0].update(task='Perform an unreviewed experiment'),
                   lambda r:r['actions'][2].update(readiness='now'),
                   lambda r:r['claims']['withheld'].clear(),lambda r:r['limits'].clear(),
                   lambda r:r.update(case_sha256='0'*64)]
        for mutate in mutations:
            changed=deepcopy(baseline);mutate(changed)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):a.validate_record(changed)

    def test_zero_null_and_synthetic_design_conflicts_are_preserved(self):
        rna=a.get_case('RNA_SYNTHETIC');manifest=rna['records'][2]['value']
        self.assertEqual(manifest['fastq_files_supplied'],0);self.assertIsNone(manifest['read_count'])
        rows=rna['records'][1]['value']['rows']
        self.assertEqual(len(rows),5);self.assertEqual(len({r['sample_id'] for r in rows}),4)
        self.assertEqual(rows[2]['layout'],'single');self.assertEqual(manifest['SYN-T1_layout'],'paired')
        rep=a.get_case('REPRO_SYNTHETIC')['records'][3]['value']
        self.assertEqual(rep['exit_code'],0);self.assertIsNone(rep['command'])
        for case_id in ('RNA_SYNTHETIC','REPRO_SYNTHETIC'):
            pkg=a.package(self.record(case_id));case=pkg['case']
            if case_id=='RNA_SYNTHETIC':case['records'][2]['value']['read_count']=0
            else:case['records'][3]['value']['command']='invented'
            pkg['sha256']=study.digest({k:v for k,v in pkg.items() if k!='sha256'})
            with self.assertRaises(ValueError):a.validate_package(pkg)

    def test_phosphorus_endpoints_remain_distinct_and_no_winner_is_accepted(self):
        record=self.record('ENV_ALGAE');case=a.get_case('ENV_ALGAE')
        scope=next(r for r in case['records'] if r['id']=='ENV_SCOPE')['value']
        self.assertTrue({'removal','assimilation','collection','plant_use'}<=scope.keys())
        self.assertIn('ENV_ENDPOINTS',[c['id'] for c in record['claims']['unknown_or_contradictory']])
        for claim in ('recovery_winner','plant_use_benefit','DE_significant','structure_confirmed'):
            p=self.proposal('ENV_ALGAE');p['supports'].append(claim)
            with self.assertRaises(ValueError):a.validate_proposal('ENV_ALGAE',p)

    def test_refusal_incomplete_wrong_model_tool_call_and_multiple_texts_rejected(self):
        base=a.synthetic_reply('ENV_ALGAE');request=a.prepare('ENV_ALGAE')['request_sha256']
        variants=[dict(base,status='incomplete'),dict(base,model='other'),dict(base,output=[]),
                  dict(base,output=[{'type':'function_call','name':'shell'}]),
                  dict(base,output=[{'type':'message','content':[{'type':'refusal','refusal':'declined'}]}]),
                  dict(base,output=base['output']*2),dict(base,traitweaver_synthetic='true')]
        for reply in variants:
            with self.subTest(reply=reply),self.assertRaises(ValueError):a.parse_reply('ENV_ALGAE',study.canonical(reply).encode(),request)

    def test_duplicate_keys_nonfinite_malformed_oversize_and_stale_replies_rejected(self):
        request=a.prepare('ENV_ALGAE')['request_sha256']
        for raw in (b'{bad',b'{"x":1,"x":2}',b'{"x":NaN}',b' '* (a.MAX_BYTES+1),b'null'):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):a.parse_reply('ENV_ALGAE',raw,request)
        with self.assertRaises(ValueError):a.parse_reply('ENV_ALGAE',study.canonical(a.synthetic_reply('ENV_ALGAE')).encode(),'0'*64)

    def test_imported_reply_is_unverified_raw_provider_metadata_is_not_exported(self):
        reply=a.synthetic_reply('ENV_ALGAE');reply.pop('traitweaver_synthetic')
        reply['provider_extra']='RAW_METADATA_NOT_FOR_EXPORT'
        reply['output'].insert(0,{'type':'reasoning','summary':'RAW_REASONING_NOT_FOR_EXPORT'})
        reply['usage']={'input_tokens':100,'output_tokens':0,'total_tokens':100}
        record=a.parse_reply('ENV_ALGAE',study.canonical(reply).encode(),a.prepare('ENV_ALGAE')['request_sha256'])
        self.assertEqual(record['receipt']['provenance'],'owner_imported_reply_authenticity_unverified')
        self.assertEqual(record['receipt']['reported_usage']['output_tokens'],0)
        serialized=study.canonical(a.package(record))+a.readable(record)
        self.assertNotIn('RAW_METADATA_NOT_FOR_EXPORT',serialized);self.assertNotIn('RAW_REASONING_NOT_FOR_EXPORT',serialized)

    def test_invalid_usage_cannot_be_saved_as_billing_evidence(self):
        for usage in ({'output_tokens':False},{'input_tokens':-1},{'total_tokens':1.5},
                      {'input_tokens':2,'output_tokens':3,'total_tokens':0},{'cookie':'bad'}):
            reply=a.synthetic_reply('ENV_ALGAE');reply['usage']=usage
            with self.subTest(usage=usage),self.assertRaises(ValueError):
                a.parse_reply('ENV_ALGAE',study.canonical(reply).encode(),a.prepare('ENV_ALGAE')['request_sha256'])

    def test_native_json_text_export_reopen_preserves_all_claims_actions_limits_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case_id in CASES:
                record=self.record(case_id);folder=Path(tmp)/case_id
                a.export_bundle(record,folder)
                # Reopen must not dispatch inference, preparation of a new result,
                # synthetic generation or any local research tool.
                with (patch.object(a,'synthetic_reply',side_effect=AssertionError('No inference')),
                      patch.object(study,'coverage',side_effect=AssertionError('No execution'))):
                    self.assertEqual(a.reopen(folder/'assistant-review.json'),record)
                text=(folder/'assistant-review.txt').read_text()
                for group in a.GROUPS:
                    for claim in record['claims'][group]:self.assertIn(study.canonical(claim),text)
                for action in record['actions']:self.assertIn(study.canonical(action),text)
                for limit in record['limits']:self.assertIn(limit,text)
                self.assertIn(study.canonical(record['receipt']),text)
                self.assertIn('synthetic_fixture',text)
                self.assertEqual(set(p.name for p in folder.iterdir()),{'assistant-review.json','assistant-review.txt'})

    def test_corrupt_altered_or_symlink_packages_rejected_without_changing_prior_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'saved';record=self.record('RNA_SYNTHETIC');a.export_bundle(record,folder)
            original=(folder/'assistant-review.json').read_bytes()
            for raw in (b'{bad',b'{"x":1,"x":2}',b' '* (a.MAX_BYTES+1)):
                bad=Path(tmp)/'bad.json';bad.write_bytes(raw)
                with self.assertRaises(ValueError):a.reopen(bad)
            link=Path(tmp)/'link';link.symlink_to(folder/'assistant-review.json')
            with self.assertRaises(ValueError):a.reopen(link)
            with self.assertRaises(ValueError):a.export_bundle(record,folder)
            self.assertEqual((folder/'assistant-review.json').read_bytes(),original)

    def test_interrupted_export_preserves_earlier_saved_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'saved';record=self.record('REPRO_SYNTHETIC');a.export_bundle(record,folder)
            before=(folder/'assistant-review.json').read_bytes();new=Path(tmp)/'interrupted'
            with patch('os.fsync',side_effect=OSError('Synthetic interrupted save')),self.assertRaises(OSError):a.export_bundle(record,new)
            self.assertFalse(new.exists());self.assertEqual((folder/'assistant-review.json').read_bytes(),before)
            self.assertFalse(list(Path(tmp).glob('.assistant-pending-*')))

    def test_cli_is_offline_only_and_reopens_saved_review(self):
        guard="import runpy,sys\ndef deny(e,a):\n if e.startswith('socket.'):raise RuntimeError('Offline only')\nsys.addaudithook(deny)\nsys.argv=sys.argv[1:]\nrunpy.run_path(sys.argv[0],run_name='__main__')"
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'review'
            def run(*args):
                return subprocess.run([sys.executable,'-B','-c',guard,str(ROOT/'tools/assistant_review.py'),*map(str,args)],
                    cwd=tmp,env={'PATH':'/usr/bin:/bin'},capture_output=True,text=True,timeout=20)
            result=run('--synthetic','RNA_SYNTHETIC','--output',folder)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('synthetic_fixture',result.stdout)
            reopened=run('--reopen',folder/'assistant-review.json')
            self.assertEqual(reopened.returncode,0,reopened.stderr);self.assertEqual(reopened.stdout,result.stdout)
            prepared=run('--prepare','PROTEIN_GFP');self.assertEqual(prepared.returncode,0)
            self.assertFalse(json.loads(prepared.stdout)['live_transport_available'])
            self.assertNotEqual(run('--live').returncode,0)


if __name__=='__main__':unittest.main()
