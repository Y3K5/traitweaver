"""Independent workbench/history/privacy tests using actual services and handlers."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from traitweaver import assistant, assistant_workspace, research_story, study, workbench as w, workspace_server
from traitweaver.study_store import Store
from test_review_handlers import MemoryServer, MemoryConnection


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.a=assistant_workspace.Session();self.s=research_story.Session();self.w=w.Session(self.a,self.s)

    def package(self):return self.w.export(self.w.current()['hash'])

    def test_annotation_history_parents_and_branch_base_do_not_change_science(self):
        before=self.w.science();first=self.w.view()['annotation']
        self.w.save('Public-source review','Second annotation');second=self.w.view()['annotation']
        self.w.history(first['hash']);self.w.save('Earlier question revisited','Third annotation')
        p=self.package();third=p['annotations'][2]
        self.assertEqual(third['parent_hash'],second['hash']);self.assertEqual(third['based_on_hash'],first['hash'])
        self.assertEqual(p['annotations'][0],first);self.assertEqual(self.w.science(),before)
        self.assertEqual(w.validate_package(p),p)

    def test_annotation_edits_are_not_tool_arguments_or_model_prompts(self):
        request=assistant.prepare('ENV_ALGAE');self.w.save('Different review question','Uninterpreted proposal')
        self.w.act('check');self.w.act('synthetic')
        self.assertEqual(assistant.prepare('ENV_ALGAE'),request)
        self.assertEqual(self.w.science()['local_checks'][0]['decision']['case_sha256'],study.digest(assistant.get_case('ENV_ALGAE')))
        self.assertEqual(self.w.science()['accepted_review']['receipt']['provenance'],'synthetic_fixture')

    def test_muse_preparation_excludes_notes_and_does_not_execute_or_change_state(self):
        for cid in assistant_workspace.TITLES:
            self.w.select(cid);self.w.save('Synthetic private-note test','Cookie: SYNTHETIC_NOTE_CANARY')
            before=self.w.current()
            with patch.object(assistant_workspace,'run_local_check',side_effect=AssertionError('No execution')):
                request=self.w.prepare_muse()
            self.assertEqual(request,assistant.prepare(cid));self.assertEqual(self.w.current(),before)
            self.assertEqual(request['body']['max_output_tokens'],1024);self.assertFalse(request['live_transport_available'])
            self.assertEqual(request['status'],'not_sent');self.assertNotIn('SYNTHETIC_NOTE_CANARY',study.canonical(request))

    def test_all_cases_use_unchanged_pins_and_keep_case_slots(self):
        for cid in assistant_workspace.TITLES:
            self.w.select(cid);self.w.save('Public or synthetic review',cid+' annotation');self.w.act('check');self.w.act('synthetic')
            p=self.package();self.assertEqual(p['science']['case'],assistant.get_case(cid));self.assertEqual(len(p['science']['accepted_review']['actions']),3)
            self.assertEqual(p['science']['story_package'] is not None,cid=='ENV_ALGAE')
            w.validate_package(p)
        self.w.select('ENV_ALGAE');self.assertEqual(self.w.view()['annotation']['notes'],'ENV_ALGAE annotation')

    def test_checkpoint_navigation_never_dispatches_check_or_model(self):
        with patch.object(assistant_workspace,'run_local_check',side_effect=AssertionError('No execution')),patch.object(assistant,'prepare',side_effect=AssertionError('No request')):
            for checkpoint in w.STAGES:self.w.present(checkpoint);self.w.view();self.package()
        self.assertEqual(self.w.science()['local_checks'],[]);self.assertIsNone(self.w.science()['accepted_review'])

    def test_current_privacy_acknowledgment_required_for_json_and_markdown(self):
        with self.assertRaises(ValueError):self.w.export()
        old=self.w.current()['hash'];self.w.present('export')
        with self.assertRaises(ValueError):self.w.export(old)
        self.package();self.w.readable(self.w.current()['hash'])
        self.w.save('New public question','')
        with self.assertRaises(ValueError):self.w.export(old)

    def test_privacy_canaries_are_blocked_without_printing_values_or_removing_notes(self):
        canaries=['/home/synthetic-owner/private.txt','api_key: FAKE_NOT_A_KEY',
                  'Cookie: synthetic-session','<script>synthetic()</script>',
                  'https://example.invalid/?token=SYNTHETIC','confidential synthetic example',
                  'sk-'+'x'*32,'![synthetic](https://example.invalid/image)']
        for canary in canaries:
            owner=w.Session(assistant_workspace.Session(),self.s);owner.save('Synthetic screening test',canary)
            findings=owner.view()['privacy'];self.assertEqual(findings['status'],'blocked')
            self.assertNotIn(canary,study.canonical(findings))
            for method in (owner.export,owner.readable):
                with self.assertRaises(ValueError) as e:method(owner.current()['hash'])
                self.assertNotIn(canary,str(e.exception))
            self.assertEqual(owner.view()['annotation']['notes'],canary)

    def test_all_history_screened_even_after_clean_successor_or_history_selection(self):
        self.w.save('Synthetic screening test','Cookie: SYNTHETIC_CANARY');private=self.w.view()['annotation']
        self.w.save('Public review','Clean successor');self.w.history(self.w.view()['annotations'][0]['hash'])
        with self.assertRaises(ValueError):self.package()
        self.assertEqual(self.w.view()['annotations'][1],private);self.assertEqual(len(self.w.view()['annotations']),3)

    def test_markdown_escapes_markup_without_changing_json(self):
        notes='A [literal](proposal) <b>label</b> & a *proposal*'
        self.w.save('Public review',notes);p=self.package();text=self.w.readable(self.w.current()['hash'])
        self.assertEqual(p['annotations'][-1]['notes'],notes)
        self.assertIn(w.markdown_literal(notes),text);self.assertNotIn('<b>',text)
        self.assertNotIn('[literal](proposal)',text);self.assertIn('NOT REVIEWED',text)

    def test_reopen_preserves_full_history_and_receipts_but_no_underlying_owner_mutation(self):
        self.w.save('Public review','Saved note');self.w.act('check');self.w.act('synthetic');self.w.present('actions');p=self.package()
        target=w.Session(assistant_workspace.Session(),research_story.Session());before=target.assistant.current()
        with patch.object(assistant_workspace,'run_local_check',side_effect=AssertionError('No rerun')):
            target.open(p);self.assertEqual(target.export(target.current()['hash']),p)
        self.assertEqual(target.assistant.current(),before);self.assertTrue(target.view()['current']['read_only'])
        for action in (lambda:target.save('Changed',''),lambda:target.act('check'),lambda:target.history(p['selected_hash'])):
            with self.assertRaises(ValueError):action()
        target.present('evidence');self.assertTrue(target.view()['current']['read_only'])
        target.select('ENV_ALGAE');self.assertFalse(target.view()['current']['read_only'])

    def test_published_statistics_mapping_and_nulls_survive_export(self):
        d=self.package()['science']['story_package']['content']
        self.assertEqual(d['summaries']['phosphate_uptake']['rows'][2]['record']['uncertainty']['n'],3)
        self.assertEqual(d['reference_chain'][-1]['length'],752);self.assertIsNone(d['actual_edited_material_id'])
        self.assertIsNone(d['gfp_reference']['relevance_link_to_algae'])
        self.w.select('RNA_SYNTHETIC');self.w.act('check');result=self.package()['science']['local_checks'][0]['result']
        self.assertEqual(result['fastq_files_supplied'],0);self.assertIsNone(result['read_count'])
        self.assertFalse(result['analysis_ready'])

    def test_tampering_roles_sources_history_and_review_rejected_even_after_rehash(self):
        self.w.act('synthetic');self.w.act('check');p=self.package()
        mutations=[lambda p:p.update(human_review='approved'),lambda p:p['science']['case'].update(objective='Changed'),
                   lambda p:p['annotations'][0].update(notes='Changed'),lambda p:p.update(selected_hash='unknown'),
                   lambda p:p['science']['local_checks'][0]['result'].update(status='approved'),
                   lambda p:p['science']['accepted_review']['actions'][0].update(citations=['UNKNOWN']),
                   lambda p:p['science']['story_package']['content'].update(actual_lab_run_id='invented')]
        for mutate in mutations:
            bad=deepcopy(p);mutate(bad);bad['sha256']=study.digest({k:v for k,v in bad.items() if k!='sha256'})
            before=self.w.current()
            with self.assertRaises(ValueError):self.w.open(bad)
            self.assertEqual(self.w.current(),before)

    def test_malformed_and_oversized_annotations_leave_prior_record(self):
        before=self.w.current()
        for question,notes in [('',''),('Valid',None),('Valid','x'*2001),('x'*1201,'')]:
            with self.assertRaises(ValueError):self.w.save(question,notes)
            self.assertEqual(self.w.current(),before)
        with self.assertRaises(ValueError):w.Session(None,self.s)
        for value in (None,[],{},dict(self.package(),science={'case':[]})):
            with self.assertRaises(ValueError):self.w.open(value)

    def test_failed_audit_receipt_is_retained_and_never_retried(self):
        with patch.object(assistant_workspace,'run_local_check',side_effect=RuntimeError('Synthetic failure')):self.w.act('check')
        result=self.package()['science']['local_checks'][0]['result'];self.assertEqual(result['status'],'failed')
        with self.assertRaises(ValueError):self.w.act('check')
        self.assertEqual(self.w.science()['local_checks'][0]['result'],result)


class WorkbenchHandlerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'study');self.addCleanup(self.store.close)
        guard=patch('socket.socket',side_effect=AssertionError('No sockets'));guard.start();self.addCleanup(guard.stop)
        self.server=workspace_server.make_server(self.store,server_factory=MemoryServer)
        self.token=self.request('/api/session')[1]['token'];self.w=self.server.workspace.workbench

    def request(self,path,body=None,headers=None):
        h={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','X-Traitweaver-Client':'workspace'}
        if body is not None:h.update({'Content-Type':'application/json','X-Traitweaver-Token':self.token})
        h.update(headers or {});raw=b'' if body is None else study.canonical(body).encode();h['Content-Length']=str(len(raw))
        wire=(('GET' if body is None else 'POST')+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in h.items())+'\r\n').encode()+raw
        conn=MemoryConnection(wire);self.server.RequestHandlerClass(conn,('127.0.0.1',1000),self.server)
        head,payload=bytes(conn.response).split(b'\r\n\r\n',1)
        return int(head.split(b' ')[1]),json.loads(payload) if b'application/json' in head else payload.decode()

    def body(self,**kw):return {'expected_hash':self.store.current()['hash'],'workbench_hash':self.w.current()['hash'],**kw}

    def test_actual_save_check_synthetic_export_reopen_preserve_study_and_services(self):
        before=self.store.export();science=self.server.workspace.research_story.export()
        self.assertEqual(self.request('/api/workbench/save',self.body(question='Public review',notes='Synthetic note'))[0],200)
        for action in ('check','synthetic'):self.assertEqual(self.request('/api/workbench/'+action,self.body())[0],200)
        headers={'X-Traitweaver-Expected-Revision':self.w.current()['hash'],'X-Traitweaver-Privacy-Reviewed':self.w.current()['hash']}
        code,p=self.request('/api/workbench/export.json',headers=headers);self.assertEqual(code,200)
        code,md=self.request('/api/workbench/export.md',headers=headers);self.assertEqual(code,200);self.assertIn('NOT REVIEWED',md)
        self.assertEqual(self.request('/api/workbench/open',self.body(package_json=study.canonical(p)))[0],200)
        self.assertEqual(self.store.export(),before);self.assertEqual(self.server.workspace.research_story.export(),science)
        self.assertTrue(self.w.view()['current']['read_only'])

    def test_origin_host_session_both_revisions_and_unknown_arguments_are_refused(self):
        for h in ({'Origin':'https://outside.invalid'},{'Host':'outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/workbench/present',self.body(checkpoint='plan'),h)[0],403)
        for field in ('expected_hash','workbench_hash'):
            self.assertEqual(self.request('/api/workbench/present',self.body(checkpoint='plan',**{field:'0'*64}))[0],409)
        self.assertEqual(self.request('/api/workbench/check',self.body(script='unavailable'))[0],400)
        self.assertEqual(self.request('/api/workbench/run',self.body())[0],404)
        self.assertEqual(self.request('/api/workbench/present',self.body(checkpoint='unknown'))[0],400)

    def test_export_acknowledgment_staleness_and_privacy_bypass_are_refused(self):
        self.assertEqual(self.request('/api/workbench/export.json')[0],400)
        old=self.w.current()['hash'];self.w.save('Public review','Cookie: SYNTHETIC_CANARY')
        self.assertEqual(self.request('/api/workbench/export.json',headers={'X-Traitweaver-Expected-Revision':old})[0],409)
        code,error=self.request('/api/workbench/export.json',headers={'X-Traitweaver-Privacy-Reviewed':self.w.current()['hash']})
        self.assertEqual(code,400);self.assertNotIn('SYNTHETIC_CANARY',study.canonical(error))
        self.assertEqual(len(self.w.view()['annotations']),2)

    def test_invalid_import_does_not_change_any_prior_valid_view(self):
        before=self.w.current()
        for raw in ('{bad','{"x":1,"x":2}',' '*524289):
            self.assertEqual(self.request('/api/workbench/open',self.body(package_json=raw))[0],400)
            self.assertEqual(self.w.current(),before)

    def test_muse_preview_handler_is_public_only_and_rejects_unreviewed_inputs(self):
        self.w.save('Public review','Cookie: SYNTHETIC_NOTE_CANARY');before=self.w.current()
        code,data=self.request('/api/workbench/prepare',self.body());self.assertEqual(code,200)
        self.assertEqual(data['prepared'],assistant.prepare('ENV_ALGAE'));self.assertEqual(self.w.current(),before)
        self.assertNotIn('SYNTHETIC_NOTE_CANARY',study.canonical(data))
        for headers in ({'Origin':'https://outside.invalid'},{'X-Traitweaver-Token':''}):
            self.assertEqual(self.request('/api/workbench/prepare',self.body(),headers)[0],403)
        self.assertEqual(self.request('/api/workbench/prepare',self.body(workbench_hash='0'*64))[0],409)
        self.assertEqual(self.request('/api/workbench/prepare',self.body(notes='unreviewed'))[0],400)


if __name__=='__main__':unittest.main()
