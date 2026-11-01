"""Offline-only assistant review CLI. No provider transport or credentials."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traitweaver import assistant, study


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--synthetic',metavar='CASE_ID',help='Explicitly generate a labelled synthetic review')
    mode.add_argument('--prepare',metavar='CASE_ID',help='Print a not-sent screened request; this CLI never sends')
    mode.add_argument('--reopen',type=Path,help='Read-only reopen of an assistant-review.json package')
    parser.add_argument('--output',type=Path,help='Fresh external directory for synthetic JSON/text export')
    args=parser.parse_args(argv)
    if args.output and not args.synthetic:
        parser.error('--output requires --synthetic; reopen is read-only')
    try:
        if args.prepare:
            print(study.canonical(assistant.prepare(args.prepare)))
            return 0
        if args.reopen:
            record=assistant.reopen(args.reopen)
        else:
            preview=assistant.prepare(args.synthetic)
            raw=study.canonical(assistant.synthetic_reply(args.synthetic)).encode()
            record=assistant.parse_reply(args.synthetic,raw,preview['request_sha256'])
            if args.output:
                assistant.export_bundle(record,args.output)
        print(assistant.readable(record),end='')
        return 0
    except (OSError,ValueError):
        print('Assistant review refused: invalid case, package, response or output directory. No live request was made.',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
