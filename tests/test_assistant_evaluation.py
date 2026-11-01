"""Evaluation qualification: actual scorer and CLI, no sockets/model/credentials."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import assistant, assistant_evaluation as e, study

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('evaluation_cli_test',ROOT/'tools/evaluate_assistant.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)

def no_network(event,args):
    if event.startswith('socket.'):raise RuntimeError('Evaluation tests forbid socket operations')
sys.addaudithook(no_network)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cid='RNA_BEFORE';self.preview=e.prepare(self.cid,0)

    def all_controls(self,kind):return [e.control(c['id'],p,kind) for c in e.catalog()['cases'] for p in range(3)]

    def test_separate_catalog_has_six_pairs_and_keeps_original_scientific_inputs_pinned(self):
        cases=e.catalog()['cases'];self.assertEqual(len(cases),12);self.assertEqual(len({c['family_id'] for c in cases}),6)
        self.assertTrue(all(c['input_kind']=='clearly_synthetic' for c in cases))
        self.assertEqual(hashlib.sha256(assistant.CATALOG.read_bytes()).hexdigest(),assistant.CATALOG_SHA256)
        self.assertEqual(assistant.prepare('ENV_ALGAE')['body']['max_output_tokens'],1024)
        self.assertEqual(len(assistant.catalog()['cases']),4)

    def test_expected_judgments_and_human_scores_are_not_in_requests(self):
        for case in e.catalog()['cases']:
            preview=e.prepare(case['id']);supplied=json.loads(preview['body']['input'])
            self.assertEqual(set(supplied),{'id','area','question','input_kind','records','candidate_claims','limits','candidate_actions'})
            self.assertNotIn('rubric',study.canonical(preview['body']));self.assertNotIn('first_action_id',study.canonical(preview['body']))
            self.assertNotIn('human_review',study.canonical(preview['body']))
            self.assertEqual(supplied['records'],case['records']);self.assertEqual(supplied['candidate_claims'],case['candidate_claims'])
            self.assertFalse(preview['live_transport_available']);self.assertEqual(preview['spend_authorized_usd'],0)
            self.assertFalse(preview['body']['store']);self.assertNotIn('tools',preview['body'])

    def test_permutations_change_only_action_presentation_and_request_identity(self):
        requests=[e.prepare(self.cid,p) for p in range(3)]
        self.assertEqual(len({r['request_sha256'] for r in requests}),3)
        for r in requests:
            inp=json.loads(r['body']['input']);actions=inp.pop('candidate_actions')
            self.assertEqual(inp,{k:v for k,v in json.loads(requests[0]['body']['input']).items() if k!='candidate_actions'})
            self.assertEqual({a['id'] for a in actions},{a['id'] for a in e.get_case(self.cid)['candidate_actions']})
        for p in (True,3,-1,'1'):
            with self.assertRaises(ValueError):e.prepare(self.cid,p)

    def test_reference_control_tracks_evidence_changes_and_is_order_invariant(self):
        s=e.summarize(self.all_controls('oracle'))
        self.assertEqual(s['first_action_rubric_matches'],36);self.assertEqual(s['claim_verdict_rubric_matches'],108)
        self.assertTrue(all(r['observed_change'] and r['both_first_actions_match_rubric'] for r in s['evidence_change_pairs']))
        self.assertTrue(all(r['first_action_consistent'] for r in s['order_variants']))
        self.assertEqual(s['human_usefulness'],'not_reviewed')

    def test_supplied_order_control_is_detected_despite_valid_ids_and_correct_claim_labels(self):
        s=e.summarize(self.all_controls('supplied_order'))
        self.assertEqual(s['first_action_rubric_matches'],12);self.assertEqual(s['claim_verdict_rubric_matches'],108)
        self.assertTrue(all(not r['observed_change'] for r in s['evidence_change_pairs']))
        self.assertTrue(all(not r['first_action_consistent'] for r in s['order_variants']))

    def test_false_certainty_cannot_hide_behind_correct_priorities(self):
        s=e.summarize(self.all_controls('false_certainty'))
        self.assertEqual(s['first_action_rubric_matches'],36);self.assertLess(s['claim_verdict_rubric_matches'],108)
        self.assertEqual(s['unsupported_successes_withheld'],0)
        with self.assertRaises(ValueError):assistant.validate_record(e.control(self.cid,0,'false_certainty'))

    def test_wrong_but_known_citations_are_scored_not_silently_treated_as_support(self):
        record=e.control(self.cid);answer=deepcopy(record['answer'])
        answer['judgments'][0]['cited_record_ids']=['RNA_DESIGN']
        value=e.grade(self.cid,0,answer,self.preview['request_sha256'],'synthetic_oracle_control')
        self.assertFalse(value['automated']['all_required_claim_citations_present'])
        self.assertEqual(value['automated']['scientific_entailment'],'not_automatically_established')
        answer['judgments'][0]['cited_record_ids']=['UNKNOWN_SOURCE']
        with self.assertRaises(ValueError):e.grade(self.cid,0,answer,self.preview['request_sha256'],'synthetic_oracle_control')

    def test_duplicates_missing_claims_and_unavailable_actions_are_rejected_without_dispatch(self):
        answer=e.control(self.cid)['answer']
        mutations=[lambda v:v['judgments'].pop(),lambda v:v['judgments'].append(v['judgments'][0]),lambda v:v['actions'][0].update(action_id='run_shell'),lambda v:v['actions'][0].update(execute=True),lambda v:v['actions'][0].update(cited_record_ids=['RNA_SAMPLES','RNA_SAMPLES']),lambda v:v['actions'][0].update(rationale='')]
        for mutate in mutations:
            bad=deepcopy(answer);mutate(bad)
            with self.assertRaises(ValueError):e.grade(self.cid,0,bad,self.preview['request_sha256'],'synthetic_oracle_control')
        with self.assertRaises(ValueError):e.grade(self.cid,1,answer,self.preview['request_sha256'],'synthetic_oracle_control')

    def test_missing_pair_members_are_unknown_not_zero_or_pass(self):
        s=e.summarize([e.control(self.cid)])
        self.assertEqual(s['scored_responses'],1)
        self.assertTrue(all(p['observed_change'] is None for p in s['evidence_change_pairs']))
        self.assertTrue(all(o['first_action_consistent'] is None for o in s['order_variants']))
        with self.assertRaises(ValueError):e.summarize([e.control(self.cid)]*2)

    def test_control_kinds_and_model_imports_cannot_be_pooled_into_one_score(self):
        with self.assertRaises(ValueError):e.package([e.control('RNA_BEFORE',0,'oracle'),e.control('RNA_AFTER',0,'supplied_order')])
        fixture=e.control('RNA_AFTER')
        model=e.grade('RNA_AFTER',0,fixture['answer'],fixture['request_sha256'],'imported_model_response_unverified')
        with self.assertRaises(ValueError):e.package([e.control(self.cid),model])

    def test_export_reopen_preserves_synthetic_roles_zero_null_and_limits(self):
        package=e.package([e.control('WATER_AFTER')]);value=e.reopen(package)
        records=e.get_case('WATER_AFTER')['records'];self.assertIn(records[2],next(c for c in value['catalog']['cases'] if c['id']=='WATER_AFTER')['records'])
        self.assertEqual(records[2]['value']['reported_value'],0);self.assertIsNone(records[2]['value']['missing_value'])
        self.assertEqual(value['results'][0]['provenance'],'synthetic_oracle_control');self.assertEqual(value['limit'],e.LIMIT)
        self.assertTrue(all(r['role']=='synthetic_record' for c in value['catalog']['cases'] for r in c['records']))
        changed=deepcopy(package);changed['catalog']['cases'][0]['records'][-1]['value']['plant_use_value']=0
        changed['sha256']=study.digest({k:v for k,v in changed.items() if k!='sha256'})
        with self.assertRaises(ValueError):e.reopen(changed)

    def test_tampered_scores_and_readiness_fail_even_with_new_outer_hash(self):
        for mutate in (lambda v:v['summary'].update(first_action_rubric_matches=999),lambda v:v['results'][0]['expanded_actions'][0].update(readiness='needs_human_approval'),lambda v:v['results'][0].update(provenance='real_muse')):
            p=e.package([e.control(self.cid)]);mutate(p);p['sha256']=study.digest({k:v for k,v in p.items() if k!='sha256'})
            with self.assertRaises(ValueError):e.reopen(p)

    def test_human_scores_remain_separate_allow_zero_and_require_explicit_status(self):
        records=[e.control(self.cid)];review=e.review_template(records)
        self.assertTrue(all(v is None for v in review['rows'][0]['scores'].values()))
        review['rows'][0]['scores']['priority']=0
        with self.assertRaises(ValueError):e.validate_human_review(review,records)
        review['status']='partially_or_fully_scored';result=e.package(records,review)
        self.assertEqual(e.reopen(result)['human_review']['rows'][0]['scores']['priority'],0)
        self.assertEqual(result['summary']['human_usefulness'],'partially_or_fully_scored')
        for bad in (True,-1,3,'2'):
            review['rows'][0]['scores']['priority']=bad
            with self.assertRaises(ValueError):e.validate_human_review(review,records)

    def test_private_notes_and_rationale_block_export_without_redaction(self):
        record=e.control(self.cid);review=e.review_template([record]);review['rows'][0]['notes']='confidential synthetic privacy canary'
        with self.assertRaises(ValueError):e.package([record],review)
        answer=deepcopy(record['answer']);answer['actions'][0]['rationale']='private research synthetic canary'
        with self.assertRaises(ValueError):e.grade(self.cid,0,answer,self.preview['request_sha256'],'synthetic_oracle_control')
        self.assertEqual(review['rows'][0]['notes'],'confidential synthetic privacy canary')

    def test_model_parser_strips_raw_metadata_and_rejects_refusal_incomplete_and_tools(self):
        answer=e.control(self.cid)['answer']
        reply={'model':assistant.MODEL,'status':'completed','id':'RAW_ID_CANARY','output':[{'type':'reasoning','summary':'RAW_REASONING_CANARY'},{'type':'message','content':[{'type':'output_text','text':study.canonical(answer)}]}]}
        record=e.parse_reply(self.cid,0,study.canonical(reply).encode(),self.preview['request_sha256'])
        self.assertEqual(record['provenance'],'imported_model_response_unverified')
        self.assertNotIn('RAW_ID_CANARY',study.canonical(record));self.assertNotIn('RAW_REASONING_CANARY',study.canonical(record))
        for changes in ({'status':'incomplete'},{'model':'other'},{'traitweaver_synthetic':True},{'output':[{'type':'function_call','name':'shell'}]},{'output':[{'type':'message','content':[{'type':'refusal'}]}]}):
            with self.assertRaises(ValueError):e.parse_reply(self.cid,0,study.canonical(dict(reply,**changes)).encode(),self.preview['request_sha256'])
        for raw in (b'{"x":1,"x":2}',b'null',b'{"x":NaN}',b'bad',b' '*(e.MAX_BYTES+1)):
            with self.assertRaises(ValueError):e.parse_reply(self.cid,0,raw,self.preview['request_sha256'])

    def test_offline_cli_exports_reopens_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'controls';result=cli.run_offline(target)
            self.assertEqual(result['new_model_calls'],0);self.assertEqual(result['synthetic_responses'],108)
            for kind in ('oracle','supplied_order','false_certainty'):
                p=e.reopen(e.read_json(target/kind/'evaluation.json'))
                self.assertEqual(p['summary']['scored_responses'],36)
                self.assertIn('Human', (target/kind/'REPORT.html').read_text())
            before=(target/'CONTROL_REPORT.json').read_bytes()
            with self.assertRaises(ValueError):cli.run_offline(target)
            self.assertEqual((target/'CONTROL_REPORT.json').read_bytes(),before)
            r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/evaluate_assistant.py'),'reopen','--package',str(target/'oracle/evaluation.json')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['scored_responses'],36)

    def test_cli_unknown_credential_argument_is_not_echoed(self):
        r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/evaluate_assistant.py'),'prepare','--case',self.cid,'--key','SYNTHETIC_ARG_CANARY'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertNotIn('SYNTHETIC_ARG_CANARY',r.stdout+r.stderr)

    def make_saved_transport_fixture(self,folder):
        # Entirely synthetic saved-file fixture. It proves no provider authenticity.
        from decimal import Decimal
        for case in assistant.catalog()['cases']:
            cid=case['case_id'];reply=assistant.synthetic_reply(cid);reply.pop('traitweaver_synthetic')
            reply['usage']={'input_tokens':120,'output_tokens':60,'total_tokens':180}
            record=assistant.parse_reply(cid,study.canonical(reply).encode(),assistant.prepare(cid)['request_sha256'])
            directory=folder/cid;directory.mkdir()
            (directory/'assistant-review.json').write_text(study.canonical(assistant.package(record)))
            (directory/'assistant-review.txt').write_text(assistant.readable(record))
            body=assistant.prepare(cid)['body'];body['max_output_tokens']=8192
            receipt={'schema_version':'traitweaver.assistant_batch_receipt.v2','case_id':cid,'approval_sha256':'a'*64,
                     'request_sha256':study.digest(body),'response_sha256':record['receipt']['response_sha256'],
                     'transport':'direct_meta_transport','core_request_sha256':record['request_sha256'],'wire_override':{'max_output_tokens':8192},
                     'reported_model':assistant.MODEL,'reported_usage':dict(reply['usage'],reasoning_tokens=20,cached_tokens=0),
                     'estimated_cost_usd':str((Decimal(120)*Decimal('1.25')+Decimal(60)*Decimal('4.25'))/1000000),
                     'actual_provider_charge_usd':None,'local_checks':[],
                     'core_provenance_limit':'Synthetic saved-file fixture only; not authentication.','qualification':'Synthetic test; no model or research execution.'}
            (directory/'BATCH_RECEIPT.json').write_text(study.canonical(receipt))

    def test_saved_batch_review_reads_only_named_exports_never_controls_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.make_saved_transport_fixture(folder)
            forbidden=folder/'LOCAL_CONTROL.json';forbidden.write_text('SYNTHETIC_NOT_FOR_REVIEW')
            before={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
            original=e.read_json
            def checked(path):
                self.assertNotEqual(Path(path),forbidden);return original(path)
            with patch.object(e,'read_json',side_effect=checked):result=e.historical_batch(folder)
            self.assertEqual(result['new_model_or_tool_calls'],0);self.assertEqual(len(result['cases']),4)
            self.assertTrue(all(r['action_order_unchanged'] for r in result['cases']))
            self.assertTrue(all(r['position_bias']=='not_tested_in_saved_batch' for r in result['cases']))
            self.assertNotIn('SYNTHETIC_NOT_FOR_REVIEW',study.canonical(result))
            after={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
            self.assertEqual(before,after)

    def test_saved_batch_mixed_identities_invalid_cost_and_changed_text_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.make_saved_transport_fixture(folder)
            path=folder/'PROTEIN_GFP/BATCH_RECEIPT.json';original=e.read_json(path)
            for change in ({'approval_sha256':'b'*64},{'estimated_cost_usd':'not-a-number'},{'reported_usage':dict(original['reported_usage'],reasoning_tokens=True)},{'request_sha256':'0'*64}):
                path.write_text(study.canonical(dict(original,**change)))
                with self.assertRaises(ValueError):e.historical_batch(folder)
            path.write_text(study.canonical(original));(folder/'PROTEIN_GFP/assistant-review.txt').write_text('Synthetic changed readable export')
            with self.assertRaises(ValueError):e.historical_batch(folder)

    def test_catalog_tampering_missing_and_symlink_have_no_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'catalog';p.write_text('{}')
            with patch.object(e,'CATALOG',p),self.assertRaises(ValueError):e.catalog()
            p.unlink()
            with patch.object(e,'CATALOG',p),self.assertRaises(OSError):e.catalog()
            p.symlink_to(e.CATALOG)
            with patch.object(e,'CATALOG',p),self.assertRaises(ValueError):e.catalog()


if __name__=='__main__':unittest.main()
