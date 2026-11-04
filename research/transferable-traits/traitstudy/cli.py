import argparse
import json
from pathlib import Path
from .core import Store, canonical, digest, require
from .display import render
from .model import prepare, fake_transport, parse_candidate, unsigned_plan
from .pilot import synthetic_fixtures, groups, trail_plan
from .queue import Queue
from .retrieval import plan
from .workbook import inspect_workbook


def write(path,value):
    raw=value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(raw)
    temp.replace(path)


def pilot(output, limit=6):
    require(type(limit) is int and 1<=limit<=6,'Offline pilot limit must be 1–6')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    store=Store(output/'study.sqlite');queue=Queue(store)
    try:
        ids=[];packets=[]
        for record in synthetic_fixtures(store):
            oid=store.add_observation(record);ids.append(oid)
            packet=prepare(store,oid);packets.append(packet)
            queue.enqueue('offline_extract',{'observation_id':oid,'wire_sha256':packet['wire_sha256']})
        processed=0
        for _ in range(limit):
            job=queue.claim()
            if job is None:
                break
            try:
                packet=prepare(store,job['payload']['observation_id'])
                require(packet['wire_sha256']==job['payload']['wire_sha256'],'Checkpoint input changed')
                result=parse_candidate(fake_transport(packet),packet)
                queue.finish(job,'needs_review',{'candidate_sha256':digest(result),'transport':'synthetic_fake','muse_called':False})
                processed+=1
            except ValueError:
                queue.finish(job,'blocked',{'muse_called':False},'invalid_evidence')
                raise
        groups(store,ids)
        package=store.export()
        write(output/'atlas.json',package)
        write(output/'research-trails.json',trail_plan())
        write(output/'START_HERE.html',render(package,trail_plan()))
        write(output/'UNSIGNED_PILOT.json',unsigned_plan(packets))
        for i,packet in enumerate(packets,1):
            write(output/('REQUEST-%02d.json'%i),packet)
            (output/('WIRE-%02d.json'%i)).write_bytes(canonical(packet['body']).encode())
        summary={'mode':'synthetic_offline','processed_this_run':processed,
                 'jobs':len(package['queue']),'awaiting_review':sum(j['state']=='needs_review' for j in package['queue']),
                 'synthetic_observations':len(package['observations']),'real_cases_imported':0,
                 'muse_calls':0,'muse_cost_usd':0,'workbook_status':'blocked_not_materialized'}
        write(output/'SUMMARY.json',summary)
        return summary
    finally:
        store.close()


def main():
    parser=argparse.ArgumentParser(description='Offline Traitweaver study; no network or live mode')
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('pilot');p.add_argument('--output',required=True);p.add_argument('--limit',type=int,default=6)
    p=commands.add_parser('inspect-workbook');p.add_argument('path');p.add_argument('--output',required=True)
    p=commands.add_parser('retrieval-plan');p.add_argument('query')
    p=commands.add_parser('search');p.add_argument('--db',required=True);p.add_argument('query')
    p=commands.add_parser('review');p.add_argument('--db',required=True);p.add_argument('--id',required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--reviewer',required=True)
    p.add_argument('--decision',choices=['source_checked','needs_correction','rejected'],required=True);p.add_argument('--note',required=True)
    args=parser.parse_args()
    if args.command=='pilot':
        print(json.dumps(pilot(args.output,args.limit),indent=2))
    elif args.command=='inspect-workbook':
        result=inspect_workbook(args.path);write(Path(args.output),result)
        print(json.dumps({'status':result['status'],'sheets':[s['name'] for s in result['sheets']],'sha256':result['sha256']}))
    elif args.command=='retrieval-plan':
        print(json.dumps(plan(args.query),indent=2))
    else:
        require(Path(args.db).is_file(),'Database does not exist')
        store=Store(args.db)
        try:
            if args.command=='search':
                print(json.dumps(store.export(args.query),indent=2))
            else:
                store.review(args.id,args.sha256,args.reviewer,args.decision,args.note)
                print('Reviewer judgment saved; no scientific or laboratory approval implied.')
        finally:
            store.close()


if __name__=='__main__':
    main()
