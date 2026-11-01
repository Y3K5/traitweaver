"""Local evaluation CLI: synthetic controls, unsent previews and saved-file scoring.

No live flag, key access, provider client, retries or fallback exists here.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from traitweaver import assistant_evaluation as e, study


def offline(event,args):
    if event.startswith('socket.'):raise RuntimeError('Evaluation CLI forbids sockets')


def write(path,value):
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    path.write_text(text);path.chmod(0o600)


def export(folder,writer):
    folder=Path(folder).absolute()
    if any(p.is_symlink() for p in (folder,*folder.parents)):raise ValueError('Output path cannot traverse symlinks')
    folder=folder.resolve()
    if folder.exists() or not folder.parent.is_dir() or folder==ROOT or ROOT in folder.parents:raise ValueError('Fresh external output directory required')
    with tempfile.TemporaryDirectory(prefix='.traitweaver-evaluation-',dir=folder.parent) as tmp:
        staged=Path(tmp)/'output';staged.mkdir(mode=0o700);writer(staged)
        if folder.exists():raise ValueError('Output already exists; no overwrite')
        # mkdir is exclusive, so even concurrent exports cannot replace a result.
        folder.mkdir(mode=0o700)
        try:
            for item in staged.iterdir():shutil.move(str(item),str(folder/item.name))
        except (OSError,ValueError):
            # Preserve a partial destination for review; never overwrite/retry it.
            raise ValueError('Local export interrupted; existing files retained') from None
    return folder


def bundle_files(folder,package):
    e.reopen(package)
    write(folder/'evaluation.json',package);write(folder/'human-review.json',package['human_review'])
    write(folder/'REPORT.html',e.report_html(package))


def run_offline(output,historical=None):
    summaries={}
    def writer(folder):
        for kind in ('oracle','supplied_order','false_certainty'):
            records=[e.control(case['id'],perm,kind) for case in e.catalog()['cases'] for perm in range(3)]
            value=e.package(records);sub=folder/kind;sub.mkdir(mode=0o700);bundle_files(sub,value);summaries[kind]=value['summary']
        if historical is not None:write(folder/'SAVED_REAL_BATCH_REVIEW.json',e.historical_batch(historical))
        report={'schema_version':'traitweaver.evaluation_controls_report.v1','qualification':e.LIMIT,'cases':12,'families':6,'order_variants_per_case':3,'synthetic_control_responses':108,
                'new_model_calls':0,'model_usefulness_evaluated_live':False,'summaries':summaries,'human_usefulness':'not_reviewed','response_control_note':'Supplied-order control keeps correct authored claim labels constant to isolate ordering. Oracle is an authored reference fixture, not an AI or independent expert.'}
        write(folder/'CONTROL_REPORT.json',report)
        page='<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Traitweaver evaluation qualification</title><style>body{max-width:1000px;margin:35px auto;padding:20px;background:#02070a;color:#edf4f8;font:17px/1.65 system-ui}a,h1{color:#0297de}strong{color:#fc734d}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #28404d}</style><h1>Test useful plans, not just valid replies</h1><p><strong>OFFLINE SYNTHETIC CONTROLS ONLY — no new Muse calls.</strong></p><p>12 scenarios in six paired research areas; three action orders each. 108 synthetic control responses test the scorer. These are not 108 model calls or biological studies. Expected judgments are excluded from model inputs; open authored criteria remain inspectable.</p><table><tr><th>Control</th><th>First action matches rubric</th><th>Claim labels match rubric</th><th>Human usefulness</th></tr>'
        for kind,summary in summaries.items():page+='<tr><td><a href="'+kind+'/REPORT.html">'+kind+'</a></td><td>'+str(summary['first_action_rubric_matches'])+'/36</td><td>'+str(summary['claim_verdict_rubric_matches'])+'/108</td><td>NOT REVIEWED</td></tr>'
        page+='</table><p>High priority agreement cannot rescue false certainty. Citation validity cannot establish source entailment. Missing pair members remain unscored, never zero or a pass.</p><p><a href="CONTROL_REPORT.json">Exact metrics and pair/order comparisons</a></p>'
        if historical is not None:page+='<p><a href="SAVED_REAL_BATCH_REVIEW.json">Read-only review of the four saved real Muse replies</a>: old action order is preserved; order bias and deeper usefulness remain untested.</p>'
        write(folder/'START_HERE.html',page)
    export(output,writer)
    return {'status':'offline_controls_completed','synthetic_responses':108,'new_model_calls':0,'reference_first_action_matches':summaries['oracle']['first_action_rubric_matches'],
            'supplied_order_first_action_matches':summaries['supplied_order']['first_action_rubric_matches'],'false_certainty_successes_withheld':summaries['false_certainty']['unsupported_successes_withheld'],'human_usefulness':'not_reviewed'}


class SafeParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,'Invalid evaluation arguments. Use --help; never pass credentials. No sending is available.\n')


def main(argv=None):
    parser=SafeParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('offline');p.add_argument('--output',type=Path,required=True);p.add_argument('--saved-batch',type=Path)
    p=sub.add_parser('prepare');p.add_argument('--case',required=True);p.add_argument('--permutation',type=int,default=0)
    p=sub.add_parser('score');p.add_argument('--case',required=True);p.add_argument('--permutation',type=int,default=0);p.add_argument('--reply',type=Path,required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('reopen');p.add_argument('--package',type=Path,required=True)
    p=sub.add_parser('review');p.add_argument('--package',type=Path,required=True);p.add_argument('--human-review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.mode=='prepare':value=e.prepare(args.case,args.permutation)
        elif args.mode=='offline':value=run_offline(args.output,args.saved_batch)
        elif args.mode=='reopen':value=e.reopen(e.read_json(args.package))['summary']
        elif args.mode=='score':
            if args.reply.is_symlink() or args.reply.stat().st_size>e.MAX_BYTES:raise ValueError('Unsafe reply')
            record=e.parse_reply(args.case,args.permutation,args.reply.read_bytes(),args.request_sha256)
            package=e.package([record]);export(args.output,lambda folder:bundle_files(folder,package));value=package['summary']
        else:
            old=e.reopen(e.read_json(args.package));package=e.package(old['results'],e.read_json(args.human_review))
            export(args.output,lambda folder:bundle_files(folder,package));value={'status':'local_human_review_saved','human_review_status':package['human_review']['status'],'new_model_calls':0}
        print(study.canonical(value));return 0
    except (OSError,ValueError,TypeError,KeyError):
        print('Evaluation refused: invalid source, request, result, review or output location. No provider call or retry occurred; existing records remain.',file=sys.stderr);return 2


if __name__=='__main__':
    sys.addaudithook(offline)
    raise SystemExit(main())
