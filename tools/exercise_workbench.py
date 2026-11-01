"""Exercise four research-review workflows locally; no live transport exists here."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traitweaver import assistant, assistant_workspace, research_story, study, workbench

ORDERS=(
    ('evidence','identity','check','actions','plan','export'),
    ('plan','check','evidence','identity','actions','export'),
    ('actions','evidence','check','identity','plan','export'),
    ('identity','plan','actions','check','evidence','export'),
    ('check','actions','plan','identity','evidence','export'),
    ('export','plan','identity','check','actions','evidence'),
)


def offline(event,args):
    if event.startswith('socket.'):
        raise RuntimeError('Workflow exercise prohibits network sockets')


def exercise(destination):
    target=Path(destination)
    if target.exists() or target.is_symlink():raise ValueError('Choose a fresh output folder')
    resolved=target.resolve()
    if resolved==study.APP_ROOT or study.APP_ROOT in resolved.parents:raise ValueError('Keep generated review files outside the repository')
    target.mkdir()
    rows=[]
    for cid in assistant_workspace.TITLES:
        for number,order in enumerate(ORDERS,1):
            helper=assistant_workspace.Session();story=research_story.Session();owner=workbench.Session(helper,story);owner.select(cid)
            case=deepcopy(owner.science()['case']);original=owner.view()['annotation']
            owner.save('Public or synthetic study review','Offline workflow exercise only.')
            for stage in order:
                owner.present(stage)
                before=helper.current()
                owner.view()
                if helper.current()!=before:raise AssertionError('Presentation dispatched an action')
                if stage=='check':owner.act('check')
                if stage=='actions':owner.act('synthetic')
            owner.history(original['hash']);owner.save('Public or synthetic review revisited','Branched from the first notes without changing evidence.')
            p=owner.export(owner.current()['hash']);text=owner.readable(owner.current()['hash'])
            if p['science']['case']!=case or len(p['annotations'])!=3:raise AssertionError('Source or history changed')
            if p['science']['accepted_review']['receipt']['provenance']!='synthetic_fixture':raise AssertionError('Missing synthetic label')
            if len(p['science']['accepted_review']['actions'])!=3:raise AssertionError('Three complete actions required')
            if p['science']['local_checks'][0]['result']['status']!='completed':raise AssertionError('Local check did not complete')
            if 'NOT REVIEWED' not in text:raise AssertionError('Human review limit missing')
            reopened=workbench.Session(assistant_workspace.Session(),research_story.Session());before=reopened.assistant.current()
            reopened.open(study.decode(study.canonical(p)))
            if reopened.export(reopened.current()['hash'])!=p or reopened.assistant.current()!=before:raise AssertionError('Reopen changed accepted records or executed work')
            try:reopened.act('check')
            except ValueError:pass
            else:raise AssertionError('Imported review allowed execution')
            stem=cid+'-'+str(number)
            (target/(stem+'.json')).write_text(study.canonical(p)+'\n')
            (target/(stem+'.md')).write_text(text)
            rows.append({'case_id':cid,'order':list(order),'status':'passed','annotation_revisions':3,
                         'local_audit_receipts':1,'proposals':3,'model_provenance':'synthetic_fixture','package_sha256':p['sha256']})
        request=assistant.prepare(cid)
        (target/(cid+'-unsent-muse-request.json')).write_text(study.canonical(request)+'\n')
    report={'status':'passed','journeys':rows,'journey_count':len(rows),'case_count':4,
            'live_provider_calls':0,'external_requests':0,'experimental_runs':0,'new_live_budget_usd':0,
            'qualification':'Offline software journeys over two public reference cases and two synthetic planning cases. Synthetic priorities are not real model calls or new scientific studies. All published evidence and unknowns remain unchanged.',
            'unsent_requests':'Four public/synthetic request previews only; 1024 output tokens each if separately approved later. No transport, retries, fallback, approval or spending is enabled.'}
    (target/'WORKFLOW_REPORT.json').write_text(study.canonical(report)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    sys.addaudithook(offline)
    try:
        report=exercise(args.output)
    except (ValueError,OSError,AssertionError) as exc:
        print('Offline workflow exercise stopped: '+str(exc),file=sys.stderr);raise SystemExit(1)
    print(study.canonical({k:v for k,v in report.items() if k!='journeys'}))
